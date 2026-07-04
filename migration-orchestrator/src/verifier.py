from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time

from .config import settings
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

PROBE_RE = re.compile(r"\s*PROBE(?:\[(\d+)\])?:\s*(.+)", re.DOTALL)


def default_probe_timeout() -> float:
    """Default per-probe timeout: ORCHESTRATOR_PROBE_TIMEOUT (seconds) from the
    environment, falling back to PROBE_TIMEOUT_S."""
    try:
        return float(os.environ["ORCHESTRATOR_PROBE_TIMEOUT"])
    except (KeyError, ValueError):
        return float(PROBE_TIMEOUT_S)


def probe_env(repo_dir: str) -> dict[str, str]:
    """Environment for probe subprocesses: the orchestrator's own environment
    plus the repo's .env.local (KEY=VALUE lines; comments and blanks ignored;
    path overridable via ORCHESTRATOR_ENV_FILE). Probes and plans reference
    $JAHIA_URL / $JAHIA_USER / $JAHIA_PASS — literal credentials must never
    appear in prompts, state_json, or the audit log."""
    env = dict(os.environ)
    path = settings.env_file
    if not os.path.isabs(path):
        path = os.path.join(repo_dir, path)
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip()
    except OSError:
        pass
    return env


def probe_commands(step: StepState) -> list[tuple[str, float]]:
    """The deterministic gate: every `PROBE: <cmd>` in the step's acceptance
    criteria, returned as (command, timeout_seconds). `PROBE[NNN]: <cmd>` sets a
    per-probe timeout override (e.g. a cold `yarn install && yarn build` that
    outlasts the default); plain `PROBE:` gets default_probe_timeout(). Extracted
    and executed by the ENGINE, never trusted to the agent's self-report — an LLM
    that skips or excuses a failing probe must not be able to advance the run."""
    cmds: list[tuple[str, float]] = []
    for crit in step.acceptance_criteria or []:
        m = PROBE_RE.match(crit)
        if m:
            timeout_s = float(m.group(1)) if m.group(1) else default_probe_timeout()
            cmds.append((" ".join(m.group(2).split()), timeout_s))
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
    # commands not already covered (those get the default timeout). setdefault
    # dedups while keeping order and preserving a probe's timeout override.
    to_run: dict[str, float] = {}
    for cmd, timeout_s in probe_commands(step):
        to_run.setdefault(cmd, timeout_s)
    for cmd in result.commands_requested:
        to_run.setdefault(cmd, default_probe_timeout())
    env = probe_env(repo_dir)
    for cmd, timeout_s in to_run.items():
        cmd_start = time.time() * 1000
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                cwd=repo_dir,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                errors.append(f"Command timed out after {int(timeout_s)}s: {cmd[:80]}")
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

    # Authority ladder (P5, M4 live find): engine-enforced PROBEs are the
    # deterministic truth; the agent's final JSON is narrative. When EVERY
    # probe passed and the only complaints are about the agent's reply shape
    # (missing summary / step_id echo), pass with a note instead of burning
    # retries re-running work the probes already proved (step_pages lost 2
    # attempts to a DeepSeek reply without the JSON envelope).
    narrative_only = {"missing summary"}
    if errors and all(e in narrative_only for e in errors) and any(
            c.startswith("command_passed:") for c in checks) and not any(
            e.startswith(("Command", "step_id mismatch", "invalid status")) for e in errors):
        checks.append("passed_on_probes_despite_narrative_gaps:" + ";".join(errors))
        errors = []

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
