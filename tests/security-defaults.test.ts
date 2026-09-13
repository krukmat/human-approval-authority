import assert from 'node:assert/strict';
import test from 'node:test';
import { createEphemeralSigner } from '../packages/core/src/index.ts';
import { SqliteStore } from '../packages/persistence-sqlite/src/index.ts';
import { HaaApplication } from '../apps/haa-server/src/application.ts';

test('production defaults exclude the software-only test-key verifier', () => {
  const store = new SqliteStore(':memory:');
  const app = new HaaApplication({ store, authoritySigner: createEphemeralSigner('authority') });
  assert.equal(app.verifiers.has('test-key'), false);
  assert.equal(app.verifiers.has('apple-secure-enclave'), true);
  assert.equal(app.verifiers.has('haa-hardware-v1'), true);
  store.close();
});
