# macOS HAA Approver

Native macOS authenticator for the HAA protocol. It verifies HAA-signed challenge bytes before rendering structured approval claims. The signing key is P-256 in Secure Enclave with private-key usage protected by `biometryCurrentSet`; use of the key requires system biometric authorization.

## Ceremony UX

The macOS approver now exposes three distinct outcomes:

```text
Approve with Touch ID -> APPROVE
Esc                   -> REJECT
close / local timeout -> UNKNOWN
```

The trusted alert intentionally has no prominent Reject button. The informative text shows `Esc: Reject` and Escape is the only initial explicit negative-decision gesture.

Positive approval preserves the existing output contract: after successful Touch ID / Secure Enclave signing, stdout contains `haa.evidence.v1` and the process exits `0`.

Explicit Escape prints a challenge-bound result such as:

```json
{"outcome":"REJECT","requestId":"...","challengeDigest":"sha256:...","reason":"USER_ESCAPE"}
```

and exits `3`. That local result must be submitted through the HAA reject service/SDK using the configured approver credential before the server state becomes `REJECTED`.

Indeterminate outcomes print `UNKNOWN` and exit `4`. Supported initial reasons include `WINDOW_CLOSED`, `LOCAL_TIMEOUT`, `INTERACTION_ERROR` and `AUTHENTICATOR_UNAVAILABLE`. UNKNOWN is not a human rejection and does not mutate the server request state.

Use optional `--timeout-seconds <seconds>` for a local ceremony timeout. A local timeout is UNKNOWN; it is not request expiry.

## Build/runtime boundary

`Package.swift` remains useful for source-level tests and compile checks. It is **not** the production validation runtime for Secure Enclave enrollment: a standalone CLI has no place to embed the provisioning profile required by the macOS Data Protection Keychain.

The real validation path compiles these same sources through `../haa-approver-app/HAAApprover.xcodeproj`, producing a provisioned `HAAApprover.app`. The gate then runs `HAAApprover.app/Contents/MacOS/HAAApprover` as the CLI entry point.

Run from the repository root:

```bash
npm run validate:macos
npm run validate:agent-macos
```

See `docs/MACOS-RUNBOOK.md` for Xcode/team prerequisites and failure diagnostics, and `docs/W8-CEREMONY-OUTCOMES.md` for the universal outcome contract.
