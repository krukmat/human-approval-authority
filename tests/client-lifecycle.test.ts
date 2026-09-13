import test from 'node:test';
import assert from 'node:assert/strict';
import { createEphemeralSigner, sha256 } from '../packages/core/src/index.ts';
import { SqliteStore } from '../packages/persistence-sqlite/src/index.ts';
import { HaaApplication } from '../apps/haa-server/src/application.ts';
import type { ActionSpec } from '../packages/protocol/src/index.ts';

const action: ActionSpec = {
  schema: 'haa.action.v1',
  type: 'demo.action.v1',
  payload: { resource: 'production-service', operation: 'deploy' },
};

test('client roles separate requester approver and executor capabilities', () => {
  const store = new SqliteStore(':memory:');
  const app = new HaaApplication({ store, authoritySigner: createEphemeralSigner('authority-client-role-test') });
  app.registerClient('agent-a', 'agent-secret', ['REQUESTER']);
  app.registerClient('human-a', 'human-secret', ['APPROVER']);
  app.registerClient('executor-a', 'executor-secret', ['EXECUTOR']);

  const request = app.createApprovalRequest({
    apiKey: 'agent-secret',
    action,
    approverPrincipalId: 'human-a',
    executorAudience: 'executor-a',
    requestId: 'role-test-request',
  });
  assert.equal(request.intent.requesterId, 'agent-a');
  assert.throws(() => app.issueApprovalChallenge({
    apiKey: 'agent-secret', requestId: request.id, authenticatorId: 'missing-auth',
  }), /FORBIDDEN/);
  assert.throws(() => app.createApprovalRequest({
    apiKey: 'human-secret', action, approverPrincipalId: 'human-b', executorAudience: 'executor-a', requestId: 'wrong-role',
  }), /FORBIDDEN/);
  assert.throws(() => app.authorizeAndConsume({
    apiKey: 'agent-secret', requestId: request.id, executionId: 'exec-role-test', actualAction: action,
  }), /FORBIDDEN/);
  store.close();
});

test('credential rotation invalidates old key and retains non-secret history metadata', () => {
  const store = new SqliteStore(':memory:');
  const oldHash = sha256('old-secret');
  const newHash = sha256('new-secret');
  store.registerClient('client-a', oldHash, ['REQUESTER'], { now: '2026-09-13T05:00:00.000Z' });
  assert.equal(store.authenticateClient(oldHash, '2026-09-13T05:00:01.000Z')?.id, 'client-a');

  const version = store.rotateClientCredential('client-a', newHash, { now: '2026-09-13T05:01:00.000Z' });
  assert.equal(version, 2);
  assert.equal(store.authenticateClient(oldHash, '2026-09-13T05:01:01.000Z'), null);
  assert.equal(store.authenticateClient(newHash, '2026-09-13T05:01:01.000Z')?.credentialVersion, 2);
  assert.deepEqual(store.listClientCredentialHistory('client-a').map((entry) => entry.status), ['RETIRED', 'ACTIVE']);
  assert.deepEqual(store.listAdminAudit('client-a').map((event) => event.eventType), ['CLIENT_PROVISIONED', 'CLIENT_CREDENTIAL_ROTATED']);
  store.close();
});

test('expired and disabled client credentials fail authentication', () => {
  const store = new SqliteStore(':memory:');
  const expiredHash = sha256('expired-secret');
  store.registerClient('expired-client', expiredHash, ['REQUESTER'], {
    now: '2026-09-13T05:00:00.000Z',
    expiresAt: '2026-09-13T05:05:00.000Z',
  });
  assert.equal(store.authenticateClient(expiredHash, '2026-09-13T05:04:59.000Z')?.id, 'expired-client');
  assert.equal(store.authenticateClient(expiredHash, '2026-09-13T05:05:00.000Z'), null);

  const disabledHash = sha256('disabled-secret');
  store.registerClient('disabled-client', disabledHash, ['EXECUTOR'], { now: '2026-09-13T05:00:00.000Z' });
  assert.equal(store.disableClient('disabled-client', { now: '2026-09-13T05:02:00.000Z' }), true);
  assert.equal(store.authenticateClient(disabledHash, '2026-09-13T05:02:01.000Z'), null);
  assert.equal(store.listClientCredentialHistory('disabled-client').at(-1)?.status, 'REVOKED');
  assert.equal(store.listAdminAudit('disabled-client').at(-1)?.eventType, 'CLIENT_DISABLED');
  store.close();
});
