# macOS Touch ID runbook

W3 cannot pass without a real Mac with Touch ID/Secure Enclave.

1. Start HAA with persistent authority key and dev clients.
2. Fetch `GET /v1/authority-key` and save `publicKeyPem`.
3. Build `macos/haa-approver` on macOS.
4. Run `haa-approver --enroll --authenticator-id <id>` and register the returned P-256 public key through `POST /v1/authenticators` using the human principal API key.
5. Create an approval request with the agent API key.
6. Issue the challenge with the human API key and save the JSON.
7. Run `haa-approver --challenge challenge.json --authority-public-key authority.pem --authenticator-id <id>`.
8. Confirm the native display fields, approve with Touch ID, then submit returned ApprovalEvidence to `POST /v1/approval-evidence`.
9. Execute through the reference executor/authorize endpoint and verify single use.

Acceptance requires evidence that changed action or preconditions are denied after human approval.
