# Mamute Politico Agent Guide

## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues for `voltdatalab/mamute-politico`. See `docs/agents/issue-tracker.md`.

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
