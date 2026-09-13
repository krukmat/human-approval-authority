#!/usr/bin/env node
import { readFile } from 'node:fs/promises';
import { SqliteStore } from '../packages/persistence-sqlite/src/index.ts';
import { sha256 } from '../packages/core/src/index.ts';

const clientId = process.argv[2]?.trim();
if (!clientId || !/^[A-Za-z0-9._:-]{1,128}$/.test(clientId)) {
  throw new Error('Usage: npm run rotate:client -- <client-id>. Client id must be 1-128 safe characters.');
}

let apiKey = process.env.HAA_CLIENT_KEY?.trim();
if (!apiKey) {
  if (process.stdin.isTTY) throw new Error('Provide the replacement key through HAA_CLIENT_KEY or stdin.');
  apiKey = (await readFile(0, 'utf8')).trim();
}
if (apiKey.length < 32) throw new Error('Refusing to rotate to an API key shorter than 32 characters.');

const expiresAt = process.env.HAA_CLIENT_EXPIRES_AT?.trim();
if (expiresAt && !Number.isFinite(Date.parse(expiresAt))) throw new Error('HAA_CLIENT_EXPIRES_AT must be a valid timestamp.');

const store = new SqliteStore(process.env.HAA_DB_PATH ?? './haa.db');
try {
  const version = store.rotateClientCredential(clientId, sha256(apiKey), {
    ...(expiresAt ? { expiresAt } : {}),
    actorId: 'rotate-client-cli',
  });
  console.log(`Rotated HAA client credential: ${clientId} version=${version}`);
} finally {
  store.close();
}
