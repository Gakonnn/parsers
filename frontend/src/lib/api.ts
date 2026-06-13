import type {
  AuthResponse,
  AuditLog,
  Invoice,
  ListResponse,
  NotificationList,
  ParserJob,
  ParserJobLive,
  ParserResult,
  ParserSource,
  SubscriptionPlan,
  OlxCategoriesTree,
  TwoGisCitiesTree,
  TwoGisRubricsTree,
  UsageSummary,
  User,
  PaymentProviderInfo,
  UserSubscription,
  UserProfileUpdateRequest,
  ChangePasswordRequest,
} from "./types";

const TOKEN_KEY = "parsers_platform_token";

function browserApiFallback(): string {
  if (typeof window === "undefined") return "http://backend:8000/api/v1";
  return `${window.location.protocol}//${window.location.hostname}:8000/api/v1`;
}

export function apiBase(): string {
  return (process.env.NEXT_PUBLIC_API_URL || browserApiFallback()).replace(/\/$/, "");
}

export function getToken(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(TOKEN_KEY) || "";
}

export function setToken(token: string): void {
  if (typeof window !== "undefined") window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  if (typeof window !== "undefined") window.localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function humanizeApiError(message: string, status: number): string {
  if (message === "Incorrect email or password") return "Неверный email или пароль.";
  if (message === "User with this email already exists") return "Пользователь с таким email уже зарегистрирован.";
  if (message === "User account is disabled") return "Аккаунт отключен. Обратитесь к администратору.";
  if (message === "Failed to fetch") return "Не удалось подключиться к API. Проверьте, что backend запущен и доступен.";
  if (status === 0) return "Не удалось подключиться к API. Проверьте адрес backend.";
  return message || "Произошла ошибка запроса.";
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`${apiBase()}${path}`, { ...init, headers, cache: "no-store" });
  } catch (error) {
    throw new ApiError(humanizeApiError(error instanceof Error ? error.message : "", 0), 0);
  }
  const contentType = response.headers.get("content-type") || "";
  const raw = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = typeof raw === "object" && raw && "detail" in raw ? String(raw.detail) : String(raw || response.statusText);
    throw new ApiError(humanizeApiError(detail, response.status), response.status);
  }
  return raw as T;
}

export const api = {
  login: (email: string, password: string) =>
    apiRequest<AuthResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  register: (email: string, password: string, fullName: string) =>
    apiRequest<AuthResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, full_name: fullName || null }),
    }),
  me: () => apiRequest<User>("/users/me"),
  updateMe: (payload: UserProfileUpdateRequest) =>
    apiRequest<User>("/users/me", {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  changePassword: (payload: ChangePasswordRequest) =>
    apiRequest<{ ok: boolean }>("/users/me/password", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  jobs: (allUsers = false) => apiRequest<ListResponse<ParserJob>>(`/jobs?limit=80&all_users=${allUsers ? "true" : "false"}`),
  job: (jobId: string) => apiRequest<ParserJob>(`/jobs/${jobId}`),
  jobLive: (jobId: string) => apiRequest<ParserJobLive>(`/jobs/${jobId}/live`),
  stopJob: (jobId: string) => apiRequest<ParserJobLive>(`/jobs/${jobId}/stop`, { method: "POST" }),
  retryJob: (jobId: string) => apiRequest<ParserJob>(`/jobs/${jobId}/retry`, { method: "POST" }),
  createJob: (source: ParserSource, parameters: Record<string, unknown>, progressTotal: number) =>
    apiRequest<ParserJob>("/jobs", {
      method: "POST",
      body: JSON.stringify({ source, parameters, progress_total: progressTotal }),
    }),
  notifications: () => apiRequest<NotificationList>("/notifications?limit=80"),
  markNotificationsRead: () => apiRequest<{ updated: number }>("/notifications/read-all", { method: "POST" }),
  usage: () => apiRequest<UsageSummary>("/billing/me"),
  paymentProvider: () => apiRequest<PaymentProviderInfo>("/billing/provider"),
  plans: () => apiRequest<SubscriptionPlan[]>("/billing/plans"),
  invoices: () => apiRequest<ListResponse<Invoice>>("/billing/invoices?limit=30"),
  createInvoice: (planCode: string, provider = "kaspi_qr") =>
    apiRequest<Invoice>("/billing/invoices", {
      method: "POST",
      body: JSON.stringify({ plan_code: planCode, provider }),
    }),
  syncKaspiInvoice: (invoiceId: string) =>
    apiRequest<Invoice>(`/billing/invoices/${invoiceId}/kaspi/status`, { method: "POST" }),
  results: (source = "", allUsers = false) =>
    apiRequest<ListResponse<ParserResult> & { limit: number; offset: number }>(
      `/results?limit=80&all_users=${allUsers ? "true" : "false"}${source ? `&source=${encodeURIComponent(source)}` : ""}`,
    ),
  resultFields: (source = "", allUsers = false) =>
    apiRequest<{ fields: string[] }>(
      `/results/fields?all_users=${allUsers ? "true" : "false"}${source ? `&source=${encodeURIComponent(source)}` : ""}`,
    ),
  olxCategories: () => apiRequest<OlxCategoriesTree>("/parser-meta/olx/categories"),
  twoGisRubrics: () => apiRequest<TwoGisRubricsTree>("/parser-meta/2gis/rubrics"),
  twoGisCities: () => apiRequest<TwoGisCitiesTree>("/parser-meta/2gis/cities"),
  adminUsers: () => apiRequest<ListResponse<User>>("/admin/users?limit=30"),
  adminUpdateUser: (userId: string, payload: Partial<Pick<User, "full_name" | "role" | "is_active" | "is_verified">>) =>
    apiRequest<User>(`/admin/users/${userId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  adminAudit: () => apiRequest<ListResponse<AuditLog>>("/admin/audit-logs?limit=40"),
  adminPlans: () => apiRequest<SubscriptionPlan[]>("/billing/admin/plans"),
  adminCreatePlan: (payload: {
    code: string;
    name: string;
    description?: string | null;
    price_kzt: number;
    currency: string;
    billing_period: string;
    max_jobs_per_month: number;
    max_records_per_month: number;
    allowed_sources: string[];
    is_active: boolean;
    is_public: boolean;
  }) =>
    apiRequest<SubscriptionPlan>("/billing/admin/plans", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  adminUpdatePlan: (planId: string, payload: Partial<SubscriptionPlan>) =>
    apiRequest<SubscriptionPlan>(`/billing/admin/plans/${planId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  adminAssignSubscription: (userId: string, planCode: string) =>
    apiRequest<UserSubscription>(`/billing/admin/users/${userId}/subscription`, {
      method: "POST",
      body: JSON.stringify({ plan_code: planCode }),
    }),
  adminInvoices: () => apiRequest<ListResponse<Invoice>>("/billing/admin/invoices?limit=20"),
  adminMarkInvoicePaid: (invoiceId: string) =>
    apiRequest<unknown>(`/billing/admin/invoices/${invoiceId}/mark-paid`, { method: "POST" }),
};

export async function downloadResults(format: "csv" | "xlsx" | "json", source = "", allUsers = false, adservlet = false): Promise<void> {
  const token = getToken();
  const query = new URLSearchParams({ format, all_users: allUsers ? "true" : "false" });
  if (source) query.set("source", source);
  if (adservlet) query.set("adservlet", "true");
  const response = await fetch(`${apiBase()}/results/export?${query.toString()}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) throw new ApiError(await response.text(), response.status);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = adservlet ? `parser-results-adservlet.${format}` : `parser-results.${format}`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
