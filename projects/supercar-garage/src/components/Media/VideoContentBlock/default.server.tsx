import { buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { VideoContentBlockProps } from "./types.js";

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

/** Extract the 11-char YouTube id from watch / youtu.be / embed / shorts URLs. */
function youTubeId(url: string): string | undefined {
  if (!url) return undefined;
  for (const p of [/[?&]v=([A-Za-z0-9_-]{11})/, /youtu\.be\/([A-Za-z0-9_-]{11})/, /\/embed\/([A-Za-z0-9_-]{11})/, /\/shorts\/([A-Za-z0-9_-]{11})/]) {
    const m = url.match(p);
    if (m) return m[1];
  }
  return undefined;
}

jahiaComponent(
  {
    componentType: "view",
    nodeType: "usg:videoContentBlock",
    displayName: "Video Content Block",
  },
  (props: VideoContentBlockProps, { currentNode }) => {
    const { heading, body } = props;
    const videoSrc = resolveVideoSrc(currentNode as unknown as JCRNodeWrapper);
    const ytId = youTubeId(videoSrc);
    const embedSrc = ytId
      ? `https://www.youtube-nocookie.com/embed/${ytId}?rel=0&modestbranding=1&playsinline=1`
      : undefined;

    return (
      <div className="component video-content-block container bg-gray-1 col-12">
        <div className="component-content">
          <div className="container-bp">
            <div className="row ">
              <div className="col-md-6 ">
                <div className="row">
                  <div className="component video col-12" data-properties="{&quot;enableKeyboard&quot;:&quot;true&quot;,&quot;name&quot;:&quot;Movie&quot;,&quot;completedTime&quot;:&quot;null&quot;}">
                    <div className="component-content">
                      <div className="sxa-video-wrapper">
                        {embedSrc ? (
                          <iframe
                            src={embedSrc}
                            title={heading || "Vidéo"}
                            allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
                            allowFullScreen
                            loading="lazy"
                          />
                        ) : (
                          videoSrc && (
                            <video style={{ width: "100%" }} controls preload="none">
                              <source src={videoSrc} />
                            </video>
                          )
                        )}
                      </div>
                      <div className="video-caption"></div>
                      <div className="video-description"></div>
                    </div>
                  </div>
                </div>
              </div>
              <div className="col-md-6 align-self-center py-md-70 py-sm-30">
                <div className="row justify-content-center">
                  <div className="offset-lg-2 col-lg-9">
                    <i className="fa-brands fa-youtube fa-3x"></i>
                  </div>
                  <div className="offset-lg-2 col-lg-9">
                    {heading && (
                      <h2 className="field-title">{heading}</h2>
                    )}
                    {body && (
                      <div
                        className="rich-text field-description"
                        dangerouslySetInnerHTML={{ __html: body }}
                      />
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  },
);
