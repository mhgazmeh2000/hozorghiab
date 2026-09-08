import { useCallback, useEffect, useState } from "react";
import { apiClient, download } from "../api/client";
import type { AttendanceLog, Device } from "../api/types";
import { DataTable, Empty, Field, Pagination, RawBadge, Spinner, toast } from "../components/ui";
import { EVENT_TYPE_LABEL, faNum, fmtTime, toLocalInputDate, VERIFY_LABEL } from "../lib/fa";

const EVENT_TYPES = ["CHECK_IN", "CHECK_OUT", "BREAK_IN", "BREAK_OUT", "OVERTIME_IN", "OVERTIME_OUT", "UNKNOWN"];
const VERIFY_TYPES = ["FINGERPRINT", "FACE", "CARD", "PASSWORD", "PIN", "UNKNOWN"];

export default function Attendance() {
  const [items, setItems] = useState<AttendanceLog[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [f, setF] = useState({
    device_id: "",
    employee: "",
    event_type: "",
    verification: "",
    search: "",
    date_from: "",
    date_to: "",
  });
  const [auto, setAuto] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p: Record<string, string> = { page: String(page), page_size: "30" };
      if (f.device_id) p.device_id = f.device_id;
      if (f.employee) p.employee = f.employee;
      if (f.event_type) p.event_type = f.event_type;
      if (f.verification) p.verification = f.verification;
      if (f.search) p.search = f.search;
      if (f.date_from) p.date_from = new Date(f.date_from).toISOString();
      if (f.date_to) p.date_to = new Date(`${f.date_to}T23:59:59`).toISOString();
      const r = await apiClient.attendance(p);
      setItems(r.items);
      setTotal(r.total);
    } catch (e) {
      toast(String((e as Error).message), "err");
    } finally {
      setLoading(false);
    }
  }, [page, f]);

  useEffect(() => {
    apiClient
      .devices({ page_size: "200" })
      .then((d) => setDevices(d.items))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!auto) return;
    const t = setInterval(() => void load(), 15_000);
    return () => clearInterval(t);
  }, [auto, load]);

  const exportFmt = (fmt: string, label: string) => {
    const q = new URLSearchParams({ fmt });
    if (f.device_id) q.set("device_id", f.device_id);
    if (f.employee) q.set("employee", f.employee);
    if (f.event_type) q.set("event_type", f.event_type);
    if (f.verification) q.set("verification", f.verification);
    if (f.date_from) q.set("date_from", new Date(f.date_from).toISOString());
    if (f.date_to) q.set("date_to", new Date(`${f.date_to}T23:59:59`).toISOString());
    void download(`/api/attendance/export?${q}`, `attendance.${fmt}`).catch((e) =>
      toast(String((e as Error).message), "err")
    );
  };

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">ترددها</h1>
          <div className="page-sub">رکوردهای ورود/خروج — {faNum(total)} رکورد با فیلترهای جاری</div>
        </div>
        <div className="page-actions">
          <label className="row gap">
            <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} />
            به‌روزرسانی خودکار (۱۵ ثانیه)
          </label>
          <button className="btn btn-sm" onClick={() => exportFmt("csv", "csv")}>
            خروجی CSV
          </button>
          <button className="btn btn-sm" onClick={() => exportFmt("xlsx", "xlsx")}>
            خروجی Excel
          </button>
          <button className="btn btn-sm" onClick={() => exportFmt("json", "json")}>
            خروجی JSON
          </button>
        </div>
      </div>

      <div className="filter-group">
        <Field label="دستگاه">
          <select value={f.device_id} onChange={(e) => { setF({ ...f, device_id: e.target.value }); setPage(1); }}>
            <option value="">همه دستگاه‌ها</option>
            {devices.map((d) => (
              <option key={d.id} value={d.id}>
                {d.ip_address}
                {d.model ? ` (${d.model})` : ""}
              </option>
            ))}
          </select>
        </Field>
        <Field label="کد پرسنلی">
          <input value={f.employee} onChange={(e) => { setF({ ...f, employee: e.target.value }); setPage(1); }} placeholder="e.g. 1001" />
        </Field>
        <Field label="نوع رویداد">
          <select value={f.event_type} onChange={(e) => { setF({ ...f, event_type: e.target.value }); setPage(1); }}>
            <option value="">همه</option>
            {EVENT_TYPES.map((t) => (
              <option key={t} value={t}>
                {EVENT_TYPE_LABEL[t] || t}
              </option>
            ))}
          </select>
        </Field>
        <Field label="روش احراز">
          <select value={f.verification} onChange={(e) => { setF({ ...f, verification: e.target.value }); setPage(1); }}>
            <option value="">همه</option>
            {VERIFY_TYPES.map((t) => (
              <option key={t} value={t}>
                {VERIFY_LABEL[t] || t}
              </option>
            ))}
          </select>
        </Field>
        <Field label="از تاریخ">
          <input type="date" dir="ltr" value={f.date_from} onChange={(e) => { setF({ ...f, date_from: e.target.value }); setPage(1); }} />
        </Field>
        <Field label="تا تاریخ">
          <input type="date" dir="ltr" value={f.date_to} onChange={(e) => { setF({ ...f, date_to: e.target.value }); setPage(1); }} />
        </Field>
        <button className="btn btn-sm" style={{ alignSelf: "flex-end" }} onClick={() => { setF({ device_id: "", employee: "", event_type: "", verification: "", search: "", date_from: "", date_to: "" }); setPage(1); }}>
          پاک‌کردن فیلترها
        </button>
      </div>

      <div className="card">
        <div className="card-body flush">
          {loading ? (
            <div className="page-center" style={{ height: 220 }}>
              <Spinner />
            </div>
          ) : items.length === 0 ? (
            <Empty text="رکوردی با این فیلترها یافت نشد" />
          ) : (
            <DataTable<AttendanceLog>
              keyOf={(a) => a.id}
              columns={[
                {
                  key: "event_time",
                  label: "زمان",
                  render: (a) => <span className="mono small">{fmtTime(a.event_time)}</span>,
                },
                { key: "employee_code", label: "کد پرسنلی", render: (a) => <b>{a.employee_code || a.user_id_on_device || "—"}</b> },
                {
                  key: "device_ip",
                  label: "دستگاه",
                  render: (a) => (
                    <span className="mono small">
                      {devices.find((d) => d.id === a.device_id)?.ip_address || a.device_ip || a.device_id?.slice(0, 8) || "—"}
                    </span>
                  ),
                },
                {
                  key: "event_type",
                  label: "نوع رویداد",
                  render: (a) => <RawBadge value={a.event_type} label={EVENT_TYPE_LABEL[a.event_type] || a.event_type} />,
                },
                { key: "raw_state", label: "State خام", render: (a) => <span className="mono">{a.raw_state || "UNKNOWN"}</span> },
                { key: "raw_punch", label: "Punch خام", render: (a) => <span className="mono">{a.raw_punch || "UNKNOWN"}</span> },
                { key: "verification_type", label: "احراز", render: (a) => VERIFY_LABEL[a.verification_type] || a.verification_type || "—" },
                { key: "source", label: "منبع", render: (a) => <span className="chip">{a.source}</span> },
              ]}
              rows={items}
            />
          )}
        </div>
        <Pagination page={page} pageSize={30} total={total} onChange={setPage} />
      </div>
      <p className="muted small">
        امروز: {toLocalInputDate(new Date())} — همه رکوردها بر اساس رویداد واقعی دستگاه ثبت شده‌اند؛ هیچ رکوردی به‌صورت
        مصنوعی تولید نمی‌شود.
      </p>
    </div>
  );
}
