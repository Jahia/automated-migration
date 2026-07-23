# SegDSL — mode assist « dernier recours » (DSL de découpe bornée composée par le LLM)

**Statut :** plan validé par Julian (2026-07-05) — construire l'option #2, pilotée sur discoverASR.
**Décision amont :** cf. la discussion des 3 formes de « mode manuel » (règles → DSL → script). Retenu = **#2 (DSL déclarative bornée)**. Le **#3 (script Python par site)** est écarté sauf quarantaine stricte.

---

## 0. Principe directeur

Le LLM ne segmente **pas** en écrivant du code. Il **compose une liste ordonnée d'opérations déclaratives** tirées d'un vocabulaire **générique, borné, testé cross-stack**. Le moteur applique ces opérations de façon déterministe et **reste propriétaire de tous les invariants** (recompose byte-exact, gates G1/G2/G6).

- **SÉLECTION** = par-site (donnée auditée).
- **OPÉRATEURS** = génériques (code testé sur les 5 stacks).

C'est le prolongement direct de l'arbitrage existant (`apply_attribution` + `scope-rules.json` + decide `repatch`), pas un greenfield. La seg-plan n'est **qu'un proposeur de plus**, au même titre que heuristique / vision.

---

## 1. Vocabulaire (petit et gelé — ~7 opérateurs)

Chaque op est **placement / typage / frontière uniquement**. Aucun opérateur n'écrit du contenu → le garde-fou « never generate content » est **structurellement impossible à violer**, pas seulement interdit.

| Opérateur | Effet | Cible du bug discoverASR |
|---|---|---|
| `route_absolute(sel, area)` | envoie un sous-arbre vers une AbsoluteArea (header/nav/footer) | les 40 nav / hamburger |
| `dissolve(sel)` | `descend_transparent` : supprime un wrapper de layout, reparent les enfants dans la zone | `aem-Grid` / `responsivegrid` |
| `split(sel, at=child|selector)` | coupe un conteneur en N zones aux frontières d'enfants | monstres `container-structure` (66–98 Ko) |
| `promote(sel, as=<type>, childAs=<type>)` | force un type composant + lift des enfants | vraies grilles (`featured-voucher-3tiles`) |
| `leaf(sel, as=richText|image|rawHtml)` | traite un sous-arbre comme une feuille éditable unique / verbatim | résidus texte |
| `group(sel, every=N)` | regroupe des frères répétés en un composant | listings ratés |
| `widget(sel)` | marque un sous-arbre script-driven non-contributif (verbatim, hors dénominateur G1) | forms / filtres |

**Langage de sélecteur borné** (pas de code arbitraire) :
`tag`, `class~=substr`, `id`, `role`, `nth`, `within(sel)` (ancêtre), `has(sel)` (descendant), `area` (header/footer/main depuis le shell), `size>N`/`size<N` (octets skeleton), `repeated>=N` (compte de frères same-signature), `textDensity<x`.
Compilé sur l'arbre déjà annoté par le bridge.

> **Frontière #2 ↔ #3 :** ce vocabulaire reste **déclaratif et non-Turing-complet**. Si un site réclame un 8ᵉ opérateur, on tranche d'abord : *générique* (on l'ajoute + tests 5 stacks) ou *hack site* (on refuse).

---

## 2. Architecture / points d'insertion (incrémental)

- **Artefact** : `projects/<proj>/workflow-output/segmentation-plan.json` — liste ordonnée d'ops. Donnée auditée, versionnée (sur-ensemble de `scope-rules.json`).
- **Bridge** : `zone_to_contentload --seg-plan <file>` — après la reco heuristique, applique les ops dans l'ordre ; **chaque op repasse par le self-check `emit_typed` recompose==source** ; une op qui violerait le byte-exact est **refusée + loggée**, jamais appliquée silencieusement → 0-DOM safe par construction. Généralise `apply_attribution` en dispatcher d'opérateurs.
- **Moteur** : nouvelle decide-action au model gate — `decide {action:'segment', ops:[...]}` (analogue à `repatch`) → écrit la seg-plan, re-run le bridge, re-run les gates. Entièrement audité.
- **Le moteur reste garant** de G1/G2/G6 + byte-exact.

---

## 3. Garde-fous câblés dans le design (validés Julian)

1. **Never generate content** : aucun opérateur n'a de primitive d'écriture de contenu (impossible, pas juste interdit).
2. **0-DOM safe** : chaque op passe le gate recompose byte-exact ; refus → fallback verbatim.
3. **Dette d'assist mesurée** : le manifest enregistre `nodesPlacedBySegPlan / nodesPlacedByHeuristic` → indicateur objectif d'éloignement du générique (comme `mergeBacklog`). Une seg-plan volumineuse est signalée.
4. **Quarantaine + critère d'escalade** : mode activé **seulement** si le model gate reste rouge après N tentatives génériques bornées ; marqué non-générique ; jamais le chemin par défaut.
5. **Opérateurs génériques + testés 5 stacks** ; seuls sélecteurs + composition sont par-site.

---

## 4. Phasage

- **Phase 0 — prérequis (presque fait).** Clore le fix générique cardGrid (décision backstop) et **mesurer le résidu discoverASR** (5 monstres + borderline) = la cible de la seg-plan. *Si le générique suffisait, on ne construirait pas le DSL.*
- **Phase 1 — spec.** Geler le vocabulaire (ops) + grammaire de sélecteur dans `orchestration/SEGDSL-SPEC.md`. Livrable : spec + exemples. **Précédée du pressure-test cross-stack (option B).**
- **Phase 2 — moteur d'ops.** Matcher + opérateurs dans le bridge, chacun self-checké byte-exact, chacun **unit-testé sur fixtures des 5 stacks**. Mode `--seg-plan`.
- **Phase 3 — surface moteur.** decide-action `segment` + artefact seg-plan + métrique dette d'assist + affichage au model gate (overlay montre seg-plan vs heuristique).
- **Phase 4 — pilote discoverASR.** Composer la seg-plan discoverasr : `route_absolute` nav → header, `dissolve` aem-Grid, `split`/`leaf` les monstres, `promote` les vraies grilles. Mesure : monstres → 0, coverage ↑, fidélité/0-DOM verts, dette d'assist enregistrée. **Valide aussi que le vocabulaire est suffisant ET générique.**
- **Phase 5 — durcissement.** Doc du mode, critère d'escalade câblé au model gate, itération du vocabulaire uniquement par généralisation.

---

## 5. Risques / questions ouvertes

- **Creep du vocabulaire** : le garder petit ; toute nouvelle op passe par « générique + tests 5 stacks ».
- **Ordre / interaction des ops** : pipeline ordonné, chaque op voit le résultat de la précédente (déterministe).
- **Expressivité sélecteur vs sûreté** : sélecteurs bornés seulement ; pas d'XPath / code arbitraire.
- **La ligne #2 ↔ #3** : si la DSL dérive vers du Turing-complet, on est retombé dans le script — vigilance à chaque ajout.

---

## 6. État du fix générique cardGrid (contexte Phase 0)

Livré + validé cette session (non committé) :
- `zone_to_contentload.py` : `is_card_grid()` (4 axes intrinsèques + veto nav-role) remplace le test `_slots ≥ 2` ; audit `cardGrid{Promoted,Refused,Oversize}` dans `mergeBacklog` ; fix densité (ne plus stripper le texte des `<a>`).
- `zone_detect.py:438` : token nu `"grid"` retiré de `library_map` (bug voie #1 rattrapé par la validation cross-stack — la synthèse le croyait inerte, faux sur contentful).
- `test_zone_detect.py` : régression anti-overfit verrouillée.
- **Résultat discoverASR : cardGrid 78 → 11** (40/40 nav tués, méga-composant adoor-apartment éclaté). **Résidu = 5 monstres `container-structure`/`wrap` (66–98 Ko) + borderline** → cible du backstop générique OU de la SegDSL.
