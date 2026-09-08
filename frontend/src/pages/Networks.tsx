import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiClient } from "../api/client";
import type { DiscoveryJob, DiscoveryResult, Network } from "../api/types";
import { Confirm, DataTable, Field, Modal, RawBadge, Spinner, toast } from "../components/ui";
import { faNum, fmtTime, pct } from "../lib/fa";

export default function Networks() {
  const nav = useNavigate();
  const [nets, setNets] = useState<Network[]>([]);
  const [jobs, setJobs] = useState<DiscoveryJob[]>([]);
  const [results, setResults] = useState<DiscoveryResult[]>([]);
  const [addOpen, setAddOpen] = useState(false);
  const [edit, setEdit] = useState<Network | null>(null);
  const [del, setDel] = useState<Network | null>(null);
  const [clearJobs, setClearJobs] = useState(false);
  const [clearResults, setClearResults] = useState(false);
  const [scanTarget, setScanTarget] = useState<Network | null>(null);
  const [scanning, setScanning] = useState(false);
  const [form, setForm] = useState({ cidr: "", label: "", exclude_ips: "" });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [n, j] = await Promise.all([apiClient.networks(), apiClient.discoveryJobs()]);
      setNets(n);
      setJobs(j);
    } catch (e) {
      toast(String((e as Error).message), "err");
    }
  }, []);

  const loadResults = useCallback(() => {
    apiClient
      .discoveryResults()
      .then(setResults)
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    void load();
    void loadResults();
    const t = setInterval(() => {
      void load();
      void loadResults();
    }, 5000);
    return () => clearInterval(t);
  }, [load, loadResults]);

  const saveNet = async () => {
    setBusy(true);
    try {
      const body = {
        cidr: form.cidr.trim(),
        label: form.label.trim() || null,
        exclude_ips: form.exclude_ips.split(/[\n,،\s]+/).filter(Boolean),
      };
      if (edit) {
        await apiClient.updateNetwork(edit.id, body);
        toast("شبکه به‌روزرسانی شد", "ok");
      } else {
        await apiClient.createNetwork(body);
        toast("شبکه اضافه شد", "ok");
      }
      setAddOpen(false);
      setEdit(null);
      void load();
    } catch (e) {
      toast(String((e as Error).message), "err");
    } finally {
      setBusy(false);
    }
  };

  const scan = async (targetId: string | null, label: string) => {
    setScanning(true);
    try {
      if (targetId) {
        await apiClient.scanNetwork(targetId);
        toast(`اسکن «${label}» آغاز شد`, "ok");
      } else {
        const enabled = nets.filter((n) => n.enabled);
        if (enabled.length === 0) {
          toast("شبکه فعالی برای اسکن وجود ندارد", "err");
        } else {
          for (const n of enabled) {
            try {
              await apiClient.scanNetwork(n.id);
            } catch (e) {
              toast(`اسکن ${n.cidr}: ${String((e as Error).message)}`, "err");
            }
          }
          toast(`اسکن ${enabled.length} شبکه فعال آغاز شد`, "ok");
        }
      }
    } catch (e) {
      toast(String((e as Error).message), "err");
    } finally {
      setScanning(false);
      setScanTarget(null);
    }
  };

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">شبکه‌ها و اسکن</h1>
          <div className="page-sub">
            تنها شبکه‌های تعریف‌شده در همین صفحه قابل اسکن هستند — اسکن خارج از این فهرست ممکن نیست
          </div>
        </div>
        <div className="page-actions">
          <button className="btn btn-soft" disabled={scanning || nets.length === 0} onClick={() => void scan(null, "همه شبکه‌ها")}>
            {scanning ? <Spinner small /> : "🌐 اسکن همه شبکه‌ها"}
          </button>
          <button className="btn btn-primary" onClick={() => { setEdit(null); setForm({ cidr: "", label: "", exclude_ips: "" }); setAddOpen(true); }}>
            + شبکه جدید
          </button>
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <span className="card-title">شبکه‌های تعریف‌شده</span>
        </div>
        <div className="card-body flush">
          {nets.length === 0 ? (
            <div className="empty">شبکه‌ای تعریف نشده است</div>
          ) : (
            <DataTable<Network>
              keyOf={(n) => n.id}
              columns={[
                { key: "cidr", label: "CIDR", render: (n) => <span className="mono">{n.cidr}</span> },
                { key: "label", label: "برچسب", render: (n) => n.label || "—" },
                { key: "enabled", label: "وضعیت", render: (n) => (n.enabled ? <RawBadge value="فعال" custom="green" /> : <RawBadge value="غیرفعال" custom="gray" />) },
                { key: "is_default", label: "پیش‌فرض", render: (n) => (n.is_default ? <span className="chip">بله</span> : "—") },
                { key: "is_single_ip", label: "نوع", render: (n) => (n.is_single_ip ? <span className="chip">تک‌IP</span> : <span className="chip">شبکه</span>) },
                {
                  key: "exclude_ips",
                  label: "IPهای مستثنی",
                  render: (n) => (n.exclude_ips.length ? <span className="small mono">{n.exclude_ips.join("، ")}</span> : "—"),
                },
                { key: "last_scan_at", label: "آخرین اسکن", render: (n) => fmtTime(n.last_scan_at) },
                {
                  key: "actions",
                  label: "عملیات",
                  render: (n) => (
                    <div className="row gap" onClick={(e) => e.stopPropagation()}>
                      <button className="btn btn-sm btn-soft" disabled={scanning} onClick={() => { setScanTarget(n); void scan(n.id, n.cidr); }}>
                        اسکن
                      </button>
                      <button
                        className="btn btn-sm"
                        onClick={() => {
                          setEdit(n);
                          setForm({ cidr: n.cidr, label: n.label || "", exclude_ips: (n.exclude_ips as string[]).join("\n") });
                          setAddOpen(true);
                        }}
                      >
                        ویرایش
                      </button>
                      <button className="btn btn-sm btn-danger" onClick={() => setDel(n)}>
                        حذف
                      </button>
                    </div>
                  ),
                },
              ]}
              rows={nets}
            />
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <span className="card-title">کارهای کشف / اسکن</span>
          <button className="btn btn-sm btn-danger" disabled={jobs.length === 0} onClick={() => setClearJobs(true)}>
            پاک کردن کارها
          </button>
        </div>
        <div className="card-body flush">
          {jobs.length === 0 ? (
            <div className="empty">کار کشفی اجرا نشده است</div>
          ) : (
            <DataTable<DiscoveryJob>
              keyOf={(j) => j.id}
              columns={[
                { key: "target", label: "هدف", render: (j) => <span className="mono small">{j.target}</span> },
                { key: "kind", label: "نوع", render: (j) => <span className="chip">{j.kind}</span> },
                { key: "requested_by", label: "درخواست‌دهنده", render: (j) => j.requested_by || "سیستم" },
                {
                  key: "status",
                  label: "وضعیت",
                  render: (j) => <RawBadge value={j.status} />,
                },
                {
                  key: "progress",
                  label: "پیشرفت",
                  render: (j) => (
                    <div style={{ minWidth: 130 }}>
                      <div className="progress">
                        <div className="progress-bar" style={{ width: `${Math.max(0, Math.min(100, j.progress))}%` }} />
                      </div>
                      <span className="small muted">
                        {pct(j.progress)} — {faNum(j.scanned_hosts)}/{faNum(j.total_hosts)} میزبان
                      </span>
                    </div>
                  ),
                },
                { key: "found_hosts", label: "یافت‌شده", render: (j) => faNum(j.found_hosts) },
                { key: "errors", label: "خطاها", render: (j) => faNum(j.errors) },
                { key: "error", label: "پیام", render: (j) => <span className="small muted">{j.error || "—"}</span> },
              ]}
              rows={jobs}
            />
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <span className="card-title">نتایج کشف اخیر</span>
          <button className="btn btn-sm btn-danger" disabled={results.length === 0} onClick={() => setClearResults(true)}>
            پاک کردن نتایج
          </button>
        </div>
        <div className="card-body flush">
          {results.length === 0 ? (
            <div className="empty">نتیجه کشفی ثبت نشده است</div>
          ) : (
            <DataTable<DiscoveryResult>
              keyOf={(r) => r.id}
              onRowClick={(r) => nav(`/devices`)}
              columns={[
                { key: "ip_address", label: "IP", render: (r) => <span className="mono">{r.ip_address}</span> },
                { key: "reachable", label: "در دسترس", render: (r) => (r.reachable ? <RawBadge value="بله" custom="green" /> : <RawBadge value="خیر" custom="red" />) },
                {
                  key: "open_ports",
                  label: "پورت‌های باز",
                  render: (r) => (r.open_ports.length ? <span className="mono small">{r.open_ports.join("، ")}</span> : "—"),
                },
                { key: "hostname", label: "نام", render: (r) => r.hostname || "—" },
                { key: "detection_state", label: "تشخیص", render: (r) => <RawBadge value={r.detection_state} /> },
                { key: "confidence", label: "اطمینان", render: (r) => pct(r.confidence * 100) },
                { key: "source", label: "منبع", render: (r) => r.source || "—" },
                { key: "probed_at", label: "زمان", render: (r) => fmtTime(r.probed_at) },
              ]}
              rows={results}
            />
          )}
        </div>
      </div>

      <Modal open={addOpen} title={edit ? "ویرایش شبکه" : "افزودن شبکه"} onClose={() => setAddOpen(false)}>
        <div className="col">
          <Field label="CIDR یا IP" hint="مثلاً 172.16.50.0/24 یا یک IP تکی مانند 172.16.50.30">
            <input dir="ltr" value={form.cidr} onChange={(e) => setForm({ ...form, cidr: e.target.value })} placeholder="172.16.50.0/24" />
          </Field>
          <Field label="برچسب (اختیاری)">
            <input value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} />
          </Field>
          <Field label="IPهای مستثنی (هر خط یک IP)">
            <textarea rows={3} dir="ltr" value={form.exclude_ips} onChange={(e) => setForm({ ...form, exclude_ips: e.target.value })} placeholder={"172.16.50.1\n172.16.50.254"} />
          </Field>
        </div>
        <div className="form-actions">
          <button className="btn" onClick={() => setAddOpen(false)}>
            انصراف
          </button>
          <button className="btn btn-primary" disabled={busy || !form.cidr.trim()} onClick={() => void saveNet()}>
            {busy ? <Spinner small /> : edit ? "ذخیره تغییرات" : "افزودن"}
          </button>
        </div>
      </Modal>

      <Confirm
        open={del !== null}
        title="حذف شبکه"
        danger
        message={
          <>
            آیا از حذف شبکه <b className="mono">{del?.cidr}</b> مطمئن هستید؟ دستگاه‌های کشف‌شده از این شبکه حذف نخواهند شد.
          </>
        }
        onCancel={() => setDel(null)}
        onConfirm={async () => {
          if (!del) return;
          try {
            await apiClient.deleteNetwork(del.id);
            toast("شبکه حذف شد", "ok");
            void load();
          } catch (e) {
            toast(String((e as Error).message), "err");
          } finally {
            setDel(null);
          }
        }}
      />

      <Confirm
        open={clearJobs}
        title="پاک کردن کارهای کشف"
        danger
        message="همه کارهای تکمیل‌شده، ناموفق و لغوشده حذف می‌شوند و نتایج وابسته آن‌ها نیز پاک خواهد شد. کارهای در حال اجرا حذف نمی‌شوند. ادامه می‌دهید؟"
        onCancel={() => setClearJobs(false)}
        onConfirm={async () => {
          try {
            await apiClient.deleteDiscoveryJobs();
            toast("کارهای کشف پاک شدند", "ok");
            void load();
            void loadResults();
          } catch (e) {
            toast(String((e as Error).message), "err");
          } finally {
            setClearJobs(false);
          }
        }}
      />

      <Confirm
        open={clearResults}
        title="پاک کردن نتایج کشف"
        danger
        message="همه نتایج کشف اخیر حذف می‌شوند. رکورد دستگاه‌های ثبت‌شده حذف نخواهند شد. ادامه می‌دهید؟"
        onCancel={() => setClearResults(false)}
        onConfirm={async () => {
          try {
            await apiClient.deleteDiscoveryResults();
            toast("نتایج کشف پاک شدند", "ok");
            void loadResults();
          } catch (e) {
            toast(String((e as Error).message), "err");
          } finally {
            setClearResults(false);
          }
        }}
      />
    </div>
  );
}
