import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  getPreviewKeys,
  isFeaturePreviewOn,
  previewHeaderValue,
  subscribeFeaturePreview,
  toggleFeaturePreview,
} from './featurePreview';

describe('featurePreview', () => {
  beforeEach(() => localStorage.clear());

  it('liga, desliga e serializa o header', () => {
    expect(getPreviewKeys()).toEqual([]);
    expect(previewHeaderValue()).toBeNull();

    toggleFeaturePreview('emendas');
    expect(isFeaturePreviewOn('emendas')).toBe(true);

    toggleFeaturePreview('trajetoria');
    expect(previewHeaderValue()).toBe('emendas,trajetoria');

    toggleFeaturePreview('emendas');
    expect(isFeaturePreviewOn('emendas')).toBe(false);
    expect(previewHeaderValue()).toBe('trajetoria');
  });

  it('notifica assinantes ao alternar', () => {
    const spy = vi.fn();
    const off = subscribeFeaturePreview(spy);
    toggleFeaturePreview('emendas');
    expect(spy).toHaveBeenCalled();
    off();
  });

  it('lixo no storage vale lista vazia', () => {
    localStorage.setItem('mp-feature-preview', '{nao-e-json');
    expect(getPreviewKeys()).toEqual([]);
  });

  it('getPreviewKeys devolve referencia estavel sem mudanca', () => {
    // Exigencia do useSyncExternalStore: snapshot novo so quando muda.
    toggleFeaturePreview('emendas');
    expect(getPreviewKeys()).toBe(getPreviewKeys());
  });
});
