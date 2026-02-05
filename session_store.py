import json
import os
import time
from typing import List, Dict, Any, Optional


class SessionStore:
    def __init__(self, base_dir: str, session_id: str) -> None:
        self.base_dir = base_dir
        self.session_id = session_id
        os.makedirs(base_dir, exist_ok=True)
        self.path = os.path.join(base_dir, f"{session_id}.jsonl")

    def load(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.path):
            return []
        messages: List[Dict[str, Any]] = []
        with open(self.path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                role = data.get("role")
                content = data.get("content")
                if role and content:
                    messages.append({"role": role, "content": content})
        return messages

    def append(self, role: str, content: str, **extra: Any) -> None:
        record = {
            "ts": round(time.time(), 3),
            "role": role,
            "content": content,
            **extra,
        }
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def clear(self) -> None:
        if os.path.exists(self.path):
            os.remove(self.path)

    def save_state(self, state: Dict[str, Any]) -> None:
        """Save session state (facts, policy) to a separate state file."""
        state_path = os.path.join(self.base_dir, f"{self.session_id}.state.json")
        with open(state_path, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2)

    def load_state(self) -> Optional[Dict[str, Any]]:
        """Load session state (facts, policy) from state file."""
        state_path = os.path.join(self.base_dir, f"{self.session_id}.state.json")
        if not os.path.exists(state_path):
            return None
        try:
            with open(state_path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (json.JSONDecodeError, IOError):
            return None
