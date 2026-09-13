# Authenticator assurance model

Status: **HAA v1 baseline**

HAA separates what the protocol cryptographically verifies from what the enrollment and authenticator implementation assert about a device.

## Assurance levels

`VerifiedEvidence.humanVerificationLevel` has three existing protocol-v1 values:

- `presence` — the verifier establishes evidence from the enrolled authenticator, without claiming biometric/user verification.
- `user-verified` — the authenticator path asserts an explicit local user-verification ceremony before signing.
- `user-verified-device-bound` — the authenticator path asserts explicit local user verification and use of a device-bound enrolled signing key.

These values describe the assurance produced by the configured authenticator path. They are **not platform-attestation statements**.

## Apple Secure Enclave path

The physically validated macOS path currently provides:

1. authenticated enrollment into HAA;
2. a registered P-256 public key associated with the human principal;
3. an Apple-side implementation that creates/uses a Secure Enclave-backed key and gates signing with Touch ID / the current biometric set;
4. challenge verification and trusted display before the local signing ceremony;
5. server-side signature verification against the enrolled public key.

For this path HAA reports `user-verified-device-bound`.

### Explicit limitation

HAA v1 does **not** independently verify Apple hardware/platform attestation proving that an enrolled public key was generated inside a genuine Secure Enclave. The server trusts the authenticated enrollment path plus the declared/supported authenticator type and then verifies possession of the enrolled key.

Therefore documentation and APIs must not describe HAA v1 as providing Apple Secure Enclave attestation, hardware provenance attestation, or remote platform attestation.

## Trust boundary

```text
trusted provisioning / enrollment
          │
          ▼
AuthenticatorRecord(type + public key + principal)
          │
          ▼
local authenticator ceremony
          │
          ▼
signed ApprovalEvidence
          │
          ▼
HAA verifier
```

The HAA verifier can prove that valid evidence was produced by the private key corresponding to the enrolled public key and that it is bound to the exact challenge. The strength of claims about where that private key lives depends on the authenticator implementation and enrollment trust model unless a future attestation mechanism is added.

## Future attestation

Platform/device attestation, if added later, must be an explicit versioned capability with:

- a defined trust root;
- attestation-chain verification;
- enrollment binding;
- revocation/update policy;
- clear fallback behavior;
- no silent upgrade of existing `user-verified-device-bound` semantics.

Until then, attestation is outside the HAA v1 assurance claim.
