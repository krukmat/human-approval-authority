import test from 'node:test';
import assert from 'node:assert/strict';
import {
  ActionProfileRegistry,
  assertTransition,
  canonicalize,
  challengeDigest,
  createEphemeralSigner,
  decodeChallengePayload,
  digestJson,
  issueChallenge,
  verifyChallengeAuthority,
} from '../packages/core/src/index.ts';
import type { ApprovalRequest } from '../packages/protocol/src/index.ts';

test('canonicalization is deterministic across key order', () => {
  assert.equal(canonicalize({ b: 2, a: 1 }), canonicalize({ a: 1, b: 2 }));
  assert.equal(digestJson({ b: 2, a: 1 }), digestJson({ a: 1, b: 2 }));
});

test('approval-critical action mutation changes digest', () => {
  const profiles = new ActionProfileRegistry();
  const a = { schema: 'haa.action.v1' as const, type: 'demo.action.v1', payload: { resource: 'prod', operation: 'deploy' } };
  const b = { schema: 'haa.action.v1' as const, type: 'demo.action.v1', payload: { resource: 'prod', operation: 'delete' } };
  assert.notEqual(profiles.actionDigest(a), profiles.actionDigest(b));
});

test('state machine denies invalid transition', () => {
  assert.doesNotThrow(() => assertTransition('PENDING', 'APPROVED'));
  assert.throws(() => assertTransition('APPROVED', 'APPROVED'), /ILLEGAL_TRANSITION/);
  assert.throws(() => assertTransition('CONSUMED', 'APPROVED'), /ILLEGAL_TRANSITION/);
});

test('challenge uses fresh nonce and binds exact request', () => {
  const profiles = new ActionProfileRegistry();
  const signer = createEphemeralSigner();
  const now = new Date('2026-09-13T02:00:00Z');
  const action = { schema: 'haa.action.v1' as const, type: 'demo.action.v1', payload: { resource: 'prod', operation: 'deploy' } };
  const request: ApprovalRequest = {
    schema: 'haa.request.v1', id: 'r1',
    intent: { schema: 'haa.intent.v1', requestId: 'r1', action, requesterId: 'agent', approverPrincipalId: 'human', executorAudience: 'executor', policySnapshotHash: 'sha256:policy', createdAt: now.toISOString(), expiresAt: new Date(now.getTime() + 600_000).toISOString() },
    actionDigest: profiles.actionDigest(action), intentDigest: 'sha256:intent', state: 'PENDING', createdAt: now.toISOString(), updatedAt: now.toISOString(),
  };
  const c1 = issueChallenge(request, 'auth-1', profiles, signer, now);
  const c2 = issueChallenge(request, 'auth-1', profiles, signer, now);
  const p1 = decodeChallengePayload(c1);
  const p2 = decodeChallengePayload(c2);
  assert.notEqual(p1.nonce, p2.nonce);
  assert.notEqual(challengeDigest(c1), challengeDigest(c2));
  assert.equal(p1.actionDigest, request.actionDigest);
  assert.equal(p1.displayClaims[0]?.value, 'deploy');
});

test('unknown action profile fails closed', () => {
  const profiles = new ActionProfileRegistry();
  assert.throws(() => profiles.validate({ schema: 'haa.action.v1', type: 'shell.anything.v1', payload: {} }), /UNSUPPORTED_ACTION_PROFILE/);
});

test('challenge authority signature fails if signed payload bytes are altered', () => {
  const profiles = new ActionProfileRegistry();
  const signer = createEphemeralSigner();
  const now = new Date('2026-09-13T02:00:00Z');
  const action = { schema: 'haa.action.v1' as const, type: 'demo.action.v1', payload: { resource: 'prod', operation: 'deploy' } };
  const request: ApprovalRequest = {
    schema: 'haa.request.v1', id: 'r2',
    intent: { schema: 'haa.intent.v1', requestId: 'r2', action, requesterId: 'agent', approverPrincipalId: 'human', executorAudience: 'executor', policySnapshotHash: 'sha256:policy', createdAt: now.toISOString(), expiresAt: new Date(now.getTime()+600000).toISOString() },
    actionDigest: profiles.actionDigest(action), intentDigest: 'sha256:intent', state: 'PENDING', createdAt: now.toISOString(), updatedAt: now.toISOString(),
  };
  const challenge = issueChallenge(request, 'auth-1', profiles, signer, now);
  assert.equal(verifyChallengeAuthority(challenge, signer.publicKeyPem), true);
  const raw = Buffer.from(challenge.payload, 'base64url');
  raw[raw.length - 2] ^= 1;
  const tampered = { ...challenge, payload: raw.toString('base64url') };
  assert.equal(verifyChallengeAuthority(tampered, signer.publicKeyPem), false);
});
