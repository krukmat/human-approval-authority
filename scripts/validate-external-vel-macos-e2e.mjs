#!/usr/bin/env node
import { execFileSync, spawn, spawnSync } from 'node:child_process';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildProvisionedMacApprover } from './lib/macos-approver.mjs';

if (process.platform !== 'darwin') {
  throw new Error('W9-T06 requires a real macOS host with Touch ID / Secure Enclave');
}

const haaRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const velRoot = resolve(process.env.HAA_VEL_REPO_PATH ?? join(haaRoot, '..', 'verifiable-event-ledger'));
const temp = await mkdtemp(join(tmpdir(), 'haa-w9-vel-'));
const port = Number(process.env.HAA_VALIDATION_PORT ?? 8794);
const baseUrl = `http://127.0.0.1:${port}`;
const authenticatorId = `w9-vel-${Date.now()}`;
const executionId = `w9-exec-${Date.now()}`;
const repository = 'krukmat/verifiable-event-ledger';
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
  return execFileSync(command, args, {
    encoding: 'utf8',
    ...options,
  }).trim();
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

function pythonRun(python, module, args, env) {
  return spawnSync(python, ['-m', module, ...args], {
    encoding: 'utf8',
    env: { ...process.env, ...env },
  });
}

try {
  console.log('W9-T06 — external VEL requester → HAA → Touch ID → external VEL executor');
  console.log(`HAA: ${haaRoot}`);
  console.log(`VEL: ${velRoot}`);

  run('git', ['-C', velRoot, 'rev-parse', '--is-inside-work-tree']);
  const velMain = run('git', ['-C', velRoot, 'rev-parse', 'main']);
  console.log(`✓ External consumer available at main ${velMain}`);

  const pythonCommand = process.env.HAA_PYTHON ?? 'python3.12';
  run(pythonCommand, ['--version']);
  const venv = join(temp, 'venv');
  execFileSync(pythonCommand, ['-m', 'venv', venv], { stdio: 'inherit' });
  const python = join(venv, 'bin', 'python');
  execFileSync(python, ['-m', 'pip', 'install', '--disable-pip-version-check', '-e', velRoot], { stdio: 'inherit' });
  console.log('✓ External VEL Python package installed in isolated validation environment');

  const work = join(temp, 'vel-work');
  execFileSync('git', ['clone', '--quiet', '--no-local', '--branch', 'main', velRoot, work]);
  run('git', ['-C', work, 'config', 'user.name', 'HAA W9 Validation']);
  run('git', ['-C', work, 'config', 'user.email', 'haa-w9@example.invalid']);
  const targetBefore = run('git', ['-C', work, 'rev-parse', 'HEAD']);
  run('git', ['-C', work, 'checkout', '-q', '-b', 'w9-haa-source']);
  await writeFile(
    join(work, 'w9-haa-physical-proof.txt'),
    `HAA W9-T06 physical integration proof\ntarget-before=${targetBefore}\ncreated-at=${new Date().toISOString()}\n`,
    'utf8',
  );
  run('git', ['-C', work, 'add', 'w9-haa-physical-proof.txt']);
  run('git', ['-C', work, 'commit', '-q', '-m', 'test: W9 HAA physical integration probe']);
  const sourceCommit = run('git', ['-C', work, 'rev-parse', 'HEAD']);
  run('git', ['-C', work, 'checkout', '-q', 'main']);
  console.log(`✓ Temporary external merge fixture prepared`);
  console.log(`  targetBefore=${targetBefore}`);
  console.log(`  sourceCommit=${sourceCommit}`);

  server = spawn(process.execPath, ['--experimental-strip-types', 'apps/haa-server/src/server.ts'], {
    cwd: haaRoot,
    env: {
      ...process.env,
      HAA_DB_PATH: join(temp, 'haa.db'),
      HAA_AUTHORITY_KEY_FILE: join(temp, 'authority-private.pem'),
      HAA_AUTHORITY_KEY_ID: 'w9-external-validation-authority',
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
  const enrollment = JSON.parse(execFileSync(
    approver,
    ['--enroll', '--authenticator-id', authenticatorId],
    { encoding: 'utf8' },
  ));
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
  const requestedResult = pythonRun(
    python,
    'veriledger.haa_reference',
    [
      'request-merge',
      '--repository', repository,
      '--source-commit', sourceCommit,
      '--target-branch', 'main',
      '--target-before', targetBefore,
    ],
    requesterEnv,
  );
  if (requestedResult.status !== 0) throw new Error(`External requester failed:\n${outputOf(requestedResult)}`);
  const requested = JSON.parse(requestedResult.stdout);
  const requestId = requested.id;
  if (!requestId || requested.state !== 'PENDING') {
    throw new Error(`Unexpected external request result: ${requestedResult.stdout}`);
  }
  console.log(`✓ External VEL requester created PENDING request: ${requestId}`);

  const executorArgs = [
    '--request-id', requestId,
    '--execution-id', executionId,
    '--repo-path', work,
    '--repository', repository,
    '--source-commit', sourceCommit,
    '--target-branch', 'main',
    '--target-before', targetBefore,
  ];
  const executorEnv = {
    HAA_BASE_URL: baseUrl,
    HAA_EXECUTOR_API_KEY: keys.executor,
    HAA_EXECUTOR_AUDIENCE: executorAudience,
    HAA_EXPECTED_REPOSITORY: repository,
  };
  const beforeApproval = pythonRun(python, 'veriledger.haa_executor', executorArgs, executorEnv);
  if (beforeApproval.status === 0 || !outputOf(beforeApproval).includes('REQUEST_NOT_APPROVED:PENDING')) {
    throw new Error(`External executor was not blocked before approval:\n${outputOf(beforeApproval)}`);
  }
  if (run('git', ['-C', work, 'rev-parse', 'HEAD']) !== targetBefore) {
    throw new Error('External Git target changed before human approval');
  }
  console.log('✓ External executor blocked before approval; Git target unchanged');

  const challenge = await api(`/v1/approval-requests/${encodeURIComponent(requestId)}/challenges`, {
    method: 'POST',
    key: keys.human,
    body: { authenticatorId },
  });
  const challengePath = join(temp, 'challenge.json');
  await writeFile(challengePath, JSON.stringify(challenge, null, 2), 'utf8');

  console.log('\nTouch ID interaction expected now.');
  console.log('Confirm the trusted display shows:');
  console.log(`  REPOSITORY: ${repository}`);
  console.log(`  SOURCE: ${sourceCommit}`);
  console.log('  TARGET: main');
  console.log(`  TARGET BEFORE: ${targetBefore}\n`);

  const evidence = JSON.parse(execFileSync(
    approver,
    [
      '--challenge', challengePath,
      '--authority-public-key', authorityKeyPath,
      '--authenticator-id', authenticatorId,
    ],
    { encoding: 'utf8', stdio: ['inherit', 'pipe', 'inherit'] },
  ));
  const receipt = await api('/v1/approval-evidence', {
    method: 'POST',
    key: keys.human,
    body: evidence,
  });
  if (receipt?.schema !== 'haa.receipt.v1') throw new Error('Expected ApprovalReceipt');
  console.log('✓ Human Touch ID approval accepted');

  const execution = pythonRun(python, 'veriledger.haa_executor', executorArgs, executorEnv);
  if (execution.status !== 0) throw new Error(`External approved executor failed:\n${outputOf(execution)}`);
  const executionResult = JSON.parse(execution.stdout);
  if (executionResult.status !== 'MERGED' || executionResult.head !== sourceCommit) {
    throw new Error(`Unexpected external execution result: ${execution.stdout}`);
  }
  const finalHead = run('git', ['-C', work, 'rev-parse', 'HEAD']);
  if (finalHead !== sourceCommit) throw new Error(`Expected final HEAD ${sourceCommit}, got ${finalHead}`);
  console.log('✓ External VEL executor obtained/verifed grant and applied exact fast-forward merge');

  const statusResult = pythonRun(python, 'veriledger.haa_reference', ['status', requestId], requesterEnv);
  if (statusResult.status !== 0) throw new Error(`External status failed:\n${outputOf(statusResult)}`);
  const finalStatus = JSON.parse(statusResult.stdout);
  if (finalStatus.state !== 'CONSUMED') throw new Error(`Expected CONSUMED, got ${statusResult.stdout}`);
  console.log('✓ External requester observes final CONSUMED state without execution authority');

  const audit = await api(`/v1/approval-requests/${encodeURIComponent(requestId)}/audit`, { key: keys.requester });
  const consumed = audit.filter((event) => event.eventType === 'CONSUMED');
  if (consumed.length !== 1) throw new Error(`Expected exactly one CONSUMED event, got ${consumed.length}`);
  console.log('✓ Exactly one execution consumption recorded');

  console.log('\nPASS W9-T06: external repository → HAA → Touch ID → detached-verifying external executor\n');
} finally {
  if (approver) {
    try {
      execFileSync(approver, ['--delete', '--authenticator-id', authenticatorId], { stdio: 'ignore' });
    } catch {}
  }
  if (server && server.exitCode === null) server.kill('SIGTERM');
  await rm(temp, { recursive: true, force: true });
}
