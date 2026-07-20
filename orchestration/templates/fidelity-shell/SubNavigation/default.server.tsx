import { jahiaComponent, buildNodeUrl, useServerContext } from "@jahia/javascript-modules-library";

/**
 * Section sub-navigation — TREE-DRIVEN (AIStartupKit rule 19 / migration
 * principle 12; operator finding 2026-07-20, speedpost-standard).
 *
 * The source renders a per-page sibling-service menu (sticky sidebar) on
 * service pages: the parent section's title + links to every child page of
 * that section, the current page highlighted. Frozen into body content that
 * menu can never follow the page tree; semanticize's subnavify pass replaces
 * the captured sidebar with this component. Add/move/remove a sibling page
 * in jContent and the menu follows — no code deploy.
 *
 * STYLING: pixel fidelity comes from the node's `classMap` property (the
 * source sidebar's own wrapper classes, captured at conversion time); the
 * site-agnostic `sub-navigation__*` classes remain as the semantic fallback
 * styled by the shell's semantic.css.
 */

type JCRNode = {
  getName: () => string;
  getPath: () => string;
  isNodeType: (t: string) => boolean;
  getDisplayableName: () => string;
  getParent: () => JCRNode;
  getNodes: () => { hasNext: () => boolean; nextNode: () => JCRNode };
};

const childPages = (node: JCRNode): JCRNode[] => {
  const out: JCRNode[] = [];
  try {
    const it = node.getNodes();
    while (it.hasNext()) {
      const n = it.nextNode();
      try {
        if (n.isNodeType("jnt:page") && !n.isNodeType("$NSmix:hideFromNav")) out.push(n);
      } catch {
        /* ignore unreadable child */
      }
    }
  } catch {
    /* no children */
  }
  return out;
};

const label = (n: JCRNode): string => {
  try {
    return n.getDisplayableName();
  } catch {
    return n.getName();
  }
};

jahiaComponent(
  {
    componentType: "view",
    nodeType: "$NS:subNavigation",
    name: "default",
    displayName: "Section Sub-Navigation (page tree)",
    // the menu depends on the CURRENT page (active item + sibling scope) —
    // without this the fragment cache serves one page's menu site-wide
    properties: { "cache.mainResource": "true" },
  },
  () => {
    const { renderContext, currentNode } = useServerContext();
    // source sidebar classes captured by subnavify (pixel fidelity); the
    // semantic sub-navigation__* classes stay alongside as the fallback skin
    let cm: Record<string, string> = {};
    try {
      const raw = (
        currentNode as unknown as { getPropertyAsString: (k: string) => string }
      ).getPropertyAsString("classMap");
      if (raw) cm = JSON.parse(raw) as Record<string, string>;
    } catch {
      cm = {};
    }
    // the node's own editable heading (the source sidebar's display copy,
    // e.g. "International shipping services") — parent page title as fallback
    let ownTitle = "";
    try {
      ownTitle = (
        currentNode as unknown as { getPropertyAsString: (k: string) => string }
      ).getPropertyAsString("jcr:title") || "";
    } catch {
      ownTitle = "";
    }
    const cls = (key: string, fallback: string): string =>
      cm[key] ? `${fallback} ${cm[key]}` : fallback;

    let page: JCRNode | null = null;
    try {
      page = (
        renderContext as unknown as { getMainResource: () => { getNode: () => JCRNode } }
      ).getMainResource().getNode();
    } catch {
      page = null;
    }
    if (!page) return null;
    let parent: JCRNode | null = null;
    try {
      const p = page.getParent();
      if (p.isNodeType("jnt:page")) parent = p;
    } catch {
      parent = null;
    }
    if (!parent) return null;
    const siblings = childPages(parent);
    if (siblings.length === 0) return null;
    const currentPath = page.getPath();
    return (
      <nav className={cls("box", "sub-navigation")} aria-label={ownTitle || label(parent)}>
        <h2 className={cls("heading", "sub-navigation__heading")}>{ownTitle || label(parent)}</h2>
        <hr />
        <ul className={cls("list", "sub-navigation__list")}>
          {siblings.map((s) => (
            <li key={s.getPath()} className={cls("item", "sub-navigation__item")}>
              <a
                href={buildNodeUrl(s as never)}
                aria-current={s.getPath() === currentPath ? "page" : undefined}
                className={
                  s.getPath() === currentPath
                    ? cls("active", "sub-navigation__link sub-navigation__link--active")
                    : cls("link", "sub-navigation__link")
                }
              >
                {label(s)}
              </a>
            </li>
          ))}
        </ul>
      </nav>
    );
  },
);
