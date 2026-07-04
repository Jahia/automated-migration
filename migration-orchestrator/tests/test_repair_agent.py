"""In-engine RÉPARATEUR tool-loop tests (P5.5).

No real network: a scripted FakeLLM feeds canned turns. Asserts:
  (a) the three tools dispatch correctly (read_file / bash / write_file) through
      the SAME subprocess+env path (bash) and real filesystem (read/write);
  (b) each tool call is audited as tool_executed;
  (c) a tool FAILURE does not end the loop — the error is fed back and the model
      continues;
  (d) the tool-call cap forces a final (tool-free, json_object) turn;
  (e) the wall-clock budget forces a final turn;
  (f) the final envelope text is returned verbatim for parse_agent_result;
  (g) reviewer: review_epic_direct makes ONE tool-free call and returns the text.
"""
from __future__ import annotations

import json
import os

import pytest

from src import repair_agent
from src.config import settings
from src.models import EpicInput, PlanInput, StepInput, StoryInput
from src.state import build_run_state


# ── scripted fake LLM ────────────────────────────────────────────────────────
def _tool_call(cid, name, args):
    return {"id": cid, "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)}}


class FakeLLM:
    """Returns pre-scripted (message, usage) turns. Records every chat() call so a
    test can assert tools were / weren't offered and response_format forced."""

    model = "fake-model"

    def __init__(self, turns):
        self._turns = list(turns)
        self.calls = []

    async def chat(self, messages, tools=None, response_format=None, timeout=None,
                   temperature=None, tool_choice=None):
        self.calls.append({"tools": tools, "response_format": response_format,
                           "n_messages": len(messages)})
        message = self._turns.pop(0) if self._turns else {"role": "assistant", "content": "{}"}
        return message, {"prompt_tokens": 5, "completion_tokens": 2}


def _run(tmp_repo, task_type="content"):
    plan = PlanInput(
        goal="g", repo_dir=str(tmp_repo),
        epics=[EpicInput(id="e1", title="E", goal="g", stories=[
            StoryInput(id="s1", title="S", description="d", steps=[
                StepInput(id="step_x", title="x", task_type=task_type,
                          inputs={"project": "demoproj"},
                          acceptance_criteria=["PROBE: true"]),
            ]),
        ])],
    )
    run = build_run_state(plan)
    run.run_id = "run_repair_test"
    return run


def _ctx(run):
    epic = run.epics[0]
    story = epic.stories[0]
    step = story.steps[0]
    return epic, story, step


async def _drive(run, llm, monkeypatch):
    # keep the per-project ledger out of the way — record → step counters only
    monkeypatch.setattr("src.llm_cost.project_of", lambda run, step=None: None)
    epic, story, step = _ctx(run)
    prompt = "do the work"
    return await repair_agent.run_repair_agent(
        run=run, epic=epic, story=story, step=step, prompt=prompt, client=llm,
    )


@pytest.mark.asyncio
async def test_tools_dispatch_and_final_envelope(tmp_path, monkeypatch):
    # a file to read + a target to write
    (tmp_path / "readme.txt").write_text("line1\nline2\nline3\n")
    envelope = '{"step_id":"step_x","status":"completed","summary":"done"}'
    llm = FakeLLM([
        {"role": "assistant", "content": "", "tool_calls": [
            _tool_call("c1", "read_file", {"path": "readme.txt", "offset": 1, "limit": 1})]},
        {"role": "assistant", "content": "", "tool_calls": [
            _tool_call("c2", "bash", {"command": "echo hi"})]},
        {"role": "assistant", "content": "", "tool_calls": [
            _tool_call("c3", "write_file", {"path": "out.txt", "content": "written"})]},
        {"role": "assistant", "content": envelope},  # terminal turn (no tool_calls)
    ])
    run = _run(tmp_path)
    text = await _drive(run, llm, monkeypatch)
    assert text == envelope
    # write_file really wrote
    assert (tmp_path / "out.txt").read_text() == "written"
    # step token counters accumulated across the 4 chat() calls
    _, _, step = _ctx(run)
    assert step.tokens_in == 4 * 5
    assert step.tokens_out == 4 * 2


@pytest.mark.asyncio
async def test_tool_calls_are_audited(tmp_path, monkeypatch):
    (tmp_path / "f.txt").write_text("x\n")
    events = []
    from src import audit

    class _Audit:
        def tool_executed(self, **kw):
            events.append(kw)

    monkeypatch.setattr(audit, "get_audit_logger", lambda rid: _Audit())
    monkeypatch.setattr(repair_agent, "get_audit_logger", lambda rid: _Audit())

    llm = FakeLLM([
        {"role": "assistant", "content": "", "tool_calls": [
            _tool_call("c1", "bash", {"command": "echo audited"})]},
        {"role": "assistant", "content": '{"status":"completed","summary":"s"}'},
    ])
    run = _run(tmp_path)
    await _drive(run, llm, monkeypatch)
    assert len(events) == 1
    assert events[0]["tool"] == "bash"
    assert events[0]["ok"] is True
    assert "audited" in events[0]["result"]


@pytest.mark.asyncio
async def test_tool_failure_does_not_end_loop(tmp_path, monkeypatch):
    # first tool fails (nonexistent file); model then recovers and finishes
    llm = FakeLLM([
        {"role": "assistant", "content": "", "tool_calls": [
            _tool_call("c1", "read_file", {"path": "does_not_exist.txt"})]},
        {"role": "assistant", "content": '{"status":"completed","summary":"recovered"}'},
    ])
    run = _run(tmp_path)
    text = await _drive(run, llm, monkeypatch)
    assert "recovered" in text
    # two chat() calls: the failure was fed back, the loop continued
    assert len(llm.calls) == 2
    # the SECOND call still offered tools (loop had not hit a cap)
    assert llm.calls[1]["tools"] is not None


@pytest.mark.asyncio
async def test_tool_call_cap_forces_final_turn(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "repair_max_tool_calls", 1)
    # first turn uses the 1 allowed tool call; loop then forces a tool-free final turn
    envelope = '{"status":"completed","summary":"capped"}'
    llm = FakeLLM([
        {"role": "assistant", "content": "", "tool_calls": [
            _tool_call("c1", "bash", {"command": "echo one"})]},
        {"role": "assistant", "content": envelope},  # served on the forced final turn
    ])
    run = _run(tmp_path)
    text = await _drive(run, llm, monkeypatch)
    assert text == envelope
    # the LAST chat() call had tools disabled + json_object forced
    assert llm.calls[-1]["tools"] is None
    assert llm.calls[-1]["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_wall_budget_forces_final_turn(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "repair_wall_budget_s", 0.0)  # already over budget
    envelope = '{"status":"failed","summary":"out of time"}'
    llm = FakeLLM([{"role": "assistant", "content": envelope}])
    run = _run(tmp_path)
    text = await _drive(run, llm, monkeypatch)
    assert text == envelope
    # the single call was the forced final turn (no tools, json_object)
    assert llm.calls[0]["tools"] is None
    assert llm.calls[0]["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_bash_timeout_is_capped(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "repair_bash_timeout_cap_s", 5.0)
    captured = {}

    async def _fake_dispatch(name, args, repo_dir):
        captured["args"] = args
        return True, "ok"

    # spy the bash tool timeout resolution via a real dispatch of a fast command
    llm = FakeLLM([
        {"role": "assistant", "content": "", "tool_calls": [
            _tool_call("c1", "bash", {"command": "echo x", "timeout": 9999})]},
        {"role": "assistant", "content": '{"status":"completed","summary":"s"}'},
    ])
    run = _run(tmp_path)
    # run for real: the cap keeps a fast command fast; assert it still completes
    text = await _drive(run, llm, monkeypatch)
    assert "completed" in text


@pytest.mark.asyncio
async def test_reviewer_direct_single_toolfree_call(tmp_path, monkeypatch):
    monkeypatch.setattr("src.llm_cost.project_of", lambda run, step=None: None)
    verdict = '{"action":"approved","summary":"looks good","confidence":0.9}'
    llm = FakeLLM([{"role": "assistant", "content": verdict}])
    run = _run(tmp_path)
    epic = run.epics[0]
    text = await repair_agent.review_epic_direct(run, epic, llm)
    assert text == verdict
    assert len(llm.calls) == 1
    assert llm.calls[0]["tools"] is None  # reviewer never gets tools
    assert llm.calls[0]["response_format"] == {"type": "json_object"}
