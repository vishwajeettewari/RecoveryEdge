from __future__ import annotations

import base64
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Dict, Optional, Tuple


def _now_ts() -> float:
    return round(time.time(), 3)


class ActionRouter:
    def __init__(
        self,
        pay_base_url: str = "https://pay.example/demo",
        *,
        twilio_account_sid: Optional[str] = None,
        twilio_auth_token: Optional[str] = None,
        twilio_from_number: Optional[str] = None,
        twilio_whatsapp_from: Optional[str] = None,
        twilio_send_enabled: Optional[bool] = None,
        twilio_timeout_s: float = 8.0,
    ) -> None:
        self.pay_base_url = (pay_base_url or "").rstrip("/") or "https://pay.example/demo"
        self._twilio_account_sid = (twilio_account_sid or "").strip()
        self._twilio_auth_token = (twilio_auth_token or "").strip()
        self._twilio_from_number = (twilio_from_number or "").strip()
        self._twilio_whatsapp_from = (twilio_whatsapp_from or "").strip()
        self._twilio_timeout_s = max(1.0, float(twilio_timeout_s or 8.0))
        if twilio_send_enabled is None:
            self._twilio_send_enabled = bool(
                self._twilio_account_sid and self._twilio_auth_token and self._twilio_from_number
            )
        else:
            self._twilio_send_enabled = bool(twilio_send_enabled)

    @staticmethod
    def _to_twilio_number(phone: Optional[str], channel: str) -> Optional[str]:
        value = str(phone or "").strip()
        if not value:
            return None
        is_whatsapp = value.lower().startswith("whatsapp:")
        if channel == "whatsapp":
            return value if is_whatsapp else f"whatsapp:{value}"
        return value.split(":", 1)[1] if is_whatsapp else value

    def _twilio_from_for_channel(self, channel: str) -> Optional[str]:
        if channel == "whatsapp":
            value = self._twilio_whatsapp_from or self._twilio_from_number
            if not value:
                return None
            return value if value.lower().startswith("whatsapp:") else f"whatsapp:{value}"
        value = self._twilio_from_number
        if not value:
            return None
        if value.lower().startswith("whatsapp:"):
            return value.split(":", 1)[1]
        return value

    def _send_twilio_message(
        self,
        *,
        to_number: str,
        from_number: str,
        body: str,
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        account_sid = self._twilio_account_sid
        auth_token = self._twilio_auth_token
        if not account_sid or not auth_token:
            return None, None, "twilio_credentials_missing"

        endpoint = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
        form_payload = urllib.parse.urlencode({"To": to_number, "From": from_number, "Body": body}).encode("utf-8")
        auth_b64 = base64.b64encode(f"{account_sid}:{auth_token}".encode("utf-8")).decode("ascii")

        req = urllib.request.Request(endpoint, data=form_payload, method="POST")
        req.add_header("Authorization", f"Basic {auth_b64}")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        req.add_header("Accept", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=self._twilio_timeout_s) as response:
                payload = response.read().decode("utf-8", errors="replace")
            data = json.loads(payload) if payload else {}
            sid = str(data.get("sid") or "").strip() or None
            status = str(data.get("status") or "").strip() or None
            if sid:
                return sid, status, None
            err = str(data.get("message") or data.get("error_message") or "twilio_send_failed").strip()
            return None, None, err or "twilio_send_failed"
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                payload = exc.read().decode("utf-8", errors="replace")
                data = json.loads(payload) if payload else {}
                detail = str(data.get("message") or data.get("error_message") or "").strip()
            except Exception:
                detail = ""
            return None, None, detail or f"twilio_http_{exc.code}"
        except Exception as exc:
            return None, None, str(exc)

    @staticmethod
    def _normalize_e164(phone: Optional[str], default_country_code: str = "+91") -> Optional[str]:
        raw = str(phone or "").strip()
        if not raw:
            return None
        if raw.lower().startswith("whatsapp:"):
            raw = raw.split(":", 1)[1].strip()
        # Keep only digits and +, then normalize into E.164.
        cleaned = re.sub(r"[^0-9+]", "", raw)
        if cleaned.startswith("00"):
            cleaned = f"+{cleaned[2:]}"
        if cleaned.startswith("+"):
            digits = re.sub(r"[^0-9]", "", cleaned)
            if 8 <= len(digits) <= 15:
                return f"+{digits}"
            return None
        digits = re.sub(r"[^0-9]", "", cleaned)
        if len(digits) == 10:
            cc = (default_country_code or "+91").strip()
            if not cc.startswith("+"):
                cc = f"+{cc}"
            cc_digits = re.sub(r"[^0-9]", "", cc)
            if not cc_digits:
                cc_digits = "91"
            return f"+{cc_digits}{digits}"
        if 11 <= len(digits) <= 15:
            return f"+{digits}"
        return None

    def _twilio_voice_from_number(self) -> Optional[str]:
        value = (self._twilio_from_number or "").strip()
        if not value:
            return None
        if value.lower().startswith("whatsapp:"):
            value = value.split(":", 1)[1]
        return self._normalize_e164(value, default_country_code="+1")

    def _send_twilio_voice_call(
        self,
        *,
        to_number: str,
        from_number: str,
        twiml: str,
        timeout_s: int = 25,
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        account_sid = self._twilio_account_sid
        auth_token = self._twilio_auth_token
        if not account_sid or not auth_token:
            return None, None, "twilio_credentials_missing"

        endpoint = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls.json"
        form_payload = urllib.parse.urlencode(
            {
                "To": to_number,
                "From": from_number,
                "Twiml": twiml,
                "Timeout": max(5, int(timeout_s or 25)),
            }
        ).encode("utf-8")
        auth_b64 = base64.b64encode(f"{account_sid}:{auth_token}".encode("utf-8")).decode("ascii")

        req = urllib.request.Request(endpoint, data=form_payload, method="POST")
        req.add_header("Authorization", f"Basic {auth_b64}")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        req.add_header("Accept", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=self._twilio_timeout_s) as response:
                payload = response.read().decode("utf-8", errors="replace")
            data = json.loads(payload) if payload else {}
            sid = str(data.get("sid") or "").strip() or None
            status = str(data.get("status") or "").strip() or None
            if sid:
                return sid, status, None
            err = str(data.get("message") or data.get("error_message") or "twilio_call_failed").strip()
            return None, None, err or "twilio_call_failed"
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                payload = exc.read().decode("utf-8", errors="replace")
                data = json.loads(payload) if payload else {}
                detail = str(data.get("message") or data.get("error_message") or "").strip()
            except Exception:
                detail = ""
            return None, None, detail or f"twilio_http_{exc.code}"
        except Exception as exc:
            return None, None, str(exc)

    def send_payment_link(
        self,
        *,
        session_id: str,
        customer_id: Optional[str],
        customer_phone: Optional[str],
        amount: Optional[str],
        channel: str = "whatsapp",
    ) -> Dict[str, Any]:
        channel = (channel or "whatsapp").strip().lower()
        token = uuid.uuid4().hex[:10]
        link = f"{self.pay_base_url}?sid={session_id}&cid={customer_id or ''}&amt={amount or ''}&t={token}"
        body = f"Payment link for your overdue amount{(' INR ' + str(amount)) if amount else ''}: {link}"
        result = {
            "ts": _now_ts(),
            "channel": channel,
            "to": customer_phone,
            "amount": amount,
            "link": link,
            "body": body,
            "message_id": f"msg-{token}",
            "provider": "mock",
            "delivery_status": "simulated",
            "delivery_ok": True,
        }
        if not self._twilio_send_enabled:
            return result
        if channel not in {"sms", "whatsapp"}:
            return result

        to_number = self._to_twilio_number(customer_phone, channel)
        from_number = self._twilio_from_for_channel(channel)
        if not to_number or not from_number:
            result.update(
                {
                    "provider": "twilio",
                    "delivery_status": "failed",
                    "delivery_ok": False,
                    "delivery_error": "missing_to_or_from_number",
                }
            )
            return result

        sid, status, err = self._send_twilio_message(to_number=to_number, from_number=from_number, body=body)
        if sid:
            result.update(
                {
                    "message_id": sid,
                    "provider": "twilio",
                    "delivery_status": status or "queued",
                    "delivery_ok": True,
                }
            )
            return result

        result.update(
            {
                "provider": "twilio",
                "delivery_status": "failed",
                "delivery_ok": False,
                "delivery_error": err or "twilio_send_failed",
            }
        )
        return result

    def place_test_voice_call(
        self,
        *,
        customer_phone: Optional[str],
        customer_name: Optional[str] = None,
        amount: Optional[str] = None,
        timeout_s: int = 25,
    ) -> Dict[str, Any]:
        name = (customer_name or "customer").strip() or "customer"
        amount_text = str(amount or "").strip()
        result = {
            "ts": _now_ts(),
            "channel": "voice",
            "to": customer_phone,
            "provider": "twilio",
            "delivery_status": "failed",
            "delivery_ok": False,
            "call_sid": None,
            "call_status": None,
        }
        if not self._twilio_send_enabled:
            result["delivery_error"] = "twilio_disabled"
            return result
        to_number = self._normalize_e164(customer_phone)
        from_number = self._twilio_voice_from_number()
        if not to_number or not from_number:
            result["delivery_error"] = "invalid_to_or_from_number"
            return result

        intro = f"Hello {name}. This is TuringEdge collections agent test call."
        amount_line = (
            f"Our records show an overdue amount of rupees {amount_text}. "
            if amount_text
            else "This call verifies outbound telephony setup. "
        )
        outro = "No action is required on this test call. Thank you."
        twiml = (
            "<Response>"
            f"<Say voice=\"alice\">{html.escape(intro)}</Say>"
            "<Pause length=\"1\"/>"
            f"<Say voice=\"alice\">{html.escape(amount_line + outro)}</Say>"
            "</Response>"
        )
        sid, status, err = self._send_twilio_voice_call(
            to_number=to_number,
            from_number=from_number,
            twiml=twiml,
            timeout_s=timeout_s,
        )
        result["normalized_to"] = to_number
        result["from"] = from_number
        if sid:
            result.update(
                {
                    "delivery_status": status or "queued",
                    "delivery_ok": True,
                    "call_sid": sid,
                    "call_status": status or "queued",
                }
            )
            return result
        result["delivery_error"] = err or "twilio_call_failed"
        return result

    def place_agent_stream_call(
        self,
        *,
        customer_phone: Optional[str],
        stream_ws_url: str,
        customer_name: Optional[str] = None,
        amount: Optional[str] = None,
        customer_id: Optional[str] = None,
        campaign_id: Optional[str] = None,
        language: Optional[str] = None,
        tts_speaker: Optional[str] = None,
        timeout_s: int = 25,
    ) -> Dict[str, Any]:
        result = {
            "ts": _now_ts(),
            "channel": "voice",
            "to": customer_phone,
            "provider": "twilio",
            "delivery_status": "failed",
            "delivery_ok": False,
            "call_sid": None,
            "call_status": None,
        }
        if not self._twilio_send_enabled:
            result["delivery_error"] = "twilio_disabled"
            return result
        stream_url = (stream_ws_url or "").strip()
        if not stream_url.startswith("wss://"):
            result["delivery_error"] = "invalid_stream_ws_url"
            return result
        to_number = self._normalize_e164(customer_phone)
        from_number = self._twilio_voice_from_number()
        if not to_number or not from_number:
            result["delivery_error"] = "invalid_to_or_from_number"
            return result

        def _param(name: str, value: Optional[str]) -> str:
            if value is None:
                return ""
            text = str(value).strip()
            if not text:
                return ""
            return f"<Parameter name=\"{html.escape(name)}\" value=\"{html.escape(text)}\"/>"

        params = "".join(
            [
                _param("customer_name", customer_name),
                _param("amount_due", amount),
                _param("customer_id", customer_id),
                _param("campaign_id", campaign_id),
                _param("language", language),
                _param("tts_speaker", tts_speaker),
                _param("phone", to_number),
            ]
        )
        twiml = (
            "<Response>"
            "<Connect>"
            f"<Stream url=\"{html.escape(stream_url)}\">"
            f"{params}"
            "</Stream>"
            "</Connect>"
            "</Response>"
        )
        sid, status, err = self._send_twilio_voice_call(
            to_number=to_number,
            from_number=from_number,
            twiml=twiml,
            timeout_s=timeout_s,
        )
        result["normalized_to"] = to_number
        result["from"] = from_number
        result["stream_ws_url"] = stream_url
        if sid:
            result.update(
                {
                    "delivery_status": status or "queued",
                    "delivery_ok": True,
                    "call_sid": sid,
                    "call_status": status or "queued",
                }
            )
            return result
        result["delivery_error"] = err or "twilio_call_failed"
        return result

    def escalate_ticket(
        self,
        *,
        session_id: str,
        customer_id: Optional[str],
        category: str,
        reason: str,
        last_user_text: str,
        last_assistant_text: str,
    ) -> Dict[str, Any]:
        tid = f"TCK-{uuid.uuid4().hex[:8].upper()}"
        summary = (
            f"Escalation requested. Category={category}. Reason={reason}. "
            f"Last customer: {last_user_text[:160]}. Last agent: {last_assistant_text[:160]}."
        )
        return {
            "ts": _now_ts(),
            "ticket_id": tid,
            "session_id": session_id,
            "customer_id": customer_id,
            "category": category,
            "reason": reason,
            "summary": summary,
            "status": "open",
        }
