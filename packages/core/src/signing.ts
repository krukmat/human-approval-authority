import { createPrivateKey, createPublicKey, generateKeyPairSync, sign, verify } from 'node:crypto';

export type SignatureAlgorithm = 'Ed25519' | 'ES256';

export interface Signer {
  keyId: string;
  algorithm: SignatureAlgorithm;
  publicKeyPem: string;
  sign(data: Uint8Array): string;
}

export function createEphemeralSigner(keyId = 'dev-authority'): Signer {
  const { privateKey } = generateKeyPairSync('ed25519');
  return createPemSigner(keyId, 'Ed25519', privateKey.export({ type: 'pkcs8', format: 'pem' }).toString());
}

export function createEphemeralP256Signer(keyId = 'dev-authority-p256'): Signer {
  const { privateKey } = generateKeyPairSync('ec', { namedCurve: 'prime256v1' });
  return createPemSigner(keyId, 'ES256', privateKey.export({ type: 'pkcs8', format: 'pem' }).toString());
}

export function createPemSigner(keyId: string, algorithm: SignatureAlgorithm, privateKeyPem: string): Signer {
  const privateKey = createPrivateKey(privateKeyPem);
  const publicKeyPem = createPublicKey(privateKey).export({ type: 'spki', format: 'pem' }).toString();
  return {
    keyId,
    algorithm,
    publicKeyPem,
    sign(data) {
      const signature = algorithm === 'Ed25519'
        ? sign(null, Buffer.from(data), privateKey)
        : sign('sha256', Buffer.from(data), privateKey);
      return signature.toString('base64url');
    },
  };
}

export function verifySignature(algorithm: SignatureAlgorithm, publicKeyPem: string, data: Uint8Array, signature: string): boolean {
  const publicKey = createPublicKey(publicKeyPem);
  const sig = Buffer.from(signature, 'base64url');
  return algorithm === 'Ed25519'
    ? verify(null, Buffer.from(data), publicKey, sig)
    : verify('sha256', Buffer.from(data), publicKey, sig);
}
