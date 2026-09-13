import type { ApprovalState } from '../../protocol/src/index.ts';

const transitions: Record<ApprovalState, ReadonlySet<ApprovalState>> = {
  REQUESTED: new Set(['PENDING', 'REJECTED', 'EXPIRED']),
  PENDING: new Set(['APPROVED', 'REJECTED', 'EXPIRED', 'REVOKED']),
  APPROVED: new Set(['CONSUMED', 'REVOKED', 'EXPIRED']),
  REJECTED: new Set(),
  EXPIRED: new Set(),
  REVOKED: new Set(),
  CONSUMED: new Set(),
};

export function assertTransition(from: ApprovalState, to: ApprovalState): void {
  if (!transitions[from].has(to)) throw new Error(`ILLEGAL_TRANSITION:${from}->${to}`);
}
