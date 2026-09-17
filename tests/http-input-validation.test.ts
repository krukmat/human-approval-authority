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

function webAuthnFixture() {
  const store = new SqliteStore(':memory:');
  const app = new HaaApplication({
    store,
    authoritySigner: createEphemeralSigner('authority-webauthn-http-test'),
    webAuthn: { rpId: 'localhost', origin: 'http://localhost:8795', rpName: 'HAA HTTP Test' },
  });
  app.registerClient('human-a', 'human-secret', ['APPROVER']);
  return { store, app, server: buildHttpServer(app, { webAuthnUi: true }) };
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

test('WebAuthn registration-options endpoint rejects unknown fields before ceremony creation', async () => {
  const f = webAuthnFixture();
  const response = await f.server.inject({
    method: 'POST',
    url: '/v1/webauthn/registration/options',
    headers: { 'x-api-key': 'human-secret' },
    payload: { unexpected: true },
  });
  assert.equal(response.statusCode, 400);
  assert.equal(response.json().error, 'INVALID_REQUEST_INPUT');
  f.store.close();
});

test('WebAuthn registration-verification endpoint rejects malformed and oversized credential fields', async () => {
  const f = webAuthnFixture();
  const response = await f.server.inject({
    method: 'POST',
    url: '/v1/webauthn/registration/verify',
    headers: { 'x-api-key': 'human-secret' },
    payload: {
      registrationId: 'registration-1',
      credential: {
        id: 'not+base64url',
        rawId: 'a',
        type: 'public-key',
        response: {
          clientDataJSON: 'a'.repeat(49 * 1024),
          attestationObject: 'a',
          transports: ['internal'],
        },
      },
    },
  });
  assert.equal(response.statusCode, 400);
  assert.equal(response.json().error, 'INVALID_REQUEST_INPUT');
  f.store.close();
});

test('WebAuthn authentication-options endpoint enforces strict bounded envelope', async () => {
  const f = webAuthnFixture();
  const response = await f.server.inject({
    method: 'POST',
    url: '/v1/webauthn/authentication/options',
    headers: { 'x-api-key': 'human-secret' },
    payload: {
      requestId: 'req-1',
      authenticatorId: 'auth-1',
      challengeDigest: 'sha256:test',
      unexpected: 'field',
    },
  });
  assert.equal(response.statusCode, 400);
  assert.equal(response.json().error, 'INVALID_REQUEST_INPUT');
  f.store.close();
});

test('WebAuthn approval UI is no-store and frame-denied when explicitly enabled', async () => {
  const f = webAuthnFixture();
  const response = await f.server.inject({ method: 'GET', url: '/webauthn/approve?requestId=req-1' });
  assert.equal(response.statusCode, 200);
  assert.equal(response.headers['cache-control'], 'no-store');
  assert.equal(response.headers['x-frame-options'], 'DENY');
  assert.match(String(response.headers['content-security-policy']), /frame-ancestors 'none'/);
  assert.match(response.body, /not a trusted native display/);
  f.store.close();
});
