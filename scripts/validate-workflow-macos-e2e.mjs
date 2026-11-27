#!/usr/bin/env node
import { execFileSync, spawn, spawnSync } from 'node:child_process';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, isAbsolute } from 'node:path';
import { randomBytes } from 'node:crypto';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import { buildProvisionedMacApprover } from './lib/macos-approver.mjs';

if (process.platform !== 'darwin' || process.getuid?.() === 0 || !process.argv.includes('--synthetic-touch-id')) {
  throw new Error('Run as owner on macOS with explicit --synthetic-touch-id; no production activation');
}

const haaRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const workflowRoot = join(haaRoot, 'integrations/workflow-runtime');
const python = process.env.HAA_PYTHON ?? (process.env.VIRTUAL_ENV ? join(process.env.VIRTUAL_ENV, 'bin/python') : '');
if (!isAbsolute(python)) throw new Error('Activate the existing portable venv or set an absolute HAA_PYTHON');
const head = execFileSync('/usr/bin/git', ['-C', haaRoot, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
const status = () => execFileSync('/usr/bin/git', ['-C', haaRoot, 'status', '--porcelain'], { encoding: 'utf8' }).trim();
if (status()) throw new Error('CLEAN_CHECKOUT_REQUIRED');
const inherited = Object.fromEntries(Object.entries(process.env).filter(([k]) => !k.startsWith('HAA_') && !['PORT','HOST','PYTHONPATH','PYTHONHOME','PYTHONSTARTUP','PYTHONINSPECT','PYTHONUSERBASE','NODE_OPTIONS'].includes(k)));
const branch = 'synthetic-candidate';
const repository = 'fixture/workflow-physical';
const temp = await mkdtemp(join(tmpdir(), 'haa-workflow-physical-'));
const port = 8795;
const baseUrl = `http://127.0.0.1:${port}`;
const authenticatorId = `workflow-physical-${randomBytes(12).toString('hex')}`;
const approverPrincipalId = 'human-dev';
const executorAudience = 'executor-dev';
const keys = {
  requester: randomBytes(32).toString('hex'),
  human: randomBytes(32).toString('hex'),
  executor: randomBytes(32).toString('hex'),
};
let server;
let serverLogs = '';
let approver;
let physicalPassed = false;

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
  return spawnSync(python, ['-B', '-m', 'scripts.haa.adapter', ...args], {
    cwd: workflowRoot,
    encoding: 'utf8',
    timeout: 30000,
    env: { ...inherited, PYTHONNOUSERSITE: '1', PYTHONDONTWRITEBYTECODE: '1', ...env },
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
  console.log('Workflow HAA — isolated synthetic physical authority smoke');
  console.log('Validated checkout HEAD: '+head);
  run(python, ['-B', '-c', 'import cryptography; print(cryptography.__version__)']);
  // Never reuse a live server or the user's HAA credentials.
  // Random per-run role credentials are accepted only by this temporary server.
  server = spawn(process.execPath, ['--experimental-strip-types', 'apps/haa-server/src/server.ts'], {
    cwd: haaRoot,
    env: {
      ...inherited,
      HAA_WORKFLOW_PROFILES_ENABLED: '1',
      HAA_AGENT_KEY: keys.requester,
      HAA_HUMAN_KEY: keys.human,
      HAA_EXECUTOR_KEY: keys.executor,
      HAA_DB_PATH: join(temp, 'haa.db'),
      HAA_AUTHORITY_KEY_FILE: join(temp, 'authority-private.pem'),
      HAA_AUTHORITY_KEY_ID: 'workflow-physical-authority',
      HAA_DEV_BOOTSTRAP: '1',
      PORT: String(port),
      HOST: '127.0.0.1',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  server.stdout.on('data', (chunk) => { serverLogs = `${serverLogs}${chunk}`.slice(-20_000); });
  server.stderr.on('data', (chunk) => { serverLogs = `${serverLogs}${chunk}`.slice(-20_000); });
  await waitForServer();
  // An unrelated listener on the port cannot authenticate these random keys.
  console.log('✓ HAA validation server healthy; isolated role credentials');

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
      '--repository', repository,
      '--plan-id', 'workflow-physical-fixture',
      '--task-id', 'SYNTHETIC.PHYSICAL-SMOKE',
      '--session-id', `physical-${Date.now()}`,
      '--branch', branch,
      '--base-commit', head,
      '--allow-path', 'README.md',
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
    schema: 'workflow.plan-closure-manifest.v1',
    repository,
    planId: 'workflow-physical-fixture',
    planVersion: 'synthetic-v1',
    branch,
    finalCommitSha: head,
    requiredTasks: ['SYNTHETIC.PHYSICAL-SMOKE'],
    completedTasks: ['SYNTHETIC.PHYSICAL-SMOKE'],
    acceptedExceptions: [],
    unresolvedNonBlockers: [],
    validationSummary: { status: 'PASS', checks: ['synthetic-fixture-only'] },
    evidence: ['workflow-synthetic-physical-smoke'],
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

  if (status() || run('/usr/bin/git', ['-C', haaRoot, 'rev-parse', 'HEAD']) !== head) throw new Error('CHECKOUT_CHANGED');
  physicalPassed = true;
} finally {
  let cleanup = true;
  if (approver) {
    try { execFileSync(approver, ['--delete', '--authenticator-id', authenticatorId], { stdio: 'ignore', timeout: 15000 }); }
    catch { cleanup = false; }
  }
  if (server && server.exitCode === null && server.signalCode === null) {
    const exited = once(server, 'exit');
    server.kill('SIGTERM');
    const stopped = await Promise.race([exited.then(() => true), new Promise(r => setTimeout(() => r(false), 5000))]);
    if (!stopped) { server.kill('SIGKILL'); cleanup = false; }
  }
  if (cleanup) await rm(temp, { recursive: true, force: true });
  else throw new Error('CLEANUP_UNCERTAIN: temporary validation directory retained: '+temp);
}
if (physicalPassed) console.log(JSON.stringify({status:'PASS_WORKFLOW_PHYSICAL_AUTHORITY_ONLY',head,profiles:['workflow.task.start.v1','workflow.plan.close.v1'],host_isolation:'NOT_TESTED',actual_protected_runner:'NOT_CERTIFIED',activation:'NO_GO'}));
