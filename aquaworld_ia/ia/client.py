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
MODELE_IMAGE_DEFAUT = "gpt-image-1"
QUALITE_IMAGE_DEFAUT = "medium"


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


def client_et_modele(usage: str = "texte"):
	"""-> (client OpenAI, modèle, température). Pour `usage="image"`, la température vaut None
	et le modèle est celui des réglages (gpt-image-1 par défaut)."""
	from openai import OpenAI

	r = reglages()
	client = OpenAI(api_key=cle_api())
	if usage == "image":
		return client, (_valeur(r, "modele_image") or MODELE_IMAGE_DEFAUT), None
	modele = (
		_valeur(r, "modele_texte")
		or _valeur(_ai_settings(), "open_ai_model")
		or frappe.conf.get("openai_model")
		or MODELE_TEXTE_DEFAUT
	)
	try:
		temperature = float(_valeur(_ai_settings(), "open_ai_temperature") or 0.2)
	except (TypeError, ValueError):
		temperature = 0.2
	return client, modele, temperature


def qualite_image() -> str:
	return _valeur(reglages(), "qualite_image") or QUALITE_IMAGE_DEFAUT
