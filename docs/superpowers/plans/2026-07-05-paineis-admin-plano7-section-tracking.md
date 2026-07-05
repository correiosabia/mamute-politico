# Painéis Admin — Plano 7 (Section tracking) Plan

> REQUIRED SUB-SKILL: superpowers:executing-plans.

**Goal:** Rastrear "o que o user mais vê dentro de uma tela" (ex.: na página de parlamentar, se abre "Notas taquigráficas" ou olha "Temas do discurso") via eventos `section_view`, e mostrar "Seções mais vistas" no painel.

**Architecture:** Reusa `usage_events` (+ coluna `section`). O front emite `section_view` em: (a) ativação de aba (`onValueChange`), e (b) bloco entrando na viewport (IntersectionObserver, 1x por montagem). Ingesta pelo `POST /api/events`. Agregação `metrics_sections` (admin) → contagem por (page, section).

## Tasks
1. Migration `f6a7b8c9d0e1`: `ALTER usage_events ADD section TEXT`. ORM (api + scrappers).
2. Ingest: `_ALLOWED_TYPES` += `section_view`; `EventIn.section`; gravar section. Teste.
3. `metrics_sections(db)` (group by page, section, event_type='section_view') + rota `GET /admin/metrics/sections`. Teste.
4. Front: `sendSectionView(page, section)`; `useSectionOnce` (dedup por montagem); `<TrackSection page section>` (IntersectionObserver). Wire Tabs + blocos em `ParlamentarDashboard`.
5. Front: bloco "Seções mais vistas" na aba Ferramentas.
6. Preview: seed section_view + screenshot.
