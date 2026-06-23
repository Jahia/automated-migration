#!/usr/bin/env python3
"""Replace the LIMBUA placeholder article with the REAL captured content + real image.
Proof of the real-news pattern: title/excerpt/body (richtext) + thumbnail weakreference
(media.upload.url consistent-UUID) + category. Run from repo root."""
import json, base64, urllib.request
u="root:root";h="http://localhost:8080";tok=""
for line in open("projects/sial-paris/.env"):
    line=line.strip()
    if line.startswith("JAHIA_USER="):u=line.split("=",1)[1]
    elif line.startswith("JAHIA_HOST="):h=line.split("=",1)[1]
    elif line.startswith("JAHIA_MCP_TOKEN="):tok=line.split("=",1)[1]
A="Basic "+base64.b64encode(u.encode()).decode()
def mcp(name,args):
    req=urllib.request.Request(h+"/modules/mcp",json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":name,"arguments":args}}).encode(),{"Content-Type":"application/json","Authorization":"APIToken "+tok})
    t=json.load(urllib.request.urlopen(req)).get("result",{}).get("content",[{}])[0].get("text","")
    try:return json.loads(t)
    except:return {"_raw":t}
def gql(q,v=None):
    body={"query":q};
    req=urllib.request.Request(h+"/modules/graphql",json.dumps(body).encode(),{"Content-Type":"application/json","Authorization":A,"Origin":h})
    return json.load(urllib.request.urlopen(req))

NODE="/sites/sial-paris/contents/news/limbua-chaine-approvisionnement"
TITLE="LIMBUA : la chaine d'approvisionnement germano-kenyane, reference de la responsabilite alimentaire"
EXCERPT=("Des pepinieres de macadamia au Kenya a la distribution internationale, le parcours de LIMBUA au "
 "SIAL For Change 2024 montre comment un salon professionnel de l'agroalimentaire peut mettre en avant les "
 "entreprises qui placent la tracabilite, l'impact social et la responsabilite environnementale au coeur de leur developpement.")
BODY="".join([
 "<p>SIAL For Change a ete lance lors de SIAL Paris 2024 comme le premier prix du salon dedie a la responsabilite societale des entreprises, cree en partenariat avec l'agence RSE Hyssop. Son objectif : mettre en lumiere les entreprises qui integrent des pratiques responsables dans leur strategie, leurs operations et leurs chaines d'approvisionnement.</p>",
 "<p>Pour LIMBUA, entreprise germano-kenyane specialisee dans les noix de macadamia, les mangues et les avocats biologiques, SIAL For Change 2024 est devenu une puissante vitrine internationale. Le modele de l'entreprise couvre toute la chaine, de la pepiniere a l'exportation et a la distribution mondiale, avec une tracabilite complete.</p>",
 "<h2>Une chaine d'approvisionnement enracinee autour du mont Kenya</h2>",
 "<p>LIMBUA travaille avec plus de 9 000 petits exploitants agricoles au Kenya. Au cours de l'annee ecoulee, l'entreprise a elargi son reseau de 2 000 producteurs et les a accompagnes vers la certification biologique. Ses activites associent agriculture biologique, transformation locale et tracabilite numerique, de l'exploitation aux centres logistiques de Mombasa et Rotterdam jusqu'a son entrepot en Allemagne.</p>",
 "<p>Autour du mont Kenya, le modele comporte une forte dimension sociale : les noix sont cassees a la main, un procede qui soutient l'emploi rural, et l'entreprise contribue a l'assurance maladie, aux soins et a la retraite de ses salaries.</p>",
 "<h2>Croissance biologique, ambitions regeneratrices</h2>",
 "<p>LIMBUA travaille avec des cultures diversifiees pour soutenir la biodiversite et limiter la dependance a une seule source de revenus. Aucune irrigation artificielle n'est utilisee grace aux precipitations annuelles. L'entreprise a obtenu la certification Naturland et indique etre le premier producteur de macadamia certifie Naturland au monde, visant aussi le standard Regenerative Organic Certified.</p>",
 "<h2>Ce que SIAL For Change a apporte a LIMBUA</h2>",
 "<p>L'initiative a offert a LIMBUA une plateforme pour raconter une histoire complexe dans un cadre dedie au business alimentaire international. Selon l'entreprise, le concours lui a donne une visibilite internationale et lui a permis d'entrer en contact avec des parties prenantes partageant son engagement en faveur de la responsabilite sociale et environnementale.</p>",
 "<h2>De la reconnaissance a un mouvement plus large</h2>",
 "<p>SIAL For Change fera son retour a SIAL Paris du 17 au 21 octobre 2026, avec un espace dedie de 200 m2 dans le Hall 6. Le concours 2026 reunira start-ups, PME et grandes entreprises, evaluees sur l'originalite, l'impact, la capacite de deploiement et l'alignement avec les principes RSE. La ceremonie est prevue le 18 octobre 2026 sur la scene SIAL Talks.</p>",
])

# 1. import the real image (consistent UUID), publish
up=mcp("media.upload.url",{"siteKey":"sial-paris","sourceUrl":"https://www.sialparis.com/-/media/Project/Comexposium-Master1/Master1-sialparis/Cleverdis/2026/06/happy-person-limbua.jpg","folder":"migrated/imported-media","fileName":"limbua-happy-person.jpg"})
img=up.get("identifier") or ((up.get("error") or {}).get("code")=="conflict" and gql('{jcr(workspace:EDIT){nodeByPath(path:"/sites/sial-paris/files/migrated/imported-media/limbua-happy-person.jpg"){uuid}}}')["data"]["jcr"]["nodeByPath"]["uuid"])
gql(f'mutation{{jcr{{mutateNode(pathOrId:"/sites/sial-paris/files/migrated/imported-media/limbua-happy-person.jpg"){{publish}}}}}}')
print("image uuid:",img)

# 2. set real content (fr) via GraphQL setValue (i18n props need language)
def setp(name,val,lang="fr",typ="STRING"):
    q=f'mutation{{jcr{{mutateNode(pathOrId:"{NODE}"){{mutateProperty(name:"{name}"){{setValue(language:"{lang}",value:{json.dumps(val)})}}}}}}}}' if lang else f'mutation{{jcr{{mutateNode(pathOrId:"{NODE}"){{mutateProperty(name:"{name}"){{setValue(type:{typ},value:{json.dumps(val)})}}}}}}}}'
    return gql(q)
setp("title",TITLE); setp("excerpt",EXCERPT); setp("body",BODY)
# thumbnail weakref (not i18n)
gql(f'mutation{{jcr{{mutateNode(pathOrId:"{NODE}"){{mutateProperty(name:"thumbnail"){{setValue(type:WEAKREFERENCE,value:"{img}")}}}}}}}}')
# publish
gql(f'mutation{{jcr{{mutateNode(pathOrId:"{NODE}"){{publish}}}}}}')
print("LIMBUA updated + published")
