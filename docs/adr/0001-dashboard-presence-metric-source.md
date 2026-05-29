# ADR 0001: Dashboard Presence Metric Source

## Status

Proposed

## Context

The dashboard exposes `attendance_avg_percent` for the monitored parliamentarians of an authenticated project. The schema includes `plenary_attendance` and `committee_attendance`, but production currently has no rows in either table, and the codebase has no scraper that writes to them.

The original data model notes say plenary attendance should be taken from nominal votes because presence is only mandatory in deliberative sessions. Chamber pages also expose explicit plenary and committee attendance pages, while Senate committee attendance appears to require HTML parsing from commission meeting pages.

## Decision

Use nominal votes as the first production-grade source for plenary participation, and treat explicit attendance pages as a later enrichment source.

The first implementation should make the metric transparent: if it is derived from nominal votes, the API and UI should not imply that it is official attendance from `plenary_attendance` unless that table is actually populated from a presence source.

## Consequences

- We can unblock dashboard presence with data already collected by `roll_call_votes`.
- The metric needs clear naming or metadata so users understand what is being measured.
- Future crawlers may still populate `plenary_attendance` and `committee_attendance`, but they should not silently change the meaning of the dashboard metric without another ADR or explicit migration.
