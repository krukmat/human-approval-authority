import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash, randomUUID } from 'node:crypto';
import { createEphemeralP256Signer } from '../packages/core/src/index.ts';
import { SqliteStore } from '../packages/persistence-sqlite/src/index.ts';
import { createAuditCheckpoint, verifyAuditIntegrity } from '../apps/haa-server/src/audit-integrity.ts';
import type { AuditEvent } from '../packages/protocol/src/index.ts';

function event(requestId: string, eventType: AuditEvent['eventType'], at: string): AuditEvent {
  return {
    schema: 'haa.audit.v1',
    id: randomUUID(),
    requestId,
    eventType,
    actorId: 'actor-a',
    at,
  };
}

function chainDigest(sequence: number, eventId: string, eventJson: string, previousDigest: string | null): string {
  const envelope = JSON.stringify({
    schema: 'haa.audit-chain.v1',
    sequence,
    eventId,
    previousDigest,
    eventJson,
  });
  return `sha256:${createHash('sha256').update(envelope).digest('base64url')}`;
}

test('audit chain detects post-hoc event mutation', () => {
  const store = new SqliteStore(':memory:');
  try {
    store.appendAudit(event('req-1', 'REQUESTED', '2026-09-13T06:00:00.000Z'));
    store.appendAudit(event('req-1', 'APPROVED', '2026-09-13T06:00:01.000Z'));
    assert.equal(store.verifyAuditChain()?.sequence, 2);

    const row = store.db.prepare('SELECT seq,event_json FROM audit_events ORDER BY seq LIMIT 1').get() as { seq: number; event_json: string };
    const mutated = { ...JSON.parse(row.event_json), actorId: 'tampered-actor' };
    store.db.prepare('UPDATE audit_events SET event_json=? WHERE seq=?').run(JSON.stringify(mutated), row.seq);
    assert.throws(() => store.verifyAuditChain(), /AUDIT_CHAIN_DIGEST_MISMATCH/);
  } finally {
    store.close();
  }
});

test('audit chain detects deletion or reordering even when database constraints are bypassed', () => {
  const store = new SqliteStore(':memory:');
  try {
    store.appendAudit(event('req-1', 'REQUESTED', '2026-09-13T06:00:00.000Z'));
    store.appendAudit(event('req-1', 'APPROVED', '2026-09-13T06:00:01.000Z'));
    store.db.exec('PRAGMA foreign_keys = OFF');
    store.db.prepare('DELETE FROM audit_integrity WHERE seq=1').run();
    store.db.prepare('DELETE FROM audit_events WHERE seq=1').run();
    assert.throws(() => store.verifyAuditChain(), /(AUDIT_CHAIN_PREVIOUS_MISMATCH|AUDIT_INTEGRITY_ROW_COUNT_MISMATCH)/);
  } finally {
    store.close();
  }
});

test('signed checkpoint detects a DBA recomputing the hash chain after tampering', () => {
  const store = new SqliteStore(':memory:');
  const signer = createEphemeralP256Signer('audit-authority-k1');
  try {
    store.appendAudit(event('req-1', 'REQUESTED', '2026-09-13T06:00:00.000Z'));
    store.appendAudit(event('req-1', 'APPROVED', '2026-09-13T06:00:01.000Z'));
    const checkpoint = createAuditCheckpoint(store, signer, new Date('2026-09-13T06:00:02.000Z'));
    assert.equal(checkpoint.sequence, 2);

    const first = store.db.prepare('SELECT event_digest FROM audit_integrity WHERE seq=1').get() as { event_digest: string };
    const second = store.db.prepare('SELECT id,event_json FROM audit_events WHERE seq=2').get() as { id: string; event_json: string };
    const mutatedJson = JSON.stringify({ ...JSON.parse(second.event_json), actorId: 'tampered-actor' });
    const forgedDigest = chainDigest(2, second.id, mutatedJson, first.event_digest);
    store.db.prepare('UPDATE audit_events SET event_json=? WHERE seq=2').run(mutatedJson);
    store.db.prepare('UPDATE audit_integrity SET prev_digest=?,event_digest=? WHERE seq=2').run(first.event_digest, forgedDigest);

    assert.equal(store.verifyAuditChain()?.digest, forgedDigest);
    assert.throws(() => verifyAuditIntegrity(store, (keyId) => keyId === signer.keyId
      ? { algorithm: signer.algorithm, publicKeyPem: signer.publicKeyPem }
      : null), /AUDIT_CHECKPOINT_HEAD_MISMATCH/);
  } finally {
    store.close();
  }
});
