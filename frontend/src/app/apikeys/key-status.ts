import { ApiKey } from '../core/api';

export type KeyStatus = 'active' | 'expired' | 'revoked';

/** Revocation wins over expiry, because it is the deliberate act. */
export function keyStatus(key: Pick<ApiKey, 'revoked_at' | 'expires_at'>, now = new Date()): KeyStatus {
  if (key.revoked_at) {
    return 'revoked';
  }
  return new Date(key.expires_at).getTime() <= now.getTime() ? 'expired' : 'active';
}
