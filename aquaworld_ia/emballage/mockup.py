"""Aperçu 3D (illustration, non contractuelle) : les faces avant / côté droit / dessus rendues
depuis le plan à plat, données en référence à gpt-image-1 pour un rendu de boîte montée."""

from __future__ import annotations

import frappe
from frappe.utils.file_manager import save_file

from aquaworld_ia.emballage import geometrie, prompts
from aquaworld_ia.emballage.variantes import EVENEMENT, GENRE, plan_du_design
from aquaworld_ia.ia import etat, fichiers, images
from aquaworld_ia.ia.client import qualite_image


def faces_rendues(pdf_bytes: bytes, plan: dict, codes=("avant", "cote_droit", "dessus"), dpi: int = 150) -> list[tuple[str, bytes]]:
	import pymupdf

	page = pymupdf.open("pdf", pdf_bytes)[0]
	sorties = []
	for code in codes:
		f = geometrie.face(plan, code)
		if not f:
			continue
		clip = pymupdf.Rect(geometrie.mm_vers_pt(f["x"]), geometrie.mm_vers_pt(f["y"]),
		                    geometrie.mm_vers_pt(f["x"] + f["w"]), geometrie.mm_vers_pt(f["y"] + f["h"]))
		sorties.append((code, page.get_pixmap(dpi=dpi, clip=clip).tobytes("png")))
	return sorties


def generer_apercu_3d(design: str, utilisateur: str | None = None) -> None:
	doc = frappe.get_doc("Design Emballage", design)
	try:
		if not doc.plan_a_plat:
			raise ValueError("Composez d'abord le plan à plat.")
		plan = plan_du_design(doc)
		etat.progresser(GENRE, design, "rendu des faces", 20, EVENEMENT, utilisateur)
		refs = faces_rendues(fichiers.lire(doc.plan_a_plat), plan)
		etat.progresser(GENRE, design, "génération du rendu 3D", 50, EVENEMENT, utilisateur)
		png = images.editer(prompts.prompt_mockup(doc.nom_produit or doc.article, famille=plan.get("famille"),
		                                          references=[code for code, _png in refs]), refs, taille="1024x1024",
		                    qualite=qualite_image(), fonctionnalite="Mockup 3D", doc=doc, fidelite="high")[0]
		fichier = save_file("%s-apercu-3d.png" % doc.name, png, "Design Emballage", doc.name, is_private=1)
		frappe.db.set_value("Design Emballage", design, "apercu_3d", fichier.file_url, update_modified=False)
		frappe.db.commit()
		etat.terminer(GENRE, design, "termine")
	except Exception as e:
		frappe.log_error(title="Aquaworld IA : aperçu 3D %s" % design, message=frappe.get_traceback())
		etat.terminer(GENRE, design, "echec", erreur=str(e)[:300])
		frappe.db.commit()
	etat.progresser(GENRE, design, "terminé", 100, EVENEMENT, utilisateur, fin=1)
