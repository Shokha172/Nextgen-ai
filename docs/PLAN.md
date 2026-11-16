# NEXTGEN AI — Implementation Plan

## 0. Environment findings (verified, not assumed)

| Item | Finding | Consequence |
|---|---|---|
| OS | Debian 13 (trixie), x86_64, 2 vCPU, 1.9 GB RAM | Lean containers, no heavy JVM/statmodels |
| Python | 3.13.18 | FastAPI 0.163 / SQLAlchemy 2.1 / Pydantic 2.14 |
| Node | 20.20.2, npm 10.8.2 | Next.js App Router + TS |
| PostgreSQL | **none pre-installed → installed PostgreSQL 17.12**, cluster at `127.0.0.1:5433` | Real Postgres: RLS, JSONB, NUMERIC, Alembic all genuinely exercised |
| Docker | **not available (no daemon)** | Dockerfiles + compose are written and lint-reviewed but **cannot be executed here** — stated honestly in README |
| Outbound network | PyPI + npm reachable | deps installed & pinned |

## 1. Architecture

```
                      ┌──────────────────────────┐
  Next.js 15 (RSC) ──►│  FastAPI  /api/v1        │──► PostgreSQL 17
  httpOnly cookie     │  JWT + RBAC + org gate   │    RLS FORCE + app role
  server-side fetch   │  services/ (pure logic)  │    (no BYPASSRLS)
                      └──────┬─────────┬─────────┘
                             │         │
              AI provider ◄──┘         └──► Export (PDF/XLSX/CSV)
              (Gemini | rule-based,        Telegram link codes
               numeric-guard validated)
                             ▲
                    HTTP (service key)
                             │
              ┌──────────────┴───────────────┐
              │ bots/  aiogram 3             │
              │ demo_bot.py   official_bot.py│  ← isolated tokens, isolated orgs
              └──────────────────────────────┘
```

**Ground rules encoded in the build**
- Every tenant row carries `organization_id`; RLS `FORCE` + policy on every tenant-data table, app connects as a non-superuser, non-`BYPASSRLS` role. App-layer filters are a *second* wall, not the only one.
- `kWh` (energy) vs `kW` (power) are separate columns, separate types, separate UI labels. `kW = kWh / (interval_minutes/60)`.
- All timestamps stored `TIMESTAMPTZ` in UTC; rendered in `Asia/Tashkent`.
- Demo and production isolation is by **separate bot tokens, separate service keys, and `is_demo` organizations**; demo bot can only ever resolve to the demo org.
- No number reaches a user that did not come from a DB query or a deterministic function. The AI layer only *narrates* a validated fact bundle, and a numeric guard rejects any figure not in that bundle.

## 2. Phases (as executed)

| Phase | Contents | Gate |
|---|---|---|
| 1 Foundation | config, DB layer, RLS, models, Alembic, auth, orgs, members, RBAC, audit | pytest auth + isolation green |
| 2 Core | meters, imports (CSV/XLSX, cumulative→interval, duplicates, gaps, resets), analytics, anomalies | pytest analytics/import/anomaly green |
| 3 Intelligence | forecast (MA/Holt-Winters + backtest), savings, AI advisor (grounded), exports | pytest forecast/AI-grounding green |
| 4 Telegram | link codes, service-key sessions, demo bot, official bot, alerts | pytest telegram linking green |
| 5 Quality | security tests, rate limits, upload hardening, docs, seed | full suite green |
| 6 Deployment | Docker, compose, migrations-on-boot, health checks, deploy docs | config lint + documented limits |

## 3. Module map

```
backend/app
  core/       config logging errors security db tenant rate_limit deps
  models/     16 tables, UUID PKs, org-scoped, timezone-aware
  schemas/    pydantic v2 request/response contracts
  services/   analytics anomalies forecast importer ai/* advisor savings export seed
  api/v1/     auth orgs members meters imports analytics dashboard anomalies
              forecast ai reports savings notifications telegram audit
bots/         aiogram 3, polling (dev) or webhook (prod), i18n uz/ru/en
frontend/     Next.js App Router, server components, cookie session, Recharts
```

## 4. Honest limitations (declared up front)
1. **Docker daemon absent** → compose/Dockerfiles authored, not executed here.
2. **No SMTP** → password reset + invitations issue tokens; in dev they are returned in the API response/log (guarded by `EXPOSE_DEV_TOKENS`), in prod they must be emailed (interface stubbed, documented).
3. **No browser** → frontend verified by production build + typecheck + server-rendered HTML assertions, not Playwright/visual snapshots.
4. **Gemini key absent** → AI Advisor runs its deterministic grounded fallback provider; the Gemini provider is fully implemented and selected automatically when `GEMINI_API_KEY` is set.
5. **Tariffs are organization-configured**; the seeded 450 UZS/kWh demo value is labelled an example configuration, never a market fact.
