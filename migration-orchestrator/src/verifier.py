from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time

from .audit import get_audit_logger
from .config import settings
from .models import AgentResult, StepState, VerificationResult

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

# `Run: <cmd>` lines are the deterministic, plan-time-KNOWN commands of a step
# (crawl-site, load_content, create_pages, scaffold…). Same shape as PROBE_RE so
# an optional `Run[NNN]:` per-line timeout override is accepted symmetrically.
RUN_RE = re.compile(r"\s*Run(?:\[(\d+)\])?:\s*(.+)", re.DOTALL)


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


# ── engine-level integrity belt (plan-independent completeness) ──────────────
# Content-phase steps for which the belt runs as an ADDITIONAL verification once
# the step's own probes pass. Matched by task_type OR by these step ids (the v2
# gen_plan emits step_pages as task_type=build, so the id set is load-bearing).
CONTENT_TASK_TYPES = {"content"}
CONTENT_STEP_IDS = {"step_pages", "step_content_load", "step_publish_parity"}
INTEGRITY_PROBE = "orchestration/probes/integrity.py"


def is_content_phase(step: StepState) -> bool:
    return step.task_type in CONTENT_TASK_TYPES or step.id in CONTENT_STEP_IDS


def derive_site(step: StepState, project: str | None = None) -> str | None:
    """Site key for the integrity belt: from step inputs if present (gen_plan
    now emits inputs.site), else the project basename as a graceful fallback.
    The LIVE plan predates the inputs.site addition, so the fallback keeps the
    belt working on in-flight runs. `project` (the modeled run.project, P1)
    fills the gap when the step's own inputs carry neither. Returns None only
    when no project is known (belt is then skipped with an audit note, never
    crashes)."""
    inputs = step.inputs or {}
    site = inputs.get("site")
    if site:
        return str(site)
    proj = inputs.get("project") or project
    if proj:
        return os.path.basename(str(proj).rstrip("/"))
    return None


def integrity_command(step: StepState, project: str | None = None) -> str | None:
    """The read-only integrity probe command for a content step, or None when it
    is not derivable (no project/site → skip gracefully). Phase == step id so the
    probe scales its expectations to pipeline position. Step inputs stay
    authoritative (they carry the exact arg shape the plan chose); the modeled
    run.project (bare name) is the fallback for steps that carry none — it is
    re-anchored under projects/ because integrity.py joins its project_path arg
    under the repo root (a bare name would resolve to a nonexistent dir)."""
    inputs = step.inputs or {}
    proj = inputs.get("project") or (f"projects/{project}" if project else None)
    if not proj:
        return None
    site = derive_site(step, project)
    if not site:
        return None
    return f"python3 {INTEGRITY_PROBE} {proj} {site} --phase {step.id}"


async def run_integrity_belt(step: StepState, repo_dir: str,
                             run_id: str | None,
                             project: str | None = None,
                             extra_env: dict[str, str] | None = None) -> tuple[list[str], list[str]]:
    """Run the integrity belt as an additional verification for a content step.
    Returns (checks, errors) merged into the VerificationResult. A non-zero exit
    is a verification FAILURE (same retry/decision path as any probe). Audited
    like a probe with an "[integrity]" kind marker in the command string. Honours
    the ORCHESTRATOR_INTEGRITY kill-switch and its own timeout. Never raises —
    an unexpected fault degrades to a skip note, not a crash."""
    checks: list[str] = []
    errors: list[str] = []
    if not settings.integrity:
        checks.append("integrity_disabled")
        return checks, errors
    if not is_content_phase(step):
        return checks, errors
    cmd = integrity_command(step, project)
    if not cmd:
        # graceful: no site derivable → skip with an audit note, never crash
        checks.append("integrity_skipped:no_site")
        if run_id:
            from .audit import get_audit_logger
            get_audit_logger(run_id).probe_executed(
                epic_id="", story_id="", step_id=step.id,
                command=f"[integrity] {step.id}: skipped (no project/site derivable)",
                exit_code=0, stdout="", stderr="", duration_ms=0.0)
        return checks, errors

    env = probe_env(repo_dir)
    if extra_env:
        env.update(extra_env)
    cmd_start = time.time() * 1000
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd, cwd=repo_dir, env=env,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=settings.integrity_timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            errors.append(f"Integrity belt timed out after {int(settings.integrity_timeout)}s")
            return checks, errors
        duration = time.time() * 1000 - cmd_start
        out = stdout.decode("utf-8", errors="replace")[:2000]
        err = stderr.decode("utf-8", errors="replace")[:2000]
        if run_id:
            from .audit import get_audit_logger
            # "[integrity]" marker in the command string so the audit trail
            # distinguishes the belt from a plan step's own probes.
            get_audit_logger(run_id).probe_executed(
                epic_id="", story_id="", step_id=step.id,
                command=f"[integrity] {cmd}", exit_code=proc.returncode,
                stdout=out, stderr=err, duration_ms=duration)
        if proc.returncode == 0:
            checks.append("integrity_passed")
        else:
            errors.append(f"Integrity belt failed for {step.id} (exit {proc.returncode})\n{out[:1200]}")
    except Exception as e:  # never crash the verifier on an infra fault
        duration = time.time() * 1000 - cmd_start
        errors.append(f"Integrity belt error: {e}")
        if run_id:
            from .audit import get_audit_logger
            get_audit_logger(run_id).probe_executed(
                epic_id="", story_id="", step_id=step.id,
                command=f"[integrity] {cmd}", exit_code=-1,
                stdout="", stderr=str(e)[:2000], duration_ms=duration)
    return checks, errors


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


# ── engine-executes-Run: doctrine (P5) ──────────────────────────────────────
# A step whose acceptance_criteria carry `Run: <cmd>` lines has, at plan time, a
# KNOWN deterministic command. The engine runs those lines ITSELF (same
# subprocess mechanism as probe_commands) BEFORE opening any agent session — an
# LLM does not need to read source files to type a command the planner already
# wrote. Root cause it closes: step_content_load burned 2×600s of DeepSeek
# reading AGENTS.md / load_content.py source / the probes without ever running
# "python3 orchestration/lib/load_content.py …". Doctrine: the engine drives,
# the LLM assists at decision points — a known command is not a decision point.
CONTENT_TASK_TYPES_EXEC = {"content"}


def run_lines(criteria: list[str] | None) -> list[tuple[str, float | None]]:
    """Every `Run: <cmd>` line in a step's acceptance_criteria, in order, as
    (command, timeout_override_or_None). `Run[NNN]:` sets a per-line override;
    plain `Run:` gets None (resolved to the task_type default by the caller).
    Whitespace-collapsed exactly like probe_commands so a multi-line criterion
    normalises to a single shell command string."""
    out: list[tuple[str, float | None]] = []
    for crit in criteria or []:
        m = RUN_RE.match(crit)
        if m:
            timeout_s = float(m.group(1)) if m.group(1) else None
            out.append((" ".join(m.group(2).split()), timeout_s))
    return out


def is_content_task(step: StepState) -> bool:
    """A step gets the long Run: budget when it is a content step — by task_type
    OR by the known content step ids (gen_plan emits step_pages as task_type
    build, so the id set is load-bearing, mirroring is_content_phase for the
    integrity belt)."""
    return step.task_type in CONTENT_TASK_TYPES_EXEC or step.id in CONTENT_STEP_IDS


def run_step_timeout(step: StepState) -> float:
    """Default per-Run-line timeout for a step: content steps get the long budget
    (MCP media uploads, page trees), everything else the default. Both overridable
    by env (ORCHESTRATOR_ENGINE_EXEC_RUN_CONTENT_TIMEOUT / _DEFAULT_TIMEOUT)."""
    if is_content_task(step):
        return settings.engine_exec_run_content_timeout
    return settings.engine_exec_run_default_timeout


async def run_step_commands(step: StepState, repo_dir: str,
                            run_id: str | None = None,
                            extra_env: dict[str, str] | None = None) -> tuple[bool, list[dict], str]:
    """Execute the step's `Run: <cmd>` lines sequentially — same subprocess
    mechanism as the probes (same cwd=repo_dir, same probe_env, per-line timeout).
    `extra_env` (optional) is merged over the child env — the orchestrator passes
    ORCH_RUN_ID/ORCH_STEP_ID so child tools can stamp provenance (P0).
    Honours the ORCHESTRATOR_ENGINE_EXEC_RUN kill-switch (same pattern as the
    integrity belt): when disabled OR the step has no Run: lines, returns
    (True, [], "") so the caller falls straight through to the legacy agent path.

    Each execution is audited as `command_executed` (mirror of probe_executed).
    Stops at the FIRST failure (exit != 0 or timeout) — a later Run: line usually
    depends on an earlier one, so re-running the step from a clean point (retry /
    repatch after the decision) is safer than pushing past a broken prerequisite.

    Returns (all_passed, records, failure_context):
      - all_passed: True iff every Run: line exited 0 (or there were none / disabled);
      - records: one dict per executed line (command, exit_code, duration_ms, passed,
        truncated stdout/stderr) for the synthetic engine agent_result summary;
      - failure_context: "" on success, else a human-readable block naming the failed
        command, its exit code, and the tail of its stderr/stdout (~800c). P5.5b: it
        is stashed on step.failure_context and surfaces in the decision bundle
        (GET /runs/{id}/decisions) for the operator/assistant — no repair agent
        reads it anymore.
    """
    if not settings.engine_exec_run:
        return True, [], ""
    lines = run_lines(step.acceptance_criteria)
    if not lines:
        return True, [], ""

    default_timeout = run_step_timeout(step)
    env = probe_env(repo_dir)
    if extra_env:
        # P0: run/step identity for child tools (ORCH_RUN_ID / ORCH_STEP_ID) —
        # merged LAST so the executor-provided identity always wins.
        env.update(extra_env)
    records: list[dict] = []
    audit = get_audit_logger(run_id) if run_id else None

    for cmd, override in lines:
        timeout_s = override if override is not None else default_timeout
        cmd_start = time.time() * 1000
        exit_code: int
        out = ""
        err = ""
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd, cwd=repo_dir, env=env,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
                exit_code = proc.returncode
                out = stdout.decode("utf-8", errors="replace")
                err = stderr.decode("utf-8", errors="replace")
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                exit_code = -1
                err = f"Run: line timed out after {int(timeout_s)}s"
        except Exception as e:  # never crash the engine on an infra fault
            exit_code = -1
            err = f"Run: line error: {e}"
        duration = time.time() * 1000 - cmd_start

        if audit:
            audit.command_executed(
                epic_id="", story_id="", step_id=step.id,
                command=cmd, exit_code=exit_code,
                stdout=out, stderr=err, duration_ms=duration)

        rec = {
            "command": cmd, "exit_code": exit_code, "duration_ms": duration,
            "passed": exit_code == 0, "stdout": out[:500], "stderr": err[:500],
        }
        records.append(rec)

        if exit_code != 0:
            # First failure: build the failure context and stop (later lines may
            # depend on this one). ~800c of the tail of each stream — the tail
            # carries the traceback / assertion, not the boilerplate header.
            # P5.5b: this block is FOR THE DECISION BUNDLE (operator/assistant),
            # not a repair-agent prompt — the step fails, retries re-run it, and
            # once exhausted it parks as decision_pending carrying this context.
            failure_context = (
                "EXÉCUTION DÉTERMINISTE ÉCHOUÉE — le moteur a lancé cette ligne "
                "Run: lui-même et elle a échoué. Contexte pour la décision "
                "(retry / repatch / rollback) une fois les retries épuisés.\n"
                f"Commande: {cmd}\n"
                f"Exit code: {exit_code}\n"
                f"stderr (queue):\n{err[-800:]}\n"
                f"stdout (queue):\n{out[-800:]}\n"
            )
            return False, records, failure_context

    return True, records, ""


async def verify_result(step: StepState, result: AgentResult, repo_dir: str, run_id: str | None = None,
                        extra_env: dict[str, str] | None = None,
                        project: str | None = None) -> VerificationResult:
    """`extra_env` (optional) is merged over the probe subprocess env — the
    orchestrator passes ORCH_RUN_ID/ORCH_STEP_ID so probes/tools can stamp
    provenance (P0). `project` (optional, the modeled run.project) threads into
    the integrity belt's site derivation (P1)."""
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
    if extra_env:
        env.update(extra_env)
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

    # ENGINE-LEVEL INTEGRITY BELT: once a content step's own probes pass, diff the
    # live Jahia against the pipeline artifacts as an ADDITIONAL verification (a
    # weak step probe can pass while the site is hollow — observed live: 0/19
    # sub-pages with a green content.get). A belt failure fails the verification,
    # taking the same retry/decision path as any probe. Runs only when the step's
    # own gate is otherwise green (no point diffing a step that already failed).
    if not errors:
        belt_checks, belt_errors = await run_integrity_belt(step, repo_dir, run_id,
                                                            project=project, extra_env=extra_env)
        checks.extend(belt_checks)
        errors.extend(belt_errors)

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
