# W8-T09 physical macOS ceremony and compatibility gate

Status: **READY**

This is the final HAA-only physical validation after the software production-readiness gate. It runs on a provisioned Apple Silicon Mac with Touch ID and validates the actual trusted-display / Secure Enclave boundary.

It does not depend on DubBridge or any product integration.

## Preconditions

- W8-T08 automated ceremony matrix is green.
- W7-T15 is DONE on the commit being validated.
- Apple Silicon Mac with Touch ID configured.
- Full Xcode and valid Apple Development provisioning context.
- HAA approver app wrapper builds and its provisioning/signing identity verifies.
- No reuse of development/test software evidence as a substitute for the Secure Enclave path.

Record:

```text
Commit SHA:
Mac model:
macOS version:
Xcode version:
Apple team ID used:
Authenticator ID:
Validation date:
Operator:
```

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

First retain the existing W3 positive regression gate:

```bash
npm ci
npm run validate:macos
```

Then run the W8 ceremony-specific positive case:

```bash
npm run validate:macos-ceremony -- --case approve
```

Expected:

```text
trusted signed display
  -> successful Touch ID
  -> apple-secure-enclave ApprovalEvidence
  -> ApprovalReceipt
  -> exact authorizeAndConsume
  -> usable ExecutionGrant
```

Must retain the W3 invariants:

- mutated action denied;
- stale precondition denied without consumption;
- same execution ID idempotent;
- different execution ID denied after consume.

Result: `PENDING PHYSICAL EXECUTION`

## Gate 2 — Escape rejection

Run:

```bash
npm run validate:macos-ceremony -- --case escape
```

Press Esc when the trusted HAA ceremony is shown.

Expected:

```text
outcome=REJECT
reason=USER_ESCAPE
state=REJECTED
assurance=explicit-human-negative-action
ExecutionGrant impossible
```

Result: `PENDING PHYSICAL EXECUTION`

## Gate 3 — Window close rejection

Run:

```bash
npm run validate:macos-ceremony -- --case window-close
```

Press `⌘W` while the trusted HAA ceremony is active. If macOS exposes a standard close control for the alert, that control is equivalent. HAA captures `⌘W` explicitly so this gate does not depend on `NSAlert` exposing a red close button.

Expected:

```text
outcome=REJECT
reason=WINDOW_CLOSED
state=REJECTED
audit assurance=fail-closed-terminal
ExecutionGrant impossible
```

`⌘W` is treated as a deterministic window-close gesture. It is still `fail-closed-terminal`, not proof that the human explicitly selected Reject.

Result: `PENDING PHYSICAL EXECUTION`

## Gate 4 — Local timeout rejection

Run:

```bash
npm run validate:macos-ceremony -- --case timeout
```

The orchestrator supplies a short local timeout. Do not approve before it expires.

Expected:

```text
outcome=REJECT
reason=TIMEOUT
state=REJECTED
audit assurance=fail-closed-terminal
ExecutionGrant impossible
```

Result: `PENDING PHYSICAL EXECUTION`

## Gate 5 — Challenge-expiry rejection

Run:

```bash
npm run validate:macos-ceremony -- --case challenge-expired
```

The orchestrator waits until the HAA-signed challenge expires while its parent request remains valid, then launches the approver.

Expected:

```text
challenge signature/bindings still verify
local expiry classification=CHALLENGE_EXPIRED
server verifies the challenge is actually expired
state=REJECTED
audit assurance=fail-closed-terminal
ExecutionGrant impossible
```

A live challenge mislabeled `CHALLENGE_EXPIRED` is already covered by automated adversarial tests and must be denied.

Result: `PENDING PHYSICAL EXECUTION`

## Gate 6 — Terminal interaction failure

Where safely reproducible without weakening entitlements or Secure Enclave controls, trigger a terminal authenticator/interaction failure after a valid trusted challenge is established.

Expected:

```text
outcome=REJECT
reason=INTERACTION_ERROR
assurance=fail-closed-terminal
no positive evidence
no receipt/grant
```

Do not weaken key access control, remove Secure Enclave protection, or alter signing entitlements merely to manufacture this test. If a safe deterministic reproduction is unavailable, record `NOT SAFELY REPRODUCIBLE` and rely on automated coverage for this reason.

Result: `PENDING PHYSICAL EXECUTION`

## Gate 7 — Regression compatibility

Run:

```bash
npm run validate:agent-macos
```

Expected existing W4 result remains valid:

```text
MCP requester
  -> human Touch ID approval
  -> bounded external executor
  -> exact action applied once
```

The W8 negative changes must not weaken or alter the successful W3/W4 authority path.

Result: `PENDING PHYSICAL EXECUTION`

## Final acceptance matrix

```text
Touch ID success       APPROVE                   grant possible   PASS/FAIL
Esc                    REJECT/USER_ESCAPE        no grant         PASS/FAIL
⌘W / window close      REJECT/WINDOW_CLOSED      no grant         PASS/FAIL
Timeout                REJECT/TIMEOUT            no grant         PASS/FAIL
Challenge expiry       REJECT/CHALLENGE_EXPIRED  no grant         PASS/FAIL
Interaction failure    REJECT/INTERACTION_ERROR  no grant         PASS/FAIL/N-A
W3/W4 positive regressions                         preserved      PASS/FAIL
```

W8-T09 may move to DONE only when all required physical rows are PASS and any N/A is limited to the safely-nonreproducible interaction-error row with automated coverage still green.

## Final closure statement

```text
W8-T09: PASS
Validated SHA: <sha>
Physical positive Touch ID path: PASS
Esc reject: PASS
Window-close reject: PASS
Timeout reject: PASS
Challenge-expiry reject: PASS
Interaction-error row: PASS | N-A with rationale
W3/W4 regression: PASS
Only positive verified approval produced ExecutionGrant: CONFIRMED
```
