---
name: 2-scaffold-module
description: Scaffold a new Jahia JavaScript module using npm init @jahia/module@latest. Use at the start of every migration to create the project structure.
type: production
phase: 2
status: active
depends_on:
  - 3-import-assets
allowed-tools: Bash, Read, Write, Edit
---

# Skill: Scaffold Module

Creates the Jahia JS module project structure. Invoked by `/2-scaffold`.

---

## Agent identity
- **Agent name:** Scaffoldus
- **Reference style:** Construction / architecture
- **Signature line (en):** *"The structure before the structure."*
- **Personality note:** Precise and decisive. Picks sensible defaults, confirms namespace with the user before touching any CND.
- **Usage rule:** Brief invocation only in orchestrator narration. Never appears in deliverables.

---

## Scaffolding command

The tool uses `@clack/prompts` (TTY required). Use `expect` to drive it non-interactively:

```bash
mkdir -p projects/
cd projects/

expect -c "
  spawn npm init @jahia/module@latest <module-name>
  expect \"name of your module\"
  send \"\r\"
  expect \"Where do you want\"
  send \"\r\"
  expect \"module type\"
  send \"\x1B\[B\r\"
  expect eof
"
```

`\x1B\[B` = down-arrow key = select "Empty template set" (option 2, recommended for migrations).

**Fallback if `expect` missing:**
```bash
which expect || echo "not found"
```
If not found, ask user to run interactively:
```
Run in your terminal:
  cd projects/ && npm init @jahia/module@latest <module-name>
Press Enter for name, Enter for path, select "Empty template set", Enter.
```

---

## Verify generated structure

```
projects/<module-name>/
├── src/
│   └── components/
├── settings/
│   ├── definitions.cnd
│   ├── resources/
│   └── locales/
├── docker/
│   └── provisioning.yml
├── package.json
├── vite.config.ts
└── docker-compose.yml
```

---

## Install dependencies

```bash
cd projects/<module-name>
yarn install
```

---

## Configure environment

```bash
cat > .env << 'EOF'
JAHIA_USER=root:root
JAHIA_HOST=http://localhost:8080
EOF
```

---

## Add shared CND foundations

Before implementing any components, add these to `settings/definitions.cnd`:

```cnd
// Replace <ns> with the actual namespace prefix (e.g. carnival, bjhome, mysite)

// Base component mixin — all components extend this
[<ns>Mix:component] > jmix:droppableContent, jmix:accessControllableContent mixin

// Page component mixin — for components that go into page Areas
[<ns>Mix:pageComponent] > <ns>Mix:component mixin

// Link mixin — MUST declare j:url and j:linknode explicitly
// linkTypeInitializer is UI-only; it does not inject these at runtime
[<ns>:linkTo] mixin
 - j:linkType (string, choicelist[linkTypeInitializer]) = 'none' autocreated indexed=no
 - j:url (string) indexed=no
 - j:linknode (weakreference) < jmix:mainResource, jnt:page

// CTA button — child node via + * (<ns>:ctaButton)
[<ns>:ctaButton] > jnt:content, <ns>Mix:component, <ns>:linkTo
 - ctaLabel (string) i18n

// Site theme mixin — add to the site node (jnt:virtualsite) so editors can
// re-theme the whole site by overriding the :root tokens (see skills 03 + 08).
// Property values feed the inline :root{} override emitted by Layout.tsx; the
// weakreference points to an uploaded stylesheet linked LAST to win the cascade.
[<ns>Mix:siteTheme] mixin
 - themePrimaryColor (string)
 - themeSecondaryColor (string)
 - themeAccentColor (string)
 - themeTextColor (string)
 - themeBackgroundColor (string)
 - themeFontHeading (string)
 - themeFontBody (string)
 - themeOverrideCss (weakreference, picker[type='file'])
```

> CSS is tokenized into `:root` variables at import time (skill 03 — `tokenize-css.py`), and `Layout.tsx` wires both override paths (skill 08). The `<ns>Mix:siteTheme` mixin above is what surfaces the theme fields on the site node; add it to `/sites/<siteKey>` once the site exists.

---

## Validation checklist
- [ ] Module scaffolded at `projects/<module-name>/`
- [ ] `yarn install` completed without errors
- [ ] `.env` file created with correct credentials
- [ ] `settings/definitions.cnd` has module mixin, pageComponent mixin, linkTo mixin, ctaButton type, **siteTheme mixin**
- [ ] Namespace prefix recorded (needed for all subsequent CND and resource bundle work)
- [ ] Namespace prefix recorded (needed for all subsequent CND and resource bundle work)
