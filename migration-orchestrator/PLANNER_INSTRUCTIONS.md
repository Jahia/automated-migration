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

RÈGLES DE DÉCOMPOSITION (granularité des stories — obligatoire):
10. **UNE STORY = UNE STEP = un résultat contenu.** Le moteur ne transmet le contexte
    qu'au niveau des stories approuvées (résumé + fichiers); les steps d'une MÊME story
    ne se voient pas entre elles. La granularité des stories EST la granularité du contexte.
11. **Limite la charge d'une step**: jamais "tous les composants" / "toutes les pages"
    dans une seule step. Ordres de grandeur: 1 composant par step; <= 3 pages par step;
    1 famille d'artefacts par step. Une grosse step LLM produit des stubs.
12. **task_type "script" pour tout travail déterministe** (extraction, imports,
    chargeurs, batteries de gates): le moteur exécute directement `inputs.script`
    (string ou liste) + les lignes `PROBE:` des acceptance_criteria — AUCUNE session
    LLM, aucune improvisation. Une step script sans `inputs.script` exécute uniquement
    ses PROBEs.
13. **Entrées/sorties explicites par step**: `inputs.consumes` (fichiers lus, produits
    en amont) + `expected_outputs` (fichiers écrits) + une PROBE `contract.sh` — le
    vrai contrat inter-step, ce sont les FICHIERS SUR DISQUE, vérifiés, pas espérés.
14. **Compétence minimale**: au plus UN `inputs.skill` par step, le plus focalisé
    possible; chaque critère d'acceptation ne concerne QUE cette step (pas de
    boilerplate copié-collé entre steps).
15. Pour les plans de migration Jahia, ne rédige pas les plans à la main:
    `python3 orchestration/lib/gen_plan.py <project> --kind content|build` les génère
    depuis les artefacts du projet (sitemap, component-manifest, config mainResource)
    en appliquant les règles 10-14. Agnostique au CMS source: rien de spécifique au
    projet n'est codé en dur.
16. **Les PROBEs sont exécutées par le MOTEUR à chaque tentative, pour TOUTES les
    steps** (LLM comme script), quoi que l'agent déclare dans `commands_requested`.
    Une PROBE est donc le contrat de sortie infalsifiable de la step: mets-y la
    mesure contre l'artefact réel, jamais un proxy.
17. **Budget temps par step**: `inputs._deadline_s` (les clés préfixées `_` sont
    réservées au moteur, invisibles dans le prompt). Défaut: 1800s, ou l'env
    `ORCH_STEP_DEADLINE_S`. Dimensionne-le au travail réel (une step de contenu qui
    itère vers la parité pixel a besoin de 30-45 min: build + deploy + probe par
    itération). Si la deadline coupe la session, la tentative suivante est informée
    et REPREND (travail idempotent), elle ne recommence pas.

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
          "id": "story_analyze",
          "title": "Analyser la structure du module d'auth",
          "description": "UNE story = UNE step (règle 10): le résumé de cette story est le contexte de la suivante.",
          "acceptance_criteria": ["Structure identifiée"],
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
            }
          ]
        },
        {
          "id": "story_implement",
          "title": "Extraire validateSession",
          "description": "Déplacer la logique de validation vers sessionValidator.ts",
          "acceptance_criteria": ["sessionValidator.ts créé"],
          "depends_on": ["story_analyze"],
          "steps": [
            {
              "id": "s1_implement",
              "title": "Extraire validateSession",
              "task_type": "implement",
              "agent": "code",
              "depends_on": [],
              "inputs": {"target": "src/auth/session.ts"},
              "acceptance_criteria": ["Créer sessionValidator.ts"]
            }
          ]
        },
        {
          "id": "story_test",
          "title": "Tests unitaires (déterministe)",
          "description": "task_type script (règle 12): le moteur exécute les commandes, pas de session LLM.",
          "acceptance_criteria": ["Tests verts"],
          "depends_on": ["story_implement"],
          "steps": [
            {
              "id": "s1_test",
              "title": "Lancer la suite de tests",
              "task_type": "script",
              "depends_on": [],
              "inputs": {"script": "npm test"},
              "acceptance_criteria": ["PROBE: npm test"]
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
