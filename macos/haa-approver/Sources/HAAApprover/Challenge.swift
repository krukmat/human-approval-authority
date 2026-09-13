import Foundation
#if os(macOS)
import CryptoKit
import Security
#endif

struct VerifiedChallenge {
    let package: ChallengePackage
    let payload: ChallengePayload
    let payloadBytes: Data
    let digest: String
}

func isChallengeExpired(_ challenge: VerifiedChallenge, now: Date = Date()) -> Bool {
    guard let expiresAt = ISO8601DateFormatter().date(from: challenge.payload.expiresAt) else { return true }
    return expiresAt <= now
}

#if os(macOS)
private let p256SPKIPrefix = Data([0x30,0x59,0x30,0x13,0x06,0x07,0x2A,0x86,0x48,0xCE,0x3D,0x02,0x01,0x06,0x08,0x2A,0x86,0x48,0xCE,0x3D,0x03,0x01,0x07,0x03,0x42,0x00])

func rawP256PublicKey(fromPEM pem: String) throws -> Data {
    guard let der = pemBody(pem), der.starts(with: p256SPKIPrefix), der.count == p256SPKIPrefix.count + 65 else {
        throw NSError(domain: "HAA", code: 1, userInfo: [NSLocalizedDescriptionKey: "Unsupported HAA public key format"])
    }
    return der.dropFirst(p256SPKIPrefix.count)
}

func verifyChallenge(_ package: ChallengePackage, authorityPublicKeyPEM: String) throws -> VerifiedChallenge {
    guard package.schema == "haa.challenge.v1", package.signatureAlgorithm == "ES256",
          let payloadBytes = Data(base64URL: package.payload),
          let signature = Data(base64URL: package.signature) else {
        throw NSError(domain: "HAA", code: 2, userInfo: [NSLocalizedDescriptionKey: "Invalid challenge envelope"])
    }
    let rawKey = try rawP256PublicKey(fromPEM: authorityPublicKeyPEM)
    let attrs: [CFString: Any] = [
        kSecAttrKeyType: kSecAttrKeyTypeECSECPrimeRandom,
        kSecAttrKeyClass: kSecAttrKeyClassPublic,
        kSecAttrKeySizeInBits: 256
    ]
    var error: Unmanaged<CFError>?
    guard let key = SecKeyCreateWithData(rawKey as CFData, attrs as CFDictionary, &error) else {
        throw error?.takeRetainedValue() ?? NSError(domain: "HAA", code: 3)
    }
    guard SecKeyVerifySignature(key, .ecdsaSignatureMessageX962SHA256, payloadBytes as CFData, signature as CFData, &error) else {
        throw error?.takeRetainedValue() ?? NSError(domain: "HAA", code: 4, userInfo: [NSLocalizedDescriptionKey: "Invalid HAA signature"])
    }
    let payload = try JSONDecoder().decode(ChallengePayload.self, from: payloadBytes)
    guard payload.schema == "haa.challenge-payload.v1", payload.protocolVersion == 1 else {
        throw NSError(domain: "HAA", code: 5, userInfo: [NSLocalizedDescriptionKey: "Unsupported challenge payload"])
    }
    let hash = SHA256.hash(data: payloadBytes)
    let digest = "sha256:" + Data(hash).base64URLEncodedString()
    return VerifiedChallenge(package: package, payload: payload, payloadBytes: payloadBytes, digest: digest)
}
#else
func verifyChallenge(_ package: ChallengePackage, authorityPublicKeyPEM: String) throws -> VerifiedChallenge {
    throw NSError(domain: "HAA", code: 100, userInfo: [NSLocalizedDescriptionKey: "Secure challenge verification is macOS-only"])
}
#endif
