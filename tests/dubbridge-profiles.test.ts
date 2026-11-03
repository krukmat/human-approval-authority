import test from 'node:test';
import assert from 'node:assert/strict';
import { ActionProfileRegistry } from '../packages/core/src/index.ts';
import type { ActionSpec } from '../packages/protocol/src/index.ts';

function taskStartAction(): ActionSpec {
  return {
    schema: 'haa.action.v1',
    type: 'dubbridge.task.start.v1',
    payload: {
      repository: 'krukmat/dubbridge',
      planId: 'haa-hitl-integration',
      taskId: 'W2.T2a',
      sessionId: 'session-123',
      branch: 'feature/haa-hitl-w1-contract-policy',
      baseCommitSha: 'a'.repeat(40),
      allowedPaths: ['docs/**', 'scripts/haa/**'],
      scopeDigest: 'sha256:scope',
      capabilities: ['commit', 'edit', 'review', 'test'],
      leaseTtlSeconds: 1800,
    },
  };
}

function planCloseAction(): ActionSpec {
  return {
    schema: 'haa.action.v1',
    type: 'dubbridge.plan.close.v1',
    payload: {
      repository: 'krukmat/dubbridge',
      planId: 'haa-hitl-integration',
      branch: 'feature/haa-hitl-w1-contract-policy',
      finalCommitSha: 'b'.repeat(40),
      closureManifestDigest: 'sha256:closure',
      requiredTaskCount: 8,
      completedTaskCount: 8,
      acceptedExceptionCount: 1,
      validationStatus: 'PASS',
      evidenceDigest: 'sha256:evidence',
    },
  };
}

test('dubbridge task-start profile displays all authority-bearing scope and accepts exact current state', () => {
  const profiles = new ActionProfileRegistry();
  const action = taskStartAction();

  assert.doesNotThrow(() => profiles.validate(action));
  const labels = Object.fromEntries(
    profiles.displayClaims(action).map((claim) => [claim.label, claim.value]),
  );
  assert.equal(labels.ACTION, 'START DUBBRIDGE TASK');
  assert.equal(labels.PLAN, 'haa-hitl-integration');
  assert.equal(labels.TASK, 'W2.T2a');
  assert.equal(labels['ALLOWED PATHS'], 'docs/**, scripts/haa/**');
  assert.equal(labels.CAPABILITIES, 'commit, edit, review, test');
  assert.equal(labels['LEASE TTL'], '1800s');
  assert.equal(labels['SCOPE DIGEST'], 'sha256:scope');

  assert.doesNotThrow(() => profiles.validatePreconditions(action, {
    repository: 'krukmat/dubbridge',
    planId: 'haa-hitl-integration',
    taskId: 'W2.T2a',
    sessionId: 'session-123',
    branch: 'feature/haa-hitl-w1-contract-policy',
    currentHead: 'a'.repeat(40),
    scopeDigest: 'sha256:scope',
  }));
});

test('dubbridge task-start profile fails closed on unsafe scope, capability, ttl, or stale state', () => {
  const profiles = new ActionProfileRegistry();
  const base = taskStartAction();

  for (const action of [
    { ...base, payload: { ...base.payload, allowedPaths: ['../escape'] } },
    { ...base, payload: { ...base.payload, allowedPaths: ['scripts/**', 'docs/**'] } },
    { ...base, payload: { ...base.payload, capabilities: ['deploy'] } },
    { ...base, payload: { ...base.payload, leaseTtlSeconds: 1801 } },
    { ...base, payload: { ...base.payload, hiddenPrivilege: true } },
  ] as ActionSpec[]) {
    assert.throws(() => profiles.validate(action));
  }

  assert.throws(() => profiles.validatePreconditions(base, {
    repository: 'krukmat/dubbridge',
    planId: 'haa-hitl-integration',
    taskId: 'W2.T2a',
    sessionId: 'session-123',
    branch: 'feature/haa-hitl-w1-contract-policy',
    currentHead: 'c'.repeat(40),
    scopeDigest: 'sha256:scope',
  }), /STALE_APPROVAL/);
});

test('dubbridge plan-close profile binds the exact ready-to-close state', () => {
  const profiles = new ActionProfileRegistry();
  const action = planCloseAction();

  assert.doesNotThrow(() => profiles.validate(action));
  const labels = Object.fromEntries(
    profiles.displayClaims(action).map((claim) => [claim.label, claim.value]),
  );
  assert.equal(labels.ACTION, 'CLOSE DUBBRIDGE PLAN');
  assert.equal(labels['FINAL SHA'], 'b'.repeat(40));
  assert.equal(labels['COMPLETED TASKS'], '8/8');
  assert.equal(labels['ACCEPTED EXCEPTIONS'], '1');
  assert.equal(labels.VALIDATION, 'PASS');

  assert.doesNotThrow(() => profiles.validatePreconditions(action, {
    workflowState: 'PLAN_READY_FOR_APPROVAL',
    repository: 'krukmat/dubbridge',
    planId: 'haa-hitl-integration',
    branch: 'feature/haa-hitl-w1-contract-policy',
    finalCommitSha: 'b'.repeat(40),
    closureManifestDigest: 'sha256:closure',
    requiredTaskCount: 8,
    completedTaskCount: 8,
    acceptedExceptionCount: 1,
    validationStatus: 'PASS',
    evidenceDigest: 'sha256:evidence',
  }));
});

test('dubbridge plan-close profile rejects incomplete, failed, hidden, or stale closure state', () => {
  const profiles = new ActionProfileRegistry();
  const base = planCloseAction();

  for (const action of [
    { ...base, payload: { ...base.payload, validationStatus: 'FAIL' } },
    { ...base, payload: { ...base.payload, completedTaskCount: 7 } },
    { ...base, payload: { ...base.payload, hiddenOverride: true } },
  ] as ActionSpec[]) {
    assert.throws(() => profiles.validate(action));
  }

  assert.throws(() => profiles.validatePreconditions(base, {
    workflowState: 'ACTIVE',
    repository: 'krukmat/dubbridge',
    planId: 'haa-hitl-integration',
    branch: 'feature/haa-hitl-w1-contract-policy',
    finalCommitSha: 'b'.repeat(40),
    closureManifestDigest: 'sha256:closure',
    requiredTaskCount: 8,
    completedTaskCount: 8,
    acceptedExceptionCount: 1,
    validationStatus: 'PASS',
    evidenceDigest: 'sha256:evidence',
  }), /STALE_APPROVAL/);

  assert.throws(() => profiles.validatePreconditions(base, {
    workflowState: 'PLAN_READY_FOR_APPROVAL',
    repository: 'krukmat/dubbridge',
    planId: 'haa-hitl-integration',
    branch: 'feature/haa-hitl-w1-contract-policy',
    finalCommitSha: 'b'.repeat(40),
    closureManifestDigest: 'sha256:changed',
    requiredTaskCount: 8,
    completedTaskCount: 8,
    acceptedExceptionCount: 1,
    validationStatus: 'PASS',
    evidenceDigest: 'sha256:evidence',
  }), /STALE_APPROVAL/);
});
