# Implementation status

## Functional status

- **W0 Foundation:** DONE
- **W1 Universal core:** DONE
- **W2 Service/enforcement:** DONE
- **W3 Apple authenticator:** DONE and physically validated on a real Apple Silicon Mac with Touch ID / Secure Enclave
- **W4 Agent integration:** DONE; `npm run validate:agent-macos` passed the real MCP requester → human Touch ID → bounded executor scenario
- **W4-T06 Value Gate:** PASS; a future hardware POC is authorized but not required for the software product
- **W5 Hardware POC:** DEFERRED by current product priority
- **W6 Hardware hardening:** BLOCKED until W5 is deliberately resumed
- **W7-T01 Protocol/version compatibility freeze:** DONE
- **W7-T02 Docker/self-host package:** DONE
- **W7-T03 Publishable TypeScript SDK package:** DONE
- **W7-T04 WebAuthn spike:** DEFERRED_OPTIONAL
- **W7-T05 Final independent/cross-model security review:** READY_FOR_EXTERNAL_REVIEW; first-party review completed and blocking findings fixed
- **W7-T06..T15 Software production hardening:** ACTIVE / PLANNED
- **W8 Universal ceremony outcomes:** ACTIVE ROADMAP / HAA-ONLY
- **Product integrations:** PARKED; not part of the active roadmap

The canonical active plan is `docs/HAA-ACTIVE-ROADMAP.md` and the machine-readable dependency graph is `tasks/manifest.yaml`.

## Current quality gates

The current software surface is validated by CI and the physical Mac gate:

- TypeScript runtime security tests pass.
- Production TypeScript sources pass strict `tsc --noEmit`.
- `@haa/protocol` v1 and `@haa/sdk` build to JS/declarations and pass `npm pack --dry-run`.
- Docker image builds, starts and passes a live `/health` smoke test.
- MCP stdio exposes only `request_approval` and `approval_status`.
- Exact-action binding, stale-precondition rejection, replay rejection, atomic single use and post-mutation idempotent retry are covered.
- External executor remains blocked before approval and mutates its resource only after obtaining `ExecutionGrant`.
- Swift package tests and the app-like Xcode wrapper compile on a macOS CI runner.
- Real provisioned macOS execution passed Secure Enclave enrollment, trusted display, Touch ID evidence verification and bounded execution.

## W7 software productization delivered

### Protocol v1

`docs/PROTOCOL-V1.md` freezes the v1 authorization-bearing schemas and defines strict compatibility rules. Product-specific growth happens through versioned ActionProfiles and adapters rather than mutation of signed v1 primitives.

### Self-host

The repository includes:

- `Dockerfile` based on Node 24;
- `docker-compose.yml` with separate persistent SQLite and authority-key volumes;
- container healthcheck;
- loopback-only host binding by default;
- `scripts/provision-client.mjs` for non-dev client provisioning with high-entropy keys;
- `docs/SELF-HOSTING.md`.

`HAA_DEV_BOOTSTRAP` remains development-only and is not required for the self-host path.

### SDK

`@haa/sdk` has a compiled package boundary, generated declarations, exported public input types and `HaaApiError`. It depends on the frozen `@haa/protocol` v1 package rather than private monorepo source paths.

## Security review findings fixed

The first-party W7 review found and fixed three integration-blocking gaps:

1. requester identity could nominate itself as approver → now rejected with `SELF_APPROVAL_FORBIDDEN`;
2. software-only `test-key` verifier was enabled by default → now test-only through explicit injection;
3. any authenticated client could read unrelated request/audit metadata → now limited to request participants.

`docs/SECURITY-REVIEW-V1.md` also records the residual production-hardening work now promoted into W7-T06..T15:

- runtime request schemas / bounds;
- deterministic dependency/build chain;
- client credential lifecycle and role separation;
- authority key rotation;
- network edge controls;
- audit tamper-evidence;
- authenticator assurance model;
- detached `ExecutionGrant` verification;
- SQLite backup/recovery and explicit single-node boundary;
- final software production-readiness gate.

## W8 universal ceremony outcomes

W8 is now HAA-only and product-independent.

Target ceremony semantics:

```text
successful Touch ID   -> APPROVE
Esc                    -> REJECT
window close           -> UNKNOWN
local timeout          -> UNKNOWN
technical interruption -> UNKNOWN
```

Compatibility rule:

- `REJECTED` and `EXPIRED` already exist in frozen protocol v1;
- `UNKNOWN` is **not** added to `ApprovalState`;
- UNKNOWN is an indeterminate ceremony result exposed to the caller/app;
- if the request remains valid it may remain `PENDING`;
- true request/challenge expiry continues to use `EXPIRED`;
- only verified APPROVE evidence may result in `ApprovalReceipt` / `ExecutionGrant`.

Before implementing Esc-as-REJECT, W8 explicitly requires a negative-decision provenance/threat-model task so an agent/requester cannot forge a claim that the human explicitly rejected something.

## Hardware boundary

Hardware is not blocked by architecture; it is deliberately deferred. Do not continue W5/W6 unless product priority explicitly returns to the dedicated terminal POC.

## Product-integration boundary

No external product repository is part of the active plan. Existing product-integration design notes may remain in the repository as parked future material, but they do not define current task dependencies and must not drive HAA core decisions.
