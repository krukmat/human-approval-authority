import test from 'node:test';
import assert from 'node:assert/strict';
import { createEphemeralSigner, challengeDigest } from '../packages/core/src/index.ts';
import { SqliteStore } from '../packages/persistence-sqlite/src/index.ts';
import { HaaApplication } from '../apps/haa-server/src/application.ts';
import type { ActionSpec, ApprovalEvidence } from '../packages/protocol/src/index.ts';

test('same executionId returns the original grant after resource state changed', () => {
  const store = new SqliteStore(':memory:');
  const authority = createEphemeralSigner('authority-idempotency');
  const humanKey = createEphemeralSigner('human-idempotency');
  const app = new HaaApplication({ store, authoritySigner: authority });
  app.registerClient('agent', 'agent-secret');
  app.registerClient('human', 'human-secret');
  app.registerClient('executor', 'executor-secret');
  app.registerAuthenticator('human-secret', {
    id: 'auth-human', principalId: 'human', type: 'test-key', publicKeyPem: humanKey.publicKeyPem, signatureAlgorithm: humanKey.algorithm,
  });

  const now = new Date('2026-09-13T03:00:00Z');
  const action: ActionSpec = {
    schema: 'haa.action.v1', type: 'demo.action.v1', payload: { resource: 'service', operation: 'deploy' }, preconditions: { version: 'v1' },
  };
  const request = app.createApprovalRequest({
    apiKey: 'agent-secret', action, approverPrincipalId: 'human', executorAudience: 'executor', requestId: 'req-idempotency', now,
  });
  const challenge = app.issueApprovalChallenge({ apiKey: 'human-secret', requestId: request.id, authenticatorId: 'auth-human', now });
  const digest = challengeDigest(challenge);
  const evidence: ApprovalEvidence = {
    schema: 'haa.evidence.v1', type: 'test-key', authenticatorId: 'auth-human', requestId: request.id,
    challengeDigest: digest, signatureAlgorithm: humanKey.algorithm, signature: humanKey.sign(Buffer.from(digest, 'utf8')),
  };
  app.submitEvidence({ apiKey: 'human-secret', evidence, now: new Date(now.getTime() + 1000) });

  const first = app.authorizeAndConsume({
    apiKey: 'executor-secret', requestId: request.id, executionId: 'exec-1', actualAction: action,
    actualState: { version: 'v1' }, now: new Date(now.getTime() + 2000),
  });
  const retry = app.authorizeAndConsume({
    apiKey: 'executor-secret', requestId: request.id, executionId: 'exec-1', actualAction: action,
    actualState: { version: 'executed:exec-1' }, now: new Date(now.getTime() + 3000),
  });

  assert.equal(retry.signature, first.signature);
  assert.equal(app.listAudit('agent-secret', request.id).filter((event) => event.eventType === 'CONSUMED').length, 1);
  store.close();
});
