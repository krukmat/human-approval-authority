import { SqliteStore } from '../../../packages/persistence-sqlite/src/index.ts';
import { HaaApplication } from './application.ts';
import { buildHttpServer } from './http.ts';
import { loadOrCreateAuthorityKeyRing } from './authority.ts';
import { resolveNetworkBinding } from './network.ts';

const dbPath = process.env.HAA_DB_PATH ?? './haa.db';
const store = new SqliteStore(dbPath);
const authorityOptions = {
  ...(process.env.HAA_AUTHORITY_KEY_ID ? { keyId: process.env.HAA_AUTHORITY_KEY_ID } : {}),
  ...(process.env.HAA_AUTHORITY_PRIVATE_KEY_PEM ? { privateKeyPem: process.env.HAA_AUTHORITY_PRIVATE_KEY_PEM } : {}),
  ...(process.env.HAA_AUTHORITY_KEY_FILE ? { keyFile: process.env.HAA_AUTHORITY_KEY_FILE } : {}),
  ...(process.env.HAA_AUTHORITY_KEYRING_FILE ? { keyRingFile: process.env.HAA_AUTHORITY_KEYRING_FILE } : {}),
};
const authorityKeyRing = loadOrCreateAuthorityKeyRing(authorityOptions);
const app = new HaaApplication({
  store,
  authoritySigner: authorityKeyRing.signer,
  authorityKeyResolver: (keyId) => {
    const key = authorityKeyRing.resolve(keyId);
    return key ? { algorithm: key.algorithm, publicKeyPem: key.publicKeyPem } : null;
  },
});

if (process.env.HAA_DEV_BOOTSTRAP === '1') {
  app.registerClient(process.env.HAA_AGENT_ID ?? 'agent-dev', process.env.HAA_AGENT_KEY ?? 'agent-dev-secret', ['REQUESTER']);
  app.registerClient(process.env.HAA_HUMAN_ID ?? 'human-dev', process.env.HAA_HUMAN_KEY ?? 'human-dev-secret', ['APPROVER']);
  app.registerClient(process.env.HAA_EXECUTOR_ID ?? 'executor-dev', process.env.HAA_EXECUTOR_KEY ?? 'executor-dev-secret', ['EXECUTOR']);
}

const binding = resolveNetworkBinding();
const server = buildHttpServer(app, { authorityKeys: () => authorityKeyRing.listPublicKeys() });
await server.listen({ port: binding.port, host: binding.host });
