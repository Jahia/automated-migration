#!/bin/bash

VIDEO_UUID="060d468c-52c5-4e8e-84f8-7dcf7f5de291"

# 1. Create introText
echo "Creating introText component..."
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home/main\", name: \"intro\", primaryNodeType: \"sialp:introText\", properties: [{name: \"overline\", value: \"LE SALON MONDIAL\", language: \"fr\"}, {name: \"heading\", value: \"SIAL Paris, le rendez-vous mondial de l&#39;alimentation\", language: \"fr\"}, {name: \"body\", value: \"<p>Tous les 2 ans à Paris Nord Villepinte, SIAL Paris réunit les acteurs de l&#39;industrie alimentaire mondiale pour 5 jours d&#39;innovation, de tendances et de rencontres professionnelles. 7 500 exposants, 400 000 produits présentés, 200 000 visiteurs de 200 pays.</p>\", language: \"fr\"}]) { uuid } } }"
  }'

# 2. Create keyFigures
echo "Creating keyFigures component..."
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home/main\", name: \"key-figures\", primaryNodeType: \"sialp:keyFigures\") { uuid } } }"
  }'

# Add key figures
echo "Adding key figures..."
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home/main/key-figures\", name: \"fig-1\", primaryNodeType: \"sialp:keyFigure\", properties: [{name: \"number\", value: \"7 500\"}, {name: \"label\", value: \"exposants\", language: \"fr\"}]) { uuid } } }"
  }'

curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home/main/key-figures\", name: \"fig-2\", primaryNodeType: \"sialp:keyFigure\", properties: [{name: \"number\", value: \"200\"}, {name: \"unit\", value: \"pays\"}, {name: \"label\", value: \"représentés\", language: \"fr\"}]) { uuid } } }"
  }'

curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home/main/key-figures\", name: \"fig-3\", primaryNodeType: \"sialp:keyFigure\", properties: [{name: \"number\", value: \"400 000\"}, {name: \"label\", value: \"produits\", language: \"fr\"}]) { uuid } } }"
  }'

curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home/main/key-figures\", name: \"fig-4\", primaryNodeType: \"sialp:keyFigure\", properties: [{name: \"number\", value: \"200 000\"}, {name: \"label\", value: \"visiteurs\", language: \"fr\"}]) { uuid } } }"
  }'

curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home/main/key-figures\", name: \"fig-5\", primaryNodeType: \"sialp:keyFigure\", properties: [{name: \"number\", value: \"5\"}, {name: \"unit\", value: \"jours\"}, {name: \"label\", value: \"d&#39;événement\", language: \"fr\"}]) { uuid } } }"
  }'

# 3. Create newsListing
echo "Creating newsListing component..."
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home/main\", name: \"news-section\", primaryNodeType: \"sialp:newsListing\", properties: [{name: \"heading\", value: \"Dernières actualités\", language: \"fr\"}, {name: \"ctaLabel\", value: \"Voir toutes les actualités\", language: \"fr\"}, {name: \"maxItems\", value: \"3\", type: LONG}]) { uuid } } }"
  }'

# 4. Create visitorProfiles
echo "Creating visitorProfiles component..."
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home/main\", name: \"visitor-profiles\", primaryNodeType: \"sialp:visitorProfiles\", properties: [{name: \"heading\", value: \"Qui visite SIAL Paris ?\", language: \"fr\"}]) { uuid } } }"
  }'

# Add visitor profile 1
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home/main/visitor-profiles\", name: \"distributors\", primaryNodeType: \"sialp:visitorProfile\", properties: [{name: \"heading\", value: \"Distributeurs\", language: \"fr\"}, {name: \"description\", value: \"GMS, hard discount, e-commerce, cash & carry, restauration collective\", language: \"fr\"}, {name: \"ctaLabel\", value: \"En savoir plus\", language: \"fr\"}]) { uuid } } }"
  }'

# Add visitor profile 2
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home/main/visitor-profiles\", name: \"manufacturers\", primaryNodeType: \"sialp:visitorProfile\", properties: [{name: \"heading\", value: \"Industriels\", language: \"fr\"}, {name: \"description\", value: \"Fabricants, transformateurs, marques de distributeur\", language: \"fr\"}, {name: \"ctaLabel\", value: \"En savoir plus\", language: \"fr\"}]) { uuid } } }"
  }'

# Add visitor profile 3
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home/main/visitor-profiles\", name: \"restaurateurs\", primaryNodeType: \"sialp:visitorProfile\", properties: [{name: \"heading\", value: \"Restaurateurs\", language: \"fr\"}, {name: \"description\", value: \"CHR, gastronomie, restauration rapide, traiteurs\", language: \"fr\"}, {name: \"ctaLabel\", value: \"En savoir plus\", language: \"fr\"}]) { uuid } } }"
  }'

# Add visitor profile 4
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home/main/visitor-profiles\", name: \"public\", primaryNodeType: \"sialp:visitorProfile\", properties: [{name: \"heading\", value: \"Grand public\", language: \"fr\"}, {name: \"description\", value: \"Journées grand public, animations, dégustations\", language: \"fr\"}, {name: \"ctaLabel\", value: \"En savoir plus\", language: \"fr\"}]) { uuid } } }"
  }'

echo "Main content components created"

