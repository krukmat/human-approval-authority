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
    status: 'RETIRED' as const,
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

test('detached verifier accepts a correctly bound grant signed by a retained authority key', () => {
  const verified = verifyFixture();
  assert.equal(verified.executionId, 'exec-1');
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
