#!/usr/bin/env node
import { readFile } from 'node:fs/promises';
import { HaaClient } from '../../../packages/sdk-ts/src/index.ts';

const [command, ...args] = process.argv.slice(2);
const baseUrl = process.env.HAA_URL ?? 'http://127.0.0.1:8787';
const apiKey = process.env.HAA_API_KEY;
if (!apiKey) throw new Error('HAA_API_KEY is required');
const client = new HaaClient(baseUrl, apiKey);

async function jsonFile(path: string) { return JSON.parse(await readFile(path, 'utf8')); }

if (command === 'request') {
  const [actionFile, approverPrincipalId, executorAudience] = args;
  if (!actionFile || !approverPrincipalId || !executorAudience) throw new Error('usage: request <action.json> <approver> <executor>');
  console.log(JSON.stringify(await client.requestApproval({ action: await jsonFile(actionFile), approverPrincipalId, executorAudience }), null, 2));
} else if (command === 'status') {
  const [requestId] = args;
  if (!requestId) throw new Error('usage: status <requestId>');
  console.log(JSON.stringify(await client.getApproval(requestId), null, 2));
} else if (command === 'authorize') {
  const [requestId, executionId, actionFile, stateFile] = args;
  if (!requestId || !executionId || !actionFile) throw new Error('usage: authorize <requestId> <executionId> <action.json> [state.json]');
  const actualAction = await jsonFile(actionFile);
  const actualState = stateFile ? await jsonFile(stateFile) : undefined;
  console.log(JSON.stringify(await client.authorize({ requestId, executionId, actualAction, actualState }), null, 2));
} else {
  console.error('commands: request | status | authorize');
  process.exitCode = 2;
}
