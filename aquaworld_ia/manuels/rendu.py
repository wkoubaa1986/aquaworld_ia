"""Réécriture EN PLACE d'un PDF : on efface la couche texte de chaque paragraphe et on pose la
traduction dans la même boîte (PyMuPDF `insert_htmlbox`, qui réduit la police jusqu'à ce que ça
tienne et façonne l'arabe de droite à gauche).

Images, dessins et fonds restent intacts : la redaction ne retire QUE le texte (`images=0,
graphics=0`), sans aplat blanc (`fill=False`). Un texte sur fond coloré garde son fond.
"""

from __future__ import annotations

import html
import io
import os

CHEMIN_POLICES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public", "fonts")
ECHELLE_MIN = 0.5           # en dessous, on ne pose pas : le bloc est signalé « non placé »
ECHELLE_REDUIT = 0.8        # en dessous, le bloc compte comme « réduit » (à relire)
EXTENSION_MAX = 0.4         # une boîte peut s'allonger vers le bas de 40 % au plus


def polices_archive():
	import pymupdf

	return pymupdf.Archive(CHEMIN_POLICES)


def css_base() -> str:
	return (
		"@font-face{font-family:'Noto Sans';src:url(NotoSans-Regular.ttf);font-weight:400;}"
		"@font-face{font-family:'Noto Sans';src:url(NotoSans-Bold.ttf);font-weight:700;}"
		"@font-face{font-family:'Noto Naskh Arabic';src:url(NotoNaskhArabic-Regular.ttf);font-weight:400;}"
		"@font-face{font-family:'Noto Naskh Arabic';src:url(NotoNaskhArabic-Bold.ttf);font-weight:700;}"
		"body{margin:0;padding:0;}p{margin:0;padding:0;line-height:1.15;}"
	)


def famille(langue: dict) -> str:
	return langue.get("police") or ("Noto Naskh Arabic" if langue.get("rtl") else "Noto Sans")


def html_paragraphe(texte: str, style: dict, rtl: bool = False, famille_police: str = "Noto Sans") -> str:
	"""Un <p> stylé comme l'original (taille, gras, italique, couleur, alignement). Pur."""
	align = "right" if rtl else (style.get("align") or "left")
	if rtl and style.get("align") == "center":
		align = "center"
	regles = [
		"font-family:'%s'" % famille_police,
		"font-size:%spt" % style.get("taille", 10),
		"font-weight:%d" % (700 if style.get("gras") else 400),
		"font-style:%s" % ("italic" if style.get("italique") else "normal"),
		"color:%s" % (style.get("couleur") or "#000000"),
		"text-align:%s" % align,
		"direction:%s" % ("rtl" if rtl else "ltr"),
	]
	contenu = html.escape(texte or "").replace("\n", "<br>")
	return "<p style=\"%s\">%s</p>" % (";".join(regles), contenu)


def rect_insertion(bbox, page_rect, voisins, marge: float = 1.5, extension_max: float = EXTENSION_MAX) -> tuple:
	"""La boîte élargie vers le bas jusqu'au voisin suivant (au plus +extension_max de sa
	hauteur), pour absorber l'allongement du français ou de l'arabe. Pur."""
	x0, y0, x1, y1 = bbox
	h = y1 - y0
	limite = min(page_rect[3] - marge, y1 + h * extension_max)
	for v in voisins or []:
		# un voisin = une boîte située plus bas et qui chevauche horizontalement
		if v[1] >= y1 - 0.5 and v[2] > x0 and v[0] < x1:
			limite = min(limite, v[1] - marge)
	return (x0, y0, x1, max(y1, limite))


def reecrire_page(page, paragraphes: list[dict], traductions: dict, langue: dict, archive, css: str) -> dict:
	"""Efface puis repose les paragraphes traduits de cette page. -> stats de la page."""
	import pymupdf

	rtl = bool(langue.get("rtl"))
	police = famille(langue)
	cibles = [p for p in paragraphes if p["id"] in traductions]
	stats = {"poses": 0, "reduits": 0, "non_places": [], "pivotes": 0}
	a_poser = []
	for p in cibles:
		if tuple(p.get("dir", (1, 0))) != (1, 0):
			stats["pivotes"] += 1
			continue
		a_poser.append(p)
		page.add_redact_annot(pymupdf.Rect(*p["bbox"]), fill=False)
	if not a_poser:
		return stats
	page.apply_redactions(images=0, graphics=0, text=0)
	page_rect = (page.rect.x0, page.rect.y0, page.rect.x1, page.rect.y1)
	toutes = [q["bbox"] for q in paragraphes]
	for p in a_poser:
		contenu = html_paragraphe(traductions[p["id"]], p["style"], rtl, police)
		rect = pymupdf.Rect(*p["bbox"])
		spare, echelle = page.insert_htmlbox(rect, contenu, css=css, scale_low=ECHELLE_MIN, archive=archive)
		if spare < 0:
			voisins = [b for b in toutes if b != p["bbox"]]
			rect = pymupdf.Rect(*rect_insertion(p["bbox"], page_rect, voisins))
			spare, echelle = page.insert_htmlbox(rect, contenu, css=css, scale_low=ECHELLE_MIN, archive=archive)
		if spare < 0:
			stats["non_places"].append({"id": p["id"], "texte": p["texte"][:80]})
			# On pose quand même, réduit au maximum : un texte trop petit se relit, un trou non.
			page.insert_htmlbox(rect, contenu, css=css, scale_low=0.25, archive=archive)
			continue
		stats["poses"] += 1
		if echelle < ECHELLE_REDUIT:
			stats["reduits"] += 1
	return stats


def reecrire_document(pdf_bytes: bytes, paragraphes: list[dict], traductions: dict, langue: dict) -> tuple[bytes, dict]:
	"""-> (PDF traduit, stats globales {poses, reduits, non_places[{page,id,texte}], pivotes})."""
	import pymupdf

	doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
	archive, css = polices_archive(), css_base()
	total = {"poses": 0, "reduits": 0, "non_places": [], "pivotes": 0}
	par_page = {}
	for p in paragraphes:
		par_page.setdefault(p["page"], []).append(p)
	for no, page in enumerate(doc):
		s = reecrire_page(page, par_page.get(no, []), traductions, langue, archive, css)
		total["poses"] += s["poses"]
		total["reduits"] += s["reduits"]
		total["pivotes"] += s["pivotes"]
		total["non_places"].extend(dict(n, page=no + 1) for n in s["non_places"])
	try:
		doc.subset_fonts()
	except Exception:
		pass
	sortie = io.BytesIO()
	doc.save(sortie, garbage=3, deflate=True)
	return sortie.getvalue(), total
