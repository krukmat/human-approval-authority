import { SqliteStore } from '../../../packages/persistence-sqlite/src/index.ts';
import { HaaApplication } from './application.ts';
import { buildHttpServer } from './http.ts';
import { loadOrCreateAuthoritySigner } from './authority.ts';

const dbPath = process.env.HAA_DB_PATH ?? './haa.db';
const store = new SqliteStore(dbPath);
const app = new HaaApplication({
  store,
  authoritySigner: loadOrCreateAuthoritySigner({
    keyId: process.env.HAA_AUTHORITY_KEY_ID,
    privateKeyPem: process.env.HAA_AUTHORITY_PRIVATE_KEY_PEM,
    keyFile: process.env.HAA_AUTHORITY_KEY_FILE,
  }),
});

if (process.env.HAA_DEV_BOOTSTRAP === '1') {
  app.registerClient(process.env.HAA_AGENT_ID ?? 'agent-dev', process.env.HAA_AGENT_KEY ?? 'agent-dev-secret');
  app.registerClient(process.env.HAA_HUMAN_ID ?? 'human-dev', process.env.HAA_HUMAN_KEY ?? 'human-dev-secret');
  app.registerClient(process.env.HAA_EXECUTOR_ID ?? 'executor-dev', process.env.HAA_EXECUTOR_KEY ?? 'executor-dev-secret');
}

const server = buildHttpServer(app);
await server.listen({ port: Number(process.env.PORT ?? 8787), host: process.env.HOST ?? '127.0.0.1' });
