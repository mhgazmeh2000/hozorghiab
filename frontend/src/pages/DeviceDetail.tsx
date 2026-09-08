import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiClient, download } from "../api/client";
import type {
  AttendanceLog,
  AuditEntry,
  Capability,
  DeviceDetail,
  DeviceUser,
  ProtocolInfo,
  RawDataItem,
  SyncJob,
} from "../api/types";
import {
  Badge,
  Confirm,
  DataTable,
  Empty,
  Field,
  JsonView,
  Modal,
  Pagination,
  RawBadge,
  Spinner,
  Tabs,
  toast,
} from "../components/ui";
import { CAP_LABEL, EVENT_TYPE_LABEL, faNum, fmtTime, fmtTimeOnly, VERIFY_LABEL } from "../lib/fa";

type Cred = { id: string; kind: string; username: string | null; secret_masked: string | null; note: string | null };

const TABS = [
  { id: "overview", label: "نمای کلی" },
  { id: "users", label: "کاربران دستگاه" },
  { id: "attendance", label: "ترددها" },
  { id: "capabilities", label: "قابلیت‌ها" },
  { id: "network", label: "شبکه و پروتکل" },
  { id: "raw", label: "داده خام" },
  { id: "logs", label: "لاگ عملیات" },
  { id: "sync", label: "همگام‌سازی" },
  { id: "settings", label: "تنظیمات" },
];

export default function DeviceDetail() {
  const { id } = useParams();
  const [dev, setDev] = useState<DeviceDetail | null>(null);
  const [tab, setTab] = useState("overview");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const d = await apiClient.device(id);
      setDev(d);
    } catch (e) {
      toast(String((e as Error).message), "err");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    setLoading(true);
    void load();
  }, [load]);

  if (loading)
    return (
      <div className="page-center">
        <Spinner />
      </div>
    );
  if (!dev)
    return (
      <div className="card">
        <div className="card-body">
          <Empty text="دستگاه یافت نشد" />
        </div>
      </div>
    );

  return (
    <div>
      <div className="page-head">
        <div>
          <Link to="/devices" className="muted small">
            → بازگشت به فهرست دستگاه‌ها
          </Link>
          <h1 className="page-title">
            <span className="mono">{dev.ip_address}</span>
            <RawBadge value={dev.status} />
            <Badge value={dev.detection_state} />
          </h1>
          <div className="page-sub">
            {(dev.brand || dev.vendor || "برند نامشخص") + (dev.model ? ` — ${dev.model}` : "")}
            {" · "}
            اطمینان {faNum(Math.round(dev.confidence * 100))}٪
            {" · "}
            {dev.adapter_name || "بدون آداپتور"}
          </div>
        </div>
      </div>

      <Tabs tabs={TABS} active={tab} onChange={setTab} />
      <div className="tab-area">
        {tab === "overview" && <Overview dev={dev} onChanged={() => void load()} />}
        {tab === "users" && <UsersTab deviceId={dev.id} />}
        {tab === "attendance" && <AttendanceTab deviceId={dev.id} />}
        {tab === "capabilities" && <CapsTab caps={dev.capabilities} />}
        {tab === "network" && <NetworkTab protocols={dev.protocols} evidence={dev.detection_evidence} />}
        {tab === "raw" && <RawTab deviceId={dev.id} />}
        {tab === "logs" && <LogsTab deviceId={dev.id} />}
        {tab === "sync" && <SyncTab device={dev} onChanged={() => void load()} />}
        {tab === "settings" && <SettingsTab device={dev} onChanged={() => void load()} />}
      </div>
    </div>
  );
}

/* ---------- overview ---------- */

function Overview({ dev, onChanged }: { dev: DeviceDetail; onChanged: () => void }) {
  const [busy, setBusy] = useState("");
  const counts = (dev.extra_config.counts || {}) as Record<string, number | null | undefined>;
  const attendanceUsed = counts.attendance_count;
  const attendanceCapacity = counts.attendance_capacity;
  const attendanceFree = counts.attendance_free;
  const attendanceUsage = attendanceUsed != null && attendanceCapacity ? `${Math.round((attendanceUsed / attendanceCapacity) * 10000) / 100}%` : "UNKNOWN";

  const act = async (action: string, fn: () => Promise<unknown>, okMsg: string) => {
    setBusy(action);
    try {
      await fn();
      toast(okMsg, "ok");
      onChanged();
    } catch (e) {
      toast(String((e as Error).message), "err");
    } finally {
      setBusy("");
    }
  };

  const rows: [string, string][] = [
    ["آدرس IP", dev.ip_address],
    ["نام میزبان", dev.hostname || "—"],
    ["برند", dev.brand || dev.vendor || "—"],
    ["مدل", dev.model || "—"],
    ["سریال", dev.serial_number || "—"],
    ["فرم‌افزار", dev.firmware_version || "—"],
    ["پلتفرم", dev.platform || "—"],
    ["نام دستگاه", dev.device_name || "—"],
    ["آداپتور", dev.adapter_name || "—"],
    ["پروتکل", dev.protocol_name || "—"],
    ["پورت", dev.port ? String(dev.port) : "—"],
    ["آخرین حضور", fmtTime(dev.last_seen_at)],
    ["آخرین آنلاین", fmtTime(dev.last_online_at)],
    ["ساعت دستگاه", fmtTime(dev.device_time)],
    ["آخرین همگام‌سازی", fmtTime(dev.last_sync_at)],
    ["وضعیت آخرین همگام‌سازی", dev.last_sync_status || "—"],
    ["تأییدشده در", fmtTime(dev.verified_at)],
    ["اضافه‌شده دستی", dev.is_manual ? "بله" : "خیر"],
    ["نامزد دستگاه تردد", dev.is_attendance_candidate ? "بله" : "خیر"],
    ["کاربران", dev.user_count != null ? faNum(dev.user_count) : "—"],
    ["ترددها", dev.attendance_count != null ? faNum(dev.attendance_count) : "—"],
    ["ذخیره‌سازی تردد", attendanceUsed != null && attendanceCapacity ? `${faNum(attendanceUsed)} / ${faNum(attendanceCapacity)} (${attendanceUsage})` : "UNKNOWN"],
    ["تردد آزاد", attendanceFree != null ? faNum(attendanceFree) : "UNKNOWN"],
    ["MAC", dev.mac_address || "—"],
  ];

  return (
    <div className="card-body">
      {dev.last_error ? (
        <div className="banner banner-red" style={{ marginBottom: 14 }}>
          آخرین خطا: {dev.last_error}
        </div>
      ) : null}
      <div className="row wrap gap" style={{ marginBottom: 16 }}>
        <button className="btn btn-soft" disabled={!!busy} onClick={() => act("test", () => apiClient.testDevice(dev.id), "تست اتصال انجام شد")}>
          {busy === "test" ? <Spinner small /> : "🔌 تست اتصال"}
        </button>
        <button className="btn" disabled={!!busy} onClick={() => act("discover", () => apiClient.discoverDevice(dev.id), "کار کشف در پس‌زمینه آغاز شد")}>
          {busy === "discover" ? <Spinner small /> : "🔍 کشف / شناسایی"}
        </button>
        <button className="btn" disabled={!!busy} onClick={() => act("refresh", () => apiClient.refreshDeviceInfo(dev.id), "اطلاعات دستگاه به‌روزرسانی شد")}>
          {busy === "refresh" ? <Spinner small /> : "🔄 خواندن اطلاعات دستگاه"}
        </button>
        <button className="btn btn-primary" disabled={!!busy} onClick={() => act("pull", () => apiClient.pullAttendance(dev.id), "دریافت تردد آغاز شد")}>
          {busy === "pull" ? <Spinner small /> : "⇣ دریافت تردد"}
        </button>
      </div>

      <div className="kv">
        {rows.map(([k, v]) => (
          <div className="kv-item" key={k}>
            <span className="kv-key">{k}</span>
            <span className={`kv-val${k === "آدرس IP" || k === "سریال" || k === "MAC" ? " mono" : ""}`}>{v}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---------- users ---------- */

function UsersTab({ deviceId }: { deviceId: string }) {
  const [items, setItems] = useState<DeviceUser[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p: Record<string, string> = { page: String(page), page_size: "25" };
      if (search) p.search = search;
      const r = await apiClient.deviceUsers(deviceId, p);
      setItems(r.items);
      setTotal(r.total);
    } catch (e) {
      toast(String((e as Error).message), "err");
    } finally {
      setLoading(false);
    }
  }, [deviceId, page, search]);

  useEffect(() => {
    void load();
  }, [load]);

  const syncDir = async (dir: "from" | "to") => {
    setSyncing(dir);
    try {
      const r = dir === "from" ? await apiClient.syncUsersFromDevice(deviceId) : await apiClient.syncUsersToDevice(deviceId);
      toast(`کار همگام‌سازی کاربران آغاز شد (job ${String((r as { job_id: string }).job_id).slice(0, 8)}…)`, "ok");
      setTimeout(() => void load(), 1500);
    } catch (e) {
      toast(String((e as Error).message), "err");
    } finally {
      setSyncing("");
    }
  };

  return (
    <div className="card-body">
      <div className="row wrap between gap" style={{ marginBottom: 12 }}>
        <div className="row gap">
          <input
            placeholder="جستجوی کد / نام / کارت…"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            style={{ maxWidth: 260 }}
          />
          <button className="btn btn-soft" onClick={() => syncDir("from")} disabled={!!syncing}>
            {syncing === "from" ? <Spinner small /> : "⇣ همگام‌سازی از دستگاه"}
          </button>
          <button className="btn btn-soft" onClick={() => syncDir("to")} disabled={!!syncing}>
            {syncing === "to" ? <Spinner small /> : "⇡ ارسال به دستگاه"}
          </button>
        </div>
        <div className="row gap">
          <button className="btn btn-sm" onClick={() => void download(`/api/importexport/users/export?device_id=${deviceId}&fmt=csv`, "users.csv")}>
            خروجی CSV
          </button>
          <button className="btn btn-sm" onClick={() => void download(`/api/importexport/users/export?device_id=${deviceId}&fmt=xlsx`, "users.xlsx")}>
            خروجی Excel
          </button>
          <button className="btn btn-sm" onClick={() => void download(`/api/importexport/users/export?device_id=${deviceId}&fmt=json`, "users.json")}>
            خروجی JSON
          </button>
        </div>
      </div>
      <div className="table-wrap">
        {loading ? (
          <div className="page-center" style={{ height: 200 }}>
            <Spinner />
          </div>
        ) : items.length === 0 ? (
          <Empty text="کاربری روی این دستگاه ثبت نشده (یا هنوز همگام‌سازی نشده) است" />
        ) : (
          <DataTable<DeviceUser>
            keyOf={(u) => u.id}
            columns={[
              { key: "user_id_on_device", label: "شناسه کاربر", render: (u) => <span className="mono">{u.user_id_on_device}</span> },
              { key: "employee_code", label: "کد پرسنلی", render: (u) => u.employee_code || "—" },
              { key: "name", label: "نام", render: (u) => u.name || `${u.first_name || ""} ${u.last_name || ""}`.trim() || "—" },
              { key: "card", label: "شماره کارت", render: (u) => <span className="mono small">{u.card_number || "—"}</span> },
              { key: "enabled", label: "وضعیت", render: (u) => (u.enabled ? <RawBadge value="فعال" custom="green" /> : <RawBadge value="غیرفعال" custom="gray" />) },
              { key: "fp", label: "اثرانگشت", render: (u) => (u.fingerprint_count != null ? faNum(u.fingerprint_count) : "—") },
              {
                key: "bio",
                label: "حالت‌های زیستی",
                render: (u) => (
                  <span>
                    {u.face_enabled ? <span className="chip">چهره</span> : null}
                    {u.card_enabled ? <span className="chip">کارت</span> : null}
                    {u.password_enabled ? <span className="chip">رمز</span> : null}
                  </span>
                ),
              },
              { key: "last_sync_at", label: "آخرین همگام‌سازی", render: (u) => fmtTime(u.last_sync_at) },
            ]}
            rows={items}
          />
        )}
      </div>
      <Pagination page={page} pageSize={25} total={total} onChange={setPage} />
    </div>
  );
}

/* ---------- attendance ---------- */

function AttendanceTab({ deviceId }: { deviceId: string }) {
  const [items, setItems] = useState<AttendanceLog[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [pulling, setPulling] = useState(false);
  const [clearOpen, setClearOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await apiClient.deviceAttendance(deviceId, { page: String(page), page_size: "30" });
      setItems(r.items);
      setTotal(r.total);
    } catch (e) {
      toast(String((e as Error).message), "err");
    } finally {
      setLoading(false);
    }
  }, [deviceId, page]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="card-body">
      <div className="row wrap between gap" style={{ marginBottom: 12 }}>
        <div className="row gap">
          <button
            className="btn btn-primary"
            disabled={pulling}
            onClick={async () => {
              setPulling(true);
              try {
                await apiClient.pullAttendance(deviceId);
                toast("دریافت تردد از دستگاه آغاز شد", "ok");
                setTimeout(() => void load(), 1500);
              } catch (e) {
                toast(String((e as Error).message), "err");
              } finally {
                setPulling(false);
              }
            }}
          >
            {pulling ? <Spinner small /> : "⇣ دریافت تردد از دستگاه"}
          </button>
          <button
            className="btn btn-sm"
            onClick={() => void download(`/api/attendance/export?device_id=${deviceId}&fmt=csv`, "attendance.csv")}
          >
            خروجی CSV
          </button>
          <button
            className="btn btn-sm"
            onClick={() => void download(`/api/attendance/export?device_id=${deviceId}&fmt=xlsx`, "attendance.xlsx")}
          >
            خروجی Excel
          </button>
        </div>
        <button className="btn btn-sm btn-danger" onClick={() => setClearOpen(true)}>
          پاک‌سازی تردد دستگاه
        </button>
      </div>
      {loading ? (
        <div className="page-center" style={{ height: 200 }}>
          <Spinner />
        </div>
      ) : items.length === 0 ? (
        <Empty text="ترددی ثبت نشده است — از دکمه دریافت تردد استفاده کنید" />
      ) : (
        <DataTable<AttendanceLog>
          keyOf={(a) => a.id}
          columns={[
            { key: "event_time", label: "زمان", render: (a) => <span className="mono small">{fmtTime(a.event_time)}</span> },
            { key: "employee_code", label: "کد پرسنلی", render: (a) => a.employee_code || a.user_id_on_device || "—" },
            { key: "event_type", label: "نوع رویداد", render: (a) => <RawBadge value={a.event_type} label={EVENT_TYPE_LABEL[a.event_type] || a.event_type} /> },
            { key: "verification", label: "روش احراز", render: (a) => VERIFY_LABEL[a.verification_type] || a.verification_type || "—" },
            { key: "status", label: "وضعیت", render: (a) => a.status || "—" },
            { key: "source", label: "منبع", render: (a) => <span className="chip">{a.source}</span> },
          ]}
          rows={items}
        />
      )}
      <Pagination page={page} pageSize={30} total={total} onChange={setPage} />

      <Confirm
        open={clearOpen}
        title="پاک‌سازی تردد دستگاه"
        danger
        message="این عمل رکوردهای ورود/خروج را مستقیماً از روی دستگاه پاک می‌کند و غیرقابل بازگشت است. رکوردهای ذخیره‌شده در سرور دست‌نخورده می‌مانند. ادامه می‌دهید؟"
        onCancel={() => setClearOpen(false)}
        onConfirm={async () => {
          try {
            await apiClient.clearAttendance(deviceId);
            toast("تردد دستگاه پاک شد", "ok");
          } catch (e) {
            toast(String((e as Error).message), "err");
          } finally {
            setClearOpen(false);
          }
        }}
      />
    </div>
  );
}

/* ---------- capabilities ---------- */

function CapsTab({ caps }: { caps: Capability[] }) {
  return (
    <div className="card-body">
      {caps.length === 0 ? (
        <Empty text="هنوز ماتریس قابلیت‌ها ثبت نشده است — ابتدا تست اتصال یا کشف را اجرا کنید" />
      ) : (
        <DataTable<Capability>
          keyOf={(c) => c.capability}
          columns={[
            {
              key: "capability",
              label: "قابلیت",
              render: (c) => <b>{CAP_LABEL[c.capability] || c.capability}</b>,
            },
            {
              key: "supported",
              label: "پشتیبانی",
              render: (c) =>
                c.supported ? (
                  <RawBadge value="بله" custom="green" />
                ) : (
                  <RawBadge value={c.verified ? "خیر" : "نامشخص"} custom={c.verified ? "gray" : "amber"} />
                ),
            },
            {
              key: "verified",
              label: "وضعیت تأیید",
              render: (c) =>
                c.verified ? <RawBadge value="تأییدشده" custom="green" /> : <RawBadge value="تأییدنشده" custom="amber" />,
            },
            { key: "source", label: "منبع", render: (c) => c.source || "—" },
            { key: "reason", label: "توضیح", render: (c) => <span className="small muted">{c.reason || "—"}</span> },
          ]}
          rows={caps}
        />
      )}
      <div className="banner" style={{ marginTop: 14 }}>
        قابلیت‌ها از پاسخ واقعی دستگاه ثبت می‌شوند؛ هیچ قابلیتی به‌صورت پیش‌فرض «پشتیبانی‌شده» ادعا نمی‌شود.
      </div>
    </div>
  );
}

/* ---------- network / protocol ---------- */

function NetworkTab({ protocols, evidence }: { protocols: ProtocolInfo[]; evidence: unknown[] }) {
  const [showEvidence, setShowEvidence] = useState(false);
  return (
    <div className="card-body">
      {protocols.length === 0 ? (
        <Empty text="پروتکلی کشف نشده است" />
      ) : (
        <DataTable<ProtocolInfo>
          keyOf={(p) => `${p.port}-${p.transport}`}
          columns={[
            { key: "port", label: "پورت", render: (p) => <span className="mono">{p.port}</span> },
            { key: "transport", label: "ترنسپورت", render: (p) => <span className="chip">{p.transport.toUpperCase()}</span> },
            { key: "state", label: "وضعیت", render: (p) => <RawBadge value={p.state} label={p.state} /> },
            { key: "service", label: "سرویس", render: (p) => p.service || "—" },
            { key: "protocol", label: "پروتکل احتمالی", render: (p) => <span className="mono small">{p.protocol || "نامشخص"}</span> },
            { key: "confidence", label: "اطمینان", render: (p) => `${faNum(Math.round((p.confidence || 0) * 100))}٪` },
            { key: "title", label: "عنوان HTML", render: (p) => p.title || "—" },
          ]}
          rows={protocols}
        />
      )}

      <div style={{ marginTop: 16 }}>
        <button className="btn btn-sm btn-soft" onClick={() => setShowEvidence(!showEvidence)}>
          {showEvidence ? "بستن شواهد کشف" : "نمایش شواهد کشف (Evidence)"}
        </button>
        {showEvidence && (
          <div style={{ marginTop: 10 }}>
            {evidence.length === 0 ? (
              <div className="empty">شواهدی ثبت نشده است</div>
            ) : (
              <JsonView value={evidence} />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/* ---------- raw ---------- */

function RawTab({ deviceId }: { deviceId: string }) {
  const [rows, setRows] = useState<RawDataItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    apiClient
      .rawData(deviceId)
      .then(setRows)
      .catch((e) => toast(String((e as Error).message), "err"))
      .finally(() => setLoading(false));
  }, [deviceId]);

  if (loading)
    return (
      <div className="page-center" style={{ height: 200 }}>
        <Spinner />
      </div>
    );
  if (rows.length === 0) return <Empty text="داده خامی ثبت نشده است (پاسخ‌های HTTP/پروتکل در هنگام تشخیص ذخیره می‌شوند)" />;
  return (
    <div className="card-body">
      <DataTable<RawDataItem>
        keyOf={(r) => r.id}
        columns={[
          { key: "captured_at", label: "زمان", render: (r) => <span className="mono small">{fmtTime(r.captured_at)}</span> },
          { key: "category", label: "دسته", render: (r) => <span className="chip">{r.category}</span> },
          { key: "source", label: "منبع", render: (r) => r.source || "—" },
          {
            key: "payload",
            label: "محتوا",
            render: (r) => (
              <button className="linklike small" onClick={() => setOpen(open === r.id ? null : r.id)}>
                {open === r.id ? "بستن" : "نمایش"}
              </button>
            ),
          },
        ]}
        rows={rows}
      />
      {open && rows.find((r) => r.id === open) ? (
        <div style={{ marginTop: 12 }}>
          <JsonView value={rows.find((r) => r.id === open)?.payload || ""} />
        </div>
      ) : null}
    </div>
  );
}

/* ---------- device logs ---------- */

function LogsTab({ deviceId }: { deviceId: string }) {
  const [rows, setRows] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    apiClient
      .deviceLogs(deviceId)
      .then((r) => setRows(r as unknown as AuditEntry[]))
      .catch((e) => toast(String((e as Error).message), "err"))
      .finally(() => setLoading(false));
  }, [deviceId]);
  if (loading)
    return (
      <div className="page-center" style={{ height: 200 }}>
        <Spinner />
      </div>
    );
  return (
    <div className="card-body">
      {rows.length === 0 ? (
        <Empty text="عملیاتی روی این دستگاه ثبت نشده است" />
      ) : (
        <DataTable<AuditEntry>
          keyOf={(r) => r.id}
          columns={[
            { key: "created_at", label: "زمان", render: (r) => <span className="mono small">{fmtTime(r.created_at)}</span> },
            { key: "username", label: "کاربر", render: (r) => r.username || "سیستم" },
            { key: "action", label: "عملیات", render: (r) => <span className="chip">{r.action}</span> },
            { key: "result", label: "نتیجه", render: (r) => <RawBadge value={r.result} /> },
            { key: "duration_ms", label: "مدت (ms)", render: (r) => faNum(r.duration_ms) },
            { key: "error", label: "خطا", render: (r) => <span className="small muted">{r.error || "—"}</span> },
          ]}
          rows={rows}
        />
      )}
    </div>
  );
}

/* ---------- sync ---------- */

function SyncTab({ device, onChanged }: { device: DeviceDetail; onChanged: () => void }) {
  const [jobs, setJobs] = useState<SyncJob[]>([]);
  const [busy, setBusy] = useState(false);
  const [direction, setDirection] = useState("device_to_server");
  const [scope, setScope] = useState("full");

  const loadJobs = useCallback(() => {
    apiClient
      .syncJobs(device.id)
      .then(setJobs)
      .catch(() => undefined);
  }, [device.id]);

  useEffect(() => {
    void loadJobs();
    const t = setInterval(() => void loadJobs(), 4000);
    return () => clearInterval(t);
  }, [loadJobs]);

  const runSync = async () => {
    setBusy(true);
    try {
      await apiClient.syncDevice(device.id, direction, scope);
      toast("کار همگام‌سازی ایجاد شد", "ok");
      onChanged();
      setTimeout(() => void loadJobs(), 1200);
    } catch (e) {
      toast(String((e as Error).message), "err");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card-body">
      <div className="form-grid">
        <Field label="جهت همگام‌سازی">
          <select value={direction} onChange={(e) => setDirection(e.target.value)}>
            <option value="device_to_server">دستگاه ← سرور (دریافت)</option>
            <option value="server_to_device">دستگاه → سرور (ارسال)</option>
            <option value="bidirectional">دو‌طرفه</option>
          </select>
        </Field>
        <Field label="محدوده">
          <select value={scope} onChange={(e) => setScope(e.target.value)}>
            <option value="full">کامل (کاربران + تردد)</option>
            <option value="users">فقط کاربران</option>
            <option value="logs">فقط ترددها</option>
          </select>
        </Field>
      </div>
      <div className="row end" style={{ marginTop: 12 }}>
        <button className="btn btn-primary" disabled={busy} onClick={() => void runSync()}>
          {busy ? <Spinner small /> : "اجرای همگام‌سازی"}
        </button>
      </div>

      <div style={{ marginTop: 18 }}>
        <h4 style={{ fontSize: 13 }}>کارهای اخیر همگام‌سازی</h4>
        {jobs.length === 0 ? (
          <Empty text="همگام‌سازی‌ای اجرا نشده است" />
        ) : (
          <DataTable<SyncJob>
            keyOf={(j) => j.id}
            columns={[
              { key: "created_at", label: "ایجاد", render: (j) => <span className="mono small">{fmtTime(j.created_at)}</span> },
              { key: "direction", label: "جهت", render: (j) => <span className="chip">{j.direction}</span> },
              { key: "scope", label: "محدوده", render: (j) => <span className="chip">{j.scope}</span> },
              { key: "status", label: "وضعیت", render: (j) => <RawBadge value={j.status} /> },
              {
                key: "stats",
                label: "آمار",
                render: (j) => (
                  <span className="small muted">
                    {j.stats && typeof j.stats === "object" ? Object.entries(j.stats).map(([k, v]) => `${k}:${faNum(v as number)}`).join(" ") : "—"}
                  </span>
                ),
              },
              { key: "error", label: "خطا", render: (j) => <span className="small muted">{j.error || "—"}</span> },
            ]}
            rows={jobs}
          />
        )}
      </div>
    </div>
  );
}

/* ---------- device settings ---------- */

function SettingsTab({ device, onChanged }: { device: DeviceDetail; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const [creds, setCreds] = useState<Cred[]>([]);
  const [credOpen, setCredOpen] = useState(false);
  const [credForm, setCredForm] = useState({ kind: "password", username: "", secret: "", note: "" });
  const [form, setForm] = useState({
    auto_sync_enabled: device.auto_sync_enabled,
    sync_interval_min: device.sync_interval_min ?? 5,
    connect_timeout_s: 3,
    read_timeout_s: 10,
    retry_count: 2,
    hostname: device.hostname || "",
    port: device.port ? String(device.port) : "",
  });

  const loadCreds = useCallback(() => {
    apiClient
      .deviceCredentials(device.id)
      .then((r) => setCreds(r as unknown as Cred[]))
      .catch(() => setCreds([]));
  }, [device.id]);

  useEffect(() => {
    void loadCreds();
  }, [loadCreds]);

  const save = async () => {
    setBusy(true);
    try {
      const body: Record<string, unknown> = {
        auto_sync_enabled: form.auto_sync_enabled,
        sync_interval_min: Number(form.sync_interval_min),
      };
      if (form.hostname.trim()) body.hostname = form.hostname.trim();
      if (form.port) body.port = Number(form.port);
      await apiClient.updateDevice(device.id, body);
      toast("تنظیمات دستگاه ذخیره شد", "ok");
      onChanged();
    } catch (e) {
      toast(String((e as Error).message), "err");
    } finally {
      setBusy(false);
    }
  };

  const addCred = async () => {
    setBusy(true);
    try {
      await apiClient.addCredential(device.id, credForm);
      toast("اعتبارنامه ذخیره شد", "ok");
      setCredOpen(false);
      setCredForm({ kind: "password", username: "", secret: "", note: "" });
      void loadCreds();
    } catch (e) {
      toast(String((e as Error).message), "err");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card-body">
      <div className="banner banner-amber" style={{ marginBottom: 16 }}>
        در صورت نیاز به احراز هویت (ZKTeco: کد ارتباطی؛ HTTP: نام کاربری/رمز یا کلید API)، اعتبارنامه را ذخیره کنید —
        به‌صورت رمزنگاری‌شده نگهداری می‌شود و هرگز به‌صورت متن ساده نمایش داده نمی‌شود.
      </div>

      <div className="grid grid-2">
        <div>
          <h4 style={{ fontSize: 13.5 }}>همگام‌سازی خودکار</h4>
          <div className="col" style={{ marginTop: 8 }}>
            <label className="row gap">
              <input type="checkbox" checked={form.auto_sync_enabled} onChange={(e) => setForm({ ...form, auto_sync_enabled: e.target.checked })} />
              فعال‌سازی همگام‌سازی زمان‌بندی‌شده
            </label>
            <Field label="بازه همگام‌سازی (دقیقه)">
              <select value={form.sync_interval_min} onChange={(e) => setForm({ ...form, sync_interval_min: Number(e.target.value) })}>
                <option value={1}>هر ۱ دقیقه</option>
                <option value={5}>هر ۵ دقیقه</option>
                <option value={15}>هر ۱۵ دقیقه</option>
                <option value={60}>هر ۱ ساعت</option>
              </select>
            </Field>
            <Field label="نام میزبان">
              <input value={form.hostname} onChange={(e) => setForm({ ...form, hostname: e.target.value })} />
            </Field>
            <Field label="پورت" hint="ZKTeco پیش‌فرض 4370">
              <input dir="ltr" value={form.port} onChange={(e) => setForm({ ...form, port: e.target.value })} />
            </Field>
            <button className="btn btn-primary" style={{ alignSelf: "flex-start" }} disabled={busy} onClick={() => void save()}>
              {busy ? <Spinner small /> : "ذخیره تنظیمات"}
            </button>
          </div>
        </div>

        <div>
          <div className="row between" style={{ marginBottom: 8 }}>
            <h4 style={{ fontSize: 13.5 }}>اعتبارنامه‌های دستگاه</h4>
            <button className="btn btn-sm btn-soft" onClick={() => setCredOpen(true)}>
              + افزودن
            </button>
          </div>
          {creds.length === 0 ? (
            <Empty text="اعتبارنامه‌ای ذخیره نشده است" />
          ) : (
            <div className="col">
              {creds.map((c) => (
                <div className="row between" key={c.id} style={{ border: "1px solid var(--line)", borderRadius: 10, padding: "8px 12px" }}>
                  <div>
                    <b>{c.kind}</b>
                    {c.username ? <span className="muted small"> · {c.username}</span> : null}
                    <div className="muted small mono" dir="ltr">
                      {c.secret_masked || "••••"}
                    </div>
                  </div>
                  <button
                    className="btn btn-sm btn-danger"
                    onClick={async () => {
                      try {
                        await apiClient.deleteCredential(device.id, c.id);
                        toast("حذف شد", "ok");
                        void loadCreds();
                      } catch (e) {
                        toast(String((e as Error).message), "err");
                      }
                    }}
                  >
                    حذف
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <Modal open={credOpen} title="افزودن اعتبارنامه" onClose={() => setCredOpen(false)}>
        <div className="form-grid">
          <div className="span2">
            <Field label="نوع">
              <select value={credForm.kind} onChange={(e) => setCredForm({ ...credForm, kind: e.target.value })}>
                <option value="password">رمز / کد ارتباطی</option>
                <option value="username_password">نام کاربری + رمز</option>
                <option value="api_key">کلید API</option>
                <option value="token">توکن</option>
                <option value="snmp_community">SNMP Community</option>
                <option value="communication_key">ZKTeco کد ارتباطی</option>
              </select>
            </Field>
          </div>
          {(credForm.kind === "username_password" || credForm.kind === "password") && (
            <Field label="نام کاربری (اختیاری)">
              <input value={credForm.username} onChange={(e) => setCredForm({ ...credForm, username: e.target.value })} />
            </Field>
          )}
          <Field label="مقدار محرمانه">
            <input type="password" dir="ltr" value={credForm.secret} onChange={(e) => setCredForm({ ...credForm, secret: e.target.value })} />
          </Field>
          <div className="span2">
            <Field label="یادداشت (اختیاری)">
              <input value={credForm.note} onChange={(e) => setCredForm({ ...credForm, note: e.target.value })} />
            </Field>
          </div>
        </div>
        <div className="form-actions">
          <button className="btn" onClick={() => setCredOpen(false)}>
            انصراف
          </button>
          <button className="btn btn-primary" disabled={busy || !credForm.secret} onClick={() => void addCred()}>
            {busy ? <Spinner small /> : "ذخیره"}
          </button>
        </div>
      </Modal>
    </div>
  );
}
