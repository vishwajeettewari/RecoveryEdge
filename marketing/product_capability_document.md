# TuringEdge Recovery OS

## Product Capability Document

Date: 2026-03-09  
Audience: Internal team, sales, product, operations, leadership

## 1. Executive Summary

TuringEdge Recovery OS is a collections operating system for early-bucket recovery teams. It is designed to turn static portfolio files into live campaigns, route work across supervisors and agents, capture borrower commitments, enforce follow-up discipline after a promise-to-pay, and give operations leaders a control layer to understand what is working and what should change next.

The product is differentiated by one core principle: it does not stop at call activity or reporting. It closes the loop from portfolio ingestion to governed operational action.

## 2. Product Positioning

TuringEdge Recovery OS should be positioned as:

- A collections operating system, not just a dialer
- An operations control layer, not just a dashboard
- A commitment and follow-up discipline engine, not just a contact management tool
- A grounded agentic copilot, not just AI chat

## 3. Primary Business Problems Solved

- Slow conversion of lender portfolio sheets into executable collections campaigns
- Weak visibility into early-bucket performance by campaign, bucket, agent, and account
- Poor discipline after borrower commitments are captured
- Delayed re-engagement after missed PTPs, increasing roll-forward risk
- Fragmentation between agent execution, supervisor control, compliance, reporting, and leadership visibility
- Lack of evidence-backed recommendations on what strategy or routing should change

## 4. Target Users

- Collections heads and recovery leaders
- Operations managers and supervisors
- Calling agents
- Compliance teams
- CFO, CEO, and executive reviewers
- Admin users responsible for setup, access, and governance

## 5. End-to-End Product Journey

The platform supports the following operating journey:

1. Upload a portfolio file in CSV or XLSX format
2. Map required and optional fields, validate quality, and preview the dataset
3. Launch a campaign with retry, throttle, and exclusion controls
4. Seed the supervisor queue and route accounts into execution
5. Work accounts in the Calling Console with borrower context and transcript support
6. Capture PTP dates and callback commitments directly from the operating desk
7. Trigger follow-up scheduling, missed-PTP monitoring, and alert generation
8. Track containment, recovery, queue health, and discipline in the control room
9. Use the Operations Copilot to diagnose performance and recommend changes
10. Execute changes directly or through an approval-aware governance flow

## 6. Basic User Flows by Login

The current demo environment supports the following primary login personas:

- `admin`: Platform Admin
- `mgr`: Collections Manager
- `agent`: Calling Agent
- `ceo`: CEO
- `cfo`: CFO
- `comp`: Compliance Officer

### 6.1 Admin (`admin`)

Typical flow:

1. Log in and land on the Early Bucket Control Room
2. Review campaign health, missed-PTP pressure, and recovery metrics
3. Move into Portfolios and Campaigns to upload or launch a lender sheet
4. Open Supervisor Workbench to inspect queue state and task movement
5. Enter Calling Console to review live execution and commitment capture
6. Use Operations Copilot to diagnose strategy performance and launch or queue actions
7. Review Alerts, Reports, Integrations, Users, and Settings for full platform control

Best suited for:

- End-to-end demo ownership
- Platform setup and governance
- Cross-functional supervision and troubleshooting

### 6.2 Collections Manager (`mgr`)

Typical flow:

1. Log in and land on the Early Bucket Control Room
2. Review bucket performance, follow-up discipline, and queue pressure
3. Use Operations Copilot to identify what is working by campaign, bucket, or agent
4. Upload or launch portfolios as needed
5. Open Supervisor Workbench to rebalance work and manage exceptions
6. Review Calling Console for commitment capture quality
7. Use Alerts, Reports, and Integrations to manage operational follow-through

Best suited for:

- Day-to-day collections supervision
- Campaign and queue management
- Strategy review and controlled operational changes

### 6.3 Calling Agent (`agent`)

Typical flow:

1. Log in and land directly in the Calling Console
2. Open the next assigned borrower account
3. Review borrower brief and transcript context
4. Capture the correct outcome: connected, PTP, callback, or other disposition
5. Save PTP date or callback timing directly in workflow
6. Return to the queue and continue execution across assigned accounts

Best suited for:

- Active borrower calling
- Commitment capture
- High-volume task execution with minimal navigation overhead

### 6.4 CEO (`ceo`)

Typical flow:

1. Log in and land on the Early Bucket Control Room
2. Review top-level containment, missed-PTP pressure, and recovery indicators
3. Use Operations Copilot to ask what is working and where leakage is increasing
4. Review Workbench in read-oriented mode for operating context if needed
5. Review Alerts and Reports for escalation visibility
6. Check Integrations status when enterprise readiness or operational stability is in focus

Best suited for:

- Executive oversight
- Performance review
- High-level strategy conversations

### 6.5 CFO (`cfo`)

Typical flow:

1. Log in and land on the Early Bucket Control Room
2. Review expected recovery, realized recovery, and campaign-level performance
3. Use Reports for scheduled or on-demand exports
4. Review Workbench only when account-level or queue context is needed for finance review

Best suited for:

- Recovery and reporting oversight
- Export consumption and business review
- Finance-aligned performance tracking

### 6.6 Compliance Officer (`comp`)

Typical flow:

1. Log in and, in the current build, get redirected away from the dashboard because this role does not have dashboard permission
2. Move into Alerts and Compliance from the app shell
3. Filter the alert inbox by severity, status, or type
4. Open alert detail, assign ownership, acknowledge, and resolve
5. Use Workbench when account-level operational context is required
6. Use Reports for review packs and audit support

Best suited for:

- Exception management
- Compliance triage
- Audit and alert resolution workflows

## 7. Capability Overview

### 7.1 Portfolio Ingestion and Campaign Launch

The product can operationalize spreadsheet-based portfolios into live campaigns.

Current capabilities:

- Upload portfolio files in CSV or XLSX format
- Detect source columns and support field mapping
- Require core collections fields: `customer_id`, `phone`, `amount_due`, `dpd`
- Support mapped context fields: `due_date`, `language`, `customer_name`
- Validate missing fields, invalid phone numbers, invalid DPD values, invalid amounts, and duplicates
- Generate validation summaries, top issues, error exports, bucket distributions, and language distribution
- Preview valid records before launch
- Support exclusions and predicate-based row filtering before campaign launch
- Record campaign launch configuration for auditability

Operational value:

- Reduces onboarding friction for new lender files
- Makes uploaded sheets immediately actionable
- Creates a clean bridge from raw operations data to execution

### 7.2 Supervisor Workbench

The Supervisor Workbench is the queue control surface for active campaign management.

Current capabilities:

- Filter tasks by campaign, queue state, and DPD bucket
- Inspect account-level task detail and timeline context
- Update task state and disposition
- Apply bulk actions
- Escalate or close cases with immutable task-event tracking
- Track callback timing and PTP-linked task context
- Maintain SLA due timing tied to workflow state

Operational value:

- Gives supervisors a live queue command center
- Supports disciplined queue management rather than ad hoc follow-up
- Preserves operational history for audits and reviews

### 7.3 Calling Console

The Calling Console is the primary execution interface for agents and calling managers.

Current capabilities:

- Present borrower brief and account context during live work
- Display live transcript-oriented interaction flow
- Capture dispositions directly from the console
- Capture promise-to-pay dates
- Capture callback dates and times
- Persist commitment context into the task layer and outcomes layer
- Support manual commitment capture when voice extraction is not the only source of truth

Operational value:

- Moves commitment capture into the exact place where collection work happens
- Avoids broken handoffs between calling activity and supervisory follow-up
- Creates a reliable operational trail after the borrower conversation

### 7.4 Commitment Tracking and Follow-Up Discipline

One of the strongest product capabilities is what happens after the borrower gives a commitment.

Current capabilities:

- Store PTP date and callback time in the workbench and audit layers
- Schedule PTP follow-ups around the commitment timeline
- Generate missed-PTP follow-up events
- Raise open missed-PTP alerts for unresolved commitments
- Feed commitment outcomes back into campaign and control-room metrics

Operational value:

- Improves the period immediately after a missed PTP
- Increases follow-up discipline and reduces silent leakage
- Supports early-bucket containment instead of relying only on higher call volume

### 7.5 Early Bucket Control Room

The overview dashboard is designed as an early-bucket operating control room.

Current capabilities:

- Show campaign-scoped performance metrics
- Track assigned accounts, contact coverage, PTP counts, and callback counts
- Surface missed-PTP counts and open missed-PTP alerts
- Show expected recovery and realized recovery
- Show roll-forward risk and bucket-level performance
- Display queue health and operational pressure indicators
- Provide bucket-oriented and agent-oriented metric views

Operational value:

- Gives supervisors and operations leaders a single view of discipline and containment
- Helps teams focus on what drives bucket migration risk
- Makes it easier to review performance without stitching together multiple systems

### 7.6 Operations Copilot

The Operations Copilot is an agentic AI control layer for operations leaders.

Current capabilities:

- Answer performance questions across campaigns, buckets, agents, and customers
- Explain what is working and what is underperforming
- Surface evidence blocks, confidence, and expected impact
- Diagnose missed-PTP pressure, follow-up gaps, and roll-forward risk
- Recommend strategy changes by bucket or campaign
- Recommend agent-routing or coaching changes
- Propose experiments to validate different strategies
- Support direct execution when permitted
- Queue approval-based actions when governance is required

Example questions the copilot can answer:

- Which bucket is converting best right now?
- Which agents are underperforming after adjusting for bucket mix?
- Where is missed-PTP pressure building?
- Which campaign strategy should we change this week?
- What is the likely impact if we rebalance work to stronger agents?

Operational value:

- Converts metrics into decisions, not just observations
- Gives operations leaders a usable control surface instead of a passive dashboard
- Keeps AI recommendations grounded in real operational data

### 7.7 Alerts and Compliance

The platform includes a shared surface for exceptions, operational risk, and compliance review.

Current capabilities:

- Alerts inbox with filtering by status, type, and severity
- Alert detail inspection with linked context
- Ownership, acknowledgment, and resolution workflow
- Support for missed-PTP operational alerts
- Compliance-aware control surfaces aligned with operator and reviewer workflows

Operational value:

- Keeps exceptions inside the operating system
- Improves response to operational leakage and compliance-sensitive events
- Makes triage and ownership explicit

### 7.8 Reports and Exports

The reporting surface supports recurring review and stakeholder communication.

Current capabilities:

- Campaign-scoped and all-campaign report views
- Scheduled reporting
- Immediate report generation
- JSON and CSV download history
- Download-center workflow for audit and review

Operational value:

- Supports business reviews, audit requests, and stakeholder reporting
- Reduces dependence on manual data pulls
- Helps finance and leadership consume operating outputs

### 7.9 Integrations and Reconciliation

The product includes operational reconciliation features for environments where multiple systems must stay aligned.

Current capabilities:

- View outbound and inbound sync status
- Review failed events
- Replay dead-letter queue items
- Inspect field-level conflicts
- Resolve conflicts through trust-source or manual override decisions

Operational value:

- Improves fit within lender LMS or CRM environments
- Helps operations teams manage system mismatch cleanly
- Supports enterprise adoption rather than isolated pilot usage

### 7.10 Users, Roles, and Governance

The product includes role-based operational access.

Current capabilities:

- Role-based access across admin, collections manager, calling agent, CEO, CFO, and compliance profiles
- Permission-based navigation and route access
- Admin-only settings surface
- Approval-aware operating flows for selected actions
- Audit persistence for operational changes

Operational value:

- Supports enterprise controls across multiple user personas
- Prevents the product from becoming an ungoverned operations tool
- Makes actionability compatible with approval requirements

## 8. Why the Product Is Better Than Standard Collections Tooling

### Standard tooling usually provides:

- Calling activity and dispositions
- Static dashboards
- Siloed supervisor and compliance tools
- Lagging reports
- Generic AI claims with little operational evidence

### TuringEdge Recovery OS provides:

- End-to-end flow from file ingestion to governed execution
- A control room focused on discipline, containment, and roll-forward risk
- Commitment capture tied directly to downstream operations
- Agentic recommendations grounded in campaign, bucket, agent, and customer metrics
- One operating system for agents, supervisors, compliance, leadership, and admins

## 9. High-Value Use Cases

- Launching a new early-bucket pilot from an uploaded lender spreadsheet
- Tightening discipline after borrower PTP capture
- Monitoring the hours and days immediately after a missed PTP
- Identifying which buckets respond best to which recovery strategies
- Comparing agent performance while avoiding purely anecdotal judgments
- Creating supervisor-approved strategy or routing changes from evidence
- Supporting lender demos with a clear, visual operating workflow

## 10. Core Proof Points to Use in Internal or Client Conversations

- The product can take an uploaded portfolio file and operationalize it into a live campaign
- The agent desk can capture PTPs and callbacks directly in workflow
- Follow-up discipline after a commitment is part of the product, not a manual side process
- The control room shows missed-PTP pressure, bucket performance, queue health, and recovery metrics
- The copilot can explain what is working, why it is happening, and what to change next
- Governance is built into actions through approval-aware flows

## 11. Suggested One-Line Positioning Statements

- TuringEdge Recovery OS is an agentic collections operating system for early-bucket control.
- TuringEdge helps collections teams operationalize uploaded portfolios, capture commitments, enforce follow-through, and improve containment.
- TuringEdge gives supervisors an AI control layer grounded in real collections metrics.

## 12. Summary

TuringEdge Recovery OS combines portfolio ingestion, execution tooling, commitment tracking, follow-up discipline, control-room analytics, grounded agentic recommendations, compliance workflows, reporting, reconciliation, and role-based governance in one platform. The product is strongest when positioned around early-bucket containment and the operational gap that appears after a borrower promise is made but not followed through on time.
