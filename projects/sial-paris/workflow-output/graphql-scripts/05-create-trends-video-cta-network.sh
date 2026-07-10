#!/bin/bash

VIDEO_UUID="060d468c-52c5-4e8e-84f8-7dcf7f5de291"

# 5. Create trendsSection
echo "Creating trendsSection component..."
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home/main\", name: \"trends-section\", primaryNodeType: \"sialp:trendsSection\", properties: [{name: \"heading\", value: \"Tendances & Innovations\", language: \"fr\"}, {name: \"intro\", value: \"SIAL Paris est l&#39;observatoire mondial des tendances alimentaires. Décryptez les grandes évolutions qui transforment l&#39;industrie.\", language: \"fr\"}, {name: \"ctaLabel\", value: \"Toutes les tendances\", language: \"fr\"}]) { uuid } } }"
  }'

# Add trend card 1
echo "Adding trend cards..."
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home/main/trends-section\", name: \"card-1\", primaryNodeType: \"sialp:trendCard\", properties: [{name: \"tag\", value: \"Durabilité\", language: \"fr\"}, {name: \"heading\", value: \"Alimentation durable : les nouvelles protéines végétales\", language: \"fr\"}, {name: \"excerpt\", value: \"Le marché des protéines alternatives continue sa croissance avec de nouvelles solutions innovantes.\", language: \"fr\"}]) { uuid } } }"
  }'

# Add trend card 2
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home/main/trends-section\", name: \"card-2\", primaryNodeType: \"sialp:trendCard\", properties: [{name: \"tag\", value: \"Santé\", language: \"fr\"}, {name: \"heading\", value: \"Nutriscore et reformulation : où en est l&#39;industrie ?\", language: \"fr\"}, {name: \"excerpt\", value: \"Les fabricants accélèrent la reformulation de leurs recettes pour répondre aux attentes consommateurs.\", language: \"fr\"}]) { uuid } } }"
  }'

# Add trend card 3
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home/main/trends-section\", name: \"card-3\", primaryNodeType: \"sialp:trendCard\", properties: [{name: \"tag\", value: \"Tech\", language: \"fr\"}, {name: \"heading\", value: \"Food tech : l&#39;IA au service de la production alimentaire\", language: \"fr\"}, {name: \"excerpt\", value: \"Les startups food tech intègrent l&#39;intelligence artificielle pour optimiser les process de production.\", language: \"fr\"}]) { uuid } } }"
  }'

# 6. Create videoSection
echo "Creating videoSection component..."
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home/main\", name: \"video-section\", primaryNodeType: \"sialp:videoSection\", properties: [{name: \"heading\", value: \"SIAL Paris 2024 en images\", language: \"fr\"}, {name: \"videoUrl\", value: \"https://www.youtube.com/embed/sparis2024\"}]) { uuid } } }"
  }'

# Set video thumbnail
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d "{
    \"query\":\"mutation { jcr { mutateNode(pathOrId: \\\"/sites/sial-paris/home/main/video-section\\\") { mutateProperty(name: \\\"thumbnailImage\\\") { setValue(value: \\\"${VIDEO_UUID}\\\", language: \\\"fr\\\", type: WEAKREFERENCE) } } } }\"
  }" > /dev/null

# 7. Create ctaDualCards
echo "Creating ctaDualCards component..."
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home/main\", name: \"cta-cards\", primaryNodeType: \"sialp:ctaDualCards\", properties: [{name: \"leftHeading\", value: \"Vous exposez à SIAL Paris 2026 ?\", language: \"fr\"}, {name: \"leftCtaLabel\", value: \"Je dépose ma candidature\", language: \"fr\"}, {name: \"rightHeading\", value: \"Vous visitez SIAL Paris 2026 ?\", language: \"fr\"}, {name: \"rightCtaLabel\", value: \"Je commande mon badge\", language: \"fr\"}]) { uuid } } }"
  }'

# 8. Create sialNetwork
echo "Creating sialNetwork component..."
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home/main\", name: \"network-events\", primaryNodeType: \"sialp:sialNetwork\", properties: [{name: \"heading\", value: \"Le réseau SIAL mondial\", language: \"fr\"}]) { uuid } } }"
  }'

# Add network events
echo "Adding network events..."
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home/main/network-events\", name: \"event-1\", primaryNodeType: \"sialp:networkEvent\", properties: [{name: \"eventName\", value: \"SIAL Paris\"}, {name: \"city\", value: \"Paris\"}, {name: \"eventDates\", value: \"17-21 octobre 2026\", language: \"fr\"}]) { uuid } } }"
  }'

curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home/main/network-events\", name: \"event-2\", primaryNodeType: \"sialp:networkEvent\", properties: [{name: \"eventName\", value: \"SIAL Canada\"}, {name: \"city\", value: \"Montréal / Toronto\"}, {name: \"eventDates\", value: \"À venir\", language: \"fr\"}]) { uuid } } }"
  }'

curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home/main/network-events\", name: \"event-3\", primaryNodeType: \"sialp:networkEvent\", properties: [{name: \"eventName\", value: \"SIAL China\"}, {name: \"city\", value: \"Shanghai\"}, {name: \"eventDates\", value: \"À venir\", language: \"fr\"}]) { uuid } } }"
  }'

curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home/main/network-events\", name: \"event-4\", primaryNodeType: \"sialp:networkEvent\", properties: [{name: \"eventName\", value: \"SIAL India\"}, {name: \"city\", value: \"New Delhi\"}, {name: \"eventDates\", value: \"À venir\", language: \"fr\"}]) { uuid } } }"
  }'

curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home/main/network-events\", name: \"event-5\", primaryNodeType: \"sialp:networkEvent\", properties: [{name: \"eventName\", value: \"SIAL Interfood\"}, {name: \"city\", value: \"Jakarta\"}, {name: \"eventDates\", value: \"À venir\", language: \"fr\"}]) { uuid } } }"
  }'

curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home/main/network-events\", name: \"event-6\", primaryNodeType: \"sialp:networkEvent\", properties: [{name: \"eventName\", value: \"SIAL Middle East\"}, {name: \"city\", value: \"Abu Dhabi\"}, {name: \"eventDates\", value: \"À venir\", language: \"fr\"}]) { uuid } } }"
  }'

curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home/main/network-events\", name: \"event-7\", primaryNodeType: \"sialp:networkEvent\", properties: [{name: \"eventName\", value: \"SIAL Network\"}, {name: \"city\", value: \"International\"}, {name: \"eventDates\", value: \"À venir\", language: \"fr\"}]) { uuid } } }"
  }'

echo "Trends, video, CTA, and network sections created"

