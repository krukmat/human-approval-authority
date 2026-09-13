import { createHash, randomUUID } from 'node:crypto';
import { DatabaseSync } from 'node:sqlite';
import type {
  ApprovalChallengePackage,
  ApprovalReceipt,
  ApprovalRequest,
  AuditEvent,
  AuthenticatorRecord,
  ExecutionGrant,
} from '../../protocol/src/index.ts';

export type ClientRole = 'REQUESTER' | 'APPROVER' | 'EXECUTOR';

export interface AuthenticatedClient {
  id: string;
  roles: ClientRole[];
  credentialVersion: number;
}

export interface ClientRecord extends AuthenticatedClient {
  enabled: boolean;
  credentialExpiresAt?: string;
  createdAt: string;
  updatedAt: string;
}

export interface ClientCredentialHistoryEntry {
  version: number;
  status: 'ACTIVE' | 'RETIRED' | 'REVOKED';
  createdAt: string;
  expiresAt?: string;
  retiredAt?: string;
}

export interface AuditIntegrityHead {
  sequence: number;
  digest: string;
}

export interface StoredAuditCheckpoint {
  schema: 'haa.audit-checkpoint.v1';
  sequence: number;
  headDigest: string;
  createdAt: string;
  authorityKeyId: string;
  signatureAlgorithm: 'Ed25519' | 'ES256';
  signature: string;
}

const ALL_CLIENT_ROLES: ClientRole[] = ['REQUESTER', 'APPROVER', 'EXECUTOR'];

function normalizeRoles(roles: ClientRole[]): ClientRole[] {
  const unique = [...new Set(roles)];
  if (unique.length === 0 || unique.some((role) => !ALL_CLIENT_ROLES.includes(role))) throw new Error('INVALID_CLIENT_ROLES');
  return unique;
}

function auditDigest(sequence: number, eventId: string, eventJson: string, previousDigest: string | null): string {
  const envelope = JSON.stringify({
    schema: 'haa.audit-chain.v1',
    sequence,
    eventId,
    previousDigest,
    eventJson,
  });
  return `sha256:${createHash('sha256').update(envelope).digest('base64url')}`;
}

export class SqliteStore {
  readonly db: DatabaseSync;

  constructor(path = ':memory:') {
    this.db = new DatabaseSync(path);
    this.db.exec(`
      PRAGMA foreign_keys = ON;
      CREATE TABLE IF NOT EXISTS clients (
        id TEXT PRIMARY KEY,
        api_key_hash TEXT NOT NULL UNIQUE,
        enabled INTEGER NOT NULL DEFAULT 1,
        roles_json TEXT NOT NULL DEFAULT '["REQUESTER","APPROVER","EXECUTOR"]',
        credential_version INTEGER NOT NULL DEFAULT 1,
        credential_expires_at TEXT,
        created_at TEXT,
        updated_at TEXT
      );
      CREATE TABLE IF NOT EXISTS client_credential_history (
        client_id TEXT NOT NULL,
        version INTEGER NOT NULL,
        api_key_hash TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT,
        retired_at TEXT,
        PRIMARY KEY(client_id, version),
        FOREIGN KEY(client_id) REFERENCES clients(id)
      );
      CREATE TABLE IF NOT EXISTS admin_audit_events (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        id TEXT NOT NULL UNIQUE,
        event_type TEXT NOT NULL,
        actor_id TEXT NOT NULL,
        target_id TEXT NOT NULL,
        at TEXT NOT NULL,
        details_json TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS requests (
        id TEXT PRIMARY KEY,
        state TEXT NOT NULL,
        action_digest TEXT NOT NULL,
        intent_digest TEXT NOT NULL,
        intent_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS authenticators (
        id TEXT PRIMARY KEY,
        principal_id TEXT NOT NULL,
        type TEXT NOT NULL,
        public_key_pem TEXT NOT NULL,
        algorithm TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        revoked_at TEXT
      );
      CREATE TABLE IF NOT EXISTS challenges (
        digest TEXT PRIMARY KEY,
        request_id TEXT NOT NULL,
        authenticator_id TEXT NOT NULL,
        challenge_json TEXT NOT NULL,
        consumed INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY(request_id) REFERENCES requests(id)
      );
      CREATE TABLE IF NOT EXISTS receipts (
        request_id TEXT PRIMARY KEY,
        receipt_json TEXT NOT NULL,
        FOREIGN KEY(request_id) REFERENCES requests(id)
      );
      CREATE TABLE IF NOT EXISTS grants (
        execution_id TEXT PRIMARY KEY,
        request_id TEXT NOT NULL UNIQUE,
        grant_json TEXT NOT NULL,
        FOREIGN KEY(request_id) REFERENCES requests(id)
      );
      CREATE TABLE IF NOT EXISTS audit_events (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        id TEXT NOT NULL UNIQUE,
        request_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        actor_id TEXT NOT NULL,
        event_json TEXT NOT NULL,
        at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS audit_integrity (
        seq INTEGER PRIMARY KEY,
        event_id TEXT NOT NULL UNIQUE,
        prev_digest TEXT,
        event_digest TEXT NOT NULL,
        FOREIGN KEY(event_id) REFERENCES audit_events(id)
      );
      CREATE TABLE IF NOT EXISTS audit_checkpoints (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        audit_sequence INTEGER NOT NULL,
        head_digest TEXT NOT NULL,
        checkpoint_json TEXT NOT NULL,
        created_at TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_audit_request ON audit_events(request_id, at);
      CREATE INDEX IF NOT EXISTS idx_admin_audit_target ON admin_audit_events(target_id, seq);
      CREATE INDEX IF NOT EXISTS idx_audit_checkpoint_sequence ON audit_checkpoints(audit_sequence, seq);
    `);

    this.ensureClientColumn('roles_json', `TEXT NOT NULL DEFAULT '["REQUESTER","APPROVER","EXECUTOR"]'`);
    this.ensureClientColumn('credential_version', 'INTEGER NOT NULL DEFAULT 1');
    this.ensureClientColumn('credential_expires_at', 'TEXT');
    this.ensureClientColumn('created_at', 'TEXT');
    this.ensureClientColumn('updated_at', 'TEXT');

    const now = new Date().toISOString();
    this.db.prepare('UPDATE clients SET created_at = COALESCE(created_at, ?), updated_at = COALESCE(updated_at, ?)').run(now, now);
    this.db.prepare(`INSERT OR IGNORE INTO client_credential_history(
      client_id, version, api_key_hash, status, created_at, expires_at, retired_at
    ) SELECT id, credential_version, api_key_hash,
      CASE WHEN enabled = 1 THEN 'ACTIVE' ELSE 'REVOKED' END,
      COALESCE(created_at, ?), credential_expires_at,
      CASE WHEN enabled = 1 THEN NULL ELSE COALESCE(updated_at, ?) END
      FROM clients`).run(now, now);

    this.initializeAuditIntegrity();
  }

  close(): void { this.db.close(); }

  registerClient(
    id: string,
    apiKeyHash: string,
    roles: ClientRole[] = ALL_CLIENT_ROLES,
    options: { expiresAt?: string; now?: string; actorId?: string } = {},
  ): void {
    const normalizedRoles = normalizeRoles(roles);
    const now = options.now ?? new Date().toISOString();
    const existing = this.db.prepare('SELECT api_key_hash, enabled FROM clients WHERE id = ?').get(id) as { api_key_hash: string; enabled: number } | undefined;
    if (existing) {
      if (existing.api_key_hash !== apiKeyHash) throw new Error('CLIENT_ALREADY_EXISTS_USE_ROTATE');
      if (existing.enabled !== 1) throw new Error('CLIENT_DISABLED');
      this.db.prepare('UPDATE clients SET roles_json=?, credential_expires_at=?, updated_at=? WHERE id=?').run(
        JSON.stringify(normalizedRoles), options.expiresAt ?? null, now, id,
      );
      return;
    }

    this.db.exec('BEGIN IMMEDIATE');
    try {
      this.db.prepare(`INSERT INTO clients(
        id, api_key_hash, enabled, roles_json, credential_version, credential_expires_at, created_at, updated_at
      ) VALUES (?, ?, 1, ?, 1, ?, ?, ?)`).run(
        id, apiKeyHash, JSON.stringify(normalizedRoles), options.expiresAt ?? null, now, now,
      );
      this.db.prepare(`INSERT INTO client_credential_history(
        client_id, version, api_key_hash, status, created_at, expires_at
      ) VALUES (?, 1, ?, 'ACTIVE', ?, ?)`).run(id, apiKeyHash, now, options.expiresAt ?? null);
      this.appendAdminAuditInternal('CLIENT_PROVISIONED', options.actorId ?? 'local-admin', id, now, {
        roles: normalizedRoles,
        credentialVersion: 1,
        expiresAt: options.expiresAt ?? null,
      });
      this.db.exec('COMMIT');
    } catch (error) {
      this.db.exec('ROLLBACK');
      throw error;
    }
  }

  authenticateClient(apiKeyHash: string, now = new Date().toISOString()): AuthenticatedClient | null {
    const row = this.db.prepare(`SELECT id, roles_json, credential_version, credential_expires_at
      FROM clients WHERE api_key_hash = ? AND enabled = 1`).get(apiKeyHash) as {
        id: string;
        roles_json: string;
        credential_version: number;
        credential_expires_at: string | null;
      } | undefined;
    if (!row) return null;
    if (row.credential_expires_at && Date.parse(row.credential_expires_at) <= Date.parse(now)) return null;
    return { id: row.id, roles: JSON.parse(row.roles_json) as ClientRole[], credentialVersion: row.credential_version };
  }

  getClient(id: string): ClientRecord | null {
    const row = this.db.prepare(`SELECT id, roles_json, credential_version, enabled, credential_expires_at, created_at, updated_at
      FROM clients WHERE id = ?`).get(id) as any;
    if (!row) return null;
    return {
      id: row.id,
      roles: JSON.parse(row.roles_json) as ClientRole[],
      credentialVersion: row.credential_version,
      enabled: row.enabled === 1,
      createdAt: row.created_at,
      updatedAt: row.updated_at,
      ...(row.credential_expires_at ? { credentialExpiresAt: row.credential_expires_at } : {}),
    };
  }

  rotateClientCredential(
    id: string,
    apiKeyHash: string,
    options: { expiresAt?: string; now?: string; actorId?: string } = {},
  ): number {
    const now = options.now ?? new Date().toISOString();
    this.db.exec('BEGIN IMMEDIATE');
    try {
      const row = this.db.prepare('SELECT enabled, credential_version FROM clients WHERE id=?').get(id) as { enabled: number; credential_version: number } | undefined;
      if (!row) throw new Error('CLIENT_NOT_FOUND');
      if (row.enabled !== 1) throw new Error('CLIENT_DISABLED');
      const nextVersion = row.credential_version + 1;
      this.db.prepare(`UPDATE client_credential_history
        SET status='RETIRED', retired_at=?
        WHERE client_id=? AND version=? AND status='ACTIVE'`).run(now, id, row.credential_version);
      this.db.prepare(`UPDATE clients SET api_key_hash=?, credential_version=?, credential_expires_at=?, updated_at=? WHERE id=?`).run(
        apiKeyHash, nextVersion, options.expiresAt ?? null, now, id,
      );
      this.db.prepare(`INSERT INTO client_credential_history(
        client_id, version, api_key_hash, status, created_at, expires_at
      ) VALUES (?, ?, ?, 'ACTIVE', ?, ?)`).run(id, nextVersion, apiKeyHash, now, options.expiresAt ?? null);
      this.appendAdminAuditInternal('CLIENT_CREDENTIAL_ROTATED', options.actorId ?? 'local-admin', id, now, {
        credentialVersion: nextVersion,
        expiresAt: options.expiresAt ?? null,
      });
      this.db.exec('COMMIT');
      return nextVersion;
    } catch (error) {
      this.db.exec('ROLLBACK');
      throw error;
    }
  }

  disableClient(id: string, options: { now?: string; actorId?: string } = {}): boolean {
    const now = options.now ?? new Date().toISOString();
    this.db.exec('BEGIN IMMEDIATE');
    try {
      const row = this.db.prepare('SELECT credential_version FROM clients WHERE id=? AND enabled=1').get(id) as { credential_version: number } | undefined;
      if (!row) {
        this.db.exec('ROLLBACK');
        return false;
      }
      this.db.prepare('UPDATE clients SET enabled=0, updated_at=? WHERE id=?').run(now, id);
      this.db.prepare(`UPDATE client_credential_history SET status='REVOKED', retired_at=?
        WHERE client_id=? AND version=? AND status='ACTIVE'`).run(now, id, row.credential_version);
      this.appendAdminAuditInternal('CLIENT_DISABLED', options.actorId ?? 'local-admin', id, now, {
        credentialVersion: row.credential_version,
      });
      this.db.exec('COMMIT');
      return true;
    } catch (error) {
      this.db.exec('ROLLBACK');
      throw error;
    }
  }

  listClientCredentialHistory(id: string): ClientCredentialHistoryEntry[] {
    const rows = this.db.prepare(`SELECT version, status, created_at, expires_at, retired_at
      FROM client_credential_history WHERE client_id=? ORDER BY version`).all(id) as any[];
    return rows.map((row) => ({
      version: row.version,
      status: row.status,
      createdAt: row.created_at,
      ...(row.expires_at ? { expiresAt: row.expires_at } : {}),
      ...(row.retired_at ? { retiredAt: row.retired_at } : {}),
    }));
  }

  listAdminAudit(targetId: string): Array<{ eventType: string; actorId: string; targetId: string; at: string; details: Record<string, unknown> }> {
    const rows = this.db.prepare(`SELECT event_type, actor_id, target_id, at, details_json
      FROM admin_audit_events WHERE target_id=? ORDER BY seq`).all(targetId) as any[];
    return rows.map((row) => ({
      eventType: row.event_type,
      actorId: row.actor_id,
      targetId: row.target_id,
      at: row.at,
      details: JSON.parse(row.details_json),
    }));
  }

  createRequest(request: ApprovalRequest): void {
    this.db.prepare(`INSERT INTO requests(id,state,action_digest,intent_digest,intent_json,created_at,updated_at)
      VALUES (?,?,?,?,?,?,?)`).run(
        request.id, request.state, request.actionDigest, request.intentDigest,
        JSON.stringify(request.intent), request.createdAt, request.updatedAt,
      );
  }

  getRequest(id: string): ApprovalRequest | null {
    const row = this.db.prepare('SELECT * FROM requests WHERE id = ?').get(id) as any;
    if (!row) return null;
    return {
      schema: 'haa.request.v1',
      id: row.id,
      state: row.state,
      actionDigest: row.action_digest,
      intentDigest: row.intent_digest,
      intent: JSON.parse(row.intent_json),
      createdAt: row.created_at,
      updatedAt: row.updated_at,
    };
  }

  transitionRequest(id: string, expected: string, next: string, updatedAt: string): boolean {
    const result = this.db.prepare('UPDATE requests SET state = ?, updated_at = ? WHERE id = ? AND state = ?').run(next, updatedAt, id, expected);
    return result.changes === 1;
  }

  saveAuthenticator(record: AuthenticatorRecord): void {
    this.db.prepare(`INSERT INTO authenticators(id,principal_id,type,public_key_pem,algorithm,status,created_at,revoked_at)
      VALUES (?,?,?,?,?,?,?,?)`).run(
        record.id, record.principalId, record.type, record.publicKeyPem, record.signatureAlgorithm,
        record.status, record.createdAt, record.revokedAt ?? null,
      );
  }

  getAuthenticator(id: string): AuthenticatorRecord | null {
    const row = this.db.prepare('SELECT * FROM authenticators WHERE id = ?').get(id) as any;
    if (!row) return null;
    return {
      schema: 'haa.authenticator.v1', id: row.id, principalId: row.principal_id,
      type: row.type, publicKeyPem: row.public_key_pem, signatureAlgorithm: row.algorithm,
      status: row.status, createdAt: row.created_at,
      ...(row.revoked_at ? { revokedAt: row.revoked_at } : {}),
    };
  }

  revokeAuthenticator(id: string, revokedAt: string): boolean {
    const result = this.db.prepare(`UPDATE authenticators SET status='REVOKED', revoked_at=? WHERE id=? AND status='ACTIVE'`).run(revokedAt, id);
    return result.changes === 1;
  }

  saveChallenge(digest: string, challenge: ApprovalChallengePackage, requestId: string, authenticatorId: string, issuedAt: string): void {
    this.db.prepare(`INSERT INTO challenges(digest,request_id,authenticator_id,challenge_json,created_at) VALUES (?,?,?,?,?)`).run(
      digest, requestId, authenticatorId, JSON.stringify(challenge), issuedAt,
    );
  }

  getChallenge(digest: string): { challenge: ApprovalChallengePackage; consumed: boolean } | null {
    const row = this.db.prepare('SELECT challenge_json, consumed FROM challenges WHERE digest = ?').get(digest) as any;
    return row ? { challenge: JSON.parse(row.challenge_json), consumed: row.consumed === 1 } : null;
  }

  consumeChallenge(digest: string): boolean {
    const result = this.db.prepare('UPDATE challenges SET consumed=1 WHERE digest=? AND consumed=0').run(digest);
    return result.changes === 1;
  }

  saveReceipt(receipt: ApprovalReceipt): void {
    this.db.prepare('INSERT INTO receipts(request_id, receipt_json) VALUES (?, ?)').run(receipt.requestId, JSON.stringify(receipt));
  }

  getReceipt(requestId: string): ApprovalReceipt | null {
    const row = this.db.prepare('SELECT receipt_json FROM receipts WHERE request_id=?').get(requestId) as any;
    return row ? JSON.parse(row.receipt_json) : null;
  }

  getExecutionGrant(executionId: string): ExecutionGrant | null {
    const row = this.db.prepare('SELECT grant_json FROM grants WHERE execution_id=?').get(executionId) as any;
    return row ? JSON.parse(row.grant_json) : null;
  }

  appendAudit(event: AuditEvent): void {
    this.db.exec('BEGIN IMMEDIATE');
    try {
      this.appendAuditInternal(event);
      this.db.exec('COMMIT');
    } catch (error) {
      this.db.exec('ROLLBACK');
      throw error;
    }
  }

  listAudit(requestId: string): AuditEvent[] {
    const rows = this.db.prepare('SELECT event_json FROM audit_events WHERE request_id=? ORDER BY seq').all(requestId) as any[];
    return rows.map((r) => JSON.parse(r.event_json));
  }

  getAuditHead(): AuditIntegrityHead | null {
    const row = this.db.prepare(`SELECT seq, event_digest FROM audit_integrity ORDER BY seq DESC LIMIT 1`).get() as
      | { seq: number; event_digest: string }
      | undefined;
    return row ? { sequence: row.seq, digest: row.event_digest } : null;
  }

  getAuditDigestAtSequence(sequence: number): string | null {
    const row = this.db.prepare('SELECT event_digest FROM audit_integrity WHERE seq=?').get(sequence) as { event_digest: string } | undefined;
    return row?.event_digest ?? null;
  }

  verifyAuditChain(): AuditIntegrityHead | null {
    const rows = this.db.prepare(`SELECT e.seq, e.id, e.event_json, i.prev_digest, i.event_digest
      FROM audit_events e LEFT JOIN audit_integrity i ON i.seq=e.seq AND i.event_id=e.id
      ORDER BY e.seq`).all() as Array<{
        seq: number;
        id: string;
        event_json: string;
        prev_digest: string | null;
        event_digest: string | null;
      }>;
    const integrityCount = Number((this.db.prepare('SELECT COUNT(*) AS count FROM audit_integrity').get() as { count: number | bigint }).count);
    if (integrityCount !== rows.length) throw new Error('AUDIT_INTEGRITY_ROW_COUNT_MISMATCH');

    let previousDigest: string | null = null;
    for (const row of rows) {
      if (!row.event_digest) throw new Error(`AUDIT_INTEGRITY_MISSING:${row.seq}`);
      if (row.prev_digest !== previousDigest) throw new Error(`AUDIT_CHAIN_PREVIOUS_MISMATCH:${row.seq}`);
      const expected = auditDigest(row.seq, row.id, row.event_json, previousDigest);
      if (row.event_digest !== expected) throw new Error(`AUDIT_CHAIN_DIGEST_MISMATCH:${row.seq}`);
      previousDigest = expected;
    }
    return rows.length === 0 || previousDigest === null
      ? null
      : { sequence: rows.at(-1)!.seq, digest: previousDigest };
  }

  saveAuditCheckpoint(checkpoint: StoredAuditCheckpoint): void {
    const headDigest = this.getAuditDigestAtSequence(checkpoint.sequence);
    if (!headDigest || headDigest !== checkpoint.headDigest) throw new Error('AUDIT_CHECKPOINT_HEAD_MISMATCH');
    this.db.prepare(`INSERT INTO audit_checkpoints(audit_sequence,head_digest,checkpoint_json,created_at)
      VALUES (?,?,?,?)`).run(checkpoint.sequence, checkpoint.headDigest, JSON.stringify(checkpoint), checkpoint.createdAt);
  }

  listAuditCheckpoints(): StoredAuditCheckpoint[] {
    const rows = this.db.prepare('SELECT checkpoint_json FROM audit_checkpoints ORDER BY seq').all() as Array<{ checkpoint_json: string }>;
    return rows.map((row) => JSON.parse(row.checkpoint_json) as StoredAuditCheckpoint);
  }

  consumeApproved(args: {
    requestId: string;
    executionId: string;
    grant: ExecutionGrant;
    consumedAt: string;
    auditEvent?: AuditEvent;
  }): { grant: ExecutionGrant; reused: boolean } {
    this.db.exec('BEGIN IMMEDIATE');
    try {
      const prior = this.db.prepare('SELECT grant_json FROM grants WHERE execution_id=?').get(args.executionId) as any;
      if (prior) {
        const priorGrant = JSON.parse(prior.grant_json) as ExecutionGrant;
        if (priorGrant.requestId !== args.requestId) throw new Error('EXECUTION_ID_CONFLICT');
        this.db.exec('COMMIT');
        return { grant: priorGrant, reused: true };
      }
      const row = this.db.prepare('SELECT state FROM requests WHERE id=?').get(args.requestId) as any;
      if (!row) throw new Error('REQUEST_NOT_FOUND');
      if (row.state !== 'APPROVED') throw new Error(`REQUEST_NOT_APPROVED:${row.state}`);
      const changed = this.db.prepare(`UPDATE requests SET state='CONSUMED',updated_at=? WHERE id=? AND state='APPROVED'`).run(args.consumedAt, args.requestId);
      if (changed.changes !== 1) throw new Error('CONCURRENT_CONSUME');
      this.db.prepare('INSERT INTO grants(execution_id,request_id,grant_json) VALUES (?,?,?)').run(
        args.executionId, args.requestId, JSON.stringify(args.grant),
      );
      if (args.auditEvent) this.appendAuditInternal(args.auditEvent);
      this.db.exec('COMMIT');
      return { grant: args.grant, reused: false };
    } catch (error) {
      this.db.exec('ROLLBACK');
      throw error;
    }
  }

  private initializeAuditIntegrity(): void {
    const eventCount = Number((this.db.prepare('SELECT COUNT(*) AS count FROM audit_events').get() as { count: number | bigint }).count);
    const integrityCount = Number((this.db.prepare('SELECT COUNT(*) AS count FROM audit_integrity').get() as { count: number | bigint }).count);
    if (eventCount > 0 && integrityCount === 0) {
      this.db.exec('BEGIN IMMEDIATE');
      try {
        const rows = this.db.prepare('SELECT seq,id,event_json FROM audit_events ORDER BY seq').all() as Array<{ seq: number; id: string; event_json: string }>;
        let previousDigest: string | null = null;
        for (const row of rows) {
          const digest = auditDigest(row.seq, row.id, row.event_json, previousDigest);
          this.db.prepare('INSERT INTO audit_integrity(seq,event_id,prev_digest,event_digest) VALUES (?,?,?,?)').run(
            row.seq, row.id, previousDigest, digest,
          );
          previousDigest = digest;
        }
        this.db.exec('COMMIT');
      } catch (error) {
        this.db.exec('ROLLBACK');
        throw error;
      }
    } else if (eventCount !== integrityCount) {
      throw new Error('AUDIT_INTEGRITY_ROW_COUNT_MISMATCH');
    }
    this.verifyAuditChain();
  }

  private appendAuditInternal(event: AuditEvent): void {
    const eventJson = JSON.stringify(event);
    const previous = this.getAuditHead();
    const inserted = this.db.prepare('INSERT INTO audit_events(id,request_id,event_type,actor_id,event_json,at) VALUES (?,?,?,?,?,?)').run(
      event.id, event.requestId, event.eventType, event.actorId, eventJson, event.at,
    );
    const sequence = Number(inserted.lastInsertRowid);
    const digest = auditDigest(sequence, event.id, eventJson, previous?.digest ?? null);
    this.db.prepare('INSERT INTO audit_integrity(seq,event_id,prev_digest,event_digest) VALUES (?,?,?,?)').run(
      sequence, event.id, previous?.digest ?? null, digest,
    );
  }

  private ensureClientColumn(name: string, definition: string): void {
    const columns = this.db.prepare('PRAGMA table_info(clients)').all() as Array<{ name: string }>;
    if (!columns.some((column) => column.name === name)) this.db.exec(`ALTER TABLE clients ADD COLUMN ${name} ${definition}`);
  }

  private appendAdminAuditInternal(
    eventType: string,
    actorId: string,
    targetId: string,
    at: string,
    details: Record<string, unknown>,
  ): void {
    this.db.prepare(`INSERT INTO admin_audit_events(id,event_type,actor_id,target_id,at,details_json)
      VALUES (?,?,?,?,?,?)`).run(randomUUID(), eventType, actorId, targetId, at, JSON.stringify(details));
  }
}
