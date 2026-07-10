import { jahiaComponent } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { SocialLinkProps } from "./types.js";

const PLATFORM_ICONS: Record<string, { icon: string; label: string }> = {
  instagram: { icon: "fa-brands fa-instagram", label: "Instagram" },
  facebook: { icon: "fa-brands fa-facebook-f", label: "Facebook" },
  linkedin: { icon: "fa-brands fa-linkedin-in", label: "LinkedIn" },
  x: { icon: "fa-brands fa-x-twitter", label: "X (Twitter)" },
  youtube: { icon: "fa-brands fa-youtube", label: "YouTube" },
};

function resolveUrl(current: JCRNodeWrapper): string | undefined {
  try {
    if (current.hasProperty("j:url")) {
      return current.getProperty("j:url").getString();
    }
  } catch {
    // no url
  }
  return undefined;
}

jahiaComponent(
  {
    componentType: "view",
    nodeType: "lsp:socialLink",
    displayName: "Social Link",
  },
  ({ platform }: SocialLinkProps, { currentNode }: { currentNode: JCRNodeWrapper }) => {
    const url = resolveUrl(currentNode);
    const plat = platform || "instagram";
    const info = PLATFORM_ICONS[plat] || PLATFORM_ICONS.instagram;
    if (!url) return null;

    return (
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={info.label}
        className="social-link"
      >
        <div>
          <i className={info.icon} />
        </div>
      </a>
    );
  },
);
