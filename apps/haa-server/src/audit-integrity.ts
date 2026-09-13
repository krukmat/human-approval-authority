import type { JsonValue } from '../../../packages/protocol/src/index.ts';
import {
  canonicalize,
  verifySignature,
  type SignatureAlgorithm,
  type Signer,
} from '../../../packages/core/src/index.ts';
import {
  SqliteStore,
  type AuditIntegrityHead,
  type StoredAuditCheckpoint,
} from '../../../packages/persistence-sqlite/src/index.ts';

export interface AuditAuthorityKey {
  algorithm: SignatureAlgorithm;
  publicKeyPem: string;
}

function unsignedCheckpoint(checkpoint: Omit<StoredAuditCheckpoint, 'signature'>): Record<string, JsonValue> {
  return {
    schema: checkpoint.schema,
    sequence: checkpoint.sequence,
    headDigest: checkpoint.headDigest,
    createdAt: checkpoint.createdAt,
    authorityKeyId: checkpoint.authorityKeyId,
    signatureAlgorithm: checkpoint.signatureAlgorithm,
  };
}

export function createAuditCheckpoint(
  store: SqliteStore,
  signer: Signer,
  now = new Date(),
): StoredAuditCheckpoint {
  const head = store.verifyAuditChain();
  if (!head) throw new Error('AUDIT_EMPTY');
  const unsigned: Omit<StoredAuditCheckpoint, 'signature'> = {
    schema: 'haa.audit-checkpoint.v1',
    sequence: head.sequence,
    headDigest: head.digest,
    createdAt: now.toISOString(),
    authorityKeyId: signer.keyId,
    signatureAlgorithm: signer.algorithm,
  };
  const signature = signer.sign(Buffer.from(canonicalize(unsignedCheckpoint(unsigned)), 'utf8'));
  const checkpoint: StoredAuditCheckpoint = { ...unsigned, signature };
  store.saveAuditCheckpoint(checkpoint);
  return checkpoint;
}

export function verifyAuditIntegrity(
  store: SqliteStore,
  authorityKeyResolver: (keyId: string) => AuditAuthorityKey | null,
  options: { requireCheckpoint?: boolean } = {},
): { head: AuditIntegrityHead | null; checkpointsVerified: number } {
  const head = store.verifyAuditChain();
  const checkpoints = store.listAuditCheckpoints();
  if ((options.requireCheckpoint ?? true) && checkpoints.length === 0) throw new Error('AUDIT_CHECKPOINT_MISSING');

  for (const checkpoint of checkpoints) {
    if (checkpoint.schema !== 'haa.audit-checkpoint.v1') throw new Error('UNSUPPORTED_AUDIT_CHECKPOINT');
    const digestAtSequence = store.getAuditDigestAtSequence(checkpoint.sequence);
    if (!digestAtSequence || digestAtSequence !== checkpoint.headDigest) throw new Error('AUDIT_CHECKPOINT_HEAD_MISMATCH');
    const key = authorityKeyResolver(checkpoint.authorityKeyId);
    if (!key) throw new Error('AUDIT_CHECKPOINT_UNKNOWN_KEY');
    if (key.algorithm !== checkpoint.signatureAlgorithm) throw new Error('AUDIT_CHECKPOINT_ALGORITHM_MISMATCH');
    const { signature, ...unsigned } = checkpoint;
    const valid = verifySignature(
      checkpoint.signatureAlgorithm,
      key.publicKeyPem,
      Buffer.from(canonicalize(unsignedCheckpoint(unsigned)), 'utf8'),
      signature,
    );
    if (!valid) throw new Error('AUDIT_CHECKPOINT_INVALID_SIGNATURE');
  }

  return { head, checkpointsVerified: checkpoints.length };
}
