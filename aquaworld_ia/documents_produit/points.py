"""Traiter un point à vérifier avec l'IA (demande 12/11/2026 : « un mécanisme qui permet d'ajouter les points ou
les corriger dans les rubriques avec une assistance IA ; rouge par défaut, vert quand c'est traité par l'IA »).

L'utilisateur donne l'information qui répond au point ; l'IA propose où et comment l'écrire dans le document
(présentation, introduction de la gamme, une rubrique existante, une nouvelle rubrique, une caractéristique). Ce
module applique ces modifications au contenu À L'ÉCRAN — rien n'est enregistré avant « Enregistrer » — et range le
point parmi les points traités, avec ce qui a été fait. Un point traité ne bloque plus la validation ; il se
rouvre d'un clic.

Module PUR : la requête à l'IA est dans traitement.traiter_point.
"""

from __future__ import annotations

import copy

TYPES = ("resume", "gamme", "section", "nouvelle_section", "caracteristique")
# Comment choisir la catégorie d'une caractéristique (13/11/2026). Essai réel sur AP-M : rangées par grandeur seule,
# la longueur et la matière d'un filtre partaient en « Dimensions » et « Matériaux », loin de sa finesse.
REGLE_CATEGORIES = ("Choisis la catégorie d'après l'élément que la ligne décrit, avant la grandeur mesurée : tout ce qui décrit un filtre, une cartouche "
	"ou une membrane (finesse, longueur, matière, type, nombre) va avec la filtration ; les dimensions, le poids et les matériaux ne concernent que "
	"l'appareil entier (encombrement, socle, corps) ; ce que l'appareil produit (débit ou capacité de production, rendement) va avec les performances ; "
	"une pression, un raccord ou un réservoir avec l'hydraulique ; une tension, un courant ou une puissance avec l'électricité ; un élément livré avec "
	"le produit (robinet, collier, accessoire) avec les équipements fournis. Adapte ce principe aux catégories réellement proposées.")
MAX_MODIFICATIONS = 12

CONSIGNE = """Tu intègres dans un document produit technique existant UNE information fournie par l'entreprise, pour lever un point à vérifier.
Réponds uniquement en JSON {modifications:[…], action:texte, reste_a_verifier:[texte]}.
Chaque modification a un type :
- {type:"section", index, texte, titre} : réécrit la rubrique document.sections[index] — rends son texte COMPLET, l'information intégrée à sa place, le reste conservé ;
- {type:"nouvelle_section", titre, texte, article} : ajoute une rubrique, seulement si aucune rubrique existante ne convient ;
- {type:"caracteristique", nom, valeur, unite, article, categorie} : ajoute une valeur technique au tableau, ou remplace celle de même nom ; categorie est EXACTEMENT l'une des « categories_caracteristiques » fournies (celle qui convient le mieux), ou une chaîne vide si aucune ne convient ;
- {type:"resume", texte} : réécrit la présentation (texte complet) ;
- {type:"gamme", texte} : réécrit l'introduction de la gamme (texte complet), si le document en a une.
Choisis l'endroit le plus naturel : une valeur mesurable (débit, pression, dimension, volume, tension…) va en caracteristique ; une explication va dans la rubrique qui traite du sujet. Une même information peut donner une caractéristique ET une phrase dans une rubrique, sans la répéter ailleurs. Si « destination » est imposée, écris uniquement à cet endroit.
L'information de l'entreprise est un fait : écris-la au présent, sans réserve, et n'ajoute rien qu'elle ne dise pas. Ne modifie que ce qui est nécessaire ; ne touche pas aux autres parties.
Garde chaque valeur dans l'unité donnée par l'entreprise (gallons, GPD, psi, pouces…) : le système calcule lui-même l'équivalent métrique à l'impression. Ne convertis pas, et ne demande ni conversion ni source de conversion dans reste_a_verifier.
article est une référence exacte du contexte, ou une chaîne vide pour toute la gamme.
action : une phrase courte qui dit ce que tu as écrit et où. reste_a_verifier : ce que l'information ne permet pas de lever (liste vide si le point est levé)."""
CONSIGNE += "\n" + REGLE_CATEGORIES

# Compléter le tableau des caractéristiques (demande 12/11/2026 : « le tableau des caractéristiques, est-ce que je
# peux l'enrichir par IA ? »). Deux façons, une seule consigne : l'utilisateur colle un texte (extrait de fiche
# fournisseur, notes) dont l'IA tire les valeurs ; ou, sans texte, elle relit l'article et les sources du dossier et
# ajoute les valeurs qui manquent au tableau. Elle n'écrit que des caractéristiques.
MAX_CARACTERISTIQUES = 40
CONSIGNE_CARACTERISTIQUES = """Tu complètes le tableau des caractéristiques techniques d'un document produit existant (document.caracteristiques).
Réponds uniquement en JSON {modifications:[{type:"caracteristique", nom, valeur, unite, article, source, categorie}], action:texte, reste_a_verifier:[texte]}.
categorie est EXACTEMENT l'une des « categories_caracteristiques » fournies, ou une chaîne vide si aucune ne convient. N'invente pas de catégorie.
Si « information_de_l_entreprise » est fournie : c'est un fait donné par l'entreprise. Tires-en chaque valeur technique, une ligne par grandeur (nom court et usuel, valeur, unité), sans rien ajouter qu'elle ne dise pas ; n'exploite alors que ce texte.
Si elle est vide : relis contexte (article, variantes, preuves) et ajoute les valeurs techniques qui y figurent et manquent au tableau, avec leur source (« Article REF » ou une preuve comme « S1 p.3 »).
Une caractéristique est une valeur technique : débit, pression, température, dimensions, poids, volume, raccords, alimentation, matériaux, nombre d'étages… Les attributs des variantes (contexte.variantes[].attributs) sont déjà dans le tableau des variantes : ne les recopie pas.
Ne répète pas une ligne déjà au tableau avec la même valeur. Pour corriger une valeur existante, reprends exactement son nom. Une valeur qui dépend du modèle donne une ligne par modèle, avec article.
Garde chaque valeur dans l'unité donnée (gallons, GPD, psi, pouces…) : le système calcule lui-même l'équivalent métrique à l'impression. Ne convertis pas, et ne demande ni conversion ni source de conversion.
article est une référence exacte du contexte, ou une chaîne vide pour toute la gamme.
action : une phrase courte qui dit ce que tu as ajouté ou corrigé. reste_a_verifier : les valeurs ambiguës, contradictoires ou illisibles que tu n'as pas écrites (liste vide sinon)."""
CONSIGNE_CARACTERISTIQUES += "\n" + REGLE_CATEGORIES


# Organiser le tableau (demande 13/11/2026 : « est-ce que l'IA peut les organiser par catégories ? »). L'IA ne fait
# que ranger : `classer` n'applique que la catégorie, et seulement une catégorie de la liste.
CONSIGNE_ORGANISER = """Tu ranges les lignes du tableau des caractéristiques techniques d'un document produit dans des catégories.
Réponds uniquement en JSON {classement:[{index, categorie}], suggestions:[texte]}.
Pour CHAQUE ligne de « lignes », donne son index et la catégorie qui lui convient le mieux, choisie EXACTEMENT parmi « categories_caracteristiques ». Une chaîne vide si vraiment aucune ne convient. N'invente pas de catégorie, ne modifie ni le nom, ni la valeur, ni l'unité d'une ligne, n'ajoute et ne retire aucune ligne.
""" + REGLE_CATEGORIES + """
suggestions : au plus 6 remarques courtes sur le tableau, sans rien changer toi-même — une ligne dont la valeur ne dit rien de plus que son nom, deux lignes qui se répètent, une ligne qui n'est pas une valeur technique. Désigne chaque ligne par son nom entre guillemets « », jamais par son index. Liste vide s'il n'y a rien à signaler."""


def classer(contenu, data, categories):
	"""Applique le classement proposé à une copie du contenu : la catégorie de chaque ligne, rien d'autre, et
	seulement une catégorie de `categories` (ou aucune). Les lignes sont ensuite regroupées dans l'ordre de la liste.
	-> (contenu, changements, suggestions) ; changements = [{"index", "libelle"}], index dans le tableau regroupé."""
	from aquaworld_ia.documents_produit import structure as S

	nouveau = copy.deepcopy(contenu)
	lignes = nouveau.get("caracteristiques", [])
	classement = data.get("classement") if isinstance(data, dict) else None
	deplacees = []
	for c in classement if isinstance(classement, list) else []:
		if not isinstance(c, dict):
			continue
		index = c.get("index")
		if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(lignes):
			continue
		categorie = S.categorie_admise(_texte(c.get("categorie"), 200), categories)
		ligne = lignes[index]
		if categorie == (ligne.get("categorie") or ""):
			continue
		if categorie:
			ligne["categorie"] = categorie
		else:
			ligne.pop("categorie", None)
		deplacees.append(ligne)
	nouveau["caracteristiques"] = S.ranger_caracteristiques(lignes, categories)
	changements = [{"index": i, "libelle": "« " + l.get("nom", "") + " » → " + (l.get("categorie") or "sans catégorie")}
		for i, l in enumerate(nouveau["caracteristiques"]) if any(l is d for d in deplacees)]
	suggestions = [_texte(x, 400) for x in (data.get("suggestions") if isinstance(data, dict) and isinstance(data.get("suggestions"), list) else [])]
	return nouveau, changements, [x for x in suggestions if x][:6]


def document_pour_ia(contenu):
	"""Ce que l'IA voit du document : les parties qu'elle peut modifier, numérotées."""
	return {
		"titre": contenu.get("titre", ""),
		"resume": contenu.get("resume", ""),
		"gamme": contenu.get("gamme", ""),
		"sections": [{"index": i, "titre": s.get("titre", ""), "texte": s.get("texte", ""), "article": s.get("article", "")}
			for i, s in enumerate(contenu.get("sections", []))],
		"caracteristiques": [{"nom": c.get("nom", ""), "valeur": c.get("valeur", ""), "unite": c.get("unite", ""), "article": c.get("article", ""),
				**({"categorie": c["categorie"]} if c.get("categorie") else {})}
			for c in contenu.get("caracteristiques", [])],
	}


def _texte(valeur, limite):
	return str(valeur).strip()[:limite] if isinstance(valeur, (str, int, float)) and not isinstance(valeur, bool) else ""


def appliquer(contenu, data, articles, source, destination=None, maximum=MAX_MODIFICATIONS, sources_admises=None,
		portee_imposee="", categories=()):
	"""Applique les modifications proposées à une copie du contenu.

	`articles` : les références admises comme portée ; `source` : ce qui est noté comme source des ajouts ;
	`destination` : {"type", "index"?} si l'utilisateur a imposé l'endroit (les autres modifications sont écartées) ;
	`sources_admises` : les références qu'une caractéristique peut citer elle-même (« Article REF », « S1 ») — une
	source citée qui n'en contient aucune est remplacée par `source` ; `portee_imposee` : dans la fiche d'une
	variante, ce qui est écrit lui est propre (sinon l'actualisation depuis la fiche du produit l'effacerait).
	`categories` : les catégories admises pour une caractéristique ajoutée (une ligne existante garde la sienne) ;
	le tableau est ensuite regroupé dans l'ordre de cette liste, et les index des changements suivent.
	Une modification mal formée est ignorée. -> (contenu, changements, textes_ecrits)
	changements = [{"type", "index"?, "libelle"}] ; textes_ecrits sert au contrôle des nombres."""
	from aquaworld_ia.documents_produit import structure as S

	nouveau = copy.deepcopy(contenu)
	changements, textes = [], []
	touchees = []   # (changement, ligne) : l'index est recalculé après le regroupement par catégorie
	modifications = data.get("modifications") if isinstance(data, dict) else None
	if not isinstance(modifications, list):
		return nouveau, changements, textes
	impose = (destination or {}).get("type") if isinstance(destination, dict) else None
	if impose not in TYPES:
		impose = None
	for m in modifications[:maximum]:
		if not isinstance(m, dict) or m.get("type") not in TYPES:
			continue
		genre = m["type"]
		if impose and (genre != impose or (impose == "section" and m.get("index") != destination.get("index"))):
			continue
		texte = _texte(m.get("texte"), 12000)
		portee = _texte(m.get("article"), 140)
		portee = portee_imposee or (portee if portee in articles else "")
		if genre == "resume" and texte:
			nouveau["resume"] = texte
			changements.append({"type": "resume", "libelle": "Présentation modifiée"})
			textes.append(texte)
		elif genre == "gamme" and texte and len(nouveau.get("variantes", [])) >= 2:
			nouveau["gamme"] = texte[:3000]
			changements.append({"type": "gamme", "libelle": "« Gamme et configurations » modifiée"})
			textes.append(texte[:3000])
		elif genre == "section" and texte:
			index = m.get("index")
			if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(nouveau.get("sections", [])):
				continue
			rubrique = nouveau["sections"][index]
			rubrique["texte"] = texte
			titre = _texte(m.get("titre"), 200)
			if titre:
				rubrique["titre"] = titre
			changements.append({"type": "section", "index": index, "libelle": "Rubrique « " + rubrique.get("titre", "") + " » modifiée"})
			textes.append(texte)
		elif genre == "nouvelle_section" and texte:
			titre = _texte(m.get("titre"), 200)
			if not titre or len(nouveau.setdefault("sections", [])) >= 40:
				continue
			nouveau["sections"].append({"titre": titre, "texte": texte, "article": portee, "source": source})
			changements.append({"type": "section", "index": len(nouveau["sections"]) - 1, "libelle": "Rubrique « " + titre + " » ajoutée"})
			textes += [titre, texte]
		elif genre == "caracteristique":
			nom, valeur, unite = _texte(m.get("nom"), 600), _texte(m.get("valeur"), 1500), _texte(m.get("unite"), 600)
			if not nom or not valeur:
				continue
			lignes = nouveau.setdefault("caracteristiques", [])
			citee = _texte(m.get("source"), 600)
			origine = citee if sources_admises and any(ref in citee for ref in sources_admises) else source
			memes = [i for i, c in enumerate(lignes) if c.get("nom", "").strip().casefold() == nom.casefold()]
			existante = next((i for i in memes if (lignes[i].get("article") or "") == portee), None)
			if existante is None and portee_imposee:
				existante = next((i for i in memes if not lignes[i].get("article")), None)   # reprise du produit
			if existante is None:
				if len(lignes) >= 250:
					continue
				lignes.append({"nom": nom, "valeur": valeur, "unite": unite, "article": portee, "source": origine})
				categorie = S.categorie_admise(_texte(m.get("categorie"), 200), categories)
				if categorie:
					lignes[-1]["categorie"] = categorie
				changements.append({"type": "caracteristique", "index": len(lignes) - 1, "libelle": "Caractéristique « " + nom + " » ajoutée"})
				touchees.append((changements[-1], lignes[-1]))
			else:
				ligne = lignes[existante]
				if (ligne.get("valeur"), ligne.get("unite") or "", ligne.get("article") or "") == (valeur, unite, portee):
					continue   # rien de nouveau : la ligne est déjà là
				ligne.update({"valeur": valeur, "unite": unite, "source": origine, "article": portee})
				changements.append({"type": "caracteristique", "index": existante, "libelle": "Caractéristique « " + nom + " » modifiée"})
				touchees.append((changements[-1], ligne))
			textes.append(f"{nom} {valeur} {unite}")
	if touchees:
		nouveau["caracteristiques"] = S.ranger_caracteristiques(nouveau["caracteristiques"], categories)
		for changement, ligne in touchees:
			changement["index"] = next(i for i, l in enumerate(nouveau["caracteristiques"]) if l is ligne)
	return nouveau, changements, textes


def marquer_traite(contenu, point, action, information):
	"""Le point quitte les points ouverts et entre dans les points traités par l'IA, avec ce qui a été fait."""
	contenu["points_a_verifier"] = [p for p in contenu.get("points_a_verifier", []) if p != point]
	traites = [t for t in contenu.get("points_traites", []) if t.get("texte") != point]
	traites.append({"texte": point, "action": action, "information": information})
	contenu["points_traites"] = traites[-80:]
	return contenu
