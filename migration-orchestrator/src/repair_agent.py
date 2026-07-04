"""In-engine RÉPARATEUR tool loop (P5.5 — replaces the opencode agent session).

Doctrine (ASSIST-PLAN P5.5): the engine executes · the direct API judges · this
in-engine tool loop repairs. Invoked ONLY when:
  • a step's deterministic `Run:` line failed (the LLM becomes a repairer, with the
    failure context threaded into the prompt), or
  • a step has no `Run:` lines at all (the legacy "agent does the work" path).

The model chooses actions via OpenAI function-calling; the ENGINE executes them
through the SAME subprocess + env path as probes and Run: lines (cwd=repo_dir,
probe_env, per-tool timeout). Three tools:
  read_file(path, offset?, limit?)   — read a slice of a file
  bash(command, timeout?)            — run a shell command (capped)
  write_file(path, content)          — write/overwrite a file

Every tool call is audited as `tool_executed` (mirror of command_executed).
Caps: max_tool_calls and a wall-clock budget (both overridable by env). When the
model stops requesting tools it must emit the final JSON envelope (forced via
`response_format: json_object`) in the SAME schema parse_agent_result expects
(status/summary/modified_files/…) — reusing the existing parser downstream.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time

from .audit import get_audit_logger
from .config import settings
from .llm_client import LLMClient, LLMError
from .llm_cost import record as record_llm_usage
from .prompt_builder import build_review_epic_prompt
from .verifier import probe_env

log = logging.getLogger(__name__)


# ── Epic reviewer (direct, tool-free) ────────────────────────────────────────
async def review_epic_direct(run, epic, client: LLMClient, model: str | None = None) -> str | None:
    """Epic review as a SINGLE direct chat() call — no tools, json_object forced.
    Returns the raw JSON text for parse_epic_review_result (unchanged downstream:
    the 'reviewer OVERRULED' protocol lives in the orchestrator). None on failure
    → the orchestrator's resilient auto-approve path handles it. Usage is recorded
    against a synthetic per-epic step-less caller (no step to accumulate into)."""
    prompt = build_review_epic_prompt(epic, run)
    used_model = model or client.model
    try:
        message, usage = await client.chat(
            messages=[{"role": "user", "content": prompt}],
            tools=None,
            response_format={"type": "json_object"},
            timeout=settings.llm_timeout,
        )
    except LLMError as e:
        log.warning(f"Epic {epic.id}: direct review call failed: {e}")
        return None
    # No StepState to accumulate into for a review; log the call to the ledger only.
    record_llm_usage(run, None, usage, caller=f"review:{epic.id}", model=used_model)
    return message.get("content") or None


# ── Tool schemas (OpenAI function-calling) ───────────────────────────────────
TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file (or a slice of it) from the repository, relative to the repo root.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to the repo root (or absolute)."},
                    "offset": {"type": "integer", "description": "0-based line offset to start reading from (optional)."},
                    "limit": {"type": "integer", "description": "Max number of lines to read (optional)."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a shell command from the repo root. Use it to run the migration tools, tests, probes, git, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The shell command to run."},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (optional; capped by the engine)."},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file with the given content, relative to the repo root.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to the repo root (or absolute)."},
                    "content": {"type": "string", "description": "The full file content to write."},
                },
                "required": ["path", "content"],
            },
        },
    },
]

_MAX_TOOL_RESULT = 8000  # chars fed back to the model per tool result (keeps context bounded)


def _resolve_path(repo_dir: str, path: str) -> str:
    return path if os.path.isabs(path) else os.path.join(repo_dir, path)


async def _tool_read_file(repo_dir: str, args: dict) -> tuple[bool, str]:
    path = args.get("path") or ""
    if not path:
        return False, "read_file: 'path' is required"
    full = _resolve_path(repo_dir, path)
    try:
        with open(full, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError as e:
        return False, f"read_file: {e}"
    offset = args.get("offset")
    limit = args.get("limit")
    start = int(offset) if isinstance(offset, (int, float)) else 0
    start = max(0, start)
    end = start + int(limit) if isinstance(limit, (int, float)) else len(lines)
    chunk = "".join(lines[start:end])
    return True, chunk[:_MAX_TOOL_RESULT]


async def _tool_write_file(repo_dir: str, args: dict) -> tuple[bool, str]:
    path = args.get("path") or ""
    if not path:
        return False, "write_file: 'path' is required"
    content = args.get("content")
    if content is None:
        return False, "write_file: 'content' is required"
    full = _resolve_path(repo_dir, path)
    try:
        os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError as e:
        return False, f"write_file: {e}"
    return True, f"wrote {len(content)} bytes to {path}"


async def _tool_bash(repo_dir: str, args: dict) -> tuple[bool, str]:
    cmd = args.get("command") or ""
    if not cmd:
        return False, "bash: 'command' is required"
    requested = args.get("timeout")
    timeout_s = settings.repair_bash_timeout_s
    if isinstance(requested, (int, float)) and requested > 0:
        timeout_s = float(requested)
    timeout_s = min(timeout_s, settings.repair_bash_timeout_cap_s)
    env = probe_env(repo_dir)
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd, cwd=repo_dir, env=env,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return False, f"bash: command timed out after {int(timeout_s)}s"
    except Exception as e:  # noqa: BLE001
        return False, f"bash: {e}"
    out = stdout.decode("utf-8", errors="replace")
    err = stderr.decode("utf-8", errors="replace")
    ok = proc.returncode == 0
    body = f"exit_code={proc.returncode}\n--- stdout ---\n{out}\n--- stderr ---\n{err}"
    return ok, body[:_MAX_TOOL_RESULT]


async def _dispatch_tool(name: str, args: dict, repo_dir: str) -> tuple[bool, str]:
    if name == "read_file":
        return await _tool_read_file(repo_dir, args)
    if name == "bash":
        return await _tool_bash(repo_dir, args)
    if name == "write_file":
        return await _tool_write_file(repo_dir, args)
    return False, f"unknown tool '{name}'"


_FINAL_ENVELOPE_INSTRUCTION = (
    "\n\nQuand tu as terminé (ou si tu ne peux pas continuer), n'appelle plus "
    "d'outil et réponds EXCLUSIVEMENT avec un objet JSON de cette forme "
    "(sans markdown):\n"
    '{"step_id":"<id>","agent":"code","status":"completed | failed | halt",'
    '"summary":"résumé du travail fait","modified_files":["..."],'
    '"commands_requested":["..."],"risks":["..."],"loop_to":null}\n'
    "Utilise \"halt\" seulement pour un problème grave nécessitant une "
    "intervention humaine. Le harnais déterministe (probes) reste le juge final."
)


async def run_repair_agent(
    *,
    run,
    epic,
    story,
    step,
    prompt: str,
    client: LLMClient,
    model: str | None = None,
) -> str | None:
    """Drive the in-engine tool loop for a step and return the final assistant
    TEXT (the JSON envelope), or None if the loop produced nothing parseable.
    The caller feeds the return value to parse_agent_result exactly as before.

    Caps: settings.repair_max_tool_calls tool calls and settings.repair_wall_budget_s
    wall-clock. Hitting either cap ends the loop with a forced final turn (no tools)
    so the model still emits an envelope. Every tool call is audited.
    """
    audit = get_audit_logger(run.run_id)
    used_model = model or client.model

    system = (
        "Tu es un agent RÉPARATEUR in-engine. Tu disposes de trois outils "
        "(read_file, bash, write_file) exécutés par le moteur dans le dépôt "
        "(cwd = racine du repo, mêmes variables d'environnement que les probes). "
        "Utilise-les pour lire le code, corriger la cause, écrire des fichiers et "
        "relancer les commandes. Ne te contente jamais de relire une commande "
        "échouée : corrige-la puis relance-la."
    )
    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt + _FINAL_ENVELOPE_INSTRUCTION},
    ]

    start = time.time()
    tool_calls_made = 0
    max_calls = settings.repair_max_tool_calls
    wall_budget = settings.repair_wall_budget_s

    while True:
        over_budget = (time.time() - start) >= wall_budget
        at_call_cap = tool_calls_made >= max_calls
        force_final = over_budget or at_call_cap

        if force_final:
            # Cap reached: one last turn WITHOUT tools so the model must emit the
            # final JSON envelope instead of requesting more work.
            messages.append({
                "role": "user",
                "content": (
                    "Budget de réparation atteint (tool calls / temps). N'appelle plus "
                    "d'outil. Réponds MAINTENANT avec l'objet JSON final."
                ),
            })

        try:
            message, usage = await client.chat(
                messages=messages,
                tools=None if force_final else TOOLS,
                response_format={"type": "json_object"} if force_final else None,
                timeout=settings.llm_timeout,
            )
        except LLMError as e:
            log.error(f"Step {step.id}: repair LLM call failed: {e}")
            return None

        record_llm_usage(run, step, usage, caller=f"repair:{step.id}", model=used_model)

        tool_calls = message.get("tool_calls") or []
        content = message.get("content") or ""

        if force_final or not tool_calls:
            # Terminal turn: return the text envelope (may be empty → caller falls
            # back to a synthetic result).
            if content:
                return content
            # No text and no tools: nudge once more for the envelope unless we were
            # already forcing (avoid an infinite loop).
            if force_final:
                return None
            messages.append(message)
            messages.append({
                "role": "user",
                "content": "Tu n'as ni appelé d'outil ni répondu. Réponds avec l'objet JSON final.",
            })
            continue

        # Append the assistant turn (with its tool_calls) then execute each tool
        # and append a tool result message keyed by tool_call_id.
        messages.append(message)
        for tc in tool_calls:
            tool_calls_made += 1
            fn = (tc.get("function") or {})
            name = fn.get("name") or ""
            raw_args = fn.get("arguments") or "{}"
            t0 = time.time() * 1000
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            except (json.JSONDecodeError, TypeError):
                args = {}
                ok, result = False, f"{name}: could not parse arguments JSON: {str(raw_args)[:200]}"
            else:
                ok, result = await _dispatch_tool(name, args, run.repo_dir)
            duration = (time.time() * 1000) - t0
            try:
                audit.tool_executed(
                    epic_id=getattr(epic, "id", ""), story_id=getattr(story, "id", ""),
                    step_id=step.id, tool=name,
                    tool_input=json.dumps(args, ensure_ascii=False) if isinstance(args, dict) else str(args),
                    ok=ok, result=result, duration_ms=max(0.0, duration),
                )
            except Exception:  # noqa: BLE001
                pass
            # A tool FAILURE is not fatal — feed the error back and let the model
            # continue (fix path). The loop only ends at a terminal turn / cap.
            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id") or "",
                "content": result[:_MAX_TOOL_RESULT],
            })
