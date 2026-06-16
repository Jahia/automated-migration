#!/bin/bash

# SIAL Paris Content Creation Script
# Creates all content for the SIAL Paris Jahia site

JAHIA_URL="http://localhost:8080"
ORIGIN="Origin: http://localhost:8080"
USER="root:root"
SITE_KEY="sial-paris"
SITE_PATH="/sites/$SITE_KEY"

# Counter for created nodes
NODES_CREATED=0

# Helper function for GraphQL mutations
run_mutation() {
  local query="$1"
  local description="$2"
  
  echo "  $description..."
  RESPONSE=$(curl -s -u "$USER" \
    -H "Content-Type: application/json" \
    -H "$ORIGIN" \
    -X POST "$JAHIA_URL/modules/graphql" \
    -d "{\"query\":\"$query\"}")
  
  # Check for errors
  if echo "$RESPONSE" | grep -q '"errors"'; then
    echo "    ERROR: $(echo "$RESPONSE" | grep -o '"message":"[^"]*' | head -1 | cut -d'"' -f4)"
    return 1
  else
    ((NODES_CREATED++))
    return 0
  fi
}

echo "=========================================="
echo "SIAL Paris Content Creation"
echo "=========================================="
echo ""

# ========== STEP 1: Create Hero Carousel Slides ==========
echo "STEP 1: Creating Hero Carousel Slides"

# Slide 1: SIAL Paris fête ses 60 ans
run_mutation 'mutation { jcr { slide1: addNode(parentPathOrId: "'$SITE_PATH'/home/hero", primaryNodeType: "sparis:heroSlide", name: "slide-60ans") { uuid } } }' "Create hero slide: 60 ans"

# Set properties for slide 1
run_mutation 'mutation { jcr { mutateNode(pathOrId: "'$SITE_PATH'/home/hero/slide-60ans") { setPropertiesBatch(properties: [{name: "jcr:title", value: "SIAL Paris fête ses 60 ans", language: "fr"}, {name: "description", value: "17-21 Octobre 2026 • Paris Nord Villepinte", language: "fr"}, {name: "imageAlt", value: "SIAL Paris 60 ans", language: "fr"}, {name: "buttonText", value: "Découvrir l'\''édition 2026", language: "fr"}]) { path } } } }' "Set properties for slide 1"

# Slide 2: Inspire Food Business
run_mutation 'mutation { jcr { slide2: addNode(parentPathOrId: "'$SITE_PATH'/home/hero", primaryNodeType: "sparis:heroSlide", name: "slide-inspire") { uuid } } }' "Create hero slide: Inspire"

# Set properties for slide 2
run_mutation 'mutation { jcr { mutateNode(pathOrId: "'$SITE_PATH'/home/hero/slide-inspire") { setPropertiesBatch(properties: [{name: "jcr:title", value: "Inspire Food Business", language: "fr"}, {name: "description", value: "Innovation • Tendances • Business", language: "fr"}, {name: "imageAlt", value: "Inspire Food Business", language: "fr"}, {name: "buttonText", value: "Explorer les tendances", language: "fr"}]) { path } } } }' "Set properties for slide 2"

# Slide 3: Exposez à SIAL Paris
run_mutation 'mutation { jcr { slide3: addNode(parentPathOrId: "'$SITE_PATH'/home/hero", primaryNodeType: "sparis:heroSlide", name: "slide-exposants") { uuid } } }' "Create hero slide: Exposants"

# Set properties for slide 3
run_mutation 'mutation { jcr { mutateNode(pathOrId: "'$SITE_PATH'/home/hero/slide-exposants") { setPropertiesBatch(properties: [{name: "jcr:title", value: "Exposez à SIAL Paris", language: "fr"}, {name: "description", value: "Exposants 2026", language: "fr"}, {name: "imageAlt", value: "Exposez à SIAL Paris", language: "fr"}, {name: "buttonText", value: "Réserver votre stand", language: "fr"}]) { path } } } }' "Set properties for slide 3"

echo ""
echo "STEP 2: Creating News Articles"

# Article 1: SIAL Innovation 2026
run_mutation 'mutation { jcr { addNode(parentPathOrId: "'$SITE_PATH'/contents", primaryNodeType: "sparis:newsItem", name: "sial-innovation-2026") { uuid } } }' "Create news article 1: Innovation 2026"

# Set properties for article 1
run_mutation 'mutation { jcr { mutateNode(pathOrId: "'$SITE_PATH'/contents/sial-innovation-2026") { setPropertiesBatch(properties: [{name: "jcr:title", value: "SIAL Innovation 2026 : les lauréats dévoilés", language: "fr"}, {name: "excerpt", value: "Découvrez les innovations primées qui façonneront le secteur agroalimentaire demain. De nouveaux produits révolutionnaires, des emballages durables, et des solutions technologiques ont été récompensés pour leur contribution exceptionnelle à l'\''industrie.", language: "fr"}, {name: "body", value: "<p>SIAL Innovation 2026 a dévoilé les lauréats de cette année. Les innovations primées représentent le futur de l'\''agroalimentaire.</p><p>Des produits révolutionnaires aux solutions technologiques avancées, chaque lauréat a apporté une contribution significative au secteur.</p><p>Visitez le stand SIAL Innovation pour découvrir ces avancées qui changeront l'\''industrie.</p>", language: "fr"}]) { path } } } }' "Set properties for article 1"

# Article 2: Les tendances food 2026
run_mutation 'mutation { jcr { addNode(parentPathOrId: "'$SITE_PATH'/contents", primaryNodeType: "sparis:newsItem", name: "tendances-food-2026") { uuid } } }' "Create news article 2: Tendances 2026"

# Set properties for article 2
run_mutation 'mutation { jcr { mutateNode(pathOrId: "'$SITE_PATH'/contents/tendances-food-2026") { setPropertiesBatch(properties: [{name: "jcr:title", value: "Les tendances food 2026 : entre durabilité et plaisir", language: "fr"}, {name: "excerpt", value: "Les tendances émergentes du secteur alimentaire combinent durabilité environnementale et satisfaction des consommateurs. Découvrez comment les marques innovent pour répondre aux attentes d'\''un marché en mutation.", language: "fr"}, {name: "body", value: "<p>2026 marque un tournant dans l'\''industrie agroalimentaire avec la montée en puissance de la durabilité.</p><p>Les consommateurs recherchent des produits respectueux de l'\''environnement sans compromis sur le plaisir gustatif. Les marques innovent pour répondre à cette demande croissante.</p><p>SIAL Paris 2026 sera le carrefour où ces tendances convergeront avec les innovations technologiques.</p>", language: "fr"}]) { path } } } }' "Set properties for article 2"

# Article 3: 7 000 exposants attendus
run_mutation 'mutation { jcr { addNode(parentPathOrId: "'$SITE_PATH'/contents", primaryNodeType: "sparis:newsItem", name: "7000-exposants-2026") { uuid } } }' "Create news article 3: 7000 exposants"

# Set properties for article 3
run_mutation 'mutation { jcr { mutateNode(pathOrId: "'$SITE_PATH'/contents/7000-exposants-2026") { setPropertiesBatch(properties: [{name: "jcr:title", value: "7 000 exposants attendus pour SIAL Paris 2026", language: "fr"}, {name: "excerpt", value: "Un record ! Plus de 7 000 exposants du monde entier se réunissent pour la plus grande édition de SIAL Paris. Un événement incontournable pour l'\''industrie agroalimentaire mondiale.", language: "fr"}, {name: "body", value: "<p>SIAL Paris 2026 s'\''annonce comme l'\''édition la plus grande de l'\''histoire du salon.</p><p>Avec 7 000 exposants représentant 194 pays, c'\''est une occasion unique pour les professionnels du secteur agroalimentaire de réseauter et découvrir les dernières innovations.</p><p>Les visiteurs professionnels auront accès à 400 000 m² d'\''exposition, un espace record pour cette 60ème édition.</p>", language: "fr"}]) { path } } } }' "Set properties for article 3"

echo ""
echo "STEP 3: Publishing Content"

# Publish hero area
run_mutation 'mutation { jcr { mutateNode(pathOrId: "'$SITE_PATH'/home/hero") { publish(languages: ["fr", "en"]) } } }' "Publish hero area"

# Publish contents
run_mutation 'mutation { jcr { mutateNode(pathOrId: "'$SITE_PATH'/contents") { publish(languages: ["fr", "en"]) } } }' "Publish contents"

# Publish home page
run_mutation 'mutation { jcr { mutateNode(pathOrId: "'$SITE_PATH'/home") { publish(languages: ["fr", "en"]) } } }' "Publish home page"

echo ""
echo "=========================================="
echo "Content creation complete!"
echo "Nodes created: $NODES_CREATED"
echo "=========================================="

