import {
  chmodSync,
  existsSync,
  mkdirSync,
  readFileSync,
  renameSync,
  writeFileSync,
} from 'node:fs';
import { dirname } from 'node:path';
import { generateKeyPairSync } from 'node:crypto';
import {
  createPemSigner,
  type SignatureAlgorithm,
  type Signer,
} from '../../../packages/core/src/index.ts';

export type AuthorityKeyStatus = 'ACTIVE' | 'RETIRED';

export interface AuthorityPublicKeyRecord {
  keyId: string;
  algorithm: SignatureAlgorithm;
  publicKeyPem: string;
  status: AuthorityKeyStatus;
  createdAt: string;
  retiredAt?: string;
}

interface AuthorityKeyRingFile {
  version: 1;
  activeKeyId: string;
  keys: AuthorityPublicKeyRecord[];
}

export interface AuthorityKeyRingOptions {
  keyId?: string;
  privateKeyPem?: string;
  keyFile?: string;
  keyRingFile?: string;
  now?: Date;
}

function generateP256Pem(): string {
  const { privateKey } = generateKeyPairSync('ec', { namedCurve: 'prime256v1' });
  return privateKey.export({ type: 'pkcs8', format: 'pem' }).toString();
}

function writePrivateKey(path: string, pem: string): void {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, pem, { mode: 0o600 });
  try { chmodSync(path, 0o600); } catch { /* best effort on non-POSIX */ }
}

function writeJsonAtomic(path: string, value: unknown): void {
  mkdirSync(dirname(path), { recursive: true });
  const temporary = `${path}.tmp-${process.pid}`;
  writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600 });
  renameSync(temporary, path);
  try { chmodSync(path, 0o600); } catch { /* best effort on non-POSIX */ }
}

function parseKeyRing(path: string): AuthorityKeyRingFile {
  const parsed = JSON.parse(readFileSync(path, 'utf8')) as Partial<AuthorityKeyRingFile>;
  if (parsed.version !== 1 || typeof parsed.activeKeyId !== 'string' || !Array.isArray(parsed.keys)) {
    throw new Error('INVALID_AUTHORITY_KEYRING');
  }
  const keys = parsed.keys as AuthorityPublicKeyRecord[];
  const active = keys.filter((key) => key.status === 'ACTIVE');
  if (active.length !== 1 || active[0]?.keyId !== parsed.activeKeyId) throw new Error('INVALID_AUTHORITY_KEYRING_ACTIVE_KEY');
  const ids = new Set(keys.map((key) => key.keyId));
  if (ids.size !== keys.length) throw new Error('DUPLICATE_AUTHORITY_KEY_ID');
  return { version: 1, activeKeyId: parsed.activeKeyId, keys };
}

export class AuthorityKeyRing {
  readonly signer: Signer;
  private readonly records: AuthorityPublicKeyRecord[];

  constructor(signer: Signer, records: AuthorityPublicKeyRecord[]) {
    this.signer = signer;
    this.records = records.map((record) => ({ ...record }));
    const active = this.records.find((record) => record.status === 'ACTIVE');
    if (!active || active.keyId !== signer.keyId || active.algorithm !== signer.algorithm || active.publicKeyPem !== signer.publicKeyPem) {
      throw new Error('AUTHORITY_KEYRING_ACTIVE_KEY_MISMATCH');
    }
  }

  resolve(keyId: string): AuthorityPublicKeyRecord | null {
    const record = this.records.find((candidate) => candidate.keyId === keyId);
    return record ? { ...record } : null;
  }

  listPublicKeys(): AuthorityPublicKeyRecord[] {
    return this.records.map((record) => ({ ...record }));
  }
}

export function loadOrCreateAuthorityKeyRing(options: AuthorityKeyRingOptions = {}): AuthorityKeyRing {
  const keyFile = options.keyFile ?? './.haa/authority-key.pem';
  const keyRingFile = options.keyRingFile ?? `${keyFile}.ring.json`;
  const now = options.now ?? new Date();

  if (options.privateKeyPem) {
    const keyId = options.keyId ?? 'local-authority-p256-v1';
    const signer = createPemSigner(keyId, 'ES256', options.privateKeyPem);
    if (existsSync(keyRingFile)) {
      const ring = parseKeyRing(keyRingFile);
      if (ring.activeKeyId !== keyId) throw new Error('AUTHORITY_KEY_ID_CONFIG_MISMATCH');
      return new AuthorityKeyRing(signer, ring.keys);
    }
    return new AuthorityKeyRing(signer, [{
      keyId,
      algorithm: 'ES256',
      publicKeyPem: signer.publicKeyPem,
      status: 'ACTIVE',
      createdAt: now.toISOString(),
    }]);
  }

  if (existsSync(keyRingFile)) {
    const ring = parseKeyRing(keyRingFile);
    if (options.keyId && options.keyId !== ring.activeKeyId) throw new Error('AUTHORITY_KEY_ID_CONFIG_MISMATCH');
    if (!existsSync(keyFile)) throw new Error('AUTHORITY_ACTIVE_PRIVATE_KEY_MISSING');
    const signer = createPemSigner(ring.activeKeyId, 'ES256', readFileSync(keyFile, 'utf8'));
    return new AuthorityKeyRing(signer, ring.keys);
  }

  const keyId = options.keyId ?? 'local-authority-p256-v1';
  const pem = existsSync(keyFile) ? readFileSync(keyFile, 'utf8') : generateP256Pem();
  if (!existsSync(keyFile)) writePrivateKey(keyFile, pem);
  const signer = createPemSigner(keyId, 'ES256', pem);
  const ring: AuthorityKeyRingFile = {
    version: 1,
    activeKeyId: keyId,
    keys: [{
      keyId,
      algorithm: 'ES256',
      publicKeyPem: signer.publicKeyPem,
      status: 'ACTIVE',
      createdAt: now.toISOString(),
    }],
  };
  writeJsonAtomic(keyRingFile, ring);
  return new AuthorityKeyRing(signer, ring.keys);
}

export function rotateAuthorityKey(options: {
  nextKeyId: string;
  keyFile?: string;
  keyRingFile?: string;
  now?: Date;
}): AuthorityKeyRing {
  const keyFile = options.keyFile ?? './.haa/authority-key.pem';
  const keyRingFile = options.keyRingFile ?? `${keyFile}.ring.json`;
  const now = options.now ?? new Date();
  const current = loadOrCreateAuthorityKeyRing({ keyFile, keyRingFile, now });
  if (!options.nextKeyId || current.resolve(options.nextKeyId)) throw new Error('AUTHORITY_KEY_ID_ALREADY_EXISTS');

  const nextPem = generateP256Pem();
  const nextSigner = createPemSigner(options.nextKeyId, 'ES256', nextPem);
  const retiredAt = now.toISOString();
  const keys: AuthorityPublicKeyRecord[] = current.listPublicKeys().map((record) => record.status === 'ACTIVE'
    ? { ...record, status: 'RETIRED' as const, retiredAt }
    : record);
  keys.push({
    keyId: nextSigner.keyId,
    algorithm: nextSigner.algorithm,
    publicKeyPem: nextSigner.publicKeyPem,
    status: 'ACTIVE',
    createdAt: retiredAt,
  });

  const nextKeyFile = `${keyFile}.next-${process.pid}`;
  writePrivateKey(nextKeyFile, nextPem);
  renameSync(nextKeyFile, keyFile);
  writeJsonAtomic(keyRingFile, { version: 1, activeKeyId: nextSigner.keyId, keys } satisfies AuthorityKeyRingFile);
  return new AuthorityKeyRing(nextSigner, keys);
}

export function loadOrCreateAuthoritySigner(options: AuthorityKeyRingOptions = {}): Signer {
  return loadOrCreateAuthorityKeyRing(options).signer;
}
