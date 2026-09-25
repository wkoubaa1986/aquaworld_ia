"""Le « Studio emballage » : la page Desk plein écran qui remplace le formulaire pour concevoir
un emballage (demande utilisateur 23/09/2026 : « je ne vois pas une meilleure UI »).

Ici ne vivent que la LECTURE groupée (tout ce que la page affiche, en un appel) et
l'ENREGISTREMENT des champs éditables. Les actions coûteuses (textes IA, variantes, plan, faces,
3D) restent dans textes.py / job.py / composition.py : le studio et la fiche partagent le même
moteur, aucune règle n'est dupliquée.
"""

from __future__ import annotations

import io
import json
import re

import frappe
from frappe import _
from frappe.utils import cint, flt

from aquaworld_ia.emballage import geometrie, job, mise_en_forme, textes
from aquaworld_ia.manuels import rendu

#: Les seuls champs que la page peut écrire. Tout le reste (statut, plan, variantes…) est le
#: résultat d'un traitement, jamais une saisie.
CHAMPS_EDITABLES = (
	"nom_produit", "marque", "logo", "photo_produit", "type_boite", "longueur_mm", "hauteur_mm",
	"profondeur_mm", "repli_mm", "fond_perdu_mm", "zone_securite_mm", "patte_collage_mm", "caracteristiques",
	"avertissements", "contact", "type_code_barres", "code_barres", "url_qr", "brief_style", "palette",
	"nb_variantes", "couleur_fond", "image_fond", "faces_identiques", "cotes_identiques", "pictos_sans_cartouche", "fond_continu", "mise_en_page",
	"police_caracteristiques", "taille_caracteristiques",
)
CHAMPS_NUMERIQUES = ("longueur_mm", "hauteur_mm", "profondeur_mm", "repli_mm", "fond_perdu_mm", "zone_securite_mm",
                     "patte_collage_mm", "taille_caracteristiques")


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
		"images": images_du_design(doc),
		"polices": polices_du_studio(),
		"desalignes": mise_en_forme.desalignes(doc.caracteristiques, t or {}),
	}


@frappe.whitelist()
def utiliser_lignes_brutes(design: str, langue: str) -> dict:
	"""Les caractéristiques de l'étape 2, mise en forme comprise, deviennent celles qui s'impriment
	pour `langue`, telles quelles — quand elles sont déjà écrites dans cette langue (demande
	utilisateur 24/09/2026 : la zone Caractéristiques imprimait la reformulation de l'IA, 8 lignes
	sans mise en forme, au lieu de ses 11 lignes mises en forme)."""
	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("write")
	t = frappe.parse_json(doc.textes_ia) if doc.textes_ia else {}
	if langue not in (t or {}):
		frappe.throw(_("Pas de textes préparés en {0}.").format(langue))
	t[langue]["caracteristiques"] = mise_en_forme.lignes_imprimables(doc.caracteristiques)
	doc.textes_ia = json.dumps(t, ensure_ascii=False)
	doc.save()
	return charger(design)


def polices_du_studio() -> list[dict]:
	"""Les polices proposées dans le studio, avec l'URL de chaque style pour l'aperçu dans le
	navigateur : les livrées (sauf l'arabe, jamais choisie pour une ligne), puis les ajoutées."""
	out = []
	for famille, fichiers_ in rendu.POLICES_LIVREES.items():
		if famille == "Noto Naskh Arabic":
			continue
		out.append({"famille": famille, "source": "livree",
		            "styles": {cle: "/assets/aquaworld_ia/fonts/%s" % f for (cle, _p, _s), f in zip(rendu.STYLES_POLICE, fichiers_) if f}})
	for famille, styles in rendu.polices_utilisateur():
		out.append({"famille": famille, "source": "ajoutee", "styles": styles})
	return out


@frappe.whitelist()
def ajouter_police(nom: str, regulier: str, gras: str | None = None, italique: str | None = None,
                   gras_italique: str | None = None) -> list:
	"""Une police ajoutée DEPUIS le studio (demande utilisateur 24/09/2026 : « choisir la police ») :
	un fichier par style ; les fichiers téléversés dans le dialogue sont rattachés à la fiche."""
	frappe.only_for(("System Manager", "Aquaworld IA", "Item Manager", "Stock Manager", "Sales Manager"))
	valeurs = {"regulier": regulier, "gras": gras, "italique": italique, "gras_italique": gras_italique}
	doc = frappe.get_doc(dict({"doctype": "Police Emballage", "nom": (nom or "").strip()},
	                          **{k: v for k, v in valeurs.items() if v})).insert()
	for champ, url in valeurs.items():
		if url:
			for f in frappe.get_all("File", filters={"file_url": url, "attached_to_name": ("is", "not set")}, pluck="name"):
				frappe.db.set_value("File", f, {"attached_to_doctype": "Police Emballage", "attached_to_name": doc.name,
				                                "attached_to_field": champ})
	return polices_du_studio()


GENRES_IMAGE = (
	("-logo-ia", "Logo IA"), ("-logo", "Logo"), ("-photo-ia", "Photo IA"), ("-photo", "Photo"), ("-fond", "Fond IA"),
	("-apercu-3d", "Aperçu 3D"),
)


def genre_image(nom_fichier: str, design: str) -> str | None:
	"""Le genre d'un fichier image du design d'après son nom (les fichiers de l'app portent un
	suffixe stable) ; None = fichier technique à ne pas montrer (aperçu du plan). Pur."""
	base = (nom_fichier or "").rsplit(".", 1)[0]
	# Le préfixe d'un AUTRE design compte aussi : une copie (`dupliquer`) partage le fichier physique
	# de l'original, et Frappe lui en redonne le nom (« EMB-2026-0002-fond… » attaché à EMB-2026-0003).
	autre = re.match(r"^EMB-\d{4}-\d+(?=-)", base)
	prefixe = design if base.startswith(design) else (autre.group(0) if autre else None)
	if prefixe:
		reste = base[len(prefixe):]
		if reste.startswith("-apercu") and not reste.startswith("-apercu-3d"):
			return None
		for suffixe, genre in GENRES_IMAGE:
			if reste.startswith(suffixe):
				return genre
		if re.match(r"^-v\d+-", reste):
			return "Face IA"
		if re.match(r"^-v\d+", reste):
			return "Variante"
	return "Téléversé"


def images_du_design(doc) -> list:
	"""Toutes les images attachées à la fiche (demande utilisateur 24/09/2026 : « les logos et les
	logos traités, je les trouve où ? ») : une entrée par fichier, la plus récente d'abord."""
	lignes = frappe.get_all("File", filters={"attached_to_doctype": "Design Emballage", "attached_to_name": doc.name,
	                                          "is_folder": 0}, fields=["file_name", "file_url", "creation"], order_by="creation desc")
	vus, out = set(), []
	en_usage = {doc.get("logo"): "logo", doc.get("photo_produit"): "photo_produit", doc.get("image_fond"): "image_fond"}
	for f in lignes:
		ext = (f.file_url or "").rsplit(".", 1)[-1].lower()
		if ext not in ("png", "jpg", "jpeg", "svg", "webp", "gif") or f.file_url in vus:
			continue
		genre = genre_image(f.file_name, doc.name)
		if not genre:
			continue
		vus.add(f.file_url)
		out.append({"file_url": f.file_url, "file_name": f.file_name, "creation": f.creation, "genre": genre,
		            "usage": en_usage.get(f.file_url)})
	return out


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
	frappe.only_for(("System Manager", "Aquaworld IA", "Item Manager", "Stock Manager", "Sales Manager"))
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


def _depuis_article(doc, article: str, logo_de_marque: bool = True) -> None:
	"""Le nom, la photo, l'EAN et la marque d'un article, posés sur la fiche ; le logo de la marque
	seulement si `logo_de_marque` (une copie garde son logo, souvent retouché, tant que la marque
	ne change pas). Une photo ou un EAN absents de l'article ne vident pas la fiche."""
	item = frappe.get_doc("Item", article)
	doc.article = article
	doc.nom_produit = item.item_name
	if item.image:
		doc.photo_produit = item.image
	ean = next((b.barcode for b in (item.barcodes or []) if "EAN" in (b.barcode_type or "").upper()
	            or (b.barcode or "").isdigit() and len(b.barcode) == 13), None)
	if ean:
		doc.code_barres = ean
	if item.brand:
		doc.marque = item.brand
		if logo_de_marque:
			doc.logo = frappe.db.get_value("Brand", item.brand, "image")


@frappe.whitelist()
def nouveau(article: str | None = None) -> dict:
	"""Une fiche neuve, pré-remplie depuis l'article (nom, photo, EAN, logo de la marque)."""
	doc = frappe.new_doc("Design Emballage")
	if article:
		_depuis_article(doc, article)
	doc.insert()
	return {"name": doc.name}


#: Ce qu'une copie ne reprend pas : les RÉSULTATS de la fiche d'origine (PDF, aperçus, journal des
#: coûts) — ils décrivent l'original et se refont en recomposant.
CHAMPS_NON_DUPLIQUES = ("statut", "plan_a_plat", "apercu_plan", "apercu_3d", "journal")
CHAMPS_FICHIERS = ("logo", "photo_produit", "image_fond")


def nom_copie(nom_fichier: str | None, source: str, cible: str) -> str:
	"""Le nom (sans extension) d'un fichier recopié : le préfixe du design d'origine devient celui de
	la copie, pour que l'onglet Images de la copie reconnaisse logo, fond, variantes… Pur."""
	base = (nom_fichier or "fichier").rsplit(".", 1)[0]
	return cible + base[len(source):] if base.startswith(source) else base


def statut_copie(textes_ia, variantes: list) -> str:
	"""Le statut d'une copie, d'après ce qu'elle reprend (jamais « Plan prêt » : le plan est à
	recomposer). Pur."""
	if any(v.get("statut") == "Prête" for v in variantes):
		return "Variantes prêtes"
	return "Textes prêts" if textes_ia else "Brouillon"


@frappe.whitelist()
def dupliquer(design: str, article: str | None = None) -> dict:
	"""Une copie du design (demande utilisateur 24/09/2026 : « comment dupliquer un design ? ») :
	forme, dimensions, textes et leur mise en forme, langues, pictogrammes, fond, mise en page
	dessinée, variantes IA déjà payées — sans le plan ni les aperçus, à recomposer. Les fichiers
	attachés à l'original sont rattachés AUSSI à la copie (même fichier sur disque, fiche File à
	part) : supprimer l'original ne casse pas la copie. Avec un autre `article`, son nom, sa photo
	et son EAN remplacent ceux de l'original."""
	from frappe.model import no_value_fields, table_fields

	from aquaworld_ia.emballage.variantes import CHAMPS_FACES

	source = frappe.get_doc("Design Emballage", design)
	source.check_permission("read")
	frappe.has_permission("Design Emballage", "create", throw=True)
	copie = frappe.new_doc("Design Emballage")
	for df in source.meta.fields:
		if df.fieldname in CHAMPS_NON_DUPLIQUES:
			continue
		# ⚠️ Les tables sont AUSSI dans `no_value_fields` : les tester d'abord, sinon langues,
		# pictogrammes et variantes ne suivent pas.
		if df.fieldtype in table_fields:
			for ligne in source.get(df.fieldname) or []:
				copie.append(df.fieldname, ligne.as_dict(no_default_fields=True))
		elif df.fieldtype not in no_value_fields:
			copie.set(df.fieldname, source.get(df.fieldname))
	for v in copie.variantes:
		if v.statut == "En cours":
			v.statut = "À générer"            # le job de l'original ne travaille pas pour la copie
	copie.statut = statut_copie(copie.textes_ia, [v.as_dict() for v in copie.variantes])
	if article and article != source.article:
		marque = frappe.db.get_value("Item", article, "brand")
		_depuis_article(copie, article, logo_de_marque=bool(marque) and marque != source.marque)
	# Les fichiers sont posés APRÈS l'insertion : il faut le nom de la copie pour les y rattacher
	# (sinon le hook de Frappe les rattache lui-même, sous le nom de fichier de l'original).
	fichiers_haut = {champ: copie.get(champ) for champ in CHAMPS_FICHIERS}
	for champ in CHAMPS_FICHIERS:
		copie.set(champ, None)
	copie.insert()

	deja = {}

	def rattacher(url, champ=None):
		if not url or not url.startswith(("/files/", "/private/files/")):
			return url
		if url not in deja:
			f = frappe.db.get_value("File", {"file_url": url, "attached_to_doctype": "Design Emballage",
			                                 "attached_to_name": source.name}, "file_name")
			deja[url] = _copier_fichier(url, nom_copie(f, source.name, copie.name), "Design Emballage", copie.name,
			                            champ=champ) if f else url
		return deja[url]

	for champ, url in fichiers_haut.items():
		copie.set(champ, rattacher(url, champ))
	for v in copie.variantes:
		for champ in ("image",) + tuple(CHAMPS_FACES.values()):
			v.set(champ, rattacher(v.get(champ)))
	mep = frappe.parse_json(copie.mise_en_page) if copie.mise_en_page else None
	if isinstance(mep, dict):
		for zones in mep.values():
			for z in zones if isinstance(zones, list) else []:
				if isinstance(z, dict) and z.get("logo"):
					z["logo"] = rattacher(z["logo"])
		copie.mise_en_page = json.dumps(mep, ensure_ascii=False)
	copie.save()
	return {"name": copie.name}


@frappe.whitelist()
def zones_ajoutables() -> list:
	from aquaworld_ia.emballage.composition import ZONES_AJOUTABLES

	return [{"zone": z, "libelle": geometrie.ZONES_LIBELLES.get(z, z)} for z in ZONES_AJOUTABLES]


@frappe.whitelist()
def retoucher_logo(design: str, instruction: str, nombre=1) -> dict:
	"""L'atelier logo (demande utilisateur 23/09/2026) : redessiner le logo par IA d'après le
	logo actuel — changer ses couleurs, l'épurer — SANS le poser encore. Le résultat est un
	candidat attaché à la fiche ; l'utilisateur compare et adopte, ou réessaie. `nombre` (1 à 4,
	demande du 24/09/2026 : « en voir plusieurs avant de choisir ») candidats pour la même consigne.

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
	n = max(1, min(4, cint(nombre) or 1))
	pngs = images.editer(prompt, [("logo", fichiers.lire(source))], taille="1024x1024", qualite=qualite_image(),
	                     n=n, fonctionnalite="Logo IA", doc=doc, fidelite="high")
	candidats = [save_file("%s-logo-ia.png" % doc.name, png, "Design Emballage", doc.name, is_private=1).file_url for png in pngs]
	return {"candidats": candidats, "candidat": candidats[0] if candidats else None, "source": source}


PROMPTS_RETOUCHE = {
	"logo": (
		"Redraw the logo given as the reference image as a clean, flat, vector-style logo on a PURE WHITE background, "
		"centered, filling the frame, keeping its shapes, proportions and lettering EXACTLY as in the reference. "
		"Apply only this change: %s. No background scene, no shadows, no extra elements, no extra text."),
	"photo_produit": (
		"Professional packshot of the product shown in the reference image, for a retail packaging: the product itself "
		"must stay EXACTLY as in the reference (shape, proportions, colors, materials, fittings, labels, text on it), "
		"no redesign, no added parts. Clean cut-out on a PURE WHITE background, soft even studio lighting, sharp focus, "
		"straight front view, product centered and filling the frame, no props, no hands, no text, no logo, no shadow scene. "
		"Apply only this change: %s."),
}


def prompt_retouche(champ: str, instruction: str) -> str:
	"""Le prompt de l'atelier IA d'une image du design (logo, photo produit). Pur."""
	if champ not in PROMPTS_RETOUCHE:
		raise ValueError("Pas d'atelier IA pour %r" % champ)
	return PROMPTS_RETOUCHE[champ] % (instruction or "").strip().rstrip(".")


def taille_retouche(champ: str, octets: bytes | None) -> str:
	"""Le format d'image de l'atelier : carré pour un logo ; pour une photo, portrait ou paysage
	si le produit l'est nettement (un porte-filtre est haut et étroit). Pur."""
	if champ != "photo_produit" or not octets:
		return "1024x1024"
	try:
		from PIL import Image

		im = Image.open(io.BytesIO(octets))
		ratio = im.width / max(1, im.height)
	except Exception:
		return "1024x1024"
	if ratio < 0.8:
		return "1024x1536"
	if ratio > 1.25:
		return "1536x1024"
	return "1024x1024"


@frappe.whitelist()
def retoucher_image(design: str, champ: str, instruction: str, nombre=1) -> dict:
	"""L'atelier IA d'une image du design — logo, ou photo produit (demande utilisateur 24/09/2026 :
	« améliorer avec l'IA la photo du produit ») : détourage sur blanc pur, éclairage studio, retrait
	des accessoires… `nombre` propositions (1 à 4) attachées à la fiche, rien n'est posé tant que
	l'utilisateur n'adopte pas. ⚠️ L'IA REDESSINE : la photo se contrôle détail par détail."""
	from aquaworld_ia.emballage.variantes import url_logo, url_photo
	from aquaworld_ia.ia import fichiers, images
	from aquaworld_ia.ia.client import qualite_image
	from frappe.utils.file_manager import save_file

	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("write")
	source = url_logo(doc) if champ == "logo" else url_photo(doc) if champ == "photo_produit" else None
	if champ not in PROMPTS_RETOUCHE:
		frappe.throw(_("Pas d'atelier IA pour ce champ."))
	if not source:
		frappe.throw(_("Attachez d'abord un logo.") if champ == "logo" else _("Attachez d'abord une photo du produit."))
	instruction = (instruction or "").strip()
	if not instruction:
		frappe.throw(_("Dites ce que vous voulez changer."))
	octets = fichiers.lire(source)
	n = max(1, min(4, cint(nombre) or 1))
	pngs = images.editer(prompt_retouche(champ, instruction), [(champ, octets)], taille=taille_retouche(champ, octets),
	                     qualite=qualite_image(), n=n, fonctionnalite="Logo IA" if champ == "logo" else "Emballage image",
	                     doc=doc, fidelite="high")
	suffixe = "logo-ia" if champ == "logo" else "photo-ia"
	candidats = [save_file("%s-%s.png" % (doc.name, suffixe), png, "Design Emballage", doc.name, is_private=1).file_url for png in pngs]
	return {"candidats": candidats, "candidat": candidats[0] if candidats else None, "source": source}


@frappe.whitelist()
def adopter_image(design: str, champ: str, url: str) -> dict:
	"""Le candidat devient le logo ou la photo produit : fond blanc rendu transparent, fichier propre."""
	from aquaworld_ia.emballage.composition import fond_blanc_en_transparence
	from aquaworld_ia.ia import fichiers
	from frappe.utils.file_manager import save_file

	if champ not in PROMPTS_RETOUCHE:
		frappe.throw(_("Pas d'atelier IA pour ce champ."))
	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("write")
	png = fond_blanc_en_transparence(fichiers.lire(url))
	fichier = save_file("%s-%s.png" % (doc.name, "logo" if champ == "logo" else "photo"), png, "Design Emballage", doc.name, is_private=1)
	doc.set(champ, fichier.file_url)
	doc.save()
	return charger(design)


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


#: Champs du design que la bibliothèque sait remplir, et les catégories qui leur correspondent.
CHAMPS_BIBLIOTHEQUE = {"image_fond": ("Fond", "Motif"), "logo": ("Logo",), "photo_produit": ("Photo produit",)}


def categorie_par_defaut(champ: str) -> str:
	"""La catégorie proposée quand on enregistre le fichier d'un champ : un fond IA est un Fond,
	un logo est un Logo. Pur."""
	if champ not in CHAMPS_BIBLIOTHEQUE:
		raise ValueError("Champ hors bibliothèque : %r" % champ)
	return CHAMPS_BIBLIOTHEQUE[champ][0]


def _copier_fichier(url: str, nom_fichier: str, doctype: str, name: str, champ: str | None = None) -> str:
	"""Un fichier `File` à part, attaché à (doctype, name) -> file_url. Frappe dédoublonne par
	empreinte : le fichier physique est partagé tant qu'une fiche y renvoie, et n'est effacé du
	disque que lorsque plus aucune fiche ne le référence (`File._delete_file_on_disk`). Supprimer
	le design d'origine ne casse donc pas la ressource, ni l'inverse."""
	from frappe.utils.file_manager import save_file

	from aquaworld_ia.ia import fichiers

	octets = fichiers.lire(url)
	extension = (url.rsplit(".", 1)[-1].lower() if "." in url.rsplit("/", 1)[-1] else "png")[:5]
	return save_file("%s.%s" % (nom_fichier, extension), octets, doctype, name, is_private=1, df=champ).file_url


@frappe.whitelist()
def bibliotheque_enregistrer(design: str, champ: str, nom: str, categorie: str | None = None, notes: str | None = None,
                             url: str | None = None) -> dict:
	"""Garde un fichier du design dans la bibliothèque, sous un nom, avec la marque du design :
	celui du champ (image de fond, logo), ou l'`url` donnée (onglet Images : une proposition de
	logo IA, un ancien fond…)."""
	if champ not in CHAMPS_BIBLIOTHEQUE:
		frappe.throw(_("Ce champ ne va pas dans la bibliothèque."))
	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("read")
	url = url or doc.get(champ)
	if not url:
		frappe.throw(_("Aucun fichier à enregistrer : générez ou choisissez d'abord un fichier."))
	if not (nom or "").strip():
		frappe.throw(_("Donnez un nom à cette ressource."))
	categorie = categorie or categorie_par_defaut(champ)
	if categorie not in CHAMPS_BIBLIOTHEQUE[champ]:
		frappe.throw(_("Catégorie {0} impossible pour ce champ.").format(categorie))
	# L'image est obligatoire : on insère avec l'original, puis on le remplace par la copie
	# attachée à la ressource (la copie a besoin du nom de la ressource pour s'y attacher).
	res = frappe.get_doc({"doctype": "Ressource Emballage", "nom": nom.strip(), "categorie": categorie, "image": url,
	                      "marque": doc.marque or None, "notes": notes, "design_origine": doc.name}).insert()
	res.image = _copier_fichier(url, frappe.scrub(nom.strip())[:60] or "ressource", "Ressource Emballage", res.name)
	res.save()
	frappe.db.commit()
	return {"name": res.name, "nom": res.nom, "categorie": res.categorie, "image": res.image}


@frappe.whitelist()
def bibliotheque_liste(champ: str | None = None, marque: str | None = None, recherche: str | None = None, limite: int = 60) -> list:
	"""Les ressources d'un champ (fonds et motifs, logos, photos du produit), celles de la marque d'abord."""
	filtres = {}
	if champ:
		if champ not in CHAMPS_BIBLIOTHEQUE:
			frappe.throw(_("Ce champ ne va pas dans la bibliothèque."))
		filtres["categorie"] = ("in", list(CHAMPS_BIBLIOTHEQUE[champ]))
	if recherche:
		filtres["nom"] = ("like", "%%%s%%" % recherche.strip())
	lignes = frappe.get_all("Ressource Emballage", filters=filtres, fields=["name", "nom", "categorie", "marque", "image", "notes", "modified"],
	                        order_by="modified desc", limit=int(limite or 60))
	if marque:
		lignes.sort(key=lambda l: 0 if l.get("marque") == marque else 1)
	return lignes


@frappe.whitelist()
def bibliotheque_choisir(design: str, ressource: str, champ: str) -> dict:
	"""Pose une ressource de la bibliothèque dans un champ du design (copie du fichier)."""
	if champ not in CHAMPS_BIBLIOTHEQUE:
		frappe.throw(_("Ce champ ne va pas dans la bibliothèque."))
	res = frappe.get_doc("Ressource Emballage", ressource)
	if res.categorie not in CHAMPS_BIBLIOTHEQUE[champ]:
		frappe.throw(_("Une ressource « {0} » ne va pas dans ce champ.").format(res.categorie))
	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("write")
	url = _copier_fichier(res.image, "%s-%s" % (doc.name, frappe.scrub(res.nom)[:40] or champ), "Design Emballage", doc.name)
	return enregistrer(design, {champ: url})


@frappe.whitelist()
def liste(recherche: str | None = None, limite: int = 20) -> list:
	"""Les fiches récentes, pour le sélecteur du studio."""
	filtres = {}
	if recherche:
		filtres = [["Design Emballage", "nom_produit", "like", "%%%s%%" % recherche]]
	return frappe.get_list("Design Emballage", filters=filtres,
	                       fields=["name", "nom_produit", "article", "statut", "modified", "apercu_plan", "type_boite"],
	                       order_by="modified desc", limit_page_length=int(limite))
