#!/bin/sh
set -eu

python3 -c 'import cryptography' >/dev/null 2>&1 || {
  echo "HAA_TEST_DEPENDENCY_MISSING: install scripts/haa/requirements.txt in an isolated environment" >&2
  exit 2
}

exec python3 -m unittest \
  scripts.haa.contracts_test \
  scripts.haa.client_test \
  scripts.haa.authority_test \
  scripts.haa.grants_test \
  scripts.haa.adapter_test \
  scripts.haa.boundary_detector_test \
  scripts.haa.request_checkpoint_test \
  scripts.haa.live_verify_test \
  scripts.haa.authority_lease_test \
  scripts.haa.lease_guard_test \
  scripts.haa.recovery_test \
  scripts.haa.runner_authority_test \
  scripts.haa.plan_closure_test \
  scripts.haa.protected_host_test \
  scripts.haa.volatile_authority_test \
  scripts.haa.protected_broker_test \
  scripts.haa.protected_plan_test \
  scripts.haa.protected_session_test \
  scripts.haa.protected_commit_test \
  scripts.haa.protected_workflow_test \
  scripts.haa.protected_plan_entry_test \
  scripts.haa.protected_integration_test \
  scripts.haa.verification_backend_test \
  scripts.haa.macos_verifier_launcher_test \
  scripts.haa.verify_launch_test \
  scripts.haa.lease_process_restart_test \
  scripts.haa.protected_supervisor_test \
  scripts.haa.protected_credentials_test \
  scripts.haa.protected_plan_validation_test \
  scripts.haa.policy_test \
  scripts.haa.workflow_contract_parity_test \
  scripts.haa.batch_commit_test \
  scripts.haa.submit_batch_test \
  scripts.haa.project_bridge_test \
  scripts.haa.handoff_test \
  scripts.haa.native_batch_worker_test \
  scripts.haa.native_worker_invocation_test \
  scripts.haa.compare_workflow_test
