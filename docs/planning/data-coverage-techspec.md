# TechSpec: Legislative Data Coverage

## Current State

Tables exist for the documented model, but crawler coverage is uneven:

- Implemented and modeled: parliamentarians, social networks, propositions, authorship, proposition types, proposition status, agencies, nominal votes, speech transcripts, and Senate speech-to-proposition links.
- Modeled but missing scrapers: plenary attendance, committees, committee attendance, and videos/audios.
- Implemented but not fully scheduled in the current cron: several Chamber crawlers, including agency, proposition type, roll-call votes, and speech transcripts.
- Production has no active `mamute-scrappers` service in the observed CapRover/Swarm environment.

## Proposed Modules

### Data Freshness Check

A small command that reports row count, distinct parliamentarians where applicable, minimum date, maximum date, and stale/fresh status for dashboard-critical tables.

Initial tables:

- `proposition`
- `authors_proposition`
- `roll_call_votes`
- `speeches_transcripts`
- `plenary_attendance`
- `committee_attendance`

### Scraper Runtime

The existing `mamute_scrappers` Docker image and cron entrypoint should be made operational in production. The first deploy task should avoid changing scraper logic and focus on runtime presence, logs, env, and state volume.

### Parser Fixtures

New scraper slices should add fixtures under a predictable test fixture directory and test normalized payloads before any database writes.

### Participation Metric

The dashboard should first expose a participation metric derived from nominal votes. Later explicit attendance crawlers may enrich or replace it only after the meaning is documented.

### Missing Crawlers

New crawlers should follow the existing package split:

- Chamber sources under `mamute_scrappers/camara_crawler`
- Senate sources under `mamute_scrappers/senado_crawler`

Each crawler should provide:

- a command-line entry point;
- source request functions;
- parser functions;
- idempotent upsert functions;
- tests for parser and upsert behavior;
- cron entry only after the command is verified.

## Slice Order

1. Agent/docs setup and domain glossary.
2. Freshness check command.
3. Production scraper runtime.
4. Add existing Chamber crawlers to cron where appropriate.
5. Dashboard participation metric from nominal votes.
6. Committee catalog crawler.
7. Chamber committee attendance crawler.
8. Senate committee attendance crawler.
9. Videos/audios crawler.
10. Dashboard metadata for period and freshness.

## Validation Gates

- `python -m pytest api/tests -q`
- targeted scraper parser/upsert tests
- `python -m mamute_scrappers.<crawler> --help`
- dry-run or limited-ID crawler execution
- data freshness command before and after production runs

## Risks

- Source HTML pages may change without notice.
- Senate committee attendance parsing may require fuzzy matching by parliamentarian name.
- Deploying the scraper runtime can be confused with implementing missing crawlers; these should remain separate tasks.
- If dashboard labels change before metric semantics are clear, users may trust a misleading number.
