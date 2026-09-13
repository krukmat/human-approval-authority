import type { ActionSpec, ApprovalRequest, ExecutionGrant } from '@haa/protocol';

export type { ActionSpec, ApprovalRequest, ExecutionGrant } from '@haa/protocol';

export interface RequestApprovalInput {
  action: ActionSpec;
  approverPrincipalId: string;
  executorAudience: string;
  requestId?: string;
  ttlMs?: number;
}

export interface AuthorizeInput {
  requestId: string;
  executionId: string;
  actualAction: ActionSpec;
  actualState?: Record<string, unknown>;
}

export class HaaApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly responseBody: unknown;

  constructor(status: number, code: string, responseBody: unknown) {
    super(code);
    this.name = 'HaaApiError';
    this.status = status;
    this.code = code;
    this.responseBody = responseBody;
  }
}

export class HaaClient {
  readonly baseUrl: string;
  readonly apiKey: string;

  constructor(baseUrl: string, apiKey: string) {
    this.baseUrl = baseUrl;
    this.apiKey = apiKey;
  }

  private async call<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(new URL(path, this.baseUrl), {
      ...init,
      headers: { 'content-type': 'application/json', 'x-api-key': this.apiKey, ...(init.headers ?? {}) },
    });

    const text = await response.text();
    let body: unknown;
    if (text) {
      try {
        body = JSON.parse(text);
      } catch {
        body = text;
      }
    }

    if (!response.ok) {
      const code = typeof body === 'object' && body !== null && 'error' in body && typeof (body as { error?: unknown }).error === 'string'
        ? (body as { error: string }).error
        : `HTTP_${response.status}`;
      throw new HaaApiError(response.status, code, body);
    }

    if (response.status === 204 || !text) return undefined as T;
    return body as T;
  }

  requestApproval(input: RequestApprovalInput): Promise<ApprovalRequest> {
    return this.call('/v1/approval-requests', { method: 'POST', body: JSON.stringify(input) });
  }

  getApproval(requestId: string): Promise<ApprovalRequest> {
    return this.call(`/v1/approval-requests/${encodeURIComponent(requestId)}`);
  }

  authorize(input: AuthorizeInput): Promise<ExecutionGrant> {
    return this.call(`/v1/approval-requests/${encodeURIComponent(input.requestId)}/authorize`, {
      method: 'POST',
      body: JSON.stringify({
        executionId: input.executionId,
        actualAction: input.actualAction,
        ...(input.actualState ? { actualState: input.actualState } : {}),
      }),
    });
  }
}
