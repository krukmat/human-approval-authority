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

    func testRejectOutputIsExplicitAndChallengeBound() throws {
        let result = CeremonyResultOutput.reject(requestId: "req-1", challengeDigest: "sha256:abc")
        let data = try JSONEncoder().encode(result)
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: String])
        XCTAssertEqual(json["outcome"], "REJECT")
        XCTAssertEqual(json["reason"], "USER_ESCAPE")
        XCTAssertEqual(json["requestId"], "req-1")
        XCTAssertEqual(json["challengeDigest"], "sha256:abc")
    }

    func testUnknownOutputDoesNotPretendHumanRejection() throws {
        let result = CeremonyResultOutput.unknown(requestId: "req-2", challengeDigest: "sha256:def", reason: .localTimeout)
        let data = try JSONEncoder().encode(result)
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: String])
        XCTAssertEqual(json["outcome"], "UNKNOWN")
        XCTAssertEqual(json["reason"], "LOCAL_TIMEOUT")
        XCTAssertEqual(json["requestId"], "req-2")
    }
}
