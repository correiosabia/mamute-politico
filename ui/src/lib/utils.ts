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

/** Accent-insensitive alphabetical order for Portuguese names. */
export function compareByNome(a: string, b: string): number {
  return a.localeCompare(b, "pt-BR", { sensitivity: "base" });
}

export function sortByNome<T extends { nome: string }>(items: readonly T[]): T[] {
  return [...items].sort((x, y) => compareByNome(x.nome, y.nome));
}
