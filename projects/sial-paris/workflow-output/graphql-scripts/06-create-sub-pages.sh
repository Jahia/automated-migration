#!/bin/bash

PAGES=("le-salon" "les-exposants" "temps-forts" "tendances" "infos-pratiques" "medias")
PAGE_TITLES=("Le Salon" "Les Exposants" "Temps Forts" "Tendances" "Infos Pratiques" "Médias")

echo "Creating sub-pages..."
for i in "${!PAGES[@]}"; do
  PAGE="${PAGES[$i]}"
  TITLE="${PAGE_TITLES[$i]}"
  
  curl -s -u root:root \
    -H "Origin: http://localhost:8080" \
    -H "Content-Type: application/json" \
    -X POST http://localhost:8080/modules/graphql \
    -d "{
      \"query\":\"mutation { jcr { addNode(parentPathOrId: \\\"/sites/sial-paris/home\\\", name: \\\"${PAGE}\\\", primaryNodeType: \\\"jnt:page\\\", properties: [{name: \\\"jcr:title\\\", value: \\\"${TITLE}\\\", language: \\\"fr\\\"}, {name: \\\"j:templateName\\\", value: \\\"basic\\\"}]) { uuid node { path } } } }\"
    }"
  
  # Create main area for the page
  curl -s -u root:root \
    -H "Origin: http://localhost:8080" \
    -H "Content-Type: application/json" \
    -X POST http://localhost:8080/modules/graphql \
    -d "{
      \"query\":\"mutation { jcr { addNode(parentPathOrId: \\\"/sites/sial-paris/home/${PAGE}\\\", name: \\\"main\\\", primaryNodeType: \\\"jnt:contentList\\\") { uuid } } }\"
    }" > /dev/null
    
  echo "  Created sub-page: $PAGE"
done

echo "Sub-pages created"

