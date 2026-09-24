"""Le catalogue des pictogrammes (SVG livrés dans public/pictos/) et son semis en base.

⚠️ Les pictogrammes réglementaires (CE, DEEE…) engagent : ceux livrés ici sont des dessins
génériques à faire VALIDER par l'équipe avant impression. Un SVG absent du dossier n'est pas
semé ; une fiche existante n'est jamais modifiée.
"""

from __future__ import annotations

import os

import frappe

CHEMIN_PICTOS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public", "pictos")

# code, libellé, catégorie, fichier, taille (mm), obligatoire
CATALOGUE = [
	("ce", "Marquage CE", "Réglementaire", "ce.svg", 10.0, 0),
	("deee", "DEEE (poubelle barrée)", "Réglementaire", "deee.svg", 10.0, 0),
	("recyclage", "Recyclable", "Recyclage", "recyclage.svg", 10.0, 0),
	("fragile", "Fragile", "Manutention", "fragile.svg", 12.0, 0),
	("haut", "Ce côté vers le haut", "Manutention", "haut.svg", 12.0, 0),
	("humidite", "Craint l'humidité", "Manutention", "humidite.svg", 12.0, 0),
	("lire_notice", "Lire la notice", "Sécurité", "lire_notice.svg", 10.0, 0),
	# Ajoutés le 24/09/2026 (demande utilisateur : « d'autres types ») — symboles GÉNÉRIQUES, pas des
	# marques : NSF, WQA, etc. se téléversent avec leur visuel officiel via « Ajouter ».
	("contact_alimentaire", "Contact alimentaire (verre et fourchette)", "Alimentaire", "contact_alimentaire.svg", 10.0, 0),
	("sans_bpa", "Sans BPA", "Qualité de l'eau", "sans_bpa.svg", 10.0, 0),
	("eau_potable", "Eau potable", "Qualité de l'eau", "eau_potable.svg", 10.0, 0),
	("garantie", "Garantie (bouclier)", "Garantie", "garantie.svg", 10.0, 0),
	("temperature", "Plage de température", "Sécurité", "temperature.svg", 10.0, 0),
	("pression", "Pression maximale", "Sécurité", "pression.svg", 10.0, 0),
	("iso", "Certifié ISO (générique)", "Certification", "iso.svg", 10.0, 0),
]


def catalogue() -> list[dict]:
	return [{"code": c, "libelle": l, "categorie": cat, "fichier": f, "taille_mm": t, "obligatoire": o,
	         "present": os.path.exists(os.path.join(CHEMIN_PICTOS, f))}
	        for c, l, cat, f, t, o in CATALOGUE]


def svg_bytes(code: str) -> bytes | None:
	"""L'image d'un pictogramme : l'IMAGE ATTACHÉE à la fiche d'abord (photo de certification, logo
	d'organisme, PNG/JPEG/SVG — demande utilisateur 23/09/2026), sinon le SVG du catalogue. None
	s'il est introuvable. Le nom est historique : le résultat n'est plus forcément un SVG."""
	fichier, image = None, None
	try:
		fichier, image = frappe.db.get_value("Aquaworld IA Pictogramme", code, ["fichier", "image"]) or (None, None)
	except Exception:
		pass
	if image:
		try:
			from aquaworld_ia.ia import fichiers

			return fichiers.lire(image)
		except Exception:
			frappe.log_error(title="Aquaworld IA : image du pictogramme %s" % code, message=frappe.get_traceback())
	if not fichier:
		fichier = next((f for c, _l, _cat, f, _t, _o in CATALOGUE if c == code), None)
	if not fichier:
		return None
	chemin = os.path.join(CHEMIN_PICTOS, os.path.basename(fichier))
	if not os.path.exists(chemin):
		return None
	with open(chemin, "rb") as fh:
		return fh.read()


def taille_mm(code: str, defaut: float = 12.0) -> float:
	try:
		t = frappe.db.get_value("Aquaworld IA Pictogramme", code, "taille_mm")
		return float(t) if t else defaut
	except Exception:
		return defaut


def semer_pictogrammes() -> int:
	if not frappe.db.exists("DocType", "Aquaworld IA Pictogramme"):
		return 0
	ajoutes = 0
	for p in catalogue():
		if not p["present"] or frappe.db.exists("Aquaworld IA Pictogramme", p["code"]):
			continue
		frappe.get_doc({"doctype": "Aquaworld IA Pictogramme", "code": p["code"], "libelle": p["libelle"],
		                "categorie": p["categorie"], "fichier": p["fichier"], "taille_mm": p["taille_mm"],
		                "obligatoire": p["obligatoire"], "actif": 1}).insert(ignore_permissions=True)
		ajoutes += 1
	return ajoutes
