"""Choix de la marque commerciale et gestion de son logo depuis le dossier."""

import frappe

from aquaworld_ia.documents_produit import contexte as C


def lire(name, permission="read"):
	d = frappe.get_doc("Brand", name)
	d.check_permission(permission)
	return d


def effective(dossier):
	return dossier.get("marque_document") or C.article_lisible(dossier.article).brand or ""


def disponibles():
	if not frappe.has_permission("Brand", "read"):
		return []
	return frappe.get_list("Brand", fields=["name"], order_by="name", limit_page_length=1000)


def logo(name, tolerer_absent=False):
	resultat = {"logo": ""}
	if not name:
		return resultat
	try:
		url = lire(name).image
		if url and url.startswith(("/files/", "/private/files/")):
			f = C.fichier_lisible(url)
			resultat.update(logo=f.file_url, logo_hash=f.content_hash)
	except (frappe.PermissionError, frappe.DoesNotExistError):
		if not tolerer_absent:
			raise
	return resultat


def infos(name):
	if not name:
		return {"name": "", "logo": "", "peut_modifier": False}
	d = lire(name)
	return {"name": d.name, **logo(d.name, tolerer_absent=True), "peut_modifier": d.has_permission("write")}
