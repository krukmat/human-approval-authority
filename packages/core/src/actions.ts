import type { ActionSpec, DisplayClaim, JsonValue } from '../../protocol/src/index.ts';
import { digestJson } from './canonical.ts';

export interface ActionProfile {
  type: string;
  validate(action: ActionSpec): void;
  displayClaims(action: ActionSpec): DisplayClaim[];
  validatePreconditions(action: ActionSpec, actualState?: Record<string, JsonValue>): void;
}

function requireString(payload: Record<string, JsonValue>, key: string): string {
  const value = payload[key];
  if (typeof value !== 'string' || value.length === 0) throw new Error(`Invalid ${key}`);
  return value;
}

function requireInteger(
  payload: Record<string, JsonValue>,
  key: string,
  minimum: number,
  maximum?: number,
): number {
  const value = payload[key];
  if (typeof value !== 'number' || !Number.isInteger(value) || value < minimum) {
    throw new Error(`Invalid ${key}`);
  }
  if (maximum !== undefined && value > maximum) throw new Error(`Invalid ${key}`);
  return value;
}

function requireStringArray(payload: Record<string, JsonValue>, key: string): string[] {
  const value = payload[key];
  if (!Array.isArray(value) || value.length === 0) throw new Error(`Invalid ${key}`);
  if (value.some((item) => typeof item !== 'string' || item.length === 0)) {
    throw new Error(`Invalid ${key}`);
  }
  return value as string[];
}

function assertSortedUnique(values: string[], key: string): void {
  if (new Set(values).size !== values.length) throw new Error(`Invalid ${key}`);
  const sorted = [...values].sort();
  if (values.some((value, index) => value !== sorted[index])) throw new Error(`Invalid ${key}`);
}

function assertRepositoryPath(value: string): void {
  if (
    value.startsWith('/')
    || value.includes('\\')
    || value.split('/').some((part) => part === '' || part === '.' || part === '..')
  ) {
    throw new Error('Invalid allowedPaths');
  }
}

function assertExactKeys(value: Record<string, unknown>, allowed: readonly string[], label: string): void {
  const allowedSet = new Set(allowed);
  const unexpected = Object.keys(value).filter((key) => !allowedSet.has(key));
  if (unexpected.length > 0) throw new Error(`UNEXPECTED_${label}_FIELD:${unexpected.sort().join(',')}`);
}

function assertActionEnvelope(action: ActionSpec): void {
  assertExactKeys(action as unknown as Record<string, unknown>, ['schema', 'type', 'payload', 'preconditions'], 'ACTION');
  if (action.schema !== 'haa.action.v1') throw new Error(`UNSUPPORTED_ACTION_SCHEMA:${String(action.schema)}`);
}

function requireActualState(
  actualState: Record<string, JsonValue> | undefined,
  keys: readonly string[],
): Record<string, JsonValue> {
  if (!actualState) throw new Error('STALE_APPROVAL');
  try {
    assertExactKeys(actualState, keys, 'ACTUAL_STATE');
  } catch {
    throw new Error('STALE_APPROVAL');
  }
  return actualState;
}

function assertSameString(
  payload: Record<string, JsonValue>,
  payloadKey: string,
  actualState: Record<string, JsonValue>,
  actualKey = payloadKey,
): void {
  if (actualState[actualKey] !== payload[payloadKey]) throw new Error('STALE_APPROVAL');
}

function assertSameNumber(
  payload: Record<string, JsonValue>,
  payloadKey: string,
  actualState: Record<string, JsonValue>,
  actualKey = payloadKey,
): void {
  if (actualState[actualKey] !== payload[payloadKey]) throw new Error('STALE_APPROVAL');
}

export const demoActionProfile: ActionProfile = {
  type: 'demo.action.v1',
  validate(action) {
    assertExactKeys(action.payload, ['resource', 'operation'], 'PAYLOAD');
    requireString(action.payload, 'resource');
    requireString(action.payload, 'operation');
    if (action.preconditions !== undefined) {
      assertExactKeys(action.preconditions, ['version'], 'PRECONDITION');
      if (action.preconditions.version !== undefined) requireString(action.preconditions, 'version');
    }
  },
  displayClaims(action) {
    const claims: DisplayClaim[] = [
      { label: 'ACTION', value: requireString(action.payload, 'operation') },
      { label: 'RESOURCE', value: requireString(action.payload, 'resource') },
    ];
    if (action.preconditions?.version !== undefined) {
      claims.push({ label: 'EXPECTED VERSION', value: requireString(action.preconditions, 'version') });
    }
    return claims;
  },
  validatePreconditions(action, actualState) {
    const expected = action.preconditions?.version;
    if (expected === undefined) return;
    if (!actualState || actualState.version !== expected) throw new Error('STALE_APPROVAL');
  },
};

export const gitMergeProfile: ActionProfile = {
  type: 'git.merge.v1',
  validate(action) {
    assertExactKeys(action.payload, ['repository', 'sourceCommitSha', 'targetBranch', 'targetCommitBefore'], 'PAYLOAD');
    if (action.preconditions !== undefined) assertExactKeys(action.preconditions, [], 'PRECONDITION');
    requireString(action.payload, 'repository');
    requireString(action.payload, 'sourceCommitSha');
    requireString(action.payload, 'targetBranch');
    requireString(action.payload, 'targetCommitBefore');
  },
  displayClaims(action) {
    return [
      { label: 'ACTION', value: 'GIT MERGE' },
      { label: 'REPOSITORY', value: requireString(action.payload, 'repository') },
      { label: 'SOURCE', value: requireString(action.payload, 'sourceCommitSha') },
      { label: 'TARGET', value: requireString(action.payload, 'targetBranch'), emphasis: 'warning' },
      { label: 'TARGET BEFORE', value: requireString(action.payload, 'targetCommitBefore') },
    ];
  },
  validatePreconditions(action, actualState) {
    const expected = requireString(action.payload, 'targetCommitBefore');
    if (!actualState || actualState.targetCommit !== expected) throw new Error('STALE_APPROVAL');
  },
};

const DUBBRIDGE_TASK_CAPABILITIES = new Set(['edit', 'test', 'review', 'commit']);

export const dubbridgeTaskStartProfile: ActionProfile = {
  type: 'dubbridge.task.start.v1',
  validate(action) {
    assertExactKeys(
      action.payload,
      [
        'repository',
        'planId',
        'taskId',
        'sessionId',
        'branch',
        'baseCommitSha',
        'allowedPaths',
        'scopeDigest',
        'capabilities',
        'leaseTtlSeconds',
      ],
      'PAYLOAD',
    );
    if (action.preconditions !== undefined) assertExactKeys(action.preconditions, [], 'PRECONDITION');
    requireString(action.payload, 'repository');
    requireString(action.payload, 'planId');
    requireString(action.payload, 'taskId');
    requireString(action.payload, 'sessionId');
    requireString(action.payload, 'branch');
    requireString(action.payload, 'baseCommitSha');
    requireString(action.payload, 'scopeDigest');

    const allowedPaths = requireStringArray(action.payload, 'allowedPaths');
    assertSortedUnique(allowedPaths, 'allowedPaths');
    allowedPaths.forEach(assertRepositoryPath);

    const capabilities = requireStringArray(action.payload, 'capabilities');
    assertSortedUnique(capabilities, 'capabilities');
    if (capabilities.some((capability) => !DUBBRIDGE_TASK_CAPABILITIES.has(capability))) {
      throw new Error('Invalid capabilities');
    }
    requireInteger(action.payload, 'leaseTtlSeconds', 60, 1800);
  },
  displayClaims(action) {
    this.validate(action);
    return [
      { label: 'ACTION', value: 'START DUBBRIDGE TASK' },
      { label: 'PLAN', value: requireString(action.payload, 'planId') },
      { label: 'TASK', value: requireString(action.payload, 'taskId') },
      { label: 'REPOSITORY', value: requireString(action.payload, 'repository') },
      { label: 'BRANCH', value: requireString(action.payload, 'branch'), emphasis: 'warning' },
      { label: 'BASE SHA', value: requireString(action.payload, 'baseCommitSha') },
      { label: 'ALLOWED PATHS', value: requireStringArray(action.payload, 'allowedPaths').join(', ') },
      { label: 'CAPABILITIES', value: requireStringArray(action.payload, 'capabilities').join(', ') },
      { label: 'LEASE TTL', value: `${requireInteger(action.payload, 'leaseTtlSeconds', 60, 1800)}s` },
      { label: 'SCOPE DIGEST', value: requireString(action.payload, 'scopeDigest') },
    ];
  },
  validatePreconditions(action, actualState) {
    this.validate(action);
    const actual = requireActualState(
      actualState,
      ['repository', 'planId', 'taskId', 'sessionId', 'branch', 'currentHead', 'scopeDigest'],
    );
    assertSameString(action.payload, 'repository', actual);
    assertSameString(action.payload, 'planId', actual);
    assertSameString(action.payload, 'taskId', actual);
    assertSameString(action.payload, 'sessionId', actual);
    assertSameString(action.payload, 'branch', actual);
    assertSameString(action.payload, 'baseCommitSha', actual, 'currentHead');
    assertSameString(action.payload, 'scopeDigest', actual);
  },
};

export const dubbridgePlanCloseProfile: ActionProfile = {
  type: 'dubbridge.plan.close.v1',
  validate(action) {
    assertExactKeys(
      action.payload,
      [
        'repository',
        'planId',
        'branch',
        'finalCommitSha',
        'closureManifestDigest',
        'requiredTaskCount',
        'completedTaskCount',
        'acceptedExceptionCount',
        'validationStatus',
        'evidenceDigest',
      ],
      'PAYLOAD',
    );
    if (action.preconditions !== undefined) assertExactKeys(action.preconditions, [], 'PRECONDITION');
    requireString(action.payload, 'repository');
    requireString(action.payload, 'planId');
    requireString(action.payload, 'branch');
    requireString(action.payload, 'finalCommitSha');
    requireString(action.payload, 'closureManifestDigest');
    requireString(action.payload, 'evidenceDigest');
    if (requireString(action.payload, 'validationStatus') !== 'PASS') {
      throw new Error('Invalid validationStatus');
    }
    const required = requireInteger(action.payload, 'requiredTaskCount', 0);
    const completed = requireInteger(action.payload, 'completedTaskCount', 0);
    requireInteger(action.payload, 'acceptedExceptionCount', 0);
    if (completed !== required) throw new Error('Invalid completedTaskCount');
  },
  displayClaims(action) {
    this.validate(action);
    return [
      { label: 'ACTION', value: 'CLOSE DUBBRIDGE PLAN' },
      { label: 'PLAN', value: requireString(action.payload, 'planId') },
      { label: 'REPOSITORY', value: requireString(action.payload, 'repository') },
      { label: 'BRANCH', value: requireString(action.payload, 'branch'), emphasis: 'warning' },
      { label: 'FINAL SHA', value: requireString(action.payload, 'finalCommitSha') },
      {
        label: 'COMPLETED TASKS',
        value: `${requireInteger(action.payload, 'completedTaskCount', 0)}/${requireInteger(action.payload, 'requiredTaskCount', 0)}`,
      },
      {
        label: 'ACCEPTED EXCEPTIONS',
        value: String(requireInteger(action.payload, 'acceptedExceptionCount', 0)),
      },
      { label: 'VALIDATION', value: requireString(action.payload, 'validationStatus') },
      { label: 'CLOSURE MANIFEST', value: requireString(action.payload, 'closureManifestDigest') },
      { label: 'EVIDENCE', value: requireString(action.payload, 'evidenceDigest') },
    ];
  },
  validatePreconditions(action, actualState) {
    this.validate(action);
    const actual = requireActualState(
      actualState,
      [
        'workflowState',
        'repository',
        'planId',
        'branch',
        'finalCommitSha',
        'closureManifestDigest',
        'requiredTaskCount',
        'completedTaskCount',
        'acceptedExceptionCount',
        'validationStatus',
        'evidenceDigest',
      ],
    );
    if (actual.workflowState !== 'PLAN_READY_FOR_APPROVAL') throw new Error('STALE_APPROVAL');
    for (const key of [
      'repository',
      'planId',
      'branch',
      'finalCommitSha',
      'closureManifestDigest',
      'validationStatus',
      'evidenceDigest',
    ] as const) {
      assertSameString(action.payload, key, actual);
    }
    for (const key of ['requiredTaskCount', 'completedTaskCount', 'acceptedExceptionCount'] as const) {
      assertSameNumber(action.payload, key, actual);
    }
  },
};

export class ActionProfileRegistry {
  #profiles = new Map<string, ActionProfile>();

  constructor(
    profiles: ActionProfile[] = [
      demoActionProfile,
      gitMergeProfile,
      dubbridgeTaskStartProfile,
      dubbridgePlanCloseProfile,
    ],
  ) {
    for (const profile of profiles) this.#profiles.set(profile.type, profile);
  }

  get(type: string): ActionProfile {
    const profile = this.#profiles.get(type);
    if (!profile) throw new Error(`UNSUPPORTED_ACTION_PROFILE:${type}`);
    return profile;
  }

  validate(action: ActionSpec): void {
    assertActionEnvelope(action);
    this.get(action.type).validate(action);
  }

  displayClaims(action: ActionSpec): DisplayClaim[] {
    this.validate(action);
    return this.get(action.type).displayClaims(action);
  }

  validatePreconditions(action: ActionSpec, actual?: Record<string, JsonValue>): void {
    this.validate(action);
    this.get(action.type).validatePreconditions(action, actual);
  }

  actionDigest(action: ActionSpec): string {
    this.validate(action);
    return digestJson(action as unknown as JsonValue);
  }
}
