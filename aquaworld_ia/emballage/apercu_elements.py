"""Visuels des pictogrammes, tampons et codes dans le plan interactif du studio."""
from __future__ import annotations

import base64
import hashlib
import io

import frappe
from PIL import Image

from aquaworld_ia.emballage import codes, composition as C, pictos
from aquaworld_ia.emballage import geometrie


def choix_zones(doc, textes: dict, langues: dict, familles: set, fam_titres: str) -> dict:
	"""Un aperçu pour chacun des choix du menu, même si aucune zone de ce type n'est posée."""
	choix = {}
	for type_zone in (*C.ZONES_AJOUTABLES, "qr"):
		z = {"zone": "code_barres" if type_zone == "qr" else type_zone, "x": 0, "y": 0, "w": 100, "h": 35}
		if type_zone == "qr":
			z.update(code="qr", w=35)
		if type_zone == "photo":
			z.update(w=35)
		z["libelle"] = geometrie.libelle_zone(z)
		if z["zone"] in C.ZONES_TEXTE:
			z["apercu_texte"] = C.html_zone(doc, z, textes, langues, familles, fam_titres=fam_titres)
		choix[type_zone] = z
	return choix


def image_url(octets: bytes) -> str:
	"""Une image embarquée, sans fichier supplémentaire ni dépendance aux URL privées."""
	if C.est_svg(octets):
		mime = "image/svg+xml"
	else:
		with Image.open(io.BytesIO(octets)) as im:
			mime = Image.MIME.get(im.format)
			if mime not in ("image/png", "image/jpeg", "image/webp", "image/gif"):
				b = io.BytesIO(); im.convert("RGBA").save(b, "PNG")
				octets, mime = b.getvalue(), "image/png"
	return "data:%s;base64,%s" % (mime, base64.b64encode(octets).decode("ascii"))


def enrichir(doc, apercu: dict) -> None:
	"""La sélection et le placement viennent du moteur PDF. Une image n'est transmise
	qu'une fois, même si elle apparaît sur plusieurs faces ou dans plusieurs zones.
	"""
	faces = apercu.get("faces", [])
	choix = apercu.get("choix_zones", {})
	faces_a_dessiner = faces + ([{"code": "avant", "zones": list(choix.values()), "choix": True}] if choix else [])
	if not any(z["zone"] in ("pictos", "code_barres") for f in faces_a_dessiner for z in f["zones"]):
		return
	pictos_svg = [(p.pictogramme, pictos.svg_bytes(p.pictogramme)) for p in doc.get("pictogrammes") or []]
	pictos_svg = [(c, s) for c, s in pictos_svg if s]
	from aquaworld_ia.emballage import pictos_images
	images_pictos = pictos_images.charger(doc)
	tampons = set(frappe.get_all("Aquaworld IA Pictogramme", filters={"categorie": "Tampon",
		"code": ["in", [c for c, _ in pictos_svg]]}, pluck="code")) if pictos_svg else set()
	if choix:
		for code in sorted(tampons):
			choix[f"tampon:{code}"] = {"zone": "pictos", "pictos": [code], "libelle": "Tampon",
				"x": 0, "y": 0, "w": 35, "h": 35}
		faces_a_dessiner[-1]["zones"] = list(choix.values())
	ean = qr = None
	if doc.get("type_code_barres") in ("EAN-13", "EAN-13 + QR") and codes.valider_ean13(doc.get("code_barres")):
		ean = codes.ean13_svg(doc.get("code_barres"))
	if doc.get("type_code_barres") in ("QR", "EAN-13 + QR") and doc.get("url_qr"):
		qr = codes.qr_svg(doc.get("url_qr"), doc.get("couleur_qr"))
	qr_place = any(z["zone"] == "code_barres" and z.get("code") == "qr" for f in faces for z in f["zones"])
	couleur = C.couleur_texte_sur(doc.get("couleur_fond") or "#e5e7eb")
	images, cache = {}, {}
	for face in faces_a_dessiner:
		for z in face["zones"]:
			if z["zone"] not in ("pictos", "code_barres"):
				continue
			z.pop("apercu_message", None)
			z["apercu_elements"] = []
			for el in C.elements_symboles(z, face["code"], pictos_svg=pictos_svg, tampons=tampons,
			                             images_pictos=images_pictos,
			                             sans_cartouche=bool(doc.get("pictos_sans_cartouche")), couleur=couleur,
			                             ean=ean, qr=qr, qr_place=qr_place if not face.get("choix") else False):
				cle = (el["image"], el["logo"])
				if cle not in cache:
					try:
						image = C.preparer_logo(el["image"]) if el["logo"] else el["image"]
						url = image_url(image)
						identifiant = hashlib.sha256(image).hexdigest()
						images[identifiant] = url
						cache[cle] = identifiant
					except (OSError, ValueError):
						cache[cle] = None
				if cache[cle]:
					z["apercu_elements"].append({"image": cache[cle], "rect": el["rect"], "fond": el["fond"], "code": el["code"]})
					if el.get("rotation"):
						z["apercu_elements"][-1]["rotation"] = el["rotation"]
			if not z["apercu_elements"]:
				z["apercu_message"] = ("Aucun pictogramme choisi pour cette zone."
					if z["zone"] == "pictos" and C.selection_pictos(z) == [] else
					"Aucun pictogramme à afficher : vérifiez la sélection et la taille de la zone."
					if z["zone"] == "pictos" else "Code absent ou invalide : renseignez-le dans Contenus.")
	apercu["images_zones"] = images
