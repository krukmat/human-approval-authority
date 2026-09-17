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
W7 Software Production Hardening             DONE
  └─ W7-T04 Optional WebAuthn spike          DONE / KEEP_OPTIONAL
W8 Universal Ceremony Outcomes               DONE + physical validation
W9 Reference Integration / Adoption Gate     DONE / PASS_WITH_FOLLOWUPS
```

The accepted W7/W8/W9 software baselines remain closed. The optional W7-T04 adapter was completed without reopening protocol v1 or the production/adoption gates.

## W7-T04 — optional WebAuthn adapter spike

Final task sequence:

```text
T04.1  Assurance contract                   DONE
T04.2  WebAuthn authenticator model         DONE
T04.3  Registration ceremony                DONE
T04.4  Approval challenge binding           DONE
T04.5  WebAuthn assertion verifier          DONE
T04.6  WebAuthn evidence adapter            DONE
T04.7  Browser approval UI                  DONE
T04.8  Negative-path automated tests        DONE
T04.9  Physical browser gate                DONE / PASS
T04.10 Spike adoption decision              DONE / KEEP_OPTIONAL
```

The WebAuthn adapter is disabled by default and preserves the frozen protocol-v1 types. It reports `user-verified` assurance and does not claim the native trusted display, device binding or platform attestation of the macOS Secure Enclave path.

Physical validation completed on HAA SHA `52d7c8430a0d2508067f44711bc3656ee12e5887`, proving a real browser/platform WebAuthn approval through exact `ExecutionGrant` issuance and one-shot consumption.

Decision: `KEEP_OPTIONAL`. Native macOS remains the preferred higher-assurance path for high-risk actions; WebAuthn is retained for cases where browser portability and reach are worth the weaker presentation trust boundary.

The physical gate and decision record are in `docs/W7-T04-WEBAUTHN-SPIKE.md`.

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

The intentionally deferred/follow-up directions are now:

- WebAuthn production promotion beyond `KEEP_OPTIONAL`, only if future use cases justify the weaker browser-display assurance and the parser/production-origin review is completed;
- W5 hardware POC, if dedicated hardware value is reprioritized;
- W6 hardware hardening, only after W5 proves value;
- W9 P2 developer-experience follow-ups such as an official Python SDK and improved external-executor recovery ergonomics.

## Hardware justification

The DIY terminal exists only to add host separation, dedicated trusted presentation, portability/vendor neutrality and a physical human gate. It is not assumed to be stronger than Apple Secure Enclave. Firmware is part of the hardware trusted computing base.

W4-T06 authorizes a future W5 POC; it does not make hardware a current product priority.
