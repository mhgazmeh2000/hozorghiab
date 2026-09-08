export const STATUS_LABEL: Record<string, string> = {
  UNKNOWN: "ناشناخته",
  OFFLINE: "آفلاین",
  ONLINE: "آنلاین",
  POSSIBLE: "احتمالی",
  DETECTED: "تشخیص داده‌شده",
  VERIFIED: "تأییدشده",
  PENDING: "در انتظار",
  RUNNING: "در حال اجرا",
  COMPLETED: "تکمیل‌شده",
  FAILED: "ناموفق",
  CANCELLED: "لغوشده",
  PARTIAL: "ناقص",
  SUCCESS: "موفق",
};

export const EVENT_TYPE_LABEL: Record<string, string> = {
  CHECK_IN: "ورود",
  CHECK_OUT: "خروج",
  BREAK_IN: "پایان استراحت",
  BREAK_OUT: "شروع استراحت",
  OVERTIME_IN: "ورود اضافه‌کاری",
  OVERTIME_OUT: "خروج اضافه‌کاری",
  UNKNOWN: "نامشخص",
};

export const VERIFY_LABEL: Record<string, string> = {
  PASSWORD: "رمز",
  FINGERPRINT: "اثرانگشت",
  CARD: "کارت",
  FACE: "چهره",
  PIN: "PIN",
  UNKNOWN: "نامشخص",
};

export const ROLE_LABEL: Record<string, string> = {
  admin: "مدیر",
  operator: "اپراتور",
  viewer: "بیننده",
};

export const ACTION_LABEL: Record<string, string> = {
  login: "ورود به سامانه",
  logout: "خروج از سامانه",
  scan: "اسکن شبکه",
  discovery: "کشف دستگاه",
  connect: "اتصال به دستگاه",
  disconnect: "قطع اتصال",
  sync: "همگام‌سازی",
  user_import: "درون‌ریزی کاربران",
  user_export: "برون‌بری کاربران",
  user_create: "ایجاد کاربر",
  user_update: "ویرایش کاربر",
  user_delete: "حذف کاربر",
  attendance_import: "درون‌ریزی تردد",
  attendance_export: "برون‌بری تردد",
  attendance_clear: "پاک‌سازی تردد دستگاه",
  device_config: "پیکربندی دستگاه",
  network_config: "پیکربندی شبکه",
  settings_update: "تغییر تنظیمات",
  read: "خواندن",
  password_change: "تغییر رمز",
  other: "سایر",
};

export const CAP_LABEL: Record<string, string> = {
  device_info: "اطلاعات دستگاه",
  read_users: "خواندن کاربران",
  read_user: "خواندن تک‌کاربر",
  create_users: "ایجاد کاربر",
  update_users: "ویرایش کاربر",
  delete_users: "حذف کاربر",
  read_logs: "خواندن تردد",
  delete_logs: "حذف تردد",
  get_log_count: "شمارش تردد",
  sync_users_to_device: "ارسال کاربران به دستگاه",
  sync_users_from_device: "دریافت کاربران از دستگاه",
  realtime_events: "رویداد بلادرنگ",
  fingerprint: "اثرانگشت",
  face: "چهره",
  card: "کارت",
  password: "رمز / PIN",
  set_time: "تنظیم ساعت",
  get_time: "خواندن ساعت",
  clear_data: "پاک‌سازی داده",
  read_templates: "خواندن قالب‌های زیستی",
  write_templates: "نوشتن قالب‌های زیستی",
  read_operational_logs: "لاگ عملیاتی",
};

export function fmtTime(v?: string | null): string {
  if (!v) return "—";
  try {
    return new Date(v).toLocaleString("fa-IR", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return v;
  }
}

export function fmtDate(v?: string | null): string {
  if (!v) return "—";
  try {
    return new Date(v).toLocaleDateString("fa-IR");
  } catch {
    return v;
  }
}

export function fmtTimeOnly(v: string): string {
  try {
    return new Date(v).toLocaleTimeString("fa-IR", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return v;
  }
}

export function faNum(v: number | string | null | undefined): string {
  if (v === null || v === undefined) return "—";
  const digits = "۰۱۲۳۴۵۶۷۸۹";
  return String(v).replace(/[0-9]/g, (d) => digits[Number(d)]);
}

export function pct(v: number): string {
  return `${faNum(Math.round(v))}٪`;
}

export function toLocalInputDate(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}
