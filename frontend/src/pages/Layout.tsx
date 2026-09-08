import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { ROLE_LABEL } from "../lib/fa";

const NAV = [
  { to: "/", label: "داشبورد", icon: "▦" },
  { to: "/devices", label: "دستگاه‌ها", icon: "⏱" },
  { to: "/attendance", label: "ترددها", icon: "⇄" },
  { to: "/networks", label: "شبکه‌ها و اسکن", icon: "🌐" },
  { to: "/audit", label: "لاگ عملیات", icon: "📋" },
];

export default function Layout() {
  const { me, logout } = useAuth();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const role = me?.role || "viewer";

  const canAdmin = role === "admin";
  const items =
    role === "admin" ? [...NAV, { to: "/settings", label: "تنظیمات", icon: "⚙" }] : NAV;

  return (
    <div className={`shell${open ? " shell-open" : ""}`}>
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-icon">⏱</span>
          <div>
            <div className="brand-title">حضور و غیاب</div>
            <div className="brand-sub">مدیریت دستگاه‌ها</div>
          </div>
        </div>
        <nav className="nav">
          {items.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.to === "/"}
              className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
              onClick={() => setOpen(false)}
            >
              <span className="nav-icon">{n.icon}</span>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          {canAdmin && (
            <NavLink to="/settings/users" className="nav-link">
              <span className="nav-icon">👤</span> کاربران سامانه
            </NavLink>
          )}
          <div className="user-chip">
            <div>
              <b>{me?.display_name || me?.username}</b>
              <span className="muted small">{ROLE_LABEL[me?.role || "viewer"]}</span>
            </div>
            <button
              className="btn btn-ghost btn-sm"
              onClick={async () => {
                await logout();
                nav("/login");
              }}
            >
              خروج
            </button>
          </div>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <button className="btn btn-ghost burger" onClick={() => setOpen(!open)}>
            ☰
          </button>
          <div className="spacer" />
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
