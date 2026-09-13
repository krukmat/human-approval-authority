# @haa/protocol

Frozen TypeScript types and runtime version metadata for HAA wire protocol v1.

```ts
import {
  HAA_PROTOCOL_VERSION,
  HAA_PROTOCOL_RELEASE,
  HAA_V1_SCHEMAS,
  type ActionSpec,
  type ExecutionGrant,
} from '@haa/protocol';
```

The package version starts at `1.0.0` because the v1 wire contract is frozen. Product/server releases may remain pre-1.0 independently.

See `../../docs/PROTOCOL-V1.md` in the repository for compatibility and extension rules.
