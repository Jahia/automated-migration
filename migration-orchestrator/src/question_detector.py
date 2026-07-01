from __future__ import annotations

import json
import re
import time

from .models import HumanQuestion


def detect_question(text: str, step_id: str) -> HumanQuestion | None:
    pattern = r'```json\s*(\{[^`]*"type"\s*:\s*"human_question"[^`]*)\s*```'
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        match = re.search(r'(\{[^}]*"type"\s*:\s*"human_question"[^}]*"question"[^}]*\})', text, re.DOTALL)
    if match:
        try:
            raw = match.group(1) if match.lastindex else match.group(0)
            data = json.loads(raw)
            if data.get("type") == "human_question" and "question" in data:
                return HumanQuestion(
                    question_id=f"q_{step_id}_{int(time.time() * 1000)}",
                    step_id=step_id,
                    question=data["question"],
                    options=data.get("options", []),
                    default=data.get("default"),
                    timestamp=time.time() * 1000,
                )
        except (json.JSONDecodeError, ValueError):
            pass
    return None
