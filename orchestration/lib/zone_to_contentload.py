#!/usr/bin/env python3
"""
zone_to_contentload — emit content-load.json + component-manifest.json from the fine-signal
zone_detect model. The `--segmentation zone` sibling of extract_content's vision/semantic
adapters: zone_detect makes the BOUNDARY decision (scope + library_map), this recovers the
markup and delegates the field-lift to semantic_extract.decompose_group.

Emission (fidelity-first, everything covered):
  - walk the content root; DESCEND unrecognised wrapper blocks to find typed components;
  - a block whose identity maps to a library type (conf>=0.5) -> that type, with the lifted
    skeleton (fields/{{markers}}/child items) AND a verbatim `skeletonOrig` (byte-exact
    outerHTML) so the view renders byte-identical until an editor fills the typed fields;
  - everything else -> verbatim `rawHtml` passthrough (nothing dropped);
  - ABSOLUTE chrome (header/footer/nav) -> `area`-tagged instance, emitted once per site.
Containers carry decomposed `children` (item nodes) + a manifest `childType`. EDIT-only; the
loader never publishes. Media DAM-weakref lift is deferred (images render verbatim via
skeletonOrig) — a follow-up; fidelity holds by construction.
"""
import sys, os, json, re, hashlib, base64
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bs4 import BeautifulSoup
import zone_detect as ZD
import semantic_extract as SE
import extract_content as EC

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
# set per-project by build(): where extracted/looked-up assets live
MIRROR_ASSETS = STATIC_ASSETS = None
# hard per-prop budget: the loader truncates skeleton/skeletonOrig at 200k —
# a node whose markup exceeds CAP must be split, never silently truncated
CAP = 150_000
AREA = {"role:banner": "header", "tag:header": "header", "role:contentinfo": "footer",
        "tag:footer": "footer", "role:navigation": "nav", "tag:nav": "nav"}

def area_for(key):
    """Route a chrome anchor to a template AbsoluteArea (header/nav/footer). Landmark/semantic
    keys map exactly; class-based chrome (sites without ARIA landmarks, e.g. AEM) routes by name."""
    if key in AREA:
        return AREA[key]
    k = key.split(":", 1)[-1].lower()
    if "footer" in k or "contentinfo" in k:
        return "footer"
    if ("nav" in k or "menu" in k) and "footer" not in k:
        return "nav"
    return "header"  # top-bar, header, search, dialog, chatbot, announcement, booking …
CONTAINERS = {"section", "gridRow", "cardGrid", "logoWall", "carousel", "tabs", "accordion"}
TEXT_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "ul", "ol",
             "dl", "pre", "figcaption"}

# Overlay: draw the detected boundaries ON the rendered page so a human JUDGES the
# decomposition granularity (a pixel-diff can't — skeletons are byte-exact by
# construction). Colored by ROLE (Julian's scheme): normal content zone = BLUE
# (data-zone, inset box-shadow so it coexists with a nested component outline),
# absolute zone/chrome = RED, component = GREEN. The type name rides a ::before
# label; the zone id rides a ::after label. Hover/click drives the #zx-tip popin
# (hierarchy breadcrumb + cross-page xref + a "raw HTML" toggle when pinned).
OVERLAY_CSS = """
[data-zr],[data-zone]{position:relative!important}
[data-zr]{outline-offset:-2px!important}
[data-zr=absolute]{outline:2px solid #d33a2c!important}
[data-zr=component]{outline:2px solid #1aa06a!important}
[data-zr=zone]{outline:2px solid #1f6fd6!important}
[data-zone]{box-shadow:inset 0 0 0 3px #1f6fd6!important}
[data-zx-pin]{outline:3px solid #ffb000!important;outline-offset:-3px!important}
[data-zt]::before{content:attr(data-zt);position:absolute;top:0;left:0;z-index:2147483645;
 font:700 10px/1.3 ui-monospace,Menlo,monospace;color:#fff;padding:0 4px;pointer-events:none;
 white-space:nowrap;border-bottom-right-radius:4px}
[data-zr=absolute]::before{background:#d33a2c}[data-zr=component]::before{background:#1aa06a}
[data-zr=zone]::before{background:#1f6fd6}
[data-zone]::after{content:"\\25a6 " attr(data-zone);position:absolute;top:0;right:0;z-index:2147483645;
 font:700 10px/1.3 ui-monospace,Menlo,monospace;color:#fff;background:#1f6fd6;padding:0 4px;
 pointer-events:none;white-space:nowrap;border-bottom-left-radius:4px}
#zx-ban{position:fixed;top:0;left:0;right:0;z-index:2147483646;background:#001932;color:#cfe4f5;
 font:12px/1.4 ui-monospace,Menlo,monospace;padding:6px 12px;border-bottom:2px solid #0077bf}
#zx-ban b{color:#fff}
#zx-legend{float:right;font:11px/1.4 -apple-system,sans-serif;color:#9ec5e6}
#zx-legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin:0 3px 0 12px;vertical-align:-1px}
#zx-legend i.z{background:#1f6fd6}#zx-legend i.a{background:#d33a2c}#zx-legend i.c{background:#1aa06a}
body{padding-top:30px!important}
#zx-tip{position:fixed;z-index:2147483647;max-width:360px;background:#001932;color:#e8f1f9;
 font:12px/1.45 -apple-system,sans-serif;padding:9px 11px;border-radius:8px;
 box-shadow:0 6px 22px rgba(0,0,0,.45);pointer-events:none;display:none}
#zx-tip.pin{border:1px solid #0077bf}
#zx-tip .hd{display:flex;align-items:center;gap:6px;margin-bottom:5px}
#zx-tip .ty{font-family:ui-monospace,monospace;font-weight:700}
#zx-tip .badge{font:700 10px/1.5 -apple-system,sans-serif;color:#fff;padding:0 6px;border-radius:9px}
#zx-tip .badge.z{background:#1f6fd6}#zx-tip .badge.a{background:#d33a2c}#zx-tip .badge.c{background:#1aa06a}
#zx-tip #zx-x{margin-left:auto;cursor:pointer;font-size:16px;color:#9ec5e6;padding:0 2px}
#zx-tip #zx-x:hover{color:#fff}
#zx-tip .row{margin-top:3px}#zx-tip .p{color:#9ec5e6;margin-top:4px;font-size:11px}
#zx-tip .hier{margin-top:7px;padding-top:6px;border-top:1px solid #123a5a;font-size:11px;color:#cfe4f5}
#zx-tip .hier .lbl{display:block;color:#6fa5cf;text-transform:uppercase;letter-spacing:.5px;font-size:9px;margin-bottom:2px}
#zx-tip .hier .s{color:#5a86ab;margin:0 2px}
#zx-tip .act{margin-top:8px}
#zx-tip #zx-raw{cursor:pointer;background:#0d3557;color:#cfe4f5;border:1px solid #1a5183;
 border-radius:5px;font:600 11px -apple-system,sans-serif;padding:4px 9px}
#zx-tip #zx-raw:hover{background:#134470}
#zx-tip #zx-pre{margin-top:7px;max-height:300px;max-width:340px;overflow:auto;background:#00101f;
 color:#a9d5b6;font:11px/1.4 ui-monospace,monospace;padding:7px;border-radius:5px;
 white-space:pre-wrap;word-break:break-word}
#zx-tip #zx-pre .tg{color:#7ec4ff}#zx-tip #zx-pre .an{color:#e0af68}
#zx-tip #zx-pre .av{color:#e2a6a0}#zx-tip #zx-pre .id{color:#f5d76e;font-weight:600}
#zx-tip #zx-pre .pu{color:#6b8299}#zx-tip #zx-pre .cm{color:#5f8a6a;font-style:italic}
#zx-tip #zx-pre .tx{color:#cbd8e2}
#zx-tip #zx-pre .ph{font-weight:700;border-radius:3px;padding:0 3px}
#zx-tip #zx-pre .ph-component{color:#08210f;background:#4ade80}
#zx-tip #zx-pre .ph-zone{color:#07182c;background:#60a5fa}
#zx-tip #zx-pre .ph-absolute{color:#2a0808;background:#f87171}
"""

def _overlay_category(t):
    if t == "rawHtml":
        return "raw"
    if t == "zone":
        return "zone"
    if t == "section":
        return "generic"
    return "cont" if t in CONTAINERS else "atom"

# S3 cross-page observability: a fixed template banner + a hover tooltip on every
# tagged element showing its type/scope, HOW MANY instances were detected across
# the corpus, and WHICH OTHER pages reference the same component (data from agg).
_OVERLAY_JS = """
(function(){
 var ZX=%s, SLUG=%s, Q='[data-zt],[data-zone]';
 var ban=document.createElement('div');ban.id='zx-ban';
 var tmpl=(ZX.pageTemplates||{})[SLUG]||'?';
 var sibs=Object.keys(ZX.pageTemplates||{}).filter(function(s){return ZX.pageTemplates[s]===tmpl&&s!==SLUG;});
 ban.innerHTML='Page <b>'+SLUG+'</b> &middot; Template <b>'+tmpl+'</b> ('+(sibs.length+1)+' page'
  +(sibs.length?'s':'')+(sibs.length?' &middot; aussi: '+sibs.slice(0,8).join(', ')+(sibs.length>8?' +'+(sibs.length-8):''):'')+')'
  +'<span id="zx-legend"><i class="z"></i>zone <i class="a"></i>zone absolue <i class="c"></i>composant &middot; clic = épingler</span>';
 document.body.appendChild(ban);
 var tip=document.createElement('div');tip.id='zx-tip';document.body.appendChild(tip);
 var pinned=null;
 function esc(s){var d=document.createElement('div');d.textContent=s;return d.innerHTML;}
 function role(el){
   if(el.getAttribute('data-zr')==='absolute')return{k:'zone absolue',cls:'a'};
   if(el.hasAttribute('data-zone'))return{k:'zone '+el.getAttribute('data-zone'),cls:'z'};
   if(el.getAttribute('data-zr')==='zone')return{k:'zone',cls:'z'};
   return{k:'composant',cls:'c'};
 }
 function crumb(el){
   var z=el.getAttribute('data-zone'),t=el.getAttribute('data-zt'),r=el.getAttribute('data-zr');
   if(z&&t)return z+':'+t; if(z)return z;
   if(r==='zone')return 'zone';
   if(r==='absolute')return (t||'chrome')+' (abs)';
   return t||'?';
 }
 function pathOf(el){
   var chain=[],n=el;
   while(n&&n!==document.body){
     if(n.hasAttribute&&(n.hasAttribute('data-zt')||n.hasAttribute('data-zone')))chain.unshift(n);
     n=n.parentElement;
   }
   return chain;
 }
 function ph(el){
   if(el.hasAttribute('data-zone'))return '[[zone:'+el.getAttribute('data-zone')+(el.getAttribute('data-zt')?':'+el.getAttribute('data-zt'):'')+']]';
   if(el.getAttribute('data-zr')==='zone')return '[[zone:'+(el.getAttribute('data-zt')||'zone')+']]';
   if(el.getAttribute('data-zr')==='absolute')return '[[absolute:'+(el.getAttribute('data-zt')||'chrome')+']]';
   return '[[component:'+(el.getAttribute('data-zt')||'?')+']]';
 }
 function rawOf(el){
   var c=el.cloneNode(true);
   // collapse each IDENTIFIED sub-component/zone to a placeholder (topmost on each
   // path; don't recurse into it) so the view shows THIS node's own markup with its
   // children abstracted — not the whole expanded subtree (Julian's ask).
   (function collapse(node){
     Array.prototype.slice.call(node.children).forEach(function(ch){
       if(ch.hasAttribute&&(ch.hasAttribute('data-zt')||ch.hasAttribute('data-zone')))
         ch.parentNode.replaceChild(document.createTextNode(ph(ch)),ch);
       else collapse(ch);
     });
   })(c);
   // strip overlay attrs / injected nodes from what remains (incl. the root)
   var all=[c].concat(Array.prototype.slice.call(c.querySelectorAll('*')));
   all.forEach(function(x){['data-zt','data-zc','data-zk','data-zr','data-zone','data-zx-pin'].forEach(function(a){if(x.removeAttribute)x.removeAttribute(a);});});
   Array.prototype.slice.call(c.querySelectorAll('#zx-ban,#zx-tip')).forEach(function(x){x.remove();});
   return c.outerHTML;
 }
 // ---- lightweight, self-contained HTML syntax highlighter for the raw view ----
 function phSpan(tok){var mm=/\\[\\[(component|zone|absolute):/.exec(tok);var r=mm?mm[1]:'component';
   return '<span class="ph ph-'+r+'">'+esc(tok)+'</span>';}
 function attrPart(rest){
   var h='',re=/\\s+|([a-zA-Z_:][-\\w:.]*)(\\s*=\\s*)?("[^"]*"|'[^']*'|[^\\s"'=<>`]+)?/g,m;
   while(re.lastIndex<rest.length&&(m=re.exec(rest))){
     if(m[0].length===0){re.lastIndex++;continue;}
     if(m[1]===undefined){h+=esc(m[0]);continue;}
     var id=/(^|-)id$/i.test(m[1]);
     h+='<span class="'+(id?'id':'an')+'">'+esc(m[1])+'</span>';
     if(m[2])h+='<span class="pu">'+esc(m[2])+'</span>';
     if(m[3]!==undefined)h+='<span class="'+(id?'id':'av')+'">'+esc(m[3])+'</span>';
   }
   return h;
 }
 function tagSpan(tok){
   var inner=tok.slice(1,-1),cl=false,sc=false;
   if(inner.charAt(0)==='/'){cl=true;inner=inner.slice(1);}
   if(inner.charAt(inner.length-1)==='/'){sc=true;inner=inner.slice(0,-1);}
   var mm=/^([a-zA-Z][\\w:-]*)([\\s\\S]*)$/.exec(inner);
   var name=mm?mm[1]:inner,rest=mm?mm[2]:'';
   return '<span class="pu">&lt;'+(cl?'/':'')+'</span><span class="tg">'+esc(name)+'</span>'
     +attrPart(rest)+'<span class="pu">'+(sc?'/':'')+'&gt;</span>';
 }
 function hl(raw){
   var RE=/<!--[\\s\\S]*?-->|<\\/?[a-zA-Z][\\w:-]*(?:[^>"']|"[^"]*"|'[^']*')*>|\\[\\[(?:component|zone|absolute):[^\\]]+\\]\\]/g;
   var out='',last=0,m;
   while((m=RE.exec(raw))){
     if(m.index>last)out+='<span class="tx">'+esc(raw.slice(last,m.index))+'</span>';
     var t=m[0];
     if(t.substr(0,4)==='<!--')out+='<span class="cm">'+esc(t)+'</span>';
     else if(t.charAt(0)==='[')out+=phSpan(t);
     else out+=tagSpan(t);
     last=m.index+t.length;
   }
   if(last<raw.length)out+='<span class="tx">'+esc(raw.slice(last))+'</span>';
   return out;
 }
 function render(el,pin){
   var t=el.getAttribute('data-zt')||'',k=el.getAttribute('data-zk'),r=role(el);
   var info=k?(ZX.xref||{})[k]:null;
   var bc=pathOf(el).map(function(n){var lab=esc(crumb(n));return n===el?'<b>'+lab+'</b>':lab;})
     .join(' <span class="s">&rsaquo;</span> ');
   var h='<div class="hd"><span class="badge '+r.cls+'">'+esc(r.k)+'</span> <span class="ty">'+esc(t||r.k)+'</span>';
   if(pin)h+='<span id="zx-x" title="fermer">&times;</span>';
   h+='</div>';
   if(info)h+='<div class="row"><b>'+info.instances+'</b> instance(s) sur <b>'+(info.pages||[]).length
     +'</b> page(s) &middot; scope '+esc(info.scope||'?')+' &middot; '+esc(info.tier||'')+'</div>';
   if(info){var o=(info.pages||[]).filter(function(p){return p!==SLUG;});
     h+='<div class="p">'+(o.length?'aussi sur: '+o.slice(0,10).map(esc).join(', ')+(o.length>10?' +'+(o.length-10):''):'seulement sur cette page')+'</div>';}
   h+='<div class="hier"><span class="lbl">Hiérarchie (conteneurs &rsaquo; cet élément)</span>'+(bc||esc(crumb(el)))+'</div>';
   if(pin)h+='<div class="act"><button id="zx-raw">&lt;/&gt; Voir le HTML brut</button></div><pre id="zx-pre" style="display:none"></pre>';
   tip.innerHTML=h;
 }
 function place(x,y){
   tip.style.left=Math.min(x+14,window.innerWidth-380)+'px';
   tip.style.top=Math.min(y+14,window.innerHeight-80)+'px';
 }
 function unpin(){
   if(pinned){pinned.removeAttribute('data-zx-pin');pinned=null;}
   tip.className='';tip.style.pointerEvents='none';tip.style.display='none';
   tip.style.position='';  // back to CSS position:fixed for the hover tooltip
 }
 function placePinned(x,y){
   // pin in DOCUMENT coords (absolute) so a bottom-of-page popin lives in page
   // flow and can be scrolled to — not clipped off-screen like position:fixed
   // would be. Clamp horizontally; then scroll it into view so it's revealed.
   var sx=window.scrollX||window.pageXOffset||0, sy=window.scrollY||window.pageYOffset||0;
   tip.style.position='absolute';
   tip.style.left=(Math.max(4,Math.min(x+14,window.innerWidth-390))+sx)+'px';
   tip.style.top=(y+14+sy)+'px';
   tip.scrollIntoView({block:'nearest',inline:'nearest'});
 }
 function pin(el,x,y){
   unpin();pinned=el;el.setAttribute('data-zx-pin','1');
   render(el,true);tip.className='pin';tip.style.pointerEvents='auto';tip.style.display='block';placePinned(x,y);
   var xb=document.getElementById('zx-x');if(xb)xb.onclick=function(ev){ev.stopPropagation();unpin();};
   var rb=document.getElementById('zx-raw');
   if(rb)rb.onclick=function(ev){ev.stopPropagation();var pre=document.getElementById('zx-pre');
     if(pre.style.display==='none'){pre.innerHTML=hl(rawOf(el));pre.style.display='block';rb.innerHTML='&#9662; Masquer le HTML';pre.scrollIntoView({block:'nearest'});}
     else{pre.style.display='none';rb.innerHTML='&lt;/&gt; Voir le HTML brut';}};
 }
 document.body.addEventListener('mouseover',function(e){
   if(pinned)return;
   var el=e.target.closest(Q);
   if(!el){tip.style.display='none';return;}
   render(el,false);tip.style.display='block';place(e.clientX,e.clientY);
 });
 document.body.addEventListener('mousemove',function(e){if(!pinned&&tip.style.display==='block')place(e.clientX,e.clientY);});
 document.body.addEventListener('click',function(e){
   if(tip.contains(e.target))return;
   var el=e.target.closest(Q);
   if(el){e.preventDefault();e.stopPropagation();pin(el,e.clientX,e.clientY);}else unpin();
 },true);
})();
"""

def build_xref(agg, isa, page_cl, slug_by_pi):
    """Cross-page reference data for the S3 overlay tooltip: per detection key ->
    scope/tier/instance-count/pages; per page -> template cluster id."""
    xref = {}
    for k, e in agg.items():
        if not isa(k):
            continue
        pgs = sorted({slug_by_pi[pi] for pi in e.get("pages", set()) if pi < len(slug_by_pi)})
        xref[k] = {"scope": e.get("scope"), "tier": e.get("tier"),
                   "instances": e.get("inst", 0), "pages": pgs}
    page_templates = {slug_by_pi[pi]: f"T{ci}" for pi, ci in page_cl.items()
                      if pi < len(slug_by_pi)}
    return {"xref": xref, "pageTemplates": page_templates}
CHILD_TYPE = {"carousel": "card", "logoWall": "logo", "tabs": "tab", "cardGrid": "card",
              "accordion": "faqItem", "section": "card", "gridRow": "card"}

def content_root(node, chrome):
    n = node
    while True:
        live = [k for k in n["kids"] if k["key"] not in chrome]
        if len(live) == 1 and live[0]["size"] >= 0.6 * n["size"]:
            n = live[0]
        else:
            break
    return n

_LAZY = re.compile(r'\sdata-(src|srcset|original|lazy-src|bg)=')
def materialize_lazy(html):
    """rule 30b: the crawl's below-fold images carry data-src (their JS swap never ran in
    a static server render) — promote data-src/data-srcset to real src/srcset so images show."""
    if not html or "data-" not in html:
        return html
    html = re.sub(r'\sdata-srcset=(["\'])', r' srcset=\1', html)
    html = re.sub(r'\sdata-(?:src|original|lazy-src)=(["\'])', r' src=\1', html)
    return html

_DATAURI = re.compile(
    r'src="data:image/(png|jpe?g|gif|webp|svg\+xml);base64,([A-Za-z0-9+/=]{4096,})"')

def extract_data_uris(html, base):
    """Inline base64 images -> real files under local-mirror/assets (DAM source) AND
    the module's static/assets (render source), src rewritten to the static URL.
    Measured need: one AEM carousel carried 3.74MB of base64 PNG inside a 3.79MB
    node — busting the loader's 200k prop cap AND defeating the DAM media lift."""
    if "data:image/" not in html:
        return html
    def repl(m):
        ext = {"png": "png", "jpeg": "jpg", "jpg": "jpg", "gif": "gif",
               "webp": "webp", "svg+xml": "svg"}[m.group(1)]
        try:
            raw = base64.b64decode(m.group(2))
        except Exception:
            return m.group(0)
        name = "b64-" + hashlib.sha1(raw).hexdigest()[:16] + "." + ext
        for d in (MIRROR_ASSETS, STATIC_ASSETS):
            os.makedirs(d, exist_ok=True)
            p = os.path.join(d, name)
            if not os.path.exists(p):
                with open(p, "wb") as f:
                    f.write(raw)
        return f'src="{base}assets/{name}"'
    return _DATAURI.sub(repl, html)

def rw(html, base):
    return materialize_lazy(extract_data_uris(EC.rewrite_asset_refs(html, base), base))

def inst_weight(p):
    """Largest single prop this payload will write (loader truncates at 200k)."""
    w = max(len(p.get("skeleton") or ""), len(p.get("skeletonOrig") or ""))
    for ch in p.get("children") or []:
        w = max(w, len(ch.get("skeleton") or ""))
    return w

def emit_typed(el, lib, base):
    """A typed library instance with REAL lifted fields (G1: empty shells are the
    failure Julian rejected — every prop visible in Content Editor must carry the
    node's actual content). decompose_group places {{f:}}/{{media:}}/{{link:}}/
    {{child:}} markers on the source DOM and self-checks recompose == original
    byte-for-byte; on any miss this returns None and the caller falls back to
    verbatim rawHtml (rule 23: fidelity before contribution)."""
    html = rw(str(el), base)
    try:
        body = BeautifulSoup(html, "lxml").body
        root = body.find(True, recursive=False) if body else None
        d = SE.decompose_group(root, allow_items=(lib in CONTAINERS)) if root is not None else None
    except Exception as e:
        print(f"  ! decompose {lib}: {str(e)[:120]}", file=sys.stderr)
        d = None
    if not d or not d.get("ok"):
        return None
    def map_files(units):
        # DAM lift needs the mirror file: the rewritten src is /modules/<m>/static/
        # assets/<name> and the same <name> exists under local-mirror/assets
        for m in units or []:
            src = (m.get("src") or "").split("?", 1)[0]
            fn = os.path.basename(src)
            if fn and not src.startswith("data:") and MIRROR_ASSETS \
                    and os.path.isfile(os.path.join(MIRROR_ASSETS, fn)):
                m["file"] = fn
    map_files(d.get("media"))
    for ch in d.get("children") or []:
        map_files(ch.get("media"))
    return {"type": lib, "parent": None, "promoted": True,
            "skeleton": d["skeleton"], "skeletonOrig": d.get("original") or html,
            "fields": d.get("fields") or {},
            "media": d.get("media") or [], "mediaTotal": d.get("mediaTotal", 0),
            "link": d.get("link"), "linkTotal": d.get("linkTotal", 0),
            "children": d.get("children") or []}

def raw_inst(el, base, area=None):
    inst = {"type": "rawHtml", "parent": None, "passthrough": True,
            "fields": {"html": rw(str(el), base)}, "images": [], "links": []}
    if area:
        inst["area"] = area
    return inst

# ── content-free structural components (Julian, 2026-07-05) ──
# A recurring element with NOTHING to contribute (divider, spacer, empty grid row)
# must not be dumped into anonymous `rawHtml` nodes (editorially useless). It becomes
# a NAMED content-free library component the editor can add/remove/reorder, rendered
# byte-exact from its skeleton. Recognizer is agnostic: emptiness + a structural name
# from the element's own class tokens. See memory contentfree-components-decision.
_CF_CONTENT_TAGS = ["img", "picture", "video", "iframe", "audio", "object", "embed",
                    "a", "button", "input", "select", "textarea", "form", "canvas"]
_CF_DIVIDER = re.compile(r'divid|separat|hairline|(^|[-_])rule([-_]|$)|(^|[-_])hr([-_]|$)', re.I)
_CF_SPACER = re.compile(r'spacer|spacing|(^|[-_])gap([-_]|$)|blank|whitespace', re.I)

_NONRENDER_TAGS = {"template", "title", "meta", "link", "base", "script", "style", "noscript"}

def is_hidden_el(el):
    """Non-rendered element that carries no visitor content. TWO tiers, kept
    deliberately conservative to stay AGNOSTIC (not tuned to one site):
      1. structurally non-rendered tags (<template>, head-only tags, script/style)
         — per the HTML spec these NEVER hold visitor content -> always dropped.
      2. `hidden` / display:none / visibility:hidden -> dropped ONLY when TRIVIAL
         (no media, < 60 chars of text). This catches framework junk (streaming
         markers <div hidden id=S:x>, tiny metadata) WITHOUT dropping substantial
         hidden content (tab panels, accordion bodies, mobile menus) that other
         sites toggle with JS — those are kept (content-safe by construction; a
         recognized tabs/accordion component captures its own panels verbatim)."""
    if el is None:
        return True
    if (getattr(el, "name", "") or "").lower() in _NONRENDER_TAGS:
        return True
    try:
        hidden = el.has_attr("hidden")
    except Exception:
        return False
    style = (el.get("style") or "").replace(" ", "").lower()
    if hidden or "display:none" in style or "visibility:hidden" in style:
        if el.find(["img", "picture", "video", "iframe", "svg", "canvas", "audio", "object"]):
            return False
        return len(" ".join(el.get_text(" ", strip=True).split())) < 60
    return False

def is_content_free(el):
    """Nothing an editor could contribute: no real text, no media, no links, no
    interactive controls. Decorative/structural only. SVG is allowed (decorative)."""
    if el is None:
        return False
    if (el.name or "").lower() in _CF_CONTENT_TAGS or el.find(_CF_CONTENT_TAGS):
        return False
    return len(" ".join(el.get_text(" ", strip=True).split())) < 3

def content_free_name(el):
    """Deterministic name from the element's own class tokens / tag (agnostic):
    divider / spacer, else 'decoration' (anonymous residue whose LABEL S4/DeepSeek
    can refine — never content)."""
    toks = []
    for d in [el] + el.find_all(True):
        c = d.get("class")
        if c:
            toks.append(" ".join(c))
        if d.name:
            toks.append(d.name)
    blob = " ".join(toks)
    if (el.name or "").lower() == "hr" or _CF_DIVIDER.search(blob):
        return "divider"
    if _CF_SPACER.search(blob):
        return "spacer"
    return "decoration"

def build(project, site, ns, module=None, overlay=False):
    global MIRROR_ASSETS, STATIC_ASSETS
    MIRROR_ASSETS = f"{REPO}/projects/{project}/workflow-output/local-mirror/assets"
    STATIC_ASSETS = f"{REPO}/projects/{project}/static/assets"
    R = ZD.analyze(project)
    agg, isa, site_chrome = R["agg"], R["is_anchor"], R["site_chrome"]
    pages = ZD.load(project)
    stemdf = ZD.stem_docfreq([b for _, b in pages])
    module = module or project
    base = f"/modules/{module}/static/"
    stats = {"typed": 0, "wired": 0, "container": 0, "flatten": 0, "anon": 0,
             "textleaf": 0}
    try:
        EC.load_runtime_map(project)
    except Exception:
        pass
    # merge the localizer's FULL url->local-asset map (mirror.json urlMap, ~1600 entries incl.
    # /content/dam & /etc.clientlibs) so rewrite_asset_refs rewrites EVERY source asset ref to
    # the module-static copy. Without it only the ~2 runtime-manifest entries are covered and
    # 800+ property images stay as source /content/dam paths -> 404 -> broken images.
    try:
        mj = json.load(open(f"{REPO}/projects/{project}/workflow-output/local-mirror/mirror.json"))
        for k, v in mj.get("urlMap", {}).items():
            EC.RUNTIME_URL_MAP[k] = v
            # urlMap keys carry the host (//www.site.com/content/dam/…) but the markup refs
            # are host-relative (/content/dam/…) — register the host-stripped variant so the
            # substring rewrite matches. Both space and %20 forms of the path.
            m = re.match(r"^(?://|https?://)[^/]+(/.*)$", k)
            if m:
                rel = m.group(1)
                EC.RUNTIME_URL_MAP[rel] = v
                if " " in rel:
                    EC.RUNTIME_URL_MAP[rel.replace(" ", "%20")] = v
    except Exception:
        pass
    # Markup source = the LOCALISED mirror (local-mirror/<slug>.html), NOT the raw _crawl cache:
    # localize_site rewrote every asset ref to a LOCAL `assets/<hash>` path that rewrite_asset_refs
    # maps to /modules/<m>/static/assets (200). The raw crawl keeps the source's absolute
    # /content/dam/... paths (404 -> broken images). Structure is identical, so the detection
    # (scope/keys from analyze on _crawl) still applies. Shell also comes from the localised HTML.
    lm = f"{REPO}/projects/{project}/workflow-output/local-mirror"
    slug2raw, slug2body, slug2soup = {}, {}, {}
    for slug, _ in pages:
        lp = os.path.join(lm, f"{slug}.html")
        if os.path.exists(lp):
            raw = open(lp, encoding="utf-8", errors="replace").read()
            slug2raw[slug] = raw
            soup = BeautifulSoup(raw, "lxml")
            b = soup.body
            if b is not None:
                slug2body[slug] = b
                slug2soup[slug] = soup  # kept so the overlay serializes the FULL styled doc

    used, out, chrome, chrome_done = set(), {}, [], set()
    # S3 cross-page observability data (built once from the detection model)
    xref_data = None
    if overlay:
        slug_by_pi = [s for s, _ in pages]
        xref_data = build_xref(agg, isa, R["page_cl"], slug_by_pi)
        json.dump(xref_data, open(f"{REPO}/projects/{project}/workflow-output/zone-xref.json", "w"),
                  ensure_ascii=False, indent=1)

    def lib_of(node):
        k = node["key"]
        if not k or not isa(k):
            return (None, 0.0, None)
        e = agg.get(k, {})
        sc = e.get("scope")
        lib, conf = ZD.library_map(k, node["tier"], sc or "COMPONENT", e.get("sib", 0), bool(node["kids"]))
        return (lib, conf, sc)

    def is_typed(node):
        lib, conf, _ = lib_of(node)
        return bool(lib and conf >= 0.5 and lib in ZD.LIBRARY_TYPES)

    def subtree_has_typed(node):
        for d in node["kids"]:
            if is_typed(d) or subtree_has_typed(d):
                return True
        return False

    def wired(p):
        return bool(p and (p["fields"] or p["media"] or p["link"] or p["children"]))

    def text_leaf_rich(el, html):
        """Bare text element (<h1>, <p>, <ul>…) decompose has nothing to lift from:
        ONE editable richText whose body IS the element — recompose is the identity
        ({{f:body}} splices body raw), fidelity exact by construction. These leaves
        (container-kid headings/intros) are what starved the G1 per-page floor
        (measured: leadership page 43%)."""
        try:
            tag = (el.name or "").lower()
        except Exception:
            return None
        if tag not in TEXT_TAGS or el.find(["img", "picture", "form", "script",
                                            "iframe", "svg", "video"]):
            return None
        if len(" ".join(el.get_text(" ", strip=True).split())) < 8:
            return None
        return {"type": "richText", "parent": None, "promoted": True,
                "skeleton": "{{f:body}}", "skeletonOrig": html,
                "fields": {"body": html}, "media": [], "link": None, "children": []}

    def lift_or_raw(el):
        """Anonymous block: still lift editable fields when the byte-exact decompose
        succeeds (generic `section` type) — text-leaf richText, then verbatim rawHtml
        otherwise. This carries the G1 per-page coverage floor on raw-heavy sites:
        a verbatim block is pixel-faithful but contributes 0 editable text."""
        t = emit_typed(el, "section", base)
        if t is not None and wired(t) and inst_weight(t) <= CAP:
            used.add("section")
            stats["anon"] += 1
            return t
        html = rw(str(el), base)
        t = text_leaf_rich(el, html)
        if t is not None and len(html) <= CAP:
            used.add("richText")
            stats["textleaf"] += 1
            return t
        return raw_inst(el, base)

    def wrapper_container(node, ek):
        """A content-free container -> ONE structural `zone`: its OWN markup with
        {{child:N}} replacing each EXTRACTION child (descended through transparent
        wrappers, so their layout markup stays inline). Recompose is substring
        re-insertion, byte-exact by construction; children are emitted as
        parent-linked instances so the wrapper markup is PRESERVED (the v1
        flatten-descend dropped it and collapsed CSS grids: destinations 23.8% GT).
        A zone carries NO editorial content (fields:{}) — only sub-components
        (Julian, 2026-07-05). See memory zone-is-content-free-container."""
        W = rw(str(node["_el"]), base)
        parts = [rw(str(kd["_el"]), base) for kd in ek]
        skel, rest, ok = "", W, True
        for n, p in enumerate(parts):
            i = rest.find(p)
            if i < 0:
                ok = False
                break
            skel += rest[:i] + "{{child:%d}}" % n
            rest = rest[i + len(p):]
        skel += rest
        if not ok or len(skel) > CAP:
            return None
        # no skeletonOrig on containers: the skeleton is exact by construction and
        # duplicating the whole subtree per nesting level would explode the payload
        return {"type": "zone", "parent": None, "promoted": True, "structural": True,
                "skeleton": skel, "fields": {}, "media": [], "link": None,
                "children": []}

    def tag(el, t, key=None):
        # overlay: mark the SOURCE element with the type it was emitted as (+ its
        # detection KEY for the cross-page tooltip lookup). Set AFTER skeletonOrig
        # is captured (str(el) at emit time) so the content-load stays clean.
        if overlay and el is not None:
            el["data-zt"] = t
            el["data-zc"] = _overlay_category(t)  # category (probe counts)
            # role drives the 3-color scheme: chrome/ABSOLUTE = red, content-free
            # structural container = blue zone, everything else = green component
            el["data-zr"] = ("absolute" if t == "chrome"
                             else "zone" if t == "zone" else "component")
            if key:
                el["data-zk"] = key

    CF_MIN_INST, CF_MIN_PAGES = 8, 3
    cf_types = set()
    def content_free_type(node):
        """Return a content-free component name (divider/spacer/decoration) if this
        node has nothing to contribute and no typed descendant. A RECOGNIZED
        decoration (divider/spacer) is always promoted; an anonymous empty block
        only when it RECURS (else it stays rawHtml — never invent a junk type)."""
        el = node.get("_el")
        if el is None or subtree_has_typed(node) or not is_content_free(el):
            return None
        name = content_free_name(el)
        e = agg.get(node.get("key") or "", {})
        recurring = (e.get("inst", 0) >= CF_MIN_INST
                     and len(e.get("pages", set()) or []) >= CF_MIN_PAGES)
        return name if (name != "decoration" or recurring) else None

    def _own_text(el):
        """Text DIRECTLY in el (not inside its element children)."""
        try:
            return "".join(el.find_all(string=True, recursive=False)).strip()
        except Exception:
            return ""

    def descend_transparent(node):
        """Descend through single-child pure-layout wrappers (one child, no own text,
        not a typed component) so their markup stays INLINE in the parent ZONE
        skeleton instead of each becoming its own nested node. This is what collapses
        `section > section > section` chains into a flat zone + its meaningful
        children (Julian: a content-free wrapper is a zone, not a component; a
        transparent single-child wrapper dissolves)."""
        n, guard = node, 0
        while (guard < 12 and len(n["kids"]) == 1 and not is_typed(n)
               and n.get("_el") is not None and not _own_text(n["_el"])):
            n = n["kids"][0]
            guard += 1
        return n

    def extraction_children(node):
        """The meaningful children to lift out of a zone: each direct kid descended
        through transparent wrappers. Order = document order (aligns with {{child:N}}).
        Hidden/non-rendered kids are dropped — their markup stays INLINE in the zone
        skeleton (byte-exact) but they never become a node/zone."""
        out = []
        for kd in node["kids"]:
            if is_hidden_el(kd.get("_el")):
                continue
            d = descend_transparent(kd)
            if not is_hidden_el(d.get("_el")):
                out.append(d)
        return out

    def emit_node(node, insts, depth, parent=None):
        """Emit ONE annotate node, recursively, as parent-linked instances.
        Inside a container (parent is not None) every node emits EXACTLY ONE
        direct child instance — the {{child:N}} markers splice JCR children by
        ORDER, so the one-instance-per-kid contract is what keeps the container
        recomposition aligned."""
        if is_hidden_el(node.get("_el")):
            # KEEP it rendered VERBATIM — removing markup is NOT visually safe: a body
            # <style>/<link> still applies CSS (measured: dropping liferay's 53 body
            # styles changed the render). Flag it nonRendered so it is NEVER a zone
            # and NEVER painted in the overlay — carried markup, not a contribution
            # surface (Julian: "je n'y crois pas" to zero-risk removal — correct).
            t = raw_inst(node["_el"], base)
            t["nonRendered"] = True
            t["parent"] = parent
            insts.append(t)
            return
        k = node["key"]
        lib, conf, sc = lib_of(node)
        if parent is None:
            # chrome: emit each DISTINCT chrome block once (dedup by key), routed to
            # a template AbsoluteArea (header/nav/footer); prune the subtree
            if k and (k in site_chrome or sc == "ABSOLUTE"):
                if k not in chrome_done:
                    chrome_done.add(k)
                    chrome.append(raw_inst(node["_el"], base, area_for(k)))
                tag(node["_el"], "chrome", k)  # tag even the deduped repeats
                return
            if k and R["is_root_wrapper"](k):
                for kd in node["kids"]:  # transparent layout root (top level only)
                    emit_node(kd, insts, depth, parent)
                return
        if lib and conf >= 0.5 and lib in ZD.LIBRARY_TYPES:
            t = emit_typed(node["_el"], lib, base)
            # a typed node that lifts NOTHING is exactly G1's "empty shell"
            # (typed façade, zero editable content) — demote it (rule 23)
            if t is not None and wired(t) and inst_weight(t) <= CAP:
                t["parent"] = parent
                insts.append(t)
                used.add(lib)
                stats["typed"] += 1
                stats["wired"] += 1
                tag(node["_el"], lib, k)
                return  # prune at the first confident anchor (maximal typed component)
        too_big = node["size"] > 300 or len(str(node["_el"])) > CAP
        if depth < 10 and node["kids"] and (subtree_has_typed(node) or too_big):
            ek = extraction_children(node)  # descend transparent single-child wrappers
            w = wrapper_container(node, ek)
            if w is not None:
                w["parent"] = parent
                idx = len(insts)
                insts.append(w)
                used.add("zone")
                stats["zone"] = stats.get("zone", 0) + 1
                tag(node["_el"], "zone", k)
                for kd in ek:
                    emit_node(kd, insts, depth + 1, idx)
                return
            if parent is None:
                # wrapper markup not substring-splittable: flatten — loses the
                # wrapper (counted, never silent); forbidden inside containers
                # (it would break the one-instance-per-marker contract)
                stats["flatten"] += 1
                for kd in node["kids"]:
                    emit_node(kd, insts, depth + 1, parent)
                return
        cf = content_free_type(node)
        if cf is not None:
            # named content-free component: renders byte-exact (verbatim skeleton),
            # reusable, zero editable props — NOT anonymous rawHtml (Julian)
            t = raw_inst(node["_el"], base)
            t["type"] = cf
            t["contentFree"] = True
            t["parent"] = parent
            insts.append(t)
            used.add(cf); cf_types.add(cf)
            stats["contentfree"] = stats.get("contentfree", 0) + 1
            tag(node["_el"], cf, k)
            return
        if too_big:  # no silent caps: an irreducible over-cap leaf is REPORTED
            print(f"  ! irreducible verbatim leaf over cap: {len(str(node['_el']))} chars "
                  f"(key={k})", file=sys.stderr)
        t = lift_or_raw(node["_el"])
        t["parent"] = parent
        insts.append(t)
        tag(node["_el"], t["type"], k)

    max_zones = 0
    for slug, crawl_body in pages:
        body = slug2body.get(slug, crawl_body)  # prefer localised markup (local asset refs)
        ann = ZD.annotate(body, stemdf, keep_el=True)
        root = content_root(ann, site_chrome)
        insts = []
        # C1 zones: each top-level band (content-root direct child) routes its
        # top-level instances to its own template zone Area (z1..zK) — several
        # non-absolute contribution zones per page; zone order = document order
        band = 0
        pending = []  # leading non-rendered markup before the first real zone
        for kid in root["kids"]:
            start = len(insts)
            emit_node(kid, insts, 0, None)
            tops = [i for i in insts[start:]
                    if i.get("parent") is None and not i.get("area")]
            if not tops:
                continue
            real = [i for i in tops if not i.get("nonRendered")]
            if real:
                band += 1
                z = f"z{band}"
                for i in tops + pending:  # non-rendered markup rides the adjacent real zone
                    i["zone"] = z
                pending = []
                # overlay: mark the band's DOM region as a normal content zone
                # (blue). It coexists with a nested component outline (box-shadow
                # vs outline) so the zone→component nesting is both visible.
                if overlay and kid.get("_el") is not None:
                    kid["_el"]["data-zone"] = z
            elif band > 0:
                # only non-rendered markup: fold into the LAST real zone — it still
                # renders (invisible) but never becomes its own bogus zone
                for i in tops:
                    i["zone"] = f"z{band}"
            else:
                pending.extend(tops)  # no real zone yet — buffer for the first one
        if pending:  # degenerate page with only non-rendered top-level markup
            band = max(band, 1)
            for i in pending:
                i["zone"] = "z1"
        max_zones = max(max_zones, band)
        if not insts:  # never emit an empty page
            insts.append(raw_inst(root["_el"], base))
        shell = None
        if slug in slug2raw:
            try:
                shell = EC.page_shell(materialize_lazy(slug2raw[slug]), base)
            except Exception:
                shell = None
        if shell is not None:
            # zone shells carry no chrome markup (levels stop at body) — the
            # Layout must keep rendering the contributed AbsoluteAreas (C0b)
            shell["chromeAreas"] = True
        out[slug] = {"adapter": "semantic", "instances": insts, "shell": shell}
        # overlay: emit_node tagged the source elements in slug2soup's body; inject
        # the boundary CSS and write the full styled doc next to the mirror so the
        # screenshot probe serves it with assets resolving.
        if overlay and slug in slug2soup:
            soup = slug2soup[slug]
            # The overlay is a STATIC visualization of the captured post-hydration
            # DOM (rule 30: content already materialized offline — no site JS needed
            # to render it). Left in place, the page's own client scripts boot ~0.5s
            # after load, re-hydrate/re-render the body, and WIPE the injected
            # data-zk tags + boundary CSS + banner (Julian: "le zonage disparait au
            # bout de 0.5s"). Strip every <script> so NOTHING re-renders; our own
            # overlay <script> is appended AFTER this and is the only JS that runs.
            for _s in soup.find_all("script"):
                _s.decompose()
            if soup.head is not None:
                st = soup.new_tag("style")
                st.string = OVERLAY_CSS
                soup.head.append(st)
            if soup.body is not None and xref_data is not None:
                sc = soup.new_tag("script")
                sc.string = _OVERLAY_JS % (json.dumps(xref_data, ensure_ascii=False),
                                           json.dumps(slug))
                soup.body.append(sc)
            with open(os.path.join(lm, f"{slug}.overlay.html"), "w", encoding="utf-8") as f:
                f.write(str(soup))

    if chrome and out:
        first = next(iter(out))
        # prepending chrome SHIFTS every instance index on the first page —
        # parent refs must shift too, or children nest under the wrong nodes
        # (caught live by the C0a gate: en/home failures + silent mis-nesting)
        off = len(chrome)
        for i in out[first]["instances"]:
            if i.get("parent") is not None:
                i["parent"] += off
        out[first]["instances"] = chrome + out[first]["instances"]

    content = {"adapter": "semantic", "pages": out}
    # loader looks up type_map[inst["type"].lower()] (load_content.py:862) — keys MUST be lowercased
    # ("cardGrid" -> "cardgrid") or the instance is silently skipped as an unmapped helper.
    itm = {lib.lower(): f"{ns}:{lib}" for lib in used}
    itm["rawhtml"] = f"{ns}:rawHtml"
    comps = []
    for lib in sorted(used):
        c = {"nodeType": f"{ns}:{lib}"}
        if lib == "zone":
            # a zone is a STRUCTURAL content-free container: holds any sub-component,
            # zero editable props (Julian) — not counted as a content component
            c["structural"] = True
            c["isContainer"] = True
            c["childType"] = {"nodeType": f"{ns}:rawHtml"}
        elif lib in cf_types:
            c["contentFree"] = True  # reusable decorative block, zero editable props
        elif lib in CONTAINERS:
            c["isContainer"] = True
            c["childType"] = {"nodeType": f"{ns}:{CHILD_TYPE.get(lib, 'card')}"}
        comps.append(c)
    chrome_areas = sorted({c["area"] for c in chrome})
    # editorial honesty for the model gate (_verdict_model). Zones are STRUCTURAL
    # and nonRendered instances are carried-but-invisible markup — both excluded
    # from the content tally; genericShare = generic CONTENT / all content.
    all_insts = [i for p in out.values() for i in p["instances"]]
    content_insts = [i for i in all_insts
                     if i.get("type") != "zone" and not i.get("nonRendered")]
    nzone = sum(1 for i in all_insts if i.get("type") == "zone")
    nnonrender = sum(1 for i in all_insts if i.get("nonRendered"))
    ninst = len(content_insts)
    # `decoration` (anonymous content-free residue) is still generic — it needs an
    # S4 name; `divider`/`spacer` are recognized so they count as meaningful.
    ngen = sum(1 for i in content_insts
               if i["type"] in ("section", "rawHtml", "decoration"))
    generic_share = ngen / max(ninst, 1)
    violations = []
    if generic_share >= 0.5:
        violations.append({"nodeType": f"{ns}:rawHtml",
                           "reason": f"{generic_share:.0%} of CONTENT instances are generic "
                                     f"section/rawHtml/decoration (editorially weak — few meaningful types)"})
    naming_quality = "poor" if generic_share >= 0.7 else ("mixed" if generic_share >= 0.4 else "good")
    manifest = {"instanceTypeMap": itm, "passthroughType": f"{ns}:rawHtml",
                "components": comps, "zones": max_zones, "templates": [],
                "zoneInstances": nzone, "nonRenderedInstances": nnonrender,
                "contentFreeTypes": sorted(f"{ns}:{c}" for c in cf_types),
                "namingQuality": naming_quality, "namingViolations": violations,
                "genericShare": round(generic_share, 3),
                "crossCutting": [{"coversRole": a, "nodeType": f"{ns}:rawHtml", "area": a}
                                 for a in chrome_areas]}
    return content, manifest, used, stats

def stamp_zones(module_dir, k):
    """Rewrite the module's basic.server.tsx zone block: <Area name=z1..zK> in
    document order + the main fallback Area. Idempotent (zones:start/end markers;
    first stamp anchors on the bare main Area)."""
    p = os.path.join(module_dir, "src", "templates", "Page", "basic.server.tsx")
    if not os.path.exists(p):
        print(f"  ! stamp_zones: {p} missing", file=sys.stderr)
        return
    src = open(p).read()
    areas = "\n".join(f'        <Area name="z{i + 1}" />' for i in range(k))
    block = ("{/* zones:start */}\n" + areas +
             '\n        <Area name="main" />\n        {/* zones:end */}')
    new, n = re.subn(r"\{/\* zones:start \*/\}[\s\S]*?\{/\* zones:end \*/\}", block, src)
    if not n:
        new, n = re.subn(r'<Area name="main" />', block, src, count=1)
    if n:
        open(p, "w").write(new)
        print(f"  -> {k} zone Areas stamped in {p}")
    else:
        print(f"  ! stamp_zones: no anchor in {p}", file=sys.stderr)

def main():
    if len(sys.argv) < 2:
        sys.exit("usage: zone_to_contentload.py <project> [<site>] [--ns asr]")
    project = sys.argv[1]
    site = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else project
    ns = "asr"
    if "--ns" in sys.argv:
        ns = sys.argv[sys.argv.index("--ns") + 1]
    module = sys.argv[sys.argv.index("--module") + 1] if "--module" in sys.argv else None
    overlay = "--overlay" in sys.argv
    content, manifest, used, stats = build(project, site, ns, module, overlay=overlay)
    if overlay:
        lm = f"{REPO}/projects/{project}/workflow-output/local-mirror"
        n = len([f for f in os.listdir(lm) if f.endswith(".overlay.html")]) if os.path.isdir(lm) else 0
        print(f"  -> {n} zone-overlay page(s) written to {lm}/<slug>.overlay.html")
    cl_path = os.path.join(REPO, "orchestration", "content", f"{project}.content-load.json")
    mf_dir = os.path.join(REPO, "projects", project, "workflow-output")
    os.makedirs(mf_dir, exist_ok=True)
    mf_path = os.path.join(mf_dir, "component-manifest.json")
    json.dump(content, open(cl_path, "w"), ensure_ascii=False, indent=1)
    json.dump(manifest, open(mf_path, "w"), ensure_ascii=False, indent=1)
    # stamp_zones targets the PROJECT dir (source files live in projects/<project>),
    # NOT the module bundle name (which only shapes the /modules/<module>/ asset URL)
    stamp_zones(os.path.join(REPO, "projects", project), manifest["zones"])
    npages = len(content["pages"])
    ninst = sum(len(p["instances"]) for p in content["pages"].values())
    ntyped = sum(1 for p in content["pages"].values() for i in p["instances"]
                 if i["type"] != "rawHtml")
    nmedia = sum(len(i.get("media") or []) for p in content["pages"].values()
                 for i in p["instances"])
    nlink = sum(1 for p in content["pages"].values() for i in p["instances"]
                if i.get("link"))
    nkids = sum(len(i.get("children") or []) for p in content["pages"].values()
                for i in p["instances"])
    print(f"{project}: {npages} pages | {ninst} instances | {ntyped} typed ({100*ntyped/max(ninst,1):.0f}%) | "
          f"library types: {sorted(used)}")
    nzones = manifest.get("zones", 0)
    print(f"  contribution: wired {stats['wired']}/{stats['typed']} typed "
          f"({100*stats['wired']/max(stats['typed'],1):.0f}%) | anon-lift {stats['anon']} | "
          f"text-leaf {stats['textleaf']} | containers {stats['container']} "
          f"(flatten {stats['flatten']}) | media units {nmedia} | links {nlink} | "
          f"item children {nkids} | zones z1..z{nzones}")
    print(f"  -> {cl_path}")
    print(f"  -> {mf_path}")

if __name__ == "__main__":
    main()
