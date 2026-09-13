import Foundation
#if os(macOS)
import AppKit
#endif

#if os(macOS)
@MainActor
func askForApproval(_ payload: ChallengePayload, timeoutSeconds: TimeInterval? = nil) -> CeremonyDecision {
    NSApplication.shared.setActivationPolicy(.accessory)
    NSApplication.shared.activate()

    let alert = NSAlert()
    alert.alertStyle = .critical
    alert.messageText = "Human Approval Authority"
    let lines = payload.displayClaims.map { "\($0.label): \($0.value)" }
    alert.informativeText = lines.joined(separator: "\n")
        + "\n\nRequest: \(payload.requestId)"
        + "\n\nEsc: Reject"
    alert.addButton(withTitle: "Approve with Touch ID")

    var rejectionReason: RejectionReason?
    let monitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
        if event.keyCode == 53 { // Escape
            rejectionReason = .userEscape
            NSApp.abortModal()
            alert.window.orderOut(nil)
            return nil
        }
        return event
    }
    defer {
        if let monitor { NSEvent.removeMonitor(monitor) }
    }

    if let timeoutSeconds, timeoutSeconds > 0 {
        DispatchQueue.main.asyncAfter(deadline: .now() + timeoutSeconds) {
            guard NSApp.modalWindow === alert.window else { return }
            rejectionReason = .timeout
            NSApp.abortModal()
            alert.window.orderOut(nil)
        }
    }

    let response = alert.runModal()
    if let rejectionReason { return .reject(rejectionReason) }
    if response == .alertFirstButtonReturn { return .approve }
    return .reject(.windowClosed)
}
#else
func askForApproval(_ payload: ChallengePayload, timeoutSeconds: TimeInterval? = nil) -> CeremonyDecision {
    .reject(.interactionError)
}
#endif
