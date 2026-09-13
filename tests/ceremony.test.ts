import test from 'node:test';
import assert from 'node:assert/strict';
import { challengeDigest, createEphemeralSigner } from '../packages/core/src/index.ts';
import { SqliteStore } from '../packages/persistence-sqlite/src/index.ts';
import { HaaApplication } from '../apps/haa-server/src/application.ts';
import { buildHttpServer } from '../apps/haa-server/src/http.ts';
import { unknownCeremonyResult } from '../packages/sdk-ts/src/index.ts';
import type { ActionSpec } from '../packages/protocol/src/index.ts';

function fixture() {
  const store = new SqliteStore(':memory:');
  const authority = createEphemeralSigner('authority-ceremony');
  const humanKey = createEphemeralSigner('human-ceremony');
  const app = new HaaApplication({ store, authoritySigner: authority });
  app.registerClient('agent-a', 'agent-secret', ['REQUESTER']);
  app.registerClient('human-a', 'human-secret', ['APPROVER']);
  app.registerClient('human-b', 'human-b-secret', ['APPROVER']);
  app.registerClient('executor-a', 'executor-secret', ['EXECUTOR']);
  app.registerAuthenticator('human-secret', {
    id: 'auth-human-a',
    principalId: 'human-a',
    type: 'apple-secure-enclave',
    publicKeyPem: humanKey.publicKeyPem,
    signatureAlgorithm: humanKey.algorithm,
  });
  const action: ActionSpec = {
    schema: 'haa.action.v1',
    type: 'demo.action.v1',
    payload: { resource: 'ceremony-target', operation: 'change' },
    preconditions: { version: 'v1' },
  };
  return { store, app, action };
}

function requestAndChallenge(f: ReturnType<typeof fixture>, requestId = 'req-ceremony', now = new Date('2026-09-13T07:00:00Z')) {
  const request = f.app.createApprovalRequest({
    apiKey: 'agent-secret',
    action: f.action,
    approverPrincipalId: 'human-a',
    executorAudience: 'executor-a',
    requestId,
    now,
  });
  const challenge = f.app.issueApprovalChallenge({
    apiKey: 'human-secret',
    requestId,
    authenticatorId: 'auth-human-a',
    now,
  });
  return { request, challenge, digest: challengeDigest(challenge), now };
}

test('explicit approver rejection binds the active challenge and never grants execution', () => {
  const f = fixture();
  const { digest, now } = requestAndChallenge(f);
  const result = f.app.rejectApproval({
    apiKey: 'human-secret',
    requestId: 'req-ceremony',
    challengeDigest: digest,
    reason: 'USER_ESCAPE',
    now: new Date(now.getTime() + 1000),
  });

  assert.deepEqual(result, {
    outcome: 'REJECT',
    requestId: 'req-ceremony',
    state: 'REJECTED',
    reason: 'USER_ESCAPE',
  });
  assert.equal(f.app.getRequest('agent-secret', 'req-ceremony').state, 'REJECTED');
  assert.equal(f.store.getReceipt('req-ceremony'), null);
  assert.throws(() => f.app.authorizeAndConsume({
    apiKey: 'executor-secret',
    requestId: 'req-ceremony',
    executionId: 'exec-rejected',
    actualAction: f.action,
    actualState: { version: 'v1' },
  }), /REQUEST_NOT_APPROVED:REJECTED/);

  const events = f.app.listAudit('human-secret', 'req-ceremony');
  assert.deepEqual(events.map((event) => event.eventType), ['REQUESTED', 'CHALLENGE_ISSUED', 'REJECTED']);
  assert.deepEqual(events.at(-1)?.details, {
    challengeDigest: digest,
    authenticatorId: 'auth-human-a',
    reason: 'USER_ESCAPE',
    provenance: 'authenticated-approver-channel',
  });
  assert.ok(f.store.verifyAuditChain());
  f.store.close();
});

test('requester and wrong approver cannot fabricate rejection', () => {
  const f = fixture();
  const { digest } = requestAndChallenge(f);
  assert.throws(() => f.app.rejectApproval({
    apiKey: 'agent-secret', requestId: 'req-ceremony', challengeDigest: digest, reason: 'USER_ESCAPE',
  }), /FORBIDDEN/);
  assert.throws(() => f.app.rejectApproval({
    apiKey: 'human-b-secret', requestId: 'req-ceremony', challengeDigest: digest, reason: 'USER_ESCAPE',
  }), /FORBIDDEN/);
  assert.equal(f.app.getRequest('human-secret', 'req-ceremony').state, 'PENDING');
  f.store.close();
});

test('wrong challenge, expired challenge and replayed reject fail closed', () => {
  const f = fixture();
  const first = requestAndChallenge(f, 'req-1');
  const second = requestAndChallenge(f, 'req-2');

  assert.throws(() => f.app.rejectApproval({
    apiKey: 'human-secret', requestId: 'req-1', challengeDigest: second.digest, reason: 'USER_ESCAPE',
    now: new Date('2026-09-13T07:00:01Z'),
  }), /CHALLENGE_BINDING_MISMATCH/);

  assert.throws(() => f.app.rejectApproval({
    apiKey: 'human-secret', requestId: 'req-1', challengeDigest: first.digest, reason: 'USER_ESCAPE',
    now: new Date('2026-09-13T07:03:00Z'),
  }), /CHALLENGE_EXPIRED/);
  assert.equal(f.app.getRequest('human-secret', 'req-1').state, 'PENDING');

  f.app.rejectApproval({
    apiKey: 'human-secret', requestId: 'req-2', challengeDigest: second.digest, reason: 'USER_ESCAPE',
    now: new Date('2026-09-13T07:00:01Z'),
  });
  assert.throws(() => f.app.rejectApproval({
    apiKey: 'human-secret', requestId: 'req-2', challengeDigest: second.digest, reason: 'USER_ESCAPE',
  }), /REQUEST_NOT_PENDING:REJECTED/);
  f.store.close();
});

test('UNKNOWN is local and leaves a still-valid server request pending', () => {
  const f = fixture();
  requestAndChallenge(f);
  const result = unknownCeremonyResult('req-ceremony', 'WINDOW_CLOSED');
  assert.deepEqual(result, { outcome: 'UNKNOWN', requestId: 'req-ceremony', reason: 'WINDOW_CLOSED' });
  assert.equal(f.app.getRequest('human-secret', 'req-ceremony').state, 'PENDING');
  assert.deepEqual(f.app.listAudit('human-secret', 'req-ceremony').map((event) => event.eventType), ['REQUESTED', 'CHALLENGE_ISSUED']);
  f.store.close();
});

test('HTTP reject endpoint is strict and returns ceremony result', async () => {
  const f = fixture();
  const { digest } = requestAndChallenge(f);
  const server = buildHttpServer(f.app);

  const invalid = await server.inject({
    method: 'POST',
    url: '/v1/approval-requests/req-ceremony/reject',
    headers: { 'x-api-key': 'human-secret' },
    payload: { challengeDigest: digest, reason: 'USER_ESCAPE', extra: true },
  });
  assert.equal(invalid.statusCode, 400);
  assert.equal(invalid.json().error, 'INVALID_REQUEST_INPUT');

  const rejected = await server.inject({
    method: 'POST',
    url: '/v1/approval-requests/req-ceremony/reject',
    headers: { 'x-api-key': 'human-secret' },
    payload: { challengeDigest: digest, reason: 'USER_ESCAPE' },
  });
  assert.equal(rejected.statusCode, 200);
  assert.deepEqual(rejected.json(), {
    outcome: 'REJECT', requestId: 'req-ceremony', state: 'REJECTED', reason: 'USER_ESCAPE',
  });

  await server.close();
  f.store.close();
});
