export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };

export type ApprovalState =
  | 'REQUESTED'
  | 'PENDING'
  | 'APPROVED'
  | 'REJECTED'
  | 'EXPIRED'
  | 'REVOKED'
  | 'CONSUMED';

export interface DisplayClaim {
  label: string;
  value: string;
  emphasis?: 'normal' | 'warning' | 'critical';
}

export interface ActionSpec {
  schema: 'haa.action.v1';
  type: string;
  payload: Record<string, JsonValue>;
  preconditions?: Record<string, JsonValue>;
}

export interface ApprovalIntent {
  schema: 'haa.intent.v1';
  requestId: string;
  action: ActionSpec;
  requesterId: string;
  approverPrincipalId: string;
  executorAudience: string;
  policySnapshotHash: string;
  createdAt: string;
  expiresAt: string;
}

export interface ApprovalRequest {
  schema: 'haa.request.v1';
  id: string;
  intent: ApprovalIntent;
  actionDigest: string;
  intentDigest: string;
  state: ApprovalState;
  createdAt: string;
  updatedAt: string;
}

export interface ApprovalChallengePayload {
  schema: 'haa.challenge-payload.v1';
  protocolVersion: 1;
  requestId: string;
  actionType: string;
  actionDigest: string;
  intentDigest: string;
  nonce: string;
  approverPrincipalId: string;
  authenticatorId: string;
  executorAudience: string;
  policySnapshotHash: string;
  displayClaims: DisplayClaim[];
  issuedAt: string;
  expiresAt: string;
}

export interface ApprovalChallengePackage {
  schema: 'haa.challenge.v1';
  payload: string;
  authorityKeyId: string;
  signatureAlgorithm: 'Ed25519' | 'ES256';
  signature: string;
}

export interface ApprovalEvidence {
  schema: 'haa.evidence.v1';
  type: string;
  authenticatorId: string;
  requestId: string;
  challengeDigest: string;
  signatureAlgorithm: 'Ed25519' | 'ES256';
  signature: string;
  counter?: number;
}

export interface VerifiedEvidence {
  schema: 'haa.verified-evidence.v1';
  principalId: string;
  authenticatorId: string;
  verifiedChallengeDigest: string;
  humanVerificationLevel: 'presence' | 'user-verified' | 'user-verified-device-bound';
  verifiedAt: string;
}

export interface ApprovalReceipt {
  schema: 'haa.receipt.v1';
  requestId: string;
  actionDigest: string;
  intentDigest: string;
  approverPrincipalId: string;
  authenticatorId: string;
  humanVerificationLevel: VerifiedEvidence['humanVerificationLevel'];
  issuedAt: string;
  expiresAt: string;
  authorityKeyId: string;
  signatureAlgorithm: 'Ed25519' | 'ES256';
  signature: string;
}

export interface ExecutionGrant {
  schema: 'haa.execution-grant.v1';
  requestId: string;
  executionId: string;
  actionDigest: string;
  executorAudience: string;
  issuedAt: string;
  expiresAt: string;
  authorityKeyId: string;
  signatureAlgorithm: 'Ed25519' | 'ES256';
  signature: string;
}

export interface AuthenticatorRecord {
  schema: 'haa.authenticator.v1';
  id: string;
  principalId: string;
  type: string;
  publicKeyPem: string;
  signatureAlgorithm: 'Ed25519' | 'ES256';
  status: 'ACTIVE' | 'REVOKED';
  createdAt: string;
  revokedAt?: string;
}

export interface AuditEvent {
  schema: 'haa.audit.v1';
  id: string;
  requestId: string;
  eventType:
    | 'REQUESTED'
    | 'CHALLENGE_ISSUED'
    | 'APPROVED'
    | 'REJECTED'
    | 'EXPIRED'
    | 'REVOKED'
    | 'CONSUMED';
  actorId: string;
  actionDigest?: string;
  executionId?: string;
  at: string;
  details?: Record<string, JsonValue>;
}
