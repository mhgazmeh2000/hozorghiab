import type {
  AttendanceLog,
  AuditEntry,
  DashboardStats,
  Device,
  DeviceDetail,
  DeviceUser,
  DiscoveryResult,
  DiscoveryJob,
  ImportPreview,
  Me,
  Network,
  Paged,
  RawDataItem,
  Setting,
  SyncJob,
  TokenResponse,
} from "./types";

const TOKEN_KEY = "fa_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T>(
  path: string,
  init: RequestInit = {},
  auth = true
): Promise<T> {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
  if (!(init.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  if (auth) {
    const t = getToken();
    if (t) headers["Authorization"] = `Bearer ${t}`;
  }
  const resp = await fetch(path, { ...init, headers });
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (body.detail) detail = JSON.stringify(body.detail);
    } catch {
      /* noop */
    }
    if (resp.status === 401) {
      setToken(null);
      if (!path.includes("/auth/login") && window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
    }
    throw new ApiError(resp.status, detail);
  }
  return resp.json() as Promise<T>;
}

export const apiClient = {
  // auth
  login: (username: string, password: string) =>
    api<TokenResponse>("/api/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }, false),
  me: () => api<Me>("/api/auth/me"),
  logout: () => api<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),
  changePassword: (current_password: string, new_password: string) =>
    api("/api/auth/change-password", { method: "POST", body: JSON.stringify({ current_password, new_password }) }),

  // dashboard
  stats: () => api<DashboardStats>("/api/dashboard/stats"),
  recentAttendance: () => api<AttendanceLog[]>("/api/attendance/recent?limit=12"),

  // devices
  devices: (params: Record<string, string> = {}) => {
    const q = new URLSearchParams(params).toString();
    return api<Paged<Device>>(`/api/devices?${q}`);
  },
  device: (id: string) => api<DeviceDetail>(`/api/devices/${id}`),
  createDevice: (body: Record<string, unknown>) =>
    api<Device>("/api/devices", { method: "POST", body: JSON.stringify(body) }),
  updateDevice: (id: string, body: Record<string, unknown>) =>
    api<Device>(`/api/devices/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteDevice: (id: string) =>
    api(`/api/devices/${id}?confirm=true`, { method: "DELETE" }),
  testDevice: (id: string) => api(`/api/devices/${id}/test`, { method: "POST" }),
  discoverDevice: (id: string) => api<{ job_id: string }>(`/api/devices/${id}/discover`, { method: "POST" }),
  refreshDeviceInfo: (id: string) => api(`/api/devices/${id}/refresh-info`, { method: "POST" }),
  syncDevice: (id: string, direction: string, scope = "full") =>
    api<{ job_id: string }>(`/api/devices/${id}/sync`, {
      method: "POST",
      body: JSON.stringify({ direction, scope }),
    }),
  deviceCredentials: (id: string) => api(`/api/devices/${id}/credentials`),
  addCredential: (id: string, body: Record<string, unknown>) =>
    api(`/api/devices/${id}/credentials`, { method: "POST", body: JSON.stringify(body) }),
  deleteCredential: (did: string, cid: string) =>
    api(`/api/devices/${did}/credentials/${cid}`, { method: "DELETE" }),
  deviceLogs: (id: string) => api(`/api/devices/${id}/logs?limit=100`),
  rawData: (id: string) => api<RawDataItem[]>(`/api/devices/${id}/raw-data`),

  // device users
  deviceUsers: (id: string, params: Record<string, string> = {}) => {
    const q = new URLSearchParams(params).toString();
    return api<Paged<DeviceUser>>(`/api/devices/${id}/users?${q}`);
  },
  createDeviceUser: (id: string, body: Record<string, unknown>) =>
    api(`/api/devices/${id}/users`, { method: "POST", body: JSON.stringify(body) }),
  updateDeviceUser: (did: string, uid: string, body: Record<string, unknown>) =>
    api(`/api/devices/${did}/users/${uid}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteDeviceUser: (did: string, uid: string) =>
    api(`/api/devices/${did}/users/${uid}?confirm=true`, { method: "DELETE" }),
  syncUsersFromDevice: (id: string) =>
    api(`/api/devices/${id}/users/sync-from-device`, { method: "POST" }),
  syncUsersToDevice: (id: string) =>
    api(`/api/devices/${id}/users/sync-to-device`, { method: "POST" }),

  // attendance
  attendance: (params: Record<string, string> = {}) => {
    const q = new URLSearchParams(params).toString();
    return api<Paged<AttendanceLog>>(`/api/attendance?${q}`);
  },
  deviceAttendance: (id: string, params: Record<string, string> = {}) => {
    const q = new URLSearchParams(params).toString();
    return api<Paged<AttendanceLog>>(`/api/devices/${id}/attendance?${q}`);
  },
  pullAttendance: (id: string) => api(`/api/devices/${id}/attendance/pull`, { method: "POST" }),
  clearAttendance: (id: string) =>
    api(`/api/devices/${id}/attendance/clear?confirm=true`, { method: "POST" }),

  // networks + jobs
  networks: () => api<Network[]>("/api/networks"),
  discoveryResults: () => api<DiscoveryResult[]>("/api/networks/discovery/results?limit=60"),
  createNetwork: (body: Record<string, unknown>) =>
    api<Network>("/api/networks", { method: "POST", body: JSON.stringify(body) }),
  updateNetwork: (id: string, body: Record<string, unknown>) =>
    api<Network>(`/api/networks/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteNetwork: (id: string) => api(`/api/networks/${id}`, { method: "DELETE" }),
  scanNetwork: (id: string) => api<DiscoveryJob>(`/api/networks/${id}/scan`, { method: "POST" }),
  discoveryJobs: () => api<DiscoveryJob[]>("/api/networks/discovery/jobs?limit=40"),
  deleteDiscoveryJobs: () => api("/api/networks/discovery/jobs", { method: "DELETE" }),
  discoveryJob: (id: string) => api<DiscoveryJob>(`/api/networks/discovery/jobs/${id}`),
  cancelDiscoveryJob: (id: string) =>
    api(`/api/networks/discovery/jobs/${id}/cancel`, { method: "POST" }),
  deleteDiscoveryResults: () => api("/api/networks/discovery/results", { method: "DELETE" }),
  syncJobs: (deviceId?: string) =>
    api<SyncJob[]>(`/api/devices/sync/jobs?${deviceId ? `device_id=${deviceId}` : ""}`),

  // audit + settings + system users
  audit: (params: Record<string, string> = {}) => {
    const q = new URLSearchParams(params).toString();
    return api<Paged<AuditEntry>>(`/api/audit?${q}`);
  },
  settings: () => api<Setting[]>("/api/settings"),
  updateSetting: (key: string, value: unknown) =>
    api<Setting>(`/api/settings/${key}`, { method: "PUT", body: JSON.stringify({ value }) }),
  systemUsers: () => api("/api/system/users"),
  createSystemUser: (body: Record<string, unknown>) =>
    api("/api/system/users", { method: "POST", body: JSON.stringify(body) }),
  updateSystemUser: (id: string, body: Record<string, unknown>) =>
    api(`/api/system/users/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
};

// file download helper with auth header
export async function download(path: string, filename: string) {
  const resp = await fetch(path, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!resp.ok) throw new ApiError(resp.status, "export failed");
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export async function uploadPreview(path: string, file: File): Promise<ImportPreview> {
  const fd = new FormData();
  fd.append("file", file);
  return api<ImportPreview>(path, { method: "POST", body: fd });
}

export async function uploadApply(path: string, file: File, deviceId?: string): Promise<{ applied: number }> {
  const fd = new FormData();
  fd.append("file", file);
  const suffix = deviceId ? `?device_id=${deviceId}` : "";
  return api<{ applied: number }>(`${path}${suffix}`, { method: "POST", body: fd });
}
