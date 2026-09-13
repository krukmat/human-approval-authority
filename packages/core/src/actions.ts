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

function assertExactKeys(value: Record<string, unknown>, allowed: readonly string[], label: string): void {
  const allowedSet = new Set(allowed);
  const unexpected = Object.keys(value).filter((key) => !allowedSet.has(key));
  if (unexpected.length > 0) throw new Error(`UNEXPECTED_${label}_FIELD:${unexpected.sort().join(',')}`);
}

function assertActionEnvelope(action: ActionSpec): void {
  assertExactKeys(action as unknown as Record<string, unknown>, ['schema', 'type', 'payload', 'preconditions'], 'ACTION');
  if (action.schema !== 'haa.action.v1') throw new Error(`UNSUPPORTED_ACTION_SCHEMA:${String(action.schema)}`);
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

export class ActionProfileRegistry {
  #profiles = new Map<string, ActionProfile>();

  constructor(profiles: ActionProfile[] = [demoActionProfile, gitMergeProfile]) {
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
