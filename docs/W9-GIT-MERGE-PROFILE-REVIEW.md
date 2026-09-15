# W9-T04 — `git.merge.v1` real ActionProfile review

Status: **PASS / NO CORE CHANGE REQUIRED**

External consumer: `krukmat/verifiable-event-ledger`

Purpose: validate that the existing HAA `git.merge.v1` profile is sufficient for the first external adoption slice before adding any consumer-specific profile or widening HAA core semantics.

## External action

The reference consumer requests exactly:

```json
{
  "schema": "haa.action.v1",
  "type": "git.merge.v1",
  "payload": {
    "repository": "krukmat/verifiable-event-ledger",
    "sourceCommitSha": "<full source commit>",
    "targetBranch": "main",
    "targetCommitBefore": "<full target commit before merge>"
  }
}
```

No extra `preconditions` object is accepted for this profile.

## Core profile review

The built-in profile already enforces an exact payload allowlist:

```text
repository
sourceCommitSha
targetBranch
targetCommitBefore
```

Unexpected payload fields fail closed. Any precondition field also fails closed.

All authorization-relevant action fields are included in HAA's canonical `ActionSpec` digest. Therefore a change to repository, source commit, target branch or target-before commit changes the approved action digest and cannot reuse the original approval.

## Trusted display

The trusted ceremony displays:

```text
ACTION:        GIT MERGE
REPOSITORY:    <repository>
SOURCE:        <sourceCommitSha>
TARGET:        <targetBranch>       [warning emphasis]
TARGET BEFORE: <targetCommitBefore>
```

For this integration, these are the complete human-significant semantics of the authority decision. There is no hidden merge mode, path selection, force flag, remote or post-merge operation inside the HAA action.

Result: **PASS — complete display for the bounded reference action.**

## Stale-state / TOCTOU contract

The profile uses `targetCommitBefore` as both:

1. a digest-bound/displayed authorization field; and
2. the expected target state checked during `authorizeAndConsume(...)`.

At execution time HAA requires:

```text
actualState.targetCommit == action.payload.targetCommitBefore
```

otherwise authorization fails with `STALE_APPROVAL`.

The external executor additionally resolves the real target HEAD immediately before authorization and checks it again after detached grant verification before performing the Git mutation.

Result: **PASS — HAA owns the approval/state binding; the consumer closes its local side-effect TOCTOU window.**

## Consumer-specific constraints kept outside HAA

The external VEL executor adds stricter local policy:

- repository identity is pinned to `krukmat/verifiable-event-ledger`;
- source commit must resolve to the same full commit SHA;
- target branch must be the checked-out branch;
- worktree must be clean;
- merge operation is restricted to `git merge --ff-only`;
- Git commands use argv, not shell interpolation.

These constraints are execution-environment policy, not missing universal HAA authorization semantics. Moving them into the generic profile would couple HAA to one consumer's Git operating model.

## Syntax validation observation

`git.merge.v1` currently validates the four fields as non-empty strings rather than enforcing Git-specific SHA/ref syntax in HAA core.

For this reference integration that is not a blocking gap because:

- HAA binds and displays the exact supplied strings;
- the external executor resolves/pins commit objects locally before requesting execution authority;
- an invalid or abbreviated source that does not resolve to the exact full commit fails closed before `/authorize`;
- the local executor restricts target/repository according to its own policy.

Classification: **INTEGRATION_POLICY / NO CORE CHANGE**.

A future multi-consumer requirement for a stronger portable Git identifier grammar can be considered only if adoption evidence shows value across consumers.

## W9-T04 acceptance

```text
typed/versioned profile                         PASS
strict payload allowlist                        PASS
unknown payload fields fail closed              PASS
unknown precondition fields fail closed         PASS
repository digest-bound + displayed             PASS
source commit digest-bound + displayed          PASS
target branch digest-bound + displayed          PASS
target-before digest-bound + displayed          PASS
stale target checked at authorize               PASS
consumer-local Git policy kept outside core     PASS
new HAA core profile required                    NO
protocol-v1 change required                      NO
```

W9-T04 is complete. The existing `git.merge.v1` profile is accepted as the real ActionProfile for the first external consumer.
