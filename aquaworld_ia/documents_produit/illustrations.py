"""Illustrations d'une rubrique par IA (demande 07/11/2026) : graphe depuis les données, tableau rédigé, image
générée ou retouchée.

Règle : les NOMBRES ne viennent jamais du modèle. Un graphe ou un tableau proposé par l'IA n'est accepté que si
chaque valeur chiffrée figure déjà dans le document, le contexte (article, variantes, caractéristiques, preuves)
ou l'instruction de l'utilisateur ; sinon l'appel est refusé avec la liste des valeurs inconnues. Une image
générée ne porte ni chiffre ni texte : les libellés vont dans la légende, traduite avec la version.
"""

from __future__ import annotations

import json
import re

import frappe

from aquaworld_ia.documents_produit import structure as S
from aquaworld_ia.documents_produit.traitement import REGLES_COMMUNES, fonctionnalite
from aquaworld_ia.ia import journal
from aquaworld_ia.ia.chat import chat_json

NOMBRE = re.compile(r"[+-]?\d+(?:[  \xa0]\d{3})*(?:[.,]\d+)?")
FORMATS = {"carre": "1024x1024", "paysage": "1536x1024", "portrait": "1024x1536"}
CLES_HORS_PROMPT = ("entete", "mise_en_page", "logo")
REGLE_NOMBRES = ("Chaque nombre que tu écris est recopié tel quel depuis la rubrique, le document, le contexte ou "
	"l'instruction : aucun calcul, aucune estimation, aucune valeur « typique ». Une valeur absente est omise et "
	"signalée dans points_a_verifier.")


# ---- nombres connus : pur, testé ----------------------------------------------------------------------------

def _nombres(texte):
	for m in NOMBRE.findall(str(texte or "")):
		try:
			yield S.nombre(m)
		except ValueError:
			continue


def _textes(valeur):
	"""Tous les textes d'une structure JSON (dict / liste / scalaire)."""
	if isinstance(valeur, dict):
		for v in valeur.values():
			yield from _textes(v)
	elif isinstance(valeur, (list, tuple)):
		for v in valeur:
			yield from _textes(v)
	elif valeur is not None and not isinstance(valeur, bool):
		yield str(valeur)


def corpus_nombres(contenu, ctx, instruction=""):
	"""L'ensemble des nombres connus : document à l'écran, contexte (sans en-tête ni mise en page), instruction."""
	connus = set()
	for t in _textes([contenu, {k: v for k, v in (ctx or {}).items() if k not in CLES_HORS_PROMPT}, instruction]):
		connus.update(_nombres(t))
	return connus


def nombres_inconnus(valeurs, connus):
	"""Les valeurs absentes du corpus, dans l'ordre, sans doublon."""
	manquants = []
	for v in valeurs:
		if v not in connus and v not in manquants:
			manquants.append(v)
	return manquants


def nombres_du_tableau(tableau):
	return [n for ligne in tableau for c in ligne for n in _nombres(c)]


def formater(n):
	return str(n).replace(".", ",")


# ---- prompts : purs, testés ---------------------------------------------------------------------------------

def _partie(contenu, index):
	if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(contenu["sections"]):
		raise ValueError("Rubrique introuvable.")
	return contenu["sections"][index]


def requete(genre, ctx, contenu, index, instruction, existant=None):
	"""Le message utilisateur commun aux appels texte : la rubrique, le document pour la cohérence, le contexte."""
	s = _partie(contenu, index)
	return {
		"type_document": genre,
		"instruction": instruction,
		"rubrique": {"titre": s["titre"], "texte": s["texte"], "article": s.get("article", ""), "source": s.get("source", "")},
		"document": {
			"titre": contenu["titre"], "resume": contenu["resume"][:600],
			"caracteristiques": contenu["caracteristiques"],
			"autres_rubriques": [{"titre": x["titre"], "texte": x["texte"][:300]} for i, x in enumerate(contenu["sections"]) if i != index],
		},
		"existant": existant,
		"contexte": {k: v for k, v in ctx.items() if k not in CLES_HORS_PROMPT},
	}


def prompt_image(genre, ctx, s, instruction, retouche=False):
	"""Le prompt d'image : sujet du produit, rubrique, instruction, style imprimable, sans texte ni chiffre."""
	article = ctx.get("article") or {}
	sujet = article.get("item_name") or article.get("name") or "le produit"
	marque = ctx.get("marque_document") or article.get("brand") or ""
	if marque:
		sujet += f" ({marque})"
	style = ("Style : schéma ou illustration technique épurée, fond blanc uni, traits nets, couleurs sobres, cadrage "
		"centré, adaptée à l'impression dans un document A4. Aucun texte, aucun chiffre, aucun logo, aucun filigrane "
		"dans l'image : les libellés vont dans la légende du document.")
	if retouche:
		return (f"Modifie l'image fournie (illustration de la rubrique « {s['titre']} » d'un document « {genre} » "
			f"sur {sujet}) en conservant son sujet, son style et son fond blanc. Modification demandée : {instruction}. {style}")
	return (f"Illustration pour la rubrique « {s['titre']} » d'un document « {genre} » sur {sujet}. "
		f"Contenu demandé : {instruction}. Contexte de la rubrique : {s['texte'][:500]}. {style}")


# ---- appels IA ----------------------------------------------------------------------------------------------

def _points(data):
	return [S.texte(str(x), 1000) for x in (data.get("points_a_verifier") or []) if x][:10]


def _refuser_inconnus(valeurs, contenu, ctx, instruction, quoi):
	manquants = nombres_inconnus(valeurs, corpus_nombres(contenu, ctx, instruction))
	if manquants:
		raise ValueError(f"Le {quoi} proposé contient des valeurs absentes des données : "
			+ ", ".join(formater(m) for m in manquants)
			+ ". Ajoutez-les dans l’article, les caractéristiques, le texte de la rubrique ou l’instruction, puis relancez.")


def graphe_ia(d, genre, ctx, contenu, index, instruction):
	"""Les données d'un graphe (catégories, séries) choisies par l'IA dans le document selon l'instruction, ou le
	graphe existant modifié. -> {graphe, legende, points_a_verifier}. Les valeurs sont vérifiées contre les données."""
	instruction = S.texte(instruction or "", 1500)
	if not instruction:
		raise ValueError("Indiquez ce que le graphe doit montrer.")
	s = _partie(contenu, index)
	system = ("Tu prépares les DONNÉES d'un graphe pour une rubrique d'un document produit technique, en français. "
		"Réponds uniquement en JSON {graphe:{type, titre, axe_x, axe_y, unite, categories:[texte], series:[{nom, valeurs:[nombre]}]}, "
		"legende, points_a_verifier:[texte]}. type vaut barres, barres_horizontales, courbe ou secteurs (secteurs : une seule série, "
		f"valeurs positives). Au plus {S.GRAPHE_MAX[0]} catégories et {S.GRAPHE_MAX[1]} séries, exactement une valeur numérique par "
		"catégorie (jamais de texte dans valeurs). Choisis les catégories et séries qui répondent à l'instruction (par exemple une "
		"variante par catégorie, une caractéristique par série) ; unite est l'unité des valeurs ; axe_x et axe_y nomment les axes horizontal et vertical du graphe. S'il existe un graphe (existant), "
		"pars de lui et applique l'instruction. legende : une phrase courte sous le graphe. " + REGLE_NOMBRES + "\n" + REGLES_COMMUNES)
	user = requete(genre, ctx, contenu, index, instruction, s.get("graphe"))
	with journal.suivre_generation(d.name, frappe.generate_hash(length=12), "illustrer", "fr"):
		data = chat_json(system, json.dumps(user, ensure_ascii=False), fonctionnalite=fonctionnalite(genre), doc=d)
	if not isinstance(data, dict) or not isinstance(data.get("graphe"), dict):
		raise ValueError("L’IA n’a pas renvoyé de graphe. Reformulez l’instruction.")
	spec = S.graphe(data["graphe"])
	_refuser_inconnus([v for serie in spec["series"] for v in serie["valeurs"]], contenu, ctx, instruction, "graphe")
	return {"graphe": spec, "legende": S.texte(str(data.get("legende") or ""), 300), "points_a_verifier": _points(data)}


def tableau_ia(d, genre, ctx, contenu, index, instruction):
	"""Un tableau (première ligne = en-têtes) rédigé par l'IA depuis le document selon l'instruction, ou le tableau
	existant modifié. -> {tableau, points_a_verifier}. Les nombres des cellules sont vérifiés contre les données."""
	instruction = S.texte(instruction or "", 1500)
	if not instruction:
		raise ValueError("Indiquez ce que le tableau doit présenter.")
	s = _partie(contenu, index)
	system = ("Tu prépares un tableau pour une rubrique d'un document produit technique, en français. Réponds uniquement en JSON "
		"{tableau:[[texte]], points_a_verifier:[texte]} : la première ligne contient les en-têtes, toutes les lignes ont le même "
		f"nombre de colonnes (au plus {S.TABLEAU_MAX[1]} colonnes, {S.TABLEAU_MAX[0]} lignes), cellules courtes (texte brut, pas de "
		"Markdown). Choisis lignes et colonnes qui répondent à l'instruction (par exemple une variante par ligne, une caractéristique "
		"par colonne ; ou une étape par ligne). S'il existe un tableau (existant), pars de lui et applique l'instruction. "
		+ REGLE_NOMBRES + "\n" + REGLES_COMMUNES)
	user = requete(genre, ctx, contenu, index, instruction, s.get("tableau"))
	with journal.suivre_generation(d.name, frappe.generate_hash(length=12), "illustrer", "fr"):
		data = chat_json(system, json.dumps(user, ensure_ascii=False), fonctionnalite=fonctionnalite(genre), doc=d)
	if not isinstance(data, dict) or not data.get("tableau"):
		raise ValueError("L’IA n’a pas renvoyé de tableau. Reformulez l’instruction.")
	tableau = S.rubrique({"titre": s["titre"], "tableau": data["tableau"]}, lambda v: v or "")["tableau"]
	_refuser_inconnus(nombres_du_tableau(tableau), contenu, ctx, instruction, "tableau")
	return {"tableau": tableau, "points_a_verifier": _points(data)}


def image_ia(d, genre, ctx, contenu, index, instruction, format="carre", retouche=False):
	"""Une illustration générée (ou l'image actuelle retouchée, qui sert de référence) par le modèle image, enregistrée
	comme pièce jointe privée du dossier. -> {image, legende}. Un appel image, compté dans les coûts du dossier."""
	from frappe.utils.file_manager import save_file

	from aquaworld_ia.documents_produit import contexte as C
	from aquaworld_ia.ia import images
	from aquaworld_ia.ia.client import qualite_image

	instruction = S.texte(instruction or "", 1500)
	if not instruction:
		raise ValueError("Décrivez l’illustration souhaitée." if not retouche else "Indiquez ce que l’IA doit changer dans l’image.")
	s = _partie(contenu, index)
	taille = FORMATS.get(format or "carre") or FORMATS["carre"]
	prompt = prompt_image(genre, ctx, s, instruction, retouche)
	with journal.suivre_generation(d.name, frappe.generate_hash(length=12), "illustrer", "fr"):
		if retouche:
			if not s.get("image"):
				raise ValueError("Cette rubrique n’a pas d’image à retoucher.")
			C.fichier_lisible(s["image"])
			pngs = images.editer(prompt, [("rubrique", C.octets(s["image"]))], taille=taille, qualite=qualite_image(),
				fonctionnalite=fonctionnalite(genre), doc=d)
		else:
			pngs = images.generer(prompt, taille=taille, qualite=qualite_image(), fonctionnalite=fonctionnalite(genre), doc=d)
	fichier = save_file(f"{d.name}-rubrique-{index + 1}-ia.png", pngs[0], "Dossier Produit", d.name, is_private=1)
	return {"image": fichier.file_url, "legende": S.texte(s["titre"], 300)}
