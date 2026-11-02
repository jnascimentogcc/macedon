import { HttpErrorResponse } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { errorKey } from './api';
import { I18n } from './i18n';

describe('I18n', () => {
  it('fills named parameters', () => {
    const text = TestBed.inject(I18n).t('documents.range', { from: 1, to: 20, total: 45 });

    expect(text).toBe('Showing 1–20 of 45');
  });

  it('keeps an unknown placeholder visible instead of printing undefined', () => {
    const text = TestBed.inject(I18n).t('detail.activated', {});

    expect(text).toBe('Version {number} is now active.');
  });
});

describe('errorKey', () => {
  const failure = (status: number) => new HttpErrorResponse({ status });

  it('explains an unreachable server, a missing item and a forbidden one', () => {
    expect(errorKey(failure(0))).toBe('common.offline');
    expect(errorKey(failure(404))).toBe('common.notFound');
    expect(errorKey(failure(403))).toBe('common.forbidden');
  });

  it('falls back to the given message for anything else', () => {
    expect(errorKey(failure(500), 'ask.failed')).toBe('ask.failed');
    expect(errorKey(new Error('boom'))).toBe('common.unknownError');
  });
});
