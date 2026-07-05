/**
 * base-library/views/lib.ts — shared, project-agnostic view helpers.
 *
 * Generalized from the guard patterns proven in the deployed `lesalondelaphoto`
 * module (resolveCtaUrl, resolveImageUrl, getProp). All props are OPTIONAL at
 * runtime — even mandatory CND fields (CLAUDE.md rule 5) — so every reader guards.
 *
 * $NS is stamped to the project content prefix at install time.
 */
import { buildNodeUrl } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";

/**
 * Resolve a contributor link (the j:linkType pattern). j:url / j:linknode are
 * injected at runtime by Jahia's jmix:externalLink / jmix:internalLink — read
 * them from the current node, never from a CND-declared prop.
 */
export function resolveCtaUrl(
  linkType: string | undefined,
  current: JCRNodeWrapper,
): string | undefined {
  if (!linkType || linkType === "none") return undefined;
  if (linkType === "internal") {
    try {
      if (current.hasProperty("j:linknode")) {
        return buildNodeUrl(current.getProperty("j:linknode").getNode() as JCRNodeWrapper);
      }
    } catch {
      /* linknode missing / target deleted */
    }
  } else if (linkType === "external") {
    try {
      if (current.hasProperty("j:url")) {
        return current.getProperty("j:url").getString();
      }
    } catch {
      /* url missing */
    }
  }
  return undefined;
}

/** Weakreference image node -> URL, or undefined. Never calls buildNodeUrl(undefined). */
export function resolveImageUrl(image: JCRNodeWrapper | undefined | null): string | undefined {
  if (!image) return undefined;
  try {
    return buildNodeUrl(image);
  } catch {
    return undefined;
  }
}

/** Safely read a string property from a node, "" if absent. */
export function getProp(node: JCRNodeWrapper, name: string): string {
  try {
    if (node.hasProperty(name)) return node.getProperty(name).getString() ?? "";
  } catch {
    /* not set */
  }
  return "";
}
