import XCTest
@testable import HAAApprover

final class ModelsTests: XCTestCase {
    func testBase64URLRoundTrip() throws {
        let original = Data([0x00, 0x01, 0xFE, 0xFF])
        let encoded = original.base64URLEncodedString()
        XCTAssertFalse(encoded.contains("="))
        XCTAssertEqual(Data(base64URL: encoded), original)
    }
}
