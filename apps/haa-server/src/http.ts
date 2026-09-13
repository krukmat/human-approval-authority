import Fastify from 'fastify';
import type { ActionSpec, ApprovalEvidence, AuthenticatorRecord } from '../../../packages/protocol/src/index.ts';
import type { HaaApplication } from './application.ts';

function apiKey(headers: Record<string, unknown>): string {
  const value = headers['x-api-key'];
  if (typeof value !== 'string' || !value) throw new Error('UNAUTHORIZED');
  return value;
}

export function buildHttpServer(app: HaaApplication) {
  const server = Fastify({ logger: true });

  server.setErrorHandler((error, _request, reply) => {
    const message = error instanceof Error ? error.message : 'UNKNOWN_ERROR';
    const status = message === 'UNAUTHORIZED' ? 401
      : message === 'FORBIDDEN' ? 403
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
    const body = request.body as {
      action: ActionSpec;
      approverPrincipalId: string;
      executorAudience: string;
      policySnapshotHash?: string;
      requestId?: string;
      ttlMs?: number;
    };
    return app.createApprovalRequest({ apiKey: apiKey(request.headers), ...body });
  });

  server.get('/v1/approval-requests/:id', async (request) => {
    const { id } = request.params as { id: string };
    return app.getRequest(apiKey(request.headers), id);
  });

  server.post('/v1/authenticators', async (request) => {
    const body = request.body as Omit<AuthenticatorRecord, 'schema' | 'status' | 'createdAt'>;
    return app.registerAuthenticator(apiKey(request.headers), body);
  });

  server.post('/v1/authenticators/:id/revoke', async (request, reply) => {
    const { id } = request.params as { id: string };
    app.revokeAuthenticator(apiKey(request.headers), id);
    reply.code(204).send();
  });

  server.post('/v1/approval-requests/:id/challenges', async (request) => {
    const { id } = request.params as { id: string };
    const body = request.body as { authenticatorId: string };
    return app.issueApprovalChallenge({ apiKey: apiKey(request.headers), requestId: id, authenticatorId: body.authenticatorId });
  });

  server.post('/v1/approval-evidence', async (request) => {
    return app.submitEvidence({ apiKey: apiKey(request.headers), evidence: request.body as ApprovalEvidence });
  });

  server.post('/v1/approval-requests/:id/authorize', async (request) => {
    const { id } = request.params as { id: string };
    const body = request.body as { executionId: string; actualAction: ActionSpec; actualState?: Record<string, any> };
    return app.authorizeAndConsume({
      apiKey: apiKey(request.headers), requestId: id, executionId: body.executionId,
      actualAction: body.actualAction, ...(body.actualState ? { actualState: body.actualState } : {}),
    });
  });

  server.get('/v1/approval-requests/:id/audit', async (request) => {
    const { id } = request.params as { id: string };
    return app.listAudit(apiKey(request.headers), id);
  });

  return server;
}
