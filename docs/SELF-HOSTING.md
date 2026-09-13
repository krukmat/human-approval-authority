# Self-hosting HAA

Status: W7 software hardening.

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
- `haa-keys` → HAA authority private key plus authority-key-ring metadata.

Losing `haa-data` loses request/audit/client state. Losing `haa-keys` changes the authority identity and invalidates trust in previously signed HAA artifacts for participants that pinned the prior authority key. Back the database and authority-key volume up as a coordinated recovery set.

## Client roles and provisioning

HAA API clients are provisioned directly into the persistent SQLite store using a high-entropy API key. The provisioning command hashes the secret before storing it and never prints the key.

Each client is assigned an explicit subset of these roles:

- `REQUESTER` — may create approval requests;
- `APPROVER` — may register/revoke its authenticator, obtain challenges and submit approval evidence;
- `EXECUTOR` — may call `authorizeAndConsume` when it is the bound executor audience.

Generate a key outside HAA, for example:

```bash
CLIENT_KEY="$(openssl rand -hex 32)"
```

With Docker Compose, pipe the secret on stdin so it is not placed directly in the command arguments:

```bash
printf '%s' "$CLIENT_KEY" | docker compose run --rm -T haa \
  npm run provision:client -- agent-prod REQUESTER
```

Provision separate identities and roles for the requester, approver principal and bounded executor:

```bash
# REQUESTER
printf '%s' "$AGENT_KEY" | docker compose run --rm -T haa \
  npm run provision:client -- agent-prod REQUESTER

# APPROVER
printf '%s' "$HUMAN_KEY" | docker compose run --rm -T haa \
  npm run provision:client -- human-prod APPROVER

# EXECUTOR
printf '%s' "$EXECUTOR_KEY" | docker compose run --rm -T haa \
  npm run provision:client -- executor-prod EXECUTOR
```

Multiple roles may be provided as a comma-separated list only when that combination is deliberately required. Do not give an agent an `APPROVER` role merely for convenience.

Set `HAA_CLIENT_EXPIRES_AT` during provisioning or rotation to apply credential expiry. The timestamp must be parseable as an absolute date/time.

Treat client keys as credentials. Provisioning and rotation helpers reject secrets shorter than 32 characters.

## Client credential rotation and disable

Rotation preserves the client identity while invalidating the prior credential and incrementing the credential version. The old credential is retained only as hashed lifecycle history and is not accepted for authentication.

```bash
NEW_KEY="$(openssl rand -hex 32)"
printf '%s' "$NEW_KEY" | docker compose run --rm -T haa \
  npm run rotate:client -- agent-prod
```

Disable a client identity without deleting its history:

```bash
docker compose run --rm haa npm run disable:client -- agent-prod
```

Client provisioning, rotation and disable events are recorded in the administrative audit store. API keys are never stored in plaintext.

## Authority key ring

The container defaults to:

```text
HAA_AUTHORITY_KEY_FILE=/keys/authority-key.pem
HAA_AUTHORITY_KEYRING_FILE=/keys/authority-keyring.json
HAA_AUTHORITY_KEY_ID=self-host-authority-v1
```

On first start HAA creates a P-256 authority key if none exists and creates key-ring metadata containing that key as `ACTIVE`. The private key and key-ring metadata are stored in the persistent `haa-keys` volume. Do not mount that volume writable into unrelated workloads.

The active authority key signs all newly issued challenges, receipts and execution grants. Retired entries retain only the public verification material required to validate already-issued artifacts and challenges.

The public endpoints are:

```text
GET /v1/authority-key   -> current ACTIVE key (backward compatible)
GET /v1/authority-keys  -> ACTIVE + RETIRED public key metadata
```

### Rotate the authority key

Choose a new stable key ID and run the rotation against the same persistent key volume:

```bash
docker compose run --rm haa \
  npm run rotate:authority-key -- self-host-authority-v2
```

Rotation:

1. generates a new P-256 private key;
2. marks the previous key `RETIRED` in the key ring;
3. stores the retired public key for historical verification;
4. marks the new key `ACTIVE`;
5. makes the new key the only key used for new signatures.

A key ID may never be reused. HAA fails closed if the active private key does not match the active public key recorded in the key ring.

### Recovery and rollback

Treat `authority-key.pem` and `authority-keyring.json` as one consistency unit. Before rotation, back up the full `haa-keys` volume and the SQLite database.

If rotation is interrupted between file updates, startup intentionally fails with an authority-key-ring mismatch rather than silently downgrading or guessing which key is authoritative. Recover by restoring a known-consistent key-volume snapshot, then restart HAA.

Do not edit `authority-keyring.json` manually to reactivate an old key. A deliberate rollback must restore a coordinated backup containing the intended active private key and matching key-ring metadata. Historical retired public keys should remain available for as long as signed HAA artifacts must remain verifiable.

If `HAA_AUTHORITY_PRIVATE_KEY_PEM` is used instead of the persistent key-file path, the caller owns persistence and coordinated key-ring management; the self-host rotation command is intended for file-backed deployments.

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

`HAA_DEV_BOOTSTRAP=1` exists only for tests/local demos. It installs predictable development identities with separated roles (`REQUESTER`, `APPROVER`, `EXECUTOR`) and must not be enabled in a real self-hosted deployment.

## Upgrade rule

Before upgrading across a release that changes protocol support, read `docs/PROTOCOL-V1.md`. HAA must never silently reinterpret an already-approved v1 action under new semantics.
