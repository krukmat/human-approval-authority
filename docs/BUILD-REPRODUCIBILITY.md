# Build reproducibility policy

Status: W7-T07 deterministic dependency and build chain.

## JavaScript dependency graph

`package-lock.json` is committed and is the dependency-resolution authority for CI and container builds.

Required install commands:

```text
CI          -> npm ci
Docker      -> npm ci --omit=dev
Development -> npm ci for a clean baseline; npm install only when intentionally changing dependencies
```

A dependency change is not complete until both `package.json` and `package-lock.json` are committed together. CI must fail rather than silently repair a stale lockfile.

The lockfile was generated under Node 24 / npm 11 and uses npm lockfile version 3. Workspace package metadata is part of the locked graph.

## Runtime version policy

The supported JavaScript runtime is Node.js 24 or later within the Node 24 release line used by CI and the container image. CI explicitly selects Node 24. The container uses the official `node:24-bookworm-slim` image.

The base image tag intentionally tracks security and patch updates within Node 24 / Debian Bookworm rather than pinning one immutable digest forever. Therefore:

- npm dependency resolution is deterministic from the committed lockfile;
- application/package builds are reproducible against that graph;
- the OS/base-image byte content may advance with upstream security patches.

For environments requiring byte-for-byte container provenance, mirror and pin an approved image digest in the deployment pipeline and update that digest through a controlled security-patch process. Such a digest pin must not change the HAA protocol semantics.

## CI gates

A clean checkout must pass:

```bash
npm ci
npm run pack:check
npm test
npx tsc --noEmit
docker build .
```

`pack:check` verifies that the publishable protocol and TypeScript SDK still build and package from the committed dependency graph.

## Upgrade policy

For dependency or Node-runtime upgrades:

1. change the declared dependency/runtime intentionally;
2. regenerate the lockfile using the supported Node/npm toolchain;
3. review the lockfile diff;
4. run all CI gates;
5. confirm `docs/PROTOCOL-V1.md` compatibility remains intact;
6. never accept an implicit dependency refresh during production image build.
