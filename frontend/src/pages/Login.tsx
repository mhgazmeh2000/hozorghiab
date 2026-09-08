import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { Spinner, toast } from "../components/ui";

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await login(username.trim(), password.trim());
      toast("خوش آمدید", "ok");
      nav("/");
    } catch (err) {
      toast(String((err as Error).message || err), "err");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-screen">
      <form className="login-card" onSubmit={submit}>
        <div className="login-logo">⏱</div>
        <h1>سامانه حضور و غیاب</h1>
        <p className="muted">مدیریت و مانیتورینگ دستگاه‌های تردد شبکه‌ای</p>
        <label className="field">
          <span className="field-label">نام کاربری</span>
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value.trim())}
            autoFocus
            required
            autoComplete="username"
            dir="ltr"
          />
        </label>
        <label className="field">
          <span className="field-label">رمز عبور</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value.trim())}
            required
            autoComplete="current-password"
            dir="ltr"
          />
        </label>
        <button className="btn btn-primary btn-block" disabled={busy}>
          {busy ? <Spinner small /> : "ورود"}
        </button>
        <p className="muted small">نقش‌ها: admin (مدیر کامل) • operator (خواندن + همگام‌سازی) • viewer (فقط خواندن)</p>
      </form>
    </div>
  );
}
