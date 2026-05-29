import { useState } from 'react';

type StringFilterShape<T> = {
  [K in keyof T]: string;
};

export interface FilterChip<K extends string> {
  key: K;
  label: string;
  value: string;
}

export function toIsoOrUndefined(value: string): string | undefined {
  if (!value) return undefined;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return undefined;
  return date.toISOString();
}

export function formatDateTimeLabel(value: string): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
}

export function formatDateOnlyLabel(value: string): string {
  if (!value) return '';
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString('pt-BR');
}

export function buildFilterChips<T extends StringFilterShape<T>, K extends keyof T & string>(
  filters: T,
  definitions: ReadonlyArray<readonly [K, string]>
): Array<FilterChip<K>> {
  return definitions
    .map(([key, label]) => ({ key, label, value: filters[key] }))
    .filter((chip) => Boolean(chip.value));
}

export function useDraftAppliedFilters<T extends StringFilterShape<T>>(initialFilters: T) {
  const [draftFilters, setDraftFilters] = useState<T>(initialFilters);
  const [appliedFilters, setAppliedFilters] = useState<T>(initialFilters);
  const [filtersOpen, setFiltersOpen] = useState(false);

  const onFiltersOpenChange = (open: boolean) => {
    setFiltersOpen(open);
    if (open) setDraftFilters(appliedFilters);
  };

  const applyFilters = () => {
    setAppliedFilters(draftFilters);
    setFiltersOpen(false);
  };

  const clearAllFilters = () => {
    setDraftFilters(initialFilters);
    setAppliedFilters(initialFilters);
  };

  const clearFilter = (key: keyof T) => {
    setDraftFilters((prev) => ({ ...prev, [key]: '' }));
    setAppliedFilters((prev) => ({ ...prev, [key]: '' }));
  };

  return {
    draftFilters,
    setDraftFilters,
    appliedFilters,
    filtersOpen,
    onFiltersOpenChange,
    applyFilters,
    clearAllFilters,
    clearFilter,
  };
}
