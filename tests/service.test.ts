import test from 'node:test';
import assert from 'node:assert/strict';
import { createEphemeralSigner, challengeDigest, GenericSignedEvidenceVerifier } from '../packages/core/src/index.ts';
import { SqliteStore } from '../packages/persistence-sqlite/src/index.ts';
import { HaaApplication } from '../apps/haa-server/src/application.ts';
import type { ActionSpec, ApprovalEvidence } from '../packages/protocol/src/index.ts';

function fixture() {
  const store = new SqliteStore(':memory:');
  const authority = createEphemeralSigner('authority-1');
  const humanKey = createEphemeralSigner('human-key');
  const app = new HaaApplication({
    store,
    authoritySigner: authority,
    evidenceVerifiers: [new GenericSignedEvidenceVerifier('test-key', 'presence')],
  });
  app.registerClient('agent-a', 'agent-secret');
  app.registerClient('human-a', 'human-secret');
  app.registerClient('executor-a', 'executor-secret');
  app.registerClient('outsider-a', 'outsider-secret');
  app.registerAuthenticator('human-secret', {
    id: 'auth-human-a', principalId: 'human-a', type: 'test-key', publicKeyPem: humanKey.publicKeyPem, signatureAlgorithm: humanKey.algorithm,
  });
  const action: ActionSpec = {
    schema: 'haa.action.v1', type: 'demo.action.v1', payload: { resource: 'production-service', operation: 'deploy' }, preconditions: { version: 'v1' },
  };
  return { store, app, humanKey, action };
}

function approve(f: ReturnType<typeof fixture>) {
  const now = new Date('2026-09-13T02:00:00Z');
  const request = f.app.createApprovalRequest({
    apiKey: 'agent-secret', action: f.action, approverPrincipalId: 'human-a', executorAudience: 'executor-a', requestId: 'req-1', now,
  });
  const challenge = f.app.issueApprovalChallenge({ apiKey: 'human-secret', requestId: request.id, authenticatorId: 'auth-human-a', now });
  const digest = challengeDigest(challenge);
  const evidence: ApprovalEvidence = {
    schema: 'haa.evidence.v1', type: 'test-key', authenticatorId: 'auth-human-a', requestId: request.id,
    challengeDigest: digest, signatureAlgorithm: f.humanKey.algorithm, signature: f.humanKey.sign(Buffer.from(digest, 'utf8')),
  };
  const receipt = f.app.submitEvidence({ apiKey: 'human-secret', evidence, now: new Date(now.getTime() + 1000) });
  return { request, challenge, digest, evidence, receipt };
}

test('full approval flow produces receipt then one execution grant', () => {
  const f = fixture();
  const { request, receipt } = approve(f);
  assert.equal(receipt.requestId, request.id);
  assert.equal(f.app.getRequest('agent-secret', request.id).state, 'APPROVED');
  const grant = f.app.authorizeAndConsume({
    apiKey: 'executor-secret', requestId: request.id, executionId: 'exec-1', actualAction: f.action,
    actualState: { version: 'v1' }, now: new Date('2026-09-13T02:00:02Z'),
  });
  assert.equal(grant.schema, 'haa.execution-grant.v1');
  assert.equal(grant.executionId, 'exec-1');
  assert.equal(f.app.getRequest('executor-secret', request.id).state, 'CONSUMED');
  const events = f.app.listAudit('agent-secret', request.id).map((e) => e.eventType);
  assert.deepEqual(events, ['REQUESTED', 'CHALLENGE_ISSUED', 'APPROVED', 'CONSUMED']);
  f.store.close();
});

test('same execution id is idempotent, second id is denied', () => {
  const f = fixture();
  approve(f);
  const args = { apiKey: 'executor-secret', requestId: 'req-1', executionId: 'exec-1', actualAction: f.action, actualState: { version: 'v1' }, now: new Date('2026-09-13T02:00:02Z') };
  const first = f.app.authorizeAndConsume(args);
  const retry = f.app.authorizeAndConsume(args);
  assert.equal(first.signature, retry.signature);
  assert.throws(() => f.app.authorizeAndConsume({ ...args, executionId: 'exec-2' }), /REQUEST_NOT_APPROVED:CONSUMED/);
  f.store.close();
});

test('action mutation is denied after human approval', () => {
  const f = fixture();
  approve(f);
  const changed: ActionSpec = { ...f.action, payload: { ...f.action.payload, operation: 'delete' } };
  assert.throws(() => f.app.authorizeAndConsume({ apiKey: 'executor-secret', requestId: 'req-1', executionId: 'exec-1', actualAction: changed, actualState: { version: 'v1' }, now: new Date('2026-09-13T02:00:02Z') }), /ACTION_DIGEST_MISMATCH/);
  f.store.close();
});

test('stale precondition is denied without consuming approval', () => {
  const f = fixture();
  approve(f);
  assert.throws(() => f.app.authorizeAndConsume({ apiKey: 'executor-secret', requestId: 'req-1', executionId: 'exec-1', actualAction: f.action, actualState: { version: 'v2' }, now: new Date('2026-09-13T02:00:02Z') }), /STALE_APPROVAL/);
  assert.equal(f.app.getRequest('agent-secret', 'req-1').state, 'APPROVED');
  f.store.close();
});

test('replayed approval evidence is denied', () => {
  const f = fixture();
  const { evidence } = approve(f);
  assert.throws(() => f.app.submitEvidence({ apiKey: 'human-secret', evidence }), /(REQUEST_NOT_PENDING|CHALLENGE_NOT_ACTIVE)/);
  f.store.close();
});

test('wrong executor audience is denied', () => {
  const f = fixture();
  f.app.registerClient('other-executor', 'other-secret');
  approve(f);
  assert.throws(() => f.app.authorizeAndConsume({ apiKey: 'other-secret', requestId: 'req-1', executionId: 'exec-x', actualAction: f.action, actualState: { version: 'v1' } }), /WRONG_EXECUTOR_AUDIENCE/);
  f.store.close();
});

test('requester cannot nominate itself as human approver', () => {
  const f = fixture();
  assert.throws(() => f.app.createApprovalRequest({
    apiKey: 'agent-secret', action: f.action, approverPrincipalId: 'agent-a', executorAudience: 'executor-a', requestId: 'self-approval',
  }), /SELF_APPROVAL_FORBIDDEN/);
  f.store.close();
});

test('non-participants cannot read request or audit metadata', () => {
  const f = fixture();
  const { request } = approve(f);
  assert.throws(() => f.app.getRequest('outsider-secret', request.id), /FORBIDDEN/);
  assert.throws(() => f.app.listAudit('outsider-secret', request.id), /FORBIDDEN/);
  assert.equal(f.app.getRequest('human-secret', request.id).id, request.id);
  assert.equal(f.app.getRequest('executor-secret', request.id).id, request.id);
  f.store.close();
});
