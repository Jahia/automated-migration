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
import sys, os, json, re, hashlib, base64, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bs4 import BeautifulSoup, Comment
import zone_detect as ZD
import semantic_extract as SE
import extract_content as EC
import library_recognize as LR


# A wrapper's inline <style>/<script> BODY (CSS/JS text) and comment text is SKIN, not
# editorial content — it must not count as the wrapper's "own text" (else a container with
# an inline stylesheet is wrongly kept as a verbatim zone). Framework-agnostic.
_SKIN_TEXT = re.compile(r"<(style|script)\b[^>]*>.*?</\1>|<!--.*?-->", re.S | re.I)
# Elements that carry visible/contributable content even when they hold no text (an
# inter-child segment containing one is NOT invisible glue -> keep the verbatim zone).
_GLUE_VISIBLE = ["img", "picture", "video", "audio", "iframe", "svg", "canvas",
                 "object", "embed", "input", "button", "select", "textarea"]
_DISPLAY_NONE = re.compile(r"display:\s*none", re.I)


def _de_glue(seg):
    """Return the inter-child segment's VISIBLE, contributable markup — empty when the
    segment is only INVISIBLE GLUE (comments, display:none subtrees, empty structural
    elements). bs4-based so it handles NESTED hidden elements (a regex cannot balance
    tags: `<div style=display:none><div/></div>` needs a real parse). Geometric — never
    keyed on a framework class. Glue is preserved VERBATIM in the layoutSection gap, so a
    mis-call can only keep a byte-exact zone, never corrupt the render."""
    if not seg.strip():
        return ""
    soup = BeautifulSoup(seg, "html.parser")
    for c in soup.find_all(string=lambda t: isinstance(t, Comment)):
        c.extract()
    for el in soup.find_all(lambda t: t.has_attr("style") and _DISPLAY_NONE.search(t["style"] or "")):
        el.decompose()
    if soup.get_text(strip=True):
        return "x"                           # real visible text -> not glue
    if soup.find(_GLUE_VISIBLE):
        return "x"                           # visible media/interactive -> not glue
    return ""                                # only comments/hidden/empty -> glue


def _try_layout_section(skeleton):
    """Derive a byte-parity layoutSection skin from a zone skeleton (a pure structural
    wrapper `[open]{{child:0}}..{{child:N}}[close]`, no editorial own text). Shapes:
      Phase 1b — SINGLE Area: inter-child segments whitespace-only (children contiguous)
        -> {"open","close","areas":1}; view = open + <Area(children)> + close.
      Phase 1c — UNIFORM columns: all inter-child segments identical and non-empty (each
        child sits in an identical sibling cell) -> {"open","cellOpen","cellClose","close",
        "areas":N}; view = open + N x (cellOpen + <Area(child)> + cellClose) + close.
      Phase 1d — GLUE single Area: inter-child segments carry only INVISIBLE glue (hidden/
        empty els, comments), not real markup -> {"open","close","gaps":[...],"areas":1};
        view = open + child0 + gaps[0] + child1 + ... + close. Each gap preserved VERBATIM
        so the render is byte-identical to the verbatim zone, but the node now holds a
        structured skin + <Area> children (P1: a zone must contain sub-components, not HTML).
    All shapes are BYTE-PARITY with the zone render but store the wrapper STRUCTURED, not as
    an HTML blob. Returns None only when a wrapper carries editorial own text or a gap holds
    real (visible, contributable) markup -> keep the verbatim zone (fidelity-first)."""
    if "{{f:" in skeleton or "{{media:" in skeleton or "{{link:" in skeleton:
        return None                          # not a pure structural wrapper
    parts = re.split(r"\{\{child:\d+\}\}", skeleton)
    if len(parts) < 2:                       # need >=1 child slot (1 -> single-Area chain)
        return None
    prefix, mids, suffix = parts[0], parts[1:-1], parts[-1]
    # own-text test: CSS/JS/comment bodies are skin, not editorial content — strip them
    # before checking, else an inline <style> blocks a genuinely pure wrapper.
    if re.sub(r"<[^>]+>", "", _SKIN_TEXT.sub("", "".join(parts))).strip():
        return None                          # wrapper carries editorial own text
    if all(not m.strip() for m in mids):                  # 1b: contiguous -> single Area
        return {"open": prefix, "close": suffix, "areas": 1}
    if len(set(mids)) == 1:                                # 1c: uniform columns
        mid = mids[0]
        m = re.match(r"^((?:\s*</[^>]+>)+)(\s*<.*)$", mid, re.S)  # cellClose + cellOpen
        if m:
            cell_close, cell_open = m.group(1), m.group(2)
            if prefix.endswith(cell_open) and suffix.startswith(cell_close):
                return {"open": prefix[:len(prefix) - len(cell_open)],
                        "cellOpen": cell_open, "cellClose": cell_close,
                        "close": suffix[len(cell_close):], "areas": len(mids) + 1}
    if all(not _de_glue(m).strip() for m in mids):        # 1d: glue-only gaps -> single Area
        return {"open": prefix, "close": suffix, "gaps": mids, "areas": 1}
    return None                              # real heterogeneous markup -> keep verbatim zone


def fuse_single_child_layouts(insts):
    """A2 depth/profusion: fuse a single-child layoutSection->layoutSection CHAIN into ONE
    layoutSection. A wrapper whose ONLY child is another wrapper adds a nesting level with no
    editorial value; collapsing them cuts depth + component count. BYTE-EXACT: P wraps C, so
    the fused skin is P.open+C.open ... C.close+P.close and inherits C's cell/gap structure
    (C holds the real children, which re-parent onto P). Only layoutSection->layoutSection is
    fused — a real component child (carousel/card/section-with-content) is never dissolved.
    Iterates so P>C>D collapses fully. Returns a compacted list with parent indices remapped."""
    if not insts:
        return insts
    dead = set()
    changed = True
    while changed:
        changed = False
        kids = {}
        for j, y in enumerate(insts):
            if j in dead:
                continue
            p = y.get("parent")
            if p is not None:
                kids.setdefault(p, []).append(j)
        for i, x in enumerate(insts):
            if i in dead or x.get("type") != "layoutSection" or not isinstance(x.get("layout"), dict):
                continue
            ch = kids.get(i, [])
            if len(ch) != 1:
                continue
            cj = ch[0]
            c = insts[cj]
            if cj in dead or c.get("type") != "layoutSection" or not isinstance(c.get("layout"), dict):
                continue
            lp, lc = x["layout"], c["layout"]
            merged = {"open": (lp.get("open") or "") + (lc.get("open") or ""),
                      "close": (lc.get("close") or "") + (lp.get("close") or ""),
                      "areas": lc.get("areas", 1)}
            if lc.get("cellOpen") is not None:
                merged["cellOpen"], merged["cellClose"] = lc["cellOpen"], lc.get("cellClose", "")
            if lc.get("gaps") is not None:
                merged["gaps"] = lc["gaps"]
            x["layout"] = merged
            x["sourceClasses"] = ((x.get("sourceClasses") or []) + (c.get("sourceClasses") or [])) or None
            for y in insts:                              # re-parent C's children onto P
                if y.get("parent") == cj:
                    y["parent"] = i
            dead.add(cj)
            changed = True
    if not dead:
        return insts
    survivors = [j for j in range(len(insts)) if j not in dead]
    remap = {old: new for new, old in enumerate(survivors)}
    out = []
    for old in survivors:
        x = insts[old]
        if x.get("parent") is not None:
            x["parent"] = remap[x["parent"]]             # parent always survives (never a fused child)
        out.append(x)
    return out

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
# arbitrated types whose content is a single editable text run — an LLM attribution
# of one of these lifts the element's inner content into {{f:body}} (text_wrap).
_TEXT_ATOM = {"richText", "heading", "tag"}
# #2 keyless-text floor: minimum visible text (chars) for a leaf the typed lift
# couldn't reach to be lifted to editable richText rather than left an opaque orphan.
_TEXT_FLOOR = 8
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
[data-zr]{outline-offset:-2px!important}
[data-zr=absolute]{outline:2px solid #d33a2c!important}
[data-zr=component]{outline:2px solid #1aa06a!important}
[data-zr=layout]{outline:2px solid #14b8a6!important}
[data-zr=zone]{outline:2px solid #1f6fd6!important}
[data-zone]{box-shadow:inset 0 0 0 3px #1f6fd6!important}
[data-zx-pin]{outline:3px solid #ffb000!important;outline-offset:-3px!important}
[data-zt]::before{content:attr(data-zt);position:absolute;top:0;left:0;z-index:2147483645;
 font:700 10px/1.3 ui-monospace,Menlo,monospace;color:#fff;padding:0 4px;pointer-events:none;
 white-space:nowrap;border-bottom-right-radius:4px}
[data-zr=absolute]::before{background:#d33a2c}[data-zr=component]::before{background:#1aa06a}
[data-zr=layout]::before{background:#14b8a6}[data-zr=zone]::before{background:#1f6fd6}
[data-zone]::after{content:"\\25a6 " attr(data-zone);position:absolute;top:0;right:0;z-index:2147483645;
 font:700 10px/1.3 ui-monospace,Menlo,monospace;color:#fff;background:#1f6fd6;padding:0 4px;
 pointer-events:none;white-space:nowrap;border-bottom-left-radius:4px}
#zx-ban{position:fixed;top:0;left:0;right:0;z-index:2147483646;background:#001932;color:#cfe4f5;
 font:12px/1.4 ui-monospace,Menlo,monospace;padding:6px 12px;border-bottom:2px solid #0077bf}
#zx-ban b{color:#fff}
#zx-legend{float:right;font:11px/1.4 -apple-system,sans-serif;color:#9ec5e6}
#zx-legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin:0 3px 0 12px;vertical-align:-1px}
#zx-legend i.z{background:#1f6fd6}#zx-legend i.a{background:#d33a2c}#zx-legend i.c{background:#1aa06a}#zx-legend i.l{background:#14b8a6}
body{padding-top:30px!important}
#zx-tip{position:fixed;z-index:2147483647;max-width:360px;background:#001932;color:#e8f1f9;
 font:12px/1.45 -apple-system,sans-serif;padding:9px 11px;border-radius:8px;
 box-shadow:0 6px 22px rgba(0,0,0,.45);pointer-events:none;display:none}
#zx-tip.pin{border:1px solid #0077bf}
#zx-tip .hd{display:flex;align-items:center;gap:6px;margin-bottom:5px}
#zx-tip .ty{font-family:ui-monospace,monospace;font-weight:700}
#zx-tip .badge{font:700 10px/1.5 -apple-system,sans-serif;color:#fff;padding:0 6px;border-radius:9px}
#zx-tip .badge.z{background:#1f6fd6}#zx-tip .badge.a{background:#d33a2c}#zx-tip .badge.c{background:#1aa06a}#zx-tip .badge.l{background:#14b8a6}
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
#zx-tip #zx-pre .ph-layout{color:#04211d;background:#5eead4}
#zx-tip #zx-pre .ph-absolute{color:#2a0808;background:#f87171}
"""

def _overlay_category(t):
    if t == "rawHtml":
        return "raw"
    if t == "zone":
        return "zone"
    if t == "layoutSection":
        return "layout"
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
  +'<span id="zx-legend"><i class="z"></i>zone (Area) <i class="l"></i>composant layout <i class="c"></i>composant <i class="a"></i>chrome &middot; clic = épingler</span>';
 document.body.appendChild(ban);
 var tip=document.createElement('div');tip.id='zx-tip';document.body.appendChild(tip);
 var pinned=null;
 function esc(s){var d=document.createElement('div');d.textContent=s;return d.innerHTML;}
 function role(el){
   // the element's TRUE nature (data-zr) wins over the content band (data-zone): a
   // layoutSection is a content-free LAYOUT COMPONENT, never a "zone" (Julian).
   var r=el.getAttribute('data-zr');
   if(r==='absolute')return{k:'chrome (absolute)',cls:'a'};
   if(r==='layout')return{k:'composant layout',cls:'l'};
   if(r==='component')return{k:'composant',cls:'c'};
   if(el.hasAttribute('data-zone'))return{k:'zone '+el.getAttribute('data-zone'),cls:'z'};
   if(r==='zone')return{k:'zone',cls:'z'};
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
   if(el.getAttribute('data-zr')==='layout')return '[[layout:'+(el.getAttribute('data-zt')||'layoutSection')+']]';
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
   all.forEach(function(x){['data-zt','data-zc','data-zk','data-zr','data-zone','data-zx-pin','data-zx-skin'].forEach(function(a){if(x.removeAttribute)x.removeAttribute(a);});});
   Array.prototype.slice.call(c.querySelectorAll('#zx-ban,#zx-tip')).forEach(function(x){x.remove();});
   return c.outerHTML;
 }
 // ---- lightweight, self-contained HTML syntax highlighter for the raw view ----
 function phSpan(tok){var mm=/\\[\\[(component|layout|zone|absolute):/.exec(tok);var r=mm?mm[1]:'component';
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
   var RE=/<!--[\\s\\S]*?-->|<\\/?[a-zA-Z][\\w:-]*(?:[^>"']|"[^"]*"|'[^']*')*>|\\[\\[(?:component|layout|zone|absolute):[^\\]]+\\]\\]/g;
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
     if(pre.style.display==='none'){var sk=el.getAttribute('data-zx-skin');pre.innerHTML=(sk?('<div style="color:#7ee0a0;font-weight:700;margin-bottom:3px">STOCKE (modele du noeud, aucun blob HTML)</div>'+hl(sk)+'<div style="color:#9ec5e6;font-weight:700;margin:9px 0 3px">SOURCE (mirror)</div>'):'')+hl(rawOf(el));pre.style.display='block';rb.innerHTML='&#9662; Masquer le HTML';pre.scrollIntoView({block:'nearest'});}
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

# ── cardGrid POSITIVE-EVIDENCE GATE (is_card_grid) ────────────────────────────
# Replaces the old permissive "majority of children have >=2 slots" test. That test
# counted a LINK as a slot, so a nav-menu item (label+href) or a logo strip (media+href)
# trivially reached 2 → 51% of discoverasr's 78 cardGrids were navigation chrome and 43%
# were AEM layout grids (measured: 0 genuine card grids). The gate below is intrinsic and
# CMS-agnostic — it reads the node's OWN lifted shape, never a class/framework token except
# the nav-role veto (a whole-token safety net, itself gated on "no per-item heading").
# Refusal is fidelity-safe: the caller falls through to the verbatim wrapper_container/zone
# path (0-DOM preserved). Cross-stack targets held during design: discoverasr 78→~7,
# acquia keeps 7/8 genuine, contentful ~45, supercar/liferay/lesalondelaphoto stay at 0.
_NAV_ROLE_RE = re.compile(
    r"(?:^|[-_ ])(nav|navigation|menu|breadcrumb|hamburger|submenu|dropdown|pagination|tabs?)(?:$|[-_ ])",
    re.I)

def _cg_text(v):
    """Visible text of a FIELD VALUE (values may be HTML). Must read values, never the
    child skeleton — the skeleton holds {{f:body}} markers (~22 chars) that would
    false-fail the substance test on genuine text cards."""
    try:
        return " ".join(BeautifulSoup(str(v or ""), "lxml").get_text(" ", strip=True).split())
    except Exception:
        return ""

def _cg_profile(ch):
    f = ch.get("fields") or {}
    return (bool(f.get("title")),
            any(str(kk).startswith("body") for kk in f),
            bool(ch.get("media")),
            bool(ch.get("link")))

def _cg_substance(ch):
    f = ch.get("fields") or {}
    title_t = _cg_text(f.get("title"))
    body_t = " ".join(_cg_text(f[kk]) for kk in f if str(kk).startswith("body"))
    both = (title_t + " " + body_t).strip()
    return ((bool(ch.get("media")) and len(both) >= 25)   # media WITH text
            or (bool(title_t) and bool(body_t))            # title AND body
            or (len(body_t) >= 60))                        # substantial body

def is_card_grid(cg, classes_str="", key=""):
    """True iff the promoted repeated-sibling container `cg` is genuinely a grid of
    editorial CARDS, on four intrinsic axes + a nav-role veto. Decoupled from the DOM
    (takes a class string, not a bs4 element) so the offline 5-stack replay can call it
    directly against content-load.json instances."""
    kids = cg.get("children") or []
    n = len(kids)
    if n < 3:
        return False
    # 1. link-discounted slots: a CARD carries >=2 NON-LINK slots (title/body*/media).
    #    A nav/logo item is link(+media) only → 1 non-link slot → not a card.
    def _nonlink(ch):
        f = ch.get("fields") or {}
        return bool(f.get("title")) + any(str(kk).startswith("body") for kk in f) + bool(ch.get("media"))
    if sum(1 for ch in kids if _nonlink(ch) >= 2) < max(3, (n + 1) // 2):
        return False
    # 2. structural uniformity: modal (title,body,media,link) profile shared by >=60%.
    profs = [_cg_profile(ch) for ch in kids]
    if collections.Counter(profs).most_common(1)[0][1] < 0.6 * n:
        return False
    # 3. editorial substance (read from field VALUES), majority of children.
    if sum(1 for ch in kids if _cg_substance(ch)) < (n + 1) // 2:
        return False
    # 4. prose payload-density: visible text OUTSIDE interactive controls, per markup byte.
    #    A real card grid is prose-dense; a layout wrapper swallowing widgets is not.
    src = cg.get("skeletonOrig") or cg.get("skeleton") or ""
    if src:
        try:
            soup = BeautifulSoup(src, "lxml")
            # strip only NON-content controls (forms, buttons, nav). Keep <a> text: a
            # card's title/excerpt is often wrapped in a link (<a><h3>…</h3><p>…</p></a>),
            # and stripping it false-killed genuine article cards (contentful blog).
            # nav is caught earlier by the slot test + nav-role veto, so keeping link
            # text here cannot resurrect a menu.
            for t in soup.find_all(["button", "nav", "input", "select", "textarea", "label", "form"]):
                t.decompose()
            prose = len(" ".join(soup.get_text(" ", strip=True).split()))
        except Exception:
            prose = 0
        if prose / len(src) < 0.02:
            return False
    # 5. nav-role veto: a nav/menu-classed container with ZERO per-item headings is a menu,
    #    not a card grid (a genuine card grid's items carry titles, so this never fires on
    #    real cards — it only catches nav that slipped the slot test).
    if _NAV_ROLE_RE.search((classes_str or "") + " " + (key or "")) and not any(p[0] for p in profs):
        return False
    return True

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

def build(project, site, ns, module=None, overlay=False, overlay_src=None):
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
    # LLM ORPHAN ARBITRATION (Julian): attribution rules the LLM posted via
    # /decide {apply_and_rerun, rules} land in scope-rules.json. Each is
    # {match:{key}, attribution:{type[,mode:passthrough]|contentFree|nonRendered}}.
    # The bridge applies them to force a decided attribution for an element the
    # deterministic engine left as an orphan. PLACEMENT/TYPING only — content verbatim.
    attr_rules = {}
    srp = f"{REPO}/projects/{project}/workflow-output/scope-rules.json"
    if os.path.exists(srp):
        try:
            for r in (json.load(open(srp)).get("rules") or []):
                m = r.get("match") or {}
                # match by `signature` = the orphan's detection key (a stable pattern
                # key, e.g. cmp:page_navigation — NOT a page URL, per the /decide lint)
                sig = m.get("signature") or m.get("key")
                if sig and r.get("attribution"):
                    attr_rules[sig] = r["attribution"]
        except Exception as e:
            print(f"  ! scope-rules read: {e}", file=sys.stderr)
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
        # overlay_src (e.g. "frozen"): re-render the overlay from a JS-revealed FROZEN
        # capture (freeze_page.mjs) instead of the raw mirror — for SPAs whose content is
        # revealed by client JS, the script-stripped mirror renders blank; the frozen DOM
        # renders faithfully with NO site JS. Falls back to the mirror when no frozen page
        # exists. Used with overlay-only runs (main() skips writing the content-load), so
        # the CANONICAL content-load (deterministic, from the mirror) is never touched.
        if overlay_src:
            fp = os.path.join(lm, f"{slug}.{overlay_src}.html")
            if os.path.exists(fp):
                lp = fp
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

    def media_leaf(el):
        """A STANDALONE media element (<img>/<picture>) that reached the leaf
        fallback — no component absorbed it (media INSIDE a component is already a
        {{media:N}} marker in its skeleton). Type it `image`: a DAM weakref slot
        with the source markup as the verbatim default (rule 26 media contract).
        Recompose replaces {{media:image0}} with the exact source markup, so an
        UNEDITED node renders byte-identical (0-DOM safe); once an editor picks a DAM
        image it wins. Deterministic + generic — media atoms are universal; fires
        ONLY for a lone media leaf, never for already-lifted media, and only AFTER
        the content-free recognizer (a spacer/divider is caught first)."""
        try:
            name = (el.name or "").lower()
        except Exception:
            return None
        if name not in ("img", "picture"):
            return None
        img = el if name == "img" else el.find("img")
        src = ((img.get("src") if img else "") or "").split("?", 1)[0]
        if not src or src.startswith("data:"):
            return None
        html = rw(str(el), base)
        if len(html) > CAP:
            return None
        unit = {"name": "image0", "orig": html, "src": rw(src, base),
                "alt": (img.get("alt", "") if img else "") or ""}
        fn = os.path.basename(unit["src"].split("?", 1)[0])
        if fn and MIRROR_ASSETS and os.path.isfile(os.path.join(MIRROR_ASSETS, fn)):
            unit["file"] = fn
        return {"type": "image", "parent": None, "promoted": True,
                "skeleton": "{{media:image0}}", "skeletonOrig": html,
                "fields": {}, "media": [unit], "mediaTotal": 1,
                "link": None, "linkTotal": 0, "children": []}

    def text_wrap(el, typ):
        """Arbitrated TEXT atom on an element the standard lift can't reach (inline
        <span>, custom tag): keep the wrapper VERBATIM, lift its inner content into
        {{f:body}}. Recompose splices body raw → byte-exact when unedited (self-
        checked); an edit reflows into the SAME wrapper (0-DOM safe). The LLM
        asserted this is editable text, so the text becomes the field. Refuses to
        swallow widgets/media."""
        try:
            inner = el.decode_contents()
        except Exception:
            return None
        if not (inner or "").strip():
            return None
        if el.find(["form", "script", "style", "iframe", "select", "input",
                    "textarea", "video", "button", "img", "picture", "svg"]):
            return None
        outer = rw(str(el), base)
        inner_rw = rw(inner, base)
        i = outer.find(inner_rw)
        if i < 0 or len(outer) > CAP:
            return None
        skel = outer[:i] + "{{f:body}}" + outer[i + len(inner_rw):]
        if skel.replace("{{f:body}}", inner_rw) != outer:  # byte-exact or nothing
            return None
        return {"type": typ, "parent": None, "promoted": True,
                "skeleton": skel, "skeletonOrig": outer,
                "fields": {"body": inner_rw}, "media": [], "mediaTotal": 0,
                "link": None, "linkTotal": 0, "children": []}

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

    def tag(el, t, key=None, skin=None):
        # overlay: mark the SOURCE element with the type it was emitted as (+ its
        # detection KEY for the cross-page tooltip lookup). Set AFTER skeletonOrig
        # is captured (str(el) at emit time) so the content-load stays clean.
        # `skin` (layoutSection only) = a readable render of the STRUCTURED skin the
        # node actually stores, so the popin shows the stored model, not the source blob.
        if overlay and el is not None:
            el["data-zt"] = t
            el["data-zc"] = _overlay_category(t)  # category (probe counts)
            if skin:
                el["data-zx-skin"] = skin
            # role drives the 3-color scheme: chrome/ABSOLUTE = red, structural
            # container = blue zone, everything else = green component. A layoutSection
            # is a structural container (clean <Area>, stores NO HTML blob) -> blue, but
            # data-zt="layoutSection" labels it distinctly from a verbatim "zone".
            # a layoutSection is a content-free LAYOUT COMPONENT (skin markup + child
            # <Area>), NOT a zone — a zone is a pure <Area> (a LIST of components, no
            # HTML). Distinct role "layout" (teal) so the overlay never mislabels it a
            # "zone" (Julian: "une zone n'a pas de rendu HTML"). "zone" (blue) is reserved
            # for the content BANDS / <Area> regions (data-zone).
            el["data-zr"] = ("absolute" if t == "chrome"
                             else "layout" if t == "layoutSection"
                             else "zone" if t == "zone"
                             else "component")
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
        """The meaningful children to lift out of a container. Phase 4 (re-nesting):
        descend THE NODE through its OWN single-child transparent chain to the
        composition point (so that chain becomes THIS node's skin), then return the
        composition point's DIRECT kids UNDESCENDED. Each kid recurses via emit_node
        into its own nested container — so an asymmetric-celled parent (children at
        different depths, e.g. a nested chain beside a rawHtml sibling) becomes a CLEAN
        layoutSection, and each kid's chain lives in ITS OWN node instead of being
        flattened into the parent skeleton. Order = document order (aligns with
        {{child:N}}). Hidden kids drop (markup stays inline, byte-exact)."""
        comp = descend_transparent(node)
        out = []
        for kd in comp["kids"]:
            if is_hidden_el(kd.get("_el")):
                continue
            out.append(kd)
        return out

    def apply_attribution(node, rule, parent, insts):
        """Apply one LLM attribution to an orphan (placement/typing only, verbatim
        content). Returns True if it consumed the node. Rule shapes:
          {nonRendered:true}            -> carried verbatim, never a zone/component
          {contentFree:true[,type]}     -> content-free block (divider/decoration-like)
          {type:X, mode:'passthrough'}  -> NAMED verbatim component (undecomposable widget)
          {type:X}                      -> try emit_typed(X); fall back to passthrough X"""
        el = node.get("_el")
        if el is None:
            return False
        k = node.get("key")
        if rule.get("nonRendered"):
            t = raw_inst(el, base); t["nonRendered"] = True; t["parent"] = parent
            insts.append(t); return True
        if rule.get("contentFree"):
            name = rule.get("type") or content_free_name(el)
            t = raw_inst(el, base); t["type"] = name; t["contentFree"] = True
            t["parent"] = parent; insts.append(t); used.add(name); cf_types.add(name)
            tag(el, name, k); return True
        typ = rule.get("type")
        if typ:
            if rule.get("mode") != "passthrough":
                t = emit_typed(el, typ, base)
                if t is not None and wired(t) and inst_weight(t) <= CAP:
                    t["parent"] = parent; insts.append(t); used.add(typ)
                    stats["typed"] += 1; tag(el, typ, k); return True
                # text-atom arbitration the standard lift can't reach (inline <span>,
                # custom tag): lift the wrapper's inner content into {{f:body}} —
                # genuinely editable, wrapper verbatim, byte-exact when unedited.
                if typ in _TEXT_ATOM:
                    t = text_wrap(el, typ)
                    if t is not None:
                        t["parent"] = parent; insts.append(t); used.add(typ)
                        stats["typed"] += 1; tag(el, typ, k); return True
            t = raw_inst(el, base); t["type"] = typ; t["parent"] = parent
            insts.append(t); used.add(typ); tag(el, typ, k)
            stats["arbitrated"] = stats.get("arbitrated", 0) + 1
            return True
        return False

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
        # LLM arbitration wins over deterministic categorization: if the LLM posted
        # an attribution for this element's key, apply it (typing/placement only —
        # the content stays verbatim).
        rule = attr_rules.get(k) if k else None
        if rule is not None and apply_attribution(node, rule, parent, insts):
            return
        if parent is None:
            # chrome: emit each DISTINCT chrome block once (dedup by key), routed to
            # a template AbsoluteArea (header/nav/footer); prune the subtree
            if k and (k in site_chrome or sc == "ABSOLUTE"):
                if k not in chrome_done:
                    chrome_done.add(k)
                    chrome.append(raw_inst(node["_el"], base, area_for(k)))
                tag(node["_el"], "chrome", k)  # tag even the deduped repeats
                return
            # site-wide content-free SCAFFOLD (grid overlay, layout rail…): a
            # content-free element present on ~all pages as a SINGLETON (≈ one per
            # page) is TEMPLATE-level markup, not per-page content — emit once,
            # rendered on every page by the template (Julian: "toujours en haut ->
            # vue du template"). site_chrome misses it because that requires a
            # content-BEARING container; this catches the empty ubiquitous scaffold.
            # The singleton test (inst ≈ pages) keeps a REPEATED content-free element
            # (e.g. the many per-page dividers) OUT — those stay divider components.
            e = agg.get(k or "", {})
            pgs = len(e.get("pages", ()) or ())
            if (k and is_content_free(node["_el"]) and pgs >= 0.9 * len(pages)
                    and e.get("inst", 0) <= 1.5 * pgs):
                if k not in chrome_done:
                    chrome_done.add(k)
                    chrome.append(raw_inst(node["_el"], base, "scaffold"))
                tag(node["_el"], "chrome", k)  # site-wide template markup
                return
            if k and R["is_root_wrapper"](k):
                for kd in node["kids"]:  # transparent layout root (top level only)
                    emit_node(kd, insts, depth, parent)
                return
        # accept base-library types AND marker-derived types (data-component/itemtype
        # → the author's own type name, hoisted to high confidence in library_map)
        marker_typed = bool(k and k.startswith("cmp:"))
        if lib and conf >= 0.5 and (lib in ZD.LIBRARY_TYPES or marker_typed):
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
            # CONFIDENT text atom whose byte-exact lift found nothing to extract: the
            # source CMS literally named this element (…description / …content / a
            # heading class), decompose just can't lift from a <div>/<span> (not a
            # block tag). Rather than strand it as a verbatim orphan, lift its inner
            # content to {{f:body}} — same mechanism as arbitration text_wrap, run
            # deterministically. Only for a genuine text LEAF (no typed descendants):
            # a text-atom container still descends into a zone below. Byte-exact
            # self-checked, so 0-DOM holds. (Measured: clears ~66% of supercar's
            # stranded editable text with zero per-site rules.)
            if lib in _TEXT_ATOM and not subtree_has_typed(node):
                tw = text_wrap(node["_el"], lib)
                if tw is not None:
                    tw["parent"] = parent
                    insts.append(tw)
                    used.add(lib)
                    stats["typed"] += 1
                    stats["textleaf"] = stats.get("textleaf", 0) + 1
                    tag(node["_el"], lib, k)
                    return
        too_big = node["size"] > 300 or len(str(node["_el"])) > CAP
        if depth < 10 and node["kids"] and (subtree_has_typed(node) or too_big):
            # #3 SELECTIVE PARENT RECOGNITION: a KEYLESS container that is a strong
            # repeated-sibling listing (emit_typed→decompose_group→find_repeated_items
            # lifts >=3 same-signature content items) is promoted to a typed cardGrid —
            # its items become card child-nodes with lifted title/body/media/link —
            # rather than scattered as a structural zone. This only reaches keyless /
            # low-confidence nodes (a confidently-typed listing already returned in the
            # typed branch), so it never touches an already-typed cardGrid. emit_typed
            # self-checks recompose==source byte-for-byte (returns None otherwise), so
            # 0-DOM holds. Model-elegance upgrade of the #2 flat floor (Julian: #3
            # selective on strong listing/card patterns — exactly acquia's blog cards).
            cg = emit_typed(node["_el"], "cardGrid", base)
            cg_kids = (cg.get("children") if cg else None) or []
            # A repeated-sibling container is promoted to cardGrid only if it PASSES the
            # positive-evidence gate is_card_grid() (link-discounted slots + uniformity +
            # substance-from-field-values + prose density + nav-role veto). This replaces
            # the old ">=2-slot majority" test that counted a LINK as a slot and so typed
            # navigation chrome and layout grids as cardGrids. A refusal is auditable
            # (stats["cardGridRefused"]) and falls through to the verbatim zone path.
            if cg is not None and wired(cg) and len(cg_kids) >= 3 \
                    and inst_weight(cg) <= CAP:
                if is_card_grid(cg, " ".join(node["_el"].get("class", []) or []), k):
                    cg["parent"] = parent
                    insts.append(cg)
                    used.add("cardGrid")
                    stats["typed"] += 1
                    stats["container"] = stats.get("container", 0) + 1
                    stats["cardGridPromoted"] = stats.get("cardGridPromoted", 0) + 1
                    # residue: a card grid that PASSES the intrinsic gate yet is a huge
                    # page-swallower (uniform+substantive children but a layout monster) —
                    # surface it for the model gate instead of letting it pass silently.
                    if inst_weight(cg) > 8000:
                        stats["cardGridOversize"] = stats.get("cardGridOversize", 0) + 1
                    tag(node["_el"], "cardGrid", k)
                    return
                # NOT a card grid: count the refusal (per merge-backlog doctrine) and fall
                # through to wrapper_container/zone — children re-emit as their own nodes.
                stats["cardGridRefused"] = stats.get("cardGridRefused", 0) + 1
            ek = extraction_children(node)  # descend transparent single-child wrappers
            # empty container (Phase 4: composition had no liftable kids) -> NOT a promoted
            # zone (that is the empty-shell G1 failure); fall through to content-free /
            # verbatim rawHtml, which renders byte-exact and carries no editable props.
            w = wrapper_container(node, ek) if ek else None
            if w is not None:
                idx = len(insts)
                # Phase 1b/1c: a pure wrapper -> byte-parity layoutSection (skin stored
                # STRUCTURED, children in <Area>(s), NO HTML blob in the node — the P1 fix).
                # Gated by the layout recognizer (pure, >=2 slots, not a text run) AND
                # _try_layout_section (1b single Area = contiguous children; 1c columns =
                # uniform sibling cells). Celled-asymmetric / impure wrappers keep the
                # verbatim zone (fidelity-first). layoutConvertible = recognizer ceiling;
                # layoutSectionEmit = actual conversions.
                try:
                    _lp = LR._recognize_layout(node["_el"], ns)
                except Exception:
                    _lp = None
                if _lp is not None:
                    stats["layoutConvertible"] = stats.get("layoutConvertible", 0) + 1
                # _try_layout_section is the byte-parity-safe operative gate (pure wrapper,
                # >=1 contiguous/columns child, no field markers); a single-child chain now
                # becomes a 1-Area layoutSection instead of a verbatim zone. Not gated on
                # the recognizer (which descends past a lone leaf to 0 children).
                lay = _try_layout_section(w.get("skeleton") or "")
                if lay is not None:
                    insts.append({"type": "layoutSection", "parent": parent,
                                  "promoted": True, "layout": lay,
                                  "sourceClasses": (_lp.get("sourceClasses") if _lp else None)})
                    used.add("layoutSection")
                    stats["layoutSectionEmit"] = stats.get("layoutSectionEmit", 0) + 1
                    if lay.get("cellOpen") is not None:
                        skin_disp = (f'{lay["open"]}  ⟨{lay["areas"]}× cellule '
                                     f'{lay["cellOpen"]}…{lay["cellClose"]} · Area⟩  {lay["close"]}')
                    elif lay.get("gaps") is not None:
                        skin_disp = (f'{lay["open"]}  ⟨Area · {len(ek)} sous-composant(s), '
                                     f'{len(lay["gaps"])} glu invisible préservée⟩  {lay["close"]}')
                    else:
                        skin_disp = (f'{lay["open"]}  ⟨Area · {len(ek)} sous-composant(s)⟩  '
                                     f'{lay["close"]}')
                    tag(node["_el"], "layoutSection", k, skin=skin_disp)
                else:
                    w["parent"] = parent
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
        m = media_leaf(node["_el"])  # lone <img>/<picture> → editable DAM slot (verbatim default)
        if m is not None:
            m["parent"] = parent
            insts.append(m)
            used.add("image")
            stats["typed"] += 1
            stats["wired"] += 1
            tag(node["_el"], "image", k)
            return
        t = lift_or_raw(node["_el"])
        t["parent"] = parent
        if t.get("type") == "rawHtml":
            # #2 KEYLESS-TEXT FLOOR (deterministic — NO LLM → ZERO arbitrations at scale):
            # what lift_or_raw could NOT lift richly (section-lift + text-leaf both
            # failed) is about to be stranded as an opaque orphan. If it is a genuine
            # text LEAF (no typed descendants) carrying >= _TEXT_FLOOR chars, lift its
            # text to editable richText instead — keyless inline <span>/<a>, or a
            # keyed elt with no confident type. text_wrap keeps the wrapper VERBATIM
            # (href/attrs intact) and is byte-exact self-checked → 0-DOM holds. This
            # runs AFTER lift_or_raw so it never preempts the richer `section`/text-leaf
            # lift. "Editable-but-FLAT"; #3 (parent recognition) upgrades repeated
            # flats into card fields (Julian: #2 floor everywhere + #3 selective).
            if not subtree_has_typed(node) and \
                    len(node["_el"].get_text(" ", strip=True)) >= _TEXT_FLOOR:
                tw = text_wrap(node["_el"], "richText")
                if tw is not None:
                    tw["parent"] = parent
                    insts.append(tw)
                    used.add("richText")
                    stats["textleaf"] = stats.get("textleaf", 0) + 1
                    stats["flatlift"] = stats.get("flatlift", 0) + 1
                    tag(node["_el"], "richText", k)
                    return
            # editorial ORPHAN: rendered verbatim (0-DOM safe) but NOT attributed to a
            # meaningful type — the deterministic categorization couldn't place it.
            # Surface it (orphans.json) with the detector's low-confidence guess so an
            # LLM can arbitrate the attribution at the model gate (Julian, 2026-07-05).
            t["orphan"] = True
            t["orphanKey"] = k
            t["orphanCand"] = lib          # detector's best type guess (may be None)
            t["orphanConf"] = round(conf, 2)
        insts.append(t)
        tag(node["_el"], t["type"], k)

    max_zones = 0
    for slug, crawl_body in pages:
        body = slug2body.get(slug, crawl_body)  # prefer localised markup (local asset refs)
        ann = ZD.annotate(body, stemdf, keep_el=True)
        # UNIFY the content-root with the SHELL (verbatim-first, 0-DOM): page_shell
        # owns <body>→<main>→wrappers verbatim and places the content Area at the
        # SAME content-root SE.main_content_root() computes. Zones MUST therefore be
        # THAT content-root's children — else <main>/wrappers double-render (measured:
        # <main> ×2). Empty siblings (grid overlay, spacers) sit ABOVE the content-root
        # and are carried by the shell's innerLevels before/after — never zones.
        root = content_root(ann, site_chrome)  # fallback
        if hasattr(body, "find"):  # localised bs4 body (annotate kept _el in this soup)
            try:
                croot_el, _chain = SE.main_content_root(body.find("main") or body)
                elmap = {}
                def _walk(nd):
                    elmap[id(nd.get("_el"))] = nd
                    for kd in nd["kids"]:
                        _walk(kd)
                _walk(ann)
                if id(croot_el) in elmap:
                    root = elmap[id(croot_el)]
            except Exception as ex:
                print(f"  ! content-root unify {slug}: {ex}", file=sys.stderr)
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
        # A2: collapse single-child layoutSection chains (byte-exact wrapper-noise removal)
        insts = fuse_single_child_layouts(insts)
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
                     if i.get("type") not in ("zone", "layoutSection")
                     and not i.get("nonRendered")]
    nzone = sum(1 for i in all_insts if i.get("type") in ("zone", "layoutSection"))
    nnonrender = sum(1 for i in all_insts if i.get("nonRendered"))
    # FOLD-AWARE denominator: a container's lifted items live in its `children` array,
    # NOT as separate instances. Counting only top-level instances would make genericShare
    # RISE when #3 folds typed cards into a cardGrid (the rich items leave the denominator,
    # inflating the generic ratio) — punishing a BETTER model. Card children are typed
    # content, so count them in the denominator (never generic): genericShare then reflects
    # true editorial richness and #3 can only lower it.
    nchild = sum(len(i.get("children") or []) for i in content_insts)
    ninst = len(content_insts)
    # `decoration` (anonymous content-free residue) is still generic — it needs an
    # S4 name; `divider`/`spacer` are recognized so they count as meaningful.
    ngen = sum(1 for i in content_insts
               if i["type"] in ("section", "rawHtml", "decoration"))
    generic_share = ngen / max(ninst + nchild, 1)
    violations = []
    if generic_share >= 0.5:
        violations.append({"nodeType": f"{ns}:rawHtml",
                           "reason": f"{generic_share:.0%} of CONTENT instances are generic "
                                     f"section/rawHtml/decoration (editorially weak — few meaningful types)"})
    naming_quality = "poor" if generic_share >= 0.7 else ("mixed" if generic_share >= 0.4 else "good")

    # ── MERGE BACKLOG — the primary piloting/reporting indicator of how well the
    # FIRST zoning went (Julian, 2026-07-05). Orphans are fidelity-safe (verbatim,
    # 0-DOM) so the count alone lies (it is padded ~4-5× by inert widget/media/layout
    # markup that is CORRECTLY verbatim). What matters editorially is the RESIDUE an
    # editor still cannot reach as a field, expressed as two headline counters:
    #   signaturesToMerge      = distinct KEYED signatures carrying editable text —
    #                            one attribution/recognizer rule clears ALL its instances
    #   editableContentsToMerge= orphan instances carrying real editable text (>=8 chars)
    # plus a priority worklist (by stranded chars) so the operator/LLM attacks the
    # biggest editorial gaps first. Keyless editable orphans are tracked apart: they
    # have no signature to rule on and need parent recognition, not a merge rule.
    def _vtext(h):
        try:
            return " ".join(BeautifulSoup(h or "", "lxml").get_text(" ", strip=True).split())
        except Exception:
            return ""
    def _inst_html(i):
        return (i.get("fields", {}) or {}).get("html") or i.get("skeletonOrig") or i.get("skeleton") or ""
    MERGE_MIN_CHARS = 8
    by_sig, stranded_chars, typed_text = {}, 0, 0
    editable_contents = keyless_editable = 0
    for i in content_insts:
        txt = _vtext(_inst_html(i))
        if not i.get("orphan"):
            typed_text += len(txt)
            continue
        tl = len(txt)
        sig = i.get("orphanKey")
        m = re.match(r"\s*<([a-zA-Z0-9]+)", _inst_html(i))
        key = sig or ("keyless:" + (m.group(1).lower() if m else "?"))
        e = by_sig.setdefault(key, {"signature": sig, "keyless": not sig,
                                    "instances": 0, "strandedChars": 0, "sample": ""})
        e["instances"] += 1; e["strandedChars"] += tl
        if not e["sample"] and txt:
            e["sample"] = txt[:60]
        if tl >= MERGE_MIN_CHARS:
            editable_contents += 1
            stranded_chars += tl
            if not sig:
                keyless_editable += 1
    signatures_to_merge = sum(1 for e in by_sig.values()
                              if not e["keyless"] and e["strandedChars"] >= MERGE_MIN_CHARS)
    worklist = sorted((e for e in by_sig.values() if e["strandedChars"] > 0),
                      key=lambda e: -e["strandedChars"])[:15]
    merge_backlog = {
        "signaturesToMerge": signatures_to_merge,
        "editableContentsToMerge": editable_contents,
        "strandedChars": stranded_chars,
        "strandedShare": round(stranded_chars / max(1, stranded_chars + typed_text), 3),
        "keylessEditable": keyless_editable,
        "orphansTotal": sum(1 for i in content_insts if i.get("orphan")),
        "worklist": worklist,
        # cardGrid positive-evidence gate audit (is_card_grid): promoted = kept as
        # cardGrid, refused = fell through to verbatim zone (fidelity-safe, per-card
        # editability deferred to the merge worklist above), oversize = passed the gate
        # but is a >8KB page-swallower needing the altitude backstop (follow-up).
        "cardGridPromoted": stats.get("cardGridPromoted", 0),
        "cardGridRefused": stats.get("cardGridRefused", 0),
        "cardGridOversize": stats.get("cardGridOversize", 0),
        # Phase 1b real-pipeline chiffrage: zones the generic layout recognizer would
        # convert to byte-exact <Area> components (count-only; emit still skeleton).
        "layoutConvertible": stats.get("layoutConvertible", 0),
        "layoutSectionEmit": stats.get("layoutSectionEmit", 0),
        "zoneInstances": stats.get("zone", 0),
    }

    manifest = {"instanceTypeMap": itm, "passthroughType": f"{ns}:rawHtml",
                "components": comps, "zones": max_zones, "templates": [],
                "zoneInstances": nzone, "nonRenderedInstances": nnonrender,
                "contentFreeTypes": sorted(f"{ns}:{c}" for c in cf_types),
                "namingQuality": naming_quality, "namingViolations": violations,
                "genericShare": round(generic_share, 3),
                "mergeBacklog": merge_backlog,
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
    overlay_src = sys.argv[sys.argv.index("--overlay-src") + 1] if "--overlay-src" in sys.argv else None
    content, manifest, used, stats = build(project, site, ns, module, overlay=overlay,
                                           overlay_src=overlay_src)
    if overlay:
        lm = f"{REPO}/projects/{project}/workflow-output/local-mirror"
        n = len([f for f in os.listdir(lm) if f.endswith(".overlay.html")]) if os.path.isdir(lm) else 0
        print(f"  -> {n} zone-overlay page(s) written to {lm}/<slug>.overlay.html")
    if overlay_src:
        # overlay-only run (re-render overlays from a JS-revealed source, e.g. frozen):
        # do NOT rewrite the canonical content-load / manifest / orphans — they stay
        # deterministic from the mirror. The overlays were already written inside build().
        print(f"  -> overlay-src={overlay_src}: content-load left untouched (overlay-only run)")
        return
    cl_path = os.path.join(REPO, "orchestration", "content", f"{project}.content-load.json")
    mf_dir = os.path.join(REPO, "projects", project, "workflow-output")
    os.makedirs(mf_dir, exist_ok=True)
    mf_path = os.path.join(mf_dir, "component-manifest.json")
    json.dump(content, open(cl_path, "w"), ensure_ascii=False, indent=1)
    json.dump(manifest, open(mf_path, "w"), ensure_ascii=False, indent=1)
    # orphans.json — the editorial residue for LLM arbitration at the model gate:
    # elements rendered verbatim (0-DOM safe) that the deterministic categorization
    # could NOT attribute to a meaningful type. Each carries context (page, zone,
    # detector guess, markup snippet) so an LLM can decide the attribution and post
    # it back as scope-rules. NOT content generation — placement only (Julian).
    orphans = []
    for slug, pg in content["pages"].items():
        for i in pg["instances"]:
            if not i.get("orphan"):
                continue
            html = (i.get("fields", {}) or {}).get("html", "")
            snip = " ".join(html.split())
            orphans.append({
                "page": slug, "zone": i.get("zone"), "key": i.get("orphanKey"),
                # `signature` is what to put in the arbitration rule's match (the
                # /decide lint forbids matching by page URL / key — signature is a
                # stable pattern key that recurs across pages)
                "signature": i.get("orphanKey"),
                "candidate": i.get("orphanCand"), "confidence": i.get("orphanConf"),
                "reason": "no liftable fields/text — verbatim rawHtml fallback",
                "size": len(html), "snippet": snip[:400]})
    backlog = manifest.get("mergeBacklog", {})
    json.dump({"count": len(orphans), "mergeBacklog": backlog, "orphans": orphans},
              open(os.path.join(mf_dir, "orphans.json"), "w"), ensure_ascii=False, indent=1)
    if orphans:
        print(f"  -> {len(orphans)} editorial orphan(s) for arbitration -> orphans.json", file=sys.stderr)
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
    b = manifest.get("mergeBacklog", {})
    print(f"  MERGE BACKLOG (zoning quality): {b.get('signaturesToMerge', 0)} signature(s) to merge, "
          f"{b.get('editableContentsToMerge', 0)} editable content(s) stranded "
          f"({100 * b.get('strandedShare', 0):.1f}% of editable text; "
          f"{b.get('keylessEditable', 0)} keyless → need parent recognition)")
    print(f"  -> {cl_path}")
    print(f"  -> {mf_path}")

if __name__ == "__main__":
    main()
