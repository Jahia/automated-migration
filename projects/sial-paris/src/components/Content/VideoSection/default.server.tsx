import { buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import type React from "react";
import type { Props } from "./types.js";

jahiaComponent(
  { componentType: "view", nodeType: "sialp:videoSection", displayName: "Video Section" },
  ({ heading, tagline, videoUrl, thumbnailImage }: Props) => {
    if (!videoUrl) return null;

    const posterUrl = thumbnailImage ? buildNodeUrl(thumbnailImage) : undefined;

    const wrapperStyle: React.CSSProperties = {
      position: "relative",
      paddingBottom: "56.25%",
      height: 0,
      overflow: "hidden",
      background: "#000",
    };
    const iframeStyle: React.CSSProperties = {
      position: "absolute",
      top: 0,
      left: 0,
      width: "100%",
      height: "100%",
      border: 0,
    };
    const taglineStyle: React.CSSProperties = {
      fontSize: "1.5rem",
      fontWeight: 700,
      lineHeight: 1.3,
      color: "#232536",
      display: "flex",
      alignItems: "center",
      height: "100%",
      padding: "20px 40px",
    };

    return (
      <section className="component video-content-block bg-gray-1 col-12">
        <div className="component-content" style={{ maxWidth: "1140px", margin: "0 auto", width: "100%" } as React.CSSProperties}>
          {heading && (
            <div className="simple-title col-12" style={{ textAlign: "center", marginBottom: "20px" }}>
              <h2 className="field-titre">{heading}</h2>
            </div>
          )}
          <div className="row align-items-center">
            <div className="col-lg-6">
              <div style={wrapperStyle}>
                {posterUrl && (
                  <img
                    src={posterUrl}
                    alt=""
                    style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", objectFit: "cover" }}
                  />
                )}
                <iframe
                  src={videoUrl}
                  allowFullScreen
                  loading="lazy"
                  title={heading ?? "Video"}
                  style={iframeStyle}
                />
              </div>
            </div>
            {tagline && (
              <div className="col-lg-6">
                <p style={taglineStyle}>{tagline}</p>
              </div>
            )}
          </div>
        </div>
      </section>
    );
  },
);
