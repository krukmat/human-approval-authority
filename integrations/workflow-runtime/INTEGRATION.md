# Candidate integration and certification handoff

The code is a standalone companion under this directory. The server profiles are additive and disabled by default; main and the original DubBridge branches are untouched. No HAA protocol version change.

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

- Integrated source has not been executed in a complete checkout in this remote session; GitHub connector can transfer files but the execution sandbox cannot resolve github.com. Four isolated policy tests passed against policy.py (blob 1398674b7e7fcd563166d45d64ca38ce737c77d9); the migrated suite is prepared but not passed.
- The broker/commit prototype deliberately remains limited to replacing one existing regular UTF-8 file; no general multi-file create/delete, atomic batch, or push/merge mediation. Do not call it a complete production development runtime.
- Existing project workflow guides and hooks are unchanged. The source pin adapters and proposal channel exist, but actual Fénix/DubBridge runner wiring and route parity are pending.
- Complete W3/W4 after portable regression and close the above integration gaps. W5 requires full workflow A/B and final certification harness; microbenchmark alone cannot establish performance. W6 requires real macOS isolation, credentials, protected verifier, worker, HAA ceremony, negative/restart/revocation cases and explicit owner acceptance.
- Activation stays NO_GO. No CI, merge, protected host provisioning or Touch ID was performed.
