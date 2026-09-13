# Agent execution guidance

Use one bounded task per session. Feed the agent the active task, direct dependency handoffs and only relevant source files.

Recommended routing snapshot (2026-09-13):
- Normal implementation: Claude Sonnet 5 or GPT-5.6 Terra (medium).
- Mechanical edits/tests/docs: GPT-5.6 Terra low/medium or Sonnet 5 normal.
- Security/crypto/wave gates: GPT-5.6 Sol medium/high, or Sonnet 5 with extended reasoning; cross-model review when quota allows.

Do not spend premium reasoning on scaffolding. Escalate after two failed bounded attempts rather than accumulating transcript context.

## Project invariants

- Core is authenticator-agnostic.
- HAA never receives biometric material.
- Receipt is audit evidence, not an execution bearer token.
- All execution goes through atomic authorizeAndConsume.
- Hardware remains gated until W4-T06 PASS.
