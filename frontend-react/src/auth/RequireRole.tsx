import { Navigate } from "react-router-dom";

import { useAuth } from "./AuthProvider";

export function RequireRole({ allowed, children }: { allowed: string[]; children: React.ReactNode }) {
  const { role } = useAuth();
  if (!allowed.includes((role || "").toUpperCase())) {
    return <Navigate to="/app/forbidden" replace />;
  }
  return <>{children}</>;
}
