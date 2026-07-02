---
paths:
  - "**/*.cnd"
  - "**/jcr/**"
  - "**/definition.cnd"
  - "**/types.ts"
---

# JCR & Content Modeling Rules

Auto-loaded when touching `.cnd` files, `types.ts`, or JCR-related code. Full reference: `.agents/context/jahia-platform.md`.

## CND Non-Negotiables

- Always use an existing namespace declared in `settings/definitions.cnd`. Never invent a new prefix.
- Lead with mixins (`[namespace:myMixin] mixin`) before concrete types.
- Two-tier mixin system: shared mixins (reused across types) → concrete type (`[namespace:myType] > jmix:content, namespace:myMixin`).
- Contributor links: put `j:linkType (string, choicelist[linkTypeInitializer]) = 'none' autocreated indexed=no` **directly on the concrete type** (no linkTo mixin). `j:url` and `j:linknode` are injected at runtime by Jahia's built-in mixins (`jmix:externalLink` / `jmix:internalLink`) — **NEVER declare them in the CND.** Verified against all three deployed reference modules (an explicit comment in `supercar-garage/settings/definitions.cnd` states exactly this). This overrides migration.md rule 9's older "declare them explicitly" wording, which was never verified on a live instance and contradicts every working module. `cnd_emit.py` follows the reference convention.
- Restrict image weakreferences to image nodes: `- image (weakreference, picker[type='image']) < jmix:image`.
- **i18n fallback is a VIEW-level guard, not a CND default.** Do not set default values on `i18n` properties in the CND (a CND default pre-populates every locale with the same string). Instead every view guards: `prop?.value ?? ''` (see CLAUDE.md rule 5 — all props optional at runtime). `cnd_emit.py` emits no i18n defaults by design.
- Mandatory (`mandatory`) does not guarantee a non-null value at render time — always guard in the view.

## CND Property Types Quick Reference

| Type | Use for |
|---|---|
| `string` | Short text, URLs, identifiers |
| `string (textarea)` | Long text, HTML fragments |
| `weakreference` | Reference to another node (safe: null if target deleted) |
| `boolean` | Flags, toggles |
| `long` | Integers |
| `date` | Dates (stored as ISO 8601) |
| `string (richtext)` | Wysiwyg/rich text editor |

## types.ts Generation Rules

- Mirror every CND property as a typed field in the `Props` interface.
- Use `string | undefined` for optional string properties (never `null`).
- Use `boolean` for booleans; never `0 | 1`.
- Export the interface as a named export: `export interface <TypeName>Props { ... }`.
- Import from `@jahia/javascript-modules-library` only if using built-in helpers.

## JCR Session Rules (Java)

- `JCRSessionWrapper` is per-user, per-workspace, per-locale, and **not thread-safe**. Never store in a field.
- Obtain via `JCRTemplate.getInstance().doExecuteWithUserSession(...)`.
- Call `session.save()` explicitly after mutations. Never rely on auto-commit.
- Always publish after mutations: `JCRPublicationService.publishByMainId(uuid)`.
- Workspace: `default` for editing, `live` after publication.
