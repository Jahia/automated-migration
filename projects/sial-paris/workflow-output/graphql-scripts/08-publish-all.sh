#!/bin/bash

echo "Publishing entire SIAL Paris site..."

# Publish home page and all children
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { mutateNode(pathOrId: \"/sites/sial-paris/home\") { publish(languages: [\"fr\"]) } } }"
  }'

echo "Home page published"

# Publish all sub-pages
for PAGE in le-salon les-exposants temps-forts tendances infos-pratiques medias; do
  curl -s -u root:root \
    -H "Origin: http://localhost:8080" \
    -H "Content-Type: application/json" \
    -X POST http://localhost:8080/modules/graphql \
    -d "{
      \"query\":\"mutation { jcr { mutateNode(pathOrId: \\\"/sites/sial-paris/home/${PAGE}\\\") { publish(languages: [\\\"fr\\\"]) } } }\"
    }" > /dev/null
    
  echo "Published: $PAGE"
done

# Publish files folder
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { mutateNodesByQuery(query: \"SELECT * FROM [jnt:content] WHERE ISDESCENDANTNODE('\''/sites/sial-paris/files'\'') OR ISDESCENDANTNODE('\''/sites/sial-paris/actualites'\'\')\", queryLanguage: SQL2) { publish(languages: [\"fr\"]) } } }"
  }' > /dev/null

echo "All content published"

