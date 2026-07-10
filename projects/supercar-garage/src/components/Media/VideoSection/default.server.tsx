import { buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { VideoSectionProps } from "./types.js";

function resolveVideoSrc(node: JCRNodeWrapper): string {
  if (!node.hasProperty("j:linkType")) return "";
  const type = node.getProperty("j:linkType").getString();
  if (type === "internal" && node.hasProperty("j:linknode")) {
    return buildNodeUrl(node.getProperty("j:linknode").getNode() as JCRNodeWrapper);
  }
  if (type === "external" && node.hasProperty("j:url")) {
    return node.getProperty("j:url").getString() ?? "";
  }
  return "";
}

/** Extract the 11-char YouTube video id from watch / youtu.be / embed URLs. */
function youTubeId(url: string): string | undefined {
  if (!url) return undefined;
  const patterns = [
    /[?&]v=([A-Za-z0-9_-]{11})/, // watch?v=ID
    /youtu\.be\/([A-Za-z0-9_-]{11})/, // youtu.be/ID
    /\/embed\/([A-Za-z0-9_-]{11})/, // /embed/ID
    /\/shorts\/([A-Za-z0-9_-]{11})/, // /shorts/ID
  ];
  for (const p of patterns) {
    const m = url.match(p);
    if (m) return m[1];
  }
  return undefined;
}

jahiaComponent(
  {
    componentType: "view",
    nodeType: "usg:videoSection",
    displayName: "Video Section",
  },
  (props: VideoSectionProps, { currentNode }) => {
    const { caption, description } = props;
    const videoSrc = resolveVideoSrc(currentNode as unknown as JCRNodeWrapper);
    const id = youTubeId(videoSrc);

    // Autoplay-muted-loop hero embed (no controls). `playlist=id` is required
    // for `loop` to work on a single video.
    const embedSrc = id
      ? `https://www.youtube-nocookie.com/embed/${id}?autoplay=1&mute=1&loop=1&playlist=${id}&controls=0&showinfo=0&rel=0&modestbranding=1&playsinline=1&disablekb=1`
      : undefined;

    return (
      <div className="component video col-12">
        <div className="component-content">
          <div className="sxa-video-wrapper">
            {embedSrc ? (
              <iframe
                src={embedSrc}
                title={caption || "Vidéo"}
                allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
                allowFullScreen
                loading="lazy"
              />
            ) : (
              videoSrc && (
                // Non-YouTube source: native player fallback.
                <video style={{ width: "100%" }} controls preload="none">
                  <source src={videoSrc} />
                </video>
              )
            )}
          </div>
          {caption && <div className="video-caption">{caption}</div>}
          {description && (
            <div
              className="video-description"
              dangerouslySetInnerHTML={{ __html: description }}
            />
          )}
        </div>
      </div>
    );
  },
);
