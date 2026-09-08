import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiClient } from "../api/client";
import type { Device } from "../api/types";
import {
  Badge,
  Confirm,
  DataTable,
  Empty,
  Field,
  Modal,
  Pagination,
  RawBadge,
  Spinner,
  toast,
} from "../components/ui";
import { faNum, fmtTime } from "../lib/fa";

const ADAPTERS = [
  { value: "zkteco", label: "ZKTeco (پروتکل TCP 4370)" },
  { value: "generic_http", label: "Generic HTTP" },
  { value: "generic_snmp", label: "Generic SNMP" },
  { value: "suprema", label: "Suprema" },
  { value: "anviz", label: "Anviz" },
  { value: "virdi", label: "Virdi" },
  { value: "nitgen", label: "Nitgen" },
  { value: "hikvision", label: "Hikvision" },
  { value: "dahua", label: "Dahua" },
];

export default function Devices() {
  const nav = useNavigate();
  const [items, setItems] = useState<Device[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [candidateOnly, setCandidateOnly] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Device | null>(null);
  const [busy, setBusy] = useState(false);

  const [form, setForm] = useState({
    ip_address: "",
    adapter_name: "generic_http",
    port: "",
    hostname: "",
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = { page: String(page), page_size: "25" };
      if (search) params.search = search;
      if (status) params.status = status;
      if (candidateOnly) params.candidate_only = "true";
      const res = await apiClient.devices(params);
      setItems(res.items);
      setTotal(res.total);
    } catch (e) {
      toast(String((e as Error).message), "err");
    } finally {
      setLoading(false);
    }
  }, [page, search, status, candidateOnly]);

  useEffect(() => {
    void load();
  }, [load]);

  const addDevice = async () => {
    const ipAddress = form.ip_address.trim();
    const duplicate = items.find((device) => device.ip_address === ipAddress);
    if (duplicate) {
      toast(`این IP قبلاً ثبت شده است: ${ipAddress}`, "err");
      return;
    }
    setBusy(true);
    try {
      const body: Record<string, unknown> = {
        ip_address: ipAddress,
        adapter_name: form.adapter_name,
      };
      if (form.port) body.port = Number(form.port);
      if (form.hostname.trim()) body.hostname = form.hostname.trim();
      const dev = await apiClient.createDevice(body);
      toast("دستگاه اضافه شد", "ok");
      setAddOpen(false);
      nav(`/devices/${dev.id}`);
    } catch (e) {
      const message = String((e as Error).message);
      toast(
        message.includes("already exists") || message.includes("قبلاً")
          ? `این IP قبلاً ثبت شده است: ${ipAddress}`
          : message,
        "err"
      );
    } finally {
      setBusy(false);
    }
  };

  const doDelete = async () => {
    if (!deleteTarget) return;
    setBusy(true);
    try {
      await apiClient.deleteDevice(deleteTarget.id);
      toast("دستگاه حذف شد", "ok");
      setDeleteTarget(null);
      void load();
    } catch (e) {
      toast(String((e as Error).message), "err");
    } finally {
      setBusy(false);
    }
  };

  const testDevice = async (d: Device) => {
    try {
      toast(`تست اتصال ${d.ip_address} در حال اجرا…`, "info");
      const r = await apiClient.testDevice(d.id);
      if (r && typeof r === "object" && "ok" in r && (r as { ok: boolean }).ok) {
        toast(`اتصال به ${d.ip_address} موفق بود`, "ok");
      } else {
        const detail = r && typeof r === "object" && "detail" in r ? String((r as { detail: string }).detail) : "ناموفق";
        toast(`اتصال ناموفق: ${detail}`, "err");
      }
      void load();
    } catch (e) {
      toast(String((e as Error).message), "err");
      void load();
    }
  };

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">دستگاه‌ها</h1>
          <div className="page-sub">
            {faNum(total)} دستگاه ثبت‌شده — برای جزئیات روی ردیف کلیک کنید
          </div>
        </div>
        <div className="page-actions">
          <button className="btn btn-primary" onClick={() => setAddOpen(true)}>
            + افزودن دستگاه (دستی)
          </button>
        </div>
      </div>

      <div className="filter-group">
        <input
          className="grow"
          placeholder="جستجوی IP / نام / مدل / برند / سریال…"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
          style={{ maxWidth: 340 }}
        />
        <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
          <option value="">همه وضعیت‌ها</option>
          <option value="VERIFIED">VERIFIED</option>
          <option value="DETECTED">DETECTED</option>
          <option value="POSSIBLE">POSSIBLE</option>
          <option value="ONLINE">ONLINE</option>
          <option value="OFFLINE">OFFLINE</option>
          <option value="UNKNOWN">UNKNOWN</option>
        </select>
        <label className="row gap" style={{ whiteSpace: "nowrap" }}>
          <input type="checkbox" checked={candidateOnly} onChange={(e) => { setCandidateOnly(e.target.checked); setPage(1); }} />
          فقط نامزدهای دستگاه تردد
        </label>
        <button className="btn btn-sm" onClick={() => { void load(); }}>
          تازه‌سازی
        </button>
      </div>

      <div className="card">
        <div className="card-body flush">
          {loading ? (
            <div className="page-center" style={{ height: 220 }}>
              <Spinner />
            </div>
          ) : items.length === 0 ? (
            <Empty text="دستگاهی یافت نشد — شبکه را اسکن کنید یا دستگاه را دستی اضافه نمایید" />
          ) : (
            <DataTable<Device>
              keyOf={(d) => d.id}
              onRowClick={(d) => nav(`/devices/${d.id}`)}
              columns={[
                {
                  key: "ip_address",
                  label: "IP",
                  render: (d) => <span className="mono">{d.ip_address}</span>,
                },
                { key: "hostname", label: "نام / میزبان", render: (d) => d.hostname || d.device_name || "—" },
                { key: "brand", label: "برند", render: (d) => d.brand || d.vendor || "—" },
                { key: "model", label: "مدل", render: (d) => d.model || "—" },
                {
                  key: "serial",
                  label: "سریال",
                  render: (d) => <span className="mono small">{d.serial_number || "—"}</span>,
                },
                { key: "status", label: "وضعیت", render: (d) => <RawBadge value={d.status} /> },
                { key: "detection_state", label: "تشخیص", render: (d) => <Badge value={d.detection_state} /> },
                {
                  key: "protocol",
                  label: "پروتکل / پورت",
                  render: (d) => (
                    <span>
                      <span className="mono small">{d.protocol_name || d.adapter_name || "—"}</span>
                      {d.port ? <span className="muted small"> :{d.port}</span> : null}
                    </span>
                  ),
                },
                { key: "last_seen", label: "آخرین حضور", render: (d) => fmtTime(d.last_seen_at) },
                {
                  key: "actions",
                  label: "عملیات",
                  render: (d) => (
                    <div className="row gap" onClick={(e) => e.stopPropagation()}>
                      <button className="btn btn-sm" onClick={() => nav(`/devices/${d.id}`)}>
                        جزئیات
                      </button>
                      <button className="btn btn-sm btn-soft" onClick={() => void testDevice(d)}>
                        تست اتصال
                      </button>
                      <button
                        className="btn btn-sm btn-danger"
                        onClick={() => setDeleteTarget(d)}
                        disabled={(d.last_error || "") ? false : false}
                      >
                        حذف
                      </button>
                    </div>
                  ),
                },
              ]}
              rows={items}
            />
          )}
        </div>
        <Pagination page={page} pageSize={25} total={total} onChange={setPage} />
      </div>

      <Modal open={addOpen} title="افزودن دستی دستگاه" onClose={() => setAddOpen(false)}>
        <div className="form-grid">
          <div className="span2">
            <Field label="آدرس IP" hint="آدرس داخل شبکه سازمان شما، e.g. 172.16.50.30">
              <input
                dir="ltr"
                placeholder="172.16.0.0/24 - فقط تک‌IP مجاز است"
                value={form.ip_address}
                onChange={(e) => setForm({ ...form, ip_address: e.target.value })}
              />
            </Field>
          </div>
          <div className="span2">
            <Field label="آداپتور (روش ارتباط)" hint="در صورت نداشتن شواهد، ZKTeco یا Generic را حدس نزنید — تشخیص توسط Discovery انجام می‌شود">
              <select value={form.adapter_name} onChange={(e) => setForm({ ...form, adapter_name: e.target.value })}>
                {ADAPTERS.map((a) => (
                  <option key={a.value} value={a.value}>
                    {a.label}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <Field label="پورت (اختیاری)">
            <input dir="ltr" placeholder="e.g. 4370" value={form.port} onChange={(e) => setForm({ ...form, port: e.target.value })} />
          </Field>
          <Field label="نام میزبان (اختیاری)">
            <input value={form.hostname} onChange={(e) => setForm({ ...form, hostname: e.target.value })} />
          </Field>
        </div>
        <div className="form-actions">
          <button className="btn" onClick={() => setAddOpen(false)}>
            انصراف
          </button>
          <button className="btn btn-primary" onClick={() => void addDevice()} disabled={busy || !form.ip_address.trim()}>
            {busy ? <Spinner small /> : "افزودن"}
          </button>
        </div>
      </Modal>

      <Confirm
        open={deleteTarget !== null}
        title="حذف دستگاه"
        danger
        busy={busy}
        message={
          <>
            آیا از حذف دستگاه <b className="mono">{deleteTarget?.ip_address}</b> مطمئن هستید؟ کاربران، ترددها و داده‌های
            خام مرتبط با آن نیز حذف خواهند شد. این عمل قابل بازگشت نیست.
          </>
        }
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => void doDelete()}
      />
    </div>
  );
}
