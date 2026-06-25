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

jahiaComponent(
  {
    componentType: "view",
    nodeType: "usg:videoContentBlock",
    displayName: "Video Content Block",
  },
  (props: VideoContentBlockProps, { currentNode }) => {
    const { heading, body } = props;
    const videoSrc = resolveVideoSrc(currentNode as unknown as JCRNodeWrapper);

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
                        <video style={{ width: "100%", height: "100%" }} preload="none" autoPlay muted poster="">
                          {videoSrc && (
                            <source type="video/youtube" src={videoSrc} />
                          )}
                        </video>
                        <div className="video-init"></div>
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
