# W9-T07/T08 — Adoption review and integration-readiness gate

Status: **PASS_WITH_FOLLOWUPS / W9 CLOSED**

Current follow-up posture (post-S1/S3):

```text
external executor recovery   CLOSED
official Python SDK           PARKED / NOT PRIORITIZED
active W9 software follow-up  NONE
```

The historical gate result remains `PASS_WITH_FOLLOWUPS`; the follow-up statuses above describe the current state and do not rewrite the original gate decision.

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

Result: **PASS — S1 RECOVERY FOLLOW-UP CLOSED**

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

The S1 follow-up is now implemented in `krukmat/verifiable-event-ledger`.

The executor classifies local state as `READY`, `ALREADY_APPLIED_CANDIDATE`, or stale. When HEAD is already the approved source commit, it calls HAA again with the **same durable executionId**, requires HAA to return the already-issued grant, detached-verifies the original request/execution/action/audience binding, re-checks branch/target/worktree, and returns `ALREADY_APPLIED` without invoking Git merge again.

A retry with a different execution ID after consumption remains denied by HAA. The executor also recomputes the canonical HAA action digest locally before authorization so a changed repository/source/target/target-before fails closed.

A real temporary-Git automated test proves first execution `MERGED` followed by same-ID `ALREADY_APPLIED` with exactly one `git merge --ff-only` invocation.

Closure evidence:

```text
VEL commit  0e942480b2b8a9b5a0fb2f17c9ea5de4161a28a5
CI          PASS
```

Classification: `INTEGRATION_FIX`, severity P2 — **CLOSED**.

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
| No official Python HAA SDK; Python consumer implements detached verifier from the public protocol | `INTEGRATION_FIX` | P2 | **PARKED / NOT PRIORITIZED** — current consumer is functional; revisit only for concrete adoption demand |
| Post-merge same-execution recovery in the reference executor | `INTEGRATION_FIX` | P2 | **CLOSED** — automated same-ID reconciliation, detached grant verification and real-Git at-most-once test |
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

W9 is closed. The executor-recovery P2 is closed. The Python SDK/DX idea is PARKED / NOT PRIORITIZED, leaving no active W9 software follow-up. None of these follow-up decisions reopen HAA core or the closed W7/W8 security baselines.

Hardware W5/W6 remains deferred/blocked as previously decided. WebAuthn W7-T04 is complete with decision `KEEP_OPTIONAL`.
