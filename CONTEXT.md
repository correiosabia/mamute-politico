# Mamute Politico Context

## Domain Terms

### Mamute Politico

The product that lets authenticated Ghost members monitor legislative activity from selected Brazilian parliamentarians.

### Project

A customer workspace represented by a `projetos` row. A project is identified from the authenticated Ghost member e-mail and owns the list of monitored parliamentarians.

### Monitored Parliamentarian

A parliamentarian favorited by a project through `projetos_parliamentarian`. Dashboard metrics are scoped to the monitored parliamentarians of the authenticated project.

### Parliamentarian

An elected official from either the Chamber of Deputies or the Senate. Parliamentarians are stored in `parliamentarian` and are keyed to source-system codes through `parliamentarian_code`.

### Proposition

A legislative matter stored in `proposition`. Propositions can be associated with parliamentarian authors through `authors_proposition`.

### Nominal Vote

A recorded vote by a parliamentarian on a proposition, stored in `roll_call_votes`.

### Speech Transcript

A speech or stenographic note associated with a parliamentarian, stored in `speeches_transcripts`.

### Committee

A legislative committee or collegiate body stored in `committee`.

### Plenary Attendance

A parliamentarian attendance record for plenary activity, stored in `plenary_attendance` when collected from a source or derived according to an ADR.

### Committee Attendance

A parliamentarian attendance record for committee activity, stored in `committee_attendance`.

### Dashboard Stats

Aggregated activity counts shown in the authenticated project dashboard. These counts must make their source period and data freshness clear enough that a zero can be distinguished from missing data.

### Data Freshness

The recency of collected legislative data per source table. Freshness is part of operational correctness for dashboard metrics and crawler acceptance.

### Scraper

A command under `mamute_scrappers` that collects source data and persists it into the PostgreSQL legislative database. Scrapers must be idempotent.
