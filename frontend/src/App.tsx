import { useEffect } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth";
import { Spinner } from "./components/ui";
import Layout from "./pages/Layout";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Devices from "./pages/Devices";
import DeviceDetail from "./pages/DeviceDetail";
import Networks from "./pages/Networks";
import Attendance from "./pages/Attendance";
import Audit from "./pages/Audit";
import Settings from "./pages/Settings";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { me, loading } = useAuth();
  const loc = useLocation();
  if (loading)
    return (
      <div className="page-center">
        <Spinner />
      </div>
    );
  if (!me) return <Navigate to="/login" state={{ from: loc.pathname }} replace />;
  return <>{children}</>;
}

export default function App() {
  const { me, refresh } = useAuth();
  useEffect(() => {
    if (!me) return;
    const t = setInterval(() => void refresh(), 60_000);
    return () => clearInterval(t);
  }, [me, refresh]);
  useEffect(() => {
    document.title = me ? "سامانه حضور و غیاب" : "ورود | سامانه حضور و غیاب";
  }, [me]);
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="devices" element={<Devices />} />
        <Route path="devices/:id" element={<DeviceDetail />} />
        <Route path="attendance" element={<Attendance />} />
        <Route path="networks" element={<Networks />} />
        <Route path="audit" element={<Audit />} />
        <Route path="settings" element={<Settings />} />
        <Route path="settings/users" element={<Settings tab="users" />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
