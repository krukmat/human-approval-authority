import XCTest
@testable import HAAApprover

final class ModelsTests: XCTestCase {
    func testBase64URLRoundTrip() throws {
        let original = Data([0x00, 0x01, 0xFE, 0xFF])
        let encoded = original.base64URLEncodedString()
        XCTAssertFalse(encoded.contains("="))
        XCTAssertEqual(Data(base64URL: encoded), original)
    }

    func testPublicKeyPEMHasSeparatedFooter() throws {
        let der = Data((0..<96).map { UInt8($0 % 256) })
        let pem = encodePublicKeyPEM(der)
        XCTAssertTrue(pem.hasPrefix("-----BEGIN PUBLIC KEY-----\n"))
        XCTAssertTrue(pem.hasSuffix("\n-----END PUBLIC KEY-----\n"))
        XCTAssertFalse(pem.contains("A-----END PUBLIC KEY-----"))
    }
}
