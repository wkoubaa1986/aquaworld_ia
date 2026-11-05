from frappe.model.document import Document


class DossierProduit(Document):
	def validate(self):
		from aquaworld_ia.documents_produit.contexte import valider_dossier

		valider_dossier(self)
