# Architecture

```text
Requester/Agent
    │ authenticated ActionSpec
    ▼
HAA Core / Service
    ├─ canonical action + intent digests
    ├─ signed challenge payload bytes
    ├─ lifecycle / audit
    └─ atomic authorizeAndConsume
    │
    ├───────────────┐
    ▼               ▼
Apple adapter    DIY adapter (gated)
Secure Enclave   ESP32 + sensor + display
    │               │
    └──────┬────────┘
           ▼
    ApprovalEvidence
           ▼
     VerifiedEvidence
           ▼
  ApprovalReceipt (audit)
           ▼
 authorizeAndConsume(actual action)
           ▼
 ExecutionGrant
           ▼
        Executor
```

The challenge envelope carries base64url canonical payload bytes plus the HAA signature. Authenticators verify exactly those bytes, then decode them for display. They do not independently re-canonicalize JSON.

The core must never branch on Touch ID, fingerprint, Apple, ESP32 or other authenticator technology.
