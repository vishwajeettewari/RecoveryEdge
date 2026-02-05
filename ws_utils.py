from typing import Any, Dict, Optional

import websockets


def connect_ws(url: str, headers: Optional[Dict[str, str]] = None, max_queue: int = 4):
    if headers is None:
        headers = {}
    try:
        return websockets.connect(url, additional_headers=headers, max_queue=max_queue)
    except TypeError:
        return websockets.connect(url, extra_headers=headers, max_queue=max_queue)
