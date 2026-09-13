import { createHash } from 'node:crypto';
import type { JsonValue } from '../../protocol/src/index.ts';

function canonicalizeValue(value: JsonValue): string {
  if (value === null) return 'null';
  if (typeof value === 'string' || typeof value === 'boolean') return JSON.stringify(value);
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new TypeError('Non-finite numbers are not canonical JSON');
    if (Object.is(value, -0)) return '0';
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonicalizeValue).join(',')}]`;
  const keys = Object.keys(value).sort();
  return `{${keys.map((key) => `${JSON.stringify(key)}:${canonicalizeValue(value[key]!)}`).join(',')}}`;
}

export function canonicalize(value: JsonValue): string {
  return canonicalizeValue(value);
}

export function sha256(value: string | Uint8Array): string {
  return createHash('sha256').update(value).digest('base64url');
}

export function digestJson(value: JsonValue): string {
  return `sha256:${sha256(canonicalize(value))}`;
}
