import {
  AbsoluteArea,
  AddResources,
  buildModuleFileUrl,
  useServerContext,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { ReactNode } from "react";

export const Layout = ({ title, children }: { title?: string; children: ReactNode }) => {
  const { currentResource, renderContext } = useServerContext();
  const lang = currentResource.getLocale().getLanguage();

  const site = renderContext.getSite() as unknown as JCRNodeWrapper;
  const homePage = site.getNode("home") as JCRNodeWrapper;

  return (
    <html lang={lang}>
      <head>
        <meta charSet="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>{title ?? "SIAL Paris"}</title>
        <AddResources type="css" resources={buildModuleFileUrl("static/css/bootstrap4.css")} />
        <AddResources type="css" resources={buildModuleFileUrl("static/css/core-libraries.css")} />
        <AddResources type="css" resources={buildModuleFileUrl("static/css/main-theme.css")} />
        <AddResources type="css" resources={buildModuleFileUrl("static/css/sial-paris-theme.css")} />
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Mukta:wght@400;500;600;700&display=swap" />
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swiffy-slider@1.6.0/dist/css/swiffy-slider.min.css" crossOrigin="anonymous" />
        {/* Remap FA6 Pro font-family names to Free font files — core-libraries.css embeds FA6 Pro CSS but no Pro font files */}
        <style dangerouslySetInnerHTML={{ __html: `
          /* Prevent source-site carousel/slider JS from locking body height */
          body { height: auto !important; overflow-x: hidden; }
          @font-face {
            font-family: "Font Awesome 6 Pro";
            font-style: normal;
            font-weight: 900;
            font-display: block;
            src: url("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/webfonts/fa-solid-900.woff2") format("woff2");
          }
          @font-face {
            font-family: "Font Awesome 6 Pro";
            font-style: normal;
            font-weight: 400;
            font-display: block;
            src: url("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/webfonts/fa-regular-400.woff2") format("woff2");
          }
          @font-face {
            font-family: "Font Awesome 6 Brands";
            font-style: normal;
            font-weight: 400;
            font-display: block;
            src: url("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/webfonts/fa-brands-400.woff2") format("woff2");
          }
          @font-face {
            font-family: "Font Awesome 6 Sharp";
            font-style: normal;
            font-weight: 900;
            font-display: block;
            src: url("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/webfonts/fa-solid-900.woff2") format("woff2");
          }
          /* Component spacing */
          main > .jcr-draggable-content > .component,
          main section.component,
          main .component.feature-list,
          main .component.key-figures,
          main .component.cta-banner,
          main .component.rich-text-block,
          main .component.trends-section,
          main .component.sectors-section,
          main .component.intro-text,
          main .component.visitor-profiles,
          main .component.partners-carousel,
          main .component.news-listing,
          main .component.video-section,
          main .component.sial-network,
          main .component.cta-dual-cards {
            margin-bottom: 4rem;
          }
          main section.component:last-child,
          main .component:last-child {
            margin-bottom: 0;
          }
        ` }} />
      </head>
      <body>
        <AbsoluteArea name="header" nodeType="sialp:mainNavigation" parent={homePage} readOnly="children" />
        {children}
        <AbsoluteArea name="footer" nodeType="sialp:footer" parent={homePage} readOnly="children" />
        <script src="https://cdn.jsdelivr.net/npm/swiffy-slider@1.6.0/dist/js/swiffy-slider.min.js" crossOrigin="anonymous" defer></script>
        <script dangerouslySetInnerHTML={{ __html: `
          document.addEventListener('DOMContentLoaded', function() {
            // Init hero carousel
            var slides = document.querySelectorAll('.slides .slide');
            var dots = document.querySelectorAll('.slider-indicators li');
            var current = 0;
            function showSlide(n) {
              slides.forEach(function(s,i){ s.style.display = i===n?'':'none'; });
              dots.forEach(function(d,i){ d.className = i===n?'active':''; });
              current = n;
            }
            if (slides.length > 1) {
              showSlide(0);
              setInterval(function(){ showSlide((current+1)%slides.length); }, 5000);
            }
          });
        ` }} />
      </body>
    </html>
  );
};
