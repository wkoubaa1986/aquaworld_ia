"""Centrage local sur l'encre visible d'un logo, sans modifier son fichier."""
from __future__ import annotations

import io
import warnings

import frappe
from PIL import Image, ImageChops, UnidentifiedImageError

MAX_OCTETS = 20 * 1024 * 1024
MAX_PIXELS = 25_000_000
MAX_COTE = 1600


def detecter_contenu(octets: bytes) -> dict:
	"""Centre et rectangle relatifs à l'image entière. La transparence et le blanc de fond
	sont ignorés ; les lettres, symboles et détails blancs sur fond transparent sont conservés.
	La rastérisation sert uniquement à la mesure, le fichier SVG original reste vectoriel.
	"""
	from aquaworld_ia.emballage.composition import est_svg, svg_vers_pdf

	if len(octets) > MAX_OCTETS:
		raise ValueError("Logo trop lourd : maximum 20 Mo.")
	if est_svg(octets):
		import pymupdf

		with svg_vers_pdf(octets) as svg:
			page = svg[0]
			facteur = min(2, MAX_COTE / max(page.rect.width, page.rect.height))
			pix = page.get_pixmap(matrix=pymupdf.Matrix(facteur, facteur), alpha=True)
			# PNG déprémultiplie l'alpha : les couleurs pâles aux bords restent correctement mesurées.
			im = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGBA")
	else:
		try:
			with warnings.catch_warnings():
				warnings.simplefilter("error", Image.DecompressionBombWarning)
				with Image.open(io.BytesIO(octets)) as source:
					if source.width * source.height > MAX_PIXELS:
						raise ValueError("Logo trop grand : maximum 25 mégapixels.")
					im = source.convert("RGBA")
		except (UnidentifiedImageError, OSError, Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
			raise ValueError("Logo illisible : utilisez un SVG, PNG ou JPEG valide.") from exc
		im.thumbnail((MAX_COTE, MAX_COTE), Image.Resampling.LANCZOS)
	w, h = im.size
	alpha = im.getchannel("A").point(lambda a: 255 if a > 16 else 0)
	# Le fond blanc n'est retiré de la mesure que si les quatre coins sont opaques et blancs.
	# Un logo blanc sur transparence doit, lui, être détecté par son alpha.
	coins = [im.getpixel((x, y)) for x, y in ((0, 0), (w-1, 0), (0, h-1), (w-1, h-1))]
	fond_blanc = all(c[3] >= 240 and min(c[:3]) >= 243 for c in coins)
	masque = alpha
	if fond_blanc:
		r, g, b, _a = im.split()
		sombre = ImageChops.darker(ImageChops.darker(r, g), b).point(lambda c: 255 if c < 243 else 0)
		masque = ImageChops.multiply(alpha, sombre)
	bbox = masque.getbbox()
	if not bbox:
		raise ValueError("Aucune écriture ni forme visible détectée dans ce logo.")
	x0, y0, x1, y1 = bbox
	return {"x": round((x0 + x1) / (2 * w), 6), "y": round((y0 + y1) / (2 * h), 6),
	        "limites": [round(x0/w, 6), round(y0/h, 6), round(x1/w, 6), round(y1/h, 6)],
	        "fond_blanc": fond_blanc}


@frappe.whitelist()
def analyser_logo(design: str, face: str, indice: int) -> dict:
	"""Lecture du logo effectivement placé dans cette zone, après vérification des droits."""
	from aquaworld_ia.emballage.ressources import image_lisible
	from aquaworld_ia.emballage.studio import apercu_du_doc
	from aquaworld_ia.emballage.variantes import url_logo
	from aquaworld_ia.ia import fichiers

	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("read")
	apercu = apercu_du_doc(doc) or {}
	f = next((f for f in apercu.get("faces", []) if f["code"] == face), None)
	try:
		i = int(indice)
	except (TypeError, ValueError):
		i = -1
	if not f or not 0 <= i < len(f["zones"]) or f["zones"][i]["zone"] != "logo":
		frappe.throw("Sélectionnez une zone Logo sur la facette.")
	url = image_lisible(doc, f["zones"][i].get("logo") or url_logo(doc))
	try:
		mesure = detecter_contenu(fichiers.lire(url))
	except ValueError as exc:
		frappe.throw(str(exc))
	return {"centre": {"x": mesure["x"], "y": mesure["y"], "source": url}, "limites": mesure["limites"]}
