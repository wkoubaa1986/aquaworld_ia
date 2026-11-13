"""Le design « SEL EN PASTILLES » (EMB-2026-0006) arrive dans l'état où il a été terminé sur le dev le 13/11/2026
(demande : « quand je pousse en prod, l'équivalent de mon document du dev, pour l'emballage du sel seulement ») :
décor de la face avant en aplats deux couleurs, posé à 85 %, textes et mise en page retouchés, PDF imprimeur sans
pixel. La copie (champs + fichiers nouveaux) est rangée dans `contenu/designs/EMB-2026-0006/`.

Rien n'est écrit si le design n'existe pas, s'il est déjà dans cet état, ou s'il a été modifié sur place depuis
que le dev l'a copié : ce cas est consigné (Error Log), sans bloquer la migration. Pour l'appliquer quand même :
`bench --site <site> execute aquaworld_ia.transfert.appliquer_design --kwargs "{'nom': 'EMB-2026-0006', 'forcer': 1}"`.
"""
import frappe

NOM = "EMB-2026-0006"


def execute():
	from aquaworld_ia import transfert

	if not frappe.db.exists("DocType", transfert.DESIGN):
		return
	try:
		bilan = transfert.appliquer_design(NOM)
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title=f"Aquaworld IA : design {NOM} non mis à jour", message=frappe.get_traceback())
		return
	print(f"Aquaworld IA — design {NOM} : {bilan}")
	if bilan["etat"] == "modifie_sur_place":
		frappe.log_error(title=f"Aquaworld IA : design {NOM} non mis à jour",
			message=f"La fiche a été modifiée sur ce site ({bilan.get('sur_place')}) depuis la copie du dev : rien n'a été écrit. "
			        "Pour appliquer quand même la copie du dev : aquaworld_ia.transfert.appliquer_design(nom, forcer=1).")
		frappe.db.commit()
