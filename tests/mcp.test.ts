import test from 'node:test';
import assert from 'node:assert/strict';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';

test('MCP adapter exposes only bounded approval tools', async () => {
  const env = Object.fromEntries(
    Object.entries(process.env).filter((entry): entry is [string, string] => typeof entry[1] === 'string'),
  );
  const transport = new StdioClientTransport({
    command: process.execPath,
    args: ['--experimental-strip-types', 'apps/mcp/src/server.ts'],
    env: {
      ...env,
      HAA_API_KEY: 'mcp-smoke-key',
      HAA_URL: 'http://127.0.0.1:9',
    },
  });
  const client = new Client({ name: 'haa-mcp-smoke', version: '0.1.0' });

  try {
    await client.connect(transport);
    const { tools } = await client.listTools();
    const names = tools.map((tool) => tool.name).sort();
    assert.deepEqual(names, ['approval_status', 'request_approval']);
    assert.equal(names.some((name) => name.includes('execute') || name.includes('authorize')), false);
  } finally {
    await client.close();
  }
});
