import Fastify from 'fastify';
import { z } from 'zod';
import type { ActionSpec, ApprovalEvidence, AuthenticatorRecord, JsonValue } from '../../../packages/protocol/src/index.ts';
import type { HaaApplication } from './application.ts';

const MAX_BODY_BYTES = 64 * 1024;
const MAX_STRING = 4096;
const MAX_IDENTIFIER = 128;
const MAX_JSON_DEPTH = 12;
const MAX_JSON_KEYS = 128;
const MAX_JSON_ARRAY = 128;

const identifier = z.string().min(1).max(MAX_IDENTIFIER).regex(/^[A-Za-z0-9._:-]+$/);
const boundedString = z.string().max(MAX_STRING);

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
  revokedAt: z.never().optional(),
}).strict();

const challengeRequestSchema = z.object({ authenticatorId: identifier }).strict();

const evidenceSchema = z.object({
  schema: z.literal('haa.evidence.v1'),
  type: identifier,
  authenticatorId: identifier,
  requestId: identifier,
  challengeDigest: boundedString.min(1),
  signatureAlgorithm: z.enum(['Ed25519', 'ES256']),
  signature: z.string().min(1).max(16 * 1024),
  counter: z.number().int().nonnegative().optional(),
}).strict();

const authorizeSchema = z.object({
  executionId: identifier,
  actualAction: actionSpecSchema,
  actualState: jsonObject.optional(),
}).strict();

const idParamsSchema = z.object({ id: identifier }).strict();

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

export function buildHttpServer(app: HaaApplication) {
  const server = Fastify({ logger: true, bodyLimit: MAX_BODY_BYTES });

  server.setErrorHandler((error, _request, reply) => {
    const message = error instanceof Error ? error.message : 'UNKNOWN_ERROR';
    const status = message === 'UNAUTHORIZED' ? 401
      : message === 'FORBIDDEN' || message === 'SELF_APPROVAL_FORBIDDEN' ? 403
      : message.includes('NOT_FOUND') ? 404
      : message.includes('MISMATCH') || message.includes('STALE') || message.includes('EXPIRED') || message.includes('NOT_APPROVED') ? 409
      : 400;
    reply.code(status).send({ error: message });
  });

  server.get('/health', async () => ({ status: 'ok' }));
  server.get('/v1/authority-key', async () => ({
    keyId: app.signer.keyId,
    algorithm: app.signer.algorithm,
    publicKeyPem: app.signer.publicKeyPem,
  }));

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

  server.post('/v1/approval-requests/:id/challenges', async (request) => {
    const { id } = parse(idParamsSchema, request.params);
    const body = parse(challengeRequestSchema, request.body);
    return app.issueApprovalChallenge({ apiKey: apiKey(request.headers), requestId: id, authenticatorId: body.authenticatorId });
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

  return server;
}
