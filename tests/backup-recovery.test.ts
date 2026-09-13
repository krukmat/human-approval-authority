import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { SqliteStore } from '../packages/persistence-sqlite/src/index.ts';
import { loadOrCreateAuthorityKeyRing } from '../apps/haa-server/src/authority.ts';
import { createAuditCheckpoint } from '../apps/haa-server/src/audit-integrity.ts';
import {
  createBackupBundle,
  restoreBackupBundle,
  verifyBackupBundle,
} from '../apps/haa-server/src/backup.ts';
import type { AuditEvent } from '../packages/protocol/src/index.ts';

function auditEvent(requestId: string, eventType: AuditEvent['eventType'], at: string): AuditEvent {
  return {
    schema: 'haa.audit.v1',
    id: randomUUID(),
    requestId,
    eventType,
    actorId: 'actor-a',
    at,
  };
}

test('backup bundle verifies and restores database plus matching authority key ring', () => {
  const root = mkdtempSync(join(tmpdir(), 'haa-backup-'));
  const sourceDb = join(root, 'source.db');
  const sourceKey = join(root, 'source-key.pem');
  const sourceRing = join(root, 'source-keyring.json');
  const bundle = join(root, 'bundle');
  const restoredDb = join(root, 'restored', 'haa.db');
  const restoredKey = join(root, 'restored', 'authority-key.pem');
  const restoredRing = join(root, 'restored', 'authority-keyring.json');

  try {
    const ring = loadOrCreateAuthorityKeyRing({
      keyId: 'backup-authority-k1',
      keyFile: sourceKey,
      keyRingFile: sourceRing,
      now: new Date('2026-09-13T06:00:00.000Z'),
    });
    const sourceStore = new SqliteStore(sourceDb);
    sourceStore.appendAudit(auditEvent('req-backup', 'REQUESTED', '2026-09-13T06:00:01.000Z'));
    sourceStore.appendAudit(auditEvent('req-backup', 'APPROVED', '2026-09-13T06:00:02.000Z'));
    const expectedHead = sourceStore.verifyAuditChain();
    createAuditCheckpoint(sourceStore, ring.signer, new Date('2026-09-13T06:00:03.000Z'));
    sourceStore.close();

    const manifest = createBackupBundle({
      dbPath: sourceDb,
      keyFile: sourceKey,
      keyRingFile: sourceRing,
      destinationDir: bundle,
      now: new Date('2026-09-13T06:00:04.000Z'),
    });
    assert.equal(manifest.activeAuthorityKeyId, 'backup-authority-k1');
    assert.deepEqual(manifest.auditHead, expectedHead);
    assert.equal(verifyBackupBundle(bundle).activeAuthorityKeyId, 'backup-authority-k1');

    restoreBackupBundle({
      bundleDir: bundle,
      dbPath: restoredDb,
      keyFile: restoredKey,
      keyRingFile: restoredRing,
    });

    const reloadedRing = loadOrCreateAuthorityKeyRing({ keyFile: restoredKey, keyRingFile: restoredRing });
    assert.equal(reloadedRing.signer.keyId, 'backup-authority-k1');
    const restoredStore = new SqliteStore(restoredDb);
    assert.deepEqual(restoredStore.verifyAuditChain(), expectedHead);
    assert.equal(restoredStore.listAuditCheckpoints().length, 1);
    restoredStore.close();
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test('backup verification rejects tampered bundle content', () => {
  const root = mkdtempSync(join(tmpdir(), 'haa-backup-tamper-'));
  const sourceDb = join(root, 'source.db');
  const sourceKey = join(root, 'source-key.pem');
  const sourceRing = join(root, 'source-keyring.json');
  const bundle = join(root, 'bundle');

  try {
    loadOrCreateAuthorityKeyRing({ keyId: 'backup-authority-k1', keyFile: sourceKey, keyRingFile: sourceRing });
    const sourceStore = new SqliteStore(sourceDb);
    sourceStore.appendAudit(auditEvent('req-backup', 'REQUESTED', '2026-09-13T06:00:01.000Z'));
    sourceStore.close();
    createBackupBundle({ dbPath: sourceDb, keyFile: sourceKey, keyRingFile: sourceRing, destinationDir: bundle });

    const keyPath = join(bundle, 'authority-key.pem');
    writeFileSync(keyPath, `${readFileSync(keyPath, 'utf8')}\n# tampered\n`, 'utf8');
    assert.throws(() => verifyBackupBundle(bundle), /BACKUP_AUTHORITY_KEY_CHECKSUM_MISMATCH/);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test('restore refuses to overwrite an existing target without explicit confirmation', () => {
  const root = mkdtempSync(join(tmpdir(), 'haa-restore-guard-'));
  const sourceDb = join(root, 'source.db');
  const sourceKey = join(root, 'source-key.pem');
  const sourceRing = join(root, 'source-keyring.json');
  const bundle = join(root, 'bundle');
  const restoredDb = join(root, 'restored.db');
  const restoredKey = join(root, 'restored-key.pem');
  const restoredRing = join(root, 'restored-ring.json');

  try {
    loadOrCreateAuthorityKeyRing({ keyId: 'backup-authority-k1', keyFile: sourceKey, keyRingFile: sourceRing });
    const sourceStore = new SqliteStore(sourceDb);
    sourceStore.appendAudit(auditEvent('req-backup', 'REQUESTED', '2026-09-13T06:00:01.000Z'));
    sourceStore.close();
    createBackupBundle({ dbPath: sourceDb, keyFile: sourceKey, keyRingFile: sourceRing, destinationDir: bundle });
    writeFileSync(restoredDb, 'existing');

    assert.throws(() => restoreBackupBundle({
      bundleDir: bundle,
      dbPath: restoredDb,
      keyFile: restoredKey,
      keyRingFile: restoredRing,
    }), /RESTORE_TARGET_EXISTS:restored.db/);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
