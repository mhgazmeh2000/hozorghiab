import { useCallback, useEffect, useState } from "react";
import { apiClient } from "../api/client";
import type { Setting } from "../api/types";
import { Field, Modal, RawBadge, Spinner, Tabs, toast } from "../components/ui";
import { fmtTime, ROLE_LABEL } from "../lib/fa";

interface SystemUserRow {
  id: string;
  username: string;
  display_name: string | null;
  role: string;
  is_active: boolean;
  must_change_password: boolean;
  last_login_at: string | null;
  created_at: string;
}

const BOOL_KEYS = [
  "scanner.enable_icmp",
  "scanner.enable_reverse_dns",
  "scheduler.enabled",
  "security.rate_limit_enabled",
  "sync.auto_approve",
];

export default function Settings({ tab: forcedTab }: { tab?: string }) {
  const [tab, setTab] = useState(forcedTab || "scan");
  useEffect(() => {
    if (forcedTab) setTab(forcedTab);
  }, [forcedTab]);

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">تنظیمات</h1>
          <div className="page-sub">پیکربندی اسکن، زمان‌بندی، امنیت و کاربران سامانه</div>
        </div>
      </div>
      <Tabs
        tabs={[
          { id: "scan", label: "اسکن و کشف" },
          { id: "scheduler", label: "زمان‌بندی" },
          { id: "security", label: "امنیت" },
          { id: "users", label: "کاربران سامانه" },
        ]}
        active={tab}
        onChange={setTab}
      />
      <div className="tab-area">
        <div className="card-body">
          {tab === "users" ? <UsersPanel /> : <SettingsPanel tab={tab} />}
        </div>
      </div>
    </div>
  );
}

function SettingsPanel({ tab }: { tab: string }) {
  const [settings, setSettings] = useState<Setting[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    apiClient
      .settings()
      .then(setSettings)
      .catch((e) => toast(String((e as Error).message), "err"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const isBool = (k: string) => BOOL_KEYS.some((b) => k.endsWith(b.split(".")[1]));

  const save = async (key: string, value: unknown) => {
    try {
      await apiClient.updateSetting(key, value);
      toast("ذخیره شد", "ok");
      void load();
    } catch (e) {
      toast(String((e as Error).message), "err");
    }
  };

  if (loading)
    return (
      <div className="page-center" style={{ height: 200 }}>
        <Spinner />
      </div>
    );

  const groups: Record<string, Setting[]> = {};
  for (const s of settings) {
    const prefix = s.key.includes(".") ? s.key.split(".")[0] : "general";
    const g = prefix === "scanner" ? "scan" : prefix === "scheduler" ? "scheduler" : prefix === "security" ? "security" : "general";
    (groups[g] = groups[g] || []).push(s);
  }
  const rows = groups[tab] || [];

  if (rows.length === 0)
    return <div className="empty">تنظیمی در این بخش تعریف نشده است</div>;

  return (
    <div className="col">
      {rows.map((s) => {
        const numeric = typeof s.value === "number";
        const bool = typeof s.value === "boolean";
        return (
          <div
            key={s.key}
            className="row between wrap"
            style={{ border: "1px solid var(--line)", borderRadius: 10, padding: "11px 14px" }}
          >
            <div className="grow">
              <b className="small mono" dir="ltr">
                {s.key}
              </b>
              <div className="muted small">{s.description || "—"}</div>
            </div>
            {bool ? (
              <label className="row gap">
                <input type="checkbox" checked={s.value as boolean} onChange={(e) => void save(s.key, e.target.checked)} />
              </label>
            ) : (
              <input
                dir="ltr"
                type={numeric ? "number" : "text"}
                value={String(s.value ?? "")}
                style={{ maxWidth: 220 }}
                onBlur={(e) => {
                  const raw = e.target.value.trim();
                  if (raw === String(s.value)) return;
                  void save(s.key, numeric ? Number(raw) : raw);
                }}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

function UsersPanel() {
  const [rows, setRows] = useState<SystemUserRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [editTarget, setEditTarget] = useState<SystemUserRow | null>(null);
  const [form, setForm] = useState({ username: "", password: "", display_name: "", role: "viewer" });
  const [pw, setPw] = useState("");

  const load = useCallback(() => {
    setLoading(true);
    apiClient
      .systemUsers()
      .then((r) => setRows(r as unknown as SystemUserRow[]))
      .catch((e) => toast(String((e as Error).message), "err"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const create = async () => {
    setBusy(true);
    try {
      await apiClient.createSystemUser(form);
      toast("کاربر سامانه ایجاد شد", "ok");
      setAddOpen(false);
      setForm({ username: "", password: "", display_name: "", role: "viewer" });
      void load();
    } catch (e) {
      toast(String((e as Error).message), "err");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div className="row between wrap" style={{ marginBottom: 14 }}>
        <p className="muted small" style={{ margin: 0 }}>
          نقش‌ها: admin (دسترسی کامل) • operator (خواندن + همگام‌سازی + درون‌ریزی) • viewer (فقط خواندن)
        </p>
        <button className="btn btn-primary btn-sm" onClick={() => setAddOpen(true)}>
          + کاربر جدید
        </button>
      </div>

      {loading ? (
        <div className="page-center" style={{ height: 160 }}>
          <Spinner />
        </div>
      ) : (
        <div className="col">
          {rows.map((u) => (
            <div
              key={u.id}
              className="row between wrap"
              style={{ border: "1px solid var(--line)", borderRadius: 10, padding: "11px 14px" }}
            >
              <div className="row gap">
                <span className="avatar">{u.username.slice(0, 2).toUpperCase()}</span>
                <div>
                  <b>{u.display_name || u.username}</b>
                  <span className="muted small"> · @{u.username}</span>
                  <div className="small muted">
                    {ROLE_LABEL[u.role] || u.role} · آخرین ورود {u.last_login_at ? fmtTime(u.last_login_at) : "—"}
                  </div>
                </div>
              </div>
              <div className="row gap">
                {u.must_change_password && <RawBadge value="تغییر رمز الزامی" custom="amber" />}
                <RawBadge value={u.is_active ? "فعال" : "غیرفعال"} custom={u.is_active ? "green" : "gray"} />
                <button
                  className="btn btn-sm"
                  onClick={() => {
                    setEditTarget(u);
                    setPw("");
                  }}
                >
                  تغییر نقش / رمز
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <Modal open={addOpen} title="کاربر جدید سامانه" onClose={() => setAddOpen(false)}>
        <div className="form-grid">
          <Field label="نام کاربری">
            <input dir="ltr" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
          </Field>
          <Field label="نام نمایشی">
            <input value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
          </Field>
          <Field label="رمز عبور (حداقل ۸ کاراکتر)">
            <input type="password" dir="ltr" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
          </Field>
          <Field label="نقش">
            <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              <option value="admin">مدیر</option>
              <option value="operator">اپراتور</option>
              <option value="viewer">بیننده</option>
            </select>
          </Field>
        </div>
        <div className="form-actions">
          <button className="btn" onClick={() => setAddOpen(false)}>
            انصراف
          </button>
          <button className="btn btn-primary" disabled={busy || !form.username || form.password.length < 8} onClick={() => void create()}>
            {busy ? <Spinner small /> : "ایجاد"}
          </button>
        </div>
      </Modal>

      <Modal open={editTarget !== null} title={`ویرایش ${editTarget?.username || ""}`} onClose={() => setEditTarget(null)}>
        <div className="form-grid">
          <Field label="نقش">
            <select
              value={editTarget?.role || "viewer"}
              onChange={(e) => setEditTarget(editTarget ? { ...editTarget, role: e.target.value } : null)}
            >
              <option value="admin">مدیر</option>
              <option value="operator">اپراتور</option>
              <option value="viewer">بیننده</option>
            </select>
          </Field>
          <Field label="رمز جدید (اختیاری)" hint="برای بازنشانی رمز مقدار دهید">
            <input type="password" dir="ltr" value={pw} onChange={(e) => setPw(e.target.value)} />
          </Field>
        </div>
        <div className="form-actions">
          <button className="btn" onClick={() => setEditTarget(null)}>
            انصراف
          </button>
          <button
            className="btn btn-primary"
            disabled={busy || !editTarget}
            onClick={async () => {
              if (!editTarget) return;
              setBusy(true);
              try {
                const body: Record<string, unknown> = { role: editTarget.role };
                if (pw) body.password = pw;
                await apiClient.updateSystemUser(editTarget.id, body);
                toast("ذخیره شد", "ok");
                setEditTarget(null);
                void load();
              } catch (e) {
                toast(String((e as Error).message), "err");
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? <Spinner small /> : "ذخیره"}
          </button>
        </div>
      </Modal>
    </div>
  );
}
