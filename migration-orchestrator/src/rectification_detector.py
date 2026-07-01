from __future__ import annotations

import json
import re

from pydantic import ValidationError

from .models import (
    EpicReviewApproved,
    EpicReviewRectify,
    EpicReviewResult,
)


def parse_epic_review_result(text: str) -> EpicReviewResult | None:
    json_str = extract_json(text)
    if not json_str:
        return None
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        return None

    action = data.get("action")
    if action == "approved":
        try:
            return EpicReviewApproved(**data)
        except ValidationError:
            return None
    elif action == "rectify":
        try:
            normalized = normalize_rectify(data)
            return EpicReviewRectify(**normalized)
        except ValidationError:
            return None
    return None


def normalize_rectify(data: dict) -> dict:
    stories = data.get("new_stories", data.get("new_steps", []))
    for s in stories:
        if "acceptance_criteria" not in s:
            s["acceptance_criteria"] = []
        if "depends_on" not in s:
            s["depends_on"] = []
        if "github_issues" not in s:
            s["github_issues"] = []
        if "reason" not in s:
            s["reason"] = ""
    data["new_stories"] = stories
    return data


def extract_json(text: str) -> str | None:
    patterns = [
        r'```json\s*(\{.*?\})\s*```',
        r'```\s*(\{.*?\})\s*```',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1)
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None
