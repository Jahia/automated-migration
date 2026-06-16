#!/usr/bin/env python3

import json
import subprocess
import sys

JAHIA_URL = "http://localhost:8080"
USER = "root:root"
SITE_KEY = "sial-paris"
SITE_PATH = f"/sites/{SITE_KEY}"

nodes_created = 0

def run_mutation(query_str, description):
    global nodes_created
    print(f"  {description}...", end=" ")
    
    try:
        result = subprocess.run([
            "curl", "-s", "-u", USER,
            "-H", "Content-Type: application/json",
            "-H", "Origin: http://localhost:8080",
            "-X", "POST", f"{JAHIA_URL}/modules/graphql",
            "-d", json.dumps({"query": query_str})
        ], capture_output=True, text=True, timeout=10)
        
        data = json.loads(result.stdout)
        
        if "errors" in data and data["errors"]:
            error_msg = data["errors"][0].get("message", "Unknown error")[:100]
            print(f"ERROR: {error_msg}")
            return False
        
        nodes_created += 1
        print("OK")
        return True
    except Exception as e:
        print(f"ERROR: {str(e)[:100]}")
        return False

print("=" * 50)
print("SIAL Paris Content Creation")
print("=" * 50)
print()

# ========== STEP 1: Create Hero Carousel Slides ==========
print("STEP 1: Creating Hero Carousel Slides")

# Slide 1: 60 ans
query = f'mutation {{ jcr {{ addNode(parentPathOrId: "{SITE_PATH}/home/hero", primaryNodeType: "sparis:heroSlide", name: "slide-60ans") {{ uuid }} }} }}'
run_mutation(query, "Create hero slide: 60 ans")

props_query = f'''mutation {{ jcr {{ mutateNode(pathOrId: "{SITE_PATH}/home/hero/slide-60ans") {{ setPropertiesBatch(properties: [
  {{name: "jcr:title", value: "SIAL Paris fête ses 60 ans", language: "fr"}},
  {{name: "description", value: "17-21 Octobre 2026 • Paris Nord Villepinte", language: "fr"}},
  {{name: "imageAlt", value: "SIAL Paris 60 ans", language: "fr"}},
  {{name: "buttonText", value: "Découvrir l'édition 2026", language: "fr"}}
]) {{ path }} }} }} }}'''
run_mutation(props_query, "Set properties for slide 1")

# Slide 2: Inspire
query = f'mutation {{ jcr {{ addNode(parentPathOrId: "{SITE_PATH}/home/hero", primaryNodeType: "sparis:heroSlide", name: "slide-inspire") {{ uuid }} }} }}'
run_mutation(query, "Create hero slide: Inspire")

props_query = f'''mutation {{ jcr {{ mutateNode(pathOrId: "{SITE_PATH}/home/hero/slide-inspire") {{ setPropertiesBatch(properties: [
  {{name: "jcr:title", value: "Inspire Food Business", language: "fr"}},
  {{name: "description", value: "Innovation • Tendances • Business", language: "fr"}},
  {{name: "imageAlt", value: "Inspire Food Business", language: "fr"}},
  {{name: "buttonText", value: "Explorer les tendances", language: "fr"}}
]) {{ path }} }} }} }}'''
run_mutation(props_query, "Set properties for slide 2")

# Slide 3: Exposants
query = f'mutation {{ jcr {{ addNode(parentPathOrId: "{SITE_PATH}/home/hero", primaryNodeType: "sparis:heroSlide", name: "slide-exposants") {{ uuid }} }} }}'
run_mutation(query, "Create hero slide: Exposants")

props_query = f'''mutation {{ jcr {{ mutateNode(pathOrId: "{SITE_PATH}/home/hero/slide-exposants") {{ setPropertiesBatch(properties: [
  {{name: "jcr:title", value: "Exposez à SIAL Paris", language: "fr"}},
  {{name: "description", value: "Exposants 2026", language: "fr"}},
  {{name: "imageAlt", value: "Exposez à SIAL Paris", language: "fr"}},
  {{name: "buttonText", value: "Réserver votre stand", language: "fr"}}
]) {{ path }} }} }} }}'''
run_mutation(props_query, "Set properties for slide 3")

print()
print("STEP 2: Creating News Articles")

# Article 1: Innovation
query = f'mutation {{ jcr {{ addNode(parentPathOrId: "{SITE_PATH}/contents", primaryNodeType: "sparis:newsItem", name: "sial-innovation-2026") {{ uuid }} }} }}'
run_mutation(query, "Create article 1: Innovation 2026")

props_query = f'''mutation {{ jcr {{ mutateNode(pathOrId: "{SITE_PATH}/contents/sial-innovation-2026") {{ setPropertiesBatch(properties: [
  {{name: "jcr:title", value: "SIAL Innovation 2026 : les lauréats dévoilés", language: "fr"}},
  {{name: "excerpt", value: "Découvrez les innovations primées qui façonneront le secteur agroalimentaire demain. De nouveaux produits révolutionnaires, des emballages durables, et des solutions technologiques ont été récompensés.", language: "fr"}},
  {{name: "body", value: "<p>SIAL Innovation 2026 a dévoilé les lauréats de cette année.</p><p>Des produits révolutionnaires aux solutions technologiques avancées, chaque lauréat a apporté une contribution significative au secteur.</p><p>Visitez le stand SIAL Innovation pour découvrir ces avancées qui changeront l'industrie.</p>", language: "fr"}}
]) {{ path }} }} }} }}'''
run_mutation(props_query, "Set properties for article 1")

# Article 2: Tendances
query = f'mutation {{ jcr {{ addNode(parentPathOrId: "{SITE_PATH}/contents", primaryNodeType: "sparis:newsItem", name: "tendances-food-2026") {{ uuid }} }} }}'
run_mutation(query, "Create article 2: Tendances 2026")

props_query = f'''mutation {{ jcr {{ mutateNode(pathOrId: "{SITE_PATH}/contents/tendances-food-2026") {{ setPropertiesBatch(properties: [
  {{name: "jcr:title", value: "Les tendances food 2026 : entre durabilité et plaisir", language: "fr"}},
  {{name: "excerpt", value: "Les tendances émergentes du secteur alimentaire combinent durabilité environnementale et satisfaction des consommateurs. Découvrez comment les marques innovent pour répondre aux attentes d'un marché en mutation.", language: "fr"}},
  {{name: "body", value: "<p>2026 marque un tournant dans l'industrie agroalimentaire avec la montée en puissance de la durabilité.</p><p>Les consommateurs recherchent des produits respectueux de l'environnement sans compromis sur le plaisir gustatif.</p><p>SIAL Paris 2026 sera le carrefour où ces tendances convergeront avec les innovations technologiques.</p>", language: "fr"}}
]) {{ path }} }} }} }}'''
run_mutation(props_query, "Set properties for article 2")

# Article 3: 7000 exposants
query = f'mutation {{ jcr {{ addNode(parentPathOrId: "{SITE_PATH}/contents", primaryNodeType: "sparis:newsItem", name: "7000-exposants-2026") {{ uuid }} }} }}'
run_mutation(query, "Create article 3: 7000 exposants")

props_query = f'''mutation {{ jcr {{ mutateNode(pathOrId: "{SITE_PATH}/contents/7000-exposants-2026") {{ setPropertiesBatch(properties: [
  {{name: "jcr:title", value: "7 000 exposants attendus pour SIAL Paris 2026", language: "fr"}},
  {{name: "excerpt", value: "Un record ! Plus de 7 000 exposants du monde entier se réunissent pour la plus grande édition de SIAL Paris. Un événement incontournable pour l'industrie agroalimentaire mondiale.", language: "fr"}},
  {{name: "body", value: "<p>SIAL Paris 2026 s'annonce comme l'édition la plus grande de l'histoire du salon.</p><p>Avec 7 000 exposants représentant 194 pays, c'est une occasion unique pour les professionnels du secteur agroalimentaire de réseauter et découvrir les dernières innovations.</p><p>Les visiteurs professionnels auront accès à 400 000 m² d'exposition, un espace record pour cette 60ème édition.</p>", language: "fr"}}
]) {{ path }} }} }} }}'''
run_mutation(props_query, "Set properties for article 3")

print()
print("STEP 3: Publishing Content")

# Publish
query = f'mutation {{ jcr {{ mutateNode(pathOrId: "{SITE_PATH}/home/hero") {{ publish(languages: ["fr", "en"]) }} }} }}'
run_mutation(query, "Publish hero area")

query = f'mutation {{ jcr {{ mutateNode(pathOrId: "{SITE_PATH}/contents") {{ publish(languages: ["fr", "en"]) }} }} }}'
run_mutation(query, "Publish contents")

query = f'mutation {{ jcr {{ mutateNode(pathOrId: "{SITE_PATH}/home") {{ publish(languages: ["fr", "en"]) }} }} }}'
run_mutation(query, "Publish home page")

print()
print("=" * 50)
print("Content creation complete!")
print(f"Nodes created: {nodes_created}")
print("=" * 50)

