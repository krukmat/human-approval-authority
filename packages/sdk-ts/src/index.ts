import type { ActionSpec, ApprovalRequest, ExecutionGrant } from '../../protocol/src/index.ts';

export class HaaClient {
  constructor(readonly baseUrl: string, readonly apiKey: string) {}

  private async call<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(new URL(path, this.baseUrl), {
      ...init,
      headers: { 'content-type': 'application/json', 'x-api-key': this.apiKey, ...(init.headers ?? {}) },
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({})) as { error?: string };
      throw new Error(body.error ?? `HTTP_${response.status}`);
    }
    if (response.status === 204) return undefined as T;
    return response.json() as Promise<T>;
  }

  requestApproval(input: { action: ActionSpec; approverPrincipalId: string; executorAudience: string; requestId?: string; ttlMs?: number }): Promise<ApprovalRequest> {
    return this.call('/v1/approval-requests', { method: 'POST', body: JSON.stringify(input) });
  }

  getApproval(requestId: string): Promise<ApprovalRequest> {
    return this.call(`/v1/approval-requests/${encodeURIComponent(requestId)}`);
  }

  authorize(input: { requestId: string; executionId: string; actualAction: ActionSpec; actualState?: Record<string, unknown> }): Promise<ExecutionGrant> {
    return this.call(`/v1/approval-requests/${encodeURIComponent(input.requestId)}/authorize`, {
      method: 'POST',
      body: JSON.stringify({ executionId: input.executionId, actualAction: input.actualAction, actualState: input.actualState }),
    });
  }
}
