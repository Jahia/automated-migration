import { jahiaComponent } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { ExternalEmbedProps } from "./types.js";

function resolveEmbedUrl(node: ExternalEmbedProps, current: JCRNodeWrapper): string | undefined {
  try {
    if (current.hasProperty("j:url")) {
      return current.getProperty("j:url").getString();
    }
  } catch {
    // no URL
  }
  return undefined;
}

jahiaComponent(
  {
    componentType: "view",
    nodeType: "lsp:externalEmbed",
    displayName: "External Embed",
  },
  (node: ExternalEmbedProps, { currentNode }: { currentNode: JCRNodeWrapper }) => {
    const embedUrl = resolveEmbedUrl(node, currentNode);
    const embedTitle = node.embedTitle || "";
    const embedHeight = node.embedHeight || 800;

    if (!embedUrl) {
      return (
        <div className="component external-embed col-12">
          <div className="component-content">
            <p>No embed URL configured.</p>
          </div>
        </div>
      );
    }

    return (
      <div className="component external-embed col-12">
        <div className="component-content">
          <iframe
            src={embedUrl}
            title={embedTitle}
            height={embedHeight}
            sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
            style={{ width: "100%", border: "none" }}
            loading="lazy"
          />
        </div>
      </div>
    );
  },
);
