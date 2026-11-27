# Shared Workflow HAA host acceptance — candidate

Status: BLOCKED_PENDING_HOST_EVIDENCE; activation NO_GO.

The previous product-specific macOS evidence is a reusable baseline, not a certificate for this installation. The tested shared code is `dc3e56d36cb2ca24b5d9b2f2034311fc7923f94a` (portable + native contract PASS). No existing installation, identities, sudo rules, credentials or plan journals are overwritten or copied.

## G0 — read-only reconciliation

Use inspect_shared_host.py as the owner, non-root. It reports only metadata for known HAA paths, fixed candidate identities, and the official Python framework. Missing or inaccessible is not equivalent to absent. It never reads credentials or sudo policy content, changes permissions, or invokes sudo. Confirm actual allocation, ACL/effective sudo policy, code and dependency provenance with the owner before preparing installation. Do not equate root ownership with isolation.

## G1 — exact deployment manifest

Prepare versioned root-owned runtime, exact dependency/import hashes, dedicated non-login executor/worker/verifier identities and least privilege IPC/export groups. Reuse an existing installation only if identity and path policy can be reconciled without weakening its boundary. No broad sudo, no root execution of repository code, no automatic changes to the existing product installation. The owner authorizes specific administrative actions natively. Keep production credentials and all real project repos out of synthetic probes. The current launcher uses fixed paths and UID assumptions; reconcile these with actual inventory before executing any host probe.

## G2 — empirical isolation and actual runner

Test actual distinct UIDs, denied worker/verifier access to executor private canaries and protected Git, immutable candidate export, observed command exits, peer credentials, timeout/quarantine, lease expiry/restart, stale scope and batch publication/recovery. Require a real runner in scratch with deterministic fixture responses (no new model calls for this gate) and exact tree verifier. An unexpected writable path or residual process blocks. Do not use the inherited hardcoded product runner probe without staging the selected dependencies. Current batch supports tracked replacements only, and Git ref publication is atomic but not multi-file filesystem mutation. No automatic replay after partial failure.

## G3 — real authority smoke

Only with explicit owner interaction, use the new synthetic workflow profile smoke, after npm test and npx tsc --noEmit pass. Verify the trusted display for both synthetic actions; observe no grant before approval, detached verified grant after approval, final CONSUMED. Record cleanup outcome. Separate from G2: no claim that a real physical grant has been exercised through the protected runtime until a subsequent composed test proves that exact path. Do not enable persistent HAA_WORKFLOW_PROFILES_ENABLED.

## G4 — composed workflow acceptance

Integrate the controller hooks according to each project's existing HITL/QA/reviewer policy. No changes to Fénix/DubBridge project repos were made during shared-runtime development. Test actual cloud/local route and same-UID handoff under the protected runtime, closure policy and real exact grants against synthetic project content. Run matched workflow A/B evidence capture and compare without extra model/reviewer calls or unauthorized prompts. No threshold claim until comparable data exists. Creation/deletion, remote push/merge and direct unmediated Git effects are outside the current scope; they require separate explicit authorization/enforcement. Production activation and any product hook rollout require independent final owner acceptance after all required gates. 
