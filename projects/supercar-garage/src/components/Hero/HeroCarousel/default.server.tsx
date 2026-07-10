import {
  jahiaComponent,
  RenderChildren,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { HeroCarouselProps } from "./types.js";
import styles from "./component.module.css";

/**
 * Inline carousel initialiser – runs once per carousel on the page.
 * Reads timeout and transition from data-properties then cycles slides.
 * Supports "FadeInTransition" (crossfade) and "BasicTransition" (slide).
 */
const CAROUSEL_SCRIPT = `(function(){
  document.querySelectorAll('.component.carousel[data-carousel-id]').forEach(function(el){
    var id = el.getAttribute('data-carousel-id');
    var props = {};
    try { props = JSON.parse(el.getAttribute('data-properties') || '{}'); } catch(e){}
    var timeout = parseInt(props.timeout, 10) || 4000;
    var transition = props.transition || 'FadeInTransition';
    var slides = el.querySelectorAll('.slides .slide');
    if (!slides || slides.length < 2) return;
    var current = 0;
    // Hide all but the first
    slides.forEach(function(s, i){ s.style.display = i === 0 ? '' : 'none'; });
    setInterval(function(){
      var prev = current;
      current = (current + 1) % slides.length;
      if (transition === 'FadeInTransition') {
        slides[prev].style.opacity = '1';
        slides[current].style.display = '';
        slides[current].style.opacity = '0';
        (function(p, c){
          var step = 0;
          var timer = setInterval(function(){
            step += 0.05;
            c.style.opacity = String(Math.min(step, 1));
            p.style.opacity = String(Math.max(1 - step, 0));
            if (step >= 1) { clearInterval(timer); p.style.display = 'none'; }
          }, 16);
        })(slides[prev], slides[current]);
      } else {
        slides[prev].style.display = 'none';
        slides[current].style.display = '';
      }
    }, timeout);
  });
})();`;

jahiaComponent(
  {
    componentType: "view",
    nodeType: "usg:heroCarousel",
    displayName: "Hero Carousel",
  },
  (
    { timeout, transition }: HeroCarouselProps,
    {
      currentNode,
      renderContext,
    }: {
      currentNode: JCRNodeWrapper;
      renderContext: import("org.jahia.services.render").RenderContext;
    },
  ) => {
    const isEdit = renderContext.isEditMode();

    const carouselId = `divCarousel_${currentNode.getIdentifier()}`;
    const dataProperties = JSON.stringify({
      timeout: timeout ?? 4000,
      isPauseEnabled: true,
      transition: transition ?? "FadeInTransition",
    });

    // Edit mode: render slides stacked so editors can click each one
    if (isEdit) {
      return (
        <div className="component carousel col-12">
          <div className="component-content">
            <div className={styles.editStack}>
              <RenderChildren filter="usg:heroSlide" />
            </div>
          </div>
        </div>
      );
    }

    // Live mode: render as a cycling carousel
    // Each usg:heroSlide view emits its own <li className="slide"><div className="row">
    return (
      <>
        <div
          className="component carousel col-12"
          data-carousel-id={carouselId}
          data-properties={dataProperties}
        >
          <div className="component-content">
            <div data-id={carouselId} className="carousel-inner">
              <div className="background" />
              <ul className="slides">
                <RenderChildren filter="usg:heroSlide" />
              </ul>
            </div>
          </div>
        </div>
        <script dangerouslySetInnerHTML={{ __html: CAROUSEL_SCRIPT }} />
      </>
    );
  },
);
