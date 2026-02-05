import asyncio
import inspect
import json
import logging
from typing import Any, AsyncGenerator, Dict, Optional, Sequence

import aiohttp

try:
    from sarvamai import AsyncSarvamAI
except Exception:  # pragma: no cover - optional dependency
    AsyncSarvamAI = None

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = ("""
You are a polite, empathetic, and firm KreditBee collections officer calling about an overdue loan.

Your job is NOT to freely chat. Your job is to strictly follow a stateful collections flow and ask ONLY the next required question.

Rules you MUST follow:
- Speak in the customer’s language.
- Ask only ONE clear question at a time.
- Never repeat a greeting or a question already answered.
- Never use placeholders like [Customer Name].
- If a value is already known in context, use it confidently.
- If interrupted, acknowledge and continue logically.
- Stop speaking immediately after asking a question.

Compliance rules:
- Never ask for OTPs, card numbers, CVV, passwords, or full bank details.
- Never invent amounts, dates, or details.

Conversation objective (state driven):
1) Confirm identity.
2) Confirm awareness of overdue payment.
3) Capture one of: payment done, promise-to-pay date, or callback time.
4) Close politely after capturing the action.

You MUST behave like a deterministic collections agent, not a chatbot.
""")


class SarvamLLMService:
    def __init__(
        self,
        base_url: str = "https://api.sarvam.ai",
        api_key: Optional[str] = None,
        model: str = "sarvam-m",
        temperature: float = 0.4,
        use_sdk: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.use_sdk = use_sdk

    @staticmethod
    def _filter_kwargs(func, kwargs: dict) -> dict:
        try:
            sig = inspect.signature(func)
        except (TypeError, ValueError):
            return {k: v for k, v in kwargs.items() if v is not None}
        return {k: v for k, v in kwargs.items() if k in sig.parameters and v is not None}

    @staticmethod
    def _normalize_messages(messages: Sequence[Dict[str, Any]]) -> list[Dict[str, Any]]:
        """Sarvam requires exactly one system message at index 0.

        This function:
        - Collects ALL system messages (wherever they appear)
        - Merges them into a single system prompt
        - Ensures the merged system prompt is the first message
        - Drops any additional system messages from the list
        """
        if not messages:
            return [{"role": "system", "content": SYSTEM_PROMPT.strip()}]

        system_chunks = []
        non_system = []
        for m in list(messages):
            if not isinstance(m, dict):
                continue
            role = (m.get("role") or "").strip().lower()
            if role == "system":
                c = (m.get("content") or "").strip()
                if c:
                    system_chunks.append(c)
            else:
                non_system.append(m)

        merged_system = "\n\n".join(system_chunks).strip()
        if not merged_system:
            merged_system = SYSTEM_PROMPT.strip()

        return [{"role": "system", "content": merged_system}] + non_system

    async def _stream_tokens_sdk(
        self,
        messages: Sequence[Dict[str, Any]],
        language: Optional[str],
    ) -> AsyncGenerator[str, None]:
        if AsyncSarvamAI is None:
            raise RuntimeError("sarvamai SDK not installed. Run: pip install sarvamai")
        if not self.api_key:
            logger.warning("LLM api key missing; connection will likely be rejected.")
        client = AsyncSarvamAI(api_subscription_key=self.api_key or "")
        chat = getattr(client, "chat", None)
        call = None
        if chat is not None:
            completions = getattr(chat, "completions", None)
            if completions is not None:
                call = getattr(completions, "create", None) or completions
        if call is None and hasattr(client, "chat_completions"):
            call = client.chat_completions
        if call is None:
            raise RuntimeError("sarvamai SDK missing chat completions interface")

        kwargs = {
            "model": self.model,
            "messages": list(messages),
            "temperature": self.temperature,
            "stream": True,
        }
        kwargs = self._filter_kwargs(call, kwargs)
        result = call(**kwargs)
        response = await result if asyncio.iscoroutine(result) else result

        async def iter_events():
            if hasattr(response, "__aiter__"):
                async for item in response:
                    yield item
            elif hasattr(response, "__iter__"):
                for item in response:
                    yield item
            else:
                yield response

        async for event in iter_events():
            if isinstance(event, str):
                try:
                    data = json.loads(event)
                except json.JSONDecodeError:
                    continue
            elif isinstance(event, dict):
                data = event
            elif hasattr(event, "model_dump"):
                try:
                    data = event.model_dump()
                except Exception:
                    data = None
            elif hasattr(event, "dict"):
                try:
                    data = event.dict()
                except Exception:
                    data = None
            else:
                data = None
            if data is None:
                token = getattr(event, "token", None) or getattr(event, "content", None)
                if token:
                    yield token
                continue
            token = self._extract_token(data)
            if token:
                yield token

    async def stream_tokens(
        self,
        user_text: Optional[str] = None,
        messages: Optional[Sequence[Dict[str, Any]]] = None,
        language: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        # CHANGE: Allow full chat history or fallback to single-turn prompt.
        if messages is None:
            if not user_text:
                raise ValueError("Either user_text or messages must be provided")
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ]

        # Normalize to Sarvam requirement: exactly one system message at index 0.
        messages = self._normalize_messages(list(messages))

        # Append state rules ONCE (avoid growing the prompt every turn).
        if messages and messages[0].get("role") == "system":
            sys_text = messages[0].get("content", "") or ""
            marker = "State rules you must follow:"
            if marker not in sys_text:
                sys_text = sys_text.rstrip() + (
                    "\n\nState rules you must follow:\n"
                    "- Internally track: identity_confirmed, awareness_confirmed, payment_status, ptp_date, callback_time.\n"
                    "- Ask ONLY the next missing item.\n"
                    "- Never repeat any question already answered.\n"
                )
                messages[0] = {"role": "system", "content": sys_text}

        # Add target language hint ONCE.
        if language and messages and messages[0].get("role") == "system":
            sys_text = messages[0].get("content", "") or ""
            if "Respond in" not in sys_text:
                language_hint = self._language_hint(language)
                messages[0] = {"role": "system", "content": f"{sys_text} Respond in {language_hint}."}

        if self.use_sdk:
            async for token in self._stream_tokens_sdk(messages, language):
                yield token
            return

        headers = {}
        if self.api_key:
            headers["api-subscription-key"] = self.api_key
        headers["Content-Type"] = "application/json"

        payload = {
            "model": self.model,
            "stream": True,
            "temperature": self.temperature,
            "messages": messages,
        }
        if language:
            # Keep prompt-language alignment in system prompt; no extra field required.
            pass

        url = f"{self.base_url}/v1/chat/completions"

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                content_type = response.headers.get("Content-Type", "")
                if "text/event-stream" not in content_type:
                    data = await response.json()
                    token = self._extract_token(data)
                    if token:
                        yield token
                    return

                buffer = ""
                async for chunk in response.content.iter_any():
                    if not chunk:
                        continue
                    buffer += chunk.decode("utf-8", errors="ignore")
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line.replace("data:", "", 1).strip()
                        if data_str == "[DONE]":
                            return
                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        token = self._extract_token(data)
                        if token:
                            yield token

    def _extract_token(self, data: dict) -> Optional[str]:
        if data.get("error"):
            logger.error("LLM error: %s", data.get("error"))
            return None
        if isinstance(data.get("choices"), list) and data["choices"]:
            choice = data["choices"][0]
            delta = choice.get("delta") or {}
            token = delta.get("content")
            if token:
                return token
        return data.get("token") or data.get("content")

    @staticmethod
    def _language_hint(code: str) -> str:
        normalized = code.strip().lower()
        mapping = {
            "en": "English",
            "en-in": "English",
            "hi": "Hindi",
            "hi-in": "Hindi",
            "ta": "Tamil",
            "ta-in": "Tamil",
            "te": "Telugu",
            "te-in": "Telugu",
            "kn": "Kannada",
            "kn-in": "Kannada",
            "ml": "Malayalam",
            "ml-in": "Malayalam",
            "bn": "Bengali",
            "bn-in": "Bengali",
            "mr": "Marathi",
            "mr-in": "Marathi",
            "gu": "Gujarati",
            "gu-in": "Gujarati",
            "pa": "Punjabi",
            "pa-in": "Punjabi",
            "or": "Odia",
            "or-in": "Odia",
            "ur": "Urdu",
            "ur-in": "Urdu",
        }
        return mapping.get(normalized, code)
