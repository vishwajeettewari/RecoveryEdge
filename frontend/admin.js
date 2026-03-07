const refreshBtn = document.getElementById("refreshBtn");
const reindexBtn = document.getElementById("reindexBtn");
const exportLink = document.getElementById("exportLink");
const metricsBox = document.getElementById("metricsBox");
const sessionsTable = document.getElementById("sessionsTable");
const adminStatus = document.getElementById("adminStatus");
const adminTokenInput = document.getElementById("adminTokenInput");
const saveTokenBtn = document.getElementById("saveTokenBtn");
const metricSessionsToday = document.getElementById("metricSessionsToday");
const metricPtpCount = document.getElementById("metricPtpCount");
const metricCallbackCount = document.getElementById("metricCallbackCount");
const metricEscalations = document.getElementById("metricEscalations");
const metricAht = document.getElementById("metricAht");
const buildInfoBadge = document.getElementById("buildInfoBadge");

const campaignsTable = document.getElementById("campaignsTable");
const createCampaignBtn = document.getElementById("createCampaignBtn");
const campaignNameInput = document.getElementById("campaignNameInput");
const violationsTable = document.getElementById("violationsTable");
const timelineBox = document.getElementById("timelineBox");
const timelineSessionLabel = document.getElementById("timelineSessionLabel");
const outboundBox = document.getElementById("outboundBox");

const portfolioFileInput = document.getElementById("portfolioFileInput");
const portfolioUploadBtn = document.getElementById("portfolioUploadBtn");
const portfolioUploadInfo = document.getElementById("portfolioUploadInfo");
const portfolioMappingBox = document.getElementById("portfolioMappingBox");
const portfolioValidateBtn = document.getElementById("portfolioValidateBtn");
const portfolioValidationBox = document.getElementById("portfolioValidationBox");
const portfolioPreviewBox = document.getElementById("portfolioPreviewBox");
const portfolioLaunchBtn = document.getElementById("portfolioLaunchBtn");
const exclusionFileInput = document.getElementById("exclusionFileInput");
const uploadExclusionBtn = document.getElementById("uploadExclusionBtn");
const excludePredicateInput = document.getElementById("excludePredicateInput");

const workbenchCampaignFilter = document.getElementById("workbenchCampaignFilter");
const workbenchRefreshBtn = document.getElementById("workbenchRefreshBtn");
const laneNEW = document.getElementById("laneNEW");
const laneIN_PROGRESS = document.getElementById("laneIN_PROGRESS");
const lanePTP = document.getElementById("lanePTP");
const laneCALLBACK = document.getElementById("laneCALLBACK");
const laneESCALATED = document.getElementById("laneESCALATED");
const laneCLOSED = document.getElementById("laneCLOSED");
const taskDrawer = document.getElementById("taskDrawer");
const taskDrawerCloseBtn = document.getElementById("taskDrawerCloseBtn");
const taskDetailBox = document.getElementById("taskDetailBox");
const bulkIdsInput = document.getElementById("bulkIdsInput");
const bulkActionSelect = document.getElementById("bulkActionSelect");
const bulkPayloadInput = document.getElementById("bulkPayloadInput");
const bulkApplyBtn = document.getElementById("bulkApplyBtn");

const alertStatusFilter = document.getElementById("alertStatusFilter");
const alertTypeFilter = document.getElementById("alertTypeFilter");
const evaluateAlertsBtn = document.getElementById("evaluateAlertsBtn");
const alertsTable = document.getElementById("alertsTable");
const alertDetailBox = document.getElementById("alertDetailBox");
const alertAssignInput = document.getElementById("alertAssignInput");
const alertAckBtn = document.getElementById("alertAckBtn");
const alertAssignBtn = document.getElementById("alertAssignBtn");
const alertResolveBtn = document.getElementById("alertResolveBtn");
const alertRulesTable = document.getElementById("alertRulesTable");
const ruleIdInput = document.getElementById("ruleIdInput");
const ruleNameInput = document.getElementById("ruleNameInput");
const ruleTypeInput = document.getElementById("ruleTypeInput");
const ruleEnabledInput = document.getElementById("ruleEnabledInput");
const ruleThresholdJsonInput = document.getElementById("ruleThresholdJsonInput");
const ruleRoutingJsonInput = document.getElementById("ruleRoutingJsonInput");
const saveRuleBtn = document.getElementById("saveRuleBtn");

const reportTimeInput = document.getElementById("reportTimeInput");
const reportEnabledInput = document.getElementById("reportEnabledInput");
const saveReportScheduleBtn = document.getElementById("saveReportScheduleBtn");
const generateReportsBtn = document.getElementById("generateReportsBtn");
const reportsTable = document.getElementById("reportsTable");

const refreshIntegrationsBtn = document.getElementById("refreshIntegrationsBtn");
const sendInboundSampleBtn = document.getElementById("sendInboundSampleBtn");
const syncEventsTable = document.getElementById("syncEventsTable");
const conflictsTable = document.getElementById("conflictsTable");
const deadLettersTable = document.getElementById("deadLettersTable");
const integrationsSection = document.getElementById("integrationsSection");
const integrationTabBtns = Array.from(document.querySelectorAll(".integration-tab-btn"));
const integrationTabOutbound = document.getElementById("integrationTabOutbound");
const integrationTabInbound = document.getElementById("integrationTabInbound");
const integrationTabDeadletters = document.getElementById("integrationTabDeadletters");
const integrationTabConflicts = document.getElementById("integrationTabConflicts");

const ADMIN_TOKEN_KEY = "te_admin_token";

const portfolioState = {
  upload_id: null,
  portfolio_id: null,
  mappings: {},
  exclusion_upload_id: null,
};
const runtimeFlags = {
  demo_mode: true,
  pilot_mode: false,
};
const workbenchLanes = {
  NEW: laneNEW,
  IN_PROGRESS: laneIN_PROGRESS,
  PTP: lanePTP,
  CALLBACK: laneCALLBACK,
  ESCALATED: laneESCALATED,
  CLOSED: laneCLOSED,
};
const workbenchStates = ["NEW", "IN_PROGRESS", "PTP", "CALLBACK", "ESCALATED", "CLOSED"];
let selectedAlertId = null;
let alertRowsCache = [];
let alertRulesCache = [];
let activeIntegrationTab = "conflicts";

function setStatus(msg) {
  if (!adminStatus) return;
  const ts = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  adminStatus.textContent = `[${ts}] ${msg || ""}`;
}

function readToken() {
  return (adminTokenInput && adminTokenInput.value ? adminTokenInput.value : "").trim();
}

async function fetchJson(path, opts) {
  const options = { ...(opts || {}) };
  options.headers = { ...(options.headers || {}) };
  const token = readToken();
  if (token) options.headers.Authorization = `Bearer ${token}`;
  const res = await fetch(path, options);
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

function setIntegrationTab(tab) {
  activeIntegrationTab = tab || "conflicts";
  const panels = {
    outbound: integrationTabOutbound,
    inbound: integrationTabInbound,
    deadletters: integrationTabDeadletters,
    conflicts: integrationTabConflicts,
  };
  Object.entries(panels).forEach(([name, panel]) => {
    if (!panel) return;
    panel.style.display = name === activeIntegrationTab ? "" : "none";
  });
  integrationTabBtns.forEach((btn) => {
    const isActive = btn.dataset.tab === activeIntegrationTab;
    btn.style.opacity = isActive ? "1" : "0.7";
    btn.style.borderColor = isActive ? "#5cacff" : "";
  });
}

function renderMetrics(m) {
  if (!metricsBox) return;
  if (metricSessionsToday) metricSessionsToday.textContent = String(m.sessions_today ?? 0);
  if (metricPtpCount) metricPtpCount.textContent = String(m.ptp_count ?? 0);
  if (metricCallbackCount) metricCallbackCount.textContent = String(m.callback_count ?? 0);
  if (metricEscalations) metricEscalations.textContent = String(m.escalations ?? 0);
  if (metricAht) metricAht.textContent = m.avg_handle_seconds == null ? "n/a" : Number(m.avg_handle_seconds).toFixed(1);

  metricsBox.textContent =
    `Live: ${m.sessions_today ?? 0} sessions, ${m.ptp_count ?? 0} PTP, ${m.callback_count ?? 0} callbacks, ` +
    `${m.escalations ?? 0} escalations, retries pending ${m.retries_pending ?? 0}.`;

  if (outboundBox) {
    const o = m.outbound_status || {};
    outboundBox.textContent = `queued=${o.queued || 0}, retry=${o.retry_scheduled || 0}, acked=${o.acked || 0}, dead_letter=${o.dead_letter || 0}`;
  }
}

async function loadBuildInfo() {
  try {
    const data = await fetchJson("/api/system/build_info");
    runtimeFlags.demo_mode = !!data.demo_mode;
    runtimeFlags.pilot_mode = !!data.pilot_mode;
    if (buildInfoBadge) {
      buildInfoBadge.textContent = `build: ${data.static_token || "dev"}`;
      buildInfoBadge.title = `demo_mode=${data.demo_mode ? 1 : 0}, pilot_mode=${data.pilot_mode ? 1 : 0}`;
    }
    if (integrationsSection) {
      integrationsSection.style.display = runtimeFlags.pilot_mode ? "" : "none";
    }
    if (runtimeFlags.pilot_mode) {
      setIntegrationTab(activeIntegrationTab || "conflicts");
    }
  } catch (e) {
    // ignore
  }
}

async function showTimeline(sessionId) {
  if (!sessionId) return;
  try {
    const data = await fetchJson(`/api/sessions/${encodeURIComponent(sessionId)}/timeline`);
    if (timelineSessionLabel) timelineSessionLabel.textContent = sessionId;
    if (timelineBox) {
      const lines = (data.timeline || []).slice(-40).map((ev) => {
        const ts = ev.ts ? new Date(ev.ts * 1000).toLocaleTimeString() : "--";
        const payload = ev.payload ? JSON.stringify(ev.payload) : "";
        return `${ts} | ${ev.type || "event"} | ${payload}`;
      });
      timelineBox.textContent = lines.join("\n") || "No events";
    }
  } catch (e) {
    setStatus(`Timeline error: ${e.message}`);
  }
}

function renderSessions(sessions) {
  if (!sessionsTable) return;
  const tbody = sessionsTable.querySelector("tbody");
  if (!tbody) return;
  tbody.innerHTML = "";

  (sessions || []).forEach((s) => {
    const tr = document.createElement("tr");
    const cells = [
      s.session_id || "",
      `${s.customer_id || ""}${s.customer_name ? " — " + s.customer_name : ""}`,
      `${s.current_step || ""}${s.dpd_bucket ? ` (${s.dpd_bucket})` : ""}`,
      s.stress === undefined ? "" : String(s.stress),
      s.last_activity_ts ? new Date(s.last_activity_ts * 1000).toLocaleTimeString() : "",
      s.disposition || "",
    ];
    cells.forEach((c) => {
      const td = document.createElement("td");
      td.textContent = c;
      tr.appendChild(td);
    });

    const tdAction = document.createElement("td");

    const btnClose = document.createElement("button");
    btnClose.className = "secondary-btn btn-sm";
    btnClose.type = "button";
    btnClose.textContent = "Close";
    btnClose.onclick = async () => {
      try {
        await fetchJson(`/api/sessions/${encodeURIComponent(s.session_id)}/disposition`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ disposition: "closed" }),
        });
        await refresh();
      } catch (e) {
        setStatus(`Disposition error: ${e.message}`);
      }
    };

    const btnTimeline = document.createElement("button");
    btnTimeline.className = "secondary-btn btn-sm";
    btnTimeline.type = "button";
    btnTimeline.style.marginLeft = "6px";
    btnTimeline.textContent = "Timeline";
    btnTimeline.onclick = () => showTimeline(s.session_id);

    const btnReplay = document.createElement("button");
    btnReplay.className = "secondary-btn btn-sm";
    btnReplay.type = "button";
    btnReplay.style.marginLeft = "6px";
    btnReplay.textContent = "CRM Replay";
    btnReplay.onclick = async () => {
      try {
        await fetchJson(`/api/integrations/crm/replay/${encodeURIComponent(s.session_id)}`, { method: "POST" });
        setStatus(`CRM replay queued for ${s.session_id}`);
        await refresh();
      } catch (e) {
        setStatus(`CRM replay error: ${e.message}`);
      }
    };

    tdAction.appendChild(btnClose);
    tdAction.appendChild(btnTimeline);
    tdAction.appendChild(btnReplay);
    tr.appendChild(tdAction);
    tbody.appendChild(tr);
  });
}

function renderCampaigns(rows) {
  if (!campaignsTable) return;
  const tbody = campaignsTable.querySelector("tbody");
  if (!tbody) return;
  tbody.innerHTML = "";

  (rows || []).forEach((c) => {
    const tr = document.createElement("tr");
    const total = Number(c.total_accounts || 0);
    const completed = Number(c.completed || 0);
    const retries = Number(c.retry_scheduled || 0);
    const cells = [c.name || c.campaign_id || "", c.status || "", String(total), String(completed), String(retries)];
    cells.forEach((v) => {
      const td = document.createElement("td");
      td.textContent = v;
      tr.appendChild(td);
    });

    const tdAction = document.createElement("td");
    const startBtn = document.createElement("button");
    startBtn.className = "secondary-btn btn-sm";
    startBtn.textContent = "Start";
    startBtn.onclick = async () => {
      try {
        await fetchJson(`/api/campaigns/${encodeURIComponent(c.campaign_id)}/start`, { method: "POST" });
        await refresh();
      } catch (e) {
        setStatus(`Start campaign error: ${e.message}`);
      }
    };
    const pauseBtn = document.createElement("button");
    pauseBtn.className = "secondary-btn btn-sm";
    pauseBtn.style.marginLeft = "6px";
    pauseBtn.textContent = "Pause";
    pauseBtn.onclick = async () => {
      try {
        await fetchJson(`/api/campaigns/${encodeURIComponent(c.campaign_id)}/pause`, { method: "POST" });
        await refresh();
      } catch (e) {
        setStatus(`Pause campaign error: ${e.message}`);
      }
    };
    tdAction.appendChild(startBtn);
    tdAction.appendChild(pauseBtn);
    tr.appendChild(tdAction);
    tbody.appendChild(tr);
  });
}

function renderViolations(rows) {
  if (!violationsTable) return;
  const tbody = violationsTable.querySelector("tbody");
  if (!tbody) return;
  tbody.innerHTML = "";
  (rows || []).slice(0, 50).forEach((v) => {
    const tr = document.createElement("tr");
    const cells = [
      v.ts ? new Date(v.ts * 1000).toLocaleTimeString() : "",
      v.session_id || "",
      v.rule_code || "",
      v.severity || "",
      v.detail || "",
    ];
    cells.forEach((x) => {
      const td = document.createElement("td");
      td.textContent = x;
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
}

function suggestMapping(columns) {
  const map = {};
  (columns || []).forEach((c) => {
    const n = String(c.source_col || "").toLowerCase();
    if (n.includes("customer") && n.includes("id")) map[c.source_col] = "customer_id";
    else if (n === "phone" || n.includes("mobile")) map[c.source_col] = "phone";
    else if (n.includes("amount") || n.includes("due")) map[c.source_col] = "amount_due";
    else if (n === "dpd" || n.includes("days_past_due")) map[c.source_col] = "dpd";
    else if (n.includes("due_date") || n === "due date") map[c.source_col] = "due_date";
    else if (n.includes("language")) map[c.source_col] = "language";
    else if (n.includes("name")) map[c.source_col] = "customer_name";
  });
  return map;
}

function renderMappingUi(columns) {
  if (!portfolioMappingBox) return;
  const options = ["", "customer_id", "phone", "amount_due", "dpd", "due_date", "language", "customer_name"];
  const table = document.createElement("table");
  table.className = "admin-table";
  const thead = document.createElement("thead");
  thead.innerHTML = "<tr><th>Source Column</th><th>Map To</th><th>Type</th><th>Sample</th></tr>";
  table.appendChild(thead);
  const tbody = document.createElement("tbody");

  columns.forEach((c) => {
    const tr = document.createElement("tr");
    const tdCol = document.createElement("td");
    tdCol.textContent = c.source_col || "";
    tr.appendChild(tdCol);

    const tdMap = document.createElement("td");
    const sel = document.createElement("select");
    sel.className = "demo-input";
    sel.dataset.sourceCol = c.source_col || "";
    options.forEach((o) => {
      const opt = document.createElement("option");
      opt.value = o;
      opt.textContent = o || "(ignore)";
      if (portfolioState.mappings[c.source_col] === o) opt.selected = true;
      sel.appendChild(opt);
    });
    tdMap.appendChild(sel);
    tr.appendChild(tdMap);

    const tdType = document.createElement("td");
    tdType.textContent = c.inferred_type || "string";
    tr.appendChild(tdType);

    const tdSample = document.createElement("td");
    tdSample.textContent = (c.sample_values || []).join(", ");
    tr.appendChild(tdSample);

    tbody.appendChild(tr);
  });
  table.appendChild(tbody);

  const saveBtn = document.createElement("button");
  saveBtn.className = "secondary-btn btn-sm";
  saveBtn.type = "button";
  saveBtn.textContent = "Step 2: Save Mapping";
  saveBtn.onclick = savePortfolioMapping;

  portfolioMappingBox.innerHTML = "";
  portfolioMappingBox.appendChild(table);
  portfolioMappingBox.appendChild(saveBtn);
}

async function uploadPortfolio() {
  if (!portfolioFileInput || !portfolioFileInput.files || !portfolioFileInput.files[0]) {
    setStatus("Select a portfolio CSV/XLSX first.");
    return;
  }
  try {
    setStatus("Uploading portfolio...");
    const fd = new FormData();
    fd.append("file", portfolioFileInput.files[0]);
    const token = readToken();
    const headers = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch("/api/portfolio/upload", { method: "POST", headers, body: fd });
    if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
    const data = await res.json();
    portfolioState.upload_id = data.upload_id;
    portfolioState.portfolio_id = data.portfolio_id;
    portfolioState.mappings = suggestMapping(data.columns || []);
    if (portfolioUploadInfo) {
      portfolioUploadInfo.textContent = `upload_id=${data.upload_id}\nportfolio_id=${data.portfolio_id}\nrows=${data.row_count}`;
    }
    renderMappingUi(data.columns || []);
    setStatus("Portfolio uploaded. Review mapping.");
  } catch (e) {
    setStatus(`Portfolio upload error: ${e.message}`);
  }
}

async function savePortfolioMapping() {
  if (!portfolioState.upload_id) {
    setStatus("Upload portfolio first.");
    return;
  }
  try {
    const mappingInputs = portfolioMappingBox ? portfolioMappingBox.querySelectorAll("select[data-source-col]") : [];
    const mappings = {};
    mappingInputs.forEach((sel) => {
      const source = sel.dataset.sourceCol;
      if (!source) return;
      mappings[source] = sel.value || "";
    });
    portfolioState.mappings = mappings;
    const data = await fetchJson(`/api/portfolio/${encodeURIComponent(portfolioState.upload_id)}/map`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mappings, portfolio_name: `Portfolio ${new Date().toISOString().slice(0, 10)}` }),
    });
    portfolioState.portfolio_id = data.portfolio_id;
    setStatus("Mapping saved. Run validation.");
  } catch (e) {
    setStatus(`Mapping error: ${e.message}`);
  }
}

async function validatePortfolio() {
  if (!portfolioState.portfolio_id) {
    setStatus("Upload + map first.");
    return;
  }
  try {
    const data = await fetchJson(`/api/portfolio/${encodeURIComponent(portfolioState.portfolio_id)}/validate`, { method: "POST" });
    if (portfolioValidationBox) {
      portfolioValidationBox.innerHTML =
        `<div>Data Quality Score: <strong>${data.data_quality_score}</strong></div>` +
        `<div>Valid: ${data.valid_rows}, Invalid: ${data.invalid_rows}, Duplicates: ${data.duplicates_dropped}</div>` +
        `<div>Top Issues: ${(data.top_issues || []).map((i) => `${i.issue}:${i.count}`).join(", ") || "none"}</div>` +
        `<div><a href="/api/portfolio/${encodeURIComponent(portfolioState.portfolio_id)}/errors.csv" target="_blank" rel="noreferrer">Download errors.csv</a></div>`;
    }
    const preview = await fetchJson(`/api/portfolio/${encodeURIComponent(portfolioState.portfolio_id)}/preview?limit=20`);
    if (portfolioPreviewBox) {
      portfolioPreviewBox.textContent = JSON.stringify(preview.rows || [], null, 2);
    }
    setStatus("Validation complete.");
  } catch (e) {
    setStatus(`Validation error: ${e.message}`);
  }
}

async function uploadExclusions() {
  if (!portfolioState.portfolio_id) {
    setStatus("Validate portfolio first.");
    return;
  }
  if (!exclusionFileInput || !exclusionFileInput.files || !exclusionFileInput.files[0]) {
    setStatus("Choose exclusions CSV first.");
    return;
  }
  try {
    const fd = new FormData();
    fd.append("file", exclusionFileInput.files[0]);
    const token = readToken();
    const headers = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(`/api/portfolio/${encodeURIComponent(portfolioState.portfolio_id)}/exclusions/upload`, {
      method: "POST",
      headers,
      body: fd,
    });
    if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
    const data = await res.json();
    portfolioState.exclusion_upload_id = data.exclusion_id;
    setStatus(`Exclusions uploaded (${data.row_count} rows).`);
  } catch (e) {
    setStatus(`Exclusion upload error: ${e.message}`);
  }
}

async function launchPortfolio() {
  if (!portfolioState.portfolio_id) {
    setStatus("Validate portfolio first.");
    return;
  }
  try {
    const excludePredicate = excludePredicateInput && excludePredicateInput.value ? excludePredicateInput.value.trim() : "";
    const payload = {
      campaign_name: `Launch ${new Date().toISOString().slice(0, 10)}`,
      retry_policy: { max_attempts: 3, retry_delay_minutes: 30 },
      contact_window: { start: "09:00", end: "20:00" },
      throttle: 250,
      dpd_bucket_strategies: {},
      exclusion_upload_id: portfolioState.exclusion_upload_id,
      exclude_predicate: excludePredicate || null,
    };
    const out = await fetchJson(`/api/portfolio/${encodeURIComponent(portfolioState.portfolio_id)}/launch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    setStatus(`Launched campaign ${out.campaign_id}. Seeded=${out.seeded_accounts}, tasks=${out.tasks_created}`);
    if (workbenchCampaignFilter) workbenchCampaignFilter.value = out.campaign_id || "";
    await refresh();
  } catch (e) {
    setStatus(`Launch error: ${e.message}`);
  }
}

async function refreshTasks() {
  try {
    const campaign = workbenchCampaignFilter && workbenchCampaignFilter.value ? workbenchCampaignFilter.value.trim() : "";
    const data = await fetchJson(`/api/tasks?campaign_id=${encodeURIComponent(campaign)}`);
    renderTasks(data.rows || []);
  } catch (e) {
    setStatus(`Workbench refresh error: ${e.message}`);
  }
}

function complianceBadgesHtml(task) {
  let badges = {};
  try {
    badges = JSON.parse(task.compliance_status_json || "{}") || {};
  } catch (e) {
    badges = {};
  }
  const keys = ["CONSENT_OK", "IDENTITY_OK", "NO_THREATS_OK", "SENSITIVE_ASKS_OK"];
  return keys
    .map((k) => {
      const ok = badges[k] !== false;
      return `<span style="display:inline-block;padding:2px 6px;border-radius:8px;margin-right:4px;border:1px solid ${ok ? "#2ecc71" : "#ff6b6b"};">${k}:${ok ? "OK" : "FAIL"}</span>`;
    })
    .join(" ");
}

function renderTasks(rows) {
  Object.values(workbenchLanes).forEach((lane) => {
    if (lane) lane.innerHTML = "";
  });
  const grouped = {};
  workbenchStates.forEach((s) => {
    grouped[s] = [];
  });
  (rows || []).forEach((t) => {
    const s = String(t.state || "NEW").toUpperCase();
    if (!grouped[s]) grouped[s] = [];
    grouped[s].push(t);
  });

  workbenchStates.forEach((state) => {
    const lane = workbenchLanes[state];
    if (!lane) return;
    const tasks = grouped[state] || [];
    if (!tasks.length) {
      const empty = document.createElement("div");
      empty.style.opacity = "0.7";
      empty.style.fontSize = "12px";
      empty.textContent = "No tasks";
      lane.appendChild(empty);
      return;
    }
    tasks.forEach((t) => {
      const card = document.createElement("button");
      card.type = "button";
      card.style.textAlign = "left";
      card.style.padding = "8px";
      card.style.borderRadius = "10px";
      card.style.border = "1px solid rgba(92,172,255,0.45)";
      card.style.background = "rgba(5,20,38,0.85)";
      card.style.color = "inherit";
      card.style.cursor = "pointer";
      card.innerHTML =
        `<div><strong>${t.customer_id || "-"}</strong></div>` +
        `<div style="margin-top:4px;font-size:12px;">amount: ${Number(t.amount_due || 0).toFixed(2)} | dpd: ${t.dpd ?? "-"}</div>` +
        `<div style="margin-top:4px;font-size:12px;">SLA: ${t.sla_due_at ? new Date(t.sla_due_at * 1000).toLocaleString() : "-"}</div>` +
        `<div style="margin-top:4px;font-size:12px;color:${t.sla_breach ? "#ff8a80" : "#90caf9"};">${t.sla_breach ? "SLA BREACH" : "SLA OK"}${t.compliance_block ? " | COMPLIANCE BLOCK" : ""}</div>` +
        `<div style="margin-top:4px;font-size:12px;opacity:.8;">last action: ${t.last_action_at ? new Date(t.last_action_at * 1000).toLocaleString() : "-"}</div>`;
      card.onclick = () => loadTaskDetail(t.id);
      lane.appendChild(card);
    });
  });
}

async function loadTaskDetail(taskId) {
  try {
    const t = await fetchJson(`/api/tasks/${encodeURIComponent(taskId)}`);
    if (!taskDetailBox || !taskDrawer) return;
    const sessions = await fetchJson("/api/sessions");
    const matching = (sessions.sessions || []).find((s) => String(s.customer_id || "") === String(t.customer_id || ""));
    const transcriptLink = matching && matching.session_id ? `/api/sessions/${encodeURIComponent(matching.session_id)}/timeline` : "";
    const events = (t.events || []).slice(0, 30).map((e) => `${new Date((e.ts || 0) * 1000).toLocaleTimeString()} | ${e.event_type} | ${e.payload_json || ""}`);
    taskDetailBox.innerHTML =
      `<div><strong>Task ${t.id}</strong> (${t.state})</div>` +
      `<div style="margin-top:6px;">customer: ${t.customer_id || "-"} | campaign: ${t.campaign_id || "-"}</div>` +
      `<div style="margin-top:6px;">transcript: ${transcriptLink ? `<a href="${transcriptLink}" target="_blank" rel="noreferrer">open timeline</a>` : "no linked live session"}</div>` +
      `<div style="margin-top:6px;">Compliance: ${complianceBadgesHtml(t)} ${t.compliance_block ? "<strong>BLOCKED</strong>" : ""}</div>` +
      `<div style="margin-top:8px;display:flex;gap:8px;align-items:center;flex-wrap:wrap;">` +
      `<select id="taskStateInput" class="demo-input">` +
      workbenchStates.map((s) => `<option value="${s}" ${t.state === s ? "selected" : ""}>${s}</option>`).join("") +
      `</select>` +
      `<input id="taskDispositionInput" class="demo-input" placeholder="disposition" value="${t.disposition || ""}" />` +
      `<input id="taskNotesInput" class="demo-input" placeholder="notes" value="${t.notes || ""}" />` +
      `<label style="display:flex;align-items:center;gap:4px;"><input id="taskOverrideInput" type="checkbox" /> override</label>` +
      `<button id="claimTaskBtn" class="secondary-btn btn-sm" type="button">Claim</button>` +
      `<button id="saveTaskBtn" class="secondary-btn btn-sm" type="button">Save Task</button>` +
      `</div>` +
      `<pre style="margin-top:10px;max-height:220px;overflow:auto;">${events.join("\n") || "No events"}</pre>`;
    taskDrawer.style.transform = "translateX(0)";

    const saveBtn = document.getElementById("saveTaskBtn");
    const claimBtn = document.getElementById("claimTaskBtn");
    if (claimBtn) {
      claimBtn.onclick = async () => {
        try {
          const out = await fetchJson(`/api/tasks/${encodeURIComponent(taskId)}/claim`, { method: "POST" });
          if (!out.ok) throw new Error(out.error || "claim_failed");
          await refreshTasks();
          await loadTaskDetail(taskId);
        } catch (e) {
          setStatus(`Claim error: ${e.message}`);
        }
      };
    }
    if (saveBtn) {
      saveBtn.onclick = async () => {
        try {
          const state = document.getElementById("taskStateInput").value;
          const disposition = document.getElementById("taskDispositionInput").value;
          const notes = document.getElementById("taskNotesInput").value;
          const override = document.getElementById("taskOverrideInput").checked;
          await fetchJson(`/api/tasks/${encodeURIComponent(taskId)}/update`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ state, disposition, notes, compliance_override: override }),
          });
          await refreshTasks();
          await loadTaskDetail(taskId);
        } catch (e) {
          setStatus(`Task update error: ${e.message}`);
        }
      };
    }
  } catch (e) {
    setStatus(`Task detail error: ${e.message}`);
  }
}

async function runBulkUpdate() {
  try {
    const ids = (bulkIdsInput && bulkIdsInput.value ? bulkIdsInput.value : "").split(",").map((x) => x.trim()).filter(Boolean);
    const action = bulkActionSelect && bulkActionSelect.value ? bulkActionSelect.value : "assign";
    let payload = {};
    const txt = bulkPayloadInput && bulkPayloadInput.value ? bulkPayloadInput.value.trim() : "{}";
    try {
      payload = JSON.parse(txt || "{}");
    } catch (e) {
      throw new Error("Invalid bulk payload JSON");
    }
    const res = await fetchJson("/api/tasks/bulk_update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids, action, payload }),
    });
    setStatus(`Bulk updated=${res.updated}, errors=${(res.errors || []).length}`);
    await refreshTasks();
  } catch (e) {
    setStatus(`Bulk update error: ${e.message}`);
  }
}

function renderAlerts(rows) {
  if (!alertsTable) return;
  const tbody = alertsTable.querySelector("tbody");
  if (!tbody) return;
  tbody.innerHTML = "";
  alertRowsCache = rows || [];
  (rows || []).forEach((a) => {
    const tr = document.createElement("tr");
    tr.style.cursor = "pointer";
    const cells = [
      a.ts ? new Date(a.ts * 1000).toLocaleTimeString() : "",
      a.type || "",
      a.severity || "",
      a.status || "",
      a.message || "",
    ];
    cells.forEach((v) => {
      const td = document.createElement("td");
      td.textContent = v;
      tr.appendChild(td);
    });
    tr.onclick = () => selectAlert(a.id);
    if (selectedAlertId && selectedAlertId === a.id) {
      tr.style.outline = "1px solid #5cacff";
      tr.style.background = "rgba(23, 56, 90, 0.45)";
    }
    tbody.appendChild(tr);
  });
}

function renderAlertRules(rows) {
  if (!alertRulesTable) return;
  alertRulesCache = rows || [];
  const tbody = alertRulesTable.querySelector("tbody");
  if (!tbody) return;
  tbody.innerHTML = "";
  (rows || []).forEach((r) => {
    const tr = document.createElement("tr");
    tr.style.cursor = "pointer";
    tr.onclick = () => {
      if (ruleIdInput) ruleIdInput.value = r.id || "";
      if (ruleNameInput) ruleNameInput.value = r.name || "";
      if (ruleTypeInput) ruleTypeInput.value = r.type || "PTP_MISS";
      if (ruleEnabledInput) ruleEnabledInput.checked = Number(r.enabled || 0) === 1;
      if (ruleThresholdJsonInput) ruleThresholdJsonInput.value = (() => {
        try {
          return JSON.stringify(JSON.parse(r.threshold_json || "{}"), null, 2);
        } catch (e) {
          return r.threshold_json || "{}";
        }
      })();
      if (ruleRoutingJsonInput) ruleRoutingJsonInput.value = (() => {
        try {
          return JSON.stringify(JSON.parse(r.routing_json || "{}"), null, 2);
        } catch (e) {
          return r.routing_json || "{}";
        }
      })();
    };
    const tdId = document.createElement("td");
    tdId.textContent = r.id || "";
    tr.appendChild(tdId);
    const tdName = document.createElement("td");
    tdName.textContent = r.name || "";
    tr.appendChild(tdName);
    const tdType = document.createElement("td");
    tdType.textContent = r.type || "";
    tr.appendChild(tdType);
    const tdEnabled = document.createElement("td");
    const toggle = document.createElement("input");
    toggle.type = "checkbox";
    toggle.checked = Number(r.enabled || 0) === 1;
    toggle.onclick = async (event) => {
      event.stopPropagation();
      try {
        await fetchJson(`/api/alert_rules/${encodeURIComponent(r.id)}/toggle`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ enabled: toggle.checked }),
        });
        await refreshAlerts();
      } catch (e) {
        setStatus(`Rule toggle error: ${e.message}`);
      }
    };
    tdEnabled.appendChild(toggle);
    tr.appendChild(tdEnabled);
    tbody.appendChild(tr);
  });
}

async function selectAlert(alertId) {
  selectedAlertId = alertId;
  renderAlerts(alertRowsCache);
  if (!alertDetailBox || !selectedAlertId) return;
  try {
    const a = await fetchJson(`/api/alerts/${encodeURIComponent(selectedAlertId)}`);
    let payload = a.payload_json || "";
    try {
      payload = JSON.stringify(JSON.parse(a.payload_json || "{}"), null, 2);
    } catch (e) {
      payload = a.payload_json || "";
    }
    alertDetailBox.textContent =
      `id: ${a.id}\n` +
      `type: ${a.type}\n` +
      `severity: ${a.severity}\n` +
      `status: ${a.status}\n` +
      `assigned_to: ${a.assigned_to || "-"}\n` +
      `entity: ${(a.entity_type || "-") + ":" + (a.entity_id || "-")}\n` +
      `message: ${a.message || ""}\n` +
      `ts: ${a.ts ? new Date(a.ts * 1000).toLocaleString() : "-"}\n` +
      `payload:\n${payload}`;
  } catch (e) {
    alertDetailBox.textContent = `Failed to load alert: ${e.message}`;
  }
}

async function saveRule() {
  try {
    const threshold = JSON.parse((ruleThresholdJsonInput && ruleThresholdJsonInput.value ? ruleThresholdJsonInput.value : "{}") || "{}");
    const routing = JSON.parse((ruleRoutingJsonInput && ruleRoutingJsonInput.value ? ruleRoutingJsonInput.value : "{}") || "{}");
    await fetchJson("/api/alert_rules", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id: ruleIdInput && ruleIdInput.value ? ruleIdInput.value.trim() : null,
        name: ruleNameInput && ruleNameInput.value ? ruleNameInput.value.trim() : "Rule",
        type: ruleTypeInput && ruleTypeInput.value ? ruleTypeInput.value : "PTP_MISS",
        enabled: !!(ruleEnabledInput && ruleEnabledInput.checked),
        threshold_json: threshold,
        routing_json: routing,
      }),
    });
    setStatus("Rule saved.");
    await refreshAlerts();
  } catch (e) {
    setStatus(`Rule save error: ${e.message}`);
  }
}

async function refreshAlerts() {
  try {
    const status = alertStatusFilter && alertStatusFilter.value ? alertStatusFilter.value : "";
    const type = alertTypeFilter && alertTypeFilter.value ? alertTypeFilter.value : "";
    const q = new URLSearchParams();
    if (status) q.set("status", status);
    if (type) q.set("type", type);
    const [alerts, rules] = await Promise.all([
      fetchJson(`/api/alerts?${q.toString()}`),
      fetchJson("/api/alert_rules"),
    ]);
    renderAlerts(alerts.rows || []);
    renderAlertRules(rules.rows || []);
    if (selectedAlertId) {
      const exists = (alerts.rows || []).some((r) => r.id === selectedAlertId);
      if (exists) {
        await selectAlert(selectedAlertId);
      } else {
        selectedAlertId = null;
        if (alertDetailBox) alertDetailBox.textContent = "Select an alert row.";
      }
    } else if ((alerts.rows || []).length > 0) {
      await selectAlert(alerts.rows[0].id);
    }
  } catch (e) {
    setStatus(`Alerts refresh error: ${e.message}`);
  }
}

async function evaluateAlerts() {
  try {
    const out = await fetchJson("/api/alerts/evaluate", { method: "POST" });
    setStatus(`Alerts evaluated. created=${out.result ? out.result.created : 0}`);
    await refreshAlerts();
  } catch (e) {
    setStatus(`Alerts evaluate error: ${e.message}`);
  }
}

function renderReports(rows) {
  if (!reportsTable) return;
  const tbody = reportsTable.querySelector("tbody");
  if (!tbody) return;
  tbody.innerHTML = "";
  (rows || []).forEach((r) => {
    const tr = document.createElement("tr");
    const cells = [
      r.report_date || "",
      r.campaign_id || "",
      r.created_at ? new Date(r.created_at * 1000).toLocaleString() : "",
    ];
    cells.forEach((v) => {
      const td = document.createElement("td");
      td.textContent = v;
      tr.appendChild(td);
    });
    const tdDownload = document.createElement("td");
    tdDownload.innerHTML =
      `<a href="/api/reports/${encodeURIComponent(r.id)}/download?format=json" target="_blank" rel="noreferrer">JSON</a> | ` +
      `<a href="/api/reports/${encodeURIComponent(r.id)}/download?format=csv" target="_blank" rel="noreferrer">CSV</a>`;
    tr.appendChild(tdDownload);
    tbody.appendChild(tr);
  });
}

async function refreshReports() {
  try {
    const out = await fetchJson("/api/reports");
    renderReports(out.rows || []);
    if (reportTimeInput && out.schedule && out.schedule.daily_time) reportTimeInput.value = out.schedule.daily_time;
    if (reportEnabledInput && out.schedule) reportEnabledInput.checked = Number(out.schedule.enabled || 0) === 1;
  } catch (e) {
    setStatus(`Reports refresh error: ${e.message}`);
  }
}

async function saveReportSchedule() {
  try {
    const daily_time = reportTimeInput && reportTimeInput.value ? reportTimeInput.value : "09:00";
    const enabled = !!(reportEnabledInput && reportEnabledInput.checked);
    await fetchJson("/api/reports/schedule", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ daily_time, enabled }),
    });
    setStatus("Report schedule saved.");
    await refreshReports();
  } catch (e) {
    setStatus(`Report schedule error: ${e.message}`);
  }
}

async function generateReportsNow() {
  try {
    const campaign_id = workbenchCampaignFilter && workbenchCampaignFilter.value ? workbenchCampaignFilter.value.trim() : "";
    const out = await fetchJson("/api/reports/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ campaign_id: campaign_id || undefined }),
    });
    setStatus(`Reports generated: ${out.count}`);
    await refreshReports();
  } catch (e) {
    setStatus(`Generate reports error: ${e.message}`);
  }
}

function renderSyncEvents(rows) {
  if (!syncEventsTable) return;
  const tbody = syncEventsTable.querySelector("tbody");
  if (!tbody) return;
  tbody.innerHTML = "";
  (rows || []).forEach((r) => {
    const tr = document.createElement("tr");
    const cells = [
      r.ts ? new Date(r.ts * 1000).toLocaleString() : "",
      r.direction || "",
      `${r.entity_type || ""}:${r.entity_id || ""}`,
      r.status || "",
    ];
    cells.forEach((v) => {
      const td = document.createElement("td");
      td.textContent = v;
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
}

function renderConflicts(rows) {
  if (!conflictsTable) return;
  const tbody = conflictsTable.querySelector("tbody");
  if (!tbody) return;
  tbody.innerHTML = "";
  (rows || []).forEach((r) => {
    const tr = document.createElement("tr");
    const cells = [
      r.ts ? new Date(r.ts * 1000).toLocaleString() : "",
      `${r.entity_type || ""}:${r.entity_id || ""}`,
      r.status || "",
      r.resolution || "",
    ];
    cells.forEach((v) => {
      const td = document.createElement("td");
      td.textContent = v;
      tr.appendChild(td);
    });

    const tdAction = document.createElement("td");
    ["TRUST_LMS", "TRUST_LOCAL"].forEach((action) => {
      const btn = document.createElement("button");
      btn.className = "secondary-btn btn-sm";
      btn.style.marginRight = "6px";
      btn.textContent = action;
      btn.onclick = async () => {
        try {
          await fetchJson(`/api/integrations/conflicts/${encodeURIComponent(r.id)}/resolve`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action }),
          });
          await refreshIntegrations();
        } catch (e) {
          setStatus(`Conflict resolve error: ${e.message}`);
        }
      };
      tdAction.appendChild(btn);
    });

    const manualBtn = document.createElement("button");
    manualBtn.className = "secondary-btn btn-sm";
    manualBtn.textContent = "MANUAL_OVERRIDE";
    manualBtn.onclick = async () => {
      try {
        await fetchJson(`/api/integrations/conflicts/${encodeURIComponent(r.id)}/resolve`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "MANUAL_OVERRIDE", manual_override: { state: "ESCALATED", disposition: "manual_override" } }),
        });
        await refreshIntegrations();
      } catch (e) {
        setStatus(`Manual override error: ${e.message}`);
      }
    };
    tdAction.appendChild(manualBtn);

    tr.appendChild(tdAction);
    tbody.appendChild(tr);
  });
}

function renderDeadLetters(rows) {
  if (!deadLettersTable) return;
  const tbody = deadLettersTable.querySelector("tbody");
  if (!tbody) return;
  tbody.innerHTML = "";
  (rows || []).forEach((r) => {
    const tr = document.createElement("tr");
    const cells = [r.queue_id || "", String(r.attempts || 0), r.updated_ts ? new Date(r.updated_ts * 1000).toLocaleString() : ""];
    cells.forEach((v) => {
      const td = document.createElement("td");
      td.textContent = v;
      tr.appendChild(td);
    });
    const tdAct = document.createElement("td");
    const btn = document.createElement("button");
    btn.className = "secondary-btn btn-sm";
    btn.textContent = "Replay";
    btn.onclick = async () => {
      try {
        await fetchJson(`/api/integrations/dead_letters/${encodeURIComponent(r.queue_id)}/replay`, { method: "POST" });
        await refreshIntegrations();
      } catch (e) {
        setStatus(`Replay error: ${e.message}`);
      }
    };
    tdAct.appendChild(btn);
    tr.appendChild(tdAct);
    tbody.appendChild(tr);
  });
}

async function refreshIntegrations() {
  if (!runtimeFlags.pilot_mode) {
    return;
  }
  try {
    const [events, conflicts, dead] = await Promise.all([
      fetchJson("/api/integrations/sync_events"),
      fetchJson("/api/integrations/conflicts"),
      fetchJson("/api/integrations/dead_letters"),
    ]);
    renderSyncEvents(events.rows || []);
    renderConflicts(conflicts.rows || []);
    renderDeadLetters(dead.rows || []);
    setIntegrationTab(activeIntegrationTab || "conflicts");
  } catch (e) {
    setStatus(`Integrations refresh error: ${e.message}`);
  }
}

async function sendInboundSample() {
  if (!runtimeFlags.pilot_mode) {
    setStatus("PILOT_MODE=1 required for inbound LMS simulation.");
    return;
  }
  try {
    const payload = {
      customer_id: "CUST001",
      payment_status: "DISPUTE",
      paid_amount: 0,
      paid_at: new Date().toISOString(),
      external_ref: `lms-${Date.now()}`,
      callback_at: new Date(Date.now() + 2 * 3600 * 1000).toISOString(),
    };
    await fetchJson("/api/integrations/lms/inbound", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    setStatus("Inbound LMS sample sent.");
    await refreshIntegrations();
  } catch (e) {
    setStatus(`Inbound sample error: ${e.message}`);
  }
}

async function refreshCampaigns() {
  const list = await fetchJson("/api/campaigns");
  const rows = [];
  for (const c of list.rows || []) {
    try {
      const m = await fetchJson(`/api/campaigns/${encodeURIComponent(c.campaign_id)}/metrics`);
      rows.push({ ...c, ...m });
    } catch (e) {
      rows.push(c);
    }
  }
  renderCampaigns(rows);
}

async function createCampaign() {
  try {
    const name = (campaignNameInput && campaignNameInput.value ? campaignNameInput.value : "").trim() || `Portfolio Campaign ${new Date().toISOString().slice(0, 10)}`;
    await fetchJson("/api/campaigns", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, max_accounts: 10000, batch_size: 300 }),
    });
    setStatus("Campaign created.");
    await refresh();
  } catch (e) {
    setStatus(`Create campaign error: ${e.message}`);
  }
}

async function refresh() {
  try {
    setStatus("Refreshing…");
    await loadBuildInfo();
    const [m, s, v] = await Promise.all([
      fetchJson("/api/metrics"),
      fetchJson("/api/sessions"),
      fetchJson("/api/compliance/violations"),
    ]);
    renderMetrics(m);
    renderSessions(s.sessions || []);
    renderViolations(v.rows || []);
    const jobs = [
      refreshCampaigns(),
      refreshTasks(),
      refreshAlerts(),
      refreshReports(),
    ];
    if (runtimeFlags.pilot_mode) jobs.push(refreshIntegrations());
    await Promise.all(jobs);
    setStatus("Updated.");
  } catch (e) {
    setStatus(`Error: ${e.message}`);
  }
}

async function reindex() {
  try {
    setStatus("Reindexing…");
    const res = await fetchJson("/api/knowledge/reindex", { method: "POST" });
    setStatus(`Reindexed. chunks=${res.chunks_indexed}`);
  } catch (e) {
    setStatus(`Reindex error: ${e.message}`);
  }
}

if (refreshBtn) refreshBtn.addEventListener("click", refresh);
if (reindexBtn) reindexBtn.addEventListener("click", reindex);
if (createCampaignBtn) createCampaignBtn.addEventListener("click", createCampaign);

if (portfolioUploadBtn) portfolioUploadBtn.addEventListener("click", uploadPortfolio);
if (portfolioValidateBtn) portfolioValidateBtn.addEventListener("click", validatePortfolio);
if (portfolioLaunchBtn) portfolioLaunchBtn.addEventListener("click", launchPortfolio);
if (uploadExclusionBtn) uploadExclusionBtn.addEventListener("click", uploadExclusions);

if (workbenchRefreshBtn) workbenchRefreshBtn.addEventListener("click", refreshTasks);
if (bulkApplyBtn) bulkApplyBtn.addEventListener("click", runBulkUpdate);
if (taskDrawerCloseBtn) {
  taskDrawerCloseBtn.addEventListener("click", () => {
    if (taskDrawer) taskDrawer.style.transform = "translateX(110%)";
  });
}

if (evaluateAlertsBtn) evaluateAlertsBtn.addEventListener("click", evaluateAlerts);
if (alertStatusFilter) alertStatusFilter.addEventListener("change", refreshAlerts);
if (alertTypeFilter) alertTypeFilter.addEventListener("change", refreshAlerts);
if (alertAckBtn) {
  alertAckBtn.addEventListener("click", async () => {
    if (!selectedAlertId) return;
    try {
      await fetchJson(`/api/alerts/${encodeURIComponent(selectedAlertId)}/ack`, { method: "POST" });
      await refreshAlerts();
    } catch (e) {
      setStatus(`Alert ack error: ${e.message}`);
    }
  });
}
if (alertAssignBtn) {
  alertAssignBtn.addEventListener("click", async () => {
    if (!selectedAlertId) return;
    try {
      const assignee = alertAssignInput && alertAssignInput.value ? alertAssignInput.value.trim() : "";
      await fetchJson(`/api/alerts/${encodeURIComponent(selectedAlertId)}/assign`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ assignee }),
      });
      await refreshAlerts();
    } catch (e) {
      setStatus(`Alert assign error: ${e.message}`);
    }
  });
}
if (alertResolveBtn) {
  alertResolveBtn.addEventListener("click", async () => {
    if (!selectedAlertId) return;
    try {
      await fetchJson(`/api/alerts/${encodeURIComponent(selectedAlertId)}/resolve`, { method: "POST" });
      await refreshAlerts();
    } catch (e) {
      setStatus(`Alert resolve error: ${e.message}`);
    }
  });
}
if (saveRuleBtn) saveRuleBtn.addEventListener("click", saveRule);

if (saveReportScheduleBtn) saveReportScheduleBtn.addEventListener("click", saveReportSchedule);
if (generateReportsBtn) generateReportsBtn.addEventListener("click", generateReportsNow);

if (refreshIntegrationsBtn) refreshIntegrationsBtn.addEventListener("click", refreshIntegrations);
if (sendInboundSampleBtn) sendInboundSampleBtn.addEventListener("click", sendInboundSample);
integrationTabBtns.forEach((btn) => {
  btn.addEventListener("click", () => setIntegrationTab(btn.dataset.tab || "conflicts"));
});

if (adminTokenInput) {
  try {
    adminTokenInput.value = localStorage.getItem(ADMIN_TOKEN_KEY) || "";
  } catch (e) {
    // ignore
  }
}

if (saveTokenBtn) {
  saveTokenBtn.addEventListener("click", () => {
    if (!adminTokenInput) return;
    try {
      localStorage.setItem(ADMIN_TOKEN_KEY, adminTokenInput.value || "");
      setStatus("Token saved.");
    } catch (e) {
      setStatus("Unable to save token.");
    }
  });
}

if (exportLink) {
  exportLink.addEventListener("click", async (event) => {
    event.preventDefault();
    try {
      setStatus("Preparing export…");
      const headers = {};
      const token = readToken();
      if (token) headers.Authorization = `Bearer ${token}`;
      const res = await fetch("/api/export/demo.xlsx", { headers });
      if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "demo.xlsx";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setStatus("Export downloaded.");
    } catch (e) {
      setStatus(`Export error: ${e.message}`);
    }
  });
}

setIntegrationTab("conflicts");
refresh();
setInterval(refresh, 5000);

// ===========================================================================
// ANALYTICS TAB
// ===========================================================================

const refreshAnalyticsBtn = document.getElementById("refreshAnalyticsBtn");
const analyticsDaysSelect = document.getElementById("analyticsDaysSelect");
const rollForwardMatrixBox = document.getElementById("rollForwardMatrixBox");
const rollForwardSummary = document.getElementById("rollForwardSummary");
const agentLeaderboardTable = document.getElementById("agentLeaderboardTable");
const recoveryKpis = document.getElementById("recoveryKpis");
const recoverySparkline = document.getElementById("recoverySparkline");
const reconciliationTable = document.getElementById("reconciliationTable");
const analyticsTabBtns = Array.from(document.querySelectorAll(".analytics-tab-btn"));

let activeAnalyticsTab = "rollforward";

function setAnalyticsTab(tab) {
  activeAnalyticsTab = tab;
  const panels = {
    rollforward: document.getElementById("analyticsTabRollforward"),
    recovery: document.getElementById("analyticsTabRecovery"),
    agents: document.getElementById("analyticsTabAgents"),
  };
  Object.entries(panels).forEach(([name, panel]) => {
    if (panel) panel.style.display = name === activeAnalyticsTab ? "" : "none";
  });
  analyticsTabBtns.forEach((btn) => {
    btn.style.opacity = btn.dataset.atab === activeAnalyticsTab ? "1" : "0.65";
  });
}

analyticsTabBtns.forEach((btn) => {
  btn.addEventListener("click", () => setAnalyticsTab(btn.dataset.atab));
});
setAnalyticsTab("rollforward");

function fmt(n) {
  if (n == null) return "—";
  if (typeof n === "number") return n.toLocaleString();
  return String(n);
}

async function loadRollForward() {
  if (!rollForwardMatrixBox) return;
  const days = analyticsDaysSelect ? analyticsDaysSelect.value : 30;
  try {
    const data = await fetchJson(`/api/metrics/roll-forward?days=${days}`);
    const buckets = data.buckets || [];
    const matrix = data.matrix || {};
    if (!buckets.length) {
      rollForwardMatrixBox.textContent = "No DPD snapshot data yet. Run some calls to populate.";
      return;
    }
    // Find max value for heat-map scaling
    let maxVal = 0;
    buckets.forEach((from) => {
      buckets.forEach((to) => {
        const v = (matrix[from] || {})[to] || 0;
        if (v > maxVal) maxVal = v;
      });
    });
    let html = '<table class="admin-table" style="border-collapse:collapse;">';
    html += "<thead><tr><th>From \\ To</th>";
    buckets.forEach((b) => { html += `<th>${b}</th>`; });
    html += "</tr></thead><tbody>";
    buckets.forEach((from) => {
      html += `<tr><td style="font-weight:600;">${from}</td>`;
      buckets.forEach((to) => {
        const v = (matrix[from] || {})[to] || 0;
        const pct = maxVal > 0 ? Math.round((v / maxVal) * 80) : 0;
        const bg = `rgba(92,172,255,${(pct / 100).toFixed(2)})`;
        html += `<td style="text-align:center;background:${bg};padding:6px 10px;">${v > 0 ? v : ""}</td>`;
      });
      html += "</tr>";
    });
    html += "</tbody></table>";
    rollForwardMatrixBox.innerHTML = html;
    if (rollForwardSummary) {
      const pct = typeof data.roll_forward_pct === "number" ? data.roll_forward_pct.toFixed(1) + "%" : "—";
      rollForwardSummary.textContent = `Overall roll-forward rate: ${pct} over last ${days} days`;
    }
  } catch (e) {
    if (rollForwardMatrixBox) rollForwardMatrixBox.textContent = `Error: ${e.message}`;
  }
}

async function loadRecoveryTrend() {
  const days = analyticsDaysSelect ? analyticsDaysSelect.value : 30;
  try {
    const data = await fetchJson(`/api/metrics/recovery?days=${days}`);
    if (recoveryKpis) {
      const kpis = [
        { label: "Total Recovered", value: "₹" + (data.total_recovered || 0).toLocaleString() },
        { label: "Portfolio Value", value: "₹" + (data.portfolio_value || 0).toLocaleString() },
        { label: "Recovery Rate", value: (data.recovery_rate_pct || 0).toFixed(2) + "%" },
      ];
      recoveryKpis.innerHTML = kpis.map((k) =>
        `<div class="admin-metric"><div class="admin-metric-label">${k.label}</div><div class="admin-metric-value">${k.value}</div></div>`
      ).join("");
    }
    // Draw sparkline
    const dates = data.dates || [];
    const amounts = data.amounts || [];
    if (recoverySparkline && dates.length > 1) {
      const w = recoverySparkline.clientWidth || 600;
      const h = 70;
      const maxAmt = Math.max(...amounts, 1);
      const pts = amounts.map((a, i) => {
        const x = (i / (amounts.length - 1)) * w;
        const y = h - (a / maxAmt) * (h - 8) - 4;
        return `${x},${y}`;
      }).join(" ");
      recoverySparkline.innerHTML = `
        <polyline fill="none" stroke="rgba(92,172,255,0.85)" stroke-width="2" points="${pts}"/>
        <text x="4" y="12" fill="rgba(255,255,255,0.45)" font-size="10">${dates[0] || ""}</text>
        <text x="${w - 50}" y="12" fill="rgba(255,255,255,0.45)" font-size="10">${dates[dates.length - 1] || ""}</text>
      `;
    }
    // Reconciliation table
    if (reconciliationTable) {
      const tbody = reconciliationTable.querySelector("tbody");
      const rows = data.reconciliation || [];
      tbody.innerHTML = rows.map((r) =>
        `<tr><td>${r.date || "—"}</td><td>${r.session_id || "—"}</td><td>${r.customer_id || "—"}</td><td>₹${(r.amount || 0).toLocaleString()}</td></tr>`
      ).join("") || "<tr><td colspan='4' style='text-align:center;opacity:.45;'>No data yet</td></tr>";
    }
  } catch (e) {
    setStatus(`Recovery trend error: ${e.message}`);
  }
}

async function loadAgentLeaderboard() {
  if (!agentLeaderboardTable) return;
  try {
    const data = await fetchJson("/api/metrics/agents");
    const agents = data.agents || [];
    const tbody = agentLeaderboardTable.querySelector("tbody");
    if (!agents.length) {
      tbody.innerHTML = "<tr><td colspan='9' style='text-align:center;opacity:.45;'>No agent data yet</td></tr>";
      return;
    }
    tbody.innerHTML = agents.map((a) => `
      <tr>
        <td>${a.rank || "—"}</td>
        <td>${a.display_name || a.agent_id || "—"}</td>
        <td>${a.total_calls || 0}</td>
        <td>${(a.connect_rate_pct || 0).toFixed(1)}%</td>
        <td>${(a.avg_handle_time_s || 0).toFixed(0)}</td>
        <td>${a.ptp_count || 0}</td>
        <td>${(a.ptp_conversion_pct || 0).toFixed(1)}%</td>
        <td>${a.escalations || 0}</td>
        <td>${a.compliance_violations || 0}</td>
      </tr>
    `).join("");
  } catch (e) {
    setStatus(`Agent leaderboard error: ${e.message}`);
  }
}

async function loadAnalytics() {
  await Promise.allSettled([loadRollForward(), loadRecoveryTrend(), loadAgentLeaderboard()]);
}

if (refreshAnalyticsBtn) {
  refreshAnalyticsBtn.addEventListener("click", loadAnalytics);
}
if (analyticsDaysSelect) {
  analyticsDaysSelect.addEventListener("change", loadAnalytics);
}
loadAnalytics();

// ===========================================================================
// BORROWER 360 TAB
// ===========================================================================

const borrowerSearchInput = document.getElementById("borrowerSearchInput");
const borrowerSearchBtn = document.getElementById("borrowerSearchBtn");
const borrower360Content = document.getElementById("borrower360Content");
const borrower360Placeholder = document.getElementById("borrower360Placeholder");
const borrowerProfileCard = document.getElementById("borrowerProfileCard");
const borrowerTimeline = document.getElementById("borrowerTimeline");
const borrowerLoansTable = document.getElementById("borrowerLoansTable");
const nbaCard = document.getElementById("nbaCard");
const settlementsTable = document.getElementById("settlementsTable");
const settlementAmountInput = document.getElementById("settlementAmountInput");
const settlementOriginalInput = document.getElementById("settlementOriginalInput");
const createSettlementBtn = document.getElementById("createSettlementBtn");
const settlementMessage = document.getElementById("settlementMessage");
const b360TabBtns = Array.from(document.querySelectorAll(".b360-tab-btn"));

let activeB360Tab = "timeline";
let currentBorrowerCustomerId = null;
let lastBorrower360Session = null;
let latestNegotiableOfferId = null;

function setB360Tab(tab) {
  activeB360Tab = tab;
  const panels = {
    timeline: document.getElementById("b360TabTimeline"),
    loans: document.getElementById("b360TabLoans"),
    nba: document.getElementById("b360TabNba"),
    settlements: document.getElementById("b360TabSettlements"),
  };
  Object.entries(panels).forEach(([name, panel]) => {
    if (panel) panel.style.display = name === activeB360Tab ? "" : "none";
  });
  b360TabBtns.forEach((btn) => {
    btn.style.opacity = btn.dataset.b360tab === activeB360Tab ? "1" : "0.65";
  });
}

b360TabBtns.forEach((btn) => {
  btn.addEventListener("click", () => setB360Tab(btn.dataset.b360tab));
});
setB360Tab("timeline");

function timelineEventHtml(event) {
  const icons = {
    call: "📞", payment: "💳", settlement: "🤝", followup: "📅",
    summary: "📝", ptp_saved: "📌", escalation: "⚠️", compliance_violation: "🚨", event: "•",
  };
  const icon = icons[event.type] || "•";
  const ts = event.ts ? new Date(event.ts * 1000).toLocaleString() : "—";
  let detail = "";
  if (event.type === "call") {
    detail = `Disposition: <strong>${event.disposition || "—"}</strong>${event.ptp_date ? ` · PTP: ${event.ptp_date}` : ""}`;
  } else if (event.type === "payment") {
    detail = `₹${(event.amount || 0).toLocaleString()} via ${event.rail || "—"} · <strong>${event.status || "—"}</strong>`;
  } else if (event.type === "settlement") {
    detail = `₹${(event.offered_amount || 0).toLocaleString()} offer · <strong>${event.status || "—"}</strong>`;
  } else if (event.type === "summary") {
    detail = `Sentiment: ${event.sentiment || "—"} · ${event.commitment || ""}`;
  } else if (event.type === "followup") {
    detail = `Channel: ${event.channel || "—"} · ${event.status || "—"}`;
  } else {
    detail = JSON.stringify(event.payload || {}).slice(0, 80);
  }
  return `<div style="display:flex;gap:10px;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.07);">
    <div style="font-size:18px;min-width:24px;text-align:center;">${icon}</div>
    <div style="flex:1;">
      <div style="display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;">
        <span class="badge badge-soft">${event.type}</span>
        <span style="font-size:11px;color:rgba(255,255,255,0.45);">${ts}</span>
        ${event.session_id ? `<span style="font-size:11px;color:rgba(255,255,255,0.35);">${event.session_id}</span>` : ""}
      </div>
      <div style="font-size:13px;margin-top:3px;color:rgba(255,255,255,0.8);">${detail}</div>
    </div>
  </div>`;
}

async function loadBorrower360(customerId) {
  currentBorrowerCustomerId = customerId;
  try {
    const data = await fetchJson(`/api/customers/${encodeURIComponent(customerId)}/360`);
    if (borrower360Content) borrower360Content.style.display = "";
    if (borrower360Placeholder) borrower360Placeholder.style.display = "none";

    // Profile card
    if (borrowerProfileCard) {
      const p = data.profile || {};
      borrowerProfileCard.innerHTML = [
        `<div><div class="admin-metric-label">Customer ID</div><div class="admin-metric-value" style="font-size:14px;">${p.customer_id || customerId}</div></div>`,
        `<div><div class="admin-metric-label">Name</div><div class="admin-metric-value" style="font-size:14px;">${p.full_name || "—"}</div></div>`,
        `<div><div class="admin-metric-label">Phone</div><div class="admin-metric-value" style="font-size:14px;">${p.phone || "—"}</div></div>`,
        `<div><div class="admin-metric-label">DPD</div><div class="admin-metric-value" style="font-size:14px;color:${(p.dpd || 0) > 60 ? "#ff6b6b" : "inherit"}">${p.dpd ?? "—"}</div></div>`,
        `<div><div class="admin-metric-label">Risk Band</div><div class="admin-metric-value" style="font-size:14px;">${p.risk_band || "—"}</div></div>`,
      ].join("");
    }

    // Timeline
    if (borrowerTimeline) {
      const events = data.timeline || [];
      borrowerTimeline.innerHTML = events.length
        ? events.map(timelineEventHtml).join("")
        : "<div style='opacity:.45;'>No timeline events yet.</div>";
    }

    // Loans
    if (borrowerLoansTable) {
      const tbody = borrowerLoansTable.querySelector("tbody");
      const loans = data.loan_accounts || [];
      tbody.innerHTML = loans.map((l) =>
        `<tr><td>${l.loan_account_id || "—"}</td><td>${l.product_type || "—"}</td><td>₹${(l.principal_outstanding || 0).toLocaleString()}</td><td>₹${(l.emi_amount || 0).toLocaleString()}</td><td>${l.due_date || "—"}</td><td>${l.dpd ?? "—"}</td><td>${l.status || "—"}</td></tr>`
      ).join("") || "<tr><td colspan='7' style='text-align:center;opacity:.45;'>No loans</td></tr>";
    }

    setStatus(`Borrower 360 loaded for ${customerId}`);
  } catch (e) {
    setStatus(`Borrower 360 error: ${e.message}`);
  }
}

async function loadNba(customerId) {
  if (!nbaCard) return;
  try {
    const data = await fetchJson(`/api/customers/${encodeURIComponent(customerId)}/nba`);
    const nba = data.nba || {};
    const action = nba.action || nba.recommended_action || nba.recommendation || {};
    const actionType = action.action_type || action.action || nba.action_type || "—";
    const channel = action.channel || nba.channel || "—";
    const timing = action.timing || action.delay || "immediate";
    const msgTemplate = action.message_template || action.script || (nba.message && nba.message.text) || "—";
    const rationale = action.rationale || nba.rationale || "—";
    nbaCard.innerHTML = `
      <div style="display:grid;gap:8px;">
        <div><span class="admin-metric-label">Recommended Action</span><br/><strong>${actionType}</strong></div>
        <div><span class="admin-metric-label">Channel</span> ${channel}</div>
        <div><span class="admin-metric-label">Timing</span> ${timing}</div>
        <div><span class="admin-metric-label">Message Template</span><br/><span style="font-size:12px;opacity:.75;">${msgTemplate}</span></div>
        <div><span class="admin-metric-label">Rationale</span><br/><span style="font-size:12px;opacity:.75;">${rationale}</span></div>
        ${nba.requires_approval ? '<div><span class="badge badge-soft" style="color:#ffa94d;">Requires Approval</span></div>' : ""}
      </div>
    `;
  } catch (e) {
    if (nbaCard) nbaCard.innerHTML = `<span style="opacity:.45;">NBA error: ${e.message}</span>`;
  }
}

async function loadSettlements(customerId) {
  if (!settlementsTable) return;
  try {
    const data = await fetchJson(`/api/customers/${encodeURIComponent(customerId)}/settlements`);
    const tbody = settlementsTable.querySelector("tbody");
    const offers = data.offers || [];
    latestNegotiableOfferId = null;
    for (const offer of offers) {
      const st = String(offer.status || "").toUpperCase();
      if (st === "OPEN" || st === "PENDING" || st === "COUNTERED") {
        latestNegotiableOfferId = offer.id || null;
        break;
      }
    }
    tbody.innerHTML = offers.map((o) => {
      const expiry = o.expiry_ts ? new Date(o.expiry_ts * 1000).toLocaleDateString() : "—";
      const created = o.created_at ? new Date(o.created_at * 1000).toLocaleDateString() : "—";
      return `<tr><td>${o.id || "—"}</td><td>₹${(o.offered_amount || 0).toLocaleString()}</td><td>${o.status || "—"}</td><td>${expiry}</td><td>${created}</td></tr>`;
    }).join("") || "<tr><td colspan='5' style='text-align:center;opacity:.45;'>No settlement offers</td></tr>";
  } catch (e) {
    setStatus(`Settlements error: ${e.message}`);
  }
}

if (borrowerSearchBtn) {
  borrowerSearchBtn.addEventListener("click", async () => {
    const cid = borrowerSearchInput ? borrowerSearchInput.value.trim() : "";
    if (!cid) return;
    await loadBorrower360(cid);
    await Promise.allSettled([loadNba(cid), loadSettlements(cid)]);
  });
}

if (createSettlementBtn) {
  createSettlementBtn.addEventListener("click", async () => {
    if (!currentBorrowerCustomerId) return;
    const offered = parseFloat(settlementAmountInput ? settlementAmountInput.value : 0);
    const original = parseFloat(settlementOriginalInput ? settlementOriginalInput.value : 0);
    if (!offered || offered <= 0) { setStatus("Enter offered amount"); return; }
    // We use a fake session_id based on customer for the demo
    const sessionId = `demo-${currentBorrowerCustomerId}`;
    try {
      const body = { offered_amount: offered, customer_id: currentBorrowerCustomerId };
      if (original > 0) body.original_amount = original;
      if (latestNegotiableOfferId) body.counter_offer_of = latestNegotiableOfferId;
      const data = await fetchJson(`/api/sessions/${sessionId}/settlement`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const discount = (data.discount_pct || 0).toFixed(1);
      const round = data.round || data.offer?.terms?.round || 1;
      const counterOf = data.counter_offer_of || data.offer?.terms?.counter_of || null;
      const msg = `Offer created: ${data.offer?.id || "—"} · Round ${round}${counterOf ? ` · Counter of ${counterOf}` : ""} · Discount: ${discount}%${data.requires_approval ? " · ⚠️ Requires manager approval" : ""}`;
      if (settlementMessage) settlementMessage.textContent = msg;
      await loadSettlements(currentBorrowerCustomerId);
    } catch (e) {
      setStatus(`Create settlement error: ${e.message}`);
    }
  });
}

// ===========================================================================
// CALL SUMMARIES TAB
// ===========================================================================

const summarySearchInput = document.getElementById("summarySearchInput");
const summarySearchBtn = document.getElementById("summarySearchBtn");
const summaryRefreshBtn = document.getElementById("summaryRefreshBtn");
const summaryList = document.getElementById("summaryList");

function renderSummaryCard(s) {
  const ts = s.generated_ts ? new Date(s.generated_ts * 1000).toLocaleString() : "—";
  const facts = Array.isArray(s.key_facts) ? s.key_facts : [];
  const factsHtml = facts.slice(0, 3).map((f) => `<span class="badge badge-soft" style="font-size:11px;">${f}</span>`).join(" ");
  return `<div style="padding:10px;background:rgba(255,255,255,0.04);border-radius:8px;border:1px solid rgba(92,172,255,0.12);">
    <div style="display:flex;gap:10px;align-items:baseline;flex-wrap:wrap;margin-bottom:6px;">
      <span class="badge badge-soft">${s.disposition || "—"}</span>
      <span style="font-size:12px;opacity:.55;">${ts}</span>
      <span style="font-size:12px;opacity:.45;">${s.session_id || "—"}</span>
      ${s.customer_id ? `<span style="font-size:12px;opacity:.55;">Customer: ${s.customer_id}</span>` : ""}
      ${s.sentiment ? `<span style="font-size:12px;opacity:.7;">Sentiment: ${s.sentiment}</span>` : ""}
    </div>
    <div style="margin-bottom:6px;">${factsHtml}</div>
    ${s.commitment ? `<div style="font-size:12px;margin-bottom:4px;"><strong>Commitment:</strong> ${s.commitment}</div>` : ""}
    ${s.next_step ? `<div style="font-size:12px;opacity:.75;"><strong>Next Step:</strong> ${s.next_step}</div>` : ""}
  </div>`;
}

async function loadSummaries(query) {
  if (!summaryList) return;
  summaryList.innerHTML = "<div style='opacity:.45;'>Loading…</div>";
  try {
    const q = encodeURIComponent(query || "");
    const data = await fetchJson(`/api/summaries/search?q=${q}&limit=30`);
    const rows = data.summaries || [];
    summaryList.innerHTML = rows.length
      ? rows.map(renderSummaryCard).join("")
      : "<div style='opacity:.45;'>No summaries found. Summaries are generated after each call ends.</div>";
  } catch (e) {
    summaryList.innerHTML = `<div style="opacity:.45;">Error: ${e.message}</div>`;
  }
}

if (summarySearchBtn) {
  summarySearchBtn.addEventListener("click", () => {
    loadSummaries(summarySearchInput ? summarySearchInput.value.trim() : "");
  });
}
if (summaryRefreshBtn) {
  summaryRefreshBtn.addEventListener("click", () => loadSummaries(""));
}
if (summarySearchInput) {
  summarySearchInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") loadSummaries(summarySearchInput.value.trim());
  });
}
loadSummaries("");

// ===========================================================================
// CRM SYNC TAB
// ===========================================================================

const crmSyncNowBtn = document.getElementById("crmSyncNowBtn");
const crmStatusRefreshBtn = document.getElementById("crmStatusRefreshBtn");
const crmStatusKpis = document.getElementById("crmStatusKpis");
const crmSyncLogTable = document.getElementById("crmSyncLogTable");

async function loadCrmStatus() {
  try {
    const data = await fetchJson("/api/crm/status");
    const status = data.status || {};
    const counts = status.counts || {};
    if (crmStatusKpis) {
      const kpis = [
        { label: "Provider", value: "Zoho" },
        { label: "Pushed (OK)", value: counts.ok || 0 },
        { label: "Failed", value: counts.failed || 0 },
        { label: "Conflicts", value: counts.conflict || 0 },
        { label: "Last Sync", value: status.last_sync_ts ? new Date(status.last_sync_ts * 1000).toLocaleTimeString() : "Never" },
      ];
      crmStatusKpis.innerHTML = kpis.map((k) =>
        `<div class="admin-metric"><div class="admin-metric-label">${k.label}</div><div class="admin-metric-value" style="font-size:14px;">${k.value}</div></div>`
      ).join("");
    }
    if (crmSyncLogTable) {
      const tbody = crmSyncLogTable.querySelector("tbody");
      const rows = data.log || [];
      tbody.innerHTML = rows.map((r) => {
        const ts = r.created_at ? new Date(r.created_at * 1000).toLocaleString() : "—";
        return `<tr>
          <td>${ts}</td>
          <td>${r.session_id || "—"}</td>
          <td>${r.customer_id || "—"}</td>
          <td>${r.direction || "—"}</td>
          <td><span class="badge badge-soft" style="${r.status === "ok" ? "color:#63e6be;" : r.status === "failed" ? "color:#ff6b6b;" : ""}">${r.status || "—"}</span></td>
          <td>${r.zoho_record_id || "—"}</td>
          <td>${r.retry_count || 0}</td>
        </tr>`;
      }).join("") || "<tr><td colspan='7' style='text-align:center;opacity:.45;'>No sync log entries yet</td></tr>";
    }
  } catch (e) {
    setStatus(`CRM status error: ${e.message}`);
  }
}

if (crmStatusRefreshBtn) {
  crmStatusRefreshBtn.addEventListener("click", loadCrmStatus);
}

if (crmSyncNowBtn) {
  crmSyncNowBtn.addEventListener("click", async () => {
    crmSyncNowBtn.disabled = true;
    crmSyncNowBtn.textContent = "Syncing…";
    try {
      const data = await fetchJson("/api/crm/sync", { method: "POST" });
      const stats = data.stats || {};
      setStatus(`CRM sync done: retried=${stats.retried || 0}, recovered=${stats.recovered || 0}, still_failed=${stats.still_failed || 0}`);
      await loadCrmStatus();
    } catch (e) {
      setStatus(`CRM sync error: ${e.message}`);
    } finally {
      crmSyncNowBtn.disabled = false;
      crmSyncNowBtn.textContent = "Sync Now";
    }
  });
}

loadCrmStatus();
