import { existsSync } from 'node:fs';
import { SqliteStore } from '../packages/persistence-sqlite/src/index.ts';
import { loadOrCreateAuthorityKeyRing } from '../apps/haa-server/src/authority.ts';
import { verifyAuditIntegrity } from '../apps/haa-server/src/audit-integrity.ts';

const dbPath = process.env.HAA_DB_PATH ?? './haa.db';
const keyFile = process.env.HAA_AUTHORITY_KEY_FILE ?? './.haa/authority-key.pem';
const keyRingFile = process.env.HAA_AUTHORITY_KEYRING_FILE ?? `${keyFile}.ring.json`;

if (!existsSync(dbPath)) throw new Error('AUDIT_DB_NOT_FOUND');
if (!existsSync(keyFile) || !existsSync(keyRingFile)) throw new Error('AUTHORITY_KEYRING_NOT_FOUND');

const store = new SqliteStore(dbPath);
try {
  const ring = loadOrCreateAuthorityKeyRing({ keyFile, keyRingFile });
  const result = verifyAuditIntegrity(store, (keyId) => {
    const key = ring.resolve(keyId);
    return key ? { algorithm: key.algorithm, publicKeyPem: key.publicKeyPem } : null;
  });
  console.log(JSON.stringify({
    status: 'ok',
    head: result.head,
    checkpointsVerified: result.checkpointsVerified,
  }, null, 2));
} finally {
  store.close();
}
