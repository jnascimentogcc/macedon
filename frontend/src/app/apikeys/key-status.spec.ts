import { keyStatus } from './key-status';

describe('keyStatus', () => {
  const now = new Date('2026-11-23T12:00:00Z');
  const future = '2027-01-01T00:00:00Z';
  const past = '2026-11-01T00:00:00Z';

  it('is active until the expiry date', () => {
    expect(keyStatus({ revoked_at: null, expires_at: future }, now)).toBe('active');
  });

  it('is expired once the expiry date has passed', () => {
    expect(keyStatus({ revoked_at: null, expires_at: past }, now)).toBe('expired');
  });

  it('is revoked even when it has also expired', () => {
    expect(keyStatus({ revoked_at: past, expires_at: past }, now)).toBe('revoked');
    expect(keyStatus({ revoked_at: past, expires_at: future }, now)).toBe('revoked');
  });
});
