# Copyright (c) 2026, Wassim Koubaa and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class DesignEmballage(Document):
	def validate(self):
		from aquaworld_ia.emballage import contenus, exports, pictos_images

		pictos_images.valider(self)
		contenus.synchroniser_saisie(self, self.get_doc_before_save())
		if self.plan_a_plat and exports.etat(self)["pdf"] != "a_jour":
			self.statut = "À recomposer"
		elif self.plan_a_plat and self.statut == "À recomposer":
			self.statut = "Plan prêt"
