export type NetworkProfile = 'local' | 'edge';

export interface NetworkBinding {
  profile: NetworkProfile;
  host: string;
  port: number;
}

const LOOPBACK_HOSTS = new Set(['127.0.0.1', '::1', 'localhost']);

export function resolveNetworkBinding(env: NodeJS.ProcessEnv = process.env): NetworkBinding {
  const profile = env.HAA_NETWORK_PROFILE ?? 'local';
  if (profile !== 'local' && profile !== 'edge') throw new Error('INVALID_NETWORK_PROFILE');

  const host = env.HOST ?? '127.0.0.1';
  if (profile === 'local' && !LOOPBACK_HOSTS.has(host)) throw new Error('LOCAL_PROFILE_REQUIRES_LOOPBACK');

  const rawPort = env.PORT ?? '8787';
  const port = Number(rawPort);
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('INVALID_PORT');

  return { profile, host, port };
}
