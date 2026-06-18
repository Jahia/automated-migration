---
name: migration-workflow
description: Master orchestrator for website-to-Jahia migrations. Reads state.json to resume mid-migration. Chains all 13 steps in order. Always start here.
type: workflow
phase: 0
status: active
allowed-tools: Bash, Read, Write, WebFetch
---

# Skill: Migration Workflow

Master orchestrator. Runs steps 0-12 in order, tracks state, and knows how to resume.

---

## Agent identity
- **Agent name:** Conductor
- **Personality:** Methodical scheduler. Never skips a step. Always checks state before acting. Announces each step before starting it.

---

## Step 1: Read current state

Find the project:
```bash
find . -name "state.json" -path "*/workflow-output/*" | head -1
```

If found, read it and print the current status of each step. If not found, this is a fresh migration - state.json will be created in step 0.

Show the user:
```
MIGRATION STATUS
================
Step 0 - Environment setup:    [done / pending]
Step 1 - Analyze website:      [done / pending]
Step 2 - Scaffold module:      [done / pending]
Step 3 - Import assets:        [done / pending]
Step 4 - Define content types: [done / pending]
Step 5 - Navigation:           [done / pending]
Step 6 - JCR Query component:  [done / pending]
Step 7 - Components:           [done / pending]
Step 8 - Page templates:       [done / pending]
Step 9 - Create content:       [done / pending]
Step 10 - Code review:         [done / pending]
Step 10.5 - Accessibility:     [done / pending]
Step 11 - Visual diff:         [done / pending]

Resume from step: N
```

Ask the user: "Shall I resume from step N, or start over from step 0?"

---

## Step 2: Execute each step in order

For each pending step, announce it, invoke the corresponding skill, and write the result to state.json before moving to the next.

### State write pattern (run after EVERY step completes)

```bash
python3 - << 'EOF'
import json, datetime, os

state_path = next((r for r in [
    f for f in __import__('glob').glob('**/workflow-output/state.json', recursive=True)
]), 'workflow-output/state.json')

os.makedirs(os.path.dirname(state_path), exist_ok=True)

try:
    with open(state_path) as f:
        state = json.load(f)
except:
    state = {"steps": {}}

state["steps"]["STEP_KEY"] = {
    "status": "completed",
    "completedAt": datetime.datetime.utcnow().isoformat() + "Z",
    "notes": "STEP_NOTES"
}

with open(state_path, 'w') as f:
    json.dump(state, f, indent=2)

print(f"State written: STEP_KEY = completed")
EOF
```

Replace `STEP_KEY` with the step identifier (e.g. `0-environment`, `1-analyze`, `7-components`) and `STEP_NOTES` with a one-line summary of what was done.

### Step sequence

| Step | Skill to invoke | State key |
|------|----------------|-----------|
| 0 | `/0-migration-start` | `0-environment` |
| 1 | `/1-analyze <reference-url>` | `1-analyze` |
| 2 | `/2-scaffold` | `2-scaffold` |
| 3 | `/3-assets` | `3-assets` |
| 4-6 | `/4-content-types` (includes nav + jcr-query) | `4-content-types` |
| 7 | `/5-components` | `7-components` |
| 8 | `/4-templates` | `8-templates` |
| 9 | `/6-content` | `9-content` |
| 10 | `/jahia-review` | `10-review` |
| 10.5 | `/jahia-dev-accessibility` (run on home + 3 key sub-pages) | `10.5-accessibility` |
| 11 | `/11-debug` (only if issues found) | `11-debug` |
| 12 | `/12-visual-diff` | `12-visual-diff` |

---

## Step 3: Final completion check

Only declare migration complete when ALL of the following are true:

- [ ] `state.json` shows all steps completed
- [ ] `workflow-output/visual-diff/SUMMARY.md` exists and has 0 critical gaps
- [ ] Both `fr` and `en` content populated on all pages
- [ ] Code review (step 10) passed with 0 critical issues
- [ ] Accessibility audit (step 10.5) passed with 0 critical or serious axe-core violations on home + key pages
- [ ] User has given explicit SIGNOFF

```
MIGRATION COMPLETE

Site:     <siteKey>
Pages:    N
ISO gaps: 0 critical, M minor
Duration: started <date> -> completed <date>

The site is ready for handoff.
```
