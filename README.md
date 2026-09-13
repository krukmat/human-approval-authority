# Human Approval Authority (HAA)

A vendor-neutral human approval authority for agentic workflows. HAA binds human approval to one exact canonical action and produces a short-lived execution grant only after atomic authorization/consumption.

## Trust flow

Requester → ActionSpec → ApprovalIntent → signed ChallengePackage → Authenticator → ApprovalEvidence → APPROVED/Receipt → authorizeAndConsume(actualAction) → ExecutionGrant → Executor

## Authenticator paths

- macOS: Touch ID-gated Secure Enclave signing.
- DIY hardware (conditional subplan): XIAO ESP32-S3 + local fingerprint match + trusted display + protected signing key.

The HAA core never handles fingerprint templates/images and never contains Apple/ESP32-specific behavior.

## Status

W0-W2 software core/service implemented in this repository. W3 Apple source is included but needs validation on a real macOS Secure Enclave host. W5-W6 remain blocked until the W4 value gate passes, as required by the plan.

See docs/PLAN.md and tasks/manifest.yaml.
