"""Aperçu 3D (illustration, non contractuelle) : les faces avant / côté droit / dessus rendues
depuis le plan à plat, données en référence à gpt-image-1 pour un rendu de boîte montée."""

from __future__ import annotations

import base64

import frappe
from frappe.utils.file_manager import save_file

from aquaworld_ia.emballage import geometrie, prompts
from aquaworld_ia.emballage.variantes import EVENEMENT, GENRE, plan_du_design
from aquaworld_ia.ia import etat, fichiers, images
from aquaworld_ia.ia.client import qualite_image


FACES_VOLUME = ("avant", "arriere", "cote_gauche", "cote_droit", "dessus", "dessous")


def faces_rendues(pdf_bytes: bytes, plan: dict, codes=("avant", "cote_droit", "dessus"), dpi: int = 150,
                  max_pixels: int = 1800) -> list[tuple[str, bytes]]:
	import pymupdf

	with pymupdf.open("pdf", pdf_bytes) as pdf:
		# Ces traits servent à l’imprimeur, pas à l’aspect de la boîte montée. Le PDF reste intact.
		for calque in pdf.layer_ui_configs() or []:
			if calque["text"] == "Découpe et plis":
				pdf.set_layer_ui_config(calque["number"], action=2)
		page = pdf[0]
		sorties = []
		for code in codes:
			f = geometrie.face(plan, code)
			if not f:
				continue
			clip = pymupdf.Rect(geometrie.mm_vers_pt(f["x"]), geometrie.mm_vers_pt(f["y"]),
			                    geometrie.mm_vers_pt(f["x"] + f["w"]), geometrie.mm_vers_pt(f["y"] + f["h"]))
			echelle = min(dpi / 72, max_pixels / max(clip.width, clip.height))
			sorties.append((code, page.get_pixmap(matrix=pymupdf.Matrix(echelle, echelle), clip=clip, alpha=False).tobytes("png")))
		return sorties


@frappe.whitelist()
def apercu_interactif(design: str) -> dict:
	"""Six textures du PDF courant, sans IA ni fichier ajouté, pour la maquette de l’étui."""
	from aquaworld_ia.emballage import exports

	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("read")
	plan = plan_du_design(doc)
	if doc.type_boite != geometrie.ETUI or not all(geometrie.face(plan, c) for c in FACES_VOLUME):
		return {"disponible": False, "raison": "La maquette interactive est disponible pour les étuis à rabats. Le rendu IA reste disponible pour cette forme."}
	if exports.etat(doc)["pdf"] != "a_jour":
		frappe.throw("Actualisez le PDF pour afficher la maquette du design actuel.")
	faces = faces_rendues(fichiers.lire(doc.plan_a_plat), plan, codes=FACES_VOLUME, dpi=100, max_pixels=1200)
	return {"disponible": True, "empreinte": doc.empreinte_plan,
	        "dimensions": {"largeur": doc.longueur_mm, "hauteur": doc.hauteur_mm, "profondeur": doc.profondeur_mm},
	        "faces": {code: "data:image/png;base64," + base64.b64encode(png).decode("ascii") for code, png in faces}}


def generer_apercu_3d(design: str, utilisateur: str | None = None) -> None:
	from aquaworld_ia.emballage import exports

	doc = frappe.get_doc("Design Emballage", design)
	try:
		if exports.etat(doc)["pdf"] != "a_jour":
			raise ValueError("Actualisez le PDF avant de générer la simulation IA.")
		plan = plan_du_design(doc)
		etat.progresser(GENRE, design, "rendu des faces", 20, EVENEMENT, utilisateur)
		refs = faces_rendues(fichiers.lire(doc.plan_a_plat), plan)
		etat.progresser(GENRE, design, "génération du rendu 3D", 50, EVENEMENT, utilisateur)
		png = images.editer(prompts.prompt_mockup(doc.nom_produit or doc.article, famille=plan.get("famille"),
		                                          references=[code for code, _png in refs]), refs, taille="1024x1024",
		                    qualite=qualite_image(), fonctionnalite="Mockup 3D", doc=doc, fidelite="high")[0]
		fichier = save_file("%s-apercu-3d.png" % doc.name, png, "Design Emballage", doc.name, is_private=1)
		frappe.db.set_value("Design Emballage", design, {"apercu_3d": fichier.file_url,
		                    "empreinte_3d": doc.empreinte_plan}, update_modified=False)
		frappe.db.commit()
		etat.terminer(GENRE, design, "termine")
	except Exception as e:
		frappe.log_error(title="Aquaworld IA : aperçu 3D %s" % design, message=frappe.get_traceback())
		etat.terminer(GENRE, design, "echec", erreur=str(e)[:300])
		frappe.db.commit()
	etat.progresser(GENRE, design, "terminé", 100, EVENEMENT, utilisateur, fin=1)
