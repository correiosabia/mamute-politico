export function getSafeExternalUrl(value: string | null | undefined): string | null {
  if (!value) return null;

  try {
    const url = new URL(value.trim());
    if (url.protocol !== 'http:' && url.protocol !== 'https:') {
      return null;
    }
    return url.href;
  } catch {
    return null;
  }
}

export function openSafeExternalUrl(value: string | null | undefined): boolean {
  const safeUrl = getSafeExternalUrl(value);
  if (!safeUrl) return false;

  window.open(safeUrl, '_blank', 'noopener,noreferrer');
  return true;
}
