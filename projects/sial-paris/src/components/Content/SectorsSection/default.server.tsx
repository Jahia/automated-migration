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
    nodeType: "sialp:sectorsSection",
    displayName: "Sectors Section",
  },
  ({ heading }: Props) => {
    const { currentNode } = useServerContext();
    const sectors = getChildNodes(currentNode, -1, 0, (node: JCRNodeWrapper) =>
      node.isNodeType("sialp:sectorItem"),
    );

    return (
      <section className="component search-results container-bp sectors col-12">
        {heading && <h2>{heading}</h2>}
        <ul className="search-result-list">
          {sectors.map((sector: JCRNodeWrapper) => {
            const label = sector.hasProperty("label")
              ? sector.getPropertyAsString("label")
              : undefined;
            const iconNode: JCRNodeWrapper | undefined = sector.hasProperty("icon")
              ? (sector.getProperty("icon").getNode() as JCRNodeWrapper)
              : undefined;

            return (
              <li key={sector.getPath()}>
                <a href="#">
                  <div className="grid">
                    <div className="grid-icon">
                      {iconNode ? (
                        <img src={buildNodeUrl(iconNode)} alt="" />
                      ) : (
                        <div></div>
                      )}
                    </div>
                    {label && (
                      <h3 className="grid-title field-title">{label}</h3>
                    )}
                    <div className="grid-arrow">
                      <i className="fa-solid fa-chevron-right"></i>
                    </div>
                  </div>
                </a>
              </li>
            );
          })}
        </ul>
      </section>
    );
  },
);
