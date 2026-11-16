"""Le design « SEL EN PASTILLES » fait sur le dev (décor en aplats deux couleurs, état du 13/11/2026) arrive À CÔTÉ de
la fiche EMB-2026-0006 du site, qui reste telle quelle (demande 16/11/2026 : « dans la prod je ne vois pas ce que j'ai
fait en dev par rapport à l'impression en aplats ; je veux garder ça en prod comme historique »).

Le patch v0_55 n'a rien écrit en prod : la fiche y avait été retravaillée depuis sa copie vers le dev, et il n'écrase
pas un travail fait sur place. Celui-ci crée donc un second design (`transfert.design_a_cote`) : une copie de la fiche
du site par le chemin de « Dupliquer », qui reçoit les champs et les fichiers du dev. Les deux fiches portent un
commentaire qui renvoie l'une à l'autre.

Rien n'est créé si la fiche du site est déjà celle du dev (le dev lui-même, ou un site où le patch v0_55 est passé),
ni au second passage. Une erreur est consignée (Error Log) sans bloquer la migration ; à rejouer alors à la main :
`bench --site <site> execute aquaworld_ia.transfert.design_a_cote --kwargs "{'nom': 'EMB-2026-0006'}"`.
"""
import frappe

NOM = "EMB-2026-0006"


def execute():
	from aquaworld_ia import transfert

	if not frappe.db.exists("DocType", transfert.DESIGN):
		return
	try:
		bilan = transfert.design_a_cote(NOM)
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title=f"Aquaworld IA : design {NOM} du dev non créé à côté", message=frappe.get_traceback())
		print(f"Aquaworld IA — design {NOM} du dev, à côté : ÉCHEC, voir Error Log")
		return
	print(f"Aquaworld IA — design {NOM} du dev, à côté : {bilan}")
