# PRD: Legislative Data Coverage For Dashboard Metrics

## Problem Statement

Mamute Politico has a dashboard that summarizes monitored parliamentarian activity, but the data coverage is incomplete. Some dashboard numbers return zero or `null` not because there was no activity, but because the backing tables are stale, empty, or not populated by any running scraper.

The immediate symptom is `attendance_avg_percent` returning `null` for every project because `plenary_attendance` and `committee_attendance` are empty. A broader audit showed several modeled tables with no scraper, and some implemented scrapers are not scheduled in the current production environment.

## Solution

Make legislative data coverage explicit and operational:

- Reactivate or deploy the scraper runtime in production.
- Add a data freshness check across dashboard-critical tables.
- Schedule existing implemented scrapers that are missing from cron.
- Implement missing scrapers or derived metrics in thin vertical slices.
- Make the dashboard API clear about period and freshness so missing data is visible instead of silently looking like zero activity.

## User Stories

1. As a project user, I want dashboard stats to reflect recent monitored parliamentarian activity, so that I can trust the dashboard.
2. As a project user, I want zeros to mean no activity, not missing collection, so that I do not misread stale data.
3. As a project user, I want presence or participation metrics to be clearly named, so that I know what is being measured.
4. As an operator, I want to know which scraper last updated each table, so that I can diagnose stale dashboard data.
5. As an operator, I want scrapers to be idempotent, so that reruns are safe.
6. As an engineer, I want crawler parser fixtures, so that source HTML/XML/JSON changes are caught before production.
7. As an engineer, I want independently shippable crawler slices, so that one missing source does not block all data coverage.
8. As an agent, I want documented source-to-table contracts, so that future implementation can proceed without rediscovering the model.

## Implementation Decisions

- Keep the current dashboard stats endpoint compatible with the UI while adding metadata in a follow-up slice.
- Treat data freshness as a first-class acceptance criterion.
- Implement missing collection in vertical slices: production scraper runtime, freshness check, scheduled existing scrapers, presence metric, committees, committee attendance, and videos/audios.
- Use nominal votes as the first source for a dashboard participation metric, per ADR 0001.
- Keep crawler commands idempotent and safe to rerun.
- Prefer parser fixtures and narrow integration tests over broad live-network tests.

## Testing Decisions

- Parser tests should exercise source fixtures and expected normalized payloads.
- Upsert tests should prove reruns update existing records instead of duplicating rows.
- Dashboard tests should cover missing-data versus zero-activity behavior.
- Operational checks should report row counts and max dates for dashboard-critical tables.

## Out Of Scope

- Full historical backfill of every source before any dashboard improvement ships.
- Rewriting existing scrapers into a new framework.
- Changing Ghost authentication or project favorite behavior.
- Guaranteeing Senate committee attendance parity in the first implementation slice.

## Further Notes

The first milestone should focus on trustworthy visibility: run the scraper service, expose freshness, and avoid misleading dashboard metrics. New crawlers can then be added behind that observability.
