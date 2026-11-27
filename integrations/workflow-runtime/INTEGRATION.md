# Candidate integration and certification handoff

The code is a standalone companion under this directory. The server profiles are additive and disabled by default; the companion is published on HAA main by owner instruction; original DubBridge branches are untouched. No HAA protocol version change.

## Integration map (W4)

| Surface | Fénix | DubBridge | Candidate |
|---|---|---|---|
| Policy sources | Guide + HITL + AGENTS/CLAUDE, preserve their precedence | Guide is canonical, HITL references it | pin_project_policy binds exact bytes + the trusted resolved decision |
| Task contract | Existing Task Cards; projection to v2 required | Existing local-agent task-card-v2 | Existing strict parser retained; no implicit legacy command conversion |
| Low-risk path | Existing local delegation/QA | Existing local-first routing/QA | No extra HAA gate when governing policy says no |
| Explicit authority | Existing HITL, plus exact action when activated | Existing HITL, plus exact action when activated | PolicyPin + session-bound action + verified grant |
| Worker | Cloud or local writes scratch | Existing local runner in scratch | Typed one-existing-file proposal; explicit protected runner script selection |
| QA, review, RRI | Unchanged | Unchanged | No new model/reviewer; exact-tree verifier remains separate |

The protected supervisor accepts only the policy decision from the trusted workflow controller. It verifies source hashes at session bind and before subsequent mediated operations. A changed pin/card/policy blocks the operation and invalidates the live lease. The prototype's RRI numeric field remains metadata for its existing task-card/checkpoint format; the new protected admission uses explicit policy decision rather than a global threshold. Legacy synthetic unit paths retain historical RRI behavior only and cannot enter the volatile protected admission without a PolicyPin.

A successful task-start grant authorizes lease activation only, not a push/merge/deploy or plan close. Worker identity and broker window are bound; no model-specific authority. A change of agent must remain in the same authenticated worker/lease boundary; cross-UID handoff is not implemented. Ordinary closure stays with existing governance. The candidate protected plan closure path still requires its separate exact HAA grant. A waiver or model verdict is not a grant.

The standalone worker proposal module can submit one edit made in scratch by any existing model/agent. Its claims are untrusted: the broker checks kernel peer, current live authority and preimage independently. Direct cloud GitHub writes and unmediated shell effects are not controlled. The repo-specific runner must be staged, pinned and selected out-of-band; no fallback to a product repository script in the executor. Fénix's existing delegate-low-rri.py is not the same CLI as DubBridge's local-agent/run_local_task.py, and neither is implicitly invoked as a generic high-authority runner.

## Candidate gates

Run the portable gate from a clean checkout, as a non-root user, with Node and an isolated Python environment containing cryptography>=45,<46:

```sh
python3 integrations/workflow-runtime/certify.py
```

It runs the profile tests, cross-language digest fixture, Python regressions, card parser tests and synthetic microbenchmark; reports PASS_PORTABLE_ONLY or BLOCKED_OR_FAIL. It cannot grant real authority. The full inherited HAA npm test/typecheck remain required before any PR or merge; run them after installing the existing locked dependencies. The benchmark measures incremental p50/p95/p99 and CPU, plus process peak RSS; it is not a full workflow or biometric latency benchmark.

The previous macOS fixture probes are ported as source candidates only. Their hardcoded synthetic layout, UIDs, Python dependency lock and verifier provisioning must be reconciled against the actual Mac before any invocation. Do not copy credentials, automatically run sudo, modify host permissions, use live HAA, or enable HAA_WORKFLOW_PROFILES_ENABLED based on the portable gate. The original host installation is not assumed to be compatible with the new path.

## Known remaining acceptance gaps

- The complete portable gate passed on the owner's Mac at 202988b. This is not a protected-host or actual runner certification. The remote execution sandbox has no GitHub checkout access.
- The original single-file path remains as a compatibility reference. A bounded multi-file replacement candidate is now implemented; see the batch section below. Create/delete, remote writes and physical certification are not supported by this batch profile.
- Existing project workflow guides and hooks are unchanged. The source pin adapters and proposal channel exist, but actual Fénix/DubBridge runner wiring and route parity are pending.
- W3 portable extraction is validated; complete W4 integration and close the above acceptance gaps. W5 requires full workflow A/B and final certification harness; microbenchmark alone cannot establish performance. W6 requires real macOS isolation, credentials, protected verifier, worker, HAA ceremony, negative/restart/revocation cases and explicit owner acceptance.
- Activation stays NO_GO. No CI, protected host provisioning or Touch ID was performed. HAA main was fast-forwarded at owner direction.

## Portable gate repair (2026-11-27)

The first Mac execution reported 4/4 profile tests PASS; Python regression: 157 tests, 10 failures, 30 errors, 1 skipped; parser import error; microbenchmark PASS; dirty checkout caused by generated bytecode. The observed dominant cause was inconsistent synthetic origin URL (`krukmat/workflow` versus `example/workflow-fixture`) introduced by the extraction. Correct the six fixture URLs, not the runtime's origin validation. Keep the two original runner-specific Task Card cases in `scripts/local-agent/task_card_runner_integration_test.py` for the actual runner integration gate; the standalone parser suite must not import the absent product-specific runner. Isolated subprocesses ignore PYTHONDONTWRITEBYTECODE; use explicit -B and ignore generated __pycache__ directories only within this companion. Report complete test output and pin HEAD before/after. Re-run required; no new PASS inferred from these repairs. Actual runner integration remains pending.

## Portable gate acceptance (2026-11-27)

Owner-supplied console output at `202988b3df70fa048ab9dabd026390b79c81f4f7`: `PASS_PORTABLE_ONLY`, Python 3.15.2, 4 TypeScript profile/parity tests passed, 156 Python regression tests passed and one skipped, 12 parser tests passed; total 172 passed, zero failures/errors. Clean checkout and unchanged HEAD confirmed. The aggregate output does not identify the skipped test by name; the dependency-negative test is conditional in source and no skip identity is asserted from this run. Synthetic benchmark: p50 45.042 µs, p95 51.208 µs, p99 64.958 µs, incremental p95 51.083 µs; peak RSS 23,724,032 native macOS bytes; 0 model calls and tokens. No full workflow A/B claim. Runner contract integration not run, host isolation and Touch ID not tested, activation NO_GO. The evidence applies to the tested code SHA, not future changes.

## Next implementation dependency

1. Preserve the existing single-file protected prototype as a passing reference; implement a candidate-tree transaction for bounded multi-file changes, with exact preimages, explicit operation capabilities, full scope validation before mutation, verified tree, local ref CAS and recovery that never auto-retries an ambiguous publish. Creation/deletion require explicit policy authorization; no implicit privilege expansion. No arbitrary Git shell or remote push is included.
2. Wire existing policy-owned task inputs, not new model calls: Fénix `scripts/delegate-low-rri.py` is low-band only and must not be used to circumvent its HITL, reviewer or QA gates. DubBridge `scripts/local-agent/run_local_task.py` consumes native task-card-v2. High-authority Cloud–Local implementation submits typed proposals from scratch through the protected channel. Retain the two runner-specific tests for actual integration. Product guide changes require the existing project gates and are not made by this evidence commit.
3. Run regression on the changed candidate, then combined real-runner/host validation and full workflow A/B on the Mac; final owner Touch ID certification remains last. Do not equate 172 portable passes with deployment approval.

## W4 batch and project bridge candidate

The worker may submit one typed `replace_batch` proposal with up to 32 existing tracked UTF-8 regular files, 512 KiB per file and 1 MiB aggregate content (also subject to the 2 MiB framed message limit). No filename aliases, duplicate paths, unsafe paths, mode changes, create/delete or arbitrary Git operations. The broker binds one immutable proposal to the kernel peer and one-time window. The executor checks the whole batch against the same live lease, original Git parent, pinned card/policy, tracked blobs and exact current preimages before creating a temporary-index candidate tree. Verify the exact tree in the separate verifier identity, then recheck authority and preimages before checkout writes and local ref CAS. The canonical plan journal is IN_FLIGHT before publication; failure leaves UNCERTAIN and never automatically retries. Git ref publication is atomic, but the filesystem is not a multi-file atomic transaction. A partial filesystem failure requires operator reconciliation. The protected runtime still disallows direct main publication; the HAA development repository uses main as requested by the owner. The two are separate.

`submit_batch.py` collects the complete explicitly selected tracked diff from scratch and submits preimages and new bytes; cloud/local implementations share the same protocol. `project_bridge.py` produces the native runner argv: Fénix `delegate-low-rri.py` only for RRI 0–25; DubBridge `run_local_task.py` for the policy-selected native Task Card route. No new model, reviewer or route selection is performed; the existing controller remains responsible for HITL, RRI, peer review, QA and fallback. The adapter does not launch a runner by itself. Existing product repository hooks are unchanged. Extra project policy sources (orientation, RRI and Fénix local model policy) are now pinned. Native runner/host integration and same-UID implementer handoff are not yet certified.

Regression sources added: eight batch tests, three scratch collection tests, four project argv tests, and one additional signed synthetic task-to-plan-close case. None of these 16 new cases has been executed in the full repository yet. The earlier portable PASS is not a PASS of this candidate. No production activation, CI or protected-host changes.
