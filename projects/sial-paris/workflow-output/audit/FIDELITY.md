# Fidelity audit - local render vs reference (sialparis.com)

Signal = `<main>` body text length + image count (proxy for content parity). Reference captured via browser; local via Jahia live render.

| sev | page | class | local txt | ref txt | local img | ref img | finding |
|----|------|-------|----:|----:|----:|----:|--------|
| 🔴 | `le-salon/nos-partenaires` | STUB | 1885 | 12454 | 115 | 117 | local is a thin stub: 1885 vs 12454 chars on reference (×0.15) |
| 🟠 | `home` | MISSING-IMG | 4247 | 5048 | 88 | 103 | reference has 103 images, local has 88 |
| 🟠 | `infos-pratiques/contacts` | THIN | 1270 | 2688 | 4 | 5 | local thinner than reference: 1270 vs 2688 chars (×0.47) |
| 🟠 | `infos-pratiques/faq` | MISSING-IMG | 1393 | 941 | 1 | 81 | reference has 81 images, local has 1 |
| 🟠 | `infos-pratiques/sial-off` | THIN | 1383 | 2496 | 2 | 5 | local thinner than reference: 1383 vs 2496 chars (×0.55) |
| 🟠 | `infos-pratiques/tarifs-visiteurs` | THIN | 2399 | 4423 | 3 | 5 | local thinner than reference: 2399 vs 4423 chars (×0.54) |
| 🟠 | `le-salon/pourquoi-visiter-sial-paris` | THIN | 1764 | 5024 | 3 | 5 | local thinner than reference: 1764 vs 5024 chars (×0.35) |
| 🟠 | `le-salon/sial-newsfeed-trends` | THIN | 1476 | 2956 | 1 | 2 | local thinner than reference: 1476 vs 2956 chars (×0.50) |
| 🟠 | `temps-forts` | THIN | 1842 | 3941 | 1 | 13 | local thinner than reference: 1842 vs 3941 chars (×0.47) |
| 🟠 | `temps-forts/sial-summits` | THIN | 1752 | 3676 | 3 | 6 | local thinner than reference: 1752 vs 3676 chars (×0.48) |
| 🟠 | `temps-forts/sial-talks` | THIN | 4013 | 9241 | 4 | 19 | local thinner than reference: 4013 vs 9241 chars (×0.43) |
| 🟡 | `tendances` | REVIEW | 1702 | 801 | 1 | 2 | 1702 vs 801 chars (×2.12), 1 vs 2 imgs |
| 🟡 | `tendances/actualites` | REVIEW | 10308 | 508 | 23 | 20 | 10308 vs 508 chars (×20.29), 23 vs 20 imgs |
| 🟡 | `tendances/livres-blancs/sial-insights-2024` | REVIEW | 2817 | 3899 | 4 | 11 | 2817 vs 3899 chars (×0.72), 4 vs 11 imgs |
| 🟢 | `exposer` | N/A-NEW | 953 | - | 1 | - | net-new section, no reference |
| 🟢 | `exposer/augmentez-votre-visibilite` | N/A-NEW | 1320 | - | 3 | - | net-new section, no reference |
| 🟢 | `exposer/augmentez-votre-visibilite/outils-de-communication-sial-paris` | N/A-NEW | 883 | - | 1 | - | net-new section, no reference |
| 🟢 | `exposer/je-veux-exposer` | N/A-NEW | 953 | - | 1 | - | net-new section, no reference |
| 🟢 | `exposer/je-veux-exposer/je-suis-une-start-up` | N/A-NEW | 1006 | - | 1 | - | net-new section, no reference |
| 🟢 | `exposer/les-secteurs-du-salon` | N/A-NEW | 1960 | - | 2 | - | net-new section, no reference |
| 🟢 | `exposer/les-secteurs-du-salon/boissons-sans-alcool` | N/A-NEW | 1120 | - | 1 | - | net-new section, no reference |
| 🟢 | `infos-pratiques` | OK | 1628 | 1239 | 1 | 3 | comparable (1628 vs 1239 chars, 1 vs 3 imgs) |
| 🟢 | `infos-pratiques/dates-et-acces` | OK | 1237 | 1239 | 1 | 3 | comparable (1237 vs 1239 chars, 1 vs 3 imgs) |
| 🟢 | `infos-pratiques/vip-ticket` | OK | 3964 | 3737 | 3 | 2 | comparable (3964 vs 3737 chars, 3 vs 2 imgs) |
| 🟢 | `le-salon` | OK | 8438 | 13418 | 8 | 10 | comparable (8438 vs 13418 chars, 8 vs 10 imgs) |
| 🟢 | `le-salon/top-acheteurs-programme` | OK | 3244 | 3719 | 5 | 3 | comparable (3244 vs 3719 chars, 5 vs 3 imgs) |
| 🟢 | `les-exposants` | N/A-REF | 1451 | err | 1 | - | reference page errors (HTTP 500) |
| 🟢 | `medias` | OK | 903 | 706 | 1 | 5 | comparable (903 vs 706 chars, 1 vs 5 imgs) |
| 🟢 | `tendances/focus` | OK | 78 | 53 | 1 | 1 | comparable (78 vs 53 chars, 1 vs 1 imgs) |
| 🟢 | `tendances/focus/proteines` | OK | 6639 | 10001 | 7 | 11 | comparable (6639 vs 10001 chars, 7 vs 11 imgs) |
| 🟢 | `tendances/livres-blancs` | OK | 1059 | 1278 | 3 | 8 | comparable (1059 vs 1278 chars, 3 vs 8 imgs) |

## Summary

- **OK**: 9
- **THIN**: 8
- **N/A-NEW**: 7
- **REVIEW**: 3
- **MISSING-IMG**: 2
- **STUB**: 1
- **N/A-REF**: 1
