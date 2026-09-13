import test from 'node:test';
import assert from 'node:assert/strict';
import {
  GenericSignedEvidenceVerifier,
  challengeDigest,
  createEphemeralSigner,
} from '../packages/core/src/index.ts';
import { SqliteStore } from '../packages/persistence-sqlite/src/index.ts';
import { HaaApplication } from '../apps/haa-server/src/application.ts';
import { buildHttpServer } from '../apps/haa-server/src/http.ts';
import type { ActionSpec, ApprovalChallengePackage } from '../packages/protocol/src/index.ts';

const action: ActionSpec = {
  schema: 'haa.action.v1',
  type: 'demo.action.v1',
  payload: { resource: 'w8-e2e', operation: 'change' },
  preconditions: { version: 'v1' },
};

function fixture() {
  const store = new SqliteStore(':memory:');
  const authority = createEphemeralSigner('w8-authority');
  const humanKey = createEphemeralSigner('w8-human');
  const app = new HaaApplication({
    store,
    authoritySigner: authority,
    evidenceVerifiers: [new GenericSignedEvidenceVerifier('test-key', 'presence')],
  });
  app.registerClient('agent-w8', 'agent-w8-secret', ['REQUESTER']);
  app.registerClient('human-w8', 'human-w8-secret', ['APPROVER']);
  app.registerClient('executor-w8', 'executor-w8-secret', ['EXECUTOR']);
  app.registerAuthenticator('human-w8-secret', {
    id: 'auth-w8',
    principalId: 'human-w8',
    type: 'test-key',
    publicKeyPem: humanKey.publicKeyPem,
    signatureAlgorithm: humanKey.algorithm,
  });
  return { store, app, humanKey, server: buildHttpServer(app) };
}

async function requestChallenge(server: ReturnType<typeof buildHttpServer>, requestId: string) {
  const request = await server.inject({
    method: 'POST',
    url: '/v1/approval-requests',
    headers: { 'x-api-key': 'agent-w8-secret' },
    payload: {
      action,
      approverPrincipalId: 'human-w8',
      executorAudience: 'executor-w8',
      requestId,
    },
  });
  assert.equal(request.statusCode, 200);

  const challengeResponse = await server.inject({
    method: 'POST',
    url: `/v1/approval-requests/${requestId}/challenges`,
    headers: { 'x-api-key': 'human-w8-secret' },
    payload: { authenticatorId: 'auth-w8' },
  });
  assert.equal(challengeResponse.statusCode, 200);
  const challenge = challengeResponse.json() as ApprovalChallengePackage;
  return { challenge, digest: challengeDigest(challenge) };
}

async function assertRejectedWithoutGrant(
  f: ReturnType<typeof fixture>,
  requestId: string,
  reason: 'USER_ESCAPE' | 'WINDOW_CLOSED' | 'TIMEOUT' | 'INTERACTION_ERROR',
) {
  const challenge = await requestChallenge(f.server, requestId);
  const rejectResponse = await f.server.inject({
    method: 'POST',
    url: `/v1/approval-requests/${requestId}/reject`,
    headers: { 'x-api-key': 'human-w8-secret' },
    payload: { challengeDigest: challenge.digest, reason },
  });
  assert.equal(rejectResponse.statusCode, 200);
  assert.equal(rejectResponse.json().outcome, 'REJECT');
  assert.equal(rejectResponse.json().state, 'REJECTED');
  assert.equal(rejectResponse.json().reason, reason);
  assert.equal(
    rejectResponse.json().assurance,
    reason === 'USER_ESCAPE' ? 'explicit-human-negative-action' : 'fail-closed-terminal',
  );

  const rejectedGrant = await f.server.inject({
    method: 'POST',
    url: `/v1/approval-requests/${requestId}/authorize`,
    headers: { 'x-api-key': 'executor-w8-secret' },
    payload: {
      executionId: `exec-${requestId}`,
      actualAction: action,
      actualState: { version: 'v1' },
    },
  });
  assert.equal(rejectedGrant.statusCode, 409);
  assert.equal(rejectedGrant.json().error, 'REQUEST_NOT_APPROVED:REJECTED');
}

test('HAA-only ceremony E2E allows only APPROVE to create execution authority', async () => {
  const f = fixture();

  const approve = await requestChallenge(f.server, 'w8-approve');
  const evidenceResponse = await f.server.inject({
    method: 'POST',
    url: '/v1/approval-evidence',
    headers: { 'x-api-key': 'human-w8-secret' },
    payload: {
      schema: 'haa.evidence.v1',
      type: 'test-key',
      authenticatorId: 'auth-w8',
      requestId: 'w8-approve',
      challengeDigest: approve.digest,
      signatureAlgorithm: f.humanKey.algorithm,
      signature: f.humanKey.sign(Buffer.from(approve.digest, 'utf8')),
    },
  });
  assert.equal(evidenceResponse.statusCode, 200);
  assert.equal(evidenceResponse.json().schema, 'haa.receipt.v1');

  const grantResponse = await f.server.inject({
    method: 'POST',
    url: '/v1/approval-requests/w8-approve/authorize',
    headers: { 'x-api-key': 'executor-w8-secret' },
    payload: {
      executionId: 'w8-exec-approve',
      actualAction: action,
      actualState: { version: 'v1' },
    },
  });
  assert.equal(grantResponse.statusCode, 200);
  assert.equal(grantResponse.json().schema, 'haa.execution-grant.v1');

  await assertRejectedWithoutGrant(f, 'w8-escape', 'USER_ESCAPE');
  await assertRejectedWithoutGrant(f, 'w8-close', 'WINDOW_CLOSED');
  await assertRejectedWithoutGrant(f, 'w8-timeout', 'TIMEOUT');
  await assertRejectedWithoutGrant(f, 'w8-error', 'INTERACTION_ERROR');

  assert.ok(f.store.verifyAuditChain());
  await f.server.close();
  f.store.close();
});

test('actual request TTL remains EXPIRED lifecycle state rather than ceremony rejection', async () => {
  const f = fixture();
  const createdAt = new Date('2026-09-13T07:00:00Z');
  f.app.createApprovalRequest({
    apiKey: 'agent-w8-secret',
    action,
    approverPrincipalId: 'human-w8',
    executorAudience: 'executor-w8',
    requestId: 'w8-expired',
    ttlMs: 1000,
    now: createdAt,
  });

  assert.throws(() => f.app.issueApprovalChallenge({
    apiKey: 'human-w8-secret',
    requestId: 'w8-expired',
    authenticatorId: 'auth-w8',
    now: new Date(createdAt.getTime() + 2000),
  }), /REQUEST_EXPIRED/);

  assert.equal(f.store.getRequest('w8-expired')?.state, 'EXPIRED');
  assert.deepEqual(f.app.listAudit('human-w8-secret', 'w8-expired').map((event) => event.eventType), ['REQUESTED', 'EXPIRED']);
  assert.equal(f.app.listAudit('human-w8-secret', 'w8-expired').at(-1)?.details?.reason, 'REQUEST_TTL');

  assert.throws(() => f.app.authorizeAndConsume({
    apiKey: 'executor-w8-secret',
    requestId: 'w8-expired',
    executionId: 'w8-exec-expired',
    actualAction: action,
    actualState: { version: 'v1' },
    now: new Date(createdAt.getTime() + 3000),
  }), /APPROVAL_EXPIRED/);
  assert.ok(f.store.verifyAuditChain());

  await f.server.close();
  f.store.close();
});
