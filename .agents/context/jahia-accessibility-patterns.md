# Context — Jahia Accessibility Patterns

All public-facing views built with Jahia JS modules must meet **WCAG 2.1 Level AA**. The applicable Success Criteria include (non-exhaustive): 1.1.1 Non-text Content, 1.3.1 Info and Relationships, 1.3.2 Meaningful Sequence, 1.4.1 Use of Color, 1.4.3 Contrast (Minimum), 1.4.4 Resize Text, 1.4.10 Reflow, 1.4.11 Non-text Contrast, 2.1.1 Keyboard, 2.1.2 No Keyboard Trap, 2.4.1 Bypass Blocks, 2.4.3 Focus Order, 2.4.6 Headings and Labels, 2.4.7 Focus Visible, 3.1.1 Language of Page, 3.3.1 Error Identification, 3.3.2 Labels or Instructions, 4.1.2 Name, Role, Value.

---

## Semantic HTML and ARIA Roles

Use native HTML elements. ARIA roles are only for elements without a native HTML equivalent.

| Element | Correct use | ARIA equivalent (fallback only) |
|---|---|---|
| `<header>` | Site-wide header area, once per page | `role="banner"` |
| `<nav>` | Navigation landmark (can appear multiple times) | `role="navigation"` |
| `<main>` | Primary page content, once per page | `role="main"` |
| `<footer>` | Site-wide footer, once per page | `role="contentinfo"` |
| `<aside>` | Complementary content (sidebars, related links) | `role="complementary"` |
| `<article>` | Self-contained composition (blog post, news item, card) | — |
| `<section>` | Thematic grouping with a visible heading | — |

Multiple `<nav>` elements on the same page must have distinct `aria-label`:

```tsx
{/* ✅ Distinguishable navigation landmarks */}
<nav aria-label="Primary navigation">...</nav>
<nav aria-label="Footer navigation">...</nav>
<nav aria-label="Breadcrumb">...</nav>

{/* ❌ Screen reader lists two identical "navigation" landmarks */}
<nav>...</nav>
<nav>...</nav>
```

```
✅  <button type="button">Open menu</button>     ← native button, keyboard and screen reader built-in
✅  <a href="/about">About</a>                   ← native link, built-in semantics
❌  <div role="button" onClick={...}>Open menu</div>  ← requires tabIndex, keyboard handler, ARIA manually
❌  <span onClick={...}>About</span>             ← not focusable, not announced as a link
```

---

## Skip Link — Mandatory in Every Page Template

The skip link must be the first focusable element in the document. Without it, keyboard users must Tab through every nav item on every page to reach the main content.

```tsx
// In Layout.tsx — first child of <body>
<a href="#main-content" className={classes.skipLink}>
  Skip to main content
</a>
```

```css
/* layout.module.css */
.skipLink {
  position: absolute;
  left: -9999px;
  top: auto;
  width: 1px;
  height: 1px;
  overflow: hidden;
}

.skipLink:focus {
  position: fixed;
  left: 0;
  top: 0;
  width: auto;
  height: auto;
  overflow: visible;
  padding: 0.75rem 1.25rem;
  background: #000;
  color: #fff;
  font-weight: 700;
  z-index: 9999;
  text-decoration: none;
}
```

The target must exist:

```tsx
<main id="main-content" tabIndex={-1}>
  {children}
</main>
```

> `tabIndex={-1}` on `<main>` allows the browser to move focus to it programmatically when the skip link is activated, without adding it to the natural tab order.

---

## Heading Hierarchy

One `<h1>` per page — always the page title from `jcr:title` in the template. Components must never render `<h1>`.

```
✅  Template:   <h1>{pageTitle}</h1>
✅  Component:  <h2>Section title</h2>
✅  Component:  <h3>Card title within a section</h3>
❌  Component:  <h1>Hero headline</h1>   ← second h1
❌  Structure:  h1 → h3                  ← skipped h2
```

For components that can be placed at different nesting depths, expose a `headingLevel` prop:

```tsx
interface SectionProps {
  title?: string;
  headingLevel?: "h2" | "h3" | "h4";
}

function Section({ title, headingLevel: Heading = "h2", children }: SectionProps) {
  return (
    <section>
      {title && <Heading>{title}</Heading>}
      {children}
    </section>
  );
}
```

---

## Focus Indicators (Visible `:focus-visible`)

Never remove the focus ring without providing a replacement. Screen keyboard users and switch users depend on it.

```css
/* ❌ Breaks keyboard navigation */
:focus { outline: none; }
button:focus { outline: 0; }

/* ✅ Custom focus style — use :focus-visible to avoid showing ring on mouse click */
:focus-visible {
  outline: 2px solid currentColor;
  outline-offset: 2px;
}

/* ✅ For dark backgrounds — use a contrasting ring color */
.dark-bg :focus-visible {
  outline: 2px solid #ffffff;
  outline-offset: 2px;
}
```

Use `:focus-visible` (not `:focus`) so the ring appears only for keyboard navigation, not on mouse click.

---

## Color Contrast

| Text type | Minimum ratio |
|---|---|
| Normal text (< 18pt or < 14pt bold) | 4.5:1 |
| Large text (≥ 18pt or ≥ 14pt bold) | 3:1 |
| UI components and focus indicators | 3:1 against adjacent colors |

**Warning:** The example design token `--luxe-color-primary: #c29b40` (gold) has approximately 2.3:1 contrast against white — this **fails WCAG AA** for body text. Always verify brand colors before using them for text:

- Chrome DevTools: Inspect element → Accessibility tab
- [WebAIM Contrast Checker](https://webaim.org/resources/contrastchecker/)
- axe DevTools browser extension

Use gold for decorative accents and borders (UI component contrast: 3:1 is easier to achieve) but not as the primary text color on white backgrounds.

---

## Images — Informative vs Decorative

| Image type | Pattern |
|---|---|
| Informative (conveys meaning) | `alt="descriptive text"` — describe what the image shows, not "image of..." |
| Decorative (pure visual) | `alt="" aria-hidden="true"` — add a code comment `{/* decorative */}` |
| Functional (icon button) | `aria-label` on the `<button>`, `alt=""` on the `<img>` inside it |
| Complex (chart, infographic) | Short `alt` + longer description in adjacent text or `aria-describedby` |

```tsx
{/* ✅ Informative */}
<img src={hero.src} alt="Aerial view of the Bordeaux conference centre at sunset" width={1200} height={600} />

{/* ✅ Decorative */}
<img src={divider.src} alt="" aria-hidden="true" /> {/* decorative */}

{/* ✅ Functional icon button */}
<button type="button" aria-label="Close dialog">
  <img src="/icons/close.svg" alt="" aria-hidden="true" />
</button>

{/* ❌ jcr:title as alt — often a filename */}
<img src={node.src} alt={node["jcr:title"]} />  {/* alt="hero-photo-v3-FINAL.jpg" */}
```

### SVG Accessibility

```tsx
{/* ✅ Informative SVG */}
<svg aria-labelledby="chartTitle" role="img">
  <title id="chartTitle">Monthly registrations — Q1 2026</title>
  {/* chart paths */}
</svg>

{/* ✅ Decorative SVG */}
<svg aria-hidden="true" focusable="false">
  {/* icon paths */}
</svg>
```

---

## Keyboard Navigation

All interactive elements must be reachable via Tab and operable without a mouse.

### `tabindex` Rules

| Value | Meaning |
|---|---|
| `tabIndex={0}` | Add to natural tab order |
| `tabIndex={-1}` | Focusable via `element.focus()` only — not in tab order |
| `tabIndex > 0` | **Forbidden** — breaks the natural tab order for all users |

### Dropdown Keyboard Pattern

```
Enter / Space  → open dropdown
Arrow Down     → move to first/next item
Arrow Up       → move to previous item
Escape         → close dropdown, return focus to trigger
Home / End     → first / last item (optional, improves UX)
```

### Modal Focus Trap

When a modal opens, focus must be trapped inside it. When it closes, focus must return to the element that triggered it.

```tsx
// useFocusTrap.ts — or use a library like focus-trap-react
import { useEffect, useRef } from "react";

export function useFocusTrap(isOpen: boolean) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen || !containerRef.current) return;
    const focusable = containerRef.current.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), textarea, input, select, [tabindex="0"]',
    );
    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    first?.focus();

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key !== "Tab") return;
      if (e.shiftKey) {
        if (document.activeElement === first) { e.preventDefault(); last.focus(); }
      } else {
        if (document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen]);

  return containerRef;
}
```

Modal must also close on Escape:

```tsx
useEffect(() => {
  function onKeyDown(e: KeyboardEvent) {
    if (e.key === "Escape") onClose();
  }
  if (isOpen) document.addEventListener("keydown", onKeyDown);
  return () => document.removeEventListener("keydown", onKeyDown);
}, [isOpen, onClose]);
```

---

## ARIA Live Regions for Islands

When a client-side Island updates content dynamically (search results, cart count, filter output), screen readers do not notice the DOM change unless a live region is present.

```tsx
{/* ✅ Non-urgent update — search results, pagination */}
<div role="status" aria-live="polite" aria-atomic="true" className={classes.srOnly}>
  {announcement}
</div>

{/* ✅ Urgent message — form error, session expired */}
<div role="alert" aria-live="assertive" aria-atomic="true" className={classes.srOnly}>
  {errorMessage}
</div>
```

```css
/* Visually hidden but readable by screen readers */
.srOnly {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border-width: 0;
}
```

### Usage Pattern in a Search Island

```tsx
const [announcement, setAnnouncement] = useState("");

async function handleSearch(query: string) {
  const results = await fetchResults(query);
  setResults(results);
  // Announce result count — screen reader reads this even though it is visually hidden
  setAnnouncement(
    results.length === 0
      ? `No results found for "${query}"`
      : `${results.length} results found for "${query}"`,
  );
}

return (
  <>
    <div role="status" aria-live="polite" aria-atomic="true" className={classes.srOnly}>
      {announcement}
    </div>
    {/* result list */}
  </>
);
```

> Use `assertive` only for genuine urgent messages (authentication errors, session loss). Using `assertive` for routine updates interrupts the user mid-sentence.

---

## Form Accessibility

Every form control must have a visible, programmatically associated label.

```tsx
{/* ✅ Associated via htmlFor / id */}
<label htmlFor="email">Email address</label>
<input id="email" type="email" name="email" required aria-required="true" />

{/* ❌ placeholder is not a label — it disappears on input */}
<input type="email" placeholder="Email address" />

{/* ❌ aria-label with no visible label — acceptable only when truly impossible */}
<input type="search" aria-label="Search" />
```

### Required Fields

```tsx
<label htmlFor="fullName">
  Full name <span aria-hidden="true">*</span>
</label>
<input
  id="fullName"
  type="text"
  required
  aria-required="true"
/>
<p className={classes.hint}>* Required field</p>
```

### Error Messages

```tsx
<label htmlFor="phone">Phone number</label>
<input
  id="phone"
  type="tel"
  aria-describedby="phone-error"
  aria-invalid={hasError ? "true" : "false"}
/>
{hasError && (
  <p id="phone-error" role="alert">
    Please enter a valid phone number (e.g., +33 6 12 34 56 78).
  </p>
)}
```

### Group Related Fields

```tsx
{/* ✅ Radio group */}
<fieldset>
  <legend>Preferred contact method</legend>
  <label><input type="radio" name="contact" value="email" /> Email</label>
  <label><input type="radio" name="contact" value="phone" /> Phone</label>
</fieldset>

{/* ✅ Checkbox group */}
<fieldset>
  <legend>Topics of interest</legend>
  <label><input type="checkbox" name="topics" value="events" /> Events</label>
  <label><input type="checkbox" name="topics" value="news" /> News</label>
</fieldset>
```

---

## Link Text Quality

Screen reader users often navigate by listing all links on the page. Ambiguous link text ("click here", "read more") provides no context when read out of context.

```tsx
{/* ❌ Meaningless out of context */}
<a href={url}>Read more</a>
<a href={url}>Click here</a>

{/* ✅ Descriptive — self-contained */}
<a href={url}>Read more about our advisory services</a>

{/* ✅ aria-label when visual design must stay short */}
<a href={url} aria-label={`Learn more about ${title}`}>Learn more</a>
```

### Links vs Buttons

```
<a href="...">   → navigates to a URL (changes location)
<button>         → triggers an action (submits form, opens modal, toggles state)
```

Never use an `<a>` without an `href` as a button, and never style a `<button>` as a link to trigger navigation.

### Icon-Only Buttons

```tsx
{/* ✅ aria-label provides the accessible name */}
<button type="button" aria-label="Share this article">
  <ShareIcon aria-hidden="true" />
</button>

{/* ❌ No accessible name — screen reader reads nothing or the SVG path data */}
<button type="button">
  <ShareIcon />
</button>
```

---

## Motion and Animation

Wrap all transitions and animations to respect the user's motion preference. Users with vestibular disorders can be harmed by motion.

```css
/* ✅ Define motion token with reduced-motion fallback */
:root {
  --ns-transition-standard: 0.2s ease;
}

@media (prefers-reduced-motion: reduce) {
  :root {
    --ns-transition-standard: 0ms;
  }
}

/* Use the token everywhere */
.card {
  transition: box-shadow var(--ns-transition-standard, 0.2s ease);
}

/* ✅ Wrap explicit animations */
@media (prefers-reduced-motion: no-preference) {
  .fadeIn {
    animation: fadeIn 0.4s ease forwards;
  }
}
```

For JavaScript-driven animations (e.g., scroll-triggered, GSAP):

```ts
const prefersReducedMotion = window.matchMedia(
  "(prefers-reduced-motion: reduce)",
).matches;

if (!prefersReducedMotion) {
  // start animation
}
```

---

## Testing Checklist

- [ ] **axe DevTools** (browser extension, free) — zero critical violations
- [ ] **Lighthouse Accessibility** score ≥ 90
- [ ] **Keyboard-only** — Tab, Shift+Tab, Enter, Space, Escape, Arrow keys navigate all interactive elements without a mouse
- [ ] **Skip link** visible on first Tab press, activates correctly
- [ ] **Focus indicator** visible on every interactive element during keyboard navigation
- [ ] **Screen reader** — VoiceOver + Safari (macOS) or NVDA + Firefox (Windows) — all content is announced correctly
- [ ] **Color contrast** — all text and UI component colors verified with [WebAIM Contrast Checker](https://webaim.org/resources/contrastchecker/)
- [ ] **Zoom to 200%** — no content is lost or overlapping (SC 1.4.4)
- [ ] **Live regions** present on all Islands that update content dynamically

---

## Non-Negotiables

| Rule | Why |
|---|---|
| Skip link as first focusable element in every template | SC 2.4.1 Bypass Blocks — keyboard users must skip repetitive nav |
| One `<h1>` per page — always the page title from the template | SC 1.3.1 — logical heading structure for AT navigation |
| Never `outline: none` without a replacement focus style | SC 2.4.7 Focus Visible — keyboard users lose their position |
| All `<img>` with `alt` — empty string for decorative, descriptive for informative | SC 1.1.1 Non-text Content |
| Never use `jcr:title` as default `alt` without editorial review | Often a filename, not a useful description |
| Every `<input>` must have a `<label>` — not just `placeholder` | SC 3.3.2 Labels — placeholder disappears on input |
| Error messages associated via `aria-describedby` + `aria-invalid` | SC 3.3.1 Error Identification |
| Focus trap in modals; Escape closes and returns focus | SC 2.1.2 No Keyboard Trap + 2.1.1 Keyboard |
| ARIA live regions on Islands that update content dynamically | SC 4.1.3 Status Messages — updates invisible to screen readers otherwise |
| Wrap all CSS transitions in `prefers-reduced-motion` | SC 2.3.3 — motion can trigger vestibular disorders |
