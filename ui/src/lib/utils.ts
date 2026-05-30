import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Lowercase and strip accents for accent-insensitive substring search. */
export function normalizeForSearch(text: string): string {
  return text
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

export function includesNormalizedSearch(haystack: string, needle: string): boolean {
  const normalizedNeedle = normalizeForSearch(needle.trim());
  if (!normalizedNeedle) return true;
  return normalizeForSearch(haystack).includes(normalizedNeedle);
}
