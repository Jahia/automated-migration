import { buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { ContactBlockProps } from "./types.js";

function resolveBlogLink(linkType: string | undefined, current: JCRNodeWrapper): string | undefined {
  if (!linkType || linkType === "none") return undefined;
  if (linkType === "internal") {
    try {
      if (current.hasProperty("j:linknode")) {
        const linked = current.getProperty("j:linknode").getNode() as JCRNodeWrapper;
        return buildNodeUrl(linked);
      }
    } catch {
      // no internal link
    }
  } else if (linkType === "external") {
    try {
      if (current.hasProperty("j:url")) {
        return current.getProperty("j:url").getString();
      }
    } catch {
      // no external url
    }
  }
  return undefined;
}

jahiaComponent(
  {
    componentType: "view",
    nodeType: "lsp:contactBlock",
    displayName: "Contact Block",
  },
  (props: ContactBlockProps, { currentNode }: { currentNode: JCRNodeWrapper }) => {
    const blogUrl = resolveBlogLink(props["j:linkType"], currentNode);

    return (
      <div className="component contact-block col-12">
        <div className="component-content">
          <div className="container-bp p-20 mb-20">
            {props.prenomNom && (
              <div className="field-prenom-nom contact-name">
                <strong>{props.prenomNom}</strong>
              </div>
            )}
            {props.fonction && (
              <div className="field-fonction contact-role">{props.fonction}</div>
            )}
            {props.email && (
              <div className="field-email contact-email">
                <a href={`mailto:${props.email}`}>{props.email}</a>
              </div>
            )}
            {props.telephone && (
              <div className="field-telephone contact-phone">
                <a href={`tel:${props.telephone}`}>{props.telephone}</a>
              </div>
            )}
            {blogUrl && (
              <div className="field-lien-blog contact-blog-link">
                <a href={blogUrl} target="_blank" rel="noopener noreferrer">
                  Blog
                </a>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  },
);
