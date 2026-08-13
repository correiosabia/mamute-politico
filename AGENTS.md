# Mamute Politico Agent Guide

## Constitution (mandatory)

This repository operates under Spec-Driven Development. Read
`.sdd/memory/constituicao.md` before planning or implementing anything.

Its `0*` clauses are **entrenched clauses (cláusulas pétreas): compliance is
mandatory** and overrides any contrary impulse from whoever implements, human
or AI. In short:

- **0a** — a new feature (including a new crawler, a new cron line, or a tier
  change) requires `.sdd/specs/NNN-slug/{spec,plano,tarefas}.md` approved
  before any code. Bugfix, refactor and cosmetic changes do not.
- **0b** — the audience is a non-technical subscriber; a zero must never be
  mistakable for uncollected data, and `detail` in an API error reaches the
  screen.
- **0c** — recommend one option with reasoning; do not hand over a menu.
- **0d** — `feat/*` branch → PR with all 7 CI gates green → merge to `main`,
  which **deploys straight to production**. There is no staging.
- **0e** — user scope comes from the Ghost JWT, never from the request body or
  URL; admin failures return 404.
- **0f** — user-visible changes update the affected module README (and
  `CONTEXT.md` / `docs/adr/` when applicable) in the same PR.

## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues for `correiosabia/mamute-politico`. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the standard triage labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, and `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

This repo uses a single-context domain layout: `CONTEXT.md` plus ADRs under `docs/adr/`. See `docs/agents/domain.md`.

## Working conventions

- Prefer small, verifiable vertical slices for crawler work.
- Keep crawler changes idempotent: rerunning a scraper should update existing rows without duplicating data.
- Add parser tests with fixtures before broad network runs.
- Treat production data freshness as part of acceptance, not an afterthought.
- Do not print secrets from `.env`, container env, or JWTs in logs or reports.
