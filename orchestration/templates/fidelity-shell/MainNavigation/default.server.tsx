import { jahiaComponent, buildNodeUrl, useServerContext } from "@jahia/javascript-modules-library";

/**
 * Main navigation — TREE-DRIVEN (AIStartupKit rule 19 / migration principle 12).
 *
 * Renders the site's main menu from the JCR PAGE TREE, 3 levels deep:
 *   L1 = jnt:page children of the site home (the nav sections, sitemap order)
 *   L2 = their child pages, L3 = grandchild pages
 * Labels come from jcr:title; every href is buildNodeUrl (never hardcoded).
 * Add/move/remove a page in jContent and the menu follows — no code deploy.
 *
 * STYLING: site-AGNOSTIC `main-navigation__*` classes styled by the shell's
 * shipped semantic.css (horizontal L1 bar + hover-revealed L2/L3 dropdowns).
 * A per-site theme can override those classes; the nav never depends on any
 * one source site's class names (the old asr-* hardcoding styled ascott only).
 */

type JCRNode = {
  getName: () => string;
  getPath: () => string;
  isNodeType: (t: string) => boolean;
  getDisplayableName: () => string;
  getNodes: () => { hasNext: () => boolean; nextNode: () => JCRNode };
};

const childPages = (node: JCRNode): JCRNode[] => {
  const out: JCRNode[] = [];
  try {
    const it = node.getNodes();
    while (it.hasNext()) {
      const n = it.nextNode();
      try {
        // pages flagged $NSmix:hideFromNav exist (URL reachable, editable in
        // jContent) but are NOT part of the source's menu IA — skip them here.
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
    nodeType: "$NS:mainNavigation",
    name: "default",
    displayName: "Main Navigation (page tree)",
  },
  () => {
    const { renderContext } = useServerContext();
    let home: JCRNode | null = null;
    try {
      home = (
        renderContext as unknown as { getSite: () => { getHome: () => JCRNode } }
      ).getSite().getHome();
    } catch {
      home = null;
    }
    if (!home) return null;
    const level1 = childPages(home);
    return (
      <nav className="main-navigation" aria-label="Main">
        <ul className="main-navigation__bar">
          {level1.map((l1) => {
            const level2 = childPages(l1);
            return (
              <li className="main-navigation__item" key={l1.getPath()}>
                <a className="main-navigation__link" href={buildNodeUrl(l1 as never)}>
                  {label(l1)}
                </a>
                {level2.length > 0 && (
                  <ul className="main-navigation__sub">
                    {level2.map((l2) => {
                      const level3 = childPages(l2);
                      return (
                        <li className="main-navigation__item" key={l2.getPath()}>
                          <a className="main-navigation__link" href={buildNodeUrl(l2 as never)}>
                            {label(l2)}
                          </a>
                          {level3.length > 0 && (
                            <ul className="main-navigation__sub main-navigation__sub--l3">
                              {level3.map((l3) => (
                                <li className="main-navigation__item" key={l3.getPath()}>
                                  <a
                                    className="main-navigation__link"
                                    href={buildNodeUrl(l3 as never)}
                                  >
                                    {label(l3)}
                                  </a>
                                </li>
                              ))}
                            </ul>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      </nav>
    );
  },
);
