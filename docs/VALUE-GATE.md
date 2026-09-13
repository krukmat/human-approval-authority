# W4-T06 — Hardware Value Gate

Status: **PASS — W5 POC AUTHORIZED**

Decision date: **2026-09-13**

This gate decides whether the DIY hardware authenticator subplan (W5/W6) is worth implementing. It is deliberately separate from the question of whether HAA itself works.

## Prerequisite evidence

`npm run validate:agent-macos` completed successfully on a real Apple Silicon Mac with Touch ID and ended with:

```text
PASS W4-T05: real MCP agent → human Touch ID → bounded executor scenario
```

The run demonstrated all required properties:

- an agent requested approval through the bounded MCP surface;
- the external executor was blocked while the request was PENDING and the resource remained unchanged;
- a human approved signed, structured action claims using Touch ID / Secure Enclave;
- the exact action received an ExecutionGrant and was applied once;
- retry with the same execution ID was idempotent after resource mutation;
- a different execution ID was denied after consumption;
- the agent observed final CONSUMED status without self-approval or generic execution capability;
- audit contained exactly one CONSUMED event.

The successful W4-T05 scenario also subsumes the W3-T06 Apple end-to-end gate.

## Hardware-value scoring

Score: `0 = no value`, `1 = useful`, `2 = material requirement`.

| Property | What hardware adds | Score | Rationale |
|---|---|---:|---|
| Host separation | Approval display/signing can remain trustworthy even if the agent host is treated as untrusted transport | **2** | This is the primary hardware thesis. A dedicated terminal removes the approver UI/signing key from the workstation or host running/transporting the agent action. |
| Dedicated trusted display | A small independent screen renders only HAA-signed display claims | **2** | For high-risk agent actions, an independent renderer materially improves the human trust boundary compared with a UI on the same host as the agent/executor tooling. |
| Portability/vendor independence | Approval endpoint can move across hosts without depending on Apple hardware | **1** | Useful for multi-host and non-Apple deployment, but not required to prove the current HAA product. |
| Physical approval boundary | High-risk actions have a visible, dedicated physical human gate | **2** | A separate terminal makes the approval ceremony physically distinct from the agent host and is valuable for actions such as deploy/merge/external-operation approvals. |

## Concrete target workflow

Initial hardware POC target:

```text
Agent requests a high-risk deployment/merge-style action
        ↓
HAA issues a signed, exact-action challenge
        ↓ USB transport only
Dedicated terminal verifies challenge signature
        ↓
Dedicated display renders trusted signed claims
        ↓
Human locally verifies and approves
        ↓
Terminal emits signed ApprovalEvidence
        ↓
HAA authorizeAndConsume → ExecutionGrant → bounded executor
```

The POC is successful only if the terminal adds this independent trust boundary without changing HAA core semantics.

## Decision

**PASS.** W4-T05 passed and multiple hardware properties score `2` for a concrete high-risk agentic workflow.

This PASS authorizes **W5 POC only**.

It does **not** pre-authorize:

- W6 hardening;
- secure-element integration;
- production claims;
- certification claims;
- purchase decisions beyond the minimal POC BOM.

W6 remains blocked until W5-T07 passes.

## Explicit non-arguments for PASS

These are not reasons for the decision:

- fingerprint scanning is interesting;
- DIY hardware is visually differentiated;
- a secure element sounds safer;
- the terminal is assumed to be more secure than a Mac Secure Enclave.

The DIY terminal is authorized because its separate physical trust boundary creates workflow value that the Mac path cannot fully provide.
