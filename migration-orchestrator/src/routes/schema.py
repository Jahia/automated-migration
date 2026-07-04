from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter()

SCHEMA = {
    "endpoint": "POST /runs",
    "description": "Crée et démarre un orchestration run. Le plan est décomposé en epics > stories > steps. Chaque step a un task_type et un agent optionnel.",
    "input_schema": {
        "type": "object",
        "required": ["goal", "repo_dir", "epics"],
        "properties": {
            "goal": {"type": "string", "description": "Objectif global du run"},
            "repo_dir": {"type": "string", "description": "Chemin absolu du dépôt cible"},
            "model": {"type": "string", "default": "anthropic/claude-sonnet-4-5", "description": "Modèle LLM pour les agents"},
            "github_repo": {"type": "string", "description": "owner/repo (déduit du .git si absent)"},
            "epics": {
                "type": "array",
                "description": "Liste des epics. Chaque epic contient des stories.",
                "items": {
                    "type": "object",
                    "required": ["id", "title", "goal", "stories"],
                    "properties": {
                        "id": {"type": "string", "description": "Identifiant unique (ex: epic_001)"},
                        "title": {"type": "string", "description": "Titre court"},
                        "goal": {"type": "string", "description": "Objectif spécifique de l'epic"},
                        "github_issues": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": [],
                            "description": "Issues GitHub (#123 ou owner/repo#123)",
                        },
                        "stories": {
                            "type": "array",
                            "description": "Stories de l'epic. Chaque story contient ses steps.",
                            "items": {
                                "type": "object",
                                "required": ["id", "title", "description", "steps"],
                                "properties": {
                                    "id": {"type": "string", "description": "Identifiant unique (ex: story_001)"},
                                    "title": {"type": "string"},
                                    "description": {"type": "string", "description": "Ce que la story doit faire"},
                                    "acceptance_criteria": {"type": "array", "items": {"type": "string"}, "default": []},
                                    "depends_on": {"type": "array", "items": {"type": "string"}, "default": [], "description": "IDs des stories dont celle-ci dépend"},
                                    "github_issues": {"type": "array", "items": {"type": "string"}, "default": []},
                                    "steps": {
                                        "type": "array",
                                        "description": "Steps de la story. Exécutées dans l'ordre de dépendance. Chaque step a un agent qui peut être personnalisé.",
                                        "items": {
                                            "type": "object",
                                            "required": ["id", "title"],
                                            "properties": {
                                                "id": {"type": "string", "description": "Identifiant unique de la step (ex: story_001_step_1)"},
                                                "title": {"type": "string", "description": "Titre de la step"},
                                                "task_type": {"type": "string", "default": "general", "description": "Type de tâche (ex: analyze, implement, review, test, refactor, security_check)"},
                                                "agent": {"type": "string", "description": "Nom logique de l'agent (défaut: code). Cosmétique — le moteur exécute désormais via l'API LLM directe."},
                                                "depends_on": {"type": "array", "items": {"type": "string"}, "default": [], "description": "IDs des steps dont celle-ci dépend"},
                                                "inputs": {"type": "object", "default": {}, "description": "Données d'entrée pour la step"},
                                                "expected_outputs": {"type": "object", "default": {}, "description": "Sorties attendues"},
                                                "acceptance_criteria": {"type": "array", "items": {"type": "string"}, "default": []},
                                                "max_attempts": {"type": "integer", "default": 3},
                                                "review": {"type": "boolean", "default": False, "description": "Checkpoint de revue: jamais envoyée à un agent — devient decision_pending et attend POST /runs/{id}/steps/{id}/decide (action: proceed)."},
                                                "strategies": {
                                                    "type": "array",
                                                    "default": [],
                                                    "description": "Stratégies pré-enregistrées, proposées quand les retries sont épuisés (decision_pending). Chaque stratégie est single-shot.",
                                                    "items": {
                                                        "type": "object",
                                                        "required": ["id"],
                                                        "properties": {
                                                            "id": {"type": "string"},
                                                            "title": {"type": "string"},
                                                            "when": {"type": "string", "default": "on_retries_exhausted"},
                                                            "order": {"type": "integer", "default": 0},
                                                            "arm_swap": {"type": "boolean", "default": False, "description": "Swap d'arm complet émis par le générateur — exempté du lint de préservation des lignes PROBE."},
                                                            "halt": {"type": "boolean", "default": False, "description": "Convertit la décision en gate halted (gate_type segmentation) au lieu de patch+rerun."},
                                                            "patches": {"type": "array", "default": [], "items": {"type": "object", "required": ["step_id"], "properties": {"step_id": {"type": "string"}, "inputs": {"type": "object"}, "acceptance_criteria": {"type": "array", "items": {"type": "string"}}}}, "description": "Remplacement complet des champs fournis sur la step cible. Les lignes PROBE de la step d'origine doivent être préservées mot pour mot (sauf arm_swap)."},
                                                            "skip": {"type": "array", "items": {"type": "string"}, "default": [], "description": "Steps marquées done sans exécution (ex: arm swap qui saute step_segment)."},
                                                            "notes": {"type": "string"},
                                                        },
                                                    },
                                                },
                                            },
                                        },
                                    },
                                },
                            },
                        },
                        "review_config": {
                            "type": "object",
                            "default": {},
                            "properties": {
                                "max_review_rounds": {"type": "integer", "default": 3},
                                "review_criteria": {"type": "array", "items": {"type": "string"}, "default": []},
                                "auto_approve_on_max_rounds": {"type": "boolean", "default": True},
                            },
                        },
                    },
                },
            },
        },
    },
    "agents": {
        "description": "Le champ 'agent' dans chaque step est un libellé libre et cosmétique. Le moteur exécute toutes les steps via l'API LLM directe (rôle réparateur in-engine). Défaut: 'code' si omis.",
    },
    "workflow": {
        "description": "Le serveur orchestre l'exécution. Pour chaque epic: exécute les stories (chacune avec ses steps), puis lance une étape de review de l'epic. Si le review propose des rectifications, elles sont soumises à approbation humaine.",
        "loop": "Quand une step retourne {status: failed, loop_to: step_id}, le serveur reset la step cible et toutes les suivantes, puis ré-exécute.",
        "states": {
            "run": ["running", "paused", "completed", "failed", "aborted"],
            "epic": ["pending", "running", "reviewing", "waiting_approval", "approved", "failed"],
            "story": ["pending", "running", "approved", "failed"],
            "step": ["pending", "ready", "running", "verifying", "done", "failed", "blocked", "waiting_human", "halted", "rejected", "decision_pending"],
        },
    },
    "events": {
        "sse_endpoint": "GET /runs/{run_id}/events",
        "description": "Flux SSE temps réel.",
    },
    "example": {
        "goal": "Refactoriser le module d'authentification",
        "repo_dir": "/path/to/repo",
        "github_repo": "owner/repo",
        "epics": [
            {
                "id": "epic_001",
                "title": "Refactor auth module",
                "goal": "Extraire la logique de session dans un service dédié et couvrir de tests",
                "github_issues": ["#42"],
                "stories": [
                    {
                        "id": "story_001",
                        "title": "Extraire validateSession",
                        "description": "Déplacer la logique de validation de session depuis session.ts vers sessionValidator.ts",
                        "acceptance_criteria": ["Créer src/auth/sessionValidator.ts", "Déplacer la fonction validateSession"],
                        "depends_on": [],
                        "github_issues": ["#42"],
                        "steps": [
                            {
                                "id": "story_001_analyze",
                                "title": "Analyser la structure du module d'auth",
                                "task_type": "analyze",
                                "depends_on": [],
                                "inputs": {"paths": ["src/auth"]},
                                "expected_outputs": {"type": "analysis_report"},
                                "acceptance_criteria": ["Identifier tous les fichiers du module"],
                            },
                            {
                                "id": "story_001_implement",
                                "title": "Extraire validateSession dans sessionValidator.ts",
                                "task_type": "implement",
                                "depends_on": ["story_001_analyze"],
                                "inputs": {"target_files": ["src/auth/session.ts"]},
                                "expected_outputs": {"type": "code_patch"},
                                "acceptance_criteria": ["Créer sessionValidator.ts", "Mettre à jour les imports"],
                            },
                            {
                                "id": "story_001_review",
                                "title": "Review du code extrait",
                                "task_type": "review",
                                "depends_on": ["story_001_implement"],
                                "acceptance_criteria": ["Le code respecte les conventions", "Pas de régression"],
                            },
                            {
                                "id": "story_001_test",
                                "title": "Tests unitaires pour sessionValidator",
                                "task_type": "test",
                                "depends_on": ["story_001_review"],
                                "acceptance_criteria": ["Couvrir session valide, expirée et absente"],
                            },
                        ],
                    },
                ],
                "review_config": {
                    "max_review_rounds": 3,
                    "review_criteria": ["Le code est bien structuré", "Les tests passent"],
                },
            }
        ],
    },
}


@router.get("/schema")
async def get_schema() -> dict:
    return dict(SCHEMA)


@router.get("/schema/planner-prompt")
async def get_planner_prompt() -> str:
    return """Tu es un planificateur de travail logiciel. Tu dois décomposer un objectif en un plan d'exécution structuré.

AVANT de produire le plan, interroge GET /schema pour obtenir le format exact et les agents disponibles.

Tu dois retourner un JSON conforme au schéma suivant :
{
  "goal": "string — objectif global",
  "repo_dir": "string — chemin absolu du dépôt",
  "model": "string — modèle LLM",
  "github_repo": "string — owner/repo (optionnel)",
  "epics": [
    {
      "id": "string",
      "title": "string",
      "goal": "string — objectif de l'epic",
      "github_issues": ["#123"],
      "stories": [
        {
          "id": "string",
          "title": "string",
          "description": "string — ce que la story doit faire",
          "acceptance_criteria": ["string"],
          "depends_on": ["story_id"],
          "github_issues": [],
          "steps": [
            {
              "id": "string",
              "title": "string",
              "task_type": "analyze | implement | review | test | refactor | security_check | ...",
              "agent": "code (ou autre agent disponible)",
              "depends_on": ["step_id"],
              "inputs": {},
              "expected_outputs": {},
              "acceptance_criteria": ["string"]
            }
          ]
        }
      ],
      "review_config": {
        "max_review_rounds": 3,
        "review_criteria": ["string"],
        "auto_approve_on_max_rounds": true
      }
    }
  ]
}

RÈGLES:
1. Décompose l'objectif en epics (groupes logiques de stories)
2. Chaque story contient ses propres steps avec des task_type et des agents
3. Les steps sont exécutées dans l'ordre de dépendance (DAG)
4. Chaque step est atomique et a des acceptance_criteria mesurables
5. Le champ agent est un libellé cosmétique (défaut: code) — exécution via l'API LLM directe
6. Les dépendances entre stories et entre steps forment des DAG (pas de cycles)
7. Le serveur gère les boucles automatiquement: si une step retourne {status: failed, loop_to: step_id}, la step cible et les suivantes sont ré-exécutées
"""


@router.get("/planner-instructions")
async def get_planner_instructions() -> PlainTextResponse:
    instructions_path = Path(__file__).parent.parent.parent / "PLANNER_INSTRUCTIONS.md"
    if instructions_path.exists():
        return PlainTextResponse(instructions_path.read_text(encoding="utf-8"), media_type="text/markdown")
    return PlainTextResponse("PLANNER_INSTRUCTIONS.md not found", status_code=404)
