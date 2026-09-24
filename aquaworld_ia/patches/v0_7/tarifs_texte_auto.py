"""Les Réglages livrés jusqu'en v0.6 portaient la grille gpt-4o-mini (0,15 / 0,60 $ par million)
alors que le modèle texte en service est gpt-5.2 (1,75 / 14 $) : le coût affiché était ~20 fois
trop bas. Un site encore sur ces deux défauts passe en « automatique » (vide = grille intégrée du
modèle). Une valeur saisie exprès reste telle quelle. Idempotent.
"""

import frappe
from frappe.utils import flt


def execute():
	if not frappe.db.exists("DocType", "Aquaworld IA Reglages"):
		return
	r = frappe.get_single("Aquaworld IA Reglages")
	if abs(flt(r.prix_entree_par_million) - 0.15) < 1e-6 and abs(flt(r.prix_sortie_par_million) - 0.60) < 1e-6:
		frappe.db.set_single_value("Aquaworld IA Reglages", {"prix_entree_par_million": 0, "prix_sortie_par_million": 0})
		frappe.clear_cache(doctype="Aquaworld IA Reglages")
