import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { STATUS_LABEL } from "../lib/fa";

// --- toast ---------------------------------------------------------------

let pushToast: (kind: "ok" | "err" | "info", msg: string) => void = () => undefined;

export function toast(msg: string, kind: "ok" | "err" | "info" = "info") {
  pushToast(kind, msg);
}

export function ToastHost() {
  const [items, setItems] = useState<{ id: number; kind: string; msg: string }[]>([]);
  useEffect(() => {
    let id = 0;
    pushToast = (kind, msg) => {
      const my = ++id;
      setItems((l) => [...l, { id: my, kind, msg }]);
      setTimeout(() => setItems((l) => l.filter((x) => x.id !== my)), 4200);
    };
    return () => {
      pushToast = () => undefined;
    };
  }, []);
  return (
    <div className="toast-host">
      {items.map((t) => (
        <div key={t.id} className={`toast toast-${t.kind}`}>
          {t.msg}
        </div>
      ))}
    </div>
  );
}

// --- spinner / empty -------------------------------------------------------

export function Spinner({ small = false }: { small?: boolean }) {
  return <span className={`spinner${small ? " spinner-sm" : ""}`} aria-label="loading" />;
}

export function Empty({ text }: { text: string }) {
  return <div className="empty">{text}</div>;
}

// --- badge -----------------------------------------------------------------

const COLORS: Record<string, string> = {
  VERIFIED: "green",
  ONLINE: "green",
  SUCCESS: "green",
  COMPLETED: "green",
  RUNNING: "blue",
  PENDING: "blue",
  DETECTED: "blue",
  POSSIBLE: "amber",
  OFFLINE: "red",
  FAILED: "red",
  CANCELLED: "gray",
  UNKNOWN: "gray",
  PARTIAL: "amber",
  ERROR: "red",
};

export function Badge({ value, custom }: { value: string; custom?: string }) {
  const color = custom || COLORS[value] || "gray";
  return (
    <span className={`badge badge-${color}`}>
      {STATUS_LABEL[value] || custom ? (custom ? value : value) : value}
    </span>
  );
}

export function RawBadge({ value, label, custom }: { value: string; label?: string; custom?: string }) {
  const color = custom || COLORS[value] || "gray";
  return <span className={`badge badge-${color}`}>{label || value}</span>;
}

// --- modal ---------------------------------------------------------------

export function Modal({
  open,
  title,
  onClose,
  children,
  wide = false,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
}) {
  if (!open) return null;
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className={`modal${wide ? " modal-wide" : ""}`} onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>{title}</h3>
          <button className="btn btn-ghost" onClick={onClose} aria-label="بستن">
            ✕
          </button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

export function Confirm({
  open,
  title,
  message,
  danger = false,
  onCancel,
  onConfirm,
  busy = false,
}: {
  open: boolean;
  title: string;
  message: ReactNode;
  danger?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
  busy?: boolean;
}) {
  return (
    <Modal open={open} title={title} onClose={onCancel}>
      <div className="confirm-text">{message}</div>
      <div className="row gap end">
        <button className="btn" onClick={onCancel} disabled={busy}>
          انصراف
        </button>
        <button className={`btn ${danger ? "btn-danger" : "btn-primary"}`} onClick={onConfirm} disabled={busy}>
          {busy ? <Spinner small /> : "تأیید"}
        </button>
      </div>
    </Modal>
  );
}

// --- stat card --------------------------------------------------------------

export function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: ReactNode;
  tone?: string;
}) {
  return (
    <div className={`stat stat-${tone || ""}`}>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

// --- tabs -------------------------------------------------------------------

export function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: { id: string; label: string }[];
  active: string;
  onChange: (id: string) => void;
}) {
  return (
    <div className="tabs">
      {tabs.map((t) => (
        <button
          key={t.id}
          className={`tab${active === t.id ? " tab-active" : ""}`}
          onClick={() => onChange(t.id)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

// --- table --------------------------------------------------------------------

export function DataTable<T>({
  columns,
  rows,
  empty = "داده‌ای موجود نیست",
  onRowClick,
  keyOf,
}: {
  columns: { key?: string; label: string; render?: (row: T) => ReactNode; className?: string }[];
  rows: T[];
  empty?: string;
  onRowClick?: (row: T) => void;
  keyOf?: (row: T) => string;
}) {
  if (rows.length === 0) return <Empty text={empty} />;
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            {columns.map((c, i) => (
              <th key={c.key || i} className={c.className || ""}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr
              key={keyOf ? keyOf(row) : String((row as { id?: string }).id || ri)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={onRowClick ? "clickable" : ""}
            >
              {columns.map((c, ci) => (
                <td key={ci} className={c.className || ""}>
                  {c.render ? c.render(row) : String((row as Record<string, unknown>)[c.key || ""] ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Pagination({
  page,
  pageSize,
  total,
  onChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  onChange: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="pagination">
      <span>
        صفحه {page} از {pages} — مجموع {total} رکورد
      </span>
      <div className="row gap">
        <button className="btn btn-sm" disabled={page <= 1} onClick={() => onChange(page - 1)}>
          قبلی
        </button>
        <button className="btn btn-sm" disabled={page >= pages} onClick={() => onChange(page + 1)}>
          بعدی
        </button>
      </div>
    </div>
  );
}

export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint ? <span className="field-hint">{hint}</span> : null}
    </label>
  );
}

export function JsonView({ value }: { value: unknown }) {
  return (
    <pre className="json-view" dir="ltr">
      {typeof value === "string" ? value : JSON.stringify(value, null, 2)}
    </pre>
  );
}
