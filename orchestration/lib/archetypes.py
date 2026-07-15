#!/usr/bin/env python3
"""archetypes.py — the bounded semantic archetype library (redesign §10).

The authoring-model foundation. Instead of minting one skeleton nodeType per
segmented region (the 40-type explosion), the migration classifies each region
to ONE of these ~15 archetypes and emits a clean, semantic Jahia type that
COMPOSES reusable mixins (cta / media / seo) — grounded in two production
template sets (`luxe-jahia-demo`, `soprahr/mysoprahr`).

Consumers:
  * segment2manifest.py — maps a region's archetype label -> to_manifest_component()
  * cnd_emit.py         — emits base_mixin_cnd() + shared_mixin_cnd() once, then a
                          type per component composing its mixins (never re-declaring
                          mixin-provided fields), plus childType for containers
  * gen_bundles.py      — emits the resource-bundle labels via archetype_labels()

Field/type conventions (both reference modules agree — see redesign §10.3):
  - titles      -> mix:title (never declare jcr:title)
  - images      -> (weakreference, picker[type='image']) < jmix:image  + imageAlt i18n
                   [provided by nsmix:media]
  - links       -> j:linkType (string, choicelist[linkTypeInitializer]) + ctaLabel i18n
                   [provided by nsmix:cta; j:linknode/j:url injected at runtime]
  - rich text   -> (string, richtext) i18n
  - taxonomy    -> jmix:categorized + jmix:tagged (never custom fields)
  - mainResource-> jmix:mainResource stack; ships default/compact/cm/featured/fullPage
"""
from __future__ import annotations


# ── field helper ──────────────────────────────────────────────────────────
def f(name, typ, i18n=False, mandatory=False):
    return {"name": name, "type": typ, "i18n": i18n, "mandatory": mandatory}


RICHTEXT = "string, richtext"
TEXTAREA = "string, textarea"


# ── reusable mixins (emitted once; archetypes compose them) ─────────────────
# Each entry: local mixin name -> {supertypes, fields}. `label` fields carry the
# resource-bundle text. j:linknode/j:url are NEVER declared (linkTypeInitializer).
SHARED_MIXINS = {
    "cta": {
        "fields": [
            f("ctaType", "string, choicelist[linkTypeInitializer]"),   # = 'none' autocreated (emitted by cnd)
            f("ctaLabel", "string", i18n=True),
        ],
        "labels": {
            "": "Call to Action",
            "ctaType": "Link",
            "ctaType.ui.tooltip": "Where the button links: an internal page, an external URL, or none.",
            "ctaLabel": "Button Label",
            "ctaLabel.ui.tooltip": "Text on the button. Leave blank to use the target page title.",
        },
    },
    "media": {
        # No imageAlt field: the DAM image node's own jcr:title IS the alt text
        # (check-cnd redundantImageAlt rule) — the view reads
        # image.getPropertyAsString("jcr:title") for alt.
        "fields": [
            f("image", "weakreference, picker[type='image']"),          # < jmix:image (emitted by cnd)
        ],
        "labels": {
            "": "Image",
            "image": "Image",
            "image.ui.tooltip": "Image selected from the media library (DAM); its title is used as alt text.",
        },
    },
    "seo": {
        "fields": [
            f("metaTitle", "string", i18n=True),
            f("metaDescription", TEXTAREA, i18n=True),
            f("ogImage", "weakreference, picker[type='image']"),        # < jmix:image
        ],
        "labels": {
            "": "SEO",
            "metaTitle": "Meta Title",
            "metaTitle.ui.tooltip": "Title shown in search results and browser tabs.",
            "metaDescription": "Meta Description",
            "metaDescription.ui.tooltip": "Summary shown under the title in search results.",
            "ogImage": "Social Share Image",
            "ogImage.ui.tooltip": "Image used when the page is shared on social media.",
        },
    },
}


# ── the archetype catalog ───────────────────────────────────────────────────
# Each archetype: display name, the reusable mixins it composes, whether it uses
# mix:title, its OWN semantic fields (mixin-provided fields are NOT repeated), an
# optional layout choicelist (per-instance variation — NOT a new type), an optional
# typed childType (containers), view names, and mainResource flag.
def _card_child():
    return {"key": "card", "name": "Card", "title": True,
            "mixins": ["media", "cta"], "fields": [f("text", RICHTEXT, i18n=True)]}


ARCHETYPES = {
    # ── content ──────────────────────────────────────────────────────────
    "hero": {"name": "Hero", "title": True, "mixins": ["media", "cta"],
             "fields": [f("subtitle", RICHTEXT, i18n=True)],
             "views": ["default", "textUp", "textDown"]},
    "mediaText": {"name": "Media & Text", "title": True, "mixins": ["media", "cta"],
                  "fields": [f("text", RICHTEXT, i18n=True)],
                  "layout": {"name": "layout", "default": "imageRight", "values": ["imageRight", "imageLeft"]},
                  "views": ["default"]},
    "teaserCard": {"name": "Teaser Card", "title": True, "mixins": ["media", "cta"],
                   "fields": [f("text", RICHTEXT, i18n=True)],
                   "views": ["default", "compact"]},
    "banner": {"name": "Banner", "title": True, "mixins": ["media", "cta"],
               "fields": [f("text", RICHTEXT, i18n=True)],
               "views": ["default"]},
    "statCallout": {"name": "Stat Callout", "title": False, "mixins": [],
                    "fields": [f("value", "string", i18n=True), f("unit", "string", i18n=True),
                               f("statLabel", "string", i18n=True),
                               f("trend", "string, choicelist[resourceBundle]")],
                    "views": ["default"]},
    "richTextSection": {"name": "Rich Text Section", "title": True, "mixins": [],
                        "fields": [f("body", RICHTEXT, i18n=True)],
                        "views": ["default"]},
    # ── containers (typed children) ──────────────────────────────────────
    "cardGrid": {"name": "Card Grid", "title": True, "mixins": [], "list": True,
                 "layout": {"name": "layout", "default": "grid", "values": ["grid", "carousel", "slider"]},
                 "child": _card_child(), "fields": [],
                 "views": ["default", "carousel"]},
    "accordion": {"name": "Accordion", "title": True, "mixins": [], "list": True,
                  "child": {"key": "accordionItem", "name": "Accordion Item", "title": True,
                            "mixins": [], "fields": [f("body", RICHTEXT, i18n=True)]},
                  "fields": [], "views": ["default"]},
    # ── layout ────────────────────────────────────────────────────────────
    "section": {"name": "Layout Section", "node": "layoutSection", "title": True,
                "mixins": [], "layoutType": True,
                "contentList": True, "fields": [],
                "layout": {"name": "arrangement", "default": "stack", "values": ["stack", "row"]},
                "views": ["default"]},
    "cols": {"name": "Columns", "title": True, "mixins": [], "layoutType": True,
             "fields": [f("colsNumber", "string, choicelist[resourceBundle]")],
             "views": ["default"]},
    "jcrQuery": {"name": "Content List", "title": True, "mixins": [], "list": True, "cache": True,
                 "fields": [f("type", "string, choicelist[subnodetypes,resourceBundle]"),
                            f("startNode", "weakreference"),
                            f("maxItems", "long"),
                            f("sortBy", "string, choicelist[resourceBundle]")],
                 "subNodesView": True, "views": ["default", "grid", "inline"]},
    # ── structured content (mainResource) ────────────────────────────────
    "article": {"name": "Article", "node": "newsArticle", "title": True, "mainResource": True,
                "mixins": ["media", "seo"], "taxonomy": True,
                "fields": [f("body", RICHTEXT, i18n=True), f("date", "date, DatePicker")],
                "views": ["default", "compact", "cm", "featured", "fullPage"]},
    "event": {"name": "Event", "title": True, "mainResource": True,
              "mixins": ["media", "seo"], "taxonomy": True,
              "fields": [f("body", RICHTEXT, i18n=True), f("startDate", "date, DatePicker"),
                         f("endDate", "date, DatePicker"), f("location", "string", i18n=True)],
              "views": ["default", "compact", "cm", "featured", "fullPage"]},
    # ── chrome (absolute-area) ────────────────────────────────────────────
    "mainNavigation": {"name": "Main Navigation", "title": False, "mixins": [],
                       "fields": [], "chrome": "header", "treeDriven": True, "views": ["default"]},
    "siteHeader": {"name": "Site Header", "title": False, "mixins": ["media", "cta"],
                   "fields": [], "chrome": "header", "views": ["default"]},
    "footer": {"name": "Footer", "title": False, "mixins": [], "chrome": "footer",
               "child": {"key": "footerLink", "name": "Footer Link", "title": True,
                         "mixins": [], "link": True, "fields": []},
               "fields": [], "views": ["default"]},
}


# ── manifest-component builder (the schema cnd_emit / load_content consume) ──
def _child_component(child, ns, mixns):
    sup = ["jnt:content", f"{mixns}:component"]
    if child.get("title"):
        sup.append("mix:title")
    for m in child.get("mixins", []):
        sup.append(f"{mixns}:{m}")
    return {
        "name": child["name"],
        "nodeType": f"{ns}:{child['key']}",
        "supertypes": sup,
        "mixins": [f"{mixns}:{m}" for m in child.get("mixins", [])],
        "link": bool(child.get("link")),
        "fields": list(child.get("fields", [])),
    }


def node_local(key):
    """Local nodeType name for an archetype key — the key itself, unless the key
    is a bare HTML tag (section/article) that the authoring naming gate rejects,
    in which case an editorial `node` override is used."""
    return ARCHETYPES[key].get("node", key)


def to_manifest_component(key, ns, mixns, name_override=None, covers_roles=None):
    """Build one manifest component for the given archetype key.

    Extends the manifest schema with `archetype`, `supertypes`, `mixins`, `layout`,
    `chrome`, `treeDriven` — cnd_emit composes supertypes verbatim and emits ONLY
    the component's own `fields` inline (mixin-provided fields come from the mixin).
    """
    a = ARCHETYPES[key]
    sup = ["jnt:content"]
    if a.get("contentList"):
        sup = ["jnt:contentList"]
    if a.get("layoutType"):
        sup.append(f"{mixns}:layout")
    else:
        sup.append(f"{mixns}:pageComponent")
    if a.get("mainResource"):
        sup += ["jmix:mainResource", "jmix:editorialContent", f"{mixns}:queryContent"]
    if a.get("list"):
        sup.append("jmix:list")
    if a.get("cache"):
        sup.append("jmix:cache")
    if a.get("title"):
        sup.append("mix:title")
    for m in a.get("mixins", []):
        sup.append(f"{mixns}:{m}")
    if a.get("taxonomy"):
        sup += ["jmix:categorized", "jmix:tagged"]
    comp = {
        "name": name_override or a["name"],
        "nodeType": f"{ns}:{node_local(key)}",
        "archetype": key,
        "coversRoles": covers_roles or [key],
        "supertypes": sup,
        "orderable": bool(a.get("mainResource") or a.get("list")),
        "mixins": [f"{mixns}:{m}" for m in a.get("mixins", [])],
        "fields": list(a.get("fields", [])),
        "isContainer": bool(a.get("list") or a.get("contentList") or a.get("child")),
        "needsMainResource": bool(a.get("mainResource")),
        "needsFullPage": bool(a.get("mainResource")),
        "views": [{"name": v} for v in a.get("views", ["default"])],
        "layoutProperty": a.get("layout"),
        "subNodesView": bool(a.get("subNodesView")),
        "chrome": a.get("chrome"),
        "treeDriven": bool(a.get("treeDriven")),
    }
    if a.get("child"):
        comp["childType"] = _child_component(a["child"], ns, mixns)
    return comp


# ── CND emission for the mixins (cnd_emit calls these once) ─────────────────
def base_mixin_cnd(mixns):
    """The base marker-mixin split (picker grouping + droppability)."""
    return [
        f"[{mixns}:component] > jmix:droppableContent, jmix:editorialContent mixin",
        f"[{mixns}:pageComponent] > {mixns}:component mixin",
        f"[{mixns}:layout] > jmix:droppableContent, jmix:editorialContent mixin",
        f"[{mixns}:queryContent] mixin",
    ]


def _mixin_field_line(fld):
    line = f"  - {fld['name']} ({fld['type']})"
    if fld["name"] in ("image", "ogImage") and "weakreference" in fld["type"]:
        line += " < jmix:image"
    if fld["name"] == "ctaType":
        line += " = 'none' autocreated"
    if fld.get("i18n"):
        line += " i18n"
    return line


def shared_mixin_cnd(mixns):
    """The reusable functional mixins (cta / media / seo) — one definition each,
    composed by archetypes so functionality is never duplicated."""
    out = []
    for key, spec in SHARED_MIXINS.items():
        out.append(f"[{mixns}:{key}] mixin")
        out += [_mixin_field_line(fld) for fld in spec["fields"]]
    return out


def archetype_labels(mixns):
    """Resource-bundle labels for the shared mixins (mixns_cta.ctaLabel=…). Type +
    per-field archetype labels are derived by gen_bundles from the manifest."""
    out = {}
    for key, spec in SHARED_MIXINS.items():
        prefix = f"{mixns}_{key}"
        for k, v in spec["labels"].items():
            out[prefix if k == "" else f"{prefix}.{k}"] = v
    return out


# ── region -> archetype classifier ─────────────────────────────────────────
# Deterministic keyword+structure rules mapping a segmentation region (vision or
# adjudicated NAME + kind + container/mainResource signals) onto ONE archetype key.
# Order = priority (most specific first). This is what collapses 40+ ad-hoc region
# names into the bounded library; adjudication may override by naming a region
# after an archetype key directly. Returns (key, confidence) — confidence 'low'
# means the fallback fired and the region should surface for review.
_CLASS_RULES = [
    # (archetype key, [keywords matched against the normalized name tokens])
    ("mainNavigation", ["nav", "navigation", "menu", "navbar"]),
    ("footer",         ["footer"]),
    ("siteHeader",     ["header", "masthead", "topbar"]),
    ("event",          ["event", "agenda", "webinar", "calendar"]),
    ("article",        ["article", "news", "post", "press", "story", "blog", "publication"]),
    ("accordion",      ["accordion", "faq", "toggle", "collapsible"]),
    ("cardGrid",       ["carousel", "slider", "grid", "cards", "gallery", "logos",
                        "logowall", "tiles", "industries", "solutions"]),
    ("jcrQuery",       ["listing", "latest", "query", "results", "related", "recommendation"]),
    ("statCallout",    ["stat", "stats", "kpi", "metric", "counter", "number", "figures"]),
    ("hero",           ["hero", "jumbotron"]),
    ("banner",         ["banner", "cta", "call-to-action", "call to action", "callout",
                        "promo", "alert", "notice"]),
    ("mediaText",      ["editorial", "illustrated", "media", "feature", "split",
                        "two-column", "content-row", "content-block", "teaser",
                        "shop", "app", "vpost", "receiving", "sending"]),
    ("richTextSection", ["intro", "introduction", "text", "rich-text", "information",
                         "steps", "instructions", "ordered-list", "additional",
                         "section-text", "content", "details"]),
]


def classify_region(name, kind="component", is_container=False, needs_mr=False):
    """Map a region -> (archetype_key, confidence). Adjudication that already named
    a region after an archetype key wins immediately."""
    key_norm = norm_name(name)
    if key_norm in ARCHETYPES:                 # adjudication snapped to a key
        return key_norm, "exact"
    toks = set(key_norm.split("-"))
    hay = " " + key_norm.replace("-", " ") + " "

    if kind == "chrome":
        if toks & {"nav", "navigation", "menu"}:
            return "mainNavigation", "chrome"
        if "footer" in toks:
            return "footer", "chrome"
        return "siteHeader", "chrome"
    if needs_mr:
        return ("event" if toks & {"event", "agenda", "webinar"} else "article"), "mainResource"

    _CONTAINER_OK = ("cardGrid", "accordion", "jcrQuery", "section", "cols",
                     "footer", "article", "event")
    for akey, kws in _CLASS_RULES:
        if any((" " + kw.replace("-", " ") + " ") in hay or kw in toks for kw in kws):
            # a container region must resolve to a container-capable archetype:
            # genuine grids/carousels already matched cardGrid via keyword; a
            # container that matched a NON-container archetype (mediaText/banner/
            # hero) is a layout SECTION (2-col split, "In The Shop"), not cards.
            if is_container and akey not in _CONTAINER_OK:
                return "section", "container"
            return akey, "keyword"
    # structural fallbacks — never a new one-off type
    if is_container:
        return "section", "low"
    return "richTextSection", "low"


def norm_name(name):  # local shim (segment2manifest has its own; keep module self-contained)
    import re as _re
    return _re.sub(r"[^A-Za-z0-9]+", "-", (name or "").strip().lower()).strip("-")


# archetype vocabulary for the classifier (segment2manifest / adjudication snap-to)
ARCHETYPE_KEYS = sorted(ARCHETYPES)

if __name__ == "__main__":
    import json
    import sys
    ns = sys.argv[1] if len(sys.argv) > 1 else "ns"
    mixns = sys.argv[2] if len(sys.argv) > 2 else "nsmix"
    print("# base + shared mixins")
    for line in base_mixin_cnd(mixns) + shared_mixin_cnd(mixns):
        print(line)
    print("\n# archetype vocabulary:", ", ".join(ARCHETYPE_KEYS))
    print("\n# sample components")
    for k in ("hero", "cardGrid", "article"):
        print(json.dumps(to_manifest_component(k, ns, mixns), indent=1))
