import { clearToken, readCookie } from "./auth";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
  created_at: string;
  updated_at: string;
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
  owner_id: string | null;
  sort_index: number;
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
  created_at: string;
  updated_at: string;
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

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: string;
  locale: string;
  is_active: boolean;
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

/** Returned by /login when the user has MFA enabled — instead of the
 *  full AuthResponse. The client posts `mfa_token` + a TOTP/backup
 *  code to /mfa/verify to complete the login. */
export interface MfaChallenge {
  mfa_required: true;
  mfa_token: string;
}

export type LoginResponse = AuthResponse | MfaChallenge;

export function isMfaChallenge(r: LoginResponse): r is MfaChallenge {
  return (r as MfaChallenge).mfa_required === true;
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
  entity_type: "lead" | "customer" | "deal";
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

export type PlanId = "free" | "standard" | "premium";
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

// Hook for the app shell to redirect on 401 without circular imports.
let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: (() => void) | null) {
  onUnauthorized = fn;
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
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
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
  register: (payload: { email: string; password: string; full_name: string; locale: string }) =>
    request<AuthResponse>("/api/auth/register", {
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
    entity_type: "lead" | "customer" | "deal",
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

  // ---- Notes (markdown notes per Lead/Customer/Deal) ----
  listNotes: (entity_type: "lead" | "customer" | "deal", entity_id: string) => {
    const params = new URLSearchParams({ entity_type, entity_id });
    return request<Note[]>(`/api/notes?${params.toString()}`);
  },
  createNote: (
    entity_type: "lead" | "customer" | "deal",
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
    entity_type: "lead" | "customer" | "deal",
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
  listLeads: (token: string, q?: string) =>
    request<Lead[]>(`/api/leads${q ? `?q=${encodeURIComponent(q)}` : ""}`, { token }),
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
  listCustomers: (token: string, q?: string) =>
    request<Customer[]>(`/api/customers${q ? `?q=${encodeURIComponent(q)}` : ""}`, { token }),
  createCustomer: (token: string, payload: Partial<Customer>) =>
    request<Customer>("/api/customers", { method: "POST", token, body: JSON.stringify(payload) }),
  getCustomer: (token: string, id: string) => request<Customer>(`/api/customers/${id}`, { token }),
  updateCustomer: (token: string, id: string, payload: Partial<Customer>) =>
    request<Customer>(`/api/customers/${id}`, {
      method: "PATCH",
      token,
      body: JSON.stringify(payload),
    }),
  summarizeCustomer: (token: string, id: string) =>
    request<Customer>(`/api/customers/${id}/summarize`, { method: "POST", token }),
  deleteCustomer: (token: string, id: string) =>
    request<void>(`/api/customers/${id}`, { method: "DELETE", token }),

  // Deals
  listDeals: (token: string) => request<Deal[]>("/api/deals", { token }),
  createDeal: (token: string, payload: Partial<Deal>) =>
    request<Deal>("/api/deals", { method: "POST", token, body: JSON.stringify(payload) }),
  updateDeal: (token: string, id: string, payload: Partial<Deal>) =>
    request<Deal>(`/api/deals/${id}`, { method: "PATCH", token, body: JSON.stringify(payload) }),
  moveDeal: (token: string, id: string, stage: DealStage, sort_index: number) =>
    request<Deal>(`/api/deals/${id}/move`, {
      method: "POST",
      token,
      body: JSON.stringify({ stage, sort_index }),
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
  updateTask: (token: string, id: string, payload: Partial<Task>) =>
    request<Task>(`/api/tasks/${id}`, { method: "PATCH", token, body: JSON.stringify(payload) }),
  deleteTask: (token: string, id: string) =>
    request<void>(`/api/tasks/${id}`, { method: "DELETE", token }),

  // Dashboard
  stats: (token: string) => request<DashboardStats>("/api/dashboard/stats", { token }),

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
