import asyncio
import contextlib
import json
import logging
import os
import time
from typing import Dict, Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.websockets import WebSocketState

from config import get_env, get_env_bool, load_dotenv
from logging_utils import configure_logging, log_event, mask_secret
from sarvam_llm_service import SarvamLLMService
from sarvam_stt_service import SaarikaSTTService
from web_session import WebCallSession
from audit_store import SQLiteAuditStore
from excel_source import ExcelCustomerSource
from excel_sink import ExcelOutcomeSink
from actions import ActionRouter
from knowledge_store import SQLiteFTSKnowledgeStore

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(__file__)
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
DATA_DIR = os.path.join(BASE_DIR, "data")
KNOWLEDGE_DIR_DEFAULT = os.path.join(BASE_DIR, "knowledge")

app = FastAPI()
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

# Global singletons for the demo server process.
_demo_state: Dict[str, object] = {}


@app.get("/")
async def index() -> HTMLResponse:
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    with open(index_path, "r", encoding="utf-8") as handle:
        return HTMLResponse(handle.read())

@app.get("/admin")
async def admin() -> HTMLResponse:
    admin_path = os.path.join(FRONTEND_DIR, "admin.html")
    with open(admin_path, "r", encoding="utf-8") as handle:
        return HTMLResponse(handle.read())


def _require_admin(request) -> Optional[JSONResponse]:
    token = get_env("ADMIN_TOKEN")
    if not token:
        return None
    auth = request.headers.get("authorization") or ""
    if auth.strip() == f"Bearer {token}":
        return None
    return JSONResponse({"error": "unauthorized"}, status_code=401)


def _get_demo_singletons() -> Dict[str, object]:
    if _demo_state:
        return _demo_state

    os.makedirs(DATA_DIR, exist_ok=True)
    customers_path = get_env("CUSTOMERS_XLSX_PATH", os.path.join(DATA_DIR, "customers.xlsx"))
    output_path = get_env("DEMO_OUTPUT_XLSX_PATH", os.path.join(DATA_DIR, "demo_output.xlsx"))
    db_path = get_env("DEMO_DB_PATH", os.path.join(DATA_DIR, "demo.db"))
    knowledge_dir = get_env("KNOWLEDGE_DIR", KNOWLEDGE_DIR_DEFAULT)
    pay_base_url = get_env("DEMO_PAY_BASE_URL", "https://pay.example/demo")

    retention_days = int(get_env("PHI_RETENTION_DAYS", "30") or "30")

    audit = SQLiteAuditStore(db_path, retention_days=retention_days)
    sink = ExcelOutcomeSink(output_path)
    sink.ensure_workbook()
    source = ExcelCustomerSource(customers_path)
    router = ActionRouter(pay_base_url=pay_base_url)
    knowledge = SQLiteFTSKnowledgeStore(db_path, knowledge_dir)
    # Best-effort reindex on startup for demos (fast for small docs).
    try:
        knowledge.reindex()
    except Exception:
        pass

    _demo_state.update(
        {
            "audit": audit,
            "sink": sink,
            "source": source,
            "router": router,
            "knowledge": knowledge,
            "sessions": {},  # session_id -> snapshot dict
            "session_objs": {},  # session_id -> WebCallSession
        }
    )
    return _demo_state


@app.get("/api/metrics")
async def api_metrics(request: Request):
    deny = _require_admin(request)
    if deny:
        return deny
    demo = _get_demo_singletons()
    audit: SQLiteAuditStore = demo["audit"]  # type: ignore[assignment]
    return audit.metrics()

@app.get("/api/customers")
async def api_customers(request: Request):
    demo = _get_demo_singletons()
    source: ExcelCustomerSource = demo["source"]  # type: ignore[assignment]
    try:
        rows = source.list_customers()
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
    return {"rows": rows}


@app.get("/api/sessions")
async def api_sessions(request: Request):
    deny = _require_admin(request)
    if deny:
        return deny
    demo = _get_demo_singletons()
    sessions: Dict[str, dict] = demo["sessions"]  # type: ignore[assignment]
    # Return "active" snapshots (updated by the WS session loop).
    return {"sessions": list(sessions.values())}


@app.post("/api/sessions/{session_id}/disposition")
async def api_set_disposition(session_id: str, request: Request):
    deny = _require_admin(request)
    if deny:
        return deny
    demo = _get_demo_singletons()
    objs: Dict[str, WebCallSession] = demo["session_objs"]  # type: ignore[assignment]
    sessions: Dict[str, dict] = demo["sessions"]  # type: ignore[assignment]
    sess = objs.get(session_id)
    if not sess:
        return JSONResponse({"error": "unknown session"}, status_code=404)
    try:
        data = await request.json()
    except Exception:
        data = {}
    disp = (data.get("disposition") or "").strip() or "closed"
    try:
        await sess.admin_set_disposition(disp)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    sessions[session_id] = sess.get_snapshot()
    return {"ok": True, "session": sessions[session_id]}


@app.get("/api/export/demo.xlsx")
async def api_export_demo(request: Request):
    deny = _require_admin(request)
    if deny:
        return deny
    demo = _get_demo_singletons()
    sink: ExcelOutcomeSink = demo["sink"]  # type: ignore[assignment]
    audit: SQLiteAuditStore = demo["audit"]  # type: ignore[assignment]

    # Build a one-off export file with a Metrics sheet (client-friendly demo artifact).
    try:
        from openpyxl import load_workbook
    except Exception:
        return FileResponse(sink.path, filename="demo.xlsx")

    export_path = os.path.join(DATA_DIR, "demo_export.xlsx")
    wb = load_workbook(sink.path)
    try:
        if "Metrics" in wb.sheetnames:
            ws = wb["Metrics"]
            ws.delete_rows(1, ws.max_row)
        else:
            ws = wb.create_sheet("Metrics")
        m = audit.metrics()
        ws.append(["key", "value"])
        for k, v in m.items():
            ws.append([k, v])
        wb.save(export_path)
    finally:
        wb.close()

    return FileResponse(export_path, filename="demo.xlsx")


@app.post("/api/knowledge/reindex")
async def api_knowledge_reindex(request: Request):
    deny = _require_admin(request)
    if deny:
        return deny
    demo = _get_demo_singletons()
    knowledge: SQLiteFTSKnowledgeStore = demo["knowledge"]  # type: ignore[assignment]
    n = knowledge.reindex()
    return {"ok": True, "chunks_indexed": n}


class WebSocketSender:
    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._counter = 0
        self._task: Optional[asyncio.Task] = None
        self._closed = asyncio.Event()

    def start(self) -> None:
        if not self._task:
            self._task = asyncio.create_task(self._send_loop(), name="ws_send_loop")

    async def close(self) -> None:
        self._closed.set()
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def send_json(self, payload: dict) -> None:
        if self.websocket.application_state != WebSocketState.CONNECTED:
            return
        self._counter += 1
        await self._queue.put((0, self._counter, "text", json.dumps(payload)))

    async def send_bytes(self, data: bytes) -> None:
        if self.websocket.application_state != WebSocketState.CONNECTED:
            return
        self._counter += 1
        await self._queue.put((1, self._counter, "bytes", data))

    async def _send_loop(self) -> None:
        try:
            while not self._closed.is_set():
                if self.websocket.application_state != WebSocketState.CONNECTED:
                    break
                try:
                    priority, _, kind, payload = await asyncio.wait_for(self._queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                try:
                    if kind == "text":
                        await self.websocket.send_text(payload)
                    else:
                        await self.websocket.send_bytes(payload)
                except (RuntimeError, WebSocketDisconnect):
                    break
        finally:
            self._closed.set()


@app.websocket("/ws/voice")
async def voice_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    sender = WebSocketSender(websocket)
    sender.start()
    demo = _get_demo_singletons()
    audit: SQLiteAuditStore = demo["audit"]  # type: ignore[assignment]
    sink: ExcelOutcomeSink = demo["sink"]  # type: ignore[assignment]
    source: ExcelCustomerSource = demo["source"]  # type: ignore[assignment]
    router: ActionRouter = demo["router"]  # type: ignore[assignment]
    knowledge: SQLiteFTSKnowledgeStore = demo["knowledge"]  # type: ignore[assignment]
    sessions: Dict[str, dict] = demo["sessions"]  # type: ignore[assignment]
    session_objs: Dict[str, WebCallSession] = demo["session_objs"]  # type: ignore[assignment]

    client = websocket.client
    log_event(
        logger,
        "ws_open",
        client=f"{client.host}:{client.port}" if client else None,
    )

    def _extract_context_from_payload(data: dict) -> dict:
        # Accept either {type: 'context', context: {...}} OR flat keys on the payload.
        ctx = data.get("context") if isinstance(data.get("context"), dict) else {}
        if not isinstance(ctx, dict):
            ctx = {}

        # Merge flat keys (excluding type/context) if caller sends them at top-level.
        for k, v in (data or {}).items():
            if k in {"type", "context"}:
                continue
            if v is None:
                continue
            ctx.setdefault(k, v)

        # Normalize common aliases
        # amount / overdue
        if "overdue_amount" not in ctx:
            if "amount" in ctx:
                ctx["overdue_amount"] = ctx.get("amount")
            elif "overdue" in ctx:
                ctx["overdue_amount"] = ctx.get("overdue")

        # due date
        if "due_date" not in ctx:
            if "due" in ctx:
                ctx["due_date"] = ctx.get("due")
            elif "overdue_date" in ctx:
                ctx["due_date"] = ctx.get("overdue_date")

        # customer name
        if "customer_name" not in ctx and "name" in ctx:
            ctx["customer_name"] = ctx.get("name")

        # Normalize empty strings
        cleaned = {}
        for k, v in ctx.items():
            if isinstance(v, str):
                vv = v.strip()
                if vv:
                    cleaned[k] = vv
            else:
                cleaned[k] = v
        return cleaned

    load_dotenv(override=True)
    stt_ws_url = get_env(
        "SAARIKA_WS_URL",
        get_env("SARVAM_STT_WS_URL", "wss://api.sarvam.ai/speech-to-text/ws"),
    )
    llm_base_url = get_env("SARVAM_BASE_URL", "https://api.sarvam.ai")
    tts_ws_url = get_env(
        "BULBUL_WS_URL",
        get_env("SARVAM_TTS_WS_URL", "wss://api.sarvam.ai/text-to-speech/ws"),
    )

    api_key = get_env("SARVAM_API_KEY")
    stt_api_key = get_env("SAARIKA_API_KEY")
    llm_api_key = get_env("SARVAM_LLM_API_KEY", api_key)
    tts_api_key = get_env("BULBUL_API_KEY", api_key)
    if not stt_api_key:
        log_event(logger, "config_error", error="Missing SAARIKA_API_KEY for STT.")
        await sender.send_json({"type": "error", "message": "Missing SAARIKA_API_KEY for STT."})
        await websocket.close()
        return

    llm_model = get_env("SARVAM_CHAT_MODEL", get_env("SARVAM_LLM_MODEL", "sarvam-m"))
    tts_voice = get_env("BULBUL_VOICE")
    tts_speaker = get_env("SARVAM_TTS_SPEAKER")
    stt_model = get_env("SARVAM_STT_MODEL")
    tts_model = get_env("SARVAM_TTS_MODEL")
    stt_language = get_env("SARVAM_STT_LANGUAGE", "en-IN")
    stt_language_key = get_env("SARVAM_STT_LANGUAGE_PARAM", "language_code")

    vad_threshold = float(get_env("VAD_RMS_THRESHOLD", "500"))
    vad_silence_ms = int(get_env("VAD_SILENCE_MS", "600"))
    stt_flush_interval_ms = int(get_env("STT_FLUSH_INTERVAL_MS", "250"))
    stt_vad_signals = get_env_bool("STT_VAD_SIGNALS", True)
    stt_high_vad = get_env_bool("STT_HIGH_VAD_SENSITIVITY", True)
    use_sdk = get_env_bool("USE_SARVAMAI_SDK", True)
    use_sdk_stt = get_env_bool("USE_SARVAMAI_SDK_STT", use_sdk)
    # SDK TTS streams MP3; browser/player expects PCM16. Default to raw WS unless explicitly enabled.
    use_sdk_tts = get_env_bool("USE_SARVAMAI_SDK_TTS", False)
    # LLM streaming via SDK doesn't handle event-stream correctly; default to HTTP SSE unless overridden.
    use_sdk_llm = get_env_bool("USE_SARVAMAI_SDK_LLM", False)
    stt_flush_signal_env = get_env("STT_FLUSH_SIGNAL")
    if stt_flush_signal_env is None or stt_flush_signal_env == "":
        stt_flush_signal = use_sdk_stt
    else:
        stt_flush_signal = get_env_bool("STT_FLUSH_SIGNAL", False)
    stt_audio_payload_format = get_env("STT_AUDIO_PAYLOAD_FORMAT", "flat")
    stt_input_audio_codec = get_env("STT_INPUT_AUDIO_CODEC", "pcm_s16le")
    stt_audio_encoding = get_env("STT_AUDIO_ENCODING")
    stt_log_raw = get_env_bool("LOG_STT_RAW", False)
    log_partials = get_env_bool("LOG_PARTIAL_TRANSCRIPTS", True)
    log_tokens = get_env_bool("LOG_LLM_TOKENS", False)
    log_audio_chunks = get_env_bool("LOG_TTS_CHUNKS", False)
    greeting_text = get_env(
        "GREETING_TEXT",
        "Hello, this is KreditBee collections calling about your overdue payment. Is now a good time to talk?",
    )
    enable_greeting = get_env_bool("ENABLE_GREETING", True)
    max_history_turns = int(get_env("MAX_HISTORY_TURNS", "10"))
    session_store_path = get_env("SESSION_STORE_PATH")
    dynamic_stt_language = get_env_bool("STT_DYNAMIC_LANGUAGE", False)
    preview_partials = get_env_bool("PREVIEW_PARTIALS", True)
    preview_after_ms = int(get_env("PREVIEW_AFTER_MS", "300"))
    llm_timeout_s = float(get_env("LLM_STREAM_TIMEOUT_S", "20"))
    tts_timeout_s = float(get_env("TTS_STREAM_TIMEOUT_S", "20"))
    stt_connect_timeout_s = float(get_env("STT_CONNECT_TIMEOUT_S", "10"))
    tts_stream_chunk_chars = int(get_env("TTS_STREAM_CHUNK_CHARS", "30"))
    tts_stream_flush_punct = get_env_bool("TTS_STREAM_FLUSH_PUNCT", True)
    tts_min_buffer_size = int(get_env("TTS_MIN_BUFFER_SIZE", "30"))
    tts_max_chunk_length = int(get_env("TTS_MAX_CHUNK_LENGTH", "120"))
    tts_output_audio_codec = get_env("TTS_OUTPUT_AUDIO_CODEC", "linear16")
    tts_output_audio_bitrate = get_env("TTS_OUTPUT_AUDIO_BITRATE")
    post_speech_pause_ms = int(get_env("POST_SPEECH_PAUSE_MS", "600"))  # Default 600ms for human-like turns

    stt = SaarikaSTTService(
        ws_url=stt_ws_url,
        api_key=stt_api_key,
        model=stt_model,
        language=stt_language,
        language_param_key=stt_language_key,
        vad_signals=stt_vad_signals,
        high_vad_sensitivity=stt_high_vad,
        flush_signal=stt_flush_signal,
        audio_payload_format=stt_audio_payload_format,
        input_audio_codec=stt_input_audio_codec,
        audio_encoding=stt_audio_encoding,
        log_raw_messages=stt_log_raw,
        use_sdk=use_sdk_stt,
    )
    llm = SarvamLLMService(base_url=llm_base_url, api_key=llm_api_key, model=llm_model, use_sdk=use_sdk_llm)

    log_event(
        logger,
        "config_loaded",
        stt_ws_url=stt_ws_url,
        llm_base_url=llm_base_url,
        tts_ws_url=tts_ws_url,
        stt_model=stt_model,
        llm_model=llm_model,
        tts_model=tts_model,
        api_key_prefix=mask_secret(api_key),
        stt_key_prefix=mask_secret(stt_api_key),
        llm_key_prefix=mask_secret(llm_api_key),
        tts_key_prefix=mask_secret(tts_api_key),
        use_sdk=use_sdk,
        use_sdk_stt=use_sdk_stt,
        use_sdk_llm=use_sdk_llm,
        use_sdk_tts=use_sdk_tts,
        tts_output_audio_codec=tts_output_audio_codec,
        tts_min_buffer_size=tts_min_buffer_size,
        tts_max_chunk_length=tts_max_chunk_length,
    )

    session = WebCallSession(
        stt_service=stt,
        llm_service=llm,
        tts_ws_url=tts_ws_url,
        send_event=sender.send_json,
        send_audio=sender.send_bytes,
        tts_api_key=tts_api_key,
        tts_voice=tts_voice,
        tts_model=tts_model,
        tts_speaker=tts_speaker,
        greeting_text=greeting_text if enable_greeting else None,
        max_history_turns=max_history_turns,
        session_store_path=session_store_path,
        dynamic_stt_language=dynamic_stt_language,
        preview_partials=preview_partials,
        preview_after_ms=preview_after_ms,
        llm_timeout_s=llm_timeout_s,
        tts_timeout_s=tts_timeout_s,
        stt_connect_timeout_s=stt_connect_timeout_s,
        vad_rms_threshold=vad_threshold,
        vad_silence_ms=vad_silence_ms,
        stt_flush_interval_ms=stt_flush_interval_ms,
        log_partial_transcripts=log_partials,
        log_tokens=log_tokens,
        log_audio_chunks=log_audio_chunks,
        use_sdk=use_sdk_tts,
        tts_stream_chunk_chars=tts_stream_chunk_chars,
        tts_stream_flush_punct=tts_stream_flush_punct,
        tts_min_buffer_size=tts_min_buffer_size,
        tts_max_chunk_length=tts_max_chunk_length,
        tts_output_audio_codec=tts_output_audio_codec,
        tts_output_audio_bitrate=tts_output_audio_bitrate,
        post_speech_pause_ms=post_speech_pause_ms,
        audit_store=audit,
        excel_sink=sink,
        action_router=router,
        knowledge_store=knowledge,
        session_registry=sessions,
    )
    audit.record_event(event_type="ws_open", session_id=session._session_id, payload={"client": f"{client.host}:{client.port}" if client else None})
    sink.upsert_call(session_id=session._session_id, customer_id=None, start_ts=round(time.time(), 3))
    audit.upsert_outcome(session_id=session._session_id, start_ts=round(time.time(), 3))
    sessions[session._session_id] = session.get_snapshot()
    session_objs[session._session_id] = session

    try:
        await session.start()
    except Exception as exc:
        log_event(logger, "session_start_failed", error=str(exc))
        await sender.send_json({"type": "error", "message": "STT connection failed"})
        await websocket.close()
        return

    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if message.get("bytes") is not None:
                await session.handle_audio(message["bytes"])
                continue
            if message.get("text"):
                try:
                    data = json.loads(message["text"])
                except json.JSONDecodeError:
                    continue
                msg_type = data.get("type")

                if msg_type == "start":
                    # UI may send session context together with start.
                    ctx = _extract_context_from_payload(data)
                    if not ctx.get("customer_id"):
                        await sender.send_json({"type": "error", "message": "Please select a customer before starting."})
                        continue
                    if ctx and hasattr(session, "set_context"):
                        await session.set_context(ctx)
                    await sender.send_json({"type": "context_received", "context": ctx})
                    await sender.send_json({"type": "started"})
                    if hasattr(session, "start_greeting"):
                        await session.start_greeting()
                    sessions[session._session_id] = session.get_snapshot()
                    continue

                if msg_type == "stop":
                    break

                if msg_type == "ping":
                    await sender.send_json({"type": "pong"})
                    continue

                if msg_type == "audio_started":
                    log_event(logger, "audio_started", session_id=session._session_id)
                    audit.record_event(event_type="audio_started", session_id=session._session_id, payload={})
                    continue

                # Allow typed/text input from the UI (e.g., the yellow input block)
                if msg_type in {"text", "user_text", "chat"}:
                    text = (data.get("text") or "").strip()
                    if text:
                        if hasattr(session, "handle_text"):
                            await session.handle_text(text)
                        else:
                            await sender.send_json(
                                {"type": "error", "message": "Text input is not supported by this server build."}
                            )
                        sessions[session._session_id] = session.get_snapshot()
                    continue

                # Allow the UI to pass known context (customer name / amount / due date etc.)
                if msg_type in {"set_context", "context"}:
                    ctx = _extract_context_from_payload(data)
                    if ctx and hasattr(session, "set_context"):
                        await session.set_context(ctx)
                    await sender.send_json({"type": "context_received", "context": ctx})
                    sessions[session._session_id] = session.get_snapshot()
                    continue


                if msg_type == "action":
                    await sender.send_json(
                        {"type": "action_error", "name": data.get("name"), "ok": False, "error": "Actions are disabled in this demo."}
                    )
                    continue
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.exception("Websocket error: %s", exc)
    finally:
        # Final snapshot + outcome.
        try:
            sessions[session._session_id] = session.get_snapshot()
        except Exception:
            pass
        await session.stop()
        await sender.close()
        try:
            session_objs.pop(session._session_id, None)
        except Exception:
            pass
        try:
            audit.upsert_outcome(
                session_id=session._session_id,
                end_ts=round(time.time(), 3),
                disposition=session.get_snapshot().get("disposition"),
                ptp_date=session.get_snapshot().get("ptp_date"),
                callback_time=session.get_snapshot().get("callback_time"),
            )
            sink.upsert_call(
                session_id=session._session_id,
                customer_id=session.get_snapshot().get("customer_id"),
                end_ts=round(time.time(), 3),
                disposition=session.get_snapshot().get("disposition"),
                ptp_date=session.get_snapshot().get("ptp_date"),
                callback_time=session.get_snapshot().get("callback_time"),
            )
        except Exception:
            pass
        log_event(logger, "ws_close")


def main() -> None:
    import uvicorn

    load_dotenv(override=True)
    configure_logging()
    host = get_env("API_HOST", "0.0.0.0")
    port = int(get_env("API_PORT", "8000"))
    log_level = get_env("LOG_LEVEL", "info").lower()

    uvicorn.run("web_app:app", host=host, port=port, log_level=log_level, reload=False)


if __name__ == "__main__":
    configure_logging()
    main()
