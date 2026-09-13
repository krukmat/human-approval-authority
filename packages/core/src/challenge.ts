import { randomBytes } from 'node:crypto';
import type {
  ApprovalChallengePackage,
  ApprovalChallengePayload,
  ApprovalIntent,
  ApprovalRequest,
  JsonValue,
} from '../../protocol/src/index.ts';
import type { ActionProfileRegistry } from './actions.ts';
import { canonicalize, digestJson, sha256 } from './canonical.ts';
import type { Signer } from './signing.ts';
import { verifySignature } from './signing.ts';

export function intentDigest(intent: ApprovalIntent): string {
  return digestJson(intent as unknown as JsonValue);
}

export function challengePayloadBytes(challenge: ApprovalChallengePackage): Uint8Array {
  return Buffer.from(challenge.payload, 'base64url');
}

export function decodeChallengePayload(challenge: ApprovalChallengePackage): ApprovalChallengePayload {
  const parsed = JSON.parse(Buffer.from(challenge.payload, 'base64url').toString('utf8')) as ApprovalChallengePayload;
  if (parsed.schema !== 'haa.challenge-payload.v1' || parsed.protocolVersion !== 1) throw new Error('UNSUPPORTED_CHALLENGE_PAYLOAD');
  return parsed;
}

export function verifyChallengeAuthority(challenge: ApprovalChallengePackage, authorityPublicKeyPem: string): boolean {
  return verifySignature(challenge.signatureAlgorithm, authorityPublicKeyPem, challengePayloadBytes(challenge), challenge.signature);
}

export function challengeDigest(challenge: ApprovalChallengePackage): string {
  return `sha256:${sha256(challengePayloadBytes(challenge))}`;
}

export function issueChallenge(
  request: ApprovalRequest,
  authenticatorId: string,
  profiles: ActionProfileRegistry,
  signer: Signer,
  now = new Date(),
  ttlMs = 2 * 60_000,
): ApprovalChallengePackage {
  if (request.state !== 'PENDING') throw new Error('REQUEST_NOT_PENDING');
  if (new Date(request.intent.expiresAt).getTime() <= now.getTime()) throw new Error('REQUEST_EXPIRED');
  const expiresAt = new Date(Math.min(now.getTime() + ttlMs, new Date(request.intent.expiresAt).getTime())).toISOString();
  const payload: ApprovalChallengePayload = {
    schema: 'haa.challenge-payload.v1',
    protocolVersion: 1,
    requestId: request.id,
    actionType: request.intent.action.type,
    actionDigest: request.actionDigest,
    intentDigest: request.intentDigest,
    nonce: randomBytes(32).toString('base64url'),
    approverPrincipalId: request.intent.approverPrincipalId,
    authenticatorId,
    executorAudience: request.intent.executorAudience,
    policySnapshotHash: request.intent.policySnapshotHash,
    displayClaims: profiles.displayClaims(request.intent.action),
    issuedAt: now.toISOString(),
    expiresAt,
  };
  const bytes = Buffer.from(canonicalize(payload as unknown as JsonValue), 'utf8');
  return {
    schema: 'haa.challenge.v1',
    payload: Buffer.from(bytes).toString('base64url'),
    authorityKeyId: signer.keyId,
    signatureAlgorithm: signer.algorithm,
    signature: signer.sign(bytes),
  };
}
