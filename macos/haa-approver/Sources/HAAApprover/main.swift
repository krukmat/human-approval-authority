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

func emitReject(_ verified: VerifiedChallenge, reason: RejectionReason) throws -> Never {
    try printJSON(CeremonyResultOutput.reject(requestId: verified.payload.requestId, challengeDigest: verified.digest, reason: reason))
    exit(3)
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
    let output: [String: Any] = ["id": authenticatorId, "type": "apple-secure-enclave", "publicKeyPem": publicKey, "signatureAlgorithm": "ES256"]
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
if isChallengeExpired(verified) { try emitReject(verified, reason: .challengeExpired) }

// Single-popup ceremony experiment: skip the HAA NSAlert and let the native
// macOS authentication dialog be the only interactive UI. The prompt is built
// exclusively from the verified, authority-signed display claims.
let promptLines = verified.payload.displayClaims.map { "\($0.label): \($0.value)" }
let approvalPrompt = (["Human Approval Authority"] + promptLines).joined(separator: "\n")

do {
    let signature = try authenticator.signApprovalDigest(
        verified.digest,
        prompt: approvalPrompt
    )
    let evidence = ApprovalEvidence(
        authenticatorId: authenticatorId,
        requestId: verified.payload.requestId,
        challengeDigest: verified.digest,
        signature: signature
    )
    try printJSON(evidence)
    exit(0)
} catch {
    // Protocol v1 has no USER_CANCEL reason. A user cancellation in the native
    // macOS authentication dialog therefore remains fail-closed as
    // INTERACTION_ERROR for this UX experiment.
    try emitReject(verified, reason: .interactionError)
}
