"""Lecture du contenu d'un fichier attaché (URL /files, /private/files ou http), et remise sur le disque d'un
fichier que la base connaît encore mais que le disque n'a plus."""

from __future__ import annotations

import os

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


def ecrire_si_absent(chemin: str, contenu: bytes) -> bool:
	"""Écrit `contenu` à `chemin` seulement si rien n'y est ; ne touche jamais à un fichier présent."""
	if os.path.exists(chemin):
		return False
	os.makedirs(os.path.dirname(chemin) or ".", exist_ok=True)
	provisoire = "%s.%d.tmp" % (chemin, os.getpid())
	with open(provisoire, "wb") as f:
		f.write(contenu.encode("utf-8") if isinstance(contenu, str) else contenu)
	os.replace(provisoire, chemin)
	return True


def retablir(contenu: bytes, prive: int = 1) -> int:
	"""Remet sur le disque les fichiers de même contenu que la base connaît mais que le disque n'a plus.

	`save_file` de Frappe dédoublonne par empreinte : quand une fiche File porte déjà ce contenu, il reprend son
	`file_url` sans rien écrire, puis RELIT ce fichier — et échoue (« No such file or directory ») s'il a disparu
	du disque. C'est le cas d'une base restaurée sans ses fichiers privés (13/11/2026 : « Actualiser le PDF » d'un
	design inchangé, dont l'aperçu recalculé était identique à celui de la base). À appeler juste avant `save_file` ;
	renvoie le nombre de fichiers rétablis."""
	from frappe.utils.file_manager import get_content_hash

	retablis = 0
	for fiche in frappe.get_all("File", filters={"content_hash": get_content_hash(contenu), "is_private": prive},
			fields=["name", "file_url"]):
		if (fiche.file_url or "").startswith(("/files/", "/private/files/")):
			retablis += ecrire_si_absent(frappe.get_doc("File", fiche.name).get_full_path(), contenu)
	return retablis
