# HAA network edge contract

Status: W7-T10 production network profile.

HAA has two supported network profiles. The profile is an operational trust-boundary declaration; it does not change protocol semantics.

## `local`

`HAA_NETWORK_PROFILE=local` is the default.

Rules:

- HAA may bind only to `127.0.0.1`, `::1`, or `localhost`;
- a non-loopback `HOST` fails startup;
- this is the recommended direct-development and single-host mode;
- no external reverse-proxy assumptions are required.

## `edge`

`HAA_NETWORK_PROFILE=edge` explicitly permits a non-loopback bind. It is intended only when HAA sits behind a trusted reverse proxy, ingress or service mesh.

The edge boundary MUST provide:

1. TLS termination using an operator-approved certificate and protocol policy;
2. request-rate / connection-rate abuse controls;
3. upstream request-size limits no larger than HAA's own HTTP body limit;
4. network ACLs / service identity rules appropriate to the deployment;
5. secrets isolation so HAA API keys and authority private-key storage are not exposed to unrelated workloads;
6. logging that does not record API-key header values or private key material.

HAA's Fastify listener intentionally does **not** enable `trustProxy`. `X-Forwarded-For`, `Forwarded` and similar headers therefore do not become security identity inputs. Client authorization remains API-key / role based and must not depend on spoofable forwarding headers.

Rate limiting is currently an edge responsibility rather than an in-process HAA policy. This keeps the application deployment-neutral and allows the operator to apply controls consistently at the actual ingress boundary. Exposing the plain HAA listener directly to an untrusted network is unsupported.

## Development bootstrap guard

`HAA_DEV_BOOTSTRAP=1` provisions predictable development identities/credentials and is therefore a development-only mechanism.

HAA refuses startup when both are true:

```text
HAA_NETWORK_PROFILE=edge
HAA_DEV_BOOTSTRAP=1
```

unless the operator also supplies the deliberately unsafe override:

```text
HAA_ALLOW_UNSAFE_DEV_BOOTSTRAP_EDGE=1
```

That override exists only for controlled test environments. It must not be used as a production deployment pattern.

The safe invariant is:

```text
edge + dev bootstrap + no unsafe override -> FAIL STARTUP
```

## Body and input limits

HAA enforces its own application limits even behind an edge:

- Fastify body limit: 64 KiB;
- strict request schemas;
- bounded identifiers and strings;
- bounded JSON depth, key count and array length;
- unsupported or oversized input fails before domain execution.

The upstream edge should use an equal or stricter request-body limit so abusive payloads are rejected before consuming application resources.

## Container profile

The image binds `0.0.0.0` internally and therefore declares:

```text
HAA_NETWORK_PROFILE=edge
```

The provided Compose file still publishes the service only on host loopback:

```text
127.0.0.1:${HAA_PORT:-8787}:8787
```

Changing that publication to a public or LAN interface is an operator decision and requires the edge controls above.

## Security invariant

```text
local profile + non-loopback bind -> FAIL
edge profile + non-loopback bind  -> permitted, edge controls required
edge profile + dev bootstrap      -> FAIL unless explicit unsafe override
unknown profile                   -> FAIL
```

No network profile weakens requester, approver, executor, exact-action, replay or `ExecutionGrant` validation.
