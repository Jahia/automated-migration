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
- No `j:linknode` or `j:url` hardcoded — use `weakreference` or `string (uri)` instead.
- Every `i18n` property must have a default value fallback.
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
