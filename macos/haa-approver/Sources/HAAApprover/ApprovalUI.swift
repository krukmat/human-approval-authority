import Foundation
#if os(macOS)
import AppKit
#endif

#if os(macOS)
@MainActor
func askForApproval(_ payload: ChallengePayload) -> Bool {
    NSApplication.shared.setActivationPolicy(.accessory)
    NSApplication.shared.activate()
    let alert = NSAlert()
    alert.alertStyle = .critical
    alert.messageText = "Human Approval Authority"
    let lines = payload.displayClaims.map { "\($0.label): \($0.value)" }
    alert.informativeText = lines.joined(separator: "\n") + "\n\nRequest: \(payload.requestId)"
    alert.addButton(withTitle: "Approve with Touch ID")
    alert.addButton(withTitle: "Reject")
    return alert.runModal() == .alertFirstButtonReturn
}
#else
func askForApproval(_ payload: ChallengePayload) -> Bool { false }
#endif
