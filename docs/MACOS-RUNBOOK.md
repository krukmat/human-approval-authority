# macOS Touch ID runbook

W3 cannot pass without a real Mac with Touch ID / Secure Enclave.

## Preferred validation

From the repository root on the target Mac:

```bash
npm install
npm run validate:macos
```

The validation script performs the full W3-T06 gate:

1. Starts an isolated HAA server with temporary SQLite storage and authority key.
2. Builds the Swift approver in release mode.
3. Creates a new device-bound Secure Enclave P-256 key protected by the current biometric set.
4. Registers the authenticator with HAA.
5. Creates an exact `demo.action.v1` approval request and signed challenge.
6. Launches the native trusted presentation and Touch ID approval.
7. Submits the signed `ApprovalEvidence` and verifies an `ApprovalReceipt` is issued.
8. Confirms a mutated action is denied with `ACTION_DIGEST_MISMATCH`.
9. Confirms stale resource state is denied with `STALE_APPROVAL` without consuming the approval.
10. Authorizes the exact action, confirms idempotent retry, denies a second execution ID, and verifies the audit lifecycle.

Success ends with:

```text
PASS W3-T06: Apple Secure Enclave / Touch ID end-to-end gate
```

The script uses a unique authenticator ID each run. Keys are device-bound and are not exported; validation server files are temporary and removed when the run ends.

## Requirements

- macOS host with Secure Enclave and Touch ID configured.
- Swift toolchain available (`swift --version`).
- Node.js 24+.
- Port `8791` free, or set `HAA_VALIDATION_PORT` to another local port.

## Manual fallback

If the automated gate fails before the biometric ceremony, reproduce the individual steps manually:

1. Start HAA with persistent authority key and dev clients.
2. Fetch `GET /v1/authority-key` and save `publicKeyPem`.
3. Build `macos/haa-approver` on macOS.
4. Run `haa-approver --enroll --authenticator-id <id>` and register the returned P-256 public key through `POST /v1/authenticators` using the human principal API key.
5. Create an approval request with the agent API key.
6. Issue the challenge with the human API key and save the JSON.
7. Run `haa-approver --challenge challenge.json --authority-public-key authority.pem --authenticator-id <id>`.
8. Confirm the native display fields, approve with Touch ID, then submit returned `ApprovalEvidence` to `POST /v1/approval-evidence`.
9. Execute through the authorize endpoint and verify mutation, stale-precondition and single-use protections.
