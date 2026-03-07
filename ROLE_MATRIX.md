# Role Matrix

## Roles

- ADMIN
- CEO
- CFO
- COLLECTIONS_MANAGER
- CALLING_AGENT
- COMPLIANCE_OFFICER
- VIEWER

## Permission mapping

- `VIEW_DASHBOARD`
- `PORTFOLIO_MANAGE`
- `WORKBENCH_VIEW`
- `WORKBENCH_MUTATE`
- `ALERTS_VIEW`
- `ALERTS_MUTATE`
- `ALERT_RULES_EDIT`
- `REPORTS_VIEW`
- `REPORTS_SCHEDULE`
- `INTEGRATIONS_VIEW`
- `INTEGRATIONS_RESOLVE_CONFLICTS`
- `USERS_MANAGE`
- `SYSTEM_VIEW_BUILD_INFO`

## Effective access

- ADMIN: full access across all modules and user/settings management.
- CEO: overview, reports, alerts (read), workbench (read), integrations (read).
- CFO: overview + reports + workbench read; no task mutation.
- COLLECTIONS_MANAGER: portfolio launch, workbench mutate, alerts mutate, reports schedule, integrations resolve.
- CALLING_AGENT: calling console + assigned tasks updates only; no bulk updates, no admin/config screens.
- COMPLIANCE_OFFICER: alerts/compliance operations, rules edit, workbench read.
- VIEWER: read-only operational visibility.

## Route notes

- Calling Console default landing for CALLING_AGENT.
- Integrations module shown only when `PILOT_MODE=1` and role has integrations permission.
- `/app/users` and `/app/settings` are admin-only.
