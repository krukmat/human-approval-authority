import { randomUUID } from 'node:crypto';
import type {
  ActionSpec,
  ApprovalEvidence,
  ApprovalRequest,
  AuditEvent,
  AuthenticatorRecord,
  JsonValue,
} from '../../../packages/protocol/src/index.ts';
import {
  ActionProfileRegistry,
  GenericSignedEvidenceVerifier,
  assertTransition,
  challengeDigest,
  createExecutionGrant,
  createReceipt,
  decodeChallengePayload,
  digestJson,
  intentDigest,
  issueChallenge,
  sha256,
  verifyChallengeAuthority,
  type EvidenceVerifier,
  type Signer,
} from '../../../packages/core/src/index.ts';
import { SqliteStore } from '../../../packages/persistence-sqlite/src/index.ts';

export interface HaaApplicationOptions {
  store: SqliteStore;
  authoritySigner: Signer;
  profiles?: ActionProfileRegistry;
  evidenceVerifiers?: EvidenceVerifier[];
}

export class HaaApplication {
  readonly store: SqliteStore;
  readonly signer: Signer;
  readonly profiles: ActionProfileRegistry;
  readonly verifiers = new Map<string, EvidenceVerifier>();

  constructor(options: HaaApplicationOptions) {
    this.store = options.store;
    this.signer = options.authoritySigner;
    this.profiles = options.profiles ?? new ActionProfileRegistry();
    const defaults: EvidenceVerifier[] = [
      new GenericSignedEvidenceVerifier('test-key', 'presence'),
      new GenericSignedEvidenceVerifier('apple-secure-enclave', 'user-verified-device-bound'),
      new GenericSignedEvidenceVerifier('haa-hardware-v1', 'user-verified-device-bound'),
    ];
    for (const verifier of options.evidenceVerifiers ?? defaults) this.verifiers.set(verifier.type, verifier);
  }

  registerClient(clientId: string, apiKey: string): void {
    this.store.registerClient(clientId, sha256(apiKey));
  }

  authenticate(apiKey: string): string {
    const id = this.store.authenticateClient(sha256(apiKey));
    if (!id) throw new Error('UNAUTHORIZED');
    return id;
  }

  registerAuthenticator(apiKey: string, record: Omit<AuthenticatorRecord, 'schema' | 'status' | 'createdAt'>, now = new Date()): AuthenticatorRecord {
    const actor = this.authenticate(apiKey);
    if (actor !== record.principalId) throw new Error('PRINCIPAL_MISMATCH');
    const full: AuthenticatorRecord = {
      schema: 'haa.authenticator.v1',
      ...record,
      status: 'ACTIVE',
      createdAt: now.toISOString(),
    };
    this.store.saveAuthenticator(full);
    return full;
  }

  revokeAuthenticator(apiKey: string, authenticatorId: string, now = new Date()): void {
    const actor = this.authenticate(apiKey);
    const record = this.store.getAuthenticator(authenticatorId);
    if (!record) throw new Error('AUTHENTICATOR_NOT_FOUND');
    if (record.principalId !== actor) throw new Error('FORBIDDEN');
    if (!this.store.revokeAuthenticator(authenticatorId, now.toISOString())) throw new Error('AUTHENTICATOR_NOT_ACTIVE');
  }

  createApprovalRequest(args: {
    apiKey: string;
    action: ActionSpec;
    approverPrincipalId: string;
    executorAudience: string;
    policySnapshotHash?: string;
    requestId?: string;
    ttlMs?: number;
    now?: Date;
  }): ApprovalRequest {
    const requesterId = this.authenticate(args.apiKey);
    const now = args.now ?? new Date();
    this.profiles.validate(args.action);
    const requestId = args.requestId ?? randomUUID();
    const actionDigest = this.profiles.actionDigest(args.action);
    const intent = {
      schema: 'haa.intent.v1' as const,
      requestId,
      action: args.action,
      requesterId,
      approverPrincipalId: args.approverPrincipalId,
      executorAudience: args.executorAudience,
      policySnapshotHash: args.policySnapshotHash ?? digestJson({ policy: 'manual-approval-v1' }),
      createdAt: now.toISOString(),
      expiresAt: new Date(now.getTime() + (args.ttlMs ?? 10 * 60_000)).toISOString(),
    };
    const request: ApprovalRequest = {
      schema: 'haa.request.v1',
      id: requestId,
      intent,
      actionDigest,
      intentDigest: intentDigest(intent),
      state: 'PENDING',
      createdAt: now.toISOString(),
      updatedAt: now.toISOString(),
    };
    this.store.createRequest(request);
    this.store.appendAudit(this.audit({ requestId, eventType: 'REQUESTED', actorId: requesterId, actionDigest, at: now }));
    return request;
  }

  getRequest(apiKey: string, requestId: string): ApprovalRequest {
    this.authenticate(apiKey);
    const request = this.store.getRequest(requestId);
    if (!request) throw new Error('REQUEST_NOT_FOUND');
    return request;
  }

  issueApprovalChallenge(args: { apiKey: string; requestId: string; authenticatorId: string; now?: Date }) {
    const actor = this.authenticate(args.apiKey);
    const request = this.mustRequest(args.requestId);
    if (actor !== request.intent.approverPrincipalId) throw new Error('FORBIDDEN');
    const auth = this.store.getAuthenticator(args.authenticatorId);
    if (!auth || auth.status !== 'ACTIVE') throw new Error('AUTHENTICATOR_NOT_ACTIVE');
    if (auth.principalId !== request.intent.approverPrincipalId) throw new Error('AUTHENTICATOR_PRINCIPAL_MISMATCH');
    const challenge = issueChallenge(request, auth.id, this.profiles, this.signer, args.now);
    const digest = challengeDigest(challenge);
    const payload = decodeChallengePayload(challenge);
    this.store.saveChallenge(digest, challenge, payload.requestId, payload.authenticatorId, payload.issuedAt);
    this.store.appendAudit(this.audit({ requestId: request.id, eventType: 'CHALLENGE_ISSUED', actorId: actor, actionDigest: request.actionDigest, at: args.now ?? new Date(), details: { challengeDigest: digest } }));
    return challenge;
  }

  submitEvidence(args: { apiKey: string; evidence: ApprovalEvidence; now?: Date }) {
    const actor = this.authenticate(args.apiKey);
    const request = this.mustRequest(args.evidence.requestId);
    if (actor !== request.intent.approverPrincipalId) throw new Error('FORBIDDEN');
    if (request.state !== 'PENDING') throw new Error(`REQUEST_NOT_PENDING:${request.state}`);
    const storedChallenge = this.store.getChallenge(args.evidence.challengeDigest);
    if (!storedChallenge || storedChallenge.consumed) throw new Error('CHALLENGE_NOT_ACTIVE');
    const challenge = storedChallenge.challenge;
    if (challenge.authorityKeyId !== this.signer.keyId || !verifyChallengeAuthority(challenge, this.signer.publicKeyPem)) throw new Error('INVALID_HAA_CHALLENGE_SIGNATURE');
    const challengePayload = decodeChallengePayload(challenge);
    if (challengePayload.requestId !== request.id || challengePayload.intentDigest !== request.intentDigest || challengePayload.actionDigest !== request.actionDigest) {
      throw new Error('CHALLENGE_BINDING_MISMATCH');
    }
    const authenticator = this.store.getAuthenticator(args.evidence.authenticatorId);
    if (!authenticator) throw new Error('AUTHENTICATOR_NOT_FOUND');
    if (authenticator.principalId !== request.intent.approverPrincipalId) throw new Error('AUTHENTICATOR_PRINCIPAL_MISMATCH');
    const verifier = this.verifiers.get(args.evidence.type);
    if (!verifier) throw new Error('UNSUPPORTED_EVIDENCE_TYPE');
    const verified = verifier.verify({
      evidence: args.evidence,
      challenge,
      authenticator,
      ...(args.now ? { now: args.now } : {}),
    });
    if (!this.store.consumeChallenge(args.evidence.challengeDigest)) throw new Error('CHALLENGE_REPLAY');
    assertTransition('PENDING', 'APPROVED');
    if (!this.store.transitionRequest(request.id, 'PENDING', 'APPROVED', (args.now ?? new Date()).toISOString())) throw new Error('CONCURRENT_APPROVAL');
    const receipt = createReceipt({
      requestId: request.id,
      actionDigest: request.actionDigest,
      intentDigest: request.intentDigest,
      evidence: verified,
      expiresAt: request.intent.expiresAt,
      signer: this.signer,
      ...(args.now ? { now: args.now } : {}),
    });
    this.store.saveReceipt(receipt);
    this.store.appendAudit(this.audit({ requestId: request.id, eventType: 'APPROVED', actorId: verified.principalId, actionDigest: request.actionDigest, at: args.now ?? new Date(), details: { authenticatorId: verified.authenticatorId } }));
    return receipt;
  }

  authorizeAndConsume(args: {
    apiKey: string;
    requestId: string;
    executionId: string;
    actualAction: ActionSpec;
    actualState?: Record<string, JsonValue>;
    now?: Date;
  }) {
    const executorId = this.authenticate(args.apiKey);
    const request = this.mustRequest(args.requestId);
    if (request.intent.executorAudience !== executorId) throw new Error('WRONG_EXECUTOR_AUDIENCE');

    this.profiles.validate(args.actualAction);
    const actualDigest = this.profiles.actionDigest(args.actualAction);
    if (actualDigest !== request.actionDigest) throw new Error('ACTION_DIGEST_MISMATCH');

    const priorGrant = this.store.getExecutionGrant(args.executionId);
    if (priorGrant) {
      if (priorGrant.requestId !== request.id) throw new Error('EXECUTION_ID_CONFLICT');
      if (priorGrant.actionDigest !== request.actionDigest || priorGrant.executorAudience !== executorId) throw new Error('EXECUTION_GRANT_BINDING_MISMATCH');
      if (new Date(priorGrant.expiresAt).getTime() <= (args.now ?? new Date()).getTime()) throw new Error('EXECUTION_GRANT_EXPIRED');
      return priorGrant;
    }

    if (request.state !== 'APPROVED') throw new Error(`REQUEST_NOT_APPROVED:${request.state}`);
    if (new Date(request.intent.expiresAt).getTime() <= (args.now ?? new Date()).getTime()) throw new Error('APPROVAL_EXPIRED');
    this.profiles.validatePreconditions(args.actualAction, args.actualState);

    const grant = createExecutionGrant({
      requestId: request.id,
      executionId: args.executionId,
      actionDigest: request.actionDigest,
      executorAudience: executorId,
      signer: this.signer,
      ...(args.now ? { now: args.now } : {}),
    });
    const at = args.now ?? new Date();
    const result = this.store.consumeApproved({
      requestId: request.id,
      executionId: args.executionId,
      grant,
      consumedAt: at.toISOString(),
      auditEvent: this.audit({ requestId: request.id, eventType: 'CONSUMED', actorId: executorId, actionDigest: request.actionDigest, executionId: args.executionId, at }),
    });
    return result.grant;
  }

  listAudit(apiKey: string, requestId: string): AuditEvent[] {
    this.authenticate(apiKey);
    return this.store.listAudit(requestId);
  }

  private mustRequest(id: string): ApprovalRequest {
    const request = this.store.getRequest(id);
    if (!request) throw new Error('REQUEST_NOT_FOUND');
    return request;
  }

  private audit(args: {
    requestId: string;
    eventType: AuditEvent['eventType'];
    actorId: string;
    at: Date;
    actionDigest?: string;
    executionId?: string;
    details?: Record<string, JsonValue>;
  }): AuditEvent {
    return {
      schema: 'haa.audit.v1',
      id: randomUUID(),
      requestId: args.requestId,
      eventType: args.eventType,
      actorId: args.actorId,
      at: args.at.toISOString(),
      ...(args.actionDigest ? { actionDigest: args.actionDigest } : {}),
      ...(args.executionId ? { executionId: args.executionId } : {}),
      ...(args.details ? { details: args.details } : {}),
    };
  }
}
