import { restoreBackupBundle } from '../apps/haa-server/src/backup.ts';

const bundleDir = process.argv[2];
if (!bundleDir) {
  console.error('Usage: npm run restore:instance -- <bundle-dir>');
  process.exit(2);
}

const dbPath = process.env.HAA_DB_PATH ?? './haa.db';
const keyFile = process.env.HAA_AUTHORITY_KEY_FILE ?? './.haa/authority-key.pem';
const keyRingFile = process.env.HAA_AUTHORITY_KEYRING_FILE ?? `${keyFile}.ring.json`;
const overwrite = process.env.HAA_RESTORE_CONFIRM === 'YES';
const manifest = restoreBackupBundle({ bundleDir, dbPath, keyFile, keyRingFile, overwrite });
console.log(JSON.stringify({ status: 'restored', manifest }, null, 2));
