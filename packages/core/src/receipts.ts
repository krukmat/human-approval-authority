import type { ApprovalReceipt, ExecutionGrant, JsonValue, VerifiedEvidence } from '../../protocol/src/index.ts';
import { canonicalize } from './canonical.ts';
import type { Signer } from './signing.ts';

function signObject<T extends { signature: string }>(obj: Omit<T, 'signature'>, signer: Signer): T {
  const signature = signer.sign(Buffer.from(canonicalize(obj as unknown as JsonValue)));
  return { ...obj, signature } as T;
}

export function createReceipt(args: {
  requestId: string;
  actionDigest: string;
  intentDigest: string;
  evidence: VerifiedEvidence;
  expiresAt: string;
  signer: Signer;
  now?: Date;
}): ApprovalReceipt {
  const now = args.now ?? new Date();
  return signObject<ApprovalReceipt>({
    schema: 'haa.receipt.v1',
    requestId: args.requestId,
    actionDigest: args.actionDigest,
    intentDigest: args.intentDigest,
    approverPrincipalId: args.evidence.principalId,
    authenticatorId: args.evidence.authenticatorId,
    humanVerificationLevel: args.evidence.humanVerificationLevel,
    issuedAt: now.toISOString(),
    expiresAt: args.expiresAt,
    authorityKeyId: args.signer.keyId,
    signatureAlgorithm: args.signer.algorithm,
  }, args.signer);
}

export function createExecutionGrant(args: {
  requestId: string;
  executionId: string;
  actionDigest: string;
  executorAudience: string;
  signer: Signer;
  now?: Date;
  ttlMs?: number;
}): ExecutionGrant {
  const now = args.now ?? new Date();
  const ttlMs = args.ttlMs ?? 30_000;
  return signObject<ExecutionGrant>({
    schema: 'haa.execution-grant.v1',
    requestId: args.requestId,
    executionId: args.executionId,
    actionDigest: args.actionDigest,
    executorAudience: args.executorAudience,
    issuedAt: now.toISOString(),
    expiresAt: new Date(now.getTime() + ttlMs).toISOString(),
    authorityKeyId: args.signer.keyId,
    signatureAlgorithm: args.signer.algorithm,
  }, args.signer);
}
