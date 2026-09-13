import { createPublicKey, verify as verifyCryptoSignature } from 'node:crypto';
import type { ActionSpec, ApprovalRequest, ExecutionGrant } from '../../protocol/src/index.ts';
import { canonicalize } from '../../core/src/canonical.ts';

export type CeremonyOutcome = 'APPROVE' | 'REJECT';

export type RejectionReason =
  | 'USER_ESCAPE'
  | 'WINDOW_CLOSED'
  | 'TIMEOUT'
  | 'CHALLENGE_EXPIRED'
  | 'INTERACTION_ERROR';

export interface RejectionRecord {
  outcome: 'REJECT';
  requestId: string;
  state: 'REJECTED';
  challengeDigest: string;
  reason: RejectionReason;
  rejectedAt: string;
  provenance: 'authenticated-approver-channel';
  assurance: 'explicit-human-negative-action' | 'fail-closed-terminal';
}

export interface AuthorityPublicKey {
  keyId: string;
  algorithm: 'Ed25519' | 'ES256';
  publicKeyPem: string;
  status: 'ACTIVE' | 'RETIRED';
  createdAt?: string;
  retiredAt?: string;
}

export class HaaGrantVerificationError extends Error {
  readonly code: string;

  constructor(code: string) {
    super(code);
    this.name = 'HaaGrantVerificationError';
    this.code = code;
  }
}

export interface VerifyExecutionGrantInput {
  grant: ExecutionGrant;
  authorityKeys: AuthorityPublicKey[];
  expectedRequestId: string;
  expectedExecutionId?: string;
  expectedActionDigest: string;
  expectedExecutorAudience: string;
  now?: Date;
  clockSkewMs?: number;
  maxTtlMs?: number;
}

const DEFAULT_EXECUTION_GRANT_CLOCK_SKEW_MS = 5_000;
const DEFAULT_MAX_EXECUTION_GRANT_TTL_MS = 30_000;

export class HaaClient {
  constructor(
    readonly baseUrl: string,
    readonly apiKey: string,
  ) {}

  async requestApproval(input: {
    action: ActionSpec;
    approverPrincipalId: string;
    executorAudience: string;
    policySnapshotHash?: string;
    requestId?: string;
    ttlMs?: number;
  }): Promise<ApprovalRequest> {
    return this.request('/v1/approval-requests', { method: 'POST', body: input }) as Promise<ApprovalRequest>;
  }

  async getApproval(requestId: string): Promise<ApprovalRequest> {
    return this.request(`/v1/approval-requests/${encodeURIComponent(requestId)}`) as Promise<ApprovalRequest>;
  }

  async rejectApproval(input: {
    requestId: string;
    challengeDigest: string;
    reason: RejectionReason;
  }): Promise<RejectionRecord> {
    return this.request(`/v1/approval-requests/${encodeURIComponent(input.requestId)}/reject`, {
      method: 'POST',
      body: { challengeDigest: input.challengeDigest, reason: input.reason },
    }) as Promise<RejectionRecord>;
  }

  async authorize(input: {
    requestId: string;
    executionId: string;
    actualAction: ActionSpec;
    actualState?: Record<string, unknown>;
  }): Promise<ExecutionGrant> {
    return this.request(`/v1/approval-requests/${encodeURIComponent(input.requestId)}/authorize`, {
      method: 'POST',
      body: {
        executionId: input.executionId,
        actualAction: input.actualAction,
        ...(input.actualState !== undefined ? { actualState: input.actualState } : {}),
      },
    }) as Promise<ExecutionGrant>;
  }

  async getAuthorityKeys(): Promise<AuthorityPublicKey[]> {
    return this.request('/v1/authority-keys') as Promise<AuthorityPublicKey[]>;
  }

  private async request(path: string, options: { method?: string; body?: unknown } = {}): Promise<unknown> {
    const response = await fetch(new URL(path, this.baseUrl), {
      method: options.method ?? 'GET',
      headers: {
        'content-type': 'application/json',
        'x-api-key': this.apiKey,
      },
      ...(options.body !== undefined ? { body: JSON.stringify(options.body) } : {}),
    });
    const text = await response.text();
    let body: unknown;
    try { body = text ? JSON.parse(text) : undefined; } catch { body = text; }
    if (!response.ok) {
      const code = typeof body === 'object' && body !== null && 'error' in body && typeof (body as { error?: unknown }).error === 'string'
        ? (body as { error: string }).error
        : `HTTP_${response.status}`;
      throw new HaaApiError(response.status, code, body);
    }
    return body;
  }
}

const GRANT_KEYS = [
  'actionDigest',
  'authorityKeyId',
  'executionId',
  'executorAudience',
  'expiresAt',
  'issuedAt',
  'requestId',
  'schema',
  'signature',
  'signatureAlgorithm',
].sort();

function assertGrantShape(grant: ExecutionGrant): void {
  const keys = Object.keys(grant as unknown as Record<string, unknown>).sort();
  if (keys.length !== GRANT_KEYS.length || keys.some((key, index) => key !== GRANT_KEYS[index])) {
    throw new HaaGrantVerificationError('INVALID_GRANT_SHAPE');
  }
  const requiredStrings = [
    grant.requestId,
    grant.executionId,
    grant.actionDigest,
    grant.executorAudience,
    grant.issuedAt,
    grant.expiresAt,
    grant.authorityKeyId,
    grant.signature,
  ];
  if (requiredStrings.some((value) => typeof value !== 'string' || value.length === 0)) {
    throw new HaaGrantVerificationError('INVALID_GRANT_SHAPE');
  }
}

export function verifyExecutionGrant(input: VerifyExecutionGrantInput): ExecutionGrant {
  const { grant } = input;
  assertGrantShape(grant);
  if (grant.schema !== 'haa.execution-grant.v1') throw new HaaGrantVerificationError('UNSUPPORTED_GRANT_SCHEMA');
  if (grant.signatureAlgorithm !== 'Ed25519' && grant.signatureAlgorithm !== 'ES256') {
    throw new HaaGrantVerificationError('UNSUPPORTED_SIGNATURE_ALGORITHM');
  }

  const authorityKey = input.authorityKeys.find((key) => key.keyId === grant.authorityKeyId);
  if (!authorityKey) throw new HaaGrantVerificationError('UNKNOWN_AUTHORITY_KEY');
  if (authorityKey.status !== 'ACTIVE') throw new HaaGrantVerificationError('AUTHORITY_KEY_NOT_ACTIVE');
  if (authorityKey.algorithm !== grant.signatureAlgorithm) throw new HaaGrantVerificationError('AUTHORITY_ALGORITHM_MISMATCH');

  const issuedAt = Date.parse(grant.issuedAt);
  const expiresAt = Date.parse(grant.expiresAt);
  if (!Number.isFinite(issuedAt) || !Number.isFinite(expiresAt) || expiresAt <= issuedAt) {
    throw new HaaGrantVerificationError('GRANT_INVALID_TIME_RANGE');
  }
  const now = (input.now ?? new Date()).getTime();
  if (!Number.isFinite(now)) throw new HaaGrantVerificationError('INVALID_VERIFICATION_TIME');
  const clockSkewMs = input.clockSkewMs ?? DEFAULT_EXECUTION_GRANT_CLOCK_SKEW_MS;
  const maxTtlMs = input.maxTtlMs ?? DEFAULT_MAX_EXECUTION_GRANT_TTL_MS;
  if (!Number.isFinite(clockSkewMs) || clockSkewMs < 0 || !Number.isFinite(maxTtlMs) || maxTtlMs <= 0) {
    throw new HaaGrantVerificationError('INVALID_GRANT_SHAPE');
  }
  if (issuedAt > now + clockSkewMs) throw new HaaGrantVerificationError('GRANT_ISSUED_IN_FUTURE');
  if (expiresAt - issuedAt > maxTtlMs) throw new HaaGrantVerificationError('GRANT_TTL_EXCEEDS_POLICY');
  if (expiresAt <= now) throw new HaaGrantVerificationError('GRANT_EXPIRED');

  if (authorityKey.createdAt !== undefined) {
    const keyCreatedAt = Date.parse(authorityKey.createdAt);
    if (!Number.isFinite(keyCreatedAt)) throw new HaaGrantVerificationError('AUTHORITY_KEY_METADATA_INVALID');
    if (issuedAt + clockSkewMs < keyCreatedAt) throw new HaaGrantVerificationError('GRANT_ISSUED_BEFORE_KEY_ACTIVE');
  }

  const unsigned = {
    schema: grant.schema,
    requestId: grant.requestId,
    executionId: grant.executionId,
    actionDigest: grant.actionDigest,
    executorAudience: grant.executorAudience,
    issuedAt: grant.issuedAt,
    expiresAt: grant.expiresAt,
    authorityKeyId: grant.authorityKeyId,
    signatureAlgorithm: grant.signatureAlgorithm,
  };
  const bytes = Buffer.from(canonicalize(unsigned), 'utf8');
  const publicKey = createPublicKey(authorityKey.publicKeyPem);
  const signature = Buffer.from(grant.signature, 'base64url');
  const validSignature = grant.signatureAlgorithm === 'Ed25519'
    ? verifyCryptoSignature(null, bytes, publicKey, signature)
    : verifyCryptoSignature('sha256', bytes, publicKey, signature);
  if (!validSignature) throw new HaaGrantVerificationError('INVALID_GRANT_SIGNATURE');

  if (grant.requestId !== input.expectedRequestId) throw new HaaGrantVerificationError('REQUEST_ID_MISMATCH');
  if (input.expectedExecutionId !== undefined && grant.executionId !== input.expectedExecutionId) {
    throw new HaaGrantVerificationError('EXECUTION_ID_MISMATCH');
  }
  if (grant.actionDigest !== input.expectedActionDigest) throw new HaaGrantVerificationError('ACTION_DIGEST_MISMATCH');
  if (grant.executorAudience !== input.expectedExecutorAudience) throw new HaaGrantVerificationError('EXECUTOR_AUDIENCE_MISMATCH');
  return grant;
}

export class HaaApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly responseBody: unknown;

  constructor(status: number, code: string, responseBody: unknown) {
    super(code);
    this.name = 'HaaApiError';
    this.status = status;
    this.code = code;
    this.responseBody = responseBody;
  }
}
