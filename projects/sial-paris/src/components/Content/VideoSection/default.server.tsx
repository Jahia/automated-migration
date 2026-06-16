import { jahiaComponent } from "@jahia/javascript-modules-library";
import type { Props } from "./types.js";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "sialp:videoSection",
    displayName: "Video Section",
  },
  ({ heading, videoUrl }: Props) => (
    <section className="section video-section">
      <div className="container">
        {heading && <h2 className="section__heading">{heading}</h2>}
        {videoUrl && (
          <div className="video-section__embed">
            <iframe
              src={videoUrl}
              allowFullScreen
              loading="lazy"
              title={heading ?? "Video"}
            />
          </div>
        )}
      </div>
    </section>
  ),
);
