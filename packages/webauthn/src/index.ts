import {
  createHash,
  createPublicKey,
  randomBytes,
  verify as verifyCryptoSignature,
} from 'node:crypto';
import type {
  ApprovalChallengePackage,
  ApprovalEvidence,
  AuthenticatorRecord,
  VerifiedEvidence,
} from '../../protocol/src/index.ts';
import { challengeDigest } from '../../core/src/challenge.ts';
import type { EvidenceVerifier } from '../../core/src/evidence.ts';

export const WEBAUTHN_EVIDENCE_TYPE = 'webauthn-v1' as const;
export const WEBAUTHN_PROOF_SCHEMA = 'haa.webauthn-proof.v1' as const;

const FLAG_UP = 0x01;
const FLAG_UV = 0x04;
const FLAG_AT = 0x40;
const FLAG_ED = 0x80;
const MAX_WEBAUTHN_BLOB_BYTES = 32 * 1024;
const DEFAULT_REGISTRATION_TTL_MS = 5 * 60_000;
const DEFAULT_AUTHENTICATION_TIMEOUT_MS = 2 * 60_000;

export interface WebAuthnPolicy {
  rpId: string;
  origin: string;
  rpName: string;
  registrationTtlMs?: number;
  authenticationTimeoutMs?: number;
}

export interface WebAuthnCredentialMetadata {
  authenticatorId: string;
  credentialId: string;
  principalId: string;
  rpId: string;
  origin: string;
  signCount: number;
  transports: string[];
  aaguid?: string;
  createdAt: string;
}

export interface PendingWebAuthnRegistration {
  registrationId: string;
  principalId: string;
  challenge: string;
  rpId: string;
  origin: string;
  expiresAt: string;
  consumed: boolean;
}

export interface WebAuthnRegistrationCredentialJSON {
  id: string;
  rawId: string;
  type: 'public-key';
  response: {
    clientDataJSON: string;
    attestationObject: string;
    transports?: string[];
  };
}

export interface WebAuthnAuthenticationCredentialJSON {
  id: string;
  rawId: string;
  type: 'public-key';
  response: {
    clientDataJSON: string;
    authenticatorData: string;
    signature: string;
    userHandle?: string | null;
  };
}

export interface WebAuthnEvidenceProof {
  schema: 'haa.webauthn-proof.v1';
  credentialId: string;
  clientDataJSON: string;
  authenticatorData: string;
  assertionSignature: string;
}

export interface VerifiedRegistrationCredential {
  credentialId: string;
  publicKeyPem: string;
  signCount: number;
  transports: string[];
  aaguid: string;
}

export interface WebAuthnMetadataResolver {
  get(authenticatorId: string): WebAuthnCredentialMetadata | null;
  advanceCounter(authenticatorId: string, expectedCounter: number, nextCounter: number): boolean;
}

export function normalizeWebAuthnPolicy(policy: WebAuthnPolicy): Required<WebAuthnPolicy> {
  if (!policy.rpId || !policy.origin || !policy.rpName) throw new Error('INVALID_WEBAUTHN_POLICY');
  let parsed: URL;
  try {
    parsed = new URL(policy.origin);
  } catch {
    throw new Error('INVALID_WEBAUTHN_ORIGIN');
  }
  if (parsed.pathname !== '/' || parsed.search || parsed.hash) throw new Error('INVALID_WEBAUTHN_ORIGIN');
  if (parsed.protocol !== 'https:' && parsed.hostname !== 'localhost') throw new Error('WEBAUTHN_INSECURE_ORIGIN');
  const host = parsed.hostname.toLowerCase();
  const rpId = policy.rpId.toLowerCase();
  if (host !== rpId && !host.endsWith(`.${rpId}`)) throw new Error('WEBAUTHN_RP_ORIGIN_MISMATCH');
  const registrationTtlMs = policy.registrationTtlMs ?? DEFAULT_REGISTRATION_TTL_MS;
  const authenticationTimeoutMs = policy.authenticationTimeoutMs ?? DEFAULT_AUTHENTICATION_TIMEOUT_MS;
  if (!Number.isInteger(registrationTtlMs) || registrationTtlMs < 30_000 || registrationTtlMs > 10 * 60_000) {
    throw new Error('INVALID_WEBAUTHN_REGISTRATION_TTL');
  }
  if (!Number.isInteger(authenticationTimeoutMs) || authenticationTimeoutMs < 30_000 || authenticationTimeoutMs > 5 * 60_000) {
    throw new Error('INVALID_WEBAUTHN_AUTHENTICATION_TIMEOUT');
  }
  return {
    rpId,
    origin: parsed.origin,
    rpName: policy.rpName,
    registrationTtlMs,
    authenticationTimeoutMs,
  };
}

export function createRegistrationChallenge(): string {
  return randomBytes(32).toString('base64url');
}

export function createWebAuthnRegistrationOptions(args: {
  policy: WebAuthnPolicy;
  principalId: string;
  challenge: string;
  excludeCredentials?: Array<Pick<WebAuthnCredentialMetadata, 'credentialId' | 'transports'>>;
}) {
  const policy = normalizeWebAuthnPolicy(args.policy);
  const userHandle = createHash('sha256')
    .update(`haa-webauthn-user:${args.principalId}`, 'utf8')
    .digest('base64url');
  return {
    challenge: args.challenge,
    rp: { id: policy.rpId, name: policy.rpName },
    user: { id: userHandle, name: args.principalId, displayName: args.principalId },
    pubKeyCredParams: [{ type: 'public-key' as const, alg: -7 }],
    timeout: policy.registrationTtlMs,
    attestation: 'none' as const,
    authenticatorSelection: {
      authenticatorAttachment: 'platform' as const,
      residentKey: 'preferred' as const,
      requireResidentKey: false,
      userVerification: 'required' as const,
    },
    excludeCredentials: (args.excludeCredentials ?? []).map((credential) => ({
      type: 'public-key' as const,
      id: credential.credentialId,
      ...(credential.transports.length > 0 ? { transports: credential.transports } : {}),
    })),
  };
}

export function createWebAuthnAuthenticationOptions(args: {
  policy: WebAuthnPolicy;
  challengeDigest: string;
  credential: Pick<WebAuthnCredentialMetadata, 'credentialId' | 'transports'>;
}) {
  const policy = normalizeWebAuthnPolicy(args.policy);
  return {
    challenge: Buffer.from(args.challengeDigest, 'utf8').toString('base64url'),
    rpId: policy.rpId,
    timeout: policy.authenticationTimeoutMs,
    userVerification: 'required' as const,
    allowCredentials: [{
      type: 'public-key' as const,
      id: args.credential.credentialId,
      ...(args.credential.transports.length > 0 ? { transports: args.credential.transports } : {}),
    }],
  };
}

function decodeBase64Url(value: string, label: string): Buffer {
  if (typeof value !== 'string' || value.length === 0 || value.length > MAX_WEBAUTHN_BLOB_BYTES * 2) {
    throw new Error(`INVALID_${label}`);
  }
  if (!/^[A-Za-z0-9_-]+$/.test(value)) throw new Error(`INVALID_${label}`);
  const decoded = Buffer.from(value, 'base64url');
  if (decoded.length === 0 || decoded.length > MAX_WEBAUTHN_BLOB_BYTES) throw new Error(`INVALID_${label}`);
  if (decoded.toString('base64url') !== value) throw new Error(`INVALID_${label}`);
  return decoded;
}

function decodeClientData(value: string): { type: string; challenge: string; origin: string; crossOrigin?: boolean } {
  const bytes = decodeBase64Url(value, 'CLIENT_DATA');
  let parsed: unknown;
  try {
    parsed = JSON.parse(bytes.toString('utf8'));
  } catch {
    throw new Error('INVALID_CLIENT_DATA_JSON');
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('INVALID_CLIENT_DATA_JSON');
  const data = parsed as Record<string, unknown>;
  if (typeof data.type !== 'string' || typeof data.challenge !== 'string' || typeof data.origin !== 'string') {
    throw new Error('INVALID_CLIENT_DATA_JSON');
  }
  if (data.crossOrigin !== undefined && typeof data.crossOrigin !== 'boolean') throw new Error('INVALID_CLIENT_DATA_JSON');
  return {
    type: data.type,
    challenge: data.challenge,
    origin: data.origin,
    ...(data.crossOrigin !== undefined ? { crossOrigin: data.crossOrigin } : {}),
  };
}

interface CborDecodeResult {
  value: unknown;
  offset: number;
}

function readCborLength(bytes: Buffer, offset: number, additional: number): { length: number; offset: number } {
  if (additional < 24) return { length: additional, offset };
  if (additional === 24) {
    if (offset + 1 > bytes.length) throw new Error('INVALID_CBOR');
    return { length: bytes[offset]!, offset: offset + 1 };
  }
  if (additional === 25) {
    if (offset + 2 > bytes.length) throw new Error('INVALID_CBOR');
    return { length: bytes.readUInt16BE(offset), offset: offset + 2 };
  }
  if (additional === 26) {
    if (offset + 4 > bytes.length) throw new Error('INVALID_CBOR');
    return { length: bytes.readUInt32BE(offset), offset: offset + 4 };
  }
  throw new Error('UNSUPPORTED_CBOR_LENGTH');
}

function decodeCbor(bytes: Buffer, startOffset = 0, depth = 0): CborDecodeResult {
  if (depth > 12 || startOffset >= bytes.length) throw new Error('INVALID_CBOR');
  const initial = bytes[startOffset]!;
  const major = initial >> 5;
  const additional = initial & 0x1f;
  const lengthResult = readCborLength(bytes, startOffset + 1, additional);
  let offset = lengthResult.offset;
  const length = lengthResult.length;

  if (major === 0) return { value: length, offset };
  if (major === 1) return { value: -1 - length, offset };
  if (major === 2 || major === 3) {
    if (offset + length > bytes.length) throw new Error('INVALID_CBOR');
    const data = bytes.subarray(offset, offset + length);
    return { value: major === 2 ? Buffer.from(data) : data.toString('utf8'), offset: offset + length };
  }
  if (major === 4) {
    const values: unknown[] = [];
    for (let index = 0; index < length; index += 1) {
      const decoded = decodeCbor(bytes, offset, depth + 1);
      values.push(decoded.value);
      offset = decoded.offset;
    }
    return { value: values, offset };
  }
  if (major === 5) {
    const map = new Map<unknown, unknown>();
    for (let index = 0; index < length; index += 1) {
      const key = decodeCbor(bytes, offset, depth + 1);
      const value = decodeCbor(bytes, key.offset, depth + 1);
      map.set(key.value, value.value);
      offset = value.offset;
    }
    return { value: map, offset };
  }
  if (major === 7) {
    if (additional === 20) return { value: false, offset: startOffset + 1 };
    if (additional === 21) return { value: true, offset: startOffset + 1 };
    if (additional === 22) return { value: null, offset: startOffset + 1 };
  }
  throw new Error('UNSUPPORTED_CBOR_TYPE');
}

function assertRpIdHash(authenticatorData: Buffer, rpId: string): void {
  if (authenticatorData.length < 37) throw new Error('INVALID_AUTHENTICATOR_DATA');
  const expected = createHash('sha256').update(rpId, 'utf8').digest();
  if (!authenticatorData.subarray(0, 32).equals(expected)) throw new Error('WEBAUTHN_RP_ID_MISMATCH');
}

function assertUserVerification(flags: number): void {
  if ((flags & FLAG_UP) === 0) throw new Error('WEBAUTHN_USER_PRESENCE_REQUIRED');
  if ((flags & FLAG_UV) === 0) throw new Error('WEBAUTHN_USER_VERIFICATION_REQUIRED');
}

function parseCredentialPublicKey(cose: unknown): string {
  if (!(cose instanceof Map)) throw new Error('INVALID_COSE_KEY');
  if (cose.get(1) !== 2 || cose.get(3) !== -7 || cose.get(-1) !== 1) throw new Error('UNSUPPORTED_WEBAUTHN_KEY');
  const x = cose.get(-2);
  const y = cose.get(-3);
  if (!Buffer.isBuffer(x) || !Buffer.isBuffer(y) || x.length !== 32 || y.length !== 32) throw new Error('INVALID_COSE_KEY');
  const key = createPublicKey({
    key: {
      kty: 'EC',
      crv: 'P-256',
      x: x.toString('base64url'),
      y: y.toString('base64url'),
    },
    format: 'jwk',
  });
  return key.export({ format: 'pem', type: 'spki' }).toString();
}

function parseAttestationObject(attestationObject: Buffer): {
  authData: Buffer;
  fmt: string;
  attStmt: Map<unknown, unknown>;
} {
  const decoded = decodeCbor(attestationObject);
  if (decoded.offset !== attestationObject.length || !(decoded.value instanceof Map)) throw new Error('INVALID_ATTESTATION_OBJECT');
  const authData = decoded.value.get('authData');
  const fmt = decoded.value.get('fmt');
  const attStmt = decoded.value.get('attStmt');
  if (!Buffer.isBuffer(authData) || typeof fmt !== 'string' || !(attStmt instanceof Map)) throw new Error('INVALID_ATTESTATION_OBJECT');
  return { authData, fmt, attStmt };
}

export function verifyWebAuthnRegistration(args: {
  credential: WebAuthnRegistrationCredentialJSON;
  expectedChallenge: string;
  policy: WebAuthnPolicy;
}): VerifiedRegistrationCredential {
  const policy = normalizeWebAuthnPolicy(args.policy);
  const credential = args.credential;
  if (credential.type !== 'public-key' || !credential.response) throw new Error('INVALID_WEBAUTHN_REGISTRATION');
  const rawId = decodeBase64Url(credential.rawId, 'CREDENTIAL_ID');
  if (credential.id !== rawId.toString('base64url')) throw new Error('WEBAUTHN_CREDENTIAL_ID_MISMATCH');

  const clientData = decodeClientData(credential.response.clientDataJSON);
  if (clientData.type !== 'webauthn.create') throw new Error('WEBAUTHN_CLIENT_DATA_TYPE_MISMATCH');
  if (clientData.challenge !== args.expectedChallenge) throw new Error('WEBAUTHN_CHALLENGE_MISMATCH');
  if (clientData.origin !== policy.origin) throw new Error('WEBAUTHN_ORIGIN_MISMATCH');
  if (clientData.crossOrigin === true) throw new Error('WEBAUTHN_CROSS_ORIGIN_FORBIDDEN');

  const attestation = parseAttestationObject(decodeBase64Url(credential.response.attestationObject, 'ATTESTATION_OBJECT'));
  if (attestation.fmt !== 'none' || attestation.attStmt.size !== 0) throw new Error('WEBAUTHN_ATTESTATION_NOT_NONE');
  assertRpIdHash(attestation.authData, policy.rpId);
  const flags = attestation.authData[32]!;
  assertUserVerification(flags);
  if ((flags & FLAG_AT) === 0) throw new Error('WEBAUTHN_ATTESTED_CREDENTIAL_MISSING');
  const signCount = attestation.authData.readUInt32BE(33);

  let offset = 37;
  if (offset + 18 > attestation.authData.length) throw new Error('INVALID_AUTHENTICATOR_DATA');
  const aaguid = attestation.authData.subarray(offset, offset + 16).toString('hex');
  offset += 16;
  const credentialIdLength = attestation.authData.readUInt16BE(offset);
  offset += 2;
  if (credentialIdLength < 1 || offset + credentialIdLength > attestation.authData.length) throw new Error('INVALID_CREDENTIAL_ID_LENGTH');
  const attestedCredentialId = attestation.authData.subarray(offset, offset + credentialIdLength);
  offset += credentialIdLength;
  if (!attestedCredentialId.equals(rawId)) throw new Error('WEBAUTHN_CREDENTIAL_ID_MISMATCH');

  const cose = decodeCbor(attestation.authData, offset);
  offset = cose.offset;
  const publicKeyPem = parseCredentialPublicKey(cose.value);
  if ((flags & FLAG_ED) !== 0) {
    const extensions = decodeCbor(attestation.authData, offset);
    offset = extensions.offset;
  }
  if (offset !== attestation.authData.length) throw new Error('INVALID_AUTHENTICATOR_DATA_TRAILING_BYTES');

  const transports = [...new Set((credential.response.transports ?? []).filter((value) => typeof value === 'string' && value.length <= 64))];
  return {
    credentialId: credential.id,
    publicKeyPem,
    signCount,
    transports,
    aaguid,
  };
}

export function encodeWebAuthnEvidenceProof(proof: WebAuthnEvidenceProof): string {
  return Buffer.from(JSON.stringify(proof), 'utf8').toString('base64url');
}

export function decodeWebAuthnEvidenceProof(value: string): WebAuthnEvidenceProof {
  const raw = decodeBase64Url(value, 'WEBAUTHN_PROOF');
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw.toString('utf8'));
  } catch {
    throw new Error('INVALID_WEBAUTHN_PROOF');
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('INVALID_WEBAUTHN_PROOF');
  const object = parsed as Record<string, unknown>;
  const expectedKeys = ['schema', 'credentialId', 'clientDataJSON', 'authenticatorData', 'assertionSignature'];
  if (Object.keys(object).sort().join('|') !== [...expectedKeys].sort().join('|')) throw new Error('INVALID_WEBAUTHN_PROOF');
  if (object.schema !== WEBAUTHN_PROOF_SCHEMA
    || typeof object.credentialId !== 'string'
    || typeof object.clientDataJSON !== 'string'
    || typeof object.authenticatorData !== 'string'
    || typeof object.assertionSignature !== 'string') {
    throw new Error('INVALID_WEBAUTHN_PROOF');
  }
  return {
    schema: WEBAUTHN_PROOF_SCHEMA,
    credentialId: object.credentialId,
    clientDataJSON: object.clientDataJSON,
    authenticatorData: object.authenticatorData,
    assertionSignature: object.assertionSignature,
  };
}

export class WebAuthnEvidenceVerifier implements EvidenceVerifier {
  readonly type = WEBAUTHN_EVIDENCE_TYPE;
  private readonly policy: Required<WebAuthnPolicy>;
  private readonly metadata: WebAuthnMetadataResolver;

  constructor(policy: WebAuthnPolicy, metadata: WebAuthnMetadataResolver) {
    this.policy = normalizeWebAuthnPolicy(policy);
    this.metadata = metadata;
  }

  verify({ evidence, challenge, authenticator, now = new Date() }: {
    evidence: ApprovalEvidence;
    challenge: ApprovalChallengePackage;
    authenticator: AuthenticatorRecord;
    now?: Date;
  }): VerifiedEvidence {
    if (evidence.type !== this.type || authenticator.type !== this.type) throw new Error('EVIDENCE_TYPE_MISMATCH');
    if (evidence.signatureAlgorithm !== 'ES256' || authenticator.signatureAlgorithm !== 'ES256') {
      throw new Error('WEBAUTHN_ALGORITHM_MISMATCH');
    }
    if (authenticator.status !== 'ACTIVE') throw new Error('AUTHENTICATOR_REVOKED');
    if (evidence.authenticatorId !== authenticator.id) throw new Error('AUTHENTICATOR_MISMATCH');
    const expectedDigest = challengeDigest(challenge);
    if (evidence.challengeDigest !== expectedDigest) throw new Error('CHALLENGE_DIGEST_MISMATCH');

    const metadata = this.metadata.get(authenticator.id);
    if (!metadata) throw new Error('WEBAUTHN_METADATA_NOT_FOUND');
    if (metadata.principalId !== authenticator.principalId) throw new Error('WEBAUTHN_PRINCIPAL_MISMATCH');
    if (metadata.rpId !== this.policy.rpId || metadata.origin !== this.policy.origin) throw new Error('WEBAUTHN_POLICY_MISMATCH');

    const proof = decodeWebAuthnEvidenceProof(evidence.signature);
    if (proof.credentialId !== metadata.credentialId) throw new Error('WEBAUTHN_CREDENTIAL_ID_MISMATCH');
    const clientData = decodeClientData(proof.clientDataJSON);
    if (clientData.type !== 'webauthn.get') throw new Error('WEBAUTHN_CLIENT_DATA_TYPE_MISMATCH');
    const expectedWebAuthnChallenge = Buffer.from(expectedDigest, 'utf8').toString('base64url');
    if (clientData.challenge !== expectedWebAuthnChallenge) throw new Error('WEBAUTHN_CHALLENGE_MISMATCH');
    if (clientData.origin !== this.policy.origin) throw new Error('WEBAUTHN_ORIGIN_MISMATCH');
    if (clientData.crossOrigin === true) throw new Error('WEBAUTHN_CROSS_ORIGIN_FORBIDDEN');

    const authenticatorData = decodeBase64Url(proof.authenticatorData, 'AUTHENTICATOR_DATA');
    assertRpIdHash(authenticatorData, this.policy.rpId);
    const flags = authenticatorData[32]!;
    assertUserVerification(flags);
    const nextCounter = authenticatorData.readUInt32BE(33);
    if (evidence.counter !== undefined && evidence.counter !== nextCounter) throw new Error('WEBAUTHN_COUNTER_MISMATCH');

    const clientHash = createHash('sha256').update(decodeBase64Url(proof.clientDataJSON, 'CLIENT_DATA')).digest();
    const signedBytes = Buffer.concat([authenticatorData, clientHash]);
    const assertionSignature = decodeBase64Url(proof.assertionSignature, 'ASSERTION_SIGNATURE');
    const valid = verifyCryptoSignature('sha256', signedBytes, authenticator.publicKeyPem, assertionSignature);
    if (!valid) throw new Error('INVALID_EVIDENCE_SIGNATURE');

    if ((metadata.signCount !== 0 || nextCounter !== 0)
      && !this.metadata.advanceCounter(authenticator.id, metadata.signCount, nextCounter)) {
      throw new Error('WEBAUTHN_COUNTER_REPLAY');
    }

    return {
      schema: 'haa.verified-evidence.v1',
      principalId: authenticator.principalId,
      authenticatorId: authenticator.id,
      verifiedChallengeDigest: expectedDigest,
      humanVerificationLevel: 'user-verified',
      verifiedAt: now.toISOString(),
    };
  }
}

export { WebAuthnStore } from './store.ts';
