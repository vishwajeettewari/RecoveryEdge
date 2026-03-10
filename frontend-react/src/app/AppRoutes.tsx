import { Navigate, Route, Routes } from "react-router-dom";

import { RequireAuth } from "../auth/RequireAuth";
import { RequirePermission } from "../auth/RequirePermission";
import { RequireRole } from "../auth/RequireRole";
import { PERMS, ROLES } from "../auth/roles";
import { useAuth } from "../auth/AuthProvider";
import { AlertsPage } from "../features/alerts/AlertsPage";
import { CallingConsolePage } from "../features/calling/CallingConsolePage";
import { CommandCenterPage } from "../features/command-center/CommandCenterPage";
import { ControlLayerPage } from "../features/control/ControlLayerPage";
import { ForgotPasswordPage } from "../features/auth/ForgotPasswordPage";
import { LoginPage } from "../features/auth/LoginPage";
import { IntegrationsPage } from "../features/integrations/IntegrationsPage";
import { OverviewPage } from "../features/overview/OverviewPage";
import { RiskPortfolioPage } from "../features/overview/RiskPortfolioPage";
import { PortfolioPage } from "../features/portfolio/PortfolioPage";
import { ProfilePage } from "../features/profile/ProfilePage";
import { ReportsPage } from "../features/reports/ReportsPage";
import { SettingsPage } from "../features/settings/SettingsPage";
import { ForbiddenPage } from "../features/system/ForbiddenPage";
import { UsersPage } from "../features/users/UsersPage";
import { WorkbenchPage } from "../features/workbench/WorkbenchPage";
import { AppShellLayout } from "./AppShellLayout";

function IndexRedirect() {
  const { defaultLanding } = useAuth();
  return <Navigate to={defaultLanding} replace />;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/app" replace />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/app/login" element={<Navigate to="/login" replace />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />

      <Route element={<RequireAuth />}>
        <Route path="/app" element={<AppShellLayout />}>
          <Route index element={<IndexRedirect />} />

          <Route
            path="dashboard"
            element={
              <RequirePermission permission={PERMS.VIEW_DASHBOARD}>
                <OverviewPage />
              </RequirePermission>
            }
          />

          <Route
            path="risk-portfolio"
            element={
              <RequirePermission permission={PERMS.VIEW_DASHBOARD}>
                <RiskPortfolioPage />
              </RequirePermission>
            }
          />

          <Route
            path="command-center"
            element={
              <RequirePermission permission={PERMS.VIEW_DASHBOARD}>
                <CommandCenterPage />
              </RequirePermission>
            }
          />

          <Route
            path="control"
            element={
              <RequirePermission permission={PERMS.VIEW_DASHBOARD}>
                <ControlLayerPage />
              </RequirePermission>
            }
          />

          <Route
            path="portfolio"
            element={
              <RequirePermission permission={PERMS.PORTFOLIO_MANAGE}>
                <PortfolioPage />
              </RequirePermission>
            }
          />

          <Route
            path="workbench"
            element={
              <RequirePermission permission={PERMS.WORKBENCH_VIEW}>
                <WorkbenchPage />
              </RequirePermission>
            }
          />

          <Route
            path="calling"
            element={
              <RequirePermission permission={PERMS.WORKBENCH_VIEW}>
                <RequireRole allowed={[ROLES.ADMIN, ROLES.COLLECTIONS_MANAGER, ROLES.CALLING_AGENT]}>
                  <CallingConsolePage />
                </RequireRole>
              </RequirePermission>
            }
          />

          <Route
            path="alerts"
            element={
              <RequirePermission permission={PERMS.ALERTS_VIEW}>
                <AlertsPage />
              </RequirePermission>
            }
          />

          <Route
            path="reports"
            element={
              <RequirePermission permission={PERMS.REPORTS_VIEW}>
                <ReportsPage />
              </RequirePermission>
            }
          />

          <Route
            path="integrations"
            element={
              <RequirePermission permission={PERMS.INTEGRATIONS_VIEW}>
                <IntegrationsPage />
              </RequirePermission>
            }
          />

          <Route
            path="users"
            element={
              <RequirePermission permission={PERMS.USERS_MANAGE}>
                <UsersPage />
              </RequirePermission>
            }
          />

          <Route
            path="settings"
            element={
              <RequireRole allowed={[ROLES.ADMIN]}>
                <SettingsPage />
              </RequireRole>
            }
          />

          <Route path="profile" element={<ProfilePage />} />
          <Route path="forbidden" element={<ForbiddenPage />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/app" replace />} />
    </Routes>
  );
}
