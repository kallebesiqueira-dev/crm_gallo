# Dashboard navigation reorganization + missing features

**Goal:** reorganize the in-app sidebar into 6 professional groups, then build the
10 missing CRM modules.

**Decided approach (2026-06-08):** build the features *for real* — DB model + RLS
migration + API + UI + 7-language i18n — **incrementally, one well-made and tested
module at a time.** RLS mistakes = cross-tenant data leaks, so no rushing all ten at
once.

**Status (2026-06-09):** Nav reorg ✅ **shipped** (6-group purple sidebar + premium dashboard live). WhatsApp omnichannel ✅ **live**. Prodotti/Servizi **backend** ✅ built + RLS-verified (frontend = next slice). See the re-scoped plan below.

---

## The 6-group structure (labels shown in Italian; must be localized to all 7 locales)

| Group | Items — ✅ page already exists · ❌ to build |
|---|---|
| **Vendite** | Lead ✅`leads` · **Opportunità ❌** · Pipeline ✅`pipeline` · Preventivi ✅`quotes` · Contratti ✅`contracts` · **Prodotti/Servizi ❌** |
| **Clienti** | Clienti ✅`customers` · **Contatti ❌** · Aziende ✅`companies` · Duplicati ✅`duplicates` |
| **Lavoro** | Attività ✅`tasks` · Calendario ✅`calendar` · **Documenti ❌** · **Comunicazioni ❌** · **Notifiche ❌** (only the header bell today) |
| **Crescita** | Moduli ✅`forms` · Importazioni ✅`imports` · **Esportazioni ❌** · Automazioni ✅`automations` · Assistente IA ✅`assistant` |
| **Gestione** | Dashboard ✅`dashboard` · Report ✅`reports` · Performance ✅`performance` · Fatturazione ✅`billing` · Audit log ✅`audit` |
| **Sistema** | **Utenti ❌** · **Team/Ruoli ❌** · **Integrazioni ❌** · Impostazioni ✅`settings` · Cestino ✅`trash` |

**20 of 30 items already exist** (only need grouping). **10 to build.**

> **Re-scoped (2026-06-09):** auditing `main.py`, most "to build" items ALREADY HAVE BACKENDS — `deals`=Opportunità, `exports`=Esportazioni, `notifications`=Notifiche, `teams`=Team, `attachments`/`document_templates`=Documenti, `whatsapp`/inbox=Comunicazioni (shipped). They need **frontend pages only**, not new entities. The **only** item that needed a new table was **Prodotti/Servizi** (✅ backend built + RLS-verified).

## Build order (recommended, cleanest/highest-value first)
1. **Prodotti/Servizi** — ✅ **backend done** (`products` table + RLS migration `d7e8f9a0b1c2`, `Product` model, `/api/products` CRUD, ruff + migration verified). **Next: frontend** (list/new/edit + `products` under Vendite + i18n).
2. **Contatti** — person contacts, link to companies.
3. **Opportunità / Deals** — ⚠️ may overlap with `leads` + `pipeline` (leads already have stages). Clarify product design before building. Label `nav.deals` already exists.
4. **Documenti** — ties to the existing Cloudflare R2 file storage; label `nav.documents` already exists.
5. **Integrazioni** — settings-like; list/connect integrations.
6. **Esportazioni** — CSV export of existing entities.
7. **Comunicazioni** — email/message log per lead/customer.
8. **Notifiche** — page for the existing notifications (header bell + `/counts` API already exist).
9. **Utenti** — user management (partly under settings today).
10. **Team/Ruoli** — label `nav.team` already exists.

## Files involved
- **Nav source of truth:** `frontend/src/components/sidebar.tsx` → exported `NAV` array (flat today, 20 items). Reorganize into groups here + render group headers.
- **Mobile nav:** `frontend/src/components/mobile-nav.tsx` — imports `NAV` from sidebar (shared). Update to render the groups too.
- **i18n labels:** `frontend/messages/<locale>.json` → `nav` namespace. Add the 6 group labels (e.g. `nav.group.vendite` …). NOTE: `nav.deals`, `nav.documents`, `nav.team` **already exist** (at least in en.json) — reuse, and fill the other 6 locales.
- **Each new feature:** backend `app/models.py` + an Alembic migration **with the org-scoped RLS block**, `app/api/<entity>.py` router + entries in `app/schemas.py`, register the router in `app/main.py`; frontend `[locale]/(app)/<entity>/` pages (list + `new` + `[id]` + `[id]/edit` — mirror the existing `customers`/`companies` pattern); i18n in all 7 locales.

## RLS safety (critical — do not skip)
Every new entity table MUST carry the same org-scoped Row-Level Security as the
existing tables: `FORCE ROW LEVEL SECURITY` + a policy keyed on the current-org GUC.
The app connects through the restricted `crm_app` role (NOSUPERUSER NOBYPASSRLS).
**Copy the RLS block from an existing entity's migration exactly, then verify tenant
isolation before shipping** — a missing/wrong policy leaks data across tenants.

## Next session — start here
1. **Nav reorg ✅ done** (6-group purple sidebar live; group labels still hardcoded Italian — move to the `nav` i18n namespace when convenient).
2. **Prodotti/Servizi backend ✅ done.** Build its **frontend**: `[locale]/(app)/products/` list + `new` + `[id]/edit` (mirror `companies/`); add `{ href: "products", label: "products", icon: Package }` to the **Vendite** group in `sidebar.tsx`; add a `Product` type + CRUD to `lib/api.ts`; add a `products` namespace + `nav.products` to all 7 `messages/*.json`. Then deploy backend+frontend together.
3. After Prodotti, the rest are **frontend-only over existing backends** — Notifiche (`/notifications`), Esportazioni (`/exports`), Opportunità (`/deals`), Team (`/teams`), Documenti (`/attachments`). One list page each, mirror the pattern.
