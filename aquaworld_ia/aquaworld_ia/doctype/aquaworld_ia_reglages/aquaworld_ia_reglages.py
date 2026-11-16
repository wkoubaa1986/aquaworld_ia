# Copyright (c) 2026, Wassim Koubaa and contributors
# For license information, please see license.txt

import json

import frappe
from frappe.model.document import Document


class AquaworldIAReglages(Document):
	def validate(self):
		# Mise en page de base des nouveaux dossiers produit : relue et rangée comme le fait un dossier, pour qu'une
		# saisie à la main invalide soit refusée ici plutôt qu'à la création du prochain dossier.
		if (self.get("mise_en_page_base") or "").strip():
			from aquaworld_ia.documents_produit import mise_en_page as M

			try:
				base = M.base(self.mise_en_page_base)
			except ValueError as e:
				raison = "le texte n’est pas lisible." if isinstance(e, json.JSONDecodeError) else str(e)
				frappe.throw("Mise en page de base des nouveaux dossiers : " + raison + " Videz le champ pour revenir à la mise en page d’origine.")
			self.mise_en_page_base = json.dumps(base, ensure_ascii=False) if base else ""
		else:
			self.mise_en_page_base = ""
