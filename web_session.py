import asyncio
import contextlib
import logging
import random
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

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

logger = logging.getLogger(__name__)

SendEvent = Callable[[dict], Awaitable[None]]
SendAudio = Callable[[bytes], Awaitable[None]]


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
    ) -> None:
        self.stt = stt_service
        self.llm = llm_service
        self.tts_ws_url = tts_ws_url
        self.tts_api_key = tts_api_key
        self.tts_voice = tts_voice
        self.tts_model = tts_model
        self.tts_speaker = tts_speaker
        self.greeting_text = greeting_text
        # CHANGE: Conversation memory (history + optional persistence).
        self._max_history_turns = max(1, max_history_turns)
        self._chat_history = [{"role": "system", "content": SYSTEM_PROMPT}]
        self._session_id = uuid.uuid4().hex[:12]
        self._session_store = SessionStore(session_store_path, self._session_id) if session_store_path else None
        self._dynamic_stt_language = dynamic_stt_language
        self._pending_stt_language: Optional[str] = None
        self._preview_partials = preview_partials
        self._preview_after_s = max(0, preview_after_ms) / 1000.0
        self._preview_active = False
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
        self._barge_in_grace_s: float = 0.25  # ignore barge-in immediately after TTS starts
        self._barge_in_min_speech_frames: int = 2  # require a few consecutive "speech" frames
        self._vad_speech_frames: int = 0
        self._barge_in_armed: bool = False  # one-shot per assistant speech turn
        self._vad_barge_task: Optional[asyncio.Task] = None
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

        # Demo integrations
        self._audit_store = audit_store
        self._excel_sink = excel_sink
        self._action_router = action_router
        self._knowledge_store = knowledge_store
        self._session_registry = session_registry
        self._log_redact_pii = get_env_bool("LOG_REDACT_PHI", True)
        self._greeting_started = False
        self._greeting_active = False
        self._turn_state: str = "IDLE"
        self._no_response_task: Optional[asyncio.Task] = None
        self._last_question_ts: float = 0.0

        # Deterministic workflow engine
        self._wf = WorkflowEngine()
        self._wf_state = WorkflowState()
        if not get_env_bool("ENABLE_CONSENT", True):
            self._wf_state.consent = True
        else:
            # For demos, make the very first spoken message include consent capture,
            # so the customer's first response can be interpreted deterministically.
            if self.greeting_text:
                gt = self.greeting_text.strip()
                if "consent" not in gt.lower() and "record" not in gt.lower():
                    self.greeting_text = gt.rstrip(". ") + ". This call may be recorded for quality. Do I have your consent to continue?"
        self._wf_state.current_step = self._wf.compute_next_step(self._wf_state)

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
        self._last_speech_ts = 0.0  # Initialize to 0, will be set when speech detected
        self._audio_frames = 0
        self._audio_bytes = 0
        self._has_sent_audio = False
        self._current_llm_text = ""
        self._current_llm_token_count = 0
        self._watchdog_task: Optional[asyncio.Task] = None
        self._stt_reconnect_lock = asyncio.Lock()
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
                    if self._speech_start_ts is not None:
                        log_event(
                            logger,
                            "vad_segment",
                            session_id=self._session_id,
                            duration_ms=int((time.time() - self._speech_start_ts) * 1000),
                        )
                        self._speech_start_ts = None
                    await self._emit_timeline_event("user_speech_end")
                    if self._dynamic_stt_language and self._pending_stt_language:
                        await self._apply_language_update()
                    # Flush once on silence transition to finalize STT.
                    if (self.stt.flush_signal or getattr(self.stt, "use_sdk", False)) and self._has_sent_audio:
                        now = time.time()
                        if now - self._last_flush_ts >= self._flush_min_gap_s:
                            try:
                                await self.stt.flush()
                                self._last_flush_ts = now
                                log_event(logger, "stt_flush", session_id=self._session_id, reason="silence")
                            except Exception as exc:
                                log_event(
                                    logger,
                                    "stt_flush_error",
                                    session_id=self._session_id,
                                    reason="silence",
                                    error=str(exc),
                                )
        else:
            self._silent_frames = 0
            self._vad_speech_frames += 1
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
                # Cancel pending finalization if user starts speaking again
                if self._finalize_task and not self._finalize_task.done():
                    log_event(logger, "finalize_cancelled", session_id=self._session_id, reason="user_speaking")
                    self._finalize_task.cancel()
                    self._pending_final = None
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

        lang = language or self._facts.get("language_preference") or getattr(self.stt, "language", None)

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
        self._update_policy_from_user(t)
        reply_step = self._pending_step_id or self._wf_state.last_agent_intent or self._wf_state.current_step
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
            self._facts["language_preference"] = str(updated["language_preference"]).strip()
        if updated.get("dpd") is not None:
            self._facts["dpd"] = updated.get("dpd")
        if updated.get("risk_band") is not None:
            self._facts["risk_band"] = updated.get("risk_band")

        # Optionally update STT language for subsequent audio, if dynamic language is enabled.
        if self._dynamic_stt_language and self._facts.get("language_preference"):
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
            except Exception:
                pass
        if self._audit_store:
            try:
                self._audit_store.record_event(
                    event_type="message",
                    session_id=self._session_id,
                    payload={"role": role, "content_redacted": redacted},
                )
            except Exception:
                pass
        if self._session_registry is not None:
            try:
                self._session_registry[self._session_id] = self.get_snapshot()
            except Exception:
                pass

    async def _emit_chat_message(self, *, role: str, text: str) -> None:
        """Send canonical chat message event to the UI."""
        # Disabled: UI now relies on transcript (user) + assistant_final (agent) only.
        return
        t = (text or "").strip()
        if not t:
            return
        try:
            await self.send_event({"type": "chat_message", "role": role, "text": t})
        except Exception:
            pass

    def _set_turn_state(self, state: str) -> None:
        self._turn_state = state

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
            except Exception:
                pass
        if self._audit_store:
            try:
                self._audit_store.upsert_outcome(
                    session_id=self._session_id,
                    customer_id=str(self._facts.get("customer_id") or "") or None,
                    disposition=self._wf_state.disposition,
                    ptp_date=ptp,
                    callback_time=cb,
                )
            except Exception:
                pass

    def _sync_workflow_from_facts(self) -> None:
        if self._facts.get("ptp_date"):
            self._wf_state.ptp_date = self._facts.get("ptp_date")
        if self._facts.get("callback_time"):
            self._wf_state.callback_time = self._facts.get("callback_time")
        if self._facts.get("reference_number"):
            self._wf_state.reference_number = self._facts.get("reference_number")


    def get_snapshot(self) -> dict:
        """Safe-ish session snapshot for supervisor/demo views."""
        return {
            "session_id": self._session_id,
            "customer_id": self._facts.get("customer_id"),
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
            "stress": round(float(self._emotional_state.stress_level), 3),
            "sentiment": self._emotional_state.sentiment,
            "last_user_text": self._redact(self._last_user_text) if self._last_user_text else "",
            "last_assistant_text": self._redact(self._last_assistant_text) if self._last_assistant_text else "",
            "last_activity_ts": round(float(self._last_activity_ts), 3),
        }

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
            self._wf_state.current_step = self._wf.compute_next_step(self._wf_state)

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
                        ptp_date=self._wf_state.ptp_date,
                        callback_time=self._wf_state.callback_time,
                        disposition=self._wf_state.disposition,
                    )
                    self._audit_store.record_event(event_type="action", session_id=self._session_id, payload={"name": name, "payload": payload, "result": {"ok": True}, "ok": True})
                except Exception:
                    pass
            return {"ok": True, "ptp_date": self._wf_state.ptp_date, "callback_time": self._wf_state.callback_time}

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
                    self._audit_store.upsert_outcome(session_id=self._session_id, customer_id=customer_id, escalations_inc=1)
                    self._audit_store.record_event(event_type="action", session_id=self._session_id, payload={"name": name, "payload": payload, "result": result, "ok": True})
                except Exception:
                    pass
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
        if disp in {"closed", "no_consent"}:
            self._wf_state.current_step = "closing"
        else:
            self._wf_state.current_step = self._wf.compute_next_step(self._wf_state)

        if self._audit_store:
            try:
                self._audit_store.upsert_outcome(
                    session_id=self._session_id,
                    customer_id=str(self._facts.get("customer_id") or "") or None,
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
        await self.send_event({"type": "supervisor_update", "disposition": disp})

    def _should_barge_in_from_vad(self) -> bool:
        """Guard against false barge-in due to speaker echo / noise."""
        now = time.time()
        # If we don't have a TTS start timestamp yet, don't barge-in.
        if not self._tts_start_ts:
            return False
        # Grace window after TTS starts.
        if (now - self._tts_start_ts) < self._barge_in_grace_s:
            return False
        # Require a few consecutive frames above threshold (reduces single-frame spikes).
        if self._vad_speech_frames < self._barge_in_min_speech_frames:
            return False
        return True

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

                    if self._dynamic_stt_language and transcript.language:
                        if transcript.language != self.stt.language:
                            self._pending_stt_language = transcript.language
                            log_event(
                                logger,
                                "stt_language_detected",
                                session_id=self._session_id,
                                language=transcript.language,
                            )
                            if self._in_silence:
                                await self._apply_language_update()

                    now = time.time()
                    # CHANGE: Preview on partials to reduce latency.
                    if transcript.is_final:
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
                                await self._run_fixed_turn(
                                    assistant_text="Sorry, I didn’t catch that. Could you repeat?",
                                    language=transcript.language,
                                    step="clarify",
                                    update_workflow=False,
                                )
                                continue
                        token_count = len([t for t in (text or "").strip().split() if t])
                        if not binary_step and token_count <= 2 and not (self._is_yes(text) or self._is_no(text)):
                            await self._run_fixed_turn(
                                assistant_text="Sorry, I didn’t catch that. Could you repeat?",
                                language=transcript.language,
                                step="clarify",
                                update_workflow=False,
                            )
                            continue
                        if self._greeting_active and (self._tts_playing.is_set() or self._tts_pending):
                            t_norm = " ".join(text.lower().strip().split())
                            if t_norm in {"hi", "hello", "hey", "ok", "okay", "yes"}:
                                log_event(logger, "greeting_ack_ignored", session_id=self._session_id, text=text)
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
                        await self._emit_chat_message(role="user", text=text)
                        self._log_message(role="user", content=text)
                        self._extract_facts_from_text(text)
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
                            self._wf_state.current_step = self._wf.compute_next_step(self._wf_state)
                        # Clear reply binding once consumed.
                        self._reply_to_step_id = None
                        self._reply_to_turn_id = None
                        self._sync_workflow_from_facts()
                        self._persist_commitments()
                        self._persist_state()  # Persist state after extracting facts
                        self._preview_active = False
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
                    if (
                        self._preview_partials
                        and not self._preview_active
                        and self._speech_start_ts is not None
                        and (now - self._speech_start_ts) >= self._preview_after_s
                        and (self._gen_task is None or self._gen_task.done())
                    ):
                        self._preview_active = True
                        log_event(logger, "preview_start", session_id=self._session_id, text=text)
                        await self._start_generation(text, transcript, preview=True)
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
        log_event(
            logger,
            "schedule_final_generation",
            session_id=self._session_id,
            text=text[:50],
            has_pending=bool(self._pending_final),
            has_task=bool(self._finalize_task and not self._finalize_task.done()),
        )
        self._pending_final = (text, transcript, epoch)
        if self._finalize_task and not self._finalize_task.done():
            self._finalize_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._finalize_task
        self._finalize_task = asyncio.create_task(self._finalize_pending_final(), name="finalize_pending_final")

    async def _finalize_pending_final(self) -> None:
        """Wait for sustained silence before responding.
        
        This method waits for a pause period, but checks periodically if the user
        has started speaking again. If new speech is detected, it cancels the response.
        """
        pause_start_ts = time.time()
        last_speech_at_start = self._last_speech_ts
        
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
            # Only cancel if speech timestamp is significantly newer (more than 200ms after we started)
            time_since_start = time.time() - pause_start_ts
            if self._last_speech_ts > last_speech_at_start and time_since_start > 0.2:
                # User started speaking again after we began waiting, cancel response
                log_event(
                    logger,
                    "finalize_cancelled",
                    session_id=self._session_id,
                    reason="user_speaking",
                    silence_duration_ms=int(time_since_start * 1000),
                )
                self._pending_final = None
                return
        
        # After the full pause period, proceed with response
        # Don't require _in_silence to be True - the pause timer is sufficient
        # VAD silence detection has its own delay, so we can't rely on it here
        if not self._pending_final:
            return
        
        # Final check: only cancel if user spoke AFTER we started waiting (not before)
        # The pause period itself is sufficient - we don't need to check recent speech
        # because if the user spoke during the pause, we would have caught it in the loop above
        time_since_last_speech = time.time() - self._last_speech_ts
        # Only cancel if speech happened very recently AND after we started waiting
        # This catches cases where user started speaking just as we were about to respond
        if time_since_last_speech < 0.1 and self._last_speech_ts > pause_start_ts:
            log_event(
                logger,
                "finalize_cancelled",
                session_id=self._session_id,
                reason="recent_speech_after_wait",
                ms_since_speech=int(time_since_last_speech * 1000),
            )
            self._pending_final = None
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
            next_step = self._wf.compute_next_step(self._wf_state)
            self._wf_state.current_step = next_step
            if not preview:
                self._set_pending_step(next_step)
            if not preview and next_step in {
                "consent",
                "confirm_identity",
                "confirm_awareness",
                "ask_payment_made",
                "ask_reference_number",
                "ask_ptp_or_callback",
                "closing",
            }:
                fixed = self._fixed_prompt_for_step(next_step)
                self._wf.update_from_assistant(fixed, self._wf_state)
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
            language = transcript.language
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
            next_step = self._wf.compute_next_step(self._wf_state)
            self._wf_state.current_step = next_step
            if not preview:
                self._set_pending_step(next_step)
            if not preview and next_step in {
                "consent",
                "confirm_identity",
                "confirm_awareness",
                "ask_payment_made",
                "ask_reference_number",
                "ask_ptp_or_callback",
                "closing",
            }:
                fixed = self._fixed_prompt_for_step(next_step)
                self._wf.update_from_assistant(fixed, self._wf_state)
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
            # Log emotional state
            log_event(
                logger,
                "emotion_state",
                session_id=self._session_id,
                stress=self._emotional_state.stress_level,
                sentiment=self._emotional_state.sentiment,
                refusals=self._emotional_state.consecutive_refusals,
            )
            self._gen_task = asyncio.create_task(
                self._run_generation(messages=messages, user_text=text, language=language, preview=preview),
                name="generation",
            )

    async def _start_tts_only(self, text: str) -> None:
        async with self._cancel_lock:
            await self._cancel_generation_locked()
            log_event(logger, "greeting_start", session_id=self._session_id, text=text)
            self._gen_task = asyncio.create_task(
                self._run_tts_only(text=text),
                name="greeting_tts",
            )

    async def _run_tts_only(self, text: str) -> None:
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
                self._wf_state.current_step = self._wf.compute_next_step(self._wf_state)
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
                self._greeting_active = False
                raise
            finally:
                self._tts_playing.clear()
                self._tts_pending = False
                self._barge_in_armed = False
                self._current_utterance_status = "completed"

            self._barge_in_armed = False

    def _fixed_prompt_for_step(self, step: str) -> str:
        """Deterministic prompts for key workflow steps (no LLM)."""
        step = (step or "").strip()
        name = self._facts.get("customer_name")
        amt = self._facts.get("overdue_amount")
        due = self._facts.get("due_date")
        if step == "consent":
            return "This call may be recorded for quality. Do I have your consent to continue?"
        if step == "confirm_identity":
            if name:
                return f"Am I speaking with {name}?"
            return "May I confirm your name?"
        if step == "confirm_awareness":
            if (
                self._wf_state.last_asked_step == "confirm_awareness"
                and time.time() - self._wf_state.last_asked_ts < 15
            ):
                if amt:
                    return f"Just to confirm, you’re aware of the pending payment of ₹{amt}, correct?"
                return "Just to confirm, you’re aware of the pending payment, correct?"
            if amt and due:
                return f"Are you aware that your loan payment of ₹{amt} is overdue as of {due}?"
            if amt:
                return f"Are you aware that your loan payment of ₹{amt} is overdue?"
            if due:
                return f"Are you aware that your loan payment is overdue as of {due}?"
            return "Are you aware of the overdue payment on your KreditBee loan?"
        if step == "ask_payment_made":
            if (
                self._wf_state.last_asked_step == "ask_payment_made"
                and time.time() - self._wf_state.last_asked_ts < 15
            ):
                if amt:
                    return f"Just to confirm, have you already paid the ₹{amt}? A simple yes or no is fine."
                return "Just to confirm, have you already made the payment? A simple yes or no is fine."
            if amt:
                return f"Have you already made the payment of ₹{amt}?"
            return "Have you already made the payment?"
        if step == "ask_reference_number":
            if (
                self._wf_state.last_asked_step == "ask_reference_number"
                and time.time() - self._wf_state.last_asked_ts < 15
            ):
                return (
                    "If you have already paid, please share the transaction reference or UTR and the payment date. "
                    "If you have not paid, just let me know."
                )
            return "Please share the transaction reference number or UTR and the date of payment."
        if step == "ask_ptp_or_callback":
            if (
                self._wf_state.last_asked_step == "ask_ptp_or_callback"
                and time.time() - self._wf_state.last_asked_ts < 15
            ):
                if amt:
                    return f"If you can't pay now, when can you make the payment of ₹{amt}, or what time should I call back?"
                return "If you can't pay now, when can you make the payment, or what time should I call back?"
            if amt:
                return f"When would you be able to make the payment of ₹{amt}?"
            return "When would you be able to make the payment?"
        if step == "closing":
            if self._wf_state.disposition == "no_consent" or self._wf_state.consent is False:
                return "Understood. I will not continue without your consent. Thank you."
            if self._wf_state.reference_number:
                return "Thanks. Please allow me some time to verify the transaction reference. We will update you if needed."
            if self._wf_state.ptp_date:
                return f"Thanks. Noted your commitment to pay by {self._wf_state.ptp_date}. Please ensure the payment is done by then."
            if self._wf_state.callback_time:
                return f"Thanks. I will call you back at {self._wf_state.callback_time}."
            return "Thanks for your time. We will follow up as needed."
        # Shouldn't happen for fixed steps, but keep safe.
        return "One moment, please."

    def _build_runtime_user_instruction(self, *, step: str, user_text: str) -> str:
        """Wrap the customer utterance with strict step instructions for the LLM."""
        amt = self._facts.get("overdue_amount")
        due = self._facts.get("due_date")
        base = [
            "You are a KreditBee collections agent. Follow the collections workflow strictly.",
            "Ask ONLY ONE clear question.",
            "Do NOT greet. Do NOT repeat a question already answered.",
            "Do NOT ask for OTP/CVV/card numbers/passwords/bank details.",
            f"Current workflow step: {step}.",
        ]
        if amt:
            base.append(f"Known overdue amount: INR {amt}. Use it exactly if mentioned.")
        if due:
            base.append(f"Known due date: {due}. Use it exactly if mentioned.")

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
        assistant_history_appended = False
        if update_workflow:
            self._wf_state.last_agent_intent = step
            self._wf_state.last_asked_step = step
            self._wf_state.last_asked_ts = time.time()
        self._current_utterance_id = self._next_utterance_id()
        self._current_utterance_status = "completed"
        await self._emit_timeline_event(
            "agent_utterance_created",
            utterance_id=self._current_utterance_id,
            text=assistant_text,
        )
        if not self._is_duplicate_assistant_text(assistant_text):
            self._last_assistant_text = assistant_text.strip()
            self._log_message(role="assistant", content=self._last_assistant_text)
            if update_workflow:
                self._wf.update_from_assistant(self._last_assistant_text, self._wf_state)
                self._wf_state.current_step = self._wf.compute_next_step(self._wf_state)
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
                if not self._is_duplicate_assistant_text(assistant_text):
                    await self.send_event(
                        {
                            "type": "assistant_final",
                            "text": assistant_text,
                            "source": f"fixed:{step}",
                            "utterance_id": self._current_utterance_id,
                        }
                    )
                    if not assistant_history_appended:
                        self._last_assistant_text = assistant_text.strip()
                        self._log_message(role="assistant", content=self._last_assistant_text)
                        if update_workflow:
                            self._wf.update_from_assistant(self._last_assistant_text, self._wf_state)
                            self._wf_state.current_step = self._wf.compute_next_step(self._wf_state)
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
                if not self._is_duplicate_assistant_text(assistant_text):
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

                        gate_released = True
                        gate_buffer = ""

                        self._update_policy_from_assistant(candidate)
                        
                        # Humanize and add prosody hints
                        candidate = self._humanize_response(candidate)
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
                            self._wf_state.current_step = self._wf.compute_next_step(self._wf_state)
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
                            tts_buffer = self._humanize_response(tts_buffer)
                            tts_buffer = self._add_prosody_hints(tts_buffer, self._emotional_state)
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
                        tts_buffer = self._humanize_response(tts_buffer)
                        tts_buffer = self._add_prosody_hints(tts_buffer, self._emotional_state)
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
                        self._wf_state.current_step = self._wf.compute_next_step(self._wf_state)
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
                    tts_buffer = self._humanize_response(tts_buffer)
                    tts_buffer = self._add_prosody_hints(tts_buffer, self._emotional_state)
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
                        self._wf_state.current_step = self._wf.compute_next_step(self._wf_state)

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

        # Dates (simple dd/mm/yyyy or dd-mm-yyyy or dd/mm)
        dt = re.search(r"\b(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\b", t)
        if dt:
            self._facts["ptp_date"] = dt.group(1)
        elif not self._facts.get("ptp_date"):
            if re.search(r"\b(tomorrow|next week|next monday|today evening|salary day)\b", t, re.IGNORECASE):
                self._facts["ptp_date"] = t.strip()

        # Callback time (simple: "call me at 5 pm", "callback 14:30")
        if self._facts.get("callback_time") is None:
            if re.search(r"\b(call me|call back|callback|call)\b", t, re.IGNORECASE):
                tm = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", t, re.IGNORECASE)
                if tm:
                    hh = tm.group(1)
                    mm = tm.group(2) or "00"
                    ap = (tm.group(3) or "").lower()
                    self._facts["callback_time"] = f"{hh}:{mm} {ap}".strip()

        # Reference number (very naive)
        ref = re.search(r"\b(?:ref(?:erence)?\s*(?:no\.?|number)?|utr)\s*[:\-]?\s*([A-Za-z0-9\-]{6,})\b", t, re.IGNORECASE)
        if ref:
            self._facts["reference_number"] = ref.group(1)

        # Language preference
        if re.search(r"\b(hindi|hinglish)\b", t, re.IGNORECASE):
            self._facts["language_preference"] = "hi-IN"
        elif re.search(r"\b(english)\b", t, re.IGNORECASE):
            self._facts["language_preference"] = "en-IN"

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
        name = self._facts.get("customer_name")
        amt = self._facts.get("overdue_amount")
        due = self._facts.get("due_date")
        ptp = self._facts.get("ptp_date")
        ref = self._facts.get("reference_number")
        lang = self._facts.get("language_preference")

        # IMPORTANT: This is a *system* hint to prevent repetitive greetings and placeholders.
        parts = [
            "You are a KreditBee collections voice agent.",
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
        
        # Add emotional context
        empathy_instruction = EmotionAnalyzer.get_empathy_prompt(self._emotional_state)
        if empathy_instruction:
            parts.append(f"EMOTIONAL CONTEXT: {empathy_instruction}")
        
        parts.append("Goal: progress the collection conversation logically, remember what the user just said, and avoid repeating questions already answered.")
        parts.append(self._build_policy_system_message())
        return "\n".join(parts)

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

                await self.send_event({"type": "assistant_token", "text": candidate, "final": False})
                assistant_text += candidate

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

        # Compare against both streaming text and last completed assistant message.
        a_stream = norm(self._current_llm_text)
        a_final = norm(self._last_assistant_text)

        # If STT text is contained in assistant text (or vice-versa), it’s very likely echo.
        if a_stream and (t in a_stream or a_stream in t):
            return True
        if a_final and (t in a_final or a_final in t):
            return True
        return False

    def _is_yes(self, text: str) -> bool:
        t = (text or "").strip().lower()
        t = re.sub(r"[^a-z0-9\s]", " ", t)
        tokens = [tok for tok in t.split() if tok]
        if not tokens:
            return False
        yes_tokens = {"yes", "y", "yeah", "yep", "ok", "okay", "sure", "haan", "han", "ha", "haa", "ji", "jihaan"}
        no_tokens = {"no", "nah", "nope", "nahi", "nahin", "na", "not"}
        if any(tok in no_tokens for tok in tokens):
            return False
        return any(tok in yes_tokens for tok in tokens)

    def _is_no(self, text: str) -> bool:
        t = (text or "").strip().lower()
        t = re.sub(r"[^a-z0-9\s]", " ", t)
        tokens = [tok for tok in t.split() if tok]
        if not tokens:
            return False
        yes_tokens = {"yes", "y", "yeah", "yep", "ok", "okay", "sure", "haan", "han", "ha", "haa", "ji", "jihaan"}
        no_tokens = {"no", "n", "nah", "nope", "nahi", "nahin", "na", "not"}
        if any(tok in yes_tokens for tok in tokens):
            return False
        return any(tok in no_tokens for tok in tokens)

    def _classify_assistant_intent(self, text: str) -> Optional[str]:
        """Very small intent classifier for policy gating."""
        t = " ".join((text or "").lower().split())
        if not t:
            return None
        if ("aware" in t or "confirm" in t) and ("overdue" in t or "due" in t) and "kreditbee" in t:
            return "confirm_awareness"
        if "confirm your identity" in t or ("identity" in t and "confirm" in t):
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
        return t

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
        return "Thank you. Are you aware of the overdue payment on your KreditBee loan?"

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

    def _humanize_response(self, text: str) -> str:
        """Add natural disfluencies and filler words to make speech sound human.
        Only apply to non-critical compliance statements.
        """
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
        
        confusion_signals = [
            r'what\??', r'what do you mean', r'i didn\'t understand', 
            r'not clear', r'confused', r'repeat', r'again\??',
            r'क्या', r'समझा नहीं', r'दोबारा', r'फिर से'
        ]
        
        correction_signals = [
            r'no,? i said', r'actually', r'i meant', r'not', 
            r'wrong', r'incorrect', r'नहीं', r'गलत'
        ]
        
        for pattern in confusion_signals:
            if re.search(pattern, t):
                return "confusion"
        for pattern in correction_signals:
            if re.search(pattern, t):
                return "correction"
        
        # Semantic mismatch detection
        if last_assistant_text:
            # If user response is completely unrelated to question asked
            asked_about_payment = any(w in last_assistant_text.lower() 
                                      for w in ['pay', 'payment', 'amount', '₹'])
            user_talks_something_else = not any(w in t 
                                               for w in ['pay', 'money', 'amount', 'rupee', '₹'])
            
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
        # Seed with session ID for consistency within session
        random.seed(hash(self._session_id) + int(time.time()) // 3600)
        
        greetings = [
            "Hello, this is KreditBee calling. Do you have a quick moment to discuss your loan?",
            "Hi, I'm calling from KreditBee about your outstanding payment. Is now a good time?",
            "Good {time_of_day}, this is KreditBee collections. Can we quickly go over your payment status?",
            "Hello, this is KreditBee. I'm reaching out about a pending payment - do you have two minutes?"
        ]
        
        hour = time.localtime().tm_hour
        time_of_day = "morning" if 5 <= hour < 12 else \
                      "afternoon" if 12 <= hour < 17 else "evening"
        
        greeting = random.choice(greetings).format(time_of_day=time_of_day)
        
        # Add slight personalization if name known
        if self._facts.get('customer_name'):
            greeting = greeting.replace("Hello", f"Hello {self._facts['customer_name']}")

        # If consent is required and not yet captured, append consent line.
        if self._wf_state.consent is not True:
            greeting = greeting.rstrip(". ") + ". This call may be recorded for quality. Do I have your consent to continue?"

        return greeting

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
