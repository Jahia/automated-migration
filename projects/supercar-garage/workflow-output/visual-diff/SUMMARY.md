# Visual / structural fidelity — supercar-garage vs ultimate-supercar-garage.com

Final sweep (fidelity.sh, headings + repeated-structure coverage vs cached reference).

## Scorecard
- Total sitemap pages: 36
- Content present (>400 chars live): 36 / 36 PASS
- Fidelity PASS (>=85% headings, clean reference): 21
- Fidelity FAIL (<85%, clean reference): 0
- Fidelity UNSCORABLE: 15 (6 JS-gated near-empty references + 9 pages with no captured original)
- cnd-patterns gate: PASS
- no-url-images gate: PASS

## 0 critical gaps
No page with a usable reference falls below threshold. Home: 11/11 headings + 3/3 card structures (100%).
Lowest scored page: evenement/les-univers 92% (missing 1 heading "préparateurs marchands d'exception").

## Unscorable (reference-side limitation, not a module defect)
JS-gated reference (source renders body client-side; cached snapshot near-empty):
exposants-et-animations, .../calendrier-des-animations, .../liste-des-exposants,
actualites/etudiant, presse/accreditation-presse, presse/accreditation-influence.
No captured original (new/added page): espace-exposant/pourquoi-exposer,
espace-exposant/offres-de-stand-..., actualites/ultimate-supercar-garage-en-images,
presse/kit-media, presse/communique-de-presse(+annonce, constructeurs, tendance-supercar, journee-presse).

To score/perfect these, re-capture the references via a rendered-DOM browser grab (Chrome MCP).
