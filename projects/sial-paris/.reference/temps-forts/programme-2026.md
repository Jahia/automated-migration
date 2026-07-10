# Reference: /temps-forts/programme-2026  (nav label "Évènements 2026")

Source: https://www.sialparis.com/fr-FR/temps-forts/programme-2026
Title: Programme

## ⚠️ COMPLEXITY: application-grade, NOT editorial

This is a faceted **event calendar / search app** (Algolia-backed). 44 events.

- Hero: eyebrow none; Title `PROGRAMME 2026`; breadcrumb Accueil | Temps forts | Évènements 2026; lead "SIAL Paris présente sa liste d'événements inédits sur le salon : conférences, sommets, sessions de pitch et de dégustations pour l'industrie alimentaire."
- "CALENDRIER DES ÉVÉNEMENTS 2026" — 44 results, "Ma sélection (0)" basket.
- Day tabs: sam 17/10, dim 18/10, lun 19/10, mar 20/10, mer 21/10. Time-of-day: Matin / Après-midi / Soir.
- Faceted filters: Thématiques (35 themes w/ counts), Langues (FR/EN), Types (15 incl. Conférence, Keynote, SIAL Talks, SIAL Summits, Table ronde...), Organisateurs, Lieux (Hall 6A, SIAL For Change Hall 6A, SIAL Summits Hall 5A, SIAL Talks Hall 5A, StrEat Lab...), Publics (PAYANT / SUR RESERVATION / TOUT PUBLIC).
- 44 event cards (title + theme + venue + schedule). Examples: "Cérémonie d'ouverture SIAL Paris 2026", "Tendances mondiales dans le secteur de l'alimentation & des boissons", "Cérémonie de remise des prix SIAL Innovation 2026", etc.

## Migration note
Faithful migration requires an `event` content type (date, time, theme, type, venue, language, public) + a filterable listing component. This is a sub-project on its own, far larger than the editorial subpages. Flag to user — likely out of scope for a single content pass; candidate for a static editorial summary + link, or a dedicated later effort.
