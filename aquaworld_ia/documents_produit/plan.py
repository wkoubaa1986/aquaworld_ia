"""Plan du document (demande 12/11/2026 : « lorsque je crée la fiche, les parties dont l'IA va parler, est-ce que
je peux la guider — par exemple utilisation, entretien, les sous-rubriques ? »).

À l'étape Préparer, l'utilisateur choisit et ordonne les rubriques de la fiche technique et celles du manuel, avec
des sous-rubriques facultatives. L'IA rédige ces rubriques-là, dans cet ordre ; l'outil remet l'ordre, rétablit les
titres du plan et signale en point à vérifier ce qui manque ou sort du plan. Sans plan, rien ne change : l'IA
choisit les rubriques.

Une sous-rubrique est une ligne du texte de la rubrique qui commence par « ## » : le PDF l'imprime en sous-titre.
Elle se saisit aussi à la main dans n'importe quelle rubrique.

Le plan est rangé par type de document dans le champ `plans` du dossier ({"fiche": […], "manuel": […]}) et entre
dans le contexte de la version (clé `plan`, absente sans plan : l'empreinte des versions existantes ne bouge pas).

Module PUR.
"""

from __future__ import annotations

import copy
import json
import re
import unicodedata

TYPES = {"Fiche technique": "fiche", "Manuel d'utilisation": "manuel"}
MAX_RUBRIQUES = 20
MAX_SOUS = 8
LIMITE_TITRE = 120

_SOUS_TITRE = re.compile(r"^\s*#{2,3}\s*(.*?)\s*#*\s*$")

CONSIGNE = """contexte.plan est le plan du document, imposé par l'entreprise : « sections » reprend EXACTEMENT ces rubriques, avec ces titres, dans cet ordre, et aucune autre.
Quand une rubrique du plan a des « sous » (sous-rubriques), son texte est découpé en sous-parties dans l'ordre du plan : chacune commence par une ligne « ## » suivie du sous-titre exact, seul sur sa ligne, puis son texte sur les lignes suivantes. N'écris aucun sous-titre hors plan.
Une rubrique ou une sous-rubrique pour laquelle tu n'as aucune information est omise : ne la remplis ni de généralités ni d'excuses, le système la signale lui-même.
Une information importante des sources qui n'entre dans aucune rubrique du plan va dans points_a_verifier (« Hors plan : … »), jamais dans une rubrique supplémentaire.
Le plan est un choix éditorial, jamais une preuve technique."""

CONSIGNE_SOUS_TITRES = "Dans le texte d'une rubrique, une ligne qui commence par « ## » est un sous-titre. Conserve ceux qui existent ; n'en crée que si le plan (contexte.plan) ou une instruction le demande."


def _titre(valeur):
	if not isinstance(valeur, str):
		return ""
	return " ".join(valeur.replace("\x00", "").lstrip("#").split())[:LIMITE_TITRE]


def cle(titre):
	"""Deux titres désignent la même rubrique à la casse, aux accents et à la ponctuation près."""
	sans_accents = "".join(c for c in unicodedata.normalize("NFKD", str(titre or "")) if not unicodedata.combining(c))
	return " ".join(re.sub(r"[^a-z0-9]+", " ", sans_accents.casefold()).split())


def normaliser(valeur):
	"""-> [{"titre", "sous": [titres]}] : rubriques sans titre et doublons écartés, vingt rubriques et huit
	sous-rubriques au plus."""
	if not isinstance(valeur, list):
		return []
	plan, vus = [], set()
	for r in valeur:
		if isinstance(r, str):
			r = {"titre": r}
		if not isinstance(r, dict):
			continue
		titre = _titre(r.get("titre"))
		if not titre or cle(titre) in vus or not cle(titre):
			continue
		vus.add(cle(titre))
		sous, sous_vus = [], set()
		for s in r.get("sous") if isinstance(r.get("sous"), list) else []:
			s = _titre(s)
			if s and cle(s) and cle(s) not in sous_vus:
				sous_vus.add(cle(s))
				sous.append(s)
		plan.append({"titre": titre, "sous": sous[:MAX_SOUS]})
	return plan[:MAX_RUBRIQUES]


def configuration(valeur):
	"""Le champ `plans` du dossier -> {"fiche": plan, "manuel": plan}, sans les plans vides."""
	if valeur in (None, ""):
		return {}
	if isinstance(valeur, str):
		valeur = json.loads(valeur)
	if not isinstance(valeur, dict) or set(valeur) - set(TYPES.values()):
		raise ValueError("Les plans doivent correspondre à la fiche et au manuel.")
	resultat = {k: normaliser(v) for k, v in valeur.items()}
	return {k: v for k, v in resultat.items() if v}


def pour_document(dossier, genre):
	return configuration(dossier.get("plans")).get(TYPES[genre], [])


def appliquer(ctx, dossier, genre):
	"""Le contexte avec le plan du dossier pour ce type de document ; sans plan, pas de clé."""
	resultat = copy.deepcopy(ctx)
	plan = pour_document(dossier, genre)
	if plan:
		resultat["plan"] = plan
	else:
		resultat.pop("plan", None)
	return resultat


def sous_titre(ligne):
	"""Le sous-titre porté par une ligne « ## Titre », ou None pour une ligne de texte."""
	m = _SOUS_TITRE.match(ligne or "")
	return m.group(1) if m and m.group(1) else None


def sous_titres(texte):
	return [t for t in (sous_titre(ligne) for ligne in str(texte or "").split("\n")) if t]


def decouper(texte):
	"""Le texte d'une rubrique en morceaux, dans l'ordre : ("titre", sous-titre) ou ("texte", paragraphes)."""
	morceaux, courant = [], []

	def vider():
		bloc = "\n".join(courant).strip("\n")
		if bloc.strip():
			morceaux.append(("texte", bloc))
		courant.clear()

	for ligne in str(texte or "").split("\n"):
		titre = sous_titre(ligne)
		if titre is None:
			courant.append(ligne)
		else:
			vider()
			morceaux.append(("titre", titre))
	vider()
	return morceaux


def ordonner(sections, plan):
	"""Les rubriques dans l'ordre du plan, avec le titre exact du plan ; celles que le plan ne prévoit pas suivent,
	dans leur ordre. Une même rubrique du plan peut revenir pour plusieurs modèles : elles restent ensemble.
	-> (sections, titres hors plan)"""
	titres = {cle(r["titre"]): r["titre"] for r in plan}
	prevues, autres = {}, []
	for s in sections:
		k = cle(s.get("titre"))
		if k in titres:
			prevues.setdefault(k, []).append({**s, "titre": titres[k]})
		else:
			autres.append(s)
	dans_l_ordre = [s for r in plan for s in prevues.get(cle(r["titre"]), [])]
	return dans_l_ordre + autres, [s.get("titre", "") for s in autres]


def points(sections, plan):
	"""Ce que le plan demandait et que la rédaction n'a pas donné, et ce qu'elle a ajouté : des points à vérifier."""
	ordonnees, hors_plan = ordonner(sections, plan)
	textes = {}
	for s in ordonnees:
		textes.setdefault(cle(s.get("titre")), []).append(str(s.get("texte", "")))
	resultat = []
	for r in plan:
		texte = "\n".join(textes.get(cle(r["titre"]), []))
		if not texte.strip():
			resultat.append("Rubrique du plan sans information : « " + r["titre"] + " ». Ajoutez une source, ou donnez l’information avec « Traiter avec l’IA ».")
			continue
		presents = {cle(t) for t in sous_titres(texte)}
		manquantes = [t for t in r["sous"] if cle(t) not in presents]
		if manquantes:
			resultat.append("Sous-rubrique(s) du plan sans information dans « " + r["titre"] + " » : " + " ; ".join(manquantes) + ".")
	for titre in hors_plan:
		resultat.append("Rubrique ajoutée hors du plan : « " + titre + " ». Gardez-la ou retirez-la.")
	return resultat


def depuis_contenu(contenu):
	"""Le plan d'une version existante : ses titres de rubriques et leurs sous-titres « ## »."""
	return normaliser([{"titre": s.get("titre", ""), "sous": sous_titres(s.get("texte"))}
		for s in (contenu or {}).get("sections", []) if isinstance(s, dict)])


def resume(plan):
	"""« Applications → Entretien (Désinfection ; Cartouches) » — pour l'écran et les messages."""
	return " → ".join(r["titre"] + (" (" + " ; ".join(r["sous"]) + ")" if r["sous"] else "") for r in plan)
