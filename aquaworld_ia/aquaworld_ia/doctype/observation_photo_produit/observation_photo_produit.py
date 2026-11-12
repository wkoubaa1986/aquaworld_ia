from frappe.model.document import Document

from aquaworld_ia.documents_produit import observations


class ObservationPhotoProduit(Document):
	"""Ce que l'IA a vu sur UNE image (identifiée par l'empreinte de son contenu), relu et corrigé au besoin.

	Une image partagée par plusieurs variantes, ou par plusieurs dossiers, n'est lue qu'une fois."""

	def validate(self):
		propre = observations.normaliser(observations.depuis_document(self))
		observations.vers_document(self, propre)
