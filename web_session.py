import asyncio
import contextlib
import logging
import random
import re
import time
import unicodedata
import uuid
from datetime import date, datetime, timedelta
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Dict, Optional
from zoneinfo import ZoneInfo

from audio_io import FRAME_MS
from audio_utils import rms_energy
from config import get_env, get_env_bool
from logging_utils import log_event
from sarvam_llm_service import SarvamLLMService, SYSTEM_PROMPT
from sarvam_stt_service import SaarikaSTTService, Transcript
from sarvam_tts_service import BulbulTTSService
from websockets.exceptions import ConnectionClosed
from session_store import SessionStore
from pii import redact_pii
from workflow_engine import WorkflowEngine, WorkflowState
from audit_store import SQLiteAuditStore
from excel_sink import ExcelOutcomeSink
from actions import ActionRouter
from knowledge_store import SQLiteFTSKnowledgeStore
from strategy_engine import StrategyEngine
from compliance_engine import ComplianceEngine
from followup_service import FollowupService
from integrations.crm_adapter import CRMAdapter
from datetime_utils import (
    parse_date_from_text,
    parse_time_from_text,
    validate_callback_time,
    validate_ptp_date,
)

logger = logging.getLogger(__name__)

SendEvent = Callable[[dict], Awaitable[None]]
SendAudio = Callable[[bytes], Awaitable[None]]

_CONSENT_PROMPT = "This call may be recorded for quality. Do I have your consent to continue?"
_CONSENT_PROMPT_RE = re.compile(
    r"this call may be recorded for quality[\.\!\?]?\s*do i have your consent to continue[\.\!\?]?",
    flags=re.IGNORECASE,
)


@dataclass
class EmotionalState:
    """Track customer emotional state for empathetic responses."""
    stress_level: float = 0.0  # 0-1
    sentiment: str = "neutral"  # positive, negative, neutral
    consecutive_refusals: int = 0
    last_emotion_update: float = field(default_factory=time.time)


class EmotionAnalyzer:
    """Simple lexicon-based emotion detection for Indic languages."""
    
    STRESS_INDICATORS = {
        'high': ['urgent', 'legal', 'court', 'police', 'fraud', 'cheat', 'harassment', 
                 'pressure', 'force', 'threat', 'scam', 'fake', 'frustrated', 'angry',
                 'तंग', 'परेशान', 'गुस्सा', 'धमकी', 'cheating'],
        'medium': ['worry', 'concern', 'problem', 'difficult', 'struggle', 'tight',
                   'मुश्किल', 'पैसा नहीं', 'नौकरी गई'],
        'payment_willing': ['pay', 'will pay', 'by tomorrow', 'next week', 'salary',
                           'भरूंगा', 'दे दूंगा', 'ho jayega']
    }
    
    POSITIVE_SIGNALS = ['thank', 'understand', 'help', 'cooperate', 'clear', 'done',
                       'धन्यवाद', 'समझा', 'ठीक है', 'कर दूंगा']
    
    @classmethod
    def analyze(cls, text: str, current_state: EmotionalState) -> EmotionalState:
        """Analyze text and update emotional state."""
        t = text.lower()
        
        new_state = EmotionalState(
            stress_level=current_state.stress_level * 0.8,  # Decay
            sentiment=current_state.sentiment,
            consecutive_refusals=current_state.consecutive_refusals,
            last_emotion_update=time.time()
        )
        
        # Detect stress indicators
        high_stress = any(w in t for w in cls.STRESS_INDICATORS['high'])
        med_stress = any(w in t for w in cls.STRESS_INDICATORS['medium'])
        
        if high_stress:
            new_state.stress_level = min(1.0, new_state.stress_level + 0.4)
            new_state.sentiment = "negative"
            new_state.consecutive_refusals += 1
        elif med_stress:
            new_state.stress_level = min(1.0, new_state.stress_level + 0.2)
            new_state.sentiment = "negative"
        elif any(w in t for w in cls.STRESS_INDICATORS['payment_willing']):
            new_state.stress_level = max(0.0, new_state.stress_level - 0.3)
            new_state.sentiment = "positive"
            new_state.consecutive_refusals = 0
        elif any(w in t for w in cls.POSITIVE_SIGNALS):
            new_state.sentiment = "positive"
            new_state.consecutive_refusals = max(0, new_state.consecutive_refusals - 1)
        
        return new_state
    
    @classmethod
    def get_empathy_prompt(cls, state: EmotionalState) -> str:
        """Generate context-specific empathy instructions."""
        if state.stress_level > 0.7:
            return (
                "The customer is showing high stress/anger. CRITICAL: Acknowledge their "
                "concern first. Say 'I completely understand this is stressful' or similar. "
                "Then pause. Only then continue with solution. Do NOT rush to payment demand."
            )
        elif state.stress_level > 0.4:
            return (
                "Customer seems worried. Use reassuring tone. Acknowledge difficulty. "
                "Offer flexible options. Be patient and helpful."
            )
        elif state.consecutive_refusals >= 2:
            return (
                "Customer has refused multiple times. Do NOT repeat same request. "
                "Pivot to understanding their situation first. Ask 'What would work for you?'"
            )
        return ""


class WebCallSession:
    def __init__(
        self,
        stt_service: SaarikaSTTService,
        llm_service: SarvamLLMService,
        tts_ws_url: str,
        send_event: SendEvent,
        send_audio: SendAudio,
        tts_api_key: Optional[str] = None,
        tts_voice: Optional[str] = None,
        tts_model: Optional[str] = None,
        tts_speaker: Optional[str] = None,
        greeting_text: Optional[str] = None,
        max_history_turns: int = 10,
        session_store_path: Optional[str] = None,
        dynamic_stt_language: bool = False,
        preview_partials: bool = False,
        preview_after_ms: int = 600,
        llm_timeout_s: float = 20.0,
        tts_timeout_s: float = 20.0,
        stt_connect_timeout_s: float = 10.0,
        vad_rms_threshold: float = 500.0,
        vad_silence_ms: int = 600,
        stt_flush_interval_ms: int = 400,
        audio_queue_max: int = 100,
        log_partial_transcripts: bool = True,
        log_tokens: bool = False,
        log_audio_chunks: bool = False,
        use_sdk: bool = True,
        tts_stream_chunk_chars: int = 30,
        tts_stream_flush_punct: bool = True,
        tts_min_buffer_size: int = 50,
        tts_max_chunk_length: int = 150,
        tts_output_audio_codec: str = "linear16",
        tts_output_audio_bitrate: Optional[str] = None,
        tts_first_audio_timeout_s: float = 2.5,
        post_speech_pause_ms: int = 600,
        audit_store: Optional[SQLiteAuditStore] = None,
        excel_sink: Optional[ExcelOutcomeSink] = None,
        action_router: Optional[ActionRouter] = None,
        knowledge_store: Optional[SQLiteFTSKnowledgeStore] = None,
        session_registry: Optional[dict] = None,
        strategy_engine: Optional[StrategyEngine] = None,
        compliance_engine: Optional[ComplianceEngine] = None,
        followup_service: Optional[FollowupService] = None,
        crm_adapter: Optional[CRMAdapter] = None,
    ) -> None:
        self.stt = stt_service
        self.llm = llm_service
        self.tts_ws_url = tts_ws_url
        self.tts_api_key = tts_api_key
        self.tts_voice = tts_voice
        self.tts_model = tts_model
        self.tts_speaker = tts_speaker
        self.greeting_text = self._normalize_branding_text(greeting_text) if greeting_text else greeting_text
        # CHANGE: Conversation memory (history + optional persistence).
        self._max_history_turns = max(1, max_history_turns)
        self._chat_history = [{"role": "system", "content": SYSTEM_PROMPT}]
        self._session_id = uuid.uuid4().hex[:12]
        self._session_store = SessionStore(session_store_path, self._session_id) if session_store_path else None
        self._dynamic_stt_language = dynamic_stt_language
        self._pending_stt_language: Optional[str] = None
        self._last_detected_stt_lang: Optional[str] = None
        self._detected_stt_lang_streak: int = 0
        self._preview_partials = preview_partials
        self._preview_after_s = max(0, preview_after_ms) / 1000.0
        self._preview_active = False
        self._preview_suppressed_logged = False
        self._llm_timeout_s = llm_timeout_s
        self._tts_timeout_s = tts_timeout_s
        self._tts_first_audio_timeout_s = max(0.5, float(tts_first_audio_timeout_s))
        self._post_speech_pause_s = max(0.0, int(post_speech_pause_ms)) / 1000.0
        self._pending_final: Optional[tuple[str, Transcript, int]] = None
        self._finalize_task: Optional[asyncio.Task] = None
        self._last_speech_ts: float = 0.0  # Track when user last spoke
        self._generation_epoch: int = 0
        self._stt_connect_timeout_s = stt_connect_timeout_s
        self._use_sdk = use_sdk

        self.send_event = send_event
        self._send_audio = send_audio

        self._audio_in_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=audio_queue_max)
        self._audio_sender_task: Optional[asyncio.Task] = None
        self._stt_task: Optional[asyncio.Task] = None
        self._gen_task: Optional[asyncio.Task] = None
        self._cancel_event = asyncio.Event()

        self._tts_playing = asyncio.Event()
        self._tts_audio_received = asyncio.Event()
        self._tts_pending: bool = False
        # --- Barge-in / echo suppression guards ---
        # When testing on laptop speakers + mic, TTS audio can leak back into STT and trigger false barge-in.
        self._tts_start_ts: float = 0.0
        self._last_tts_end_ts: float = 0.0
        self._barge_in_grace_s: float = max(0.2, float(get_env("BARGE_IN_GRACE_S", "0.45") or 0.45))
        self._barge_in_min_speech_frames: int = max(
            2, int(get_env("BARGE_IN_MIN_SPEECH_FRAMES", "5") or 5)
        )
        self._vad_speech_frames: int = 0
        self._barge_in_armed: bool = False  # one-shot per assistant speech turn
        self._vad_barge_task: Optional[asyncio.Task] = None
        self._last_rms: float = 0.0
        self._segment_speech_frames: int = 0
        self._min_flush_speech_frames: int = max(
            1, int(get_env("STT_MIN_FLUSH_SPEECH_FRAMES", "2") or 2)
        )
        self._short_flush_skip_count: int = 0
        self._force_flush_segment_ms: int = max(
            250, int(get_env("STT_FORCE_FLUSH_SEGMENT_MS", "600") or 600)
        )
        self._force_flush_after_skips: int = max(
            1, int(get_env("STT_FORCE_FLUSH_AFTER_SKIPS", "1") or 1)
        )
        self._force_flush_no_final_s: float = max(
            2.0, float(get_env("STT_FORCE_FLUSH_NO_FINAL_S", "4.0") or 4.0)
        )
        self._last_assistant_text: str = ""
        self._pending_step_id: Optional[str] = None
        self._pending_turn_id: Optional[str] = None
        self._reply_to_step_id: Optional[str] = None
        self._reply_to_turn_id: Optional[str] = None
        self._pending_utterance_id: Optional[str] = None
        self._reply_to_utterance_id: Optional[str] = None
        self._current_utterance_id: Optional[str] = None
        self._current_utterance_status: str = "completed"
        self._utterance_seq: int = 0
        self._event_timeline: list = []
        self._event_timeline_max: int = 500
        self._last_event_ts_ms: int = 0
        self._use_timeline_history: bool = True
        # --- Thin policy state (prevents repeated questions / placeholder leakage) ---
        self._policy = {
            "asked": {
                "confirm_awareness": False,
                "confirm_identity": False,
                "ask_payment_made": False,
                "ask_ptp_date": False,
                "ask_utr": False,
            },
            "confirmed": {
                "awareness": False,
                "identity": False,
                "payment_made": None,
            },
            "pending_intent": None,
        }
        # Lightweight conversation memory for key facts (used to prevent повтор greetings / placeholders).
        self._facts: dict = {
            "customer_id": None,
            "campaign_id": None,
            "customer_name": None,
            "phone": None,
            "overdue_amount": None,
            "due_date": None,
            "ptp_date": None,
            "callback_time": None,
            "reference_number": None,
            "language_preference": None,
            "mentioned_family": False,
            "family_emergency": False,
            "job_loss_mentioned": False,
            "salary_date": None,
            "dpd": None,
            "risk_band": None,
        }
        self._has_greeted = False
        self._emotional_state = EmotionalState()
        self._last_backchannel_ts: float = 0.0
        self._drift_count: int = 0
        self._interrupted_response: str = ""
        self._interrupted_at: float = 0.0
        self._cancel_lock = asyncio.Lock()
        self._last_transcript_text = ""
        self._last_user_text: str = ""
        self._last_user_text_norm: str = ""
        self._last_assistant_text_norm: str = ""
        self._last_user_text_ts: float = 0.0
        self._last_assistant_text_ts: float = 0.0
        self._dedupe_window_s: float = 2.5
        self._last_persisted_ptp: Optional[str] = None
        self._last_persisted_callback: Optional[str] = None
        self._refusal_followup_emitted: bool = False

        # Demo integrations
        self._audit_store = audit_store
        self._excel_sink = excel_sink
        self._action_router = action_router
        self._knowledge_store = knowledge_store
        self._session_registry = session_registry
        self._strategy_engine = strategy_engine
        self._compliance_engine = compliance_engine
        self._followup_service = followup_service
        self._crm_adapter = crm_adapter
        self._compliance_flags: Dict[str, int] = {}
        self._log_redact_pii = get_env_bool("LOG_REDACT_PHI", True)
        self._greeting_started = False
        self._greeting_active = False
        self._turn_state: str = "IDLE"
        self._no_response_task: Optional[asyncio.Task] = None
        self._last_question_ts: float = 0.0
        self._last_clarify_ts: float = 0.0
        self._clarify_cooldown_s: float = max(0.5, float(get_env("CLARIFY_COOLDOWN_S", "2.0") or 2.0))

        # Deterministic workflow engine
        self._enable_advanced_workflow = get_env_bool("ENABLE_ADVANCED_WORKFLOW", True)
        self._workflow_max_retries = int(get_env("WORKFLOW_MAX_RETRIES", "2") or 2)
        self._workflow_tz = get_env("WORKFLOW_TZ", "Asia/Kolkata") or "Asia/Kolkata"
        self._ptp_min_days = int(get_env("PTP_MIN_DAYS", "0") or 0)
        self._ptp_max_days = int(get_env("PTP_MAX_DAYS", "30") or 30)
        self._callback_hours_start = int(get_env("CALLBACK_HOURS_START", "9") or 9)
        self._callback_hours_end = int(get_env("CALLBACK_HOURS_END", "20") or 20)
        self._wf = WorkflowEngine(
            enable_advanced=self._enable_advanced_workflow,
            max_retries=self._workflow_max_retries,
            tz=self._workflow_tz,
            ptp_min_days=self._ptp_min_days,
            ptp_max_days=self._ptp_max_days,
            callback_hours_start=self._callback_hours_start,
            callback_hours_end=self._callback_hours_end,
        )
        self._wf_state = WorkflowState()
        if not get_env_bool("ENABLE_CONSENT", True):
            self._wf_state.consent = True
        else:
            # For demos, make the very first spoken message include consent capture,
            # so the customer's first response can be interpreted deterministically.
            if self.greeting_text:
                self.greeting_text = self._ensure_consent_prompt_once(self.greeting_text.strip())
        self._set_workflow_step(reason="init")

        self._vad_threshold = vad_rms_threshold
        self._silence_frames_required = max(1, int(vad_silence_ms / FRAME_MS))
        self._silent_frames = 0
        self._in_silence = True
        self._stt_flush_interval = max(0, stt_flush_interval_ms) / 1000.0
        self._last_flush_ts = 0.0
        self._flush_min_gap_s = max(0.05, self._stt_flush_interval) if self._stt_flush_interval > 0 else 0.2
        self._last_partial_log_ts = 0.0
        self._log_partial_transcripts = log_partial_transcripts
        self._log_tokens = log_tokens
        self._log_audio_chunks = log_audio_chunks
        self._tts_stream_chunk_chars = max(1, tts_stream_chunk_chars)
        self._tts_stream_flush_punct = tts_stream_flush_punct
        self._tts_min_buffer_size = max(0, int(tts_min_buffer_size))
        self._tts_max_chunk_length = max(0, int(tts_max_chunk_length))
        self._tts_output_audio_codec = tts_output_audio_codec
        self._tts_output_audio_bitrate = tts_output_audio_bitrate
        self._last_activity_ts = time.time()
        self._cancel_no_response_watch()
        self._set_turn_state("USER_SPEAKING")
        self._last_audio_ts = 0.0
        self._last_stt_ts = time.time()
        self._last_stt_final_ts = time.time()
        self._last_speech_ts = 0.0  # Initialize to 0, will be set when speech detected
        self._audio_frames = 0
        self._audio_bytes = 0
        self._has_sent_audio = False
        self._current_llm_text = ""
        self._current_llm_token_count = 0
        self._watchdog_task: Optional[asyncio.Task] = None
        self._stt_reconnect_lock = asyncio.Lock()
        self._apply_context_language_to_stt = get_env_bool("STT_APPLY_CONTEXT_LANGUAGE", False)
        self._audio_drop_count = 0
        self._last_queue_log_ts = 0.0
        self._speech_start_ts: Optional[float] = None
        self._first_partial_logged = False
        self._turn_seq = 0
        self._current_turn_id: Optional[str] = None
        self._llm_start_ts: Optional[float] = None
        self._llm_first_token_ts: Optional[float] = None
        self._tts_first_chunk_ts: Optional[float] = None
        self._stt_partial_count = 0
        self._stt_final_count = 0
        self._expected_audio_bytes = int(self.stt.sample_rate * FRAME_MS / 1000) * 2

        if self._session_store:
            prior = self._session_store.load()
            if prior:
                self._chat_history = [{"role": "system", "content": SYSTEM_PROMPT}] + prior
                self._trim_history()
            # Load persisted state (facts and policy)
            saved_state = self._session_store.load_state()
            if saved_state:
                if "facts" in saved_state:
                    self._facts.update(saved_state["facts"])
                if "policy" in saved_state:
                    self._policy.update(saved_state["policy"])
                if "has_greeted" in saved_state:
                    self._has_greeted = saved_state["has_greeted"]
                log_event(
                    logger,
                    "state_loaded",
                    session_id=self._session_id,
                    facts=self._facts,
                    has_greeted=self._has_greeted,
                )

    async def start(self) -> None:
        try:
            # CHANGE: STT connect timeout for robustness.
            await asyncio.wait_for(self.stt.connect(), timeout=self._stt_connect_timeout_s)
        except Exception as exc:
            log_event(logger, "stt_connect_error", session_id=self._session_id, error=str(exc))
            await self.send_event({"type": "error", "message": "STT connection failed"})
            raise
        log_event(
            logger,
            "stt_connected",
            session_id=self._session_id,
            language=self.stt.language,
            language_param=self.stt.language_param_key,
            sample_rate=self.stt.sample_rate,
            audio_payload=self.stt.audio_payload_format,
            input_audio_codec=self.stt.input_audio_codec,
        )
        self._audio_sender_task = asyncio.create_task(self._audio_sender_loop(), name="audio_sender")
        self._stt_task = asyncio.create_task(self._stt_loop(), name="stt")
        self._watchdog_task = asyncio.create_task(self._watchdog_loop(), name="watchdog")
        log_event(
            logger,
            "session_start",
            session_id=self._session_id,
            stt_model=self.stt.model,
            llm_model=self.llm.model,
            tts_model=self.tts_model,
            tts_speaker=self.tts_speaker or self.tts_voice,
            vad_threshold=self._vad_threshold,
            vad_silence_ms=self._silence_frames_required * FRAME_MS,
            barge_in_grace_s=self._barge_in_grace_s,
            barge_in_min_speech_frames=self._barge_in_min_speech_frames,
            min_flush_speech_frames=self._min_flush_speech_frames,
        )
        await self.send_event({"type": "status", "state": "ready"})
        self._set_turn_state("IDLE")
        # Greeting is triggered after client "start" (so customer context is loaded first).

    async def start_greeting(self) -> None:
        if not self.greeting_text or self._greeting_started:
            return
        self._greeting_started = True
        self._greeting_active = True
        self._has_greeted = True
        # If no language preference has been set yet, default to the greeting
        # language so that the agent stays in English until the user explicitly
        # switches.  The greeting text is always English in the current config.
        if not self._facts.get("language_preference"):
            self._facts["language_preference"] = "en-IN"
        greeting = self._select_varied_greeting()
        asyncio.create_task(self._start_tts_only(greeting), name="greeting")

    async def stop(self) -> None:
        await self._cancel_generation()
        for task in [self._audio_sender_task, self._stt_task, self._watchdog_task]:
            if task and not task.done():
                task.cancel()
        for task in [self._audio_sender_task, self._stt_task, self._watchdog_task]:
            if task:
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        await self.stt.close()
        log_event(logger, "session_stop", session_id=self._session_id)

    async def handle_audio(self, pcm_bytes: bytes) -> None:
        if not pcm_bytes:
            return
        self._last_activity_ts = time.time()
        self._last_audio_ts = self._last_activity_ts
        if self._expected_audio_bytes and len(pcm_bytes) != self._expected_audio_bytes:
            log_event(
                logger,
                "audio_frame_size_mismatch",
                session_id=self._session_id,
                expected=self._expected_audio_bytes,
                actual=len(pcm_bytes),
            )
            if len(pcm_bytes) < self._expected_audio_bytes:
                pcm_bytes = pcm_bytes + b"\x00" * (self._expected_audio_bytes - len(pcm_bytes))
            else:
                pcm_bytes = pcm_bytes[: self._expected_audio_bytes]
        self._audio_frames += 1
        self._audio_bytes += len(pcm_bytes)
        rms = rms_energy(pcm_bytes)
        self._last_rms = rms
        if self._audio_frames == 1 or self._audio_frames % 50 == 0:
            log_event(
                logger,
                "audio_ingest",
                session_id=self._session_id,
                frames=self._audio_frames,
                bytes=self._audio_bytes,
                rms=round(rms, 2),
            )
        if rms < self._vad_threshold:
            self._silent_frames += 1
            self._vad_speech_frames = 0
            if self._silent_frames >= self._silence_frames_required:
                if not self._in_silence:
                    self._in_silence = True
                    self._cancel_vad_barge()
                    log_event(logger, "vad_speech_end", session_id=self._session_id, rms=round(rms, 2))
                    self._preview_active = False
                    # Notify UI that customer speech ended (frontend often relies on these for the listening block).
                    asyncio.create_task(
                        self.send_event({"type": "vad_speech_end"}),
                        name="evt_vad_end",
                    )
                    segment_duration_ms: Optional[int] = None
                    if self._speech_start_ts is not None:
                        segment_duration_ms = int((time.time() - self._speech_start_ts) * 1000)
                        log_event(
                            logger,
                            "vad_segment",
                            session_id=self._session_id,
                            duration_ms=segment_duration_ms,
                        )
                        self._speech_start_ts = None
                    await self._emit_timeline_event("user_speech_end")
                    if self._dynamic_stt_language and self._pending_stt_language:
                        await self._apply_language_update()
                    # Flush once on silence transition to finalize STT.
                    if self._should_flush_on_silence_transition(segment_duration_ms=segment_duration_ms):
                        now = time.time()
                        try:
                            await self.stt.flush()
                            self._last_flush_ts = now
                            self._short_flush_skip_count = 0
                            log_event(logger, "stt_flush", session_id=self._session_id, reason="silence")
                        except Exception as exc:
                            log_event(
                                logger,
                                "stt_flush_error",
                                session_id=self._session_id,
                                reason="silence",
                                error=str(exc),
                            )
                    elif self._segment_speech_frames > 0:
                        self._short_flush_skip_count += 1
                        log_event(
                            logger,
                            "stt_flush_skipped",
                            session_id=self._session_id,
                            reason="short_segment",
                            speech_frames=self._segment_speech_frames,
                            min_required=self._min_flush_speech_frames,
                            segment_duration_ms=segment_duration_ms,
                            skip_count=self._short_flush_skip_count,
                        )
                    self._segment_speech_frames = 0
        else:
            self._silent_frames = 0
            self._vad_speech_frames += 1
            self._segment_speech_frames += 1
            if self._in_silence:
                self._speech_start_ts = time.time()
                self._last_speech_ts = time.time()  # Update last speech timestamp
                self._first_partial_logged = False
                log_event(logger, "vad_speech_start", session_id=self._session_id, rms=round(rms, 2))
                self._cancel_no_response_watch()
                self._set_turn_state("USER_SPEAKING")
                # Bind this reply to the last pending question as soon as speech starts.
                self._freeze_reply_binding(reason="vad_speech_start")
                await self._emit_timeline_event("user_speech_start")
                if self._tts_playing.is_set() or self._tts_pending:
                    # Re-arm to allow STT-partial barge-in if user starts speaking.
                    self._barge_in_armed = True
                    # Schedule VAD-based barge-in after grace if speech continues.
                    self._schedule_vad_barge_in()
                # Notify UI that customer speech started.
                asyncio.create_task(
                    self.send_event({"type": "vad_speech_start"}),
                    name="evt_vad_start",
                )
                # Keep pending finalization alive for a brief period; the finalize loop
                # cancels only on sustained speech to avoid dropping valid transcripts.
                if self._finalize_task and not self._finalize_task.done():
                    log_event(
                        logger,
                        "finalize_pending_on_speech_start",
                        session_id=self._session_id,
                        reason="await_sustained_speech",
                    )
            self._in_silence = False
            self._last_speech_ts = time.time()  # Update on any speech activity
            # Hybrid barge-in: VAD triggers after grace; STT partials remain a second signal.
            if (
                (not getattr(self.stt, "use_sdk", False))
                and self._stt_flush_interval > 0
                and self._has_sent_audio
            ):
                now = time.time()
                if now - self._last_flush_ts >= self._stt_flush_interval:
                    self._last_flush_ts = now
                    try:
                        await self.stt.flush()
                        log_event(logger, "stt_flush", session_id=self._session_id, reason="interval")
                    except Exception as exc:
                        log_event(
                            logger,
                            "stt_flush_error",
                            session_id=self._session_id,
                            reason="interval",
                            error=str(exc),
                        )

        try:
            self._audio_in_queue.put_nowait(pcm_bytes)
        except asyncio.QueueFull:
            self._audio_drop_count += 1
            log_event(
                logger,
                "audio_drop",
                session_id=self._session_id,
                drops=self._audio_drop_count,
            )
            with contextlib.suppress(asyncio.QueueEmpty):
                _ = self._audio_in_queue.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                self._audio_in_queue.put_nowait(pcm_bytes)
        self._maybe_log_queue()


    async def handle_text(self, text: str, language: Optional[str] = None) -> None:
        """Handle a user/customer text message coming from the UI (typed input).

        This mirrors the behavior of receiving a final STT transcript.
        """
        t = (text or "").strip()
        if not t:
            return

        self._last_activity_ts = time.time()

        # If the assistant is currently speaking, treat typed text as barge-in.
        if self._tts_playing.is_set():
            await self._graceful_interrupt("typed")

        lang = self._resolve_output_language(language)

        # Show the typed message in the UI transcript stream.
        await self.send_event(
            {
                "type": "transcript",
                "text": t,
                "final": True,
                "language": lang,
                "confidence": None,
                "source": "typed",
            }
        )
        await self._emit_chat_message(role="user", text=t)

        # Update facts and generate an assistant response.
        self._last_user_text = t
        self._log_message(role="user", content=t)
        self._extract_facts_from_text(t)
        reply_step = self._pending_step_id or self._wf_state.last_agent_intent or self._wf_state.current_step
        requested_language = self._detect_language_switch_request(t)
        if requested_language:
            await self._handle_language_switch_request(
                requested_language=requested_language,
                bound_step=reply_step,
                source="typed",
            )
            return
        self._update_policy_from_user(t)
        self._wf.update_from_user(
            t,
            self._wf_state,
            extracted={
                "customer_name": self._facts.get("customer_name"),
                "ptp_date": self._facts.get("ptp_date"),
                "reference_number": self._facts.get("reference_number"),
                "callback_time": self._facts.get("callback_time"),
            },
            reply_to_step_id=reply_step,
        )
        self._sync_workflow_from_facts()
        self._persist_commitments()
        self._persist_state()  # Persist state after extracting facts
        self._preview_active = False
        await self._start_generation_from_text(user_text=t, language=lang, preview=False)


    async def set_context(self, ctx: dict) -> None:
        """Update session context/facts from the UI (e.g., customer profile fields)."""
        if not isinstance(ctx, dict):
            return

        # Accept a few common aliases from the frontend.
        mapping = {
            "customer_id": ["customer_id", "customerId", "id"],
            "campaign_id": ["campaign_id", "campaignId"],
            "customer_name": ["customer_name", "name", "customerName"],
            "phone": ["phone", "customer_phone", "customerPhone"],
            "overdue_amount": ["overdue_amount", "amount", "overdueAmount"],
            "due_date": ["due_date", "dueDate"],
            "ptp_date": ["ptp_date", "ptpDate"],
            "reference_number": ["reference_number", "reference", "utr", "referenceNumber"],
            "language_preference": ["language_preference", "language", "lang", "languagePreference"],
            "dpd": ["dpd", "days_past_due", "daysPastDue"],
            "risk_band": ["risk_band", "risk", "riskBand"],
        }

        updated = {}
        for key, aliases in mapping.items():
            for a in aliases:
                if a in ctx and ctx[a] not in (None, ""):
                    updated[key] = ctx[a]
                    break

        if updated.get("customer_id"):
            self._facts["customer_id"] = str(updated["customer_id"]).strip()
        if updated.get("campaign_id"):
            self._facts["campaign_id"] = str(updated["campaign_id"]).strip()
        if updated.get("customer_name"):
            self._facts["customer_name"] = str(updated["customer_name"]).strip()
        if updated.get("phone"):
            self._facts["phone"] = str(updated["phone"]).strip()
        if updated.get("overdue_amount"):
            self._facts["overdue_amount"] = str(updated["overdue_amount"]).strip().replace(",", "")
        if updated.get("due_date"):
            self._facts["due_date"] = str(updated["due_date"]).strip()
        if updated.get("ptp_date"):
            self._facts["ptp_date"] = str(updated["ptp_date"]).strip()
        if updated.get("reference_number"):
            self._facts["reference_number"] = str(updated["reference_number"]).strip()
        if updated.get("language_preference"):
            self._facts["language_preference"] = self._canonical_language_code(
                str(updated["language_preference"]).strip()
            )
        if updated.get("dpd") is not None:
            self._facts["dpd"] = updated.get("dpd")
        if updated.get("risk_band") is not None:
            self._facts["risk_band"] = updated.get("risk_band")

        # Optionally update STT language for subsequent audio, if dynamic language is enabled.
        if (
            self._dynamic_stt_language
            and self._apply_context_language_to_stt
            and self._facts.get("language_preference")
        ):
            self._pending_stt_language = self._facts.get("language_preference")
            if self._in_silence:
                await self._apply_language_update()

        self._persist_state()  # Persist state after context update
        await self.send_event({"type": "context_updated", "facts": updated})

        # Update deterministic workflow state from known context.
        if self._facts.get("customer_name"):
            # Known identity value lets us confirm faster, but we still ask the confirm question.
            pass

    def _maybe_log_queue(self) -> None:
        now = time.time()
        if now - self._last_queue_log_ts < 2.0:
            return
        self._last_queue_log_ts = now
        log_event(
            logger,
            "audio_queue",
            session_id=self._session_id,
            queued=self._audio_in_queue.qsize(),
            drops=self._audio_drop_count,
            frames=self._audio_frames,
            bytes=self._audio_bytes,
        )

    def _redact(self, text: str) -> str:
        return redact_pii(text) if self._log_redact_pii else text

    def _log_message(self, *, role: str, content: str) -> None:
        """Persist message to Excel + SQLite audit (redacted)."""
        content = (content or "").strip()
        if not content:
            return
        redacted = self._redact(content)
        if self._excel_sink:
            try:
                self._excel_sink.log_message(session_id=self._session_id, role=role, content_redacted=redacted)
            except Exception as exc:
                log_event(logger, "excel_log_message_error", session_id=self._session_id, error=str(exc))
        if self._audit_store:
            try:
                self._audit_store.record_event(
                    event_type="message",
                    session_id=self._session_id,
                    payload={"role": role, "content_redacted": redacted},
                )
            except Exception as exc:
                log_event(logger, "audit_log_message_error", session_id=self._session_id, error=str(exc))
        if role == "assistant" and self._compliance_engine and self._audit_store:
            try:
                violations = self._compliance_engine.evaluate_assistant_text(
                    text=content,
                    consent=self._wf_state.consent,
                    identity_confirmed=bool(self._wf_state.identity_confirmed),
                    current_step=self._wf_state.current_step,
                )
                for v in violations:
                    self._audit_store.record_compliance_violation(
                        session_id=self._session_id,
                        rule_code=v.rule_code,
                        severity=v.severity,
                        detail=v.detail,
                        excerpt=v.excerpt,
                    )
                    self._compliance_flags[v.rule_code] = int(self._compliance_flags.get(v.rule_code, 0)) + 1
            except Exception as exc:
                log_event(logger, "compliance_eval_error", session_id=self._session_id, error=str(exc))
        if self._session_registry is not None:
            try:
                self._session_registry[self._session_id] = self.get_snapshot()
            except Exception as exc:
                log_event(logger, "session_registry_update_error", session_id=self._session_id, error=str(exc))

    async def _emit_chat_message(self, *, role: str, text: str) -> None:
        """Send canonical chat message event to the UI."""
        # Disabled: UI now relies on transcript (user) + assistant_final (agent) only.
        return

    def _set_turn_state(self, state: str) -> None:
        self._turn_state = state

    async def _start_fixed_turn(
        self,
        *,
        assistant_text: str,
        language: Optional[str],
        step: str,
        update_workflow: bool = True,
        schedule_no_response: bool = True,
    ) -> None:
        """Preempt any current generation and start a deterministic TTS turn."""
        async with self._cancel_lock:
            await self._cancel_generation_locked()
            self._cancel_no_response_watch()
            self._turn_seq += 1
            self._current_turn_id = f"turn-{self._turn_seq}"
            # Fixed turns don't use LLM, but we still record start time for latency logs.
            self._llm_start_ts = time.time()
            self._llm_first_token_ts = None
            self._tts_first_chunk_ts = None
            self._gen_task = asyncio.create_task(
                self._run_fixed_turn(
                    assistant_text=assistant_text,
                    language=language,
                    step=step,
                    update_workflow=update_workflow,
                    schedule_no_response=schedule_no_response,
                ),
                name=f"fixed_{step}",
            )

    def _log_workflow_transition(self, *, from_step: str, to_step: str, reason: str) -> None:
        log_event(
            logger,
            "workflow_transition",
            session_id=self._session_id,
            from_step=from_step,
            to_step=to_step,
            reason=reason,
            disposition=self._wf_state.disposition,
            attempts=self._wf_state.attempts,
        )

    def _set_workflow_step(self, *, reason: str) -> str:
        prev = self._wf_state.current_step
        next_step = self._wf.compute_next_step(self._wf_state)
        if next_step != prev:
            self._wf_state.current_step = next_step
            self._log_workflow_transition(from_step=prev, to_step=next_step, reason=reason)
        else:
            self._wf_state.current_step = next_step
        # Emit workflow update to frontend for live progress tracking
        self._emit_workflow_update()
        return next_step

    def _emit_workflow_update(self) -> None:
        """Send workflow state to frontend for live UI updates."""
        try:
            state_dict = self._wf_state.to_dict()
            asyncio.get_event_loop().create_task(
                self.send_event({
                    "type": "workflow_update",
                    "state": state_dict,
                })
            )
        except Exception:
            pass

    def _set_pending_step(self, step: Optional[str]) -> None:
        if not step:
            return
        if hasattr(self._wf, "STEPS") and step not in self._wf.STEPS:
            return
        self._pending_step_id = step
        self._pending_turn_id = self._current_turn_id
        if self._current_utterance_id:
            self._pending_utterance_id = self._current_utterance_id

    def _next_utterance_id(self) -> str:
        self._utterance_seq += 1
        return f"utt-{self._utterance_seq}"

    def _event_ts_ms(self) -> int:
        ts = int(time.time() * 1000)
        if ts <= self._last_event_ts_ms:
            ts = self._last_event_ts_ms + 1
        self._last_event_ts_ms = ts
        return ts

    async def _emit_timeline_event(self, event_type: str, **payload) -> None:
        ts = self._event_ts_ms()
        event = {"type": event_type, "ts": ts, **payload}
        self._event_timeline.append(event)
        if len(self._event_timeline) > self._event_timeline_max:
            self._event_timeline = self._event_timeline[-self._event_timeline_max :]
        try:
            await self.send_event(event)
        except Exception:
            pass

    def _freeze_reply_binding(self, *, reason: str) -> None:
        if self._reply_to_step_id is not None:
            return
        step = self._pending_step_id or self._wf_state.last_agent_intent or self._wf_state.current_step
        if not step:
            return
        self._reply_to_step_id = step
        self._reply_to_turn_id = self._pending_turn_id
        self._reply_to_utterance_id = self._pending_utterance_id
        log_event(
            logger,
            "reply_binding",
            session_id=self._session_id,
            reason=reason,
            step=step,
            turn_id=self._reply_to_turn_id,
        )

    def _cancel_vad_barge(self) -> None:
        if self._vad_barge_task and not self._vad_barge_task.done():
            self._vad_barge_task.cancel()
        self._vad_barge_task = None

    def _schedule_vad_barge_in(self) -> None:
        self._cancel_vad_barge()
        self._vad_barge_task = asyncio.create_task(self._vad_barge_in_after_grace(), name="vad_barge_in")

    async def _vad_barge_in_after_grace(self) -> None:
        try:
            await asyncio.sleep(max(self._barge_in_grace_s, 0.05))
            if self._in_silence:
                return
            if not (self._tts_playing.is_set() or self._tts_pending):
                return
            if self._barge_in_armed and self._should_barge_in_from_vad():
                self._barge_in_armed = False
                self._freeze_reply_binding(reason="vad")
                await self._graceful_interrupt("vad")
        except asyncio.CancelledError:
            return

    def _cancel_no_response_watch(self) -> None:
        if self._no_response_task and not self._no_response_task.done():
            self._no_response_task.cancel()
        self._no_response_task = None

    def _schedule_no_response_watch(self) -> None:
        self._cancel_no_response_watch()
        self._last_question_ts = time.time()
        self._no_response_task = asyncio.create_task(self._no_response_loop(), name="no_response_watch")

    async def _no_response_loop(self) -> None:
        try:
            await asyncio.sleep(8.0)
            # If user spoke or agent is speaking, skip reprompt.
            if self._last_speech_ts > self._last_question_ts or self._tts_playing.is_set():
                return
            self._last_question_ts = time.time()
            await self._run_fixed_turn(
                assistant_text="Just checking—are you still there?",
                language=self._facts.get("language_preference"),
                step="reprompt",
                update_workflow=False,
                schedule_no_response=False,
            )
            await asyncio.sleep(8.0)
            if self._last_speech_ts > self._last_question_ts or self._tts_playing.is_set():
                return
            await self._run_fixed_turn(
                assistant_text="I’ll call back later. Thank you.",
                language=self._facts.get("language_preference"),
                step="no_response_end",
                update_workflow=False,
                schedule_no_response=False,
            )
        except asyncio.CancelledError:
            return

    def _persist_commitments(self) -> None:
        """Persist PTP/callback changes to Excel + audit."""
        ptp = self._facts.get("ptp_date")
        cb = self._facts.get("callback_time")
        if ptp == self._last_persisted_ptp and cb == self._last_persisted_callback:
            return
        # Only persist when something exists.
        if not ptp and not cb:
            return
        self._last_persisted_ptp = ptp
        self._last_persisted_callback = cb
        if self._excel_sink:
            try:
                self._excel_sink.upsert_call(
                    session_id=self._session_id,
                    customer_id=str(self._facts.get("customer_id") or "") or None,
                    disposition=self._wf_state.disposition,
                    ptp_date=ptp,
                    callback_time=cb,
                )
            except Exception as exc:
                log_event(logger, "excel_commitment_persist_error", session_id=self._session_id, error=str(exc))
        if self._audit_store:
            try:
                self._audit_store.upsert_outcome(
                    session_id=self._session_id,
                    customer_id=str(self._facts.get("customer_id") or "") or None,
                    campaign_id=str(self._facts.get("campaign_id") or "") or None,
                    dpd_bucket=(self._get_strategy_decision().dpd_bucket if self._get_strategy_decision() else None),
                    disposition=self._wf_state.disposition,
                    ptp_date=ptp,
                    callback_time=cb,
                )
            except Exception as exc:
                log_event(logger, "audit_commitment_persist_error", session_id=self._session_id, error=str(exc))
        if self._crm_adapter and (ptp or cb):
            try:
                self._crm_adapter.enqueue_outcome(
                    session_id=self._session_id,
                    event_type="commitment_update",
                    payload={
                        "session_id": self._session_id,
                        "customer_id": self._facts.get("customer_id"),
                        "campaign_id": self._facts.get("campaign_id"),
                        "ptp_date": ptp,
                        "callback_time": cb,
                        "disposition": self._wf_state.disposition,
                    },
                )
            except Exception as exc:
                log_event(logger, "crm_enqueue_commitment_error", session_id=self._session_id, error=str(exc))

    def _sync_workflow_from_facts(self) -> None:
        if self._facts.get("ptp_date"):
            normalized_ptp = self._normalize_ptp_text(str(self._facts.get("ptp_date")))
            if normalized_ptp:
                self._facts["ptp_date"] = normalized_ptp
                self._wf_state.ptp_date = normalized_ptp
        elif self._wf_state.ptp_date:
            normalized_ptp = self._normalize_ptp_text(str(self._wf_state.ptp_date))
            if normalized_ptp:
                self._wf_state.ptp_date = normalized_ptp
                self._facts["ptp_date"] = normalized_ptp

        if self._facts.get("callback_time"):
            normalized_callback = self._normalize_callback_text(str(self._facts.get("callback_time")))
            if normalized_callback:
                self._facts["callback_time"] = normalized_callback
                self._wf_state.callback_time = normalized_callback
        elif self._wf_state.callback_time:
            normalized_callback = self._normalize_callback_text(str(self._wf_state.callback_time))
            if normalized_callback:
                self._wf_state.callback_time = normalized_callback
                self._facts["callback_time"] = normalized_callback

        if self._facts.get("reference_number"):
            self._wf_state.reference_number = self._facts.get("reference_number")

    def _canonical_language_code(self, language: Optional[str]) -> Optional[str]:
        raw = (language or "").strip()
        if not raw:
            return None
        norm = unicodedata.normalize("NFKC", raw).casefold()
        mapping = {
            "hi": "hi-IN",
            "hi-in": "hi-IN",
            "hindi": "hi-IN",
            "hinglish": "hi-IN",
            "en": "en-IN",
            "en-in": "en-IN",
            "english": "en-IN",
            "ta": "ta-IN",
            "ta-in": "ta-IN",
            "tamil": "ta-IN",
            "tamizh": "ta-IN",
            "te": "te-IN",
            "te-in": "te-IN",
            "telugu": "te-IN",
            "kn": "kn-IN",
            "kn-in": "kn-IN",
            "kannada": "kn-IN",
            "ml": "ml-IN",
            "ml-in": "ml-IN",
            "malayalam": "ml-IN",
            "bn": "bn-IN",
            "bn-in": "bn-IN",
            "bengali": "bn-IN",
            "bangla": "bn-IN",
            "mr": "mr-IN",
            "mr-in": "mr-IN",
            "marathi": "mr-IN",
            "gu": "gu-IN",
            "gu-in": "gu-IN",
            "gujarati": "gu-IN",
            "pa": "pa-IN",
            "pa-in": "pa-IN",
            "punjabi": "pa-IN",
            "or": "or-IN",
            "or-in": "or-IN",
            "od": "or-IN",
            "od-in": "or-IN",
            "odia": "or-IN",
            "oriya": "or-IN",
        }
        if norm in mapping:
            return mapping[norm]
        return raw

    def _language_name(self, language: Optional[str]) -> str:
        code = self._canonical_language_code(language) or "en-IN"
        names = {
            "en-IN": "English",
            "hi-IN": "Hindi",
            "ta-IN": "Tamil",
            "te-IN": "Telugu",
            "kn-IN": "Kannada",
            "ml-IN": "Malayalam",
            "bn-IN": "Bengali",
            "mr-IN": "Marathi",
            "gu-IN": "Gujarati",
            "pa-IN": "Punjabi",
            "or-IN": "Odia",
        }
        return names.get(code, code)

    def _supports_fixed_language(self, language: Optional[str]) -> bool:
        code = self._canonical_language_code(language)
        return code in {"en-IN", "hi-IN"}

    def _contains_native_script(self, text: str, language: Optional[str]) -> bool:
        code = self._canonical_language_code(language)
        if not code or not text:
            return False
        script_patterns = {
            "hi-IN": r"[\u0900-\u097f]",
            "ta-IN": r"[\u0b80-\u0bff]",
            "te-IN": r"[\u0c00-\u0c7f]",
            "kn-IN": r"[\u0c80-\u0cff]",
            "ml-IN": r"[\u0d00-\u0d7f]",
            "bn-IN": r"[\u0980-\u09ff]",
            "mr-IN": r"[\u0900-\u097f]",
            "gu-IN": r"[\u0a80-\u0aff]",
            "pa-IN": r"[\u0a00-\u0a7f]",
            "or-IN": r"[\u0b00-\u0b7f]",
        }
        patt = script_patterns.get(code)
        return bool(patt and re.search(patt, text))

    def _is_language_auto_align_candidate(
        self,
        *,
        detected_language: Optional[str],
        text: str,
        current_preference: Optional[str],
    ) -> bool:
        detected = self._canonical_language_code(detected_language)
        current = self._canonical_language_code(current_preference)
        if not detected:
            return False
        # When no preference is set yet, require stronger evidence before switching:
        # either 2+ consecutive detections in the same language, or native script
        # in a substantive (>3 token) utterance.
        if current is None:
            token_count = len(text.strip().split())
            if token_count <= 3 and self._detected_stt_lang_streak < 2:
                return False
            if self._contains_native_script(text, detected) and token_count > 3:
                return True
            return self._detected_stt_lang_streak >= 2
        if detected == current:
            return False
        # For switching away from an established preference, require native script
        # or a streak of 2+ consecutive detections in the new language.
        if self._contains_native_script(text, detected):
            return True
        return self._detected_stt_lang_streak >= 2

    def _resolve_output_language(self, fallback: Optional[str] = None) -> Optional[str]:
        preferred = self._canonical_language_code(self._facts.get("language_preference"))
        if preferred:
            return preferred
        fallback_lang = self._canonical_language_code(fallback)
        if fallback_lang:
            return fallback_lang
        return self._canonical_language_code(getattr(self.stt, "language", None))

    def _detect_language_switch_request(self, text: str) -> Optional[str]:
        raw = unicodedata.normalize("NFKC", (text or "")).casefold().strip()
        if not raw:
            return None
        t = re.sub(r"[^\w\s]", " ", raw, flags=re.UNICODE)
        t = t.replace("_", " ")
        t = " ".join(t.split())
        if not t:
            return None

        hi_direct = (
            "hindi",
            "hinglish",
            "हिंदी",
            "हिन्दी",
            "english nahi samajh",
            "english nahin samajh",
            "don t understand english",
            "do not understand english",
            "cannot understand english",
            "aapki english nahi samajh",
            "aapki english nahin samajh",
            "hindi me baat",
            "hindi mein baat",
            "speak in hindi",
            "talk in hindi",
        )
        en_direct = (
            "english",
            "अंग्रेजी",
            "इंग्लिश",
            "hindi nahi samajh",
            "hindi nahin samajh",
            "don t understand hindi",
            "do not understand hindi",
            "cannot understand hindi",
            "english me baat",
            "english mein baat",
            "angrezi mein baat",
            "angrezi me baat",
            "speak in english",
            "talk in english",
        )
        if any(p in t for p in hi_direct):
            return "hi-IN"
        if any(p in t for p in en_direct):
            return "en-IN"

        language_keywords = {
            "hi-IN": ("hindi", "hinglish", "हिंदी", "हिन्दी"),
            "en-IN": ("english", "अंग्रेजी", "इंग्लिश"),
            "ta-IN": ("tamil", "tamizh", "தமிழ்"),
            "te-IN": ("telugu", "తెలుగు"),
            "kn-IN": ("kannada", "ಕನ್ನಡ"),
            "ml-IN": ("malayalam", "മലയാളം"),
            "bn-IN": ("bengali", "bangla", "বাংলা"),
            "mr-IN": ("marathi", "मराठी"),
            "gu-IN": ("gujarati", "ગુજરાતી"),
            "pa-IN": ("punjabi", "ਪੰਜਾਬੀ"),
            "or-IN": ("odia", "oriya", "ଓଡ଼ିଆ"),
        }
        switch_markers = (
            "speak",
            "talk",
            "language",
            "switch",
            "in ",
            "mein",
            "me",
            "bol",
            "bhasha",
            "understand",
            "समझ",
            "பேச",
            "ಕನ್ನಡ",
            "తెలుగు",
            "മലയാളം",
        )
        for code, keys in language_keywords.items():
            if any(k in t for k in keys) and any(marker in t for marker in switch_markers):
                return code
        return None

    def _language_switch_ack(self, language: Optional[str]) -> str:
        lang = self._canonical_language_code(language)
        if lang and lang.lower().startswith("hi"):
            return "ज़रूर, मैं हिंदी में बात करती हूँ।"
        if lang and lang.lower().startswith("ta"):
            return "சரி, நான் தமிழில் தொடர்கிறேன்."
        if lang and lang.lower().startswith("en"):
            return "Sure, I can continue in English."
        return f"Sure, I can continue in {self._language_name(lang)}."

    def _clarify_prompt(self, language: Optional[str]) -> str:
        lang = self._canonical_language_code(language)
        if lang and lang.lower().startswith("hi"):
            return "माफ़ कीजिए, मुझे ठीक से सुनाई नहीं दिया। क्या आप दोबारा बता सकते हैं?"
        return "Sorry, I didn’t catch that. Could you repeat?"

    async def _handle_language_switch_request(
        self,
        *,
        requested_language: str,
        bound_step: Optional[str],
        source: str,
    ) -> None:
        target_lang = self._canonical_language_code(requested_language) or "en-IN"
        previous_lang = self._resolve_output_language()
        self._facts["language_preference"] = target_lang

        log_event(
            logger,
            "language_switch_requested",
            session_id=self._session_id,
            source=source,
            requested_language=target_lang,
            previous_language=previous_lang,
            bound_step=bound_step,
        )

        # Explicit user language request should always switch STT for subsequent speech.
        self._pending_stt_language = target_lang
        if self._in_silence:
            await self._apply_language_update()

        step = (
            bound_step
            or self._pending_step_id
            or self._wf_state.last_agent_intent
            or self._wf_state.current_step
            or "consent"
        )
        if hasattr(self._wf, "STEPS") and step not in self._wf.STEPS:
            step = self._wf_state.current_step or "consent"

        ack = self._language_switch_ack(target_lang)
        if self._supports_fixed_language(target_lang):
            prompt = self._fixed_prompt_for_step(step, language=target_lang)
            assistant_text = f"{ack} {prompt}".strip()
            await self._start_fixed_turn(
                assistant_text=assistant_text,
                language=target_lang,
                step=step,
                update_workflow=False,
            )
        else:
            followup = (
                f"{ack} Continue in {self._language_name(target_lang)} and ask only the required "
                f"{step} question in that language."
            )
            await self._start_generation_from_text(
                user_text=followup,
                language=target_lang,
                preview=False,
            )
        self._persist_state()

    def _normalize_ptp_text(self, text: str) -> Optional[str]:
        parsed = parse_date_from_text(text or "", tz=self._workflow_tz)
        if not parsed:
            return None
        if self._enable_advanced_workflow and not validate_ptp_date(
            parsed,
            tz=self._workflow_tz,
            min_days=self._ptp_min_days,
            max_days=self._ptp_max_days,
        ):
            return None
        return parsed

    def _normalize_callback_text(self, text: str) -> Optional[str]:
        parsed = parse_time_from_text(text or "")
        if not parsed:
            return None
        if self._enable_advanced_workflow and not validate_callback_time(
            parsed,
            start_hour=self._callback_hours_start,
            end_hour=self._callback_hours_end,
        ):
            return None
        return parsed

    def _ptp_label_for_speech(self, value: Optional[str], language: Optional[str]) -> Optional[str]:
        raw = (value or "").strip()
        if not raw:
            return None
        normalized = self._normalize_ptp_text(raw)
        if not normalized:
            return raw
        try:
            due = date.fromisoformat(normalized)
            today = datetime.now(ZoneInfo(self._workflow_tz)).date()
            delta_days = (due - today).days
        except Exception:
            return normalized

        lang = self._canonical_language_code(language)
        if lang and lang.lower().startswith("hi"):
            if delta_days == 0:
                return "आज"
            if delta_days == 1:
                return "कल"
            if delta_days == 2:
                return "परसों"
        else:
            if delta_days == 0:
                return "today"
            if delta_days == 1:
                return "tomorrow"
            if delta_days == 2:
                return "day after tomorrow"
        return normalized

    async def _maybe_handle_retry_exceeded_refusal_close(self) -> None:
        """Emit follow-up signal for retry-exceeded hard/soft refusal closes."""
        if self._refusal_followup_emitted:
            return
        if self._wf_state.current_step != "closing":
            return
        if self._wf_state.last_transition_reason != "retry_exceeded":
            return
        if not self._wf_state.refusal_detected:
            return
        if self._wf_state.disposition != "refusal_unresolved":
            return

        self._refusal_followup_emitted = True
        log_event(
            logger,
            "retry_exceeded_refusal_close",
            session_id=self._session_id,
            refusal_strength=self._wf_state.refusal_strength,
            refusal_reason=self._wf_state.refusal_reason,
            no_count=self._wf_state.no_count,
        )
        with contextlib.suppress(Exception):
            await self.send_event(
                {
                    "type": "supervisor_update",
                    "follow_up": "refusal_retry_exceeded",
                    "disposition": self._wf_state.disposition,
                    "refusal_strength": self._wf_state.refusal_strength,
                    "refusal_reason": self._wf_state.refusal_reason,
                }
            )

        if self._action_router:
            try:
                result = self._action_router.escalate_ticket(
                    session_id=self._session_id,
                    customer_id=str(self._facts.get("customer_id") or "") or None,
                    category="collections_refusal",
                    reason="retry_exceeded_without_commitment",
                    last_user_text=self._last_user_text,
                    last_assistant_text=self._last_assistant_text,
                )
                log_event(
                    logger,
                    "retry_exceeded_refusal_escalated",
                    session_id=self._session_id,
                    ticket_id=result.get("ticket_id"),
                )
            except Exception as exc:
                log_event(
                    logger,
                    "retry_exceeded_refusal_escalation_failed",
                    session_id=self._session_id,
                    error=str(exc),
                )


    def get_snapshot(self) -> dict:
        """Safe-ish session snapshot for supervisor/demo views."""
        strategy = self._get_strategy_decision()
        return {
            "session_id": self._session_id,
            "customer_id": self._facts.get("customer_id"),
            "campaign_id": self._facts.get("campaign_id"),
            "customer_name": self._facts.get("customer_name"),
            "phone": self._facts.get("phone"),
            "current_step": self._wf_state.current_step,
            "consent": self._wf_state.consent,
            "identity_confirmed": self._wf_state.identity_confirmed,
            "awareness_confirmed": self._wf_state.awareness_confirmed,
            "payment_made": self._wf_state.payment_made,
            "ptp_date": self._wf_state.ptp_date,
            "callback_time": self._wf_state.callback_time,
            "reference_number": self._wf_state.reference_number,
            "disposition": self._wf_state.disposition,
            "dnd_requested": self._wf_state.dnd_requested,
            "wrong_party": self._wf_state.wrong_party,
            "attempts": self._wf_state.attempts,
            "hardship_detected": self._wf_state.hardship_detected,
            "refusal_detected": self._wf_state.refusal_detected,
            "refusal_strength": self._wf_state.refusal_strength,
            "refusal_reason": self._wf_state.refusal_reason,
            "no_count": self._wf_state.no_count,
            "stress": round(float(self._emotional_state.stress_level), 3),
            "sentiment": self._emotional_state.sentiment,
            "last_user_text": self._redact(self._last_user_text) if self._last_user_text else "",
            "last_assistant_text": self._redact(self._last_assistant_text) if self._last_assistant_text else "",
            "last_activity_ts": round(float(self._last_activity_ts), 3),
            "dpd_bucket": strategy.dpd_bucket if strategy else None,
            "strategy_mode": strategy.strategy_mode if strategy else None,
            "tone_profile": strategy.tone_profile if strategy else None,
            "compliance_flags": dict(self._compliance_flags),
        }

    def get_timeline(self) -> list:
        return list(self._event_timeline)

    async def handle_action(self, *, name: str, payload: dict) -> dict:
        """Handle UI-triggered demo workflow actions."""
        if not self._action_router:
            raise RuntimeError("Action router not configured")
        name = (name or "").strip()
        payload = payload or {}

        if name == "send_payment_link":
            channel = str(payload.get("channel") or "whatsapp")
            amount = str(payload.get("amount") or self._facts.get("overdue_amount") or "").strip() or None
            phone = str(payload.get("customer_phone") or self._facts.get("phone") or "").strip() or None
            customer_id = str(payload.get("customer_id") or self._facts.get("customer_id") or "").strip() or None
            result = self._action_router.send_payment_link(
                session_id=self._session_id,
                customer_id=customer_id,
                customer_phone=phone,
                amount=amount,
                channel=channel,
            )
            if self._excel_sink:
                try:
                    self._excel_sink.log_action(session_id=self._session_id, action_name=name, payload=payload, result=result, ok=True)
                    self._excel_sink.log_outbox(session_id=self._session_id, channel=channel, to=phone or "", body=result.get("body") or "", link=result.get("link") or "")
                except Exception:
                    pass
            if self._audit_store:
                try:
                    self._audit_store.record_event(event_type="action", session_id=self._session_id, payload={"name": name, "payload": payload, "result": result, "ok": True})
                except Exception:
                    pass
            if self._session_registry is not None:
                try:
                    self._session_registry[self._session_id] = self.get_snapshot()
                except Exception:
                    pass
            return result

        if name == "save_ptp_or_callback":
            ptp_date = payload.get("ptp_date")
            callback_time = payload.get("callback_time")
            if ptp_date:
                self._wf_state.ptp_date = str(ptp_date)
                self._facts["ptp_date"] = str(ptp_date)
            if callback_time:
                self._wf_state.callback_time = str(callback_time)
            self._set_workflow_step(reason="save_ptp_or_callback")

            customer_id = str(self._facts.get("customer_id") or "") or None
            if self._excel_sink:
                try:
                    self._excel_sink.upsert_call(
                        session_id=self._session_id,
                        customer_id=customer_id,
                        disposition=self._wf_state.disposition,
                        ptp_date=self._wf_state.ptp_date,
                        callback_time=self._wf_state.callback_time,
                    )
                    self._excel_sink.log_action(session_id=self._session_id, action_name=name, payload=payload, result={"ok": True}, ok=True)
                except Exception:
                    pass
            if self._audit_store:
                try:
                    self._audit_store.upsert_outcome(
                        session_id=self._session_id,
                        customer_id=customer_id,
                        campaign_id=str(self._facts.get("campaign_id") or "") or None,
                        dpd_bucket=(self._get_strategy_decision().dpd_bucket if self._get_strategy_decision() else None),
                        ptp_date=self._wf_state.ptp_date,
                        callback_time=self._wf_state.callback_time,
                        disposition=self._wf_state.disposition,
                    )
                    self._audit_store.record_event(event_type="action", session_id=self._session_id, payload={"name": name, "payload": payload, "result": {"ok": True}, "ok": True})
                except Exception:
                    pass
            auto_link = None
            auto_followups = []
            auto_send_link = bool(payload.get("auto_send_link", True))
            if auto_send_link and self._wf_state.ptp_date and self._action_router:
                try:
                    auto_link = await self.handle_action(
                        name="send_payment_link",
                        payload={
                            "channel": payload.get("channel") or "whatsapp",
                            "amount": payload.get("amount") or self._facts.get("overdue_amount"),
                            "customer_phone": payload.get("customer_phone") or self._facts.get("phone"),
                            "customer_id": payload.get("customer_id") or self._facts.get("customer_id"),
                        },
                    )
                except Exception as exc:
                    log_event(logger, "auto_send_link_error", session_id=self._session_id, error=str(exc))
            if self._followup_service and self._wf_state.ptp_date:
                try:
                    auto_followups = self._followup_service.schedule_ptp_followups(
                        session_id=self._session_id,
                        customer_id=customer_id,
                        ptp_date=str(self._wf_state.ptp_date),
                        phone=str(self._facts.get("phone") or ""),
                        channel=str(payload.get("channel") or "whatsapp"),
                    )
                    if self._audit_store and auto_followups:
                        self._audit_store.record_event(
                            event_type="followup_scheduled",
                            session_id=self._session_id,
                            payload={"items": auto_followups},
                        )
                except Exception as exc:
                    log_event(logger, "followup_schedule_error", session_id=self._session_id, error=str(exc))
            if self._crm_adapter:
                try:
                    self._crm_adapter.enqueue_outcome(
                        session_id=self._session_id,
                        event_type="ptp_saved",
                        payload={
                            "session_id": self._session_id,
                            "customer_id": customer_id,
                            "campaign_id": self._facts.get("campaign_id"),
                            "ptp_date": self._wf_state.ptp_date,
                            "callback_time": self._wf_state.callback_time,
                        },
                    )
                except Exception as exc:
                    log_event(logger, "crm_enqueue_ptp_error", session_id=self._session_id, error=str(exc))
            return {
                "ok": True,
                "ptp_date": self._wf_state.ptp_date,
                "callback_time": self._wf_state.callback_time,
                "payment_link": auto_link,
                "followups": auto_followups,
            }

        if name == "escalate_ticket":
            category = str(payload.get("category") or "customer_issue")
            reason = str(payload.get("reason") or "requested escalation")
            customer_id = str(payload.get("customer_id") or self._facts.get("customer_id") or "") or None
            result = self._action_router.escalate_ticket(
                session_id=self._session_id,
                customer_id=customer_id,
                category=category,
                reason=reason,
                last_user_text=self._last_user_text,
                last_assistant_text=self._last_assistant_text,
            )
            if self._excel_sink:
                try:
                    self._excel_sink.append_row(
                        "Tickets",
                        {
                            "ts": result.get("ts"),
                            "session_id": self._session_id,
                            "customer_id": customer_id,
                            "category": category,
                            "reason": reason,
                            "summary": self._redact(result.get("summary") or ""),
                            "status": result.get("status"),
                        },
                    )
                    self._excel_sink.log_action(session_id=self._session_id, action_name=name, payload=payload, result=result, ok=True)
                except Exception:
                    pass
            if self._audit_store:
                try:
                    self._audit_store.upsert_outcome(
                        session_id=self._session_id,
                        customer_id=customer_id,
                        campaign_id=str(self._facts.get("campaign_id") or "") or None,
                        dpd_bucket=(self._get_strategy_decision().dpd_bucket if self._get_strategy_decision() else None),
                        escalations_inc=1,
                    )
                    self._audit_store.record_event(event_type="action", session_id=self._session_id, payload={"name": name, "payload": payload, "result": result, "ok": True})
                except Exception:
                    pass
            if self._crm_adapter:
                try:
                    self._crm_adapter.enqueue_outcome(
                        session_id=self._session_id,
                        event_type="escalation",
                        payload=result,
                    )
                except Exception as exc:
                    log_event(logger, "crm_enqueue_escalation_error", session_id=self._session_id, error=str(exc))
            if self._session_registry is not None:
                try:
                    self._session_registry[self._session_id] = self.get_snapshot()
                except Exception:
                    pass
            return result

        raise ValueError(f"Unknown action: {name}")

    async def admin_set_disposition(self, disposition: str) -> None:
        """Supervisor action: mark disposition (demo-grade)."""
        disp = (disposition or "").strip() or "closed"
        self._wf_state.disposition = disp
        if disp in {"closed", "no_consent", "consent_refused", "wrong_party", "dnd_requested", "identity_not_confirmed"}:
            prev = self._wf_state.current_step
            self._wf_state.current_step = "closing"
            if prev != "closing":
                self._log_workflow_transition(from_step=prev, to_step="closing", reason="admin_disposition")
        else:
            self._set_workflow_step(reason="admin_disposition")

        if self._audit_store:
            try:
                self._audit_store.upsert_outcome(
                    session_id=self._session_id,
                    customer_id=str(self._facts.get("customer_id") or "") or None,
                    campaign_id=str(self._facts.get("campaign_id") or "") or None,
                    dpd_bucket=(self._get_strategy_decision().dpd_bucket if self._get_strategy_decision() else None),
                    disposition=disp,
                    ptp_date=self._wf_state.ptp_date,
                    callback_time=self._wf_state.callback_time,
                )
                self._audit_store.record_event(
                    event_type="admin",
                    session_id=self._session_id,
                    payload={"action": "set_disposition", "disposition": disp},
                )
            except Exception:
                pass
        if self._excel_sink:
            try:
                self._excel_sink.upsert_call(
                    session_id=self._session_id,
                    customer_id=str(self._facts.get("customer_id") or "") or None,
                    disposition=disp,
                    ptp_date=self._wf_state.ptp_date,
                    callback_time=self._wf_state.callback_time,
                )
            except Exception:
                pass
        if self._session_registry is not None:
            try:
                self._session_registry[self._session_id] = self.get_snapshot()
            except Exception:
                pass
        if self._crm_adapter:
            try:
                self._crm_adapter.enqueue_outcome(
                    session_id=self._session_id,
                    event_type="disposition_update",
                    payload={
                        "session_id": self._session_id,
                        "customer_id": self._facts.get("customer_id"),
                        "campaign_id": self._facts.get("campaign_id"),
                        "disposition": disp,
                        "ptp_date": self._wf_state.ptp_date,
                        "callback_time": self._wf_state.callback_time,
                    },
                )
            except Exception as exc:
                log_event(logger, "crm_enqueue_disposition_error", session_id=self._session_id, error=str(exc))
        await self.send_event({"type": "supervisor_update", "disposition": disp})

    def _should_barge_in_from_vad(self) -> bool:
        """Guard against false barge-in due to speaker echo / noise."""
        now = time.time()
        # If we don't have a TTS start timestamp yet, don't barge-in.
        if not self._tts_start_ts:
            return False
        if self._in_silence:
            return False
        # Grace window after TTS starts.
        if (now - self._tts_start_ts) < self._barge_in_grace_s:
            return False
        # Require a few consecutive frames above threshold (reduces single-frame spikes).
        if self._vad_speech_frames < self._barge_in_min_speech_frames:
            return False
        # Require energy to be above VAD threshold by a margin to reduce random blips.
        if self._last_rms < (self._vad_threshold * 1.2):
            return False
        return True

    def _should_flush_on_silence_transition(self, *, segment_duration_ms: Optional[int] = None) -> bool:
        if not (self.stt.flush_signal or getattr(self.stt, "use_sdk", False)):
            return False
        if not self._has_sent_audio:
            return False
        now = time.time()
        if (now - self._last_flush_ts) < self._flush_min_gap_s:
            return False
        if self._segment_speech_frames >= self._min_flush_speech_frames:
            return True
        if segment_duration_ms is not None and segment_duration_ms >= self._force_flush_segment_ms:
            return True
        if self._short_flush_skip_count >= self._force_flush_after_skips:
            return True
        if (
            self._segment_speech_frames > 0
            and (now - self._last_stt_final_ts) >= self._force_flush_no_final_s
        ):
            return True
        return False

    def _should_barge_in_from_stt(self, text: str) -> bool:
        """Decide whether an STT final should trigger barge-in.

        This is safer than VAD-based barge-in because it uses actual
        recognized speech instead of raw audio energy, and also guards
        against echo from the assistant's own TTS.
        """
        now = time.time()

        # If TTS is not playing or pending, nothing to barge into.
        if not (self._tts_playing.is_set() or self._tts_pending):
            return False

        # Ignore speech very soon after TTS started (echo / speaker leak).
        if self._tts_start_ts and (now - self._tts_start_ts) < self._barge_in_grace_s:
            return False

        t = (text or "").strip().lower()

        # Allow "yes/no" to interrupt during consent/identity/awareness questions.
        t_clean = "".join(ch for ch in t if ch.isalnum() or ch.isspace()).strip()
        if t_clean:
            parts = [p for p in t_clean.split() if p]
            if len(parts) == 1:
                single = parts[0]
                if single in {"yes", "yeah", "yep", "haan", "han", "no", "nah", "nahi"}:
                    step = (
                        self._reply_to_step_id
                        or self._pending_step_id
                        or self._wf_state.current_step
                    )
                    return step in {"consent", "confirm_identity", "confirm_awareness"}
                if single in {"hi", "hello", "hey", "hmm", "hm", "ok", "okay"}:
                    return False

        # Very short utterances like "hi", "hmm" should not interrupt.
        if len(t) <= 3:
            return False

        # If STT text overlaps strongly with what the assistant is saying, it's echo.
        def norm(s: str) -> str:
            return " ".join((s or "").lower().split())

        stt_norm = norm(t)
        a_stream = norm(self._current_llm_text)
        a_final = norm(self._last_assistant_text)

        if a_stream and (stt_norm in a_stream or a_stream in stt_norm):
            return False
        if a_final and (stt_norm in a_final or a_final in stt_norm):
            return False

        # Otherwise, this is real user speech during assistant talk → barge-in.
        return True

    async def _audio_sender_loop(self) -> None:
        while True:
            frame = await self._audio_in_queue.get()
            if not frame:
                continue
            try:
                await self.stt.send_audio(frame)
                self._has_sent_audio = True
            except ConnectionClosed as exc:
                log_event(
                    logger,
                    "stt_connection_closed",
                    session_id=self._session_id,
                    code=getattr(exc, "code", None),
                    reason=getattr(exc, "reason", None),
                )
                await self._reconnect_stt()
                continue
            except Exception as exc:
                log_event(logger, "stt_send_error", session_id=self._session_id, error=str(exc))
                await self._reconnect_stt()
                continue

    async def _stt_loop(self) -> None:
        log_event(logger, "stt_stream_open", session_id=self._session_id)
        reconnect_attempts = 0
        max_reconnect_attempts = 5
        while reconnect_attempts < max_reconnect_attempts:
            try:
                async for transcript in self.stt.transcript_stream():
                    self._last_stt_ts = time.time()
                    text = transcript.text.strip()
                    if not text:
                        continue
                    segment_id = None
                    if transcript.is_final:
                        self._stt_final_count += 1
                        segment_id = f"seg-{self._stt_final_count}"

                    # Suppress obvious echo during laptop-speaker testing: if TTS is playing and STT matches assistant output.
                    if self._is_likely_echo(text, transcript):
                        log_event(
                            logger,
                            "stt_echo_suppressed",
                            session_id=self._session_id,
                            text=text,
                            final=transcript.is_final,
                        )
                        continue

                    await self.send_event(
                        {
                            "type": "transcript",
                            "text": text,
                            "final": transcript.is_final,
                            "language": transcript.language,
                            "confidence": transcript.confidence,
                            "source": "customer",
                            "segment_id": segment_id,
                        }
                    )

                    detected_lang = self._canonical_language_code(transcript.language)
                    if detected_lang:
                        if detected_lang == self._last_detected_stt_lang:
                            self._detected_stt_lang_streak += 1
                        else:
                            self._last_detected_stt_lang = detected_lang
                            self._detected_stt_lang_streak = 1

                    if self._dynamic_stt_language and detected_lang:
                        if detected_lang != self.stt.language:
                            self._pending_stt_language = detected_lang
                            log_event(
                                logger,
                                "stt_language_detected",
                                session_id=self._session_id,
                                language=detected_lang,
                            )
                            if self._in_silence:
                                await self._apply_language_update()

                    if transcript.is_final and detected_lang:
                        current_pref = self._canonical_language_code(self._facts.get("language_preference"))
                        if self._is_language_auto_align_candidate(
                            detected_language=detected_lang,
                            text=text,
                            current_preference=current_pref,
                        ):
                            self._facts["language_preference"] = detected_lang
                            # Also queue STT language switch so transcription
                            # uses the newly detected language.
                            if self._dynamic_stt_language and detected_lang != self.stt.language:
                                self._pending_stt_language = detected_lang
                                if self._in_silence:
                                    await self._apply_language_update()
                            log_event(
                                logger,
                                "language_auto_aligned",
                                session_id=self._session_id,
                                from_language=current_pref,
                                to_language=detected_lang,
                                reason="stt_final_language_match",
                                streak=self._detected_stt_lang_streak,
                            )

                    now = time.time()
                    # CHANGE: Preview on partials to reduce latency.
                    if transcript.is_final:
                        self._last_stt_final_ts = now
                        self._short_flush_skip_count = 0
                        self._cancel_no_response_watch()
                        self._set_turn_state("USER_SPEAKING")
                        log_event(
                            logger,
                            "stt_final",
                            session_id=self._session_id,
                            text=text,
                            language=transcript.language,
                            confidence=transcript.confidence,
                            )
                        if self._speech_start_ts is not None:
                            log_event(
                                logger,
                                "stt_final_latency",
                                session_id=self._session_id,
                                ms=int((now - self._speech_start_ts) * 1000),
                            )
                        reply_step = (
                            self._reply_to_step_id
                            or self._pending_step_id
                            or self._wf_state.last_agent_intent
                            or self._wf_state.current_step
                        )
                        # Determine if this final is a barge-in while TTS is active.
                        is_barge_in = False
                        barge_in_on = None
                        if (self._tts_playing.is_set() or self._tts_pending) and self._barge_in_armed:
                            is_barge_in = True
                            barge_in_on = self._reply_to_utterance_id or self._current_utterance_id
                            self._barge_in_armed = False
                            if self._reply_to_step_id is None:
                                self._freeze_reply_binding(reason="stt_final")
                        t_norm = " ".join(text.lower().strip().split())
                        if self._greeting_active and (self._tts_playing.is_set() or self._tts_pending):
                            # Only ignore trivial acks if consent has already been captured.
                            # If consent is still pending (e.g. user barged in before consent
                            # portion was spoken), do NOT swallow the response.
                            if self._wf_state.consent is True and t_norm in {"hi", "hello", "hey", "ok", "okay", "yes"}:
                                log_event(logger, "greeting_ack_ignored", session_id=self._session_id, text=text)
                                continue
                        if is_barge_in and (self._tts_playing.is_set() or self._tts_pending):
                            # Cut current speech immediately once we have a decisive final.
                            await self._graceful_interrupt("stt_final")
                        await self._emit_timeline_event(
                            "stt_final",
                            segment_id=segment_id,
                            text=text,
                            barge_in_on=barge_in_on,
                            bound_step=reply_step,
                        )
                        binary_step = reply_step in {
                            "consent",
                            "confirm_identity",
                            "confirm_awareness",
                        }
                        if transcript.confidence is not None and transcript.confidence < 0.4:
                            if not (binary_step and (self._is_yes(text) or self._is_no(text))):
                                if (time.time() - self._last_clarify_ts) >= self._clarify_cooldown_s:
                                    self._last_clarify_ts = time.time()
                                    clarify_lang = self._resolve_output_language(transcript.language)
                                    await self._start_fixed_turn(
                                        assistant_text=self._clarify_prompt(clarify_lang),
                                        language=clarify_lang,
                                        step="clarify",
                                        update_workflow=False,
                                    )
                                    continue
                                log_event(
                                    logger,
                                    "clarify_suppressed",
                                    session_id=self._session_id,
                                    reason="cooldown",
                                    source="low_confidence",
                                    text=text[:50],
                                )
                        token_count = len([t for t in (text or "").strip().split() if t])
                        if (
                            not binary_step
                            and token_count <= 2
                            and self._is_ambiguous_short_reply(text)
                            and (time.time() - self._last_clarify_ts) >= self._clarify_cooldown_s
                        ):
                            self._last_clarify_ts = time.time()
                            clarify_lang = self._resolve_output_language(transcript.language)
                            await self._start_fixed_turn(
                                assistant_text=self._clarify_prompt(clarify_lang),
                                language=clarify_lang,
                                step="clarify",
                                update_workflow=False,
                            )
                            continue
                    elif self._log_partial_transcripts and (now - self._last_partial_log_ts) > 0.3:
                        self._last_partial_log_ts = now
                        self._stt_partial_count += 1
                        log_event(
                            logger,
                            "stt_partial",
                            session_id=self._session_id,
                            text=text,
                            language=transcript.language,
                            confidence=transcript.confidence,
                        )
                        if self._speech_start_ts is not None and not self._first_partial_logged:
                            self._first_partial_logged = True
                            log_event(
                                logger,
                                "stt_first_partial_latency",
                                session_id=self._session_id,
                                ms=int((now - self._speech_start_ts) * 1000),
                            )
                        # Backchanneling for long partials
                        backchannel = self._should_backchannel(text, transcript)
                        if backchannel:
                            asyncio.create_task(self._send_backchannel(backchannel), name="backchannel")

                    if text == self._last_transcript_text and not transcript.is_final:
                        continue
                    # Only update last transcript text if it's different (to allow same text as final)
                    if text != self._last_transcript_text or transcript.is_final:
                        self._last_transcript_text = text

                    if (
                        not transcript.is_final
                        and (self._tts_playing.is_set() or self._tts_pending)
                        and self._barge_in_armed
                        and self._should_barge_in_from_stt(text)
                    ):
                        self._barge_in_armed = False
                        self._freeze_reply_binding(reason="stt_partial")
                        asyncio.create_task(self._graceful_interrupt("stt_partial"), name="barge_in_partial")

                    if transcript.is_final:
                        if self._is_duplicate_user_text(text):
                            log_event(
                                logger,
                                "user_text_deduped",
                                session_id=self._session_id,
                                text=text[:50],
                            )
                            continue
                        log_event(
                            logger,
                            "processing_final_transcript",
                            session_id=self._session_id,
                            text=text[:50],
                            is_barge_in=is_barge_in,
                            tts_playing=self._tts_playing.is_set(),
                        )
                        # Update last speech timestamp when we get a final transcript
                        self._last_speech_ts = time.time()
                        # Update lightweight conversation facts + policy confirmations from user final text.
                        self._last_user_text = text
                        prev_no_count = self._wf_state.no_count
                        prev_refusal_strength = self._wf_state.refusal_strength
                        prev_refusal_reason = self._wf_state.refusal_reason
                        prev_lang_pref = self._canonical_language_code(self._facts.get("language_preference"))
                        await self._emit_chat_message(role="user", text=text)
                        self._log_message(role="user", content=text)
                        self._extract_facts_from_text(text)
                        requested_language = self._detect_language_switch_request(text)
                        if not requested_language:
                            updated_lang_pref = self._canonical_language_code(self._facts.get("language_preference"))
                            if updated_lang_pref and updated_lang_pref != prev_lang_pref:
                                requested_language = updated_lang_pref
                        if requested_language:
                            await self._handle_language_switch_request(
                                requested_language=requested_language,
                                bound_step=reply_step,
                                source="stt_final",
                            )
                            continue
                        self._update_policy_from_user(text)
                        self._wf.update_from_user(
                            text,
                            self._wf_state,
                            extracted={
                                "customer_name": self._facts.get("customer_name"),
                                "ptp_date": self._facts.get("ptp_date"),
                                "reference_number": self._facts.get("reference_number"),
                                "callback_time": self._facts.get("callback_time"),
                            },
                            reply_to_step_id=reply_step,
                        )
                        # Fallback: if we just asked awareness, any user response counts as answered.
                        if (
                            (reply_step == "confirm_awareness")
                            and not self._wf_state.awareness_confirmed
                        ):
                            self._wf_state.awareness_confirmed = True
                            if self._is_no(text):
                                self._facts["awareness_denied"] = True
                            self._set_workflow_step(reason="fallback_awareness")
                        # Clear reply binding once consumed.
                        self._reply_to_step_id = None
                        self._reply_to_turn_id = None
                        self._sync_workflow_from_facts()
                        self._persist_commitments()
                        self._persist_state()  # Persist state after extracting facts
                        await self._maybe_handle_retry_exceeded_refusal_close()
                        self._preview_active = False
                        negative_class = None
                        if self._wf_state.no_count > prev_no_count:
                            neg_strength = self._wf_state.refusal_strength or prev_refusal_strength or "soft"
                            neg_reason = self._wf_state.refusal_reason or prev_refusal_reason or "unknown"
                            negative_class = f"{neg_strength}:{neg_reason}"
                        # For binary steps, respond immediately on yes/no (skip debounce).
                        if binary_step and (self._is_yes(text) or self._is_no(text)):
                            self._generation_epoch += 1
                            await self._start_generation(text, transcript, preview=False)
                            continue
                        # Check for repair need before scheduling
                        repair_type = self._detect_misunderstanding(text, self._last_assistant_text)
                        if repair_type:
                            repair_response = await self._handle_repair(repair_type, text)
                            if repair_response:
                                log_event(logger, "repair_triggered", session_id=self._session_id, 
                                          type=repair_type, user_text=text[:50])
                                # Inject repair into context
                                self._append_history("assistant", f"[Repair: {repair_type}] {repair_response}")
                        
                        # Check for post-interrupt handling
                        post_interrupt = await self._handle_post_interrupt(text)
                        if post_interrupt:
                            # User asked us to continue
                            self._append_history("assistant", post_interrupt)

                        log_event(
                            logger,
                            "stt_final_scheduling",
                            session_id=self._session_id,
                            text=text[:50],
                            bound_step=reply_step,
                            negative_class=negative_class,
                            in_silence=self._in_silence,
                            tts_playing=self._tts_playing.is_set(),
                            barge_in_armed=self._barge_in_armed,
                            stress_level=self._emotional_state.stress_level,
                            sentiment=self._emotional_state.sentiment,
                        )
                        try:
                            self._generation_epoch += 1
                            await self._schedule_final_generation(text, transcript, self._generation_epoch)
                        except Exception as exc:
                            log_event(
                                logger,
                                "schedule_final_generation_error",
                                session_id=self._session_id,
                                error=str(exc),
                                exc_type=type(exc).__name__,
                            )
                            raise
                else:
                    if self._preview_partials and not self._preview_suppressed_logged:
                        self._preview_suppressed_logged = True
                        log_event(
                            logger,
                            "preview_suppressed",
                            session_id=self._session_id,
                            reason="finals_only_decision_path",
                        )
                # If we exit the loop normally (shouldn't happen), break
                break
            except Exception as exc:
                reconnect_attempts += 1
                log_event(
                    logger,
                    "stt_stream_error",
                    session_id=self._session_id,
                    error=str(exc),
                    attempt=reconnect_attempts,
                )
                # Don't raise - try to reconnect and continue
                # Raising would stop the STT loop permanently
                if reconnect_attempts < max_reconnect_attempts:
                    try:
                        await asyncio.sleep(min(1.0 * reconnect_attempts, 5.0))  # Exponential backoff
                        await self._reconnect_stt()
                        reconnect_attempts = 0  # Reset on successful reconnect
                        log_event(logger, "stt_reconnected", session_id=self._session_id)
                    except Exception as reconnect_exc:
                        log_event(
                            logger,
                            "stt_reconnect_failed",
                            session_id=self._session_id,
                            error=str(reconnect_exc),
                            attempt=reconnect_attempts,
                        )
                        # Continue to next iteration to retry
                else:
                    log_event(
                        logger,
                        "stt_max_reconnect_attempts",
                        session_id=self._session_id,
                        attempts=max_reconnect_attempts,
                    )
                    raise


    async def _schedule_final_generation(self, text: str, transcript: Transcript, epoch: int) -> None:
        """Debounce final STT to avoid interrupting the user on short pauses."""
        has_pending = bool(self._pending_final)
        keep_existing = False
        replacement_reason = "no_pending"
        if self._pending_final:
            pending_text, _, _ = self._pending_final
            keep_existing = self._should_keep_existing_pending_final(pending_text, text)
            replacement_reason = "kept_existing_meaningful" if keep_existing else "replaced_with_new_final"
        log_event(
            logger,
            "schedule_final_generation",
            session_id=self._session_id,
            text=text[:50],
            has_pending=has_pending,
            has_task=bool(self._finalize_task and not self._finalize_task.done()),
            replacement_reason=replacement_reason,
        )
        if self._pending_final:
            pending_text, _, _ = self._pending_final
            if keep_existing:
                log_event(
                    logger,
                    "pending_final_kept",
                    session_id=self._session_id,
                    pending_text=pending_text[:50],
                    dropped_text=text[:50],
                    reason="new_low_information",
                )
                return
        self._pending_final = (text, transcript, epoch)
        if self._finalize_task and not self._finalize_task.done():
            self._finalize_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._finalize_task
        self._finalize_task = asyncio.create_task(self._finalize_pending_final(), name="finalize_pending_final")

    def _should_cancel_pending_final_for_speech(
        self,
        *,
        last_speech_at_start: float,
        speech_active_checks: int,
        time_since_start: float,
    ) -> bool:
        if self._last_speech_ts <= last_speech_at_start:
            return False
        if self._in_silence:
            return False
        if speech_active_checks < 3:
            return False
        if time_since_start < 0.25:
            return False
        if self._vad_speech_frames < self._barge_in_min_speech_frames:
            return False
        return True

    async def _finalize_pending_final(self) -> None:
        """Wait for sustained silence before responding.
        
        This method waits for a pause period, but checks periodically if the user
        has started speaking again. If new speech is detected, it cancels the response.
        """
        pause_start_ts = time.time()
        last_speech_at_start = self._last_speech_ts
        speech_active_checks = 0
        
        # Wait in smaller chunks so we can check if user started speaking
        chunk_duration = 0.1  # Check every 100ms
        total_chunks = int(self._post_speech_pause_s / chunk_duration) + 1
        
        for _ in range(total_chunks):
            await asyncio.sleep(chunk_duration)
            
            # Check if pending final was cleared (user started speaking)
            if not self._pending_final:
                log_event(
                    logger,
                    "finalize_cancelled",
                    session_id=self._session_id,
                    reason="pending_cleared",
                )
                return
            
            # Check if user has spoken since we started waiting (NEW speech detected)
            time_since_start = time.time() - pause_start_ts
            if self._in_silence:
                speech_active_checks = 0
            else:
                speech_active_checks += 1
            if self._should_cancel_pending_final_for_speech(
                last_speech_at_start=last_speech_at_start,
                speech_active_checks=speech_active_checks,
                time_since_start=time_since_start,
            ):
                log_event(
                    logger,
                    "finalize_cancelled",
                    session_id=self._session_id,
                    reason="user_speaking",
                    silence_duration_ms=int(time_since_start * 1000),
                    speech_active_checks=speech_active_checks,
                    vad_speech_frames=self._vad_speech_frames,
                    rms=round(self._last_rms, 2),
                )
                self._pending_final = None
                return
        
        # After pause, require explicit silence confirmation before response.
        if not self._pending_final:
            return

        confirm_window_s = max(0.2, min(0.8, self._post_speech_pause_s))
        confirm_deadline = time.time() + confirm_window_s
        speech_active_checks = 0
        silence_confirmed = False
        while time.time() < confirm_deadline:
            if not self._pending_final:
                return
            time_since_start = time.time() - pause_start_ts
            if self._in_silence:
                speech_active_checks = 0
            else:
                speech_active_checks += 1
            if self._should_cancel_pending_final_for_speech(
                last_speech_at_start=last_speech_at_start,
                speech_active_checks=speech_active_checks,
                time_since_start=time_since_start,
            ):
                log_event(
                    logger,
                    "finalize_cancelled",
                    session_id=self._session_id,
                    reason="user_speaking_during_confirm",
                    silence_duration_ms=int(time_since_start * 1000),
                    speech_active_checks=speech_active_checks,
                    vad_speech_frames=self._vad_speech_frames,
                    rms=round(self._last_rms, 2),
                )
                self._pending_final = None
                return

            time_since_last_speech = time.time() - self._last_speech_ts
            if self._in_silence and time_since_last_speech >= 0.25:
                silence_confirmed = True
                break
            await asyncio.sleep(0.05)

        if not silence_confirmed:
            log_event(
                logger,
                "finalize_cancelled",
                session_id=self._session_id,
                reason="silence_not_confirmed",
                in_silence=self._in_silence,
                ms_since_last_speech=int((time.time() - self._last_speech_ts) * 1000),
            )
            # Keep pending final and wait again instead of generating too early.
            self._finalize_task = asyncio.create_task(self._finalize_pending_final(), name="finalize_pending_final")
            return

        text, transcript, epoch = self._pending_final
        self._pending_final = None
        if epoch != self._generation_epoch:
            log_event(
                logger,
                "finalize_cancelled",
                session_id=self._session_id,
                reason="stale_epoch",
                epoch=epoch,
                current_epoch=self._generation_epoch,
            )
            return
        
        log_event(
            logger,
            "finalize_pending_final",
            session_id=self._session_id,
            text=text[:50],
            in_silence=self._in_silence,
            pause_duration_ms=int((time.time() - pause_start_ts) * 1000),
            ms_since_last_speech=int((time.time() - self._last_speech_ts) * 1000),
        )
        await self._start_generation(text, transcript, preview=False)

    async def _start_generation_from_text(self, user_text: str, language: Optional[str], preview: bool = False) -> None:
        """Start an LLM+TTS turn from a plain text user utterance (no Transcript object)."""
        async with self._cancel_lock:
            await self._cancel_generation_locked()
            self._cancel_no_response_watch()
            self._turn_seq += 1
            self._current_turn_id = f"turn-{self._turn_seq}"
            self._llm_start_ts = time.time()
            self._llm_first_token_ts = None
            self._tts_first_chunk_ts = None
            language = self._resolve_output_language(language)

            raw = list(self._trim_history())

            base_system, tail = self._sanitize_history_for_llm(raw)

            combined_system = (base_system.strip() + "\n\n" + self._build_context_system_message()).strip()
            # Offline demo RAG: inject top snippets (SQLite FTS) into the system context.
            if self._knowledge_store:
                try:
                    chunks = self._knowledge_store.query(user_text, limit=3)
                    ktxt = self._knowledge_store.format_for_prompt(chunks)
                except Exception:
                    ktxt = ""
                    chunks = []
                if ktxt:
                    combined_system = (combined_system + "\n\n" + ktxt).strip()
                if chunks:
                    try:
                        await self.send_event(
                            {
                                "type": "knowledge_used",
                                "chunks": [
                                    {"doc_id": c.doc_id, "title": c.title, "chunk_id": c.chunk_id, "text": c.text}
                                    for c in chunks
                                ],
                            }
                        )
                    except Exception:
                        pass
            combined_system = (combined_system + f"\n\nCurrent workflow step: {self._wf_state.current_step}. Ask only what is needed for this step.").strip()
            messages = [{"role": "system", "content": combined_system}] + tail

            messages.append({"role": "user", "content": user_text})

            # Deterministic hard-routing for key workflow steps (kills looping for demos).
            next_step = self._set_workflow_step(reason="generation_from_text")
            if not preview:
                self._set_pending_step(next_step)
            if (
                not preview
                and self._supports_fixed_language(language)
                and next_step in {
                "consent",
                "confirm_identity",
                "confirm_awareness",
                "ask_payment_made",
                "ask_reference_number",
                "ask_ptp_or_callback",
                "closing",
                }
            ):
                fixed = self._fixed_prompt_for_step(next_step, language=language)
                self._gen_task = asyncio.create_task(
                    self._run_fixed_turn(assistant_text=fixed, language=language, step=next_step),
                    name=f"fixed_{next_step}",
                )
                return

            # For non-fixed steps, inject a strict runtime instruction into the last user message.
            messages[-1] = {
                "role": "user",
                "content": self._build_runtime_user_instruction(step=next_step, user_text=user_text),
            }

            log_event(
                logger,
                "llm_start",
                session_id=self._session_id,
                turn_id=self._current_turn_id,
                text=user_text,
                language=language,
                preview=preview,
                source="typed",
            )

            self._gen_task = asyncio.create_task(
                self._run_generation(messages=messages, user_text=user_text, language=language, preview=preview),
                name="generation_typed",
            )

    # CHANGE: Optional preview generation on partials.
    async def _start_generation(self, text: str, transcript: Transcript, preview: bool = False) -> None:
        async with self._cancel_lock:
            await self._cancel_generation_locked()
            self._cancel_no_response_watch()
            language = self._resolve_output_language(transcript.language)
            self._turn_seq += 1
            self._current_turn_id = f"turn-{self._turn_seq}"
            self._llm_start_ts = time.time()
            self._llm_first_token_ts = None
            self._tts_first_chunk_ts = None
            raw = list(self._trim_history())

            base_system, tail = self._sanitize_history_for_llm(raw)

            combined_system = (base_system.strip() + "\n\n" + self._build_context_system_message()).strip()
            # Offline demo RAG: inject top snippets (SQLite FTS) into the system context.
            if self._knowledge_store:
                try:
                    chunks = self._knowledge_store.query(text, limit=3)
                    ktxt = self._knowledge_store.format_for_prompt(chunks)
                except Exception:
                    ktxt = ""
                    chunks = []
                if ktxt:
                    combined_system = (combined_system + "\n\n" + ktxt).strip()
                if chunks:
                    try:
                        await self.send_event(
                            {
                                "type": "knowledge_used",
                                "chunks": [
                                    {"doc_id": c.doc_id, "title": c.title, "chunk_id": c.chunk_id, "text": c.text}
                                    for c in chunks
                                ],
                            }
                        )
                    except Exception:
                        pass
            combined_system = (combined_system + f"\n\nCurrent workflow step: {self._wf_state.current_step}. Ask only what is needed for this step.").strip()
            messages = [{"role": "system", "content": combined_system}] + tail

            messages.append({"role": "user", "content": text})

            # Deterministic hard-routing for key workflow steps (kills looping for demos).
            next_step = self._set_workflow_step(reason="generation")
            if not preview:
                self._set_pending_step(next_step)
            if (
                not preview
                and self._supports_fixed_language(language)
                and next_step in {
                "consent",
                "confirm_identity",
                "confirm_awareness",
                "ask_payment_made",
                "ask_reference_number",
                "ask_ptp_or_callback",
                "closing",
                }
            ):
                fixed = self._fixed_prompt_for_step(next_step, language=language)
                self._gen_task = asyncio.create_task(
                    self._run_fixed_turn(assistant_text=fixed, language=language, step=next_step),
                    name=f"fixed_{next_step}",
                )
                return

            # For non-fixed steps, inject a strict runtime instruction into the last user message.
            messages[-1] = {
                "role": "user",
                "content": self._build_runtime_user_instruction(step=next_step, user_text=text),
            }

            log_event(
                logger,
                "llm_start",
                session_id=self._session_id,
                turn_id=self._current_turn_id,
                text=text,
                language=language,
                preview=preview,
            )
            # Log emotional state and emit to frontend
            log_event(
                logger,
                "emotion_state",
                session_id=self._session_id,
                stress=self._emotional_state.stress_level,
                sentiment=self._emotional_state.sentiment,
                refusals=self._emotional_state.consecutive_refusals,
            )
            await self.send_event({
                "type": "emotion_state",
                "stress_level": round(float(self._emotional_state.stress_level), 3),
                "sentiment": self._emotional_state.sentiment,
                "consecutive_refusals": self._emotional_state.consecutive_refusals,
            })
            self._gen_task = asyncio.create_task(
                self._run_generation(messages=messages, user_text=text, language=language, preview=preview),
                name="generation",
            )

    async def _start_tts_only(self, text: str) -> None:
        async with self._cancel_lock:
            await self._cancel_generation_locked()
            normalized_text = self._normalize_branding_text(text)
            log_event(logger, "greeting_start", session_id=self._session_id, text=normalized_text)
            self._gen_task = asyncio.create_task(
                self._run_tts_only(text=normalized_text),
                name="greeting_tts",
            )

    async def _run_tts_only(self, text: str) -> None:
        text = self._normalize_branding_text(text)
        assistant_history_appended = False
        self._current_utterance_id = self._next_utterance_id()
        self._current_utterance_status = "completed"
        await self._emit_timeline_event(
            "agent_utterance_created",
            utterance_id=self._current_utterance_id,
            text=text,
        )
        if not self._is_duplicate_assistant_text(text):
            self._last_assistant_text = text.strip()
            self._log_message(role="assistant", content=self._last_assistant_text)
            self._append_history("assistant", self._last_assistant_text)
            self._trim_history()
            assistant_history_appended = True
        tts = BulbulTTSService(
            ws_url=self.tts_ws_url,
            api_key=self.tts_api_key,
            voice=self.tts_voice,
            model=self.tts_model,
            speaker=self.tts_speaker,
            output_audio_codec=self._tts_output_audio_codec,
            output_audio_bitrate=self._tts_output_audio_bitrate,
            min_buffer_size=self._tts_min_buffer_size or None,
            max_chunk_length=self._tts_max_chunk_length or None,
            use_sdk=self._use_sdk,
        )
        async with tts:
            self._tts_audio_received.clear()
            audio_task = asyncio.create_task(self._tts_audio_loop(tts), name="tts_greeting_audio")
            try:
                await self.send_event({"type": "status", "state": "speaking"})
                self._set_turn_state("AGENT_SPEAKING")
                log_event(
                    logger,
                    "tts_input",
                    session_id=self._session_id,
                    turn_id=self._current_turn_id,
                    chars=len(text),
                    source="greeting",
                )
                self._tts_pending = True
                self._tts_start_ts = time.time()
                self._barge_in_armed = True
                # Set last asked intent before speech in case user barges in.
                self._wf.update_from_assistant(text, self._wf_state)
                self._set_pending_step(self._wf_state.last_agent_intent or self._wf_state.current_step)
                await self._emit_chat_message(role="assistant", text=text)
                await tts.send_text(text)
                await tts.end_input()
                await audio_task
                await self._emit_timeline_event(
                    "agent_tts_end",
                    utterance_id=self._current_utterance_id,
                    status=self._current_utterance_status,
                )
                if not self._is_duplicate_assistant_text(text):
                    await self.send_event(
                        {
                            "type": "assistant_final",
                            "text": text,
                            "source": "greeting",
                            "utterance_id": self._current_utterance_id,
                        }
                    )
                    log_event(logger, "greeting_end", session_id=self._session_id)
                    # IMPORTANT: Add greeting to history so LLM won't repeat it later.
                    if text and text.strip() and not assistant_history_appended:
                        self._last_assistant_text = text.strip()
                        self._log_message(role="assistant", content=self._last_assistant_text)
                        self._append_history("assistant", text.strip())
                        self._trim_history()
                self._set_workflow_step(reason="greeting_end")
                await self.send_event({"type": "status", "state": "listening"})
                self._set_turn_state("WAITING_FOR_USER")
                self._schedule_no_response_watch()
                self._greeting_active = False
            except asyncio.CancelledError:
                audio_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await audio_task
                await self._emit_timeline_event(
                    "agent_tts_end",
                    utterance_id=self._current_utterance_id,
                    status="interrupted",
                )
                if not self._is_duplicate_assistant_text(text):
                    await self.send_event(
                        {
                            "type": "assistant_final",
                            "text": text,
                            "source": "greeting",
                            "interrupted": True,
                            "utterance_id": self._current_utterance_id,
                        }
                    )
                await self._emit_chat_message(role="assistant", text=text)
                await self.send_event({"type": "assistant_cancelled", "source": "greeting"})
                log_event(logger, "greeting_cancelled", session_id=self._session_id)
                # If the greeting was interrupted before the consent portion
                # was spoken, reset consent state so it gets re-asked.
                if self._wf_state.consent is None or not self._wf_state.consent:
                    self._wf_state.consent = None
                    self._wf_state.consent_asked = False
                    self._wf_state.current_step = "consent"
                    log_event(
                        logger,
                        "consent_reset_after_barge_in",
                        session_id=self._session_id,
                        reason="greeting_interrupted_before_consent_spoken",
                    )
                self._greeting_active = False
                raise
            finally:
                self._tts_playing.clear()
                self._tts_pending = False
                self._barge_in_armed = False
                self._current_utterance_status = "completed"

            self._barge_in_armed = False

    def _fixed_prompt_for_step(self, step: str, language: Optional[str] = None) -> str:
        """Deterministic prompts for key workflow steps (no LLM)."""
        step = (step or "").strip()
        name = self._facts.get("customer_name")
        amt = self._facts.get("overdue_amount")
        due = self._facts.get("due_date")
        lang = self._resolve_output_language(language)
        is_hi = bool(lang and lang.lower().startswith("hi"))
        if step == "consent":
            if is_hi:
                return "यह कॉल गुणवत्ता के लिए रिकॉर्ड की जा सकती है। क्या मैं आपकी सहमति से बातचीत आगे बढ़ाऊँ?"
            return "This call may be recorded for quality. Do I have your consent to continue?"
        if step == "confirm_identity":
            if name:
                if is_hi:
                    return f"क्या मैं {name} जी से बात कर रही हूँ?"
                return f"Am I speaking with {name}?"
            if is_hi:
                return "क्या मैं आपका नाम पुष्टि कर सकती हूँ?"
            return "May I confirm your name?"
        if step == "confirm_awareness":
            if (
                self._wf_state.last_asked_step == "confirm_awareness"
                and time.time() - self._wf_state.last_asked_ts < 15
            ):
                if amt:
                    if is_hi:
                        return f"पुष्टि के लिए पूछ रही हूँ, क्या आपको ₹{amt} की लंबित भुगतान राशि के बारे में पता है?"
                    return f"Just to confirm, you’re aware of the pending payment of ₹{amt}, correct?"
                if is_hi:
                    return "पुष्टि के लिए पूछ रही हूँ, क्या आपको लंबित भुगतान के बारे में पता है?"
                return "Just to confirm, you’re aware of the pending payment, correct?"
            if amt and due:
                if is_hi:
                    return f"क्या आपको पता है कि ₹{amt} की आपकी लोन भुगतान राशि {due} से ओवरड्यू है?"
                return f"Are you aware that your loan payment of ₹{amt} is overdue as of {due}?"
            if amt:
                if is_hi:
                    return f"क्या आपको पता है कि ₹{amt} की आपकी लोन भुगतान राशि ओवरड्यू है?"
                return f"Are you aware that your loan payment of ₹{amt} is overdue?"
            if due:
                if is_hi:
                    return f"क्या आपको पता है कि आपकी लोन भुगतान राशि {due} से ओवरड्यू है?"
                return f"Are you aware that your loan payment is overdue as of {due}?"
            if is_hi:
                return "क्या आपको अपने TuringEdge लोन की ओवरड्यू भुगतान राशि के बारे में पता है?"
            return "Are you aware of the overdue payment on your TuringEdge loan?"
        if step == "ask_payment_made":
            if (
                self._wf_state.last_asked_step == "ask_payment_made"
                and time.time() - self._wf_state.last_asked_ts < 15
            ):
                if amt:
                    if is_hi:
                        return f"पुष्टि के लिए पूछ रही हूँ, क्या आपने ₹{amt} का भुगतान कर दिया है? सिर्फ हाँ या ना काफी है।"
                    return f"Just to confirm, have you already paid the ₹{amt}? A simple yes or no is fine."
                if is_hi:
                    return "पुष्टि के लिए पूछ रही हूँ, क्या आपने भुगतान कर दिया है? सिर्फ हाँ या ना काफी है।"
                return "Just to confirm, have you already made the payment? A simple yes or no is fine."
            if amt:
                if is_hi:
                    return f"क्या आपने ₹{amt} का भुगतान कर दिया है?"
                return f"Have you already made the payment of ₹{amt}?"
            if is_hi:
                return "क्या आपने भुगतान कर दिया है?"
            return "Have you already made the payment?"
        if step == "ask_reference_number":
            if (
                self._wf_state.last_asked_step == "ask_reference_number"
                and time.time() - self._wf_state.last_asked_ts < 15
            ):
                if is_hi:
                    return (
                        "अगर भुगतान हो गया है, तो कृपया ट्रांज़ैक्शन रेफरेंस या UTR और भुगतान की तारीख साझा करें। "
                        "अगर भुगतान नहीं हुआ है, तो बस बता दीजिए।"
                    )
                return (
                    "If you have already paid, please share the transaction reference or UTR and the payment date. "
                    "If you have not paid, just let me know."
                )
            if is_hi:
                return "कृपया ट्रांज़ैक्शन रेफरेंस नंबर या UTR और भुगतान की तारीख बताइए।"
            return "Please share the transaction reference number or UTR and the date of payment."
        if step == "ask_ptp_or_callback":
            if self._wf_state.last_transition_reason == "invalid_ptp_date":
                if is_hi:
                    return "कृपया अगले 30 दिनों के भीतर की वैध भुगतान तारीख बताइए।"
                return "Please share a valid payment date within the next 30 days."
            if self._wf_state.last_transition_reason == "invalid_callback_time":
                if is_hi:
                    return "कृपया 9am–8pm के बीच का कॉलबैक समय बताइए।"
                return "Please share a callback time between 9am–8pm."
            if self._wf_state.last_transition_reason == "uncertain_commitment":
                if amt:
                    if is_hi:
                        return (
                            f"कोई बात नहीं। अगर आप अभी सुनिश्चित नहीं हैं, तो मैं कॉलबैक शेड्यूल कर सकती हूँ। "
                            f"कृपया 9am–8pm के बीच का समय बताइए, या ₹{amt} की भुगतान तारीख बताइए।"
                        )
                    return (
                        f"No problem. If you're unsure right now, I can schedule a callback. "
                        f"Please share a time between 9am–8pm, or a date when you can pay ₹{amt}."
                    )
                if is_hi:
                    return (
                        "कोई बात नहीं। अगर आप अभी सुनिश्चित नहीं हैं, तो मैं कॉलबैक शेड्यूल कर सकती हूँ। "
                        "कृपया 9am–8pm के बीच का समय बताइए, या भुगतान तारीख बताइए।"
                    )
                return (
                    "No problem. If you're unsure right now, I can schedule a callback. "
                    "Please share a time between 9am–8pm, or a payment date."
                )
            if self._wf_state.last_transition_reason == "needs_callback":
                if is_hi:
                    return "ठीक है। मैं आपको किस समय कॉलबैक करूँ? कृपया 9am–8pm के बीच का समय बताइए।"
                return "Okay. What time should I call you back? Please share a time between 9am–8pm."
            if self._wf_state.last_transition_reason == "hardship" or self._wf_state.hardship_detected:
                if is_hi:
                    return "मैं समझ सकती हूँ। विकल्पों पर बात करने के लिए 9am–8pm के बीच कॉलबैक का समय बताइए।"
                return "I understand. What time should I call you back to discuss options? Please share a time between 9am–8pm."
            ask_attempts = int(self._wf_state.attempts.get("ask_ptp_or_callback", 0) or 0)
            if (
                self._wf_state.last_asked_step == "ask_ptp_or_callback"
                and time.time() - self._wf_state.last_asked_ts < 15
            ):
                if ask_attempts >= 2:
                    if amt:
                        if is_hi:
                            return f"आपकी मदद के लिए मैं कॉलबैक समय या ₹{amt} की भुगतान तारीख नोट कर सकती हूँ। आपके लिए क्या ठीक रहेगा?"
                        return (
                            f"To help you better, I can either note a callback time or a payment date "
                            f"for ₹{amt}. Which one works for you?"
                        )
                    if is_hi:
                        return "आपकी मदद के लिए मैं कॉलबैक समय या भुगतान तारीख नोट कर सकती हूँ। आपके लिए क्या ठीक रहेगा?"
                    return "To help you better, I can either note a callback time or a payment date. Which one works for you?"
                if amt:
                    if is_hi:
                        return f"अगर अभी भुगतान नहीं हो सकता, तो ₹{amt} कब तक कर पाएँगे, या मैं कॉलबैक कब करूँ?"
                    return f"If you can't pay now, when can you make the payment of ₹{amt}, or what time should I call back?"
                if is_hi:
                    return "अगर अभी भुगतान नहीं हो सकता, तो कब तक कर पाएँगे, या मैं कॉलबैक कब करूँ?"
                return "If you can't pay now, when can you make the payment, or what time should I call back?"
            if amt:
                if is_hi:
                    return f"आप ₹{amt} का भुगतान कब तक कर पाएँगे?"
                return f"When would you be able to make the payment of ₹{amt}?"
            if is_hi:
                return "आप भुगतान कब तक कर पाएँगे?"
            return "When would you be able to make the payment?"
        if step == "closing":
            ptp_spoken = self._ptp_label_for_speech(
                self._wf_state.ptp_date or self._facts.get("ptp_date"),
                lang,
            )
            callback_spoken = self._normalize_callback_text(
                str(self._wf_state.callback_time or self._facts.get("callback_time") or "")
            ) or self._wf_state.callback_time or self._facts.get("callback_time")
            if self._wf_state.disposition in {"dnd_requested"}:
                if is_hi:
                    return "समझ गई। हम इस नंबर पर कॉल करना बंद कर देंगे। धन्यवाद।"
                return "Understood. We’ll stop calling this number. Thank you."
            if self._wf_state.disposition in {"wrong_party"}:
                if is_hi:
                    return "असुविधा के लिए माफ़ कीजिए। हम रिकॉर्ड अपडेट कर देंगे। धन्यवाद।"
                return "Sorry for the inconvenience. We’ll update our records. Thank you."
            if self._wf_state.disposition in {"identity_not_confirmed"}:
                if is_hi:
                    return "पहचान पुष्टि किए बिना हम आगे नहीं बढ़ सकते। धन्यवाद।"
                return "We can’t proceed without confirming identity. Thank you."
            if self._wf_state.disposition in {"consent_refused", "no_consent"} or self._wf_state.consent is False:
                if is_hi:
                    return "ठीक है। आपकी सहमति के बिना मैं बातचीत आगे नहीं बढ़ाऊँगी। धन्यवाद।"
                return "Understood. I will not continue without your consent. Thank you."
            if self._wf_state.disposition in {"refusal_unresolved"} and not (
                self._wf_state.ptp_date or self._wf_state.callback_time
            ):
                if self._wf_state.refusal_strength == "hard":
                    if is_hi:
                        return (
                            "मैं समझ सकती हूँ कि आप अभी भुगतान के लिए प्रतिबद्ध नहीं हो पा रहे हैं। "
                            "मैं इसे फॉलो-अप सहायता के लिए मार्क कर रही हूँ। धन्यवाद।"
                        )
                    return (
                        "I understand you are not able to commit to payment right now. "
                        "I am marking this for follow-up support. Thank you for your time."
                    )
                if is_hi:
                    return (
                        "मैं समझ सकती हूँ कि आप अभी प्रतिबद्ध नहीं हो पा रहे हैं। "
                        "मैं इसे फॉलो-अप के लिए नोट कर रही हूँ। धन्यवाद।"
                    )
                return (
                    "I understand you are not able to commit right now. "
                    "I am noting this for follow-up. Thank you for your time."
                )
            if self._wf_state.reference_number:
                if is_hi:
                    return "धन्यवाद। ट्रांज़ैक्शन रेफरेंस सत्यापित करने के लिए थोड़ा समय दीजिए। ज़रूरत हुई तो हम अपडेट करेंगे।"
                return "Thanks. Please allow me some time to verify the transaction reference. We will update you if needed."
            if ptp_spoken:
                if is_hi:
                    return f"धन्यवाद। आपका भुगतान वादा {ptp_spoken} के लिए नोट कर लिया गया है। कृपया समय पर भुगतान कर दीजिए।"
                return f"Thanks. Noted your commitment to pay by {ptp_spoken}. Please ensure the payment is done by then."
            if callback_spoken:
                if is_hi:
                    return f"धन्यवाद। मैं आपको {callback_spoken} पर कॉलबैक करूँगी।"
                return f"Thanks. I will call you back at {callback_spoken}."
            if is_hi:
                return "धन्यवाद, आपके समय के लिए। ज़रूरत पड़ने पर हम फॉलो अप करेंगे।"
            return "Thanks for your time. We will follow up as needed."
        # Shouldn't happen for fixed steps, but keep safe.
        if is_hi:
            return "एक पल दीजिए।"
        return "One moment, please."

    def _build_runtime_user_instruction(self, *, step: str, user_text: str) -> str:
        """Wrap the customer utterance with strict step instructions for the LLM."""
        amt = self._facts.get("overdue_amount")
        due = self._facts.get("due_date")
        strategy = self._get_strategy_decision()
        base = [
            "You are a TuringEdge collections agent. Follow the collections workflow strictly.",
            "Ask ONLY ONE clear question.",
            "Do NOT greet. Do NOT repeat a question already answered.",
            "Do NOT ask for OTP/CVV/card numbers/passwords/bank details.",
            f"Current workflow step: {step}.",
        ]
        if amt:
            base.append(f"Known overdue amount: INR {amt}. Use it exactly if mentioned.")
        if due:
            base.append(f"Known due date: {due}. Use it exactly if mentioned.")
        if strategy:
            base.append(f"DPD strategy bucket: {strategy.dpd_bucket}.")
            base.append(f"Strategy mode: {strategy.strategy_mode}.")
            base.append(f"Tone profile: {strategy.tone_profile}.")
            base.append(strategy.instruction)

        if step == "ask_payment_made":
            base.append("Question to ask: Have you made the payment?")
        elif step == "ask_reference_number":
            base.append("Question to ask: Please share the transaction reference/UTR and payment date so I can verify.")
        elif step == "ask_ptp_or_callback":
            base.append("Question to ask: By when can you make the payment? Share a date (preferred) or a callback time.")
        else:
            base.append("Question to ask: Ask the next missing required detail for this step.")

        return "\n".join(base) + f"\n\nCustomer said: {user_text}"

    async def _run_fixed_turn(
        self,
        *,
        assistant_text: str,
        language: Optional[str],
        step: str,
        update_workflow: bool = True,
        schedule_no_response: bool = True,
    ) -> None:
        """Speak a deterministic question/statement via TTS and finalize the turn."""
        assistant_text = self._normalize_branding_text(assistant_text)
        assistant_history_appended = False
        normalized_assistant_text = assistant_text.strip()
        is_duplicate_assistant_text = self._is_duplicate_assistant_text(assistant_text)
        if update_workflow:
            self._wf_state.last_agent_intent = step
            self._wf_state.last_asked_step = step
            self._wf_state.last_asked_ts = time.time()
            # Count asks even when text is repeated; prevents infinite repeat loops.
            self._wf.update_from_assistant(normalized_assistant_text, self._wf_state)
            self._set_workflow_step(reason="fixed_turn")
        self._current_utterance_id = self._next_utterance_id()
        self._current_utterance_status = "completed"
        await self._emit_timeline_event(
            "agent_utterance_created",
            utterance_id=self._current_utterance_id,
            text=assistant_text,
        )
        if not is_duplicate_assistant_text:
            self._last_assistant_text = normalized_assistant_text
            self._log_message(role="assistant", content=self._last_assistant_text)
            self._append_history("assistant", self._last_assistant_text)
            self._trim_history()
            assistant_history_appended = True
        self._set_pending_step(step)
        tts = BulbulTTSService(
            ws_url=self.tts_ws_url,
            api_key=self.tts_api_key,
            voice=self.tts_voice,
            model=self.tts_model,
            speaker=self.tts_speaker,
            language=language,
            output_audio_codec=self._tts_output_audio_codec,
            output_audio_bitrate=self._tts_output_audio_bitrate,
            min_buffer_size=self._tts_min_buffer_size or None,
            max_chunk_length=self._tts_max_chunk_length or None,
            use_sdk=self._use_sdk,
        )
        async with tts:
            self._tts_audio_received.clear()
            audio_task = asyncio.create_task(self._tts_audio_loop(tts), name=f"tts_fixed_{step}")
            try:
                await self.send_event({"type": "status", "state": "speaking"})
                self._set_turn_state("AGENT_SPEAKING")
                log_event(
                    logger,
                    "tts_input",
                    session_id=self._session_id,
                    turn_id=self._current_turn_id,
                    chars=len(assistant_text),
                    source=f"fixed:{step}",
                )
                self._tts_pending = True
                self._tts_start_ts = time.time()
                self._barge_in_armed = True
                await self._emit_chat_message(role="assistant", text=assistant_text)
                await tts.send_text(assistant_text)
                await tts.end_input()
                await audio_task
                await self._emit_timeline_event(
                    "agent_tts_end",
                    utterance_id=self._current_utterance_id,
                    status=self._current_utterance_status,
                )
                if not is_duplicate_assistant_text:
                    await self.send_event(
                        {
                            "type": "assistant_final",
                            "text": assistant_text,
                            "source": f"fixed:{step}",
                            "utterance_id": self._current_utterance_id,
                        }
                    )
                    if not assistant_history_appended:
                        self._last_assistant_text = normalized_assistant_text
                        self._log_message(role="assistant", content=self._last_assistant_text)
                        self._append_history("assistant", self._last_assistant_text)
                        self._trim_history()
                await self.send_event({"type": "status", "state": "listening"})
                self._set_turn_state("WAITING_FOR_USER")
                if schedule_no_response:
                    self._schedule_no_response_watch()
            except asyncio.CancelledError:
                audio_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await audio_task
                await self._emit_timeline_event(
                    "agent_tts_end",
                    utterance_id=self._current_utterance_id,
                    status="interrupted",
                )
                if not is_duplicate_assistant_text:
                    await self.send_event(
                        {
                            "type": "assistant_final",
                            "text": assistant_text,
                            "source": f"fixed:{step}",
                            "interrupted": True,
                            "utterance_id": self._current_utterance_id,
                        }
                    )
                await self._emit_chat_message(role="assistant", text=assistant_text)
                await self.send_event({"type": "assistant_cancelled", "source": f"fixed:{step}"})
                raise
            finally:
                self._tts_playing.clear()
                self._tts_pending = False
                self._barge_in_armed = False
    # CHANGE: Full-history LLM calls + timeout wrapper.
    async def _run_generation(self, messages, user_text: str, language: Optional[str], preview: bool = False) -> None:
        if preview:
            await self._run_generation_preview(messages=messages, user_text=user_text, language=language)
            return
        self._set_turn_state("THINKING")
        self._current_utterance_id = self._next_utterance_id()
        self._current_utterance_status = "completed"
        self._pending_utterance_id = self._current_utterance_id
        utterance_emitted = False
        assistant_history_appended = False

        tts = BulbulTTSService(
            ws_url=self.tts_ws_url,
            api_key=self.tts_api_key,
            voice=self.tts_voice,
            model=self.tts_model,
            speaker=self.tts_speaker,
            language=language,
            output_audio_codec=self._tts_output_audio_codec,
            output_audio_bitrate=self._tts_output_audio_bitrate,
            min_buffer_size=self._tts_min_buffer_size or None,
            max_chunk_length=self._tts_max_chunk_length or None,
            use_sdk=self._use_sdk,
        )

        async with tts:
            # Reset first-audio marker for this turn.
            self._tts_audio_received.clear()

            audio_task = asyncio.create_task(self._tts_audio_loop(tts), name="tts_audio")

            assistant_text = ""
            spoken_text = ""  # what we attempted to send to TTS
            tts_buffer = ""

            self._current_llm_text = ""
            self._current_llm_token_count = 0

            # Gate the first sentence to block placeholders / repeated questions early.
            gate_buffer = ""
            gate_released = False

            try:
                await self.send_event({"type": "status", "state": "thinking"})

                async for token in self._stream_with_timeout(
                    self.llm.stream_tokens(
                        user_text=user_text,
                        messages=messages,
                        language=language,
                    ),
                    self._llm_timeout_s,
                    "llm_timeout",
                ):
                    if self._cancel_event.is_set():
                        raise asyncio.CancelledError()

                    if not token:
                        continue

                    if self._llm_first_token_ts is None:
                        self._llm_first_token_ts = time.time()
                        if self._llm_start_ts:
                            log_event(
                                logger,
                                "llm_first_token_latency",
                                session_id=self._session_id,
                                turn_id=self._current_turn_id,
                                ms=int((self._llm_first_token_ts - self._llm_start_ts) * 1000),
                            )

                    self._current_llm_text += token
                    self._current_llm_token_count += 1

                    # First-sentence gate
                    if not gate_released:
                        gate_buffer += token
                        boundary_hit = any(ch in gate_buffer for ch in [".", "?", "!", "।", "\n"]) or len(gate_buffer) >= 320
                        if not boundary_hit:
                            continue

                        candidate = self._sanitize_placeholders(gate_buffer.strip())
                        candidate = self._dedupe_repeated_sentences(candidate)

                        reason = self._policy_disallows_assistant_text(candidate)
                        if reason:
                            candidate = self._policy_fallback_response(user_text)
                            candidate = self._sanitize_placeholders(candidate)
                            candidate = self._dedupe_repeated_sentences(candidate)
                        candidate = self._normalize_branding_text(candidate)

                        gate_released = True
                        gate_buffer = ""

                        self._update_policy_from_assistant(candidate)
                        
                        # Humanize and add prosody hints
                        candidate = self._humanize_response(candidate, language=language)
                        candidate = self._add_prosody_hints(candidate, self._emotional_state)

                        if not utterance_emitted:
                            await self._emit_timeline_event(
                                "agent_utterance_created",
                                utterance_id=self._current_utterance_id,
                                text=candidate,
                            )
                            utterance_emitted = True
                        if (not assistant_history_appended) and candidate.strip() and not self._is_duplicate_assistant_text(candidate):
                            self._last_assistant_text = candidate.strip()
                            self._log_message(role="assistant", content=self._last_assistant_text)
                            self._wf.update_from_assistant(self._last_assistant_text, self._wf_state)
                            self._set_workflow_step(reason="llm_stream")
                            self._append_history("assistant", self._last_assistant_text)
                            self._trim_history()
                            assistant_history_appended = True
                        await self.send_event(
                            {
                                "type": "assistant_token",
                                "text": candidate,
                                "final": False,
                                "utterance_id": self._current_utterance_id,
                            }
                        )
                        assistant_text += candidate
                        spoken_text += candidate
                        tts_buffer += candidate

                        if candidate and self._should_flush_tts(tts_buffer, candidate[-1]):
                            # Humanize and add prosody before sending to TTS
                            tts_buffer = self._humanize_response(tts_buffer, language=language)
                            tts_buffer = self._add_prosody_hints(tts_buffer, self._emotional_state)
                            tts_buffer = self._normalize_branding_text(tts_buffer)
                            log_event(
                                logger,
                                "tts_input",
                                session_id=self._session_id,
                                turn_id=self._current_turn_id,
                                chars=len(tts_buffer),
                                source="llm_stream",
                            )
                            if not self._tts_pending:
                                self._tts_pending = True
                                self._tts_start_ts = time.time()
                                self._barge_in_armed = True
                            await tts.send_text(tts_buffer)
                            tts_buffer = ""
                        continue

                    # After gate release: stream tokens normally
                    await self.send_event(
                        {
                            "type": "assistant_token",
                            "text": token,
                            "final": False,
                            "utterance_id": self._current_utterance_id,
                        }
                    )
                    assistant_text += token
                    spoken_text += token
                    tts_buffer += token

                    if self._should_flush_tts(tts_buffer, token):
                        # Humanize and add prosody before sending to TTS
                        tts_buffer = self._humanize_response(tts_buffer, language=language)
                        tts_buffer = self._add_prosody_hints(tts_buffer, self._emotional_state)
                        tts_buffer = self._normalize_branding_text(tts_buffer)
                        log_event(
                            logger,
                            "tts_input",
                            session_id=self._session_id,
                            turn_id=self._current_turn_id,
                            chars=len(tts_buffer),
                            source="llm_stream",
                        )
                        await tts.send_text(tts_buffer)
                        tts_buffer = ""

                # If stream ended before gate released, flush what we have.
                if not gate_released and gate_buffer.strip():
                    candidate = self._sanitize_placeholders(gate_buffer.strip())
                    candidate = self._dedupe_repeated_sentences(candidate)

                    reason = self._policy_disallows_assistant_text(candidate)
                    if reason:
                        candidate = self._policy_fallback_response(user_text)
                        candidate = self._sanitize_placeholders(candidate)
                        candidate = self._dedupe_repeated_sentences(candidate)
                    candidate = self._normalize_branding_text(candidate)

                    self._update_policy_from_assistant(candidate)
                    if not utterance_emitted:
                        await self._emit_timeline_event(
                            "agent_utterance_created",
                            utterance_id=self._current_utterance_id,
                            text=candidate,
                        )
                        utterance_emitted = True
                    if (not assistant_history_appended) and candidate.strip() and not self._is_duplicate_assistant_text(candidate):
                        self._last_assistant_text = candidate.strip()
                        self._log_message(role="assistant", content=self._last_assistant_text)
                        self._wf.update_from_assistant(self._last_assistant_text, self._wf_state)
                        self._set_workflow_step(reason="llm_stream_flush")
                        self._append_history("assistant", self._last_assistant_text)
                        self._trim_history()
                        assistant_history_appended = True
                    await self.send_event(
                        {
                            "type": "assistant_token",
                            "text": candidate,
                            "final": False,
                            "utterance_id": self._current_utterance_id,
                        }
                    )
                    assistant_text += candidate
                    spoken_text += candidate
                    tts_buffer += candidate

                # Flush remaining TTS buffer
                if tts_buffer.strip():
                    # Humanize and add prosody before sending to TTS
                    tts_buffer = self._humanize_response(tts_buffer, language=language)
                    tts_buffer = self._add_prosody_hints(tts_buffer, self._emotional_state)
                    tts_buffer = self._normalize_branding_text(tts_buffer)
                    log_event(
                        logger,
                        "tts_input",
                        session_id=self._session_id,
                        turn_id=self._current_turn_id,
                        chars=len(tts_buffer),
                        source="llm_stream",
                    )
                    if not self._tts_pending:
                        self._tts_pending = True
                        self._tts_start_ts = time.time()
                        self._barge_in_armed = True
                    await tts.send_text(tts_buffer)
                    tts_buffer = ""

                await tts.end_input()

                # Wait briefly for first audio (avoid hanging the UI on TTS issues)
                try:
                    await asyncio.wait_for(self._tts_audio_received.wait(), timeout=self._tts_first_audio_timeout_s)
                except asyncio.TimeoutError:
                    log_event(
                        logger,
                        "tts_first_audio_timeout",
                        session_id=self._session_id,
                        turn_id=self._current_turn_id,
                        timeout_s=self._tts_first_audio_timeout_s,
                    )

                # Ensure we don't hang forever on a stuck TTS audio stream.
                try:
                    await asyncio.wait_for(audio_task, timeout=max(self._tts_timeout_s, 5.0))
                except asyncio.TimeoutError:
                    log_event(
                        logger,
                        "tts_audio_task_timeout",
                        session_id=self._session_id,
                        turn_id=self._current_turn_id,
                        timeout_s=self._tts_timeout_s,
                    )
                    audio_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await audio_task

                assistant_text = self._normalize_branding_text(assistant_text)
                if utterance_emitted:
                    await self._emit_timeline_event(
                        "agent_tts_end",
                        utterance_id=self._current_utterance_id,
                        status=self._current_utterance_status,
                    )
                assistant_deduped = self._is_duplicate_assistant_text(assistant_text)
                if not assistant_deduped:
                    await self.send_event(
                        {
                            "type": "assistant_final",
                            "text": assistant_text,
                            "utterance_id": self._current_utterance_id,
                        }
                    )
                    await self._emit_chat_message(role="assistant", text=assistant_text)

                    if assistant_text and assistant_text.strip() and not assistant_history_appended:
                        self._last_assistant_text = assistant_text.strip()
                        self._log_message(role="assistant", content=self._last_assistant_text)
                        self._wf.update_from_assistant(self._last_assistant_text, self._wf_state)
                        # Snapshot step after the agent asked its question.
                        self._set_workflow_step(reason="llm_complete")

                log_event(
                    logger,
                    "llm_complete",
                    session_id=self._session_id,
                    turn_id=self._current_turn_id,
                    text=assistant_text,
                    token_count=self._current_llm_token_count,
                )

                if assistant_text and not assistant_deduped:
                    self._append_history("user", user_text)
                    if not assistant_history_appended:
                        self._append_history("assistant", assistant_text)
                    self._trim_history()

                await self.send_event({"type": "status", "state": "listening"})
                self._set_turn_state("WAITING_FOR_USER")
                self._schedule_no_response_watch()

            except asyncio.CancelledError:
                # Preserve what the user actually heard so we don't repeat on the next turn.
                interrupted_text = (spoken_text or "").strip() or (assistant_text or "").strip()
                interrupted_text = self._normalize_branding_text(interrupted_text)
                self._current_utterance_status = "interrupted"
                if utterance_emitted:
                    await self._emit_timeline_event(
                        "agent_tts_end",
                        utterance_id=self._current_utterance_id,
                        status="interrupted",
                    )
                if interrupted_text:
                    if not assistant_history_appended:
                        self._last_assistant_text = interrupted_text
                        self._update_policy_from_assistant(interrupted_text)
                    if not self._is_duplicate_assistant_text(interrupted_text):
                        self._append_history("user", user_text)
                        if not assistant_history_appended:
                            self._append_history("assistant", interrupted_text)
                        self._trim_history()
                        await self.send_event(
                            {
                                "type": "assistant_final",
                                "text": interrupted_text,
                                "interrupted": True,
                                "utterance_id": self._current_utterance_id,
                            }
                        )
                        await self._emit_chat_message(role="assistant", text=interrupted_text)

                audio_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await audio_task

                await self.send_event({"type": "assistant_cancelled"})
                log_event(logger, "llm_cancelled", session_id=self._session_id)
                raise

            except Exception as exc:
                log_event(logger, "llm_error", session_id=self._session_id, error=str(exc))
                # If TTS audio is still running, stop it.
                audio_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await audio_task
                await self.send_event({"type": "error", "message": "LLM generation failed"})

            finally:
                # Always reset speaking flags for next turn.
                self._tts_playing.clear()
                self._barge_in_armed = False

    def _should_flush_tts(self, buffer: str, token: str) -> bool:
        min_size = max(0, self._tts_min_buffer_size)
        flush_len = max(self._tts_stream_chunk_chars, min_size) if min_size else self._tts_stream_chunk_chars
        if len(buffer) >= flush_len:
            return True
        if self._tts_stream_flush_punct and any(ch in token for ch in ".!?।,;:"):
            return len(buffer) >= min_size if min_size else True
        return False

    async def _tts_audio_loop(self, tts: BulbulTTSService) -> None:
        first_chunk = True
        chunk_count = 0
        total_bytes = 0
        try:
            async for chunk in self._stream_with_timeout(
                tts.audio_stream(),
                self._tts_timeout_s,
                "tts_timeout",
            ):
                if not chunk:
                    continue
                if first_chunk:
                    first_chunk = False
                    self._tts_audio_received.set()
                    self._tts_playing.set()
                    self._tts_start_ts = time.time()
                    self._tts_first_chunk_ts = self._tts_start_ts
                    self._barge_in_armed = True
                    self._tts_pending = False
                    self._set_turn_state("AGENT_SPEAKING")
                    await self.send_event({"type": "status", "state": "speaking"})
                    await self._emit_timeline_event(
                        "agent_tts_start",
                        utterance_id=self._current_utterance_id,
                    )
                    log_event(logger, "tts_start", session_id=self._session_id, turn_id=self._current_turn_id)
                    if self._llm_first_token_ts:
                        log_event(
                            logger,
                            "tts_first_chunk_latency",
                            session_id=self._session_id,
                            turn_id=self._current_turn_id,
                            ms=int((self._tts_first_chunk_ts - self._llm_first_token_ts) * 1000),
                        )
                    elif self._llm_start_ts:
                        log_event(
                            logger,
                            "tts_first_chunk_latency",
                            session_id=self._session_id,
                            turn_id=self._current_turn_id,
                            ms=int((self._tts_first_chunk_ts - self._llm_start_ts) * 1000),
                        )
                chunk_count += 1
                total_bytes += len(chunk)
                if self._log_audio_chunks:
                    log_event(
                        logger,
                        "tts_chunk",
                        session_id=self._session_id,
                        turn_id=self._current_turn_id,
                        bytes=len(chunk),
                        chunk_index=chunk_count,
                    )
                await self._send_audio(chunk)
        except ConnectionClosed as exc:
            log_event(
                logger,
                "tts_connection_closed",
                session_id=self._session_id,
                code=getattr(exc, "code", None),
                reason=getattr(exc, "reason", None),
            )
        finally:
            self._tts_playing.clear()
            self._last_tts_end_ts = time.time()
            self._tts_pending = False
            if chunk_count:
                log_event(
                    logger,
                    "tts_end",
                    session_id=self._session_id,
                    turn_id=self._current_turn_id,
                    chunks=chunk_count,
                    bytes=total_bytes,
                )

    def _extract_facts_from_text(self, text: str) -> None:
        """Best-effort extraction of key facts from user utterances.

        Keeps it conservative; LLM is responsible for deeper reasoning.
        """
        import re

        t = (text or "").strip()
        if not t:
            return

        # Name
        m = re.search(r"\b(?:my name is|i am|this is)\s+([A-Za-z][A-Za-z\s\-']{1,40})\b", t, re.IGNORECASE)
        if m and not self._facts.get("customer_name"):
            name = m.group(1).strip(" .,")
            # Avoid capturing generic words.
            if name and name.lower() not in {"hello", "hi", "yes", "okay"}:
                self._facts["customer_name"] = " ".join(w.capitalize() for w in name.split())

        # Amount (₹ / Rs / rupees)
        amt = re.search(r"(?:₹|\brs\.?|\brupees\b)\s*([0-9][0-9,]*(?:\.[0-9]+)?)", t, re.IGNORECASE)
        if amt:
            raw = amt.group(1)
            self._facts["overdue_amount"] = raw.replace(",", "")

        # Date normalization (supports relative + absolute phrases).
        normalized_ptp = self._normalize_ptp_text(t)
        if normalized_ptp:
            self._facts["ptp_date"] = normalized_ptp

        # Callback time (simple: "call me at 5 pm", "callback 14:30")
        if self._facts.get("callback_time") is None:
            if re.search(r"\b(call me|call back|callback|call)\b", t, re.IGNORECASE):
                normalized_callback = self._normalize_callback_text(t)
                if normalized_callback:
                    self._facts["callback_time"] = normalized_callback

        # Reference number (very naive)
        ref = re.search(r"\b(?:ref(?:erence)?\s*(?:no\.?|number)?|utr)\s*[:\-]?\s*([A-Za-z0-9\-]{6,})\b", t, re.IGNORECASE)
        if ref:
            self._facts["reference_number"] = ref.group(1)

        # Language preference / switch requests.
        lang_pref = self._detect_language_switch_request(t)
        if lang_pref:
            self._facts["language_preference"] = lang_pref

        # Personal context for empathy
        if any(w in t for w in ['mother', 'father', 'mom', 'dad', 'parents']):
            self._facts['mentioned_family'] = True
            family_issue = re.search(r'(?:mother|father|mom|dad|parents)[^\.,]*(?:hospital|sick|ill|died|passed)', t, re.I)
            if family_issue:
                self._facts['family_emergency'] = True
        
        if any(w in t for w in ['job', 'work', 'office', 'company']):
            job_loss = re.search(r'(?:job|work)[^\.,]*(?:lost|left|fired|resigned)', t, re.I)
            if job_loss:
                self._facts['job_loss_mentioned'] = True
        
        # Store for future empathy
        if 'salary' in t or 'month' in t:
            salary_match = re.search(r'(?:salary|pay)\s*(?:day|date)?[:\-]?\s*(\d{1,2})', t, re.I)
            if salary_match:
                self._facts['salary_date'] = salary_match.group(1)
        
        # Update emotional state
        self._emotional_state = EmotionAnalyzer.analyze(text, self._emotional_state)

    def _build_context_system_message(self) -> str:
        strategy = self._get_strategy_decision()
        name = self._facts.get("customer_name")
        amt = self._facts.get("overdue_amount")
        due = self._facts.get("due_date")
        ptp = self._facts.get("ptp_date")
        ref = self._facts.get("reference_number")
        lang = self._facts.get("language_preference")

        # IMPORTANT: This is a *system* hint to prevent repetitive greetings and placeholders.
        parts = [
            "You are a TuringEdge collections voice agent.",
            f"The conversation has {'already' if self._has_greeted else 'not yet'} started with an initial greeting.",
            "Do NOT repeat the greeting once it has happened.",
            "Never use placeholders like [Customer's Name]. If a value is unknown, ask a short question to obtain it and then use it consistently.",
            "Do not repeat the same question verbatim twice; if unclear, rephrase or clarify once.",
        ]
        if name:
            parts.append(f"Customer name (confirmed): {name}.")
        if amt:
            parts.append(f"Overdue amount (known): INR {amt}.")
        if due:
            parts.append(f"Due date (known): {due}.")
        if ptp:
            parts.append(f"Promise-to-pay date mentioned: {ptp}.")
        if ref:
            parts.append(f"Payment reference/UTR mentioned: {ref}.")
        if lang:
            parts.append(f"Language preference: {lang}.")
            if str(lang).lower().startswith("hi"):
                parts.append(
                    "Respond in Hindi using Devanagari script unless the customer requests another language. "
                    "Never use Romanized Hindi."
                )
            elif str(lang).lower().startswith("en"):
                parts.append("Respond in English unless the customer requests another language.")
            else:
                parts.append(
                    f"Respond in {self._language_name(lang)} in native script unless the customer requests another language. "
                    "Never use transliterated Roman script."
                )
        if strategy:
            parts.append(f"DPD bucket: {strategy.dpd_bucket}.")
            parts.append(f"Strategy mode: {strategy.strategy_mode}.")
            parts.append(f"Tone profile: {strategy.tone_profile}.")
            parts.append(strategy.instruction)
        
        # Add conversation history context
        history_turns = len([m for m in self._chat_history if m.get("role") in ("user", "assistant")])
        if history_turns > 0:
            parts.append(f"Conversation history: {history_turns} turns of dialogue have occurred. Remember previous exchanges.")
        
        # Add personal context for empathy
        if self._facts.get('family_emergency'):
            parts.append("Customer previously mentioned a family emergency. Be extra empathetic.")
        if self._facts.get('job_loss_mentioned'):
            parts.append("Customer mentioned job loss. Acknowledge difficulty and offer flexible solutions.")
        if self._facts.get('salary_date'):
            parts.append(f"Customer's salary date: {self._facts['salary_date']}. Consider this when discussing payment dates.")
        
        # Add workflow state context for difficult scenarios
        ws = self._wf_state
        if ws.dispute_raised:
            dtype = ws.dispute_type or "general"
            parts.append(
                f"DISPUTE ACTIVE: Customer has raised a {dtype} dispute. "
                "Acknowledge the dispute, do NOT argue. Assure them it will be reviewed. "
                "If they agree to pay any undisputed amount, capture that."
            )
        if ws.legal_hold:
            parts.append(
                "LEGAL HOLD: Customer has mentioned legal proceedings. "
                "STOP all collection activity immediately. Acknowledge politely and close the call. "
                "Do NOT ask for payment."
            )
        if ws.partial_payment_offered:
            amt = ws.partial_amount
            parts.append(
                f"PARTIAL PAYMENT: Customer offered partial payment{f' of INR {amt}' if amt else ''}. "
                "Accept gracefully and ask when they can pay the remainder."
            )
        if ws.emi_restructure_requested:
            parts.append(
                "EMI RESTRUCTURE REQUEST: Customer wants EMI restructuring. "
                "Acknowledge and inform them the team will review and contact with options."
            )
        if ws.document_requested:
            parts.append(
                "DOCUMENT REQUEST: Customer wants loan statement/proof. "
                "Confirm it will be sent to their registered contact."
            )
        if ws.hardship_detected:
            parts.append(
                "HARDSHIP DETECTED: Customer is in financial difficulty. "
                "Be extra empathetic. Offer callback or flexible payment."
            )

        # Add emotional context
        empathy_instruction = EmotionAnalyzer.get_empathy_prompt(self._emotional_state)
        if empathy_instruction:
            parts.append(f"EMOTIONAL CONTEXT: {empathy_instruction}")

        parts.append("Goal: progress the collection conversation logically, remember what the user just said, and avoid repeating questions already answered.")
        parts.append(self._build_policy_system_message())
        return "\n".join(parts)

    def _get_strategy_decision(self):
        if not self._strategy_engine:
            return None
        try:
            return self._strategy_engine.classify(self._facts.get("dpd"))
        except Exception:
            return None

    async def _cancel_generation_locked(self) -> None:
        self._cancel_event.set()
        if self._gen_task and not self._gen_task.done():
            self._gen_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._gen_task
        self._gen_task = None
        self._tts_playing.clear()
        self._tts_pending = False
        self._cancel_event.clear()

    async def _cancel_generation(self) -> None:
        async with self._cancel_lock:
            await self._cancel_generation_locked()

    async def _barge_in(self, reason: str) -> None:
        if self._gen_task and not self._gen_task.done():
            logger.info("Barge-in triggered (%s)", reason)
            await self.send_event(
                {
                    "type": "barge_in",
                    "reason": reason,
                    "fade_ms": 120,
                    "utterance_id": self._reply_to_utterance_id or self._current_utterance_id,
                }
            )
            log_event(logger, "barge_in", session_id=self._session_id, reason=reason)
            self._current_utterance_status = "interrupted"
            await self._emit_timeline_event(
                "barge_in",
                utterance_id=self._reply_to_utterance_id or self._current_utterance_id,
                reason=reason,
            )
            await self._cancel_generation()

    def _append_history(self, role: str, content: str) -> None:
        self._chat_history.append({"role": role, "content": content})
        if self._session_store:
            self._session_store.append(role, content)
            # Persist state after each message exchange
            self._persist_state()

    def _trim_history(self):
        if not self._chat_history:
            return []
        system = self._chat_history[0]
        tail = self._chat_history[1:]
        max_msgs = self._max_history_turns * 2
        if len(tail) > max_msgs:
            tail = tail[-max_msgs:]
        self._chat_history = [system] + tail
        return self._chat_history

    def _sanitize_history_for_llm(self, raw: list) -> tuple[str, list]:
        """Ensure alternating user/assistant messages starting with user."""
        base_system = SYSTEM_PROMPT
        if raw and raw[0].get("role") == "system":
            base_system = raw[0].get("content") or SYSTEM_PROMPT

        tail = [m for m in raw[1:] if m.get("role") in {"user", "assistant"}]
        cleaned: list = []
        last_role: Optional[str] = None
        for m in tail:
            role = m.get("role")
            if role == last_role and cleaned:
                # Replace previous same-role message with the latest.
                cleaned[-1] = m
            else:
                cleaned.append(m)
                last_role = role

        # Ensure the first message is user.
        while cleaned and cleaned[0].get("role") != "user":
            log_event(logger, "history_repair", session_id=self._session_id, action="drop_leading_assistant")
            cleaned.pop(0)

        # Ensure we don't end with a user message before appending the new user turn.
        if cleaned and cleaned[-1].get("role") == "user":
            log_event(logger, "history_repair", session_id=self._session_id, action="drop_trailing_user")
            cleaned.pop()

        return base_system, cleaned

    async def _stream_with_timeout(self, aiter, timeout_s: float, event: str, **kwargs):
        """Iterate an async iterator with a per-item timeout.

        Backward compatible with older call sites.

        Also supports being passed a callable (generator factory) + kwargs.
        This prevents crashes if some code calls:
            self._stream_with_timeout(self.llm.stream_tokens, ..., user_text=..., messages=...)
        """
        if callable(aiter):
            aiter = aiter(**kwargs)

        if timeout_s <= 0:
            async for item in aiter:
                yield item
            return

        iterator = aiter.__aiter__()
        while True:
            try:
                item = await asyncio.wait_for(iterator.__anext__(), timeout=timeout_s)
            except StopAsyncIteration:
                break
            except asyncio.TimeoutError:
                log_event(logger, event, session_id=self._session_id, timeout_s=timeout_s)
                break
            yield item


    async def _run_generation_preview(self, messages, user_text: str, language: Optional[str]) -> None:
        """Preview generation for partials.

        Streams tokens to UI but intentionally does NOT invoke TTS.
        """
        assistant_text = ""
        gate_buffer = ""
        gate_released = False

        # Reset per-turn counters for consistency.
        self._current_llm_text = ""
        self._current_llm_token_count = 0

        try:
            await self.send_event({"type": "status", "state": "thinking"})

            async for token in self._stream_with_timeout(
                self.llm.stream_tokens,
                self._llm_timeout_s,
                "llm_timeout",
                user_text=user_text,
                messages=messages,
                language=language,
            ):
                if self._cancel_event.is_set():
                    raise asyncio.CancelledError()

                if not token:
                    continue

                self._current_llm_text += token
                self._current_llm_token_count += 1

                # Gate the first sentence to block repeats/placeholders early.
                if not gate_released:
                    gate_buffer += token
                    boundary_hit = any(ch in gate_buffer for ch in [".", "?", "!", "।", "\n"]) or len(gate_buffer) >= 320
                    if not boundary_hit:
                        continue

                    candidate = self._sanitize_placeholders(gate_buffer.strip())
                    candidate = self._dedupe_repeated_sentences(candidate)

                    reason = self._policy_disallows_assistant_text(candidate)
                    if reason:
                        candidate = self._policy_fallback_response(user_text)
                        candidate = self._sanitize_placeholders(candidate)
                        candidate = self._dedupe_repeated_sentences(candidate)
                    candidate = self._normalize_branding_text(candidate)

                    gate_released = True
                    await self.send_event({"type": "assistant_token", "text": candidate, "final": False})
                    assistant_text += candidate
                    gate_buffer = ""
                    continue

                await self.send_event({"type": "assistant_token", "text": token, "final": False})
                assistant_text += token

            # Flush any leftover gate buffer
            if not gate_released and gate_buffer.strip():
                candidate = self._sanitize_placeholders(gate_buffer.strip())
                candidate = self._dedupe_repeated_sentences(candidate)

                reason = self._policy_disallows_assistant_text(candidate)
                if reason:
                    candidate = self._policy_fallback_response(user_text)
                    candidate = self._sanitize_placeholders(candidate)
                    candidate = self._dedupe_repeated_sentences(candidate)
                candidate = self._normalize_branding_text(candidate)

                await self.send_event({"type": "assistant_token", "text": candidate, "final": False})
                assistant_text += candidate

            assistant_text = self._normalize_branding_text(assistant_text)
            await self.send_event({"type": "assistant_final", "text": assistant_text, "preview": True})
            await self.send_event({"type": "status", "state": "listening"})

        except asyncio.CancelledError:
            await self.send_event({"type": "assistant_cancelled"})
            raise
        except Exception as exc:
            log_event(logger, "llm_error", session_id=self._session_id, error=str(exc))
            await self.send_event({"type": "error", "message": "LLM generation failed"})

    async def _apply_language_update(self) -> None:
        if not self._pending_stt_language:
            return
        new_lang = self._pending_stt_language
        self._pending_stt_language = None
        if new_lang == self.stt.language:
            return
        self.stt.language = new_lang
        log_event(logger, "stt_language_update", session_id=self._session_id, language=new_lang)
        await self._reconnect_stt()

    # CHANGE: STT reconnect with backoff + timeout.
    async def _reconnect_stt(self) -> None:
        async with self._stt_reconnect_lock:
            try:
                await self.stt.close()
            except Exception:
                pass
            for attempt in range(3):
                try:
                    await asyncio.sleep(0.3 * (attempt + 1))
                    await asyncio.wait_for(self.stt.connect(), timeout=self._stt_connect_timeout_s)
                    self._last_flush_ts = 0.0
                    self._segment_speech_frames = 0
                    self._short_flush_skip_count = 0
                    log_event(logger, "stt_reconnected", session_id=self._session_id, attempt=attempt + 1)
                    return
                except Exception as exc:
                    log_event(
                        logger,
                        "stt_reconnect_error",
                        session_id=self._session_id,
                        attempt=attempt + 1,
                        error=str(exc),
                    )


    async def _watchdog_loop(self) -> None:
        while True:
            await asyncio.sleep(2.0)
            now = time.time()
            if self._audio_frames == 0 and now - self._last_activity_ts > 5.0:
                log_event(
                    logger,
                    "audio_missing",
                    session_id=self._session_id,
                    message="No audio frames received yet from client.",
                )
            elif self._last_audio_ts and now - self._last_audio_ts > 3.0:
                log_event(
                    logger,
                    "audio_gap",
                    session_id=self._session_id,
                    gap_sec=round(now - self._last_audio_ts, 2),
                )

    def _is_likely_echo(self, text: str, transcript: Transcript) -> bool:
        """Heuristic echo detection for laptop-speaker testing.

        If TTS is playing and STT returns content that matches what the assistant is/was saying, suppress it.
        """
        if not self._tts_playing.is_set():
            return False
        now = time.time()
        # Only consider echo suppression near the time TTS is active.
        if self._tts_start_ts and (now - self._tts_start_ts) > 6.0:
            return False

        def norm(s: str) -> str:
            return " ".join((s or "").lower().strip().split())

        t = norm(text)
        if len(t) < 4:
            return False
        # Don't suppress common human short replies; they are often real barge-ins.
        core = [tok for tok in re.sub(r"[^a-z0-9\s]", " ", t).split() if tok]
        human_short = {"hi", "hello", "hey", "yes", "no", "haan", "han", "nahi", "nahin"}
        if core and len(core) <= 2 and any(tok in human_short for tok in core):
            return False

        # Compare against both streaming text and last completed assistant message.
        a_stream = norm(self._current_llm_text)
        a_final = norm(self._last_assistant_text)

        # If STT text is contained in assistant text (or vice-versa), it’s very likely echo.
        if a_stream and (t in a_stream or a_stream in t):
            return True
        if a_final and (t in a_final or a_final in t):
            return True
        return False

    def _is_ambiguous_short_reply(self, text: str) -> bool:
        t = (text or "").strip().lower()
        t = re.sub(r"[^a-z0-9\s]", " ", t)
        tokens = [tok for tok in t.split() if tok]
        if not tokens or len(tokens) > 2:
            return False
        if self._is_yes(text) or self._is_no(text):
            return False
        # Keep clarify for genuinely ambiguous short fillers, not meaningful answers.
        ambiguous = {
            "sorry",
            "pardon",
            "what",
            "huh",
            "hmm",
            "hm",
            "again",
            "repeat",
            "come",
        }
        return all(tok in ambiguous for tok in tokens)

    def _normalize_intent_text(self, text: str) -> str:
        txt = unicodedata.normalize("NFKC", (text or "")).casefold()
        out = []
        for ch in txt:
            if ch.isspace():
                out.append(" ")
                continue
            cat = unicodedata.category(ch)
            if cat[0] in {"L", "N"} or cat in {"Mn", "Mc", "Me"}:
                out.append(ch)
            else:
                out.append(" ")
        return " ".join("".join(out).split())

    def _is_payment_negative_utterance(self, text: str) -> bool:
        t = self._normalize_intent_text(text)
        if not t:
            return False
        if self._is_no(text):
            return True
        negative_phrases = (
            "cannot pay",
            "cant pay",
            "can t pay",
            "cannot make payment",
            "cant make payment",
            "can t make payment",
            "not able to pay",
            "unable to pay",
            "won t pay",
            "wont pay",
            "will not pay",
            "won t be able to",
            "wont be able to",
            "will not be able to",
            "no money",
            "not possible",
            "never",
            "not paid",
            "haven t paid",
            "have not paid",
            "i haven t made",
            "i have not made",
            "i did not make",
            "didn t pay",
            "did not pay",
            "not yet",
            "नहीं",
            "नहि",
            "ना",
            "भुगतान नहीं",
            "भुगतान नही",
            "नहीं किया",
            "नही किया",
            "कर नहीं सकता",
            "कर नही सकता",
            "पैसे नहीं",
            "पैसे नही",
            "பணம் இல்லை",
            "கட்ட முடியாது",
        )
        return any(p in t for p in negative_phrases)

    def _is_low_information_user_text(self, text: str) -> bool:
        t = re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())
        tokens = [tok for tok in t.split() if tok]
        if not tokens:
            return True
        if self._is_yes(text) or self._is_no(text) or self._is_payment_negative_utterance(text):
            return False
        if len(tokens) >= 5:
            return False
        low_info = {
            "hi",
            "hello",
            "hey",
            "ok",
            "okay",
            "hmm",
            "hm",
            "uh",
            "um",
            "sorry",
            "thanks",
            "thankyou",
            "bank",
            "rank",
            "this",
            "is",
        }
        if len(tokens) == 1:
            return tokens[0] in low_info
        return len(tokens) <= 2 and all(tok in low_info for tok in tokens)

    def _is_trivial_followup_final(self, text: str) -> bool:
        return self._is_low_information_user_text(text)

    def _should_keep_existing_pending_final(self, existing_text: str, new_text: str) -> bool:
        if not existing_text:
            return False
        existing_meaningful = not self._is_low_information_user_text(existing_text)
        new_is_low_information = self._is_low_information_user_text(new_text)
        return existing_meaningful and new_is_low_information

    def _is_yes(self, text: str) -> bool:
        t = self._normalize_intent_text(text)
        tokens = [tok for tok in t.split() if tok]
        if not tokens:
            return False
        yes_tokens = {
            "yes",
            "y",
            "yeah",
            "yep",
            "ok",
            "okay",
            "sure",
            "right",
            "correct",
            "affirmative",
            "haan",
            "han",
            "ha",
            "haa",
            "ji",
            "jihaan",
            "हाँ",
            "हां",
            "हाँजी",
            "जीहाँ",
            "हांजी",
            "जी",
            "ஆம்",
            "ஆமாம்",
            "ஆமா",
            "சரி",
            "அமாம்",
            "అవును",
            "హా",
            "ಹೌದು",
            "അതെ",
            "ഹാ",
            "হ্যাঁ",
            "হ্যা",
            "હા",
            "ਹਾਂ",
            "ହଁ",
        }
        no_tokens = {
            "no",
            "nah",
            "nope",
            "nahi",
            "nahin",
            "na",
            "नहीं",
            "नहि",
            "ना",
            "मत",
            "இல்லை",
            "வேண்டாம்",
            "வேணாம்",
            "కాదు",
            "లేదు",
            "ಇಲ್ಲ",
            "ಬೇಡ",
            "ഇല്ല",
            "വേണ്ട",
            "না",
            "নয়",
            "ના",
            "ਨਹੀਂ",
            "ਨਹੀ",
            "ନା",
        }
        if any(tok in no_tokens for tok in tokens):
            return False
        return any(tok in yes_tokens for tok in tokens)

    def _is_no(self, text: str) -> bool:
        t = self._normalize_intent_text(text)
        tokens = [tok for tok in t.split() if tok]
        if not tokens:
            return False
        yes_tokens = {
            "yes",
            "y",
            "yeah",
            "yep",
            "ok",
            "okay",
            "sure",
            "right",
            "correct",
            "affirmative",
            "haan",
            "han",
            "ha",
            "haa",
            "ji",
            "jihaan",
            "हाँ",
            "हां",
            "हाँजी",
            "जीहाँ",
            "हांजी",
            "जी",
            "ஆம்",
            "ஆமாம்",
            "ஆமா",
            "சரி",
            "அமாம்",
            "అవును",
            "హా",
            "ಹೌದು",
            "അതെ",
            "ഹാ",
            "হ্যাঁ",
            "হ্যা",
            "હા",
            "ਹਾਂ",
            "ହଁ",
        }
        no_tokens = {
            "no",
            "n",
            "nah",
            "nope",
            "nahi",
            "nahin",
            "na",
            "नहीं",
            "नहि",
            "ना",
            "मत",
            "இல்லை",
            "வேண்டாம்",
            "வேணாம்",
            "కాదు",
            "లేదు",
            "ಇಲ್ಲ",
            "ಬೇಡ",
            "ഇല്ല",
            "വേണ്ട",
            "না",
            "নয়",
            "ના",
            "નહીં",
            "ਨਹੀਂ",
            "ନା",
        }
        if any(tok in yes_tokens for tok in tokens):
            return False
        return any(tok in no_tokens for tok in tokens)

    def _classify_assistant_intent(self, text: str) -> Optional[str]:
        """Very small intent classifier for policy gating."""
        t = " ".join((text or "").lower().split())
        if not t:
            return None
        if ("aware" in t or "confirm" in t) and ("overdue" in t or "due" in t or "pending payment" in t):
            return "confirm_awareness"
        if (
            "confirm your identity" in t
            or ("identity" in t and "confirm" in t)
            or "am i speaking with" in t
            or "confirm your name" in t
            or "may i confirm your name" in t
        ):
            return "confirm_identity"
        if "have you made the payment" in t or ("payment" in t and "made" in t):
            return "ask_payment_made"
        if ("commit" in t and "payment date" in t) or ("payment date" in t and "able" in t):
            return "ask_ptp_date"
        if ("transaction" in t and "details" in t) or "utr" in t or "reference number" in t:
            return "ask_utr"
        return None

    def _update_policy_from_assistant(self, assistant_text: str) -> None:
        intent = self._classify_assistant_intent(assistant_text)
        self._policy["pending_intent"] = intent
        if intent and intent in self._policy["asked"]:
            self._policy["asked"][intent] = True

    def _update_policy_from_user(self, user_text: str) -> None:
        pending = self._policy.get("pending_intent")
        if not pending:
            return

        if pending == "confirm_awareness":
            if self._is_yes(user_text):
                self._policy["confirmed"]["awareness"] = True
            elif self._is_no(user_text):
                self._policy["confirmed"]["awareness"] = False

        if pending == "confirm_identity":
            if self._is_yes(user_text):
                self._policy["confirmed"]["identity"] = True
            elif self._is_no(user_text):
                self._policy["confirmed"]["identity"] = False

        if pending == "ask_payment_made":
            if self._is_yes(user_text):
                self._policy["confirmed"]["payment_made"] = True
            elif self._is_no(user_text):
                self._policy["confirmed"]["payment_made"] = False

        # Clear once we observed a response to the assistant's last question.
        self._policy["pending_intent"] = None

    def _build_policy_system_message(self) -> str:
        c = self._policy.get("confirmed", {})
        lines = [
            "POLICY (strict): Ask ONE question at a time. Do not repeat questions already answered.",
            "Never output placeholders like [amount], [date], [Customer's Name]. If unknown, ask to obtain it and then use it consistently.",
            "Never invent or hallucinate amounts or dates. Use only the values provided in context; if missing, ask for them.",
        ]
        if c.get("awareness") is True:
            lines.append("User has CONFIRMED awareness of the overdue payment. Do NOT ask awareness-confirmation again.")
        if c.get("identity") is True:
            lines.append("User identity is CONFIRMED. Do NOT ask identity confirmation again.")
        pm = c.get("payment_made")
        if pm is True:
            lines.append("User says payment is made. Next question should request UTR/reference number and date.")
        elif pm is False:
            lines.append("User says payment is NOT made. Next question should request commitment/payment date or best callback time.")
        amt = self._facts.get("overdue_amount")
        due = self._facts.get("due_date")
        if amt:
            lines.append(f"Known overdue amount: INR {amt}. Use it exactly.")
        if due:
            lines.append(f"Known due date: {due}. Use it exactly.")
        return "\n".join(lines)

    def _normalize_branding_text(self, text: Optional[str]) -> str:
        t = text or ""
        if not t:
            return ""
        # Hard-normalize all spoken branding to TuringEdge.
        return re.sub(r"\bkredit[\s\-]*bee\b", "TuringEdge", t, flags=re.IGNORECASE)

    def _has_consent_prompt(self, text: Optional[str]) -> bool:
        t = (text or "").strip()
        if not t:
            return False
        if _CONSENT_PROMPT_RE.search(t):
            return True
        t_norm = self._normalize_for_dedupe(t)
        if "do i have your consent to continue" in t_norm:
            return True
        # Be tolerant to minor ASR / copy variants to avoid double-speaking consent.
        has_recording_hint = "record" in t_norm or "quality" in t_norm or "qualit" in t_norm
        has_consent_hint = "consent" in t_norm or "permission" in t_norm or "permiss" in t_norm
        has_continue_hint = "continue" in t_norm or "proceed" in t_norm
        return has_recording_hint and has_consent_hint and has_continue_hint

    def _strip_consent_like_fragments(self, text: str) -> str:
        """Remove consent-like fragments from greeting text.

        This protects against legacy or malformed greeting strings where the
        consent line is already present with slight wording/typos.
        """
        if not text:
            return ""
        # Keep punctuation boundaries simple and deterministic.
        parts = re.split(r"(?<=[\.\!\?])\s+|\n+", text)
        kept: list[str] = []
        for part in parts:
            p = (part or "").strip()
            if not p:
                continue
            p_norm = self._normalize_for_dedupe(p)
            if not p_norm:
                continue
            if "do i have your consent to continue" in p_norm:
                continue
            if "do i have your permission to continue" in p_norm:
                continue

            # Common malformed/ASR variants.
            if p_norm.startswith("this call may") and ("record" in p_norm or "qualit" in p_norm):
                continue
            if p_norm.startswith("do i have your") and ("continue" in p_norm or "proceed" in p_norm):
                if "consent" in p_norm or "permiss" in p_norm:
                    continue

            has_consent_hint = "consent" in p_norm or "permission" in p_norm or "permiss" in p_norm
            has_recording_hint = "record" in p_norm or "quality" in p_norm or "qualit" in p_norm
            has_continue_hint = "continue" in p_norm or "proceed" in p_norm
            if has_consent_hint and (has_recording_hint or has_continue_hint):
                continue
            kept.append(p)
        return " ".join(kept).strip()

    def _ensure_consent_prompt_once(self, text: Optional[str]) -> str:
        t = (text or "").strip()
        if not t:
            return _CONSENT_PROMPT
        # Remove all consent prompt variants, then append exactly one canonical copy.
        stripped = _CONSENT_PROMPT_RE.sub(" ", t).strip()
        stripped = self._strip_consent_like_fragments(stripped)
        stripped = re.sub(r"\s+", " ", stripped)
        stripped = re.sub(r"\s+([,.;:!?])", r"\1", stripped)
        stripped = stripped.rstrip(". ")

        if stripped:
            return stripped + ". " + _CONSENT_PROMPT
        return _CONSENT_PROMPT

    def _sanitize_placeholders(self, text: str) -> str:
        """Replace obvious placeholders with known facts, if available."""
        t = text or ""
        amt = self._facts.get("overdue_amount")
        due = self._facts.get("due_date")

        if amt:
            t = (
                t.replace("₹[amount]", f"₹{amt}")
                .replace("[amount]", str(amt))
                .replace("INR [amount]", f"INR {amt}")
                .replace("Rs [amount]", f"Rs {amt}")
            )
        if due:
            t = t.replace("[date]", str(due)).replace("as of [date]", f"as of {due}")
        return self._normalize_branding_text(t)

    def _normalize_for_dedupe(self, text: str) -> str:
        t = (text or "").strip().lower()
        if not t:
            return ""
        t = re.sub(r"[^a-z0-9\s]", " ", t)
        return " ".join(t.split())

    def _is_duplicate_user_text(self, text: str) -> bool:
        norm = self._normalize_for_dedupe(text)
        if not norm:
            return False
        now = time.time()
        if norm == self._last_user_text_norm and (now - self._last_user_text_ts) < self._dedupe_window_s:
            return True
        self._last_user_text_norm = norm
        self._last_user_text_ts = now
        return False

    def _is_duplicate_assistant_text(self, text: str) -> bool:
        norm = self._normalize_for_dedupe(text)
        if not norm:
            return False
        now = time.time()
        if norm == self._last_assistant_text_norm and (now - self._last_assistant_text_ts) < self._dedupe_window_s:
            return True
        self._last_assistant_text_norm = norm
        self._last_assistant_text_ts = now
        return False

    def _contains_placeholders(self, text: str) -> bool:
        t = (text or "")
        return any(x in t for x in ["[amount]", "₹[amount]", "[date]", "[Customer", "[customer", "[name]"])

    def _policy_disallows_assistant_text(self, first_sentence: str) -> Optional[str]:
        """Return a reason string if we should block this output."""
        # Block placeholder leakage.
        if self._contains_placeholders(first_sentence):
            return "placeholder_leak"

        intent = self._classify_assistant_intent(first_sentence)
        c = self._policy.get("confirmed", {})
        if intent == "confirm_awareness" and c.get("awareness") is True:
            return "repeat_awareness"
        if intent == "confirm_identity" and c.get("identity") is True:
            return "repeat_identity"

        # Block immediate repeats of what we just said.
        def norm(s: str) -> str:
            return " ".join((s or "").lower().split())

        if norm(first_sentence) and norm(first_sentence) == norm(self._last_assistant_text):
            return "repeat_last"
        return None

    def _policy_fallback_response(self, user_text: str) -> str:
        """If we blocked the model's first sentence, produce a safe deterministic response."""
        # Prefer continuing the flow without repeats.
        c = self._policy.get("confirmed", {})
        amt = self._facts.get("overdue_amount")
        due = self._facts.get("due_date")

        if c.get("awareness") is True:
            if c.get("payment_made") is True:
                return "Thanks. Please share the transaction reference/UTR and payment date so I can confirm it."
            if c.get("payment_made") is False:
                return "Okay. By when can you make the payment? Please share a date or a time I can call you back."
            # Payment made not answered yet.
            return "Okay. Have you made the payment? If yes, please share the transaction details. If not, can you commit to a payment date?"
        # If awareness not confirmed yet, ask with known facts if available.
        if amt and due:
            return f"Thank you. Are you aware that your loan payment of ₹{amt} is overdue as of {due}?"
        if amt:
            return f"Thank you. Are you aware that your loan payment of ₹{amt} is overdue?"
        if due:
            return f"Thank you. Are you aware that your loan payment is overdue as of {due}?"
        return "Thank you. Are you aware of the overdue payment on your TuringEdge loan?"

    def _dedupe_repeated_sentences(self, text: str) -> str:
        """Remove consecutive duplicate sentences/questions."""
        t = (text or "").strip()
        if not t:
            return t
        # Split on sentence enders while keeping them.
        parts = re.split(r"(?<=[\.!\?।])\s+", t)
        out = []
        last_norm = None
        for p in parts:
            pn = " ".join(p.lower().split())
            if pn and pn == last_norm:
                continue
            out.append(p)
            last_norm = pn
        return " ".join(out).strip()

    def _humanize_response(self, text: str, language: Optional[str] = None) -> str:
        """Add natural disfluencies and filler words to make speech sound human.
        Only apply to non-critical compliance statements.
        """
        lang = self._canonical_language_code(language) or self._resolve_output_language()
        if lang and lang.lower().startswith("hi"):
            # English fillers make Hindi responses sound broken/romanized.
            return text

        # Don't modify if contains critical compliance info
        critical_patterns = [r'\b\d{6,}\b', r'₹\s*\d+', r'UTR', r'reference number']
        if any(re.search(p, text, re.I) for p in critical_patterns):
            return text
        
        fillers = ["um", "uh", "you know", "like", "so", "well"]
        hesitations = ["let me see", "just a moment", "okay so"]
        
        # 30% chance to add filler at start
        if random.random() < 0.3:
            text = f"{random.choice(hesitations).capitalize()}, {text[0].lower()}{text[1:]}"
        
        # 20% chance to add mid-sentence filler
        sentences = re.split(r'(?<=[.!?])\s+', text)
        if len(sentences) > 1 and random.random() < 0.2:
            insert_pos = random.randint(0, len(sentences) - 2)
            sentences[insert_pos] = sentences[insert_pos].rstrip('.') + f", {random.choice(fillers)}."
            text = ' '.join(sentences)
        
        return text

    def _should_backchannel(self, text: str, transcript: Transcript) -> Optional[str]:
        """Generate short acknowledgments during user speech.
        Only for long utterances or when user pauses mid-thought.
        """
        # Only on partials, not finals
        if transcript.is_final:
            return None
        
        words = len(text.split())
        if words < 8:  # Too short for backchannel
            return None
        
        # Don't backchannel too frequently (max once per 10 seconds)
        now = time.time()
        if now - self._last_backchannel_ts < 10:
            return None
        
        backchannels = [
            "I see", "right", "okay", "got it", "understood",
            "makes sense", "alright", "sure"
        ]
        
        self._last_backchannel_ts = now
        return random.choice(backchannels)

    async def _send_backchannel(self, text: str) -> None:
        """Send a quick acknowledgment without interrupting STT flow."""
        await self.send_event({"type": "backchannel", "text": text})
        # Don't add to history - transient acknowledgment

    def _detect_misunderstanding(self, user_text: str, last_assistant_text: str) -> Optional[str]:
        """Detect if user is correcting or confused by previous agent message."""
        t = user_text.lower()
        bound_step = (
            self._reply_to_step_id
            or self._pending_step_id
            or self._wf_state.last_agent_intent
            or self._wf_state.current_step
        )

        if bound_step in {"ask_payment_made", "ask_ptp_or_callback", "confirm_awareness"} and self._is_payment_negative_utterance(user_text):
            return None
        if bound_step in {
            "consent",
            "confirm_identity",
            "confirm_awareness",
            "ask_payment_made",
            "ask_reference_number",
            "ask_ptp_or_callback",
        } and (self._is_yes(user_text) or self._is_no(user_text)):
            return None
        if self._detect_language_switch_request(user_text):
            return None
        
        confusion_signals = [
            r'what\??', r'what do you mean', r'i didn\'t understand', 
            r'not clear', r'confused', r'repeat', r'again\??',
            r'क्या', r'समझा नहीं', r'दोबारा', r'फिर से'
        ]
        
        correction_signals = [
            r'no,? i said', r'actually', r'i meant',
            r'wrong', r'incorrect', r'गलत'
        ]
        
        for pattern in confusion_signals:
            if re.search(pattern, t):
                return "confusion"
        for pattern in correction_signals:
            if re.search(pattern, t):
                return "correction"

        # Semantic mismatch detection
        if last_assistant_text:
            uncertain_phrases = (
                "not sure",
                "don't know",
                "dont know",
                "cannot say",
                "can't say",
                "cant say",
                "not decided",
                "maybe",
            )
            if any(p in t for p in uncertain_phrases):
                return None
            # If user response is completely unrelated to question asked
            asked_about_payment = any(w in last_assistant_text.lower() 
                                      for w in ['pay', 'payment', 'amount', '₹'])
            payment_relevant_terms = [
                'pay', 'payment', 'money', 'amount', 'rupee', '₹', 'date', 'when',
                'tomorrow', 'today', 'next', 'week', 'month', 'monday', 'tuesday',
                'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
                'callback', 'call', 'later', 'am', 'pm', 'aware', 'awareness',
            ]
            has_date_or_time = bool(
                re.search(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b", t)
                or re.search(r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b", t)
            )
            user_talks_something_else = not (
                any(w in t for w in payment_relevant_terms) or has_date_or_time
            )
            
            if asked_about_payment and user_talks_something_else and len(t.split()) > 3:
                return "topic_drift"
        
        return None

    async def _handle_repair(self, repair_type: str, user_text: str) -> Optional[str]:
        """Generate appropriate repair response."""
        repairs = {
            "confusion": "I apologize for the confusion. Let me rephrase that more clearly.",
            "correction": "I see, thank you for the correction. Let me note that down.",
            "topic_drift": "I understand. Before we get to that, could we quickly clarify the payment aspect? Then I'm happy to discuss the other matter."
        }
        
        # For confusion, actually rephrase using context
        if repair_type == "confusion":
            # Simplify last question
            return repairs[repair_type] + " " + self._simplify_last_question()
        
        return repairs.get(repair_type)

    def _simplify_last_question(self) -> str:
        """Simplify the last question asked for clarification."""
        # Extract core intent from last agent message
        if self._policy.get("confirmed", {}).get("payment_made") is None:
            return "Have you had a chance to make the payment yet?"
        if not self._facts.get('ptp_date') and not self._policy.get("confirmed", {}).get("payment_made"):
            return "When do you think you can make the payment?"
        return "Could you help me understand your current situation?"

    async def _graceful_interrupt(self, reason: str) -> None:
        """Save state and acknowledge interruption before canceling."""
        if not (self._tts_playing.is_set() or self._tts_pending):
            return
        
        # Quick acknowledgment of interruption
        interrupt_acknowledgments = [
            "Sorry, go ahead.",
            "Yes, please.",
            "I'm listening.",
            "Please continue."
        ]
        ack = random.choice(interrupt_acknowledgments)
        
        # Tell the client to fade out audio and clear its queue.
        await self.send_event(
            {
                "type": "barge_in",
                "reason": reason,
                "fade_ms": 120,
                "utterance_id": self._reply_to_utterance_id or self._current_utterance_id,
            }
        )
        self._current_utterance_status = "interrupted"
        await self._emit_timeline_event(
            "barge_in",
            utterance_id=self._reply_to_utterance_id or self._current_utterance_id,
            reason=reason,
        )
        # Send acknowledgment event (don't speak it, just UI)
        await self.send_event({"type": "interrupt_acknowledged", "text": ack})
        
        # Save what we were going to say for potential resumption
        self._interrupted_response = self._current_llm_text
        self._interrupted_at = time.time()
        
        log_event(logger, "graceful_interrupt", session_id=self._session_id,
                  saved_chars=len(self._current_llm_text),
                  reason=reason)
        
        await self._cancel_generation()

    def _should_resume_interrupted(self) -> Optional[str]:
        """Check if we should resume a previous interrupted response."""
        # Only resume if interruption was recent (< 30s) and we had substantial content
        if time.time() - self._interrupted_at > 30:
            return None
        
        if len(self._interrupted_response) < 20:
            return None
        
        # Check if user asked us to continue
        return self._interrupted_response

    async def _handle_post_interrupt(self, user_text: str) -> Optional[str]:
        """Handle follow-up after interruption."""
        # If user asks us to continue what we were saying
        continue_signals = ['continue', 'go on', 'what were you saying', 
                           'you were saying', 'aur batao', 'continue karo']
        
        if any(s in user_text.lower() for s in continue_signals):
            resume = self._should_resume_interrupted()
            if resume:
                return f"As I was saying, {resume}"
        
        # If user changed subject, acknowledge and move on
        return None

    def _calculate_drift_tolerance(self) -> int:
        """How many off-topic turns allowed before firm redirection."""
        base_tolerance = 1
        
        # More tolerant if customer is stressed
        if self._emotional_state.stress_level > 0.6:
            base_tolerance += 1
        
        # Less tolerant if already have payment commitment
        if self._facts.get('ptp_date') or self._policy.get("confirmed", {}).get("payment_made"):
            base_tolerance = 0
        
        return base_tolerance

    async def _handle_topic_drift(self, user_text: str, current_step: str) -> Optional[str]:
        """Allow brief human conversation but track toward goal."""
        # If we've drifted too many times, firm redirect
        tolerance = self._calculate_drift_tolerance()
        
        if self._drift_count >= tolerance:
            self._drift_count = 0
            return self._gentle_redirect_to_goal(current_step)
        
        # Check if this is off-topic
        is_off_topic = self._is_off_topic(user_text, current_step)
        
        if is_off_topic:
            self._drift_count = self._drift_count + 1
            
            # Brief acknowledgment then steer back
            acknowledgments = [
                "I understand. By the way, ",
                "Thanks for sharing. Just to wrap up on the payment - ",
                "Got it. Quick question on the overdue amount - "
            ]
            return random.choice(acknowledgments) + self._get_step_question(current_step)
        
        return None

    def _is_off_topic(self, text: str, current_step: str) -> bool:
        """Detect if user is going off-topic."""
        payment_keywords = ['pay', 'payment', 'amount', 'money', 'date', 'when', 
                           'tomorrow', 'next week', 'salary', 'account', 'utr']
        
        # If discussing payment-related things, not off-topic
        if any(k in text.lower() for k in payment_keywords):
            return False
        
        # If personal/family issues (common in collections), allow but track
        personal_topics = ['job', 'work', 'family', 'health', 'hospital', 
                          'mother', 'father', 'wife', 'husband', 'child']
        
        if any(t in text.lower() for t in personal_topics):
            return True  # Off-topic but empathetically relevant
        
        return True

    def _gentle_redirect_to_goal(self, step: str) -> str:
        """Firm but polite redirect when drift tolerance exceeded."""
        redirects = [
            "I appreciate you sharing that. To help resolve this today, ",
            "I understand your situation. To move forward, ",
            "Thank you for explaining. Let's focus on finding a solution - "
        ]
        return random.choice(redirects) + self._get_step_question(step)

    def _get_step_question(self, step: str) -> str:
        """Get appropriate question for current step."""
        questions = {
            'confirm_identity': "may I confirm your name please?",
            'confirm_awareness': "are you aware there's an overdue payment?",
            'ask_payment_plan': "have you made the payment, or when can you make it?",
            'ask_ptp': "what date works for you to make this payment?",
            'ask_callback': "what time works best for me to call you back?"
        }
        return questions.get(step, "can we discuss the payment?")

    def _should_self_correct(self, text: str, spoken_sofar: str) -> Optional[str]:
        """Detect if we should correct ourselves mid-sentence."""
        # If we catch a factual error in what we're saying
        known_amount = self._facts.get('overdue_amount')
        mentioned_amount = re.search(r'₹\s*(\d[\d,]+)', spoken_sofar)
        
        if mentioned_amount and known_amount:
            mentioned_clean = mentioned_amount.group(1).replace(',', '')
            known_clean = known_amount.replace(',', '')
            if mentioned_clean != known_clean:
                return f"Actually, I apologize - the amount is ₹{known_amount}, not what I just said."
        
        return None

    async def _inject_correction(self, correction: str, tts_service) -> None:
        """Pause and correct ourselves."""
        await tts_service.send_text(correction)
        log_event(logger, "self_correction", session_id=self._session_id, 
                  correction=correction)

    def _add_prosody_hints(self, text: str, emotion: EmotionalState) -> str:
        """Add subtle pauses and emphasis for more natural speech.
        Sarvam Bulbul may or may not support SSML, so use textual cues.
        """
        # Add micro-pauses (represented as commas or ellipses)
        # After key information
        text = re.sub(r'(₹\d+)', r'\1,', text)
        
        # Before important questions
        text = re.sub(r'(\w+)\s*\?\s*$', r'\1...?', text)
        
        # Emphasize urgency if needed but stressed customer
        if emotion.stress_level > 0.6:
            # Soften the message
            text = text.replace("must", "would really help if you could")
            text = text.replace("immediately", "as soon as possible")
        
        # Add breathing space for long sentences
        if len(text) > 100 and ',' not in text:
            # Find a good breaking point
            words = text.split()
            if len(words) > 15:
                mid = len(words) // 2
                text = ' '.join(words[:mid]) + ', ' + ' '.join(words[mid:])
        
        return text

    def _select_varied_greeting(self) -> str:
        """Rotate through natural greetings instead of fixed text."""
        # Use a session-scoped RNG; do not mutate global random state.
        rng = random.Random(hash(self._session_id) + int(time.time()) // 3600)

        if self.greeting_text:
            greeting = self._normalize_branding_text(self.greeting_text.strip())
        else:
            greetings = [
                "Hello, this is TuringEdge calling. Do you have a quick moment to discuss your loan?",
                "Hi, I'm calling from TuringEdge about your outstanding payment. Is now a good time?",
                "Good {time_of_day}, this is TuringEdge collections. Can we quickly go over your payment status?",
                "Hello, this is TuringEdge. I'm reaching out about a pending payment - do you have two minutes?"
            ]
            hour = time.localtime().tm_hour
            time_of_day = "morning" if 5 <= hour < 12 else \
                          "afternoon" if 12 <= hour < 17 else "evening"
            greeting = rng.choice(greetings).format(time_of_day=time_of_day)
        
        # Add slight personalization if name known
        if self._facts.get('customer_name'):
            greeting = greeting.replace("Hello", f"Hello {self._facts['customer_name']}")

        # If consent is required and not yet captured, append consent line.
        if self._wf_state.consent is not True:
            greeting = self._ensure_consent_prompt_once(greeting)

        return self._normalize_branding_text(greeting)

    def _persist_state(self) -> None:
        """Persist current state (facts, policy) to session store."""
        if not self._session_store:
            return
        state = {
            "facts": self._facts,
            "policy": self._policy,
            "has_greeted": self._has_greeted,
        }
        try:
            self._session_store.save_state(state)
        except Exception as exc:
            log_event(logger, "state_persist_error", session_id=self._session_id, error=str(exc))
