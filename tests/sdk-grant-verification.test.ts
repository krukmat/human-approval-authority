import test from 'node:test';
import assert from 'node:assert/strict';
import { createEphemeralP256Signer, createExecutionGrant } from '../packages/core/src/index.ts';
import {
  HaaGrantVerificationError,
  verifyExecutionGrant,
} from '../packages/sdk-ts/src/index.ts';

function fixture() {
  const signer = createEphemeralP256Signer('authority-k1');
  const now = new Date('2026-09-13T06:00:00.000Z');
  const grant = createExecutionGrant({
    requestId: 'req-1',
    executionId: 'exec-1',
    actionDigest: 'sha256:action',
    executorAudience: 'executor-a',
    signer,
    now,
    ttlMs: 30_000,
  });
  const authorityKeys = [{
    keyId: signer.keyId,
    algorithm: signer.algorithm,
    publicKeyPem: signer.publicKeyPem,
    status: 'ACTIVE' as const,
    createdAt: new Date('2026-09-13T05:00:00.000Z').toISOString(),
  }];
  return { signer, grant, authorityKeys, now };
}

function verifyFixture(overrides: Partial<Parameters<typeof verifyExecutionGrant>[0]> = {}) {
  const f = fixture();
  return verifyExecutionGrant({
    grant: f.grant,
    authorityKeys: f.authorityKeys,
    expectedRequestId: 'req-1',
    expectedExecutionId: 'exec-1',
    expectedActionDigest: 'sha256:action',
    expectedExecutorAudience: 'executor-a',
    now: new Date('2026-09-13T06:00:10.000Z'),
    ...overrides,
  });
}

test('detached verifier accepts a correctly bound grant signed by the active authority key', () => {
  const verified = verifyFixture();
  assert.equal(verified.executionId, 'exec-1');
});

test('detached verifier rejects RETIRED authority keys for live execution grants', () => {
  const f = fixture();
  const retiredKeys = [{
    ...f.authorityKeys[0]!,
    status: 'RETIRED' as const,
    retiredAt: '2026-09-13T05:59:59.000Z',
  }];
  assert.throws(() => verifyFixture({ authorityKeys: retiredKeys }), (error: unknown) =>
    error instanceof HaaGrantVerificationError && error.code === 'AUTHORITY_KEY_NOT_ACTIVE');

  const forgedAfterRetirement = createExecutionGrant({
    requestId: 'req-1',
    executionId: 'exec-forged',
    actionDigest: 'sha256:action',
    executorAudience: 'executor-a',
    signer: f.signer,
    now: new Date('2026-09-13T06:01:00.000Z'),
    ttlMs: 30_000,
  });
  assert.throws(() => verifyExecutionGrant({
    grant: forgedAfterRetirement,
    authorityKeys: retiredKeys,
    expectedRequestId: 'req-1',
    expectedExecutionId: 'exec-forged',
    expectedActionDigest: 'sha256:action',
    expectedExecutorAudience: 'executor-a',
    now: new Date('2026-09-13T06:01:01.000Z'),
  }), /AUTHORITY_KEY_NOT_ACTIVE/);
});

test('detached verifier rejects signature and binding mutations', () => {
  const f = fixture();
  assert.throws(() => verifyExecutionGrant({
    grant: { ...f.grant, actionDigest: 'sha256:changed' },
    authorityKeys: f.authorityKeys,
    expectedRequestId: 'req-1',
    expectedActionDigest: 'sha256:changed',
    expectedExecutorAudience: 'executor-a',
    now: new Date('2026-09-13T06:00:10.000Z'),
  }), (error: unknown) => error instanceof HaaGrantVerificationError && error.code === 'INVALID_GRANT_SIGNATURE');

  assert.throws(() => verifyFixture({ expectedExecutorAudience: 'executor-b' }), /EXECUTOR_AUDIENCE_MISMATCH/);
  assert.throws(() => verifyFixture({ expectedRequestId: 'req-2' }), /REQUEST_ID_MISMATCH/);
  assert.throws(() => verifyFixture({ expectedExecutionId: 'exec-2' }), /EXECUTION_ID_MISMATCH/);
  assert.throws(() => verifyFixture({ expectedActionDigest: 'sha256:other' }), /ACTION_DIGEST_MISMATCH/);
});

test('detached verifier enforces execution-grant time policy', () => {
  const f = fixture();
  const longLived = createExecutionGrant({
    requestId: 'req-1', executionId: 'exec-long', actionDigest: 'sha256:action', executorAudience: 'executor-a',
    signer: f.signer, now: f.now, ttlMs: 60_000,
  });
  assert.throws(() => verifyExecutionGrant({
    grant: longLived,
    authorityKeys: f.authorityKeys,
    expectedRequestId: 'req-1', expectedExecutionId: 'exec-long', expectedActionDigest: 'sha256:action', expectedExecutorAudience: 'executor-a',
    now: new Date('2026-09-13T06:00:01.000Z'),
  }), /GRANT_TTL_EXCEEDS_POLICY/);

  const future = createExecutionGrant({
    requestId: 'req-1', executionId: 'exec-future', actionDigest: 'sha256:action', executorAudience: 'executor-a',
    signer: f.signer, now: new Date('2026-09-13T06:01:00.000Z'), ttlMs: 30_000,
  });
  assert.throws(() => verifyExecutionGrant({
    grant: future,
    authorityKeys: f.authorityKeys,
    expectedRequestId: 'req-1', expectedExecutionId: 'exec-future', expectedActionDigest: 'sha256:action', expectedExecutorAudience: 'executor-a',
    now: new Date('2026-09-13T06:00:00.000Z'),
  }), /GRANT_ISSUED_IN_FUTURE/);

  const beforeKey = createExecutionGrant({
    requestId: 'req-1', executionId: 'exec-before-key', actionDigest: 'sha256:action', executorAudience: 'executor-a',
    signer: f.signer, now: new Date('2026-09-13T04:00:00.000Z'), ttlMs: 30_000,
  });
  assert.throws(() => verifyExecutionGrant({
    grant: beforeKey,
    authorityKeys: f.authorityKeys,
    expectedRequestId: 'req-1', expectedExecutionId: 'exec-before-key', expectedActionDigest: 'sha256:action', expectedExecutorAudience: 'executor-a',
    now: new Date('2026-09-13T04:00:01.000Z'),
  }), /GRANT_ISSUED_BEFORE_KEY_ACTIVE/);
});

test('detached verifier fails closed for unknown keys, algorithm mismatch, expiry and extra fields', () => {
  const f = fixture();
  assert.throws(() => verifyFixture({ authorityKeys: [] }), /UNKNOWN_AUTHORITY_KEY/);
  assert.throws(() => verifyFixture({
    authorityKeys: [{ ...f.authorityKeys[0]!, algorithm: 'Ed25519' }],
  }), /AUTHORITY_ALGORITHM_MISMATCH/);
  assert.throws(() => verifyFixture({ now: new Date('2026-09-13T06:00:30.000Z') }), /GRANT_EXPIRED/);

  const withExtra = { ...f.grant, untrusted: true } as typeof f.grant;
  assert.throws(() => verifyFixture({ grant: withExtra }), /INVALID_GRANT_SHAPE/);
});
