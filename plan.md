# Gallo CRM — Plano de Produto

## Promessa

> **Gallo CRM**
> The CRM that makes sure no opportunity is forgotten.
> Setup in 30 minutes. Learn in 15 minutes.
> Follow-up driven. AI-assisted. GDPR-ready.

---

## Por que a Europa

Existe uma fadiga enorme com Salesforce, Dynamics, HubSpot Enterprise, SAP e Oracle.  
PMEs europeias não querem mais plataformas gigantes. Querem: **"Abrir, usar e vender."**

| Diferencial | Por que funciona na Europa |
|-------------|---------------------------|
| Simplicidade radical | Alemanha, Suíça, Holanda e países nórdicos valorizam processos e previsibilidade — um CRM que não precisa de consultant é um argumento forte |
| Follow-up obrigatório | "Você esqueceu este cliente" gera valor imediato em qualquer mercado organizado |
| Zero-consulting setup | Maior reclamação das PMEs europeias: "Compramos e passamos semanas configurando" |
| Dashboard orientado à ação | Ao invés de gráficos, mostrar: "Ligue para João · Negociação X parada há 12 dias" |
| GDPR nativo | Compliance como diferencial competitivo, não como compliance reativo |

---

## Posicionamento de comunicação

**Communication-first CRM** — não WhatsApp-first.

O WhatsApp é obrigatório em Brasil, Espanha, Portugal e Itália. Mas na Alemanha, Holanda, Reino Unido e países nórdicos o email domina. A mensagem deve ser:

> Venda pelo canal que seu cliente prefere: email, WhatsApp, telefone ou reunião.

---

## Princípios do produto

- **Simplicidade radical:** qualquer vendedor entende em 15 minutos
- **Follow-up obrigatório:** nenhum negócio ativo sem próxima ação definida
- **Communication-first:** email + WhatsApp + calendário + telefone — sem canal único obrigatório
- **IA operacional:** IA resume conversa, detecta intenção, sugere próximo passo, cria follow-up — não é só um chat
- **Setup rápido:** < 30 minutos para começar, templates por setor
- **Ação acima de dashboard:** responde "O que devo fazer agora para vender mais?"
- **GDPR nativo:** consentimento, retenção, exportação, exclusão e auditoria desde o dia 1

---

## Estado atual (2026-06-11)

O núcleo técnico está **completo e em produção**. As lacunas abaixo são de produto, não de infraestrutura.

### ✅ Já construído

| Módulo | Detalhes |
|--------|----------|
| Multi-tenancy | Organizations, RLS Postgres, memberships, convites, billing migration |
| Auth | JWT + cookies httpOnly + CSRF, refresh tokens, MFA TOTP, sessões, password reset |
| Leads | CRUD, paginação cursor, FTS + pg_trgm fallback, pipeline kanban, AI scoring |
| Clientes (Contacts) | CRUD, FTS + pg_trgm fallback, AI summary com deals/tasks do contexto |
| Empresas | CRUD completo |
| Deals/Oportunidades | Kanban drag-drop, stages, valor, responsável, versão otimística |
| Tasks/Follow-ups | Modelo completo, due_date, prioridade, status, atribuição |
| Timeline de Atividades | Append-only ledger por entidade (lead, customer, deal), tipo, metadata |
| Notas | Markdown por entidade, autoria, edição, soft-delete |
| Notificações | In-app bell, por usuário, polling, mark-as-read |
| WhatsApp Omnichannel | Cloud API, webhook, inbox UI, conversations, messages, read-receipts |
| IA | Scoring de leads, summary de clientes, chat assistant com streaming e histórico |
| Quotes & Contratos | Pipeline completo: quote → contrato → assinatura eletrônica → PDF |
| Importação/Exportação | CSV/XLSX, deduplicação, validação por linha, streaming export |
| Public API | API keys, `/api/v1/`, rate limit por chave, scopes read/write |
| Billing | Stripe, planos Free/Standard/Premium, seat enforcement, trial 14 dias |
| Observabilidade | Prometheus, Grafana, Sentry, Arq DLQ, alertas Prometheus |
| CI/CD | GitHub Actions backend+frontend+docker+security, pytest, ruff, tsc, Playwright |
| Webhooks | Outgoing HMAC-signed, retry, auto-pause, outbox pattern |
| Automações | Engine no-code, trigger→condition→action sobre event bus |
| Performance/KPI | Metas de vendas, aggregates sobre deals/leads, goals por vendedor |
| Multilíngue | 7 idiomas: EN, PT, DE, FR, IT, RM, ES — cobertura Europa completa |
| Auditoria | Audit log com UI, RLS estrito, trilha imutável por organização |

---

## Lacunas reais do produto (o que falta construir)

### 1 — Campos de próxima ação em Deals *(P1 — bloqueador do pitch principal)*

A promessa central é "nenhum negócio sem próxima ação". Hoje os Deals **não têm esses campos**:

```
deals.next_action_type  — enum: ligar, whatsapp, email, proposta, reunião, follow-up, contrato, cobrar, outro
deals.next_action_at    — timestamp: quando executar
```

**O que construir:**
- Migração: dois novos campos em `deals`
- Schema Pydantic: `DealUpdate` / `DealOut` expondo os campos
- Endpoint `PATCH /api/deals/{id}/next-action` (atalho explícito)
- Estados de follow-up: `sem_acao`, `hoje`, `atrasado`, `futuro`, `concluido`
- Card no kanban mostrando ícone de status + prazo

---

### 2 — Tela Hoje / Central de Ação *(P1 — coração do produto)*

O vendedor deve abrir o sistema e saber em < 10 segundos o que fazer. É a tela que diferencia o Gallo CRM de qualquer dashboard genérico.

**O que construir:**

Rota `/hoje` com as seções:

| Seção | Dados |
|-------|-------|
| Follow-ups atrasados | Deals com `next_action_at < now()` |
| Follow-ups de hoje | Deals com `next_action_at` entre 00h e 23h59 |
| Sem próxima ação | Deals ativos sem `next_action_at` |
| Parados há muito tempo | Deals sem atividade há > 7 dias |
| Tasks de hoje | Tasks com `due_date = hoje` |
| Tasks atrasadas | Tasks com `due_date < hoje` e status != done |

Endpoint: `GET /api/dashboard/today` (complementa o `/api/dashboard/stats` existente).

---

### 3 — Onboarding em < 30 minutos *(P2 — ativação)*

Um org novo cai num CRM vazio — péssima primeira impressão.

**O que construir:**
- [x] Checklist de onboarding na primeira sessão (5 passos) — **backend DONE 2026-06-11 (`26ee0f6`)**: `GET /api/onboarding/checklist` computado de dados reais (sem tabela de estado): pipeline_ready / first_lead / next_action_set / teammate_invited / proposal_sent. **frontend DONE 2026-06-11**: `components/onboarding-checklist.tsx` (widget no dashboard, desaparece quando tudo feito ou dismissed via localStorage, barra de progresso), 7 locais.
- [x] Templates de pipeline prontos por setor — **backend DONE (mesmo commit)**: `GET /api/onboarding/templates` (7 setores: agency, saas, consulting, construction, real-estate, whatsapp-sales, b2b-simple) + `POST /api/onboarding/templates/{slug}/apply` (cria Pipeline+stages, set_default opcional, re-apply 409). Nomes de stage em EN canônico — wizard localiza a exibição, stages editáveis no editor existente. 6 testes. **frontend DONE 2026-06-11**: `app/[locale]/(app)/onboarding/page.tsx` — grid de cards com badge de stages, botão apply, toast de sucesso/409.
- [x] Empty-states com CTAs em todas as listas vazias — **DONE 2026-06-11**: `<EmptyState>` compartilhado (ícone+título+CTA) nas 7 listas principais — leads/customers/tasks (lane paralela) + contracts/quotes/products/companies (`1bf3def`). Tasks sem CTA (criação é inline); trash/notifications/duplicates/imports mantêm texto simples de propósito (vazio ali é normal).

---

### 4 — Conversão Lead → Contato/Empresa/Deal *(P2 — fluxo comercial)*

Hoje leads e clientes são entidades separadas sem fluxo de conversão formal.

**O que construir:**
- [x] `POST /api/leads/{id}/convert` → cria Customer + Company + Deal atomicamente com o contexto do lead — **DONE 2026-06-11 (`323b501`)**: `app/api/lead_convert.py`, reusa customer por email / company por nome, deal espelha POST /api/deals (audit+activity+evento `deal_created` p/ automações), guard de dupla conversão via atividade (409). 6 testes.
- [ ] UI: botão "Converter" no detalhe do lead *(frontend — pendente)*
- [x] Atividade `lead_converted` na timeline de ambas as entidades — DONE (mesmo commit)

---

### 5 — GDPR nativo *(P2 — diferencial competitivo na Europa)*

Compliance como vantagem de venda, não como tarefa de último minuto. Base já existe (audit log, soft-delete, RLS). O que falta:

**O que construir:**
- [~] Campo `contact_consent_at` + `consent_source` em leads/clientes — *em voo na lane paralela (migration `b5c6d7e8f9a0` aplicada, WIP uncommitted)*
- [x] `POST /api/leads/{id}/forget` → anonimiza PII mantendo ID na auditoria — **DONE 2026-06-11 (`f17b047`)**: `app/api/gdpr.py`, leads E customers, admin-only; anonimiza + soft-delete, hard-delete das notas, timeline mantém esqueleto sem conteúdo. Residuais documentados (avatar S3, mensagens WhatsApp, metadata histórica de audit).
- [x] Exportação de dados por contato (`GET /api/leads/{id}/export`) — DONE (mesmo commit; também `/api/customers/{id}/export` com deals associados). 6 testes.
- [x] Policy de retenção configurável por org — **DONE 2026-06-12 (`2db4f42`+`f2c93f3`)**: `organizations.retention_months` (null=off, 1..120) via `GET/PATCH /api/gdpr/settings` (admin, auditado); sweep diário no worker (04:23 UTC) anonimiza LEADS inativos além do cutoff pelo mesmo core do /forget (cap 200/org/dia; customers de propósito FORA — relação paga exige humano). 4 testes.
- [x] Página de configurações GDPR no painel — **DONE 2026-06-12 (`a0d74e8`)**: `<GdprCard>` em /settings (admin-gated), edita a janela de retenção (1–120 meses, vazio = off) com copy explicando o sweep; `gdpr.*` nos 7 locales.

---

### 6 — Multi-moeda completa *(P2 — mercado europeu)*

Hoje deals e quotes usam EUR. Para operar em CH/UK obrigatório.

**O que construir:**
- [x] Adicionar `currency` field em deals com padrão configurável por org — `deals.currency` JÁ EXISTIA (ADR-015); **`org.default_currency` DONE 2026-06-12 (`1dabacf`)**: migration `5b6c7d8e9f0a` (backfill EUR), `GET/PATCH /api/orgs/current/settings` (admin, auditado), deal E quote herdam quando o payload omite a moeda (`model_fields_set` — explícito sempre vence, clientes existentes intactos). 4 testes.
- [x] Suporte a CHF, GBP e BRL nas plans do Stripe — **DONE 2026-06-11 (`bdd0e15`)**: price points posicionados por moeda no catálogo, `resolve_stripe_price_id(plan, cycle, currency)` (EUR mantém env names legados), checkout aceita `currency` (400 amigável p/ não suportada; price id ausente = erro claro, nunca fallback p/ EUR). 4 testes, zero chamadas reais à Stripe.
- [ ] Seletor de moeda na criação de deal e quote *(frontend)*
- [ ] Dashboard mostrando valores na moeda de cada deal *(frontend)*

---

### 7 — Produtos no frontend *(P2 — catálogo para propostas)*

Backend do catálogo está **completo** (migration `d7e8f9a0b1c2`, CRUD `/api/products`). Falta:

- [x] Página de lista `/produtos` com criar/editar/arquivar — JÁ EXISTIA (`products/page.tsx` + `/new`; o plano estava conservador)
- [x] Entry no sidebar — JÁ EXISTIA
- [x] Seletor de produto nas line items de quotes — **DONE 2026-06-11 (`041e003`)**: select compacto "do catálogo" por linha (só produtos ativos, name · sku) que pré-preenche descrição + preço unitário; campos seguem editáveis (line item não tem FK de produto — é fill helper); catálogo vazio = form inalterado. Chave `quotes.fromCatalog` nos 7 locales. **§7 FECHADA.**

---

## Fora do escopo imediato (post-pagante)

- Integrações Gmail/Outlook/Google Calendar
- RAG / embeddings pgvector para busca em documentos
- Instagram Messaging / Messenger
- Aplicativo mobile
- Staging environment automático

---

## Pergunta guia para cada funcionalidade nova

> Isso ajuda o vendedor a lembrar, priorizar ou executar a próxima ação comercial?

Se não → provavelmente não entra agora.
