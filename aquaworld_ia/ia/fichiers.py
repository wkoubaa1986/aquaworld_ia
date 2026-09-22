"""Lecture du contenu d'un fichier attaché (URL /files, /private/files ou http)."""

from __future__ import annotations

import frappe
from frappe import _


def lire(url: str) -> bytes:
	if not url:
		frappe.throw(_("Fichier manquant."))
	if url.startswith(("http://", "https://")) and not url.startswith(frappe.utils.get_url()):
		import requests

		r = requests.get(url, timeout=30)
		r.raise_for_status()
		return r.content
	nom = frappe.db.get_value("File", {"file_url": url}, "name")
	if not nom:
		frappe.throw(_("Fichier introuvable : {0}").format(url))
	contenu = frappe.get_doc("File", nom).get_content()
	# File.get_content() DÉCODE les fichiers texte (un SVG revient en str) : on veut toujours des octets.
	return contenu.encode("utf-8") if isinstance(contenu, str) else contenu
