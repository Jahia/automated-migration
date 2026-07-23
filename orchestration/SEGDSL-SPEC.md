# SEGDSL-SPEC — vocabulaire gelé (Phase 1)

**Statut :** GELÉ le 2026-07-05 (Julian). Issu du plan [SEGDSL-PLAN.md](SEGDSL-PLAN.md) + pressure-test cross-stack (5 stacks, run `wf_cd395e30-83d`).
**Verdict du pressure-test :** GO. 9 opérateurs (7 originaux nécessaires — chacun utilisé par ≥2 stacks — + 2 imposés par la preuve). **0 gap Turing-complet sur les 5 stacks** → la suffisance déclarative du DSL est une propriété *observée*, pas un pari.

---

## 1. Contrat (#2 — DSL déclarative bornée)

Le LLM compose une **liste ordonnée d'opérations déclaratives** tirées de ce vocabulaire gelé. Le moteur les applique déterministiquement et **reste propriétaire des invariants** (recompose byte-exact, gates G1/G2/G6). SÉLECTEURS = donnée par-site auditée ; OPÉRATEURS = code générique testé cross-stack. La seg-plan (`projects/<proj>/workflow-output/segmentation-plan.json`) n'est **qu'un proposeur de plus**, au même titre que heuristique/vision.

**Le DSL reste déclaratif et non-Turing-complet.** Confirmé : aucun résidu des 5 stacks n'a exigé de logique conditionnelle/itérative/positionnelle. Un résidu qui l'exigerait sort de #2 (→ repatch/humain), il n'est pas forcé dans une op.

---

## 2. Opérateurs (9 — gelés)

Chaque op est **placement / typage / frontière / suppression uniquement**. **Aucun opérateur n'écrit du contenu** → « never generate content » est structurellement impossible à violer.

| # | Signature | Sémantique | Garde-fou invariant |
|---|---|---|---|
| 1 | `route_absolute(sel, area=header\|nav\|footer)` | route un sous-arbre chrome vers une AbsoluteArea de template | recompose==source du reste ; le sous-arbre routé rend à l'identique dans l'area |
| 2 | `dissolve(sel)` | supprime un wrapper de layout, reparent les enfants dans la zone (`descend_transparent`) | recompose==source (le wrapper n'ajoute pas de markup rendu) |
| 3 | `split(sel, at=child\|<selector>\|keep=has(repeated>=N))` | coupe un conteneur en N zones aux frontières d'enfants | recompose==source (concat des morceaux == original) |
| 4 | `promote(sel, as=<type> [,childAs=<type>])` | force un type composant ; lift optionnel des enfants | `emit_typed` recompose==source, sinon refus → verbatim |
| 5 | `leaf(sel, as=richText\|image\|rawHtml)` | traite un sous-arbre comme une feuille éditable unique / verbatim | `{{f:body}}` splice l'identité → byte-exact |
| 6 | `group(sel, every=N)` | regroupe des frères **same-signature** répétés en un composant | recompose==source |
| 7 | `widget(sel)` | marque un sous-arbre script-driven non-contributif (verbatim, **hors dénominateur G1**) | verbatim → byte-exact |
| **8** | `drop(sel)` | **prune** un sous-arbre entièrement (phantom / empty-shell) | ⚠️ **guard spécial — voir §4** |
| **9** | `chrome(sel, slot=pageTop\|pageBottom)` | épingle une chrome **éditable page-locale** (breadcrumb/pager) en haut/bas de la zone main | recompose==source à la position épinglée |

**Distinction 1 vs 9 :** `route_absolute` = chrome *site-wide* → AbsoluteArea de template (header/nav/footer, rendu une fois pour tout le site). `chrome` = chrome *page-locale éditable* (breadcrumb, pager, barre utilitaire) → épinglée en haut/bas de CETTE page, éditable en place.

---

## 3. Grammaire de sélecteur (bornée — pas de code/XPath)

```
tag                 nom de balise
class~=substr       la classe contient le substring
id                  identifiant
role                attribut role
nth                 index parmi les frères
within(sel)         a un ANCÊTRE matchant sel
has(sel)            a un DESCENDANT matchant sel
area                header | footer | main (depuis le shell)
size>N | size<N     octets de skeleton
repeated>=N         compte de frères same-signature
textDensity<x       densité de prose hors contrôles interactifs

# borne de frontière data-driven (réutilise repeated>=N — reste déclaratif) :
keep=has(repeated>=N)   split garde le sous-arbre contenant le cluster de N cartes répétées,
                        largue le reste. Le MOTEUR choisit la région depuis la donnée
                        (pas de sélecteur par-instance). C'est ce qui garde les 3 monstres
                        container-structure de discoverASR DANS #2 plutôt que #3.
```

---

## 4. Garde-fous (validés Julian)

1. **Never generate content** — aucun opérateur n'a de primitive d'écriture de contenu. Impossible, pas juste interdit.
2. **0-DOM / fidélité par op** — chaque op (sauf `drop`) repasse le self-check `recompose == source` ; échec → refus → fallback verbatim `rawHtml`. Fidélité avant contribution.
3. **`drop` — guard « rend-rien » STRICT (choix Julian).** `drop` est la seule op qui supprime du markup, donc `recompose == source` est inapplicable par construction. Contrat : **un `drop` est refusé sauf si le sous-arbre ciblé ne rend RIEN de visible** — 0 texte visible **ET** 0 media **ET** 0 pixel rendu (vrai empty-shell / phantom). Un sélecteur trop large qui toucherait un sous-arbre rendu est **refusé + loggé**, jamais appliqué. `drop` ne prune donc que ce qui, retiré, laisse le rendu byte-identique.
4. **Dette d'assist mesurée** — le manifest enregistre `nodesPlacedBySegPlan / nodesPlacedByHeuristic` par site → indicateur objectif d'éloignement du générique (cf. `mergeBacklog`). Une seg-plan volumineuse est signalée.
5. **Quarantaine + critère d'escalade** — mode activé **seulement** si le model gate reste rouge après N tentatives génériques bornées ; marqué non-générique ; jamais le chemin par défaut.
6. **Opérateurs génériques + testés 5 stacks** (Phase 2 : unit-tests par op sur fixtures des 5 stacks) ; seuls sélecteurs+composition sont par-site.

---

## 5. Nécessité — preuve cross-stack (audit)

Chaque op est exercée par ≥2 stacks pour du résidu éditorial réel (aucune coupée pour non-usage) :

| Op | Stacks | Volume notable |
|---|---|---|
| `route_absolute` | discoverasr, lesalondelaphoto, acquia | disco 920 nav + 51 footer + 60 chrome |
| `dissolve` | contentful, acquia | acquia **426** (op la plus porteuse du stack) |
| `split` | contentful, supercar | supercar 3 page-swallowers |
| `promote` | contentful, acquia, supercar | acquia 108 cartes ; contentful 66 mistypes |
| `leaf` | supercar, acquia, lesalondelaphoto | — |
| `group` | acquia, supercar, lesalondelaphoto | acquia 33+ card-runs |
| `widget` | contentful, supercar, acquia, lesalondelaphoto | l'op la plus universelle |
| `drop` (NEW) | supercar (41), lesalondelaphoto (59) | empty-shells/phantoms G1 |
| `chrome` (NEW) | lesalondelaphoto (100) | breadcrumb/pager page-local |

---

## 6. Limites connues (documentées, non corrigées)

- **`every=N` / `repeated>=N` supposent des frères same-signature.** Les interleaves A-B-A-B (paires Q&R d'accordéon) sont un edge connu (déjà en nœuds enfants corrects, juste non appariés). Non corrigé pour un cas borderline.
- **Pas de sélecteur de field-set** — les field-triples parallèles à plat ne sont pas adressables. Op `fanout(sel, byFieldSuffix)` **parquée** (1 stack, trivial ; ré-évaluée si un 2e stack l'exhibe).
- **`reparent(sel, into=)` REJETÉE** — supercar-only, le but contribution est atteint par `group`+`promote` ; le parent JCR exact est cosmétique. Near-hack.
- **Pages sans arbre d'instances décomposé** (ex. page tombée sur l'adapter générique, 0 instance) → **hors contrat SegDSL par construction** (rien où accrocher un sélecteur). Route au repatch amont, pas à une op.

---

## 7. Statut / suite

- **Phase 1 (cette spec) : GELÉE.** 9 ops + grammaire + garde-fous.
- **Phase 2 (non commencée) :** implémenter matcher + opérateurs dans `zone_to_contentload --seg-plan`, chacun self-checké byte-exact (guard §4.3 pour `drop`), chacun unit-testé sur fixtures des 5 stacks. Généralise `apply_attribution` en dispatcher d'opérateurs.
- **Phase 3 :** decide-action moteur `segment` + métrique dette d'assist + affichage au model gate.
- **Phase 4 :** pilote discoverASR (composer la seg-plan, mesurer monstres→0 + coverage↑ + fidélité verte).
