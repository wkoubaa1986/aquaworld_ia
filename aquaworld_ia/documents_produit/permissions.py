"""Les liens et PDF privés héritent des droits du dossier et de l'article."""

import frappe
from frappe.model.db_query import DatabaseQuery


def dossier_permission(doc, ptype=None, user=None, **kwargs):
	if doc.get("article") and not frappe.has_permission("Item", "read", doc=doc.article, user=user):
		return False
	return None


def document_permission(doc, ptype=None, user=None, **kwargs):
	if doc.get("dossier") and not frappe.has_permission(
		"Dossier Produit", "read", doc=doc.dossier, user=user
	):
		return False
	return None


def fichier_permission(doc, ptype=None, user=None, **kwargs):
	# Même le propriétaire du fichier doit conserver l'accès au produit.
	if (
		ptype != "create"
		and doc.get("attached_to_doctype") in ("Dossier Produit", "Document Produit")
		and doc.get("attached_to_name")
		and not frappe.has_permission(doc.attached_to_doctype, "read", doc=doc.attached_to_name, user=user)
	):
		return False
	return None


def dossier_query(user=None, **kwargs):
	try:
		condition = DatabaseQuery("Item", user=user).build_match_conditions()
	except frappe.PermissionError:
		return "1=0"
	return (
		"exists (select 1 from `tabItem` where `tabItem`.name = `tabDossier Produit`.article"
		+ (" and (" + condition + ")" if condition else "")
		+ ")"
	)


def document_query(user=None, **kwargs):
	try:
		condition = DatabaseQuery("Dossier Produit", user=user).build_match_conditions()
	except frappe.PermissionError:
		return "1=0"
	return (
		"exists (select 1 from `tabDossier Produit` where `tabDossier Produit`.name = `tabDocument Produit`.dossier"
		+ (" and (" + condition + ")" if condition else "")
		+ ")"
	)
