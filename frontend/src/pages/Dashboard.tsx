import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient } from "../api/client";
import type { AttendanceLog, DashboardStats, Device } from "../api/types";
import { Badge, DataTable, RawBadge, Spinner, Stat, toast } from "../components/ui";
import { EVENT_TYPE_LABEL, fmtTime, fmtTimeOnly, faNum, VERIFY_LABEL } from "../lib/fa";

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const [recent, setRecent] = useState<AttendanceLog[]>([]);
  const [err, setErr] = useState("");

  const load = async () => {
    try {
      const [s, d, r] = await Promise.all([
        apiClient.stats(),
        apiClient.devices({ page_size: "12", sort: "last_seen_at" }).catch(() => null),
        apiClient.recentAttendance(),
      ]);
      setStats(s);
      if (d) setDevices(d.items);
      setRecent(r);
    } catch (e) {
      setErr(String((e as Error).message));
    }
  };

  useEffect(() => {
    void load();
    const t = setInterval(() => void load(), 30_000);
    return () => clearInterval(t);
  }, []);

  if (!stats) {
    return err ? (
      <div className="card">
        <div className="card-body">
          <div className="banner banner-red">خطا در دریافت اطلاعات: {err}</div>
        </div>
      </div>
    ) : (
      <div className="page-center">
        <Spinner />
      </div>
    );
  }

  const s = stats;
  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">داشبورد</h1>
          <div className="page-sub">
            مدیریت و مانیتورینگ دستگاه‌های حضور و غیاب — آخرین به‌روزرسانی {fmtTime(new Date().toISOString())}
          </div>
        </div>
        <div className="page-actions">
          <Link className="btn" to="/networks">
            🌐 اسکن شبکه‌ها
          </Link>
          <Link className="btn btn-primary" to="/devices">
            مدیریت دستگاه‌ها
          </Link>
        </div>
      </div>

      <div className="grid grid-4" style={{ marginBottom: 18 }}>
        <Stat label="کل دستگاه‌ها" value={faNum(s.total_devices)} />
        <Stat label="آنلاین" value={faNum(s.online_devices)} tone="green" />
        <Stat label="آفلاین" value={faNum(s.offline_devices)} tone="red" />
        <Stat label="ناشناخته" value={faNum(s.unknown_devices)} tone="gray" />
        <Stat label="تأییدشده (VERIFIED)" value={faNum(s.verified_devices)} tone="green" />
        <Stat label="نامزد دستگاه تردد" value={faNum(s.attendance_candidates)} tone="blue" />
        <Stat label="کاربران ثبت‌شده" value={faNum(s.total_users)} />
        <Stat label="تردد امروز" value={faNum(s.today_attendance)} tone="blue" />
        <Stat label="آخرین همگام‌سازی" value={s.last_sync_at ? fmtTime(s.last_sync_at) : "—"} />
        <Stat label="خطاهای ۲۴ ساعت اخیر" value={faNum(s.failed_operations_24h)} tone={s.failed_operations_24h > 0 ? "red" : "green"} />
        <Stat label="شبکه‌های تعریف‌شده" value={faNum(s.networks_count)} />
        <Stat label="کارهای در انتظار" value={faNum(s.pending_jobs)} tone={s.pending_jobs > 0 ? "amber" : ""} />
      </div>

      <div className="grid grid-3">
        <div className="card" style={{ gridColumn: "span 2" }}>
          <div className="card-head">
            <span className="card-title">وضعیت دستگاه‌ها</span>
            <Link className="btn btn-sm btn-soft" to="/devices">
              مشاهده همه
            </Link>
          </div>
          <div className="card-body flush">
            <DataTable<Device>
              columns={[
                {
                  key: "ip_address",
                  label: "IP",
                  render: (d) => (
                    <Link to={`/devices/${d.id}`} onClick={(e) => e.stopPropagation()}>
                      <span className="mono">{d.ip_address}</span>
                    </Link>
                  ),
                },
                { key: "brand", label: "برند", render: (d) => d.brand || d.vendor || "—" },
                { key: "model", label: "مدل", render: (d) => d.model || "—" },
                {
                  key: "status",
                  label: "وضعیت",
                  render: (d) => <RawBadge value={d.status} />,
                },
                {
                  key: "detection_state",
                  label: "تشخیص",
                  render: (d) => <Badge value={d.detection_state} />,
                },
                { key: "confidence", label: "اطمینان", render: (d) => `${faNum(Math.round(d.confidence * 100))}٪` },
                { key: "last_seen_at", label: "آخرین حضور", render: (d) => fmtTime(d.last_seen_at) },
              ]}
              rows={devices}
              empty="دستگاهی ثبت نشده است — از بخش شبکه‌ها اسکن کنید"
            />
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <span className="card-title">آخرین ترددها (بلادرنگ)</span>
          </div>
          <div className="card-body flush">
            {recent.length === 0 ? (
              <div className="empty">هنوز رکوردی دریافت نشده است</div>
            ) : (
              <div className="ticker">
                {recent.map((r) => (
                  <div className="ticker-row" key={r.id}>
                    <span className="avatar">{(r.employee_code || r.user_id_on_device || "؟").slice(0, 2)}</span>
                    <div className="grow">
                      <b>{r.employee_code || r.user_id_on_device || "—"}</b>
                      <span className="muted small"> · {EVENT_TYPE_LABEL[r.event_type] || r.event_type}</span>
                      <div className="muted small">
                        {VERIFY_LABEL[r.verification_type] || r.verification_type}
                        {r.device_ip ? ` · ${r.device_ip}` : ""}
                      </div>
                    </div>
                    <span className="ticker-time">{fmtTimeOnly(r.event_time)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="card-foot small muted">
            به‌روزرسانی خودکار هر ۳۰ ثانیه — برای رویداد بلادرنگ از دستگاه، همگام‌سازی را اجرا کنید.
          </div>
        </div>
      </div>
    </div>
  );
}
