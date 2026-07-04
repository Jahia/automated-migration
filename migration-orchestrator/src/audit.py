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

log = logging.getLogger(__name__)


class RunAuditLogger:
    """Structured audit trail for a single run.

    Writes to:
    - Python logger (for /tmp/orch.log filtering)
    - Per-run JSONL file (for programmatic analysis)
    """

    def __init__(self, run_id: str, log_dir: str | Path = "/tmp/orch-audit"):
        self.run_id = run_id
        self.log_dir = Path(log_dir)
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

    def tool_executed(self, epic_id: str, story_id: str, step_id: str,
                      tool: str, tool_input: str, ok: bool, result: str, duration_ms: float) -> None:
        """A tool call the RÉPARATEUR loop executed in-engine (P5.5: read_file /
        bash / write_file via the SAME subprocess+env path as probes and Run:).
        Mirrors command_executed so a post-mortem sees every repair action —
        tool name, truncated input (~500c), success flag, truncated result
        (~500c), duration. `ok` is the tool-level success (bash exit 0, file
        read/written), NOT the LLM's verdict."""
        self._write("tool_executed", {
            "epic_id": epic_id, "story_id": story_id, "step_id": step_id,
            "tool": tool,
            "input": (tool_input or "")[:500],
            "result": (result or "")[:500],
            "duration_ms": duration_ms,
            "passed": ok,
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
