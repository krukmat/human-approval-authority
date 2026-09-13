import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  GenericSignedEvidenceVerifier,
  challengeDigest,
  createEphemeralSigner,
  verifySignature,
} from '../packages/core/src/index.ts';
import { SqliteStore } from '../packages/persistence-sqlite/src/index.ts';
import { HaaApplication } from '../apps/haa-server/src/application.ts';
import {
  loadOrCreateAuthorityKeyRing,
  rotateAuthorityKey,
} from '../apps/haa-server/src/authority.ts';
import type { ActionSpec, ApprovalEvidence } from '../packages/protocol/src/index.ts';

function tempKeyPaths() {
  const dir = mkdtempSync(join(tmpdir(), 'haa-keyring-'));
  return {
    dir,
    keyFile: join(dir, 'authority-key.pem'),
    keyRingFile: join(dir, 'authority-keyring.json'),
  };
}

test('authority rotation keeps retired public keys verifiable and activates only the new key', () => {
  const paths = tempKeyPaths();
  try {
    const first = loadOrCreateAuthorityKeyRing({
      keyId: 'authority-k1',
      keyFile: paths.keyFile,
      keyRingFile: paths.keyRingFile,
      now: new Date('2026-09-13T05:00:00.000Z'),
    });
    const data = Buffer.from('historical-signed-object', 'utf8');
    const signature = first.signer.sign(data);

    const second = rotateAuthorityKey({
      nextKeyId: 'authority-k2',
      keyFile: paths.keyFile,
      keyRingFile: paths.keyRingFile,
      now: new Date('2026-09-13T05:01:00.000Z'),
    });

    assert.equal(second.signer.keyId, 'authority-k2');
    assert.equal(second.resolve('authority-k2')?.status, 'ACTIVE');
    const retired = second.resolve('authority-k1');
    assert.equal(retired?.status, 'RETIRED');
    assert.equal(retired?.retiredAt, '2026-09-13T05:01:00.000Z');
    assert.equal(retired ? verifySignature(retired.algorithm, retired.publicKeyPem, data, signature) : false, true);

    const reloaded = loadOrCreateAuthorityKeyRing({ keyFile: paths.keyFile, keyRingFile: paths.keyRingFile });
    assert.equal(reloaded.signer.keyId, 'authority-k2');
    assert.equal(reloaded.resolve('authority-k1')?.status, 'RETIRED');
  } finally {
    rmSync(paths.dir, { recursive: true, force: true });
  }
});

test('challenge issued before rotation can be verified through the retired authority key', () => {
  const paths = tempKeyPaths();
  const store = new SqliteStore(':memory:');
  try {
    const firstRing = loadOrCreateAuthorityKeyRing({
      keyId: 'authority-k1',
      keyFile: paths.keyFile,
      keyRingFile: paths.keyRingFile,
      now: new Date('2026-09-13T05:00:00.000Z'),
    });
    const humanKey = createEphemeralSigner('human-key');
    const verifier = new GenericSignedEvidenceVerifier('test-key', 'presence');
    const beforeRotation = new HaaApplication({
      store,
      authoritySigner: firstRing.signer,
      authorityKeyResolver: (keyId) => {
        const key = firstRing.resolve(keyId);
        return key ? { algorithm: key.algorithm, publicKeyPem: key.publicKeyPem } : null;
      },
      evidenceVerifiers: [verifier],
    });
    beforeRotation.registerClient('agent-a', 'agent-secret', ['REQUESTER']);
    beforeRotation.registerClient('human-a', 'human-secret', ['APPROVER']);
    beforeRotation.registerClient('executor-a', 'executor-secret', ['EXECUTOR']);
    beforeRotation.registerAuthenticator('human-secret', {
      id: 'auth-human-a',
      principalId: 'human-a',
      type: 'test-key',
      publicKeyPem: humanKey.publicKeyPem,
      signatureAlgorithm: humanKey.algorithm,
    });
    const action: ActionSpec = {
      schema: 'haa.action.v1',
      type: 'demo.action.v1',
      payload: { resource: 'production-service', operation: 'deploy' },
    };
    const request = beforeRotation.createApprovalRequest({
      apiKey: 'agent-secret',
      action,
      approverPrincipalId: 'human-a',
      executorAudience: 'executor-a',
      requestId: 'rotation-request',
      now: new Date('2026-09-13T05:00:00.000Z'),
    });
    const challenge = beforeRotation.issueApprovalChallenge({
      apiKey: 'human-secret',
      requestId: request.id,
      authenticatorId: 'auth-human-a',
      now: new Date('2026-09-13T05:00:01.000Z'),
    });
    assert.equal(challenge.authorityKeyId, 'authority-k1');

    const secondRing = rotateAuthorityKey({
      nextKeyId: 'authority-k2',
      keyFile: paths.keyFile,
      keyRingFile: paths.keyRingFile,
      now: new Date('2026-09-13T05:00:02.000Z'),
    });
    const afterRotation = new HaaApplication({
      store,
      authoritySigner: secondRing.signer,
      authorityKeyResolver: (keyId) => {
        const key = secondRing.resolve(keyId);
        return key ? { algorithm: key.algorithm, publicKeyPem: key.publicKeyPem } : null;
      },
      evidenceVerifiers: [verifier],
    });
    const digest = challengeDigest(challenge);
    const evidence: ApprovalEvidence = {
      schema: 'haa.evidence.v1',
      type: 'test-key',
      authenticatorId: 'auth-human-a',
      requestId: request.id,
      challengeDigest: digest,
      signatureAlgorithm: humanKey.algorithm,
      signature: humanKey.sign(Buffer.from(digest, 'utf8')),
    };
    const receipt = afterRotation.submitEvidence({
      apiKey: 'human-secret',
      evidence,
      now: new Date('2026-09-13T05:00:03.000Z'),
    });
    assert.equal(receipt.authorityKeyId, 'authority-k2');
    assert.equal(afterRotation.getRequest('human-secret', request.id).state, 'APPROVED');
  } finally {
    store.close();
    rmSync(paths.dir, { recursive: true, force: true });
  }
});
