# Proposed Issue Breakdown: Legislative Data Coverage

This is a draft breakdown for approval before publishing to GitHub Issues.

## 1. Configure Agent And Domain Docs

- Type: AFK
- Blocked by: none
- Goal: add repo-local agent instructions, domain glossary, and ADR location so future agents share vocabulary.

## 2. Add Data Freshness Check Command

- Type: AFK
- Blocked by: none
- Goal: provide a command that reports row counts and latest dates for dashboard-critical tables.

## 3. Restore Production Scraper Runtime

- Type: HITL
- Blocked by: issue 2
- Goal: deploy or reactivate the `mamute_scrappers` runtime in CapRover/Swarm and verify logs plus freshness movement.

## 4. Schedule Existing Chamber Crawlers

- Type: AFK
- Blocked by: issue 2
- Goal: add missing cron entries for already implemented Chamber data collectors where safe.

## 5. Replace Attendance Null With Vote-Derived Participation Metric

- Type: AFK
- Blocked by: issue 2
- Goal: use nominal votes to provide a transparent participation metric while explicit attendance tables remain empty.

## 6. Implement Committee Catalog Crawler

- Type: AFK
- Blocked by: issue 2
- Goal: populate `committee` from Chamber and Senate committee sources with idempotent upserts.

## 7. Implement Chamber Committee Attendance Crawler

- Type: AFK
- Blocked by: issue 6
- Goal: populate `committee_attendance` from Chamber attendance pages with fixtures and upsert tests.

## 8. Implement Senate Committee Attendance Crawler

- Type: AFK
- Blocked by: issue 6
- Goal: populate `committee_attendance` from Senate meeting pages, including name matching to parliamentarians.

## 9. Implement Videos And Audios Crawler

- Type: AFK
- Blocked by: issue 2
- Goal: populate `videos_audios` for Chamber sources.

## 10. Expose Dashboard Period And Freshness Metadata

- Type: AFK
- Blocked by: issues 2 and 5
- Goal: extend dashboard stats so the UI can distinguish no activity from stale or missing data.
