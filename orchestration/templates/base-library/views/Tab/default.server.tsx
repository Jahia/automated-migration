import { jahiaComponent, RenderChildren } from "@jahia/javascript-modules-library";
import { createElement } from "react";
import { useSkeleton } from "../SkeletonBody.js";
import styles from "./tab.module.css";

/**
 * $NS:tab — one titled tabs pane. Title via jcr:title (mix:title supertype); used
 * by the parent $NS:tabs as the tab label.
 *
 * P6.3-bis FIDELITY-FIRST (rule 26 verbatim-default): a PROMOTED tab pane carries
 * its exact captured panel markup in `panelOrig`, rendered verbatim so an unedited
 * pane is byte-exact in EDIT/PREVIEW (LIVE is byte-exact via the tabs container's
 * {{child:N}} splice, so this view runs only in EDIT/PREVIEW). RenderChildren still
 * renders any composable atom the editor adds alongside — the pane stays an open
 * palette (`+ * ($NSMIX:component)`).
 */
jahiaComponent(
  { componentType: "view", nodeType: "$NS:tab", displayName: "Tab" },
  ({ panelOrig }: { panelOrig?: string }) => {
    // skeleton-first: a migrated node renders its captured source markup
    const skeletal = useSkeleton();
    if (skeletal) return skeletal;
    return (
      <div className={styles.tab}>
        {panelOrig
          ? createElement("div", {
              className: "$NS-tab-orig",
              // eslint-disable-next-line react/no-danger -- verbatim captured panel markup
              dangerouslySetInnerHTML: { __html: panelOrig },
            })
          : null}
        <RenderChildren />
      </div>
    );
  },
);
