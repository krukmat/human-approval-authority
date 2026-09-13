import test from 'node:test';
import assert from 'node:assert/strict';
import { createEphemeralSigner } from '../packages/core/src/index.ts';
import { SqliteStore } from '../packages/persistence-sqlite/src/index.ts';
import { HaaApplication } from '../apps/haa-server/src/application.ts';
import { buildHttpServer } from '../apps/haa-server/src/http.ts';

function fixture() {
  const store = new SqliteStore(':memory:');
  const app = new HaaApplication({ store, authoritySigner: createEphemeralSigner('authority-http-test') });
  app.registerClient('agent-a', 'agent-secret');
  return { store, app, server: buildHttpServer(app) };
}

test('HTTP edge rejects unknown request fields before domain execution', async () => {
  const f = fixture();
  const response = await f.server.inject({
    method: 'POST',
    url: '/v1/approval-requests',
    headers: { 'x-api-key': 'agent-secret' },
    payload: {
      action: { schema: 'haa.action.v1', type: 'demo.action.v1', payload: { operation: 'deploy' } },
      approverPrincipalId: 'human-a',
      executorAudience: 'executor-a',
      unexpected: true,
    },
  });
  assert.equal(response.statusCode, 400);
  assert.equal(response.json().error, 'INVALID_REQUEST_INPUT');
  f.store.close();
});

test('HTTP edge rejects oversized nested JSON strings', async () => {
  const f = fixture();
  const response = await f.server.inject({
    method: 'POST',
    url: '/v1/approval-requests',
    headers: { 'x-api-key': 'agent-secret' },
    payload: {
      action: { schema: 'haa.action.v1', type: 'demo.action.v1', payload: { value: 'x'.repeat(5000) } },
      approverPrincipalId: 'human-a',
      executorAudience: 'executor-a',
    },
  });
  assert.equal(response.statusCode, 400);
  assert.equal(response.json().error, 'INVALID_REQUEST_INPUT');
  f.store.close();
});

test('HTTP edge accepts a bounded valid approval request', async () => {
  const f = fixture();
  const response = await f.server.inject({
    method: 'POST',
    url: '/v1/approval-requests',
    headers: { 'x-api-key': 'agent-secret' },
    payload: {
      action: { schema: 'haa.action.v1', type: 'demo.action.v1', payload: { resource: 'production-service', operation: 'deploy' } },
      approverPrincipalId: 'human-a',
      executorAudience: 'executor-a',
      requestId: 'req-http-1',
    },
  });
  assert.equal(response.statusCode, 200);
  assert.equal(response.json().id, 'req-http-1');
  f.store.close();
});
