# Final implementation plan

## Waves

- W0 Foundation & Contracts
- W1 Universal HAA Core
- W2 HAA Service & Enforcement
- W3 Apple Authenticator
- W4 Agent Integration & Value Gate
- W5 Hardware Authenticator POC (blocked until W4 PASS)
- W6 Hardware Hardening
- W7 Packaging / Optional Adapters

## Stable primitives

ActionSpec, ApprovalIntent, ApprovalRequest, ApprovalChallengePackage, ApprovalEvidence, VerifiedEvidence, ApprovalReceipt, ExecutionGrant, AuthenticatorRecord, AuditEvent.

## Core rule

A new human-verification mechanism must be implementable as an authenticator/evidence adapter without changing ActionSpec, ApprovalIntent, approval lifecycle, receipt semantics, execution-grant semantics, policy evaluation or audit semantics.

## Hardware justification

The DIY terminal exists only to add host separation, dedicated trusted presentation, portability/vendor neutrality and a physical human gate. It is not assumed to be stronger than Apple Secure Enclave. Firmware is part of the hardware trusted computing base.
