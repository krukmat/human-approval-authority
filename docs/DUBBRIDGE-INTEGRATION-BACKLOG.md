# Parked DubBridge integration design

Status: **PARKED / NON-CANONICAL**

DubBridge is deliberately outside the active HAA roadmap.

Do **not** execute task IDs previously defined in this file. The canonical active HAA plan is:

- `docs/HAA-ACTIVE-ROADMAP.md`
- `tasks/manifest.yaml`

The prior detailed DubBridge design remains available in Git history (the last detailed version was committed before this parking change) and can be re-baselined if product-integration work is deliberately resumed.

## Preserved design direction

The parked integration concept was:

```text
human authorizes task start
        ↓
agents work autonomously inside the authorized envelope
        ↓
human accepts/rejects the exact result
```

with HAA remaining the human authorization authority rather than becoming the product workflow/routing authority.

The agreed ceremony semantics that are useful beyond DubBridge have been promoted into the universal HAA roadmap:

```text
successful Touch ID  -> APPROVE
Esc                   -> REJECT
window close          -> UNKNOWN
local timeout         -> UNKNOWN
```

Those semantics are now developed and validated as HAA-only capabilities in W8.

## Resume rule

If DubBridge integration is resumed later:

1. inspect the then-current HAA protocol/service/SDK state;
2. inspect the then-current DubBridge workflow and task contracts;
3. create a new product-integration wave/plan;
4. reuse universal HAA ceremony semantics rather than introducing product-specific branches into HAA core;
5. do not assume the old W8 task numbering or manifests are still valid.
