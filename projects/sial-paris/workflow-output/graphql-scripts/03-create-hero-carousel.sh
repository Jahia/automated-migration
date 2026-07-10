#!/bin/bash

# Create hero carousel
echo "Creating hero carousel..."
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home/hero\", name: \"hero-carousel\", primaryNodeType: \"sialp:heroCarousel\") { uuid } } }"
  }'

# Create slide 1
echo "Creating hero slide 1..."
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home/hero/hero-carousel\", name: \"slide-1\", primaryNodeType: \"sialp:heroSlide\", properties: [{name: \"badge\", value: \"17 - 21 OCT. 2026\", language: \"fr\"}, {name: \"heading\", value: \"Le salon mondial de l&#39;alimentation\", language: \"fr\"}, {name: \"body\", value: \"Paris Nord Villepinte\", language: \"fr\"}, {name: \"ctaLabel\", value: \"Découvrir\", language: \"fr\"}]) { uuid } } }"
  }'

# Create slide 2
echo "Creating hero slide 2..."
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home/hero/hero-carousel\", name: \"slide-2\", primaryNodeType: \"sialp:heroSlide\", properties: [{name: \"badge\", value: \"SIAL Innovation 2026\", language: \"fr\"}, {name: \"heading\", value: \"Les innovations alimentaires de demain\", language: \"fr\"}, {name: \"body\", value: \"Découvrez les tendances qui façonnent le secteur\", language: \"fr\"}, {name: \"ctaLabel\", value: \"En savoir plus\", language: \"fr\"}]) { uuid } } }"
  }'

# Create slide 3
echo "Creating hero slide 3..."
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home/hero/hero-carousel\", name: \"slide-3\", primaryNodeType: \"sialp:heroSlide\", properties: [{name: \"badge\", value: \"SIAL for Change\", language: \"fr\"}, {name: \"heading\", value: \"Un salon engagé pour une alimentation durable\", language: \"fr\"}, {name: \"body\", value: \"Retrouvez nos initiatives RSE et développement durable\", language: \"fr\"}, {name: \"ctaLabel\", value: \"Notre engagement\", language: \"fr\"}]) { uuid } } }"
  }'

echo "Hero carousel created with 3 slides"

