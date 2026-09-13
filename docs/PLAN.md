# Final implementation plan

## Waves

- W0 Foundation & Contracts — DONE
- W1 Universal HAA Core — DONE
- W2 HAA Service & Enforcement — DONE
- W3 Apple Authenticator — DONE / physically validated
- W4 Agent Integration & Value Gate — DONE / PASS
- W5 Hardware Authenticator POC — DEFERRED by product priority; authorized but not current work
- W6 Hardware Hardening — BLOCKED until a W5 POC proves value
- W7 Software Productization / Optional Adapters — ACTIVE
- W8 Product Integrations — FUTURE; DubBridge is the first planned integration

## W7 software-first order

1. **W7-T01 Protocol/version compatibility freeze.** Freeze the v1 public contracts, compatibility policy and extension rules before downstream integrations depend on them.
2. **W7-T02 Self-host/Docker package.** Make HAA reproducibly deployable with persistent state/key material, healthcheck and explicit configuration.
3. **W7-T03 Publishable TypeScript SDK.** Produce a stable package boundary, typed errors and generated JS/declarations suitable for external consumers.
4. **W7-T04 WebAuthn adapter spike.** Optional portability experiment; not required for the first product integration.
5. **W7-T05 Final security/architecture review.** Re-evaluate threat model, deployment assumptions, key lifecycle, compatibility and release readiness.

## W8 future product integrations

The first planned consumer is **DubBridge**, but integration is intentionally postponed until HAA's v1 protocol and SDK boundaries are stable.

Planned DubBridge sequence:

- define a typed `dubbridge.ai-execution.v1` ActionProfile for exact model/provider/task/cost/input binding;
- integrate HAA at DubBridge's execution boundary, after routing/policy decisions and before the bounded executor/provider call;
- preserve DubBridge routing/context authorities: HAA approves an already-decided exact action and does not choose model/provider/route;
- validate a real end-to-end path: DubBridge requester → HAA → human authenticator → ExecutionGrant → bounded execution;
- add cross-system audit/failure/retry semantics.

DubBridge integration is not a prerequisite for HAA productization and must not leak DubBridge-specific behavior into HAA core/protocol.

## Stable primitives

ActionSpec, ApprovalIntent, ApprovalRequest, ApprovalChallengePackage, ApprovalEvidence, VerifiedEvidence, ApprovalReceipt, ExecutionGrant, AuthenticatorRecord, AuditEvent.

## Core rule

A new human-verification mechanism must be implementable as an authenticator/evidence adapter without changing ActionSpec, ApprovalIntent, approval lifecycle, receipt semantics, execution-grant semantics, policy evaluation or audit semantics.

A new product integration must be implementable as an ActionProfile + requester/executor adapter without introducing product-specific behavior into the universal HAA core.

## Hardware justification

The DIY terminal exists only to add host separation, dedicated trusted presentation, portability/vendor neutrality and a physical human gate. It is not assumed to be stronger than Apple Secure Enclave. Firmware is part of the hardware trusted computing base.

W4-T06 passed because host separation and a dedicated physical approval boundary are materially useful for high-risk agent actions. That authorizes a future W5 POC; it does not make hardware the current product priority.
