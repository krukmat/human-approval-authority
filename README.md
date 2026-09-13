# Human Approval Authority (HAA)

A vendor-neutral human approval authority for agentic workflows. HAA binds human approval to one exact canonical action and produces a short-lived execution grant only after atomic authorization/consumption.

## Trust flow

```text
Requester / Agent
    ↓
ActionSpec → ApprovalIntent → signed ChallengePackage
    ↓
Human-verifying Authenticator
    ↓
ApprovalEvidence → ApprovalReceipt
    ↓
authorizeAndConsume(actualAction, executionId)
    ↓
ExecutionGrant → bounded Executor
```

`ApprovalReceipt` is audit evidence. It is **not** an execution bearer token. A real action can proceed only through `authorizeAndConsume()` and an `ExecutionGrant` bound to the exact action and executor audience.

## Authenticator paths

- **macOS:** Touch ID-gated P-256 signing with a device-bound Secure Enclave key.
- **DIY hardware (conditional):** XIAO ESP32-S3 + local fingerprint match + trusted display + protected signing key.
- Future authenticators plug into the evidence-verifier boundary without changing core execution semantics.

The HAA core never handles fingerprint images/templates and contains no Apple/ESP32-specific policy logic.

## Current status

- W0–W2: complete and CI validated.
- W3 Apple implementation: complete; physical Touch ID validation ready on a real Mac.
- W4 SDK/CLI/MCP/reference executor: cloud-testable work complete; real agentic Touch ID scenario ready for local validation.
- W5/W6 hardware: intentionally blocked until the W4 value gate passes.

CI currently covers runtime security tests, MCP stdio surface, strict production typecheck, exact-action binding, stale preconditions, replay, single consumption and post-mutation idempotent retry.

## Local Mac gates

```bash
npm install
npm run validate:macos
npm run validate:agent-macos
```

`validate:macos` validates the Apple authenticator ceremony. `validate:agent-macos` validates the stronger end-to-end scenario: **MCP requester → human Touch ID → external bounded executor**.

The validation helpers create temporary HAA state and clean their validation Secure Enclave key when finished.

## Project control

- Architecture: `docs/ARCHITECTURE.md`
- Security invariants: `docs/SECURITY.md`
- Current status: `docs/STATUS.md`
- Hardware subplan: `docs/HARDWARE-SUBPLAN.md`
- Hardware decision gate: `docs/VALUE-GATE.md`
- 50-task dependency graph/status: `tasks/manifest.yaml`
- Agent working contract: `AGENTS.md`

Do not begin hardware firmware work before `W4-T06` records PASS.
