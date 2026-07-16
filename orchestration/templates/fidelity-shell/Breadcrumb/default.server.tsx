import { jahiaComponent, buildNodeUrl, useServerContext } from "@jahia/javascript-modules-library";
import { useTranslation } from "react-i18next";

/**
 * Breadcrumb — TREE-DRIVEN (no content needed): renders the ancestor chain of
 * the current page from the JCR page tree, home first. Labels are jcr:title
 * (getDisplayableName), every href is buildNodeUrl — never hardcoded. Hidden
 * on the home page itself. Rendered as a virtual node by the Layout.
 */
type JCRNode = {
  getPath: () => string;
  getName: () => string;
  getDisplayableName: () => string;
  getParent: () => JCRNode;
  isNodeType: (t: string) => boolean;
};

jahiaComponent(
  {
    componentType: "view",
    nodeType: "$NS:breadcrumb",
    displayName: "Breadcrumb",
  },
  () => {
    const { t } = useTranslation();
    const { renderContext, mainNode } = useServerContext();
    let home: JCRNode | null = null;
    try {
      home = (renderContext as unknown as { getSite: () => { getHome: () => JCRNode } })
        .getSite()
        .getHome();
    } catch {
      home = null;
    }
    const page = mainNode as unknown as JCRNode;
    if (!home || !page || page.getPath() === home.getPath()) return null;

    const chain: JCRNode[] = [];
    try {
      let n: JCRNode = page;
      while (n && n.getPath() !== home.getPath() && n.getPath().split("/").length > 3) {
        if (n.isNodeType("jnt:page")) chain.unshift(n);
        n = n.getParent();
      }
    } catch {
      /* partial chain is fine */
    }

    return (
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <ol className="breadcrumb__list">
          <li className="breadcrumb__item">
            <a className="breadcrumb__link" href={buildNodeUrl(home as never)}>
              {t("breadcrumb.home")}
            </a>
          </li>
          {chain.map((n, i) => (
            <li className="breadcrumb__item" key={n.getPath()}>
              {i === chain.length - 1 ? (
                <span aria-current="page">{n.getDisplayableName()}</span>
              ) : (
                <a className="breadcrumb__link" href={buildNodeUrl(n as never)}>
                  {n.getDisplayableName()}
                </a>
              )}
            </li>
          ))}
        </ol>
      </nav>
    );
  },
);
