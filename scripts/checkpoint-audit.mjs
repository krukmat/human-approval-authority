import { SqliteStore } from '../packages/persistence-sqlite/src/index.ts';
import { loadOrCreateAuthorityKeyRing } from '../apps/haa-server/src/authority.ts';
import { createAuditCheckpoint } from '../apps/haa-server/src/audit-integrity.ts';

const dbPath = process.env.HAA_DB_PATH ?? './haa.db';
const keyFile = process.env.HAA_AUTHORITY_KEY_FILE ?? './.haa/authority-key.pem';
const keyRingFile = process.env.HAA_AUTHORITY_KEYRING_FILE ?? `${keyFile}.ring.json`;
const store = new SqliteStore(dbPath);
try {
  const ring = loadOrCreateAuthorityKeyRing({ keyFile, keyRingFile });
  const checkpoint = createAuditCheckpoint(store, ring.signer);
  console.log(JSON.stringify(checkpoint, null, 2));
} finally {
  store.close();
}
