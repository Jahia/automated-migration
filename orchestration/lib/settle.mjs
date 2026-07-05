// settle.mjs — shared JS-hydration settle logic (rule 30).
//
// The crawl (render_page.mjs) captures the POST-HYDRATION DOM: it lets the page
// JS finish, then reads what a VISITOR sees. The ground-truth gate must judge the
// SAME kind of rendered state on BOTH sides (rule 35): the source site's JS drives
// element visibility (e.g. an empty "Featured Offers" carousel receives a `hide`
// class when its data XHR fails offline). If one capture lets that JS finish and
// the other does not, the two DOMs differ in HEIGHT for a non-content reason and
// the pixel diff cascades. This helper applies the SAME settle to reference and
// preview so the JS-driven visibility state is symmetric.
//
// It is deliberately a faithful copy of render_page.mjs's settle sequence
// (network-idle + stepped scroll-to-bottom + MutationObserver quiescence). It is
// a standalone helper so the crawl's CLI script keeps its exact behavior — nothing
// in the crawl path changes.

// Wait for the page's JS to reach a quiet, fully-materialised state:
//   1. network-idle (best-effort; SPAs poll forever → capped, then ignored)
//   2. stepped scroll to the bottom (fires lazy / viewport-gated content), back to top
//   3. MutationObserver quiescence — the DOM stops mutating for `settle` ms
//      (or the `max` ceiling), the generic "content has arrived" signal.
export async function settlePage(page, { settle = 1200, max = 20000, networkIdle = 15000 } = {}) {
  try { await page.waitForLoadState('networkidle', { timeout: networkIdle }); } catch { /* SPAs poll forever */ }

  // scroll the full height in steps to trigger lazy / viewport-gated content
  await page.evaluate(async () => {
    const step = Math.round(window.innerHeight * 0.9);
    for (let y = 0; y < document.body.scrollHeight; y += step) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 250));
    }
    window.scrollTo(0, 0);
  });

  // wait until the DOM stops mutating for `settle` ms (or the `max` ceiling)
  await page.evaluate(({ settle, max }) => new Promise((resolve) => {
    let last = performance.now();
    const obs = new MutationObserver(() => { last = performance.now(); });
    obs.observe(document.documentElement, { childList: true, subtree: true, attributes: true, characterData: true });
    const t0 = performance.now();
    const tick = setInterval(() => {
      const now = performance.now();
      if (now - last >= settle || now - t0 >= max) { clearInterval(tick); obs.disconnect(); resolve(); }
    }, 100);
  }), { settle, max });
}
