import { Navigate } from "react-router-dom";

import { useAuth } from "./AuthProvider";

export function RequirePermission({ permission, children }: { permission: string; children: React.ReactNode }) {
  const { hasPermission } = useAuth();
  if (!hasPermission(permission)) {
    return <Navigate to="/app/forbidden" replace />;
  }
  return <>{children}</>;
}
