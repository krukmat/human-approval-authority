#!/usr/bin/env node
import { execFileSync, spawn, spawnSync } from 'node:child_process';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { buildProvisionedMacApprover } from './lib/macos-approver.mjs';

if (process.platform !== 'darwin') {
  throw new Error('W4-T05 requires a real macOS host with Touch ID / Secure Enclave');
}

const repoRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const temp = await mkdtemp(join(tmpdir(), 'haa-agent-macos-validation-'));
const port = Number(process.env.HAA_VALIDATION_PORT ?? 8792);
const baseUrl = `http://127.0.0.1:${port}`;
const authenticatorId = `mac-agent-validation-${Date.now()}`;
const executionId = `exec-agent-${Date.now()}`;
let server;
let serverLogs = '';
let approver;
let mcpClient;

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
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`HAA server did not become healthy\n${serverLogs}`);
}

function runExecutor(requestId, id, actionPath, resourcePath) {
  return spawnSync(
    process.execPath,
    ['--experimental-strip-types', 'apps/reference-executor/src/index.ts', requestId, id, actionPath, resourcePath],
    {
      cwd: repoRoot,
      encoding: 'utf8',
      env: { ...process.env, HAA_URL: baseUrl, HAA_API_KEY: keys.executor },
    },
  );
}

function outputOf(result) {
  return `${result.stdout ?? ''}\n${result.stderr ?? ''}`;
}

try {
  console.log('W4-T05 — MCP agent → Touch ID → external executor validation');
  server = spawn(process.execPath, ['--experimental-strip-types', 'apps/haa-server/src/server.ts'], {
    cwd: repoRoot,
    env: {
      ...process.env,
      HAA_DB_PATH: join(temp, 'haa.db'),
      HAA_AUTHORITY_KEY_FILE: join(temp, 'authority-private.pem'),
      HAA_AUTHORITY_KEY_ID: 'agent-validation-authority',
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
    method: 'POST', key: keys.human, body: { ...enrollment, principalId: 'human-dev' },
  });
  console.log('✓ Secure Enclave authenticator registered');

  const authority = await api('/v1/authority-key');
  const authorityKeyPath = join(temp, 'authority-public.pem');
  await writeFile(authorityKeyPath, authority.publicKeyPem, 'utf8');

  const action = {
    schema: 'haa.action.v1',
    type: 'demo.action.v1',
    payload: { resource: 'agent-managed-resource', operation: 'deploy' },
    preconditions: { version: 'v1' },
  };
  const actionPath = join(temp, 'action.json');
  const resourcePath = join(temp, 'resource.json');
  await writeFile(actionPath, `${JSON.stringify(action, null, 2)}\n`, 'utf8');
  await writeFile(resourcePath, `${JSON.stringify({ name: 'agent-managed-resource', version: 'v1', lastOperation: null }, null, 2)}\n`, 'utf8');

  const mcpTransport = new StdioClientTransport({
    command: process.execPath,
    args: ['--experimental-strip-types', 'apps/mcp/src/server.ts'],
    env: { ...process.env, HAA_URL: baseUrl, HAA_API_KEY: keys.agent },
  });
  mcpClient = new Client({ name: 'haa-real-agent-gate', version: '0.1.0' });
  await mcpClient.connect(mcpTransport);
  const { tools } = await mcpClient.listTools();
  const toolNames = tools.map((tool) => tool.name).sort();
  if (JSON.stringify(toolNames) !== JSON.stringify(['approval_status', 'request_approval'])) {
    throw new Error(`Unexpected MCP surface: ${JSON.stringify(toolNames)}`);
  }
  console.log('✓ Agent MCP surface is request/status only');

  const toolResult = await mcpClient.callTool({
    name: 'request_approval',
    arguments: {
      actionType: action.type,
      payload: action.payload,
      preconditions: action.preconditions,
      approverPrincipalId: 'human-dev',
      executorAudience: 'executor-dev',
    },
  });
  const text = toolResult.content.find((item) => item.type === 'text')?.text;
  if (!text) throw new Error('request_approval returned no text payload');
  const requested = JSON.parse(text);
  const requestId = requested.requestId;
  if (!requestId || requested.state !== 'PENDING') throw new Error(`Unexpected MCP request result: ${text}`);
  console.log(`✓ Agent requested approval through MCP: ${requestId}`);

  const beforeApproval = runExecutor(requestId, executionId, actionPath, resourcePath);
  if (beforeApproval.status === 0 || !outputOf(beforeApproval).includes('REQUEST_NOT_APPROVED:PENDING')) {
    throw new Error(`Executor was not blocked before approval:\n${outputOf(beforeApproval)}`);
  }
  const untouched = JSON.parse(await readFile(resourcePath, 'utf8'));
  if (untouched.version !== 'v1' || untouched.lastOperation !== null) throw new Error('Resource changed before approval');
  console.log('✓ External executor blocked before human approval; resource unchanged');

  const challenge = await api(`/v1/approval-requests/${encodeURIComponent(requestId)}/challenges`, {
    method: 'POST', key: keys.human, body: { authenticatorId },
  });
  const challengePath = join(temp, 'challenge.json');
  await writeFile(challengePath, JSON.stringify(challenge, null, 2), 'utf8');

  console.log('\nTouch ID interaction expected now. Verify the trusted display before approving.\n');
  const evidence = JSON.parse(execFileSync(
    approver,
    ['--challenge', challengePath, '--authority-public-key', authorityKeyPath, '--authenticator-id', authenticatorId],
    { encoding: 'utf8', stdio: ['inherit', 'pipe', 'inherit'] },
  ));
  const receipt = await api('/v1/approval-evidence', { method: 'POST', key: keys.human, body: evidence });
  if (receipt?.schema !== 'haa.receipt.v1') throw new Error('Expected ApprovalReceipt');
  console.log('✓ Human Touch ID approval accepted');

  const execution = runExecutor(requestId, executionId, actionPath, resourcePath);
  if (execution.status !== 0) throw new Error(`Approved executor failed:\n${outputOf(execution)}`);
  const executionResult = JSON.parse(execution.stdout);
  if (executionResult.grant?.schema !== 'haa.execution-grant.v1' || executionResult.reused !== false) {
    throw new Error(`Unexpected first execution result: ${execution.stdout}`);
  }
  const changed = JSON.parse(await readFile(resourcePath, 'utf8'));
  if (changed.version !== `executed:${executionId}` || changed.lastOperation !== 'deploy') {
    throw new Error(`Executor did not apply expected exact action: ${JSON.stringify(changed)}`);
  }
  console.log('✓ External executor obtained grant then applied exact action');

  const retry = runExecutor(requestId, executionId, actionPath, resourcePath);
  if (retry.status !== 0) throw new Error(`Idempotent retry failed:\n${outputOf(retry)}`);
  const retryResult = JSON.parse(retry.stdout);
  if (retryResult.reused !== true || retryResult.grant.signature !== executionResult.grant.signature) {
    throw new Error('Retry did not reuse the original execution grant');
  }
  console.log('✓ Same executionId is idempotent after resource mutation');

  const second = runExecutor(requestId, `${executionId}-second`, actionPath, resourcePath);
  if (second.status === 0 || !outputOf(second).includes('REQUEST_NOT_APPROVED:CONSUMED')) {
    throw new Error(`Second execution was not rejected as consumed:\n${outputOf(second)}`);
  }
  console.log('✓ Different executionId rejected after consumption');

  const statusResult = await mcpClient.callTool({ name: 'approval_status', arguments: { requestId } });
  const statusText = statusResult.content.find((item) => item.type === 'text')?.text;
  const status = statusText ? JSON.parse(statusText) : null;
  if (status?.state !== 'CONSUMED') throw new Error(`Agent status did not observe CONSUMED: ${statusText}`);
  console.log('✓ Agent observes final CONSUMED status without execution capability');

  const audit = await api(`/v1/approval-requests/${requestId}/audit`, { key: keys.agent });
  const consumedEvents = audit.filter((event) => event.eventType === 'CONSUMED');
  if (consumedEvents.length !== 1) throw new Error(`Expected one CONSUMED audit event, got ${consumedEvents.length}`);
  console.log('✓ Exactly one execution consumption recorded');

  console.log('\nPASS W4-T05: real MCP agent → human Touch ID → bounded executor scenario\n');
} finally {
  if (mcpClient) {
    try { await mcpClient.close(); } catch {}
  }
  if (approver) {
    try { execFileSync(approver, ['--delete', '--authenticator-id', authenticatorId], { stdio: 'ignore' }); } catch {}
  }
  if (server && server.exitCode === null) server.kill('SIGTERM');
  await rm(temp, { recursive: true, force: true });
}
