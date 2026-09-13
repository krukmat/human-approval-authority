import test from 'node:test';
import assert from 'node:assert/strict';
import { assertSafeDevelopmentBootstrap, resolveNetworkBinding } from '../apps/haa-server/src/network.ts';

test('local profile defaults to loopback', () => {
  assert.deepEqual(resolveNetworkBinding({}), {
    profile: 'local',
    host: '127.0.0.1',
    port: 8787,
  });
});

test('local profile refuses non-loopback binding', () => {
  assert.throws(() => resolveNetworkBinding({ HOST: '0.0.0.0', HAA_NETWORK_PROFILE: 'local' }), /LOCAL_PROFILE_REQUIRES_LOOPBACK/);
});

test('edge profile permits explicit non-loopback binding', () => {
  assert.deepEqual(resolveNetworkBinding({ HOST: '0.0.0.0', PORT: '9443', HAA_NETWORK_PROFILE: 'edge' }), {
    profile: 'edge',
    host: '0.0.0.0',
    port: 9443,
  });
});

test('development bootstrap is forbidden in edge profile unless explicitly overridden', () => {
  const edge = resolveNetworkBinding({ HOST: '0.0.0.0', HAA_NETWORK_PROFILE: 'edge' });
  assert.throws(() => assertSafeDevelopmentBootstrap(edge, { HAA_DEV_BOOTSTRAP: '1' }), /DEV_BOOTSTRAP_FORBIDDEN_IN_EDGE_PROFILE/);
  assert.doesNotThrow(() => assertSafeDevelopmentBootstrap(edge, {
    HAA_DEV_BOOTSTRAP: '1',
    HAA_ALLOW_UNSAFE_DEV_BOOTSTRAP_EDGE: '1',
  }));

  const local = resolveNetworkBinding({ HAA_NETWORK_PROFILE: 'local' });
  assert.doesNotThrow(() => assertSafeDevelopmentBootstrap(local, { HAA_DEV_BOOTSTRAP: '1' }));
});

test('invalid profile and port fail closed', () => {
  assert.throws(() => resolveNetworkBinding({ HAA_NETWORK_PROFILE: 'public' }), /INVALID_NETWORK_PROFILE/);
  assert.throws(() => resolveNetworkBinding({ PORT: '0' }), /INVALID_PORT/);
  assert.throws(() => resolveNetworkBinding({ PORT: '70000' }), /INVALID_PORT/);
});
