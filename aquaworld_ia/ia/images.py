"""L'unique point d'appel de la génération d'images (gpt-image-1) — journalisé.

`editer` = génération GUIDÉE par des images de référence (photo produit, logo, face avant
choisie) : c'est ce qui donne une cohérence de style. `generer` = fond seul, sans référence,
repli si la modération refuse l'édition.
"""

from __future__ import annotations

import base64
import io
import time

import frappe
from frappe import _

from aquaworld_ia.ia import journal
from aquaworld_ia.ia.client import client_et_modele

TAILLES = ("1024x1024", "1536x1024", "1024x1536")
COTE_MAX_REFERENCE = 2048


def _est_svg(octets: bytes) -> bool:
	debut = octets[:300].lstrip().lower()
	return debut.startswith(b"<svg") or (debut.startswith(b"<?xml") and b"<svg" in octets[:2000].lower())


def rasteriser_svg(octets: bytes, dpi: int = 300) -> bytes:
	"""SVG -> PNG (RGBA) via PyMuPDF, pour servir de référence de couleur à l'IA."""
	import pymupdf

	doc = pymupdf.open("svg", octets)
	pdf = pymupdf.open("pdf", doc.convert_to_pdf())
	pix = pdf[0].get_pixmap(dpi=dpi, alpha=True)
	return pix.tobytes("png")


def normaliser_reference(octets: bytes) -> bytes:
	"""N'importe quelle image (PNG/JPEG/WebP/SVG) -> PNG RGBA de côté ≤ 2048 px."""
	from PIL import Image

	if _est_svg(octets):
		octets = rasteriser_svg(octets)
	image = Image.open(io.BytesIO(octets)).convert("RGBA")
	if max(image.size) > COTE_MAX_REFERENCE:
		image.thumbnail((COTE_MAX_REFERENCE, COTE_MAX_REFERENCE))
	sortie = io.BytesIO()
	image.save(sortie, format="PNG")
	return sortie.getvalue()


def _decoder(reponse) -> list[bytes]:
	images = []
	for item in reponse.data or []:
		if getattr(item, "b64_json", None):
			images.append(base64.b64decode(item.b64_json))
	if not images:
		frappe.throw(_("OpenAI n'a rendu aucune image."))
	return images


def editer(prompt: str, references: list[tuple[str, bytes]], *, taille: str, qualite: str,
           n: int = 1, fonctionnalite: str, doc=None, fidelite: str | None = "high") -> list[bytes]:
	"""images.edit avec des images de référence -> liste de PNG."""
	client, modele, _ = client_et_modele("image")
	fichiers = [(f"{nom}.png", io.BytesIO(normaliser_reference(octets)), "image/png")
	            for nom, octets in references]
	params = {"model": modele, "image": fichiers, "prompt": prompt, "size": taille,
	          "quality": qualite, "n": n}
	if fidelite and modele.startswith("gpt-image"):
		params["input_fidelity"] = fidelite
	debut = time.monotonic()
	try:
		try:
			reponse = client.images.edit(**params)
		except Exception as e:
			# gpt-image-1-mini (et d'autres) refusent input_fidelity : on réessaie sans.
			if "input_fidelity" in str(e) and "input_fidelity" in params:
				params.pop("input_fidelity")
				for f in fichiers:
					f[1].seek(0)
				reponse = client.images.edit(**params)
			else:
				raise
	except Exception as e:
		journal.enregistrer(fonctionnalite=fonctionnalite, appel="images.edit", modele=modele, doc=doc,
		                    images=0, taille=taille, qualite=qualite,
		                    duree_ms=(time.monotonic() - debut) * 1000, erreur=str(e))
		raise
	journal.enregistrer(fonctionnalite=fonctionnalite, appel="images.edit", modele=modele, doc=doc,
	                    usage=getattr(reponse, "usage", None), images=n, taille=taille, qualite=qualite,
	                    duree_ms=(time.monotonic() - debut) * 1000)
	return _decoder(reponse)


def generer(prompt: str, *, taille: str, qualite: str, n: int = 1, fonctionnalite: str, doc=None) -> list[bytes]:
	"""images.generate sans référence -> liste de PNG."""
	client, modele, _ = client_et_modele("image")
	debut = time.monotonic()
	try:
		reponse = client.images.generate(model=modele, prompt=prompt, size=taille, quality=qualite, n=n)
	except Exception as e:
		journal.enregistrer(fonctionnalite=fonctionnalite, appel="images.generate", modele=modele, doc=doc,
		                    images=0, taille=taille, qualite=qualite,
		                    duree_ms=(time.monotonic() - debut) * 1000, erreur=str(e))
		raise
	journal.enregistrer(fonctionnalite=fonctionnalite, appel="images.generate", modele=modele, doc=doc,
	                    usage=getattr(reponse, "usage", None), images=n, taille=taille, qualite=qualite,
	                    duree_ms=(time.monotonic() - debut) * 1000)
	return _decoder(reponse)
