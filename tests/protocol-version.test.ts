import assert from 'node:assert/strict';
import test from 'node:test';
import { HAA_PROTOCOL_RELEASE, HAA_PROTOCOL_VERSION, HAA_V1_SCHEMAS } from '../packages/protocol/src/index.ts';

test('protocol v1 version metadata is frozen', () => {
  assert.equal(HAA_PROTOCOL_VERSION, 1);
  assert.equal(HAA_PROTOCOL_RELEASE, '1.0.0');
  assert.deepEqual(HAA_V1_SCHEMAS, {
    action: 'haa.action.v1',
    intent: 'haa.intent.v1',
    request: 'haa.request.v1',
    challengePayload: 'haa.challenge-payload.v1',
    challenge: 'haa.challenge.v1',
    evidence: 'haa.evidence.v1',
    verifiedEvidence: 'haa.verified-evidence.v1',
    receipt: 'haa.receipt.v1',
    executionGrant: 'haa.execution-grant.v1',
    authenticator: 'haa.authenticator.v1',
    audit: 'haa.audit.v1',
  });
});
