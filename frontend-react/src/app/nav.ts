import {
  Bell,
  Bot,
  BriefcaseBusiness,
  ChartColumnBig,
  CircleUserRound,
  FileUp,
  Gauge,
  LifeBuoy,
  PhoneCall,
  Plug,
  Settings,
  Users,
} from "lucide-react";
import type { ComponentType } from "react";

import { PERMS, ROLES } from "../auth/roles";

export interface NavItem {
  to: string;
  label: string;
  icon: ComponentType<{ size?: number; strokeWidth?: number }>;
  permission?: string;
  roles?: string[];
  pilotOnly?: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { to: "/app/dashboard", label: "Home / Overview", icon: Gauge, permission: PERMS.VIEW_DASHBOARD },
  { to: "/app/control", label: "Operations Copilot", icon: Bot, permission: PERMS.VIEW_DASHBOARD },
  { to: "/app/portfolio", label: "Portfolios & Campaigns", icon: FileUp, permission: PERMS.PORTFOLIO_MANAGE },
  { to: "/app/workbench", label: "Workbench (Supervisor)", icon: BriefcaseBusiness, permission: PERMS.WORKBENCH_VIEW },
  { to: "/app/calling", label: "Calling Console (Agent)", icon: PhoneCall, permission: PERMS.WORKBENCH_VIEW },
  { to: "/app/alerts", label: "Alerts & Compliance", icon: Bell, permission: PERMS.ALERTS_VIEW },
  { to: "/app/reports", label: "Reports", icon: ChartColumnBig, permission: PERMS.REPORTS_VIEW },
  { to: "/app/integrations", label: "Integrations", icon: Plug, permission: PERMS.INTEGRATIONS_VIEW, pilotOnly: true },
  { to: "/app/users", label: "Users & Access", icon: Users, permission: PERMS.USERS_MANAGE },
  { to: "/app/settings", label: "Settings", icon: Settings, roles: [ROLES.ADMIN] },
  { to: "/app/profile", label: "Profile", icon: CircleUserRound },
  { to: "/app/forbidden", label: "Forbidden", icon: LifeBuoy, roles: [] },
];

export function canShowNavItem(opts: {
  item: NavItem;
  permissions: string[];
  role: string;
  pilotMode: boolean;
}): boolean {
  const { item, permissions, role, pilotMode } = opts;
  if (item.to === "/app/forbidden") {
    return false;
  }
  if (item.pilotOnly && !pilotMode) {
    return false;
  }
  if (item.roles && !item.roles.includes((role || "").toUpperCase())) {
    return false;
  }
  if (item.permission && !permissions.includes(item.permission)) {
    return false;
  }
  if ((role || "").toUpperCase() === ROLES.CALLING_AGENT && item.to === "/app/dashboard") {
    return false;
  }
  return true;
}
