import asyncio
import contextlib
import logging
import time
from typing import Optional

from audio_io import FRAME_MS, mic_stream, play_audio, rms_energy
from logging_utils import log_event
from sarvam_llm_service import SarvamLLMService, SYSTEM_PROMPT
from sarvam_stt_service import SaarikaSTTService, Transcript
from sarvam_tts_service import BulbulTTSService
from websockets.exceptions import ConnectionClosed
from session_store import SessionStore

logger = logging.getLogger(__name__)


class CallSession:
    def __init__(
        self,
        stt_service: SaarikaSTTService,
        llm_service: SarvamLLMService,
        tts_ws_url: str,
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
        audio_queue_max: int = 50,
        use_sdk: bool = True,
        tts_stream_chunk_chars: int = 30,
        tts_stream_flush_punct: bool = True,
        tts_min_buffer_size: int = 50,
        tts_max_chunk_length: int = 150,
        tts_output_audio_codec: str = "linear16",
        tts_output_audio_bitrate: Optional[str] = None,
    ) -> None:
        self.stt = stt_service
        self.llm = llm_service
        self.tts_ws_url = tts_ws_url
        self.tts_api_key = tts_api_key
        self.tts_voice = tts_voice
        self.tts_model = tts_model
        self.tts_speaker = tts_speaker
        self.greeting_text = greeting_text
        # Conversation memory (history + optional persistence)
        self._max_history_turns = max(1, max_history_turns)

        # Enterprise memory (facts / slots)
        self._facts = {
            "customer_name": None,
            "overdue_amount": None,
            "due_date": None,
            "ptp_date": None,
            "reference_number": None,
            "language_preference": None,
        }

        # Enterprise state machine (what has already been confirmed)
        self._state = {
            "identity_confirmed": False,
            "awareness_confirmed": False,
            "payment_done": False,
            "ptp_captured": False,
            "callback_captured": False,
        }
        self._last_agent_intent: Optional[str] = None  # e.g. "confirm_awareness", "confirm_identity", "ask_ptp", "ask_callback"
        self._pending_agent_intent: Optional[str] = None  # intent for current/last outgoing question (survives barge-in/cancel)
        self._has_greeted = False

        self._chat_history = [{"role": "system", "content": SYSTEM_PROMPT}]
        self._session_id = f"cli-{id(self)}"
        self._session_store = SessionStore(session_store_path, self._session_id) if session_store_path else None

        if self._session_store:
            prior = self._session_store.load()
            if prior:
                self._chat_history = [{"role": "system", "content": SYSTEM_PROMPT}] + prior
                self._trim_history()

                # If assistant already spoke earlier, greeting has happened
                self._has_greeted = any(
                    m.get("role") == "assistant" for m in self._chat_history[1:]
                )

        # Build dynamic system prompt with context
        self._refresh_system_prompt()

        self._vad_threshold = vad_rms_threshold
        self._silence_frames_required = max(1, int(vad_silence_ms / FRAME_MS))
        self._silent_frames = 0
        self._in_silence = True
        self._stt_flush_interval = max(0, stt_flush_interval_ms) / 1000.0
        self._last_flush_ts = 0.0
        self._speech_start_ts: Optional[float] = None
        self._first_partial_logged = False
        self._has_sent_audio = False
        self._flush_min_gap_s = max(0.05, self._stt_flush_interval) if self._stt_flush_interval > 0 else 0.2
        self._last_stt_ts = time.time()

    async def run(self) -> None:
        # CHANGE: STT connect timeout for robustness.
        await asyncio.wait_for(self.stt.connect(), timeout=self._stt_connect_timeout_s)
        self._speaker_task = asyncio.create_task(self._speaker_loop(), name="speaker")
        self._mic_task = asyncio.create_task(self._mic_loop(), name="mic")
        self._stt_task = asyncio.create_task(self._stt_loop(), name="stt")
        log_event(logger, "session_start", session_id=self._session_id)
        if self.greeting_text:
            asyncio.create_task(self._start_tts_only(self.greeting_text), name="greeting")

        tasks = [self._speaker_task, self._mic_task, self._stt_task]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()

    async def stop(self) -> None:
        await self._cancel_generation()
        for task in [self._mic_task, self._stt_task, self._speaker_task]:
            if task and not task.done():
                task.cancel()
        for task in [self._mic_task, self._stt_task, self._speaker_task]:
            if task:
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        await self.stt.close()
        log_event(logger, "session_stop", session_id=self._session_id)

    async def _mic_loop(self) -> None:
        async for frame in mic_stream():
            rms = rms_energy(frame)
            if rms < self._vad_threshold:
                self._silent_frames += 1
                if self._silent_frames >= self._silence_frames_required:
                    if not self._in_silence:
                        self._in_silence = True
                        log_event(logger, "vad_speech_end", session_id=self._session_id)
                        self._preview_active = False
                        if self._speech_start_ts is not None:
                            log_event(
                                logger,
                                "vad_segment",
                                session_id=self._session_id,
                                duration_ms=int((time.time() - self._speech_start_ts) * 1000),
                            )
                            self._speech_start_ts = None
                    if self._dynamic_stt_language and self._pending_stt_language:
                        await self._apply_language_update()
                    # Flush once on silence transition to finalize STT.
                    if (self.stt.flush_signal or getattr(self.stt, "use_sdk", False)) and self._has_sent_audio:
                        now = asyncio.get_running_loop().time()
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
                if self._in_silence and self._tts_playing.is_set():
                    asyncio.create_task(self._barge_in("vad"))
                if self._in_silence:
                    self._speech_start_ts = time.time()
                    self._first_partial_logged = False
                    log_event(logger, "vad_speech_start", session_id=self._session_id)
                self._in_silence = False
            if (
                (not getattr(self.stt, "use_sdk", False))
                and self._stt_flush_interval > 0
                and self._has_sent_audio
            ):
                now = asyncio.get_running_loop().time()
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

            await self.stt.send_audio(frame)
            self._has_sent_audio = True

    async def _stt_loop(self) -> None:
        log_event(logger, "stt_stream_open", session_id=self._session_id)
        try:
            async for transcript in self.stt.transcript_stream():
                self._last_stt_ts = time.time()
                text = transcript.text.strip()
                if not text:
                    continue
                if text == self._last_transcript_text:
                    continue
                self._last_transcript_text = text

                if self._tts_playing.is_set():
                    await self._barge_in("stt")

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
                if transcript.is_final:
                    self._preview_active = False
                    await self._start_generation(text, transcript, preview=False)
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
        except Exception as exc:
            log_event(logger, "stt_stream_error", session_id=self._session_id, error=str(exc))
            raise

    # CHANGE: Optional preview generation on partials.
    async def _start_generation(self, text: str, transcript: Transcript, preview: bool = False) -> None:
        async with self._cancel_lock:
            await self._cancel_generation_locked()
            language = transcript.language
            log_event(logger, "llm_start", session_id=self._session_id, text=text, language=language)
            # Extract facts from user speech and refresh system context
            self._extract_facts_from_text(text)
            # Update state machine from user's reply (e.g., "yes" should satisfy the last asked question)
            self._update_state_from_user_reply(text)

            if self._dynamic_stt_language and self._facts.get("language_preference"):
                pref = self._facts.get("language_preference")
                if pref and pref != self.stt.language:
                    self._pending_stt_language = pref
                    if self._in_silence:
                        await self._apply_language_update()

            self._refresh_system_prompt()

            messages = list(self._trim_history())
            if messages and messages[-1].get("role") == "user":
                log_event(logger, "history_repair", session_id=self._session_id, action="drop_trailing_user")
                messages = messages[:-1]

            
            # Deterministic next-step guidance to prevent the model from looping.
            next_step = self._compute_next_step()

            # Lock intent so next yes/no maps correctly even after barge-in
            if next_step in ("confirm_identity", "confirm_awareness"):
                self._pending_agent_intent = next_step

            # HARD ROUTE — do NOT use LLM for confirmations (this kills repetition forever)
            if not preview and next_step == "confirm_identity":
                if self._facts.get("customer_name"):
                    self._state["identity_confirmed"] = True
                else:
                    self._append_history("user", text)
                    self._gen_task = asyncio.create_task(
                        self._run_fixed_turn(
                            assistant_text="May I confirm your name?",
                            intent="confirm_identity",
                            language=language,
                        ),
                        name="fixed_confirm_identity",
                    )
                    return

            if not preview and next_step == "confirm_awareness":
                if not self._state.get("awareness_confirmed", False):
                    self._append_history("user", text)
                    self._gen_task = asyncio.create_task(
                        self._run_fixed_turn(
                            assistant_text="Are you aware that your KreditBee payment is overdue?",
                            intent="confirm_awareness",
                            language=language,
                        ),
                        name="fixed_confirm_awareness",
                    )
                    return

            # Normal LLM flow for all other steps
            runtime_instruction = self._build_runtime_user_instruction(next_step)
            user_payload = f"{runtime_instruction}\n\nCustomer said: {text}"
            messages.append({"role": "user", "content": user_payload})
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
            audio_task = asyncio.create_task(self._tts_audio_loop(tts), name="tts_greeting_audio")
            try:
                log_event(
                    logger,
                    "tts_input",
                    session_id=self._session_id,
                    chars=len(text),
                    source="greeting",
                )
                await tts.send_text(text)
                await tts.end_input()
                await audio_task
                log_event(logger, "greeting_end", session_id=self._session_id)
                self._has_greeted = True
                self._refresh_system_prompt()
            except asyncio.CancelledError:
                audio_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await audio_task
                log_event(logger, "greeting_cancelled", session_id=self._session_id)
                raise
            finally:
                self._tts_playing.clear()

    async def _run_fixed_turn(self, assistant_text: str, intent: Optional[str], language: Optional[str]) -> None:
        """Deterministic question without LLM to prevent looping confirmations."""

        if intent:
            self._pending_agent_intent = intent

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
            audio_task = asyncio.create_task(self._tts_audio_loop(tts), name="tts_fixed_audio")
            try:
                await tts.send_text(assistant_text)
                await tts.end_input()
                await audio_task

                if intent:
                    self._last_agent_intent = intent
                    self._pending_agent_intent = None

                self._append_history("assistant", assistant_text)
                self._refresh_system_prompt()
                self._trim_history()

            except asyncio.CancelledError:
                audio_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await audio_task
                raise
            finally:
                self._tts_playing.clear()

    # CHANGE: Full-history LLM calls + timeout wrapper.
    async def _run_generation(self, messages, user_text: str, language: Optional[str], preview: bool = False) -> None:
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
            audio_task = asyncio.create_task(self._tts_audio_loop(tts), name="tts_audio")
            assistant_text = ""
            tts_buffer = ""
            try:
                async for token in self._stream_with_timeout(
                    self.llm.stream_tokens(messages=messages, language=language),
                    self._llm_timeout_s,
                    "llm_timeout",
                ):
                    assistant_text += token
                    tts_buffer += token
                    if self._should_flush_tts(tts_buffer, token):
                        log_event(
                            logger,
                            "tts_input",
                            session_id=self._session_id,
                            chars=len(tts_buffer),
                        )
                        await tts.send_text(tts_buffer)
                        tts_buffer = ""
                if tts_buffer.strip():
                    log_event(
                        logger,
                        "tts_input",
                        session_id=self._session_id,
                        chars=len(tts_buffer),
                    )
                    await tts.send_text(tts_buffer)
                await tts.end_input()
                await audio_task
                if assistant_text and not preview:
                    # Lock intent for the question we just asked (even if regex intent inference fails)
                    if self._pending_agent_intent:
                        self._last_agent_intent = self._pending_agent_intent

                    self._append_history("user", user_text)
                    self._append_history("assistant", assistant_text)

                    # Track what the agent just asked so "yes/no" can be interpreted next turn
                    self._update_state_from_assistant(assistant_text)

                    # Clear pending intent once we successfully produced an assistant turn
                    self._pending_agent_intent = None

                    if not self._has_greeted:
                        self._has_greeted = True

                    self._refresh_system_prompt()
                    self._trim_history()
            except asyncio.CancelledError:
                audio_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await audio_task
                raise
            except Exception as exc:
                log_event(logger, "llm_error", session_id=self._session_id, error=str(exc))
            finally:
                self._tts_playing.clear()

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
        try:
            async for chunk in self._stream_with_timeout(
                tts.audio_stream(),
                self._tts_timeout_s,
                "tts_timeout",
            ):
                if first_chunk:
                    self._tts_playing.set()
                    first_chunk = False
                    log_event(logger, "tts_start", session_id=self._session_id)
                self._queue_audio(chunk)
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

    async def _speaker_loop(self) -> None:
        while True:
            chunk = await self._audio_queue.get()
            await play_audio(chunk)

    def _queue_audio(self, chunk: bytes) -> None:
        if not chunk:
            return
        try:
            self._audio_queue.put_nowait(chunk)
        except asyncio.QueueFull:
            with contextlib.suppress(asyncio.QueueEmpty):
                _ = self._audio_queue.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                self._audio_queue.put_nowait(chunk)

    async def _flush_audio_queue(self) -> None:
        while True:
            try:
                _ = self._audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def _cancel_generation_locked(self) -> None:
        if self._gen_task and not self._gen_task.done():
            self._gen_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._gen_task
        self._gen_task = None
        await self._flush_audio_queue()
        self._tts_playing.clear()

    async def _cancel_generation(self) -> None:
        async with self._cancel_lock:
            await self._cancel_generation_locked()

    async def _barge_in(self, reason: str) -> None:
        if self._gen_task and not self._gen_task.done():
            logger.info("Barge-in triggered (%s)", reason)
            log_event(logger, "barge_in", session_id=self._session_id, reason=reason)
            await self._cancel_generation()

    def _append_history(self, role: str, content: str) -> None:
        self._chat_history.append({"role": role, "content": content})
        if self._session_store:
            self._session_store.append(role, content)

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

    async def _stream_with_timeout(self, aiter, timeout_s: float, event: str):
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

    async def _reconnect_stt(self) -> None:
        try:
            await self.stt.close()
        except Exception:
            pass
        await asyncio.wait_for(self.stt.connect(), timeout=self._stt_connect_timeout_s)

    def _refresh_system_prompt(self) -> None:
        base = SYSTEM_PROMPT.strip()
        ctx = self._build_context_system_message().strip()
        system_msg = base + "\n\n" + ctx if ctx else base

        if self._chat_history and self._chat_history[0].get("role") == "system":
            self._chat_history[0]["content"] = system_msg
        else:
            self._chat_history = [{"role": "system", "content": system_msg}] + self._chat_history

    def _build_context_system_message(self) -> str:
        name = self._facts.get("customer_name")
        amt = self._facts.get("overdue_amount")
        due = self._facts.get("due_date")
        ptp = self._facts.get("ptp_date")
        ref = self._facts.get("reference_number")
        lang = self._facts.get("language_preference")

        parts = [
            "You are a KreditBee collections voice agent.",
            f"The conversation has {'already' if self._has_greeted else 'not yet'} started with an initial greeting.",
            "Do NOT repeat the greeting once it has happened.",
            "Never use placeholders like [Customer's Name]. If a value is unknown, ask ONE short question to obtain it, then use it consistently.",
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

        # Explicit state injection (this is what prevents repetition)
        state_lines = [
            "STATE (do not ask again if true):",
            f"- identity_confirmed: {self._state.get('identity_confirmed', False)}",
            f"- awareness_confirmed: {self._state.get('awareness_confirmed', False)}",
            f"- payment_done: {self._state.get('payment_done', False)}",
            f"- ptp_captured: {self._state.get('ptp_captured', False)}",
            f"- callback_captured: {self._state.get('callback_captured', False)}",
        ]
        if self._last_agent_intent:
            state_lines.append(f"- last_agent_intent: {self._last_agent_intent}")

        parts.append("\n".join(state_lines))
        parts.append(
            "Goal: move to the NEXT missing step ONLY. "
            "If awareness_confirmed is true, NEVER ask awareness again. "
            "If identity_confirmed is true, NEVER ask identity again. "
            "Ask only one short question at a time."
        )
        return "\n".join(parts)

    def _extract_facts_from_text(self, text: str) -> None:
        import re
        t = (text or "").strip()
        if not t:
            return

        if not self._facts.get("customer_name"):
            m = re.search(r"\b(?:my name is|i am|this is)\s+([A-Za-z][A-Za-z\s\-']{1,40})\b", t, re.IGNORECASE)
            if not m:
                m = re.search(r"\bmera\s+naam\s+([A-Za-z\u0900-\u097F]{2,30})\b", t, re.IGNORECASE)
            if m:
                name = m.group(1).strip(" .,")
                self._facts["customer_name"] = name

        amt = re.search(r"(?:₹|\brs\.?|\brupees\b)\s*([0-9][0-9,]*(?:\.[0-9]+)?)", t, re.IGNORECASE)
        if amt:
            self._facts["overdue_amount"] = amt.group(1).replace(",", "")

        dt = re.search(r"\b(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\b", t)
        if dt:
            self._facts["ptp_date"] = dt.group(1)

        ref = re.search(r"\b(?:ref|utr)\s*[:\-]?\s*([A-Za-z0-9\-]{6,})\b", t, re.IGNORECASE)
        if ref:
            self._facts["reference_number"] = ref.group(1)

        if re.search(r"\b(hindi|हिंदी)\b", t, re.IGNORECASE):
            self._facts["language_preference"] = "hi-IN"
        elif re.search(r"\b(english)\b", t, re.IGNORECASE):
            self._facts["language_preference"] = "en-IN"

    def _normalize_yes_no(self, text: str) -> Optional[bool]:
        t = (text or "").strip().lower()
        if not t:
            return None
        # common yes variants
        if any(x in t for x in ["yes", "yeah", "yep", "haan", "han", "haa", "ji", "bilkul", "ok", "okay", "sure"]):
            return True
        # common no variants
        if any(x in t for x in ["no", "nope", "nah", "nahi", "nahin", "na", "not really"]):
            return False
        return None

    def _update_state_from_user_reply(self, user_text: str) -> None:
        yn = self._normalize_yes_no(user_text)
        intent = self._last_agent_intent or self._pending_agent_intent

        if yn is None:
            return

        if intent == "confirm_awareness":
            self._state["awareness_confirmed"] = bool(yn)
        elif intent == "confirm_identity":
            self._state["identity_confirmed"] = bool(yn)

    def _infer_agent_intent(self, assistant_text: str) -> Optional[str]:
        t = (assistant_text or "").lower()
        if not t:
            return None

        # awareness confirmation patterns
        if "aware" in t and "overdue" in t:
            return "confirm_awareness"
        if "overdue" in t and "confirm" in t:
            return "confirm_awareness"

        # identity confirmation patterns
        if "speaking to" in t or "is this" in t and "?" in t:
            return "confirm_identity"
        if "confirm your name" in t or "your name" in t and "confirm" in t:
            return "confirm_identity"

        # promise-to-pay / date ask
        if ("when" in t or "by" in t) and ("pay" in t or "payment" in t) and ("date" in t or "today" in t or "tomorrow" in t):
            return "ask_ptp"
        if "promise" in t and "pay" in t:
            return "ask_ptp"

        # callback ask
        if "call you back" in t or "callback" in t or ("what time" in t and "call" in t):
            return "ask_callback"

        return None

    def _update_state_from_assistant(self, assistant_text: str) -> None:
        inferred = self._infer_agent_intent(assistant_text)
        if inferred:
            self._last_agent_intent = inferred

        # If the agent explicitly thanked for confirming awareness/identity, lock them true.
        t = (assistant_text or "").lower()
        if "thank you for confirming" in t and "overdue" in t:
            self._state["awareness_confirmed"] = True
        if "thank you for confirming" in t and "name" in t:
            self._state["identity_confirmed"] = True

        # If PTP date got extracted already, mark captured.
        if self._facts.get("ptp_date"):
            self._state["ptp_captured"] = True
        if self._facts.get("reference_number"):
            self._state["payment_done"] = True
    
    def _compute_next_step(self) -> str:
        """Return a strict next step label the model must follow."""
        # Highest priority: identity (if we don't have a name yet)
        if not self._facts.get("customer_name") and not self._state.get("identity_confirmed", False):
            return "confirm_identity"

        # Awareness of overdue
        if not self._state.get("awareness_confirmed", False):
            return "confirm_awareness"

        # If they already provided a payment reference, treat as paid
        if self._facts.get("reference_number"):
            self._state["payment_done"] = True
            return "close_paid"

        # If they provided a PTP date, capture it
        if self._facts.get("ptp_date"):
            self._state["ptp_captured"] = True
            return "confirm_ptp"

        # Otherwise, move to payment plan
        return "ask_payment_plan"


    def _build_runtime_user_instruction(self, next_step: str) -> str:
        """High-control instruction injected as a USER message (not system)."""
        lines = [
            "IMPORTANT INSTRUCTIONS (follow strictly):",
            "- Do NOT repeat any question whose STATE value is true.",
            "- Ask only ONE short question at a time.",
            "- Never ask the same confirmation twice (no re-confirmation loops).",
            "",
            "STATE:",
            f"- identity_confirmed={self._state.get('identity_confirmed', False)}",
            f"- awareness_confirmed={self._state.get('awareness_confirmed', False)}",
            f"- payment_done={self._state.get('payment_done', False)}",
            f"- ptp_captured={self._state.get('ptp_captured', False)}",
            f"- callback_captured={self._state.get('callback_captured', False)}",
        ]

        if self._facts.get("customer_name"):
            lines.append(f"- customer_name={self._facts.get('customer_name')}")
        if self._facts.get("overdue_amount"):
            lines.append(f"- overdue_amount=INR {self._facts.get('overdue_amount')}")
        if self._facts.get("due_date"):
            lines.append(f"- due_date={self._facts.get('due_date')}")
        if self._facts.get("ptp_date"):
            lines.append(f"- ptp_date={self._facts.get('ptp_date')}")
        if self._facts.get("reference_number"):
            lines.append(f"- reference_number={self._facts.get('reference_number')}")

        lines.append("")
        lines.append(f"NEXT_STEP={next_step}")

        if next_step == "confirm_identity":
            lines.append("Ask: 'May I confirm your name?' (ONE time only).")
        elif next_step == "confirm_awareness":
            lines.append("Ask ONCE: 'Are you aware your KreditBee payment is overdue?' If user says yes, do NOT ask again.")
        elif next_step == "ask_payment_plan":
            lines.append("Do NOT ask awareness again. Ask: 'Can you pay now, or what date can you make the payment by?'")
        elif next_step == "confirm_ptp":
            lines.append("Confirm the promised payment date briefly and close with next action (WhatsApp/SMS reminder).")
        elif next_step == "close_paid":
            lines.append("Acknowledge payment reference and close politely.")

        lines.append("Reply naturally in the user's language if known.")
        return "\n".join(lines)