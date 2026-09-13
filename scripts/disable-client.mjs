#!/usr/bin/env node
import { SqliteStore } from '../packages/persistence-sqlite/src/index.ts';

const clientId = process.argv[2]?.trim();
if (!clientId || !/^[A-Za-z0-9._:-]{1,128}$/.test(clientId)) {
  throw new Error('Usage: npm run disable:client -- <client-id>. Client id must be 1-128 safe characters.');
}

const store = new SqliteStore(process.env.HAA_DB_PATH ?? './haa.db');
try {
  if (!store.disableClient(clientId, { actorId: 'disable-client-cli' })) {
    throw new Error('Client not found or already disabled.');
  }
  console.log(`Disabled HAA client: ${clientId}`);
} finally {
  store.close();
}
