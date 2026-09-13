# macOS Touch ID runbook

W3 cannot pass without a real Mac with Touch ID / Secure Enclave.

## Why the approver is wrapped as an app

The Touch ID-protected Secure Enclave key lives in the macOS Data Protection Keychain. Apple derives access to that keychain from code-signing entitlements that must be authorized by a provisioning profile. A standalone Swift command-line executable has nowhere to embed that profile, so the validation path compiles the same HAA approver sources into a minimal app-like bundle and executes its binary from `HAAApprover.app/Contents/MacOS/HAAApprover`.

The wrapper does not change the HAA protocol or turn the approver into a general desktop application. It exists only to establish a valid macOS application identity for the Secure Enclave/keychain boundary.

## Preferred validation

From the repository root on the target Mac:

```bash
npm install
npm run validate:macos
npm run validate:agent-macos
```

The validation helper automatically:

- uses `HAA_APPLE_TEAM_ID` when provided;
- otherwise detects a single `Apple Development` signing identity in the login keychain;
- uses the active full Xcode installation, or `/Applications/Xcode.app` when `xcode-select` points only to Command Line Tools;
- invokes Xcode automatic signing/provisioning for the minimal approver app;
- verifies the resulting code signature, provisioning profile and application/keychain entitlements before creating the Secure Enclave key.

If multiple development teams exist, set:

```bash
export HAA_APPLE_TEAM_ID=XXXXXXXXXX
```

An alternate bundle identifier can be supplied with `HAA_APPLE_BUNDLE_ID` if required.

## W3-T06 gate

`npm run validate:macos` performs the full Apple authenticator gate:

1. Starts an isolated HAA server with temporary SQLite storage and authority key.
2. Builds and provisions the app-like macOS approver wrapper.
3. Creates a new device-bound Secure Enclave P-256 key protected by the current biometric set.
4. Registers the authenticator with HAA.
5. Creates an exact `demo.action.v1` approval request and signed challenge.
6. Launches the native trusted presentation and Touch ID approval.
7. Submits the signed `ApprovalEvidence` and verifies an `ApprovalReceipt` is issued.
8. Confirms a mutated action is denied with `ACTION_DIGEST_MISMATCH`.
9. Confirms stale resource state is denied with `STALE_APPROVAL` without consuming the approval.
10. Authorizes the exact action, confirms idempotent retry, denies a second execution ID, and verifies the audit lifecycle.

Success ends with:

```text
PASS W3-T06: Apple Secure Enclave / Touch ID end-to-end gate
```

`npm run validate:agent-macos` then runs the stronger W4-T05 scenario: MCP requester → human Touch ID → external bounded executor.

The scripts use a unique authenticator ID each run. Keys are device-bound and are not exported; the validation key and temporary server state are removed at the end.

## W8-T09 final physical ceremony gate

W8 adds the terminal ceremony invariant:

```text
Touch ID success       -> APPROVE
Esc                    -> REJECT / USER_ESCAPE
window close           -> REJECT / WINDOW_CLOSED
timeout                -> REJECT / TIMEOUT
challenge expiry       -> REJECT / CHALLENGE_EXPIRED
terminal interaction   -> REJECT / INTERACTION_ERROR
```

Only the APPROVE path may produce positive evidence / receipt / execution authority. The negative paths do not require Touch ID and do not claim biometric rejection.

W8-T09 must be run only after W7-T15 closes. The exact physical acceptance matrix and evidence fields are in `docs/W8-PHYSICAL-CEREMONY-GATE.md`.

## Requirements

- macOS host with Secure Enclave and Touch ID configured.
- Full Xcode installed, not only Command Line Tools.
- Apple ID signed into Xcode with an Apple Development certificate available for the selected team.
- Node.js 24+ recommended and required by the project engine contract.
- Port `8791`/`8792` free, or set `HAA_VALIDATION_PORT` to another local port.

If Xcode signing has never been configured on the machine, open **Xcode → Settings → Accounts**, add the Apple ID/team and create an Apple Development certificate before rerunning the gate.

## Failure diagnostics

`OSStatus -34018` means `errSecMissingEntitlement`. For this project it indicates that the approver was executed without a provisioned application identity suitable for the Data Protection Keychain. Do not work around it by weakening the key access-control flags or by moving the signing key out of Secure Enclave; fix the signing/provisioning context instead.

Useful checks on the built wrapper:

```bash
codesign -d --entitlements :- /path/to/HAAApprover.app
security cms -D -i /path/to/HAAApprover.app/Contents/embedded.provisionprofile
```

The signed app must expose an application identifier and keychain access group authorized by the embedded profile.
