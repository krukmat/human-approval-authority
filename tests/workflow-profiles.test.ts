import test from 'node:test';
import assert from 'node:assert/strict';
import { ActionProfileRegistry, demoActionProfile, gitMergeProfile } from '../packages/core/src/actions.ts';
import { digestJson } from '../packages/core/src/canonical.ts';
import { workflowActionProfiles } from '../packages/core/src/workflow-actions.ts';
import type { ActionSpec } from '../packages/protocol/src/index.ts';
const registry = new ActionProfileRegistry([demoActionProfile, gitMergeProfile, ...workflowActionProfiles]);
function task() {
  const scope = {repository: 'example/project', planId: 'plan', taskId: 'task', sessionId: 'session', branch: 'feature/test',
    baseCommitSha: 'a'.repeat(40), allowedPaths: ['docs/**', 'scripts/**'], capabilities: ['commit','edit','review','test']};
  const action: ActionSpec = {schema:'haa.action.v1',type:'workflow.task.start.v1',
    payload:{...scope,scopeDigest:digestJson(scope),leaseTtlSeconds:1800}};
  const actual = {repository:scope.repository,planId:scope.planId,taskId:scope.taskId,sessionId:scope.sessionId,branch:scope.branch,currentHead:scope.baseCommitSha,scopeDigest:action.payload.scopeDigest!};
  return {action,actual};
}
test('task scope and current state bind; display includes session',()=>{
  const {action,actual}=task();
  registry.validatePreconditions(action,actual);
  const claims=Object.fromEntries(registry.displayClaims(action).map(c=>[c.label,c.value]));
  assert.equal(claims.SESSION,'session');
  assert.equal(claims.ACTION,'START WORKFLOW TASK');
  assert.equal(claims['SCOPE DIGEST'],action.payload.scopeDigest);
  assert.throws(()=>registry.validatePreconditions(action,{...actual,currentHead:'b'.repeat(40)}),/STALE_APPROVAL/);
  assert.throws(()=>registry.validatePreconditions(action,{...actual,unknown:true}),/STALE_APPROVAL/);
});
test('unknown, tampered, unsupported, or ambiguous task scope fails closed',()=>{
  const {action}=task();
  assert.throws(()=>new ActionProfileRegistry().validate(action),/UNSUPPORTED_ACTION_PROFILE/);
  for(const payload of [{...action.payload,scopeDigest:digestJson('changed')},{...action.payload,capabilities:['deploy']},
    {...action.payload,allowedPaths:['../escape']},{...action.payload,leaseTtlSeconds:1801},{...action.payload,unknown:true}]) {
    assert.throws(()=>registry.validate({...action,payload}));
  }
});
test('plan closure requires completed exact state and valid digests',()=>{
  const payload = {repository:'example/project',planId:'plan',branch:'feature/test',finalCommitSha:'a'.repeat(40),
    closureManifestDigest:digestJson('closure'),requiredTaskCount:2,completedTaskCount:2,acceptedExceptionCount:0,
    validationStatus:'PASS',evidenceDigest:digestJson(['evidence'])};
  const action:ActionSpec={schema:'haa.action.v1',type:'workflow.plan.close.v1',payload};
  registry.validatePreconditions(action,{...payload,workflowState:'PLAN_READY_FOR_APPROVAL'});
  assert.throws(()=>registry.validatePreconditions(action,{...payload,workflowState:'ACTIVE'}),/STALE_APPROVAL/);
  assert.throws(()=>registry.validate({...action,payload:{...payload,completedTaskCount:1}}));
  assert.throws(()=>registry.validate({...action,payload:{...payload,validationStatus:'FAIL'}}));
});
