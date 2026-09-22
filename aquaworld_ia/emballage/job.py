"""Les points d'entrée web du design d'emballage : lancer les jobs, lire leur état, choisir une
variante, prévisualiser le plan. Les workers sont dans variantes.py / mockup.py."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, flt

from aquaworld_ia.emballage import geometrie
from aquaworld_ia.emballage.variantes import GENRE
from aquaworld_ia.ia import couts, etat, journal
from aquaworld_ia.ia.client import qualite_image, reglages


def _doc(design: str, droit: str = "write"):
	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission(droit)
	return doc


def _verifier_libre(design: str) -> None:
	if etat.bloque(etat.lire_etat(GENRE, design)):
		frappe.throw(_("Un traitement est déjà en cours pour cette fiche."))


@frappe.whitelist()
def apercu(type_boite, longueur_mm, hauteur_mm, profondeur_mm, patte_collage_mm=None, fond_perdu_mm=None, zone_securite_mm=None) -> dict:
	"""Le plan (feuille, faces, SVG) pour la fiche — recalculé à chaque changement de dimension."""
	r = reglages()
	try:
		plan = geometrie.plan_a_plat(
			type_boite or geometrie.ETUI, flt(longueur_mm), flt(hauteur_mm), flt(profondeur_mm),
			patte=flt(patte_collage_mm) or flt(getattr(r, "patte_collage_mm", 15)) or 15,
			fond_perdu=flt(fond_perdu_mm) if fond_perdu_mm not in (None, "") else flt(getattr(r, "fond_perdu_mm", 3)),
			securite=flt(zone_securite_mm) if zone_securite_mm not in (None, "") else flt(getattr(r, "zone_securite_mm", 3)))
	except ValueError as e:
		return {"erreur": str(e)}
	return {"feuille": plan["feuille"], "svg": geometrie.apercu_svg(plan), "problemes": geometrie.verifier(plan),
	        "faces": [{"code": f["code"], "libelle": f["libelle"], "w": f["w"], "h": f["h"]} for f in plan["faces"] if f["imprimable"]]}


@frappe.whitelist()
def estimation_variantes(nombre) -> dict:
	q = qualite_image()
	return {"qualite": q, "cout": couts.cout_variantes(cint(nombre), q, couts.tarifs_depuis_reglages(reglages())),
	        "mois": journal.cout_du_mois(), "plafond": flt(getattr(reglages(), "plafond_mensuel_usd", 0))}


@frappe.whitelist()
def lancer_variantes(design: str, numeros=None) -> dict:
	doc = _doc(design)
	if not doc.textes_ia or not doc.variantes:
		frappe.throw(_("Préparez d'abord les textes et les styles (bouton 1)."))
	_verifier_libre(design)
	numeros = [cint(n) for n in (frappe.parse_json(numeros) if isinstance(numeros, str) else (numeros or []))]
	cibles = [v for v in doc.variantes if (not numeros or v.numero in numeros) and v.statut in ("À générer", "Échec")]
	if not cibles:
		frappe.throw(_("Aucune variante à générer."))
	q = qualite_image()
	journal.verifier_plafond(couts.cout_variantes(len(cibles), q, couts.tarifs_depuis_reglages(reglages())))
	frappe.db.set_value("Design Emballage", design, "statut", "Variantes en cours", update_modified=False)
	etat.demarrer(GENRE, design, tache="variantes", total=len(cibles))
	frappe.enqueue("aquaworld_ia.emballage.variantes.generer", queue="long", timeout=3600,
	               job_id="aqia-emballage-%s" % design, deduplicate=True,
	               design=design, numeros=[v.numero for v in cibles], utilisateur=frappe.session.user)
	return etat.lire_etat(GENRE, design)


@frappe.whitelist()
def regenerer_variante(design: str, numero) -> dict:
	doc = _doc(design)
	v = next((x for x in doc.variantes if x.numero == cint(numero)), None)
	if not v:
		frappe.throw(_("Variante introuvable."))
	frappe.db.set_value("Design Emballage Variante", v.name, {"statut": "À générer", "image": None}, update_modified=False)
	frappe.db.commit()
	return lancer_variantes(design, [cint(numero)])


@frappe.whitelist()
def choisir_variante(design: str, numero) -> dict:
	doc = _doc(design)
	v = next((x for x in doc.variantes if x.numero == cint(numero) and x.statut == "Prête"), None)
	if not v:
		frappe.throw(_("Cette variante n'est pas prête."))
	frappe.db.set_value("Design Emballage", design, "variante_choisie", cint(numero), update_modified=False)
	frappe.db.commit()
	return {"variante_choisie": cint(numero)}


@frappe.whitelist()
def lancer_faces(design: str) -> dict:
	doc = _doc(design)
	if not doc.variante_choisie:
		frappe.throw(_("Choisissez d'abord une variante."))
	_verifier_libre(design)
	journal.verifier_plafond(couts.cout_variantes(5, qualite_image(), couts.tarifs_depuis_reglages(reglages())))
	etat.demarrer(GENRE, design, tache="faces")
	frappe.enqueue("aquaworld_ia.emballage.variantes.generer_faces_secondaires", queue="long", timeout=3600,
	               job_id="aqia-emballage-%s" % design, deduplicate=True, design=design, utilisateur=frappe.session.user)
	return etat.lire_etat(GENRE, design)


@frappe.whitelist()
def lancer_mockup(design: str) -> dict:
	doc = _doc(design)
	if not doc.plan_a_plat:
		frappe.throw(_("Composez d'abord le plan à plat (bouton 3)."))
	_verifier_libre(design)
	journal.verifier_plafond(couts.cout_variantes(1, qualite_image(), couts.tarifs_depuis_reglages(reglages())))
	etat.demarrer(GENRE, design, tache="mockup")
	frappe.enqueue("aquaworld_ia.emballage.mockup.generer_apercu_3d", queue="long", timeout=900,
	               job_id="aqia-emballage-%s" % design, deduplicate=True, design=design, utilisateur=frappe.session.user)
	return etat.lire_etat(GENRE, design)


@frappe.whitelist()
def etat_design(design: str) -> dict:
	_doc(design, "read")
	e = etat.lire_etat(GENRE, design)
	e["bloque"] = etat.bloque(e)
	e["cout_document"] = journal.cout_document("Design Emballage", design)
	return e
