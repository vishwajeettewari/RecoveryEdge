# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI-powered voice collections agent that conducts phone calls to customers about overdue loan payments. Uses Sarvam AI services for speech-to-text (Saarika), text-to-speech (Bulbul), and LLM chat (sarvam-m). Built for Indian market collections with Hindi/English support.

## Running the Application

```bash
# Web mode (browser console UI) — primary way to use
python web_app.py
# Serves at http://0.0.0.0:8000 (configurable via API_HOST, API_PORT env vars)
# Admin dashboard at /admin (requires ADMIN_TOKEN env var)

# CLI mode (direct mic/speaker voice call)
python main.py
```

## Running Tests

```bash
# All tests (unittest-based, no pytest config)
python -m unittest discover tests

# Single test file
python -m unittest tests.test_pii
python -m unittest tests.test_workflow_engine
```

Tests directory has no `__init__.py` or `conftest.py`. Tests import modules from the project root directly.

## Environment Configuration

All config is via `.env` file (loaded by custom `config.py`, no python-dotenv dependency). Key variables:

- `SARVAM_API_KEY` — master API key, used as fallback for service-specific keys
- `SAARIKA_API_KEY` — STT key (required; no fallback to SARVAM_API_KEY in web mode)
- `SARVAM_CHAT_MODEL` — LLM model (default: `sarvam-m`)
- `SARVAM_STT_MODEL` — STT model (e.g., `saarika:v2.5`)
- `SARVAM_TTS_MODEL` — TTS model (e.g., `bulbul:v2`)
- `POST_SPEECH_PAUSE_MS` — ms to wait after user stops speaking before responding (default: 600)
- `USE_SARVAMAI_SDK` — use the sarvamai Python SDK (default: True for STT, False for TTS/LLM due to codec/streaming issues)

## Architecture

### Two Entry Points

- **`web_app.py`** — FastAPI server with REST API + WebSocket `/ws/voice` endpoint. Serves the frontend from `frontend/`. This is the main entry point.
- **`main.py`** — CLI mode using `call_session.py` with local mic/speaker via `audio_io.py`.

### Core Orchestrator: `web_session.py` (WebCallSession)

The largest file (~161KB). Manages the real-time voice call loop by coordinating three concurrent async tasks:

1. **STT loop** (`_stt_loop`) — streams audio to Sarvam Saarika, processes VAD signals, detects speech completion
2. **LLM generation** (`_run_generation`) — builds context from workflow state + facts + history, streams response from LLM, applies humanization (filler words, prosody hints)
3. **TTS loop** — chunks LLM text output, streams to Sarvam Bulbul, sends PCM audio frames back to client

`call_session.py` is the base class; `web_session.py` extends it for WebSocket delivery.

### Deterministic Workflow: `workflow_engine.py`

State machine that enforces the collections call flow in sequence:
`consent → confirm_identity → confirm_awareness → ask_payment_made → ask_reference_number → ask_ptp_or_callback → closing`

`WorkflowState` (dataclass) tracks what has been confirmed. `WorkflowEngine.compute_next_step()` determines what to ask next. Includes Hindi/English yes/no parsing.

### Service Layer

- **`sarvam_llm_service.py`** — LLM wrapper. Supports both HTTP SSE streaming and sarvamai SDK. SDK streaming is off by default (`USE_SARVAMAI_SDK_LLM=False`).
- **`sarvam_stt_service.py`** — STT via WebSocket. Handles VAD signals, flush signals, reconnection on error.
- **`sarvam_tts_service.py`** — TTS via WebSocket. Outputs PCM16/linear16 audio.

### Data Layer

- **`excel_source.py`** — reads customer records from `data/customers.xlsx`
- **`excel_sink.py`** — writes call outcomes/messages/actions to `data/demo_output.xlsx` (multiple sheets: Calls, Messages, Actions, Outbox)
- **`audit_store.py`** — SQLite (`data/demo.db`) with tables: events, outcomes, violations
- **`knowledge_store.py`** — SQLite FTS5 over markdown files in `knowledge/` directory
- **`session_store.py`** — persists conversation history and state to disk

### Supporting Modules

- **`pii.py`** — regex-based redaction for email, phone, PAN, Aadhaar numbers
- **`actions.py`** — routes post-call actions (payment links, escalations)
- **`logging_utils.py`** — JSON structured logging with secret masking

### Frontend

Vanilla HTML/JS in `frontend/`. `app.js` handles WebSocket communication, Web Audio API for mic capture, and console-style UI. `admin.html`/`admin.js` for metrics dashboard. Audio processing uses Web Audio worklets in `frontend/worklets/`.

## Key Design Decisions

- **No requirements.txt/pyproject.toml** — dependencies managed via venv directly. Key packages: fastapi, uvicorn, websockets, aiohttp, openpyxl, sounddevice, sarvamai, httpx
- **Custom dotenv** — `config.py` has its own `.env` parser (no python-dotenv)
- **SDK defaults** — sarvamai SDK is enabled for STT but disabled for TTS (codec mismatch: SDK streams MP3, browser expects PCM16) and LLM (SDK doesn't handle SSE streaming correctly)
- **Human-like features** — filler words, backchanneling, emotion detection, repair strategies, prosody hints are all implemented in `web_session.py` (see `HUMAN_LIKE_FEATURES.md`)
- **Post-speech pause** — configurable delay (default 600ms) between user silence detection and agent response, with smart cancellation if user resumes speaking (see `PAUSE_FIX_SUMMARY.md`)
