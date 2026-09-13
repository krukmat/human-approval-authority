import { existsSync, mkdirSync, readFileSync, writeFileSync, chmodSync } from 'node:fs';
import { dirname } from 'node:path';
import { generateKeyPairSync } from 'node:crypto';
import { createPemSigner, type Signer } from '../../../packages/core/src/index.ts';

export function loadOrCreateAuthoritySigner(options: { keyId?: string; privateKeyPem?: string; keyFile?: string } = {}): Signer {
  const keyId = options.keyId ?? 'local-authority-p256-v1';
  if (options.privateKeyPem) return createPemSigner(keyId, 'ES256', options.privateKeyPem);
  const keyFile = options.keyFile ?? './.haa/authority-key.pem';
  if (existsSync(keyFile)) return createPemSigner(keyId, 'ES256', readFileSync(keyFile, 'utf8'));
  const { privateKey } = generateKeyPairSync('ec', { namedCurve: 'prime256v1' });
  const pem = privateKey.export({ type: 'pkcs8', format: 'pem' }).toString();
  mkdirSync(dirname(keyFile), { recursive: true });
  writeFileSync(keyFile, pem, { mode: 0o600 });
  try { chmodSync(keyFile, 0o600); } catch { /* best effort on non-POSIX */ }
  return createPemSigner(keyId, 'ES256', pem);
}
