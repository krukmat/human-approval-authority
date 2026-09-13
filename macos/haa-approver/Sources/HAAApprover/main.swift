import Foundation

func arg(_ name: String) -> String? {
    guard let i = CommandLine.arguments.firstIndex(of: name), i + 1 < CommandLine.arguments.count else { return nil }
    return CommandLine.arguments[i + 1]
}

let authenticatorId = arg("--authenticator-id") ?? "mac-default"
let authenticator = SecureEnclaveAuthenticator(authenticatorId: authenticatorId)

if CommandLine.arguments.contains("--delete") {
    try authenticator.delete()
    print("deleted \(authenticatorId)")
    exit(0)
}

if CommandLine.arguments.contains("--enroll") {
    let publicKey = try authenticator.enroll()
    let output: [String: Any] = [
        "id": authenticatorId,
        "type": "apple-secure-enclave",
        "publicKeyPem": publicKey,
        "signatureAlgorithm": "ES256"
    ]
    let data = try JSONSerialization.data(withJSONObject: output, options: [.prettyPrinted, .sortedKeys])
    print(String(decoding: data, as: UTF8.self))
    exit(0)
}

guard let challengePath = arg("--challenge"), let authorityKeyPath = arg("--authority-public-key") else {
    FileHandle.standardError.write(Data("usage: haa-approver --enroll --authenticator-id <id> | --delete --authenticator-id <id> | --challenge <json> --authority-public-key <pem> --authenticator-id <id>\n".utf8))
    exit(2)
}
let challengeData = try Data(contentsOf: URL(fileURLWithPath: challengePath))
let package = try JSONDecoder().decode(ChallengePackage.self, from: challengeData)
let authorityPEM = try String(contentsOfFile: authorityKeyPath, encoding: .utf8)
let verified = try verifyChallenge(package, authorityPublicKeyPEM: authorityPEM)
guard verified.payload.authenticatorId == authenticatorId else { throw NSError(domain: "HAA", code: 20, userInfo: [NSLocalizedDescriptionKey: "Authenticator mismatch"]) }
guard await askForApproval(verified.payload) else { exit(3) }
let signature = try authenticator.signApprovalDigest(verified.digest, prompt: "Approve HAA request \(verified.payload.requestId)")
let evidence = ApprovalEvidence(authenticatorId: authenticatorId, requestId: verified.payload.requestId, challengeDigest: verified.digest, signature: signature)
let out = try JSONEncoder().encode(evidence)
print(String(decoding: out, as: UTF8.self))
