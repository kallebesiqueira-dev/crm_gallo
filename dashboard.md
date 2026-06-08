# Dashboard navigation reorganization + missing features

**Goal:** reorganize the in-app sidebar into 6 professional groups, then build the
10 missing CRM modules.

**Decided approach (2026-06-08):** build the features *for real* — DB model + RLS
migration + API + UI + 7-language i18n — **incrementally, one well-made and tested
module at a time.** RLS mistakes = cross-tenant data leaks, so no rushing all ten at
once.

**Status:** _planned, not yet coded._ Exploration done; nav reorg + features pending.

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

## Build order (recommended, cleanest/highest-value first)
1. **Prodotti/Servizi** — clean self-contained entity (name, type, price, SKU, active); used by quotes/contracts.
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
1. Nav reorg: group the 20 existing items into the 6 groups in `sidebar.tsx` + `mobile-nav.tsx`; add the 6 group labels to the `nav` namespace in all 7 `messages/*.json`.
2. Then build **Prodotti/Servizi** end-to-end as the first module (template for the rest).
