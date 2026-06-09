import { clearToken, readCookie } from "./auth";

export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

export type LeadStage =
  | "new"
  | "contacted"
  | "qualified"
  | "proposal_sent"
  | "negotiation"
  | "won"
  | "lost";

export type DealStage =
  | "new"
  | "qualified"
  | "proposal_sent"
  | "negotiation"
  | "won"
  | "lost";

export type Currency = "EUR" | "CHF" | "USD" | "GBP";
export type TaskStatus = "todo" | "in_progress" | "done";
export type TaskPriority = "low" | "medium" | "high";
export type QuoteStatus = "draft" | "sent" | "accepted" | "declined" | "expired";

export interface Lead {
  id: string;
  first_name: string;
  last_name: string;
  email: string | null;
  phone: string | null;
  company: string | null;
  industry: string | null;
  country: string | null;
  company_size: number | null;
  budget: number | null;
  source: string | null;
  notes: string | null;
  stage: LeadStage;
  ai_score: number | null;
  ai_priority: string | null;
  ai_next_action: string | null;
  ai_conversion_probability: number | null;
  ai_risk_analysis: string | null;
  ai_scored_at: string | null;
  owner_id: string | null;
  company_id: string | null;
  custom_fields: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface Customer {
  id: string;
  first_name: string;
  last_name: string;
  email: string | null;
  phone: string | null;
  company: string | null;
  industry: string | null;
  country: string | null;
  address: string | null;
  website: string | null;
  notes: string | null;
  ai_summary: string | null;
  ai_summary_updated_at: string | null;
  owner_id: string | null;
  company_id: string | null;
  custom_fields: Record<string, unknown>;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface Company {
  id: string;
  name: string;
  industry: string | null;
  website: string | null;
  phone: string | null;
  email: string | null;
  country: string | null;
  address: string | null;
  size: number | null;
  notes: string | null;
  owner_id: string | null;
  custom_fields: Record<string, unknown>;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface CompanyRollup {
  company: Company;
  customers: Customer[];
  leads: Lead[];
  deals: Deal[];
}

export interface Deal {
  id: string;
  title: string;
  value: number;
  currency: Currency;
  stage: DealStage;
  probability: number;
  expected_close_date: string | null;
  notes: string | null;
  customer_id: string | null;
  company_id: string | null;
  owner_id: string | null;
  sort_index: number;
  custom_fields: Record<string, unknown>;
  version: number;
  created_at: string;
  updated_at: string;
}

export type CustomFieldEntity = "lead" | "customer" | "deal" | "company";

export type CustomFieldKind =
  | "text"
  | "textarea"
  | "number"
  | "date"
  | "boolean"
  | "select"
  | "multiselect"
  | "url"
  | "email";

export interface CustomFieldDefinition {
  id: string;
  entity_type: CustomFieldEntity;
  key: string;
  label: string;
  field_type: CustomFieldKind;
  options: string[] | null;
  required: boolean;
  position: number;
  created_at: string;
  updated_at: string;
}

export type TaggableEntity = CustomFieldEntity;

export interface Tag {
  id: string;
  name: string;
  color: string;
  created_at: string;
  updated_at: string;
}

export interface EntityTags {
  entity_id: string;
  tags: Tag[];
}

export interface SavedSegment {
  id: string;
  entity_type: TaggableEntity;
  name: string;
  filters: Record<string, unknown>;
  created_by_id: string | null;
  created_at: string;
  updated_at: string;
}

export type DuplicateEntity = "lead" | "customer" | "company";

export interface DuplicateRecord {
  id: string;
  label: string;
  email: string | null;
  phone: string | null;
  created_at: string;
}

export interface DuplicateGroup {
  match_type: "email" | "phone" | "name";
  key: string;
  records: DuplicateRecord[];
}

export interface DuplicateGroupsOut {
  entity_type: DuplicateEntity;
  groups: DuplicateGroup[];
}

export interface MergeResult {
  survivor_id: string;
  merged_count: number;
  reparented: Record<string, number>;
}

export interface WebForm {
  id: string;
  name: string;
  token: string;
  default_source: string | null;
  redirect_url: string | null;
  active: boolean;
  submission_count: number;
  created_at: string;
  updated_at: string;
}

export interface Task {
  id: string;
  title: string;
  description: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  due_date: string | null;
  assignee_id: string | null;
  customer_id: string | null;
  deal_id: string | null;
  lead_id: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface QuoteLineItem {
  id: string;
  description: string;
  quantity: number;
  unit_price: number;
  line_total: number;
  sort_index: number;
}

/** A line item as sent to the server — no id / line_total (the
 *  server computes totals and assigns ids). */
export interface QuoteLineItemInput {
  description: string;
  quantity: number;
  unit_price: number;
  sort_index?: number;
}

export interface Quote {
  id: string;
  number: string;
  version: number;
  status: QuoteStatus;
  title: string;
  currency: Currency;
  valid_until: string | null;
  notes: string | null;
  deal_id: string | null;
  customer_id: string | null;
  owner_id: string | null;
  subtotal: number;
  tax_rate: number;
  tax_amount: number;
  total: number;
  superseded_by: string | null;
  sent_at: string | null;
  accepted_at: string | null;
  declined_at: string | null;
  line_items: QuoteLineItem[];
  created_at: string;
  updated_at: string;
}

export interface QuoteCreate {
  title: string;
  currency?: Currency;
  tax_rate?: number;
  valid_until?: string | null;
  notes?: string | null;
  deal_id?: string | null;
  customer_id?: string | null;
  owner_id?: string | null;
  line_items?: QuoteLineItemInput[];
}

export interface QuoteUpdate {
  title?: string;
  currency?: Currency;
  tax_rate?: number;
  valid_until?: string | null;
  notes?: string | null;
  line_items?: QuoteLineItemInput[];
}

export type ContractStatus =
  | "draft"
  | "sent"
  | "signed"
  | "active"
  | "terminated"
  | "expired";

export interface Contract {
  id: string;
  number: string;
  version: number;
  status: ContractStatus;
  title: string;
  currency: Currency;
  value: number;
  effective_date: string | null;
  end_date: string | null;
  auto_renew: boolean;
  renewal_term_months: number | null;
  body: string | null;
  notes: string | null;
  quote_id: string | null;
  deal_id: string | null;
  customer_id: string | null;
  owner_id: string | null;
  applied_template_id: string | null;
  superseded_by: string | null;
  sent_at: string | null;
  signed_at: string | null;
  activated_at: string | null;
  terminated_at: string | null;
  created_at: string;
  updated_at: string;
}

export type DocumentType = "contract";

export interface DocumentTemplate {
  id: string;
  doc_type: DocumentType;
  name: string;
  body: string;
  is_default: boolean;
  created_by_user_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentTemplateCreate {
  name: string;
  body?: string;
  doc_type?: DocumentType;
  is_default?: boolean;
}

export interface DocumentTemplateUpdate {
  name?: string;
  body?: string;
  is_default?: boolean;
}

export interface MergeField {
  token: string;
  label: string;
  description: string;
  example: string;
}

export interface ContractCreate {
  title: string;
  currency?: Currency;
  value?: number;
  effective_date?: string | null;
  end_date?: string | null;
  auto_renew?: boolean;
  renewal_term_months?: number | null;
  body?: string | null;
  notes?: string | null;
  quote_id?: string | null;
  deal_id?: string | null;
  customer_id?: string | null;
  owner_id?: string | null;
}

export interface ContractUpdate {
  title?: string;
  currency?: Currency;
  value?: number;
  effective_date?: string | null;
  end_date?: string | null;
  auto_renew?: boolean;
  renewal_term_months?: number | null;
  body?: string | null;
  notes?: string | null;
  quote_id?: string | null;
  deal_id?: string | null;
  customer_id?: string | null;
  owner_id?: string | null;
}

export type SignatureStatus =
  | "drafted"
  | "sent"
  | "viewed"
  | "signed"
  | "countersigned"
  | "declined"
  | "cancelled";

export interface SignatureRequest {
  id: string;
  // Exactly one of quote_id / contract_id is set — the request signs a quote
  // XOR a contract (DB CHECK).
  quote_id: string | null;
  contract_id: string | null;
  provider: string;
  status: SignatureStatus;
  signer_name: string;
  signer_email: string;
  message: string | null;
  external_id: string | null;
  document_attachment_id: string | null;
  signed_document_key: string | null;
  owner_id: string | null;
  sent_at: string | null;
  viewed_at: string | null;
  signed_at: string | null;
  declined_at: string | null;
  decline_reason: string | null;
  created_at: string;
  updated_at: string;
  // Where the signer goes to sign. Set by the server on /send (manual
  // provider builds it from the token); null on plain reads.
  signing_url: string | null;
}

/** The minimal, unauthenticated view the signer sees on /sign/[token]. */
export interface SignatureSignContext {
  status: SignatureStatus;
  signer_name: string;
  document_type: "quote" | "contract";
  document_number: string;
  document_title: string;
  document_total: number;
  document_currency: Currency;
  organization_name: string;
}

export type ApiKeyScope = "read" | "write";

export interface ApiKey {
  id: string;
  organization_id: string;
  name: string;
  // Non-secret label like `crmk_a1b2c3d4…wxyz` — safe to show anywhere.
  display_prefix: string;
  scopes: ApiKeyScope[];
  last_used_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

/** Returned ONCE by createApiKey — `token` is the plaintext bearer
 *  credential and is never retrievable again after this response. */
export interface ApiKeyCreated extends ApiKey {
  token: string;
}

export interface ApiKeyCreate {
  name: string;
  scopes?: ApiKeyScope[];
  expires_at?: string | null;
}

export interface DashboardStats {
  total_leads: number;
  leads_by_stage: Record<string, number>;
  won_count: number;
  lost_count: number;
  conversion_rate: number;
  avg_ai_score: number | null;
  total_customers: number;
  total_deals: number;
  pipeline_value_eur: number;
  open_tasks: number;
}

export type GoalPeriod = "month" | "quarter" | "year";
export type GoalMetric = "revenue" | "deal_count";

export interface LeaderboardRow {
  owner_id: string | null;
  owner_name: string;
  won_value_eur: number;
  won_count: number;
}

export interface FunnelStage {
  stage: string;
  count: number;
}

export interface PerformanceSummary {
  period: GoalPeriod;
  period_start: string;
  period_end: string;
  won_value_eur: number;
  won_count: number;
  lost_count: number;
  win_rate: number;
  lead_funnel: FunnelStage[];
  lead_conversion_rate: number;
  leads_lost: number;
  avg_days_to_close: number | null;
  median_days_to_close: number | null;
  leaderboard: LeaderboardRow[];
}

export interface SalesGoal {
  id: string;
  owner_id: string | null;
  team_id: string | null;
  period: GoalPeriod;
  period_start: string;
  metric: GoalMetric;
  target: number;
  attainment: number;
  attainment_pct: number;
  created_at: string;
  updated_at: string;
}

export type AutomationTrigger =
  | "lead_created"
  | "deal_created"
  | "deal_won"
  | "deal_lost"
  | "deal_stage_changed"
  | "lead_stale";
export type AutomationAction = "create_task" | "send_notification" | "change_stage";

export interface AutomationRule {
  id: string;
  name: string;
  description: string | null;
  enabled: boolean;
  trigger: AutomationTrigger;
  action: AutomationAction;
  action_config: Record<string, unknown>;
  run_count: number;
  last_run_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AutomationRun {
  id: string;
  rule_id: string;
  status: string;
  entity_type: string | null;
  entity_id: string | null;
  detail: string | null;
  created_at: string;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: string;
  locale: string;
  is_active: boolean;
  // Whether the user confirmed their email. False for fresh self-signups
  // until they click the verification link; true otherwise.
  email_verified: boolean;
  // Which org the user is currently working in. Frontend reads this
  // to highlight the active item in the org switcher and to decide
  // which workspace's data to render.
  last_active_org_id: string | null;
  created_at: string;
}

export type Role = "admin" | "manager" | "sales_agent" | "support_agent" | "client";

export interface Organization {
  id: string;
  name: string;
  slug: string;
  plan: PlanId;
  created_at: string;
}

export interface Membership {
  organization: Organization;
  role: Role;
  created_at: string;
}

export interface InvitePreview {
  organization_id: string;
  organization_name: string;
  email: string;
  role: Role;
  expires_at: string;
}

export interface Invite {
  id: string;
  organization_id: string;
  email: string;
  role: Role;
  expires_at: string;
  accepted_at: string | null;
  created_at: string;
  invite_url?: string | null;
}

export interface AuthResponse {
  user: User;
  token: { access_token: string; token_type: string };
}

/** Returned by /register. When `verification_required` is true the user
 *  must confirm their email before logging in — `token` is null and the
 *  frontend shows a "check your email" screen. When false (the first
 *  user / install founder, auto-verified) a session was started and
 *  `token` carries the access token for an immediate login. */
export interface RegisterResponse {
  verification_required: boolean;
  email: string;
  user: User;
  token: { access_token: string; token_type: string } | null;
}

/** Returned by /login when the user has MFA enabled — instead of the
 *  full AuthResponse. The client posts `mfa_token` + a TOTP/backup
 *  code to /mfa/verify to complete the login. */
export interface MfaChallenge {
  mfa_required: true;
  mfa_token: string;
}

/** Returned by /login when the user holds a privileged role, hasn't
 *  enrolled in MFA, and the server's `mfa_required_for_privileged`
 *  policy is on. A full session IS started (cookies set) — but every
 *  tenant-data endpoint stays 403 `mfa_enrollment_required` until the
 *  user finishes enrolling, so the client should route straight to the
 *  forced-enrollment page. Carries `user`/`token` like AuthResponse. */
export interface MfaSetupRequired {
  mfa_setup_required: true;
  user: User;
  token: { access_token: string; token_type: string };
}

export type LoginResponse = AuthResponse | MfaChallenge | MfaSetupRequired;

export function isMfaChallenge(r: LoginResponse): r is MfaChallenge {
  return (r as MfaChallenge).mfa_required === true;
}

export function isMfaSetupRequired(r: LoginResponse): r is MfaSetupRequired {
  return (r as MfaSetupRequired).mfa_setup_required === true;
}

export interface MfaStatus {
  enabled: boolean;
  enrolled_at: string | null;
  backup_codes_remaining: number;
}

export interface MfaSetup {
  secret: string;
  provisioning_uri: string;
}

export interface MfaEnableResponse {
  backup_codes: string[];
}

export interface Notification {
  id: string;
  type: string;
  title: string;
  body: string | null;
  link_url: string | null;
  metadata_json: string | null;
  actor_user_id: string | null;
  actor_name: string | null;
  read_at: string | null;
  created_at: string;
}

export interface PipelineStage {
  id: string;
  name: string;
  slug: string;
  position: number;
  probability: number;
  is_won: boolean;
  is_lost: boolean;
}

export interface Pipeline {
  id: string;
  kind: "lead" | "deal";
  name: string;
  slug: string;
  is_default: boolean;
  created_at: string;
  updated_at: string;
  stages: PipelineStage[];
}

/** Body for PATCH /api/pipelines/{id} stage reconcile. Pass `id`
 *  null for new stages; omit a stage's id from the array to soft-
 *  delete the existing one. */
export interface PipelineStageDraft {
  id?: string | null;
  name: string;
  slug?: string | null;
  position: number;
  probability: number;
  is_won: boolean;
  is_lost: boolean;
}

export interface TeamMember {
  user_id: string;
  full_name: string;
  email: string;
  role: Role;
}

export interface Team {
  id: string;
  name: string;
  slug: string;
  created_at: string;
  updated_at: string;
  member_count: number;
  members: TeamMember[];
}

export interface FileAttachment {
  id: string;
  entity_type: "lead" | "customer" | "deal" | "quote" | "contract";
  entity_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  uploader_user_id: string | null;
  uploader_name: string | null;
  uploader_email: string | null;
  created_at: string;
}

export type ImportEntityType = "lead" | "customer";
export type ImportMode = "create" | "upsert";
export type ImportStatus = "pending" | "processing" | "completed" | "failed";

export interface ImportRowError {
  row: number;
  field: string | null;
  message: string;
}

export interface ImportJob {
  id: string;
  entity_type: ImportEntityType;
  mode: ImportMode;
  status: ImportStatus;
  filename: string;
  total_rows: number;
  created_count: number;
  updated_count: number;
  skipped_count: number;
  error_count: number;
  error_report: ImportRowError[] | null;
  error_message: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface ImportTemplate {
  entity_type: ImportEntityType;
  headers: string[];
}

export interface Note {
  id: string;
  entity_type: "lead" | "customer" | "deal";
  entity_id: string;
  body: string;
  author_user_id: string | null;
  author_name: string | null;
  author_email: string | null;
  created_at: string;
  updated_at: string;
}

export interface ActivityEntry {
  id: string;
  entity_type: "lead" | "customer" | "deal";
  entity_id: string;
  type: string; // matches ActivityType slug — frontend maps to i18n label
  content: string | null;
  metadata_json: string | null;
  actor_user_id: string | null;
  actor_name: string | null;
  actor_email: string | null;
  created_at: string;
}

export interface AuditEntry {
  id: string;
  organization_id: string | null;
  actor_id: string | null;
  actor_email: string | null;
  actor_name: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  metadata_json: string | null;
  created_at: string;
}

export interface AuditFilters {
  actor_id?: string;
  action?: string;
  entity_type?: string;
  since?: string;
  until?: string;
  limit?: number;
  offset?: number;
}

export interface SessionInfo {
  id: string;
  created_at: string | null;
  last_seen_at: string | null;
  user_agent: string;
  ip_address: string;
  current: boolean;
}

export interface TrashItem {
  id: string;
  entity_type: "lead" | "customer" | "deal" | "task";
  title: string;
  deleted_at: string;
}

export type PlanId = "free" | "standard" | "business" | "premium";
export type BillingCycle = "monthly" | "yearly";

export interface PlanOut {
  id: PlanId;
  name: string;
  tagline: string;
  monthly_eur: number;
  yearly_eur_per_user: number;
  yearly_total_eur: number;
  seat_limit: number | null;
  features: string[];
  highlighted: boolean;
  requires_payment: boolean;
  trial_days: number;
}

export interface BillingMe {
  plan: PlanId;
  billing_cycle: BillingCycle;
  seat_limit: number | null;
  seats_used: number;
  seats_remaining: number | null;
  plan_started_at: string | null;
  plan_renewed_at: string | null;
  plan_canceled_at: string | null;
  trial_ends_at: string | null;
  stripe_configured: boolean;
}

// ── WhatsApp inbox (omnichannel, phase 1) ────────────────────────────
export type WhatsAppAccountStatus = "active" | "disabled";
export type ConversationStatus = "open" | "closed";
export type MessageDirection = "inbound" | "outbound";
export type MessageStatus = "received" | "pending" | "sent" | "delivered" | "read" | "failed";
export type MessageType =
  | "text"
  | "image"
  | "document"
  | "audio"
  | "video"
  | "sticker"
  | "location"
  | "contacts"
  | "unsupported";

export interface WhatsAppAccount {
  id: string;
  phone_number_id: string;
  waba_id: string | null;
  display_phone_number: string | null;
  verified_name: string | null;
  status: WhatsAppAccountStatus;
  created_at: string;
  updated_at: string;
}

export interface Conversation {
  id: string;
  account_id: string;
  channel: "whatsapp" | "instagram" | "messenger";
  contact_wa_id: string;
  contact_name: string | null;
  lead_id: string | null;
  customer_id: string | null;
  status: ConversationStatus;
  last_message_at: string | null;
  last_message_preview: string | null;
  unread_count: number;
  created_at: string;
  updated_at: string;
}

export interface ConversationMessage {
  id: string;
  conversation_id: string;
  wa_message_id: string | null;
  direction: MessageDirection;
  type: MessageType;
  body: string | null;
  media_id: string | null;
  media_url: string | null;
  status: MessageStatus;
  error: string | null;
  sender_user_id: string | null;
  timestamp: string;
  created_at: string;
}

export interface WhatsAppAccountConnect {
  phone_number_id: string;
  access_token: string;
  waba_id?: string | null;
  display_phone_number?: string | null;
  verified_name?: string | null;
}

// Hook for the app shell to redirect on 401 without circular imports.
let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: (() => void) | null) {
  onUnauthorized = fn;
}

// Hook for the app shell to redirect a privileged-but-unenrolled user
// into forced MFA setup. Fired when any data endpoint answers
// 403 `mfa_enrollment_required` (the server's choke-point gate).
let onMfaEnrollmentRequired: (() => void) | null = null;
export function setMfaEnrollmentHandler(fn: (() => void) | null) {
  onMfaEnrollmentRequired = fn;
}

const MUTATING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const REFRESH_PATH = "/api/auth/refresh";

// Singleton in-flight refresh so that N concurrent 401s (e.g. multiple
// queries firing on a stale page) trigger ONE /refresh call. Cleared
// after settle so the next 401-after-recovery starts a fresh attempt.
let refreshInFlight: Promise<boolean> | null = null;

async function attemptRefresh(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    try {
      const csrf = readCookie("csrf_token");
      const res = await fetch(`${API_URL}${REFRESH_PATH}`, {
        method: "POST",
        credentials: "include",
        headers: csrf ? { "X-CSRF-Token": csrf } : {},
      });
      return res.ok;
    } catch {
      return false;
    }
  })();
  try {
    return await refreshInFlight;
  } finally {
    // Yield to allow concurrent awaiters to read the resolved value
    // before we drop the reference, so the next genuinely-new 401
    // starts a fresh attempt.
    setTimeout(() => {
      refreshInFlight = null;
    }, 0);
  }
}

async function request<T>(
  path: string,
  init: RequestInit & { token?: string | null } = {},
  _retrying = false,
): Promise<T> {
  // `token` is preserved in the type for source compatibility with
  // every consumer that still passes `getToken()` — the value is
  // ignored now that auth lives in an httpOnly cookie attached
  // automatically via `credentials: 'include'`. The destructure
  // discards it so it can't accidentally leak into the request.
  const { token: _unused, headers, method, ...rest } = init;
  void _unused;

  // CSRF: double-submit. On mutating methods, mirror the JS-readable
  // `csrf_token` cookie into the X-CSRF-Token header. The backend
  // verifies they match (in constant time). Safe methods are exempt.
  const csrfHeader: Record<string, string> = {};
  if (method && MUTATING_METHODS.has(method.toUpperCase())) {
    const csrf = readCookie("csrf_token");
    if (csrf) csrfHeader["X-CSRF-Token"] = csrf;
  }

  const res = await fetch(`${API_URL}${path}`, {
    ...rest,
    method,
    headers: {
      "Content-Type": "application/json",
      ...csrfHeader,
      ...(headers ?? {}),
    },
    // Send cookies on every request — the auth credential lives in
    // an httpOnly cookie set by the backend on login. Without
    // `include`, browsers strip cookies on cross-origin requests
    // (frontend on :3030 → backend on :8001 IS cross-origin in dev).
    credentials: "include",
    cache: "no-store",
  });
  if (res.status === 401) {
    // Try to recover by minting a new access token via /refresh —
    // unless we ARE the refresh call (would loop) or we already
    // retried once (avoid second-loop on a stubbornly-401 endpoint).
    if (!_retrying && !path.endsWith(REFRESH_PATH)) {
      const refreshed = await attemptRefresh();
      if (refreshed) return request(path, init, true);
    }
    clearToken();
    onUnauthorized?.();
    throw new ApiError(401, "Session expired");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body?.detail || JSON.stringify(body);
    } catch {
      try {
        detail = await res.text();
      } catch {
        /* ignore */
      }
    }
    // Privileged user who hasn't enrolled in MFA (server policy on):
    // every data endpoint is gated until they finish. Bounce them into
    // forced enrollment instead of surfacing a wall of raw 403s.
    if (res.status === 403 && detail === "mfa_enrollment_required") {
      onMfaEnrollmentRequired?.();
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// Keyset-paginated list envelope (TD-11). `next_cursor` is an opaque
// token; pass it back verbatim to fetch the next page.
export interface Page<T> {
  items: T[];
  next_cursor: string | null;
  has_more: boolean;
}

export const api = {
  async login(email: string, password: string): Promise<LoginResponse> {
    const body = new URLSearchParams({ username: email, password });
    const res = await fetch(`${API_URL}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: body.toString(),
      // Login is the path that SETS the auth + csrf cookies. Without
      // `credentials: 'include'` the browser would silently drop the
      // Set-Cookie headers on this cross-origin response.
      credentials: "include",
    });
    if (res.status === 429) throw new ApiError(429, "Too many attempts. Try again shortly.");
    if (!res.ok) {
      let detail = "Login failed";
      try {
        const body = await res.json();
        detail = body?.detail || detail;
      } catch {
        /* ignore */
      }
      throw new ApiError(res.status, detail);
    }
    return res.json();
  },
  register: (payload: {
    email: string;
    password: string;
    full_name: string;
    locale: string;
    turnstile_token?: string;
  }) =>
    request<RegisterResponse>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  me: (token: string) => request<User>("/api/auth/me", { token }),
  updateMe: (
    token: string,
    payload: { full_name?: string; email?: string; locale?: string },
  ) => request<User>("/api/auth/me", { method: "PATCH", token, body: JSON.stringify(payload) }),
  changePassword: (token: string, current_password: string, new_password: string) =>
    request<void>("/api/auth/me/password", {
      method: "POST",
      token,
      body: JSON.stringify({ current_password, new_password }),
    }),
  requestPasswordReset: (email: string) =>
    request<void>("/api/auth/password-reset/request", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),
  confirmPasswordReset: (token: string, new_password: string) =>
    request<void>("/api/auth/password-reset/confirm", {
      method: "POST",
      body: JSON.stringify({ token, new_password }),
    }),

  // ---- Email verification ----
  // Confirm step: clicking the link in the verification email posts the
  // token here. On success the backend marks the email verified AND
  // starts a session (sets cookies), returning AuthResponse so the user
  // is logged straight in.
  verifyEmailConfirm: (token: string) =>
    request<AuthResponse>("/api/auth/verify-email/confirm", {
      method: "POST",
      body: JSON.stringify({ token }),
    }),
  // Resend step: always 204 (no enumeration). A fresh link is sent only
  // when the email maps to an active, not-yet-verified user.
  verifyEmailResend: (email: string) =>
    request<void>("/api/auth/verify-email/resend", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),

  // ---- MFA (TOTP) ----
  mfaStatus: () => request<MfaStatus>("/api/auth/mfa/status"),
  mfaSetup: () =>
    request<MfaSetup>("/api/auth/mfa/setup", { method: "POST" }),
  mfaEnable: (code: string) =>
    request<MfaEnableResponse>("/api/auth/mfa/enable", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),
  mfaDisable: (password: string, code: string) =>
    request<void>("/api/auth/mfa/disable", {
      method: "POST",
      body: JSON.stringify({ password, code }),
    }),
  mfaVerify: (mfa_token: string, code: string) =>
    request<AuthResponse>("/api/auth/mfa/verify", {
      method: "POST",
      body: JSON.stringify({ mfa_token, code }),
    }),

  // ---- Sessions ----
  listSessions: () => request<SessionInfo[]>("/api/auth/sessions"),
  revokeSession: (id: string) =>
    request<void>(`/api/auth/sessions/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),
  revokeOtherSessions: () =>
    request<{ revoked: number }>("/api/auth/sessions/revoke-others", {
      method: "POST",
    }),

  // ---- Notifications (per-user bell) ----
  listNotifications: (opts: { unread?: boolean; limit?: number } = {}) => {
    const params = new URLSearchParams();
    if (opts.unread !== undefined) params.set("unread", String(opts.unread));
    if (opts.limit !== undefined) params.set("limit", String(opts.limit));
    const qs = params.toString();
    return request<Notification[]>(`/api/notifications${qs ? `?${qs}` : ""}`);
  },
  notificationCounts: () =>
    request<{ unread: number }>("/api/notifications/counts"),
  markNotificationRead: (id: string) =>
    request<Notification>(
      `/api/notifications/${encodeURIComponent(id)}/read`,
      { method: "POST" },
    ),
  markAllNotificationsRead: () =>
    request<{ unread: number }>("/api/notifications/mark-all-read", {
      method: "POST",
    }),
  deleteNotification: (id: string) =>
    request<void>(`/api/notifications/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),

  // ---- Pipelines (Phase 1: not yet wired into Lead/Deal) ----
  listPipelines: (kind?: "lead" | "deal") => {
    const qs = kind ? `?kind=${kind}` : "";
    return request<Pipeline[]>(`/api/pipelines${qs}`);
  },
  createPipeline: (kind: "lead" | "deal", name: string, slug?: string) =>
    request<Pipeline>("/api/pipelines", {
      method: "POST",
      body: JSON.stringify({ kind, name, ...(slug ? { slug } : {}) }),
    }),
  updatePipeline: (
    id: string,
    patch: {
      name?: string;
      slug?: string;
      is_default?: boolean;
      stages?: PipelineStageDraft[];
    },
  ) =>
    request<Pipeline>(`/api/pipelines/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  deletePipeline: (id: string) =>
    request<void>(`/api/pipelines/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),

  // ---- Teams ----
  listTeams: () => request<Team[]>("/api/teams"),
  createTeam: (name: string, slug?: string) =>
    request<Team>("/api/teams", {
      method: "POST",
      body: JSON.stringify({ name, ...(slug ? { slug } : {}) }),
    }),
  updateTeam: (id: string, patch: { name?: string; slug?: string }) =>
    request<Team>(`/api/teams/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  deleteTeam: (id: string) =>
    request<void>(`/api/teams/${encodeURIComponent(id)}`, { method: "DELETE" }),
  addTeamMember: (team_id: string, user_id: string) =>
    request<Team>(`/api/teams/${encodeURIComponent(team_id)}/members`, {
      method: "POST",
      body: JSON.stringify({ user_id }),
    }),
  removeTeamMember: (team_id: string, user_id: string) =>
    request<void>(
      `/api/teams/${encodeURIComponent(team_id)}/members/${encodeURIComponent(user_id)}`,
      { method: "DELETE" },
    ),

  // ---- File attachments (S3-backed) ----
  listAttachments: (
    entity_type: "lead" | "customer" | "deal" | "quote" | "contract",
    entity_id: string,
  ) => {
    const params = new URLSearchParams({ entity_type, entity_id });
    return request<FileAttachment[]>(`/api/attachments?${params.toString()}`);
  },

  // Multipart upload bypasses the JSON `request()` helper — the
  // browser must set the multipart boundary on Content-Type itself,
  // so we can't pre-set application/json. We still attach the CSRF
  // header manually + send cookies via `credentials: include`.
  async uploadAttachment(
    entity_type: "lead" | "customer" | "deal",
    entity_id: string,
    file: File,
  ): Promise<FileAttachment> {
    const form = new FormData();
    form.append("entity_type", entity_type);
    form.append("entity_id", entity_id);
    form.append("file", file);
    const csrf = readCookie("csrf_token");
    const res = await fetch(`${API_URL}/api/attachments`, {
      method: "POST",
      body: form,
      headers: csrf ? { "X-CSRF-Token": csrf } : undefined,
      credentials: "include",
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        detail = (await res.json())?.detail || detail;
      } catch {
        /* ignore */
      }
      throw new ApiError(res.status, detail);
    }
    return res.json();
  },

  // Fetches a short-lived presigned URL, then the caller does a
  // `window.location.href = url` (or open-in-tab) — bytes flow
  // straight from S3 to the browser, never through this app.
  attachmentDownloadUrl: (id: string) =>
    request<{ url: string; expires_in: number }>(
      `/api/attachments/${encodeURIComponent(id)}/download`,
    ),

  deleteAttachment: (id: string) =>
    request<void>(`/api/attachments/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),

  // ---- Bulk imports (CSV / XLSX → leads / customers) ----
  listImports: (limit = 25, offset = 0) => {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    return request<ImportJob[]>(`/api/imports?${params.toString()}`);
  },

  getImport: (id: string) => request<ImportJob>(`/api/imports/${encodeURIComponent(id)}`),

  importTemplate: (entity_type: ImportEntityType) => {
    const params = new URLSearchParams({ entity_type });
    return request<ImportTemplate>(`/api/imports/template?${params.toString()}`);
  },

  // Multipart upload — like uploadAttachment, the browser must own the
  // multipart boundary so we can't route through the JSON `request()`
  // helper. CSRF header + cookies are attached manually.
  async createImport(
    entity_type: ImportEntityType,
    mode: ImportMode,
    file: File,
  ): Promise<ImportJob> {
    const form = new FormData();
    form.append("entity_type", entity_type);
    form.append("mode", mode);
    form.append("file", file);
    const csrf = readCookie("csrf_token");
    const res = await fetch(`${API_URL}/api/imports`, {
      method: "POST",
      body: form,
      headers: csrf ? { "X-CSRF-Token": csrf } : undefined,
      credentials: "include",
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        detail = (await res.json())?.detail || detail;
      } catch {
        /* ignore */
      }
      throw new ApiError(res.status, detail);
    }
    return res.json();
  },

  // ---- Exports (streaming CSV download) ----
  // Returns the absolute URL; the caller navigates the browser to it so
  // the file streams straight from the API as an attachment. Cookies ride
  // along on the top-level navigation, so auth still applies.
  exportUrl: (entity_type: ImportEntityType) =>
    `${API_URL}/api/exports/${encodeURIComponent(entity_type)}?format=csv`,

  // ---- Notes (markdown notes per Lead/Customer/Deal) ----
  listNotes: (entity_type: "lead" | "customer" | "deal" | "company", entity_id: string) => {
    const params = new URLSearchParams({ entity_type, entity_id });
    return request<Note[]>(`/api/notes?${params.toString()}`);
  },
  createNote: (
    entity_type: "lead" | "customer" | "deal" | "company",
    entity_id: string,
    body: string,
  ) =>
    request<Note>("/api/notes", {
      method: "POST",
      body: JSON.stringify({ entity_type, entity_id, body }),
    }),
  updateNote: (id: string, body: string) =>
    request<Note>(`/api/notes/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify({ body }),
    }),
  deleteNote: (id: string) =>
    request<void>(`/api/notes/${encodeURIComponent(id)}`, { method: "DELETE" }),

  // ---- Activities (timeline) ----
  listActivities: (
    entity_type: "lead" | "customer" | "deal" | "company",
    entity_id: string,
    opts: { limit?: number; offset?: number } = {},
  ) => {
    const params = new URLSearchParams({ entity_type, entity_id });
    if (opts.limit !== undefined) params.set("limit", String(opts.limit));
    if (opts.offset !== undefined) params.set("offset", String(opts.offset));
    return request<ActivityEntry[]>(`/api/activities?${params.toString()}`);
  },

  // ---- Audit log (admin/manager only) ----
  listAudit: (filters: AuditFilters = {}) => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") params.set(k, String(v));
    });
    const qs = params.toString();
    return request<AuditEntry[]>(`/api/audit${qs ? `?${qs}` : ""}`);
  },
  logout: (token: string) =>
    request<void>("/api/auth/logout", { method: "POST", token }),

  // Leads
  listLeads: (token: string, opts?: { q?: string; cursor?: string; limit?: number }) => {
    const params = new URLSearchParams();
    if (opts?.q) params.set("q", opts.q);
    if (opts?.cursor) params.set("cursor", opts.cursor);
    if (opts?.limit) params.set("limit", String(opts.limit));
    const qs = params.toString();
    return request<Page<Lead>>(`/api/leads${qs ? `?${qs}` : ""}`, { token });
  },
  // Walk every page — for analytics/exports that genuinely need all rows.
  listAllLeads: async (token: string, opts?: { q?: string }): Promise<Lead[]> => {
    const all: Lead[] = [];
    let cursor: string | undefined;
    do {
      const page = await api.listLeads(token, { ...opts, cursor, limit: 200 });
      all.push(...page.items);
      cursor = page.next_cursor ?? undefined;
    } while (cursor);
    return all;
  },
  createLead: (token: string, payload: Partial<Lead>) =>
    request<Lead>("/api/leads", { method: "POST", token, body: JSON.stringify(payload) }),
  getLead: (token: string, id: string) => request<Lead>(`/api/leads/${id}`, { token }),
  updateLead: (token: string, id: string, payload: Partial<Lead>) =>
    request<Lead>(`/api/leads/${id}`, { method: "PATCH", token, body: JSON.stringify(payload) }),
  scoreLead: (token: string, id: string) =>
    request<Lead>(`/api/leads/${id}/score`, { method: "POST", token }),
  deleteLead: (token: string, id: string) =>
    request<void>(`/api/leads/${id}`, { method: "DELETE", token }),

  // Customers
  listCustomers: (token: string, opts?: { q?: string; cursor?: string; limit?: number }) => {
    const params = new URLSearchParams();
    if (opts?.q) params.set("q", opts.q);
    if (opts?.cursor) params.set("cursor", opts.cursor);
    if (opts?.limit) params.set("limit", String(opts.limit));
    const qs = params.toString();
    return request<Page<Customer>>(`/api/customers${qs ? `?${qs}` : ""}`, { token });
  },
  listAllCustomers: async (token: string, opts?: { q?: string }): Promise<Customer[]> => {
    const all: Customer[] = [];
    let cursor: string | undefined;
    do {
      const page = await api.listCustomers(token, { ...opts, cursor, limit: 200 });
      all.push(...page.items);
      cursor = page.next_cursor ?? undefined;
    } while (cursor);
    return all;
  },
  createCustomer: (token: string, payload: Partial<Customer>) =>
    request<Customer>("/api/customers", { method: "POST", token, body: JSON.stringify(payload) }),
  getCustomer: (token: string, id: string) => request<Customer>(`/api/customers/${id}`, { token }),
  updateCustomer: (token: string, id: string, payload: Partial<Customer>, version?: number) =>
    request<Customer>(`/api/customers/${id}`, {
      method: "PATCH",
      token,
      body: JSON.stringify(payload),
      headers: version !== undefined ? { "If-Match": String(version) } : undefined,
    }),
  summarizeCustomer: (token: string, id: string) =>
    request<Customer>(`/api/customers/${id}/summarize`, { method: "POST", token }),
  deleteCustomer: (token: string, id: string) =>
    request<void>(`/api/customers/${id}`, { method: "DELETE", token }),

  // Companies (B2B accounts)
  listCompanies: (token: string, opts?: { q?: string; cursor?: string; limit?: number }) => {
    const params = new URLSearchParams();
    if (opts?.q) params.set("q", opts.q);
    if (opts?.cursor) params.set("cursor", opts.cursor);
    if (opts?.limit) params.set("limit", String(opts.limit));
    const qs = params.toString();
    return request<Page<Company>>(`/api/companies${qs ? `?${qs}` : ""}`, { token });
  },
  listAllCompanies: async (token: string, opts?: { q?: string }): Promise<Company[]> => {
    const all: Company[] = [];
    let cursor: string | undefined;
    do {
      const page = await api.listCompanies(token, { ...opts, cursor, limit: 200 });
      all.push(...page.items);
      cursor = page.next_cursor ?? undefined;
    } while (cursor);
    return all;
  },
  createCompany: (token: string, payload: Partial<Company>) =>
    request<Company>("/api/companies", { method: "POST", token, body: JSON.stringify(payload) }),
  getCompany: (token: string, id: string) => request<Company>(`/api/companies/${id}`, { token }),
  getCompanyRollup: (token: string, id: string) =>
    request<CompanyRollup>(`/api/companies/${id}/rollup`, { token }),
  updateCompany: (token: string, id: string, payload: Partial<Company>, version?: number) =>
    request<Company>(`/api/companies/${id}`, {
      method: "PATCH",
      token,
      body: JSON.stringify(payload),
      headers: version !== undefined ? { "If-Match": String(version) } : undefined,
    }),
  deleteCompany: (token: string, id: string) =>
    request<void>(`/api/companies/${id}`, { method: "DELETE", token }),

  // Custom field definitions (per-org schema extension)
  listCustomFields: (token: string, entityType?: CustomFieldEntity) => {
    const qs = entityType ? `?entity_type=${entityType}` : "";
    return request<CustomFieldDefinition[]>(`/api/custom-fields${qs}`, { token });
  },
  createCustomField: (token: string, payload: Partial<CustomFieldDefinition>) =>
    request<CustomFieldDefinition>("/api/custom-fields", {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),
  updateCustomField: (
    token: string,
    id: string,
    payload: Partial<CustomFieldDefinition>,
  ) =>
    request<CustomFieldDefinition>(`/api/custom-fields/${id}`, {
      method: "PATCH",
      token,
      body: JSON.stringify(payload),
    }),
  deleteCustomField: (token: string, id: string) =>
    request<void>(`/api/custom-fields/${id}`, { method: "DELETE", token }),

  // Tags
  listTags: (token: string) => request<Tag[]>("/api/tags", { token }),
  createTag: (token: string, payload: { name: string; color?: string }) =>
    request<Tag>("/api/tags", { method: "POST", token, body: JSON.stringify(payload) }),
  updateTag: (
    token: string,
    id: string,
    payload: { name?: string; color?: string },
  ) =>
    request<Tag>(`/api/tags/${id}`, {
      method: "PATCH",
      token,
      body: JSON.stringify(payload),
    }),
  deleteTag: (token: string, id: string) =>
    request<void>(`/api/tags/${id}`, { method: "DELETE", token }),
  listTagAssignments: (
    token: string,
    entityType: TaggableEntity,
    entityIds: string[],
  ) => {
    const qs = `?entity_type=${entityType}&entity_ids=${entityIds.join(",")}`;
    return request<EntityTags[]>(`/api/tags/assignments${qs}`, { token });
  },
  assignTag: (
    token: string,
    payload: { tag_id: string; entity_type: TaggableEntity; entity_id: string },
  ) =>
    request<Tag[]>("/api/tags/assign", {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),
  unassignTag: (
    token: string,
    payload: { tag_id: string; entity_type: TaggableEntity; entity_id: string },
  ) =>
    request<void>("/api/tags/unassign", {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),
  bulkTag: (
    token: string,
    payload: {
      tag_ids: string[];
      entity_type: TaggableEntity;
      entity_ids: string[];
      action: "add" | "remove";
    },
  ) =>
    request<{ affected: number }>("/api/tags/bulk", {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),

  // Saved segments (stored list filters)
  listSegments: (token: string, entityType?: TaggableEntity) => {
    const qs = entityType ? `?entity_type=${entityType}` : "";
    return request<SavedSegment[]>(`/api/segments${qs}`, { token });
  },
  createSegment: (
    token: string,
    payload: { entity_type: TaggableEntity; name: string; filters: Record<string, unknown> },
  ) =>
    request<SavedSegment>("/api/segments", {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),
  updateSegment: (
    token: string,
    id: string,
    payload: { name?: string; filters?: Record<string, unknown> },
  ) =>
    request<SavedSegment>(`/api/segments/${id}`, {
      method: "PATCH",
      token,
      body: JSON.stringify(payload),
    }),
  deleteSegment: (token: string, id: string) =>
    request<void>(`/api/segments/${id}`, { method: "DELETE", token }),

  // Duplicate detection & merge
  listDuplicates: (token: string, entityType: DuplicateEntity) =>
    request<DuplicateGroupsOut>(`/api/duplicates?entity_type=${entityType}`, { token }),
  mergeDuplicates: (
    token: string,
    payload: { entity_type: DuplicateEntity; survivor_id: string; loser_ids: string[] },
  ) =>
    request<MergeResult>("/api/duplicates/merge", {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),

  // Web-to-Lead capture forms
  listForms: (token: string) => request<WebForm[]>("/api/forms", { token }),
  createForm: (
    token: string,
    payload: {
      name: string;
      default_source?: string | null;
      redirect_url?: string | null;
      active?: boolean;
    },
  ) => request<WebForm>("/api/forms", { method: "POST", token, body: JSON.stringify(payload) }),
  updateForm: (
    token: string,
    id: string,
    payload: {
      name?: string;
      default_source?: string | null;
      redirect_url?: string | null;
      active?: boolean;
    },
  ) =>
    request<WebForm>(`/api/forms/${id}`, {
      method: "PATCH",
      token,
      body: JSON.stringify(payload),
    }),
  deleteForm: (token: string, id: string) =>
    request<void>(`/api/forms/${id}`, { method: "DELETE", token }),

  // Deals
  listDeals: (token: string) => request<Deal[]>("/api/deals", { token }),
  createDeal: (token: string, payload: Partial<Deal>) =>
    request<Deal>("/api/deals", { method: "POST", token, body: JSON.stringify(payload) }),
  updateDeal: (token: string, id: string, payload: Partial<Deal>, version?: number) =>
    request<Deal>(`/api/deals/${id}`, {
      method: "PATCH",
      token,
      body: JSON.stringify(payload),
      headers: version !== undefined ? { "If-Match": String(version) } : undefined,
    }),
  moveDeal: (
    token: string,
    id: string,
    stage: DealStage,
    sort_index: number,
    version?: number,
  ) =>
    request<Deal>(`/api/deals/${id}/move`, {
      method: "POST",
      token,
      body: JSON.stringify({ stage, sort_index }),
      headers: version !== undefined ? { "If-Match": String(version) } : undefined,
    }),
  getDeal: (token: string, id: string) => request<Deal>(`/api/deals/${id}`, { token }),
  deleteDeal: (token: string, id: string) =>
    request<void>(`/api/deals/${id}`, { method: "DELETE", token }),

  // Tasks
  listTasks: (token: string, opts?: { status?: TaskStatus; mine?: boolean }) => {
    const params = new URLSearchParams();
    if (opts?.status) params.set("status", opts.status);
    if (opts?.mine) params.set("mine", "true");
    const qs = params.toString();
    return request<Task[]>(`/api/tasks${qs ? `?${qs}` : ""}`, { token });
  },
  createTask: (token: string, payload: Partial<Task>) =>
    request<Task>("/api/tasks", { method: "POST", token, body: JSON.stringify(payload) }),
  updateTask: (token: string, id: string, payload: Partial<Task>, version?: number) =>
    request<Task>(`/api/tasks/${id}`, {
      method: "PATCH",
      token,
      body: JSON.stringify(payload),
      headers: version !== undefined ? { "If-Match": String(version) } : undefined,
    }),
  deleteTask: (token: string, id: string) =>
    request<void>(`/api/tasks/${id}`, { method: "DELETE", token }),

  // Quotes (versioned proposals — ADR-016)
  listQuotes: (
    token: string,
    opts?: {
      status?: QuoteStatus;
      deal_id?: string;
      customer_id?: string;
      cursor?: string;
      limit?: number;
    },
  ) => {
    const params = new URLSearchParams();
    if (opts?.status) params.set("status", opts.status);
    if (opts?.deal_id) params.set("deal_id", opts.deal_id);
    if (opts?.customer_id) params.set("customer_id", opts.customer_id);
    if (opts?.cursor) params.set("cursor", opts.cursor);
    if (opts?.limit) params.set("limit", String(opts.limit));
    const qs = params.toString();
    return request<Page<Quote>>(`/api/quotes${qs ? `?${qs}` : ""}`, { token });
  },
  getQuote: (token: string, id: string) => request<Quote>(`/api/quotes/${id}`, { token }),
  createQuote: (token: string, payload: QuoteCreate) =>
    request<Quote>("/api/quotes", { method: "POST", token, body: JSON.stringify(payload) }),
  updateQuote: (token: string, id: string, payload: QuoteUpdate) =>
    request<Quote>(`/api/quotes/${id}`, { method: "PATCH", token, body: JSON.stringify(payload) }),
  deleteQuote: (token: string, id: string) =>
    request<void>(`/api/quotes/${id}`, { method: "DELETE", token }),
  sendQuote: (token: string, id: string) =>
    request<Quote>(`/api/quotes/${id}/send`, { method: "POST", token }),
  acceptQuote: (token: string, id: string) =>
    request<Quote>(`/api/quotes/${id}/accept`, { method: "POST", token }),
  declineQuote: (token: string, id: string) =>
    request<Quote>(`/api/quotes/${id}/decline`, { method: "POST", token }),
  resendQuote: (token: string, id: string) =>
    request<Quote>(`/api/quotes/${id}/resend`, { method: "POST", token }),
  // Enqueues a PDF render (202). The worker attaches it to the quote,
  // surfacing via listAttachments("quote", id). Returns {queued} flag.
  generateQuotePdf: (token: string, id: string) =>
    request<{ queued: boolean; job_id?: string; dedupe?: boolean }>(
      `/api/quotes/${id}/pdf`,
      { method: "POST", token },
    ),

  // Contracts (versioned agreements — ADR-016)
  listContracts: (
    token: string,
    opts?: {
      status?: ContractStatus;
      deal_id?: string;
      customer_id?: string;
      quote_id?: string;
      cursor?: string;
      limit?: number;
    },
  ) => {
    const params = new URLSearchParams();
    if (opts?.status) params.set("status", opts.status);
    if (opts?.deal_id) params.set("deal_id", opts.deal_id);
    if (opts?.customer_id) params.set("customer_id", opts.customer_id);
    if (opts?.quote_id) params.set("quote_id", opts.quote_id);
    if (opts?.cursor) params.set("cursor", opts.cursor);
    if (opts?.limit) params.set("limit", String(opts.limit));
    const qs = params.toString();
    return request<Page<Contract>>(`/api/contracts${qs ? `?${qs}` : ""}`, { token });
  },
  getContract: (token: string, id: string) =>
    request<Contract>(`/api/contracts/${id}`, { token }),
  createContract: (token: string, payload: ContractCreate) =>
    request<Contract>("/api/contracts", { method: "POST", token, body: JSON.stringify(payload) }),
  createContractFromQuote: (token: string, quoteId: string, templateId?: string) => {
    const qs = templateId ? `?template_id=${encodeURIComponent(templateId)}` : "";
    return request<Contract>(`/api/contracts/from-quote/${quoteId}${qs}`, {
      method: "POST",
      token,
    });
  },
  applyContractTemplate: (token: string, contractId: string, templateId: string) =>
    request<Contract>(`/api/contracts/${contractId}/apply-template/${templateId}`, {
      method: "POST",
      token,
    }),
  updateContract: (token: string, id: string, payload: ContractUpdate) =>
    request<Contract>(`/api/contracts/${id}`, {
      method: "PATCH",
      token,
      body: JSON.stringify(payload),
    }),
  deleteContract: (token: string, id: string) =>
    request<void>(`/api/contracts/${id}`, { method: "DELETE", token }),
  sendContract: (token: string, id: string) =>
    request<Contract>(`/api/contracts/${id}/send`, { method: "POST", token }),
  signContract: (token: string, id: string) =>
    request<Contract>(`/api/contracts/${id}/sign`, { method: "POST", token }),
  activateContract: (token: string, id: string) =>
    request<Contract>(`/api/contracts/${id}/activate`, { method: "POST", token }),
  terminateContract: (token: string, id: string) =>
    request<Contract>(`/api/contracts/${id}/terminate`, { method: "POST", token }),
  resendContract: (token: string, id: string) =>
    request<Contract>(`/api/contracts/${id}/resend`, { method: "POST", token }),
  // Enqueues a PDF render (202). The worker attaches it to the contract,
  // surfacing via listAttachments("contract", id). Returns {queued} flag.
  generateContractPdf: (token: string, id: string) =>
    request<{ queued: boolean; job_id?: string; dedupe?: boolean }>(
      `/api/contracts/${id}/pdf`,
      { method: "POST", token },
    ),

  // Signature requests on a quote or contract (ADR-016)
  listSignatureRequests: (
    token: string,
    filter: { quote_id?: string; contract_id?: string },
  ) => {
    const params = new URLSearchParams();
    if (filter.quote_id) params.set("quote_id", filter.quote_id);
    if (filter.contract_id) params.set("contract_id", filter.contract_id);
    return request<Page<SignatureRequest>>(`/api/signatures?${params.toString()}`, { token });
  },
  createSignatureRequest: (
    token: string,
    payload: {
      quote_id?: string;
      contract_id?: string;
      signer_name: string;
      signer_email: string;
      message?: string | null;
    },
  ) =>
    request<SignatureRequest>("/api/signatures", {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),
  getSignatureRequest: (token: string, id: string) =>
    request<SignatureRequest>(`/api/signatures/${id}`, { token }),
  sendSignatureRequest: (token: string, id: string) =>
    request<SignatureRequest>(`/api/signatures/${id}/send`, { method: "POST", token }),
  cancelSignatureRequest: (token: string, id: string) =>
    request<SignatureRequest>(`/api/signatures/${id}/cancel`, { method: "POST", token }),
  deleteSignatureRequest: (token: string, id: string) =>
    request<void>(`/api/signatures/${id}`, { method: "DELETE", token }),

  // Merge-field document templates (ADR-016)
  listMergeFields: (token: string, docType: DocumentType = "contract") =>
    request<MergeField[]>(`/api/document-templates/fields?doc_type=${docType}`, { token }),
  listDocumentTemplates: (token: string, docType?: DocumentType) => {
    const qs = docType ? `?doc_type=${docType}` : "";
    return request<DocumentTemplate[]>(`/api/document-templates${qs}`, { token });
  },
  getDocumentTemplate: (token: string, id: string) =>
    request<DocumentTemplate>(`/api/document-templates/${id}`, { token }),
  createDocumentTemplate: (token: string, payload: DocumentTemplateCreate) =>
    request<DocumentTemplate>("/api/document-templates", {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),
  updateDocumentTemplate: (token: string, id: string, payload: DocumentTemplateUpdate) =>
    request<DocumentTemplate>(`/api/document-templates/${id}`, {
      method: "PATCH",
      token,
      body: JSON.stringify(payload),
    }),
  deleteDocumentTemplate: (token: string, id: string) =>
    request<void>(`/api/document-templates/${id}`, { method: "DELETE", token }),

  // Public signer surface — no token; the URL token IS the credential.
  getSigningContext: (signToken: string) =>
    request<SignatureSignContext>(`/api/signatures/sign/${encodeURIComponent(signToken)}`),
  submitSignature: (signToken: string, typed_name: string) =>
    request<SignatureRequest>(`/api/signatures/sign/${encodeURIComponent(signToken)}`, {
      method: "POST",
      body: JSON.stringify({ typed_name }),
    }),
  declineSignature: (signToken: string, reason?: string | null) =>
    request<SignatureRequest>(`/api/signatures/sign/${encodeURIComponent(signToken)}/decline`, {
      method: "POST",
      body: JSON.stringify({ reason: reason ?? null }),
    }),

  // Dashboard
  stats: (token: string) => request<DashboardStats>("/api/dashboard/stats", { token }),

  // Performance / KPI
  performanceSummary: (token: string, period: GoalPeriod = "month") =>
    request<PerformanceSummary>(`/api/performance/summary?period=${period}`, { token }),
  listGoals: (token: string) => request<SalesGoal[]>("/api/performance/goals", { token }),
  createGoal: (
    token: string,
    payload: {
      period: GoalPeriod;
      period_start: string;
      metric: GoalMetric;
      target: number;
      owner_id?: string | null;
      team_id?: string | null;
    },
  ) =>
    request<SalesGoal>("/api/performance/goals", {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),
  updateGoal: (
    token: string,
    id: string,
    payload: { period?: GoalPeriod; period_start?: string; metric?: GoalMetric; target?: number },
  ) =>
    request<SalesGoal>(`/api/performance/goals/${id}`, {
      method: "PATCH",
      token,
      body: JSON.stringify(payload),
    }),
  deleteGoal: (token: string, id: string) =>
    request<void>(`/api/performance/goals/${id}`, { method: "DELETE", token }),

  // Automations
  listAutomations: (token: string) =>
    request<AutomationRule[]>("/api/automations", { token }),
  createAutomation: (
    token: string,
    payload: {
      name: string;
      description?: string | null;
      enabled?: boolean;
      trigger: AutomationTrigger;
      action: AutomationAction;
      action_config?: Record<string, unknown>;
    },
  ) =>
    request<AutomationRule>("/api/automations", {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),
  updateAutomation: (
    token: string,
    id: string,
    payload: {
      name?: string;
      description?: string | null;
      enabled?: boolean;
      trigger?: AutomationTrigger;
      action?: AutomationAction;
      action_config?: Record<string, unknown>;
    },
  ) =>
    request<AutomationRule>(`/api/automations/${id}`, {
      method: "PATCH",
      token,
      body: JSON.stringify(payload),
    }),
  deleteAutomation: (token: string, id: string) =>
    request<void>(`/api/automations/${id}`, { method: "DELETE", token }),
  listAutomationRuns: (token: string, ruleId?: string) =>
    request<AutomationRun[]>(
      `/api/automations/runs${ruleId ? `?rule_id=${ruleId}` : ""}`,
      { token },
    ),

  // Trash
  listTrash: (token: string) =>
    request<TrashItem[]>("/api/trash", { token }),
  trashCounts: (token: string) =>
    request<{ lead: number; customer: number; deal: number; task: number }>(
      "/api/trash/counts",
      { token },
    ),
  restoreFromTrash: (token: string, type: TrashItem["entity_type"], id: string) =>
    request<void>(`/api/trash/${type}/${id}/restore`, { method: "POST", token }),
  hardDelete: (token: string, type: TrashItem["entity_type"], id: string) =>
    request<void>(`/api/trash/${type}/${id}`, { method: "DELETE", token }),
  emptyTrash: (token: string) =>
    request<void>("/api/trash/empty", { method: "POST", token }),

  // Assistant
  chat: (token: string, message: string, locale: string) =>
    request<{ reply: string }>("/api/assistant/chat", {
      method: "POST",
      token,
      body: JSON.stringify({ message, locale }),
    }),

  // Billing
  plans: () => request<PlanOut[]>("/api/billing/plans"),
  billingMe: (token: string) => request<BillingMe>("/api/billing/me", { token }),
  upgrade: (token: string, plan: PlanId, billing_cycle: BillingCycle) =>
    request<BillingMe>("/api/billing/upgrade", {
      method: "POST",
      token,
      body: JSON.stringify({ plan, billing_cycle }),
    }),
  checkout: (token: string, plan: PlanId, billing_cycle: BillingCycle) =>
    request<{ url: string }>("/api/billing/checkout", {
      method: "POST",
      token,
      body: JSON.stringify({ plan, billing_cycle }),
    }),
  portal: (token: string, return_url?: string) =>
    request<{ url: string }>("/api/billing/portal", {
      method: "POST",
      token,
      body: JSON.stringify({ return_url: return_url ?? null }),
    }),

  // ── Organizations ────────────────────────────────────────────────
  // Memberships drive the org switcher. switchOrg() writes the new
  // active org server-side and the response carries the refreshed
  // user object; callers reload the page to remount data.
  listMyOrgs: (token: string) =>
    request<Membership[]>("/api/orgs/me", { token }),
  switchOrg: (token: string, organization_id: string) =>
    request<User>("/api/orgs/me/switch", {
      method: "POST",
      token,
      body: JSON.stringify({ organization_id }),
    }),
  createOrg: (token: string, name: string, slug?: string) =>
    request<Organization>("/api/orgs", {
      method: "POST",
      token,
      body: JSON.stringify({ name, slug: slug ?? null }),
    }),

  // ── Invites ──────────────────────────────────────────────────────
  // Admin endpoints — current org only; backend resolves it from the
  // user's last_active_org_id.
  listInvites: (token: string) =>
    request<Invite[]>("/api/orgs/current/invites", { token }),
  createInvite: (token: string, email: string, role: Role) =>
    request<Invite>("/api/orgs/current/invites", {
      method: "POST",
      token,
      body: JSON.stringify({ email, role }),
    }),
  revokeInvite: (token: string, invite_id: string) =>
    request<void>(`/api/orgs/current/invites/${invite_id}`, {
      method: "DELETE",
      token,
    }),
  // ── API keys (Public API bearer credentials — ADR-016) ───────────
  // Admin-gated, current-org only. createApiKey returns the plaintext
  // `token` ONCE; subsequent reads expose only `display_prefix`.
  listApiKeys: (token: string) =>
    request<ApiKey[]>("/api/api-keys", { token }),
  createApiKey: (token: string, payload: ApiKeyCreate) =>
    request<ApiKeyCreated>("/api/api-keys", {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),
  getApiKey: (token: string, id: string) =>
    request<ApiKey>(`/api/api-keys/${encodeURIComponent(id)}`, { token }),
  revokeApiKey: (token: string, id: string) =>
    request<ApiKey>(`/api/api-keys/${encodeURIComponent(id)}`, {
      method: "DELETE",
      token,
    }),

  // ── WhatsApp inbox (omnichannel, phase 1) ───────────────────────
  // Accounts are admin-gated on the backend (connect/update/delete);
  // listing + reading + sending are any member's.
  listWhatsAppAccounts: (token: string) =>
    request<WhatsAppAccount[]>("/api/whatsapp/accounts", { token }),
  connectWhatsAppAccount: (token: string, payload: WhatsAppAccountConnect) =>
    request<WhatsAppAccount>("/api/whatsapp/accounts", {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),
  disconnectWhatsAppAccount: (token: string, id: string) =>
    request<void>(`/api/whatsapp/accounts/${encodeURIComponent(id)}`, {
      method: "DELETE",
      token,
    }),
  listConversations: (token: string, status?: ConversationStatus) =>
    request<Conversation[]>(
      `/api/whatsapp/conversations${status ? `?status=${status}` : ""}`,
      { token },
    ),
  getConversation: (token: string, id: string) =>
    request<Conversation>(`/api/whatsapp/conversations/${encodeURIComponent(id)}`, { token }),
  markConversationRead: (token: string, id: string) =>
    request<Conversation>(`/api/whatsapp/conversations/${encodeURIComponent(id)}/read`, {
      method: "POST",
      token,
    }),
  linkConversation: (
    token: string,
    id: string,
    payload: { lead_id?: string | null; customer_id?: string | null },
  ) =>
    request<Conversation>(`/api/whatsapp/conversations/${encodeURIComponent(id)}/link`, {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),
  listMessages: (token: string, conversationId: string, limit = 100) =>
    request<ConversationMessage[]>(
      `/api/whatsapp/conversations/${encodeURIComponent(conversationId)}/messages?limit=${limit}`,
      { token },
    ),
  sendMessage: (token: string, conversationId: string, body: string) =>
    request<ConversationMessage>(
      `/api/whatsapp/conversations/${encodeURIComponent(conversationId)}/messages`,
      { method: "POST", token, body: JSON.stringify({ body }) },
    ),

  // Public — no token. Token in URL IS the credential.
  previewInvite: (token: string) =>
    request<InvitePreview>(`/api/invites/${encodeURIComponent(token)}`),
  registerWithInvite: (payload: {
    token: string;
    full_name: string;
    password: string;
    locale: string;
  }) =>
    request<AuthResponse>("/api/auth/register-with-invite", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
