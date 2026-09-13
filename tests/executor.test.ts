import test from 'node:test';
import assert from 'node:assert/strict';
import { challengeDigest, createEphemeralSigner, GenericSignedEvidenceVerifier } from '../packages/core/src/index.ts';
import { SqliteStore } from '../packages/persistence-sqlite/src/index.ts';
import { HaaApplication } from '../apps/haa-server/src/application.ts';
import { ReferenceExecutor, ReferenceResource } from '../apps/haa-server/src/reference-executor.ts';
import type { ActionSpec, ApprovalEvidence } from '../packages/protocol/src/index.ts';

test('reference executor is blocked until approval then consumes exact action', () => {
  const store = new SqliteStore(':memory:');
  const human = createEphemeralSigner('human');
  const app = new HaaApplication({
    store,
    authoritySigner: createEphemeralSigner('authority'),
    evidenceVerifiers: [new GenericSignedEvidenceVerifier('test-key', 'presence')],
  });
  app.registerClient('agent', 'a'); app.registerClient('human', 'h'); app.registerClient('executor', 'e');
  app.registerAuthenticator('h', { id: 'auth', principalId: 'human', type: 'test-key', publicKeyPem: human.publicKeyPem, signatureAlgorithm: human.algorithm });
  const action: ActionSpec = { schema: 'haa.action.v1', type: 'demo.action.v1', payload: { resource: 'svc', operation: 'deploy' }, preconditions: { version: 'v1' } };
  const now = new Date('2026-09-13T02:00:00Z');
  const request = app.createApprovalRequest({ apiKey: 'a', action, approverPrincipalId: 'human', executorAudience: 'executor', requestId: 'r', now });
  const executor = new ReferenceExecutor(app, 'e');
  const resource = new ReferenceResource('svc', 'v1');
  assert.throws(() => executor.execute({ requestId: request.id, executionId: 'x', action, resource, now }), /REQUEST_NOT_APPROVED/);
  const challenge = app.issueApprovalChallenge({ apiKey: 'h', requestId: request.id, authenticatorId: 'auth', now });
  const digest = challengeDigest(challenge);
  const evidence: ApprovalEvidence = { schema: 'haa.evidence.v1', type: 'test-key', authenticatorId: 'auth', requestId: 'r', challengeDigest: digest, signatureAlgorithm: human.algorithm, signature: human.sign(Buffer.from(digest)) };
  app.submitEvidence({ apiKey: 'h', evidence, now: new Date(now.getTime()+1000) });
  const grant = executor.execute({ requestId: request.id, executionId: 'x', action, resource, now: new Date(now.getTime()+2000) });
  assert.equal(grant.executionId, 'x');
  assert.equal(resource.lastOperation, 'deploy');
  assert.equal(resource.version, 'executed:x');
  store.close();
});
