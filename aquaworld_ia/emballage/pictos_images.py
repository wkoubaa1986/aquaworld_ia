"""Variantes SVG privées d'un pictogramme, propres à une zone du design."""
from __future__ import annotations

import json
import re

import frappe
from frappe import _
from frappe.utils import cint


def variantes(zone):
	v = zone.get("pictos_images") if zone.get("zone") == "pictos" else None
	return {c: u for c, u in v.items() if isinstance(c, str) and isinstance(u, str) and u} if isinstance(v, dict) else {}


def verifier_fichier(doc, url):
	"""Seuls les SVG attachés à ce design peuvent devenir une variante locale."""
	if not isinstance(url, str) or not url.lower().endswith(".svg") or not frappe.db.exists("File", {
		"file_url": url, "attached_to_doctype": "Design Emballage", "attached_to_name": doc.name,
	}):
		frappe.throw(_("Choisissez un SVG créé ou attaché à ce design."))
	return url


def urls_du_design(doc):
	mep = doc.get("mise_en_page") or {}
	if isinstance(mep, str):
		mep = json.loads(mep)
	return {u for zones in mep.values() if isinstance(zones, list) for z in zones
		if isinstance(z, dict) for u in variantes(z).values()} if isinstance(mep, dict) else set()


def valider(doc):
	for url in urls_du_design(doc):
		verifier_fichier(doc, url)


def charger(doc):
	from aquaworld_ia.ia import fichiers

	return {url: fichiers.lire(verifier_fichier(doc, url)) for url in urls_du_design(doc)}


def transformer(octets, mode="couleur", couleur="#000000", garder_blanc=True, couleurs=16, retirer_fond=False):
	"""Les courbes d'un vrai SVG sont conservées ; un bitmap doit être retracé."""
	from aquaworld_ia.emballage import logo_couleur as LC, vectorisation as V
	from aquaworld_ia.emballage.composition import est_svg

	if mode not in ("couleur", "vectoriser"):
		raise ValueError("Choisissez Recolorer ou Vectoriser en couleurs.")
	if len(octets) > V.MAX_OCTETS:
		raise ValueError("Image trop lourde : maximum 20 Mo.")
	vectoriel = LC.svg_vectoriel(octets)
	infos = {"source_vectorielle": vectoriel, "trace": not vectoriel, "avertissements": []}
	if mode == "couleur" and vectoriel:
		# Les encres d'un masque ou filtre participent à la silhouette, pas à sa couleur.
		# Éviter de modifier leur luminance en prétendant conserver exactement le dessin.
		if re.search(rb"<(?:[\w-]+:)?(?:mask|filter)\b", octets, re.I):
			raise ValueError("Ce SVG utilise un masque ou un filtre. Exportez une version SVG avec les effets décomposés pour recolorer sans modifier la silhouette.")
		c = LC.normaliser(couleur)
		if not c:
			raise ValueError("Saisissez une couleur au format #RRGGBB.")
		svg = LC.recolorer_svg(octets, c, garder_blanc)
	elif vectoriel:
		svg = octets  # Déjà vectoriel : aucune dégradation par un nouveau tracé.
	else:
		if mode == "couleur" and not LC.normaliser(couleur):
			raise ValueError("Saisissez une couleur au format #RRGGBB.")
		png = LC.rasteriser_svg(octets) if est_svg(octets) else octets
		svg, details = V.vectoriser(png, "logo", couleurs, retirer_fond)
		infos["avertissements"] = details.get("avertissements", [])
		if mode == "couleur":
			c = LC.normaliser(couleur)
			if not c:
				raise ValueError("Saisissez une couleur au format #RRGGBB.")
			svg = LC.recolorer_svg(svg, c, garder_blanc)
		infos["avertissements"].append("Le tracé d’une image peut modifier les petits détails. Comparez les lettres et contours à l’original.")
	return svg, infos


@frappe.whitelist()
def preparer(design: str, code: str, mode="couleur", couleur="#000000", garder_blanc=1,
		couleurs=16, retirer_fond=0, source_url=None):
	from aquaworld_ia.emballage import pictos
	from aquaworld_ia.ia import fichiers
	from frappe.utils.file_manager import save_file

	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("write")
	if code not in {p.pictogramme for p in doc.get("pictogrammes") or []}:
		frappe.throw(_("Ajoutez d’abord ce pictogramme dans Contenus."))
	octets = fichiers.lire(verifier_fichier(doc, source_url)) if source_url else pictos.svg_bytes(code)
	if not octets:
		frappe.throw(_("L’image de ce pictogramme est introuvable."))
	try:
		svg, infos = transformer(octets, mode, couleur, bool(cint(garder_blanc)), cint(couleurs), bool(cint(retirer_fond)))
	except ValueError as exc:
		frappe.throw(str(exc))
	f = save_file("%s-picto-%s.svg" % (doc.name, frappe.scrub(code)[:40]), svg,
		"Design Emballage", doc.name, is_private=1)
	return dict(infos, candidat=f.file_url, format="svg")
