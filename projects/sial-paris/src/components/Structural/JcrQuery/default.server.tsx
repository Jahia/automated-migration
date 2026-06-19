import { jahiaComponent, useJCRQuery, Render } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { Props } from "./types.js";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "sialp:jcrQuery",
    displayName: "JCR Query",
  },
  ({ nodeType, basePath, maxItems = 10, orderBy }: Props, { renderContext }) => {
    const siteKey = renderContext.getSite().getName();
    const resolvedPath = basePath ?? `/sites/${siteKey}/contents`;
    const resolvedType = nodeType ?? "jnt:content";
    const orderClause = orderBy ? `ORDER BY node.[${orderBy}] DESC` : "";

    const nodes: JCRNodeWrapper[] = useJCRQuery({
      query: `SELECT * FROM [${resolvedType}] AS node
              WHERE ISDESCENDANTNODE(node, '${resolvedPath}')
              ${orderClause}`,
    });

    const limited = nodes?.slice(0, maxItems) ?? [];

    if (limited.length === 0) {
      return (
        <div className="jcr-query jcr-query--empty">
          <p>No content found.</p>
        </div>
      );
    }

    return (
      <div className="jcr-query">
        {limited.map((node: JCRNodeWrapper) => (
          <Render key={node.getPath()} node={node} />
        ))}
      </div>
    );
  },
);
