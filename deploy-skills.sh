#!/usr/bin/env bash
# deploy-skills.sh — Install jahiaMigration skills as Claude Code commands
#
# Reads agents/claude.yaml from each workflow skill folder and installs
# the skill as a .claude/commands/<skill-name>.md symlink or copy.
#
# Usage:
#   ./deploy-skills.sh                    # install all workflow skills
#   ./deploy-skills.sh --target /path     # install into a specific project
#   ./deploy-skills.sh --list             # list what would be installed

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$SCRIPT_DIR/.agents/skills"
DEFAULT_TARGET="$SCRIPT_DIR/.claude/commands"

# Parse arguments
TARGET_DIR="$DEFAULT_TARGET"
LIST_ONLY=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) TARGET_DIR="$2"; shift 2 ;;
    --list)   LIST_ONLY=true; shift ;;
    *) echo "Unknown argument: $1"; exit 1 ;;
  esac
done

# Workflow skill folders to deploy (numbered, sequential)
WORKFLOW_SKILLS=(
  "01-analyze-website"
  "02-scaffold-module"
  "03-import-assets"
  "04-define-content-types"
  "05-implement-navigation"
  "06-implement-jcr-query"
  "07-implement-components"
  "08-page-templates"
  "09-create-content"
  "10-review"
  "11-debug"
  "support-create-view"
  "support-deploy"
)

echo "jahiaMigration skill deployer"
echo "Source: $SKILLS_DIR"
echo "Target: $TARGET_DIR"
echo ""

if $LIST_ONLY; then
  echo "Skills that would be installed:"
  for skill in "${WORKFLOW_SKILLS[@]}"; do
    yaml="$SKILLS_DIR/$skill/agents/claude.yaml"
    if [[ -f "$yaml" ]]; then
      display_name=$(grep 'display_name:' "$yaml" | head -1 | sed 's/.*display_name: *"//' | sed 's/"//')
      echo "  $skill → $display_name"
    else
      echo "  $skill → (no agents/claude.yaml — skill SKILL.md only)"
    fi
  done
  exit 0
fi

mkdir -p "$TARGET_DIR"

installed=0
skipped=0

for skill in "${WORKFLOW_SKILLS[@]}"; do
  skill_dir="$SKILLS_DIR/$skill"
  skill_md="$skill_dir/SKILL.md"
  yaml="$skill_dir/agents/claude.yaml"
  target_file="$TARGET_DIR/$skill.md"

  if [[ ! -f "$skill_md" ]]; then
    echo "  SKIP $skill — no SKILL.md found"
    ((skipped++)) || true
    continue
  fi

  # Read display name from claude.yaml if present
  if [[ -f "$yaml" ]]; then
    display_name=$(grep 'display_name:' "$yaml" | head -1 | sed 's/.*display_name: *"//' | sed 's/"//')
  else
    display_name="$skill"
  fi

  # Extract description from SKILL.md frontmatter
  description=$(awk '/^---$/{n++} n==1 && /^description:/{print; exit}' "$skill_md" | sed 's/^description: *//')

  # Create a thin command wrapper that references the skill
  cat > "$target_file" <<EOF
---
description: $description
---

# $display_name

This command invokes the \`$skill\` skill from the jahiaMigration harness.

Read and follow: \`$skill_dir/SKILL.md\`
EOF

  echo "  OK  $skill → $target_file"
  ((installed++)) || true
done

echo ""
echo "Done. $installed installed, $skipped skipped."
echo ""
echo "To install into a different project:"
echo "  ./deploy-skills.sh --target /path/to/project/.claude/commands"
