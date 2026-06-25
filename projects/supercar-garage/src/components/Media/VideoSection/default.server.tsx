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

jahiaComponent(
  {
    componentType: "view",
    nodeType: "usg:videoSection",
    displayName: "Video Section",
  },
  (props: VideoSectionProps, { currentNode }) => {
    const { caption, description } = props;
    const videoSrc = resolveVideoSrc(currentNode as unknown as JCRNodeWrapper);

    return (
      <div
        className="component video col-12"
        data-properties="{&quot;enableKeyboard&quot;:&quot;true&quot;,&quot;name&quot;:&quot;Movie&quot;,&quot;completedTime&quot;:&quot;null&quot;}"
      >
        <div className="component-content">
          <div className="sxa-video-wrapper">
            <video
              style={{ width: "100%", height: "100%" }}
              preload="none"
              autoPlay
              muted
              poster=""
            >
              {videoSrc && (
                <source type="video/youtube" src={videoSrc} />
              )}
            </video>
            <div className="video-init"></div>
          </div>
          <div className="video-caption">
            {caption && caption}
          </div>
          <div className="video-description">
            {description && (
              <div dangerouslySetInnerHTML={{ __html: description }} />
            )}
          </div>
        </div>
      </div>
    );
  },
);
