# Self-hosting HAA

Status: W7-T02 software packaging.

This path is intended for internal/self-hosted deployments. It does **not** enable `HAA_DEV_BOOTSTRAP` and does not ship default API keys.

## Build and start

```bash
docker compose build
docker compose up -d
```

By default the service binds only to loopback:

```text
127.0.0.1:8787
```

Override the host-side port with `HAA_PORT`, for example:

```bash
HAA_PORT=8877 docker compose up -d
```

Persistent state is split into two named volumes:

- `haa-data` → SQLite database;
- `haa-keys` → HAA authority private key.

Losing `haa-data` loses request/audit/client state. Losing `haa-keys` changes the authority identity and invalidates trust in previously signed HAA artifacts for participants that pinned the prior authority key. Back them up according to the deployment's recovery requirements.

## Provision clients without dev bootstrap

HAA API clients are provisioned directly into the persistent SQLite store using a high-entropy API key. The provisioning command hashes the secret before storing it and never prints the key.

Generate a key outside HAA, for example:

```bash
CLIENT_KEY="$(openssl rand -hex 32)"
```

With Docker Compose, pipe the secret on stdin so it is not placed directly in the command arguments:

```bash
printf '%s' "$CLIENT_KEY" | docker compose run --rm -T haa \
  npm run provision:client -- agent-prod
```

Provision separate identities for the requester, approver principal and bounded executor when the workflow requires them:

```text
agent-prod
human-prod
executor-prod
```

The current v1 authorization model binds sensitive operations to identity through the approval intent (`requesterId`, `approverPrincipalId`, `executorAudience`) rather than a generic RBAC role field. Authenticator registration/evidence additionally requires the authenticated actor to equal the approver principal, while `authorizeAndConsume` requires the authenticated executor to equal `executorAudience`.

Treat client keys as credentials. The provisioning helper rejects secrets shorter than 32 characters.

## Authority key

The container defaults to:

```text
HAA_AUTHORITY_KEY_FILE=/keys/authority-key.pem
HAA_AUTHORITY_KEY_ID=self-host-authority-v1
```

On first start HAA creates a P-256 authority key if none exists. The key is stored in the persistent `haa-keys` volume. Do not mount the same authority-key volume writable into unrelated workloads.

For a controlled deployment, set a stable `HAA_AUTHORITY_KEY_ID` and establish a backup/rotation procedure before production use.

## Health check

```bash
curl -fsS http://127.0.0.1:8787/health
```

Expected:

```json
{"status":"ok"}
```

The Docker image includes the same check as its container healthcheck.

## Exposure and TLS

The compose file intentionally publishes HAA only on `127.0.0.1`. For remote access, place a trusted reverse proxy or service mesh in front of HAA and terminate TLS there. Do not expose the plain HTTP listener directly to an untrusted network.

## Development bootstrap

`HAA_DEV_BOOTSTRAP=1` exists only for tests/local demos. It installs predictable development identities and must not be enabled in a real self-hosted deployment.

## Upgrade rule

Before upgrading across a release that changes protocol support, read `docs/PROTOCOL-V1.md`. HAA must never silently reinterpret an already-approved v1 action under new semantics.
