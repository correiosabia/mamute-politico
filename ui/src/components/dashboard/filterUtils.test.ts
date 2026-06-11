import { describe, expect, it } from 'vitest';

import { formatDateOnlyLabel } from './filterUtils';

describe('formatDateOnlyLabel', () => {
  it('formats date-only API values without shifting the calendar day', () => {
    expect(formatDateOnlyLabel('2026-05-25')).toBe('25/05/2026');
    expect(formatDateOnlyLabel('2026-05-18')).toBe('18/05/2026');
  });

  it('uses the calendar date portion from ISO-like values', () => {
    expect(formatDateOnlyLabel('2026-05-25T23:30:00Z')).toBe('25/05/2026');
  });

  it('returns invalid values unchanged', () => {
    expect(formatDateOnlyLabel('not-a-date')).toBe('not-a-date');
  });
});
