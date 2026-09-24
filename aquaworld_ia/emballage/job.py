"""Les points d'entrée web du design d'emballage : lancer les jobs, lire leur état, choisir une
variante, prévisualiser le plan. Les workers sont dans variantes.py / mockup.py."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, flt

from aquaworld_ia.emballage import geometrie
from aquaworld_ia.emballage.variantes import CHAMPS_FACES, GENRE
from aquaworld_ia.ia import couts, etat, journal
from aquaworld_ia.ia.client import qualite_image, reglages


def _doc(design: str, droit: str = "write"):
	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission(droit)
	return doc


def _verifier_libre(design: str) -> None:
	if etat.bloque(etat.lire_etat(GENRE, design)):
		frappe.throw(_("Un traitement est déjà en cours pour cette fiche."))


def _contenu(contenu) -> dict:
	"""Les drapeaux de contenu envoyés par la fiche -> le `contenu` de maquette_face."""
	c = frappe.parse_json(contenu) if isinstance(contenu, str) else (contenu or {})
	return {
		"logo": bool(c.get("logo")), "nom": True, "accroche": bool(c.get("textes")),
		"caracteristiques": bool(c.get("caracteristiques")), "avertissements": bool(c.get("avertissements")),
		"contact": bool(c.get("contact")), "pictos": cint(c.get("pictos")),
		"code_barres": geometrie.EAN_NOMINAL_MM if c.get("code_barres") else None,
	}


@frappe.whitelist()
def types_emballage() -> list:
	"""Les formes disponibles, chacune avec sa vignette — le sélecteur visuel de la fiche."""
	out = []
	for t in geometrie.TYPES:
		ex = geometrie.DIMENSIONS_EXEMPLE[t]
		plan = geometrie.plan_a_plat(t, *ex[:3], repli=ex[3] if len(ex) > 3 else 0)
		out.append({"type": t, "famille": plan["famille"], "description": geometrie.DESCRIPTIONS[t],
		            "dimensions": geometrie.DIMENSIONS_TYPE[t], "requises": geometrie.DIMENSIONS_REQUISES[t],
		            "svg": geometrie.apercu_svg(plan, 180, compact=True)})
	return out


@frappe.whitelist()
def apercu(type_boite, longueur_mm, hauteur_mm, profondeur_mm, patte_collage_mm=None, fond_perdu_mm=None,
           zone_securite_mm=None, contenu=None, repli_mm=None) -> dict:
	"""Le plan (feuille, faces, SVG) pour la fiche — recalculé à chaque changement de dimension.
	Avec `contenu`, chaque face imprimable rend aussi ses zones (logo, nom, EAN…) pour le survol."""
	r = reglages()
	try:
		plan = geometrie.plan_a_plat(
			type_boite or geometrie.ETUI, flt(longueur_mm), flt(hauteur_mm), flt(profondeur_mm),
			patte=flt(patte_collage_mm) or flt(getattr(r, "patte_collage_mm", 15)) or 15,
			fond_perdu=flt(fond_perdu_mm) if fond_perdu_mm not in (None, "") else flt(getattr(r, "fond_perdu_mm", 3)),
			securite=flt(zone_securite_mm) if zone_securite_mm not in (None, "") else flt(getattr(r, "zone_securite_mm", 3)),
			repli=flt(repli_mm))
	except ValueError as e:
		return {"erreur": str(e)}
	from aquaworld_ia.emballage.composition import zones_par_face

	c = _contenu(contenu)
	brut = frappe.parse_json(contenu) if isinstance(contenu, str) else (contenu or {})
	mep = brut.get("mise_en_page")
	mep = frappe.parse_json(mep) if isinstance(mep, str) else mep
	from aquaworld_ia.emballage.composition import faces_copiees

	zones = zones_par_face(plan, c, bool(brut.get("faces_identiques")), mep or None, bool(brut.get("cotes_identiques")))
	copies = faces_copiees(plan, bool(brut.get("faces_identiques")), bool(brut.get("cotes_identiques")), mep or None)
	return {"feuille": plan["feuille"], "famille": plan["famille"], "dimensions": geometrie.DIMENSIONS_TYPE.get(plan["type"]),
	        "reserves": plan.get("reserves") or [],
	        "svg": geometrie.apercu_svg(plan, zones=zones), "problemes": geometrie.verifier(plan),
	        "faces": [{"code": f["code"], "libelle": f["libelle"], "x": f["x"], "y": f["y"], "w": f["w"], "h": f["h"],
	                   "utile": f.get("utile"), "copie_de": copies.get(f["code"]),
	                   "personnalisee": bool(mep and f["code"] in mep),
	                   "zones": [dict(z, libelle=geometrie.ZONES_LIBELLES.get(z["zone"], z["zone"])) for z in zones[f["code"]]]}
	                  for f in plan["faces"] if f["imprimable"]]}


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
	# ⚠️ UNE VARIANTE RÉGÉNÉRÉE REPART DE ZÉRO. Ses faces secondaires ont été dessinées dans le
	# style de l'ANCIEN visuel ; et si c'est la variante retenue, le plan à plat, son aperçu et
	# le rendu 3D montrent une image qui n'existe plus. Les laisser, c'est livrer à l'imprimeur
	# un PDF périmé sans que rien ne le dise (constaté le 23/09/2026).
	faces = {champ: None for champ in CHAMPS_FACES.values()}
	frappe.db.set_value("Design Emballage Variante", v.name, dict(faces, statut="À générer", image=None),
	                    update_modified=False)
	if cint(doc.variante_choisie) == cint(numero):
		frappe.db.set_value("Design Emballage", design, {"plan_a_plat": None, "apercu_plan": None,
		                                                 "apercu_3d": None, "faces_ia": 0}, update_modified=False)
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
def lancer_fond(design: str, continu=None) -> dict:
	"""Un fond d'ambiance par IA (1 image). `continu` : le panorama qui fait le tour."""
	doc = _doc(design)
	manque = geometrie.dimensions_manquantes(doc.type_boite or geometrie.ETUI, flt(doc.longueur_mm), flt(doc.hauteur_mm),
	                                         flt(doc.profondeur_mm), flt(doc.get("repli_mm")))
	if manque:
		frappe.throw(_("Renseignez d'abord les dimensions : {0}.").format(", ".join(manque)))
	_verifier_libre(design)
	if continu is not None:
		frappe.db.set_value("Design Emballage", design, "fond_continu", cint(continu), update_modified=False)
		frappe.db.commit()
	journal.verifier_plafond(couts.cout_variantes(1, qualite_image(), couts.tarifs_depuis_reglages(reglages())))
	etat.demarrer(GENRE, design, tache="fond")
	frappe.enqueue("aquaworld_ia.emballage.variantes.generer_fond", queue="long", timeout=900,
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
