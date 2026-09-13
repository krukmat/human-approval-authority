#!/usr/bin/env node
import { execFileSync, spawn } from 'node:child_process';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

if (process.platform !== 'darwin') {
  throw new Error('W3-T06 requires a real macOS host with Touch ID / Secure Enclave');
}

const repoRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const macPackage = join(repoRoot, 'macos', 'haa-approver');
const temp = await mkdtemp(join(tmpdir(), 'haa-macos-validation-'));
const port = Number(process.env.HAA_VALIDATION_PORT ?? 8791);
const baseUrl = `http://127.0.0.1:${port}`;
const authenticatorId = `mac-validation-${Date.now()}`;
let server;
let serverLogs = '';
let approver;

const keys = {
  agent: 'agent-dev-secret',
  human: 'human-dev-secret',
  executor: 'executor-dev-secret',
};

async function api(path, { method = 'GET', key, body } = {}) {
  const response = await fetch(`${baseUrl}${path}`, {
    method,
    headers: {
      ...(key ? { 'x-api-key': key } : {}),
      ...(body !== undefined ? { 'content-type': 'application/json' } : {}),
    },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : undefined;
  if (!response.ok) {
    const error = new Error(data?.error ?? `HTTP_${response.status}`);
    error.status = response.status;
    throw error;
  }
  return data;
}

async function expectError(label, operation, expected) {
  try {
    await operation();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (message.includes(expected)) {
      console.log(`✓ ${label}: ${expected}`);
      return;
    }
    throw new Error(`${label}: expected ${expected}, got ${message}`);
  }
  throw new Error(`${label}: expected ${expected}, operation succeeded`);
}

async function waitForServer() {
  for (let i = 0; i < 50; i += 1) {
    if (server.exitCode !== null) throw new Error(`HAA server exited early\n${serverLogs}`);
    try {
      const health = await api('/health');
      if (health?.status === 'ok') return;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`HAA server did not become healthy\n${serverLogs}`);
}

try {
  console.log('W3-T06 — macOS Secure Enclave / Touch ID end-to-end validation');
  server = spawn(process.execPath, ['--experimental-strip-types', 'apps/haa-server/src/server.ts'], {
    cwd: repoRoot,
    env: {
      ...process.env,
      HAA_DB_PATH: join(temp, 'haa.db'),
      HAA_AUTHORITY_KEY_FILE: join(temp, 'authority-private.pem'),
      HAA_AUTHORITY_KEY_ID: 'mac-validation-authority',
      HAA_DEV_BOOTSTRAP: '1',
      PORT: String(port),
      HOST: '127.0.0.1',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  server.stdout.on('data', (chunk) => { serverLogs = `${serverLogs}${chunk}`.slice(-20_000); });
  server.stderr.on('data', (chunk) => { serverLogs = `${serverLogs}${chunk}`.slice(-20_000); });
  await waitForServer();
  console.log('✓ HAA server healthy');

  execFileSync('swift', ['build', '-c', 'release'], { cwd: macPackage, stdio: 'inherit' });
  const binPath = execFileSync('swift', ['build', '-c', 'release', '--show-bin-path'], { cwd: macPackage, encoding: 'utf8' }).trim();
  approver = join(binPath, 'haa-approver');
  console.log('✓ macOS approver built');

  const enrollment = JSON.parse(execFileSync(approver, ['--enroll', '--authenticator-id', authenticatorId], { encoding: 'utf8' }));
  await api('/v1/authenticators', {
    method: 'POST',
    key: keys.human,
    body: { ...enrollment, principalId: 'human-dev' },
  });
  console.log(`✓ Secure Enclave authenticator enrolled: ${authenticatorId}`);

  const authority = await api('/v1/authority-key');
  const authorityKeyPath = join(temp, 'authority-public.pem');
  await writeFile(authorityKeyPath, authority.publicKeyPem, 'utf8');

  const action = {
    schema: 'haa.action.v1',
    type: 'demo.action.v1',
    payload: { resource: 'validation-service', operation: 'deploy' },
    preconditions: { version: 'v1' },
  };
  const requestId = `mac-validation-${Date.now()}`;
  const request = await api('/v1/approval-requests', {
    method: 'POST',
    key: keys.agent,
    body: {
      action,
      approverPrincipalId: 'human-dev',
      executorAudience: 'executor-dev',
      requestId,
      ttlMs: 5 * 60_000,
    },
  });
  console.log(`✓ Approval request created: ${request.id}`);

  const challenge = await api(`/v1/approval-requests/${encodeURIComponent(request.id)}/challenges`, {
    method: 'POST',
    key: keys.human,
    body: { authenticatorId },
  });
  const challengePath = join(temp, 'challenge.json');
  await writeFile(challengePath, JSON.stringify(challenge, null, 2), 'utf8');

  console.log('\nTouch ID interaction expected now. Verify the displayed action before approving.\n');
  const evidenceOutput = execFileSync(
    approver,
    ['--challenge', challengePath, '--authority-public-key', authorityKeyPath, '--authenticator-id', authenticatorId],
    { encoding: 'utf8', stdio: ['inherit', 'pipe', 'inherit'] },
  );
  const evidence = JSON.parse(evidenceOutput);
  const receipt = await api('/v1/approval-evidence', { method: 'POST', key: keys.human, body: evidence });
  if (receipt?.schema !== 'haa.receipt.v1') throw new Error('Expected haa.receipt.v1');
  console.log('✓ Touch ID evidence accepted and ApprovalReceipt issued');

  const mutatedAction = { ...action, payload: { ...action.payload, operation: 'delete' } };
  await expectError('mutated action denied', () => api(`/v1/approval-requests/${request.id}/authorize`, {
    method: 'POST',
    key: keys.executor,
    body: { executionId: 'exec-mutated', actualAction: mutatedAction, actualState: { version: 'v1' } },
  }), 'ACTION_DIGEST_MISMATCH');

  await expectError('stale precondition denied', () => api(`/v1/approval-requests/${request.id}/authorize`, {
    method: 'POST',
    key: keys.executor,
    body: { executionId: 'exec-stale', actualAction: action, actualState: { version: 'v2' } },
  }), 'STALE_APPROVAL');

  const grant = await api(`/v1/approval-requests/${request.id}/authorize`, {
    method: 'POST',
    key: keys.executor,
    body: { executionId: 'exec-success', actualAction: action, actualState: { version: 'v1' } },
  });
  if (grant?.schema !== 'haa.execution-grant.v1') throw new Error('Expected haa.execution-grant.v1');
  console.log('✓ Exact action authorized and consumed');

  const retry = await api(`/v1/approval-requests/${request.id}/authorize`, {
    method: 'POST',
    key: keys.executor,
    body: { executionId: 'exec-success', actualAction: action, actualState: { version: 'executed:exec-success' } },
  });
  if (retry.signature !== grant.signature) throw new Error('Idempotent retry returned a different grant');
  console.log('✓ Same executionId remains idempotent after resource state changes');

  await expectError('second execution denied', () => api(`/v1/approval-requests/${request.id}/authorize`, {
    method: 'POST',
    key: keys.executor,
    body: { executionId: 'exec-second', actualAction: action, actualState: { version: 'executed:exec-success' } },
  }), 'REQUEST_NOT_APPROVED:CONSUMED');

  const audit = await api(`/v1/approval-requests/${request.id}/audit`, { key: keys.agent });
  const events = audit.map((event) => event.eventType);
  const expectedEvents = ['REQUESTED', 'CHALLENGE_ISSUED', 'APPROVED', 'CONSUMED'];
  if (JSON.stringify(events) !== JSON.stringify(expectedEvents)) {
    throw new Error(`Unexpected audit lifecycle: ${JSON.stringify(events)}`);
  }
  console.log('✓ Audit lifecycle reconstructed exactly');

  console.log('\nPASS W3-T06: Apple Secure Enclave / Touch ID end-to-end gate\n');
} finally {
  if (approver) {
    try { execFileSync(approver, ['--delete', '--authenticator-id', authenticatorId], { stdio: 'ignore' }); } catch {}
  }
  if (server && server.exitCode === null) server.kill('SIGTERM');
  await rm(temp, { recursive: true, force: true });
}
