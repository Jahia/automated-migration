# Skill Creation Governance

Rules for adding, modifying, or removing skills in jahiaMigration.

---

## When to add a new skill

A new skill is warranted when:
1. An agent repeats the same multi-step procedure across 2+ sessions without a written guide.
2. A domain is materially different from all existing skills (not a variation of an existing one).
3. The skill represents a reusable workflow, not a one-off fix.

A new skill is NOT warranted when:
- The knowledge can be added as a section to an existing skill.
- The task is a one-shot fix documented in git history.

---

## Skill file structure (required)

```
.agents/skills/<skill-name>/
  SKILL.md              ← Required. Frontmatter + content.
  agents/
    claude.yaml         ← Required. Platform descriptor for Claude Code.
  references/           ← Optional. Skill-specific reference docs.
```

---

## SKILL.md frontmatter (required fields)

```yaml
---
name: <slug matching folder name>
description: <one sentence — what the skill does>
type: <workflow | production | technical | review | content | osgi>
phase: <1-11 | support | dev | osgi | content>
status: <active | draft | deprecated>
allowed-tools: <comma-separated tool names>
---
```

Optional frontmatter fields (for orchestrators):
```yaml
invokes_workflow: true
sub_skills:
  - <skill-name-1>
  - <skill-name-2>
depends_on:
  - <skill-name>
```

---

## claude.yaml format (required)

```yaml
interface:
  display_name: "<AgentName> — <Short task description>"
  short_description: "<One sentence — what the agent does for the user>"
  default_prompt: "Use $<skill-name> to <task description>."
  triggers:
    - "<natural language phrase that invokes this skill>"
    - "<alternative phrase>"
```

---

## Agent identity (required for workflow skills 01-11)

Every workflow skill (01-11) and the `migration-workflow` orchestrator must include an `## Agent identity` section in SKILL.md:

```markdown
## Agent identity
- **Agent name:** <Name>
- **Reference style:** <Metaphor or domain>
- **Signature line (en):** *"<Short memorable phrase>"*
- **Personality note:** <One sentence on tone and approach>
- **Usage rule:** Brief invocation only in orchestrator narration. Never appears in deliverables.
```

Support, dev, osgi, and content skills do not require agent identity sections.

---

## SKILL_MANIFEST.md and SKILLS.md

After adding a skill:
1. Add a row to `SKILL_MANIFEST.md` in the correct group.
2. Add trigger phrases to `SKILLS.md` under the correct category.
3. Add a row to `.agents/README.md` in the correct table.

---

## Deprecating a skill

1. Set `status: deprecated` in frontmatter.
2. Add a one-line note at the top of SKILL.md pointing to the replacement.
3. Remove the skill from `SKILLS.md` triggers.
4. Keep the folder — do not delete deprecated skills (referenced in session transcripts).
