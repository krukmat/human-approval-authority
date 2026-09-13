import { createHash } from 'node:crypto';
import {
  chmodSync,
  copyFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  renameSync,
  writeFileSync,
} from 'node:fs';
import { basename, dirname, join } from 'node:path';
import { SqliteStore, type AuditIntegrityHead } from '../../../packages/persistence-sqlite/src/index.ts';
import { loadOrCreateAuthorityKeyRing } from './authority.ts';
import { verifyAuditIntegrity } from './audit-integrity.ts';

export interface BackupManifest {
  schema: 'haa.backup-bundle.v1';
  createdAt: string;
  activeAuthorityKeyId: string;
  auditHead: AuditIntegrityHead | null;
  files: {
    database: { name: 'haa.db'; sha256: string };
    authorityPrivateKey: { name: 'authority-key.pem'; sha256: string };
    authorityKeyRing: { name: 'authority-keyring.json'; sha256: string };
  };
}

export interface BackupPaths {
  dbPath: string;
  keyFile: string;
  keyRingFile: string;
}

function sha256File(path: string): string {
  return `sha256:${createHash('sha256').update(readFileSync(path)).digest('base64url')}`;
}

function sqlString(value: string): string {
  return `'${value.replaceAll("'", "''")}'`;
}

function requiredFile(path: string, code: string): void {
  if (!existsSync(path)) throw new Error(code);
}

function resolver(ring: ReturnType<typeof loadOrCreateAuthorityKeyRing>) {
  return (keyId: string) => {
    const key = ring.resolve(keyId);
    return key ? { algorithm: key.algorithm, publicKeyPem: key.publicKeyPem } : null;
  };
}

export function createBackupBundle(args: BackupPaths & { destinationDir: string; now?: Date }): BackupManifest {
  requiredFile(args.dbPath, 'BACKUP_DB_NOT_FOUND');
  requiredFile(args.keyFile, 'BACKUP_AUTHORITY_KEY_NOT_FOUND');
  requiredFile(args.keyRingFile, 'BACKUP_AUTHORITY_KEYRING_NOT_FOUND');
  if (existsSync(args.destinationDir)) throw new Error('BACKUP_DESTINATION_ALREADY_EXISTS');
  mkdirSync(args.destinationDir, { recursive: true });

  const databaseOut = join(args.destinationDir, 'haa.db');
  const keyOut = join(args.destinationDir, 'authority-key.pem');
  const ringOut = join(args.destinationDir, 'authority-keyring.json');
  const store = new SqliteStore(args.dbPath);
  try {
    const authorityRing = loadOrCreateAuthorityKeyRing({ keyFile: args.keyFile, keyRingFile: args.keyRingFile });
    const audit = verifyAuditIntegrity(store, resolver(authorityRing), { requireCheckpoint: false });
    store.db.exec(`VACUUM INTO ${sqlString(databaseOut)}`);
    copyFileSync(args.keyFile, keyOut);
    copyFileSync(args.keyRingFile, ringOut);
    try { chmodSync(keyOut, 0o600); } catch { /* best effort on non-POSIX */ }

    const manifest: BackupManifest = {
      schema: 'haa.backup-bundle.v1',
      createdAt: (args.now ?? new Date()).toISOString(),
      activeAuthorityKeyId: authorityRing.signer.keyId,
      auditHead: audit.head,
      files: {
        database: { name: 'haa.db', sha256: sha256File(databaseOut) },
        authorityPrivateKey: { name: 'authority-key.pem', sha256: sha256File(keyOut) },
        authorityKeyRing: { name: 'authority-keyring.json', sha256: sha256File(ringOut) },
      },
    };
    writeFileSync(join(args.destinationDir, 'manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`, 'utf8');
    return manifest;
  } finally {
    store.close();
  }
}

export function verifyBackupBundle(bundleDir: string): BackupManifest {
  const manifestPath = join(bundleDir, 'manifest.json');
  requiredFile(manifestPath, 'BACKUP_MANIFEST_NOT_FOUND');
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8')) as BackupManifest;
  if (manifest.schema !== 'haa.backup-bundle.v1') throw new Error('UNSUPPORTED_BACKUP_MANIFEST');

  const databasePath = join(bundleDir, manifest.files.database.name);
  const keyPath = join(bundleDir, manifest.files.authorityPrivateKey.name);
  const ringPath = join(bundleDir, manifest.files.authorityKeyRing.name);
  requiredFile(databasePath, 'BACKUP_DB_NOT_FOUND');
  requiredFile(keyPath, 'BACKUP_AUTHORITY_KEY_NOT_FOUND');
  requiredFile(ringPath, 'BACKUP_AUTHORITY_KEYRING_NOT_FOUND');

  if (sha256File(databasePath) !== manifest.files.database.sha256) throw new Error('BACKUP_DB_CHECKSUM_MISMATCH');
  if (sha256File(keyPath) !== manifest.files.authorityPrivateKey.sha256) throw new Error('BACKUP_AUTHORITY_KEY_CHECKSUM_MISMATCH');
  if (sha256File(ringPath) !== manifest.files.authorityKeyRing.sha256) throw new Error('BACKUP_AUTHORITY_KEYRING_CHECKSUM_MISMATCH');

  const authorityRing = loadOrCreateAuthorityKeyRing({ keyFile: keyPath, keyRingFile: ringPath });
  if (authorityRing.signer.keyId !== manifest.activeAuthorityKeyId) throw new Error('BACKUP_ACTIVE_AUTHORITY_KEY_MISMATCH');

  const store = new SqliteStore(databasePath);
  try {
    const audit = verifyAuditIntegrity(store, resolver(authorityRing), { requireCheckpoint: false });
    if (JSON.stringify(audit.head) !== JSON.stringify(manifest.auditHead)) throw new Error('BACKUP_AUDIT_HEAD_MISMATCH');
  } finally {
    store.close();
  }
  return manifest;
}

function installFile(source: string, destination: string, overwrite: boolean): void {
  if (existsSync(destination) && !overwrite) throw new Error(`RESTORE_TARGET_EXISTS:${basename(destination)}`);
  mkdirSync(dirname(destination), { recursive: true });
  const temporary = `${destination}.restore-${process.pid}`;
  copyFileSync(source, temporary);
  renameSync(temporary, destination);
}

export function restoreBackupBundle(args: BackupPaths & { bundleDir: string; overwrite?: boolean }): BackupManifest {
  const manifest = verifyBackupBundle(args.bundleDir);
  const overwrite = args.overwrite ?? false;
  installFile(join(args.bundleDir, manifest.files.database.name), args.dbPath, overwrite);
  installFile(join(args.bundleDir, manifest.files.authorityPrivateKey.name), args.keyFile, overwrite);
  try { chmodSync(args.keyFile, 0o600); } catch { /* best effort on non-POSIX */ }
  installFile(join(args.bundleDir, manifest.files.authorityKeyRing.name), args.keyRingFile, overwrite);

  const restoredRing = loadOrCreateAuthorityKeyRing({ keyFile: args.keyFile, keyRingFile: args.keyRingFile });
  if (restoredRing.signer.keyId !== manifest.activeAuthorityKeyId) throw new Error('RESTORE_AUTHORITY_KEY_MISMATCH');
  const restoredStore = new SqliteStore(args.dbPath);
  try {
    const audit = verifyAuditIntegrity(restoredStore, resolver(restoredRing), { requireCheckpoint: false });
    if (JSON.stringify(audit.head) !== JSON.stringify(manifest.auditHead)) throw new Error('RESTORE_AUDIT_HEAD_MISMATCH');
  } finally {
    restoredStore.close();
  }
  return manifest;
}
