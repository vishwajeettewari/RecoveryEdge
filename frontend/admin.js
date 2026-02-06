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
const ADMIN_TOKEN_KEY = "te_admin_token";

function setStatus(msg) {
  if (!adminStatus) return;
  const ts = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  adminStatus.textContent = `[${ts}] ${msg || ""}`;
}

async function fetchJson(path, opts) {
  const options = { ...(opts || {}) };
  options.headers = { ...(options.headers || {}) };
  const token = (adminTokenInput && adminTokenInput.value ? adminTokenInput.value : "").trim();
  if (token) {
    options.headers.Authorization = `Bearer ${token}`;
  }
  const res = await fetch(path, options);
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`${res.status}: ${txt}`);
  }
  return res.json();
}

function renderMetrics(m) {
  if (!metricsBox) return;
  if (metricSessionsToday) metricSessionsToday.textContent = String(m.sessions_today ?? 0);
  if (metricPtpCount) metricPtpCount.textContent = String(m.ptp_count ?? 0);
  if (metricCallbackCount) metricCallbackCount.textContent = String(m.callback_count ?? 0);
  if (metricEscalations) metricEscalations.textContent = String(m.escalations ?? 0);
  if (metricAht) {
    metricAht.textContent =
      m.avg_handle_seconds == null ? "n/a" : Number(m.avg_handle_seconds).toFixed(1);
  }
  metricsBox.textContent =
    `Live: ${m.sessions_today ?? 0} sessions, ${m.ptp_count ?? 0} PTP, ` +
    `${m.callback_count ?? 0} callbacks, ${m.escalations ?? 0} escalations. ` +
    `AHT ${m.avg_handle_seconds == null ? "n/a" : Number(m.avg_handle_seconds).toFixed(2)}s`;
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
      s.current_step || "",
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
    const btn = document.createElement("button");
    btn.className = "secondary-btn btn-sm";
    btn.type = "button";
    btn.textContent = "Close";
    btn.onclick = async () => {
      try {
        setStatus("Setting disposition…");
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
    tdAction.appendChild(btn);
    tr.appendChild(tdAction);
    tbody.appendChild(tr);
  });
}

async function refresh() {
  try {
    setStatus("Refreshing…");
    const [m, s] = await Promise.all([fetchJson("/api/metrics"), fetchJson("/api/sessions")]);
    renderMetrics(m);
    renderSessions(s.sessions || []);
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
      const token = (adminTokenInput && adminTokenInput.value ? adminTokenInput.value : "").trim();
      if (token) headers.Authorization = `Bearer ${token}`;
      const res = await fetch("/api/export/demo.xlsx", { headers });
      if (!res.ok) {
        const txt = await res.text();
        throw new Error(`${res.status}: ${txt}`);
      }
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
setInterval(refresh, 3000);
