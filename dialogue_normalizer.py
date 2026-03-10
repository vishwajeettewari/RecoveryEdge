from __future__ import annotations

import re
import unicodedata

_PHRASE_ALIASES: tuple[tuple[str, str], ...] = (
    ("day after tomorrow", "परसों"),
    ("agle hafte", "अगले हफ्ते"),
    ("next week", "अगले हफ्ते"),
    ("call back", "callback"),
    ("call me later", "callback"),
    ("call later", "callback"),
    ("call kariye", "callback"),
    ("baad mein call karo", "callback"),
    ("baad mein call kariye", "callback"),
    ("kal", "कल"),
    ("parso", "परसों"),
    ("theek hai", "ठीक"),
    ("thik hai", "ठीक"),
    ("ho jayega", "हो जाएगा"),
    ("kar dunga", "कर दूंगा"),
    ("kar dungi", "कर दूंगी"),
    ("kar denge", "कर देंगे"),
    ("pay kar dunga", "भुगतान कर दूंगा"),
    ("pay kar dungi", "भुगतान कर दूंगी"),
)

_TOKEN_ALIASES = {
    "yes": "हाँ",
    "yeah": "हाँ",
    "yep": "हाँ",
    "ok": "ठीक",
    "okay": "ठीक",
    "sure": "ठीक",
    "haan": "हाँ",
    "han": "हाँ",
    "haanji": "हाँ",
    "hmm": "हूँ",
    "hmmm": "हूँ",
    "hm": "हूँ",
    "huh": "हूँ",
    "theek": "ठीक",
    "thik": "ठीक",
    "nahi": "नहीं",
    "nahin": "नहीं",
    "na": "नहीं",
    "tomorrow": "कल",
    "today": "आज",
    "callback": "callback",
    "ਨਹੀਂ": "नहीं",
    "ਹਾਂ": "हाँ",
    "ਹਾਂਜੀ": "हाँ",
    "ਜੀ": "जी",
    "ਠੀਕ": "ठीक",
    "ਕੱਲ": "कल",
    "ਪਰਸੋਂ": "परसों",
    "ਹੂੰ": "हूँ",
    "হুম": "हूँ",
    "হ্যাঁ": "हाँ",
    "হ্যা": "हाँ",
    "না": "नहीं",
    "ঠিক": "ठीक",
    "কাল": "कल",
    "পরশু": "परसों",
}


def normalize_borrower_text(text: str) -> str:
    value = unicodedata.normalize("NFKC", (text or "")).casefold()
    if not value:
        return ""

    for src, dst in _PHRASE_ALIASES:
        value = re.sub(rf"\b{re.escape(src)}\b", dst, value)

    normalized_words: list[str] = []
    for raw_token in value.split():
        token = raw_token
        if token.isascii():
            token = re.sub(r"[^a-z0-9:/-]", "", token)
        else:
            token = token.strip(".,!?;:'\"`~()[]{}<>|")
        if not token:
            continue
        normalized_words.append(_TOKEN_ALIASES.get(token, token))

    out: list[str] = []
    for ch in " ".join(normalized_words):
        if ch.isspace():
            out.append(" ")
            continue
        cat = unicodedata.category(ch)
        if cat[0] in {"L", "N"} or cat in {"Mn", "Mc", "Me"} or ch in {":", "/", "-"}:
            out.append(ch)
        else:
            out.append(" ")
    return " ".join("".join(out).split())


def contains_short_acknowledgement(text: str) -> bool:
    norm = normalize_borrower_text(text)
    if not norm:
        return False
    tokens = norm.split()
    if len(tokens) > 3:
        return False
    ack_tokens = {
        "हाँ",
        "जी",
        "हूँ",
        "ठीक",
        "हो",
        "जाएगा",
        "होजाएगा",
    }
    if norm == "हो जाएगा":
        return True
    return all(token in ack_tokens for token in tokens)
