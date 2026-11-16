"""Le dossier produit AP-M arrive comme exemple pour l'équipe, et sa présentation devient celle dont part tout
nouveau dossier (demande 16/11/2026 : « la version actuelle d'AP-M, je veux qu'elle soit patchée pour que, lorsque je
pousse en prod, elle soit poussée comme exemple pour mes employés ; le setting de mise en page, je le veux le setting
de base, celui d'AP-M ; l'en-tête que j'ai créé aussi »).

1. Le dossier : `transfert.appliquer_dossier("AP-M")` recrée le dossier du dev (présentation, 45 variantes, photos,
   logo AquaJad) et sa fiche technique validée le 16/11/2026 (version 20) avec son PDF, depuis la copie rangée dans
   `contenu/dossiers/AP-M/`. Rien n'est écrit si l'article AP-M n'existe pas sur le site ou si cette version y est
   déjà. Un dossier AP-M déjà présent est complété : il prend cette présentation et reçoit la version à la suite
   des siennes.
2. La présentation de base (Réglages) : la mise en page d'AP-M — sans son QR ni ses photos — et l'en-tête officiel
   (créé par le patch v0_48), seulement là où les Réglages n'en ont pas encore. Les dossiers existants ne changent pas.

Une erreur est consignée (Error Log) sans bloquer la migration ; le dossier se rejoue alors à la main :
`bench --site <site> execute aquaworld_ia.transfert.appliquer_dossier --kwargs "{'cle': 'AP-M'}"`.
"""
import json
import os

import frappe

CLE = "AP-M"


def execute():
	from aquaworld_ia import transfert

	if not frappe.db.exists("DocType", transfert.DOSSIER_PRODUIT):
		return
	try:
		bilan = transfert.appliquer_dossier(CLE)
		frappe.db.commit()
		print(f"Aquaworld IA — dossier d'exemple {CLE} : {bilan}")
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title=f"Aquaworld IA : dossier d'exemple {CLE} non apporté", message=frappe.get_traceback())
		print(f"Aquaworld IA — dossier d'exemple {CLE} : ÉCHEC, voir Error Log")
	try:
		print("Aquaworld IA — présentation de base des nouveaux dossiers :", presentation_de_base())
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="Aquaworld IA : présentation de base des dossiers produit", message=frappe.get_traceback())
		print("Aquaworld IA — présentation de base des nouveaux dossiers : ÉCHEC, voir Error Log")


def presentation_de_base(cle=CLE):
	"""-> ce qui a été posé dans les Réglages ([] si tout y était déjà)."""
	from aquaworld_ia import transfert
	from aquaworld_ia.documents_produit import mise_en_page as M

	chemin = transfert._fiche_dossier(cle)
	if not os.path.exists(chemin):
		return []
	with open(chemin, encoding="utf-8") as f:
		dossier = json.load(f)["dossier"]
	r = frappe.get_single("Aquaworld IA Reglages")
	poses = []
	base = M.base(dossier.get("mises_en_page") or {})
	if base and not (r.get("mise_en_page_base") or "").strip():
		r.mise_en_page_base = json.dumps(base, ensure_ascii=False)
		poses.append("mise en page")
	entete = dossier.get("entete") or ""
	if entete and not r.get("entete_base") and frappe.db.exists("Letter Head", {"name": entete, "disabled": 0}):
		r.entete_base = entete
		poses.append("en-tête")
	if poses:
		r.save(ignore_permissions=True)
	return poses
