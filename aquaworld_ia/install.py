"""Semis après migration : la liste prédéfinie des langues et le catalogue des pictogrammes.

Idempotent — ajoute ce qui manque, ne touche jamais à une fiche existante (l'utilisateur peut
activer/désactiver une langue, changer ses consignes, sans que le prochain migrate l'écrase).
"""

from __future__ import annotations

import frappe

# code, libellé (FR), libellé natif, rtl, actif, police, consignes de traduction
LANGUES = [
	("fr", "Français", "Français", 0, 1, "Noto Sans",
	 "Français standard, vouvoiement, terminologie technique usuelle."),
	# Anglais (demande utilisateur 24/09/2026) : pour les textes d'emballage ; c'est aussi la langue
	# source des manuels, qui ne se traduisent donc jamais vers elle.
	("en", "Anglais", "English", 0, 1, "Noto Sans",
	 "International English, imperative mood for instructions, keep units and part numbers as they are."),
	("ar", "Arabe", "العربية", 1, 1, "Noto Naskh Arabic",
	 "Arabe standard moderne. Conserver les chiffres en chiffres occidentaux (0-9) et les unités "
	 "telles quelles (V, Hz, mm, kg)."),
	("de", "Allemand", "Deutsch", 0, 0, "Noto Sans", "Deutsch, Sie-Form."),
	("es", "Espagnol", "Español", 0, 0, "Noto Sans", "Español neutro, tratamiento de usted."),
	("it", "Italien", "Italiano", 0, 0, "Noto Sans", "Italiano, forma di cortesia."),
	("pt", "Portugais", "Português", 0, 0, "Noto Sans", "Português europeu."),
	("nl", "Néerlandais", "Nederlands", 0, 0, "Noto Sans", "Nederlands, u-vorm."),
]


def after_migrate():
	semer_langues()
	from aquaworld_ia.emballage.pictos import semer_pictogrammes

	semer_pictogrammes()
	# fichiers des fixtures, Réglages, rôle « Aquaworld IA » (transfert.py) — après les fixtures
	from aquaworld_ia import transfert

	transfert.restaurer()
	frappe.db.commit()


def semer_langues() -> int:
	if not frappe.db.exists("DocType", "Aquaworld IA Langue"):
		return 0
	ajoutees = 0
	for code, libelle, natif, rtl, actif, police, consignes in LANGUES:
		if frappe.db.exists("Aquaworld IA Langue", code):
			continue
		frappe.get_doc({
			"doctype": "Aquaworld IA Langue", "code": code, "libelle": libelle, "libelle_natif": natif,
			"rtl": rtl, "actif": actif, "police": police, "instructions": consignes,
		}).insert(ignore_permissions=True)
		ajoutees += 1
	return ajoutees
