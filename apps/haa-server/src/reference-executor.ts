import type { ActionSpec, ExecutionGrant, JsonValue } from '../../../packages/protocol/src/index.ts';
import type { HaaApplication } from './application.ts';

export class ReferenceResource {
  readonly name: string;
  version: string;
  lastOperation: string | null = null;
  constructor(name: string, version = 'v1') { this.name = name; this.version = version; }
}

export class ReferenceExecutor {
  private readonly app: HaaApplication;
  private readonly apiKey: string;
  constructor(app: HaaApplication, apiKey: string) { this.app = app; this.apiKey = apiKey; }

  execute(args: { requestId: string; executionId: string; action: ActionSpec; resource: ReferenceResource; now?: Date }): ExecutionGrant {
    const resourceName = args.action.payload.resource;
    if (resourceName !== args.resource.name) throw new Error('RESOURCE_MISMATCH');
    const actualState: Record<string, JsonValue> = { version: args.resource.version };
    const grant = this.app.authorizeAndConsume({
      apiKey: this.apiKey,
      requestId: args.requestId,
      executionId: args.executionId,
      actualAction: args.action,
      actualState,
      ...(args.now ? { now: args.now } : {}),
    });
    args.resource.lastOperation = String(args.action.payload.operation);
    args.resource.version = `executed:${args.executionId}`;
    return grant;
  }
}
