# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Human Approval Authority (HAA): a vendor-neutral service that binds a human's approval to one exact, canonical action and issues a short-lived `ExecutionGrant` only after atomic authorization/consumption. It is designed so a new human-verification mechanism (Touch ID, hardware fingerprint terminal, WebAuthn, etc.) can be added as an authenticator/evidence adapter *without* changing core contracts, lifecycle, receipt semantics, or audit semantics. See [README.md](README.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), and [docs/PLAN.md](docs/PLAN.md).

Trust flow: `Requester → ActionSpec → ApprovalIntent → signed ChallengePackage → Authenticator → ApprovalEvidence → APPROVED/Receipt → authorizeAndConsume(actualAction) → ExecutionGrant → Executor`

## Known broken state — read before touching `packages/core`

`packages/core/src/index.ts` imports from `./actions.ts` and `./challenge.ts`, but **these two files do not exist in this checkout**. This is a known, intentional gap documented in [docs/STATUS.md](docs/STATUS.md): a prior sync via a GitHub connector refused to write these files, and they were deliberately not recreated as simplified placeholders. As a result `npm test` currently fails at module resolution for every test file.

- `actions.ts` must export `ActionProfileRegistry` (validates an `ActionSpec` against a registered profile, computes `actionDigest`, validates preconditions — throws `UNSUPPORTED_ACTION_PROFILE` / `STALE_APPROVAL` per the tests in [tests/core.test.ts](tests/core.test.ts) and [tests/service.test.ts](tests/service.test.ts)).
- `challenge.ts` must export `issueChallenge`, `challengeDigest`, `decodeChallengePayload`, `verifyChallengeAuthority`, and `intentDigest` — building/signing/verifying the `ApprovalChallengePackage` defined in [packages/protocol/src/index.ts](packages/protocol/src/index.ts).

Do not "fix" this by weakening the exports in `index.ts` or by inventing a different, simpler contract — reconstruct these two modules to satisfy the existing call sites (`apps/haa-server/src/application.ts`, `tests/core.test.ts`) and the security invariants in [docs/SECURITY.md](docs/SECURITY.md). Treat this as the default starting task in this repo unless told otherwise.

## Commands

```bash
npm test              # runs all tests: node --experimental-strip-types --test tests/*.test.ts
npm run test:core      # tests/core.test.ts only
npm run test:service   # tests/service.test.ts only
npm run check          # alias for npm test
npm start              # runs apps/haa-server/src/server.ts directly
```

To run a single test file directly (e.g. to add `--test-name-pattern`):
```bash
node --experimental-strip-types --test tests/core.test.ts
node --experimental-strip-types --test --test-name-pattern="challenge" tests/core.test.ts
```

There is no build step and no bundler in the loop: TypeScript files run directly via Node's `--experimental-strip-types` (types are stripped, not checked, at runtime). Requires Node ≥24 per `package.json` engines (tested here against Node 22, which also works for `--experimental-strip-types` and the built-in `node:sqlite` module used by `packages/persistence-sqlite`). There is no separate `tsc`/lint script configured — `tsconfig.json` exists mainly for editor type-checking (`strict`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes` are all on).

Workspaces are npm workspaces (`packages/*`, `apps/*`), but packages import each other via relative `../../pkg/src/index.ts` paths with explicit `.ts` extensions (NodeNext ESM resolution), not by package name — there is no compiled `dist/` being consumed at runtime.

## Architecture

### Package layering (dependency direction is one-way)

```
packages/protocol   — pure types/interfaces only (ActionSpec, ApprovalIntent, ApprovalRequest,
                       ApprovalChallengePayload/Package, ApprovalEvidence, VerifiedEvidence,
                       ApprovalReceipt, ExecutionGrant, AuthenticatorRecord, AuditEvent).
                       No logic. This is the schema-frozen contract everything else depends on.
      ↑
packages/core       — canonicalization/digests (canonical.ts), state machine (state-machine.ts),
                       signing abstraction (signing.ts), evidence verification (evidence.ts),
                       receipt/grant construction (receipts.ts), plus the missing actions.ts/challenge.ts.
                       MUST stay authenticator-agnostic: no branching on "Touch ID", "fingerprint",
                       "Apple", "ESP32", etc. anywhere in this package.
      ↑
packages/persistence-sqlite — SqliteStore: the only place SQL / node:sqlite lives. Owns atomicity
                       for authorizeAndConsume (BEGIN IMMEDIATE / COMMIT / ROLLBACK in consumeApproved)
                       and the idempotency-by-executionId behavior.
      ↑
apps/haa-server     — HaaApplication (application.ts) is the actual service/orchestration layer:
                       auth, request creation, challenge issuance, evidence submission, and
                       authorizeAndConsume. http.ts is a thin Fastify wrapper mapping HTTP <-> app
                       methods with one error-message-to-status-code mapping. authority.ts loads/
                       creates the HAA authority signing key (P-256 by default, persisted to
                       ./.haa/authority-key.pem unless overridden by env vars).
      ↑
packages/sdk-ts     — HaaClient: thin fetch wrapper over the HTTP API (requestApproval/getApproval/authorize).
      ↑
apps/cli, apps/mcp  — consumers of sdk-ts. CLI is a plain argv dispatcher. MCP server exposes
                       `request_approval` and `approval_status` tools only — deliberately no
                       generic "execute" tool, since execution must go through a bounded Executor
                       that itself calls authorizeAndConsume.
```

`apps/haa-server/src/reference-executor.ts` is a reference/example `Executor` implementation showing the intended pattern: track a resource's version, call `authorizeAndConsume` with the actual current action + state, and only mutate the resource after the grant is returned. Real executors should follow this shape.

### Core invariants that constrain any change

These are the enforceable rules from [docs/SECURITY.md](docs/SECURITY.md) that show up directly in code and tests — violating them will break the threat-model tests even if the happy path still works:

1. **Exact-action binding**: approval is valid only for one canonical `ActionSpec` digest (`ACTION_DIGEST_MISMATCH` if the actual action at execution time differs from what was approved).
2. **TOCTOU / stale precondition**: `authorizeAndConsume` re-validates preconditions against actual current state (`STALE_APPROVAL`) even though the request was already `APPROVED`, and does *not* consume the approval if preconditions fail.
3. **Atomic single use**: `authorizeAndConsume` verifies and consumes state in one DB transaction (`SqliteStore.consumeApproved`).
4. **Idempotent retry**: replaying the same `executionId` returns the prior grant; a *different* `executionId` after consumption is denied (`REQUEST_NOT_APPROVED:CONSUMED`).
5. **Executor audience binding**: `authorizeAndConsume` checks `request.intent.executorAudience` equals the authenticated caller (`WRONG_EXECUTOR_AUDIENCE`).
6. **Challenge replay/binding**: evidence submission checks the stored challenge is unconsumed, matches the HAA authority signature, and binds to the exact request/action/intent digests (`CHALLENGE_NOT_ACTIVE`, `CHALLENGE_BINDING_MISMATCH`, `CHALLENGE_REPLAY`).
7. **Authenticator status**: evidence is only accepted from an `ACTIVE` authenticator registered to the expected principal (`AUTHENTICATOR_REVOKED`, `AUTHENTICATOR_PRINCIPAL_MISMATCH`).
8. **Fail closed**: unknown action profile, invalid/altered signature, or expired challenge all throw rather than degrade gracefully.
9. **No biometric material** ever enters `packages/core` or `apps/haa-server` — authenticator adapters (macOS Secure Enclave, DIY hardware) only ever hand back a signed `ApprovalEvidence`, never raw biometric data.

Canonicalization matters: `canonicalize()` in [packages/core/src/canonical.ts](packages/core/src/canonical.ts) sorts object keys and normalizes numbers (rejects non-finite, folds `-0` to `0`) before hashing, so digests are stable regardless of key order — any new digestable structure must go through `canonicalize`/`digestJson`, not `JSON.stringify` directly.

### Adjacent, gated components

- `macos/haa-approver` — Swift package for the Touch ID / Secure Enclave authenticator app. Marked `DONE_UNVALIDATED` in [tasks/manifest.yaml](tasks/manifest.yaml): source exists but needs real hardware validation (see [docs/MACOS-RUNBOOK.md](docs/MACOS-RUNBOOK.md)).
- `firmware/haa-terminal` — DIY ESP32-S3 hardware authenticator subplan. Entirely `BLOCKED` in the task manifest until wave W4's value gate (W4-T06) passes — do not build this out unless explicitly asked; see [docs/HARDWARE-SUBPLAN.md](docs/HARDWARE-SUBPLAN.md).

### Project status tracking

[tasks/manifest.yaml](tasks/manifest.yaml) is the authoritative task/wave status ledger (W0 through W7, with `depends_on` edges and `DONE` / `DONE_UNVALIDATED` / `BLOCKED` statuses). [docs/STATUS.md](docs/STATUS.md) gives the current narrative snapshot. Check both before assuming a wave/feature is complete — several are source-complete but unvalidated on real hardware, and later waves are formally blocked on earlier gates per [docs/PLAN.md](docs/PLAN.md)'s "Core rule".
