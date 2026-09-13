import { verifyBackupBundle } from '../apps/haa-server/src/backup.ts';

const bundleDir = process.argv[2];
if (!bundleDir) {
  console.error('Usage: npm run verify:backup -- <bundle-dir>');
  process.exit(2);
}

const manifest = verifyBackupBundle(bundleDir);
console.log(JSON.stringify({ status: 'ok', manifest }, null, 2));
