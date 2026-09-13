import { createBackupBundle } from '../apps/haa-server/src/backup.ts';

const destinationDir = process.argv[2];
if (!destinationDir) {
  console.error('Usage: npm run backup:instance -- <destination-dir>');
  process.exit(2);
}

const dbPath = process.env.HAA_DB_PATH ?? './haa.db';
const keyFile = process.env.HAA_AUTHORITY_KEY_FILE ?? './.haa/authority-key.pem';
const keyRingFile = process.env.HAA_AUTHORITY_KEYRING_FILE ?? `${keyFile}.ring.json`;
const manifest = createBackupBundle({ dbPath, keyFile, keyRingFile, destinationDir });
console.log(JSON.stringify(manifest, null, 2));
