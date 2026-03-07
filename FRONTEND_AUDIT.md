# Frontend Audit (Current State)

Date: 2026-02-11
Scope: `frontend-react` + auth wiring against `web_app.py`

## Current Routes

- `/login` (credentials form)
- `/app/dashboard`
- `/app/portfolio`
- `/app/workbench`
- `/app/alerts`
- `/app/reports`
- `/app/integrations`
- `/app/users`
- `/app/settings`
- `/app/profile`
- `/app/forbidden`

## Current Frontend Architecture

- Flat structure with `src/pages`, `src/components`, `src/lib`, `src/providers`
- Mantine + React Query + React Hook Form is already present
- Permission checks exist (`RequirePermission`) and backend RBAC is wired
- Build token + DEMO/PILOT pills are visible in header

## Missing Screens / Product Flows

- Missing first-class **Calling Console** (`/app/calling`) for agent operations
- Missing branded product shell (logo lockup, stronger product identity)
- Missing role-aware default landing behavior (agent should land on calling console)
- Missing "Forgot password" flow screen
- Missing clear module IA labels aligned to NBFC operations floor language

## UX Problems Observed

- UI looks functional but not product-grade (minimal visual hierarchy, weak information scent)
- Dashboard is metric-heavy but lacks trend and portfolio narrative
- Portfolio flow is technically complete but visually dense and not guided enough
- Workbench drawer/action UX is usable but not optimized for high-volume supervision
- Alerts and Integrations are data tables first, not workflow-first surfaces
- Navigation labels are generic and don’t map cleanly to persona workflows
- No explicit agent-focused command center experience

## Fix List (Implementation Targets)

1. Introduce branded app shell with TuringEdge logo, improved spacing, typography, and role-aware nav.
2. Add a dedicated Calling Console module with queue, conversation panel, and compliance guidance.
3. Re-organize frontend code into `src/app`, `src/components`, `src/features/*`, `src/auth`, `src/api`, `src/theme`.
4. Implement route-level role guards (`RequireRole`) and role->permission mapping constants.
5. Improve Dashboard with operations story: KPI tiles + trend chart + bucket visualization.
6. Refine Portfolio, Workbench, Alerts, Reports, Integrations, Users pages into clearer product workflows.
7. Add docs: `RUNBOOK_UI.md`, `ROLE_MATRIX.md`.
8. Add minimal UI tests for route guard, login flow, and calling console assigned queue rendering.
