export type Role =
  | "ADMIN"
  | "CEO"
  | "CFO"
  | "COLLECTIONS_MANAGER"
  | "CALLING_AGENT"
  | "COMPLIANCE_OFFICER"
  | "VIEWER"
  | "SUPERVISOR";

export interface User {
  id: string;
  username: string;
  full_name?: string | null;
  email?: string | null;
  role: Role;
  is_active: boolean;
  default_tenant_id?: string;
  must_change_password?: boolean;
  password_changed_at?: number | null;
  created_at?: number;
  last_login_at?: number | null;
}

export interface AuthMeResponse {
  user: User;
  role: Role;
  permissions: string[];
  tenant_ids?: string[];
  default_tenant_id?: string;
  session_id?: string;
  must_change_password?: boolean;
}

export interface UserSession {
  id: string;
  user_id: string;
  tenant_id: string;
  user_agent?: string | null;
  ip_addr?: string | null;
  created_at?: number;
  expires_at?: number | null;
  last_seen_at?: number | null;
  revoked_at?: number | null;
}

export interface BuildInfo {
  app: string;
  static_token: string;
  demo_mode: boolean;
  app_env?: string;
  pilot_mode: boolean;
  git_sha?: string | null;
  timestamp: number;
}

export interface ApiListResponse<T> {
  rows: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface TaskRow {
  id: string;
  campaign_id: string;
  portfolio_id?: string;
  customer_id: string;
  customer_name?: string;
  phone?: string;
  amount_due?: number;
  dpd?: number;
  ptp_date?: string;
  state: "NEW" | "IN_PROGRESS" | "PTP" | "CALLBACK" | "ESCALATED" | "CLOSED";
  disposition?: string;
  owner?: string;
  sla_due_at?: number;
  last_action_at?: number;
  updated_at?: number;
  created_at?: number;
  sla_breach?: boolean;
  aging_seconds?: number;
  compliance_block?: number;
  compliance_status_json?: string;
}

export interface TaskEvent {
  id: number;
  task_id: string;
  ts: number;
  actor: string;
  event_type: string;
  payload_json?: string;
}

export interface TaskDetail extends TaskRow {
  notes?: string;
  callback_at?: number;
  events: TaskEvent[];
}

export interface SessionSnapshot {
  session_id: string;
  customer_id?: string;
  customer_name?: string;
  phone?: string;
  dpd?: number;
  due_amount?: number;
  amount_due?: number;
  campaign_id?: string;
  strategy_mode?: string;
  tone_profile?: string;
  compliance_flags?: string[];
  disposition?: string;
  step?: string;
  current_step?: string;
  ptp_date?: string;
  callback_time?: string;
}

export interface AlertRow {
  id: string;
  ts: number;
  type: string;
  severity: string;
  status: string;
  message: string;
  payload_json?: string;
  entity_type?: string;
  entity_id?: string;
  assigned_to?: string;
  acked_at?: number;
  resolved_at?: number;
}

export interface RuleRow {
  id: string;
  name: string;
  type: string;
  enabled: number;
  threshold_json?: string;
  routing_json?: string;
}

export interface ReportRow {
  id: string;
  campaign_id: string;
  report_date: string;
  created_at: number;
}

export interface CampaignRow {
  campaign_id: string;
  name: string;
  status: string;
  total_accounts: number;
  created_at: number;
  started_at?: number;
  completed_at?: number;
}
