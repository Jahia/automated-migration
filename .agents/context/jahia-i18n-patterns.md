# Context — Jahia i18n Patterns

i18n in Jahia splits across two concerns and two module types. The file locations and mechanisms differ depending on whether you are in a JS template set or an OSGi module.

**Rule: every new module ships EN and FR at minimum — no English-only strings.**

---

## JS Template Set (React 19, Vite)

There are two separate i18n systems in a template set. Both are required.

### 1. CND / Editor labels — `settings/resources/`

Labels shown in the **jcontent editor** (field names, node type names, choicelist options, view names, tooltips). These are Java ResourceBundle `.properties` files picked up by Jahia at deploy time.

**File location:**
```
settings/
└── resources/
    ├── <module-name>.properties         ← default (English fallback)
    ├── <module-name>_en.properties      ← explicit English
    └── <module-name>_fr.properties      ← French (minimum required)
```

> The default `.properties` file (no locale suffix) acts as the fallback. Always keep it in sync with `_en.properties`.

**Key naming conventions:**

| Pattern | Example | Purpose |
|---|---|---|
| `ns_typeName=Label` | `ailp_heroBanner=Hero Banner` | Node type display name |
| `nsmix_mixinName=Label` | `ailpmix_component=AI Landing Page Component` | Mixin display name |
| `ns_typeName.propertyName=Label` | `ailp_heroBanner.headline=Headline` | Field label |
| `ns_typeName.propertyName.ui.tooltip=Text` | `ailp_heroBanner.headline.ui.tooltip=Main hero title` | Editor tooltip |
| `ns_typeName.propertyName.choiceValue=Label` | `ailp_gridRow.columns.2=2 columns` | Choicelist option |
| `ns_typeName.viewName=Label` | `ailp_heroBanner.default=Default View` | View display name |

### `.ui.tooltip` — Mandatory for Every Property

**Every property definition MUST have a `.ui.tooltip` entry.** This is not optional. Tooltips appear as a `?` icon next to each field in jContent Editor — clicking it shows the tooltip content. They are the only in-editor guidance editors have at content-creation time.

**HTML is accepted** — use it for rich descriptions: bold terms, line breaks, constraint explanations, or links to brand guidelines.

```properties
# ─── Minimal tooltip (acceptable) ─────────────────────────────────────────────
ns_heroBanner.headline.ui.tooltip=Main title shown prominently across the hero section.

# ─── Rich tooltip with HTML (preferred) ───────────────────────────────────────
ns_heroBanner.headline.ui.tooltip=<b>Hero headline</b> — the primary H1 shown over the background image.<br/>\
  Max 80 characters. Use sentence case, no trailing period.

ns_heroBanner.backgroundImage.ui.tooltip=<b>Background image</b> — full-width, min 1920×1080px.<br/>\
  Use a high-contrast image so the headline text remains readable.<br/>\
  <i>Formats accepted: JPEG, WebP.</i>

ns_heroBanner.ctaLabel.ui.tooltip=<b>Call-to-action button label</b>.<br/>\
  Keep under 30 characters. Examples: <i>Book a visit</i>, <i>Learn more</i>.

# ─── Choicelist with tooltip explaining each option ───────────────────────────
ns_heroBanner.layout.ui.tooltip=<b>Layout variant</b>:<br/>\
  <b>left</b> — text on the left, image on the right.<br/>\
  <b>center</b> — text centered, image as full background.<br/>\
  <b>right</b> — text on the right, image on the left.

# ─── Boolean with tooltip explaining impact ───────────────────────────────────
ns_article.isFeatured.ui.tooltip=When checked, this article appears in the <b>Featured</b> carousel\
  on the homepage. Only 3 articles can be featured at a time.

# ─── Link to external documentation ──────────────────────────────────────────
ns_article.canonicalUrl.ui.tooltip=Override the canonical URL for SEO. Leave blank to use the page URL.\
  See <a href="https://wiki.example.com/seo-guidelines" target="_blank">SEO guidelines</a>.
```

> **Validation rule:** every `ns_type.property=Label` line must be followed (in any order) by a `ns_type.property.ui.tooltip=...` line. A missing tooltip is a review blocker.

**Full example:**

```properties
# ─── Node Types ───────────────────────────────────────────────────────────────
ailp_heroBanner=Hero Banner
ailpmix_component=AI Landing Page Component

# ─── HeroBanner properties ────────────────────────────────────────────────────
ailp_heroBanner.headline=Headline
ailp_heroBanner.headline.ui.tooltip=<b>Hero headline</b> — primary H1 displayed over the background image.<br/>\
  Max 80 characters. Use sentence case.
ailp_heroBanner.backgroundImage=Background Image
ailp_heroBanner.backgroundImage.ui.tooltip=<b>Background image</b> — full-width, min 1920×1080px.<br/>\
  Use a high-contrast image so the headline text remains readable.

# ─── Choicelist values ────────────────────────────────────────────────────────
ailp_gridRow.columns=Number of Columns
ailp_gridRow.columns.1=1 column
ailp_gridRow.columns.2=2 columns
ailp_gridRow.columns.3=3 columns
ailp_gridRow.columns.4=4 columns

# ─── Views ────────────────────────────────────────────────────────────────────
ailp_heroBanner.default=Default View

# ─── Default value pulled from resourceBundle ─────────────────────────────────
label.contactForm_feedbackMsg=<i>Dear <b>$name</b></i> <br/> Thank you for reaching out!
```

### `resourceBundle('key')` — Default Values from Properties

A CND property default can reference a properties key instead of a hardcoded string. Useful for richtext fields whose default content varies by locale.

```cnd
// CND
[ns:contactForm] > jnt:content, ns:componentMixin
 - feedbackMsg (string, richtext) = resourceBundle('label.contactForm_feedbackMsg') autocreated mandatory i18n
```

```properties
# ns-module.properties (EN)
label.contactForm_feedbackMsg=<i>Dear <b>$name</b></i> <br/> Thank you for reaching out!

# ns-module_fr.properties (FR)
label.contactForm_feedbackMsg=<i>Cher <b>$name</b></i> <br/> Merci de nous avoir contactés !
```

When Jahia creates the node, it reads the properties file for the editor's current locale and pre-fills the field. The `$name` syntax is a server-side placeholder (not i18next `{{name}}`).

### `choicelist[subnodetypes, resourceBundle]` — Combined Selector

When a choicelist is backed by JCR node types AND needs translated labels, combine both selectors:

```cnd
- type (string, choicelist[subnodetypes='jnt:page,ns:queryContent',resourceBundle]) mandatory
- criteria (string, choicelist[resourceBundle]) = 'jcr:created' autocreated < 'jcr:created','jcr:lastModified'
- sortDirection (string, choicelist[resourceBundle]) = 'asc' autocreated < 'asc','desc'
```

The `resourceBundle` selector then resolves labels from `.properties` for each value:

```properties
ns_queryContent.criteria=Sort by
ns_queryContent.criteria.jcr:created=Creation date
ns_queryContent.criteria.jcr:lastModified=Last modified
ns_queryContent.sortDirection=Direction
ns_queryContent.sortDirection.asc=Ascending
ns_queryContent.sortDirection.desc=Descending
```

---

### 2. Front-end UI labels — `settings/locales/`

Labels used inside **React components** — button text, section headings, form labels, alt text, error messages, anything that is not a CND editor label. These are JSON files auto-discovered by the `@jahia/vite-plugin` and served by the module at runtime via `react-i18next`.

**File location:**
```
settings/
└── locales/
    ├── en.json      ← English (minimum required)
    └── fr.json      ← French (minimum required)
```

**No manual registration is needed.** The `@jahia/vite-plugin` in `vite.config.js` picks up all files in `settings/locales/` automatically.

**Key structure — two equivalent formats:**

i18next accepts both **flat dot-notation** and **nested JSON**. Pick one style per project and stick to it.

```json
// ✅ Flat (used in the luxe-jahia-demo reference implementation)
{
  "section.heading.contact": "contact",
  "section.contact.address": "address",
  "section.contact.btn": "make an appointment",
  "alt.estate": "view of the real estate: {{estate}}",
  "pagination.showing": "Showing {{from}} to {{to}} of {{total}} results",
  "form.contact.sendMessageError": "Something went wrong. Status: {{status}}.",
  "footer.copyright": "© 2002-{{currentDate}} All Rights Reserved"
}

// ✅ Nested (equivalent — t("section.contact.btn") works identically)
{
  "section": {
    "heading": { "contact": "contact" },
    "contact": {
      "address": "address",
      "btn": "make an appointment"
    }
  }
}
```

**Interpolation syntax** — always `{{variableName}}` (double braces):

```tsx
t("alt.estate", { estate: title })                         // → "view of the real estate: Villa Riviera"
t("pagination.showing", { from: 1, to: 10, total: 42 })   // → "Showing 1 to 10 of 42 results"
t("footer.copyright", { currentDate: new Date().getFullYear() })
t("form.contact.sendMessageError", { name, status })
```

**Usage in views** (`useTranslation` from `react-i18next`):

```tsx
// Works in both .server.tsx and .client.tsx
import { useTranslation } from "react-i18next";

const { t } = useTranslation();

// Simple key
<button>{t("section.contact.btn")}</button>

// With interpolation
<img alt={t("alt.estate", { estate: title })} />

// In server view alongside JCR data — two separate concerns
const locale = currentResource.getLocale().getLanguage(); // for Number/Date formatting
<p>{price.toLocaleString(locale)}€</p>       // JS locale formatting
<span>{t("estate.bedrooms.label")}</span>    // UI label from locales/en.json
```

### HTML Translations

When a translated string contains HTML markup (links, bold, line breaks), use `dangerouslySetInnerHTML` — **never** render raw `t()` output as JSX:

```tsx
// ✅ HTML translation — the value in en.json contains <br/>, <b>, <i> tags
<p dangerouslySetInnerHTML={{
  __html: t("form.contact.sendMessageError", { name, status }),
}} />

// ❌ Wrong — JSX escapes HTML entities, tags appear as literal text
<p>{t("form.contact.sendMessageError", { name, status })}</p>
```

Mark HTML translation keys with a comment in the JSON so future editors know not to strip the markup:

```json
{
  "form.contact.sendMessageError": "Oops! Sorry, <b>{{name}}</b>.<br/> Status: {{status}}."
}
```

### `TFunction` Type — For Utility Functions Outside Components

When a non-component helper needs to format translated strings, accept `t` as a parameter typed with `TFunction`:

```tsx
import type { TFunction } from "i18next";

// Utility outside a component
function buildEstateRows(estate: EstateProps, t: TFunction) {
  return [
    { label: t("estate.type.label"),     value: t(`estate.type.${estate.type}`) },
    { label: t("estate.surface.label"),  value: `${estate.surface} m²` },
    { label: t("estate.bedrooms.label"), value: estate.bedrooms },
  ];
}

// In the component
const { t } = useTranslation();
const rows = buildEstateRows(estate, t);
```

### Locale in Islands — No Prop Needed

`useTranslation()` inside a client component (`.client.tsx`) **automatically** picks up the correct locale. The `@jahia/javascript-modules-library` initializes i18next with the current page language before hydration — you do not need to pass `locale` or `language` as a prop to Islands for translation purposes.

```tsx
// ✅ Server — pass only data props, never a "locale" prop for translations
return (
  <Island
    component={SearchEstateFormClient}
    props={{ params, onChange }}   // locale-for-t() is automatic
  />
);

// ✅ Client — useTranslation() works without receiving locale as a prop
export default function SearchEstateFormClient({ params, onChange }) {
  const { t } = useTranslation();  // correct locale injected by i18next context
  return <button>{t("form.estate.submit")}</button>;
}
```

The only case where you pass locale as a prop is for **JS `Intl`/`toLocaleString` formatting** (numbers, dates), not for translations:

```tsx
// Server
const locale = currentResource.getLocale().getLanguage();
<Island component={PriceClient} props={{ price, locale }} />

// Client
export default function PriceClient({ price, locale }: { price: number; locale: string }) {
  const { t } = useTranslation();                          // translations — automatic
  return <span>{price.toLocaleString(locale)}€</span>;     // formatting — needs locale prop
}
```

---

## OSGi Module (Java bundle or UI extension)

Only one i18n system — `.properties` files — used for both CND labels and UI extension labels.

**File location:**
```
src/main/resources/
└── resources/
    ├── <artifact-id>.properties         ← default (English fallback)
    ├── <artifact-id>_en.properties      ← explicit English
    └── <artifact-id>_fr.properties      ← French (minimum required)
```

> Note the path: `src/main/resources/resources/` — the double `resources/` is correct and required.

**Example (OSGi module with a UI extension):**

```properties
# efficy-ent-services.properties
efficy-ent-services.label=Efficy Enterprise service
efficy-ent-services.label.settings.title=Efficy Enterprise service settings
efficy-ent-services.label.action.title=Efficy Enterprise service
efficy-ent-services.label.appsAccordion.title=Efficy Enterprise service
```

**Loading in the UI extension JS** — must call `loadNamespaces` before registering anything:

```javascript
// registerExtensions.js (or index.js)
window.jahia.i18n.loadNamespaces('my-module-name');

window.jahia.uiExtender.registry.add('callback', 'my-module-init', {
    targets: ['jahiaApp-init:60'],
    callback: function () {
        registry.add('action', 'myAction', {
            buttonLabel: 'my-module-name:label.action.title',  // module:key
            targets: ['contentActions:50'],
            // ...
        });
    }
});
```

Labels in registry entries always use the `'module-name:key'` format — the module name as namespace, the property key as the path.

---

## Quick comparison

| | JS Template Set | OSGi Module |
|---|---|---|
| **CND / editor labels** | `settings/resources/<module>.properties` | `src/main/resources/resources/<artifact>.properties` |
| **Front-end UI labels** | `settings/locales/en.json`, `fr.json` | n/a — use `.properties` for everything |
| **React usage** | `useTranslation()` → `t("key")` | `'module:label.key'` in registry entries |
| **Loading** | Automatic (`@jahia/vite-plugin`) | `window.jahia.i18n.loadNamespaces('module')` |
| **Minimum locales** | EN + FR `.properties` + EN + FR `.json` | EN + FR `.properties` |

---

## Common pitfalls

| Pitfall | Consequence |
|---|---|
| Missing `_fr.properties` | French editors see raw property keys instead of labels |
| Using hardcoded strings in React views instead of `t()` | Untranslatable UI; breaks locale switching |
| Choicelist values without `.properties` entries | Raw values (`_self`, `Monday`) shown in editor instead of display labels |
| OSGi: missing `loadNamespaces` call | UI extension labels render as raw `module:key` strings |
| OSGi: wrong path (`src/main/resources/` instead of `src/main/resources/resources/`) | Properties file not found; all labels missing |
| JS template set: putting UI strings in `.properties` instead of `locales/*.json` | Labels work in the editor but `t()` calls return the key at runtime |
| Missing `.ui.tooltip` for any property | **Review blocker** — editors have zero guidance at content-creation time; no `?` icon appears |
| Tooltip is plain text when HTML would help | Missed opportunity — `<b>`, `<br/>`, `<a>` are all rendered; use them for constraints and examples |
