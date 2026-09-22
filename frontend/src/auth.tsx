import { Navigate, Outlet } from "react-router-dom";
import { getToken, getStoredUser, type Role } from "./api";

export function RequireAuth({ roles }: { roles?: Role[] }) {
  const token = getToken();
  const user = getStoredUser();
  if (!token || !user) return <Navigate to="/login" replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to="/" replace />;
  return <Outlet />;
}
