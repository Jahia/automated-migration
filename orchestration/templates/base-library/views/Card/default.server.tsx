import { buildNodeUrl, jahiaComponent, RenderChild } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { createElement } from "react";
import { resolveImageUrl } from "../lib.js";
import { Verbatim } from "../Verbatim.js";
import styles from "./card.module.css";

/**
 * $NS:card — the richest ATOM, and the carousel SLIDE atom (P6.3-bis).
 *
 * TWO fidelity modes, chosen by whether the node carries a verbatim slide skin:
 *
 *  1. SLIDE (promoted carousel slide) — `slideOrig` present. FIDELITY-FIRST
 *     (rule 26 verbatim-default, the $NS:logo contract generalized to a rich
 *     block): render the exact captured slide markup verbatim while the picked
 *     image weakref still targets the DAM copy of the original (image UUID ==
 *     slideOrigRef → byte-exact). Once an editor picks a different image, the
 *     chosen one is swapped into the first <img>. In EDIT this is the clickable
 *     Page-Builder edit frame for the slide (G6b); LIVE renders byte-exact via the
 *     carousel container's {{child:N}} splice so this view runs only in EDIT/PREVIEW.
 *
 *  2. COMPOSABLE CARD — no `slideOrig`. Node-level lifted fields: jcr:title, body,
 *     image, imageAltText, theme, cornerCut = 6 (< K=8). tag/button are fixed CHILD
 *     nodes rendered through the pipeline (RenderChild → edit frames, rule 28).
 */
jahiaComponent(
  { componentType: "view", nodeType: "$NS:card", displayName: "Card" },
  (
    props: {
      "jcr:title"?: string;
      body?: string;
      image?: JCRNodeWrapper;
      imageAltText?: string;
      theme?: string;
      cornerCut?: string;
      slideOrig?: string;
      slideOrigRef?: string;
      slideClass?: string;
      skeletonOrig?: string;
    },
    { currentNode }: { currentNode: JCRNodeWrapper },
  ) => {
    // ── SLIDE mode: verbatim-default source markup (fidelity-first) ──
    if (props.slideOrig) {
      // Only swap the image once the editor picks a DIFFERENT one (UUID differs
      // from the captured original). Otherwise render the captured markup byte-exact.
      let picked: string | undefined;
      let isOriginal = true;
      try {
        if (props.image) {
          const uuid = props.image.getIdentifier();
          picked = buildNodeUrl(props.image);
          isOriginal = !!props.slideOrigRef && uuid === props.slideOrigRef;
        }
      } catch {
        /* image missing / target deleted → keep the captured markup */
      }

      let html = props.slideOrig;
      if (!isOriginal && picked) {
        // swap the first <img src> to the picked image (drop srcset so it wins)
        html = html
          .replace(/<img\b([^>]*?)\ssrc="[^"]*"/i, `<img$1 src="${picked}"`)
          .replace(/\ssrcset="[^"]*"/gi, "");
      }
      const cls = ["$NS-card-slide", props.slideClass || ""].filter(Boolean).join(" ");
      return createElement("div", {
        className: cls,
        // eslint-disable-next-line react/no-danger -- verbatim captured slide markup
        dangerouslySetInnerHTML: { __html: html },
      });
    }

    // ── COMPOSABLE CARD mode ──
    const title = props["jcr:title"];
    const imgSrc = resolveImageUrl(props.image);

    // Universal fidelity backstop: a card with no typed content falls back to the
    // captured markup rather than an empty <article> shell (G1: 0 empty shells).
    if (!title && !props.body && !imgSrc && props.skeletonOrig)
      return <Verbatim html={props.skeletonOrig} />;

    const cls = [
      styles.card,
      props.theme ? styles[`theme_${props.theme}`] : "",
      props.cornerCut && props.cornerCut !== "none" ? styles[props.cornerCut] : "",
    ]
      .filter(Boolean)
      .join(" ");

    return (
      <article className={cls}>
        {imgSrc && (
          <div className={styles.media}>
            <img src={imgSrc} alt={props.imageAltText ?? ""} loading="lazy" />
          </div>
        )}
        <div className={styles.body}>
          {/* tag: a fixed child slot; RenderChild shows an Add button when empty in edit mode */}
          <RenderChild name="tag" />
          {title && <h3 className={styles.title}>{title}</h3>}
          {props.body && (
            <div
              className={styles.text}
              // eslint-disable-next-line react/no-danger -- CMS rich-text output
              dangerouslySetInnerHTML={{ __html: props.body }}
            />
          )}
          {/* button: a fixed child slot rendered through the pipeline */}
          <RenderChild name="button" />
        </div>
      </article>
    );
  },
);
