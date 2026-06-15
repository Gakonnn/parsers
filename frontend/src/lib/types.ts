export type UserRole = "user" | "admin";
export type ParserSource = "olx" | "krisha" | "2gis" | "kolesa";
export type JobStatus = "pending" | "running" | "completed" | "failed" | "cancelled";

export type User = {
  id: string;
  email: string;
  full_name?: string | null;
  role: UserRole | string;
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
  updated_at?: string | null;
};

export type AuthResponse = {
  access_token: string;
  token_type: string;
  user: User;
};

export type EmailCodeResponse = {
  ok: boolean;
  email: string;
  expires_in_minutes: number;
};

export type ParserJob = {
  id: string;
  user_id: string;
  source: ParserSource | string;
  status: JobStatus | string;
  parameters: Record<string, unknown>;
  progress_current: number;
  progress_total: number;
  celery_task_id?: string | null;
  runner_job_id?: string | null;
  db_run_id?: string | null;
  result_path?: string | null;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  finished_at?: string | null;
};

export type RunnerSnapshot = {
  job_id?: string;
  parser_key?: string;
  status?: string;
  return_code?: number | null;
  command?: string[];
  cwd?: string;
  output_path?: string;
  created_at?: string;
  started_at?: string | null;
  finished_at?: string | null;
  stop_requested?: boolean;
  log?: string;
  error?: string;
  progress?: {
    current?: number;
    total?: number;
    percent?: number;
    label?: string;
    indeterminate?: boolean;
    source?: string;
  };
};

export type ParserJobLive = {
  job: ParserJob;
  runner: RunnerSnapshot | null;
};

export type ListResponse<T> = {
  items: T[];
  total: number;
};

export type SubscriptionPlan = {
  id: string;
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
};

export type UserSubscription = {
  id: string;
  user_id: string;
  plan_id: string;
  status: string;
  starts_at: string;
  ends_at?: string | null;
  plan: SubscriptionPlan;
};

export type UsageSummary = {
  subscription: UserSubscription;
  jobs_used: number;
  records_used: number;
  jobs_remaining: number;
  records_remaining: number;
  month_started_at: string;
};

export type Invoice = {
  id: string;
  user_id: string;
  plan_id: string;
  status: string;
  amount_kzt: number;
  currency: string;
  provider: string;
  provider_invoice_id?: string | null;
  payment_url?: string | null;
  metadata_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  paid_at?: string | null;
  expires_at?: string | null;
  plan: SubscriptionPlan;
};

export type NotificationItem = {
  id: string;
  user_id: string;
  channel: string;
  type: string;
  title: string;
  body?: string | null;
  payload: Record<string, unknown>;
  is_read: boolean;
  created_at: string;
  read_at?: string | null;
};

export type NotificationList = ListResponse<NotificationItem> & {
  unread_total: number;
};

export type ParserResult = {
  id: number;
  job_id: string;
  run_id: string;
  source: string;
  external_id: string;
  payload: Record<string, unknown>;
  created_at: string;
  run_status?: string | null;
};

export type AuditLog = {
  id: string;
  actor_user_id?: string | null;
  target_user_id?: string | null;
  event_type: string;
  entity_type?: string | null;
  entity_id?: string | null;
  ip_address?: string | null;
  user_agent?: string | null;
  message?: string | null;
  payload: Record<string, unknown>;
  created_at: string;
};

export type SupportMessage = {
  id: string;
  name: string;
  email: string;
  phone?: string | null;
  message: string;
  status: "new" | "in_progress" | "closed" | string;
  source: string;
  created_at: string;
  updated_at: string;
};

export type PaymentProviderInfo = {
  provider_name: string;
  checkout_mode: string;
  checkout_url_template?: string | null;
  success_url?: string | null;
  cancel_url?: string | null;
  webhook_secret_configured: boolean;
  kaspi_qr_enabled: boolean;
  kaspi_pos_base_url?: string | null;
};

export type UserProfileUpdateRequest = {
  full_name?: string | null;
};

export type ChangePasswordRequest = {
  current_password: string;
  new_password: string;
};

export type OlxCategoryNode = {
  slug: string;
  name: string;
  url: string;
  level2?: OlxCategoryNode[];
  level3?: OlxCategoryNode[];
};

export type OlxCategoriesTree = {
  level1: OlxCategoryNode[];
  stats?: Record<string, number>;
  updated_at?: string;
};

export type TwoGisRubricLevel2 = {
  name: string;
  rubrics: string[];
};

export type TwoGisRubricLevel1 = {
  name: string;
  level2: TwoGisRubricLevel2[];
};

export type TwoGisRubricsTree = {
  level1: TwoGisRubricLevel1[];
  stats?: Record<string, number>;
  updated_at?: string;
};

export type TwoGisCity = {
  name: string;
  code: string;
  domain: string;
  country_code?: string;
};

export type TwoGisCitiesTree = {
  cities: TwoGisCity[];
  domains: string[];
  stats?: Record<string, number>;
  updated_at?: string;
};
