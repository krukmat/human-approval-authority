# Implementation status

## Functional status

- **W0:** DONE
- **W1:** DONE
- **W2:** DONE
- **W3-T01:** DONE
- **W3-T02/T03/T04:** implementation complete; real Touch ID/Secure Enclave behavior requires local macOS validation
- **W3-T05:** DONE
- **W3-T06:** READY_FOR_LOCAL_VALIDATION via `npm run validate:macos`
- **W4-T01/T02/T03/T04:** DONE
- **W4-T05:** READY_FOR_LOCAL_VALIDATION via `npm run validate:agent-macos`
- **W4-T06:** BLOCKED until W4-T05 passes and the hardware value criteria are evaluated
- **W5/W6 hardware:** BLOCKED by W4-T06 value gate
- **W7:** BLOCKED by W4-T05 / release gates

## Current quality gate

GitHub CI is green for the implemented cloud-testable surface:

- TypeScript runtime security tests pass.
- MCP stdio smoke test validates that only `request_approval` and `approval_status` are exposed.
- Production TypeScript sources pass strict `tsc --noEmit`.
- Idempotent retry after resource mutation returns the original grant while a different execution ID is rejected.
- The external reference executor obtains an `ExecutionGrant` before mutating its bounded resource and does not reapply the side effect for the same execution ID.

## Local physical gates

The remaining uncertainty is intentionally physical rather than architectural:

1. `npm run validate:macos` validates the Secure Enclave / Touch ID ceremony end to end.
2. `npm run validate:agent-macos` validates the complete agentic boundary: MCP requester → human Touch ID → bounded external executor.

Both commands require a real macOS host with Touch ID and Secure Enclave. The validation authenticator key is device-bound; the approver CLI now supports explicit deletion so validation keys can be cleaned up after a run.

## Hardware boundary

Do not begin W5/W6 firmware or purchase-driven implementation until W4-T06 records PASS. The DIY terminal remains a conditional authenticator subplan whose value proposition is host separation, dedicated trusted presentation, portability and a physical approval boundary—not a claim of higher cryptographic assurance than Apple's Secure Enclave.
