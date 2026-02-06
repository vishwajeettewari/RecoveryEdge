const statusDot = document.getElementById("statusDot");
const statusText = document.getElementById("statusText");
const toggleBtn = document.getElementById("toggleBtn");
const muteBtn = document.getElementById("muteBtn");
const autoScrollBtn = document.getElementById("autoScrollBtn");
const clearChatBtn = document.getElementById("clearChatBtn");
const turnBadge = document.getElementById("turnBadge");
const chatStream =
  document.getElementById("chatStream") || document.querySelector(".chat-stream");
const chatEmpty =
  document.getElementById("chatEmpty") ||
  (chatStream ? chatStream.querySelector(".chat-empty") : null);
const micMeterFill = document.getElementById("micMeterFill");
const bargeStatus = document.getElementById("bargeStatus");
const languageValue = document.getElementById("languageValue");
const latencyValue = document.getElementById("latencyValue");
const hudState = document.getElementById("hudState");
const hudDuration = document.getElementById("hudDuration");
const hudTurns = document.getElementById("hudTurns");
const hudInterruptions = document.getElementById("hudInterruptions");
const hudLanguage = document.getElementById("hudLanguage");
const hudLastEvent = document.getElementById("hudLastEvent");

// Customer intelligence panel values
const customerNameValue = document.getElementById("customerNameValue");
const customerPhoneValue = document.getElementById("customerPhoneValue");
const customerCityValue = document.getElementById("customerCityValue");
const loanIdValue = document.getElementById("loanIdValue");
const loanAmountValue = document.getElementById("loanAmountValue");
const loanDueValue = document.getElementById("loanDueValue");
const dpdBadge = document.getElementById("dpdBadge");
const intentValue = document.getElementById("intentValue");
const riskValue = document.getElementById("riskValue");
const promiseValue = document.getElementById("promiseValue");

// Demo controls (customer selection only)
const customerSelect = document.getElementById("customerSelect");
const reloadCustomersBtn = document.getElementById("reloadCustomersBtn");

// Enterprise UI elements
const typingIndicator = document.getElementById("typingIndicator");
const sentimentValue = document.getElementById("sentimentValue");
const workflowSteps = document.getElementById("workflowSteps");
const dispositionActions = document.getElementById("dispositionActions");
const compConsent = document.getElementById("compConsent");
const compIdentity = document.getElementById("compIdentity");
const compDisclosure = document.getElementById("compDisclosure");

// Theme toggle (works even if the button structure changes)
const themeToggleEl =
  document.getElementById("themeToggle") ||
  document.getElementById("themeBtn") ||
  document.querySelector("[data-theme-toggle]") ||
  document.querySelector(".theme-toggle");

// Optional: waveform canvas (if present in index.html)
const waveCanvas =
  document.getElementById("waveCanvas") ||
  document.getElementById("pcmCanvas") ||
  document.querySelector("canvas[data-waveform]") ||
  document.querySelector("canvas.wave-canvas");

let ws = null;
let audioContext = null;
let micStream = null;
let workletNode = null;
let sourceNode = null;
let silentGain = null;
let ttsGain = null;
let playhead = 0;
let activeSources = [];
let running = false;
let muted = false;
let assistantBuffer = "";
let transcriptBuffer = "";
let meterLevel = 0;
let currentState = "disconnected";
let assistantCommittedThisTurn = false;
let userLiveBubble = null;
let agentLiveBubble = null;
let currentContext = {};
let customersIndex = {};
let lastChatByRole = { user: "", assistant: "" };
let lastChatAt = { user: 0, assistant: 0 };
let lastChatNorm = { user: "", assistant: "" };
const useTimelineEvents = true;
const timelineBubbles = new Map();
let autoScrollEnabled = true;
let sessionStartedAtMs = 0;
let sessionTimer = null;
let turnCount = 0;
let interruptionCount = 0;
const countedAssistantTurns = new Set();

// Theme
let currentTheme = "dark";
let parallaxRaf = null;
let parallaxTargetX = 0;
let parallaxTargetY = 0;
let parallaxCurrentX = 0;
let parallaxCurrentY = 0;

// Waveform
let analyserNode = null;
let waveRafId = null;
let waveCtx = null;
let waveData = null;
let cachedAccent = null;
let waveResizeHandler = null;
let waveMode = "idle"; // "idle" (no mic) | "live" (mic)
let waveIdlePhase = 0;

const FRAME_SAMPLES = 320;
const TARGET_SAMPLE_RATE = 16000;

function cssVar(name, fallback = "") {
  try {
    const v = getComputedStyle(document.documentElement)
      .getPropertyValue(name)
      .trim();
    return v || fallback;
  } catch (e) {
    return fallback;
  }
}

function statusColorFor(state) {
  const accent = cssVar("--accent", "#2d6bff");
  const accent2 = cssVar("--accent2", accent);
  const text = cssVar("--text", "#f5f5f5");
  const muted = cssVar("--muted", "#6b7280");

  switch (state) {
    case "connecting":
      return accent2;
    case "listening":
      return accent;
    case "thinking":
      return accent2;
    case "speaking":
      return text;
    case "ready":
      return text;
    case "disconnected":
    default:
      return muted;
  }
}

function formatClockTime(ts) {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch (e) {
    return "—";
  }
}

function formatDuration(ms) {
  const total = Math.max(0, Math.floor((ms || 0) / 1000));
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

function updateHudDuration() {
  if (!hudDuration) return;
  if (!running || !sessionStartedAtMs) {
    hudDuration.textContent = "00:00";
    return;
  }
  hudDuration.textContent = formatDuration(Date.now() - sessionStartedAtMs);
}

function setHudLastEvent(text) {
  if (!hudLastEvent) return;
  hudLastEvent.textContent = (text || "Ready").toString().slice(0, 48);
}

function setAutoScroll(enabled) {
  autoScrollEnabled = !!enabled;
  if (!autoScrollBtn) return;
  autoScrollBtn.setAttribute("aria-pressed", autoScrollEnabled ? "true" : "false");
  autoScrollBtn.textContent = autoScrollEnabled ? "Auto-scroll: On" : "Auto-scroll: Off";
}

function scrollChatToBottom(force = false) {
  if (!chatStream) return;
  if (force || autoScrollEnabled) {
    chatStream.scrollTop = chatStream.scrollHeight;
  }
}

function updateTurnUi() {
  if (hudTurns) hudTurns.textContent = String(turnCount);
  if (turnBadge) turnBadge.textContent = `${turnCount} ${turnCount === 1 ? "turn" : "turns"}`;
}

function updateInterruptionUi() {
  if (hudInterruptions) hudInterruptions.textContent = String(interruptionCount);
}

function applyTheme(theme) {
  currentTheme = theme === "light" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", currentTheme);

  // Mirror theme on body as well (some CSS setups target body)
  if (document.body) {
    document.body.setAttribute("data-theme", currentTheme);
    document.body.classList.toggle("theme-light", currentTheme === "light");
    document.body.classList.toggle("theme-dark", currentTheme === "dark");
  }

  // Update browser UI color hint (nice polish)
  try {
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      meta.setAttribute(
        "content",
        currentTheme === "light" ? "#eef3ff" : "#050a14"
      );
    }
  } catch (e) {
    // ignore
  }

  // keep toggle state accessible
  if (themeToggleEl) {
    themeToggleEl.setAttribute(
      "aria-pressed",
      currentTheme === "light" ? "true" : "false"
    );
    themeToggleEl.title =
      currentTheme === "light" ? "Switch to dark" : "Switch to light";
    themeToggleEl.setAttribute("aria-label", themeToggleEl.title);
    const iconNode = themeToggleEl.querySelector(".icon");
    if (iconNode) {
      iconNode.textContent = currentTheme === "light" ? "☼" : "◐";
    }
    themeToggleEl.classList.toggle("is-light", currentTheme === "light");
  }

  cachedAccent = null; // refresh waveform stroke color

  try {
    localStorage.setItem("te_theme", currentTheme);
  } catch (e) {
    // ignore
  }
}

function initTheme() {
  let saved = null;
  try {
    saved = localStorage.getItem("te_theme");
  } catch (e) {
    // ignore
  }

  const preferred =
    saved ||
    (window.matchMedia &&
    window.matchMedia("(prefers-color-scheme: light)").matches
      ? "light"
      : "dark");

  applyTheme(preferred);

  if (themeToggleEl) {
    themeToggleEl.addEventListener("click", () => {
      applyTheme(currentTheme === "dark" ? "light" : "dark");
    });
  }
}

function writeParallaxVars(x, y) {
  const rx = Math.max(-14, Math.min(14, x));
  const ry = Math.max(-14, Math.min(14, y));
  document.documentElement.style.setProperty("--parallax-x", `${rx.toFixed(2)}px`);
  document.documentElement.style.setProperty("--parallax-y", `${ry.toFixed(2)}px`);
  document.documentElement.style.setProperty("--parallax-tilt-x", `${(ry * -0.08).toFixed(2)}deg`);
  document.documentElement.style.setProperty("--parallax-tilt-y", `${(rx * 0.08).toFixed(2)}deg`);
}

function tickParallax() {
  parallaxCurrentX += (parallaxTargetX - parallaxCurrentX) * 0.11;
  parallaxCurrentY += (parallaxTargetY - parallaxCurrentY) * 0.11;
  writeParallaxVars(parallaxCurrentX, parallaxCurrentY);

  const dx = Math.abs(parallaxTargetX - parallaxCurrentX);
  const dy = Math.abs(parallaxTargetY - parallaxCurrentY);
  if (dx < 0.02 && dy < 0.02) {
    parallaxRaf = null;
    return;
  }
  parallaxRaf = requestAnimationFrame(tickParallax);
}

function queueParallax() {
  if (parallaxRaf) return;
  parallaxRaf = requestAnimationFrame(tickParallax);
}

function initParallax() {
  const prefersReducedMotion =
    window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const isCoarsePointer =
    window.matchMedia &&
    window.matchMedia("(pointer: coarse)").matches;

  if (prefersReducedMotion || isCoarsePointer) {
    writeParallaxVars(0, 0);
    return;
  }

  const onPointerMove = (event) => {
    const w = Math.max(window.innerWidth || 1, 1);
    const h = Math.max(window.innerHeight || 1, 1);
    const nx = event.clientX / w - 0.5;
    const ny = event.clientY / h - 0.5;
    parallaxTargetX = nx * 18;
    parallaxTargetY = ny * 16;
    queueParallax();
  };

  const reset = () => {
    parallaxTargetX = 0;
    parallaxTargetY = 0;
    queueParallax();
  };

  window.addEventListener("pointermove", onPointerMove, { passive: true });
  window.addEventListener("pointerleave", reset, { passive: true });
  window.addEventListener("blur", reset, { passive: true });
}

function attachAnalyserToWaveform() {
  // If the waveform loop started before the analyser existed (idle mode),
  // we must allocate the wave buffer now so "live" actually renders.
  if (!waveCanvas || !analyserNode) return;
  try {
    waveData = new Uint8Array(analyserNode.fftSize);
  } catch (e) {
    waveData = null;
  }
  waveMode = "live";
  // If the loop wasn't running yet, start it; otherwise the existing RAF will pick up waveData.
  if (!waveRafId) startWaveformLoop("live");
}

function startWaveformLoop(mode = "idle") {
  if (!waveCanvas) return;

  // If already running, don't start a second loop.
  if (waveRafId) return;

  waveMode = mode;
  waveCtx = waveCanvas.getContext("2d");
  let waveCssW = 0;
  let waveCssH = 0;
  let waveDpr = 1;

  const resize = () => {
    const rect = waveCanvas.getBoundingClientRect();
    waveCssW = Math.max(1, rect.width);
    waveCssH = Math.max(1, rect.height);
    waveDpr = window.devicePixelRatio || 1;

    waveCanvas.width = Math.max(1, Math.floor(waveCssW * waveDpr));
    waveCanvas.height = Math.max(1, Math.floor(waveCssH * waveDpr));

    // Draw in CSS pixels
    waveCtx.setTransform(waveDpr, 0, 0, waveDpr, 0, 0);
  };

  // ensure we don't leak multiple resize listeners
  if (waveResizeHandler) {
    try {
      window.removeEventListener("resize", waveResizeHandler);
    } catch (e) {
      // ignore
    }
  }
  waveResizeHandler = resize;

  resize();
  // Track layout changes (e.g., grid reflow) that won't trigger window.resize
  try {
    const ro = new ResizeObserver(() => resize());
    ro.observe(waveCanvas);
  } catch (e) {
    // ignore
  }
  window.addEventListener("resize", waveResizeHandler);

  // If we have a live analyser, use it. Otherwise we render an elegant idle wave.
  if (analyserNode) {
    waveData = new Uint8Array(analyserNode.fftSize);
  } else {
    waveData = null;
  }

  const drawIdle = (w, h) => {
    // Subtle animated idle line so the UI never looks "dead"
    waveIdlePhase += 0.035;
    const mid = h / 2;

    // A very subtle amplitude that still reacts a bit to meterLevel
    const amp = Math.min(h * 0.12, (h / 2) * 0.35) * (0.35 + Math.min(1, meterLevel) * 0.9);

    waveCtx.beginPath();
    for (let x = 0; x < w; x += 2) {
      const t = (x / w) * Math.PI * 2;
      const y = mid + Math.sin(t * 2 + waveIdlePhase) * amp * 0.35 + Math.sin(t * 6 + waveIdlePhase * 1.3) * amp * 0.15;
      if (x === 0) waveCtx.moveTo(x, y);
      else waveCtx.lineTo(x, y);
    }
    waveCtx.stroke();
  };

  const drawLive = (w, h) => {
    if (!analyserNode || !waveData) {
      drawIdle(w, h);
      return;
    }

    analyserNode.getByteTimeDomainData(waveData);

    waveCtx.beginPath();

    const mid = h / 2;
    // Base amplitude in CSS pixels, then gently boosted by mic meter.
    // Clamp so the wave always stays centered and doesn't hit top/bottom.
    const boost = 0.55 + Math.min(1, meterLevel) * 1.25;
    const maxAmp = (h / 2) * 0.72; // keep some headroom
    const baseAmp = Math.min(h * 0.28, maxAmp);
    const amp = Math.min(maxAmp, baseAmp * boost);

    for (let x = 0; x < w; x += 2) {
      const idx = Math.floor((x / w) * waveData.length);
      const v = (waveData[idx] - 128) / 128; // -1..1 centered
      const y = mid + v * amp;
      if (x === 0) waveCtx.moveTo(x, y);
      else waveCtx.lineTo(x, y);
    }

    waveCtx.stroke();
  };

  const draw = () => {
    waveRafId = requestAnimationFrame(draw);

    // If the canvas has zero layout size, don't draw
    if (!waveCssW || !waveCssH) return;

    // Clear in *device pixels* to avoid transform/shadow artifacts that can look like
    // extra stray lines at the top/bottom.
    waveCtx.save();
    waveCtx.setTransform(1, 0, 0, 1, 0, 0);
    waveCtx.clearRect(0, 0, waveCanvas.width, waveCanvas.height);
    waveCtx.restore();

    // Style (coordinates are in CSS pixels because resize() sets the transform)
    if (!cachedAccent) cachedAccent = cssVar("--accent", "#2d6bff");
    waveCtx.strokeStyle = cachedAccent;
    waveCtx.lineWidth = 2;
    waveCtx.globalAlpha = waveMode === "idle" ? 0.55 : 0.8;

    // Soft glow pass
    waveCtx.save();
    waveCtx.shadowColor = cachedAccent;
    waveCtx.shadowBlur = waveMode === "idle" ? 10 : 14;

    if (waveMode === "live") drawLive(waveCssW, waveCssH);
    else drawIdle(waveCssW, waveCssH);

    waveCtx.restore();
    waveCtx.globalAlpha = 1;
  };

  draw();
}

function stopWaveformLoop() {
  if (waveRafId) {
    cancelAnimationFrame(waveRafId);
    waveRafId = null;
  }
  if (waveResizeHandler) {
    try {
      window.removeEventListener("resize", waveResizeHandler);
    } catch (e) {
      // ignore
    }
    waveResizeHandler = null;
  }
  waveCtx = null;
  waveData = null;
  // keep analyserNode as-is (it will be nulled by teardownAudio when appropriate)
}

function setStatus(state, label) {
  currentState = state || "ready";
  document.body.dataset.state = currentState;

  if (!statusDot || !statusText) return;

  const color = statusColorFor(currentState);
  statusDot.style.background = color;
  statusDot.style.boxShadow = `0 0 12px ${color}99`;
  statusText.textContent = label || currentState;
  if (hudState) hudState.textContent = (label || currentState || "ready").toString();
  setHudLastEvent(`state:${label || currentState}`);
}

function createChatBubble(role, text, isLive = false, ts = Date.now()) {
  if (!chatStream) return null;
  const bubble = document.createElement("div");
  bubble.className = `chat-bubble ${role}${isLive ? " live" : ""}`;

  const meta = document.createElement("div");
  meta.className = "chat-meta";

  const label = document.createElement("div");
  label.className = "chat-role";
  label.textContent = role === "agent" ? "Agent" : "User";

  const timeNode = document.createElement("div");
  timeNode.className = "chat-time";
  timeNode.textContent = formatClockTime(ts);

  const body = document.createElement("div");
  body.className = "chat-text";
  body.textContent = text || "";

  meta.appendChild(label);
  meta.appendChild(timeNode);
  bubble.appendChild(meta);
  bubble.appendChild(body);
  return bubble;
}

function insertBubbleByTs(bubble, ts) {
  if (!chatStream) return;
  bubble.dataset.ts = String(ts || Date.now());
  const nodes = Array.from(chatStream.querySelectorAll(".chat-bubble[data-ts]"));
  for (const node of nodes) {
    const nodeTs = Number(node.dataset.ts || 0);
    if (ts < nodeTs) {
      chatStream.insertBefore(bubble, node);
      return;
    }
  }
  chatStream.appendChild(bubble);
}

function upsertTimelineBubble({ key, role, text, ts, interrupted }) {
  if (!chatStream) return null;
  if (!key) return null;
  let bubble = timelineBubbles.get(key);
  if (!bubble) {
    bubble = createChatBubble(role, text || "", false, ts || Date.now());
    if (!bubble) return null;
    bubble.dataset.key = key;
    insertBubbleByTs(bubble, ts);
    timelineBubbles.set(key, bubble);
  } else {
    const body = bubble.querySelector(".chat-text");
    if (body && text != null) body.textContent = text;
    const timeNode = bubble.querySelector(".chat-time");
    if (timeNode && ts) timeNode.textContent = formatClockTime(ts);
    if (ts && Number(bubble.dataset.ts || 0) !== ts) {
      bubble.dataset.ts = String(ts);
      bubble.remove();
      insertBubbleByTs(bubble, ts);
    }
  }
  if (interrupted) {
    bubble.classList.add("interrupted");
  }
  if (chatEmpty) chatEmpty.style.display = "none";
  scrollChatToBottom();
  return bubble;
}

function appendChatBubble(role, text, isLive = false, ts = Date.now()) {
  if (!chatStream) return null;
  const bubble = createChatBubble(role, text, isLive, ts);
  if (!bubble) return null;
  if (chatEmpty) chatEmpty.style.display = "none";
  chatStream.appendChild(bubble);
  scrollChatToBottom();
  return bubble;
}

function updateLiveBubble(role, text) {
  if (!chatStream) return;
  let bubble = role === "agent" ? agentLiveBubble : userLiveBubble;
  if (!bubble) {
    bubble = appendChatBubble(role, "", true, Date.now());
    if (!bubble) return;
    if (role === "agent") agentLiveBubble = bubble;
    else userLiveBubble = bubble;
  }
  const body = bubble.querySelector(".chat-text");
  if (body) body.textContent = text || "";
  if (chatEmpty) chatEmpty.style.display = "none";
  scrollChatToBottom();
}

function clearLiveBubble(role) {
  const bubble = role === "agent" ? agentLiveBubble : userLiveBubble;
  if (bubble && bubble.parentElement) {
    bubble.parentElement.removeChild(bubble);
  }
  if (role === "agent") agentLiveBubble = null;
  else userLiveBubble = null;
}

function commitLiveBubble(role, text) {
  const finalText = (text || "").trim();
  if (!finalText) {
    clearLiveBubble(role);
    return;
  }
  const key = role === "agent" ? "assistant" : "user";
  const norm = finalText
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  const now = Date.now();
  if (norm && norm === lastChatNorm[key] && now - lastChatAt[key] < 2500) {
    clearLiveBubble(role);
    return;
  }
  lastChatNorm[key] = norm;
  lastChatByRole[key] = finalText;
  lastChatAt[key] = now;
  const bubble = role === "agent" ? agentLiveBubble : userLiveBubble;
  if (bubble) {
    bubble.classList.remove("live");
    const body = bubble.querySelector(".chat-text");
    if (body) body.textContent = finalText;
    const timeNode = bubble.querySelector(".chat-time");
    if (timeNode) timeNode.textContent = formatClockTime(now);
    if (role === "agent") agentLiveBubble = null;
    else userLiveBubble = null;
  } else {
    appendChatBubble(role, finalText, false, now);
  }
  if (chatEmpty) chatEmpty.style.display = "none";
}

function resetChatStream() {
  if (!chatStream) return;
  const placeholder = chatEmpty && chatEmpty.parentElement === chatStream ? chatEmpty : null;
  chatStream.innerHTML = "";
  if (placeholder) {
    chatStream.appendChild(placeholder);
    chatEmpty.style.display = "";
  }
  userLiveBubble = null;
  agentLiveBubble = null;
  timelineBubbles.clear();
}

function setText(el, value) {
  if (!el) return;
  el.textContent = value == null || value === "" ? "—" : value;
}

function updateWorkflowSteps(currentStep, stateData) {
  if (!workflowSteps) return;
  const stepOrder = ["consent", "confirm_identity", "confirm_awareness", "ask_payment_made", "ask_ptp_or_callback", "closing"];
  const currentIdx = stepOrder.indexOf(currentStep || "consent");
  const steps = workflowSteps.querySelectorAll(".wf-step");
  steps.forEach((el) => {
    const step = el.dataset.step;
    const idx = stepOrder.indexOf(step);
    el.classList.remove("completed", "active");
    if (idx < currentIdx) {
      el.classList.add("completed");
    } else if (idx === currentIdx) {
      el.classList.add("active");
    }
  });
}

function updateComplianceFlags(stateData) {
  const s = stateData || {};
  if (compConsent) {
    const consented = s.consent === true;
    compConsent.classList.toggle("comp-pass", consented);
    const icon = compConsent.querySelector(".comp-icon");
    if (icon) icon.innerHTML = consented ? "&#10003;" : "&#9675;";
  }
  if (compIdentity) {
    const confirmed = !!s.identity_confirmed;
    compIdentity.classList.toggle("comp-pass", confirmed);
    const icon = compIdentity.querySelector(".comp-icon");
    if (icon) icon.innerHTML = confirmed ? "&#10003;" : "&#9675;";
  }
  if (compDisclosure) {
    const aware = !!s.awareness_confirmed;
    compDisclosure.classList.toggle("comp-pass", aware);
    const icon = compDisclosure.querySelector(".comp-icon");
    if (icon) icon.innerHTML = aware ? "&#10003;" : "&#9675;";
  }
}

function updateSentiment(emotionData) {
  if (!sentimentValue) return;
  const stress = emotionData.stress_level || 0;
  const sent = emotionData.sentiment || "neutral";
  let label = "Neutral";
  let cls = "sentiment-neutral";
  if (stress > 0.7) { label = "High Stress"; cls = "sentiment-stressed"; }
  else if (stress > 0.4) { label = "Tense"; cls = "sentiment-negative"; }
  else if (sent === "positive" || stress < 0.15) { label = "Cooperative"; cls = "sentiment-positive"; }
  else { label = "Neutral"; cls = "sentiment-neutral"; }
  sentimentValue.textContent = label;
  sentimentValue.className = "intel-value " + cls;
}

function enableDispositionButtons(enable) {
  if (!dispositionActions) return;
  dispositionActions.querySelectorAll(".disp-btn").forEach((btn) => {
    btn.disabled = !enable;
  });
}

function renderCustomerContext() {
  const ctx = currentContext || {};
  setText(customerNameValue, ctx.customer_name || ctx.customerName || ctx.name);
  setText(customerPhoneValue, ctx.phone || ctx.customer_phone || ctx.customerPhone);
  setText(customerCityValue, ctx.city || ctx.customer_city || ctx.city_name);
  setText(loanIdValue, ctx.customer_id || ctx.customerId || ctx.id);
  const amt = ctx.overdue_amount || ctx.amount || ctx.overdueAmount;
  setText(loanAmountValue, amt ? `₹${amt}` : "—");
  setText(loanDueValue, ctx.due_date || ctx.dueDate);
  const dpd = ctx.dpd ?? ctx.days_past_due ?? ctx.daysPastDue;
  if (dpdBadge) {
    dpdBadge.textContent = dpd != null && dpd !== "" ? `DPD ${dpd}` : "DPD —";
  }
  setText(riskValue, ctx.risk_band || ctx.riskBand || ctx.risk);
  const ptp = ctx.ptp_date || ctx.ptpDate || ctx.promise_to_pay;
  if (promiseValue) {
    promiseValue.textContent = ptp ? `Captured (${ptp})` : "Not captured";
  }
  setText(intentValue, ctx.intent || ctx.last_intent || "—");
  const lang = ctx.language_preference || ctx.language || "hi-IN";
  if (hudLanguage) hudLanguage.textContent = lang;
}

function commitAssistantBuffer() {
  const text = (assistantBuffer || "").trim();
  if (!text) return;
  if (assistantCommittedThisTurn) return;

  commitLiveBubble("agent", text);
  assistantBuffer = "";
  assistantCommittedThisTurn = true;
}

function updateMeter(rms) {
  if (!micMeterFill) return;
  const normalized = Math.min(1, rms / 1200);
  meterLevel = meterLevel * 0.8 + normalized * 0.2;
  micMeterFill.style.width = `${Math.round(meterLevel * 100)}%`;
}

function clearAudioQueue() {
  activeSources.forEach((source) => {
    try {
      source.stop();
    } catch (err) {
      // ignore
    }
  });
  activeSources = [];
  if (audioContext) {
    playhead = audioContext.currentTime + 0.01;
  }
  if (ttsGain && audioContext) {
    ttsGain.gain.cancelScheduledValues(audioContext.currentTime);
    ttsGain.gain.setValueAtTime(1, audioContext.currentTime);
  }
}

function applyBargeInFade(fadeMs = 120) {
  if (!audioContext || !ttsGain) {
    clearAudioQueue();
    return;
  }
  const now = audioContext.currentTime;
  const fadeSec = Math.max(0.05, fadeMs / 1000);
  try {
    ttsGain.gain.cancelScheduledValues(now);
    ttsGain.gain.setValueAtTime(ttsGain.gain.value || 1, now);
    ttsGain.gain.linearRampToValueAtTime(0.0, now + fadeSec);
  } catch (e) {
    // ignore
  }
  setTimeout(() => {
    clearAudioQueue();
  }, Math.round(fadeSec * 1000));
}

async function setupAudio() {
  audioContext = new (window.AudioContext || window.webkitAudioContext)({
    latencyHint: "interactive",
  });

  ttsGain = audioContext.createGain();
  ttsGain.gain.value = 1.0;
  ttsGain.connect(audioContext.destination);

  await audioContext.audioWorklet.addModule("/static/worklets/pcm-processor.js");

  micStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      sampleRate: TARGET_SAMPLE_RATE,
      echoCancellation: true,
      noiseSuppression: false,
      autoGainControl: false,
    },
  });

  sourceNode = audioContext.createMediaStreamSource(micStream);

  // For live waveform rendering (no output)
  analyserNode = audioContext.createAnalyser();
  analyserNode.fftSize = 2048;
  attachAnalyserToWaveform();
  try {
    sourceNode.connect(analyserNode);
  } catch (e) {
    // ignore
  }

  workletNode = new AudioWorkletNode(audioContext, "pcm-processor", {
    processorOptions: {
      targetSampleRate: TARGET_SAMPLE_RATE,
      frameSamples: FRAME_SAMPLES,
    },
  });

  workletNode.port.postMessage({ type: "init" });

  workletNode.port.onmessage = (event) => {
    if (event.data && event.data.status === "ready") return;
    if (!running || !ws || ws.readyState !== WebSocket.OPEN) return;

    const { pcm, rms } = event.data;
    if (typeof rms === "number") updateMeter(rms);

    if (muted) return;

    if (!workletNode._sentAudioStart) {
      ws.send(JSON.stringify({ type: "audio_started" }));
      workletNode._sentAudioStart = true;
    }
    ws.send(pcm);
  };

  silentGain = audioContext.createGain();
  silentGain.gain.value = 0;

  // Keep destination alive (some browsers need an output node)
  sourceNode
    .connect(workletNode)
    .connect(silentGain)
    .connect(audioContext.destination);

  if (audioContext.state === "suspended") {
    await audioContext.resume();
  }

  // Switch waveform to live mode now that mic/analyser is ready.
  // If the loop started in idle mode earlier, attachAnalyserToWaveform() will
  // allocate waveData so the line actually animates from the mic.
  attachAnalyserToWaveform();
}

async function teardownAudio() {
  // stop any live loop; we'll restart an idle loop after teardown
  stopWaveformLoop();

  clearAudioQueue();
  if (workletNode) workletNode.port.onmessage = null;
  if (micStream) micStream.getTracks().forEach((track) => track.stop());
  if (audioContext) await audioContext.close();

  workletNode = null;
  sourceNode = null;
  micStream = null;
  silentGain = null;
  ttsGain = null;
  audioContext = null;

  analyserNode = null;
  waveData = null;

  // Keep the UI feeling alive even when disconnected
  cachedAccent = null;
  waveMode = "idle";
  if (waveCanvas) startWaveformLoop("idle");
}

function handleServerEvent(payload) {
  setHudLastEvent(payload && payload.type ? payload.type : "event");

  if (payload.type === "context_received" || payload.type === "context_updated") {
    const incoming = payload.context || payload.facts || {};
    if (incoming && typeof incoming === "object") {
      currentContext = { ...(currentContext || {}), ...incoming };
    }
    if (currentContext.language_preference && languageValue) {
      languageValue.textContent = currentContext.language_preference;
    }
    if (currentContext.language_preference && hudLanguage) {
      hudLanguage.textContent = currentContext.language_preference;
    }
    renderCustomerContext();
    updateStartButtonState();
    // Enterprise: Update workflow & compliance
    if (currentContext.workflow_state || currentContext.current_step) {
      const ws = currentContext.workflow_state || currentContext;
      updateWorkflowSteps(ws.current_step || currentContext.current_step, ws);
      updateComplianceFlags(ws);
    }
    return;
  }

  if (payload.type === "workflow_update") {
    const ws = payload.state || payload;
    updateWorkflowSteps(ws.current_step, ws);
    updateComplianceFlags(ws);
    if (ws.current_step && hudLastEvent) {
      const stepLabels = {
        consent: "Requesting Consent",
        confirm_identity: "Confirming Identity",
        confirm_awareness: "Confirming Awareness",
        ask_payment_made: "Checking Payment",
        ask_reference_number: "Getting Reference",
        ask_ptp_or_callback: "Securing Commitment",
        closing: "Closing Call",
      };
      hudLastEvent.textContent = stepLabels[ws.current_step] || ws.current_step;
    }
    return;
  }

  if (payload.type === "emotion_state") {
    updateSentiment(payload);
    return;
  }

  if (payload.type === "chat_message") {
    return;
  }

  if (payload.type === "vad_speech_start") {
    if (currentState !== "speaking") {
      setStatus("listening", "listening");
    }
    return;
  }

  if (payload.type === "vad_speech_end") {
    if (currentState === "listening") {
      setStatus("thinking", "thinking");
    }
    return;
  }

  if (payload.type === "backchannel") {
    if (payload.text) {
      updateLiveBubble("agent", payload.text);
    }
    return;
  }

  if (payload.type === "interrupt_acknowledged") {
    if (bargeStatus) {
      bargeStatus.textContent = "Acknowledged";
      setTimeout(() => {
        bargeStatus.textContent = "Idle";
      }, 600);
    }
    return;
  }

  if (payload.type === "knowledge_used" || payload.type === "supervisor_update") {
    return;
  }

  if (payload.type === "action_result" || payload.type === "action_error") {
    return;
  }

  if (payload.type === "status") {
    setStatus(payload.state || "ready", payload.state);
    if ((payload.state || "") === "speaking") {
      if (!useTimelineEvents) commitAssistantBuffer();
      if (typingIndicator) typingIndicator.style.display = "none";
    }
    if ((payload.state || "") === "thinking") {
      if (typingIndicator) typingIndicator.style.display = "flex";
    }
    if ((payload.state || "") === "listening") {
      if (typingIndicator) typingIndicator.style.display = "none";
    }
    return;
  }

  if (payload.type === "transcript") {
    transcriptBuffer = payload.text || "";
    if (payload.final) {
      if (!useTimelineEvents) {
        commitLiveBubble("user", transcriptBuffer);
      }
      transcriptBuffer = "";
      clearLiveBubble("user");
    } else {
      updateLiveBubble("user", transcriptBuffer);
    }
    if (payload.language && languageValue) {
      languageValue.textContent = payload.language;
    }
    if (payload.language && hudLanguage) {
      hudLanguage.textContent = payload.language;
    }
    return;
  }

  if (payload.type === "agent_utterance_created") {
    const key = payload.utterance_id ? `utt:${payload.utterance_id}` : `utt:${payload.ts || Date.now()}`;
    upsertTimelineBubble({
      key,
      role: "agent",
      text: payload.text || "",
      ts: payload.ts || Date.now(),
      interrupted: false,
    });
    clearLiveBubble("agent");
    return;
  }

  if (payload.type === "agent_tts_end") {
    if (payload.utterance_id && payload.status === "interrupted") {
      const key = `utt:${payload.utterance_id}`;
      const bubble = timelineBubbles.get(key);
      if (bubble) bubble.classList.add("interrupted");
    }
    return;
  }

  if (payload.type === "stt_final") {
    const key = payload.segment_id ? `seg:${payload.segment_id}` : `seg:${payload.ts || Date.now()}`;
    upsertTimelineBubble({
      key,
      role: "user",
      text: payload.text || "",
      ts: payload.ts || Date.now(),
      interrupted: false,
    });
    clearLiveBubble("user");
    if (payload.language && languageValue) {
      languageValue.textContent = payload.language;
    }
    if (payload.language && hudLanguage) {
      hudLanguage.textContent = payload.language;
    }
    return;
  }

  if (payload.type === "assistant_token") {
    if (useTimelineEvents) return;
    // New assistant response stream starts
    if (!assistantBuffer && assistantCommittedThisTurn) {
      assistantCommittedThisTurn = false;
    }
    assistantBuffer += payload.text || "";
    updateLiveBubble("agent", assistantBuffer);
    return;
  }

  if (payload.type === "assistant_final") {
    const finalText = (payload.text || assistantBuffer || "").trim();
    if (useTimelineEvents && payload.utterance_id) {
      const key = `utt:${payload.utterance_id}`;
      const bubble = timelineBubbles.get(key);
      if (bubble) {
        const body = bubble.querySelector(".chat-text");
        if (body && finalText) body.textContent = finalText;
        if (payload.interrupted) bubble.classList.add("interrupted");
      } else if (finalText) {
        commitLiveBubble("agent", finalText);
      }
    } else if (finalText) {
      commitLiveBubble("agent", finalText);
    }
    assistantBuffer = "";
    assistantCommittedThisTurn = true;
    const turnKey = payload.utterance_id ? `utt:${payload.utterance_id}` : `ts:${payload.ts || Date.now()}`;
    if (!countedAssistantTurns.has(turnKey)) {
      countedAssistantTurns.add(turnKey);
      if (countedAssistantTurns.size > 2000) {
        countedAssistantTurns.clear();
      }
      turnCount += 1;
      updateTurnUi();
    }
    return;
  }

  if (payload.type === "assistant_cancelled") {
    assistantBuffer = "";
    clearLiveBubble("agent");
    assistantCommittedThisTurn = false;
    return;
  }

  if (payload.type === "barge_in") {
    if (!bargeStatus) return;
    bargeStatus.textContent = "Active";
    bargeStatus.classList.remove("muted");
    applyBargeInFade(payload.fade_ms || 120);
    if (payload.utterance_id) {
      const key = `utt:${payload.utterance_id}`;
      const bubble = timelineBubbles.get(key);
      if (bubble) bubble.classList.add("interrupted");
    }
    interruptionCount += 1;
    updateInterruptionUi();
    setTimeout(() => {
      bargeStatus.textContent = "Idle";
      bargeStatus.classList.add("muted");
    }, 800);
  }
}

function handleAudioChunk(arrayBuffer) {
  if (!audioContext) return;

  // If TTS audio starts arriving before an explicit assistant_final event,
  // persist whatever text we have so it doesn't disappear from the UI.
  if (!useTimelineEvents && !assistantCommittedThisTurn) {
    if ((assistantBuffer || "").trim()) {
      commitAssistantBuffer();
    } else {
      clearLiveBubble("agent");
    }
  }

  const pcm = new Int16Array(arrayBuffer);
  const floats = new Float32Array(pcm.length);
  for (let i = 0; i < pcm.length; i += 1) {
    floats[i] = Math.max(-1, Math.min(1, pcm[i] / 32768));
  }

  const buffer = audioContext.createBuffer(1, floats.length, TARGET_SAMPLE_RATE);
  buffer.copyToChannel(floats, 0);

  const source = audioContext.createBufferSource();
  source.buffer = buffer;
  if (ttsGain && audioContext && ttsGain.gain.value < 0.02) {
    ttsGain.gain.cancelScheduledValues(audioContext.currentTime);
    ttsGain.gain.setValueAtTime(1, audioContext.currentTime);
  }
  if (ttsGain) {
    source.connect(ttsGain);
  } else {
    source.connect(audioContext.destination);
  }

  if (playhead < audioContext.currentTime) {
    playhead = audioContext.currentTime + 0.02;
  }

  source.start(playhead);
  playhead += buffer.duration;
  activeSources.push(source);

  source.onended = () => {
    activeSources = activeSources.filter((s) => s !== source);
  };
}

function tryHandleJsonFromArrayBuffer(arrayBuffer) {
  if (!arrayBuffer || !(arrayBuffer instanceof ArrayBuffer)) return false;
  const bytes = new Uint8Array(arrayBuffer);
  if (!bytes.length || bytes.length > 65536) return false;
  let i = 0;
  while (i < bytes.length && bytes[i] <= 32) i += 1;
  if (i >= bytes.length) return false;
  const first = bytes[i];
  if (first !== 123 && first !== 91) return false; // '{' or '['
  try {
    const text = new TextDecoder("utf-8").decode(bytes);
    const payload = JSON.parse(text);
    if (payload && typeof payload === "object" && payload.type) {
      handleServerEvent(payload);
      return true;
    }
  } catch (err) {
    return false;
  }
  return false;
}

function getWsUrl() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  return `${protocol}://${window.location.host}/ws/voice`;
}

function wsSend(obj) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  try {
    ws.send(JSON.stringify(obj));
  } catch (e) {
    // ignore
  }
}

function updateStartButtonState() {
  if (!toggleBtn) return;
  const hasCustomer = !!(currentContext && currentContext.customer_id);
  toggleBtn.disabled = !hasCustomer && !running;
}

function populateCustomers(rows) {
  if (!customerSelect) return;
  customersIndex = {};
  customerSelect.innerHTML = "";
  const opt0 = document.createElement("option");
  opt0.value = "";
  opt0.textContent = "Select customer…";
  customerSelect.appendChild(opt0);

  (rows || []).forEach((r) => {
    const cid = (r.customer_id || "").toString();
    customersIndex[cid] = r;
    const name = (r.customer_name || "").toString();
    const amt = (r.overdue_amount || "").toString();
    const opt = document.createElement("option");
    opt.value = cid;
    opt.textContent = `${cid} — ${name}${amt ? ` (₹${amt})` : ""}`;
    customerSelect.appendChild(opt);
  });
}

async function loadCustomers() {
  try {
    const res = await fetch("/api/customers");
    const data = await res.json();
    populateCustomers(data.rows || []);
  } catch (e) {
    // ignore
  }
}

async function startSession() {
  if (running) return;
  if (!toggleBtn || !muteBtn) return;
  if (!currentContext || !currentContext.customer_id) {
    return;
  }

  running = true;
  sessionStartedAtMs = Date.now();
  if (sessionTimer) clearInterval(sessionTimer);
  sessionTimer = setInterval(updateHudDuration, 1000);
  updateHudDuration();
  setHudLastEvent("session_started");
  toggleBtn.textContent = "End Call";
  toggleBtn.classList.add("btn-danger");
  muteBtn.disabled = false;
  enableDispositionButtons(true);
  setStatus("connecting", "connecting");

  ws = new WebSocket(getWsUrl());
  ws.binaryType = "arraybuffer";

  ws.onopen = async () => {
    try {
      await setupAudio();
      if (audioContext && audioContext.state === "suspended") {
        await audioContext.resume();
      }
    } catch (err) {
      console.error("Microphone setup failed", err);
      await stopSession();
      setStatus("disconnected", "mic blocked");
      return;
    }

    wsSend({ type: "start", sampleRate: TARGET_SAMPLE_RATE, context: currentContext });
    setStatus("listening", "listening");
    updateStartButtonState();
  };

  ws.onmessage = (event) => {
    if (typeof event.data === "string") {
      try {
        const payload = JSON.parse(event.data);
        if (payload.type === "error") {
          setStatus("disconnected", payload.message || "server error");
        }
        handleServerEvent(payload);
      } catch (err) {
        // ignore
      }
      return;
    }
    if (event.data instanceof Blob) {
      event.data
        .text()
        .then((text) => {
          try {
            const payload = JSON.parse(text);
            handleServerEvent(payload);
          } catch (err) {
            event.data.arrayBuffer().then(handleAudioChunk).catch(() => {});
          }
        })
        .catch(() => {});
      return;
    }
    if (tryHandleJsonFromArrayBuffer(event.data)) return;
    handleAudioChunk(event.data);
  };

  ws.onclose = () => {
    stopSession();
  };

  ws.onerror = () => {
    setStatus("disconnected", "error");
  };
}

async function stopSession() {
  if (!running) return;
  running = false;
  muted = false;
  if (sessionTimer) {
    clearInterval(sessionTimer);
    sessionTimer = null;
  }
  sessionStartedAtMs = 0;
  updateHudDuration();

  if (toggleBtn) toggleBtn.textContent = "Start Call";
  if (toggleBtn) toggleBtn.classList.remove("btn-danger");
  if (muteBtn) {
    muteBtn.disabled = true;
    muteBtn.textContent = "Mute Mic";
    muteBtn.classList.add("ghost");
    muteBtn.classList.remove("primary");
  }

  setStatus("disconnected", "disconnected");
  enableDispositionButtons(false);
  if (typingIndicator) typingIndicator.style.display = "none";

  resetChatStream();

  assistantBuffer = "";
  transcriptBuffer = "";
  assistantCommittedThisTurn = false;
  turnCount = 0;
  interruptionCount = 0;
  countedAssistantTurns.clear();
  updateTurnUi();
  updateInterruptionUi();
  setHudLastEvent("session_stopped");
  updateMeter(0);

  if (ws) {
    try {
      wsSend({ type: "stop" });
    } catch (err) {
      // ignore
    }
    try {
      ws.close();
    } catch (err) {
      // ignore
    }
    ws = null;
  }

  await teardownAudio();
  updateStartButtonState();
}

function toggleMute() {
  muted = !muted;
  if (!muteBtn) return;
  muteBtn.textContent = muted ? "Unmute Mic" : "Mute Mic";
  muteBtn.classList.toggle("ghost", !muted);
  muteBtn.classList.toggle("primary", muted);
}

if (toggleBtn) {
  toggleBtn.addEventListener("click", () => {
    if (running) stopSession();
    else startSession();
  });
}

if (muteBtn) {
  muteBtn.addEventListener("click", () => {
    if (!running) return;
    toggleMute();
  });
}

if (autoScrollBtn) {
  autoScrollBtn.addEventListener("click", () => {
    setAutoScroll(!autoScrollEnabled);
    if (autoScrollEnabled) scrollChatToBottom(true);
  });
}

if (clearChatBtn) {
  clearChatBtn.addEventListener("click", () => {
    resetChatStream();
    setHudLastEvent("transcript_cleared");
  });
}

// Initialize theme toggle
initTheme();
initParallax();
setAutoScroll(true);
updateTurnUi();
updateInterruptionUi();
updateHudDuration();
if (hudLanguage && languageValue) hudLanguage.textContent = languageValue.textContent || "hi-IN";

// Render an idle waveform immediately (so the area isn't empty before starting)
if (waveCanvas) startWaveformLoop("idle");

setStatus("disconnected", "disconnected");
loadCustomers();

// Demo controls wiring
if (reloadCustomersBtn) {
  reloadCustomersBtn.addEventListener("click", () => {
    loadCustomers();
  });
}

  if (customerSelect) {
    customerSelect.addEventListener("change", () => {
      const cid = customerSelect.value || "";
      if (!cid) return;
      currentContext = customersIndex[cid] || {};
      renderCustomerContext();
      updateStartButtonState();
      if (running) {
        wsSend({ type: "set_context", context: currentContext });
      }
    });
  }
updateStartButtonState();

// Disposition button handlers
if (dispositionActions) {
  dispositionActions.addEventListener("click", (e) => {
    const btn = e.target.closest(".disp-btn");
    if (!btn || btn.disabled || !running) return;
    const disp = btn.dataset.disp;
    if (!disp) return;
    wsSend({ type: "set_disposition", disposition: disp });
    dispositionActions.querySelectorAll(".disp-btn").forEach((b) => b.classList.remove("disp-active"));
    btn.classList.add("disp-active");
    setHudLastEvent(`disposition:${disp}`);
  });
}
