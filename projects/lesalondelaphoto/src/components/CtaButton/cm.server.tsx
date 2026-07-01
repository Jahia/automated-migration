import { jahiaComponent, Render } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { CMPreview } from "../../templates/CMPreview.jsx";

/**
 * `cm` view — standalone preview for the jContent back-office editor panel.
 * Wraps the node's default view in CMPreview so it renders
 * with the module's full stylesheet cascade but without the site Layout chrome.
 */
jahiaComponent(
  {
    componentType: "view",
    nodeType: "lsp:ctaButton",
    name: "cm",
    displayName: "Cta Button (jContent Preview)",
  },
  (_, { currentNode }) => (
    <CMPreview>
      <Render node={currentNode as JCRNodeWrapper} />
    </CMPreview>
  ),
);
