"""Le « Studio emballage » : la page Desk plein écran qui remplace le formulaire pour concevoir
un emballage (demande utilisateur 23/09/2026 : « je ne vois pas une meilleure UI »).

Ici ne vivent que la LECTURE groupée (tout ce que la page affiche, en un appel) et
l'ENREGISTREMENT des champs éditables. Les actions coûteuses (textes IA, variantes, plan, faces,
3D) restent dans textes.py / job.py / composition.py : le studio et la fiche partagent le même
moteur, aucune règle n'est dupliquée.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import flt

from aquaworld_ia.emballage import geometrie, job, textes

#: Les seuls champs que la page peut écrire. Tout le reste (statut, plan, variantes…) est le
#: résultat d'un traitement, jamais une saisie.
CHAMPS_EDITABLES = (
	"nom_produit", "marque", "logo", "photo_produit", "type_boite", "longueur_mm", "hauteur_mm",
	"profondeur_mm", "repli_mm", "fond_perdu_mm", "zone_securite_mm", "patte_collage_mm", "caracteristiques",
	"avertissements", "contact", "type_code_barres", "code_barres", "url_qr", "brief_style", "palette",
	"nb_variantes", "couleur_fond", "image_fond", "faces_identiques", "cotes_identiques", "pictos_sans_cartouche", "fond_continu", "mise_en_page",
)
CHAMPS_NUMERIQUES = ("longueur_mm", "hauteur_mm", "profondeur_mm", "repli_mm", "fond_perdu_mm", "zone_securite_mm",
                     "patte_collage_mm")


def _contenu_du_doc(doc) -> dict:
	"""Les drapeaux de contenu pour la maquette, lus dans la fiche elle-même."""
	t = frappe.parse_json(doc.textes_ia) if doc.textes_ia else {}
	premiere = t[next(iter(t))] if t else {}
	return {
		"logo": bool(doc.logo or doc.marque),
		"textes": bool(premiere.get("accroche")),
		"caracteristiques": bool(premiere.get("caracteristiques") or (doc.caracteristiques or "").strip()),
		"avertissements": bool(premiere.get("avertissements") or (doc.avertissements or "").strip()),
		"contact": bool(premiere.get("contact") or (doc.contact or "").strip()),
		"pictos": len(doc.pictogrammes or []),
		"code_barres": doc.type_code_barres != "Aucun" and bool(doc.code_barres or doc.url_qr),
		"faces_identiques": bool(doc.get("faces_identiques")),
		"cotes_identiques": bool(doc.get("cotes_identiques")),
		"mise_en_page": doc.get("mise_en_page") or None,
	}


def apercu_du_doc(doc) -> dict | None:
	if geometrie.dimensions_manquantes(doc.type_boite or geometrie.ETUI, flt(doc.longueur_mm), flt(doc.hauteur_mm),
	                                   flt(doc.profondeur_mm), flt(doc.get("repli_mm"))):
		return None
	return job.apercu(doc.type_boite, doc.longueur_mm, doc.hauteur_mm, doc.profondeur_mm, doc.patte_collage_mm,
	                  doc.fond_perdu_mm, doc.zone_securite_mm, contenu=_contenu_du_doc(doc), repli_mm=doc.get("repli_mm"))


@frappe.whitelist()
def charger(design: str) -> dict:
	"""Tout ce que la page affiche, en UN appel : la fiche, le plan, les textes, l'état du job,
	les catalogues (formes, langues, pictogrammes)."""
	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("read")
	langues = {l["code"]: l for l in textes._langues_du_design(doc)}
	t = frappe.parse_json(doc.textes_ia) if doc.textes_ia else {}
	return {
		"doc": doc.as_dict(),
		"peut_ecrire": doc.has_permission("write"),
		"apercu": apercu_du_doc(doc),
		"textes_html": textes.html_textes(t or {}, langues),
		"etat": job.etat_design(design),
		"types": job.types_emballage(),
		"langues": frappe.get_all("Aquaworld IA Langue", filters={"actif": 1}, fields=["code", "libelle", "rtl"],
		                          order_by="code"),
		"pictos": pictos_avec_vignette(),
		"estimation": job.estimation_variantes(1),
	}


def url_pictogramme(p) -> str | None:
	"""L'image à montrer pour un pictogramme : la sienne, sinon le SVG livré (servi en asset)."""
	if p.get("image"):
		return p["image"]
	if p.get("fichier"):
		return "/assets/aquaworld_ia/pictos/%s" % p["fichier"].split("/")[-1]
	return None


def pictos_avec_vignette() -> list:
	out = frappe.get_all("Aquaworld IA Pictogramme", filters={"actif": 1},
	                     fields=["code", "libelle", "categorie", "image", "fichier"], order_by="categorie, code")
	for p in out:
		p["url"] = url_pictogramme(p)
	return out


@frappe.whitelist()
def ajouter_pictogramme(libelle: str, image: str, categorie: str = "Certification", taille_mm=12) -> dict:
	"""Un pictogramme ou une certification ajouté DEPUIS le studio, image à l'appui (demande
	utilisateur 23/09/2026). Le code se déduit du libellé et reste unique."""
	frappe.only_for(("System Manager", "Item Manager", "Stock Manager", "Sales Manager"))
	libelle = (libelle or "").strip()
	if not libelle:
		frappe.throw(_("Donnez un nom au pictogramme."))
	if not image:
		frappe.throw(_("Téléversez l'image du pictogramme."))
	base = frappe.scrub(libelle)[:40] or "picto"
	code, n = base, 2
	while frappe.db.exists("Aquaworld IA Pictogramme", code):
		code = "%s_%d" % (base, n)
		n += 1
	doc = frappe.get_doc({"doctype": "Aquaworld IA Pictogramme", "code": code, "libelle": libelle,
	                      "categorie": categorie or "Certification", "image": image, "taille_mm": flt(taille_mm) or 12,
	                      "actif": 1}).insert()
	return {"code": doc.code, "libelle": doc.libelle, "url": image}


@frappe.whitelist()
def enregistrer(design: str, valeurs) -> dict:
	"""Écrit les champs éditables (et les listes langues / pictogrammes), puis renvoie la page."""
	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("write")
	v = frappe.parse_json(valeurs) if isinstance(valeurs, str) else (valeurs or {})
	for champ in CHAMPS_EDITABLES:
		if champ in v:
			val = v[champ]
			if champ in CHAMPS_NUMERIQUES:
				val = flt(val)
			if champ == "mise_en_page" and not isinstance(val, str):
				val = json.dumps(val, ensure_ascii=False) if val else None
			doc.set(champ, val)
	if "langues" in v:
		doc.set("langues", [{"langue": c} for c in (v["langues"] or []) if c])
	if "pictogrammes" in v:
		doc.set("pictogrammes", [{"pictogramme": c} for c in (v["pictogrammes"] or []) if c])
	if doc.type_boite and doc.type_boite not in geometrie.TYPES:
		frappe.throw(_("Forme inconnue : {0}").format(doc.type_boite))
	doc.save()
	return charger(design)


@frappe.whitelist()
def nouveau(article: str | None = None) -> dict:
	"""Une fiche neuve, pré-remplie depuis l'article (nom, photo, EAN, logo de la marque)."""
	doc = frappe.new_doc("Design Emballage")
	if article:
		item = frappe.get_doc("Item", article)
		doc.article = article
		doc.nom_produit = item.item_name
		doc.photo_produit = item.image
		ean = next((b.barcode for b in (item.barcodes or []) if "EAN" in (b.barcode_type or "").upper()
		            or (b.barcode or "").isdigit() and len(b.barcode) == 13), None)
		if ean:
			doc.code_barres = ean
		if item.brand:
			doc.marque = item.brand
			doc.logo = frappe.db.get_value("Brand", item.brand, "image")
	doc.insert()
	return {"name": doc.name}


@frappe.whitelist()
def zones_ajoutables() -> list:
	from aquaworld_ia.emballage.composition import ZONES_AJOUTABLES

	return [{"zone": z, "libelle": geometrie.ZONES_LIBELLES.get(z, z)} for z in ZONES_AJOUTABLES]


@frappe.whitelist()
def retoucher_logo(design: str, instruction: str) -> dict:
	"""L'atelier logo (demande utilisateur 23/09/2026) : redessiner le logo par IA d'après le
	logo actuel — changer ses couleurs, l'épurer — SANS le poser encore. Le résultat est un
	candidat attaché à la fiche ; l'utilisateur compare et adopte, ou réessaie.

	⚠️ L'IA redessine les LETTRES à sa façon : le candidat se relit lettre par lettre."""
	from aquaworld_ia.emballage.variantes import url_logo
	from aquaworld_ia.ia import fichiers, images
	from aquaworld_ia.ia.client import qualite_image
	from frappe.utils.file_manager import save_file

	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("write")
	source = url_logo(doc)
	if not source:
		frappe.throw(_("Attachez d'abord un logo."))
	instruction = (instruction or "").strip()
	if not instruction:
		frappe.throw(_("Dites ce que vous voulez changer : couleurs, épuration, style…"))
	prompt = (
		"Redraw the logo given as the reference image as a clean, flat, vector-style logo on a PURE WHITE background, "
		"centered, filling the frame, keeping its shapes, proportions and lettering EXACTLY as in the reference. "
		"Apply only this change: %s. No background scene, no shadows, no extra elements, no extra text." % instruction)
	png = images.editer(prompt, [("logo", fichiers.lire(source))], taille="1024x1024", qualite=qualite_image(),
	                    fonctionnalite="Logo IA", doc=doc, fidelite="high")[0]
	fichier = save_file("%s-logo-ia.png" % doc.name, png, "Design Emballage", doc.name, is_private=1)
	return {"candidat": fichier.file_url, "source": source}


@frappe.whitelist()
def adopter_logo(design: str, url: str) -> dict:
	"""Le candidat devient le logo : fond blanc rendu transparent, fichier propre attaché."""
	from aquaworld_ia.emballage.composition import fond_blanc_en_transparence
	from aquaworld_ia.ia import fichiers
	from frappe.utils.file_manager import save_file

	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("write")
	png = fond_blanc_en_transparence(fichiers.lire(url))
	fichier = save_file("%s-logo.png" % doc.name, png, "Design Emballage", doc.name, is_private=1)
	doc.logo = fichier.file_url
	doc.save()
	return charger(design)


@frappe.whitelist()
def liste(recherche: str | None = None, limite: int = 20) -> list:
	"""Les fiches récentes, pour le sélecteur du studio."""
	filtres = {}
	if recherche:
		filtres = [["Design Emballage", "nom_produit", "like", "%%%s%%" % recherche]]
	return frappe.get_list("Design Emballage", filters=filtres,
	                       fields=["name", "nom_produit", "article", "statut", "modified", "apercu_plan", "type_boite"],
	                       order_by="modified desc", limit_page_length=int(limite))
