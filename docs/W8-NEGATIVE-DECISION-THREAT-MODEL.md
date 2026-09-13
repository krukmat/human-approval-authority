# W8 negative-decision provenance threat model

Status: FROZEN FOR INITIAL IMPLEMENTATION

## Security question

How can HAA terminate every non-approved ceremony as REJECT without requiring Touch ID for the negative path, while preventing a requester/agent from fabricating a trusted rejection claim?

## Assurance boundary

Positive approval and negative terminal outcomes deliberately have different assurance levels.

### Positive approval

Positive approval is authority-granting and therefore requires strong authenticator evidence. On macOS the existing path uses a Secure Enclave key released after Touch ID user verification.

### Negative terminal outcome

REJECT grants no capability and is fail-closed. HAA therefore does **not** require biometric proof for rejection.

The provenance claim is limited to:

> An authenticated APPROVER client, representing the request's configured approver principal, terminated this exact active challenge with the recorded reason.

For `USER_ESCAPE` the additional assurance is:

> The trusted approver UI observed the explicit Escape negative action.

For all other reasons the assurance is only:

> The ceremony ended without a successful positive authorization and therefore failed closed.

It must **not** be upgraded to claims such as biometric rejection, Touch ID verified rejection, Secure Enclave-signed rejection, or hardware-attested human rejection.

## Rejection record

The server-side reject request contains:

- request ID from the route;
- exact `challengeDigest`;
- one typed reason:
  - `USER_ESCAPE`
  - `WINDOW_CLOSED`
  - `TIMEOUT`
  - `CHALLENGE_EXPIRED`
  - `INTERACTION_ERROR`

The server verifies:

1. the API credential authenticates as a client with `APPROVER` role;
2. authenticated actor equals `request.intent.approverPrincipalId`;
3. request state is exactly `PENDING` and request TTL has not elapsed;
4. challenge exists and is not consumed;
5. challenge belongs to the same request;
6. challenge authenticator belongs to the same approver principal and is ACTIVE;
7. signed payload binds the same request ID, intent digest and action digest;
8. challenge authority signature verifies through the authority key ring;
9. rejection reason is in the supported allow-list;
10. `CHALLENGE_EXPIRED` is accepted only if the challenge has actually expired;
11. non-expiry reasons are denied after challenge expiry;
12. challenge consumption and `PENDING -> REJECTED` transition cannot create execution authority.

The resulting audit event records at minimum:

```json
{
  "eventType": "REJECTED",
  "actorId": "<approver principal>",
  "details": {
    "challengeDigest": "sha256:...",
    "authenticatorId": "...",
    "reason": "TIMEOUT",
    "provenance": "authenticated-approver-channel",
    "assurance": "fail-closed-terminal"
  }
}
```

For `USER_ESCAPE`, `assurance` is `explicit-human-negative-action`.

## Threats and controls

### Requester fabricates rejection

Threat: an agent attempts to call the reject endpoint.

Control: requester-only credential lacks `APPROVER`; even a mixed-role credential must authenticate as the exact configured approver principal.

Residual operational rule: provisioning must not give an agent the human approver credential.

### Approver rejects a different request/challenge

Threat: replaying a legitimate approver request against another approval.

Control: exact request ID + challenge digest + signed payload binding are checked before transition.

### Reason forgery

Threat: a caller reports `USER_ESCAPE` after the challenge already expired or reports `CHALLENGE_EXPIRED` before it actually expired.

Control: server validates challenge time against the requested reason. Reason semantics are not accepted solely from caller text.

### Replaying the same reject

Threat: duplicate delivery or malicious replay.

Control: challenge is consumed and request becomes terminal `REJECTED`. Replays cannot create a second authority-bearing object.

### Window close / timeout falsely described as explicit human rejection

Threat: operational fail-closed termination is overstated as proof that the human consciously chose Reject.

Control: both map operationally to REJECT but retain their own reason and `fail-closed-terminal` assurance. Only `USER_ESCAPE` uses `explicit-human-negative-action`.

### Network attacker fabricates rejection

Threat: attacker sends an APPROVER request.

Control: authenticated API channel plus production network-edge TLS requirements. No rejection is accepted solely because traffic originates from localhost or carries forwarded headers.

### Compromised approver credential

Threat: theft of the approver API credential can produce rejections.

Control: credential expiry/rotation/disable from W7-T08. This remains weaker assurance than APPROVE, but a forged negative decision cannot grant execution authority.

### Compromised local process injects Esc or closes the window

Threat: malware/accessibility automation forces a negative terminal result.

Control: this remains fail-closed with respect to execution. If non-repudiable negative intent becomes a requirement, introduce a separately versioned signed negative-decision mechanism rather than relabeling the current assurance.

## Why not sign REJECT with the approval Secure Enclave key?

Doing so would make rejection UX equivalent in cost to approval and create misleading equivalence between capability-granting approval and capability-denying refusal.

The product intentionally chooses asymmetric assurance:

```text
APPROVE                 -> strong user verification -> may grant authority
REJECT / USER_ESCAPE    -> explicit negative UI action -> grants no authority
REJECT / other reason   -> fail-closed terminal outcome -> grants no authority
```

## Acceptance invariants

- requester credential alone cannot reject;
- wrong approver cannot reject;
- wrong/consumed challenge cannot reject;
- challenge-expiry reason must match actual challenge expiry;
- every non-approved terminal ceremony ends REJECTED;
- reject cannot create receipt or grant;
- reason/assurance prevents overstating human intent;
- no protocol-v1 signed schema is modified.
