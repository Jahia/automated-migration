import { getChildNodes, jahiaComponent, Render, useServerContext } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { HeroCarouselProps } from "./types.js";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "lsp:heroCarousel",
    displayName: "Hero Carousel",
  },
  ({ autoplay, interval }: HeroCarouselProps, { currentNode }: { currentNode: JCRNodeWrapper }) => {
    const { renderContext } = useServerContext();
    const isEdit = renderContext.isEditMode();
    const children = getChildNodes(currentNode, -1, 0, (n: JCRNodeWrapper) =>
      n.isNodeType("lsp:hero"),
    );
    const auto = autoplay !== false;
    const intervalMs = interval || 4000;

    if (isEdit) {
      return (
        <div className="component carousel col-12">
          <div className="component-content">
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
                gap: "16px",
              }}
            >
              {children.map((child) => (
                <div key={child.getIdentifier()} style={{ border: "1px solid #ccc", padding: "8px" }}>
                  <Render node={child as JCRNodeWrapper} view="default" readOnly />
                </div>
              ))}
            </div>
          </div>
        </div>
      );
    }

    return (
      <div className="component carousel col-12">
        <div className="component-content">
          <div className="carousel-inner">
            <div className="background" />
            <ul className="slides" style={{ padding: 0, listStyle: "none" }}>
              {children.map((child) => (
                <li key={child.getIdentifier()} className="slide">
                  <div className="row">
                    <Render node={child as JCRNodeWrapper} view="default" />
                  </div>
                </li>
              ))}
            </ul>
            <div className="nav">
              <a className="prev-text" href="#" aria-label="Previous" />
              <a className="next-text" href="#" aria-label="Next" />
            </div>
          </div>
          {auto && (
            <script
              dangerouslySetInnerHTML={{
                __html: `(function(){
                  var slides=document.querySelectorAll('.carousel-inner .slide');
                  var current=0;
                  var total=slides.length;
                  if(total<=1)return;
                  slides.forEach(function(s,i){s.style.display=i===0?'':'none';});
                  setInterval(function(){
                    slides[current].style.display='none';
                    current=(current+1)%total;
                    slides[current].style.display='';
                  },${intervalMs});
                })();`,
              }}
            />
          )}
        </div>
      </div>
    );
  },
);
