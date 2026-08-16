# Mamute Politico Agent Guide

## Working rules

These describe how this repository actually behaves. They are not aspirational.

- **No staging.** `feat/*` branch → PR with all 7 CI gates green → merge to
  `main`, which **deploys straight to production**. A user-visible feature ships
  behind a feature flag (`ui/src/lib/featureFlags.ts`), off by default.
- **Deploy applies migrations after the containers start.** New code runs
  against the old schema for a window, so a query that depends on a brand-new
  column must guard for its absence — see `_table_has_column` in
  `api/routers/roll_call_votes.py`.
- **User scope comes from the Ghost JWT**, never from the request body or URL
  (`_get_project_from_token_email`). Admin gate failures return 404, not 403.
- **The audience is a non-technical subscriber.** `detail` in an API error
  reaches the screen, so write it as product copy. A zero must never be
  mistakable for uncollected data.
- **User-visible changes update the affected module README** — and `CONTEXT.md`
  or `docs/adr/` when a term or a hard-to-reverse decision is involved — in the
  same PR.

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
