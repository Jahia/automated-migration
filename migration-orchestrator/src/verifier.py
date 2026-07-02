from __future__ import annotations

import asyncio
import json
import logging
import re
import time

from .models import AgentResult, StepState, VerificationResult
from .opencode_client import OpenCodeClient

log = logging.getLogger(__name__)


def parse_agent_result(text: str, step: StepState) -> AgentResult | None:
    json_str = extract_json(text)
    if not json_str:
        return None
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        return None

    if data.get("step_id") != step.id:
        data["step_id"] = step.id
    if not data.get("agent"):
        data["agent"] = "code"
    if not data.get("status"):
        data["status"] = "completed"
    if not data.get("summary"):
        data["summary"] = ""

    try:
        return AgentResult(**data)
    except Exception:
        return None


PROBE_TIMEOUT_S = 600  # a probe may drive a real browser (playwright) — cap, don't hang


def probe_commands(step: StepState) -> list[str]:
    """The deterministic gate: every `PROBE: <cmd>` in the step's acceptance
    criteria. Extracted and executed by the ENGINE, never trusted to the agent's
    self-report — an LLM that skips or excuses a failing probe must not be able
    to advance the run."""
    cmds: list[str] = []
    for crit in step.acceptance_criteria or []:
        m = re.match(r"\s*PROBE:\s*(.+)", crit, re.DOTALL)
        if m:
            cmds.append(" ".join(m.group(1).split()))
    return cmds


async def verify_result(step: StepState, result: AgentResult, repo_dir: str, run_id: str | None = None) -> VerificationResult:
    checks: list[str] = []
    errors: list[str] = []

    if result.step_id == step.id:
        checks.append("step_id_matches")
    else:
        errors.append(f"step_id mismatch: expected {step.id}, got {result.step_id}")

    if result.status in ("completed", "failed", "blocked"):
        checks.append("status_valid")
    else:
        errors.append(f"invalid status: {result.status}")

    if result.summary:
        checks.append("summary_present")
    else:
        errors.append("missing summary")

    if step.task_type in ("build", "edit_code", "refactor", "write_tests") and not result.modified_files:
        checks.append("no_files_claimed")
    elif result.modified_files:
        checks.append("files_claimed")

    # Engine-enforced probes first (the real gate), then any agent-declared
    # commands not already covered. dict.fromkeys dedups while keeping order.
    to_run = list(dict.fromkeys(probe_commands(step) + list(result.commands_requested)))
    for cmd in to_run:
        cmd_start = time.time() * 1000
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                cwd=repo_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=PROBE_TIMEOUT_S)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                errors.append(f"Command timed out after {PROBE_TIMEOUT_S}s: {cmd[:80]}")
                continue
            cmd_duration = time.time() * 1000 - cmd_start
            stdout_text = stdout.decode("utf-8", errors="replace")[:2000]
            stderr_text = stderr.decode("utf-8", errors="replace")[:2000]

            # Log probe execution via audit if run_id available
            if run_id:
                from .audit import get_audit_logger
                audit = get_audit_logger(run_id)
                audit.probe_executed(
                    epic_id="", story_id="", step_id=step.id,
                    command=cmd, exit_code=proc.returncode,
                    stdout=stdout_text, stderr=stderr_text,
                    duration_ms=cmd_duration,
                )

            if proc.returncode == 0:
                checks.append(f"command_passed:{cmd[:50]}")
            else:
                errors.append(f"Command failed: {cmd[:50]} (exit {proc.returncode})\nstdout: {stdout_text[:500]}\nstderr: {stderr_text[:500]}")
        except Exception as e:
            cmd_duration = time.time() * 1000 - cmd_start
            errors.append(f"Command error: {cmd[:50]} ({e})")
            if run_id:
                from .audit import get_audit_logger
                audit = get_audit_logger(run_id)
                audit.probe_executed(
                    epic_id="", story_id="", step_id=step.id,
                    command=cmd, exit_code=-1,
                    stdout="", stderr=str(e)[:2000],
                    duration_ms=cmd_duration,
                )

    return VerificationResult(passed=len(errors) == 0, checks=checks, errors=errors)


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
