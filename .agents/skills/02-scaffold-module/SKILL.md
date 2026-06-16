---
name: 2-scaffold-module
description: Scaffold a new Jahia JavaScript module using npm init @jahia/module@latest. Use at the start of every migration to create the project structure.
allowed-tools: Bash, Read, Write, Edit
---

# Skill: Scaffold Module

Creates the Jahia JS module project structure. Invoked by `/2-scaffold`.

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
```

---

## Validation checklist
- [ ] Module scaffolded at `projects/<module-name>/`
- [ ] `yarn install` completed without errors
- [ ] `.env` file created with correct credentials
- [ ] `settings/definitions.cnd` has module mixin, pageComponent mixin, linkTo mixin, ctaButton type
- [ ] Namespace prefix recorded (needed for all subsequent CND and resource bundle work)
