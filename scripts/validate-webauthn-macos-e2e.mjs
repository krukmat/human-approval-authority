#!/usr/bin/env node
import { spawn, spawnSync } from 'node:child_process';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

if (process.platform !== 'darwin') {
  throw new Error('W7-T04.9 requires a real macOS host with a browser and Touch ID');
}

const repoRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const temp = await mkdtemp(join(tmpdir(), 'haa-webauthn-'));
const port = Number(process.env.HAA_WEBAUTHN_VALIDATION_PORT ?? 8795);
const baseUrl = `http://localhost:${port}`;
const keys = {
  requester: 'agent-dev-secret',
  human: 'human-dev-secret',
  executor: 'executor-dev-secret',
};
const action = {
  schema: 'haa.action.v1',
  type: 'demo.action.v1',
  payload: { resource: 'webauthn-physical-gate', operation: 'approve' },
  preconditions: { version: 'v1' },
};
let server;
let logs = '';

async function api(path, { method = 'GET', key, body } = {}) {
  const response = await fetch(`${baseUrl}${path}`, {
    method,
    headers: {
      ...(key ? { 'x-api-key': key } : {}),
      ...(body === undefined ? {} : { 'content-type': 'application/json' }),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const text = await response.text();
  const value = text ? JSON.parse(text) : undefined;
  if (!response.ok) throw new Error(value?.error ?? `HTTP_${response.status}`);
  return value;
}

async function waitForServer() {
  for (let i = 0; i < 80; i += 1) {
    if (server.exitCode !== null) throw new Error(`HAA server exited early\n${logs}`);
    try {
      const health = await api('/health');
      if (health?.status === 'ok') return;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`HAA server did not become healthy\n${logs}`);
}

async function waitForApproval(requestId) {
  for (let i = 0; i < 360; i += 1) {
    const request = await api(`/v1/approval-requests/${encodeURIComponent(requestId)}`, { key: keys.requester });
    if (request.state === 'APPROVED') return request;
    if (request.state !== 'PENDING') throw new Error(`Unexpected request state while waiting for WebAuthn: ${request.state}`);
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error('Timed out waiting for browser WebAuthn approval');
}

try {
  console.log('W7-T04.9 — browser WebAuthn → Touch ID → HAA approval → execution grant');
  console.log(`HAA: ${repoRoot}`);

  server = spawn(process.execPath, ['--experimental-strip-types', 'apps/haa-server/src/server.ts'], {
    cwd: repoRoot,
    env: {
      ...process.env,
      HAA_DB_PATH: join(temp, 'haa.db'),
      HAA_AUTHORITY_KEY_FILE: join(temp, 'authority-private.pem'),
      HAA_AUTHORITY_KEY_ID: 'w7-t04-webauthn-authority',
      HAA_DEV_BOOTSTRAP: '1',
      HAA_WEBAUTHN_ENABLED: '1',
      HAA_WEBAUTHN_UI: '1',
      HAA_WEBAUTHN_RP_ID: 'localhost',
      HAA_WEBAUTHN_ORIGIN: baseUrl,
      HAA_WEBAUTHN_RP_NAME: 'HAA WebAuthn Physical Gate',
      PORT: String(port),
      HOST: '127.0.0.1',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  server.stdout.on('data', (chunk) => { logs = `${logs}${chunk}`.slice(-20_000); });
  server.stderr.on('data', (chunk) => { logs = `${logs}${chunk}`.slice(-20_000); });
  await waitForServer();
  console.log('✓ HAA WebAuthn validation server healthy');

  const request = await api('/v1/approval-requests', {
    method: 'POST',
    key: keys.requester,
    body: {
      action,
      approverPrincipalId: 'human-dev',
      executorAudience: 'executor-dev',
      requestId: `w7-t04-${Date.now()}`,
      ttlMs: 10 * 60_000,
    },
  });
  console.log(`✓ PENDING request created: ${request.id}`);

  try {
    await api(`/v1/approval-requests/${encodeURIComponent(request.id)}/authorize`, {
      method: 'POST',
      key: keys.executor,
      body: { executionId: 'before-human', actualAction: action, actualState: { version: 'v1' } },
    });
    throw new Error('Executor unexpectedly authorized before human approval');
  } catch (error) {
    if (!String(error).includes('REQUEST_NOT_APPROVED:PENDING')) throw error;
  }
  console.log('✓ Executor blocked before browser ceremony');

  const url = `${baseUrl}/webauthn/approve?requestId=${encodeURIComponent(request.id)}#apiKey=${encodeURIComponent(keys.human)}`;
  console.log('\nBrowser interaction required:');
  console.log('  1. Register Touch ID credential');
  console.log('  2. Prepare exact approval and inspect displayed claims');
  console.log('  3. Approve with WebAuthn / Touch ID');
  console.log('\nAssurance reminder: the action display is web-origin protected, not a native trusted display.');
  console.log(`Expected RESOURCE: ${action.payload.resource}`);
  console.log(`Expected OPERATION: ${action.payload.operation}\n`);

  const opened = spawnSync('open', [url], { encoding: 'utf8' });
  if (opened.status !== 0) {
    console.log(`Open this local URL manually:\n${url}\n`);
  }

  const approved = await waitForApproval(request.id);
  console.log('✓ Browser WebAuthn assertion accepted; request APPROVED');
  if (approved.state !== 'APPROVED') throw new Error('Expected APPROVED');

  const executionId = `w7-t04-exec-${Date.now()}`;
  const grant = await api(`/v1/approval-requests/${encodeURIComponent(request.id)}/authorize`, {
    method: 'POST',
    key: keys.executor,
    body: { executionId, actualAction: action, actualState: { version: 'v1' } },
  });
  if (grant.schema !== 'haa.execution-grant.v1' || grant.executionId !== executionId) {
    throw new Error('Expected exact ExecutionGrant after WebAuthn approval');
  }
  console.log('✓ Exact ExecutionGrant issued after WebAuthn approval');

  const final = await api(`/v1/approval-requests/${encodeURIComponent(request.id)}`, { key: keys.requester });
  if (final.state !== 'CONSUMED') throw new Error(`Expected CONSUMED, got ${final.state}`);
  const audit = await api(`/v1/approval-requests/${encodeURIComponent(request.id)}/audit`, { key: keys.requester });
  const consumed = audit.filter((event) => event.eventType === 'CONSUMED');
  if (consumed.length !== 1) throw new Error(`Expected one CONSUMED event, got ${consumed.length}`);
  console.log('✓ Request CONSUMED exactly once');

  console.log('\nPASS W7-T04.9: browser WebAuthn → Touch ID → user-verified HAA evidence → exact grant\n');
} finally {
  if (server && server.exitCode === null) server.kill('SIGTERM');
  await rm(temp, { recursive: true, force: true });
}
