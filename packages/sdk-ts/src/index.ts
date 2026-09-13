import { createPublicKey, verify as verifyCryptoSignature } from 'node:crypto';
import type { ActionSpec, ApprovalRequest, ExecutionGrant } from '@haa/protocol';

export type { ActionSpec, ApprovalRequest, ApprovalState, ExecutionGrant } from '@haa/protocol';

export type CeremonyOutcome = 'APPROVE' | 'REJECT';
export type RejectionReason =
  | 'USER_ESCAPE'
  | 'WINDOW_CLOSED'
  | 'TIMEOUT'
  | 'CHALLENGE_EXPIRED'
  | 'INTERACTION_ERROR';
export type RejectionAssurance = 'explicit-human-negative-action' | 'fail-closed-terminal';

export interface CeremonyResult {
  outcome: CeremonyOutcome;
  requestId: string;
  reason?: RejectionReason;
}

export interface RejectionRecord {
  outcome: 'REJECT';
  requestId: string;
  state: 'REJECTED';
  challengeDigest: string;
  reason: RejectionReason;
  rejectedAt: string;
  provenance: 'authenticated-approver-channel';
  assurance: RejectionAssurance;
}

export interface RejectApprovalInput {
  requestId: string;
  challengeDigest: string;
  reason?: RejectionReason;
}

export interface RequestApprovalInput {
  action: ActionSpec;
  approverPrincipalId: string;
  executorAudience: string;
  requestId?: string;
  ttlMs?: number;
}

export interface AuthorizeInput {
  requestId: string;
  executionId: string;
  actualAction: ActionSpec;
  actualState?: Record<string, unknown>;
}

export interface AuthorityVerificationKey {
  keyId: string;
  algorithm: 'Ed25519' | 'ES256';
  publicKeyPem: string;
  status?: 'ACTIVE' | 'RETIRED';
  createdAt?: string;
  retiredAt?: string;
}

export const DEFAULT_MAX_EXECUTION_GRANT_TTL_MS = 30_000;
export const DEFAULT_EXECUTION_GRANT_CLOCK_SKEW_MS = 5_000;

export interface VerifyExecutionGrantInput {
  grant: ExecutionGrant;
  authorityKeys: AuthorityVerificationKey[];
  expectedRequestId: string;
  expectedActionDigest: string;
  expectedExecutorAudience: string;
  expectedExecutionId?: string;
  now?: Date;
  maxTtlMs?: number;
  clockSkewMs?: number;
}

export type GrantVerificationErrorCode =
  | 'INVALID_GRANT_SHAPE'
  | 'UNSUPPORTED_GRANT_SCHEMA'
  | 'UNSUPPORTED_SIGNATURE_ALGORITHM'
  | 'UNKNOWN_AUTHORITY_KEY'
  | 'AUTHORITY_KEY_NOT_ACTIVE'
  | 'AUTHORITY_KEY_METADATA_INVALID'
  | 'AUTHORITY_ALGORITHM_MISMATCH'
  | 'INVALID_GRANT_SIGNATURE'
  | 'GRANT_INVALID_TIME_RANGE'
  | 'INVALID_VERIFICATION_TIME'
  | 'GRANT_ISSUED_IN_FUTURE'
  | 'GRANT_ISSUED_BEFORE_KEY_ACTIVE'
  | 'GRANT_TTL_EXCEEDS_POLICY'
  | 'GRANT_EXPIRED'
  | 'REQUEST_ID_MISMATCH'
  | 'EXECUTION_ID_MISMATCH'
  | 'ACTION_DIGEST_MISMATCH'
  | 'EXECUTOR_AUDIENCE_MISMATCH';

export class HaaGrantVerificationError extends Error {
  readonly code: GrantVerificationErrorCode;

  constructor(code: GrantVerificationErrorCode) {
    super(code);
    this.name = 'HaaGrantVerificationError';
    this.code = code;
  }
}

function canonicalize(value: unknown): string {
  if (value === null) return 'null';
  if (typeof value === 'string' || typeof value === 'boolean') return JSON.stringify(value);
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new HaaGrantVerificationError('INVALID_GRANT_SHAPE');
    if (Object.is(value, -0)) return '0';
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonicalize).join(',')}]`;
  if (typeof value !== 'object') throw new HaaGrantVerificationError('INVALID_GRANT_SHAPE');
  const object = value as Record<string, unknown>;
  const keys = Object.keys(object).sort();
  return `{${keys.map((key) => `${JSON.stringify(key)}:${canonicalize(object[key])}`).join(',')}}`;
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

export class HaaClient {
  readonly baseUrl: string;
  readonly apiKey: string;

  constructor(baseUrl: string, apiKey: string) {
    this.baseUrl = baseUrl;
    this.apiKey = apiKey;
  }

  private async call<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(new URL(path, this.baseUrl), {
      ...init,
      headers: { 'content-type': 'application/json', 'x-api-key': this.apiKey, ...(init.headers ?? {}) },
    });

    const text = await response.text();
    let body: unknown;
    if (text) {
      try {
        body = JSON.parse(text);
      } catch {
        body = text;
      }
    }

    if (!response.ok) {
      const code = typeof body === 'object' && body !== null && 'error' in body && typeof (body as { error?: unknown }).error === 'string'
        ? (body as { error: string }).error
        : `HTTP_${response.status}`;
      throw new HaaApiError(response.status, code, body);
    }

    if (response.status === 204 || !text) return undefined as T;
    return body as T;
  }

  getAuthorityKeys(): Promise<AuthorityVerificationKey[]> {
    return this.call('/v1/authority-keys');
  }

  requestApproval(input: RequestApprovalInput): Promise<ApprovalRequest> {
    return this.call('/v1/approval-requests', { method: 'POST', body: JSON.stringify(input) });
  }

  getApproval(requestId: string): Promise<ApprovalRequest> {
    return this.call(`/v1/approval-requests/${encodeURIComponent(requestId)}`);
  }

  rejectApproval(input: RejectApprovalInput): Promise<RejectionRecord> {
    return this.call(`/v1/approval-requests/${encodeURIComponent(input.requestId)}/reject`, {
      method: 'POST',
      body: JSON.stringify({
        challengeDigest: input.challengeDigest,
        reason: input.reason ?? 'USER_ESCAPE',
      }),
    });
  }

  authorize(input: AuthorizeInput): Promise<ExecutionGrant> {
    return this.call(`/v1/approval-requests/${encodeURIComponent(input.requestId)}/authorize`, {
      method: 'POST',
      body: JSON.stringify({
        executionId: input.executionId,
        actualAction: input.actualAction,
        ...(input.actualState ? { actualState: input.actualState } : {}),
      }),
    });
  }
}
