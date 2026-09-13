#!/usr/bin/env node
import { readFile } from 'node:fs/promises';
import { SqliteStore } from '../packages/persistence-sqlite/src/index.ts';
import { sha256 } from '../packages/core/src/index.ts';

const clientId = process.argv[2]?.trim();
const rolesInput = process.argv[3]?.trim() || process.env.HAA_CLIENT_ROLES?.trim();
if (!clientId || !rolesInput) {
  throw new Error('Usage: npm run provision:client -- <client-id> <REQUESTER|APPROVER|EXECUTOR[,..]>. Provide the API key through HAA_CLIENT_KEY or stdin.');
}
if (!/^[A-Za-z0-9._:-]{1,128}$/.test(clientId)) {
  throw new Error('Client id must be 1-128 characters using letters, numbers, dot, underscore, colon or hyphen.');
}

const allowedRoles = new Set(['REQUESTER', 'APPROVER', 'EXECUTOR']);
const roles = [...new Set(rolesInput.split(',').map((role) => role.trim().toUpperCase()).filter(Boolean))];
if (roles.length === 0 || roles.some((role) => !allowedRoles.has(role))) {
  throw new Error('Client roles must be a comma-separated subset of REQUESTER, APPROVER, EXECUTOR.');
}

let apiKey = process.env.HAA_CLIENT_KEY?.trim();
if (!apiKey) {
  if (process.stdin.isTTY) {
    throw new Error('No API key provided. Pipe a high-entropy key on stdin or set HAA_CLIENT_KEY for this command only.');
  }
  apiKey = (await readFile(0, 'utf8')).trim();
}
if (apiKey.length < 32) {
  throw new Error('Refusing to provision an API key shorter than 32 characters. Use a high-entropy secret.');
}

const expiresAt = process.env.HAA_CLIENT_EXPIRES_AT?.trim();
if (expiresAt && !Number.isFinite(Date.parse(expiresAt))) {
  throw new Error('HAA_CLIENT_EXPIRES_AT must be a valid timestamp when provided.');
}

const dbPath = process.env.HAA_DB_PATH ?? './haa.db';
const store = new SqliteStore(dbPath);
try {
  store.registerClient(clientId, sha256(apiKey), roles, {
    ...(expiresAt ? { expiresAt } : {}),
    actorId: 'provision-client-cli',
  });
  console.log(`Provisioned HAA client: ${clientId} roles=${roles.join(',')}`);
} finally {
  store.close();
}
