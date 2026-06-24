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
  const isEditMode = renderContext.isEditMode();
  const lang = currentResource.getLocale().getLanguage();

  const site = renderContext.getSite() as unknown as JCRNodeWrapper;
  const homePage = site.getNode("home") as JCRNodeWrapper;
  const parallaxBg = buildModuleFileUrl("static/assets/images/parallax-60-ans.jpg");

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
        {/* Compiled CSS-module bundle (Vite SSR). Without this, components that import
            ./component.module.css render with hashed class names but no styling. */}
        <AddResources type="css" resources={buildModuleFileUrl("dist/assets/style.css")} />
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Mukta:wght@400;500;600;700&display=swap" />
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swiffy-slider@1.6.0/dist/css/swiffy-slider.min.css" crossOrigin="anonymous" />
        {/* Remap FA6 Pro font-family names to Free font files — core-libraries.css embeds FA6 Pro CSS but no Pro font files */}
        <style dangerouslySetInnerHTML={{ __html: `
          /* Prevent source-site carousel/slider JS from locking body height */
          body { height: auto !important; overflow-x: hidden; }
          /* ===== Parallax background — HOME PAGE ONLY =====
             Scoped to main.home-main (the home template adds that class). The Layout
             is shared by every template, so an unscoped 'main' rule would put the
             parallax on all pages. */
          main.home-main {
            background-image: url("${parallaxBg}");
            background-repeat: repeat;
            background-attachment: fixed;
            background-position: top center;
          }
          /* Components that should let the parallax show through (transparent backgrounds) */
          main.home-main .component.key-figures,
          main.home-main .component.mosaic,
          main.home-main .component.sectors,
          main.home-main .component.sial-network,
          main.home-main .component.search-results { /*background: transparent !important; */}
          @media (max-width: 767px) { main.home-main { background-attachment: scroll; } }
          /* Centered content column: the loaded theme overrides Bootstrap .container to max-width:100%,
             so nothing was constrained. Constrain content components to a centered max-width while
             leaving full-bleed banners/heroes/carousels/nav/footer full width. Verified live. */
          main .component:not([class*="banner"]):not([class*="hero"]):not([class*="carousel"]):not([class*="navigation"]):not([class*="top-bar"]):not([class*="footer"]):not([class*="Slide"]):not([class*="slide"]) {
            /* max-width: 1340px; */
            margin-left: auto !important;
            margin-right: auto !important;
            padding-left: 1rem;
            padding-right: 1rem;
          }
          /* News listing (actualites): filterable card grid + voir plus */
          .news-grid-section .container { max-width: 1340px; margin: 0 auto; padding: 2rem 1rem; }
          .news-grid__filters { display: flex; flex-wrap: wrap; gap: .5rem; margin-bottom: 2rem; }
          .news-grid__filter-btn { padding: .45rem 1.1rem; border: 1px solid #d0d0d0; background: #fff; border-radius: 999px; font-size: .9rem; cursor: pointer; transition: all .15s; }
          .news-grid__filter-btn:hover { border-color: #0a3161; }
          .news-grid__filter-btn--active { background: #0a3161; color: #fff; border-color: #0a3161; }
          .news-grid__grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1.75rem; }
          .news-card { display: flex; flex-direction: column; background: #fff; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,.08); }
          .news-card__image { width: 100%; height: 200px; object-fit: cover; display: block; }
          .news-card__body { padding: 1.1rem 1.2rem 1.4rem; display: flex; flex-direction: column; gap: .5rem; }
          .news-card__categories { display: flex; flex-wrap: wrap; gap: .35rem; }
          .news-card__category { background: #f0e92a; color: #0a3161; font-size: .7rem; font-weight: 600; text-transform: uppercase; padding: .2em .7em; border-radius: 3px; }
          .news-card__date { color: #888; font-size: .8rem; }
          .news-card__title { font-size: 1.1rem; line-height: 1.3; margin: 0; }
          .news-card__title-link { color: #0a3161; text-decoration: none; }
          .news-card__title-link:hover { text-decoration: underline; }
          .news-card__excerpt { color: #555; font-size: .9rem; line-height: 1.45; margin: 0; }
          .news-grid__load-more-wrap { text-align: center; margin-top: 2.5rem; }
          .news-grid__load-more { padding: .7rem 2.2rem; border-radius: 999px; }
          /* Home "dernières actualités" teaser: 3-up grid of shared .news-card units */
          .search-results.actus { max-width: 1340px; margin: 0 auto; padding: 2rem 1rem; }
          .search-results.actus > h2 { color: #0a3161; margin: 0 0 1.5rem; }
          .search-results.actus ul.search-result-list { display: grid !important; grid-template-columns: repeat(3, 1fr); gap: 1.75rem; list-style: none; padding: 0; margin: 0; }
          .search-results.actus ul.search-result-list > li { margin: 0; width: auto; max-width: none; }
          @media (max-width: 767px) { .search-results.actus .search-result-list { grid-template-columns: 1fr; } }
          /* News article fullPage: hero banner + readable body column */
          .article-full__hero { min-height: 420px; background-size: cover; background-position: center; display: flex; align-items: flex-end; }
          .article-full__hero-overlay { width: 100%; background: linear-gradient(to top, rgba(10,49,97,.85), rgba(10,49,97,.15)); padding: 3rem 0 2.5rem; }
          .article-full__hero .container { max-width: 1100px; margin: 0 auto; padding: 0 1rem; color: #fff; }
          .article-full__categories { display: flex; flex-wrap: wrap; gap: .4rem; margin-bottom: .8rem; }
          .article-full__category { background: #f0e92a; color: #0a3161; font-size: .72rem; font-weight: 700; text-transform: uppercase; padding: .25em .8em; border-radius: 3px; }
          .article-full__date { display: block; font-size: .85rem; opacity: .9; margin-bottom: .6rem; }
          .article-full__title { font-size: 2.4rem; line-height: 1.15; font-weight: 700; margin: 0; max-width: 60rem; }
          .article-full__content { max-width: 760px; margin: 0 auto; padding: 3rem 1rem 4rem; }
          .article-full__lead { font-size: 1.25rem; line-height: 1.55; color: #0a3161; font-weight: 500; margin: 0 0 2rem; }
          .article-full__body { font-size: 1.05rem; line-height: 1.7; color: #2a2a2a; }
          .article-full__body h2 { font-size: 1.5rem; font-weight: 700; color: #0a3161; margin: 2.4rem 0 .8rem; }
          .article-full__body h3 { font-size: 1.2rem; font-weight: 700; margin: 1.8rem 0 .6rem; }
          .article-full__body p { margin: 0 0 1.2rem; }
          .article-full__body img { max-width: 100%; height: auto; border-radius: 8px; margin: 1.5rem 0; }
          .article-full__body a { color: #0a3161; text-decoration: underline; }
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
          /* Legacy FA4 family name — used by theme CSS for carousel chevrons (\\f053/\\f054) etc. */
          @font-face {
            font-family: "FontAwesome";
            font-style: normal;
            font-weight: 900;
            font-display: block;
            src: url("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/webfonts/fa-solid-900.woff2") format("woff2");
          }
          /* Carousel nav chevrons: the theme uses font-family:FontAwesome which the
             imported CSS declares with a broken URL. Override with Unicode angles
             that render in any font, so the prev/next arrows always show. */
          .component.carousel .nav a.prev-text::after { content: "\\276E" !important; font-family: inherit !important; font-weight: 700; font-size: 22px; line-height: 1; }
          .component.carousel .nav a.next-text::after { content: "\\276F" !important; font-family: inherit !important; font-weight: 700; font-size: 22px; line-height: 1; }
          /* CTA banner with an image background + parallax (background-attachment:fixed) */
          .cta-banner.image-banner { background-size: cover; background-position: center; position: relative; min-height: 420px; display: flex; align-items: center; }
          .cta-banner.parallax-banner { background-attachment: fixed; }
          .cta-banner.image-banner .cta-banner-overlay { width: 100%; background: transparent; padding: 90px 0; }
          .cta-banner.image-banner.has-overlay .cta-banner-overlay { background: rgba(20, 30, 50, 0.45); }
          .cta-banner.image-banner h2, .cta-banner.image-banner p { color: #fff; }
          .cta-banner.image-banner h2 { margin-bottom: 16px; }
          .cta-banner.image-banner p { margin-bottom: 32px; opacity: 0.9; max-width: 760px; margin-left: auto; margin-right: auto; }
          @media (max-width: 767px) { .cta-banner.parallax-banner { background-attachment: scroll; } }
          /* ===== Footer ===== */
          footer { background: #fff; color: #1b2a4a; border-top: 1px solid #ececec; }
          footer .component.footer > .component-content { max-width: 1340px; margin: 0 auto; padding: 0 1.5rem; }
          footer #footer.container { max-width: none; padding: 0; }
          footer .row { margin: 0; }
          .bg-top-footer { display: flex; flex-wrap: wrap; align-items: center; gap: 1.5rem 3rem; padding: 2.5rem 0; }
          .bg-top-footer .grid-1 { display: flex; align-items: center; gap: 1.25rem; flex-wrap: wrap; }
          .bg-top-footer .grid-1 h3 { font-size: 1.05rem; font-weight: 700; margin: 0; max-width: 230px; line-height: 1.3; }
          .social-links { display: flex; gap: .55rem; }
          .footer-social-link { width: 38px; height: 38px; border-radius: 50%; border: 1px solid #cfd3dc; display: inline-flex; align-items: center; justify-content: center; color: #1b2a4a; font-size: 1rem; text-decoration: none; transition: all .15s; }
          .footer-social-link:hover { background: #1b2a4a; border-color: #1b2a4a; color: #fff; }
          .footer-faq { margin: 0; font-weight: 600; }
          .footer-faq-link { display: inline-block; border: 1px solid #1b2a4a; border-radius: 999px; padding: .55rem 1.5rem; color: #1b2a4a; text-decoration: none; font-weight: 600; font-size: .88rem; }
          .footer-faq-link:hover { background: #1b2a4a; color: #fff; }
          .footer-newsletter { width: 100%; border-top: 1px solid #ececec; padding: 1.75rem 0; background: transparent; }
          .footer-newsletter h4 { font-size: 1rem; margin: 0 0 .75rem; }
          .footer-newsletter form { display: flex; gap: .5rem; max-width: 520px; }
          .footer-newsletter input[type=email] { flex: 1; padding: .6rem .9rem; border: 1px solid #cfd3dc; border-radius: 6px; }
          .footer-newsletter button { padding: .6rem 1.6rem; border: none; border-radius: 6px; background: #1b2a4a; color: #fff; font-weight: 600; cursor: pointer; }
          .footer-consent { display: flex; align-items: flex-start; gap: .5rem; margin-top: .75rem; font-size: .85rem; color: #555; }
          .footer-gdpr { font-size: .78rem; color: #888; margin-top: .5rem; }
          .footer-cta-row { display: flex; flex-wrap: wrap; gap: 1rem; padding: 1.75rem 0; border-top: 1px solid #ececec; }
          .footer-cta { display: inline-flex; align-items: center; padding: .6rem 1.5rem; border-radius: 999px; background: #1b2a4a; color: #fff; text-decoration: none; font-weight: 600; font-size: .82rem; text-transform: uppercase; letter-spacing: .02em; }
          .footer-cta:hover { background: #0a3161; }
          .footer-organised { display: flex; align-items: center; flex-wrap: wrap; gap: 1.5rem; padding: 1.75rem 0; border-top: 1px solid #ececec; }
          .footer-organised-label { font-size: .8rem; color: #888; text-transform: uppercase; letter-spacing: .04em; }
          .footer-logos { display: flex; align-items: center; gap: 2rem; flex-wrap: wrap; }
          .footer-logos img { height: 38px; width: auto; object-fit: contain; }
          .footer-legal { display: flex; flex-wrap: wrap; gap: .5rem 1.5rem; list-style: none; padding: 1.25rem 0; margin: 0; border-top: 1px solid #ececec; }
          .footer-legal a { color: #555; text-decoration: none; font-size: .82rem; }
          .footer-legal a:hover { color: #1b2a4a; text-decoration: underline; }
          footer .copyright { font-size: .8rem; color: #999; padding: 0 0 1.75rem; margin: 0; }
          @media (max-width: 767px) {
            .bg-top-footer { flex-direction: column; align-items: flex-start; }
            .footer-newsletter form { flex-direction: column; }
          }
          /* Sector grid cards: white, bold labels + white 54px icons over the image */
          .sectors .search-result-list a { color: #fff; text-decoration: none; }
          .sectors .search-result-list .grid-title { color: #fff; font-weight: 700; }
          .sectors .search-result-list .grid-icon { color: #fff; }
          .sectors .search-result-list .grid-icon i { color: #fff; }
          /* ===== Mobile navigation toggle (hamburger) ===== */
          .nav-burger { display: none; }
          @media (max-width: 1199.98px) {
            .nav-burger {
              display: inline-flex;
              align-items: center;
              justify-content: center;
              width: 44px;
              height: 44px;
              margin-left: 14px;
              padding: 0;
              background: transparent;
              border: 1px solid #0a3161;
              border-radius: 6px;
              cursor: pointer;
              position: relative;
              z-index: 1002;
            }
            .nav-burger span,
            .nav-burger span::before,
            .nav-burger span::after {
              content: "";
              display: block;
              width: 22px;
              height: 2px;
              background: #0a3161;
              border-radius: 2px;
            }
            .nav-burger span { position: relative; }
            .nav-burger span::before { position: absolute; left: 0; top: -7px; }
            .nav-burger span::after { position: absolute; left: 0; top: 7px; }
            /* Off-canvas panel must sit above page content when slid in */
            .component.header-navigation .navigation-main { z-index: 1001; }
          }
          /* ===== Desktop nav dropdowns (>=1200px) =====
             The imported theme uses a broad '.level1:hover .clearfix' rule that expands
             EVERY nested level-2 AND level-3 <ul> at once. Scope to DIRECT children with
             id-specificity so: level-1 hover opens its level-2 panel below; level-2 hover
             opens its level-3 list as a fly-out to the side. Nothing else shows. */
          @media (min-width: 1200px) {
            nav#main-nav li.level1 { position: relative; }
            nav#main-nav li.level1 > ul.clearfix {
              display: none;
              position: absolute;
              top: 100%;
              left: 0;
              min-width: 240px;
              z-index: 1200;
            }
            nav#main-nav li.level1:hover > ul.clearfix { display: block; }
            nav#main-nav li.level2 { position: relative; }
            nav#main-nav li.level2 > ul.clearfix.level3-dropdown {
              display: none;
              position: absolute;
              top: 0;
              left: 100%;
              min-width: 230px;
              z-index: 1300;
            }
            nav#main-nav li.level2:hover > ul.clearfix.level3-dropdown { display: block; }
            /* level-2 link shows an arrow hint when it has a level-3 fly-out */
            nav#main-nav li.level2.submenu > .navigation-title > a::after { content: " \\203A"; opacity: .6; }
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
          /* Mobile responsive: hamburger menu icon */
          @media (max-width: 991px) {
            .component.header-navigation .grid {
              flex-wrap: wrap;
            }
            .component.header-navigation .navigation-main {
              width: 100%;
              order: 10;
            }
            .component.header-navigation .title-headline {
              font-size: 0.75rem;
            }
            .component.header-navigation .cta-area {
              margin-left: auto;
            }
            .component.carousel h1 {
              font-size: 1.5rem !important;
            }
            .component.carousel .field-description {
              font-size: 0.875rem !important;
            }
            .quicklinks .col-md-3.col-6 {
              flex: 0 0 50%;
              max-width: 50%;
            }
            .component.content.mosaic .wrapper {
              flex-direction: column;
            }
            .component.content.mosaic .col-l,
            .component.content.mosaic .col-r {
              flex: 0 0 100%;
              max-width: 100%;
            }
          }
        ` }} />
      </head>
      <body>
        <AbsoluteArea name="header" nodeType="sialp:mainNavigation" parent={homePage} readOnly="children" />
        {children}
        <AbsoluteArea name="footer" nodeType="sialp:footer" parent={homePage} />
        {!isEditMode && (
          <script
            src="https://cdn.jsdelivr.net/npm/swiffy-slider@1.6.0/dist/js/swiffy-slider.min.js"
            crossOrigin="anonymous"
            defer
          ></script>
        )}
        {!isEditMode && (
          <script dangerouslySetInnerHTML={{ __html: `
            document.addEventListener('DOMContentLoaded', function() {
              /* Count-up animation for key figures */
              var counters = document.querySelectorAll('.field-chiffre-N[data-count-target]');
              if (counters.length && 'IntersectionObserver' in window) {
                var observer = new IntersectionObserver(function(entries) {
                  entries.forEach(function(entry) {
                    if (!entry.isIntersecting) return;
                    observer.unobserve(entry.target);
                    var el = entry.target;
                    var target = parseInt(el.getAttribute('data-count-target'), 10);
                    var duration = 1800;
                    var start = null;
                    function step(ts) {
                      if (!start) start = ts;
                      var progress = Math.min((ts - start) / duration, 1);
                      var ease = 1 - Math.pow(1 - progress, 3);
                      el.textContent = Math.floor(ease * target).toLocaleString('fr-FR');
                      if (progress < 1) requestAnimationFrame(step);
                      else el.textContent = target.toLocaleString('fr-FR');
                    }
                    requestAnimationFrame(step);
                  });
                }, { threshold: 0.3 });
                counters.forEach(function(el) { observer.observe(el); });
              }
            });
            document.addEventListener('DOMContentLoaded', function() {
              document.querySelectorAll('.component.carousel').forEach(function(carousel) {
                var slides = carousel.querySelectorAll('.slides .slide');
                if (!slides.length) return;
                var current = 0, timer = null;
                function show(n) {
                  current = (n + slides.length) % slides.length;
                  slides.forEach(function(s, i){ s.style.display = i === current ? '' : 'none'; });
                }
                function restart() {
                  if (timer) clearInterval(timer);
                  if (slides.length > 1) timer = setInterval(function(){ show(current + 1); }, 6000);
                }
                var prev = carousel.querySelector('.prev-text');
                var next = carousel.querySelector('.next-text');
                if (prev) prev.addEventListener('click', function(e){ e.preventDefault(); show(current - 1); restart(); });
                if (next) next.addEventListener('click', function(e){ e.preventDefault(); show(current + 1); restart(); });
                show(0);
                restart();
              });
            });
          ` }} />
        )}
      </body>
    </html>
  );
};
