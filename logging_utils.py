import json
import logging
import os
import time
from logging.handlers import RotatingFileHandler
from typing import Any, Optional

from config import get_env, get_env_bool


class JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = {
            "ts": round(time.time(), 3),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            base["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(base, ensure_ascii=False)


_LOGGING_CONFIGURED = False


def configure_logging(
    *,
    default_level: str = "INFO",
    log_file: Optional[str] = None,
    json_output: Optional[bool] = None,
) -> None:
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return
    level = (get_env("LOG_LEVEL", default_level) or default_level).upper()
    use_json = get_env_bool("LOG_JSON", True) if json_output is None else json_output
    file_path = log_file or get_env("LOG_FILE")

    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if file_path:
        os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
        rotate_mb = int(get_env("LOG_ROTATE_MB", "20"))
        backup_count = int(get_env("LOG_BACKUP_COUNT", "5"))
        handlers.append(
            RotatingFileHandler(
                file_path,
                maxBytes=rotate_mb * 1024 * 1024,
                backupCount=backup_count,
                encoding="utf-8",
            )
        )

    if use_json:
        formatter = JsonLineFormatter()
    else:
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    root = logging.getLogger()
    root.setLevel(level)
    for handler in handlers:
        handler.setFormatter(formatter)
        root.addHandler(handler)
    _LOGGING_CONFIGURED = True


def log_event(logger, event: str, **fields: Any) -> None:
    payload = {
        "event": event,
        "ts": round(time.time(), 3),
        **fields,
    }
    logger.info("%s", json.dumps(payload, ensure_ascii=False))


def log_exception(logger, event: str, err: Exception, **fields: Any) -> None:
    payload = {
        "event": event,
        "ts": round(time.time(), 3),
        "error": str(err),
        **fields,
    }
    logger.exception("%s", json.dumps(payload, ensure_ascii=False))


def mask_secret(value: Optional[str], show: int = 4) -> Optional[str]:
    if not value:
        return value
    value = value.strip()
    if len(value) <= show:
        return "*" * len(value)
    return f"{value[:show]}***"
