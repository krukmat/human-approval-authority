# W8-T09 physical macOS ceremony and compatibility gate

Status: **BLOCKED BY W7-T15**

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

## Gate 1 — Positive ceremony

Run the existing physical positive path:

```bash
npm ci
npm run validate:macos
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

Create a fresh request/challenge and open the trusted ceremony. Press Esc.

Expected approver output:

```text
outcome=REJECT
reason=USER_ESCAPE
```

Server expectation after submitting the terminal result:

```text
state=REJECTED
assurance=explicit-human-negative-action
receipt absent
ExecutionGrant impossible
```

Result: `PENDING PHYSICAL EXECUTION`

## Gate 3 — Window close rejection

Create a fresh request/challenge and close the approval window without Touch ID approval.

Expected:

```text
outcome=REJECT
reason=WINDOW_CLOSED
state=REJECTED
audit assurance=fail-closed-terminal
receipt absent
ExecutionGrant impossible
```

Do not describe this as proof that the human explicitly selected Reject.

Result: `PENDING PHYSICAL EXECUTION`

## Gate 4 — Local timeout rejection

Create a fresh request/challenge and invoke the approver with a short timeout, for example:

```bash
HAAApprover.app/Contents/MacOS/HAAApprover \
  --challenge <challenge.json> \
  --authority-public-key <authority.pem> \
  --authenticator-id <id> \
  --timeout-seconds 5
```

Do not approve before timeout.

Expected:

```text
outcome=REJECT
reason=TIMEOUT
state=REJECTED
audit assurance=fail-closed-terminal
receipt absent
ExecutionGrant impossible
```

Result: `PENDING PHYSICAL EXECUTION`

## Gate 5 — Challenge-expiry rejection

Use a HAA-signed challenge whose challenge lifetime has elapsed while the request itself remains valid. Launch the approver after challenge expiry.

Expected:

```text
challenge signature/bindings still verify
local expiry classification=CHALLENGE_EXPIRED
server verifies the challenge is actually expired
state=REJECTED
audit assurance=fail-closed-terminal
receipt absent
ExecutionGrant impossible
```

A live challenge mislabeled `CHALLENGE_EXPIRED` must be denied.

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
Touch ID success       APPROVE                 grant possible   PASS/FAIL
Esc                    REJECT/USER_ESCAPE      no grant         PASS/FAIL
Window close           REJECT/WINDOW_CLOSED    no grant         PASS/FAIL
Timeout                REJECT/TIMEOUT          no grant         PASS/FAIL
Challenge expiry       REJECT/CHALLENGE_EXPIRED no grant        PASS/FAIL
Interaction failure    REJECT/INTERACTION_ERROR no grant        PASS/FAIL/N-A
W3/W4 positive regressions                       preserved      PASS/FAIL
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
