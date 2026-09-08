import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { apiClient } from "../api/client";
import type { AuditEntry } from "../api/types";
import { DataTable, Empty, Pagination, RawBadge, Spinner, toast } from "../components/ui";
import { ACTION_LABEL, fmtTime, faNum } from "../lib/fa";

const ACTIONS = [
  "login", "logout", "scan", "discovery", "connect", "sync", "user_import", "user_export",
  "user_create", "user_update", "user_delete", "attendance_import", "attendance_export",
  "attendance_clear", "device_config", "network_config", "settings_update", "password_change",
];

export default function Audit() {
  const [items, setItems] = useState<AuditEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState("");
  const [result, setResult] = useState("");
  const [username, setUsername] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p: Record<string, string> = { page: String(page), page_size: "50" };
      if (action) p.action = action;
      if (result) p.result = result;
      if (username) p.username = username;
      const r = await apiClient.audit(p);
      setItems(r.items);
      setTotal(r.total);
    } catch (e) {
      toast(String((e as Error).message), "err");
    } finally {
      setLoading(false);
    }
  }, [page, action, result, username]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">لاگ عملیات (Audit)</h1>
          <div className="page-sub">ثبت کامل همه عملیات مهم: ورود، اسکن، کشف، همگام‌سازی، درون‌ریزی/برون‌بری و…</div>
        </div>
      </div>

      <div className="filter-group">
        <Field label="عملیات">
          <select value={action} onChange={(e) => { setAction(e.target.value); setPage(1); }}>
            <option value="">همه</option>
            {ACTIONS.map((a) => (
              <option key={a} value={a}>
                {ACTION_LABEL[a] || a}
              </option>
            ))}
          </select>
        </Field>
        <Field label="نتیجه">
          <select value={result} onChange={(e) => { setResult(e.target.value); setPage(1); }}>
            <option value="">همه</option>
            <option value="success">موفق</option>
            <option value="error">خطا</option>
          </select>
        </Field>
        <Field label="کاربر">
          <input value={username} onChange={(e) => { setUsername(e.target.value); setPage(1); }} placeholder="admin" />
        </Field>
      </div>

      <div className="card">
        <div className="card-body flush">
          {loading ? (
            <div className="page-center" style={{ height: 220 }}>
              <Spinner />
            </div>
          ) : items.length === 0 ? (
            <Empty text="لاگی ثبت نشده است" />
          ) : (
            <DataTable<AuditEntry>
              keyOf={(r) => r.id}
              columns={[
                { key: "created_at", label: "زمان", render: (r) => <span className="mono small">{fmtTime(r.created_at)}</span> },
                { key: "username", label: "کاربر", render: (r) => r.username || "سیستم" },
                { key: "action", label: "عملیات", render: (r) => <span className="chip">{ACTION_LABEL[r.action] || r.action}</span> },
                {
                  key: "device",
                  label: "دستگاه",
                  render: (r) =>
                    r.device_ip ? <span className="mono small">{r.device_ip}</span> : <span className="muted small">—</span>,
                },
                { key: "result", label: "نتیجه", render: (r) => <RawBadge value={r.result} /> },
                { key: "duration_ms", label: "مدت (ms)", render: (r) => faNum(r.duration_ms) },
                { key: "source_ip", label: "IP مبدأ", render: (r) => <span className="mono small">{r.source_ip || "—"}</span> },
                { key: "error", label: "خطا", render: (r) => <span className="small muted">{r.error ? r.error.slice(0, 90) : "—"}</span> },
              ]}
              rows={items}
            />
          )}
        </div>
        <Pagination page={page} pageSize={50} total={total} onChange={setPage} />
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
    </label>
  );
}
