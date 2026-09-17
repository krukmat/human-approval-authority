# W7-T04 — Optional WebAuthn adapter spike

Status: **DONE — physical gate PASS; decision KEEP_OPTIONAL**

This spike evaluates WebAuthn as an additional HAA authenticator without changing protocol v1 or weakening the accepted native macOS assurance model.

## T04.1 — Assurance contract

WebAuthn evidence is classified as:

```text
humanVerificationLevel = user-verified
trusted display         = authenticated web origin / DOM
platform attestation    = not claimed
hardware provenance     = not claimed
```

It is deliberately **not equivalent** to the existing Apple Secure Enclave approver:

```text
macOS approver
  HAA-signed typed intent
    -> native trusted display
    -> Touch ID
    -> Secure Enclave signature
    -> user-verified-device-bound

WebAuthn adapter
  HAA-signed typed intent
    -> browser-origin display
    -> WebAuthn UV=required
    -> assertion bound to HAA challenge digest
    -> user-verified
```

The WebAuthn assertion cryptographically binds to the exact HAA challenge digest. The browser-rendered action text is not promoted to a native trusted display: compromise of the web origin/DOM can misrepresent the human-visible claims even though it cannot change the HAA action that the assertion is bound to.

WebAuthn `UV=required` proves that the authenticator reports user verification. HAA does not cryptographically learn which local verification modality was used. A physical operator may observe Touch ID when the platform offers it, but the server must not turn that observation into a protocol-level Touch ID claim.

No biometric template, Touch ID data or biometric result is stored by HAA.

## Policy

The adapter remains disabled by default. Enabling it requires explicit configuration:

```text
HAA_WEBAUTHN_ENABLED=1
HAA_WEBAUTHN_RP_ID=<rp-id>
HAA_WEBAUTHN_ORIGIN=<exact-origin>
HAA_WEBAUTHN_RP_NAME=<display-name>
```

The browser UI is separately opt-in:

```text
HAA_WEBAUTHN_UI=1
```

Production origins must be HTTPS. Plain HTTP is accepted only for `localhost`, matching the development secure-context exception used for local WebAuthn testing.

The adapter uses:

```text
userVerification          required
authenticatorAttachment   platform
residentKey               preferred
attestation                none
credential algorithm       ES256 / P-256
```

`attestation=none` is intentional. HAA therefore does not claim remote Apple/platform attestation or device model provenance.

## T04.2 — Authenticator model

The protocol-v1 `AuthenticatorRecord` remains unchanged. WebAuthn-specific metadata is stored in an adapter-owned SQLite table keyed by the generic authenticator ID:

```text
authenticatorId
credentialId
principalId
rpId
origin
signCount
transports[]
AAGUID (observed metadata only)
createdAt
```

The generic HAA authenticator continues to hold only the public P-256 verification key and lifecycle status. This avoids adding WebAuthn-specific fields to protocol v1.

Registration challenge state is adapter-owned and short-lived. Registration IDs are single-use and principal-bound.

## T04.3 — Registration ceremony

Flow:

```text
APPROVER credential
  -> POST /v1/webauthn/registration/options
  -> random registration challenge
  -> navigator.credentials.create()
  -> platform authenticator / UV required
  -> POST /v1/webauthn/registration/verify
  -> verify clientDataJSON origin + challenge
  -> verify rpIdHash + UP + UV + AT flags
  -> require attestation format none
  -> parse ES256 COSE key
  -> atomically register generic authenticator + WebAuthn metadata
```

Registration fails closed on replay, expiry, principal mismatch, origin mismatch, RP mismatch, missing UV/UP, unsupported key/attestation format and duplicate credential ID.

## T04.4 — HAA challenge binding

The WebAuthn authentication challenge is derived directly from the exact HAA challenge digest:

```text
HAA challenge payload bytes
  -> SHA-256
  -> "sha256:<base64url digest>"
  -> UTF-8 bytes
  -> WebAuthn challenge
```

Therefore the assertion is bound to the same HAA challenge that already contains:

```text
requestId
actionDigest
intentDigest
nonce
approverPrincipalId
authenticatorId
executorAudience
policySnapshotHash
displayClaims
issuedAt / expiresAt
```

No protocol-v1 schema change is required.

## T04.5 — Assertion verifier

`WebAuthnEvidenceVerifier` checks:

```text
HAA challengeDigest exact match
credential ID exact match
clientDataJSON.type == webauthn.get
clientDataJSON.challenge exact match
origin exact match
crossOrigin != true
rpIdHash exact match
UP flag set
UV flag set
ES256 signature valid over authenticatorData || SHA256(clientDataJSON)
authenticator ACTIVE
principal binding
stored RP/origin policy binding
signature counter monotonicity when authenticator exposes a counter
```

A zero counter is allowed because WebAuthn authenticators are permitted not to implement a monotonic signature counter. If either stored or observed counter is non-zero, progression must be monotonic and is updated atomically.

## T04.6 — Evidence adapter

Protocol v1 remains unchanged. For evidence type `webauthn-v1`, the existing `ApprovalEvidence.signature` string carries a base64url-encoded type-specific proof envelope:

```text
haa.webauthn-proof.v1
  credentialId
  clientDataJSON
  authenticatorData
  assertionSignature
```

The generic HAA application still consumes `ApprovalEvidence`; only the registered evidence verifier interprets the WebAuthn proof. A valid assertion becomes `VerifiedEvidence` with `humanVerificationLevel=user-verified`.

## T04.7 — Browser approval UI

The optional local browser UI is served at:

```text
/webauthn/approve?requestId=<id>
```

It separates the ceremony into three explicit operations:

```text
1. register a platform WebAuthn credential
2. prepare and display exact HAA claims
3. explicitly approve with WebAuthn user verification
```

The page visibly warns that the action rendering is browser-origin protected and not equivalent to the native macOS trusted display. It does not claim device-bound assurance.

The route is disabled unless `HAA_WEBAUTHN_UI=1`. It is no-store, frame-denied and CSP constrained. It is an optional adapter UI, not a general login product.

## T04.8 — Automated negative-path gate

Automated tests cover the full synthetic cryptographic path with a real generated P-256 credential and fail-closed checks for:

```text
wrong origin
wrong WebAuthn challenge
wrong RP ID hash
wrong credential ID
UV=false
registration origin mismatch
registration UV=false
revoked authenticator
assertion replay
counter regression
request lifecycle / HAA challenge consumption
strict WebAuthn HTTP envelopes and bounded credential fields
browser UI no-store / frame-denied policy
```

Existing HAA tests continue to cover:

```text
mutated ActionSpec
stale approval precondition
wrong executor audience
replayed approval evidence
request/challenge expiry
role separation
```

The adapter adds no external npm dependency: CBOR parsing is deliberately bounded to the definite-length structures required by this adapter and only accepts `none` attestation plus P-256/ES256 credentials.

## T04.9 — Physical browser gate

Status: **DONE / PASS**

Physical execution evidence supplied from the real Mac:

```text
HAA SHA: 52d7c8430a0d2508067f44711bc3656ee12e5887
✓ HAA WebAuthn validation server healthy
✓ PENDING request created
✓ Executor blocked before browser ceremony
✓ Browser WebAuthn assertion accepted; request APPROVED
✓ Exact ExecutionGrant issued after WebAuthn approval
✓ Request CONSUMED exactly once
PASS W7-T04.9: browser WebAuthn → Touch ID → user-verified HAA evidence → exact grant
```

The gate proves the real browser/platform WebAuthn path, `UV=required`, exact HAA challenge binding, grant issuance and one-shot consumption on a physical macOS host. The literal PASS label names the intended operator path; the cryptographic evidence itself proves `user-verified`, not which local biometric/PIN modality satisfied UV. No stronger Touch ID-specific protocol claim is recorded.

## T04.10 — Spike decision

Status: **DONE — KEEP_OPTIONAL**

Decision: keep WebAuthn as a supported optional authenticator adapter, disabled by default. Do not replace the native macOS approver as the preferred high-assurance path.

Rationale:

```text
Dimension                    Native macOS approver              WebAuthn adapter
---------------------------  ---------------------------------  ---------------------------------
Human verification           Touch ID-gated native ceremony     WebAuthn UV=required
Display assurance             native trusted display             authenticated web origin / DOM
Device-bound key claim        supported path                     not claimed
Platform attestation          not claimed                        not claimed
Portability                   Apple/macOS specific               browser/platform portable
Operational prerequisites     local native app/provisioning      RP ID + exact origin + HTTPS
Protocol impact               none                               none
Observed physical path        PASS                               PASS
```

`KEEP_OPTIONAL` is preferred over `ADOPT` because the WebAuthn browser display has a materially larger presentation trust boundary than the native trusted renderer, and the current adapter intentionally uses `attestation=none`. It is still useful where portability, deployment reach or browser-native UX outweigh those assurance differences.

`KEEP_OPTIONAL` is preferred over `REJECT` because the physical gate and automated security matrix demonstrate a working exact-action approval path with strict RP/origin/credential/challenge binding, user verification, revocation/replay controls and unchanged HAA execution semantics.

### Production-use boundary

For high-risk actions where HAA relies on a trusted human-readable presentation boundary, prefer the native macOS approver or a future dedicated trusted-display authenticator. WebAuthn is suitable only when an authenticated web-origin display is an acceptable trust boundary for that action class.

Before promoting WebAuthn from optional adapter to a broadly recommended production authenticator, separately evaluate:

- replacing or independently reviewing the dependency-free bounded CBOR/WebAuthn parser against a mature implementation;
- production RP ID/origin/TLS lifecycle and reverse-proxy policy;
- browser UI integrity/deployment controls;
- whether attestation is required for the intended assurance level.

## Final outcome

```text
W7-T04.1   DONE
W7-T04.2   DONE
W7-T04.3   DONE
W7-T04.4   DONE
W7-T04.5   DONE
W7-T04.6   DONE
W7-T04.7   DONE
W7-T04.8   DONE
W7-T04.9   DONE / physical PASS
W7-T04.10  DONE / KEEP_OPTIONAL
W7-T04      DONE
```

The accepted W7/W8/W9 baselines remain closed; this optional adapter does not reopen protocol v1 or alter native macOS assurance semantics.
