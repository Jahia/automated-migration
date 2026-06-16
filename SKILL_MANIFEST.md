# SKILL_MANIFEST.md — jahiaMigration

Full inventory of all skills in this harness. One row per skill.

Last updated: 2026-06-16

---

## Migration workflow (sequential steps 01-11)

| Folder | Name | Type | Phase | Status | Agent | Invokes workflow |
|--------|------|------|-------|--------|-------|-----------------|
| `01-analyze-website/` | Analyze Website | workflow | 1 | active | Archaeon | yes |
| `02-scaffold-module/` | Scaffold Module | production | 2 | active | Scaffoldus | no |
| `03-import-assets/` | Import Assets | technical | 3 | active | Assetron | no |
| `04-define-content-types/` | Define Content Types | production | 4 | active | Typecraft | no |
| `05-implement-navigation/` | Implement Navigation | production | 5 | active | Navitar | no |
| `06-implement-jcr-query/` | Implement JCR Query | production | 6 | active | Queryon | no |
| `07-implement-components/` | Implement Components | workflow | 7 | active | Parallex | yes |
| `08-page-templates/` | Page Templates | production | 8 | active | Templeron | no |
| `09-create-content/` | Create Content | content | 9 | active | Datacraft | no |
| `10-review/` | Code Review | review | 10 | active | Auditor Rex | no |
| `11-debug/` | Debug | technical | 11 | active | Diagnost | no |

---

## Support skills

| Folder | Name | Type | Phase | Status |
|--------|------|------|-------|--------|
| `support-create-view/` | Create View | production | support | active |
| `support-deploy/` | Deploy Module | technical | support | active |

---

## JS/React development skills (`dev/`)

| Folder | Name | Type | Status |
|--------|------|------|--------|
| `dev/jahia/` | Jahia GPS | workflow | active |
| `dev/jahia-dev/` | JS Module GPS | workflow | active |
| `dev/jahia-dev-build-component/` | Build Component | production | active |
| `dev/jahia-dev-create-template-set/` | Create Template Set | production | active |
| `dev/jahia-dev-create-view/` | Create View | production | active |
| `dev/jahia-dev-define-content-type/` | Define Content Type | production | active |
| `dev/jahia-dev-import-from/` | Import From URL | production | active |
| `dev/jahia-dev-query-content/` | Query Content | technical | active |
| `dev/jahia-dev-accessibility/` | Accessibility Audit | review | active |
| `dev/jahia-dev-screenshot/` | Screenshot Compare | review | active |
| `dev/jahia-dev-start-local/` | Start Local | technical | active |
| `dev/jahia-dev-cypress/` | Cypress Tests | technical | active |
| `dev/jahia-dev-java/` | Java Actions | technical | active |
| `dev/jahia-dev-properties/` | JCR Properties | reference | active |
| `dev/jahia-dev-apis/` | REST & GraphQL APIs | reference | active |
| `dev/jahia-dev-jexperience/` | jExperience | technical | active |
| `dev/jahia-dev-ops/` | Operations | technical | active |
| `dev/jahia-dev-ui-extension/` | OSGi UI Extension | technical | active |

---

## OSGi/Java skills (`osgi/`)

| Folder | Name | Type | Status |
|--------|------|------|--------|
| `osgi/jahia-osgi-module/` | OSGi Module | technical | active |
| `osgi/jahia-osgi-ui-extension/` | OSGi UI Extension | technical | active |
| `osgi/jahia-dev-osgi-module/` | OSGi Dev Conventions | technical | active |

---

## Content management skills (`content/`)

| Folder | Name | Type | Status |
|--------|------|------|--------|
| `content/jahia-content/` | Content GPS | workflow | active |
| `content/jahia-content-explore-structure/` | Explore Structure | technical | active |
| `content/jahia-content-query-content/` | Query Content | technical | active |
| `content/jahia-content-move-content/` | Move Content | technical | active |
| `content/jahia-content-translate-content/` | Translate Content | content | active |

---

## Governance

- `_references/migration-quality-bar.md` — what "done" means for every migration task
- `_references/human-validation-gates.md` — 5 gates where the agent stops for human review
- `_references/skill-creation-governance.md` — rules for adding, modifying, or deprecating skills
