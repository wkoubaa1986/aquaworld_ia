"""Accès commun aux ressources du studio."""
import frappe
from frappe import _

def image_lisible(doc, url: str) -> str:
	"""Une image que ce design peut lire : attachée à lui, en bibliothèque, ou publique. Refuse le reste."""
	if not url:
		frappe.throw(_("Image manquante."))
	if url.startswith("/files/"):
		return url
	# Frappe dédoublonne les fichiers : une même `file_url` a une fiche File par design qui la partage (une copie de
	# design, une photo prise en bibliothèque) — il suffit que L'UNE d'elles soit à ce design ou à la bibliothèque.
	if frappe.db.exists("File", {"file_url": url, "attached_to_doctype": "Design Emballage", "attached_to_name": doc.name}):
		return url
	# la photo d'un AUTRE produit (14/10/2026 : « ramener les photos d'autres produits ») : image ou pièce jointe d'un
	# article, photo d'un autre design — si l'utilisateur peut lire cet article / ce design
	for fichier in frappe.get_all("File", filters={"file_url": url,
			"attached_to_doctype": ["in", ["Item", "Brand", "Design Emballage", "Ressource Emballage"]]},
			fields=["attached_to_doctype", "attached_to_name"]):
		if fichier.attached_to_name and frappe.has_permission(
				fichier.attached_to_doctype, "read", doc=fichier.attached_to_name):
			return url
	for article in frappe.get_all("Item", filters={"image": url}, pluck="name"):
		if frappe.has_permission("Item", "read", doc=article):
			return url
	frappe.throw(_("Cette image n'appartient ni à ce design ni à la bibliothèque."))
