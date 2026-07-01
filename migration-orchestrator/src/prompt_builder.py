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
) -> str:
    task_type = step.task_type
    agent = step.agent
    desc = AGENT_DESCRIPTIONS.get(agent, f"Agent spécialisé ({task_type}).")
    github_block = _format_github_issues(story.github_issues_content)
    previous = _format_previous_stories(epic, story)
    loop_block = _format_loop_context(step)
    retry_block = _format_retry_feedback(step)

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
{loop_block}{retry_block}
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


def build_review_epic_prompt(epic: EpicState, run: RunState) -> str:
    stories_block = _format_all_stories(epic)
    history_block = _format_review_history(epic)

    return f"""Tu es un agent de revue d'architecture.
Tu évalues le travail réalisé dans un epic.

OBJECTIF DE L'EPIC:
{epic.goal}

CRITÈRES D'ACCEPTATION:
{_format_criteria(epic.review_config.review_criteria)}

{stories_block}

{history_block}

Retourne EXCLUSIVEMENT un JSON (sans markdown):
{{
  "action": "approved | rectify",
  // si approved:
  "summary": "...",
  "confidence": 0.9,
  "remaining_concerns": ["..."]
  // si rectify:
  "diagnosis": "...",
  "target_after_story_id": "story_XXX ou null pour ajouter à la fin",
  "new_stories": [
    {{
      "id": "...",
      "title": "...",
      "description": "...",
      "acceptance_criteria": ["..."],
      "depends_on": [],
      "github_issues": [],
      "reason": "...",
      "steps": [
        {{
          "id": "...",
          "title": "...",
          "task_type": "...",
          "agent": "code",
          "depends_on": [],
          "inputs": {{}},
          "expected_outputs": {{}},
          "acceptance_criteria": ["..."],
          "reason": "..."
        }}
      ]
    }}
  ]
}}"""


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


def _format_retry_feedback(step: StepState) -> str:
    """On a retry (attempt > 0), inject the PREVIOUS attempt's failure so the
    agent does not retry blind: the verification errors (probe output) are the
    training signal that tells it exactly what to fix."""
    if step.attempt <= 0 or not step.verification or step.verification.passed:
        return ""
    lines = [f"\nÉCHEC DE LA TENTATIVE PRÉCÉDENTE (tentative {step.attempt}/{step.max_attempts}):"]
    if step.agent_result and step.agent_result.summary:
        lines.append(f"Résumé précédent: {step.agent_result.summary[:300]}")
    lines.append("Erreurs de vérification (à corriger — ne refais PAS la même chose):")
    budget = 2000
    for err in step.verification.errors[:6]:
        chunk = str(err)[:600]
        lines.append(f"  ✗ {chunk}")
        budget -= len(chunk)
        if budget <= 0:
            break
    lines.append("Analyse ces erreurs, corrige la cause, puis re-vérifie avec les mêmes PROBEs.\n")
    return "\n".join(lines)


def _format_loop_context(step: StepState) -> str:
    reason = step.inputs.get("_loop_reason") or step.inputs.get("_rectification_reason")
    diagnosis = step.inputs.get("_loop_diagnosis") or step.inputs.get("_rectification_diagnosis")
    if not reason:
        return ""
    text = f"\nBOUCLE — Cette étape a été relancée.\nRaison: {reason}\n"
    if diagnosis:
        text += f"Diagnostic complet:\n{diagnosis}\n"
    return text


def _format_all_stories(epic: EpicState) -> str:
    lines = ["PLAN ET RÉSULTATS:"]
    for story in epic.stories:
        lines.append(f"\n### {story.id} — {story.title} [{story.status.value}]")
        lines.append(f"Description: {story.description}")
        lines.append(f"Critères: {', '.join(story.acceptance_criteria)}")
        for step in story.steps:
            status_icon = {"done": "✅", "running": "🔄", "pending": "⏳", "failed": "❌"}.get(step.status.value, "❓")
            lines.append(f"  {status_icon} {step.task_type} [{step.status.value}] (agent: {step.agent})")
            if step.agent_result:
                lines.append(f"    Résumé: {step.agent_result.summary[:200]}")
                if step.agent_result.modified_files:
                    lines.append(f"    Fichiers: {', '.join(step.agent_result.modified_files[:10])}")
                if step.agent_result.risks:
                    lines.append(f"    Risques: {', '.join(step.agent_result.risks[:3])}")
            if step.verification:
                v = "✅ PASSÉE" if step.verification.passed else "❌ ÉCHOUÉE"
                lines.append(f"    Vérification: {v}")
    return "\n".join(lines)


def _format_review_history(epic: EpicState) -> str:
    if not epic.review_history:
        return ""
    lines = ["HISTORIQUE DES REVIEWS:"]
    for entry in epic.review_history:
        r = entry.get("result", {})
        action = r.get("action", "unknown")
        lines.append(f"\nRound {entry.get('round', '?')}: {action}")
        if action == "rectify":
            lines.append(f"  Diagnosis: {r.get('diagnosis', '')[:300]}")
            for s in r.get("new_stories", []):
                lines.append(f"  → {s.get('id', '?')}: {s.get('title', '')}")
        elif action == "approved":
            lines.append(f"  Summary: {r.get('summary', '')[:200]}")
    return "\n".join(lines)
