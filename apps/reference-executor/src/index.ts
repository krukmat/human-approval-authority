#!/usr/bin/env node
import { readFile, rename, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { HaaClient } from '../../../packages/sdk-ts/src/index.ts';
import type { ActionSpec } from '../../../packages/protocol/src/index.ts';

interface ResourceState {
  name: string;
  version: string;
  lastOperation?: string | null;
}

const [requestId, executionId, actionPath, resourcePath] = process.argv.slice(2);
if (!requestId || !executionId || !actionPath || !resourcePath) {
  throw new Error('usage: <requestId> <executionId> <action.json> <resource.json>');
}

const apiKey = process.env.HAA_API_KEY;
if (!apiKey) throw new Error('HAA_API_KEY is required');
const baseUrl = process.env.HAA_URL ?? 'http://127.0.0.1:8787';
const client = new HaaClient(baseUrl, apiKey);

const action = JSON.parse(await readFile(actionPath, 'utf8')) as ActionSpec;
const resource = JSON.parse(await readFile(resourcePath, 'utf8')) as ResourceState;

if (action.schema !== 'haa.action.v1' || action.type !== 'demo.action.v1') {
  throw new Error('UNSUPPORTED_ACTION_PROFILE');
}
const resourceName = action.payload.resource;
const operation = action.payload.operation;
if (typeof resourceName !== 'string' || typeof operation !== 'string') {
  throw new Error('INVALID_DEMO_ACTION');
}
if (resourceName !== resource.name) throw new Error('RESOURCE_MISMATCH');
if (typeof resource.version !== 'string' || !resource.version) throw new Error('INVALID_RESOURCE_VERSION');

const grant = await client.authorize({
  requestId,
  executionId,
  actualAction: action,
  actualState: { version: resource.version },
});

const executedVersion = `executed:${executionId}`;
if (resource.version === executedVersion) {
  console.log(JSON.stringify({ grant, resource, reused: true }, null, 2));
  process.exit(0);
}

const next: ResourceState = {
  ...resource,
  version: executedVersion,
  lastOperation: operation,
};
const temporaryPath = join(dirname(resourcePath), `.haa-resource-${randomUUID()}.tmp`);
await writeFile(temporaryPath, `${JSON.stringify(next, null, 2)}\n`, 'utf8');
await rename(temporaryPath, resourcePath);

console.log(JSON.stringify({ grant, resource: next, reused: false }, null, 2));
