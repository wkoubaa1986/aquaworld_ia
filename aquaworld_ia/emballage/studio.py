"""Le « Studio emballage » : la page Desk plein écran qui remplace le formulaire pour concevoir
un emballage (demande utilisateur 23/09/2026 : « je ne vois pas une meilleure UI »).

Ici ne vivent que la LECTURE groupée (tout ce que la page affiche, en un appel) et
l'ENREGISTREMENT des champs éditables. Les actions coûteuses (textes IA, variantes, plan, faces,
3D) restent dans textes.py / job.py / composition.py : le studio et la fiche partagent le même
moteur, aucune règle n'est dupliquée.
"""

from __future__ import annotations

import json
import re

import frappe
from frappe import _
from frappe.utils import cint, flt

from aquaworld_ia.emballage import codes, composition, contenus, exports, geometrie, job, mise_en_forme, textes
from aquaworld_ia.manuels import rendu
from aquaworld_ia.emballage.variantes import url_logo, url_photo

#: Les seuls champs que la page peut écrire. Tout le reste (statut, plan, variantes…) est le
#: résultat d'un traitement, jamais une saisie.
CHAMPS_EDITABLES = (
	"nom_produit", "marque", "logo", "photo_produit", "type_boite", "longueur_mm", "hauteur_mm",
	"profondeur_mm", "repli_mm", "fond_perdu_mm", "zone_securite_mm", "patte_collage_mm", "caracteristiques",
	"avertissements", "contact", "type_code_barres", "code_barres", "url_qr", "couleur_qr", "brief_style", "palette",
	"nb_variantes", "couleur_fond", "image_fond", "faces_identiques", "cotes_identiques", "pictos_sans_cartouche", "fond_continu", "mise_en_page",
	"fonds_faces", "ameliorer_images_pdf",
	"police_caracteristiques", "taille_caracteristiques",
)
CHAMPS_NUMERIQUES = ("longueur_mm", "hauteur_mm", "profondeur_mm", "repli_mm", "fond_perdu_mm", "zone_securite_mm",
                     "patte_collage_mm", "taille_caracteristiques")


def _contenu_du_doc(doc) -> dict:
	"""Les drapeaux de contenu pour la maquette, lus dans la fiche elle-même."""
	t = contenus.imprimes(doc)
	premiere = t[next(iter(t))] if t else {}
	return {
		"logo": bool(doc.logo or doc.marque),
		"textes": bool(premiere.get("accroche")),
		"caracteristiques": bool(premiere.get("caracteristiques")),
		"avertissements": bool(premiere.get("avertissements")),
		"contact": bool(premiere.get("contact")),
		"pictos": len(doc.pictogrammes or []),
		"code_barres": doc.type_code_barres != "Aucun" and bool(doc.code_barres or doc.url_qr),
		"faces_identiques": bool(doc.get("faces_identiques")),
		"cotes_identiques": bool(doc.get("cotes_identiques")),
		"mise_en_page": doc.get("mise_en_page") or None,
		"photo_auto": photo_automatique(doc),
	}


def photo_automatique(doc) -> bool:
	"""La photo produit sera-t-elle posée D'OFFICE au centre de la face avant ? Même règle que
	`composition.composer` : une photo, pas de visuel IA de face avant (variante choisie, hors fond
	continu) et aucune zone « Photo produit » dessinée. Le studio la montre alors sur le plan comme une
	zone « automatique » qu'on peut saisir (retour utilisateur 06/10/2026 : « photo produit je ne la
	trouve pas »)."""
	from aquaworld_ia.emballage.variantes import url_photo

	from aquaworld_ia.emballage.composition import reglage_fond

	if not url_photo(doc):
		return False
	reg = reglage_fond(frappe.parse_json(doc.fonds_faces) if doc.get("fonds_faces") else {}, "avant")
	if reg and reg.get("photo_incluse"):
		return False          # la face avant composée par l'IA montre déjà le produit
	continu = cint(doc.get("fond_continu")) and doc.get("image_fond")
	v = next((x for x in doc.get("variantes") or [] if x.numero == cint(doc.get("variante_choisie"))), None)
	if v and v.image and not continu and not reg:
		return False
	mep = frappe.parse_json(doc.mise_en_page) if doc.get("mise_en_page") else {}
	return not any(isinstance(z, dict) and z.get("zone") == "photo"
	               for liste in (mep or {}).values() if isinstance(liste, list) for z in liste)


def apercu_du_doc(doc) -> dict | None:
	if geometrie.dimensions_manquantes(doc.type_boite or geometrie.ETUI, flt(doc.longueur_mm), flt(doc.hauteur_mm),
	                                   flt(doc.profondeur_mm), flt(doc.get("repli_mm"))):
		return None
	return job.apercu(doc.type_boite, doc.longueur_mm, doc.hauteur_mm, doc.profondeur_mm, doc.patte_collage_mm,
	                  doc.fond_perdu_mm, doc.zone_securite_mm, contenu=_contenu_du_doc(doc), repli_mm=doc.get("repli_mm"))


@frappe.whitelist()
def charger(design: str, catalogues=1) -> dict:
	"""Tout ce que la page affiche, en UN appel : la fiche, le plan, les textes, l'état du job,
	les catalogues (formes, langues, pictogrammes)."""
	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("read")
	langues = {l["code"]: l for l in textes._langues_du_design(doc)}
	t = contenus.imprimes(doc)
	donnees = doc.as_dict()
	principal = t[contenus.langues(doc)[0]]
	for champ in ("caracteristiques", "avertissements"):
		donnees[champ] = "\n".join(principal.get(champ) or [])
	donnees["contact"] = principal.get("contact") or ""
	e = exports.etat(doc)
	if e["pdf"] == "a_regenerer" and donnees.statut == "Plan prêt":
		donnees.statut = "À recomposer"
	apercu = apercu_du_doc(doc)
	if apercu and not apercu.get("erreur"):
		familles = rendu.familles_disponibles()
		fam_titres = composition.famille_titres(rendu.FAMILLE_TITRES in {f for f, _ in rendu.polices_personnalisees()})
		for face in apercu["faces"]:
			for zone in face["zones"]:
				if zone["zone"] in composition.ZONES_TEXTE:
					zone["apercu_texte"] = composition.html_zone(doc, zone, t, langues, familles, fam_titres=fam_titres)
		from aquaworld_ia.emballage.apercu_elements import choix_zones, enrichir

		apercu["choix_zones"] = choix_zones(doc, t, langues, familles, fam_titres)
		enrichir(doc, apercu)
	out = {
		"doc": donnees,
		"peut_ecrire": doc.has_permission("write"),
		"apercu": apercu,
		"textes_html": textes.html_textes(t or {}, langues),
		"etat": job.etat_design(design),
		"images": images_du_design(doc),
		"visuels": {"logo": url_logo(doc), "photo": url_photo(doc)},
		"textes_imprimes": t,
		"exports": e,
		"verifications": exports.verifier(doc),
		"desalignes": [], "textes_non_appliques": [],
	}
	if cint(catalogues):
		out.update(catalogues_du_studio())
	return out


def catalogues_du_studio():
	"""Catalogues chargés à l’ouverture ; une sauvegarde ne les reconstruit plus."""
	return {
		"types": job.types_emballage(),
		"langues": frappe.get_all("Aquaworld IA Langue", filters={"actif": 1}, fields=["code", "libelle", "rtl"],
		                          order_by="code"),
		"pictos": pictos_avec_vignette(),
		"estimation": job.estimation_variantes(1),
		"polices": polices_du_studio(),
		"polices_apercu": polices_apercu(),
	}


def polices_apercu() -> list[dict]:
	"""Polices des textes automatiques (arabe, réglages, langues), sans changer le sélecteur."""
	arabe = rendu.POLICES_LIVREES["Noto Naskh Arabic"]
	return [{"famille": "Noto Naskh Arabic", "styles": {
		cle: "/assets/aquaworld_ia/fonts/%s" % fichier
		for (cle, _p, _s), fichier in zip(rendu.STYLES_POLICE, arabe) if fichier
	}}] + [{"famille": famille, "styles": {"regulier": url}} for famille, url in rendu.polices_personnalisees()]


@frappe.whitelist()
def utiliser_lignes_brutes(design: str, langue: str) -> dict:
	"""Les caractéristiques de l'étape 2, mise en forme comprise, deviennent celles qui s'impriment
	pour `langue`, telles quelles — quand elles sont déjà écrites dans cette langue (demande
	utilisateur 24/09/2026 : la zone Caractéristiques imprimait la reformulation de l'IA, 8 lignes
	sans mise en forme, au lieu de ses 11 lignes mises en forme)."""
	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("write")
	t = contenus.imprimes(doc)
	if langue not in (t or {}):
		frappe.throw(_("Pas de textes préparés en {0}.").format(langue))
	t[langue].update(textes_de_l_etape_2(doc))
	contenus.poser(doc, t)
	doc.save()
	return charger(design)


def textes_de_l_etape_2(doc) -> dict:
	"""Ce qui s'imprime quand on choisit « mes textes tels quels » : caractéristiques (mise en forme comprise),
	avertissements et contact de l'étape 2 (06/10/2026 : l'utilisateur avait retiré une ligne et les
	avertissements, l'emballage gardait les textes préparés par l'IA). L'accroche reste celle des textes préparés."""
	return {"caracteristiques": mise_en_forme.lignes_imprimables(doc.caracteristiques),
	        "avertissements": mise_en_forme.lignes_imprimables(doc.avertissements),
	        "contact": (doc.contact or "").strip()}


def textes_non_appliques(doc, t: dict) -> list[str]:
	"""Les langues dont le texte IMPRIMÉ diffère de l'étape 2 — seulement la PREMIÈRE langue préparée (celle dans
	laquelle on écrit ; les autres sont des traductions, forcément différentes). Pur à `doc` près."""
	if not t:
		return []
	code = next(iter(t))
	brut, imprime = textes_de_l_etape_2(doc), t.get(code) or {}
	return [code] if any((imprime.get(k) or ([] if k != "contact" else "")) != v for k, v in brut.items()) else []


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
	("-logo-ia", "Logo IA"), ("-logo-couleur", "Logo couleur"), ("-logo-vectorise", "Logo SVG"), ("-logo", "Logo"), ("-tampon", "Tampon IA"),
	("-face-", "Face composée IA"), ("-photo-ia", "Photo IA"), ("-photo-vectorise", "Photo SVG"), ("-photo", "Photo"), ("-mosaique", "Photo mosaïque"), ("-fond", "Fond IA"),
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
	# Une photo d’article ou un logo de marque peut être utilisé sans pièce jointe au design.
	for champ, genre in (("logo", "Logo"), ("photo_produit", "Photo"), ("image_fond", "Fond")):
		url = doc.get(champ)
		if url and url not in vus:
			vus.add(url)
			out.append({"file_url": url, "file_name": url.rsplit("/", 1)[-1], "creation": doc.get("modified"),
			            "genre": genre, "usage": champ})
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
	                     fields=["code", "libelle", "categorie", "image", "fichier", "taille_mm"], order_by="categorie, code")
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
			if champ in ("logo", "photo_produit", "image_fond") and val:
				_image_lisible(doc, val)
			if champ in CHAMPS_NUMERIQUES:
				val = flt(val)
			if champ in ("mise_en_page", "fonds_faces") and not isinstance(val, str):
				val = json.dumps(val, ensure_ascii=False) if val else None
			doc.set(champ, val)
	if "langues" in v:
		doc.set("langues", [{"langue": c} for c in (v["langues"] or []) if c])
	if "pictogrammes" in v:
		doc.set("pictogrammes", [{"pictogramme": c} for c in (v["pictogrammes"] or []) if c])
	if doc.type_boite and doc.type_boite not in geometrie.TYPES:
		frappe.throw(_("Forme inconnue : {0}").format(doc.type_boite))
	if "couleur_qr" in v and doc.couleur_qr:
		c = codes.normaliser_couleur(doc.couleur_qr)
		if not c:
			frappe.throw(_("Couleur du QR invalide : choisissez-la dans la palette ou saisissez un code #RRGGBB."))
		if codes.contraste_sur_blanc(c) < codes.CONTRASTE_QR_MIN:
			frappe.throw(_("{0} est trop clair pour un QR : un téléphone le lirait mal sur son cartouche blanc (contraste {1}, il faut au moins {2}). Prenez une teinte plus foncée.").format(
				c, "%.1f" % codes.contraste_sur_blanc(c), "%g" % codes.CONTRASTE_QR_MIN))
		doc.couleur_qr = c
	doc.save()
	return charger(design, catalogues=0)


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
CHAMPS_NON_DUPLIQUES = ("statut", "plan_a_plat", "apercu_plan", "apercu_3d", "empreinte_plan", "empreinte_3d", "journal", "rapport_resolution")
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
	mep_a_copier = copie.mise_en_page
	copie.mise_en_page = None  # Les variantes SVG privées seront validées après leur rattachement.
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
	mep = frappe.parse_json(mep_a_copier) if mep_a_copier else None
	if isinstance(mep, dict):
		for zones in mep.values():
			for z in zones if isinstance(zones, list) else []:
				if isinstance(z, dict) and z.get("logo"):
					z["logo"] = rattacher(z["logo"])
				if isinstance(z, dict) and isinstance(z.get("pictos_images"), dict):
					z["pictos_images"] = {c: rattacher(u) for c, u in z["pictos_images"].items()}
		copie.mise_en_page = json.dumps(mep, ensure_ascii=False)
	fonds = frappe.parse_json(copie.fonds_faces) if copie.get("fonds_faces") else None
	if isinstance(fonds, dict):
		for reg in fonds.values():
			if isinstance(reg, dict) and reg.get("image"):
				reg["image"] = rattacher(reg["image"])
		copie.fonds_faces = json.dumps(fonds, ensure_ascii=False)
	copie.save()
	return {"name": copie.name}


@frappe.whitelist()
def zones_ajoutables() -> list:
	from aquaworld_ia.emballage.composition import ZONES_AJOUTABLES

	return [{"zone": z, "libelle": geometrie.ZONES_LIBELLES.get(z, z)} for z in ZONES_AJOUTABLES]


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
	_image_lisible(doc, url)
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
	lignes = frappe.get_list("Ressource Emballage", filters=filtres, fields=["name", "nom", "categorie", "marque", "image", "notes", "modified"],
	                         order_by="modified desc", limit_page_length=max(1, min(cint(limite) or 60, 200)))
	if marque:
		lignes.sort(key=lambda l: 0 if l.get("marque") == marque else 1)
	return lignes


@frappe.whitelist()
def bibliotheque_choisir(design: str, ressource: str, champ: str) -> dict:
	"""Pose une ressource de la bibliothèque dans un champ du design (copie du fichier)."""
	if champ not in CHAMPS_BIBLIOTHEQUE:
		frappe.throw(_("Ce champ ne va pas dans la bibliothèque."))
	res = frappe.get_doc("Ressource Emballage", ressource)
	res.check_permission("read")
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


from aquaworld_ia.emballage.ressources import image_lisible as _image_lisible

# Compatibilité des routes publiques existantes et de la fiche ERPNext.
from aquaworld_ia.emballage.atelier_images import (
	retoucher_logo,
	PROMPTS_RETOUCHE,
	prompt_retouche,
	taille_retouche,
	retoucher_image,
	adopter_image,
	vectoriser_image,
	palette_logo,
	logo_couleur,
	proposer_fonds,
	COMPOSANTS_FACE,
	_references_face,
	composer_face_ia,
	adopter_face_ia,
	blanchir,
	adopter_fond,
	creer_tampons,
	adopter_tampon,
	adopter_logo,
	_mosaique_images,
	mosaique_apercu,
	mosaique_creer,
	EXTENSIONS_IMAGE,
	photos_autres_articles,
	PROMPT_ORIENTATION,
	orienter_variante,
	PROMPT_CORRECTION_ORIENTATION,
	PROMPT_REFERENCE_SILHOUETTE,
	silhouette_png,
	consigne_proportions,
	_ratio_hauteur_largeur,
	PROMPT_REFERENCE_CHOISIE,
	corriger_orientation,
)
