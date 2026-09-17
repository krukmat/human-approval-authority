import type { AuthenticatorRecord } from '../../protocol/src/index.ts';
import type { SqliteStore } from '../../persistence-sqlite/src/index.ts';
import type { PendingWebAuthnRegistration, WebAuthnCredentialMetadata } from './index.ts';

export class WebAuthnStore {
  private readonly base: SqliteStore;

  constructor(base: SqliteStore) {
    this.base = base;
    this.base.db.exec(`
      CREATE TABLE IF NOT EXISTS webauthn_registrations (
        registration_id TEXT PRIMARY KEY,
        principal_id TEXT NOT NULL,
        challenge TEXT NOT NULL,
        rp_id TEXT NOT NULL,
        origin TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        consumed INTEGER NOT NULL DEFAULT 0
      );
      CREATE TABLE IF NOT EXISTS webauthn_credentials (
        authenticator_id TEXT PRIMARY KEY,
        credential_id TEXT NOT NULL UNIQUE,
        principal_id TEXT NOT NULL,
        rp_id TEXT NOT NULL,
        origin TEXT NOT NULL,
        sign_count INTEGER NOT NULL,
        transports_json TEXT NOT NULL,
        aaguid TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(authenticator_id) REFERENCES authenticators(id)
      );
      CREATE INDEX IF NOT EXISTS idx_webauthn_principal
        ON webauthn_credentials(principal_id, created_at);
    `);
  }

  saveRegistration(registration: PendingWebAuthnRegistration): void {
    this.base.db.prepare(`INSERT INTO webauthn_registrations(
      registration_id, principal_id, challenge, rp_id, origin, expires_at, consumed
    ) VALUES (?, ?, ?, ?, ?, ?, ?)`).run(
      registration.registrationId,
      registration.principalId,
      registration.challenge,
      registration.rpId,
      registration.origin,
      registration.expiresAt,
      registration.consumed ? 1 : 0,
    );
  }

  getRegistration(registrationId: string): PendingWebAuthnRegistration | null {
    const row = this.base.db.prepare(`SELECT registration_id, principal_id, challenge, rp_id, origin, expires_at, consumed
      FROM webauthn_registrations WHERE registration_id=?`).get(registrationId) as any;
    if (!row) return null;
    return {
      registrationId: row.registration_id,
      principalId: row.principal_id,
      challenge: row.challenge,
      rpId: row.rp_id,
      origin: row.origin,
      expiresAt: row.expires_at,
      consumed: row.consumed === 1,
    };
  }

  completeRegistration(args: {
    registrationId: string;
    authenticator: AuthenticatorRecord;
    metadata: WebAuthnCredentialMetadata;
  }): void {
    this.base.db.exec('BEGIN IMMEDIATE');
    try {
      const registration = this.base.db.prepare(`SELECT principal_id, consumed FROM webauthn_registrations
        WHERE registration_id=?`).get(args.registrationId) as { principal_id: string; consumed: number } | undefined;
      if (!registration) throw new Error('WEBAUTHN_REGISTRATION_NOT_FOUND');
      if (registration.consumed === 1) throw new Error('WEBAUTHN_REGISTRATION_REPLAY');
      if (registration.principal_id !== args.authenticator.principalId
        || registration.principal_id !== args.metadata.principalId) {
        throw new Error('WEBAUTHN_REGISTRATION_PRINCIPAL_MISMATCH');
      }

      this.base.saveAuthenticator(args.authenticator);
      this.base.db.prepare(`INSERT INTO webauthn_credentials(
        authenticator_id, credential_id, principal_id, rp_id, origin, sign_count,
        transports_json, aaguid, created_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`).run(
        args.metadata.authenticatorId,
        args.metadata.credentialId,
        args.metadata.principalId,
        args.metadata.rpId,
        args.metadata.origin,
        args.metadata.signCount,
        JSON.stringify(args.metadata.transports),
        args.metadata.aaguid ?? null,
        args.metadata.createdAt,
      );
      const consumed = this.base.db.prepare(`UPDATE webauthn_registrations SET consumed=1
        WHERE registration_id=? AND consumed=0`).run(args.registrationId);
      if (consumed.changes !== 1) throw new Error('WEBAUTHN_REGISTRATION_REPLAY');
      this.base.db.exec('COMMIT');
    } catch (error) {
      this.base.db.exec('ROLLBACK');
      throw error;
    }
  }

  getCredential(authenticatorId: string): WebAuthnCredentialMetadata | null {
    const row = this.base.db.prepare(`SELECT authenticator_id, credential_id, principal_id, rp_id, origin,
      sign_count, transports_json, aaguid, created_at FROM webauthn_credentials
      WHERE authenticator_id=?`).get(authenticatorId) as any;
    return row ? this.mapCredential(row) : null;
  }

  getCredentialByCredentialId(credentialId: string): WebAuthnCredentialMetadata | null {
    const row = this.base.db.prepare(`SELECT authenticator_id, credential_id, principal_id, rp_id, origin,
      sign_count, transports_json, aaguid, created_at FROM webauthn_credentials
      WHERE credential_id=?`).get(credentialId) as any;
    return row ? this.mapCredential(row) : null;
  }

  listCredentialsForPrincipal(principalId: string): WebAuthnCredentialMetadata[] {
    const rows = this.base.db.prepare(`SELECT authenticator_id, credential_id, principal_id, rp_id, origin,
      sign_count, transports_json, aaguid, created_at FROM webauthn_credentials
      WHERE principal_id=? ORDER BY created_at`).all(principalId) as any[];
    return rows.map((row) => this.mapCredential(row));
  }

  advanceCounter(authenticatorId: string, expectedCounter: number, nextCounter: number): boolean {
    if (expectedCounter === 0 && nextCounter === 0) return true;
    if (!Number.isInteger(nextCounter) || nextCounter < 0 || nextCounter <= expectedCounter) return false;
    const result = this.base.db.prepare(`UPDATE webauthn_credentials SET sign_count=?
      WHERE authenticator_id=? AND sign_count=?`).run(nextCounter, authenticatorId, expectedCounter);
    return result.changes === 1;
  }

  private mapCredential(row: any): WebAuthnCredentialMetadata {
    return {
      authenticatorId: row.authenticator_id,
      credentialId: row.credential_id,
      principalId: row.principal_id,
      rpId: row.rp_id,
      origin: row.origin,
      signCount: row.sign_count,
      transports: JSON.parse(row.transports_json) as string[],
      ...(row.aaguid ? { aaguid: row.aaguid } : {}),
      createdAt: row.created_at,
    };
  }
}
