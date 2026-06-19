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

**Distrust `completed` without `evidence`.** Any step marked `completed` but
lacking an `evidence` field (or written in a prior session) must be re-probed
with its verification probe before you trust it. Resuming on an unverified
`completed` is how the SIAL Paris migration lost a full session: state claimed
"27 pages populated" while 6 sub-pages were empty hero stubs. Re-probe, then
resume from the first step that genuinely fails its probe.

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

### NON-NEGOTIABLE: a step is `completed` ONLY when a probe proves it

The single most expensive failure mode in this harness is an agent writing
`"status": "completed"` because it *believes* it finished, when the live
instance disagrees. A false `completed` makes the next session resume from a
lie and burn tokens on confused rework. **Never assert completion — verify it.**

Rules:
1. Every step has a **verification probe** (see table below). Run it.
2. Write `completed` **only if the probe passes**. If it fails or you cannot
   run it, write `in_progress` with `notes` describing what is actually done
   and what is missing. `in_progress` is the honest default, not a failure.
3. The thing written to `state.json` is the **probe result**, not your summary.
4. Never write `completed` for a step you did not personally verify this
   session — not even if a prior `state.json` already said so.

### State write pattern (run after EVERY step — writes the probe result)

```bash
python3 - << 'EOF'
import json, datetime, os, glob

state_path = next(iter(glob.glob('**/workflow-output/state.json', recursive=True)),
                  'workflow-output/state.json')
os.makedirs(os.path.dirname(state_path), exist_ok=True)
try:
    with open(state_path) as f: state = json.load(f)
except: state = {"steps": {}}

# VERIFIED is the boolean result of the step's probe (see verification table).
# Do NOT hardcode True. Compute it from a real probe and paste the value here.
VERIFIED = False          # <-- set from probe output
EVIDENCE = "PROBE_OUTPUT" # <-- paste the probe's actual numbers/paths

state["steps"]["STEP_KEY"] = {
    "status": "completed" if VERIFIED else "in_progress",
    "completedAt": (datetime.datetime.utcnow().isoformat() + "Z") if VERIFIED else None,
    "notes": "STEP_NOTES",
    "evidence": EVIDENCE,
}
with open(state_path, 'w') as f: json.dump(state, f, indent=2)
print(f"State written: STEP_KEY = {state['steps']['STEP_KEY']['status']}")
EOF
```

Replace `STEP_KEY`, `STEP_NOTES`, and crucially `VERIFIED`/`EVIDENCE` with the
real probe result. `VERIFIED` must come from a command you actually ran.

### Verification probes (run before writing `completed`)

| Step | Probe — passes only if | 
|------|------------------------|
| 1-analyze | `component-manifest.json` + `content-data.json` exist and total instances > 0 |
| 2-scaffold | `package.json` exists; `yarn build` exits 0 |
| 3-assets | every CSS/JS referenced in `Layout.tsx` exists under `static/` |
| 4-content-types | `yarn build` 0 errors; each new type appears in `definitions.cnd` AND has `_en`/`_fr` `.properties` keys |
| 7-components | `yarn build` 0 errors; every component has a matching resource-bundle label |
| 8-templates | `Layout.tsx` has header+footer `AbsoluteArea`; each template file exists |
| 9-content | **per-page checklist** (below) — every page's LIVE `<main>` text > 400 chars |
| 10-review | review ran; 0 critical issues |
| 10.5-accessibility | axe-core ran on home + key pages; 0 critical/serious |
| 12-visual-diff | `visual-diff/SUMMARY.md` exists; 0 critical gaps |

### Step 9 probe — per-page completion checklist (no coarse booleans)

Content is the step most prone to false `completed`. Do NOT record one boolean
for "content done". Record a checklist keyed by page path, each entry verified
against the **live render** (a child-count > 0 is NOT enough — a lone hero stub
counts as empty):

```bash
python3 - << 'EOF'
import json, subprocess, re, glob
SITE="sial-paris"; LANG="fr"
pages=["home","le-salon","les-exposants","temps-forts","tendances","infos-pratiques","medias"]
checklist={}
for p in pages:
    node=f"/sites/{SITE}/home" if p=="home" else f"/sites/{SITE}/home/{p}"
    url=f"http://localhost:8080/cms/render/live/{LANG}{node}.html"
    html=subprocess.run(["curl","-s","-u","root:root",url],capture_output=True,text=True).stdout
    m=re.search(r"<main[^>]*>(.*?)</main>",html,re.S|re.I)
    txt=re.sub(r"\s+"," ",re.sub(r"<[^>]+>","",m.group(1))).strip() if m else ""
    checklist[p]={"liveBodyTextLen":len(txt),"complete":len(txt)>400}
all_done=all(v["complete"] for v in checklist.values())
print(json.dumps(checklist,indent=2)); print("STEP 9 VERIFIED:",all_done)
EOF
```

Write the checklist into `state["steps"]["9-content"]["pageChecklist"]` and set
`status` to `completed` only when every page's `complete` is `true`.

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

Only declare migration complete when ALL of the following are true. Each box
must be backed by a probe run **this session** — a checkmark inherited from a
prior `state.json` does not count.

- [ ] `state.json` shows all steps completed AND every step has an `evidence` field
- [ ] Step 9 `pageChecklist` shows `complete: true` for EVERY page (live `<main>` text > 400 chars)
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
