"""Les dossiers produit créés avant la v0.47 reçoivent ce qu'un nouveau dossier a d'office (demande 12/11/2026 :
« pourquoi je ne vois pas l'autre image du parent et le QR code du site automatiquement ? ») :

- les images de l'article parent absentes du dossier, ajoutées À LA SUITE de ses photos (la photo principale et
  l'ordre choisis ne changent pas) ;
- le QR code du produit sur le site, sur la fiche et le manuel, là où aucun lien n'est encore saisi.
- le bloc « Le produit en images » en deuxième position, là où l'ordre des blocs est resté celui d'origine.

Une seule fois : une photo ou un QR retirés ensuite ne reviennent pas. Rien d'autre n'est modifié (ni textes, ni
versions, ni reste de la mise en page) ; les versions passent « à actualiser », comme après tout changement de
présentation, et leur PDF se refait sans appel IA. Un dossier en échec est consigné (Error Log) sans bloquer
les autres ni la migration.
"""
import json

import frappe

DOSSIER = "Dossier Produit"


def execute():
	if not frappe.db.exists("DocType", DOSSIER):
		return
	bilan = []
	for name in frappe.get_all(DOSSIER, pluck="name", order_by="creation"):
		try:
			changes = completer(name)
			frappe.db.commit()
			if changes:
				bilan.append(f"{name} : " + ", ".join(changes))
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"Aquaworld IA : dossier {name} non complété", message=frappe.get_traceback())
			bilan.append(f"{name} : ÉCHEC, voir Error Log")
	print("Aquaworld IA, dossiers produit complétés :", " ; ".join(bilan) or "rien à ajouter")


def completer(name):
	"""-> ce qui a été ajouté au dossier ([] si rien)."""
	from aquaworld_ia.documents_produit import contexte as C
	from aquaworld_ia.documents_produit import mise_en_page as M
	from aquaworld_ia.documents_produit import photos

	d = frappe.get_doc(DOSSIER, name)
	parent = C.article_lisible(d.article)
	changes = []

	existantes = []
	for r in d.images:
		try:
			existantes.append({"image": r.image, "hash": C.fichier_lisible(r.image, silencieux=True).content_hash})
		except Exception:
			existantes.append({"image": r.image, "hash": None})
	ajouts = photos.manquantes(existantes, photos.candidates_initiales(parent, parent))
	for ligne in ajouts:
		d.append("images", ligne)
	if ajouts:
		changes.append(f"{len(ajouts)} photo(s) de l’article")

	url = C.lien_woocommerce(d.article).get("url", "")
	if M.initiale(url):
		dispositions = M.configuration(d.get("mises_en_page"))
		poses = []
		for cle in M.TYPES.values():
			disposition = M.normaliser(dispositions.get(cle))
			if not disposition.get("qr_url"):
				dispositions[cle] = M.normaliser({**disposition, "qr_url": url,
					"qr_legende": disposition.get("qr_legende") or M.LEGENDE_QR_SITE})
				poses.append(cle)
		if poses:
			d.mises_en_page = json.dumps(dispositions, ensure_ascii=False)
			changes.append("QR code du site (" + ", ".join(poses) + ")")
	# « Le produit en images » en deuxième position, là où l'ordre des blocs n'a jamais été changé (ancien défaut).
	dispositions = M.configuration(d.get("mises_en_page"))
	deplaces = [cle for cle, disposition in dispositions.items() if disposition.get("ordre") == M.ORDRE]
	if deplaces:
		for cle in deplaces:
			dispositions[cle] = M.normaliser({**dispositions[cle], "ordre": list(M.ORDRE_DEFAUT)})
		d.mises_en_page = json.dumps(dispositions, ensure_ascii=False)
		changes.append("« Le produit en images » en 2e position (" + ", ".join(deplaces) + ")")
	if changes:
		d.save(ignore_permissions=True)
	return changes
