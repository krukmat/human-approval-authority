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
        let result = CeremonyResultOutput.reject(
            requestId: "req-1",
            challengeDigest: "sha256:abc",
            reason: .userEscape
        )
        let data = try JSONEncoder().encode(result)
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: String])
        XCTAssertEqual(json["outcome"], "REJECT")
        XCTAssertEqual(json["reason"], "USER_ESCAPE")
        XCTAssertEqual(json["requestId"], "req-1")
        XCTAssertEqual(json["challengeDigest"], "sha256:abc")
    }

    func testEveryTerminalFailureOutputIsReject() throws {
        let reasons: [RejectionReason] = [
            .windowClosed,
            .timeout,
            .challengeExpired,
            .interactionError
        ]

        for reason in reasons {
            let result = CeremonyResultOutput.reject(
                requestId: "req-terminal",
                challengeDigest: "sha256:def",
                reason: reason
            )
            let data = try JSONEncoder().encode(result)
            let json = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: String])
            XCTAssertEqual(json["outcome"], "REJECT")
            XCTAssertEqual(json["reason"], reason.rawValue)
            XCTAssertEqual(json["requestId"], "req-terminal")
            XCTAssertEqual(json["challengeDigest"], "sha256:def")
        }
    }

    func testISO8601ParserAcceptsNodeFractionalAndStandardTimestamps() throws {
        XCTAssertNotNil(parseISO8601("2026-09-13T07:00:00.000Z"))
        XCTAssertNotNil(parseISO8601("2026-09-13T07:00:00Z"))
        XCTAssertNil(parseISO8601("not-a-date"))
    }
}
