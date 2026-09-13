# Repository Guidelines

## Project Structure & Module Organization

This npm workspace keeps shared TypeScript in `packages/`: `protocol` defines contracts, `core` implements approval rules, `persistence-sqlite` owns storage, and `sdk-ts` provides the client. Entry points live in `apps/` (`haa-server`, `cli`, and `mcp`), with tests in `tests/*.test.ts`. The Touch ID adapter is a separate Swift package under `macos/haa-approver`; `firmware/haa-terminal` is a gated hardware subplan. Design and task records live in `docs/` and `tasks/`.

## Build, Test, and Development Commands

- `npm install` installs workspace dependencies (Node.js 24+).
- `npm test` runs every TypeScript test with Node's built-in test runner.
- `npm run test:core` and `npm run test:service` run focused suites.
- `npx tsc --noEmit` performs CI's strict type check.
- `npm start` starts the HAA server directly from TypeScript.
- `cd macos/haa-approver && swift test` tests portable Swift components; Secure Enclave behavior requires compatible hardware.

There is no JavaScript bundle step; Node executes `.ts` sources through `--experimental-strip-types`.

## Coding Style & Naming Conventions

Use NodeNext ESM, explicit `.ts` extensions for relative imports, two-space indentation, single quotes, and semicolons. Honor the strict `tsconfig.json` settings. Use `camelCase` for values/functions, `PascalCase` for types/classes, and kebab-case filenames such as `state-machine.ts`. Swift uses four-space indentation and standard API naming. No formatter or linter is configured; match adjacent code.

## Testing Guidelines

Use `node:test` with `node:assert/strict`; name files `<area>.test.ts` and tests by observable behavior. Cover success and fail-closed paths, especially action binding, replay, expiry, preconditions, and atomic consumption. Before a PR, run `npm test` and `npx tsc --noEmit`.

## Commit & Pull Request Guidelines

History uses Conventional Commit-style subjects with scopes, for example `feat(macos): add approver command-line flow`. Keep commits focused. PRs should explain behavior and security impact, link an issue or `tasks/manifest.yaml` item, list verification commands, and include screenshots for UI changes. Note outstanding hardware validation.

## Security & Task Constraints

Read `docs/SECURITY.md` before changing approval logic. Keep `packages/core` authenticator-agnostic, never ingest biometric material, preserve canonical exact-action binding, and fail closed. `ApprovalReceipt` is audit evidence, never an execution bearer capability; execution requires atomic `authorizeAndConsume(actualAction, executionId)`. Display fields must derive from the signed canonical intent, never requester prose. Any new authenticator must plug in through `ApprovalEvidence`/`EvidenceVerifier` without changing lifecycle or execution semantics. `tasks/manifest.yaml` is the dependency/status source of truth; do not begin blocked hardware work without its documented value-gate approval.
