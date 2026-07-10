#!/bin/bash

# Create article 1
echo "Creating article 1..."
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/contents\", name: \"sial-innovation-2026\", primaryNodeType: \"sialp:newsArticle\", properties: [{name: \"jcr:title\", value: \"SIAL Innovation 2026 : les candidatures sont ouvertes\", language: \"fr\"}, {name: \"category\", value: \"Innovation\", language: \"fr\"}, {name: \"publishDate\", value: \"2026-03-15T00:00:00.000+00:00\", type: DATE}, {name: \"excerpt\", value: \"Les entreprises du secteur alimentaire peuvent désormais soumettre leurs innovations pour le concours SIAL Innovation 2026.\", language: \"fr\"}, {name: \"body\", value: \"<p>Les entreprises du secteur alimentaire peuvent désormais soumettre leurs innovations.</p>\", language: \"fr\"}]) { uuid } } }"
  }'

# Create article 2
echo "Creating article 2..."
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/contents\", name: \"tendances-2026\", primaryNodeType: \"sialp:newsArticle\", properties: [{name: \"jcr:title\", value: \"Rapport tendances 2026 : les 5 grands enjeux de l&#39;alimentaire\", language: \"fr\"}, {name: \"category\", value: \"Tendances\", language: \"fr\"}, {name: \"publishDate\", value: \"2026-02-28T00:00:00.000+00:00\", type: DATE}, {name: \"excerpt\", value: \"Notre rapport annuel dévoile les grandes tendances qui vont façonner le marché alimentaire mondial en 2026.\", language: \"fr\"}, {name: \"body\", value: \"<p>Notre rapport annuel dévoile les grandes tendances.</p>\", language: \"fr\"}]) { uuid } } }"
  }'

# Create article 3
echo "Creating article 3..."
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/contents\", name: \"sial-paris-j200\", primaryNodeType: \"sialp:newsArticle\", properties: [{name: \"jcr:title\", value: \"SIAL Paris 2026 : J-200, les inscriptions exposants progressent\", language: \"fr\"}, {name: \"category\", value: \"Événement\", language: \"fr\"}, {name: \"publishDate\", value: \"2026-04-01T00:00:00.000+00:00\", type: DATE}, {name: \"excerpt\", value: \"À 200 jours de l&#39;ouverture du salon, le nombre d&#39;exposants inscrits dépasse déjà les chiffres de 2024.\", language: \"fr\"}, {name: \"body\", value: \"<p>À 200 jours de l&#39;ouverture du salon, le nombre d&#39;exposants progresse.</p>\", language: \"fr\"}]) { uuid } } }"
  }'

echo "News articles created"

