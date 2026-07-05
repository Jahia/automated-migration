from __future__ import annotations

from .models import EpicState, GitHubIssue, RunState, StepState, StoryState

AGENT_DESCRIPTIONS = {
    "code": "Agent de code général. Lit, écrit, modifie, refactor, exécute des commandes.",
    "plan": "Agent de planification. Décompose un objectif en epics et stories structurés.",
}


def build_step_prompt(
    step: StepState,
    story: StoryState,
    epic: EpicState,
    run: RunState,
    run_failure: str | None = None,
) -> str:
    task_type = step.task_type
    agent = step.agent
    desc = AGENT_DESCRIPTIONS.get(agent, f"Agent spécialisé ({task_type}).")
    github_block = _format_github_issues(story.github_issues_content)
    previous = _format_previous_stories(epic, story)
    loop_block = _format_loop_context(step)
    answer_block = _format_human_answer(step)
    # P5 engine-executes-Run: when the engine already ran this step's Run: lines
    # and one FAILED, the agent is opened as a REPAIRER — the failure context
    # (command, exit code, stderr/stdout tail) is prepended so the LLM fixes the
    # cause instead of re-discovering the command from scratch.
    repair_block = _format_run_failure(run_failure)

    inputs_block = ""
    if step.inputs:
        inputs_block = "\nINPUTS:\n" + "\n".join(f"  {k}: {v}" for k, v in step.inputs.items() if not k.startswith("_"))

    criteria_block = ""
    if step.acceptance_criteria:
        criteria_block = "\nCRITÈRES D'ACCEPTATION DE L'ÉTAPE:\n" + "\n".join(f"  - {c}" for c in step.acceptance_criteria)

    expected_block = ""
    if step.expected_outputs:
        expected_block = "\nSORTIES ATTENDUES:\n" + "\n".join(f"  {k}: {v}" for k, v in step.expected_outputs.items())

    return f"""Tu es l'agent "{agent}". Description: {desc}
Repo: {run.repo_dir}

AVANT TOUTE CHOSE, lis le fichier AGENTS.md à la racine du projet.
Ce fichier contient les conventions, le contexte et les règles du projet.
Respecte ses instructions tout au long de ton travail.

Tu es dans la tâche "{task_type}" de la story "{story.title}".
{repair_block}{loop_block}{answer_block}
STORY:
- Titre: {story.title}
- Description: {story.description}
- Critères d'acceptation:
{_format_criteria(story.acceptance_criteria)}

{github_block}

{previous}

EPIC:
- Objectif: {epic.goal}
- Critères d'acceptation de l'epic:
{_format_criteria(epic.review_config.review_criteria)}

ÉTAPE:
- Titre: {step.title}
- Type: {task_type}
{inputs_block}
{criteria_block}
{expected_block}

Retourne EXCLUSIVEMENT ce JSON (sans markdown):
{{
  "step_id": "{step.id}",
  "agent": "{agent}",
  "status": "completed | failed | halt",
  "summary": "résumé du travail fait",
  "modified_files": ["fichiers créés ou modifiés"],
  "commands_requested": ["commandes à exécuter par le harnais"],
  "risks": ["risques identifiés"],
  "loop_to": "step_id vers lequel boucler si problème, ou null"
}}

Utilise "halt" si tu détectes un problème grave nécessitant une intervention humaine (données corrompues, conflit critique, ambiguïté irrésolue, risque de perte de données). Le plan sera mis en pause jusqu'à intervention humaine.
"""


def _format_criteria(criteria: list[str]) -> str:
    if not criteria:
        return "  (aucun)"
    return "\n".join(f"  - {c}" for c in criteria)


def _format_github_issues(issues: list[GitHubIssue]) -> str:
    if not issues:
        return ""
    blocks = []
    for issue in issues:
        block = f"""---
Issue #{issue.number}: {issue.title}
État: {issue.state}
Labels: {', '.join(issue.labels) if issue.labels else 'aucun'}
Lien: {issue.url}

{issue.body}"""
        if issue.comments:
            block += "\n\nCommentaires:"
            for c in issue.comments:
                block += f"\n  [{c.author}]: {c.body}"
        block += "\n---"
        blocks.append(block)
    return "CONTEXTE — ISSUES GITHUB:\n" + "\n\n".join(blocks)


def _format_previous_stories(epic: EpicState, current: StoryState) -> str:
    done_stories = [s for s in epic.stories if s.status.value == "approved" and s.id != current.id]
    if not done_stories:
        return ""
    lines = ["RÉSULTATS DES STORIES PRÉCÉDENTES:"]
    for s in done_stories:
        lines.append(f"\n### {s.id} — {s.title}")
        for step in s.steps:
            if step.agent_result:
                lines.append(f"  [{step.task_type}] {step.agent_result.summary[:200]}")
                if step.agent_result.modified_files:
                    lines.append(f"    Fichiers: {', '.join(step.agent_result.modified_files[:10])}")
    return "\n".join(lines)


def _format_human_answer(step: StepState) -> str:
    """G-D fix: a step re-executed after POST /steps/{id}/answer must SEE the
    answer — without this block the step just re-executes blind."""
    if not step.human_answer:
        return ""
    text = "\nRÉPONSE HUMAINE — Cette étape avait posé une question; un humain a répondu.\n"
    if step.question:
        text += f"Ta question précédente: {step.question.question}\n"
    text += f"Réponse humaine à ta question précédente: {step.human_answer}\n"
    text += "Prends cette réponse en compte et NE repose PAS la même question.\n"
    return text


def _format_run_failure(run_failure: str | None) -> str:
    """P5 repair block: the engine ran this step's deterministic Run: line(s)
    itself and one failed. The block is placed high in the prompt so the LLM
    treats itself as a repairer of a known-failing command, not as the executant
    of a fresh instruction."""
    if not run_failure:
        return ""
    return "\n" + run_failure.strip() + "\n"


def _format_loop_context(step: StepState) -> str:
    reason = step.inputs.get("_loop_reason") or step.inputs.get("_rectification_reason")
    diagnosis = step.inputs.get("_loop_diagnosis") or step.inputs.get("_rectification_diagnosis")
    if not reason:
        return ""
    text = f"\nBOUCLE — Cette étape a été relancée.\nRaison: {reason}\n"
    if diagnosis:
        text += f"Diagnostic complet:\n{diagnosis}\n"
    return text
