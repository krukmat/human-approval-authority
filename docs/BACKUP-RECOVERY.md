# HAA backup and recovery contract

Status: W7-T14 persistence, backup and recovery hardening.

HAA currently supports a **single-node SQLite deployment**. High availability, shared-database multi-writer operation and active/active failover are outside the current product contract.

## Recovery unit

A valid backup is a coordinated bundle containing:

```text
haa.db
  +
authority-key.pem
  +
authority-keyring.json
  +
manifest.json
```

The database and authority-key files must be treated as one recovery unit. Restoring only the database or only authority material can break historical verification and is unsupported.

The manifest records:

- bundle schema/version;
- creation timestamp;
- active authority key ID;
- audit-chain head;
- SHA-256 checksum for each bundled file.

## Create a backup

For the current SQLite single-node model, HAA creates a transactional SQLite snapshot using `VACUUM INTO` and then binds it to the current authority material in the bundle manifest.

```bash
npm run backup:instance -- ./backups/haa-2026-09-13
```

Container example:

```bash
docker compose run --rm haa \
  npm run backup:instance -- /data/backup-2026-09-13
```

The destination directory must not already exist. Store copies outside the live HAA data/key volumes according to the operator's retention policy.

For the cleanest operational boundary, schedule backups during a low-traffic window. SQLite provides the database snapshot consistency; the authority key and key-ring metadata should not be rotated concurrently with backup creation.

## Verify a backup

Always verify a bundle before relying on it:

```bash
npm run verify:backup -- ./backups/haa-2026-09-13
```

Verification checks:

1. bundle schema;
2. file presence;
3. checksums for the database, active private key and key ring;
4. active private key vs key-ring consistency;
5. audit hash-chain integrity;
6. signed audit checkpoints when present;
7. audit head vs the head captured in the manifest.

A failed verification means the bundle must not be used for restore.

## Restore

Stop the HAA service before replacing live persistence files. Restore into an empty target whenever possible:

```bash
npm run restore:instance -- ./backups/haa-2026-09-13
```

The restore path verifies the bundle **before** copying it and re-verifies authority-key and audit consistency **after** installation.

Existing target files are not overwritten by default. Deliberate overwrite requires:

```bash
HAA_RESTORE_CONFIRM=YES npm run restore:instance -- ./backups/haa-2026-09-13
```

After restore, start HAA and run the normal health/service smoke checks before accepting new approval traffic.

## Corruption and failure policy

HAA fails closed on:

- checksum mismatch;
- authority private key / active key-ring mismatch;
- audit-chain corruption;
- audit checkpoint mismatch;
- restored audit head differing from the backup manifest;
- missing required recovery files.

Do not attempt to "repair" cryptographic metadata by editing the key ring, audit chain or manifest manually. Restore a previously verified coordinated backup instead.

## Authority rotation interaction

Create a verified backup before planned authority-key rotation. A post-rotation backup should contain:

- the new ACTIVE private key;
- ACTIVE + RETIRED public key metadata;
- the database state that references signed objects from both generations.

Historical private keys are not required for ordinary verification after rotation; retained public keys in the key ring are. A rollback of the ACTIVE authority identity is not an ordinary restore operation and must use a coordinated snapshot intentionally selected for that purpose.

## Audit checkpoints

A backup preserves `audit_checkpoints` in SQLite. The bundle verifier validates any checkpoint against ACTIVE or RETIRED authority public keys in the bundled key ring. Periodically export or retain checkpoint evidence outside the database when stronger DBA-tamper resistance is required.

## Explicit limitations

The current contract is:

```text
single HAA process / single SQLite writer
             │
             ├─ transactional DB snapshot
             ├─ coordinated authority-key bundle
             └─ verified restore
```

It is **not** a distributed HA/DR design. Replication, multi-region recovery, automatic failover and concurrent multi-writer SQLite are intentionally outside W7-T14.
