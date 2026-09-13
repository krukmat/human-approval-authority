import { rotateAuthorityKey } from '../apps/haa-server/src/authority.ts';

const nextKeyId = process.argv[2];
if (!nextKeyId) {
  console.error('Usage: npm run rotate:authority-key -- <next-key-id>');
  process.exit(2);
}
if (!/^[A-Za-z0-9._:-]{1,128}$/.test(nextKeyId)) {
  console.error('Invalid key id');
  process.exit(2);
}

const keyFile = process.env.HAA_AUTHORITY_KEY_FILE ?? './.haa/authority-key.pem';
const keyRingFile = process.env.HAA_AUTHORITY_KEYRING_FILE ?? `${keyFile}.ring.json`;
const ring = rotateAuthorityKey({ nextKeyId, keyFile, keyRingFile });

console.log(JSON.stringify({
  activeKeyId: ring.signer.keyId,
  keys: ring.listPublicKeys().map(({ keyId, algorithm, status, createdAt, retiredAt }) => ({
    keyId,
    algorithm,
    status,
    createdAt,
    ...(retiredAt ? { retiredAt } : {}),
  })),
}, null, 2));
