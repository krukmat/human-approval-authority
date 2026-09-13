# Task execution

`manifest.yaml` is the dependency source of truth. Work on one task at a time and never start a task while any `depends_on` item is not complete.

The current critical path is:

`W3-T06 → W4-T05 → W4-T06 → (PASS only) W5`

Completed W0-W2 behavior is covered by repository tests. W3 macOS source exists but requires a real Touch ID/Secure Enclave validation run. Hardware tasks are intentionally blocked until the value gate passes.

Agent context should be limited to `docs/PLAN.md`, `docs/ARCHITECTURE.md`, `docs/SECURITY.md`, the relevant wave file, direct dependency code and `manifest.yaml`.
