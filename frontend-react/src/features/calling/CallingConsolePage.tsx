import {
  Badge,
  Button,
  Card,
  Group,
  Paper,
  Progress,
  ScrollArea,
  Select,
  SimpleGrid,
  Stack,
  Switch,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import dayjs from "dayjs";
import { notifications } from "@mantine/notifications";
import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, CheckCheck, Mic, MicOff, Phone, PhoneOff, Shield, Timer, Volume2, Waves } from "lucide-react";

import { apiFetch, toQuery } from "../../api/client";
import { useAuth } from "../../auth/AuthProvider";
import { PERMS, ROLES } from "../../auth/roles";
import { EmptyStateCard } from "../../components/EmptyStateCard";
import type { BuildInfo, SessionSnapshot, TaskDetail, TaskEvent, TaskRow } from "../../types/api";

const ACTION_STATE_MAP: Record<string, string> = {
  PTP: "PTP",
  CALLBACK: "CALLBACK",
  PAID: "CLOSED",
  ESCALATE: "ESCALATED",
  CLOSE: "CLOSED",
};

const TARGET_SAMPLE_RATE = 16000;
const FRAME_SAMPLES = 320;
const FALLBACK_MIC_GAIN = 1.8;
const CALL_FLOW = [
  { label: "Consent", short: "Cons" },
  { label: "Identity", short: "ID" },
  { label: "Awareness", short: "Aware" },
  { label: "Negotiation", short: "Neg" },
  { label: "Commitment", short: "PTP" },
  { label: "Callback", short: "Back" },
  { label: "Wrap-Up", short: "Wrap" },
];
const BULBUL_V3_VOICE_OPTIONS = [
  "Shubh",
  "Aditya",
  "Ritu",
  "Priya",
  "Neha",
  "Rahul",
  "Pooja",
  "Rohan",
  "Simran",
  "Kavya",
  "Amit",
  "Dev",
  "Ishita",
  "Shreya",
  "Ratan",
  "Varun",
  "Manan",
  "Sumit",
  "Roopa",
  "Kabir",
  "Aayan",
  "Ashutosh",
  "Advait",
  "Amelia",
  "Sophia",
  "Anand",
  "Tanya",
  "Tarun",
  "Sunny",
  "Mani",
  "Gokul",
  "Vijay",
  "Shruti",
  "Suhani",
  "Mohit",
  "Kavitha",
  "Rehan",
  "Soham",
  "Rupali",
].map((label) => ({ value: label.toLowerCase(), label }));
const STARTING_LANGUAGE_OPTIONS = [
  { value: "hi-IN", label: "Hindi" },
  { value: "en-IN", label: "English" },
  { value: "mr-IN", label: "Marathi" },
  { value: "ta-IN", label: "Tamil" },
  { value: "te-IN", label: "Telugu" },
  { value: "kn-IN", label: "Kannada" },
  { value: "bn-IN", label: "Bengali" },
  { value: "gu-IN", label: "Gujarati" },
];

type VoiceStatus = "disconnected" | "connecting" | "listening" | "thinking" | "speaking" | "error";

type VoiceLogEntry = {
  id: string;
  who: "agent" | "user" | "system";
  text: string;
  ts: number;
};

function parseCompliance(jsonText?: string): Record<string, boolean> {
  try {
    const obj = jsonText ? JSON.parse(jsonText) : {};
    if (obj && typeof obj === "object") {
      return obj as Record<string, boolean>;
    }
  } catch {
    // ignore
  }
  return {
    CONSENT_OK: true,
    IDENTITY_OK: true,
    NO_THREATS_OK: true,
    SENSITIVE_ASKS_OK: true,
  };
}

function strategyForDpd(dpd?: number): { mode: string; tone: string } {
  const v = Number(dpd || 0);
  if (v <= 30) return { mode: "soft_reminder", tone: "Respectful and assistive" };
  if (v <= 60) return { mode: "firm_commitment", tone: "Firm commitment ask" };
  if (v <= 90) return { mode: "urgent_recovery", tone: "High urgency with options" };
  return { mode: "pre_legal_caution", tone: "Compliant caution, supervisor aware" };
}

function fmtAmount(v?: number) {
  try {
    return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(v || 0));
  } catch {
    return `INR ${Number(v || 0).toFixed(2)}`;
  }
}

function statusColor(status: VoiceStatus) {
  if (status === "speaking") return "teal";
  if (status === "listening") return "blue";
  if (status === "thinking") return "orange";
  if (status === "connecting") return "yellow";
  if (status === "error") return "red";
  return "gray";
}

function voiceHeadline(status: VoiceStatus) {
  if (status === "speaking") return "Agent is actively speaking";
  if (status === "listening") return "System is listening for borrower speech";
  if (status === "thinking") return "LLM is composing the next response";
  if (status === "connecting") return "Voice bridge is negotiating connection";
  if (status === "error") return "Voice engine needs intervention";
  return "Voice bridge is idle and ready";
}

function makeLogId() {
  return `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
}

function normalizeLogText(text: string) {
  return text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function humanizeSlug(value?: string) {
  const text = String(value || "").trim();
  if (!text) return "Not set";
  return text
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function flowIndexForStep(step?: string) {
  const value = String(step || "").toLowerCase();
  if (!value) return 0;
  if (value.includes("consent")) return 0;
  if (value.includes("identity")) return 1;
  if (value.includes("awareness")) return 2;
  if (value.includes("hardship") || value.includes("reason") || value.includes("objection")) return 3;
  if (value.includes("ptp") || value.includes("commit") || value.includes("payment")) return 4;
  if (value.includes("callback")) return 5;
  if (value.includes("close") || value.includes("summary")) return 6;
  return 0;
}

function callCues(strategy: { mode: string; tone: string }, step?: string, blocked?: number) {
  const cues = [
    "Open with identity and relationship confirmation before discussing dues.",
    "Keep each turn short: one ask, one confirmation, one next step.",
  ];
  if (strategy.mode === "soft_reminder") {
    cues[1] = "Lead with empathy, then anchor the borrower on the current due amount and nearest payment date.";
  } else if (strategy.mode === "firm_commitment") {
    cues[1] = "Push toward a specific payment promise or callback window within this interaction.";
  } else if (strategy.mode === "urgent_recovery") {
    cues[1] = "State urgency clearly, then present structured payment options without sounding threatening.";
  } else {
    cues[1] = "Hold a strict, compliant posture and avoid ad-libbing beyond the approved collections script.";
  }
  if (String(step || "").toLowerCase().includes("callback")) {
    cues.push("Confirm callback time, timezone, and best number before ending the conversation.");
  } else {
    cues.push("Close with a recap of amount, commitment, and follow-up channel.");
  }
  if (blocked) {
    cues.push("Compliance block is active. Do not promise exceptions or settlements without supervisor approval.");
  }
  return cues.slice(0, 3);
}

function downsampleLinear(input: Float32Array, sourceRate: number, targetRate: number): Float32Array {
  if (!input.length) return new Float32Array(0);
  if (sourceRate <= targetRate) return input;
  const ratio = sourceRate / targetRate;
  const outputLength = Math.max(1, Math.floor(input.length / ratio));
  const output = new Float32Array(outputLength);
  for (let i = 0; i < outputLength; i += 1) {
    const index = i * ratio;
    const i0 = Math.floor(index);
    const i1 = Math.min(i0 + 1, input.length - 1);
    const frac = index - i0;
    output[i] = input[i0] + (input[i1] - input[i0]) * frac;
  }
  return output;
}

function normalizeTaskDetail(input: TaskDetail | { rows?: TaskRow[] } | undefined, selectedTaskId: string | null): TaskDetail | null {
  if (!input) return null;
  if ("rows" in input && Array.isArray(input.rows)) {
    const picked = input.rows.find((row) => row.id === selectedTaskId) || input.rows[0];
    return picked ? ({ ...picked, events: [] } as TaskDetail) : null;
  }
  return input as TaskDetail;
}

function timelineFromTaskEvents(events?: TaskEvent[]) {
  return (events || []).slice(-8).reverse().map((event) => ({
    ts: Number(event.ts || 0),
    type: String(event.event_type || "event"),
    note: String(event.actor || "system"),
  }));
}

export function CallingConsolePage() {
  const qc = useQueryClient();
  const { user, role, hasPermission } = useAuth();
  const canMutate = hasPermission(PERMS.WORKBENCH_MUTATE);
  const isAgent = (role || "").toUpperCase() === ROLES.CALLING_AGENT;

  const [campaignId, setCampaignId] = useState("");
  const [dpdBucket, setDpdBucket] = useState("");
  const [slaOnly, setSlaOnly] = useState(false);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [callLive, setCallLive] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus>("disconnected");
  const [muted, setMuted] = useState(false);
  const [meterLevel, setMeterLevel] = useState(0);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [liveLog, setLiveLog] = useState<VoiceLogEntry[]>([]);
  const [draftText, setDraftText] = useState("");
  const [userPartial, setUserPartial] = useState("");
  const [agentPartial, setAgentPartial] = useState("");
  const [workflowStep, setWorkflowStep] = useState("");
  const [workflowDisposition, setWorkflowDisposition] = useState("");
  const [testCallPhone, setTestCallPhone] = useState("+91-9950022999");
  const [testCallBusy, setTestCallBusy] = useState(false);
  const [testCallSid, setTestCallSid] = useState("");
  const [testCallStatus, setTestCallStatus] = useState("");
  const [telephonySessionId, setTelephonySessionId] = useState("");
  const [selectedLanguage, setSelectedLanguage] = useState("hi-IN");
  const [selectedVoice, setSelectedVoice] = useState("shubh");
  const [ptpDateDraft, setPtpDateDraft] = useState("");
  const [callbackDateDraft, setCallbackDateDraft] = useState(dayjs().format("YYYY-MM-DD"));
  const [callbackTimeDraft, setCallbackTimeDraft] = useState("");

  const wsRef = useRef<WebSocket | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const scriptNodeRef = useRef<ScriptProcessorNode | null>(null);
  const captureTypeRef = useRef<"worklet" | "script" | null>(null);
  const resampleBufferRef = useRef<number[]>([]);
  const silentGainRef = useRef<GainNode | null>(null);
  const ttsGainRef = useRef<GainNode | null>(null);
  const playheadRef = useRef(0);
  const runningRef = useRef(false);
  const mutedRef = useRef(false);
  const audioStartedSentRef = useRef(false);
  const seenAgentUtteranceIdsRef = useRef<Set<string>>(new Set());
  const seenUserSegmentIdsRef = useRef<Set<string>>(new Set());
  const transcriptViewportRef = useRef<HTMLDivElement | null>(null);

  const build = useQuery({ queryKey: ["build_info"], queryFn: () => apiFetch<BuildInfo>("/api/system/build_info") });

  const tasksQuery = useQuery({
    queryKey: ["calling_tasks", campaignId, dpdBucket, role, user?.username],
    queryFn: () =>
      apiFetch<{ rows: TaskRow[] }>(
        `/api/tasks${toQuery({ campaign_id: campaignId, dpd_bucket: dpdBucket, sort: "sla_asc", page: 1, page_size: 100 })}`
      ),
    refetchInterval: autoRefresh ? 10_000 : false,
  });

  const selectedTaskQuery = useQuery({
    queryKey: ["calling_task_detail", selectedTaskId],
    queryFn: () => apiFetch<TaskDetail | { rows?: TaskRow[] }>(`/api/tasks/${encodeURIComponent(selectedTaskId || "")}`),
    enabled: !!selectedTaskId,
  });

  const sessionsQuery = useQuery({
    queryKey: ["calling_sessions"],
    queryFn: () => apiFetch<{ sessions: SessionSnapshot[] }>("/api/sessions"),
    refetchInterval: autoRefresh ? 10_000 : false,
  });

  useEffect(() => {
    if (!selectedTaskId && tasksQuery.data?.rows?.length) {
      const first = tasksQuery.data.rows[0];
      if (first?.id) setSelectedTaskId(first.id);
    }
  }, [tasksQuery.data, selectedTaskId]);

  useEffect(() => {
    setTelephonySessionId("");
    setTestCallSid("");
    setTestCallStatus("");
  }, [selectedTaskId]);

  const assignedQueue = useMemo(() => {
    const rows = tasksQuery.data?.rows || [];
    let out = rows;
    if (isAgent) {
      out = rows.filter((r) => String(r.owner || "") === String(user?.username || ""));
    }
    if (slaOnly) {
      out = out.filter((r) => !!r.sla_breach);
    }
    return out;
  }, [tasksQuery.data, isAgent, user?.username, slaOnly]);

  const sessionByCustomer = useMemo(() => {
    const map = new Map<string, SessionSnapshot>();
    for (const session of sessionsQuery.data?.sessions || []) {
      if (session.customer_id) {
        map.set(String(session.customer_id), session);
      }
    }
    return map;
  }, [sessionsQuery.data]);

  const task = useMemo(
    () => normalizeTaskDetail(selectedTaskQuery.data, selectedTaskId),
    [selectedTaskId, selectedTaskQuery.data]
  );

  const linkedSession = useMemo(() => {
    if (!task?.customer_id) return null;
    return sessionByCustomer.get(String(task.customer_id)) || null;
  }, [sessionByCustomer, task?.customer_id]);

  useEffect(() => {
    const nextStep = linkedSession?.current_step || linkedSession?.step;
    if (nextStep) {
      setWorkflowStep(String(nextStep));
    }
  }, [linkedSession?.current_step, linkedSession?.step]);

  useEffect(() => {
    setPtpDateDraft(String(task?.ptp_date || linkedSession?.ptp_date || ""));
    if (task?.callback_at) {
      setCallbackDateDraft(dayjs.unix(Number(task.callback_at)).format("YYYY-MM-DD"));
      setCallbackTimeDraft(dayjs.unix(Number(task.callback_at)).format("HH:mm"));
      return;
    }
    setCallbackDateDraft(dayjs().format("YYYY-MM-DD"));
    setCallbackTimeDraft(String(linkedSession?.callback_time || ""));
  }, [task?.id, task?.ptp_date, task?.callback_at, linkedSession?.ptp_date, linkedSession?.callback_time]);

  const timelineQuery = useQuery({
    queryKey: ["calling_timeline", linkedSession?.session_id],
    queryFn: () =>
      apiFetch<{ session_id: string; timeline: Array<{ ts: number; type: string; payload: Record<string, unknown> }> }>(
        `/api/sessions/${encodeURIComponent(linkedSession?.session_id || "")}/timeline`
      ),
    enabled: !!linkedSession?.session_id,
    refetchInterval: autoRefresh ? 10_000 : false,
  });

  const refresh = async () => {
    await qc.invalidateQueries({ queryKey: ["calling_tasks"] });
    await qc.invalidateQueries({ queryKey: ["calling_task_detail"] });
    await qc.invalidateQueries({ queryKey: ["calling_sessions"] });
    await qc.invalidateQueries({ queryKey: ["calling_timeline"] });
  };

  const pushLog = (who: "agent" | "user" | "system", text: string) => {
    const msg = (text || "").trim();
    if (!msg) return;
    setLiveLog((prev) => {
      const now = Date.now();
      const last = prev[prev.length - 1];
      if (last && last.who === who && normalizeLogText(last.text) === normalizeLogText(msg) && now - last.ts < 3000) {
        return prev;
      }
      const next = [...prev, { id: makeLogId(), who, text: msg, ts: now }];
      return next.slice(-200);
    });
  };

  const backendHttpBase = () => {
    const protocol = window.location.protocol;
    const host = window.location.hostname;
    const port = window.location.port;
    if (port === "5173") {
      return `${protocol}//${host}:8000`;
    }
    return window.location.origin;
  };

  const wsUrl = (token: string) => {
    const httpBase = new URL(backendHttpBase());
    const proto = httpBase.protocol === "https:" ? "wss:" : "ws:";
    const qs = new URLSearchParams({ token });
    return `${proto}//${httpBase.host}/ws/voice?${qs.toString()}`;
  };

  const voiceContext = () => {
    if (!task) return {};
    return {
      customer_id: task.customer_id,
      customer_name: task.customer_name,
      phone: task.phone,
      overdue_amount: task.amount_due,
      amount_due: task.amount_due,
      dpd: task.dpd,
      campaign_id: task.campaign_id,
      language_preference: selectedLanguage,
      tts_speaker: selectedVoice,
    };
  };

  const setupAudio = async () => {
    const Ctx = window.AudioContext || (window as Window & typeof globalThis & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctx) {
      throw new Error("AudioContext not supported in this browser");
    }

    const ctx = new Ctx({ latencyHint: "interactive" });
    audioCtxRef.current = ctx;

    const mic = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        sampleRate: TARGET_SAMPLE_RATE,
        echoCancellation: true,
        noiseSuppression: false,
        autoGainControl: false,
      },
    });
    micStreamRef.current = mic;

    const src = ctx.createMediaStreamSource(mic);
    sourceNodeRef.current = src;

    const silentGain = ctx.createGain();
    silentGain.gain.value = 0;
    silentGainRef.current = silentGain;

    const ttsGain = ctx.createGain();
    ttsGain.gain.value = 1;
    ttsGain.connect(ctx.destination);
    ttsGainRef.current = ttsGain;

    let captureNode: AudioNode | null = null;
    let usingWorklet = false;

    if ("audioWorklet" in ctx && typeof AudioWorkletNode !== "undefined") {
      try {
        const moduleCandidates = ["/worklets/pcm-processor.js", "/static/worklets/pcm-processor.js"];
        let loaded = false;
        let lastErr: unknown = null;
        for (const modulePath of moduleCandidates) {
          try {
            await ctx.audioWorklet.addModule(modulePath);
            loaded = true;
            break;
          } catch (err) {
            lastErr = err;
          }
        }
        if (!loaded) {
          throw lastErr || new Error("Unable to load pcm-processor worklet");
        }
        const worklet = new AudioWorkletNode(ctx, "pcm-processor", {
          processorOptions: { targetSampleRate: TARGET_SAMPLE_RATE, frameSamples: FRAME_SAMPLES },
        });
        workletNodeRef.current = worklet;
        captureTypeRef.current = "worklet";
        usingWorklet = true;
        captureNode = worklet;
        worklet.port.onmessage = (ev: MessageEvent<{ pcm?: ArrayBuffer; rms?: number }>) => {
          if (!runningRef.current) return;
          const rms = Number(ev.data?.rms || 0);
          const normalized = Math.max(0, Math.min(1, rms / 1800));
          setMeterLevel((prev) => prev * 0.78 + normalized * 0.22);
          const pcm = ev.data?.pcm;
          const ws = wsRef.current;
          if (pcm && ws && ws.readyState === WebSocket.OPEN && !mutedRef.current) {
            if (!audioStartedSentRef.current) {
              ws.send(JSON.stringify({ type: "audio_started" }));
              audioStartedSentRef.current = true;
            }
            ws.send(pcm);
          }
        };
      } catch {
        usingWorklet = false;
      }
    }

    if (!usingWorklet) {
      const script = ctx.createScriptProcessor(2048, 1, 1);
      scriptNodeRef.current = script;
      captureTypeRef.current = "script";
      captureNode = script;
      resampleBufferRef.current = [];
      script.onaudioprocess = (event) => {
        if (!runningRef.current) return;
        const input = event.inputBuffer.getChannelData(0);
        const rs = downsampleLinear(input, ctx.sampleRate, TARGET_SAMPLE_RATE);
        const pending = resampleBufferRef.current;
        for (let i = 0; i < rs.length; i += 1) {
          pending.push(rs[i]);
        }
        while (pending.length >= FRAME_SAMPLES) {
          const frame = pending.splice(0, FRAME_SAMPLES);
          const pcm = new Int16Array(FRAME_SAMPLES);
          let sum = 0;
          for (let i = 0; i < FRAME_SAMPLES; i += 1) {
            const sample = Math.max(-1, Math.min(1, (frame[i] || 0) * FALLBACK_MIC_GAIN));
            sum += sample * sample;
            pcm[i] = sample < 0 ? sample * 32768 : sample * 32767;
          }
          const rms = Math.sqrt(sum / FRAME_SAMPLES) * 32768;
          const normalized = Math.max(0, Math.min(1, rms / 1800));
          setMeterLevel((prev) => prev * 0.78 + normalized * 0.22);
          const ws = wsRef.current;
          if (ws && ws.readyState === WebSocket.OPEN && !mutedRef.current) {
            if (!audioStartedSentRef.current) {
              ws.send(JSON.stringify({ type: "audio_started" }));
              audioStartedSentRef.current = true;
            }
            ws.send(pcm.buffer);
          }
        }
        const output = event.outputBuffer.getChannelData(0);
        output.fill(0);
      };
    }

    if (!captureNode) {
      throw new Error("Unable to initialize audio capture");
    }

    src.connect(captureNode).connect(silentGain).connect(ctx.destination);

    if (ctx.state === "suspended") {
      await ctx.resume();
    }
  };

  const teardownAudio = async () => {
    try {
      workletNodeRef.current?.disconnect();
    } catch {
      // ignore
    }
    try {
      scriptNodeRef.current?.disconnect();
    } catch {
      // ignore
    }
    try {
      sourceNodeRef.current?.disconnect();
    } catch {
      // ignore
    }
    try {
      silentGainRef.current?.disconnect();
    } catch {
      // ignore
    }

    if (micStreamRef.current) {
      micStreamRef.current.getTracks().forEach((t) => t.stop());
    }

    if (audioCtxRef.current) {
      try {
        await audioCtxRef.current.close();
      } catch {
        // ignore
      }
    }

    workletNodeRef.current = null;
    scriptNodeRef.current = null;
    captureTypeRef.current = null;
    resampleBufferRef.current = [];
    sourceNodeRef.current = null;
    silentGainRef.current = null;
    micStreamRef.current = null;
    ttsGainRef.current = null;
    audioCtxRef.current = null;
    playheadRef.current = 0;
    setMeterLevel(0);
  };

  const handleAudioChunk = (arrayBuffer: ArrayBuffer) => {
    const ctx = audioCtxRef.current;
    if (!ctx) return;
    const pcm = new Int16Array(arrayBuffer);
    if (!pcm.length) return;

    const floats = new Float32Array(pcm.length);
    for (let i = 0; i < pcm.length; i += 1) {
      floats[i] = Math.max(-1, Math.min(1, pcm[i] / 32768));
    }

    const buffer = ctx.createBuffer(1, floats.length, TARGET_SAMPLE_RATE);
    buffer.copyToChannel(floats, 0);

    const source = ctx.createBufferSource();
    source.buffer = buffer;
    if (ttsGainRef.current) {
      source.connect(ttsGainRef.current);
    } else {
      source.connect(ctx.destination);
    }

    if (playheadRef.current < ctx.currentTime) {
      playheadRef.current = ctx.currentTime + 0.02;
    }
    source.start(playheadRef.current);
    playheadRef.current += buffer.duration;
  };

  const handleServerEvent = (payload: Record<string, unknown>) => {
    const type = String(payload.type || "");
    const utteranceId = String(payload.utterance_id || "");
    const segmentId = String(payload.segment_id || "");
    const textFromPayload = String(payload.text ?? payload.transcript ?? payload.partial ?? payload.message_text ?? payload.message ?? "");

    if (type === "status") {
      const raw = String(payload.state || "").toLowerCase();
      const normalizedState = raw === "ready" ? "listening" : raw;
      const state = normalizedState as VoiceStatus;
      setVoiceStatus(state || "listening");
      if (state === "thinking") {
        setAgentPartial("");
      }
      return;
    }

    if (type === "transcript") {
      const text = textFromPayload;
      const final = Boolean(payload.final ?? payload.is_final);
      if (final) {
        if (segmentId) {
          if (seenUserSegmentIdsRef.current.has(segmentId)) {
            setUserPartial("");
            return;
          }
          seenUserSegmentIdsRef.current.add(segmentId);
        }
        if (text.trim()) pushLog("user", text);
        setUserPartial("");
      } else {
        setUserPartial(text);
      }
      return;
    }

    if (type === "stt_final") {
      const text = textFromPayload;
      if (segmentId) {
        if (!seenUserSegmentIdsRef.current.has(segmentId)) {
          seenUserSegmentIdsRef.current.add(segmentId);
          if (text.trim()) pushLog("user", text);
        }
      } else if (text.trim()) {
        pushLog("user", text);
      }
      setUserPartial("");
      return;
    }

    if (type === "stt_partial") {
      setUserPartial(textFromPayload);
      return;
    }

    if (type === "assistant_token") {
      const text = textFromPayload;
      setAgentPartial((prev) => prev + text);
      return;
    }

    if (type === "assistant_final") {
      if (utteranceId && seenAgentUtteranceIdsRef.current.has(utteranceId)) {
        setAgentPartial("");
        return;
      }
      if (Boolean(payload.interrupted)) {
        setAgentPartial("");
        return;
      }
      const text = textFromPayload || agentPartial;
      if (text.trim()) pushLog("agent", text);
      if (utteranceId) seenAgentUtteranceIdsRef.current.add(utteranceId);
      setAgentPartial("");
      return;
    }

    if (type === "agent_utterance_created") {
      const text = textFromPayload;
      if (utteranceId && seenAgentUtteranceIdsRef.current.has(utteranceId)) {
        setAgentPartial("");
        return;
      }
      if (text.trim()) pushLog("agent", text);
      if (utteranceId) seenAgentUtteranceIdsRef.current.add(utteranceId);
      setAgentPartial("");
      return;
    }

    if (type === "workflow_update") {
      const state = (payload.state || {}) as Record<string, unknown>;
      const nextStep = String(state.current_step || "");
      const nextDisposition = String(state.disposition || "");
      if (nextStep) setWorkflowStep(nextStep);
      setWorkflowDisposition(nextDisposition);
      return;
    }

    if (type === "barge_in" || type === "interrupt_acknowledged") {
      return;
    }

    if (type === "error") {
      const msg = String(payload.message || "Voice server error");
      notifications.show({ color: "red", message: msg });
      setVoiceStatus("error");
    }
  };

  const stopCall = async () => {
    runningRef.current = false;
    setCallLive(false);
    setVoiceStatus("disconnected");
    setUserPartial("");
    setAgentPartial("");
    audioStartedSentRef.current = false;
    seenAgentUtteranceIdsRef.current.clear();
    seenUserSegmentIdsRef.current.clear();

    const ws = wsRef.current;
    if (ws) {
      try {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "stop" }));
        }
      } catch {
        // ignore
      }
      try {
        ws.close();
      } catch {
        // ignore
      }
    }
    wsRef.current = null;

    await teardownAudio();
  };

  const startCall = async () => {
    if (!task) return;
    if (!canMutate) {
      notifications.show({ color: "red", message: "This role is read-only for calling actions" });
      return;
    }

    if (!task.owner) {
      try {
        await apiFetch(`/api/tasks/${encodeURIComponent(task.id)}/claim`, { method: "POST" });
        await refresh();
      } catch {
        // ignore claim conflict
      }
    }

    await stopCall();
    runningRef.current = true;
    setCallLive(true);
    setVoiceStatus("connecting");
    setLiveLog([]);
    audioStartedSentRef.current = false;
    seenAgentUtteranceIdsRef.current.clear();
    seenUserSegmentIdsRef.current.clear();

    let wsToken = "";
    try {
      const tokenOut = await apiFetch<{ ws_token: string }>("/api/auth/ws-token", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      wsToken = tokenOut.ws_token || "";
    } catch (err) {
      notifications.show({ color: "red", message: `Unable to mint voice token: ${String(err)}` });
      await stopCall();
      return;
    }
    if (!wsToken) {
      notifications.show({ color: "red", message: "Unable to mint voice token" });
      await stopCall();
      return;
    }

    const ws = new WebSocket(wsUrl(wsToken));
    ws.binaryType = "arraybuffer";
    wsRef.current = ws;

    ws.onopen = async () => {
      try {
        await setupAudio();
      } catch (err) {
        notifications.show({ color: "red", message: `Mic setup failed: ${String(err)}` });
        await stopCall();
        return;
      }
      setVoiceStatus("listening");
      ws.send(JSON.stringify({ type: "start", sampleRate: TARGET_SAMPLE_RATE, context: voiceContext() }));
    };

    ws.onmessage = async (event) => {
      if (typeof event.data === "string") {
        try {
          handleServerEvent(JSON.parse(event.data) as Record<string, unknown>);
        } catch {
          // ignore
        }
        return;
      }
      if (event.data instanceof Blob) {
        try {
          const text = await event.data.text();
          try {
            handleServerEvent(JSON.parse(text) as Record<string, unknown>);
            return;
          } catch {
            const audioBuffer = await event.data.arrayBuffer();
            handleAudioChunk(audioBuffer);
          }
        } catch {
          // ignore
        }
        return;
      }
      if (event.data instanceof ArrayBuffer) {
        handleAudioChunk(event.data);
      }
    };

    ws.onerror = () => {
      setVoiceStatus("error");
      notifications.show({ color: "red", message: "Voice websocket error" });
    };

    ws.onclose = async () => {
      await stopCall();
    };
  };

  useEffect(() => {
    mutedRef.current = muted;
    const gain = ttsGainRef.current;
    const ctx = audioCtxRef.current;
    if (gain && ctx) {
      const now = ctx.currentTime;
      gain.gain.cancelScheduledValues(now);
      gain.gain.setValueAtTime(gain.gain.value, now);
      gain.gain.linearRampToValueAtTime(muted ? 0.0 : 1.0, now + 0.08);
    }
  }, [muted]);

  useEffect(() => {
    return () => {
      void stopCall();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!callLive || !task) return;
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: "set_context", context: voiceContext() }));
  }, [callLive, selectedLanguage, task?.id, selectedVoice]);

  useEffect(() => {
    const viewport = transcriptViewportRef.current;
    if (!viewport) return;
    viewport.scrollTop = viewport.scrollHeight;
  }, [agentPartial, liveLog, userPartial]);

  const sendNote = () => {
    const text = draftText.trim();
    if (!text) return;
    pushLog("agent", text);
    setDraftText("");
  };

  const requestMic = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((t) => t.stop());
      notifications.show({ color: "green", message: "Microphone permission granted" });
    } catch {
      notifications.show({ color: "red", message: "Microphone permission denied" });
    }
  };

  const triggerTestCall = async () => {
    if (!canMutate) {
      notifications.show({ color: "red", message: "This role is read-only for calling actions" });
      return;
    }
    const phone = testCallPhone.trim();
    if (!phone) {
      notifications.show({ color: "red", message: "Enter destination phone number" });
      return;
    }
    setTestCallBusy(true);
    try {
      const out = await apiFetch<{
        ok: boolean;
        session_id?: string;
        result?: { call_sid?: string; call_status?: string; delivery_status?: string; normalized_to?: string };
      }>("/api/telephony/agent_call", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          phone,
          customer_name: task?.customer_name || task?.customer_id || undefined,
          customer_id: task?.customer_id || undefined,
          campaign_id: task?.campaign_id || undefined,
          amount_due: task?.amount_due != null ? String(task.amount_due) : undefined,
          language: selectedLanguage,
          tts_speaker: selectedVoice,
          timeout_seconds: 25,
        }),
      });
      const sid = String(out.result?.call_sid || "");
      const status = String(out.result?.call_status || out.result?.delivery_status || "queued");
      setTelephonySessionId(String(out.session_id || ""));
      setTestCallSid(sid);
      setTestCallStatus(status);
      notifications.show({
        color: "green",
        message: sid ? `Agent call queued (${sid})` : "Agent call queued",
      });
    } catch (err) {
      notifications.show({ color: "red", message: String(err) });
    } finally {
      setTestCallBusy(false);
    }
  };

  const updateDisposition = async (action: "PTP" | "CALLBACK" | "PAID" | "ESCALATE" | "CLOSE") => {
    if (!task) return;
    const state = ACTION_STATE_MAP[action];
    const disposition =
      action === "PTP"
        ? "ptp_captured"
        : action === "CALLBACK"
          ? "callback_scheduled"
          : action === "PAID"
            ? "paid"
          : action === "ESCALATE"
              ? "escalated"
              : "closed";
    try {
      const body: Record<string, unknown> = { state, disposition, notes: `action:${action}` };
      const outcomeSessionId = linkedSession?.session_id || telephonySessionId;
      if (outcomeSessionId) {
        body.session_id = outcomeSessionId;
      }
      if (action === "PTP") {
        const ptpDate = (ptpDateDraft || linkedSession?.ptp_date || task.ptp_date || "").trim();
        if (!ptpDate) {
          notifications.show({ color: "orange", message: "Enter or confirm a PTP date before saving the commitment." });
          return;
        }
        body.ptp_date = ptpDate;
      }
      if (action === "CALLBACK") {
        const callbackTime = (callbackTimeDraft || linkedSession?.callback_time || "").trim();
        if (!callbackTime) {
          notifications.show({ color: "orange", message: "Enter a callback time before saving the follow-up." });
          return;
        }
        body.callback_at = `${callbackDateDraft || dayjs().format("YYYY-MM-DD")}T${callbackTime}`;
      }
      const out = await apiFetch<{ followups?: Array<unknown> }>(`/api/tasks/${encodeURIComponent(task.id)}/update`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const ws = wsRef.current;
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "set_disposition", disposition }));
      }
      const scheduled = Array.isArray(out.followups) ? out.followups.length : 0;
      notifications.show({
        color: "green",
        message: action === "PTP" && scheduled ? `Task marked ${action}. ${scheduled} follow-ups scheduled.` : `Task marked ${action}`,
      });
      await refresh();
    } catch (err) {
      notifications.show({ color: "red", message: String(err) });
    }
  };

  const strategy = strategyForDpd(task?.dpd);
  const compliance = parseCompliance(task?.compliance_status_json);
  const complianceEntries = Object.entries(compliance);
  const complianceScore = complianceEntries.length
    ? Math.round((complianceEntries.filter(([, ok]) => ok).length / complianceEntries.length) * 100)
    : 100;
  const currentStep = workflowStep || linkedSession?.current_step || linkedSession?.step || "consent";
  const currentFlowIndex = flowIndexForStep(currentStep);
  const strategyCues = callCues(strategy, currentStep, task?.compliance_block);
  const selectedQueueIndex = selectedTaskId ? assignedQueue.findIndex((row) => row.id === selectedTaskId) + 1 : 0;
  const slaBreaches = assignedQueue.filter((row) => !!row.sla_breach).length;
  const totalExposure = assignedQueue.reduce((sum, row) => sum + Number(row.amount_due || 0), 0);
  const activeSessionCount = (sessionsQuery.data?.sessions || []).filter((session) => session.customer_id && sessionByCustomer.has(String(session.customer_id))).length;
  const currentStageMeta = CALL_FLOW[Math.min(currentFlowIndex, CALL_FLOW.length - 1)] || CALL_FLOW[0];
  const selectedBorrowerLabel = task?.customer_name || task?.customer_id || "No borrower selected";
  const trackedPtpDate = ptpDateDraft || task?.ptp_date || linkedSession?.ptp_date || "";
  const trackedCallbackTime =
    callbackTimeDraft ||
    (task?.callback_at ? dayjs.unix(Number(task.callback_at)).format("HH:mm") : "") ||
    linkedSession?.callback_time ||
    "";
  const timelineItems = useMemo(() => {
    const liveTimeline =
      (timelineQuery.data?.timeline || [])
        .slice(-8)
        .reverse()
        .map((event) => ({
          ts: Number(event.ts || 0),
          type: String(event.type || "event"),
          note: humanizeSlug(String(event.payload?.state || event.payload?.disposition || "")),
        })) || [];
    return liveTimeline.length ? liveTimeline : timelineFromTaskEvents(task?.events);
  }, [task?.events, timelineQuery.data]);
  const ui = {
    heading: "var(--te-calling-heading)",
    body: "var(--te-calling-body)",
    soft: "var(--te-calling-soft)",
    muted: "var(--te-calling-muted)",
    label: "var(--te-calling-label)",
    icon: "var(--te-calling-icon)",
    success: "var(--te-calling-success)",
    danger: "var(--te-calling-danger)",
    warning: "var(--te-calling-warning)",
    warningText: "var(--te-calling-warning-text)",
  } as const;

  const toolbar = (
    <Paper className="te-calling-toolbar" p="lg" radius="xl" withBorder>
      <Stack gap="md">
        <Group justify="space-between" align="flex-start" wrap="wrap">
          <Stack gap={6} maw={760}>
            <Group gap="xs" wrap="wrap">
              <Badge className="te-calling-hero-badge">{isAgent ? "Calling Agent Workspace" : "Collections Voice Desk"}</Badge>
              <Badge variant="light" color={statusColor(voiceStatus)}>
                {voiceHeadline(voiceStatus)}
              </Badge>
              {build.data?.pilot_mode ? <Badge variant="light" color="orange">Pilot</Badge> : null}
              {build.data?.demo_mode ? <Badge variant="light" color="teal">Demo</Badge> : null}
            </Group>
            <Group gap="sm" wrap="wrap">
              <Title order={3} className="te-calling-toolbar-title">
                Calling Console
              </Title>
              <Badge className="te-calling-strip-badge" variant="outline">
                Stage {currentFlowIndex + 1} / {CALL_FLOW.length}
              </Badge>
              <Badge className="te-calling-strip-badge" variant="outline">
                {humanizeSlug(currentStageMeta.label)}
              </Badge>
            </Group>
            <Text className="te-calling-toolbar-copy">
              Clean voice operations, borrower context, and compliant closure in one aligned enterprise workspace.
            </Text>
          </Stack>

          <Group className="te-calling-toolbar-actions" wrap="wrap">
            <Paper className="te-calling-toggle">
              <Text size="sm" fw={600} c={ui.body}>
                Auto refresh
              </Text>
              <Switch checked={autoRefresh} onChange={(e) => setAutoRefresh(e.currentTarget.checked)} color="teal" />
            </Paper>
            <Button variant="light" color="blue" onClick={refresh}>
              Refresh
            </Button>
          </Group>
        </Group>

        <SimpleGrid cols={{ base: 2, xl: 4 }} spacing="sm">
          <Paper className="te-calling-stat" p="md" radius="xl">
            <Text className="te-calling-stat-label">Queue Ready</Text>
            <Text className="te-calling-stat-value">{assignedQueue.length}</Text>
            <Text className="te-calling-stat-hint">{isAgent ? "Accounts owned by you" : "Accounts in active queue"}</Text>
          </Paper>
          <Paper className="te-calling-stat" p="md" radius="xl">
            <Text className="te-calling-stat-label">Exposure</Text>
            <Text className="te-calling-stat-value">{fmtAmount(totalExposure)}</Text>
            <Text className="te-calling-stat-hint">{slaBreaches} SLA breach{slaBreaches === 1 ? "" : "es"} flagged</Text>
          </Paper>
          <Paper className="te-calling-stat" p="md" radius="xl">
            <Text className="te-calling-stat-label">Selected Borrower</Text>
            <Text className="te-calling-stat-value te-calling-stat-value--compact">{selectedBorrowerLabel}</Text>
            <Text className="te-calling-stat-hint">
              {task?.phone || "No phone on selection"} {selectedQueueIndex ? `• ${selectedQueueIndex}/${Math.max(assignedQueue.length, 1)}` : ""}
            </Text>
          </Paper>
          <Paper className="te-calling-stat" p="md" radius="xl">
            <Text className="te-calling-stat-label">Compliance</Text>
            <Text className="te-calling-stat-value">{complianceScore}%</Text>
            <Text className="te-calling-stat-hint">
              {callLive ? "Live voice bridge active" : "Bridge idle"} • Build {String(build.data?.static_token || "-").toUpperCase()}
            </Text>
          </Paper>
        </SimpleGrid>
      </Stack>
    </Paper>
  );

  if (!task && !assignedQueue.length) {
    return (
      <Stack gap="md" className="te-calling-shell">
        {toolbar}
        <div className="te-calling-layout te-calling-layout--empty">
          <Card className="te-calling-panel te-calling-panel--accent te-calling-fill-card">
            <Stack gap="md" h="100%">
              <Group justify="space-between" wrap="wrap">
                <div>
                  <Text className="te-calling-section-label">Phone Agent Call</Text>
                  <Title order={4} c={ui.heading}>
                    Direct phone bridge
                  </Title>
                </div>
                <Badge variant="outline" color="violet">
                  Twilio + Sarvam Live
                </Badge>
              </Group>
              <Text c={ui.body} size="sm">
                Keep outbound testing available even before task assignment.
              </Text>
              <TextInput
                label="Destination Number"
                placeholder="+91-9950022999"
                value={testCallPhone}
                onChange={(e) => setTestCallPhone(e.currentTarget.value)}
              />
              <SimpleGrid cols={2} spacing="sm">
                <Button leftSection={<Phone size={14} />} onClick={triggerTestCall} loading={testCallBusy} disabled={!canMutate}>
                  Call Number
                </Button>
                <Button variant="light" leftSection={<Mic size={14} />} onClick={requestMic}>
                  Check Mic
                </Button>
              </SimpleGrid>
              {testCallSid ? (
                <Paper className="te-calling-inline-note" p="sm" radius="lg">
                  <Group justify="space-between" wrap="wrap">
                    <Text size="sm" c={ui.heading}>
                      Last call SID: {testCallSid}
                    </Text>
                    <Badge color="teal" variant="light">
                      {humanizeSlug(testCallStatus || "queued")}
                    </Badge>
                  </Group>
                </Paper>
              ) : null}
            </Stack>
          </Card>

          <Card className="te-calling-panel te-calling-fill-card">
            <Stack gap="lg" h="100%" justify="center">
              <EmptyStateCard
                title="No assigned tasks"
                description="Assign borrower accounts from Workbench to open the live calling cockpit. This view is optimized for active calling, not empty states."
              />
              <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
                {[
                  "Route work to the calling agent from Workbench.",
                  "Verify microphone access and voice selection.",
                  "Use the phone bridge only for supervised outbound checks.",
                ].map((item) => (
                  <Paper key={item} className="te-calling-brief-card" p="md" radius="xl">
                    <Text size="sm" c={ui.body}>
                      {item}
                    </Text>
                  </Paper>
                ))}
              </SimpleGrid>
            </Stack>
          </Card>
        </div>
      </Stack>
    );
  }

  return (
    <Stack gap="md" className="te-calling-shell">
      {toolbar}

      <div className="te-calling-layout">
        <Card className="te-calling-panel te-calling-panel--queue te-calling-fill-card">
          <Stack gap="md" h="100%">
            <Group justify="space-between" wrap="wrap">
              <div>
                <Text className="te-calling-section-label">Assigned Queue</Text>
                <Title order={4} c={ui.heading}>
                  Ready to dial
                </Title>
              </div>
              <Badge variant="light" color={slaBreaches ? "red" : "teal"}>
                {slaBreaches ? `${slaBreaches} at risk` : "Healthy"}
              </Badge>
            </Group>

            <SimpleGrid cols={{ base: 1, sm: 2, xl: 1 }} spacing="sm">
              <TextInput label="Campaign" value={campaignId} onChange={(e) => setCampaignId(e.currentTarget.value)} placeholder="Filter campaign" />
              <Select
                label="DPD bucket"
                value={dpdBucket}
                onChange={(value) => setDpdBucket(value || "")}
                data={["", "1-30", "31-60", "61-90", "90+"].map((value) => ({ value, label: value || "All" }))}
              />
            </SimpleGrid>

            <Group justify="space-between" wrap="wrap">
              <Switch checked={slaOnly} onChange={(e) => setSlaOnly(e.currentTarget.checked)} label="Only SLA breaches" color="red" />
              <Text size="xs" c={ui.muted}>
                {assignedQueue.length} borrower{assignedQueue.length === 1 ? "" : "s"}
              </Text>
            </Group>

            <ScrollArea className="te-subtle-scroll te-calling-scroll-fill">
              <Stack gap="sm">
                {assignedQueue.map((row) => {
                  const rowSession = row.customer_id ? sessionByCustomer.get(String(row.customer_id)) : null;
                  const active = selectedTaskId === row.id;
                  return (
                    <Paper
                      key={row.id}
                      className="te-calling-queue-row"
                      data-active={active ? "true" : "false"}
                      p="md"
                      radius="xl"
                      onClick={() => setSelectedTaskId(row.id)}
                    >
                      <Group justify="space-between" align="flex-start" wrap="nowrap">
                        <Stack gap={2}>
                          <Text fw={700} c={ui.heading}>
                            {row.customer_name || row.customer_id}
                          </Text>
                          <Text size="xs" c={ui.muted}>
                            {row.customer_id}
                          </Text>
                        </Stack>
                        <Group gap={6} wrap="wrap" justify="flex-end">
                          <Badge color={row.sla_breach ? "red" : "teal"} variant={row.sla_breach ? "filled" : "light"}>
                            {row.sla_breach ? "SLA" : "On track"}
                          </Badge>
                          <Badge variant="outline" color="blue">
                            {humanizeSlug(row.state)}
                          </Badge>
                        </Group>
                      </Group>

                      <div className="te-calling-queue-meta">
                        <div>
                          <Text size="10px" tt="uppercase" c={ui.label} fw={700}>
                            Amount
                          </Text>
                          <Text size="sm" fw={700} c={ui.heading}>
                            {fmtAmount(row.amount_due)}
                          </Text>
                        </div>
                        <div>
                          <Text size="10px" tt="uppercase" c={ui.label} fw={700}>
                            DPD
                          </Text>
                          <Text size="sm" fw={700} c={ui.heading}>
                            {row.dpd ?? "-"}
                          </Text>
                        </div>
                        <div>
                          <Text size="10px" tt="uppercase" c={ui.label} fw={700}>
                            Owner
                          </Text>
                          <Text size="sm" c={ui.body}>
                            {row.owner || "Unassigned"}
                          </Text>
                        </div>
                        <div>
                          <Text size="10px" tt="uppercase" c={ui.label} fw={700}>
                            Last action
                          </Text>
                          <Text size="sm" c={ui.body}>
                            {row.last_action_at ? dayjs.unix(row.last_action_at).format("DD MMM HH:mm") : "Fresh"}
                          </Text>
                        </div>
                      </div>

                      <Group gap="xs" wrap="wrap" mt="sm">
                        {rowSession?.session_id ? (
                          <Badge variant="outline" color="teal">
                            Live session
                          </Badge>
                        ) : null}
                        {row.phone ? (
                          <Badge variant="outline" color="gray">
                            {row.phone}
                          </Badge>
                        ) : null}
                      </Group>
                    </Paper>
                  );
                })}

                {!assignedQueue.length ? (
                  <Paper className="te-calling-inline-note" p="md" radius="xl">
                    <Text size="sm" c={ui.body}>
                      No rows match the current filter set.
                    </Text>
                  </Paper>
                ) : null}
              </Stack>
            </ScrollArea>
          </Stack>
        </Card>

        <Card className="te-calling-panel te-calling-panel--primary te-calling-fill-card">
          <Stack gap="md" h="100%">
            <Group justify="space-between" wrap="wrap">
              <div>
                <Text className="te-calling-section-label">Live Call Engine</Text>
                <Title order={4} c={ui.heading}>
                  Voice orchestration deck
                </Title>
              </div>
              <Group gap="xs" wrap="wrap">
                <Badge color={statusColor(voiceStatus)}>{voiceStatus.toUpperCase()}</Badge>
                {callLive ? <Badge color="teal">ACTIVE</Badge> : <Badge variant="outline">IDLE</Badge>}
              </Group>
            </Group>

            {task ? (
              <>
                <Paper className="te-stage-rail" p="md" radius="xl">
                  <Group justify="space-between" wrap="wrap">
                    <div>
                      <Text className="te-calling-section-label">Call Journey</Text>
                      <Text size="sm" fw={700} c={ui.heading}>
                        Stage {currentFlowIndex + 1} of {CALL_FLOW.length} • {currentStageMeta.label}
                      </Text>
                    </div>
                    <Badge variant="outline" color="blue">
                      {humanizeSlug(workflowDisposition || task.disposition || task.state)}
                    </Badge>
                  </Group>
                  <div className="te-stage-track">
                    {CALL_FLOW.map((step, idx) => (
                      <div
                        key={step.label}
                        className="te-stage-item"
                        data-active={idx <= currentFlowIndex ? "true" : "false"}
                        data-current={idx === currentFlowIndex ? "true" : "false"}
                      >
                        <div className="te-stage-node">{idx + 1}</div>
                        <Text className="te-stage-caption">{step.short}</Text>
                      </div>
                    ))}
                  </div>
                </Paper>

                <div className="te-calling-summary-grid">
                  <Paper className="te-calling-brief-card" p="md" radius="xl">
                    <Text size="10px" tt="uppercase" fw={700} c={ui.label}>
                      Borrower
                    </Text>
                    <Text fw={700} c={ui.heading}>
                      {selectedBorrowerLabel}
                    </Text>
                    <Text size="sm" c={ui.body}>
                      {task.phone || "No phone recorded"}
                    </Text>
                  </Paper>
                  <Paper className="te-calling-brief-card" p="md" radius="xl">
                    <Text size="10px" tt="uppercase" fw={700} c={ui.label}>
                      Exposure
                    </Text>
                    <Text fw={700} c={ui.heading}>
                      {fmtAmount(task.amount_due)}
                    </Text>
                    <Text size="sm" c={ui.body}>
                      DPD {task.dpd ?? "-"} • {humanizeSlug(task.state)}
                    </Text>
                  </Paper>
                  <Paper className="te-calling-brief-card" p="md" radius="xl">
                    <Text size="10px" tt="uppercase" fw={700} c={ui.label}>
                      Campaign
                    </Text>
                    <Text fw={700} c={ui.heading}>
                      {task.campaign_id || "-"}
                    </Text>
                    <Text size="sm" c={ui.body}>
                      Owner {task.owner || "Unassigned"}
                    </Text>
                  </Paper>
                  <Paper className="te-calling-brief-card" p="md" radius="xl">
                    <Text size="10px" tt="uppercase" fw={700} c={ui.label}>
                      Session
                    </Text>
                    <Text fw={700} c={ui.heading}>
                      {linkedSession?.session_id ? linkedSession.session_id.slice(-10) : "Awaiting connection"}
                    </Text>
                    <Text size="sm" c={ui.body}>
                      {voiceHeadline(voiceStatus)}
                    </Text>
                  </Paper>
                  <Paper className="te-calling-brief-card" p="md" radius="xl">
                    <Text size="10px" tt="uppercase" fw={700} c={ui.label}>
                      Commitment
                    </Text>
                    <Text fw={700} c={ui.heading}>
                      {trackedPtpDate
                        ? dayjs(trackedPtpDate).format("DD MMM YYYY")
                        : trackedCallbackTime
                          ? `Callback ${trackedCallbackTime}`
                          : "Awaiting commitment"}
                    </Text>
                    <Text size="sm" c={ui.body}>
                      {trackedPtpDate
                        ? "PTP tracked for follow-up scheduling"
                        : trackedCallbackTime
                          ? `Next touch on ${callbackDateDraft || dayjs().format("YYYY-MM-DD")}`
                          : "Capture PTP date or callback to lock next action"}
                    </Text>
                  </Paper>
                </div>

                <div className="te-calling-control-grid">
                  <div className="te-calling-control-main">
                    <div className="te-calling-config-grid">
                      <Select
                        label="Starting Language"
                        description="Default language used when the call begins."
                        value={selectedLanguage}
                        onChange={(value) => setSelectedLanguage(value || "hi-IN")}
                        data={STARTING_LANGUAGE_OPTIONS}
                        allowDeselect={false}
                      />
                      <Select
                        label="Bulbul Voice"
                        description="Applies to live Sarvam session and phone agent call."
                        value={selectedVoice}
                        onChange={(value) => setSelectedVoice(value || "shubh")}
                        data={BULBUL_V3_VOICE_OPTIONS}
                        searchable
                        maxDropdownHeight={280}
                      />
                    </div>
                    <div className="te-calling-actions-grid">
                      <Button leftSection={<Phone size={14} />} onClick={startCall} disabled={callLive || !canMutate}>
                        Start Call
                      </Button>
                      <Button color="red" variant="light" leftSection={<PhoneOff size={14} />} onClick={() => void stopCall()} disabled={!callLive}>
                        End Call
                      </Button>
                      <Button
                        variant="light"
                        leftSection={muted ? <MicOff size={14} /> : <Mic size={14} />}
                        onClick={() => setMuted((value) => !value)}
                        disabled={!callLive}
                      >
                        {muted ? "Unmute" : "Mute"}
                      </Button>
                      <Button variant="subtle" leftSection={<Mic size={14} />} onClick={requestMic}>
                        Check Mic
                      </Button>
                    </div>
                  </div>

                  <Paper className="te-calling-meter te-calling-meter--compact" p="md" radius="xl">
                    <Stack gap={8}>
                      <Text className="te-calling-section-label">Mic Level</Text>
                      <Text size="sm" c={ui.body}>
                        {Math.round(meterLevel * 100)}% input power
                      </Text>
                      <Group gap="xs" wrap="nowrap">
                        <Waves size={16} color={ui.success} />
                        <Progress value={Math.round(meterLevel * 100)} color="teal" radius="xl" style={{ flex: 1 }} />
                      </Group>
                    </Stack>
                  </Paper>
                </div>

                <Paper className="te-calling-transcript-panel" p="md" radius="xl">
                  <Stack gap="md" h="100%">
                    <Group justify="space-between" wrap="wrap">
                      <div>
                        <Text className="te-calling-section-label">Conversation Log</Text>
                        <Title order={5} c={ui.heading}>
                          Live transcript
                        </Title>
                      </div>
                      <Badge variant="outline" color="teal">
                        {liveLog.length} message{liveLog.length === 1 ? "" : "s"}
                      </Badge>
                    </Group>

                    <ScrollArea className="te-subtle-scroll te-calling-scroll-fill" viewportRef={transcriptViewportRef}>
                      <Stack gap="sm">
                        {!liveLog.length ? (
                          <Paper className="te-calling-inline-note" p="md" radius="xl">
                            <Text size="sm" c={ui.body}>
                              Start call to begin live transcript capture.
                            </Text>
                          </Paper>
                        ) : null}
                        {liveLog.map((message) => (
                          <Paper key={message.id} className="te-transcript-bubble" data-who={message.who} p="md" radius="xl">
                            <Group justify="space-between" wrap="wrap">
                              <Text size="xs" fw={700} c={ui.body}>
                                {message.who === "agent" ? "Agent" : message.who === "user" ? "Borrower" : "System"}
                              </Text>
                              <Text size="10px" c={ui.muted}>
                                {dayjs(message.ts).format("HH:mm:ss")}
                              </Text>
                            </Group>
                            <Text size="sm" c={ui.heading} mt={6}>
                              {message.text}
                            </Text>
                          </Paper>
                        ))}
                        {userPartial ? (
                          <Paper className="te-transcript-partial" data-who="user" p="sm" radius="xl">
                            <Text size="sm" c={ui.success}>
                              Borrower (partial): {userPartial}
                            </Text>
                          </Paper>
                        ) : null}
                        {agentPartial ? (
                          <Paper className="te-transcript-partial" data-who="agent" p="sm" radius="xl">
                            <Text size="sm" c={ui.body}>
                              Agent (partial): {agentPartial}
                            </Text>
                          </Paper>
                        ) : null}
                      </Stack>
                    </ScrollArea>

                    <Group align="end" wrap="wrap">
                      <TextInput
                        label="Agent Note"
                        placeholder="Add manual note to the live call log"
                        value={draftText}
                        onChange={(e) => setDraftText(e.currentTarget.value)}
                        style={{ flex: 1, minWidth: 240 }}
                      />
                      <Button onClick={sendNote} disabled={!draftText.trim()} leftSection={<Volume2 size={14} />}>
                        Add Note
                      </Button>
                    </Group>
                  </Stack>
                </Paper>

                <Paper className="te-calling-inline-note" p="md" radius="xl">
                  <Stack gap="sm">
                    <Group justify="space-between" wrap="wrap">
                      <div>
                        <Text className="te-calling-section-label">Commitment Capture</Text>
                        <Title order={5} c={ui.heading}>
                          Save the promise or callback from the desk
                        </Title>
                      </div>
                      <Badge variant="outline" color="blue">
                        Ops Proof
                      </Badge>
                    </Group>
                    <SimpleGrid cols={{ base: 1, md: 3 }}>
                      <TextInput
                        label="PTP date"
                        type="date"
                        value={ptpDateDraft}
                        onChange={(e) => setPtpDateDraft(e.currentTarget.value)}
                        description="Required before using Capture PTP."
                      />
                      <TextInput
                        label="Callback date"
                        type="date"
                        value={callbackDateDraft}
                        onChange={(e) => setCallbackDateDraft(e.currentTarget.value)}
                        description="Used when a borrower asks for a follow-up."
                      />
                      <TextInput
                        label="Callback time"
                        type="time"
                        value={callbackTimeDraft}
                        onChange={(e) => setCallbackTimeDraft(e.currentTarget.value)}
                        description="Required before using Callback."
                      />
                    </SimpleGrid>
                    <Text size="xs" c={ui.muted}>
                      Saving a PTP from here creates the commitment trail the dashboard, alerts, and follow-up metrics depend on.
                    </Text>
                  </Stack>
                </Paper>

                <div className="te-disposition-grid">
                  {[
                    { action: "PTP" as const, label: "Capture PTP", color: "blue", variant: "filled" as const },
                    { action: "CALLBACK" as const, label: "Callback", color: "teal", variant: "light" as const },
                    { action: "PAID" as const, label: "Paid", color: "green", variant: "light" as const },
                    { action: "ESCALATE" as const, label: "Escalate", color: "orange", variant: "light" as const },
                    { action: "CLOSE" as const, label: "Close", color: "gray", variant: "light" as const },
                  ].map((item) => (
                    <Button
                      key={item.action}
                      color={item.color}
                      variant={item.variant}
                      onClick={() => updateDisposition(item.action)}
                      disabled={!canMutate}
                    >
                      {item.label}
                    </Button>
                  ))}
                </div>
              </>
            ) : (
              <Paper className="te-calling-inline-note" p="md" radius="xl">
                <Text size="sm" c={ui.body}>
                  Select a task from the queue to load the borrower brief and voice controls.
                </Text>
              </Paper>
            )}
          </Stack>
        </Card>

        <div className="te-calling-rail">
          <Card className="te-calling-panel te-calling-panel--accent">
            <Stack gap="md">
              <Group justify="space-between" wrap="wrap">
                <div>
                  <Text className="te-calling-section-label">Phone Agent Call</Text>
                  <Title order={4} c={ui.heading}>
                    Supervised outbound bridge
                  </Title>
                </div>
                <Badge variant="outline" color="violet">
                  Twilio + Sarvam Live
                </Badge>
              </Group>

              <TextInput
                label="Destination Number"
                placeholder="+91-9950022999"
                value={testCallPhone}
                onChange={(e) => setTestCallPhone(e.currentTarget.value)}
              />

              <div className="te-calling-actions-grid te-calling-actions-grid--rail">
                <Button variant="light" onClick={() => setTestCallPhone(task?.phone || "+91-9950022999")} disabled={!task?.phone}>
                  Use Task Phone
                </Button>
                <Button leftSection={<Phone size={14} />} onClick={triggerTestCall} loading={testCallBusy} disabled={!canMutate}>
                  Call Number
                </Button>
                <Button variant="subtle" leftSection={<Mic size={14} />} onClick={requestMic}>
                  Check Mic
                </Button>
              </div>

              <Text size="xs" c={ui.body}>
                This connects the phone call to your live Sarvam collections agent (two-way voice streaming).
              </Text>

              {testCallSid ? (
                <Paper className="te-calling-inline-note" p="sm" radius="lg">
                  <Group justify="space-between" wrap="wrap">
                    <Text size="sm" c={ui.heading}>
                      Last call SID
                    </Text>
                    <Badge color="teal" variant="light">
                      {humanizeSlug(testCallStatus || "queued")}
                    </Badge>
                  </Group>
                  <Text size="xs" c={ui.body} mt={6}>
                    {testCallSid}
                  </Text>
                </Paper>
              ) : null}
            </Stack>
          </Card>

          <Card className="te-calling-panel">
            <Stack gap="md">
              <Group justify="space-between" wrap="wrap">
                <div>
                  <Text className="te-calling-section-label">Guidance & Compliance</Text>
                  <Title order={4} c={ui.heading}>
                    Borrower brief
                  </Title>
                </div>
                <Badge variant="light" color="blue">
                  DPD {task?.dpd ?? "-"}
                </Badge>
              </Group>

              <Paper className="te-calling-brief-card" p="md" radius="xl">
                <Group justify="space-between" wrap="nowrap">
                  <div>
                    <Text size="10px" tt="uppercase" fw={700} c={ui.label}>
                      Strategy
                    </Text>
                    <Text fw={700} c={ui.heading}>
                      {humanizeSlug(strategy.mode)}
                    </Text>
                    <Text size="sm" c={ui.body} mt={4}>
                      {strategy.tone}
                    </Text>
                  </div>
                  <ArrowRight size={16} color={ui.icon} />
                </Group>
              </Paper>

              <Stack gap="xs">
                {strategyCues.map((cue, idx) => (
                  <Paper key={cue} className="te-calling-inline-note" p="md" radius="xl">
                    <Group align="flex-start" wrap="nowrap">
                      <Badge color="blue" variant="light">
                        {idx + 1}
                      </Badge>
                      <Text size="sm" c={ui.body}>
                        {cue}
                      </Text>
                    </Group>
                  </Paper>
                ))}
              </Stack>

              <Paper className="te-calling-meter te-calling-meter--compact" p="md" radius="xl">
                <Stack gap={8}>
                  <Group justify="space-between">
                    <Text size="sm" fw={700} c={ui.heading}>
                      Compliance score
                    </Text>
                    <Text size="sm" c={ui.success}>
                      {complianceScore}%
                    </Text>
                  </Group>
                  <Progress value={complianceScore} color={complianceScore >= 80 ? "teal" : complianceScore >= 60 ? "yellow" : "red"} radius="xl" />
                </Stack>
              </Paper>

              <div className="te-compliance-grid">
                {complianceEntries.map(([key, ok]) => (
                  <Paper key={key} className="te-compliance-row" p="sm" radius="xl">
                    <Group justify="space-between" wrap="nowrap">
                      <Group gap={8} wrap="nowrap">
                        {ok ? <CheckCheck size={15} color={ui.success} /> : <AlertTriangle size={15} color={ui.danger} />}
                        <Text size="sm" c={ui.heading}>
                          {humanizeSlug(key)}
                        </Text>
                      </Group>
                      <Badge color={ok ? "green" : "red"} variant="light">
                        {ok ? "OK" : "Fail"}
                      </Badge>
                    </Group>
                  </Paper>
                ))}
              </div>

              {task?.compliance_block ? (
                <Paper className="te-calling-alert" p="md" radius="xl">
                  <Group align="flex-start" wrap="nowrap">
                    <Shield size={16} color={ui.warning} />
                    <Text size="sm" c={ui.warningText}>
                      Compliance block active. Supervisor override is required before moving beyond the approved script.
                    </Text>
                  </Group>
                </Paper>
              ) : null}
            </Stack>
          </Card>

          <Card className="te-calling-panel te-calling-fill-card">
            <Stack gap="md" h="100%">
              <Group justify="space-between" wrap="wrap">
                <div>
                  <Text className="te-calling-section-label">Timeline</Text>
                  <Title order={4} c={ui.heading}>
                    Session activity
                  </Title>
                </div>
                <Timer size={16} color={ui.icon} />
              </Group>

              <SimpleGrid cols={2} spacing="sm">
                <Paper className="te-calling-inline-note" p="md" radius="xl">
                  <Text size="10px" tt="uppercase" fw={700} c={ui.label}>
                    SLA
                  </Text>
                  <Text fw={700} c={ui.heading}>
                    {task?.sla_breach ? "Breached" : "Within SLA"}
                  </Text>
                </Paper>
                <Paper className="te-calling-inline-note" p="md" radius="xl">
                  <Text size="10px" tt="uppercase" fw={700} c={ui.label}>
                    Last action
                  </Text>
                  <Text fw={700} c={ui.heading}>
                    {task?.last_action_at ? dayjs.unix(task.last_action_at).format("DD MMM HH:mm") : "No recent action"}
                  </Text>
                </Paper>
              </SimpleGrid>

              <ScrollArea className="te-subtle-scroll te-calling-scroll-fill">
                <Stack gap="sm">
                  {timelineItems.length ? (
                    timelineItems.map((event, idx) => (
                      <Paper key={`${event.ts}-${event.type}-${idx}`} className="te-timeline-row" p="md" radius="xl">
                        <Group justify="space-between" align="flex-start" wrap="nowrap">
                          <Stack gap={4}>
                            <Text fw={700} c={ui.heading}>
                              {humanizeSlug(event.type)}
                            </Text>
                            <Text size="sm" c={ui.body}>
                              {event.note && event.note !== "Not Set" ? event.note : "Workflow event recorded"}
                            </Text>
                          </Stack>
                          <Text size="xs" c={ui.muted} ta="right">
                            {event.ts ? dayjs.unix(event.ts).format("DD MMM HH:mm:ss") : "-"}
                          </Text>
                        </Group>
                      </Paper>
                    ))
                  ) : (
                    <Paper className="te-calling-inline-note" p="md" radius="xl">
                      <Text size="sm" c={ui.body}>
                        No session timeline yet. Start the call to stream workflow activity here.
                      </Text>
                    </Paper>
                  )}
                </Stack>
              </ScrollArea>
            </Stack>
          </Card>
        </div>
      </div>
    </Stack>
  );
}
