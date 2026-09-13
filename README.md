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

- **macOS:** physically validated Touch ID-gated P-256 signing with a device-bound Secure Enclave key.
- **DIY hardware:** authorized by the value gate but currently deferred by product priority.
- Future authenticators plug into the evidence-verifier boundary without changing core execution semantics.

The HAA core never handles fingerprint images/templates and contains no Apple/ESP32-specific policy logic.

`user-verified-device-bound` describes the supported authenticator path and enrolled device-bound key behavior. HAA v1 does **not** independently perform Apple Secure Enclave/platform attestation; see `docs/AUTHENTICATOR-ASSURANCE.md`.

## Ceremony semantics

A terminal HAA ceremony has two operational outcomes:

```text
successful verified Touch ID approval -> APPROVE
anything else terminal                -> REJECT
```

Negative reasons remain typed so HAA does not overclaim human intent:

```text
USER_ESCAPE       -> explicit-human-negative-action
WINDOW_CLOSED     -> fail-closed-terminal
TIMEOUT           -> fail-closed-terminal
CHALLENGE_EXPIRED -> fail-closed-terminal
INTERACTION_ERROR -> fail-closed-terminal
```

Only APPROVE can lead to `ApprovalReceipt` and `ExecutionGrant`. Real request-TTL expiry remains lifecycle `EXPIRED`, separate from challenge-level rejection.

## Current status

- W0–W2 foundation/core/service: DONE.
- W3 Apple authenticator: DONE and validated on a real Mac.
- W4 MCP/requester/executor scenario: DONE; real agent → Touch ID → bounded executor gate passed.
- W5/W6 hardware: DEFERRED / not current work.
- W7-T01..T14 engineering/productization work: DONE except the independent review gate.
- W7-T05 independent/cross-model security review: READY_FOR_EXTERNAL_REVIEW.
- W7-T15 software production-readiness: BLOCKED only by W7-T05.
- W8-T01..T08 universal ceremony semantics and automated validation: DONE / HAA-only.
- W8-T09 physical macOS ceremony compatibility gate: BLOCKED by W7-T15.
- Product-specific integrations: PARKED.

CI covers production dependency audit, runtime security/adversarial tests, publishable package checks, strict production typecheck, Docker build/health smoke, physical-orchestrator syntax, MCP stdio surface and macOS Swift/Xcode compilation. CodeQL runs on pushes/PRs to `main` and weekly. The physical Mac gates additionally validate Secure Enclave enrollment, trusted presentation and Touch ID approval.

## Self-host

```bash
docker compose build
docker compose up -d
```

The default compose deployment binds HAA to `127.0.0.1:8787`, persists SQLite state and the authority private key in separate volumes, and does not require development bootstrap credentials.

See `docs/SELF-HOSTING.md` for client provisioning, key persistence and network-boundary guidance.

## Public TypeScript packages

The repository builds distributable package boundaries:

```bash
npm install
npm run pack:check
```

- `@haa/protocol` — frozen protocol v1 types/runtime metadata (`1.0.0`).
- `@haa/sdk` — typed requester/executor/ceremony client with generated JS/declarations and explicit verification/error contracts.

See `docs/PROTOCOL-V1.md` for compatibility rules.

## Local Mac validation

```bash
npm install
npm run validate:macos
npm run validate:agent-macos
```

`validate:agent-macos` has passed on a real Apple Silicon Mac and validates the strongest current software path: **MCP requester → human Touch ID → external bounded executor**.

After W7-T15 closes, W8-T09 uses the HAA-only physical ceremony orchestrator:

```bash
npm run validate:macos-ceremony -- --case approve
npm run validate:macos-ceremony -- --case escape
npm run validate:macos-ceremony -- --case window-close
npm run validate:macos-ceremony -- --case timeout
npm run validate:macos-ceremony -- --case challenge-expired
```

See `docs/W8-PHYSICAL-CEREMONY-GATE.md`.

## Security posture

HAA is suitable for internal pilot/integration work under its documented trust assumptions. It is **not yet presented as an Internet-exposed/compliance-ready production system**.

The first-party review fixed requester self-approval, production exposure of the software-only test verifier and cross-client request/audit visibility. Current completion requires an actually independent/cross-model W7-T05 review and W7-T15 reconciliation before the final physical W8-T09 gate.

## Project control

- Architecture: `docs/ARCHITECTURE.md`
- Protocol v1: `docs/PROTOCOL-V1.md`
- Security invariants: `docs/SECURITY.md`
- Authenticator assurance: `docs/AUTHENTICATOR-ASSURANCE.md`
- First-party security review: `docs/SECURITY-REVIEW-V1.md`
- Independent review packet: `docs/W7-INDEPENDENT-REVIEW-PACKET.md`
- Production-readiness gate: `docs/W7-PRODUCTION-READINESS.md`
- W8 ceremony contract: `docs/W8-CEREMONY-OUTCOMES.md`
- W8 physical gate: `docs/W8-PHYSICAL-CEREMONY-GATE.md`
- Active roadmap: `docs/HAA-ACTIVE-ROADMAP.md`
- Self-hosting: `docs/SELF-HOSTING.md`
- Current status: `docs/STATUS.md`
- Hardware decision: `docs/VALUE-GATE.md`
- Parked product integration notes: `docs/DUBBRIDGE-INTEGRATION-BACKLOG.md`
- Dependency graph/status: `tasks/manifest.yaml`
- Agent working contract: `AGENTS.md`

Hardware and product-specific integrations are deliberately not the current execution priority.
