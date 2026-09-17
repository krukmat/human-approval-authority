# W9-T07/T08 — Adoption review and integration-readiness gate

Status: **PASS_WITH_FOLLOWUPS / W9 CLOSED**

Date: 2026-09-17

Reference consumer: `krukmat/verifiable-event-ledger`

## Evidence summary

The first cross-repository adoption slice uses Human Approval Authority as an external product boundary rather than importing HAA implementation code.

The physical W9-T06 run on macOS proved the positive path:

```text
external VEL requester
  -> HAA PENDING request
  -> external executor blocked before approval
  -> signed trusted-display challenge
  -> human Touch ID approval
  -> ApprovalReceipt
  -> external VEL authorizeAndConsume
  -> detached ExecutionGrant verification
  -> exact git merge --ff-only side effect
  -> request CONSUMED
  -> exactly one CONSUMED audit event
```

The physical log identified the external VEL baseline as:

```text
faa3561a0796c088ad4d7a8b6f9eeb79b22d8565
```

The validator did not print the local HAA Git SHA, so the exact checked-out HAA commit is not independently recoverable from that log. The W9 physical-validator command was introduced at `b0b047e803b13f7f3cc7b848e4e66c745b93575f`; CI and CodeQL for that validator commit passed.

The physical run also proved Apple Development signing, Secure Enclave enrollment and the real Touch ID ceremony in the external-consumer path.

## W9-T03 — Reference external consumer

Result: **PASS**

`verifiable-event-ledger` lives outside the HAA monorepo and uses public HAA HTTP contracts only.

The requester:

- owns only the REQUESTER credential;
- creates/reads approval requests;
- has no `/authorize` execution path;
- performs no Git mutation;
- cannot treat APPROVED state as execution authority.

The executor:

- owns a separate EXECUTOR credential;
- reads the actual Git target state;
- reconstructs the exact action;
- calls HAA authorization before mutation;
- detached-verifies the returned grant;
- performs only a bounded fast-forward merge.

No private HAA source import or workspace dependency was required.

## W9-T04 — Real ActionProfile

Result: **PASS / NO CORE CHANGE**

The existing `git.merge.v1` profile is the real external action profile. Its exact allow-listed fields are:

```text
repository
sourceCommitSha
targetBranch
targetCommitBefore
```

All four are digest-bound and rendered in the trusted human display. Unknown payload fields and unexpected preconditions fail closed. `targetCommitBefore` is used as the stale-state boundary at authorization.

See `docs/W9-GIT-MERGE-PROFILE-REVIEW.md`.

## W9-T05 — External executor

Result: **PASS_WITH_FOLLOWUP**

The external Python executor validates:

- configured repository policy;
- clean worktree;
- checked-out target branch;
- full source commit resolution;
- target HEAD against approved `targetCommitBefore`;
- HAA executor audience;
- detached authority signature;
- ACTIVE authority key status;
- grant time/TTL policy;
- request ID;
- execution ID;
- action digest;
- executor audience;
- local Git state again before the side effect.

The mutation is restricted to `git merge --ff-only` and occurs only after authorization and detached verification.

Recovery strategy for an ambiguous post-authorization failure is explicit:

```text
HEAD == approved source commit
  -> side effect already reached the approved result; reconcile completion

HEAD == approved targetCommitBefore
  -> retry authorization with the same durable executionId

HEAD == anything else
  -> fail closed; obtain a new approval for the new state
```

The current reference CLI does not automate the first reconciliation branch after a completed merge; a direct rerun can stop at its local stale-target check. This is fail-closed and cannot duplicate the merge, but it is developer/operational friction rather than ideal retry ergonomics.

Classification: `INTEGRATION_FIX`, severity P2/non-blocking.

## W9-T06 — External integration E2E

Result: **PASS**

The physical run proved:

- cross-repository requester boundary;
- real PENDING state;
- executor denied before approval with target unchanged;
- real HAA/macOS signed trusted display;
- real Touch ID positive approval;
- external detached grant verification;
- real bounded Git side effect in an isolated temporary clone;
- final `CONSUMED` state visible to requester;
- exactly one consumption event.

W9 does not re-enact every already-closed HAA security invariant with separate Touch ID ceremonies. Required negative properties remain enforced and continuously tested in the HAA service/core gates:

```text
REJECT                         -> no execution authority (W8 ceremony gates)
mutated action                 -> ACTION_DIGEST_MISMATCH
stale precondition             -> STALE_APPROVAL
wrong executor audience        -> WRONG_EXECUTOR_AUDIENCE
same executionId               -> original grant idempotency
new executionId after consume  -> REQUEST_NOT_APPROVED:CONSUMED
replayed approval evidence     -> denied
```

The external Python verifier additionally tests audience binding and ACTIVE-key requirements, and the external executor tests that authorization precedes mutation and repository policy fails closed.

This combination is accepted as the W9 integration gate: physical validation is reserved for the cross-repository trust path that cannot be simulated, while deterministic negative invariants remain automated.

## W9-T07 — Adoption-gap classification

| Finding | Classification | Severity | Decision |
| --- | --- | --- | --- |
| No official Python HAA SDK; Python consumer implements detached verifier from the public protocol | `INTEGRATION_FIX` | P2 | Optional future SDK/DX work; not required for correctness |
| Post-merge same-execution recovery is manual reconciliation in the reference executor | `INTEGRATION_FIX` | P2 | Fail-closed; automate only if this consumer becomes operational |
| Xcode Personal Team must be selected locally for Secure Enclave physical validation | `DOCS` | P3 | Expected platform provisioning boundary |
| Physical validator did not emit local HAA Git SHA | `DOCS` | P3 | Improve future evidence output; does not invalidate observed ceremony |
| `git.merge.v1` uses generic non-empty strings rather than enforcing portable Git ref/SHA grammar in HAA core | `NO_ACTION` | — | External executor resolves/pins Git identifiers; no cross-consumer evidence for core expansion |
| No private HAA import was needed | `NO_ACTION` | — | Public product boundary sufficient |

Open BLOCKING findings: **0**.

Open P1 findings: **0**.

No HAA core change is justified by the first external integration.

## W9-T08 — Integration-readiness gate

Result: **PASS_WITH_FOLLOWUPS**

Acceptance:

```text
external E2E green                              PASS
consumer outside HAA monorepo                   PASS
private HAA dependencies                        NONE
real typed ActionProfile                        PASS
trusted display complete                        PASS
execution requires detached-valid grant         PASS
requester cannot execute from APPROVED state    PASS
actual state checked before mutation            PASS
failure paths fail closed                       PASS
separate requester/executor credentials         PASS
BLOCKING adoption findings                      0
P1 adoption findings                            0
HAA remains consumer-agnostic                   PASS
```

W9 is closed. The two P2 integration follow-ups are optional adoption/DX improvements and do not reopen HAA core or the closed W7/W8 security baselines.

Hardware W5/W6 remains deferred/blocked as previously decided. WebAuthn W7-T04 remains optional/deferred.
