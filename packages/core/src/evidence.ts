import type { ApprovalChallengePackage, ApprovalEvidence, AuthenticatorRecord, VerifiedEvidence } from '../../protocol/src/index.ts';
import { challengeDigest, decodeChallengePayload } from './challenge.ts';
import { verifySignature } from './signing.ts';

export interface EvidenceVerifier {
  type: string;
  verify(args: {
    evidence: ApprovalEvidence;
    challenge: ApprovalChallengePackage;
    authenticator: AuthenticatorRecord;
    now?: Date;
  }): VerifiedEvidence;
}

export class GenericSignedEvidenceVerifier implements EvidenceVerifier {
  readonly type: string;
  private readonly level: VerifiedEvidence['humanVerificationLevel'];

  constructor(type: string, level: VerifiedEvidence['humanVerificationLevel']) {
    this.type = type;
    this.level = level;
  }

  verify({ evidence, challenge, authenticator, now = new Date() }: {
    evidence: ApprovalEvidence;
    challenge: ApprovalChallengePackage;
    authenticator: AuthenticatorRecord;
    now?: Date;
  }): VerifiedEvidence {
    const payload = decodeChallengePayload(challenge);
    if (authenticator.status !== 'ACTIVE') throw new Error('AUTHENTICATOR_REVOKED');
    if (evidence.type !== this.type) throw new Error('EVIDENCE_TYPE_MISMATCH');
    if (evidence.authenticatorId !== authenticator.id || payload.authenticatorId !== authenticator.id) throw new Error('AUTHENTICATOR_MISMATCH');
    if (evidence.requestId !== payload.requestId) throw new Error('REQUEST_MISMATCH');
    if (new Date(payload.expiresAt).getTime() <= now.getTime()) throw new Error('CHALLENGE_EXPIRED');
    const expectedDigest = challengeDigest(challenge);
    if (evidence.challengeDigest !== expectedDigest) throw new Error('CHALLENGE_DIGEST_MISMATCH');
    const ok = verifySignature(authenticator.signatureAlgorithm, authenticator.publicKeyPem, Buffer.from(expectedDigest, 'utf8'), evidence.signature);
    if (!ok) throw new Error('INVALID_EVIDENCE_SIGNATURE');
    return {
      schema: 'haa.verified-evidence.v1',
      principalId: authenticator.principalId,
      authenticatorId: authenticator.id,
      verifiedChallengeDigest: expectedDigest,
      humanVerificationLevel: this.level,
      verifiedAt: now.toISOString(),
    };
  }
}
