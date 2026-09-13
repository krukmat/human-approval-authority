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

## Current status

- W0–W2 foundation/core/service: DONE.
- W3 Apple authenticator: DONE and validated on a real Mac.
- W4 MCP/requester/executor scenario: DONE; real agent → Touch ID → bounded executor gate passed.
- W5/W6 hardware: DEFERRED / not current work.
- W7 protocol freeze, self-host package and publishable TypeScript SDK: DONE.
- W7 software production hardening: ACTIVE.
- W7 independent/cross-model security review: READY_FOR_EXTERNAL_REVIEW after first-party findings were fixed.
- W8 universal ceremony semantics: PLANNED / HAA-only.
- Product-specific integrations: PARKED.

CI covers runtime security tests, publishable package checks, strict production typecheck, Docker build/health smoke, MCP stdio surface and macOS compilation. The physical Mac gate additionally validates Secure Enclave enrollment, trusted presentation and Touch ID approval.

## Self-host

```bash
docker compose build
docker compose up -d
```

The default compose deployment binds HAA to `127.0.0.1:8787`, persists SQLite state and the authority private key in separate volumes, and does not require development bootstrap credentials.

See `docs/SELF-HOSTING.md` for client provisioning, key persistence and network-boundary guidance.

## Public TypeScript packages

The repository now builds distributable package boundaries:

```bash
npm install
npm run pack:check
```

- `@haa/protocol` — frozen protocol v1 types/runtime metadata (`1.0.0`).
- `@haa/sdk` — typed requester/executor client with generated JS/declarations and `HaaApiError`.

See `docs/PROTOCOL-V1.md` for compatibility rules.

## Local Mac validation

```bash
npm install
npm run validate:macos
npm run validate:agent-macos
```

`validate:agent-macos` has passed on a real Apple Silicon Mac and validates the strongest current software path: **MCP requester → human Touch ID → external bounded executor**.

## Security posture

HAA is suitable for internal pilot/integration work under its documented trust assumptions. It is **not yet presented as an Internet-exposed/compliance-ready production system**.

The current review fixed requester self-approval, production exposure of the software-only test verifier and cross-client request/audit visibility. Active hardening is tracked in `docs/HAA-ACTIVE-ROADMAP.md` and `tasks/manifest.yaml`.

## Project control

- Architecture: `docs/ARCHITECTURE.md`
- Protocol v1: `docs/PROTOCOL-V1.md`
- Security invariants: `docs/SECURITY.md`
- Authenticator assurance: `docs/AUTHENTICATOR-ASSURANCE.md`
- Security review: `docs/SECURITY-REVIEW-V1.md`
- Active roadmap: `docs/HAA-ACTIVE-ROADMAP.md`
- Self-hosting: `docs/SELF-HOSTING.md`
- Current status: `docs/STATUS.md`
- Hardware decision: `docs/VALUE-GATE.md`
- Parked product integration notes: `docs/DUBBRIDGE-INTEGRATION-BACKLOG.md`
- Dependency graph/status: `tasks/manifest.yaml`
- Agent working contract: `AGENTS.md`

Hardware and product-specific integrations are deliberately not the current execution priority.
