# Copyright (c) 2026, Wassim Koubaa and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from aquaworld_ia.emballage import mise_en_forme
from aquaworld_ia.manuels import rendu


class PoliceEmballage(Document):
	"""Une police ajoutée pour les emballages (demande utilisateur 24/09/2026 : « choisir la
	police »), en plus des polices livrées. Un fichier par style : MuPDF ne fabrique ni le gras ni
	l'italique."""

	def validate(self):
		self.nom = (self.nom or "").strip()
		if not mise_en_forme.NOM_POLICE.fullmatch(self.nom):
			frappe.throw(_("Nom de police invalide : lettres, chiffres, espaces, points et tirets seulement (60 caractères au plus)."))
		reserves = set(rendu.POLICES_LIVREES) | {rendu.FAMILLE_TITRES, rendu.FAMILLE_TEXTES}
		if self.nom in reserves or self.nom.lower().startswith("police "):
			frappe.throw(_("« {0} » est déjà le nom d'une police livrée ou réservée : choisissez-en un autre.").format(self.nom))
		for cle, _poids, _style in rendu.STYLES_POLICE:
			if self.get(cle):
				verifier_fichier_police(self.get(cle), self.meta.get_label(cle))


def verifier_fichier_police(url: str, libelle: str) -> None:
	"""Le fichier doit être une police TrueType/OpenType que le moteur PDF sait lire."""
	import pymupdf

	from aquaworld_ia.ia import fichiers

	if not url.lower().rsplit("?", 1)[0].endswith((".ttf", ".otf")):
		frappe.throw(_("{0} : un fichier .ttf ou .otf est attendu.").format(libelle))
	try:
		pymupdf.Font(fontbuffer=fichiers.lire(url))
	except Exception:
		frappe.throw(_("{0} : ce fichier n'est pas une police lisible.").format(libelle))
