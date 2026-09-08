// Mirror of backend Pydantic schemas (app/schemas/schemas.py)

export interface Me {
  id: string;
  username: string;
  display_name?: string | null;
  role: "admin" | "operator" | "viewer";
  must_change_password: boolean;
}

export interface TokenResponse {
  access_token: string;
  role: string;
  username: string;
  display_name?: string | null;
}

export interface Network {
  id: string;
  cidr: string;
  label?: string | null;
  enabled: boolean;
  is_default: boolean;
  is_single_ip: boolean;
  exclude_ips: unknown[];
  last_scan_at?: string | null;
  created_at: string;
}

export interface Capability {
  capability: string;
  supported: boolean;
  verified: boolean;
  source?: string | null;
  reason?: string | null;
}

export interface ProtocolInfo {
  port: number;
  transport: string;
  service?: string | null;
  protocol?: string | null;
  state: string;
  confidence: number;
  source?: string | null;
  banner?: string | null;
  http_headers: Record<string, unknown>;
  title?: string | null;
  first_seen_at?: string | null;
  last_seen_at?: string | null;
}

export interface Device {
  id: string;
  ip_address: string;
  hostname?: string | null;
  mac_address?: string | null;
  brand?: string | null;
  model?: string | null;
  serial_number?: string | null;
  firmware_version?: string | null;
  platform?: string | null;
  device_name?: string | null;
  vendor?: string | null;
  status: string;
  detection_state: string;
  confidence: number;
  protocol_name?: string | null;
  adapter_name?: string | null;
  port?: number | null;
  is_attendance_candidate: boolean;
  is_manual: boolean;
  last_seen_at?: string | null;
  last_online_at?: string | null;
  last_sync_at?: string | null;
  last_sync_status?: string | null;
  last_error?: string | null;
  auto_sync_enabled: boolean;
  sync_interval_min?: number | null;
  verified_at?: string | null;
  created_at: string;
}

export interface DeviceDetail extends Device {
  detection_evidence: unknown[];
  extra_config: Record<string, unknown>;
  capabilities: Capability[];
  protocols: ProtocolInfo[];
  user_count?: number | null;
  attendance_count?: number | null;
  device_time?: string | null;
}

export interface DeviceUser {
  id: string;
  device_id: string;
  user_id_on_device: string;
  device_user_sn?: number | null;
  employee_code?: string | null;
  name?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  card_number?: string | null;
  password_status?: string | null;
  role?: string | null;
  department?: string | null;
  privilege_level?: number | null;
  group_number?: number | null;
  enabled: boolean;
  fingerprint_count?: number | null;
  face_enabled: boolean;
  card_enabled: boolean;
  password_enabled: boolean;
  verification_mode?: string | null;
  status?: string | null;
  last_sync_at?: string | null;
}

export interface AttendanceLog {
  id: string;
  device_id: string;
  user_id_on_device?: string | null;
  user_sn?: number | null;
  employee_code?: string | null;
  event_time: string;
  raw_state?: string | null;
  raw_punch?: string | null;
  event_type: string;
  verification_type: string;
  status?: string | null;
  work_code?: number | null;
  door_id?: string | null;
  source: string;
  created_at: string;
  device_ip?: string | null;
}

export interface Paged<T> {
  total: number;
  page: number;
  page_size: number;
  items: T[];
}

export interface DiscoveryJob {
  id: string;
  kind: string;
  target: string;
  requested_by?: string | null;
  status: string;
  stage?: string | null;
  progress: number;
  total_hosts: number;
  scanned_hosts: number;
  found_hosts: number;
  errors: number;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
  summary: Record<string, unknown>;
  created_at: string;
}

export interface SyncJob {
  id: string;
  device_id: string;
  direction: string;
  scope: string;
  requested_by?: string | null;
  status: string;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
  stats: Record<string, unknown>;
  created_at: string;
}

export interface DiscoveryResult {
  id: string;
  ip_address: string;
  reachable: boolean;
  open_ports: number[];
  hostname?: string | null;
  detection_state: string;
  confidence: number;
  source?: string | null;
  evidence: Record<string, unknown>;
  probed_at: string;
}

export interface AuditEntry {
  id: string;
  created_at: string;
  username?: string | null;
  action: string;
  device_id?: string | null;
  device_ip?: string | null;
  result: string;
  error?: string | null;
  duration_ms?: number | null;
  source_ip?: string | null;
  details: Record<string, unknown>;
}

export interface DashboardStats {
  total_devices: number;
  online_devices: number;
  offline_devices: number;
  unknown_devices: number;
  verified_devices: number;
  attendance_candidates: number;
  total_users: number;
  today_attendance: number;
  last_sync_at?: string | null;
  failed_operations_24h: number;
  networks_count: number;
  pending_jobs: number;
}

export interface ImportPreview {
  entity: string;
  total_rows: number;
  valid_rows: number;
  issue_rows: number;
  duplicate_rows: number;
  preview: Record<string, unknown>[];
  issues: { row: number; error: string; data: Record<string, unknown> }[];
  read_errors: string[];
}

export interface Setting {
  key: string;
  value: unknown;
  description?: string | null;
}

export interface RawDataItem {
  id: string;
  category: string;
  source?: string | null;
  payload?: string | null;
  meta: Record<string, unknown>;
  captured_at: string;
}
