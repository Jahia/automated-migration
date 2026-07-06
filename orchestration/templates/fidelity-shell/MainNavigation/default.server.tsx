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
 * FIDELITY: the L1 bar reuses the SOURCE site's own classes
 * (asr-main-navigation--wrapper / __item / item-menu) so the captured CSS
 * styles it pixel-identically to the original menu bar. Sub-levels render in
 * an accessible nested list, hidden by default (the source's dropdown panels
 * are JS-built at open time and equally invisible at rest).
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
        if (n.isNodeType("jnt:page")) out.push(n);
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
      <div className="asr-main-navigation--wrapper main-navigation--wrapper">
        <div className="asr-main-navigation asr-main-navigation--desktop">
          <div className="wrap-content">
            {level1.map((l1) => {
              const level2 = childPages(l1);
              return (
                <div className="asr-main-navigation__item" key={l1.getPath()}>
                  <a className="item-menu" href={buildNodeUrl(l1 as never)}>
                    <span>{label(l1)}</span>
                  </a>
                  {level2.length > 0 && (
                    <ul className="asr-nav-sub" style={{ display: "none" }}>
                      {level2.map((l2) => {
                        const level3 = childPages(l2);
                        return (
                          <li key={l2.getPath()}>
                            <a href={buildNodeUrl(l2 as never)}>{label(l2)}</a>
                            {level3.length > 0 && (
                              <ul className="asr-nav-sub asr-nav-sub--l3">
                                {level3.map((l3) => (
                                  <li key={l3.getPath()}>
                                    <a href={buildNodeUrl(l3 as never)}>{label(l3)}</a>
                                  </li>
                                ))}
                              </ul>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    );
  },
);
