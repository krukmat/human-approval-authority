# Authenticator assurance model

Status: **HAA v1 baseline + optional WebAuthn spike**

HAA separates what the protocol cryptographically verifies from what the enrollment and authenticator implementation assert about a device.

## Assurance levels

`VerifiedEvidence.humanVerificationLevel` has three existing protocol-v1 values:

- `presence` — the verifier establishes evidence from the enrolled authenticator, without claiming biometric/user verification.
- `user-verified` — the authenticator path establishes an explicit local user-verification ceremony before producing valid evidence.
- `user-verified-device-bound` — the authenticator path asserts explicit local user verification and use of a device-bound enrolled signing key.

These values describe the assurance produced by the configured authenticator path. They are **not platform-attestation statements** and they do not, by themselves, claim that the human-visible action was rendered in a trusted native display.

## Apple Secure Enclave path

The physically validated macOS path currently provides:

1. authenticated enrollment into HAA;
2. a registered P-256 public key associated with the human principal;
3. an Apple-side implementation that creates/uses a Secure Enclave-backed key and gates signing with Touch ID / the current biometric set;
4. HAA challenge verification and native trusted display before the local signing ceremony;
5. server-side signature verification against the enrolled public key.

For this path HAA reports `user-verified-device-bound`.

### Explicit limitation

HAA v1 does **not** independently verify Apple hardware/platform attestation proving that an enrolled public key was generated inside a genuine Secure Enclave. The server trusts the authenticated enrollment path plus the declared/supported authenticator type and then verifies possession of the enrolled key.

Therefore documentation and APIs must not describe HAA v1 as providing Apple Secure Enclave attestation, hardware provenance attestation, or remote platform attestation.

## Optional WebAuthn path

W7-T04 evaluates a browser WebAuthn authenticator without changing protocol v1. Its intended assurance is deliberately narrower:

```text
humanVerificationLevel = user-verified
WebAuthn UV              required
WebAuthn UP              required
RP ID                    exact verifier policy
origin                   exact verifier policy
action binding           exact HAA challenge digest
trusted native display   NOT CLAIMED
platform attestation     NOT CLAIMED
hardware provenance      NOT CLAIMED
```

The WebAuthn assertion is cryptographically bound to the digest of the exact HAA challenge. That challenge already binds the request, action digest, intent digest, authenticator, approver, executor audience, policy snapshot, display claims, nonce and expiry.

The browser UI may render those exact HAA display claims for the human, but this is an **authenticated web-origin/DOM display**, not the native trusted display used by the macOS approver. A compromised web origin can misrepresent what the human sees even though it cannot make the assertion authorize a different HAA action digest.

The spike uses `attestation=none`. AAGUID, transports and credential metadata may be recorded for lifecycle/operational purposes, but HAA does not treat them as evidence of hardware identity or platform provenance.

For these reasons the WebAuthn spike reports `user-verified`, not `user-verified-device-bound`.

No biometric data, Touch ID template or biometric result is received or persisted by HAA in either authenticator path.

## Trust boundary

```text
trusted provisioning / enrollment
          │
          ▼
AuthenticatorRecord(type + public key + principal)
          │
          ├── native macOS ceremony → native trusted display + Touch ID
          │
          └── WebAuthn ceremony     → web-origin display + UV-required assertion
          │
          ▼
signed / verified ApprovalEvidence
          │
          ▼
HAA verifier
```

The HAA verifier can prove that valid evidence was produced by the private key corresponding to the enrolled public key and that it is bound to the exact challenge. The strength of claims about where that private key lives and what display the human trusted depends on the authenticator implementation and enrollment trust model unless a stronger attestation/display mechanism is added.

## Future attestation

Platform/device attestation, if added later, must be an explicit versioned capability with:

- a defined trust root;
- attestation-chain verification;
- enrollment binding;
- revocation/update policy;
- clear fallback behavior;
- no silent upgrade of existing `user-verified-device-bound` or WebAuthn `user-verified` semantics.

Until then, attestation is outside the HAA v1 assurance claim.
