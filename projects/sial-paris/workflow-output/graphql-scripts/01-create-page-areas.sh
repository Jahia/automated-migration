#!/bin/bash

# Publish files folder
echo "Publishing files folder..."
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { mutateNode(pathOrId: \"/sites/sial-paris/files\") { publish(languages: [\"fr\"]) } } }"
  }' > /dev/null

# Create header (AbsoluteArea) - navigation
echo "Creating header area..."
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home\", name: \"header\", primaryNodeType: \"jnt:contentList\") { uuid } } }"
  }' > /dev/null

# Create footer (AbsoluteArea)
echo "Creating footer area..."
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home\", name: \"footer\", primaryNodeType: \"jnt:contentList\") { uuid } } }"
  }' > /dev/null

# Create hero area
echo "Creating hero area..."
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home\", name: \"hero\", primaryNodeType: \"jnt:contentList\") { uuid } } }"
  }' > /dev/null

# Create main area
echo "Creating main area..."
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home\", name: \"main\", primaryNodeType: \"jnt:contentList\") { uuid } } }"
  }' > /dev/null

echo "All areas created successfully"

