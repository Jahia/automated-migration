"""Structured audit logger for orchestration runs.

Writes per-run, per-step logs to files AND emits structured events.
Every significant state transition, prompt sent, probe executed, and error
is captured with full context for post-mortem analysis.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from .config import settings

log = logging.getLogger(__name__)

# P5 observability: the audit JSONL used to default to /tmp/orch-audit — outside
# the repo, cleared by any OS tmp-reaper, and gone on a reboot. Anchored on the
# package dir (…/migration-orchestrator/logs/audit), like cost_tracker's
# DEFAULT_COST_DIR — NEVER a bare relative string (a relative default resolves
# against the process CWD, which is exactly how a stray
# migration-orchestrator/migration-orchestrator/ tree appeared elsewhere in this
# repo). Override with ORCHESTRATOR_AUDIT_DIR (settings.audit_dir) for ops.
DEFAULT_AUDIT_DIR = Path(__file__).resolve().parent.parent / "logs" / "audit"

# Pre-P5 location. Readers (audit_log_path / read_step_audit_entries) fall back
# here so a run recorded before the relocation stays readable; writers
# (RunAuditLogger) never write here anymore.
LEGACY_AUDIT_DIR = Path("/tmp/orch-audit")


def default_audit_dir() -> Path:
    """The directory new audit JSONL files are written to: settings.audit_dir
    (ORCHESTRATOR_AUDIT_DIR) when set, else the persistent package-anchored
    default."""
    return Path(settings.audit_dir) if settings.audit_dir else DEFAULT_AUDIT_DIR


def audit_log_path(run_id: str) -> Path:
    """The JSONL audit file to READ for a run: the current persistent location if
    a file actually exists there, else the legacy /tmp/orch-audit path (a run
    recorded before the P5 relocation) — so nothing written under the old default
    goes silently unreadable. When neither exists, returns the current-location
    path (callers already guard with .is_file()/.exists())."""
    current = default_audit_dir() / f"{run_id}.jsonl"
    if current.is_file():
        return current
    legacy = LEGACY_AUDIT_DIR / f"{run_id}.jsonl"
    if legacy.is_file():
        return legacy
    return current


def read_step_audit_entries(run_id: str, step_id: str) -> list[dict]:
    """Every probe_executed/command_executed entry recorded for ONE step, oldest
    first — the durable a-posteriori log of what actually ran (command, exit
    code, stdout/stderr as bounded at capture time, duration). This is the SAME
    data GET /runs/{run_id}/steps/{step_id}/log exposes and orchestrator.
    decision_bundles reads for the decision context — factored here once so both
    stay in sync. Reads whichever location actually has the file (see
    audit_log_path). Never raises: a missing file yields [], a corrupt line is
    skipped."""
    path = audit_log_path(run_id)
    if not path.is_file():
        return []
    entries: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return entries
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except (ValueError, TypeError):
            continue
        event = ev.get("event")
        if event not in ("probe_executed", "command_executed") or ev.get("step_id") != step_id:
            continue
        entries.append({
            "kind": "probe" if event == "probe_executed" else "command",
            "command": ev.get("command"),
            "exit_code": ev.get("exit_code"),
            "passed": ev.get("passed"),
            "stdout": ev.get("stdout", ""),
            "stderr": ev.get("stderr", ""),
            "duration_ms": ev.get("duration_ms"),
            "ts": ev.get("ts"),
        })
    entries.sort(key=lambda e: e.get("ts") or 0)
    return entries


class RunAuditLogger:
    """Structured audit trail for a single run.

    Writes to:
    - Python logger (module "orch.run.<run_id>")
    - Per-run JSONL file under default_audit_dir() (for programmatic analysis
      and the GET /runs/{id}/audit, /runs/{id}/steps/{id}/log endpoints)
    """

    def __init__(self, run_id: str, log_dir: str | Path | None = None):
        self.run_id = run_id
        self.log_dir = Path(log_dir) if log_dir is not None else default_audit_dir()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / f"{run_id}.jsonl"
        self._logger = logging.getLogger(f"orch.run.{run_id}")

    def _write(self, event_type: str, data: dict) -> None:
        entry = {
            "ts": time.time() * 1000,
            "run_id": self.run_id,
            "event": event_type,
            **data,
        }
        # Write to JSONL file
        try:
            with open(self.log_file, "a") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception as e:
            log.warning(f"Audit log write failed: {e}")
        # Write to Python logger
        self._logger.info(f"[{event_type}] {json.dumps(data, default=str)[:500]}")

    # ── Run lifecycle ─────────────────────────────────

    def run_started(self, goal: str, model: str, epics_count: int) -> None:
        self._write("run_started", {"goal": goal, "model": model, "epics_count": epics_count})

    def run_completed(self, duration_ms: float, total_steps: int, failed_steps: int) -> None:
        self._write("run_completed", {
            "duration_ms": duration_ms,
            "total_steps": total_steps,
            "failed_steps": failed_steps,
            "success_rate": (total_steps - failed_steps) / total_steps if total_steps else 0,
        })

    def run_failed(self, reason: str, duration_ms: float) -> None:
        self._write("run_failed", {"reason": reason, "duration_ms": duration_ms})

    def run_aborted(self) -> None:
        self._write("run_aborted", {})

    def run_paused(self, reason: str, step_id: str) -> None:
        self._write("run_paused", {"reason": reason, "step_id": step_id})

    def run_resumed(self) -> None:
        self._write("run_resumed", {})

    # ── Epic lifecycle ────────────────────────────────

    def epic_started(self, epic_id: str, title: str, stories_count: int) -> None:
        self._write("epic_started", {"epic_id": epic_id, "title": title, "stories_count": stories_count})

    def epic_completed(self, epic_id: str, duration_ms: float, review_rounds: int) -> None:
        self._write("epic_completed", {"epic_id": epic_id, "duration_ms": duration_ms, "review_rounds": review_rounds})

    def epic_failed(self, epic_id: str, reason: str) -> None:
        self._write("epic_failed", {"epic_id": epic_id, "reason": reason})

    def epic_review_result(self, epic_id: str, round: int, action: str, diagnosis: str = "") -> None:
        self._write("epic_review", {"epic_id": epic_id, "round": round, "action": action, "diagnosis": diagnosis[:500]})

    def epic_approved(self, epic_id: str, verdicts: list[dict]) -> None:
        """Deterministic epic approval (P5.5b): the LLM reviewer is gone. Every
        story approved AND every step done with a passing verification → approved.
        `verdicts` is the per-step evidence (id, status, checks/errors counts) that
        justified the approval — the audit record of what the deterministic gate saw."""
        self._write("epic_approved", {"epic_id": epic_id, "verdicts": verdicts})

    # ── Story lifecycle ───────────────────────────────

    def story_started(self, epic_id: str, story_id: str, title: str, steps_count: int) -> None:
        self._write("story_started", {"epic_id": epic_id, "story_id": story_id, "title": title, "steps_count": steps_count})

    def story_completed(self, epic_id: str, story_id: str, duration_ms: float) -> None:
        self._write("story_completed", {"epic_id": epic_id, "story_id": story_id, "duration_ms": duration_ms})

    def story_failed(self, epic_id: str, story_id: str, failed_step_id: str) -> None:
        self._write("story_failed", {"epic_id": epic_id, "story_id": story_id, "failed_step_id": failed_step_id})

    # ── Step lifecycle ────────────────────────────────

    def step_started(self, epic_id: str, story_id: str, step_id: str, task_type: str, agent: str, attempt: int) -> None:
        self._write("step_started", {
            "epic_id": epic_id, "story_id": story_id, "step_id": step_id,
            "task_type": task_type, "agent": agent, "attempt": attempt,
        })

    def step_prompt_sent(self, epic_id: str, story_id: str, step_id: str, prompt: str, session_id: str) -> None:
        self._write("step_prompt", {
            "epic_id": epic_id, "story_id": story_id, "step_id": step_id,
            "session_id": session_id,
            "prompt_length": len(prompt),
            "prompt_preview": prompt[:1000],
        })

    def step_completed(self, epic_id: str, story_id: str, step_id: str, duration_ms: float,
                       tokens_in: int, tokens_out: int, cost: float, summary: str) -> None:
        self._write("step_completed", {
            "epic_id": epic_id, "story_id": story_id, "step_id": step_id,
            "duration_ms": duration_ms,
            "tokens_in": tokens_in, "tokens_out": tokens_out, "cost": cost,
            "summary": summary[:500],
        })

    def step_failed(self, epic_id: str, story_id: str, step_id: str, duration_ms: float,
                    error: str, attempt: int, max_attempts: int, will_retry: bool) -> None:
        self._write("step_failed", {
            "epic_id": epic_id, "story_id": story_id, "step_id": step_id,
            "duration_ms": duration_ms,
            "error": error[:1000],
            "attempt": attempt, "max_attempts": max_attempts, "will_retry": will_retry,
        })

    def step_halted(self, epic_id: str, story_id: str, step_id: str, summary: str) -> None:
        self._write("step_halted", {
            "epic_id": epic_id, "story_id": story_id, "step_id": step_id,
            "summary": summary[:500],
        })

    # ── Verification ──────────────────────────────────

    def probe_executed(self, epic_id: str, story_id: str, step_id: str,
                       command: str, exit_code: int, stdout: str, stderr: str, duration_ms: float) -> None:
        self._write("probe_executed", {
            "epic_id": epic_id, "story_id": story_id, "step_id": step_id,
            "command": command[:200],
            "exit_code": exit_code,
            "stdout": stdout[:2000],
            "stderr": stderr[:2000],
            "duration_ms": duration_ms,
            "passed": exit_code == 0,
        })

    def command_executed(self, epic_id: str, story_id: str, step_id: str,
                         command: str, exit_code: int, stdout: str, stderr: str, duration_ms: float) -> None:
        """A `Run: <cmd>` line the ENGINE executed itself (P5 doctrine: a command
        known at plan time needs no LLM to run). Mirrors probe_executed so the
        audit trail treats an engine-run command exactly like a probe — same
        command / exit_code / truncated streams / duration / passed shape — but
        under its own event type so a post-mortem can tell the deterministic
        Run: phase apart from the acceptance PROBEs. stdout truncated ~500c."""
        self._write("command_executed", {
            "epic_id": epic_id, "story_id": story_id, "step_id": step_id,
            "command": command[:200],
            "exit_code": exit_code,
            "stdout": stdout[:500],
            "stderr": stderr[:500],
            "duration_ms": duration_ms,
            "passed": exit_code == 0,
        })

    def verification_result(self, epic_id: str, story_id: str, step_id: str,
                            passed: bool, checks: list[str], errors: list[str]) -> None:
        self._write("verification_result", {
            "epic_id": epic_id, "story_id": story_id, "step_id": step_id,
            "passed": passed,
            "checks_count": len(checks),
            "errors_count": len(errors),
            "errors": errors[:10],
        })

    # ── Human interaction ─────────────────────────────

    def human_question_asked(self, step_id: str, question: str) -> None:
        self._write("human_question", {"step_id": step_id, "question": question[:500]})

    def human_answer_received(self, step_id: str, answer: str) -> None:
        self._write("human_answer", {"step_id": step_id, "answer": answer[:500]})

    # ── Decision points (ASSIST-PLAN §3) ──────────────

    def decision(self, epic_id: str, story_id: str, step_id: str, payload: dict) -> None:
        """A decision-point decision (POST /steps/{id}/decide). Mirrors the
        SQLite 'decision' event into the JSONL audit trail so GET
        /runs/{id}/audit?event_type=decision surfaces it (§3 A3 audit contract)."""
        self._write("decision", {
            "epic_id": epic_id, "story_id": story_id, "step_id": step_id,
            **payload,
        })

    # ── Token/cost summary ────────────────────────────

    def cost_summary(self, step_id: str, tokens_in: int, tokens_out: int, tokens_cache: int, cost: float) -> None:
        self._write("cost_update", {
            "step_id": step_id,
            "tokens_in": tokens_in, "tokens_out": tokens_out, "tokens_cache": tokens_cache,
            "cost": cost,
        })


# Singleton registry
_loggers: dict[str, RunAuditLogger] = {}


def get_audit_logger(run_id: str) -> RunAuditLogger:
    if run_id not in _loggers:
        _loggers[run_id] = RunAuditLogger(run_id)
    return _loggers[run_id]
