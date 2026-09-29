import type { paths } from './openapi.generated';

// The route inventory is checked against the API's generated OpenAPI paths at build time.
export const contractRoutes = [
  '/api/health', '/api/auth/me', '/api/auth/login', '/api/auth/logout',
  '/api/onboardings', '/api/onboardings/{onboarding_id}',
  '/api/onboardings/{onboarding_id}/approval', '/api/onboardings/{onboarding_id}/recover',
  '/api/onboardings/{onboarding_id}/handoff', '/api/onboardings/{onboarding_id}/checklist/{item_id}',
  '/api/onboardings/{onboarding_id}/state', '/api/reminders/{reminder_id}/approval',
  '/api/client/exchange', '/api/client/onboarding', '/api/client/submissions', '/api/client/assets',
] as const satisfies readonly (keyof paths)[];

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '/api').replace(/\/$/, '');

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PATCH';
  body?: unknown;
  csrfToken?: string;
  clientToken?: string;
  formData?: FormData;
};

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';
  if (options.csrfToken) headers['X-CSRF-Token'] = options.csrfToken;
  if (options.clientToken) headers.Authorization = `Bearer ${options.clientToken}`;

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: options.method ?? 'GET',
      headers,
      credentials: 'include',
      body: options.formData ?? (options.body === undefined ? undefined : JSON.stringify(options.body)),
    });
  } catch {
    throw new ApiError('Cannot reach ClientLaunch. Check that the API is running and try again.', 0);
  }

  const contentType = response.headers.get('content-type') ?? '';
  const payload: unknown = contentType.includes('application/json')
    ? await response.json().catch(() => null)
    : await response.text().catch(() => '');
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    if (typeof payload === 'object' && payload !== null) {
      const data = payload as Record<string, unknown>;
      const detail = data.detail ?? data.message ?? data.error;
      if (typeof detail === 'string') message = detail;
      else if (Array.isArray(detail)) message = detail.map((item) => typeof item === 'object' && item !== null && 'msg' in item ? String(item.msg) : String(item)).join('; ');
    } else if (typeof payload === 'string' && payload.trim()) {
      message = payload;
    }
    throw new ApiError(message, response.status);
  }
  return payload as T;
}

export type User = {
  id: string;
  email: string;
  name: string;
  role: 'admin' | 'operator' | 'viewer';
  workspace_id: string;
};

export type AuthSession = {
  user: User;
  csrf_token: string;
  expires_at?: string;
};

export type Health = { status?: string; mode?: 'DEMO' | 'CONNECTED' | string };

export type OnboardingSummary = {
  id: string;
  client_name: string;
  client_email?: string;
  service_names: string[];
  status: string;
  substate?: string | null;
  owner_name?: string | null;
  progress_percent?: number;
  created_at: string;
  required_complete?: number;
  required_total?: number;
  workspace_name?: string;
};

export type Plan = {
  id: string;
  revision: number;
  status: string;
  proposal_hash: string;
  summary?: string;
  deliverables?: string[];
  risks?: string[];
  missing_inputs?: string[];
  suggestions?: string[];
  welcome_draft?: string;
};

export type ChecklistItem = {
  id: string;
  key?: string;
  title: string;
  description?: string | null;
  required: boolean;
  status: string;
  due_at?: string | null;
  owner_name?: string | null;
  source?: string;
  client_visible?: boolean;
  value?: string | null;
};

export type ProvisioningOperation = {
  id: string;
  system: string;
  action: string;
  status: string;
  external_id?: string | null;
  error?: string | null;
  error_message?: string | null;
  attempt_count?: number;
  created_at?: string;
};

export type ExternalResource = {
  id: string;
  system: string;
  external_id: string;
  name?: string;
  url?: string | null;
  resource_type?: string;
  kind?: string;
};

export type ProjectFolder = {
  id: string | null;
  service_code: string;
  folder_key: string;
  name: string;
  parent_id: string | null;
  parent_folder_key: string | null;
  parent_external_id: string | null;
  external_id: string | null;
  url: string | null;
  status: string;
};

export type FolderStructure = {
  root: { name: string; external_id: string | null; url: string | null; status: string };
  folders: ProjectFolder[];
  planned_count: number;
  complete_count: number;
  complete: boolean;
};

export type TimelineEvent = {
  id: string;
  kind?: string;
  message?: string;
  type?: string;
  event_type?: string;
  title?: string;
  description?: string;
  detail?: string;
  occurred_at?: string;
  created_at?: string;
  actor?: string;
};

export type Approval = {
  id: string;
  decision?: string;
  status?: string;
  created_at?: string;
  decided_at?: string;
  approver_name?: string;
  reason?: string;
};

export type Asset = {
  id: string;
  name?: string;
  filename?: string;
  file_name?: string;
  content_type?: string;
  created_at?: string;
  checklist_item_id?: string;
};

export type Submission = {
  id: string;
  created_at?: string;
  submitted_at?: string;
  answers?: { checklist_item_id: string; value: string }[];
};

export type WelcomeEntry = {
  id: string;
  subject?: string;
  body?: string;
  recipient?: string;
  status?: string;
  created_at?: string;
  sent_at?: string;
};

export type Reminder = {
  id: string;
  checklist_item_id: string;
  status: string;
  due_at?: string | null;
  created_at?: string;
  approved_at?: string | null;
  dispatched_at?: string | null;
};

export type HandoffRecord = {
  id: string;
  summary: string;
  created_at: string;
  evidence: { submission_ids: string[]; asset_ids: string[]; resource_ids: string[] };
};

export type OnboardingDetail = {
  onboarding: OnboardingSummary & { approved_scope?: string; target_date?: string; completed_at?: string; project_name?: string; portal_link?: string; connector_mode?: string };
  deal?: { approved_scope?: string; proposal_text?: string; timeline?: Record<string, string | null> };
  plan: Plan | null;
  checklist: ChecklistItem[];
  operations: ProvisioningOperation[];
  resources: ExternalResource[];
  folder_structure?: FolderStructure;
  approvals: Approval[];
  events: TimelineEvent[];
  assets: Asset[];
  submissions: Submission[];
  welcome: WelcomeEntry[];
  reminders?: Reminder[];
  handoff: HandoffRecord | null;
};

export type ClientOnboarding = {
  onboarding: Omit<OnboardingSummary, 'created_at'>;
  checklist: ChecklistItem[];
  assets: Asset[];
  submissions: Submission[];
  next_actions: ChecklistItem[];
};

const onboardingPath = (id: string) => `/onboardings/${encodeURIComponent(id)}`;

export const api = {
  health: () => request<Health>('/health'),
  me: () => request<AuthSession>('/auth/me'),
  login: (email: string, password: string) => request<AuthSession>('/auth/login', { method: 'POST', body: { email, password } }),
  logout: (csrfToken: string) => request<{ ok?: boolean }>('/auth/logout', { method: 'POST', csrfToken }),
  onboardings: async () => {
    const result = await request<{ items: OnboardingSummary[] } | OnboardingSummary[]>('/onboardings');
    return Array.isArray(result) ? result : result.items;
  },
  detail: (id: string) => request<OnboardingDetail>(onboardingPath(id)),
  decidePlan: (id: string, csrfToken: string, planRevisionId: string, proposalHash: string, decision: 'approve' | 'reject', reason?: string) =>
    request<unknown>(`${onboardingPath(id)}/approval`, { method: 'POST', csrfToken, body: { plan_revision_id: planRevisionId, proposal_hash: proposalHash, decision, reason } }),
  recover: (id: string, csrfToken: string, operationId: string, decision: 'retry' | 'reconcile' | 'compensate', externalId?: string, confirmedAbsent = false, todoListId?: string) =>
    request<unknown>(`${onboardingPath(id)}/recover`, { method: 'POST', csrfToken, body: { operation_id: operationId, decision, external_id: externalId, confirmed_absent: confirmedAbsent, todo_list_id: todoListId } }),
  handoff: (id: string, csrfToken: string, summary: string) =>
    request<unknown>(`${onboardingPath(id)}/handoff`, { method: 'POST', csrfToken, body: { summary } }),
  editChecklist: (id: string, itemId: string, csrfToken: string, dueAt: string | null, ownerName: string | null) =>
    request<unknown>(`${onboardingPath(id)}/checklist/${encodeURIComponent(itemId)}`, { method: 'PATCH', csrfToken, body: { due_at: dueAt, owner_name: ownerName } }),
  changeState: (id: string, csrfToken: string, action: 'pause' | 'resume', reason?: string) =>
    request<unknown>(`${onboardingPath(id)}/state`, { method: 'POST', csrfToken, body: { action, reason } }),
  decideReminder: (reminderId: string, csrfToken: string, decision: 'approve' | 'reject') =>
    request<unknown>(`/reminders/${encodeURIComponent(reminderId)}/approval`, { method: 'POST', csrfToken, body: { decision } }),
  exchangeClientToken: (portalToken: string) => request<{ token: string; expires_at: string }>('/client/exchange', { method: 'POST', body: { portal_token: portalToken } }),
  clientOnboarding: (clientToken: string) => request<ClientOnboarding>('/client/onboarding', { clientToken }),
  clientSubmit: (clientToken: string, answers: { checklist_item_id: string; value: string }[]) =>
    request<unknown>('/client/submissions', { method: 'POST', clientToken, body: { answers } }),
  clientUpload: (clientToken: string, file: File, checklistItemId: string) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('checklist_item_id', checklistItemId);
    return request<unknown>('/client/assets', { method: 'POST', clientToken, formData });
  },
};
