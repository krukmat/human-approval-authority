#!/usr/bin/env node
import { readFile } from 'node:fs/promises';
import { HaaClient, unknownCeremonyResult, type UnknownCeremonyReason } from '../../../packages/sdk-ts/src/index.ts';

const [command, ...args] = process.argv.slice(2);
const baseUrl = process.env.HAA_URL ?? 'http://127.0.0.1:8787';
const apiKey = process.env.HAA_API_KEY;
if (!apiKey) throw new Error('HAA_API_KEY is required');
const client = new HaaClient(baseUrl, apiKey);

async function jsonFile(path: string) { return JSON.parse(await readFile(path, 'utf8')); }

const UNKNOWN_REASONS: UnknownCeremonyReason[] = [
  'WINDOW_CLOSED',
  'LOCAL_TIMEOUT',
  'APP_TERMINATED',
  'INTERACTION_ERROR',
  'AUTHENTICATOR_UNAVAILABLE',
];

if (command === 'request') {
  const [actionFile, approverPrincipalId, executorAudience] = args;
  if (!actionFile || !approverPrincipalId || !executorAudience) throw new Error('usage: request <action.json> <approver> <executor>');
  console.log(JSON.stringify(await client.requestApproval({ action: await jsonFile(actionFile), approverPrincipalId, executorAudience }), null, 2));
} else if (command === 'status') {
  const [requestId] = args;
  if (!requestId) throw new Error('usage: status <requestId>');
  console.log(JSON.stringify(await client.getApproval(requestId), null, 2));
} else if (command === 'reject') {
  const [requestId, challengeDigest] = args;
  if (!requestId || !challengeDigest) throw new Error('usage: reject <requestId> <challengeDigest>');
  console.log(JSON.stringify(await client.rejectApproval({ requestId, challengeDigest, reason: 'USER_ESCAPE' }), null, 2));
} else if (command === 'unknown') {
  const [requestId, reason] = args;
  if (!requestId || !reason || !UNKNOWN_REASONS.includes(reason as UnknownCeremonyReason)) {
    throw new Error(`usage: unknown <requestId> <${UNKNOWN_REASONS.join('|')}>`);
  }
  console.log(JSON.stringify(unknownCeremonyResult(requestId, reason as UnknownCeremonyReason), null, 2));
} else if (command === 'authorize') {
  const [requestId, executionId, actionFile, stateFile] = args;
  if (!requestId || !executionId || !actionFile) throw new Error('usage: authorize <requestId> <executionId> <action.json> [state.json]');
  const actualAction = await jsonFile(actionFile);
  const actualState = stateFile ? await jsonFile(stateFile) : undefined;
  console.log(JSON.stringify(await client.authorize({ requestId, executionId, actualAction, actualState }), null, 2));
} else {
  console.error('commands: request | status | reject | unknown | authorize');
  process.exitCode = 2;
}
