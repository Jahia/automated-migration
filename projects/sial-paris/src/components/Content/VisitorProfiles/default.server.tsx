import {
  buildNodeUrl,
  getChildNodes,
  jahiaComponent,
  useServerContext,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { Props } from "./types.js";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "sialp:visitorProfiles",
    displayName: "Visitor Profiles",
  },
  ({ heading }: Props) => {
    const { currentNode } = useServerContext();
    const profiles = getChildNodes(currentNode, -1, 0, (node: JCRNodeWrapper) =>
      node.isNodeType("sialp:visitorProfile"),
    );

    return (
      <section className="component quicklinks container bg-gray-1 col-12">
        <div className="component-content">
          <div className="container-bp">
            {heading && <h2>{heading}</h2>}
            <div className="row justify-content-center">
              {profiles.map((profile: JCRNodeWrapper) => {
                const profileHeading = profile.hasProperty("heading")
                  ? profile.getPropertyAsString("heading")
                  : undefined;

                const linkType = profile.hasProperty("j:linkType")
                  ? profile.getPropertyAsString("j:linkType")
                  : undefined;
                const linknodeRef =
                  linkType === "internal" && profile.hasProperty("j:linknode")
                    ? (profile.getProperty("j:linknode").getNode() as JCRNodeWrapper)
                    : undefined;
                const linkUrl =
                  linkType === "external" && profile.hasProperty("j:url")
                    ? profile.getPropertyAsString("j:url")
                    : undefined;

                const href =
                  linkType === "internal" && linknodeRef
                    ? buildNodeUrl(linknodeRef)
                    : linkType === "external" && linkUrl
                      ? linkUrl
                      : "#";

                return (
                  <div key={profile.getPath()} className="col-md-3 col-6">
                    <a href={href}>
                      <div className="quicklink-icon"></div>
                      {profileHeading && (
                        <h3 className="field-titre">{profileHeading}</h3>
                      )}
                    </a>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </section>
    );
  },
);
