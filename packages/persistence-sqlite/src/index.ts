import { DatabaseSync } from 'node:sqlite';
import type {
  ApprovalChallengePackage,
  ApprovalReceipt,
  ApprovalRequest,
  AuditEvent,
  AuthenticatorRecord,
  ExecutionGrant,
} from '../../protocol/src/index.ts';

export class SqliteStore {
  readonly db: DatabaseSync;

  constructor(path = ':memory:') {
    this.db = new DatabaseSync(path);
    this.db.exec(`
      PRAGMA foreign_keys = ON;
      CREATE TABLE IF NOT EXISTS clients (
        id TEXT PRIMARY KEY,
        api_key_hash TEXT NOT NULL UNIQUE,
        enabled INTEGER NOT NULL DEFAULT 1
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
      CREATE INDEX IF NOT EXISTS idx_audit_request ON audit_events(request_id, at);
    `);
  }

  close(): void { this.db.close(); }

  registerClient(id: string, apiKeyHash: string): void {
    this.db.prepare('INSERT OR REPLACE INTO clients(id, api_key_hash, enabled) VALUES (?, ?, 1)').run(id, apiKeyHash);
  }

  authenticateClient(apiKeyHash: string): string | null {
    const row = this.db.prepare('SELECT id FROM clients WHERE api_key_hash = ? AND enabled = 1').get(apiKeyHash) as { id: string } | undefined;
    return row?.id ?? null;
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
    this.db.prepare('INSERT INTO audit_events(id,request_id,event_type,actor_id,event_json,at) VALUES (?,?,?,?,?,?)').run(
      event.id, event.requestId, event.eventType, event.actorId, JSON.stringify(event), event.at,
    );
  }

  listAudit(requestId: string): AuditEvent[] {
    const rows = this.db.prepare('SELECT event_json FROM audit_events WHERE request_id=? ORDER BY seq').all(requestId) as any[];
    return rows.map((r) => JSON.parse(r.event_json));
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
      if (args.auditEvent) {
        this.db.prepare('INSERT INTO audit_events(id,request_id,event_type,actor_id,event_json,at) VALUES (?,?,?,?,?,?)').run(
          args.auditEvent.id, args.auditEvent.requestId, args.auditEvent.eventType, args.auditEvent.actorId, JSON.stringify(args.auditEvent), args.auditEvent.at,
        );
      }
      this.db.exec('COMMIT');
      return { grant: args.grant, reused: false };
    } catch (error) {
      this.db.exec('ROLLBACK');
      throw error;
    }
  }
}
