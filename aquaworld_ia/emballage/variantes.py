"""Étape 2 : une image gpt-image-1 par variante (face AVANT seulement), puis, sur demande, les
faces secondaires de la variante retenue. Workers : rien ici n'est appelé par une requête web.

Chaque image est enregistrée et committée dès qu'elle arrive : un job qui tombe à la 3e
variante laisse les deux premières (et leur coût) en place.
"""

from __future__ import annotations

import frappe
from frappe.utils import cint
from frappe.utils.file_manager import save_file

from aquaworld_ia.emballage import geometrie, prompts
from aquaworld_ia.ia import couts, etat, fichiers, images
from aquaworld_ia.ia.client import qualite_image, reglages

GENRE = "emballage"
EVENEMENT = "aqia_emballage"
CHAMPS_FACES = {"arriere": "face_arriere", "cote_gauche": "face_gauche", "cote_droit": "face_droite",
                "dessus": "face_dessus", "dessous": "face_dessous"}


def plan_du_design(doc) -> dict:
	r = reglages()
	return geometrie.plan_a_plat(
		doc.type_boite or geometrie.ETUI, doc.longueur_mm, doc.hauteur_mm, doc.profondeur_mm,
		patte=float(doc.patte_collage_mm or getattr(r, "patte_collage_mm", 15) or 15),
		fond_perdu=float(doc.fond_perdu_mm if doc.fond_perdu_mm is not None else getattr(r, "fond_perdu_mm", 3) or 3),
		securite=float(doc.zone_securite_mm if doc.zone_securite_mm is not None else getattr(r, "zone_securite_mm", 3) or 3))


def url_photo(doc) -> str | None:
	return doc.photo_produit or frappe.db.get_value("Item", doc.article, "image")


def url_logo(doc) -> str | None:
	if doc.logo:
		return doc.logo
	if doc.marque:
		return frappe.db.get_value("Brand", doc.marque, "image")
	return None


def _references(doc) -> list[tuple[str, bytes]]:
	refs = []
	photo, logo = url_photo(doc), url_logo(doc)
	if photo:
		refs.append(("photo_produit", fichiers.lire(photo)))
	if logo:
		refs.append(("logo", fichiers.lire(logo)))
	if not refs:
		frappe.throw("Aucune image de référence : renseignez la photo produit (ou l'image de l'article) et le logo.")
	return refs


def _style(v) -> dict:
	return {"titre": v.titre, "description": v.description}


def generer(design: str, numeros=None, utilisateur: str | None = None) -> None:
	doc = frappe.get_doc("Design Emballage", design)
	numeros = {cint(n) for n in (numeros or [])} or None
	try:
		plan = plan_du_design(doc)
		avant = geometrie.face(plan, "avant")
		refs = _references(doc)
	except Exception as e:
		frappe.db.set_value("Design Emballage", design, "statut", "Échec", update_modified=False)
		etat.terminer(GENRE, design, "echec", erreur=str(e)[:300])
		frappe.db.commit()
		raise
	lignes = [v for v in doc.variantes if (numeros is None or v.numero in numeros) and v.statut in ("À générer", "Échec")]
	qualite = qualite_image()
	tarifs = couts.tarifs_depuis_reglages(reglages())
	for k, v in enumerate(lignes):
		frappe.db.set_value("Design Emballage Variante", v.name, {"statut": "En cours", "erreur": None}, update_modified=False)
		frappe.db.commit()
		etat.progresser(GENRE, design, "variante %d / %d" % (k + 1, len(lignes)), int(100 * k / max(1, len(lignes))),
		                EVENEMENT, utilisateur, numero=v.numero)
		try:
			prompt = v.prompt or prompts.prompt_variante(_style(v), doc.nom_produit or doc.article, doc.marque or "",
			                                             palette=doc.palette, brief=doc.brief_style or "")
			png = images.editer(prompt, refs, taille=geometrie.taille_image_pour(avant), qualite=qualite,
			                    fonctionnalite="Emballage image", doc=doc)[0]
			fichier = save_file("%s-v%d.png" % (doc.name, v.numero), png, "Design Emballage", doc.name, is_private=1)
			frappe.db.set_value("Design Emballage Variante", v.name, {
				"image": fichier.file_url, "statut": "Prête", "prompt": prompt,
				"cout_estime": couts.estimer_cout(images=1, qualite=qualite, tarifs=tarifs),
			}, update_modified=False)
		except Exception as e:
			frappe.log_error(title="Aquaworld IA : variante %s #%s" % (design, v.numero), message=frappe.get_traceback())
			frappe.db.set_value("Design Emballage Variante", v.name, {"statut": "Échec", "erreur": str(e)[:500]},
			                    update_modified=False)
		frappe.db.commit()
	pretes = frappe.db.count("Design Emballage Variante", {"parent": design, "statut": "Prête"})
	frappe.db.set_value("Design Emballage", design, "statut", "Variantes prêtes" if pretes else "Échec", update_modified=False)
	frappe.db.commit()
	etat.terminer(GENRE, design, "termine" if pretes else "echec", pretes=pretes)
	etat.progresser(GENRE, design, "terminé", 100, EVENEMENT, utilisateur, fin=1)


def generer_faces_secondaires(design: str, utilisateur: str | None = None) -> None:
	doc = frappe.get_doc("Design Emballage", design)
	v = next((x for x in doc.variantes if x.numero == cint(doc.variante_choisie) and x.image), None)
	if not v:
		etat.terminer(GENRE, design, "echec", erreur="Aucune variante choisie avec image.")
		frappe.db.commit()
		return
	plan = plan_du_design(doc)
	reference = [("face_avant", fichiers.lire(v.image))]
	qualite = qualite_image()
	codes = list(CHAMPS_FACES)
	for k, code in enumerate(codes):
		face = geometrie.face(plan, code)
		if not face:
			continue
		etat.progresser(GENRE, design, "face %s (%d / %d)" % (face["libelle"], k + 1, len(codes)),
		                int(100 * k / len(codes)), EVENEMENT, utilisateur)
		try:
			png = images.editer(prompts.prompt_face_secondaire(_style(v), doc.nom_produit or doc.article, code, palette=doc.palette),
			                    reference, taille=geometrie.taille_image_pour(face), qualite=qualite,
			                    fonctionnalite="Emballage faces", doc=doc)[0]
			fichier = save_file("%s-v%d-%s.png" % (doc.name, v.numero, code), png, "Design Emballage", doc.name, is_private=1)
			frappe.db.set_value("Design Emballage Variante", v.name, CHAMPS_FACES[code], fichier.file_url, update_modified=False)
		except Exception:
			frappe.log_error(title="Aquaworld IA : face %s de %s" % (code, design), message=frappe.get_traceback())
		frappe.db.commit()
	frappe.db.set_value("Design Emballage", design, "faces_ia", 1, update_modified=False)
	frappe.db.commit()
	etat.terminer(GENRE, design, "termine")
	etat.progresser(GENRE, design, "terminé", 100, EVENEMENT, utilisateur, fin=1)
