# Domain Docs

Mamute Politico uses a single-context domain documentation layout:

- Domain glossary: `CONTEXT.md`
- Architectural decisions: `docs/adr/`
- Planning artifacts: `docs/planning/`

Agents should read `CONTEXT.md` before planning or implementing work that touches legislative data, scrapers, dashboard metrics, authentication, or project favorites.

Use ADRs for decisions that are hard to reverse, surprising without context, and based on a real trade-off. Do not use ADRs for ordinary implementation notes.
