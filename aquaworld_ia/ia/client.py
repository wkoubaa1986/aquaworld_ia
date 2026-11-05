"""Le client OpenAI de l'app.

Relu ICI plutôt qu'importé de bank_retenue_sync : une app de traduction et de design ne doit pas
dépendre d'une app comptable pour lire une clé. Ordre de lecture :

1. `Aquaworld IA Reglages` (modèles seulement : la clé n'y est pas dupliquée) ;
2. `AI Settings` — le Single livré par woocommerce_fusion, où la clé est déjà en place
   (`openai_api_key`, `open_ai_model`, `open_ai_temperature`) ;
3. `site_config.json` (`openai_api_key`, `openai_model`).
"""

from __future__ import annotations

import frappe
from frappe import _

MODELE_TEXTE_DEFAUT = "gpt-4o-mini"
# gpt-image-2 : le modèle vedette d'OpenAI (avril 2026) ; gpt-image-1 est arrêté le 23/10/2026.
MODELE_IMAGE_DEFAUT = "gpt-image-2"
QUALITE_IMAGE_DEFAUT = "medium"

# Les noms de fonctionnalités sont aussi ceux du journal : un même outil garde son
# réglage dans les appels directs, les workers, les reprises et les lots parallèles.
CHAMPS_MODELES_TEXTE = {
	"Document produit — fiche technique": "modele_fiche_technique",
	"Document produit — manuel": "modele_manuel_produit",
	"Document produit — lecture": "modele_lecture_documents",
	"Document produit — traduction": "modele_traduction_documents",
	"Manuel": "modele_traduction_manuels",
	"Manuel lecture": "modele_studio_manuel",
	"Manuel mise en page": "modele_studio_manuel",
	"Emballage texte": "modele_texte_emballage",
	"Tampon IA": "modele_texte_emballage",
}
CHAMPS_MODELES_IMAGE = {
	"Manuel illustration": "modele_image_manuels",
	"Emballage image": "modele_image_emballage",
	"Emballage fond": "modele_image_emballage",
	"Emballage faces": "modele_image_emballage",
	"Logo IA": "modele_logo",
	"Mockup 3D": "modele_mockup",
}


class PlafondAtteint(frappe.ValidationError):
	"""Le plafond mensuel de dépense IA des réglages est atteint : rien ne part."""


def reglages():
	"""Le Single de l'app — un dict vide tant qu'il n'est pas migré, pour que les modules purs
	restent importables hors site."""
	try:
		return frappe.get_cached_doc("Aquaworld IA Reglages")
	except Exception:
		return frappe._dict()


def _ai_settings():
	try:
		if frappe.db.exists("DocType", "AI Settings"):
			return frappe.get_cached_doc("AI Settings")
	except Exception:
		pass
	return None


def _valeur(doc, *champs):
	for champ in champs:
		valeur = getattr(doc, champ, None) if doc is not None else None
		if valeur is not None and str(valeur).strip():
			return str(valeur).strip()
	return None


def cle_api() -> str:
	cle = _valeur(_ai_settings(), "openai_api_key") or frappe.conf.get("openai_api_key")
	if not cle:
		frappe.throw(_("Clé OpenAI absente : renseignez AI Settings (openai_api_key) ou site_config.json."))
	return cle


def modele_texte(fonctionnalite: str | None = None) -> str:
	"""Modèle effectif, sans construire un client ni lire la clé API."""
	r = reglages()
	champ = CHAMPS_MODELES_TEXTE.get(fonctionnalite)
	return (
		(_valeur(r, champ) if champ else None)
		or _valeur(r, "modele_texte")
		or _valeur(_ai_settings(), "open_ai_model")
		or frappe.conf.get("openai_model")
		or MODELE_TEXTE_DEFAUT
	)


def modele_image(fonctionnalite: str | None = None) -> str:
	r = reglages()
	champ = CHAMPS_MODELES_IMAGE.get(fonctionnalite)
	return (
		(_valeur(r, champ) if champ else None)
		or _valeur(r, "modele_image")
		or MODELE_IMAGE_DEFAUT
	)


def client_et_modele(usage: str = "texte", *, fonctionnalite: str | None = None):
	"""-> (client OpenAI, modèle de l'outil ou défaut général, température)."""
	from openai import OpenAI

	client = OpenAI(api_key=cle_api())
	if usage == "image":
		return client, modele_image(fonctionnalite), None
	modele = modele_texte(fonctionnalite)
	try:
		temperature = float(_valeur(_ai_settings(), "open_ai_temperature") or 0.2)
	except (TypeError, ValueError):
		temperature = 0.2
	return client, modele, temperature


def qualite_image() -> str:
	return _valeur(reglages(), "qualite_image") or QUALITE_IMAGE_DEFAUT
