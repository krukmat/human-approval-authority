import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { ActionProfileRegistry } from '../packages/core/src/actions.ts';
import { workflowActionProfiles } from '../packages/core/src/workflow-actions.ts';
import { digestJson } from '../packages/core/src/canonical.ts';
import type { ActionSpec } from '../packages/protocol/src/index.ts';
test('Python and HAA canonical action digest fixture matches',()=>{
  const f=JSON.parse(readFileSync(new URL('../integrations/workflow-runtime/fixtures/action-parity.json',import.meta.url),'utf8'));
  const action:ActionSpec={schema:'haa.action.v1',type:'workflow.task.start.v1',payload:{...f.scope,scopeDigest:f.scopeDigest,leaseTtlSeconds:f.leaseTtlSeconds}};
  assert.equal(digestJson(f.scope),f.scopeDigest);
  const registry=new ActionProfileRegistry([...workflowActionProfiles]);
  assert.equal(registry.actionDigest(action),f.actionDigest);
});
