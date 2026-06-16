# jahiaMigration

Agentic harness for migrating existing websites to Jahia JavaScript modules.

## Quick start

```bash
# In Claude Code, from this repo:
/migration-workflow https://example.com
```

This runs the complete 6-step pipeline: analyze -> scaffold -> assets -> templates -> components -> content.

## Step by step

| Step | Command | What you get |
|---|---|---|
| 1 | `/1-analyze https://example.com` | Component manifest, content data, HTML fragments |
| 2 | `/2-scaffold` | Scaffolded Jahia JS module in `projects/` |
| 3 | `/3-assets` | Static assets in `static/` folder |
| 4 | `/4-templates` | Layout.tsx + page template variants |
| 5 | `/5-components` | All CND + TSX + CSS + properties files |
| 6 | `/6-content` | Pages + content via GraphQL |

## Prerequisites

- Claude Code running in this directory
- Local Jahia instance at http://localhost:8080 (root/root)
- Node 18+, Yarn 4+, `expect` CLI tool

## Projects

Migrated sites are scaffolded under `projects/<module-name>/`.

## Skill map

See `.agents/README.md` for the full skill inventory and when to use each.
