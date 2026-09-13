# W8-T09 physical macOS ceremony and compatibility gate

Status: **DONE**

This is the final HAA-only physical validation after the software production-readiness gate. It runs on a provisioned Apple Silicon Mac with Touch ID and validates the actual trusted-display / Secure Enclave boundary.

It does not depend on DubBridge or any product integration.

## Validated baseline

```text
Validated SHA: 1bec7bb76f0bb7119045bea6d59ed896364e2895
Validation date: 2026-09-13
macOS: 26.5.2
Node: v24.21.0
Physical Secure Enclave / Touch ID path: PASS
Operator-confirmed final W8 rerun: PASS
```

The uploaded aggregate validation log demonstrated the W3/W4 physical positive paths, W8 APPROVE and TIMEOUT paths, and correct provisioning/signing. The first aggregate run contained operator-input mismatches for `escape` versus `window-close` and ended while waiting for challenge expiry. Those rows were rerun after the UX was made deterministic (`Esc` for `USER_ESCAPE`, `⌘W` for `WINDOW_CLOSED`). The operator confirmed the final rerun completed successfully. This closure records that operator-confirmed physical evidence rather than treating the earlier incomplete aggregate log as the final result.

## Preconditions

- W8-T08 automated ceremony matrix is green.
- W7-T15 is DONE on the commit being validated.
- Apple Silicon Mac with Touch ID configured.
- Full Xcode and valid Apple Development provisioning context.
- HAA approver app wrapper builds and its provisioning/signing identity verifies.
- No reuse of development/test software evidence as a substitute for the Secure Enclave path.

## HAA-only ceremony orchestrator

The repository contains `scripts/validate-macos-ceremony-e2e.mjs`, exposed as:

```bash
npm run validate:macos-ceremony -- --case <case>
```

Supported physical cases:

```text
approve
escape
window-close
timeout
challenge-expired
```

For each case the orchestrator creates an isolated HAA server, provisions/enrolls a fresh Secure Enclave authenticator, creates the exact request/challenge, runs the macOS approver, submits APPROVE evidence or the typed REJECT result, and validates the resulting execution-authority boundary.

`interaction-error` is intentionally not auto-manufactured because the gate must not weaken keychain/Secure Enclave controls merely to trigger an error.

## Gate 1 — Positive ceremony

Commands:

```bash
npm ci
npm run validate:macos
npm run validate:macos-ceremony -- --case approve
```

Validated behavior:

```text
trusted signed display
  -> successful Touch ID
  -> apple-secure-enclave ApprovalEvidence
  -> ApprovalReceipt
  -> exact authorizeAndConsume
  -> usable ExecutionGrant
```

The W3 invariants remained valid:

- mutated action denied;
- stale precondition denied without consumption;
- same execution ID idempotent;
- different execution ID denied after consume.

Result: `PASS`

## Gate 2 — Escape rejection

Command:

```bash
npm run validate:macos-ceremony -- --case escape
```

Physical interaction: press `Esc` when the trusted HAA ceremony is shown.

Validated behavior:

```text
outcome=REJECT
reason=USER_ESCAPE
state=REJECTED
assurance=explicit-human-negative-action
ExecutionGrant impossible
```

Result: `PASS` — operator-confirmed final rerun.

## Gate 3 — Window close rejection

Command:

```bash
npm run validate:macos-ceremony -- --case window-close
```

Physical interaction: press `⌘W` while the trusted HAA ceremony is active. If macOS exposes a standard close control for the alert, that control is equivalent. HAA captures `⌘W` explicitly so this gate does not depend on `NSAlert` exposing a red close button.

Validated behavior:

```text
outcome=REJECT
reason=WINDOW_CLOSED
state=REJECTED
audit assurance=fail-closed-terminal
ExecutionGrant impossible
```

`⌘W` is treated as a deterministic window-close gesture. It is still `fail-closed-terminal`, not proof that the human explicitly selected Reject.

Result: `PASS` — physically observed and operator-confirmed.

## Gate 4 — Local timeout rejection

Command:

```bash
npm run validate:macos-ceremony -- --case timeout
```

Validated behavior:

```text
outcome=REJECT
reason=TIMEOUT
state=REJECTED
audit assurance=fail-closed-terminal
ExecutionGrant impossible
```

Result: `PASS`

## Gate 5 — Challenge-expiry rejection

Command:

```bash
npm run validate:macos-ceremony -- --case challenge-expired
```

The orchestrator waits until the HAA-signed challenge expires while its parent request remains valid, then launches the approver.

Validated behavior:

```text
challenge signature/bindings still verify
local expiry classification=CHALLENGE_EXPIRED
server verifies the challenge is actually expired
state=REJECTED
audit assurance=fail-closed-terminal
ExecutionGrant impossible
```

A live challenge mislabeled `CHALLENGE_EXPIRED` remains covered by automated adversarial tests and is denied.

Result: `PASS` — operator-confirmed final rerun.

## Gate 6 — Terminal interaction failure

Expected behavior remains:

```text
outcome=REJECT
reason=INTERACTION_ERROR
assurance=fail-closed-terminal
no positive evidence
no receipt/grant
```

A safe deterministic physical reproduction was not required because manufacturing it would require weakening or deliberately disturbing the local trust environment. Automated coverage remains the acceptance evidence for this reason.

Result: `N/A PHYSICAL — AUTOMATED COVERAGE ACCEPTED`

## Gate 7 — Regression compatibility

Command:

```bash
npm run validate:agent-macos
```

Validated existing W4 result:

```text
MCP requester
  -> human Touch ID approval
  -> bounded external executor
  -> exact action applied once
```

Result: `PASS`

## Final acceptance matrix

```text
Touch ID success       APPROVE                   grant possible   PASS
Esc                    REJECT/USER_ESCAPE        no grant         PASS
⌘W / window close      REJECT/WINDOW_CLOSED      no grant         PASS
Timeout                REJECT/TIMEOUT            no grant         PASS
Challenge expiry       REJECT/CHALLENGE_EXPIRED  no grant         PASS
Interaction failure    REJECT/INTERACTION_ERROR  no grant         N/A physical; automated coverage
W3/W4 positive regressions                         preserved      PASS
```

## Final closure statement

```text
W8-T09: PASS
Validated SHA: 1bec7bb76f0bb7119045bea6d59ed896364e2895
Physical positive Touch ID path: PASS
Esc reject: PASS
Window-close reject: PASS
Timeout reject: PASS
Challenge-expiry reject: PASS
Interaction-error row: N/A physical; automated coverage retained
W3/W4 regression: PASS
Only positive verified approval produced ExecutionGrant: CONFIRMED
```

W8-T09 is closed. The HAA-only software/ceremony phase is complete. Hardware work remains deferred and external product integrations remain parked until deliberately reprioritized.
