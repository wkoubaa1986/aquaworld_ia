"""Extraction des paragraphes traduisibles d'un PDF TEXTE (PyMuPDF).

Un paragraphe = un groupe de lignes d'un bloc MuPDF, avec sa boîte, son texte recollé et son
style dominant. Les images, dessins et fonds ne sont pas touchés : seule la couche texte est lue,
et c'est elle seule qui sera remplacée (voir rendu.py). Tout ce qui ne dépend pas de PyMuPDF est
une fonction pure, testée sans PDF.
"""

from __future__ import annotations

import re

import frappe
from frappe import _

# Sous ce total de caractères, le PDF est un scan ou du texte en contours : rien à traduire.
MIN_CARACTERES_DOCUMENT = 200
# Écart vertical (en hauteurs de ligne) au-delà duquel deux lignes d'un même bloc font deux
# paragraphes (puces, cellules de tableau collées dans un même bloc).
SAUT_PARAGRAPHE = 0.6


def extraire_paragraphes(pdf_bytes: bytes) -> tuple[list[dict], dict]:
	"""-> (paragraphes, {pages, blocs}). Lève une erreur claire si le PDF n'a pas de texte."""
	import pymupdf

	doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
	paragraphes, total = [], 0
	for no, page in enumerate(doc):
		rect = (page.rect.x0, page.rect.y0, page.rect.x1, page.rect.y1)
		for bloc in page.get_text("dict", sort=True)["blocks"]:
			if bloc.get("type") != 0:
				continue
			for p in paragraphes_depuis_bloc(bloc, no, rect):
				p["id"] = len(paragraphes)
				paragraphes.append(p)
				total += len(p["texte"])
	if total < MIN_CARACTERES_DOCUMENT:
		frappe.throw(_("Ce PDF ne contient pas de texte extractible (scan ou texte en contours) : "
		               "traduction impossible."))
	return paragraphes, {"pages": len(doc), "blocs": len(paragraphes)}


# ------------------------------------------------------------------ fonctions pures


def paragraphes_depuis_bloc(bloc: dict, page_no: int, page_rect: tuple) -> list[dict]:
	"""Un bloc MuPDF (dict avec `lines` → `spans`) -> 0..n paragraphes."""
	lignes = [l for l in bloc.get("lines", []) if l.get("spans")]
	if not lignes:
		return []
	sorties = []
	for groupe in grouper_lignes(lignes):
		texte = fusionner_lignes(["".join(s.get("text", "") for s in l["spans"]) for l in groupe])
		if not texte.strip():
			continue
		spans = [s for l in groupe for s in l["spans"]]
		bbox = _union([l["bbox"] for l in groupe])
		sorties.append({
			"page": page_no,
			"bbox": bbox,
			"texte": texte,
			"style": style_dominant(spans, bbox, page_rect, [l["bbox"] for l in groupe]),
			"dir": tuple(groupe[0].get("dir", (1, 0))),
			"lignes": len(groupe),
		})
	return sorties


def grouper_lignes(lignes: list[dict]) -> list[list[dict]]:
	"""Coupe un bloc en paragraphes sur les grands écarts verticaux."""
	groupes, courant = [], [lignes[0]]
	for prec, ligne in zip(lignes, lignes[1:]):
		h = max(1.0, prec["bbox"][3] - prec["bbox"][1])
		ecart = ligne["bbox"][1] - prec["bbox"][3]
		if ecart > SAUT_PARAGRAPHE * h:
			groupes.append(courant)
			courant = [ligne]
		else:
			courant.append(ligne)
	groupes.append(courant)
	return groupes


def _union(boites: list) -> tuple:
	return (min(b[0] for b in boites), min(b[1] for b in boites),
	        max(b[2] for b in boites), max(b[3] for b in boites))


def fusionner_lignes(lignes: list[str]) -> str:
	"""Joint les lignes par un espace et recolle les césures (« instal-» + « lation »)."""
	texte = ""
	for brut in lignes:
		ligne = " ".join(brut.split())
		if not ligne:
			continue
		if texte.endswith("-") and ligne[:1].islower():
			texte = texte[:-1] + ligne
		elif texte:
			texte += " " + ligne
		else:
			texte = ligne
	return texte


def couleur_hex(valeur) -> str:
	try:
		v = int(valeur or 0)
	except (TypeError, ValueError):
		v = 0
	return "#%06x" % (v & 0xFFFFFF)


def style_dominant(spans: list[dict], bbox=None, page_rect=None, boites_lignes=None) -> dict:
	"""Le style du span le plus long : taille, gras, italique, couleur, police, alignement."""
	if not spans:
		return {"taille": 10.0, "gras": False, "italique": False, "couleur": "#000000", "police": "", "align": "left"}
	principal = max(spans, key=lambda s: len(s.get("text", "")))
	police = str(principal.get("font", "") or "")
	flags = int(principal.get("flags", 0) or 0)
	return {
		"taille": round(float(principal.get("size", 10) or 10), 2),
		"gras": bool(flags & 16) or "bold" in police.lower() or "black" in police.lower(),
		"italique": bool(flags & 2) or "italic" in police.lower() or "oblique" in police.lower(),
		"couleur": couleur_hex(principal.get("color")),
		"police": police,
		"align": alignement(bbox, boites_lignes, page_rect),
	}


def alignement(bbox, boites_lignes, page_rect, tolerance: float = 2.0) -> str:
	"""« center » si chaque ligne est centrée dans le bloc et qu'au moins une est plus courte ;
	« right » si les lignes finissent au même bord droit avec des débuts différents ; sinon « left »."""
	if not bbox or not boites_lignes or len(boites_lignes) < 2:
		return "left"
	cx = (bbox[0] + bbox[2]) / 2
	centres = all(abs((b[0] + b[2]) / 2 - cx) <= tolerance for b in boites_lignes)
	largeurs = {round(b[2] - b[0]) for b in boites_lignes}
	if centres and len(largeurs) > 1:
		return "center"
	droites = all(abs(b[2] - bbox[2]) <= tolerance for b in boites_lignes)
	gauches = all(abs(b[0] - bbox[0]) <= tolerance for b in boites_lignes)
	if droites and not gauches:
		return "right"
	return "left"


_REFERENCE = re.compile(r"[A-Z0-9][A-Z0-9\-_/.]*")


def est_traduisible(texte: str) -> bool:
	"""Faux pour ce qui ne doit pas passer par l'IA : nombres et unités seuls, URL, e-mails,
	références (AB-1234), lettres isolées."""
	t = (texte or "").strip()
	if len(t) < 2:
		return False
	if re.search(r"https?://|www\.|@", t):
		return False
	lettres = re.findall(r"[^\W\d_]", t)
	if len(lettres) < 2:
		return False
	if " " not in t:
		if _REFERENCE.fullmatch(t):
			return False
		if len(lettres) <= 3 and re.search(r"\d", t):
			return False
	return True


def dedoublonner(paragraphes: list[dict]) -> tuple[list[str], dict]:
	"""-> (textes uniques, {id paragraphe: indice du texte unique}) : un en-tête répété sur
	40 pages se traduit une fois."""
	uniques, positions, index = [], {}, {}
	for p in paragraphes:
		cle = " ".join(p["texte"].split())
		if cle not in positions:
			positions[cle] = len(uniques)
			uniques.append(p["texte"])
		index[p["id"]] = positions[cle]
	return uniques, index


def repartir_lots(textes: list[str], taille_max: int = 25, chars_max: int = 6000) -> list[list[int]]:
	"""Indices des textes, par lots bornés en nombre et en caractères (un très long paragraphe
	fait un lot à lui seul)."""
	lots, courant, chars = [], [], 0
	for i, t in enumerate(textes):
		n = len(t)
		if courant and (len(courant) >= max(1, taille_max) or chars + n > chars_max):
			lots.append(courant)
			courant, chars = [], 0
		courant.append(i)
		chars += n
	if courant:
		lots.append(courant)
	return lots
