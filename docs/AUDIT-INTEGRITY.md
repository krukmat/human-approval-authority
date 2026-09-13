# Audit integrity

Status: W7-T11 tamper-evident audit hardening.

HAA keeps `haa.audit.v1` unchanged. Tamper evidence is implemented as an internal persistence layer so the frozen protocol is not modified.

## Hash chain

Every request audit event is stored with an integrity record containing:

- SQLite sequence number;
- event ID;
- previous event digest;
- current event digest.

The digest binds:

```text
schema = haa.audit-chain.v1
sequence
eventId
previousDigest
exact event_json bytes
```

Event insertion and integrity insertion occur in the same SQLite transaction. `CONSUMED` audit insertion remains inside the same transaction as request consumption and grant persistence.

Existing databases are migrated once: if audit events exist and no integrity rows exist yet, HAA builds the initial chain from the existing stored history. After that migration boundary, row-count mismatch or chain mismatch fails closed.

## Signed checkpoints

A database administrator can modify SQLite directly and could recompute an unsigned hash chain. To make that detectable, HAA supports signed checkpoints:

```text
haa.audit-checkpoint.v1
sequence
headDigest
createdAt
authorityKeyId
signatureAlgorithm
signature
```

The checkpoint is domain-separated from approval receipts and execution grants. It is not execution authority and cannot be used as an approval capability.

Create a checkpoint:

```bash
npm run checkpoint:audit
```

In a container:

```bash
docker compose run --rm haa npm run checkpoint:audit
```

For production, run checkpoint creation periodically using the operator's scheduler (for example cron, systemd timer, Kubernetes CronJob, or an equivalent platform scheduler). The cadence determines the maximum tail of audit history that is not anchored by a signed checkpoint.

## Offline verification

Run:

```bash
npm run verify:audit
```

The verifier checks:

1. the complete hash chain;
2. event ordering and predecessor linkage;
3. checkpoint sequence/head binding;
4. checkpoint authority key lookup through the ACTIVE/RETIRED key ring;
5. checkpoint signature validity.

A successful result reports the current chain head and number of verified checkpoints.

## Threat boundary

This detects post-hoc modification, deletion or reordering of protected request audit history. A DBA who rewrites both audit rows and hash-chain rows still cannot make an already-signed checkpoint validate without an authority signing key.

The protection does **not** survive compromise of both SQLite and the active/retained authority signing material. Protect the authority-key volume separately and export/retain checkpoint evidence according to operational policy.

`admin_audit_events` for credential administration remain a separate operational audit stream in this increment; T11's cryptographic chain protects the protocol request audit (`audit_events`). If the deployment requires cryptographic anchoring of administrative lifecycle events as well, extend the same mechanism rather than treating request checkpoints as proof of admin-audit integrity.
