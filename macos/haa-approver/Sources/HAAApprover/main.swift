import Foundation

func arg(_ name: String) -> String? {
    guard let i = CommandLine.arguments.firstIndex(of: name), i + 1 < CommandLine.arguments.count else { return nil }
    return CommandLine.arguments[i + 1]
}

func printJSON<T: Encodable>(_ value: T) throws {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    let data = try encoder.encode(value)
    print(String(decoding: data, as: UTF8.self))
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
    FileHandle.standardError.write(Data("usage: haa-approver --enroll --authenticator-id <id> | --delete --authenticator-id <id> | --challenge <json> --authority-public-key <pem> --authenticator-id <id> [--timeout-seconds <seconds>]\n".utf8))
    exit(2)
}
let challengeData = try Data(contentsOf: URL(fileURLWithPath: challengePath))
let package = try JSONDecoder().decode(ChallengePackage.self, from: challengeData)
let authorityPEM = try String(contentsOfFile: authorityKeyPath, encoding: .utf8)
let verified = try verifyChallenge(package, authorityPublicKeyPEM: authorityPEM)
guard verified.payload.authenticatorId == authenticatorId else { throw NSError(domain: "HAA", code: 20, userInfo: [NSLocalizedDescriptionKey: "Authenticator mismatch"]) }
let timeoutSeconds = arg("--timeout-seconds").flatMap(TimeInterval.init)

switch await askForApproval(verified.payload, timeoutSeconds: timeoutSeconds) {
case .approve:
    do {
        let signature = try authenticator.signApprovalDigest(verified.digest, prompt: "Approve HAA request \(verified.payload.requestId)")
        let evidence = ApprovalEvidence(authenticatorId: authenticatorId, requestId: verified.payload.requestId, challengeDigest: verified.digest, signature: signature)
        try printJSON(evidence)
        exit(0)
    } catch {
        try printJSON(CeremonyResultOutput.unknown(requestId: verified.payload.requestId, challengeDigest: verified.digest, reason: .authenticatorUnavailable))
        exit(4)
    }
case .reject:
    try printJSON(CeremonyResultOutput.reject(requestId: verified.payload.requestId, challengeDigest: verified.digest))
    exit(3)
case .unknown(let reason):
    try printJSON(CeremonyResultOutput.unknown(requestId: verified.payload.requestId, challengeDigest: verified.digest, reason: reason))
    exit(4)
}
