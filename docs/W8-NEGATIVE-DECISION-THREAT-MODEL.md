# W8 negative-decision provenance threat model

Status: FROZEN FOR INITIAL IMPLEMENTATION

## Security question

How can HAA record an explicit human rejection without requiring Touch ID while preventing an ordinary requester/agent from fabricating the claim that the human rejected an action?

## Assurance boundary

Positive approval and explicit rejection deliberately have different assurance levels.

### Positive approval

Positive approval is authority-granting and therefore requires strong authenticator evidence. On macOS the existing path uses a Secure Enclave key released after Touch ID user verification.

### Explicit rejection

Explicit rejection grants no capability and is fail-closed. Initial HAA v1+W8 therefore does **not** require biometric proof for a rejection.

The provenance claim is limited to:

> An authenticated APPROVER client, representing the request's configured approver principal, explicitly rejected this exact active challenge through the trusted approver channel.

It must **not** be upgraded to claims such as:

- biometric rejection;
- Touch ID verified rejection;
- Secure Enclave-signed rejection;
- hardware-attested human rejection.

## Initial provenance mechanism

A server-side reject request MUST contain:

- request ID from the route;
- exact `challengeDigest`;
- typed reason `USER_ESCAPE` for the initial macOS ceremony.

The server MUST verify:

1. the API credential authenticates as a client with `APPROVER` role;
2. authenticated actor equals `request.intent.approverPrincipalId`;
3. request state is exactly `PENDING`;
4. challenge exists and is not consumed;
5. challenge belongs to the same request;
6. challenge authenticator belongs to the same approver principal and is ACTIVE;
7. challenge's signed payload binds the same request ID, intent digest and action digest;
8. challenge authority signature verifies through the authority key ring;
9. rejection reason is in the supported allow-list;
10. challenge consumption and `PENDING -> REJECTED` transition are atomic from the caller's perspective and cannot create execution authority.

The resulting request audit event records at minimum:

```json
{
  "eventType": "REJECTED",
  "actorId": "<approver principal>",
  "details": {
    "challengeDigest": "sha256:...",
    "authenticatorId": "...",
    "reason": "USER_ESCAPE",
    "provenance": "authenticated-approver-channel"
  }
}
```

The event participates in W7 audit tamper-evidence.

## Threats and controls

### Requester fabricates rejection

Threat: an agent attempts to call the reject endpoint.

Control: requester-only credential lacks `APPROVER`; even a mixed-role credential must authenticate as the exact configured approver principal.

Residual operational rule: provisioning must not give an agent the human approver credential.

### Approver rejects a different request/challenge

Threat: replaying a legitimate approver request against another approval.

Control: exact request ID + challenge digest + signed payload binding are checked before transition.

### Replaying the same reject

Threat: duplicate delivery or malicious replay.

Control: the active challenge is consumed and the request becomes terminal `REJECTED`. A replay cannot create a second authority-bearing object and must fail closed/idempotently at the service boundary.

### Forged browser/window-close rejection

Threat: absence of interaction is represented as a human refusal.

Control: only the explicit Esc path sends a reject request. Window close, local timeout, crash, network failure, or lost response produce `UNKNOWN` locally and do not transition the server to `REJECTED`.

### Network attacker fabricates rejection

Threat: attacker sends an APPROVER request.

Control: authenticated API channel plus production network-edge TLS requirements. No rejection is accepted solely because a request originated from localhost or carried forwarded headers.

### Compromised approver credential

Threat: theft of the approver API credential can produce explicit rejections.

Control: credential expiry/rotation/disable from W7-T08; this is an accepted weaker assurance boundary than APPROVE. Rejection still cannot grant execution authority.

### Compromised local process injects Esc

Threat: malware or accessibility automation triggers Escape in the trusted approver app.

Control: outside the initial threat model for negative decisions. The result remains fail-closed. If stronger non-repudiation of rejection becomes a requirement, introduce a separately versioned signed negative-decision mechanism rather than relabeling this one.

## Why not sign REJECT with the approval Secure Enclave key?

Doing so would make rejection UX equivalent in cost to approval, undermine the explicit Esc requirement, and create misleading equivalence between capability-granting approval and capability-denying refusal.

The initial product chooses asymmetric assurance intentionally:

```text
APPROVE -> strong user verification -> may grant authority
REJECT  -> authenticated explicit refusal -> grants no authority
UNKNOWN -> no attributable decision -> grants no authority
```

## Acceptance invariants

- requester credential alone cannot reject;
- wrong approver cannot reject;
- stale/wrong/consumed challenge cannot reject;
- reject cannot create receipt or grant;
- explicit Esc is distinguishable from close/timeout/failure;
- audit describes the assurance truthfully;
- no protocol-v1 signed schema is modified.
