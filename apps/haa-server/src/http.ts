import Fastify from 'fastify';
import { z } from 'zod';
import type { ActionSpec, ApprovalEvidence, AuthenticatorRecord, JsonValue } from '../../../packages/protocol/src/index.ts';
import type { SignatureAlgorithm } from '../../../packages/core/src/index.ts';
import type { WebAuthnRegistrationCredentialJSON } from '../../../packages/webauthn/src/index.ts';
import type { HaaApplication } from './application.ts';
import { webAuthnApprovalPage } from './webauthn-ui.ts';

const MAX_BODY_BYTES = 64 * 1024;
const MAX_STRING = 4096;
const MAX_IDENTIFIER = 128;
const MAX_JSON_DEPTH = 12;
const MAX_JSON_KEYS = 128;
const MAX_JSON_ARRAY = 128;
const MAX_WEBAUTHN_BLOB = 48 * 1024;

const identifier = z.string().min(1).max(MAX_IDENTIFIER).regex(/^[A-Za-z0-9._:-]+$/);
const boundedString = z.string().max(MAX_STRING);
const base64urlBlob = z.string().min(1).max(MAX_WEBAUTHN_BLOB).regex(/^[A-Za-z0-9_-]+$/);

function isBoundedJson(value: unknown, depth = 0): value is JsonValue {
  if (depth > MAX_JSON_DEPTH) return false;
  if (value === null || typeof value === 'boolean') return true;
  if (typeof value === 'number') return Number.isFinite(value);
  if (typeof value === 'string') return value.length <= MAX_STRING;
  if (Array.isArray(value)) {
    return value.length <= MAX_JSON_ARRAY && value.every((item) => isBoundedJson(item, depth + 1));
  }
  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>);
    return entries.length <= MAX_JSON_KEYS
      && entries.every(([key, item]) => key.length <= MAX_IDENTIFIER && isBoundedJson(item, depth + 1));
  }
  return false;
}

const jsonObject = z.custom<Record<string, JsonValue>>(
  (value) => typeof value === 'object' && value !== null && !Array.isArray(value) && isBoundedJson(value),
  { message: 'Expected a bounded JSON object' },
);

const actionSpecSchema = z.object({
  schema: z.literal('haa.action.v1'),
  type: identifier,
  payload: jsonObject,
  preconditions: jsonObject.optional(),
}).strict();

const createRequestSchema = z.object({
  action: actionSpecSchema,
  approverPrincipalId: identifier,
  executorAudience: identifier,
  policySnapshotHash: boundedString.optional(),
  requestId: identifier.optional(),
  ttlMs: z.number().int().min(1000).max(24 * 60 * 60_000).optional(),
}).strict();

const authenticatorSchema = z.object({
  id: identifier,
  principalId: identifier,
  type: identifier,
  publicKeyPem: z.string().min(1).max(16 * 1024),
  signatureAlgorithm: z.enum(['Ed25519', 'ES256']),
}).strict();

const challengeRequestSchema = z.object({ authenticatorId: identifier }).strict();
const rejectionReasonSchema = z.enum([
  'USER_ESCAPE',
  'WINDOW_CLOSED',
  'TIMEOUT',
  'CHALLENGE_EXPIRED',
  'INTERACTION_ERROR',
]);
const rejectSchema = z.object({
  challengeDigest: z.string().min(1).max(MAX_STRING),
  reason: rejectionReasonSchema,
}).strict();

const evidenceSchema = z.object({
  schema: z.literal('haa.evidence.v1'),
  type: identifier,
  authenticatorId: identifier,
  requestId: identifier,
  challengeDigest: boundedString.min(1),
  signatureAlgorithm: z.enum(['Ed25519', 'ES256']),
  signature: z.string().min(1).max(48 * 1024),
  counter: z.number().int().nonnegative().optional(),
}).strict();

const authorizeSchema = z.object({
  executionId: identifier,
  actualAction: actionSpecSchema,
  actualState: jsonObject.optional(),
}).strict();

const idParamsSchema = z.object({ id: identifier }).strict();
const emptyObjectSchema = z.object({}).strict();
const webAuthnCredentialSchema = z.object({
  id: base64urlBlob,
  rawId: base64urlBlob,
  type: z.literal('public-key'),
  response: z.object({
    clientDataJSON: base64urlBlob,
    attestationObject: base64urlBlob,
    transports: z.array(z.string().min(1).max(64)).max(16).optional(),
  }).strict(),
}).strict();
const webAuthnRegistrationVerifySchema = z.object({
  registrationId: identifier,
  credential: webAuthnCredentialSchema,
}).strict();
const webAuthnAuthenticationOptionsSchema = z.object({
  requestId: identifier,
  authenticatorId: identifier,
  challengeDigest: boundedString.min(1),
}).strict();

function apiKey(headers: Record<string, unknown>): string {
  const value = headers['x-api-key'];
  if (typeof value !== 'string' || value.length === 0 || value.length > MAX_STRING) throw new Error('UNAUTHORIZED');
  return value;
}

function parse<T>(schema: z.ZodType<T>, value: unknown): T {
  const result = schema.safeParse(value);
  if (!result.success) throw new Error('INVALID_REQUEST_INPUT');
  return result.data;
}

export interface HttpServerOptions {
  authorityKeys?: () => Array<{
    keyId: string;
    algorithm: SignatureAlgorithm;
    publicKeyPem: string;
    status: 'ACTIVE' | 'RETIRED';
    createdAt: string;
    retiredAt?: string;
  }>;
  webAuthnUi?: boolean;
}

export function buildHttpServer(app: HaaApplication, options: HttpServerOptions = {}) {
  const server = Fastify({ logger: true, bodyLimit: MAX_BODY_BYTES });

  server.setErrorHandler((error, _request, reply) => {
    const message = error instanceof Error ? error.message : 'UNKNOWN_ERROR';
    const status = message === 'UNAUTHORIZED' ? 401
      : message === 'FORBIDDEN' || message === 'SELF_APPROVAL_FORBIDDEN' ? 403
      : message.includes('NOT_FOUND') ? 404
      : message.includes('MISMATCH') || message.includes('STALE') || message.includes('EXPIRED') || message.includes('REPLAY') || message.includes('NOT_APPROVED') || message.includes('NOT_PENDING') ? 409
      : 400;
    reply.code(status).send({ error: message });
  });

  server.get('/health', async () => ({ status: 'ok' }));
  server.get('/v1/authority-key', async () => ({
    keyId: app.signer.keyId,
    algorithm: app.signer.algorithm,
    publicKeyPem: app.signer.publicKeyPem,
  }));
  server.get('/v1/authority-keys', async () => options.authorityKeys?.() ?? [{
    keyId: app.signer.keyId,
    algorithm: app.signer.algorithm,
    publicKeyPem: app.signer.publicKeyPem,
    status: 'ACTIVE' as const,
  }]);

  server.post('/v1/approval-requests', async (request) => {
    const body = parse(createRequestSchema, request.body);
    return app.createApprovalRequest({
      apiKey: apiKey(request.headers),
      action: body.action as ActionSpec,
      approverPrincipalId: body.approverPrincipalId,
      executorAudience: body.executorAudience,
      ...(body.policySnapshotHash !== undefined ? { policySnapshotHash: body.policySnapshotHash } : {}),
      ...(body.requestId !== undefined ? { requestId: body.requestId } : {}),
      ...(body.ttlMs !== undefined ? { ttlMs: body.ttlMs } : {}),
    });
  });

  server.get('/v1/approval-requests/:id', async (request) => {
    const { id } = parse(idParamsSchema, request.params);
    return app.getRequest(apiKey(request.headers), id);
  });

  server.post('/v1/authenticators', async (request) => {
    const body = parse(authenticatorSchema, request.body) as Omit<AuthenticatorRecord, 'schema' | 'status' | 'createdAt'>;
    return app.registerAuthenticator(apiKey(request.headers), body);
  });

  server.post('/v1/authenticators/:id/revoke', async (request, reply) => {
    const { id } = parse(idParamsSchema, request.params);
    app.revokeAuthenticator(apiKey(request.headers), id);
    reply.code(204).send();
  });

  server.post('/v1/webauthn/registration/options', async (request) => {
    parse(emptyObjectSchema, request.body ?? {});
    return app.beginWebAuthnRegistration(apiKey(request.headers));
  });

  server.post('/v1/webauthn/registration/verify', async (request) => {
    const body = parse(webAuthnRegistrationVerifySchema, request.body);
    return app.finishWebAuthnRegistration({
      apiKey: apiKey(request.headers),
      registrationId: body.registrationId,
      credential: body.credential as WebAuthnRegistrationCredentialJSON,
    });
  });

  server.post('/v1/webauthn/authentication/options', async (request) => {
    const body = parse(webAuthnAuthenticationOptionsSchema, request.body);
    return app.createWebAuthnApprovalOptions({
      apiKey: apiKey(request.headers),
      requestId: body.requestId,
      authenticatorId: body.authenticatorId,
      challengeDigest: body.challengeDigest,
    });
  });

  server.post('/v1/approval-requests/:id/challenges', async (request) => {
    const { id } = parse(idParamsSchema, request.params);
    const body = parse(challengeRequestSchema, request.body);
    return app.issueApprovalChallenge({ apiKey: apiKey(request.headers), requestId: id, authenticatorId: body.authenticatorId });
  });

  server.post('/v1/approval-requests/:id/reject', async (request) => {
    const { id } = parse(idParamsSchema, request.params);
    const body = parse(rejectSchema, request.body);
    return app.rejectApproval({
      apiKey: apiKey(request.headers),
      requestId: id,
      challengeDigest: body.challengeDigest,
      reason: body.reason,
    });
  });

  server.post('/v1/approval-evidence', async (request) => {
    const evidence = parse(evidenceSchema, request.body) as ApprovalEvidence;
    return app.submitEvidence({ apiKey: apiKey(request.headers), evidence });
  });

  server.post('/v1/approval-requests/:id/authorize', async (request) => {
    const { id } = parse(idParamsSchema, request.params);
    const body = parse(authorizeSchema, request.body);
    return app.authorizeAndConsume({
      apiKey: apiKey(request.headers),
      requestId: id,
      executionId: body.executionId,
      actualAction: body.actualAction as ActionSpec,
      ...(body.actualState !== undefined ? { actualState: body.actualState } : {}),
    });
  });

  server.get('/v1/approval-requests/:id/audit', async (request) => {
    const { id } = parse(idParamsSchema, request.params);
    return app.listAudit(apiKey(request.headers), id);
  });

  if (options.webAuthnUi) {
    server.get('/webauthn/approve', async (_request, reply) => {
      reply
        .header('cache-control', 'no-store')
        .header('x-frame-options', 'DENY')
        .header('content-security-policy', "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        .type('text/html; charset=utf-8')
        .send(webAuthnApprovalPage());
    });
  }

  return server;
}
