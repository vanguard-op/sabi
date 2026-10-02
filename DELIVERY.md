# Sabi: delivery

## Source of truth

`docs/Sabi/` — git submodule `vanguard-op/sabi-docs`, pinned at `3a87093`. 13 documents: overview,
user-personas, branding, features, nfr, roadmap, architecture, operations, schema, model-quality,
risk-log, user-flow, screens (+ 9 screen specs). The roadmap owns build order; this file owns state.

## Team and file ownership

| Owner | Owns | Read-only |
|---|---|---|
| lead | DELIVERY.md, CONTRACTS.md, ASSETS.md, .delivery/**, packages/contracts/** | docs/** |
| infra-engineer | infra/**, .github/**, docker-compose*.yml, Makefile, root config, .gitignore | docs/**, packages/contracts/** |
| backend-engineer | services/api/**, services/payments/**, migrations/** | packages/contracts/**, docs/** |
| frontend-engineer | apps/mobile/** | packages/contracts/**, docs/** |
| ai-engineer | services/ai/** | packages/contracts/**, docs/** |
| visual-artist | assets/** | docs/** |
| qa-engineer | tests/** | packages/contracts/**, docs/** |

Scratch: each owner uses `.scratch/<owner>/**` (gitignored). No two owners share a file or directory;
concurrent tasks within an owner use the subdirectories named in their route.

## Stack

| Layer | Choice |
|---|---|
| Client | Flutter (Dart), Android + iOS, go_router, Riverpod, Dio, freezed/json_serializable, passkeys |
| Backend | Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic, Uvicorn |
| Auth | Self-hosted WebAuthn (py_webauthn), Argon2id recovery secrets, session cookies |
| Data | PostgreSQL 16 + pgvector (primary, isolated payment store, full-text search, retrieval) |
| AI | Google Gemini 3.1 Pro (primary; exact provider ID pinned at Foundation); Gemini flash path for high-volume intent; google-genai SDK; evaluation harness |
| Infrastructure | Docker Compose (dev), GitHub Actions (CI), Terraform (IaC) |
| Hosting | AWS af-south-1 (Cape Town) — nearest managed Africa region to the Nigeria-primary intent; NDPA transfer assessment required |

## Structure

```
apps/mobile/          Flutter client
services/api/         FastAPI modular monolith
services/payments/    isolated payment module (own schema and audit log)
services/ai/          model serving and evaluation harness
packages/contracts/   OpenAPI and shared schemas
assets/               visual assets
infra/                IaC and CI/CD
tests/                integration and acceptance tests
docs/                 source of truth (git submodule)
```

## Contracts

`CONTRACTS.md` — C-001 to C-016 frozen for Phase 1.

## Token map

Branding tokens are implemented once at `apps/mobile/lib/design_system/tokens.dart`; no token is
redefined elsewhere. Source: `docs/Sabi/branding.md`, "Design System".

| Group | Tokens |
|---|---|
| Colour | primary 100–900, grey 50–900, success, warning, error, info, accent (each with light and dark values) |
| Semantic roles | surface, surface-secondary, text-primary, text-secondary, border, on-primary |
| Typography | display, h1, h2, h3, body-large, body, body-small, caption |
| Spacing | space-xs, space-sm, space-md, space-lg, space-xl, space-2xl, space-3xl |
| Sizing | radius-sm/md/lg/full, button-height, input-height, icon-sm/md/lg |
| Shadows | shadow-none/sm/md/lg/xl (light and dark) |

## Assets

`ASSETS.md` — asset ledger and generation briefs, written at Foundation.

## Conventions

- API base path `/v1`; JSON; field names camelCase.
- Error envelope: `{ "error": { "code": string, "message": string, "details": object? } }`.
- Session: HttpOnly, Secure, SameSite cookie; operator roles require MFA.
- Amounts: integer minor units (kobo); always paired with a `currency` field; formatted to NGN at the edge.
- Identifiers: opaque strings (UUIDv7). Timestamps: RFC 3339 UTC.
- Pagination: cursor-based (`?cursor=&limit=`).
- Locales: `en`, `pcm` at launch; fall back to English with a note.
- Idempotency-Key header on money movements (Phase 2).
- Composed surfaces use only the client component catalogue; an unknown component renders the fallback.
- Retrieved content is untrusted and never overrides payment policy.
- No secrets in code or logs; configuration from a secret store.
- Commit messages cite durable IDs (FEAT-###, C-###), never task IDs or `.delivery/` paths.
- Branching: from Phase 1 feature work onward, engineers commit to `dev`; the lead merges `dev` into `main` at each phase gate.

## Behavior rules

- No payment executes without an explicit, signed authorisation bound to amount and payee.
- Below the confidence threshold, ask exactly one clarifying question; never invent a target, amount, or reference.
- A catalogue miss records the query; never fabricate a service or collecting body.
- Provider or model failure degrades to keyword and search resolution with mandatory confirmation.
- Offline: authorisation unavailable; queued requests reconcile by idempotency key, never double-pay.
- Colour is never the only signal; honour reduced motion.
- A channel link never creates a second account.
- Operators: MFA, least privilege, no impersonation, tamper-evident audit.

## Task board

### Completed phases

| Phase | Closed | Notes |
|---|---|---|

### Phase 1: Foundations

| Task | Feature | Owner | Status | Contract |
|---|---|---|---|---|
| T-001 | FEAT-001, FEAT-003, FEAT-004, FEAT-011, FEAT-012 | infra-engineer | Done | — |
| T-002 | FEAT-001, FEAT-004, FEAT-011 | frontend-engineer | Backlog | — |
| T-003 | FEAT-001, FEAT-004, FEAT-012 | backend-engineer | Backlog | — |
| T-004 | FEAT-003, FEAT-004, FEAT-011 | ai-engineer | Backlog | — |
| T-005 | FEAT-001 | backend-engineer | Backlog | C-001–C-008 |
| T-006 | FEAT-001 | frontend-engineer | Backlog | C-001–C-008 |
| T-007 | FEAT-003 | ai-engineer | Backlog | C-009 |
| T-008 | FEAT-004 | backend-engineer | Backlog | C-010, C-011 |
| T-009 | FEAT-004 | ai-engineer | Backlog | C-010 |
| T-010 | FEAT-004, FEAT-011 | frontend-engineer | Backlog | C-009–C-012 |
| T-011 | FEAT-011 | ai-engineer | Backlog | C-012 |
| T-012 | FEAT-012 | backend-engineer | Backlog | C-013–C-016 |
| T-013 | — | visual-artist | Done | — |

## Decisions log

| # | Decision | Rationale | By |
|---|---|---|---|
| D-001 | Client platform is Flutter | One cross-platform Android + iOS codebase; user-selected | user |
| D-002 | Backend is Python + FastAPI | User-selected runtime for the modular monolith | user |
| D-003 | PostgreSQL + pgvector for primary, payment, search, and retrieval | One relational engine covers all four stores in the architecture | user |
| D-004 | Self-hosted WebAuthn passkeys with Argon2id recovery codes | Owns the passkey ceremony and single-use recovery contract in FEAT-001 and NFR-021 | user |
| D-005 | Managed cloud in the Africa region | Meets the Nigeria-primary intent as closely as managed regions allow; provider, region, and NDPA transfer position validated at Foundation | user |
| D-006 | Gemini 3.1 Pro pinned as the primary model | Strong structured output and multilingual behaviour within the NFR-050–052 cost ceilings; exact provider ID pinned at Foundation | user |
| D-007 | Monorepo for all modules, including the payment module | Matches the modular monolith and one shared contract | user |
| D-008 | All visual assets are sourced new | None exist; user confirmed | user |
| D-009 | docs/ tracked as a git submodule, both repos under vanguard-op | Parent never points at an unpushed docs commit | user |
| D-010 | Monetary amounts are integer minor units (kobo) | Removes floating-point rounding error from a payment; schema.md updated to match | user |
| D-011 | Phase 1 FEAT-012 scoped to the provider registration and review API plus operator-gated endpoints; Operations Console and provider-portal UIs deferred | operations.md defines the Phase 1 review workflow, but branding.md and screens.md are mobile-only and specify no console or portal surface; recorded for acknowledgment | lead |
| D-012 | Deployment region pinned to AWS af-south-1 (Cape Town) | Nearest managed Africa region to the Nigeria-primary residency intent under D-005; NDPA transfer assessment required before production | lead |

## Definition of Done

- Code implements the route's contract and satisfies the acceptance criteria the route cites.
- Unit tests cover the criteria and edge cases; they pass.
- Contract conformance verified: fields, status codes, and errors match CONTRACTS.md.
- Lint, format, and type checks are clean.
- No secrets in code or logs; no writes outside the route's `Own`.
- The engineer reports the task done with evidence.

## Key commands

Provisional; infra-engineer pins these at Foundation.

| Action | Command |
|---|---|
| Start dependencies | `docker compose up -d` |
| Backend dev | `cd services/api && uvicorn app.main:app --reload` |
| Backend tests | `cd services/api && pytest` |
| Client dev | `cd apps/mobile && flutter run` |
| Client tests | `cd apps/mobile && flutter test` |
| AI tests | `cd services/ai && pytest` |
| Lint | `ruff check .` and `flutter analyze` |
