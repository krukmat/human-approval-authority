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

    var explicitReject = false
    var timedOut = false
    let monitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
        if event.keyCode == 53 { // Escape
            explicitReject = true
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
            timedOut = true
            NSApp.abortModal()
            alert.window.orderOut(nil)
        }
    }

    let response = alert.runModal()
    if explicitReject { return .reject }
    if timedOut { return .unknown(.localTimeout) }
    if response == .alertFirstButtonReturn { return .approve }
    return .unknown(.windowClosed)
}
#else
func askForApproval(_ payload: ChallengePayload, timeoutSeconds: TimeInterval? = nil) -> CeremonyDecision {
    .unknown(.interactionError)
}
#endif
