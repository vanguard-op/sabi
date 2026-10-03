# Sabi: delivery

## Source of truth

`docs/Sabi/` — git submodule `vanguard-op/sabi-docs`, pinned at `47fc660`. 14 documents: overview,
user-personas, branding, features, nfr, roadmap, architecture, operations, schema, model-quality,
risk-log, user-flow, screens (+ 9 screen specs). The roadmap owns build order; this file owns state.

## Team and file ownership

| Owner | Owns | Read-only |
|---|---|---|
| lead | DELIVERY.md, CONTRACTS.md, ASSETS.md, .delivery/**, packages/contracts/** | docs/** |
| infra-engineer | infra/**, .github/**, docker-compose*.yml, Makefile, root config, .gitignore | docs/**, packages/contracts/** |
| backend-engineer | services/api/**, services/payments/**, migrations/** | packages/contracts/**, docs/** |
| frontend-engineer | apps/mobile/**, apps/console/** | packages/contracts/**, docs/** |
| ai-engineer | services/ai/** | packages/contracts/**, docs/** |
| visual-artist | assets/** | docs/** |
| qa-engineer | tests/** | packages/contracts/**, docs/** |

Scratch: each owner uses `.scratch/<owner>/**` (gitignored). No two owners share a file or directory;
concurrent tasks within an owner use the subdirectories named in their route.

## Stack

| Layer | Choice |
|---|---|
| Client | Flutter (Dart), Android + iOS, go_router, Riverpod, `http`, hand-written JSON models, `passkeys` plugin (Corbado) for the WebAuthn ceremony |
| Backend | Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic, Uvicorn |
| Auth | Self-hosted WebAuthn (py_webauthn), Argon2id recovery secrets, session cookies |
| Data | PostgreSQL 16 + pgvector (primary, isolated payment store, full-text search, retrieval) |
| AI | Gemini `gemini-3.1-pro-preview` (primary) and `gemini-3.1-flash-lite` (high-volume intent, D-026); google-genai SDK; evaluation harness |
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

`CONTRACTS.md` — C-001–C-044: Phase 1 identity/catalogue (C-001–C-016), Phase 2 payment loop (C-017–C-038, C-035 at revision 1), and the Operations Console (C-039–C-044).

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
| Motion | skeleton-pulse; payment states: success 400–600ms one-shot, pending seamless loop, error firm stop with no bounce; honours reduced motion |

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
- Backend domain modules are auto-discovered: expose `router: APIRouter` at `app/<module>/router.py` and declare paths without the `/v1` prefix. A nested module registers its dotted name in `MODULE_NAMES` (e.g. `identity.verification`).
- AI feature modules are auto-discovered: expose `router: APIRouter` at `<feature>/router.py` (packages `intent`, `ranking`, `composition`) and declare paths without the `/v1` prefix.

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
| Phase 1: Foundations | 2026-10-02 | C-001–C-016 implemented and conformant; FEAT-001/003/004/011/012 accepted; MQ-001–MQ-003 live bars deferred under D-022; post-phase fixes T-026–T-029 and T-045 verified and merged; the D-024 Operations Console wave shipped C-039–C-044 and the staff console (T-049–T-051, T-054, T-057–T-059) |

### Phase 2: The payment loop

Active. The payment loop, receipts, cases, identity verification, federal and bill flows, channels, and the Operations Console back end are built; the mobile client is wired to the gateway behind the `USE_LIVE_REPOSITORIES` build flag (T-060). The board's `Backlog` status is the dispatch gate. D1–D3 remain unsecured; the phase proceeds on mock/sandbox rails under D-027.

| Task | Feature | Owner | Status | Contract |
|---|---|---|---|---|
| T-030 | FEAT-005 | backend-engineer | Done | C-017–C-019 |
| T-031 | FEAT-002 | backend-engineer | Done | C-020–C-022 |
| T-032 | FEAT-008 | backend-engineer | Done | C-023–C-025 |
| T-033 | FEAT-009 | backend-engineer | Done | C-026–C-029 |
| T-034 | FEAT-006 | backend-engineer | Done | C-030–C-032 |
| T-035 | FEAT-007 | backend-engineer | Done | C-033–C-035 |
| T-036 | FEAT-010 | backend-engineer | Done | C-036–C-038 |
| T-037 | FEAT-005, FEAT-006, FEAT-007 | frontend-engineer | Done | C-017–C-019, C-030–C-035 |
| T-038 | FEAT-008, FEAT-009 | frontend-engineer | Done | C-023–C-029 |
| T-039 | FEAT-002 | frontend-engineer | Done | C-020–C-022 |
| T-040 | FEAT-005, FEAT-009 | ai-engineer | Done | C-017, C-026–C-029 |
| T-041 | FEAT-005 | backend-engineer | Done | C-017 |
| T-042 | FEAT-006, FEAT-007, FEAT-009 | backend-engineer | Done | C-026–C-035 |
| T-043 | FEAT-010 | backend-engineer | Done | C-036–C-038 |
| T-044 | FEAT-005, FEAT-006, FEAT-008, FEAT-009 | qa-engineer | Backlog | C-017–C-029 |
| T-046 | FEAT-008 | backend-engineer | Done | C-024 |
| T-047 | — | backend-engineer | Done | — |
| T-048 | FEAT-009 | backend-engineer | Done | C-029 |
| T-053 | FEAT-006 | backend-engineer | Done | C-030 |
| T-055 | FEAT-005 | backend-engineer | Done | C-017–C-019 |
| T-056 | FEAT-010 | backend-engineer | Done | C-038 |
| T-060 | FEAT-001, FEAT-003, FEAT-004, FEAT-005, FEAT-008, FEAT-009 | frontend-engineer | Done | C-001–C-043 |
| T-061 | FEAT-009 | backend-engineer | Done | — |
| T-062 | FEAT-004, FEAT-005, FEAT-006, FEAT-007 | frontend-engineer | Done | C-011, C-035 (revision 1) |
| T-063 | FEAT-001 | frontend-engineer | Done | C-001–C-005 |
| T-064 | FEAT-007 | backend-engineer | Done | C-035 (revision 1) |
| T-065 | FEAT-001 | backend-engineer | Done | C-002 |
| T-066 | FEAT-001 | frontend-engineer | Done | C-004, C-005 |
| T-052 | FEAT-010 | backend-engineer | Done | C-036–C-038 |
| T-067 | FEAT-009 | backend-engineer | Done | C-029 |

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
| D-013 | Add an `on-error` role token | branding.md's #FFFFFF destructive text fails WCAG AA on the dark error fill; a dark on-error value satisfies NFR-030 in both modes | user |
| D-014 | Bundle Inter and JetBrains Mono (Latin subset) | brand typography is part of the design system; platform fallback drifts across devices | user |
| D-015 | Source a custom 24px outlined icon set | branding.md requires a custom set drawn to the mark's geometry; Material stand-ins are temporary | user |
| D-016 | Ship one `assets/sabi.riv` and load artboards by name | Six byte-identical per-slot copies waste bundle size against NFR-001 cold-start and memory | user |
| D-017 | Intent confidence cutoff is 0.70 | Below this, ask one clarifying question and never initiate payment; recorded for model-quality.md | user |
| D-018 | HTTP wire fields are camelCase; the model-quality structured schema is model-internal | Removes the casing split between C-010 `ServiceSummary` and C-011 `Service`; the AI adapter maps the model's snake_case schema to camelCase at the API boundary. C-009 and C-010 revised to revision 2. | lead |
| D-019 | MQ-002 and MQ-004 use the same 0.70 confidence cutoff; after the single MQ-001 clarification, an unresolved request offers catalogue search and human support | One consistent serving cutoff across the model capabilities; the unresolved branch matches features.md FEAT-003 and user-flow Flow 2 | user |
| D-020 | Revise schema.md for the Phase 1 backend needs: AuthCredential credential id and recovery lookup digest, a capability review record, and Provider.name uniqueness | Replaces the internal credential envelope, the O(n) Argon2id recovery scan, and audit-only quarantine | user |
| D-021 | Add an API gateway agent module forwarding C-009 and C-012 to the AI service | architecture.md makes the gateway the client's sole entry point, but the agent routes exist only on the AI service; without the module the Phase 1 outcome "a request resolves to a real agency" is unreachable | lead |
| D-022 | Model quality is verified by QA-authored fixture-based harness runs in Phase 1; live golden-set accuracy with human judges is deferred | The MQ-001/MQ-002/MQ-003 datasets and judges require real labelled data and provider access, neither available at the gate; the pinned model, decoding, 0.70 cutoff, and fallbacks are verified | lead |
| D-023 | Add a documented `make test-integration` target and run `tests/**` in CI | QA's integration and acceptance layer was not executed by `make test` or CI, so the gate was not enforced | lead |
| D-024 | The Operations Console is a dedicated staff web console in Phase 1; provider self-service is Phase 2; staff log in with email + password + TOTP under MFA; the console is a stateless deployable in the primary region behind the API gateway | operations.md names a staff/provider surface that is explicitly not a mobile screen; branding.md is mobile-only. Splitting staff console now from provider portal later avoids a provider-auth contract before provider volume exists. Supersedes D-011. | user |
| D-025 | branding.md gains a Desktop and Staff Console Token Set; the console inherits the brand grammar and adds only desktop density, breakpoint, table, form, interaction, and shell tokens | Gives the Phase 1 console a sanctioned styling authority instead of ad-hoc reuse of the mobile tokens, while keeping it recognisably Sabi and bounded to what the Phase 1 views need | user |
| D-026 | The default high-volume model path moves from `gemini-3-flash-preview` to `gemini-3.1-flash-lite`; list prices refreshed to the published rates | The flash-lite tier is stable rather than preview, cheaper ($0.25/$1.50 vs $0.50/$3.00 per million), and removes preview deprecation exposure from the default build | user |
| D-027 | Payment features proceed against mock and sandbox rails with contracts C-017–C-038 frozen as written, swapped for the licensed partner later | Unblocks Phase 2 while D1–D3 remain unsecured; the isolated payment module and its port keep the rail swappable without touching callers | user |
| D-028 | The client passkey ceremony uses the `passkeys` plugin (Corbado) | Verified publisher, Android + iOS, and explicit custom relying-party-server support matching the self-hosted py_webauthn backend; a hand-rolled platform channel is avoided | user |
| D-029 | C-035 gains a failed-payment branch (`409: status: failed, reason`) and C-033's `range` is documented as `{minimum, maximum}` minor units | A failed bill has no token and must not poll `awaiting_token` forever; the 409 mirrors C-031's handling of a payment that did not succeed. Both sides re-dispatched | lead |

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
| Client on Android emulator | `cd apps/mobile && flutter run -d emulator-5554` |
| Client tests | `cd apps/mobile && flutter test` |
| AI tests | `cd services/ai && pytest` |
| Integration tests | `make test-integration` |
| Model-quality report | `make test-model-quality` |
| AI serve | `make ai-serve` |
| AI dev | `make ai-dev` |
| Lint | `ruff check .` and `flutter analyze` |
