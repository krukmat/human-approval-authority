# Implementation status

## Functional status

- **W0:** DONE
- **W1:** DONE in validated workspace
- **W2:** DONE in validated workspace
- **W3-T01:** DONE
- **W3-T02/T03/T04:** source implemented; real Touch ID/Secure Enclave validation required on macOS
- **W3-T05:** DONE
- **W3-T06:** BLOCKED on real Mac validation
- **W4-T01/T02/T04:** DONE
- **W4-T03:** source implemented; integration validation pending
- **W4-T05/T06:** BLOCKED by W3-T06
- **W5/W6 hardware:** BLOCKED by W4-T06 value gate
- **W7:** BLOCKED by value/integration gates

## GitHub connector sync limitation

The validated workspace contains all implementation files. The ChatGPT GitHub connector refused writes for these files through its safety controls, so they are intentionally not altered to work around the guardrail:

- `packages/core/src/actions.ts`
- `packages/core/src/challenge.ts`
- `AGENTS.md`

Until the two TypeScript files are copied from the complete workspace, remote CI is expected to fail module resolution. This is a publication limitation, not a design change or an invitation to replace the contracts with simplified placeholders.

Complete workspace artifacts are maintained separately from the remote publication attempt.
