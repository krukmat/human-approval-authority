import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z } from 'zod';
import { HaaClient } from '../../../packages/sdk-ts/src/index.ts';

const baseUrl = process.env.HAA_URL ?? 'http://127.0.0.1:8787';
const apiKey = process.env.HAA_API_KEY;
if (!apiKey) throw new Error('HAA_API_KEY is required');
const client = new HaaClient(baseUrl, apiKey);

const server = new McpServer({ name: 'human-approval-authority', version: '0.1.0' });

server.tool(
  'request_approval',
  'Request human approval for a typed HAA ActionSpec. This tool never approves or executes the action.',
  {
    actionType: z.string(),
    payload: z.record(z.string(), z.unknown()),
    preconditions: z.record(z.string(), z.unknown()).optional(),
    approverPrincipalId: z.string(),
    executorAudience: z.string(),
  },
  async ({ actionType, payload, preconditions, approverPrincipalId, executorAudience }) => {
    const request = await client.requestApproval({
      action: { schema: 'haa.action.v1', type: actionType, payload: payload as any, ...(preconditions ? { preconditions: preconditions as any } : {}) },
      approverPrincipalId,
      executorAudience,
    });
    return { content: [{ type: 'text', text: JSON.stringify({ requestId: request.id, state: request.state, actionDigest: request.actionDigest }) }] };
  },
);

server.tool(
  'approval_status',
  'Read the state of an existing human approval request.',
  { requestId: z.string() },
  async ({ requestId }) => {
    const request = await client.getApproval(requestId);
    return { content: [{ type: 'text', text: JSON.stringify({ requestId: request.id, state: request.state, actionDigest: request.actionDigest }) }] };
  },
);

// Deliberately no generic execute tool: execution belongs to a bounded executor that
// checks its own resource preconditions and obtains an ExecutionGrant from HAA.
await server.connect(new StdioServerTransport());
