# Current implementation plan

## Waves

```text
W0 Foundation & Contracts                    DONE
W1 Universal HAA Core                        DONE
W2 HAA Service & Enforcement                 DONE
W3 Apple Authenticator                       DONE + physical validation
W4 Agent Integration & Value Gate            DONE + physical validation
W5 Hardware Authenticator POC                DEFERRED
W6 Hardware Hardening                        BLOCKED by W5
W7 Software Production Hardening             DONE baseline
  └─ W7-T04 Optional WebAuthn spike          IN_PROGRESS
W8 Universal Ceremony Outcomes               DONE + physical validation
W9 Reference Integration / Adoption Gate     DONE / PASS_WITH_FOLLOWUPS
```

The accepted W7/W8/W9 software baselines remain closed. Reactivating the optional W7-T04 adapter does not reopen protocol v1 or the production/adoption gates.

## W7-T04 — optional WebAuthn adapter spike

Approved task sequence:

```text
T04.1  Assurance contract                   DONE
T04.2  WebAuthn authenticator model         DONE
T04.3  Registration ceremony                DONE
T04.4  Approval challenge binding           DONE
T04.5  WebAuthn assertion verifier          DONE
T04.6  WebAuthn evidence adapter            DONE
T04.7  Browser approval UI                  DONE
T04.8  Negative-path automated tests        DONE
T04.9  Physical browser gate                READY
T04.10 Spike adoption decision              BLOCKED by T04.9
```

The WebAuthn spike is disabled by default and preserves the frozen protocol-v1 types. It reports `user-verified` assurance and does not claim the native trusted display, device binding or platform attestation of the macOS Secure Enclave path.

The physical gate and decision record are defined in `docs/W7-T04-WEBAUTHN-SPIKE.md`.

## Stable primitives

ActionSpec, ApprovalIntent, ApprovalRequest, ApprovalChallengePackage, ApprovalEvidence, VerifiedEvidence, ApprovalReceipt, ExecutionGrant, AuthenticatorRecord, AuditEvent.

## Core rules

A new human-verification mechanism must be implementable as an authenticator/evidence adapter without changing ActionSpec, ApprovalIntent, approval lifecycle, receipt semantics, execution-grant semantics or audit semantics.

A new product integration must be implementable as an ActionProfile plus requester/executor adapter without introducing consumer-specific behavior into the universal HAA core.

`ApprovalReceipt` and request state `APPROVED` never authorize execution. Only an exact, detached-valid `ExecutionGrant` returned after `authorizeAndConsume(actualAction, executionId)` grants execution authority.

## Completed adoption proof

W9 proved the public product boundary with `krukmat/verifiable-event-ledger`:

```text
external requester
  -> HAA
  -> physical human Touch ID ceremony
  -> exact ExecutionGrant
  -> detached-verifying external Python executor
  -> bounded git merge --ff-only side effect
  -> CONSUMED exactly once
```

No private HAA import was required. DubBridge is not an active HAA dependency or prerequisite.

## Remaining optional product directions

After W7-T04 is decided, the only previously planned optional/deferred directions are:

- WebAuthn adoption beyond the spike, only if T04.10 chooses `ADOPT`;
- W5 hardware POC, if dedicated hardware value is reprioritized;
- W6 hardware hardening, only after W5 proves value;
- W9 P2 developer-experience follow-ups such as an official Python SDK and improved external-executor recovery ergonomics.

## Hardware justification

The DIY terminal exists only to add host separation, dedicated trusted presentation, portability/vendor neutrality and a physical human gate. It is not assumed to be stronger than Apple Secure Enclave. Firmware is part of the hardware trusted computing base.

W4-T06 authorizes a future W5 POC; it does not make hardware a current product priority.
