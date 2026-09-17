import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash, generateKeyPairSync, randomBytes, sign } from 'node:crypto';
import { createEphemeralSigner, challengeDigest } from '../packages/core/src/index.ts';
import { SqliteStore } from '../packages/persistence-sqlite/src/index.ts';
import { HaaApplication } from '../apps/haa-server/src/application.ts';
import { encodeWebAuthnEvidenceProof } from '../packages/webauthn/src/index.ts';

const rpId = 'localhost';
const origin = 'http://localhost:8795';

function cborHead(major: number, value: number): Buffer {
  if (value < 24) return Buffer.from([(major << 5) | value]);
  if (value < 256) return Buffer.from([(major << 5) | 24, value]);
  if (value < 65536) {
    const out = Buffer.alloc(3);
    out[0] = (major << 5) | 25;
    out.writeUInt16BE(value, 1);
    return out;
  }
  throw new Error('test CBOR value too large');
}

function cbor(value: unknown): Buffer {
  if (typeof value === 'number') return value >= 0 ? cborHead(0, value) : cborHead(1, -1 - value);
  if (typeof value === 'string') {
    const data = Buffer.from(value, 'utf8');
    return Buffer.concat([cborHead(3, data.length), data]);
  }
  if (Buffer.isBuffer(value)) return Buffer.concat([cborHead(2, value.length), value]);
  if (value instanceof Map) {
    const entries = [...value.entries()];
    return Buffer.concat([cborHead(5, entries.length), ...entries.flatMap(([key, item]) => [cbor(key), cbor(item)])]);
  }
  throw new Error('unsupported test CBOR');
}

function b64url(value: Buffer | string): string {
  return Buffer.from(value).toString('base64url');
}

function fixture() {
  const store = new SqliteStore(':memory:');
  const app = new HaaApplication({
    store,
    authoritySigner: createEphemeralSigner('authority-webauthn'),
    webAuthn: { rpId, origin, rpName: 'HAA Test' },
  });
  app.registerClient('agent-a', 'agent-secret', ['REQUESTER']);
  app.registerClient('human-a', 'human-secret', ['APPROVER']);
  app.registerClient('executor-a', 'executor-secret', ['EXECUTOR']);
  const keyPair = generateKeyPairSync('ec', { namedCurve: 'prime256v1' });
  const jwk = keyPair.publicKey.export({ format: 'jwk' });
  const credentialId = randomBytes(32);
  return { store, app, keyPair, jwk, credentialId };
}

function registrationCredential(f: ReturnType<typeof fixture>, challenge: string, options: { origin?: string; uv?: boolean } = {}) {
  const clientDataJSON = Buffer.from(JSON.stringify({
    type: 'webauthn.create',
    challenge,
    origin: options.origin ?? origin,
    crossOrigin: false,
  }));
  const x = Buffer.from(f.jwk.x!, 'base64url');
  const y = Buffer.from(f.jwk.y!, 'base64url');
  const cose = new Map<unknown, unknown>([[1, 2], [3, -7], [-1, 1], [-2, x], [-3, y]]);
  const flags = 0x01 | (options.uv === false ? 0 : 0x04) | 0x40;
  const header = Buffer.alloc(37);
  createHash('sha256').update(rpId).digest().copy(header, 0);
  header[32] = flags;
  header.writeUInt32BE(0, 33);
  const length = Buffer.alloc(2);
  length.writeUInt16BE(f.credentialId.length);
  const authData = Buffer.concat([header, Buffer.alloc(16), length, f.credentialId, cbor(cose)]);
  const attestationObject = cbor(new Map<unknown, unknown>([
    ['fmt', 'none'],
    ['authData', authData],
    ['attStmt', new Map()],
  ]));
  return {
    id: b64url(f.credentialId),
    rawId: b64url(f.credentialId),
    type: 'public-key' as const,
    response: {
      clientDataJSON: b64url(clientDataJSON),
      attestationObject: b64url(attestationObject),
      transports: ['internal'],
    },
  };
}

function enroll(f: ReturnType<typeof fixture>) {
  const registration = f.app.beginWebAuthnRegistration('human-secret');
  const result = f.app.finishWebAuthnRegistration({
    apiKey: 'human-secret',
    registrationId: registration.registrationId,
    credential: registrationCredential(f, registration.publicKey.challenge),
  });
  return result.authenticator.id;
}

function assertionEvidence(args: {
  f: ReturnType<typeof fixture>;
  authenticatorId: string;
  requestId: string;
  digest: string;
  webAuthnChallenge: string;
  originOverride?: string;
  uv?: boolean;
  counter?: number;
}) {
  const clientDataJSON = Buffer.from(JSON.stringify({
    type: 'webauthn.get',
    challenge: args.webAuthnChallenge,
    origin: args.originOverride ?? origin,
    crossOrigin: false,
  }));
  const authenticatorData = Buffer.alloc(37);
  createHash('sha256').update(rpId).digest().copy(authenticatorData, 0);
  authenticatorData[32] = 0x01 | (args.uv === false ? 0 : 0x04);
  const counter = args.counter ?? 1;
  authenticatorData.writeUInt32BE(counter, 33);
  const clientHash = createHash('sha256').update(clientDataJSON).digest();
  const signature = sign('sha256', Buffer.concat([authenticatorData, clientHash]), args.f.keyPair.privateKey);
  return {
    schema: 'haa.evidence.v1' as const,
    type: 'webauthn-v1',
    authenticatorId: args.authenticatorId,
    requestId: args.requestId,
    challengeDigest: args.digest,
    signatureAlgorithm: 'ES256' as const,
    signature: encodeWebAuthnEvidenceProof({
      schema: 'haa.webauthn-proof.v1',
      credentialId: b64url(args.f.credentialId),
      clientDataJSON: b64url(clientDataJSON),
      authenticatorData: b64url(authenticatorData),
      assertionSignature: b64url(signature),
    }),
    counter,
  };
}

function approval(f: ReturnType<typeof fixture>, authenticatorId: string, requestId: string) {
  const action = { schema: 'haa.action.v1' as const, type: 'demo.action.v1', payload: { resource: 'prod', operation: 'deploy' } };
  f.app.createApprovalRequest({
    apiKey: 'agent-secret', action, approverPrincipalId: 'human-a', executorAudience: 'executor-a', requestId,
  });
  const challenge = f.app.issueApprovalChallenge({ apiKey: 'human-secret', requestId, authenticatorId });
  const digest = challengeDigest(challenge);
  const options = f.app.createWebAuthnApprovalOptions({
    apiKey: 'human-secret', requestId, authenticatorId, challengeDigest: digest,
  });
  return { action, digest, options };
}

test('WebAuthn registration and approval produce user-verified receipt and executable grant', () => {
  const f = fixture();
  const authenticatorId = enroll(f);
  const flow = approval(f, authenticatorId, 'req-wa-1');
  const evidence = assertionEvidence({
    f, authenticatorId, requestId: 'req-wa-1', digest: flow.digest, webAuthnChallenge: flow.options.publicKey.challenge,
  });
  const receipt = f.app.submitEvidence({ apiKey: 'human-secret', evidence });
  assert.equal(receipt.humanVerificationLevel, 'user-verified');
  const grant = f.app.authorizeAndConsume({
    apiKey: 'executor-secret', requestId: 'req-wa-1', executionId: 'exec-wa-1', actualAction: flow.action,
  });
  assert.equal(grant.schema, 'haa.execution-grant.v1');
  assert.equal(f.app.getRequest('agent-secret', 'req-wa-1').state, 'CONSUMED');
  f.store.close();
});

test('WebAuthn registration requires exact origin and user verification', () => {
  const f = fixture();
  const registration = f.app.beginWebAuthnRegistration('human-secret');
  assert.throws(() => f.app.finishWebAuthnRegistration({
    apiKey: 'human-secret', registrationId: registration.registrationId,
    credential: registrationCredential(f, registration.publicKey.challenge, { origin: 'http://evil.example' }),
  }), /WEBAUTHN_ORIGIN_MISMATCH/);
  assert.throws(() => f.app.finishWebAuthnRegistration({
    apiKey: 'human-secret', registrationId: registration.registrationId,
    credential: registrationCredential(f, registration.publicKey.challenge, { uv: false }),
  }), /WEBAUTHN_USER_VERIFICATION_REQUIRED/);
  f.store.close();
});

test('WebAuthn approval fails closed on wrong origin, wrong challenge, and UV=false', () => {
  const f = fixture();
  const authenticatorId = enroll(f);
  for (const [suffix, mutate, expected] of [
    ['origin', { originOverride: 'http://evil.example' }, /WEBAUTHN_ORIGIN_MISMATCH/],
    ['challenge', { webAuthnChallenge: b64url('wrong') }, /WEBAUTHN_CHALLENGE_MISMATCH/],
    ['uv', { uv: false }, /WEBAUTHN_USER_VERIFICATION_REQUIRED/],
  ] as const) {
    const requestId = `req-wa-${suffix}`;
    const flow = approval(f, authenticatorId, requestId);
    const evidence = assertionEvidence({
      f,
      authenticatorId,
      requestId,
      digest: flow.digest,
      webAuthnChallenge: flow.options.publicKey.challenge,
      counter: 0,
      ...mutate,
    });
    assert.throws(() => f.app.submitEvidence({ apiKey: 'human-secret', evidence }), expected);
    assert.equal(f.app.getRequest('agent-secret', requestId).state, 'PENDING');
  }
  f.store.close();
});

test('WebAuthn counter regression is rejected when authenticator exposes a counter', () => {
  const f = fixture();
  const authenticatorId = enroll(f);
  const first = approval(f, authenticatorId, 'req-wa-counter-1');
  f.app.submitEvidence({
    apiKey: 'human-secret',
    evidence: assertionEvidence({
      f, authenticatorId, requestId: 'req-wa-counter-1', digest: first.digest,
      webAuthnChallenge: first.options.publicKey.challenge, counter: 4,
    }),
  });
  const second = approval(f, authenticatorId, 'req-wa-counter-2');
  assert.throws(() => f.app.submitEvidence({
    apiKey: 'human-secret',
    evidence: assertionEvidence({
      f, authenticatorId, requestId: 'req-wa-counter-2', digest: second.digest,
      webAuthnChallenge: second.options.publicKey.challenge, counter: 3,
    }),
  }), /WEBAUTHN_COUNTER_REPLAY/);
  f.store.close();
});
