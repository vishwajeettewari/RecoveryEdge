const refreshBtn = document.getElementById("refreshBtn");
const reindexBtn = document.getElementById("reindexBtn");
const metricsBox = document.getElementById("metricsBox");
const sessionsTable = document.getElementById("sessionsTable");
const adminStatus = document.getElementById("adminStatus");

function setStatus(msg) {
  if (!adminStatus) return;
  adminStatus.textContent = msg || "";
}

async function fetchJson(path, opts) {
  const res = await fetch(path, opts || {});
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`${res.status}: ${txt}`);
  }
  return res.json();
}

function renderMetrics(m) {
  if (!metricsBox) return;
  metricsBox.textContent =
    `sessions_today=${m.sessions_today} ` +
    `ptp_count=${m.ptp_count} ` +
    `callback_count=${m.callback_count} ` +
    `escalations=${m.escalations} ` +
    `avg_handle_seconds=${m.avg_handle_seconds === null ? "n/a" : m.avg_handle_seconds.toFixed(2)}`;
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
      td.style.padding = "8px";
      td.style.borderTop = "1px solid rgba(255,255,255,0.08)";
      td.textContent = c;
      tr.appendChild(td);
    });

    const tdAction = document.createElement("td");
    tdAction.style.padding = "8px";
    tdAction.style.borderTop = "1px solid rgba(255,255,255,0.08)";
    const btn = document.createElement("button");
    btn.className = "secondary-btn";
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

refresh();
setInterval(refresh, 1000);
