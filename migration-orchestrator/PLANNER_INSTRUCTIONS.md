# Instructions pour le planificateur LLM

## System prompt

Tu es un planificateur de travail logiciel. Tu dois décomposer un objectif en un plan d'exécution structuré.

interroge GET http://localhost:8001/schema pour obtenir :
- Le format exact attendu (input_schema)
- Un exemple de plan valide

Ensuite, retourne UNIQUEMENT le JSON conforme au schéma, sans markdown.

RÈGLES:
1. Décompose l'objectif en epics (groupes logiques de stories)
2. Chaque story contient SES PROPRES steps (tu les définis)
3. Chaque step a:
   - id: identifiant unique
   - title: ce que la step fait
   - task_type: type de tâche (analyze, implement, review, test, refactor, security_check, ou tout autre)
   - agent (optionnel): nom de l'agent OpenCode à utiliser. Si omis, utilise "code". Les agents doivent être définis dans le projet cible (`.opencode/agent/`).
   - depends_on: IDs des steps dont celle-ci dépend
   - inputs: données d'entrée
   - expected_outputs: sorties attendues
   - acceptance_criteria: critères d'acceptation vérifiables
4. Les dépendances forment des DAG (pas de cycles)
5. Quand une step a un problème, l'agent peut retourner {loop_to: step_id} pour re-exécuter cette step et les suivantes
6. Quand l'agent détecte un problème grave (données corrompues, conflit critique, risque de perte de données), il retourne {status: "halt"} — le plan est mis en pause jusqu'à intervention humaine
7. Tu peux utiliser n'importe quel task_type — le serveur n'impose pas de pipeline fixe
8. Le serveur lance automatiquement une review de l'epic après toutes les stories
9. Le champ agent est libre — tu décides quels agents utiliser (ex: "code", "security", "review", "test", etc.)

## Endpoints

### Créer le plan (sans démarrer)
```
POST http://localhost:8001/runs
```
Le run est créé avec le statut "created". Pour démarrer :
```
POST http://localhost:8001/runs/{run_id}/start
```
Ou cliquez "Démarrer" dans l'interface web.

### Suivre l'exécution
```
GET http://localhost:8001/runs/{run_id}/events (SSE)
```

### Démarrer le run
```
POST http://localhost:8001/runs/{run_id}/start
```

### Répondre à une question de l'agent
```
POST http://localhost:8001/runs/{run_id}/steps/{step_id}/answer
Body: {"answer": "..."}
```

### Approuver un sous-plan de rectification
```
POST http://localhost:8001/runs/{run_id}/epics/{epic_id}/proposal/approve
```

### Rejeter un sous-plan de rectification
```
POST http://localhost:8001/runs/{run_id}/epics/{epic_id}/proposal/reject
```

### Mettre en pause
```
POST http://localhost:8001/runs/{run_id}/pause
```

### Reprendre
```
POST http://localhost:8001/runs/{run_id}/resume
```

### Sauter à une étape
```
POST http://localhost:8001/runs/{run_id}/jump
Body: {"step_id": "...", "reset_dependents": true}
```

### Schéma complet
```
GET http://localhost:8001/schema
```

### Prompt planner prêt à l'emploi
```
GET http://localhost:8001/schema/planner-prompt
```

## Exemple de plan complet

```json
{
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
          "description": "Déplacer la logique de validation de session vers sessionValidator.ts",
          "acceptance_criteria": ["Créer sessionValidator.ts", "Déplacer la fonction"],
          "depends_on": [],
          "github_issues": ["#42"],
          "steps": [
            {
              "id": "s1_analyze",
              "title": "Analyser la structure du module d'auth",
              "task_type": "analyze",
              "depends_on": [],
              "inputs": {"paths": ["src/auth"]},
              "acceptance_criteria": ["Identifier tous les fichiers"]
            },
            {
              "id": "s1_implement",
              "title": "Extraire validateSession",
              "task_type": "implement",
              "agent": "code",
              "depends_on": ["s1_analyze"],
              "inputs": {"target": "src/auth/session.ts"},
              "acceptance_criteria": ["Créer sessionValidator.ts"]
            },
            {
              "id": "s1_review",
              "title": "Review du code",
              "task_type": "review",
              "depends_on": ["s1_implement"],
              "acceptance_criteria": ["Pas de régression"]
            },
            {
              "id": "s1_test",
              "title": "Tests unitaires",
              "task_type": "test",
              "depends_on": ["s1_review"],
              "acceptance_criteria": ["Couvrir tous les cas"]
            }
          ]
        }
      ],
      "review_config": {
        "max_review_rounds": 3,
        "review_criteria": ["Le code est bien structuré", "Les tests passent"]
      }
    }
  ]
}
```

## Démarrage du serveur

```bash
# Terminal 1 — Backend
cd migration-orchestrator
source .venv/bin/activate
uvicorn src.main:app --host 0.0.0.0 --port 8001

# Terminal 2 — Frontend (dev)
cd frontend
npm run dev
```

Le frontend est accessible sur `http://localhost:5173` (dev) ou `http://localhost:8001/app` (production).
