#!/bin/bash

LOGO_UUID="f5c9f9bc-9909-40ef-af49-9873462de461"

# Create main navigation in header
echo "Creating main navigation component..."
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home/header\", name: \"navigation\", primaryNodeType: \"sialp:mainNavigation\", properties: [{name: \"exposantCtaLabel\", value: \"Je suis exposant\", language: \"fr\"}, {name: \"visiteurCtaLabel\", value: \"Je suis visiteur\", language: \"fr\"}]) { uuid } } }"
  }'

# Get logo UUID and set it on navigation
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d "{
    \"query\":\"mutation { jcr { mutateNode(pathOrId: \\\"/sites/sial-paris/home/header/navigation\\\") { mutateProperty(name: \\\"logoImage\\\") { setValue(value: \\\"${LOGO_UUID}\\\", language: \\\"fr\\\", type: WEAKREFERENCE) } } } }\"
  }" > /dev/null

echo "Main navigation created"

# Create footer
echo "Creating footer component..."
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home/footer\", name: \"footer-content\", primaryNodeType: \"sialp:footer\", properties: [{name: \"newsletterHeading\", value: \"Restez informé\", language: \"fr\"}, {name: \"newsletterPlaceholder\", value: \"Votre adresse email\", language: \"fr\"}, {name: \"copyrightText\", value: \"© 2026 SIAL Paris - Comexposium\", language: \"fr\"}, {name: \"gdprText\", value: \"<p>Nous respectons votre vie privée</p>\", language: \"fr\"}]) { uuid } } }"
  }'

# Set logo on footer
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d "{
    \"query\":\"mutation { jcr { mutateNode(pathOrId: \\\"/sites/sial-paris/home/footer/footer-content\\\") { mutateProperty(name: \\\"sialLogo\\\") { setValue(value: \\\"${LOGO_UUID}\\\", language: \\\"fr\\\", type: WEAKREFERENCE) } } } }\"
  }" > /dev/null

echo "Footer created"

