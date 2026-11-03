#!/usr/bin/env node
import { execFileSync, spawn, spawnSync } from 'node:child_process';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildProvisionedMacApprover } from './lib/macos-approver.mjs';

if (process.platform !== 'darwin') {
  throw new Error('DubBridge W2 physical gate requires a real macOS host with Touch ID / Secure Enclave');
}

const haaRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const dubbridgeRoot = resolve(
  process.env.HAA_DUBBRIDGE_REPO_PATH ?? join(haaRoot, '..', 'dubbridge'),
);
const temp = await mkdtemp(join(tmpdir(), 'haa-dubbridge-w2-'));
const port = Number(process.env.HAA_VALIDATION_PORT ?? 8795);
const baseUrl = `http://127.0.0.1:${port}`;
const authenticatorId = `dubbridge-w2-${Date.now()}`;
const approverPrincipalId = 'human-dev';
const executorAudience = 'executor-dev';
const keys = {
  requester: 'agent-dev-secret',
  human: 'human-dev-secret',
  executor: 'executor-dev-secret',
};
let server;
let serverLogs = '';
let approver;

function run(command, args, options = {}) {
  return execFileSync(command, args, { encoding: 'utf8', ...options }).trim();
}

function outputOf(result) {
  return `${result.stdout ?? ''}\n${result.stderr ?? ''}`;
}

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
  if (!response.ok) throw new Error(data?.error ?? `HTTP_${response.status}`);
  return data;
}

async function waitForServer() {
  for (let i = 0; i < 50; i += 1) {
    if (server.exitCode !== null) throw new Error(`HAA server exited early\n${serverLogs}`);
    try {
      const health = await api('/health');
      if (health?.status === 'ok') return;
    } catch {}
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 100));
  }
  throw new Error(`HAA server did not become healthy\n${serverLogs}`);
}

function pythonRun(python, args, env) {
  return spawnSync(python, ['-m', 'scripts.haa.adapter', ...args], {
    cwd: dubbridgeRoot,
    encoding: 'utf8',
    env: { ...process.env, ...env },
  });
}

async function exerciseAction({
  label,
  python,
  action,
  actionPath,
  requesterEnv,
  executorEnv,
  authorityKeyPath,
  executionId,
}) {
  await writeFile(actionPath, JSON.stringify(action, null, 2), 'utf8');

  const requested = pythonRun(python, ['request', actionPath], requesterEnv);
  if (requested.status !== 0) throw new Error(`${label} request failed:\n${outputOf(requested)}`);
  const requestSummary = JSON.parse(requested.stdout);
  if (requestSummary.state !== 'PENDING' || !requestSummary.requestId) {
    throw new Error(`${label} unexpected request summary: ${requested.stdout}`);
  }
  const requestId = requestSummary.requestId;
  console.log(`✓ ${label}: PENDING request ${requestId}`);

  const beforeApproval = pythonRun(
    python,
    ['authorize-and-verify', requestId, executionId, actionPath],
    executorEnv,
  );
  if (
    beforeApproval.status === 0
    || !outputOf(beforeApproval).includes('REQUEST_NOT_APPROVED:PENDING')
  ) {
    throw new Error(`${label}: executor was not blocked before approval:\n${outputOf(beforeApproval)}`);
  }
  console.log(`✓ ${label}: executor blocked before Touch ID`);

  const challenge = await api(
    `/v1/approval-requests/${encodeURIComponent(requestId)}/challenges`,
    {
      method: 'POST',
      key: keys.human,
      body: { authenticatorId },
    },
  );
  const challengePath = join(temp, `${label.toLowerCase().replaceAll(' ', '-')}-challenge.json`);
  await writeFile(challengePath, JSON.stringify(challenge, null, 2), 'utf8');

  console.log(`\nTouch ID expected for ${label}. Verify the trusted display before approving.\n`);
  const evidence = JSON.parse(
    execFileSync(
      approver,
      [
        '--challenge', challengePath,
        '--authority-public-key', authorityKeyPath,
        '--authenticator-id', authenticatorId,
      ],
      { encoding: 'utf8', stdio: ['inherit', 'pipe', 'inherit'] },
    ),
  );
  const receipt = await api('/v1/approval-evidence', {
    method: 'POST',
    key: keys.human,
    body: evidence,
  });
  if (receipt?.schema !== 'haa.receipt.v1') throw new Error(`${label}: missing ApprovalReceipt`);
  console.log(`✓ ${label}: Touch ID approval accepted`);

  const authorized = pythonRun(
    python,
    ['authorize-and-verify', requestId, executionId, actionPath],
    executorEnv,
  );
  if (authorized.status !== 0) {
    throw new Error(`${label}: detached verification failed:\n${outputOf(authorized)}`);
  }
  const verified = JSON.parse(authorized.stdout);
  if (verified.status !== 'VERIFIED' || verified.executionId !== executionId) {
    throw new Error(`${label}: unexpected verification result ${authorized.stdout}`);
  }
  console.log(`✓ ${label}: authorizeAndConsume + detached verification PASS`);

  const finalStatus = pythonRun(python, ['status', requestId], requesterEnv);
  if (finalStatus.status !== 0 || JSON.parse(finalStatus.stdout).state !== 'CONSUMED') {
    throw new Error(`${label}: expected final CONSUMED state\n${outputOf(finalStatus)}`);
  }
  console.log(`✓ ${label}: final state CONSUMED`);
}

try {
  console.log('DubBridge W2 — HAA Touch ID authority smoke');
  console.log(`HAA: ${haaRoot}`);
  console.log(`DubBridge: ${dubbridgeRoot}`);

  run('git', ['-C', dubbridgeRoot, 'rev-parse', '--is-inside-work-tree']);
  const head = run('git', ['-C', dubbridgeRoot, 'rev-parse', 'HEAD']);
  const branch = run('git', ['-C', dubbridgeRoot, 'branch', '--show-current']) || 'detached-head';

  const pythonCommand = process.env.HAA_PYTHON ?? 'python3';
  run(pythonCommand, ['--version']);
  const venv = join(temp, 'venv');
  execFileSync(pythonCommand, ['-m', 'venv', venv], { stdio: 'inherit' });
  const python = join(venv, 'bin', 'python');
  execFileSync(
    python,
    ['-m', 'pip', 'install', '--disable-pip-version-check', '-r', join(dubbridgeRoot, 'scripts/haa/requirements.txt')],
    { stdio: 'inherit' },
  );
  execFileSync(join(dubbridgeRoot, 'scripts/haa/run-tests.sh'), [], {
    cwd: dubbridgeRoot,
    env: { ...process.env, PATH: `${join(venv, 'bin')}:${process.env.PATH ?? ''}` },
    stdio: 'inherit',
  });
  console.log('✓ DubBridge W2 authority unit gate PASS');

  server = spawn(process.execPath, ['--experimental-strip-types', 'apps/haa-server/src/server.ts'], {
    cwd: haaRoot,
    env: {
      ...process.env,
      HAA_DB_PATH: join(temp, 'haa.db'),
      HAA_AUTHORITY_KEY_FILE: join(temp, 'authority-private.pem'),
      HAA_AUTHORITY_KEY_ID: 'dubbridge-w2-authority',
      HAA_DEV_BOOTSTRAP: '1',
      PORT: String(port),
      HOST: '127.0.0.1',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  server.stdout.on('data', (chunk) => { serverLogs = `${serverLogs}${chunk}`.slice(-20_000); });
  server.stderr.on('data', (chunk) => { serverLogs = `${serverLogs}${chunk}`.slice(-20_000); });
  await waitForServer();
  console.log('✓ HAA validation server healthy');

  const builtApprover = buildProvisionedMacApprover({ repoRoot: haaRoot, buildRoot: temp });
  approver = builtApprover.executablePath;
  const enrollment = JSON.parse(
    execFileSync(
      approver,
      ['--enroll', '--authenticator-id', authenticatorId],
      { encoding: 'utf8' },
    ),
  );
  await api('/v1/authenticators', {
    method: 'POST',
    key: keys.human,
    body: { ...enrollment, principalId: approverPrincipalId },
  });
  console.log('✓ Secure Enclave authenticator registered');

  const authority = await api('/v1/authority-key');
  const authorityKeyPath = join(temp, 'authority-public.pem');
  await writeFile(authorityKeyPath, authority.publicKeyPem, 'utf8');

  const requesterEnv = {
    HAA_BASE_URL: baseUrl,
    HAA_REQUESTER_API_KEY: keys.requester,
    HAA_APPROVER_PRINCIPAL_ID: approverPrincipalId,
    HAA_EXECUTOR_AUDIENCE: executorAudience,
  };
  const executorEnv = {
    HAA_BASE_URL: baseUrl,
    HAA_EXECUTOR_API_KEY: keys.executor,
    HAA_EXECUTOR_AUDIENCE: executorAudience,
  };

  const taskBuild = pythonRun(
    python,
    [
      'build-task-start',
      '--plan-id', 'haa-hitl-integration',
      '--task-id', 'W2.PHYSICAL-SMOKE',
      '--session-id', `physical-${Date.now()}`,
      '--branch', branch,
      '--base-commit', head,
      '--allow-path', 'scripts/haa/**',
      '--capability', 'review',
      '--capability', 'test',
      '--lease-ttl-seconds', '300',
    ],
    {},
  );
  if (taskBuild.status !== 0) throw new Error(`Task action build failed:\n${outputOf(taskBuild)}`);
  const taskAction = JSON.parse(taskBuild.stdout);
  await exerciseAction({
    label: 'TASK START',
    python,
    action: taskAction,
    actionPath: join(temp, 'task-start-action.json'),
    requesterEnv,
    executorEnv,
    authorityKeyPath,
    executionId: `task-exec-${Date.now()}`,
  });

  const closureManifest = {
    schema: 'dubbridge.plan-closure-manifest.v1',
    repository: 'krukmat/dubbridge',
    planId: 'haa-hitl-integration',
    planVersion: 'w2-smoke',
    branch,
    finalCommitSha: head,
    requiredTasks: ['W2.PHYSICAL-SMOKE'],
    completedTasks: ['W2.PHYSICAL-SMOKE'],
    acceptedExceptions: [],
    unresolvedNonBlockers: [],
    validationSummary: { status: 'PASS', checks: ['authority-unit-gate'] },
    evidence: ['dubbridge-w2-physical-smoke'],
  };
  const manifestPath = join(temp, 'plan-closure-manifest.json');
  await writeFile(manifestPath, JSON.stringify(closureManifest, null, 2), 'utf8');
  const closeBuild = pythonRun(python, ['build-plan-close', manifestPath], {});
  if (closeBuild.status !== 0) throw new Error(`Plan-close action build failed:\n${outputOf(closeBuild)}`);
  const closeAction = JSON.parse(closeBuild.stdout);
  await exerciseAction({
    label: 'PLAN CLOSE',
    python,
    action: closeAction,
    actionPath: join(temp, 'plan-close-action.json'),
    requesterEnv,
    executorEnv,
    authorityKeyPath,
    executionId: `close-exec-${Date.now()}`,
  });

  console.log('\nPASS DubBridge W2: task-start + plan-close Touch ID authority smoke\n');
} finally {
  if (approver) {
    try {
      execFileSync(approver, ['--delete', '--authenticator-id', authenticatorId], { stdio: 'ignore' });
    } catch {}
  }
  if (server && server.exitCode === null) server.kill('SIGTERM');
  await rm(temp, { recursive: true, force: true });
}
