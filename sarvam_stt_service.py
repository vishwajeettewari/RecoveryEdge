import asyncio
import base64
import inspect
import json
import logging
from dataclasses import dataclass
from typing import AsyncGenerator, Optional
from urllib.parse import urlencode, urlparse, urlunparse

from ws_utils import connect_ws

try:
    from sarvamai import AsyncSarvamAI
    from sarvamai.types.audio_data import AudioData
    from sarvamai.types.audio_message import AudioMessage
except Exception:  # pragma: no cover - optional dependency
    AsyncSarvamAI = None
    AudioData = None
    AudioMessage = None

logger = logging.getLogger(__name__)


@dataclass
class Transcript:
    text: str
    is_final: bool
    language: Optional[str] = None
    confidence: Optional[float] = None


class SaarikaSTTService:
    @staticmethod
    def _bool_flag(value: Optional[bool]) -> Optional[str]:
        if value is None:
            return None
        return "true" if value else "false"

    def __init__(
        self,
        ws_url: str = "wss://api.sarvam.ai/speech-to-text/ws",
        api_key: Optional[str] = None,
        sample_rate: int = 16000,
        language: str = "en-IN",
        model: Optional[str] = None,
        input_audio_codec: str = "pcm_s16le",
        audio_encoding: Optional[str] = None,
        vad_signals: bool = True,
        high_vad_sensitivity: bool = True,
        flush_signal: bool = False,
        language_param_key: str = "language_code",
        audio_payload_format: str = "flat",
        log_raw_messages: bool = False,
        use_sdk: bool = True,
    ) -> None:
        self.ws_url = ws_url
        self.api_key = api_key
        self.sample_rate = sample_rate
        self.language = language
        self.model = model
        self.input_audio_codec = input_audio_codec
        self.audio_encoding = audio_encoding
        self.vad_signals = vad_signals
        self.high_vad_sensitivity = high_vad_sensitivity
        self.flush_signal = flush_signal
        self.language_param_key = language_param_key
        self.audio_payload_format = audio_payload_format
        self.log_raw_messages = log_raw_messages
        self.use_sdk = use_sdk
        self._raw_log_count = 0
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
            logger.warning("STT api key missing; connection will likely be rejected.")
        self._client = AsyncSarvamAI(api_subscription_key=self.api_key or "")
        service = getattr(self._client, "speech_to_text_streaming", None)
        if service is None:
            raise RuntimeError("sarvamai SDK missing speech_to_text_streaming")
        connect_fn = getattr(service, "connect", service)
        kwargs = {
            "language_code": self.language,
            "model": self.model,
            "sample_rate": str(self.sample_rate),
            "input_audio_codec": self.input_audio_codec,
            "vad_signals": self._bool_flag(self.vad_signals),
            "high_vad_sensitivity": self._bool_flag(self.high_vad_sensitivity),
            "flush_signal": self._bool_flag(self.flush_signal),
        }
        kwargs = self._filter_kwargs(connect_fn, kwargs)
        result = connect_fn(**kwargs)
        if hasattr(result, "__aenter__"):
            self._ws_ctx = result
            self._ws = await result.__aenter__()
        else:
            self._ws_ctx = None
            self._ws = await result if asyncio.iscoroutine(result) else result

    async def connect(self) -> None:
        if self.use_sdk:
            try:
                await self._sdk_connect()
                return
            except Exception as exc:
                if "403" in str(exc):
                    logger.error("STT auth failed (403). Check SARVAM_API_KEY/SAARIKA_API_KEY and account access.")
                raise
        # CHANGE: Use documented lowercase header only.
        headers = {}
        if self.api_key:
            headers["api-subscription-key"] = self.api_key
        else:
            logger.warning("STT api key missing; connection will likely be rejected.")

        url = self._with_query_params(self.ws_url, self.language_param_key)
        try:
            self._ws = await connect_ws(url, headers=headers, max_queue=4)
        except Exception as exc:
            status = self._extract_status(exc)
            if status in {400, 422} and self.language_param_key != "language_code":
                # Fallback for docs/examples that use language_code instead of language-code.
                url = self._with_query_params(self.ws_url, "language_code")
                self._ws = await connect_ws(url, headers=headers, max_queue=4)
            else:
                if status == 403:
                    logger.error("STT auth failed (403). Check SARVAM_API_KEY/SAARIKA_API_KEY and account access.")
                raise

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
            await self._ws.send(json.dumps({"type": "flush"}))
        except Exception:
            pass
        await self._ws.close()
        self._ws = None

    def _with_query_params(self, ws_url: str, language_key: str) -> str:
        url = urlparse(ws_url)
        query = {
            language_key: self.language,
            "sample_rate": str(self.sample_rate),
            "vad_signals": "true" if self.vad_signals else "false",
            "high_vad_sensitivity": "true" if self.high_vad_sensitivity else "false",
            "flush_signal": "true" if self.flush_signal else "false",
        }
        if self.input_audio_codec:
            query["input_audio_codec"] = self.input_audio_codec
        if self.model:
            query["model"] = self.model
        merged_query = url.query + ("&" if url.query else "") + urlencode(query)
        return urlunparse(url._replace(query=merged_query))

    @staticmethod
    def _extract_status(exc: Exception) -> Optional[int]:
        response = getattr(exc, "response", None)
        if response is None:
            return None
        status = getattr(response, "status_code", None)
        if status is None:
            status = getattr(response, "status", None)
        return status

    async def send_audio(self, pcm_chunk: bytes) -> None:
        if self._ws is None:
            raise RuntimeError("STT websocket is not connected")
        audio_b64 = base64.b64encode(pcm_chunk).decode("utf-8")
        if self.audio_encoding:
            encoding = self.audio_encoding
        else:
            if self.input_audio_codec and self.input_audio_codec.startswith("pcm"):
                encoding = "audio/wav"
            else:
                encoding = self.input_audio_codec
        if self.use_sdk:
            if hasattr(self._ws, "transcribe"):
                kwargs = {
                    "audio": audio_b64,
                    "encoding": "audio/wav",
                    "sample_rate": self.sample_rate,
                }
                kwargs = self._filter_kwargs(self._ws.transcribe, kwargs)
                result = self._ws.transcribe(**kwargs)
                if asyncio.iscoroutine(result):
                    await result
                return
            if (
                AudioData is not None
                and AudioMessage is not None
                and hasattr(self._ws, "_send_speech_to_text_streaming_audio_message")
            ):
                # SDK supports AudioMessage; include input_audio_codec for PCM streams.
                message = AudioMessage(
                    audio=AudioData(
                        data=audio_b64,
                        sample_rate=self.sample_rate,
                        encoding="audio/wav",
                        input_audio_codec=self.input_audio_codec,
                    )
                )
                result = self._ws._send_speech_to_text_streaming_audio_message(message=message)
                if asyncio.iscoroutine(result):
                    await result
                return
            raise RuntimeError("STT SDK client does not support audio send method")
        if self.audio_payload_format == "flat":
            payload = {
                "audio": audio_b64,
                "encoding": encoding,
                "sample_rate": self.sample_rate,
            }
        else:
            payload = {
                "audio": {
                    "data": audio_b64,
                    "sample_rate": self.sample_rate,
                    "encoding": encoding,
                }
            }
        await self._ws.send(json.dumps(payload))

    async def flush(self) -> None:
        if self._ws is None:
            return
        if self.use_sdk:
            if hasattr(self._ws, "flush"):
                result = self._ws.flush()
                if asyncio.iscoroutine(result):
                    await result
                return
            if hasattr(self._ws, "transcribe"):
                kwargs = {"audio": "", "flush": True}
                kwargs = self._filter_kwargs(self._ws.transcribe, kwargs)
                if kwargs:
                    result = self._ws.transcribe(**kwargs)
                    if asyncio.iscoroutine(result):
                        await result
                return
        await self._ws.send(json.dumps({"type": "flush"}))

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

    async def transcript_stream(self) -> AsyncGenerator[Transcript, None]:
        if self._ws is None:
            raise RuntimeError("STT websocket is not connected")
        stream = self._iter_messages() if self.use_sdk else self._ws
        async for message in stream:
            if isinstance(message, bytes):
                continue
            if not isinstance(message, dict) and hasattr(message, "data"):
                data_obj = getattr(message, "data", None)
                text = getattr(data_obj, "transcript", None) or getattr(data_obj, "text", None)
                if text:
                    language = getattr(data_obj, "language_code", None) or getattr(data_obj, "language", None)
                    yield Transcript(text=text, is_final=True, language=language, confidence=None)
                    continue
            data = self._coerce_dict(message)
            if data is None:
                text = getattr(message, "text", None) or getattr(message, "transcript", None)
                if text:
                    is_final = bool(getattr(message, "is_final", None) or getattr(message, "final", None))
                    language = getattr(message, "language", None) or getattr(message, "lang", None)
                    confidence = getattr(message, "confidence", None)
                    yield Transcript(text=text, is_final=is_final, language=language, confidence=confidence)
                continue

            if self.log_raw_messages and self._raw_log_count < 5:
                logger.info("STT raw message: %s", data)
                self._raw_log_count += 1

            if data.get("error"):
                logger.error("STT error: %s", data.get("error"))
                continue

            # Common shapes: {"text": "...", "is_final": false}
            if data.get("type") in {"speech_start", "speech_end"}:
                continue

            payload = data.get("data")
            if payload is not None and not isinstance(payload, dict):
                payload = self._coerce_dict(payload) or payload
            if not isinstance(payload, dict):
                payload = data
            if data.get("type") == "error" and isinstance(payload, dict):
                logger.error("STT error: %s", payload.get("error") or payload)
                continue
            if isinstance(payload, dict) and payload.get("error"):
                logger.error("STT error: %s", payload.get("error"))
                continue
            text = payload.get("text") or payload.get("transcript")
            is_final = bool(
                payload.get("is_final")
                or payload.get("final")
                or data.get("type") in {"final", "transcript", "data"}
                or data.get("event") == "final"
            )
            language = (
                payload.get("language")
                or payload.get("language_code")
                or payload.get("lang")
                or payload.get("detected_language")
            )
            confidence = payload.get("confidence")

            # Alternate shapes: {"results": [{"text": "...", "final": false}]}
            if text is None and isinstance(data.get("results"), list):
                for result in data["results"]:
                    text = result.get("text") or result.get("transcript")
                    is_final = bool(result.get("is_final") or result.get("final"))
                    language = language or result.get("language") or result.get("lang")
                    confidence = result.get("confidence")
                    if text:
                        yield Transcript(text=text, is_final=is_final, language=language, confidence=confidence)
                continue

            if not text:
                continue

            yield Transcript(text=text, is_final=is_final, language=language, confidence=confidence)
