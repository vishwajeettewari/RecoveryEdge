import asyncio
import base64
import inspect
import json
import logging
from typing import AsyncGenerator, Optional
from urllib.parse import urlencode, urlparse, urlunparse

from ws_utils import connect_ws

try:
    from sarvamai import AsyncSarvamAI
except Exception:  # pragma: no cover - optional dependency
    AsyncSarvamAI = None

logger = logging.getLogger(__name__)


class BulbulTTSService:
    def __init__(
        self,
        ws_url: str = "wss://api.sarvam.ai/text-to-speech/ws",
        api_key: Optional[str] = None,
        voice: Optional[str] = None,
        model: Optional[str] = None,
        speaker: Optional[str] = None,
        sample_rate: int = 16000,
        language: Optional[str] = None,
        output_audio_codec: str = "linear16",
        output_audio_bitrate: Optional[str] = None,
        min_buffer_size: Optional[int] = 30,
        max_chunk_length: Optional[int] = 120,
        use_sdk: bool = True,
    ) -> None:
        self.ws_url = ws_url
        self.api_key = api_key
        self.voice = voice
        self.model = model
        self.speaker = speaker
        self.sample_rate = sample_rate
        self.language = language
        self.output_audio_codec = output_audio_codec
        self.output_audio_bitrate = output_audio_bitrate
        self.min_buffer_size = min_buffer_size
        self.max_chunk_length = max_chunk_length
        self.use_sdk = use_sdk
        self._ws = None
        self._ws_ctx = None
        self._client = None

    @staticmethod
    def _filter_kwargs(func, kwargs: dict) -> dict:
        try:
            sig = inspect.signature(func)
        except (TypeError, ValueError):
            return {k: v for k, v in kwargs.items() if v is not None}
        return {k: v for k, v in kwargs.items() if k in sig.parameters and v is not None}

    async def _sdk_connect(self) -> None:
        if AsyncSarvamAI is None:
            raise RuntimeError("sarvamai SDK not installed. Run: pip install sarvamai")
        if not self.api_key:
            logger.warning("TTS api key missing; connection will likely be rejected.")
        self._client = AsyncSarvamAI(api_subscription_key=self.api_key or "")
        service = getattr(self._client, "text_to_speech_streaming", None)
        if service is None:
            raise RuntimeError("sarvamai SDK missing text_to_speech_streaming")
        connect_fn = getattr(service, "connect", service)
        connect_kwargs = {"model": self.model}
        connect_kwargs = self._filter_kwargs(connect_fn, connect_kwargs)
        result = connect_fn(**connect_kwargs)
        if hasattr(result, "__aenter__"):
            self._ws_ctx = result
            self._ws = await result.__aenter__()
        else:
            self._ws_ctx = None
            self._ws = await result if asyncio.iscoroutine(result) else result
        await self._send_start()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def connect(self) -> None:
        if self.use_sdk:
            await self._sdk_connect()
            return
        # Use documented header name (Sarvam examples commonly use api-subscription-key).
        headers = {}
        if self.api_key:
            headers["api-subscription-key"] = self.api_key
        else:
            logger.warning("TTS api key missing; connection will likely be rejected.")

        url = self._with_query_params(self.ws_url)
        self._ws = await connect_ws(url, headers=headers, max_queue=4)
        await self._send_start()

    async def close(self) -> None:
        if self.use_sdk:
            if self._ws_ctx is not None:
                await self._ws_ctx.__aexit__(None, None, None)
            elif self._ws is not None and hasattr(self._ws, "close"):
                result = self._ws.close()
                if asyncio.iscoroutine(result):
                    await result
            self._ws = None
            self._ws_ctx = None
            self._client = None
            return
        if self._ws is None:
            return
        try:
            await self._ws.send(json.dumps({"type": "close"}))
        except Exception:
            pass
        await self._ws.close()
        self._ws = None

    def _with_query_params(self, ws_url: str) -> str:
        url = urlparse(ws_url)
        query = {}
        if self.model:
            query["model"] = self.model
        query["send_completion_event"] = "true"
        merged_query = url.query + ("&" if url.query else "") + urlencode(query)
        return urlunparse(url._replace(query=merged_query))

    async def _send_start(self) -> None:
        if self.use_sdk and self._ws is not None:
            if hasattr(self._ws, "configure"):
                config_kwargs = {
                    "target_language_code": self.language or "en-IN",
                    "speaker": self.speaker or self.voice or "anushka",
                    "speech_sample_rate": self.sample_rate,
                    "output_audio_codec": self.output_audio_codec,
                    "output_audio_bitrate": self.output_audio_bitrate,
                    "min_buffer_size": self.min_buffer_size,
                    "max_chunk_length": self.max_chunk_length,
                }
                config_kwargs = self._filter_kwargs(self._ws.configure, config_kwargs)
                result = self._ws.configure(**config_kwargs)
                if asyncio.iscoroutine(result):
                    await result
            return
        data = {
            "target_language_code": self.language or "en-IN",
            "speaker": self.speaker or self.voice or "anushka",
            "speech_sample_rate": self.sample_rate,
            "output_audio_codec": self.output_audio_codec,
            "output_audio_bitrate": self.output_audio_bitrate,
            "min_buffer_size": self.min_buffer_size,
            "max_chunk_length": self.max_chunk_length,
        }
        data = {k: v for k, v in data.items() if v is not None}
        payload = {"type": "config", "data": data}
        await self._ws.send(json.dumps(payload))

    async def send_text(self, text: str) -> None:
        if not text:
            return
        if self._ws is None:
            raise RuntimeError("TTS websocket is not connected")
        if self.use_sdk:
            if hasattr(self._ws, "convert"):
                result = self._ws.convert(text)
                if asyncio.iscoroutine(result):
                    await result
                return
            if hasattr(self._ws, "send_text"):
                result = self._ws.send_text(text)
                if asyncio.iscoroutine(result):
                    await result
                return
        await self._ws.send(json.dumps({"type": "text", "data": {"text": text}}))

    async def end_input(self) -> None:
        if self._ws is None:
            return
        if self.use_sdk:
            if hasattr(self._ws, "flush"):
                result = self._ws.flush()
                if asyncio.iscoroutine(result):
                    await result
                return
            if hasattr(self._ws, "end"):
                result = self._ws.end()
                if asyncio.iscoroutine(result):
                    await result
                return
        await self._ws.send(json.dumps({"type": "flush"}))

    async def audio_stream(self) -> AsyncGenerator[bytes, None]:
        if self._ws is None:
            raise RuntimeError("TTS websocket is not connected")
        # Always iterate via _iter_messages() so we work with both websocket implementations
        # (some libs expose __aiter__, others expose recv()) and the SDK wrapper.
        async for message in self._iter_messages():
            if isinstance(message, bytes):
                yield message
                continue
            data = self._coerce_dict(message)
            if data is None:
                audio_attr = getattr(message, "audio", None)
                if isinstance(audio_attr, (bytes, bytearray)):
                    yield bytes(audio_attr)
                    continue
                if isinstance(audio_attr, str):
                    try:
                        yield base64.b64decode(audio_attr)
                    except Exception:
                        continue
                data_obj = getattr(message, "data", None)
                audio_field = getattr(data_obj, "audio", None)
                if isinstance(audio_field, str):
                    try:
                        yield base64.b64decode(audio_field)
                    except Exception:
                        continue
                continue

            event = data.get("event")
            msg_type = data.get("type")
            # Terminal events vary between SDK and raw WS; keep this conservative.
            if event in {"done", "end", "completed"}:
                break
            if msg_type in {"done", "end", "close", "completion", "completed"}:
                break
            if data.get("error"):
                logger.error("TTS error: %s", data.get("error"))
                break

            payload = data.get("data") if isinstance(data.get("data"), dict) else data
            # Common field names across Sarvam streaming variants.
            audio_b64 = (
                payload.get("audio")
                or payload.get("audio_chunk")
                or payload.get("chunk")
                or payload.get("audioContent")
            )
            if audio_b64:
                try:
                    yield base64.b64decode(audio_b64)
                except Exception:
                    continue

    async def _iter_messages(self):
        if self._ws is None:
            return
        if hasattr(self._ws, "__aiter__"):
            async for message in self._ws:
                yield message
            return
        if hasattr(self._ws, "recv"):
            while True:
                try:
                    message = await self._ws.recv()
                except Exception:
                    break
                if message is None:
                    break
                yield message
            return
        if hasattr(self._ws, "receive"):
            while True:
                try:
                    message = await self._ws.receive()
                except Exception:
                    break
                if message is None:
                    break
                yield message
            return

    @staticmethod
    def _coerce_dict(message):
        if isinstance(message, dict):
            return message
        if isinstance(message, str):
            try:
                return json.loads(message)
            except json.JSONDecodeError:
                return None
        if hasattr(message, "model_dump"):
            try:
                return message.model_dump()
            except Exception:
                return None
        if hasattr(message, "dict"):
            try:
                return message.dict()
            except Exception:
                return None
        return None
