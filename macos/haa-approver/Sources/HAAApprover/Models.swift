import Foundation

struct DisplayClaim: Decodable {
    let label: String
    let value: String
    let emphasis: String?
}

struct ChallengePayload: Decodable {
    let schema: String
    let protocolVersion: Int
    let requestId: String
    let actionType: String
    let actionDigest: String
    let intentDigest: String
    let nonce: String
    let approverPrincipalId: String
    let authenticatorId: String
    let executorAudience: String
    let policySnapshotHash: String
    let displayClaims: [DisplayClaim]
    let issuedAt: String
    let expiresAt: String
}

struct ChallengePackage: Decodable {
    let schema: String
    let payload: String
    let authorityKeyId: String
    let signatureAlgorithm: String
    let signature: String
}

struct ApprovalEvidence: Encodable {
    let schema = "haa.evidence.v1"
    let type = "apple-secure-enclave"
    let authenticatorId: String
    let requestId: String
    let challengeDigest: String
    let signatureAlgorithm = "ES256"
    let signature: String
}

extension Data {
    init?(base64URL: String) {
        var s = base64URL.replacingOccurrences(of: "-", with: "+").replacingOccurrences(of: "_", with: "/")
        s += String(repeating: "=", count: (4 - s.count % 4) % 4)
        self.init(base64Encoded: s)
    }
    func base64URLEncodedString() -> String {
        base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "")
    }
}

func pemBody(_ pem: String) -> Data? {
    let body = pem.split(separator: "\n").filter { !$0.hasPrefix("---") }.joined()
    return Data(base64Encoded: body)
}
