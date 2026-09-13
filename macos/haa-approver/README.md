# macOS HAA Approver

Native macOS authenticator for the HAA protocol. It verifies HAA-signed challenge bytes before rendering structured approval claims. The signing key is P-256 in Secure Enclave with private-key usage protected by `biometryCurrentSet`; use of the key requires system biometric authorization.

`Package.swift` remains useful for source-level tests and compile checks. It is **not** the production validation runtime for Secure Enclave enrollment: a standalone CLI has no place to embed the provisioning profile required by the macOS Data Protection Keychain.

The real validation path compiles these same sources through `../haa-approver-app/HAAApprover.xcodeproj`, producing a provisioned `HAAApprover.app`. The gate then runs `HAAApprover.app/Contents/MacOS/HAAApprover` as the CLI entry point.

Run from the repository root:

```bash
npm run validate:macos
npm run validate:agent-macos
```

See `docs/MACOS-RUNBOOK.md` for Xcode/team prerequisites and failure diagnostics.
