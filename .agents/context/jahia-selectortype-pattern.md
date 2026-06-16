# Context — Jahia SelectorType Pattern (Content Editor Override)

The SelectorType pattern lets you replace the default editor widget for any CND property with a custom or built-in React component — without touching the CND definition. It is the standard extension point for content editor UI in Jahia's back-office (jcontent).

Sources:
- jContent registry API: `/Users/stephane/Runtimes/0.Modules/jcontent/src/javascript/ContentEditor/SelectorTypes/`
- Real-world JSON overrides: `/Users/stephane/Runtimes/0.Modules/js-store-locator/settings/content-editor-forms/fieldsets/`

---

## Critical: two separate modules

**A JS template set (React 19, Vite) and a custom SelectorType component (React 18, Webpack) can never live in the same module.**

| What | Where |
|---|---|
| `settings/content-editor-forms/fieldsets/*.json` | **JS template set** — static JSON, no React code |
| `registry.add('selectorType', ...)` + React component | **Separate OSGi UI extension** (React 18, Webpack) |

The JSON override just names a key. jContent resolves that key against the registry at runtime. The component that registered itself under that key can come from any deployed UI extension module.

If you only need built-in selectors (Choicelist, RadioChoiceList, DatePicker, etc.), the JSON file alone is sufficient — no UI extension needed. A custom SelectorType (a React component you write) always requires a dedicated OSGi UI extension module.

---

## How it works — the full flow

```
CND property definition
    ↓
JSON fieldset override  (in the JS template set)
    settings/content-editor-forms/fieldsets/<ns>_<type>.json
    ↓  "selectorType": "SomeKey"
jContent resolves key → registry.get('selectorType', 'SomeKey')
    ↓
Built-in selectorType     ← no extra module needed
  OR
Custom selectorType       ← registered by a separate OSGi UI extension (React 18)
    ↓
React component renders inside jcontent editor
    ↓
onChange → Formik → GraphQL save → JCR
```

---

## Part A — JSON fieldset override (JS template set)

This file lives in the **JS template set module** and works for both built-in and custom selectors.

**File location:**
```
settings/content-editor-forms/fieldsets/<cnd-namespace>_<typeName>.json
```

> The filename separator is `_` not `:` — `jsstorelocnt_store.json`, not `jsstorelocnt:store.json`.

### Example — overriding with a built-in Choicelist

`jsstorelocnt_openingHour.json` — replaces a plain `string` property with a time dropdown, no UI extension needed:

```json
{
    "name": "jsstorelocnt:openingHour",
    "description": "",
    "dynamic": false,
    "fields": [
        {
            "name": "dayOfWeek",
            "selectorType": "Choicelist",
            "valueConstraints": [
                { "value": { "type": "String", "value": "Monday" },    "displayValue": "Monday" },
                { "value": { "type": "String", "value": "Tuesday" },   "displayValue": "Tuesday" },
                { "value": { "type": "String", "value": "Wednesday" }, "displayValue": "Wednesday" },
                { "value": { "type": "String", "value": "Thursday" },  "displayValue": "Thursday" },
                { "value": { "type": "String", "value": "Friday" },    "displayValue": "Friday" },
                { "value": { "type": "String", "value": "Saturday" },  "displayValue": "Saturday" },
                { "value": { "type": "String", "value": "Sunday" },    "displayValue": "Sunday" }
            ]
        },
        {
            "name": "opens",
            "selectorType": "Choicelist",
            "valueConstraints": [
                { "value": { "type": "String", "value": "08:00" }, "displayValue": "08:00" },
                { "value": { "type": "String", "value": "08:30" }, "displayValue": "08:30" },
                { "value": { "type": "String", "value": "09:00" }, "displayValue": "09:00" }
            ]
        },
        {
            "name": "closes",
            "selectorType": "Choicelist",
            "valueConstraints": [
                { "value": { "type": "String", "value": "17:00" }, "displayValue": "17:00" },
                { "value": { "type": "String", "value": "17:30" }, "displayValue": "17:30" },
                { "value": { "type": "String", "value": "18:00" }, "displayValue": "18:00" }
            ]
        }
    ]
}
```

### Example — mixing built-in and custom selectors

`jsstorelocnt_store.json` — `priceRange` uses a built-in Choicelist; `openingHours` references a custom SelectorType registered by a separate UI extension module:

```json
{
    "name": "jsstorelocnt:store",
    "description": "Store content editor form",
    "dynamic": false,
    "fields": [
        {
            "name": "priceRange",
            "selectorType": "Choicelist",
            "selectorOptionsMap": { "allowCustomEntry": "false" },
            "valueConstraints": [
                { "displayValue": "$",    "value": { "type": "String", "value": "$" } },
                { "displayValue": "$$",   "value": { "type": "String", "value": "$$" } },
                { "displayValue": "$$$",  "value": { "type": "String", "value": "$$$" } },
                { "displayValue": "$$$$", "value": { "type": "String", "value": "$$$$" } }
            ]
        },
        {
            "name": "openingHours",
            "selectorType": "OpeningHoursSelector"
        }
    ]
}
```

`"OpeningHoursSelector"` is registered by the companion OSGi UI extension. The template set JSON just names the key — it has no dependency on the UI extension at build time.

### JSON fieldset fields reference

| Field | Purpose |
|---|---|
| `name` (root) | CND node type, fully qualified (`namespace:typeName`) |
| `fields[].name` | CND property name to override |
| `fields[].selectorType` | Key of the built-in or custom selector |
| `fields[].valueConstraints` | Override or extend choice list values |
| `fields[].selectorOptionsMap` | Options passed to the component as `field.selectorOptions` |
| `fields[].hidden` | `true` to hide the property from the editor entirely |
| `fields[].readOnly` | `true` to lock the property |
| `"dynamic": false` | Always `false` for static overrides |

---

## Part B — Custom SelectorType component (separate OSGi UI extension)

Only needed when built-in selectors are not sufficient. This is a **separate module** from the JS template set — React 18, Webpack, `@jahia/ui-extender`.

### Registration (`init.js` in the UI extension)

```javascript
// src/javascript/init.js
import { registry } from '@jahia/ui-extender';
import { OpeningHoursSelector } from './components/OpeningHoursSelector';

export default function () {
    registry.add('callback', 'register-opening-hours', {
        targets: ['jahiaApp-init:20'],
        callback: () => {
            registry.add('selectorType', 'OpeningHoursSelector', {
                cmp: OpeningHoursSelector,   // React 18 component
                dataType: ['String'],
                supportMultiple: false,

                // Transform JCR string → component value on load (property exists)
                adaptValue: (field, property) => {
                    try { return JSON.parse(property.value); }
                    catch { return {}; }
                },

                // Default when property doesn't exist yet (new content)
                initValue: () => ({ dayOfWeek: 'Monday', opens: '09:00', closes: '17:00' }),
            });
        },
    });
}
```

### Full registration options

```javascript
registry.add('selectorType', 'MyKey', {
    cmp: MyReactComponent,              // required

    dataType: ['String'],               // JCR property types this handles

    adaptValue: (field, property) => {  // transform JCR value → component value
        return field.multiple ? property.values : property.value;
    },

    initValue: (field) => {             // default for new (empty) property
        return field.mandatory ? '' : undefined;
    },

    supportMultiple: false,

    labelKey: 'my-module:label.mySelector',
    properties: [
        { name: 'description', value: 'my-module:label.mySelector.description' },
        { name: 'iconStart', value: 'Edit' },
    ],
});
```

### Component contract

```tsx
interface SelectorProps {
    field: {
        name: string;
        readOnly?: boolean;
        mandatory?: boolean;
        multiple?: boolean;
        selectorOptions?: Array<{ name: string; value: string }>;
    };
    id: string;           // attach to root element for accessibility
    value: any;           // output of adaptValue, or raw JCR value if no adaptValue
    onChange: (v) => void; // write path — call with new value, never write JCR directly
    onBlur?: () => void;
}
```

The component renders inside jcontent (React 18). `onChange(newValue)` is the only write path — Formik stores it, the content editor persists it to JCR on save.

**For JSON-encoded values**: `adaptValue` parses the JCR string; `onChange` calls `JSON.stringify(newValue)`.

---

## Built-in selectorType keys (use in JSON, no UI extension needed)

| Key | Default for CND type | Notes |
|---|---|---|
| `Text` | `string` | Single-line; add `selectorOptionsMap: {password: ""}` for password |
| `TextArea` | `string, textarea` | Multi-line |
| `RichText` | `string, richtext` | CKEditor |
| `Checkbox` | `boolean` | Single checkbox |
| `Choicelist` | `string, choicelist` | Dropdown |
| `CheckboxChoiceList` | `string, choicelist` (multiple) | Multi-select checkboxes |
| `RadioChoiceList` | override via JSON | Radio group |
| `DateTimePicker` | `date` | Date + time |
| `DatePicker` | `date` | Date only |
| `Picker` | `weakreference, picker[...]` | Content/image/file picker |
| `Tag` | `string, tag` | Tag input |

---

## Correct module layout for a project needing a custom SelectorType

```
my-site/                         ← JS template set (React 19, Vite)
├── src/components/...
├── settings/
│   └── content-editor-forms/
│       └── fieldsets/
│           └── ns_myType.json   ← references "MyCustomSelector" key
└── package.json                 ← react: 19, @jahia/javascript-modules-library

my-site-ui/                      ← OSGi UI extension (React 18, Webpack) — SEPARATE MODULE
├── src/javascript/
│   ├── index.js                 ← jahiaApp-init callback
│   └── components/
│       └── MyCustomSelector.jsx ← registry.add('selectorType', 'MyCustomSelector', ...)
└── pom.xml                      ← maven bundle, @jahia/ui-extender, react: 18
```

Both modules are deployed to Jahia independently. The template set JSON references `"MyCustomSelector"` — jContent resolves it from the registry at runtime regardless of which module registered it.

---

## Common pitfalls

| Pitfall | Consequence |
|---|---|
| Putting `registry.add('selectorType', ...)` in the JS template set | Build failure or runtime error — Webpack/MF not configured; React 18/19 conflict |
| Key mismatch between JSON and `registry.add` | Editor falls back to default widget silently |
| Filename `ns:type.json` instead of `ns_type.json` | File not picked up by jContent |
| Not attaching `id` prop to root element | Accessibility and focus management broken |
| Calling JCR directly instead of `onChange` | Value lost on save; bypasses Formik validation |
| Missing `adaptValue` for non-string JCR types | Component receives raw string `'true'`/`'false'` instead of boolean |

---

## References

- jContent SelectorType registry: `/Users/stephane/Runtimes/0.Modules/jcontent/src/javascript/ContentEditor/SelectorTypes/`
- Real JSON overrides: `/Users/stephane/Runtimes/0.Modules/js-store-locator/settings/content-editor-forms/fieldsets/`
- OSGi UI extension pattern: [`.agents/skills/jahia-osgi-ui-extension/SKILL.md`](../skills/jahia-osgi-ui-extension/SKILL.md)
