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
import { unknownCeremonyResult } from '../packages/sdk-ts/src/index.ts';
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

test('HAA-only ceremony E2E separates APPROVE, REJECT and UNKNOWN authority effects', async () => {
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

  const reject = await requestChallenge(f.server, 'w8-reject');
  const rejectResponse = await f.server.inject({
    method: 'POST',
    url: '/v1/approval-requests/w8-reject/reject',
    headers: { 'x-api-key': 'human-w8-secret' },
    payload: { challengeDigest: reject.digest, reason: 'USER_ESCAPE' },
  });
  assert.equal(rejectResponse.statusCode, 200);
  assert.equal(rejectResponse.json().outcome, 'REJECT');
  assert.equal(rejectResponse.json().state, 'REJECTED');

  const rejectedGrant = await f.server.inject({
    method: 'POST',
    url: '/v1/approval-requests/w8-reject/authorize',
    headers: { 'x-api-key': 'executor-w8-secret' },
    payload: {
      executionId: 'w8-exec-reject',
      actualAction: action,
      actualState: { version: 'v1' },
    },
  });
  assert.equal(rejectedGrant.statusCode, 409);
  assert.equal(rejectedGrant.json().error, 'REQUEST_NOT_APPROVED:REJECTED');

  await requestChallenge(f.server, 'w8-unknown');
  const unknown = unknownCeremonyResult('w8-unknown', 'LOCAL_TIMEOUT');
  assert.deepEqual(unknown, { outcome: 'UNKNOWN', requestId: 'w8-unknown', reason: 'LOCAL_TIMEOUT' });

  const unknownStatus = await f.server.inject({
    method: 'GET',
    url: '/v1/approval-requests/w8-unknown',
    headers: { 'x-api-key': 'human-w8-secret' },
  });
  assert.equal(unknownStatus.statusCode, 200);
  assert.equal(unknownStatus.json().state, 'PENDING');

  const unknownAudit = await f.server.inject({
    method: 'GET',
    url: '/v1/approval-requests/w8-unknown/audit',
    headers: { 'x-api-key': 'human-w8-secret' },
  });
  assert.equal(unknownAudit.statusCode, 200);
  assert.deepEqual(unknownAudit.json().map((event: { eventType: string }) => event.eventType), ['REQUESTED', 'CHALLENGE_ISSUED']);

  assert.ok(f.store.verifyAuditChain());
  await f.server.close();
  f.store.close();
});

test('actual request TTL persists EXPIRED and remains distinct from local UNKNOWN', async () => {
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

  const localOutcome = unknownCeremonyResult('w8-expired', 'LOCAL_TIMEOUT');
  assert.equal(localOutcome.outcome, 'UNKNOWN');
  assert.equal(f.store.getRequest('w8-expired')?.state, 'PENDING');

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
