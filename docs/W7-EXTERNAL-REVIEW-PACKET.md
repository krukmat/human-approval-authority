# W7-T05 independent security / architecture review packet

Status: **READY_FOR_EXTERNAL_REVIEW**

Purpose: give an independent reviewer enough structure to challenge the current HAA software product without expanding scope into hardware, W8 ceremony work, or external product integrations.

The reviewer MUST record the exact `main` commit SHA reviewed. W7-T05 is not complete merely because this packet exists.

## Review objective

Answer this question:

> Does the current HAA software architecture preserve exact human authorization, identity separation and bounded single-use execution authority under the documented threat model, with no BLOCKING defect in the W7 production-hardening surface?

Do not optimize for stylistic improvements. Prioritize security boundary violations, inconsistent authority semantics, cryptographic binding mistakes, replay/concurrency issues, unsafe recovery behavior, and protocol-v1 compatibility breaks.

## Scope

Review:

```text
packages/protocol
packages/core
packages/persistence-sqlite
packages/sdk-ts
apps/haa-server
apps/cli
apps/mcp
scripts/*client*
scripts/*authority*
scripts/*audit*
scripts/*backup*
docs/SECURITY.md
docs/PROTOCOL-V1.md
docs/SECURITY-REVIEW-V1.md
docs/SELF-HOSTING.md
docs/NETWORK-EDGE.md
docs/AUDIT-INTEGRITY.md
docs/BACKUP-RECOVERY.md
docs/BUILD-REPRODUCIBILITY.md
tests/*.test.ts
```

Out of scope unless a finding directly crosses the boundary:

- W5/W6 hardware implementation;
- W8 APPROVE/REJECT/UNKNOWN changes;
- WebAuthn optional spike;
- DubBridge or any external product integration.

## Non-negotiable invariants

The review should treat these as product requirements, not optional design preferences:

1. approval binds one canonical exact action;
2. requester cannot be the approver principal;
3. agents/requesters cannot gain approver authority through ordinary APIs;
4. authenticator evidence binds the expected human principal and exact HAA challenge;
5. trusted display derives from signed typed intent;
6. ApprovalReceipt is never execution authority;
7. only `authorizeAndConsume(actualAction, executionId)` can create an ExecutionGrant;
8. executor audience, action digest and mutable preconditions are checked before first consume;
9. first consume is atomic; same execution ID is idempotent; a new execution ID after consume is denied;
10. unknown profile/schema/evidence/key/algorithm fails closed;
11. authority rotation never silently downgrades and retired public keys remain usable for historical verification;
12. detached grants can be verified without trusting an intermediary;
13. audit tampering after a signed checkpoint is detectable without the authority private key;
14. restore never silently pairs the wrong database and authority identity;
15. frozen protocol-v1 signed object semantics are not changed by hardening work.

## Required adversarial review areas

### Identity / provisioning

Challenge:

- client role escalation or mixed-role misuse;
- credential rotation/expiry/disable edge cases;
- requester creating an approval for another credential it controls;
- read authorization across unrelated request participants;
- provisioning assumptions that are stronger than documentation admits.

### Cryptography / canonicalization

Challenge:

- canonical JSON ambiguity;
- cross-language P-256 / Ed25519 encoding assumptions;
- wrong `authorityKeyId` or algorithm substitution;
- signed-object mutation / extra-field handling;
- key-ring active/retired mismatch and rotation interruption.

### Approval / execution lifecycle

Challenge:

- stale challenges;
- evidence replay;
- concurrent evidence submission;
- concurrent consumes;
- execution-ID conflicts;
- stale mutable preconditions;
- post-consume retry behavior;
- any path that could treat a receipt as capability.

### Authenticator assurance

Confirm that claims do not exceed evidence. In particular, HAA v1 must not imply Apple platform/Secure Enclave attestation when it only proves enrollment trust plus registered-key signing behavior with user verification.

### Detached ExecutionGrant verification

Challenge:

- canonicalization divergence between core signing and SDK verification;
- unknown/retired key handling;
- action/request/execution/audience binding;
- expiry boundary;
- malicious extra fields;
- algorithm confusion.

### Audit integrity

Challenge:

- migration from pre-chain databases;
- partial integrity rows;
- deletion/reordering/modification;
- DBA recomputation of the unsigned chain;
- signed checkpoint verification after authority rotation;
- transactional behavior of CONSUMED + grant + audit insertion;
- documented boundary that admin credential audit is a separate operational stream.

### Backup / recovery

Challenge:

- SQLite snapshot correctness;
- key rotation racing with backup;
- checksum substitution;
- active private key vs key-ring consistency;
- audit-head consistency;
- partial restore failure;
- overwrite guard;
- unsupported HA/multi-writer assumptions.

### Network / self-host

Challenge:

- loopback vs edge binding policy;
- plain HTTP exposure assumptions;
- forwarded-header trust;
- request size / rate-limit responsibilities;
- secret leakage through logs/process arguments/configuration;
- container privilege / persistent-volume assumptions.

### Protocol compatibility

Confirm that W7 hardening has not added authorization-significant fields to frozen signed v1 objects or changed canonical/action/receipt/grant semantics in place.

## Commands to run

At minimum:

```bash
npm ci
npm run pack:check
npm test
npx tsc --noEmit
docker build -t haa-review .
```

Review the CI workflow and confirm it uses the committed dependency graph.

Physical Touch ID validation may be cited from existing evidence; it is not necessary to reproduce physical hardware for this software-only review unless the reviewer finds a Mac-specific blocker.

## Finding format

Every finding should use:

```text
ID: W7R-XX
Severity: BLOCKING | P1 | P2 | ACCEPTED-RISK
Area: identity | protocol | crypto | lifecycle | authenticator | executor | audit | backup | network | build | other
Evidence: exact files/functions/tests
Attack/failure scenario: concrete sequence
Impact: what invariant fails
Recommendation: minimum safe correction
Regression test: required observable behavior
```

Avoid generic recommendations without an exploitable/failure scenario.

## Required final decision

The reviewer must provide one of:

```text
PASS
  no BLOCKING findings remain

PASS_WITH_FOLLOWUPS
  no BLOCKING findings remain; P1/P2 work is explicit and accepted for the declared release posture

FAIL
  one or more BLOCKING findings remain
```

W7-T05 can move to `DONE` only for `PASS` or an explicitly accepted `PASS_WITH_FOLLOWUPS` with no BLOCKING finding.

W7-T15 can move to `DONE` only after W7-T05 is closed and the final main CI remains green.
