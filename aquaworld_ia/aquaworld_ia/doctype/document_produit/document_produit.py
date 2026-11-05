import json

import frappe
from frappe.model.document import Document

from aquaworld_ia.documents_produit import structure


class DocumentProduit(Document):
	def validate(self):
		parent = frappe.get_doc("Dossier Produit", self.dossier)
		parent.check_permission("write")
		if not self.flags.document_produit_interne:
			frappe.throw("Utilisez l’éditeur Documents produit pour créer, corriger ou valider une version.")
		avant = self.get_doc_before_save()
		if avant and any(
			self.get(k) != avant.get(k)
			for k in (
				"dossier",
				"type_document",
				"langue",
				"libelle_langue",
				"rtl",
				"titre",
				"numero",
				"contenu_json",
				"contexte_json",
				"source_fr",
				"empreinte_context",
			)
		):
			frappe.throw("Chaque correction doit être enregistrée dans une nouvelle version.")
		if self.type_document not in structure.TYPES:
			frappe.throw("Type de document inconnu.")
		structure.normaliser(json.loads(self.contenu_json), json.loads(self.contexte_json))
