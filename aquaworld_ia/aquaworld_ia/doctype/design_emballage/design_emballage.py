# Copyright (c) 2026, Wassim Koubaa and contributors
# For license information, please see license.txt

import json

import frappe
from frappe.model.document import Document

from aquaworld_ia.emballage import mise_en_forme


class DesignEmballage(Document):
	def validate(self):
		self.reporter_mise_en_forme()

	def reporter_mise_en_forme(self):
		"""Mettre une caractéristique brute en gras (ou en 14 pt…) la met aussi en forme dans les
		textes préparés par l'IA — ce sont eux qui s'impriment. Seules les lignes dont la mise en
		forme vient de changer sont reportées ; une langue qui n'a pas le même nombre de lignes est
		laissée telle quelle (le studio le signale)."""
		if not self.textes_ia or self.is_new() or not self.has_value_changed("caracteristiques"):
			return
		avant = (self.get_doc_before_save() or frappe._dict()).get("caracteristiques")
		try:
			textes = json.loads(self.textes_ia)
		except ValueError:
			return
		nouveaux, _non_apparies = mise_en_forme.reporter_styles(self.caracteristiques, textes, avant=avant)
		if nouveaux != textes:
			self.textes_ia = json.dumps(nouveaux, ensure_ascii=False)
