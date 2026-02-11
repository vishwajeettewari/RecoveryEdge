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
const tasksTable = document.getElementById("tasksTable");
const taskDetailBox = document.getElementById("taskDetailBox");
const bulkIdsInput = document.getElementById("bulkIdsInput");
const bulkActionSelect = document.getElementById("bulkActionSelect");
const bulkPayloadInput = document.getElementById("bulkPayloadInput");
const bulkApplyBtn = document.getElementById("bulkApplyBtn");

const alertStatusFilter = document.getElementById("alertStatusFilter");
const alertTypeFilter = document.getElementById("alertTypeFilter");
const evaluateAlertsBtn = document.getElementById("evaluateAlertsBtn");
const alertsTable = document.getElementById("alertsTable");
const alertRulesBox = document.getElementById("alertRulesBox");

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
  if (!tasksTable) return;
  const tbody = tasksTable.querySelector("tbody");
  if (!tbody) return;
  tbody.innerHTML = "";

  (rows || []).forEach((t) => {
    const tr = document.createElement("tr");
    const sla = t.sla_due_at ? new Date(t.sla_due_at * 1000).toLocaleString() : "-";
    const cells = [t.id, t.campaign_id, `${t.customer_id}${t.customer_name ? " — " + t.customer_name : ""}`, t.state, String(t.dpd ?? ""), `${sla}${t.sla_breach ? " (BREACH)" : ""}`];
    cells.forEach((v) => {
      const td = document.createElement("td");
      td.textContent = v;
      tr.appendChild(td);
    });

    const tdComp = document.createElement("td");
    tdComp.innerHTML = complianceBadgesHtml(t) + (t.compliance_block ? " <strong>BLOCKED</strong>" : "");
    tr.appendChild(tdComp);

    const tdAction = document.createElement("td");
    const claimBtn = document.createElement("button");
    claimBtn.className = "secondary-btn btn-sm";
    claimBtn.textContent = "Claim";
    claimBtn.onclick = async () => {
      try {
        const out = await fetchJson(`/api/tasks/${encodeURIComponent(t.id)}/claim`, { method: "POST" });
        if (!out.ok) throw new Error(out.error || "claim_failed");
        await refreshTasks();
      } catch (e) {
        setStatus(`Claim error: ${e.message}`);
      }
    };

    const detailBtn = document.createElement("button");
    detailBtn.className = "secondary-btn btn-sm";
    detailBtn.style.marginLeft = "6px";
    detailBtn.textContent = "Detail";
    detailBtn.onclick = () => loadTaskDetail(t.id);

    tdAction.appendChild(claimBtn);
    tdAction.appendChild(detailBtn);
    tr.appendChild(tdAction);
    tbody.appendChild(tr);
  });
}

async function loadTaskDetail(taskId) {
  try {
    const t = await fetchJson(`/api/tasks/${encodeURIComponent(taskId)}`);
    if (!taskDetailBox) return;
    const events = (t.events || []).slice(0, 20).map((e) => `${new Date((e.ts || 0) * 1000).toLocaleTimeString()} | ${e.event_type} | ${e.payload_json || ""}`);
    taskDetailBox.innerHTML =
      `<div><strong>Task ${t.id}</strong> (${t.state})</div>` +
      `<div>Compliance: ${complianceBadgesHtml(t)} ${t.compliance_block ? "<strong>BLOCKED</strong>" : ""}</div>` +
      `<div style="margin-top:8px;display:flex;gap:8px;align-items:center;flex-wrap:wrap;">` +
      `<select id="taskStateInput" class="demo-input">` +
      ["NEW", "IN_PROGRESS", "PTP", "CALLBACK", "ESCALATED", "CLOSED"].map((s) => `<option value="${s}" ${t.state === s ? "selected" : ""}>${s}</option>`).join("") +
      `</select>` +
      `<input id="taskDispositionInput" class="demo-input" placeholder="disposition" value="${t.disposition || ""}" />` +
      `<input id="taskNotesInput" class="demo-input" placeholder="notes" value="${t.notes || ""}" />` +
      `<label><input id="taskOverrideInput" type="checkbox" /> supervisor override</label>` +
      `<button id="saveTaskBtn" class="secondary-btn btn-sm" type="button">Save Task</button>` +
      `</div>` +
      `<pre style="margin-top:10px;max-height:180px;overflow:auto;">${events.join("\n") || "No events"}</pre>`;

    const saveBtn = document.getElementById("saveTaskBtn");
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
  (rows || []).forEach((a) => {
    const tr = document.createElement("tr");
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
    const tdAction = document.createElement("td");

    const ackBtn = document.createElement("button");
    ackBtn.className = "secondary-btn btn-sm";
    ackBtn.textContent = "Ack";
    ackBtn.onclick = async () => {
      try {
        await fetchJson(`/api/alerts/${encodeURIComponent(a.id)}/ack`, { method: "POST" });
        await refreshAlerts();
      } catch (e) {
        setStatus(`Alert ack error: ${e.message}`);
      }
    };

    const resBtn = document.createElement("button");
    resBtn.className = "secondary-btn btn-sm";
    resBtn.style.marginLeft = "6px";
    resBtn.textContent = "Resolve";
    resBtn.onclick = async () => {
      try {
        await fetchJson(`/api/alerts/${encodeURIComponent(a.id)}/resolve`, { method: "POST" });
        await refreshAlerts();
      } catch (e) {
        setStatus(`Alert resolve error: ${e.message}`);
      }
    };

    tdAction.appendChild(ackBtn);
    tdAction.appendChild(resBtn);
    tr.appendChild(tdAction);
    tbody.appendChild(tr);
  });
}

function renderAlertRules(rows) {
  if (!alertRulesBox) return;
  const text = (rows || []).map((r) => `${r.name} [${r.type}] enabled=${r.enabled}`).join("\n");
  alertRulesBox.textContent = text || "No alert rules";
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

if (evaluateAlertsBtn) evaluateAlertsBtn.addEventListener("click", evaluateAlerts);
if (alertStatusFilter) alertStatusFilter.addEventListener("change", refreshAlerts);
if (alertTypeFilter) alertTypeFilter.addEventListener("change", refreshAlerts);

if (saveReportScheduleBtn) saveReportScheduleBtn.addEventListener("click", saveReportSchedule);
if (generateReportsBtn) generateReportsBtn.addEventListener("click", generateReportsNow);

if (refreshIntegrationsBtn) refreshIntegrationsBtn.addEventListener("click", refreshIntegrations);
if (sendInboundSampleBtn) sendInboundSampleBtn.addEventListener("click", sendInboundSample);

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

refresh();
setInterval(refresh, 5000);
