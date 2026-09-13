#!/usr/bin/env node
import { execFileSync, spawn, spawnSync } from 'node:child_process';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildProvisionedMacApprover } from './lib/macos-approver.mjs';

if (process.platform !== 'darwin') {
  throw new Error('W8-T09 requires a real macOS host with Touch ID / Secure Enclave');
}

function arg(name) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : undefined;
}

const testCase = arg('--case');
const cases = new Set(['approve', 'escape', 'window-close', 'timeout', 'challenge-expired']);
if (!testCase || !cases.has(testCase)) {
  throw new Error('usage: npm run validate:macos-ceremony -- --case <approve|escape|window-close|timeout|challenge-expired>');
}

const expectedReason = {
  escape: 'USER_ESCAPE',
  'window-close': 'WINDOW_CLOSED',
  timeout: 'TIMEOUT',
  'challenge-expired': 'CHALLENGE_EXPIRED',
}[testCase];

const repoRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const temp = await mkdtemp(join(tmpdir(), 'haa-macos-ceremony-'));
const port = Number(process.env.HAA_CEREMONY_VALIDATION_PORT ?? 8793);
const baseUrl = `http://127.0.0.1:${port}`;
const authenticatorId = `mac-ceremony-${Date.now()}`;
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

function challengePayload(challenge) {
  return JSON.parse(Buffer.from(challenge.payload, 'base64url').toString('utf8'));
}

async function waitUntil(timestamp) {
  const delay = new Date(timestamp).getTime() - Date.now() + 250;
  if (delay > 0) {
    console.log(`Waiting for signed challenge expiry at ${timestamp}...`);
    await new Promise((resolve) => setTimeout(resolve, delay));
  }
}

function runApprover(executable, challengePath, authorityKeyPath, extraArgs = []) {
  const result = spawnSync(executable, [
    '--challenge', challengePath,
    '--authority-public-key', authorityKeyPath,
    '--authenticator-id', authenticatorId,
    ...extraArgs,
  ], {
    encoding: 'utf8',
    stdio: ['inherit', 'pipe', 'inherit'],
  });

  if (result.error) throw result.error;
  const stdout = result.stdout?.trim();
  if (!stdout) throw new Error(`Approver produced no JSON output (status=${result.status})`);
  let body;
  try {
    body = JSON.parse(stdout);
  } catch {
    throw new Error(`Approver returned non-JSON output: ${stdout}`);
  }
  return { status: result.status, body };
}

try {
  console.log(`W8-T09 — physical macOS ceremony validation (${testCase})`);
  server = spawn(process.execPath, ['--experimental-strip-types', 'apps/haa-server/src/server.ts'], {
    cwd: repoRoot,
    env: {
      ...process.env,
      HAA_DB_PATH: join(temp, 'haa.db'),
      HAA_AUTHORITY_KEY_FILE: join(temp, 'authority-private.pem'),
      HAA_AUTHORITY_KEY_ID: 'mac-ceremony-authority',
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

  const builtApprover = buildProvisionedMacApprover({ repoRoot, buildRoot: temp });
  approver = builtApprover.executablePath;
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
    payload: { resource: `ceremony-${testCase}`, operation: 'validate' },
    preconditions: { version: 'v1' },
  };
  const requestId = `mac-ceremony-${testCase}-${Date.now()}`;
  const request = await api('/v1/approval-requests', {
    method: 'POST',
    key: keys.agent,
    body: {
      action,
      approverPrincipalId: 'human-dev',
      executorAudience: 'executor-dev',
      requestId,
      ttlMs: 10 * 60_000,
    },
  });
  const challenge = await api(`/v1/approval-requests/${encodeURIComponent(request.id)}/challenges`, {
    method: 'POST',
    key: keys.human,
    body: { authenticatorId },
  });
  const challengePath = join(temp, 'challenge.json');
  await writeFile(challengePath, JSON.stringify(challenge, null, 2), 'utf8');

  if (testCase === 'escape') console.log('\nPress Esc in the HAA ceremony window.\n');
  if (testCase === 'window-close') console.log('\nClose the HAA ceremony window using its standard close control.\n');
  if (testCase === 'approve') console.log('\nApprove the exact displayed action with Touch ID.\n');
  if (testCase === 'challenge-expired') await waitUntil(challengePayload(challenge).expiresAt);

  const extraArgs = testCase === 'timeout' ? ['--timeout-seconds', '5'] : [];
  const approverResult = runApprover(approver, challengePath, authorityKeyPath, extraArgs);

  if (testCase === 'approve') {
    if (approverResult.status !== 0 || approverResult.body.schema !== 'haa.evidence.v1') {
      throw new Error(`Expected positive ApprovalEvidence, got status=${approverResult.status} ${JSON.stringify(approverResult.body)}`);
    }
    const receipt = await api('/v1/approval-evidence', {
      method: 'POST',
      key: keys.human,
      body: approverResult.body,
    });
    if (receipt?.schema !== 'haa.receipt.v1') throw new Error('Expected haa.receipt.v1');
    const grant = await api(`/v1/approval-requests/${request.id}/authorize`, {
      method: 'POST',
      key: keys.executor,
      body: { executionId: `exec-${testCase}`, actualAction: action, actualState: { version: 'v1' } },
    });
    if (grant?.schema !== 'haa.execution-grant.v1') throw new Error('Expected haa.execution-grant.v1');
    console.log('✓ APPROVE produced verified evidence, receipt and exact ExecutionGrant');
  } else {
    if (approverResult.status !== 3) {
      throw new Error(`Expected reject exit status 3, got ${approverResult.status}`);
    }
    if (approverResult.body.outcome !== 'REJECT' || approverResult.body.reason !== expectedReason) {
      throw new Error(`Expected REJECT/${expectedReason}, got ${JSON.stringify(approverResult.body)}`);
    }
    const rejection = await api(`/v1/approval-requests/${request.id}/reject`, {
      method: 'POST',
      key: keys.human,
      body: {
        challengeDigest: approverResult.body.challengeDigest,
        reason: approverResult.body.reason,
      },
    });
    if (rejection.state !== 'REJECTED' || rejection.reason !== expectedReason) {
      throw new Error(`Unexpected rejection record: ${JSON.stringify(rejection)}`);
    }
    const expectedAssurance = testCase === 'escape'
      ? 'explicit-human-negative-action'
      : 'fail-closed-terminal';
    if (rejection.assurance !== expectedAssurance) {
      throw new Error(`Expected assurance ${expectedAssurance}, got ${rejection.assurance}`);
    }
    await expectError('rejected ceremony cannot authorize', () => api(`/v1/approval-requests/${request.id}/authorize`, {
      method: 'POST',
      key: keys.executor,
      body: { executionId: `exec-${testCase}`, actualAction: action, actualState: { version: 'v1' } },
    }), 'REQUEST_NOT_APPROVED:REJECTED');

    const audit = await api(`/v1/approval-requests/${request.id}/audit`, { key: keys.human });
    const final = audit.at(-1);
    if (final?.eventType !== 'REJECTED' || final.details?.reason !== expectedReason || final.details?.assurance !== expectedAssurance) {
      throw new Error(`Unexpected rejection audit: ${JSON.stringify(final)}`);
    }
    console.log(`✓ REJECT/${expectedReason} recorded with ${expectedAssurance}; no execution authority`);
  }

  console.log(`\nPASS W8-T09 case: ${testCase}\n`);
} finally {
  if (approver) {
    try { execFileSync(approver, ['--delete', '--authenticator-id', authenticatorId], { stdio: 'ignore' }); } catch {}
  }
  if (server && server.exitCode === null) server.kill('SIGTERM');
  await rm(temp, { recursive: true, force: true });
}
