import Foundation
#if os(macOS)
import Security
#endif

#if os(macOS)
final class SecureEnclaveAuthenticator {
    private let tag: Data
    private let p256SPKIPrefix = Data([0x30,0x59,0x30,0x13,0x06,0x07,0x2A,0x86,0x48,0xCE,0x3D,0x02,0x01,0x06,0x08,0x2A,0x86,0x48,0xCE,0x3D,0x03,0x01,0x07,0x03,0x42,0x00])

    init(authenticatorId: String) { self.tag = Data("com.haa.approver.\(authenticatorId)".utf8) }

    func enroll() throws -> String {
        var acError: Unmanaged<CFError>?
        guard let access = SecAccessControlCreateWithFlags(
            kCFAllocatorDefault,
            kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
            [.privateKeyUsage, .biometryCurrentSet],
            &acError
        ) else { throw acError!.takeRetainedValue() }
        let attributes: [CFString: Any] = [
            kSecAttrKeyType: kSecAttrKeyTypeECSECPrimeRandom,
            kSecAttrKeySizeInBits: 256,
            kSecAttrTokenID: kSecAttrTokenIDSecureEnclave,
            kSecPrivateKeyAttrs: [
                kSecAttrIsPermanent: true,
                kSecAttrApplicationTag: tag,
                kSecAttrAccessControl: access
            ]
        ]
        var error: Unmanaged<CFError>?
        guard let privateKey = SecKeyCreateRandomKey(attributes as CFDictionary, &error),
              let publicKey = SecKeyCopyPublicKey(privateKey),
              let raw = SecKeyCopyExternalRepresentation(publicKey, &error) as Data? else {
            throw error?.takeRetainedValue() ?? NSError(domain: "HAA", code: 11)
        }
        guard raw.count == 65 else { throw NSError(domain: "HAA", code: 12, userInfo: [NSLocalizedDescriptionKey: "Unexpected P-256 public key size"]) }
        return pem(spki: p256SPKIPrefix + raw)
    }

    func publicKeyPEM() throws -> String {
        let key = try loadPrivateKey(prompt: nil)
        var error: Unmanaged<CFError>?
        guard let publicKey = SecKeyCopyPublicKey(key), let raw = SecKeyCopyExternalRepresentation(publicKey, &error) as Data? else {
            throw error?.takeRetainedValue() ?? NSError(domain: "HAA", code: 13)
        }
        return pem(spki: p256SPKIPrefix + raw)
    }

    func signApprovalDigest(_ digest: String, prompt: String) throws -> String {
        let key = try loadPrivateKey(prompt: prompt)
        var error: Unmanaged<CFError>?
        guard let signature = SecKeyCreateSignature(key, .ecdsaSignatureMessageX962SHA256, Data(digest.utf8) as CFData, &error) as Data? else {
            throw error?.takeRetainedValue() ?? NSError(domain: "HAA", code: 14)
        }
        return signature.base64URLEncodedString()
    }

    private func loadPrivateKey(prompt: String?) throws -> SecKey {
        var query: [CFString: Any] = [
            kSecClass: kSecClassKey,
            kSecAttrApplicationTag: tag,
            kSecAttrKeyType: kSecAttrKeyTypeECSECPrimeRandom,
            kSecReturnRef: true
        ]
        if let prompt { query[kSecUseOperationPrompt] = prompt }
        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        guard status == errSecSuccess, let key = item as! SecKey? else {
            throw NSError(domain: NSOSStatusErrorDomain, code: Int(status))
        }
        return key
    }

    private func pem(spki: Data) -> String {
        let b64 = spki.base64EncodedString(options: [.lineLength64Characters, .endLineWithLineFeed])
        return "-----BEGIN PUBLIC KEY-----\n\(b64)-----END PUBLIC KEY-----\n"
    }
}
#else
final class SecureEnclaveAuthenticator {
    init(authenticatorId: String) {}
    func enroll() throws -> String { throw NSError(domain: "HAA", code: 100) }
    func publicKeyPEM() throws -> String { throw NSError(domain: "HAA", code: 100) }
    func signApprovalDigest(_ digest: String, prompt: String) throws -> String { throw NSError(domain: "HAA", code: 100) }
}
#endif
