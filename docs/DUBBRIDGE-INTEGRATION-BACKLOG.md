# Future DubBridge integration backlog

Status: **FUTURE / NOT STARTED**

This integration is intentionally deferred until HAA software productization is complete. DubBridge-specific semantics must remain outside the universal HAA core.

## Integration thesis

HAA belongs at DubBridge's execution boundary:

```text
DubBridge planning / context / routing
        ↓
exact execution candidate selected
        ↓
HAA approval request
        ↓
human authenticator
        ↓
ExecutionGrant
        ↓
bounded DubBridge executor/provider call
```

HAA does not choose the model, provider, route or context. It approves or denies the exact action DubBridge has already decided to execute.

## W8 tasks

### W8-T01 — `dubbridge.ai-execution.v1` ActionProfile

Define a versioned profile that binds at minimum:

- DubBridge task/work item identity;
- provider;
- model;
- route/candidate identity;
- input/context digest rather than raw large prompt content;
- maximum authorized cost/budget where applicable;
- immutable execution preconditions;
- bounded executor audience;
- trusted display claims suitable for the human approver.

Changing canonical fields or precondition/display semantics requires `dubbridge.ai-execution.v2`, never reinterpretation of v1.

### W8-T02 — DubBridge requester/executor adapter

Add a thin adapter at the DubBridge execution boundary using the public `@haa/sdk` package. It must not import HAA core internals.

The requester creates the approval after DubBridge routing/policy has selected the exact candidate. The bounded executor performs the provider/local execution only after receiving a valid HAA `ExecutionGrant`.

### W8-T03 — Real DubBridge end-to-end gate

Demonstrate:

1. DubBridge selects an exact execution candidate.
2. HAA request is generated from that candidate.
3. The executor is blocked before approval.
4. Human approval occurs through a supported HAA authenticator.
5. The exact approved provider/model/input digest executes once.
6. Candidate mutation, stale state or different execution identity is rejected.
7. DubBridge observes final status without obtaining self-approval capability.

### W8-T04 — Cross-system audit/failure/retry hardening

Define correlation IDs and operational semantics across DubBridge and HAA for:

- request IDs;
- execution IDs;
- task/route IDs;
- timeouts and expiry;
- retries after provider/network failure;
- cancellation;
- audit reconstruction;
- provider cost/result correlation.

## Dependencies

Do not start W8 before:

- HAA protocol v1 is frozen;
- self-host deployment path is validated;
- the public TypeScript SDK package is stable;
- W7 final security/architecture review has no blocking findings.

Hardware is not a dependency for DubBridge integration. The existing macOS authenticator or another software-supported authenticator is sufficient for the first integration.
