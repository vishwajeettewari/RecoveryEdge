# Recovery OS UI Runbook

## Start locally

1. Install frontend deps:

```bash
npm --prefix frontend-react install
```

2. Start backend + frontend together:

```bash
make dev
```

- Backend: `http://127.0.0.1:8000`
- React UI: `http://127.0.0.1:5173/app`

## Demo accounts

- `admin / admin123` (ADMIN)
- `mgr / mgr123` (COLLECTIONS_MANAGER)
- `agent / agent123` (CALLING_AGENT)
- `ceo / ceo123` (CEO)
- `cfo / cfo123` (CFO)
- `comp / comp123` (COMPLIANCE_OFFICER)
- `viewer / viewer123` (VIEWER)

## Click-through demo

1. Login as `admin`.
2. Open **Portfolios & Campaigns**.
3. Upload CSV/XLSX, map fields, validate, preview, launch campaign.
4. Open **Workbench (Supervisor)** and verify tasks appear in state lanes.
5. Open **Calling Console (Agent)** to process assigned tasks and capture PTP/callback/escalation.
6. Open **Alerts & Compliance** to ACK/Assign/Resolve alerts and manage rules.
7. Open **Reports** to generate and download JSON/CSV reports.
8. Open **Integrations** (when `PILOT_MODE=1`) and resolve conflicts.

## Role sanity checks

- `agent`: should land on `/app/calling`, cannot access Users/Settings.
- `ceo`: can access Overview/Workbench(read-only)/Alerts(read-only)/Reports/Integrations(read-only).
- `cfo`: reports + overview, no task mutation.

## Backend tests

```bash
pytest -q
```

## Frontend tests

```bash
npm --prefix frontend-react run test -- --run
```
