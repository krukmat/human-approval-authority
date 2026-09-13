# Implementation status

## Functional status

- **W0 Foundation:** DONE
- **W1 Universal core:** DONE
- **W2 Service/enforcement:** DONE
- **W3 Apple authenticator:** DONE and physically validated on a real Apple Silicon Mac with Touch ID / Secure Enclave
- **W4 Agent integration:** DONE; `npm run validate:agent-macos` passed the real MCP requester → human Touch ID → bounded executor scenario
- **W4-T06 Value Gate:** PASS; a future hardware POC is authorized but not required for the software product
- **W5 Hardware POC:** DEFERRED by current product priority; a minimal scaffold exists but no further hardware work is active
- **W6 Hardware hardening:** BLOCKED until W5 is deliberately resumed and its POC gate passes
- **W7-T01 Protocol/version compatibility freeze:** DONE
- **W7-T02 Docker/self-host package:** DONE
- **W7-T03 Publishable TypeScript SDK package:** DONE
- **W7-T04 WebAuthn spike:** DEFERRED_OPTIONAL
- **W7-T05 Final independent/cross-model security review:** READY_FOR_EXTERNAL_REVIEW; first-party review completed and blocking findings fixed
- **W8 Product integrations / DubBridge:** FUTURE, intentionally deferred until W7 review closes

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

The repository now includes:

- `Dockerfile` based on Node 24;
- `docker-compose.yml` with separate persistent SQLite and authority-key volumes;
- container healthcheck;
- loopback-only host binding by default;
- `scripts/provision-client.mjs` for non-dev client provisioning with high-entropy keys;
- `docs/SELF-HOSTING.md`.

`HAA_DEV_BOOTSTRAP` remains development-only and is not required for the self-host path.

### SDK

`@haa/sdk` now has a compiled package boundary, generated declarations, exported public input types and `HaaApiError`. It depends on the frozen `@haa/protocol` v1 package rather than on private monorepo source paths.

## Security review findings fixed

The first-party W7 review found and fixed three integration-blocking gaps:

1. requester identity could nominate itself as approver → now rejected with `SELF_APPROVAL_FORBIDDEN`;
2. software-only `test-key` verifier was enabled by default → now test-only through explicit injection;
3. any authenticated client could read unrelated request/audit metadata → now limited to request participants.

See `docs/SECURITY-REVIEW-V1.md` for residual production-hardening items and explicit trust assumptions.

## Hardware boundary

Hardware is **not blocked by architecture anymore**; it is deliberately deferred. W4-T06 proved that host separation/dedicated physical approval can add value, but the current priority is the software product.

Do not continue W5/W6 unless product priority explicitly returns to the dedicated terminal POC.

## Future DubBridge integration

DubBridge has been added to W8 as the first planned product integration. It is not active work yet.

The future integration must use HAA at DubBridge's execution boundary after DubBridge has selected the exact route/model/provider/action. HAA will approve that exact action and return an `ExecutionGrant`; it will not become DubBridge's routing or context authority.

See `docs/DUBBRIDGE-INTEGRATION-BACKLOG.md`.
