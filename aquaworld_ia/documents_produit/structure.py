"""Contenu documentaire structuré : aucune commande LaTeX ne provient de l'IA."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import Counter

TYPES = ("Fiche technique", "Manuel d'utilisation")
LIBELLES = dict(
	caracteristiques="Caractéristiques techniques",
	variantes="Variantes couvertes",
	reference="Référence",
	configuration="Configuration",
	marque="Marque",
	parametre="Caractéristique",
	valeur="Valeur",
	unite="Unité",
	portee="Modèles concernés",
	commun="Toute la gamme",
	illustrations="Photos et illustrations",
	brouillon="BROUILLON — À RELIRE",
	version="Version",
	sources="Sources documentaires",
)


def empreinte(value):
	return hashlib.sha256(
		json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()
	).hexdigest()


def texte(value, limite=12000):
	if not isinstance(value, str):
		raise ValueError("Le contenu doit être du texte.")
	if len(value) > limite:
		raise ValueError("Un texte dépasse la longueur autorisée.")
	return value.strip().replace("\x00", "")


IMAGE_RUBRIQUE = re.compile(r"/(?:private/)?files/[^\s\"'<>]+")
POSITIONS_IMAGE = ("droite", "gauche", "dessous", "dessus")
TABLEAU_MAX = (40, 8)   # lignes, colonnes


def rubrique(s, portee):
	"""Une rubrique : titre, texte, portée, source — et, si l'utilisateur les a posés, une image (graphe, schéma)
	avec sa disposition, et un tableau (première ligne = en-têtes). Les clés image/tableau n'apparaissent que
	remplies : une version antérieure relue sans changement garde la même empreinte (demande 06/11/2026)."""
	if not isinstance(s, dict):
		raise ValueError("Rubrique invalide.")
	out = {
		"titre": texte(s.get("titre", ""), 200),
		"texte": texte(s.get("texte", "")),
		"article": portee(s.get("article")),
		"source": texte(s.get("source", ""), 600),
	}
	image = texte(s.get("image", "") or "", 500)
	if image:
		if not IMAGE_RUBRIQUE.fullmatch(image):
			raise ValueError("L’image d’une rubrique doit être un fichier de l’outil.")
		position = s.get("image_position", "droite")
		if position not in POSITIONS_IMAGE:
			raise ValueError("Disposition de l’image de rubrique invalide.")
		largeur = s.get("image_largeur", 40)
		maximum = 60 if position in ("droite", "gauche") else 100
		if isinstance(largeur, bool) or not isinstance(largeur, int) or not 20 <= largeur <= maximum:
			raise ValueError(f"La largeur de l’image doit être un entier entre 20 et {maximum} %.")
		out.update(image=image, image_position=position, image_largeur=largeur,
			image_legende=texte(s.get("image_legende", "") or "", 300))
	tableau = s.get("tableau") or []
	if tableau:
		if not isinstance(tableau, list) or len(tableau) > TABLEAU_MAX[0] or not all(isinstance(r, list) for r in tableau):
			raise ValueError("Tableau de rubrique invalide.")
		largeurs = {len(r) for r in tableau}
		if len(largeurs) != 1 or not 1 <= largeurs.pop() <= TABLEAU_MAX[1]:
			raise ValueError(f"Un tableau a au plus {TABLEAU_MAX[1]} colonnes, identiques sur chaque ligne.")
		out["tableau"] = [[texte("" if c is None else (str(c) if isinstance(c, (int, float)) and not isinstance(c, bool) else c), 300) for c in r] for r in tableau]
	return out


def normaliser(data, contexte):
	if not isinstance(data, dict):
		raise ValueError("Le contenu du document est invalide.")
	articles = {contexte["article"]["name"]} | {a["name"] for a in contexte.get("variantes", [])}

	def portee(valeur):
		valeur = texte(valeur or "", 140)
		if valeur and valeur not in articles:
			raise ValueError("Une caractéristique concerne une variante absente de la sélection.")
		return valeur

	out = {
		"titre": texte(data.get("titre", ""), 140),
		"resume": texte(data.get("resume", "")),
		"sections": [],
		"caracteristiques": [],
		"points_a_verifier": [],
		"libelles": {k: texte(data.get("libelles", {}).get(k, v), 200) for k, v in LIBELLES.items()},
	}
	if not out["titre"]:
		raise ValueError("Le titre est obligatoire.")
	# Une ligne de caractéristique sans nom ni valeur (ligne ajoutée puis laissée vide, ou capturée par erreur) ne
	# compte pas : elle était comptée dans la limite et faisait refuser le document (06/11/2026).
	if isinstance(data.get("caracteristiques"), list):
		data = {**data, "caracteristiques": [c for c in data["caracteristiques"]
			if isinstance(c, dict) and (str(c.get("nom") or "").strip() or str(c.get("valeur") or "").strip())]}
	for cle, limite in (("sections", 40), ("caracteristiques", 250), ("points_a_verifier", 80)):
		if not isinstance(data.get(cle, []), list) or len(data.get(cle, [])) > limite:
			raise ValueError("Liste documentaire invalide : " + cle)
	for s in data.get("sections", []):
		out["sections"].append(rubrique(s, portee))
	for c in data.get("caracteristiques", []):
		out["caracteristiques"].append(
			{
				**{
					k: texte(c.get(k, ""), 1500 if k == "valeur" else 600)
					for k in ("nom", "valeur", "unite", "source")
				},
				"article": portee(c.get("article")),
			}
		)
	out["points_a_verifier"] = [texte(p, 1000) for p in data.get("points_a_verifier", []) if p]
	# Ces données proviennent des articles, pas d'une invention du modèle.
	out["variantes"] = copy.deepcopy(
		data.get("variantes")
		if data.get("variantes") is not None
		else [
			{
				"article": a["name"],
				"nom": a["item_name"],
				"marque": contexte.get("marque_document") or a.get("brand") or "",
				"attributs": a["attributs"],
			}
			for a in contexte.get("variantes", [])
		]
	)
	attendus = {a["name"]: a for a in contexte.get("variantes", [])}
	if not isinstance(out["variantes"], list) or len(out["variantes"]) != len(attendus):
		raise ValueError("Les variantes du document ne correspondent plus à la sélection.")
	vus = set()
	for v in out["variantes"]:
		if not isinstance(v, dict) or v.get("article") not in attendus or v["article"] in vus:
			raise ValueError("Référence de variante invalide.")
		vus.add(v["article"])
		a = attendus[v["article"]]
		if v.get("marque", "") != (contexte.get("marque_document") or a.get("brand") or ""):
			raise ValueError("La marque commerciale doit être conservée.")
		v["nom"] = texte(v.get("nom", ""), 500)
		if not isinstance(v.get("attributs"), list) or len(v["attributs"]) != len(a["attributs"]):
			raise ValueError("Attributs de variante incomplets.")
		for attr in v["attributs"]:
			attr["nom"] = texte(attr.get("nom", ""), 140)
			attr["valeur"] = texte(attr.get("valeur", ""), 500)
	out["legendes"] = [
		texte(s, 500)
		for s in data.get("legendes", [i.get("legende", "") for i in contexte.get("images", [])])
	]
	if len(out["legendes"]) != len(contexte.get("images", [])):
		raise ValueError("Le nombre de légendes ne correspond pas aux images.")
	return out


def champs_traduisibles(contenu):
	paths = [("titre",), ("resume",)]
	paths += [("libelles", k) for k in LIBELLES]
	for cle, champs in (("sections", ("titre", "texte")), ("caracteristiques", ("nom", "valeur"))):
		for i, _row in enumerate(contenu[cle]):
			paths += [(cle, i, k) for k in champs]
	for i, s in enumerate(contenu["sections"]):
		if s.get("image"):
			paths.append(("sections", i, "image_legende"))
		for r, ligne in enumerate(s.get("tableau") or []):
			paths += [("sections", i, "tableau", r, c) for c in range(len(ligne))]
	paths += [("points_a_verifier", i) for i in range(len(contenu["points_a_verifier"]))]
	paths += [("legendes", i) for i in range(len(contenu["legendes"]))]
	for i, v in enumerate(contenu["variantes"]):
		paths.append(("variantes", i, "nom"))
		for j, _a in enumerate(v["attributs"]):
			paths += [("variantes", i, "attributs", j, k) for k in ("nom", "valeur")]
	return [p for p in paths if lire_chemin(contenu, p).strip()]


def lire_chemin(data, path):
	for k in path:
		data = data[k]
	return data


def poser_chemin(data, path, value):
	for k in path[:-1]:
		data = data[k]
	data[path[-1]] = value


def tokens_proteges(texte, contexte):
	noms = {contexte["article"]["name"], contexte["article"].get("brand") or ""}
	noms.add(contexte.get("marque_document") or "")
	for v in contexte.get("variantes", []):
		noms.update([v["name"], v.get("brand") or ""])
		for a in v["attributs"]:
			if "marque" in a["nom"].lower():
				noms.add(a["valeur"])
	# Conserve les unités et toutes les valeurs, y compris leur multiplicité.
	tokens = Counter(re.findall(r"[+-]?\d+(?:[.,]\d+)*(?:[eE][+-]?\d+)?", texte))
	for n in noms:
		if n and n in texte:
			tokens["nom:" + n] = texte.count(n)
	for n in re.findall(
		r"(?<!\w)(?:m³/h|m3/h|L/h|l/h|L/min|V|Hz|kW|W|mm|cm|kg|bar|psi|°C|GPD|ppm|µm)(?!\w)", texte
	):
		tokens["unite:" + n] += 1
	return tokens


def appliquer_traduction(contenu, paths, sortie, contexte):
	items = sortie.get("items") if isinstance(sortie, dict) else None
	if not isinstance(items, list) or len(items) != len(paths):
		raise ValueError("La traduction est incomplète. Relancez la traduction.")
	resultat = copy.deepcopy(contenu)
	vus = set()
	for item in items:
		i = item.get("i")
		if type(i) is not int or i < 0 or i >= len(paths) or i in vus:
			raise ValueError("La traduction contient un élément invalide.")
		vus.add(i)
		t = texte(item.get("t", ""))
		if not t or tokens_proteges(t, contexte) != tokens_proteges(lire_chemin(contenu, paths[i]), contexte):
			raise ValueError(
				"La traduction a modifié une référence, une marque, une valeur ou une unité. Relancez-la."
			)
		poser_chemin(resultat, paths[i], t)
	return resultat
