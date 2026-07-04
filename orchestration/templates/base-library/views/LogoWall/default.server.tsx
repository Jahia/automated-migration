import { jahiaComponent, RenderChild, RenderChildren } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import styles from "./logoWall.module.css";

/**
 * $NS:logoWall — a wall of $NS:logo with a fixed `master` slot (the discoverasr
 * brands-logo section, DECOMP-PROTOTYPE §4). The master logo is a named child
 * (RenderChild name="master"); the rest are an open repeater the editor can
 * add/remove/reorder. This turns the frozen 19-logo skeleton (1/19 links
 * editable) into 19 editable typed atoms.
 *
 * The repeater filter is a PREDICATE that excludes the "master" node — both the
 * master and the repeated logos are $NS:logo, so a plain type filter would
 * double-render the master.
 */
jahiaComponent(
  { componentType: "view", nodeType: "$NS:logoWall", displayName: "Logo Wall" },
  ({ heading }: { heading?: string }) => (
    <section className={styles.root}>
      {heading && <h2 className={styles.heading}>{heading}</h2>}
      <div className={styles.container}>
        <div className={styles.master}>
          <RenderChild name="master" />
        </div>
        <div className={styles.logos}>
          <RenderChildren
            filter={(node: JCRNodeWrapper) =>
              node.isNodeType("$NS:logo") && node.getName() !== "master"
            }
          />
        </div>
      </div>
    </section>
  ),
);
