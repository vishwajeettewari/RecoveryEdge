# Gamma Client Demo Pack

## Purpose

This pack is for creating a client-facing Gamma deck for the TuringEdge collections product. It is grounded in the current product surfaces and demo environment in this repository.

The buyer story to optimize for:

- He cares about early-bucket containment.
- He specifically values disciplined PTP tracking and timely follow-ups.
- He wants to see how teams handle the period immediately after a missed PTP.
- He will respond well to an operations-first narrative, not generic AI claims.

The deck should therefore position the product as an operational control system, not just a dialer or dashboard.

## Product Name To Use

- TuringEdge Recovery OS
- Optional subtitle: Agentic Operations Copilot for Early Bucket Collections

## Available Assets In Repo

Use these existing assets directly in Gamma or in the deck assembly workflow.

### Brand assets

- Primary logo: `frontend-react/src/assets/turingedge-logo.png`
- Logo mark: `frontend-react/src/assets/logo-mark.svg`
- Alternate logo: `frontend/assets/actual_logo_te.png`

### Demo data assets

- Sample customer spreadsheet: `data/customers.xlsx`
- Demo export workbook: `data/demo_export.xlsx`
- Demo output workbook: `data/demo_output.xlsx`
- Recent report export JSON: `data/reports/2026-03-09/cmp-e9a3c028df-rpt-b372300d931b.json`
- Recent report export CSV: `data/reports/2026-03-09/cmp-e9a3c028df-rpt-b372300d931b.csv`
- Recent report export JSON: `data/reports/2026-03-09/cmp-68e8228ad0-rpt-6fad85995b12.json`
- Recent report export CSV: `data/reports/2026-03-09/cmp-68e8228ad0-rpt-6fad85995b12.csv`

### Demo credentials

- Admin: `admin / admin123`
- Collections manager: `mgr / mgr123`
- Agent: `agent / agent123`
- CEO: `ceo / ceo123`
- CFO: `cfo / cfo123`
- Compliance: `comp / comp123`

## Product Surfaces To Showcase

The deck should visually cover these modules:

1. Login / branded shell
2. Early Bucket Control Room
3. Operations Copilot
4. Portfolios and campaign launch
5. Supervisor Workbench
6. Calling Console with live transcript and commitment capture
7. Alerts and compliance inbox
8. Reports and download center
9. Integrations and reconciliation
10. Users, role-based access, and governance

## Generated Screenshot Assets

These screenshots have now been captured from the live demo app and saved in `marketing/screenshots`.

### Captured screens

- `02-overview-control-room.png`
  Route: `/app/dashboard`
  What to capture: Early Bucket Control Room with KPI cards, PTP discipline section, roll-forward area, and queue summary visible.
  Why it matters: proves the product is tracking operational discipline, not just activity.

- `03-ops-copilot-hero.png`
  Route: `/app/control`
  Role: `admin`
  What to capture: hero section, campaign scope panel, summary strip, and the right-rail decision spotlight.
  Why it matters: establishes the product's differentiated agentic control layer.

- `04-ops-copilot-response.png`
  Route: `/app/control`
  Role: `admin`
  What to capture: one assistant response showing the answer panel, evidence blocks, and recommended actions.
  Why it matters: proves the copilot is grounded and actionable.

- `05-portfolio-launch.png`
  Route: `/app/portfolio`
  Role: `admin`
  What to capture: upload plus mapping or validation step with spreadsheet preview visible.
  Why it matters: shows that the buyer can upload a portfolio sheet and operationalize it quickly.

- `06-workbench-queue.png`
  Route: `/app/workbench`
  Role: `admin`
  What to capture: queue lanes by state plus one task detail drawer open if possible.
  Why it matters: shows supervisor control and audit-safe intervention.

- `07-calling-console-live.png`
  Route: `/app/calling`
  Role: `admin` or `agent`
  What to capture: borrower brief, live transcript, commitment card, and action buttons.
  Why it matters: this is where the promise is captured and the follow-up trail begins.

- `08-calling-console-commitment.png`
  Route: `/app/calling`
  Role: `admin` or `agent`
  What to capture: the commitment capture panel with PTP date, callback date/time, and disposition buttons visible.
  Why it matters: it directly addresses the buyer's interest in consistent PTP tracking and follow-up discipline.

- `09-alerts-compliance.png`
  Route: `/app/alerts`
  Role: `admin` or `comp`
  What to capture: inbox filters, alert table, and selected alert detail.
  Why it matters: shows operational exceptions and compliance control in one place.

- `10-reports-download-center.png`
  Route: `/app/reports`
  Role: `admin` or `cfo`
  What to capture: report scheduling and the download center table.
  Why it matters: demonstrates executive reporting and operational auditability.

- `11-integrations-reconciliation.png`
  Route: `/app/integrations`
  Role: `admin`
  What to capture: reconciliation tabs or conflict resolution view.
  Why it matters: proves the platform can fit into an existing LMS/CRM environment.

- `12-users-access.png`
  Route: `/app/users`
  What to capture: users table or create-user modal.
  Why it matters: supports enterprise readiness and role-based control.

### Still optional to refine manually

- `01-login-hero.png` can be manually retaken if you want a cleaner login visual without Safari password UI.
- `08-calling-console-commitment.png` is usable, but a manual scrolled recapture would make it stronger if you want a tighter crop on the lower-page commitment detail.
- Prefer desktop screenshots at 1440px-wide browser windows.
- Keep the branded shell visible in at least half of the screenshots.
- If demo numbers are thin, crop for structure and flow, not absolute values.
- Use the new Operations Copilot visuals as the hero of the deck.

## Suggested Graphic Video Asset

There is no hosted product video link in the repo today. For the client deck, create a short 60-90 second Loom or Drive-hosted walkthrough and place it on a dedicated slide.

### Recommended video CTA

- Headline: `Watch the 90-second walkthrough`
- CTA label: `Open product demo`
- Link placeholder: `[INSERT LOOM OR DRIVE LINK HERE]`

### Video storyboard

- `0:00 - 0:08`
  Show branded login and app shell.
  Voiceover: "TuringEdge Recovery OS gives collections teams one control layer from portfolio upload to governed action."

- `0:08 - 0:20`
  Show portfolio upload and launch.
  Voiceover: "A portfolio sheet comes in, fields are mapped, validated, and launched into an operational campaign."

- `0:20 - 0:35`
  Show Calling Console and commitment capture.
  Voiceover: "Agents capture PTPs and callbacks directly from the desk, creating a reliable commitment trail."

- `0:35 - 0:50`
  Show Early Bucket Control Room.
  Voiceover: "Supervisors see discipline, missed PTP pressure, roll-forward risk, and recovery potential in one view."

- `0:50 - 1:10`
  Show Operations Copilot with recommendations.
  Voiceover: "The agentic copilot explains what is working by campaign, bucket, agent, or account, then proposes governed changes."

- `1:10 - 1:20`
  Show Alerts, Reports, and Integrations.
  Voiceover: "Compliance, reporting, and reconciliation stay connected to the same operating system."

## Product Capabilities To Highlight

Use these repeatedly across the deck.

### Core operating capabilities

- Portfolio upload from CSV or XLSX
- Field mapping, validation, preview, and exclusions
- Campaign launch with retry and throttle controls
- Supervisor queue management by campaign, state, and DPD bucket
- Calling Console with live voice support, transcript, and commitment capture
- PTP and callback tracking tied to downstream operations
- Missed-PTP follow-up orchestration and alerting
- Early bucket control room for discipline, containment, recovery, and queue health
- Agentic operations copilot for diagnosis, simulation, and next-best actions
- Approval-aware execution for strategy changes and experiments
- Alerts inbox and compliance rule management
- Reports scheduling and export center
- Integrations and reconciliation with LMS or CRM workflows
- Role-based access for admin, manager, agent, CFO, CEO, and compliance users

### Strongest product claims

- Not just a dialer: it is a collections operating system
- Not just a dashboard: it recommends and routes action
- Not just activity tracking: it measures discipline after commitment capture
- Not just AI chat: recommendations are grounded in campaign, bucket, agent, and customer metrics
- Not just experimentation: changes can be approval-governed for enterprise control

## Why This Product Is Better

Frame differentiation against standard collections tooling.

- Standard tools show call volumes and dispositions; TuringEdge closes the loop from portfolio ingest to governed execution.
- Standard dashboards describe what happened; TuringEdge explains what is working, what is leaking, and what to change next.
- Standard follow-up processes break after a PTP is missed; TuringEdge is designed around follow-up discipline, alerting, and containment.
- Standard collections systems split agents, supervisors, compliance, and leadership into separate tools; TuringEdge gives each role the right control layer in one platform.
- Standard AI claims are vague; TuringEdge exposes evidence, confidence, and action payloads directly in the copilot experience.

## Recommended Deck Narrative

The deck should follow this arc:

1. Why early-bucket collections break
2. Why missed PTP follow-up is the real control point
3. What TuringEdge Recovery OS is
4. How the operating flow works end to end
5. How the Operations Copilot changes decision-making
6. How the product improves discipline, containment, and recoveries
7. Why it is enterprise-ready
8. How a client pilot would work

## Gamma Master Prompt

Copy the prompt from `marketing/gamma_master_prompt.md`.

## Notes For Final Client Deck

- Use clean enterprise language, not startup hype.
- Make the Operations Copilot the hero, but keep it tied to real operations and follow-up discipline.
- If the buyer is operations-heavy, lead with control room, calling console, and post-PTP workflow before broader AI messaging.
- If screenshots still use sparse sandbox data, anchor the story on capabilities and workflow, not on the raw sample totals.
