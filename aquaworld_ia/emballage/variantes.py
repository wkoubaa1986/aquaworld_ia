"""Étape 2 : une image gpt-image-1 par variante (face AVANT seulement), puis, sur demande, les
faces secondaires de la variante retenue. Workers : rien ici n'est appelé par une requête web.

Chaque image est enregistrée et committée dès qu'elle arrive : un job qui tombe à la 3e
variante laisse les deux premières (et leur coût) en place.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, flt
from frappe.utils.file_manager import save_file

from aquaworld_ia.emballage import geometrie, prompts
from aquaworld_ia.ia import couts, etat, fichiers, images
from aquaworld_ia.ia.client import qualite_image, reglages

GENRE = "emballage"
EVENEMENT = "aqia_emballage"
CHAMPS_FACES = {"arriere": "face_arriere", "cote_gauche": "face_gauche", "cote_droit": "face_droite",
                "dessus": "face_dessus", "dessous": "face_dessous"}


def plan_du_design(doc) -> dict:
	"""Le plan à plat du design. Les dimensions ne sont pas obligatoires à la création (le studio
	les saisit à l'étape 1) : toute action qui a besoin du plan passe ici et reçoit un message
	clair plutôt qu'une ValueError de la géométrie."""
	if not (flt(doc.longueur_mm) > 0 and flt(doc.hauteur_mm) > 0 and flt(doc.profondeur_mm) > 0):
		frappe.throw(_("Renseignez d'abord les trois dimensions de l'emballage (largeur, hauteur, profondeur)."))
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
			                                             palette=doc.palette, brief=doc.brief_style or "",
			                                             famille=plan.get("famille"))
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


def generer_fond(design: str, utilisateur: str | None = None) -> None:
	"""Un fond d'ambiance par IA (sans produit), posé en image de fond. En mode continu, le
	panorama couvre la bande entière et sera découpé face par face à la composition. Puis le plan
	se recompose de lui-même si une variante est choisie ou si l'on compose sans IA."""
	doc = frappe.get_doc("Design Emballage", design)
	try:
		plan = plan_du_design(doc)
		bande = geometrie.bande(plan) or geometrie.face(plan, "avant")
		continu = bool(cint(doc.get("fond_continu")))
		cible = bande if continu else geometrie.face(plan, "avant")
		taille = geometrie.taille_image_pour(cible)
		style = next(({"titre": v.titre, "description": v.description} for v in doc.variantes
		              if v.numero == cint(doc.variante_choisie)), None)
		prompt = prompts.prompt_fond(style, doc.nom_produit or doc.article, palette=doc.palette,
		                             brief=doc.brief_style or "", famille=plan.get("famille"), continu=continu)
		etat.progresser(GENRE, design, "génération du fond", 30, EVENEMENT, utilisateur)
		qualite = qualite_image()
		logo = url_logo(doc)
		if logo:
			png = images.editer(prompt, [("logo", fichiers.lire(logo))], taille=taille, qualite=qualite,
			                    fonctionnalite="Emballage fond", doc=doc, fidelite=None)[0]
		else:
			png = images.generer(prompt, taille=taille, qualite=qualite, fonctionnalite="Emballage fond", doc=doc)[0]
		fichier = save_file("%s-fond.png" % doc.name, png, "Design Emballage", doc.name, is_private=1)
		frappe.db.set_value("Design Emballage", design, {"image_fond": fichier.file_url, "apercu_3d": None},
		                    update_modified=False)
		frappe.db.commit()
		etat.progresser(GENRE, design, "recomposition du plan à plat", 90, EVENEMENT, utilisateur)
		try:
			from aquaworld_ia.emballage.composition import composer_et_attacher

			composer_et_attacher(design, cint(doc.variante_choisie))
		except Exception:
			frappe.log_error(title="Aquaworld IA : recomposition après fond %s" % design, message=frappe.get_traceback())
		etat.terminer(GENRE, design, "termine")
	except Exception as e:
		frappe.log_error(title="Aquaworld IA : fond %s" % design, message=frappe.get_traceback())
		etat.terminer(GENRE, design, "echec", erreur=str(e)[:300])
		frappe.db.commit()
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
			png = images.editer(prompts.prompt_face_secondaire(_style(v), doc.nom_produit or doc.article, code,
			                                                   palette=doc.palette, famille=plan.get("famille")),
			                    reference, taille=geometrie.taille_image_pour(face), qualite=qualite,
			                    fonctionnalite="Emballage faces", doc=doc)[0]
			fichier = save_file("%s-v%d-%s.png" % (doc.name, v.numero, code), png, "Design Emballage", doc.name, is_private=1)
			frappe.db.set_value("Design Emballage Variante", v.name, CHAMPS_FACES[code], fichier.file_url, update_modified=False)
		except Exception:
			frappe.log_error(title="Aquaworld IA : face %s de %s" % (code, design), message=frappe.get_traceback())
		frappe.db.commit()
	# L'aperçu 3D a été rendu depuis l'ancien plan : il ne montre pas ces faces.
	frappe.db.set_value("Design Emballage", design, {"faces_ia": 1, "apercu_3d": None}, update_modified=False)
	frappe.db.commit()
	# Le plan se recompose ici, sans clic : c'est gratuit (≈ 1 s) et c'est ce qu'on est venu
	# chercher — un plan où ces faces figurent. Sans cela, le PDF attaché restait celui d'avant
	# et le bouton 3 ne disait pas qu'il fallait le refaire.
	etat.progresser(GENRE, design, "recomposition du plan à plat", 95, EVENEMENT, utilisateur)
	try:
		from aquaworld_ia.emballage.composition import composer_et_attacher

		composer_et_attacher(design, v.numero)
	except Exception:
		frappe.log_error(title="Aquaworld IA : recomposition après faces %s" % design, message=frappe.get_traceback())
	etat.terminer(GENRE, design, "termine")
	etat.progresser(GENRE, design, "terminé", 100, EVENEMENT, utilisateur, fin=1)
