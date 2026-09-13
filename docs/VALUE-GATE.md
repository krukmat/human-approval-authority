# W4-T06 — Hardware Value Gate

Status: **PENDING W4-T05 local validation**

This gate decides whether the DIY hardware authenticator subplan (W5/W6) is worth implementing. It is deliberately separate from the question of whether HAA itself works.

## Prerequisite evidence

The gate cannot be evaluated until `npm run validate:agent-macos` ends with:

```text
PASS W4-T05: real MCP agent → human Touch ID → bounded executor scenario
```

That run must demonstrate all of the following:

- an agent can request approval through the bounded MCP surface;
- the external executor cannot act while the request is PENDING;
- a human approves signed, structured action claims using Touch ID / Secure Enclave;
- the exact action receives an ExecutionGrant and is applied once;
- a retry with the same execution ID is idempotent after resource mutation;
- a different execution ID is denied after consumption;
- the agent can observe final status but has no self-approval or generic execution tool;
- audit contains exactly one CONSUMED event.

## Hardware-value criteria

After W4-T05 passes, score each property `0 = no value`, `1 = useful`, `2 = material requirement`.

| Property | What hardware adds | Score |
|---|---|---:|
| Host separation | Approval display/signing can remain trustworthy even if the agent host is treated as untrusted transport | TBD |
| Dedicated trusted display | A small independent screen renders only HAA-signed display claims | TBD |
| Portability/vendor independence | Approval endpoint can move across hosts without depending on Apple hardware | TBD |
| Physical approval boundary | High-risk actions have a visible, dedicated physical human gate | TBD |

## Decision rule

- **PASS:** W4-T05 passes **and** at least one property scores `2`, with a concrete target workflow that benefits from it.
- **DEFER:** HAA works, but no hardware property is currently material. Keep W5/W6 blocked and continue with software packaging/integrations when their dependencies permit.
- **FAIL:** W4-T05 exposes a core protocol/enforcement flaw. Fix the software architecture before reconsidering hardware.

A PASS authorizes W5 only. It does not pre-authorize W6 hardening decisions or hardware purchases beyond the POC BOM.

## Explicit non-arguments for PASS

These are not sufficient reasons to build hardware:

- fingerprint scanning is interesting;
- DIY hardware is visually differentiated;
- a secure element sounds safer;
- the terminal is assumed to be more secure than a Mac Secure Enclave.

The DIY terminal exists only if its separate physical trust boundary creates measurable workflow value.
