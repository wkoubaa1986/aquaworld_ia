"""API commune au studio et à la fiche Article. Les versions sont conservées en base."""

from __future__ import annotations

import json
import re

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, now_datetime
from frappe.utils.file_manager import save_file

from aquaworld_ia.documents_produit import contexte as C
from aquaworld_ia.documents_produit import mise_en_page as M
from aquaworld_ia.documents_produit import plan as PL
from aquaworld_ia.documents_produit import structure as S


def dossier(name, permission="read", verrou=False):
	d = frappe.get_doc(C.DOSSIER, name, for_update=verrou)
	d.check_permission(permission)
	C.article_lisible(d.article)
	return d


def document(name, permission="read"):
	d = frappe.get_doc(C.DOCUMENT, name)
	d.check_permission(permission)
	dossier(d.dossier, permission)
	return d


def categories_caracteristiques(d=None):
	"""Les catégories du tableau des caractéristiques pour un dossier : sa liste si elle est remplie, sinon celle
	des Réglages, sinon la liste par défaut (structure.CATEGORIES_DEFAUT)."""
	from aquaworld_ia.ia.client import reglages

	return S.categories(getattr(d, "categories_caracteristiques", None) or "", reglages().get("categories_caracteristiques") or "")


def _lisible(appel):
	"""Un refus du traitement (« rien à ajouter », « précisez l'information »…) est un message pour l'utilisateur.
	Levé tel quel, il partait en « erreur serveur » avec sa trace (13/11/2026, « Compléter avec l'IA » sur un texte
	sans valeur technique). Une réponse illisible de l'IA reste une vraie erreur."""
	try:
		return appel()
	except json.JSONDecodeError:
		raise
	except ValueError as e:
		frappe.throw(_(str(e)), title=_("Rien n’a été modifié"))


def _json(value):
	return frappe.parse_json(value) if isinstance(value, str) else value


@frappe.whitelist()
def lister(article=None):
	if article:
		a = C.article_lisible(article)
		parent = a.variant_of or a.name
		filters = {"article": parent}
	else:
		filters = {}
	rows = frappe.get_list(
		C.DOSSIER,
		filters=filters,
		fields=["name", "article", "titre", "modified"],
		limit_page_length=200,
		order_by="modified desc",
	)
	resultat = []
	for row in rows:
		try:
			dossier(row.name)
		except frappe.PermissionError:
			continue
		if (
			article
			and article != row.article
			and not frappe.db.exists("Dossier Produit Variante", {"parent": row.name, "article": article})
		):
			continue
		# Les fiches par variante n'apparaissent que sur l'article de leur variante (12/11/2026) : la liste des
		# dossiers et l'article parent ne montrent que les documents du produit.
		row["documents"] = [
			v for v in frappe.get_list(
				C.DOCUMENT,
				filters={"dossier": row.name},
				fields=[
					"name",
					"titre",
					"type_document",
					"langue",
					"libelle_langue",
					"numero",
					"statut",
					"pdf",
					"modified",
					"variante",
				],
				limit_page_length=5000,
				order_by="numero desc, creation desc",
			)
			if not v.variante or v.variante == article
		]
		resultat.append(row)
	return resultat


@frappe.whitelist()
def creer(article):
	frappe.has_permission(C.DOSSIER, "create", throw=True)
	a = C.article_lisible(article)
	parent = C.article_lisible(a.variant_of) if a.variant_of else a
	existant = frappe.db.get_value(C.DOSSIER, {"article": parent.name}, "name")
	if existant:
		d = dossier(existant, "write")
		if a.variant_of and a.name not in {r.article for r in d.variantes}:
			d.append("variantes", {"article": a.name})
			d.save()
		return {"name": existant}
	d = frappe.new_doc(C.DOSSIER)
	d.article = parent.name
	d.titre = parent.item_name
	choix = C.variantes_disponibles(parent.name)
	if len(choix) > 250:
		choix = [v for v in choix if v["name"] == article]
	for v in choix:
		d.append("variantes", {"article": v["name"]})
	# Automatique à la création (12/11/2026) : les photos de l'article, et le QR code du produit s'il est sur le site.
	from aquaworld_ia.documents_produit.photos import initiales

	retenues = {v["name"] for v in choix}
	for ligne in initiales(parent, a):
		if not ligne["article"] or ligne["article"] in retenues:
			d.append("images", ligne)
	depart = M.initiale(C.lien_woocommerce(parent.name).get("url", ""))
	if depart:
		d.mises_en_page = json.dumps(depart, ensure_ascii=False)
	d.insert()
	return {"name": d.name}


def langues():
	return frappe.get_all("Aquaworld IA Langue", fields=["code", "libelle", "rtl"], order_by="libelle")


@frappe.whitelist()
def charger(name):
	from aquaworld_ia.documents_produit import marques
	from aquaworld_ia.documents_produit.couts import bilan
	from aquaworld_ia.documents_produit.entetes import disponibles, instantane

	d = dossier(name)
	ctx = C.contexte(d, inclure_entete=False, tolerer_logo_absent=True)
	erreur_entete = None
	if d.get("entete"):
		try:
			ctx["entete"] = instantane(d.entete, autoriser_desactive=True)
		except (ValueError, frappe.PermissionError, frappe.DoesNotExistError, OSError):
			erreur_entete = "L’en-tête sélectionné est incomplet ou inaccessible. Choisissez un autre modèle ou corrigez-le."
			ctx["entete"] = {"nom": d.entete, "indisponible": True}
	empreintes = {genre: S.empreinte(M.appliquer(PL.appliquer(ctx, d, genre), d, genre)) for genre in S.TYPES}
	versions = frappe.get_list(
		C.DOCUMENT,
		filters={"dossier": d.name},
		fields=[
			"name",
			"titre",
			"type_document",
			"langue",
			"libelle_langue",
			"numero",
			"statut",
			"pdf",
			"source_latex",
			"archive_latex",
			"source_fr",
			"empreinte_context",
			"creation",
			"variante",
			"version_mere",
			"empreinte_variante",
		],
		limit_page_length=5000,
		order_by="numero desc, creation desc",
	)
	references = {}
	for v in versions:
		if v.langue == "fr":
			references.setdefault((v.type_document, v.variante or ""), v.name)
	# Fiche d'une variante : à actualiser quand la fiche du produit, la variante, ses photos ou leurs observations
	# ont changé depuis (empreinte de la variante), et non d'après le contexte du dossier entier.
	empreintes_variantes = {}
	if any(v.variante for v in versions):
		from aquaworld_ia.documents_produit.variantes import empreintes_courantes

		empreintes_variantes = empreintes_courantes(d)
	for v in versions:
		if v.variante:
			perimee = v.langue == "fr" and v.empreinte_variante != empreintes_variantes.get(v.variante)
		else:
			perimee = v.empreinte_context != empreintes[v.type_document]
		v["a_actualiser"] = perimee or (
			v.langue != "fr" and v.source_fr != references.get((v.type_document, v.variante or ""))
		)
		v.pop("empreinte_variante", None)
	sources = []
	pdf_produits = {v.pdf for v in versions if v.pdf}
	membres = [d.article] + [r.article for r in d.variantes]
	for a in membres:
		for f in frappe.get_all(
			"File",
			filters={"attached_to_doctype": "Item", "attached_to_name": a},
			fields=["file_url", "file_name"],
		):
			if f.file_url in pdf_produits:
				continue   # le PDF validé d'une fiche de variante, joint à son article : pas une source
			try:
				C.fichier_lisible(f.file_url, silencieux=True)
			except frappe.PermissionError:
				continue
			sources.append(
				{"fichier": f.file_url, "nom": f.file_name, "article": "" if a == d.article else a}
			)
	if frappe.db.exists("DocType", "Manuel Article"):
		for m in frappe.get_list(
			"Manuel Article",
			filters={"article": ["in", membres]},
			fields=["article", "pdf_source", "titre"],
			limit_page_length=100,
		):
			if m.pdf_source:
				try:
					C.fichier_lisible(m.pdf_source, silencieux=True)
				except frappe.PermissionError:
					continue
				sources.append(
					{
						"fichier": m.pdf_source,
						"nom": m.titre or m.pdf_source.rsplit("/", 1)[-1],
						"article": "" if m.article == d.article else m.article,
					}
				)
	return {
		"dossier": d.as_dict(),
		"contexte": ctx,
		"variantes": C.variantes_disponibles(d.article),
		"documents": versions,
		"langues": langues(),
		"sources_disponibles": list({x["fichier"]: x for x in sources}.values()),
		"peut_ecrire": d.has_permission("write"),
		"couts_ia": bilan(name),
		"entetes": disponibles(),
		"peut_creer_entete": frappe.has_permission("Letter Head", "create"),
		"erreur_entete": erreur_entete,
		"marques": marques.disponibles(),
		"peut_creer_marque": frappe.has_permission("Brand", "create"),
		"lien_woocommerce": C.lien_woocommerce(d.article),
		# Catégories du tableau des caractéristiques : celles qui s'appliquent à ce dossier, et celles des Réglages.
		"categories_caracteristiques": categories_caracteristiques(d),
		"categories_par_defaut": categories_caracteristiques(),
	}


@frappe.whitelist()
def photos_disponibles(name, variantes=None):
	from aquaworld_ia.documents_produit.photos import disponibles

	d = dossier(name)
	selection = [r.article for r in d.variantes] if variantes is None else _json(variantes)
	return disponibles(d, selection)


@frappe.whitelist()
def info_marque(name, marque=None):
	from aquaworld_ia.documents_produit import marques

	d = dossier(name)
	return marques.infos(marque or C.article_lisible(d.article).brand)


@frappe.whitelist()
def creer_marque(name, marque):
	from aquaworld_ia.documents_produit import marques

	dossier(name, "write")
	frappe.has_permission("Brand", "create", throw=True)
	marque = S.texte(marque, 140)
	if not marque:
		frappe.throw(_("Indiquez le nom de la marque."))
	existant = frappe.db.get_value("Brand", {"name": marque}, "name")
	if existant:
		return {"name": marques.lire(existant).name}
	b = frappe.get_doc({"doctype": "Brand", "brand": marque}).insert()
	return {"name": b.name}


@frappe.whitelist()
def enregistrer_logo_marque(name, marque, fichier):
	from aquaworld_ia.documents_produit import marques
	from aquaworld_ia.documents_produit.latex import image_png

	d = dossier(name, "write")
	if marque != marques.effective(d):
		frappe.throw(_("La marque du dossier a changé. Rechargez-le avant de modifier le logo."))
	b = marques.lire(marque, "write")
	image_png(C.octets(fichier))
	b.image = fichier
	b.save()
	return marques.infos(marque)


@frappe.whitelist()
def apercu_qr(name, url):
	"""Le QR d'un lien pour l'aperçu de mise en page (SVG en data URI), sans rien enregistrer."""
	import segno

	dossier(name)
	url = M.normaliser({"qr_url": url}).get("qr_url", "")
	if not url:
		return {"image": ""}
	return {"image": segno.make(url, error="m").svg_data_uri(scale=4, border=2)}


@frappe.whitelist()
def apercu_entete(name, entete):
	import base64

	from aquaworld_ia.documents_produit.entetes import instantane, rendre

	dossier(name)
	return {
		cle: "data:image/png;base64," + base64.b64encode(v["png"]).decode()
		for cle, v in rendre(instantane(entete)).items()
	}


@frappe.whitelist()
def charger_editeur_entete(name, modele=None, marque=None):
	from aquaworld_ia.documents_produit import editeur_entete as V
	from aquaworld_ia.documents_produit import marques

	d = dossier(name)
	resultat = {"peut_creer": frappe.has_permission("Letter Head", "create"), "modele": modele,
		"peut_modifier": False, "compatible": True, "modified": None}
	if modele:
		h = frappe.get_doc("Letter Head", modele)
		h.check_permission("read")
		configuration = V.configuration_enregistree(h)
		resultat.update(titre=h.name, configuration=configuration, compatible=bool(configuration),
			modified=h.modified, peut_modifier=h.has_permission("write"))
	else:
		b = marques.infos(marque or marques.effective(d))
		resultat.update(titre="En-tête " + (b["name"] or "personnalisé"),
			configuration={**V.DEFAUTS, "nom_societe": b["name"], "logo": b["logo"]})
	return resultat


@frappe.whitelist()
def apercu_editeur_entete(name, configuration):
	import base64

	from aquaworld_ia.documents_produit import editeur_entete as V
	from aquaworld_ia.documents_produit import entetes as E

	dossier(name)
	try:
		snapshot = V.preparer(_json(configuration))[3]
		return {cle: {"image": "data:image/png;base64," + base64.b64encode(v["png"]).decode(),
			"hauteur": v["hauteur"]} for cle, v in E.rendre(snapshot).items()}
	except (ValueError, frappe.PermissionError, frappe.DoesNotExistError, OSError) as e:
		return {"erreur": str(e) or "Le logo est absent ou inaccessible. Ajoutez une autre image."}


@frappe.whitelist()
def enregistrer_editeur_entete(name, titre, configuration, modele=None, modified=None, dossier_modified=None):
	from aquaworld_ia.documents_produit import editeur_entete as V
	from aquaworld_ia.documents_produit import entetes as E

	d = dossier(name, "write", True)
	if not dossier_modified or get_datetime(dossier_modified) != get_datetime(d.modified):
		frappe.throw(_("Le dossier a changé. Rechargez-le avant d’enregistrer."), frappe.TimestampMismatchError)
	if modele:
		frappe.get_doc("Letter Head", modele).check_permission("write")
	else:
		frappe.has_permission("Letter Head", "create", throw=True)
	h = V.enregistrer(titre, _json(configuration), modele, modified)
	d.entete = h.name
	d.save()
	return {"name": h.name, "modified": h.modified, "dossier_modified": d.modified, "entetes": E.disponibles()}


@frappe.whitelist()
def detail_cout(name, generation):
	from aquaworld_ia.documents_produit.couts import details

	dossier(name)
	return details(name, generation)


@frappe.whitelist()
def enregistrer(name, data, modified=None):
	d = dossier(name, "write", True)
	data = _json(data)
	if modified and get_datetime(modified) != get_datetime(d.modified):
		frappe.throw(
			_("Le dossier a changé. Rechargez-le avant d’enregistrer."), frappe.TimestampMismatchError
		)
	for k in ("consignes", "entete", "marque_document", "logo_marque_avec_entete", "connaissances_generales"):
		if k in data:
			d.set(k, data[k])
	if "categories_caracteristiques" in data:
		# Vide = la liste des Réglages. Une liste identique à celle-ci n'est pas recopiée dans le dossier.
		liste = S.lire_categories(data["categories_caracteristiques"] or "")
		d.categories_caracteristiques = "" if not liste or liste == categories_caracteristiques() else "\n".join(liste)
	if "mises_en_page" in data:
		d.mises_en_page = json.dumps(M.configuration(data["mises_en_page"]), ensure_ascii=False)
	if "plans" in data:
		plans = PL.configuration(data["plans"])
		d.plans = json.dumps(plans, ensure_ascii=False) if plans else ""
	for table, champs in (
		("variantes", ("article",)),
		("sources", ("fichier", "pages", "article")),
		("images", ("image", "legende", "article")),
	):
		if table in data:
			d.set(table, [{k: r.get(k) for k in champs} for r in data[table]])
	d.save()
	return {"modified": d.modified}


@frappe.whitelist()
def copier_presentation(name, source, elements):
	"""Reprend d'un autre dossier sa présentation pour ce produit (demande 07/11/2026 : « créer un autre document pour un
	autre produit en respectant la même mise en forme »). `elements` : mise_en_page (fiche et manuel, sans ce qui désigne
	des photos du dossier d'origine), marque (marque, logo avec en-tête, en-tête), consignes (consignes et connaissances
	générales), plan (le plan du document du dossier modèle — fiche et manuel — ou, s'il n'en a pas, les rubriques et
	sous-rubriques de ses dernières versions françaises : l'IA suit le même plan pour ce produit). Photos, variantes,
	sources et textes restent ceux de ce dossier. -> {source, repris, modified}"""
	d = dossier(name, "write", True)
	s = dossier(source)
	if s.name == d.name:
		frappe.throw(_("Choisissez un autre dossier que celui-ci."))
	elements = set(_json(elements) or [])
	repris = []
	if "mise_en_page" in elements:
		conf = M.configuration(s.get("mises_en_page"))
		d.mises_en_page = json.dumps({k: M.portable(v) for k, v in conf.items()}, ensure_ascii=False)
		repris.append("mise en page")
	if "marque" in elements:
		for k in ("marque_document", "logo_marque_avec_entete", "entete"):
			d.set(k, s.get(k))
		repris.append("marque et en-tête")
	if "consignes" in elements:
		d.consignes = s.consignes or ""
		d.connaissances_generales = s.get("connaissances_generales") or 0
		repris.append("consignes")
	if "plan" in elements:
		plans = PL.configuration(d.get("plans"))
		for genre in S.TYPES:
			plan = PL.pour_document(s, genre) or _plan_derniere_version(s.name, genre)
			if plan:
				plans[PL.TYPES[genre]] = plan
		if plans:
			d.plans = json.dumps(plans, ensure_ascii=False)
			repris.append("plan du document")
	d.save()
	return {"source": s.titre, "repris": repris, "modified": d.modified}


def _plan_derniere_version(name, genre):
	"""Le plan tiré de la dernière version française du produit : ses rubriques et leurs sous-titres."""
	v = frappe.get_all(C.DOCUMENT, filters={"dossier": name, "langue": "fr", "type_document": genre, "variante": ["is", "not set"]},
		fields=["contenu_json"], order_by="numero desc, creation desc", limit=1)
	return PL.depuis_contenu(json.loads(v[0].contenu_json)) if v else []


@frappe.whitelist()
def plan_depuis_version(name, type_document):
	"""Pour partir de l'existant à l'étape Préparer : le plan de la dernière version française de ce type."""
	d = dossier(name)
	if type_document not in S.TYPES:
		frappe.throw(_("Type de document invalide."))
	return _plan_derniere_version(d.name, type_document)


@frappe.whitelist()
def lire_document(name):
	d = document(name)
	return {
		"doc": d.as_dict(),
		"contenu": json.loads(d.contenu_json),
		"contexte": json.loads(d.contexte_json),
	}


def lien_variante(v):
	"""Ce qui rattache une version à une variante, à reporter sur la version qui la remplace."""
	return {k: v.get(k) or None for k in ("variante", "version_mere", "empreinte_variante")}


def nouvelle_version(parent, genre, contenu, ctx, langue="fr", libelle="Français", rtl=0, source_fr=None,
		variante=None, version_mere=None, empreinte_variante=None):
	"""Les versions se numérotent par document : type, langue et, pour une fiche de variante, la variante."""
	dossier(parent, "write", True)
	contenu = S.normaliser(contenu, ctx)
	maximum = frappe.db.sql(
		"""select coalesce(max(numero),0) from `tabDocument Produit` where dossier=%s and type_document=%s and langue=%s
		and coalesce(variante,'')=%s""",
		(parent, genre, langue, variante or ""),
	)[0][0]
	v = frappe.get_doc(
		{
			"doctype": C.DOCUMENT,
			"dossier": parent,
			"type_document": genre,
			"titre": contenu["titre"],
			"langue": langue,
			"libelle_langue": libelle,
			"rtl": cint(rtl),
			"numero": int(maximum) + 1,
			"statut": "Brouillon",
			"source_fr": source_fr,
			"variante": variante or None,
			"version_mere": version_mere or None,
			"empreinte_variante": empreinte_variante or None,
			"contenu_json": json.dumps(contenu, ensure_ascii=False),
			"contexte_json": json.dumps(ctx, ensure_ascii=False),
			"empreinte_context": S.empreinte({k: val for k, val in ctx.items() if k != "preuves"}),
		}
	)
	v.flags.document_produit_interne = True
	v.insert()
	return v


@frappe.whitelist()
def corriger(name, contenu):
	v = document(name, "write")
	ctx = json.loads(v.contexte_json)
	contenu = S.normaliser(_json(contenu), ctx)
	for s in contenu["sections"]:
		if s.get("image"):
			C.fichier_lisible(s["image"])   # image de rubrique : un fichier lisible par l'utilisateur, sinon refus
	if S.empreinte(contenu) == S.empreinte(json.loads(v.contenu_json)):
		return {"name": v.name}
	nouv = nouvelle_version(
		v.dossier, v.type_document, contenu, ctx, v.langue, v.libelle_langue, v.rtl, v.source_fr, **lien_variante(v)
	)
	return {"name": nouv.name}


def _contexte_presentation(v, d):
	"""Actualise la présentation sans modifier le contenu ni enregistrer de version."""
	return presentation_actuelle(json.loads(v.contexte_json), d, v.type_document, v.get("variante"))


def presentation_actuelle(ctx, d, genre, variante=None):
	"""Le contexte avec la présentation actuelle du dossier : en-tête, mise en page, marque et logo, photos. Une
	fiche de variante garde ses propres photos (celles de son article), choisies quand elle a été créée."""
	from aquaworld_ia.documents_produit import marques
	from aquaworld_ia.documents_produit.entetes import contexte_avec_entete, instantane

	snapshot = instantane(d.get("entete"))
	nouveau_ctx = contexte_avec_entete(ctx, snapshot)
	nouveau_ctx = M.appliquer(nouveau_ctx, d, genre)
	if variante:
		from aquaworld_ia.documents_produit.variantes import mise_en_page_variante

		nouveau_ctx = mise_en_page_variante(nouveau_ctx)
	else:
		nouveau_ctx["images"] = C.images_contexte(d)
		articles = {ctx["article"]["name"]} | {a["name"] for a in ctx.get("variantes", [])}
		if any(im["article"] and im["article"] not in articles for im in nouveau_ctx["images"]):
			raise ValueError("Une photo concerne une variante absente de cette version. Créez une nouvelle fiche ou un nouveau manuel avec les variantes choisies.")
	marque_version = ctx.get("marque_document") or ctx["article"].get("brand") or ""
	if marque_version == marques.effective(d):
		nouveau_ctx.pop("logo_hash", None)
		nouveau_ctx.update(marques.logo(marque_version))
	if d.get("logo_marque_avec_entete"):
		nouveau_ctx["logo_marque_avec_entete"] = 1
	else:
		nouveau_ctx.pop("logo_marque_avec_entete", None)
	return nouveau_ctx


def appliquer_entete(v, d):
	"""Un changement de présentation crée une version, sans nouvelle rédaction IA."""
	ctx = json.loads(v.contexte_json)
	nouveau_ctx = _contexte_presentation(v, d)
	if ctx == nouveau_ctx:
		return v
	from aquaworld_ia.documents_produit.photos import legendes

	return nouvelle_version(
		v.dossier, v.type_document, legendes(json.loads(v.contenu_json), ctx, nouveau_ctx),
		nouveau_ctx, v.langue, v.libelle_langue, v.rtl, v.source_fr, **lien_variante(v),
	)


@frappe.whitelist()
def reecrire_partie(name, document_name, cible, instruction, contenu=None):
	"""Réécrit le résumé ou une rubrique de la version avec l'IA, selon une instruction, à partir du contenu à
	l'écran. Rien n'est enregistré : l'écran reprend le texte, l'utilisateur relit puis enregistre. Un appel IA,
	compté dans les coûts du dossier (action « reecrire »)."""
	from aquaworld_ia.documents_produit import traitement

	d = dossier(name, "write")
	v = document(document_name, "write")
	if v.dossier != name:
		frappe.throw(_("Choisissez une version de ce dossier."))
	if v.langue != "fr":
		frappe.throw(_("Réécrivez la version française, puis traduisez-la : la traduction repart du français."))
	ctx = json.loads(v.contexte_json)
	ctx["consignes"] = d.consignes or ""
	if d.get("connaissances_generales"):
		ctx["connaissances_generales"] = 1
	c = S.normaliser(_json(contenu) if contenu is not None else json.loads(v.contenu_json), ctx)
	return _lisible(lambda: traitement.reecrire(d, v.type_document, ctx, c, _json(cible), instruction))


@frappe.whitelist()
def traiter_point(name, document_name, point, information, destination=None, contenu=None):
	"""Traite un point à vérifier avec l'IA, depuis le contenu à l'écran : l'utilisateur donne l'information, l'IA
	l'écrit au bon endroit. Rien n'est enregistré : l'écran reprend le contenu, l'utilisateur relit puis enregistre.
	Un appel IA, compté dans les coûts du dossier."""
	from aquaworld_ia.documents_produit import traitement

	d = dossier(name, "write")
	v = document(document_name, "write")
	if v.dossier != name:
		frappe.throw(_("Choisissez une version de ce dossier."))
	if v.langue != "fr":
		frappe.throw(_("Traitez les points sur la version française, puis traduisez-la : la traduction repart du français."))
	ctx = json.loads(v.contexte_json)
	ctx["consignes"] = d.consignes or ""
	if d.get("connaissances_generales"):
		ctx["connaissances_generales"] = 1
	c = S.normaliser(_json(contenu) if contenu is not None else json.loads(v.contenu_json), ctx)
	return _lisible(lambda: traitement.traiter_point(d, v.type_document, ctx, c, point, information, _json(destination) if destination else None))


@frappe.whitelist()
def completer_caracteristiques(name, document_name, information="", contenu=None):
	"""Complète le tableau des caractéristiques avec l'IA, depuis le contenu à l'écran : avec le texte collé par
	l'utilisateur, ou, sans texte, en relisant l'article et les sources de la version. Rien n'est enregistré : l'écran
	reprend le contenu, l'utilisateur relit puis enregistre. Un appel IA, compté dans les coûts du dossier."""
	from aquaworld_ia.documents_produit import traitement

	d = dossier(name, "write")
	v = document(document_name, "write")
	if v.dossier != name:
		frappe.throw(_("Choisissez une version de ce dossier."))
	if v.langue != "fr":
		frappe.throw(_("Complétez la version française, puis traduisez-la : la traduction repart du français."))
	ctx = json.loads(v.contexte_json)
	c = S.normaliser(_json(contenu) if contenu is not None else json.loads(v.contenu_json), ctx)
	return _lisible(lambda: traitement.completer_caracteristiques(d, v.type_document, ctx, c, information))


@frappe.whitelist()
def organiser_caracteristiques(name, document_name, contenu=None):
	"""Range le tableau des caractéristiques par catégories avec l'IA, depuis le contenu à l'écran : seule la
	catégorie des lignes change (ni nom, ni valeur, ni unité), puis les lignes sont regroupées. Rien n'est
	enregistré : l'écran montre le classement proposé, l'utilisateur l'applique puis enregistre. Un appel IA."""
	from aquaworld_ia.documents_produit import traitement

	d = dossier(name, "write")
	v = document(document_name, "write")
	if v.dossier != name:
		frappe.throw(_("Choisissez une version de ce dossier."))
	if v.langue != "fr":
		frappe.throw(_("Organisez la version française, puis traduisez-la : la traduction repart du français."))
	ctx = json.loads(v.contexte_json)
	c = S.normaliser(_json(contenu) if contenu is not None else json.loads(v.contenu_json), ctx)
	return _lisible(lambda: traitement.organiser_caracteristiques(d, v.type_document, ctx, c))


@frappe.whitelist()
def illustrer_rubrique(name, document_name, index, mode, instruction="", contenu=None, format=None):
	"""Pour UNE rubrique, depuis le contenu à l'écran : un graphe préparé depuis les données (mode « graphe »), un
	tableau rédigé (« tableau »), une image générée (« image ») ou l'image actuelle retouchée (« retouche ») par
	l'IA (demande 07/11/2026). Rien n'est enregistré : l'écran reprend le résultat, l'utilisateur relit puis
	enregistre. Un appel IA, compté dans les coûts du dossier (action « illustrer »). Graphe et tableau sont refusés
	s'ils citent un nombre absent des données."""
	from frappe.utils import cint

	from aquaworld_ia.documents_produit import illustrations as I

	d = dossier(name, "write")
	v = document(document_name, "write")
	if v.dossier != name:
		frappe.throw(_("Choisissez une version de ce dossier."))
	if v.langue != "fr":
		frappe.throw(_("Illustrez la version française, puis traduisez-la : la traduction repart du français."))
	ctx = json.loads(v.contexte_json)
	ctx["consignes"] = d.consignes or ""
	if d.get("connaissances_generales"):
		ctx["connaissances_generales"] = 1
	c = S.normaliser(_json(contenu) if contenu is not None else json.loads(v.contenu_json), ctx)
	index = cint(index)
	if mode == "graphe":
		return _lisible(lambda: I.graphe_ia(d, v.type_document, ctx, c, index, instruction))
	if mode == "tableau":
		return _lisible(lambda: I.tableau_ia(d, v.type_document, ctx, c, index, instruction))
	if mode in ("image", "retouche"):
		return _lisible(lambda: I.image_ia(d, v.type_document, ctx, c, index, instruction, format, retouche=mode == "retouche"))
	frappe.throw(_("Action inconnue."))


@frappe.whitelist()
def apercu_document(name, document_name=None, contenu=None, mise_en_page=None, type_document=None, echelle=1.4):
	"""Les pages du PDF composées en mémoire depuis le contenu à l'écran (corrections non enregistrées
	comprises), avec la marque, l'en-tête et les photos actuels du dossier, et la mise en page passée en
	argument si elle l'est (réglages en cours, non enregistrés). Sans version : un document d'exemple du type
	demandé. Rien n'est écrit, aucun appel IA (demandes 06/11/2026 : voir le document avant d'enregistrer, puis
	« écran partagé, l'aperçu PDF se recompose pendant que je règle »)."""
	import base64

	import pymupdf

	from aquaworld_ia.documents_produit.latex import composer
	from aquaworld_ia.documents_produit.photos import legendes

	d = dossier(name)
	if document_name:
		v = document(document_name)
		if v.dossier != name:
			frappe.throw(_("Choisissez une version de ce dossier."))
		ctx = _contexte_presentation(v, d)
		c = S.normaliser(legendes(_json(contenu) if contenu is not None else json.loads(v.contenu_json), json.loads(v.contexte_json), ctx), ctx)
		langue, rtl, numero, valide, genre = v.langue, v.rtl, v.numero, v.statut == "Validé", v.type_document
	else:
		genre = type_document if type_document in S.TYPES else S.TYPES[0]
		ctx = C.contexte(d, tolerer_logo_absent=True)
		ctx = M.appliquer(ctx, d, genre)
		c = S.normaliser({"titre": (genre + " — " + d.titre)[:140],
			"resume": "Exemple de disposition. Le contenu apparaîtra après rédaction du document."}, ctx)
		langue, rtl, numero, valide = "fr", False, 1, False
	if mise_en_page is not None:
		ctx["mise_en_page"] = M.normaliser(_json(mise_en_page))
		if ctx.get("variante"):
			from aquaworld_ia.documents_produit.variantes import mise_en_page_variante

			ctx = mise_en_page_variante(ctx)   # même galerie que dans le PDF de la fiche de variante
	for s in c["sections"]:
		if s.get("image"):
			C.fichier_lisible(s["image"])
	_tex, pdf, _zip = composer(c, ctx, langue, rtl, numero, valide)
	pages = []
	zoom = max(0.8, min(2.0, float(echelle or 1.4)))
	with pymupdf.open(stream=pdf, filetype="pdf") as doc:
		for page in list(doc)[:20]:
			png = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False).tobytes("png")
			pages.append("data:image/png;base64," + base64.b64encode(png).decode())
		return {"pages": pages, "total": len(doc), "type_document": genre}


@frappe.whitelist()
def apercu_placement_logo(name, type_document, mise_en_page, document_name=None, contenu=None):
	"""Première page sans la zone de marque : fond de placement, sans IA ni fichier enregistré."""
	import base64

	import pymupdf

	from aquaworld_ia.documents_produit.latex import composer

	d = dossier(name)
	if type_document not in S.TYPES:
		frappe.throw(_("Type de document invalide."))
	langue, rtl, numero, valide = "fr", False, 1, False
	if document_name:
		v = document(document_name)
		if v.dossier != name or v.type_document != type_document:
			frappe.throw(_("Choisissez une version de ce type dans ce dossier."))
		ctx = _contexte_presentation(v, d)
		from aquaworld_ia.documents_produit.photos import legendes

		c = S.normaliser(legendes(_json(contenu) if contenu is not None else json.loads(v.contenu_json), json.loads(v.contexte_json), ctx), ctx)
		langue, rtl, numero, valide = v.langue, v.rtl, v.numero, v.statut == "Validé"
	else:
		ctx = C.contexte(d, tolerer_logo_absent=True)
		c = S.normaliser({"titre": (type_document + " — " + d.titre)[:140],
			"resume": "Exemple de disposition. Le contenu apparaîtra après rédaction du document."}, ctx)
	disposition = M.normaliser(_json(mise_en_page))
	ctx["mise_en_page"] = {**disposition, "position_marque": "masquee"}
	_source_tex, pdf, _archive_zip = composer(c, ctx, langue, rtl, numero, valide)
	with pymupdf.open(stream=pdf, filetype="pdf") as pages:
		png = pages[0].get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False).tobytes("png")
		return {"image": "data:image/png;base64," + base64.b64encode(png).decode(),
			"pages": len(pages), "exemple": not bool(document_name)}


@frappe.whitelist()
def illustrer_page(name, fichier, page=1):
	import pymupdf

	d = dossier(name, "write", True)
	if fichier not in {r.fichier for r in d.sources}:
		frappe.throw(_("Choisissez un PDF source de ce dossier."))
	with pymupdf.open(stream=C.octets(fichier), filetype="pdf") as pdf:
		no = cint(page) - 1
		if not 0 <= no < len(pdf):
			frappe.throw(_("Cette page n’existe pas."))
		p = pdf[no]
		png = p.get_pixmap(
			matrix=pymupdf.Matrix(
				min(2, 2400 / max(p.rect.width, p.rect.height)),
				min(2, 2400 / max(p.rect.width, p.rect.height)),
			),
			alpha=False,
		).tobytes("png")
	f = save_file("illustration-page-%s.png" % (no + 1), png, C.DOSSIER, d.name, is_private=1)
	portee = next(r.article for r in d.sources if r.fichier == fichier)
	d.append(
		"images",
		{"image": f.file_url, "legende": "Illustration du manuel — page %s" % (no + 1), "article": portee},
	)
	d.save()
	return {"image": f.file_url}


@frappe.whitelist()
def lancer(name, action, document_name=None, langue=None, libelle=None, rtl=0, articles=None, forcer=0):
	"""`photos`, `variantes` et `valider_variantes` (12/11/2026) portent sur les variantes `articles` du dossier
	(toutes si absent) ; `forcer` relit les photos déjà lues ou fait réécrire les spécificités des fiches à jour."""
	from aquaworld_ia.ia import journal

	d = dossier(name, "write", True)
	if action not in ("fiche", "manuel", "les_deux", "traduire", "pdf", "valider", "photos", "variantes", "valider_variantes"):
		frappe.throw(_("Action inconnue."))
	lot = action in ("photos", "variantes", "valider_variantes")
	if lot:
		from aquaworld_ia.documents_produit import variantes as V

		document_name = None
		try:
			articles = V._articles_du_lot(d, _json(articles) if articles else None)
		except ValueError as e:
			frappe.throw(_(str(e)))
		if not articles:
			frappe.throw(_("Cochez d’abord les variantes couvertes par le dossier (étape Préparer)."))
		if action != "photos" and not V.mere_courante(name):
			frappe.throw(_("Créez d’abord la fiche technique du produit : les fiches par variante la reprennent."))
	if (
		d.etat_traitement in ("En attente", "En cours")
		and d.debut_traitement
		and (now_datetime() - get_datetime(d.debut_traitement)).total_seconds() < 3900
	):
		frappe.throw(_("Un traitement est déjà en cours sur ce dossier."))
	if action in ("traduire", "pdf", "valider"):
		v = document(document_name, "write")
		if v.dossier != name:
			frappe.throw(_("Le document appartient à un autre dossier."))
		if action == "traduire":
			langue = (langue or "").strip().lower()
			libelle = (libelle or langue).strip()
			if (
				v.langue != "fr"
				or langue == "fr"
				or not re.fullmatch(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})*", langue)
				or len(langue) > 30
				or len(libelle) > 140
			):
				frappe.throw(_("Choisissez une langue cible différente du français (code : en, ar, zh…)."))
			info = frappe.db.get_value("Aquaworld IA Langue", langue, ["libelle", "rtl"], as_dict=True)
			if info:
				libelle, rtl = info.libelle, info.rtl
			elif langue.split("-")[0] in ("ar", "fa", "he", "ur", "ps", "sd"):
				rtl = 1
		if action == "valider" and json.loads(v.contenu_json).get("points_a_verifier"):
			frappe.throw(
				_("Résolvez les points à vérifier, puis enregistrez vos corrections avant de valider.")
			)
		if action in ("pdf", "valider"):
			v = appliquer_entete(v, d)
			document_name = v.name
	if action in ("fiche", "manuel", "les_deux", "traduire", "photos", "variantes"):
		journal.verifier_plafond()
	token = frappe.generate_hash(length=20)
	d.etat_traitement = "En attente"
	d.progression = 0
	d.message_traitement = "Traitement en attente"
	d.token_traitement = token
	d.debut_traitement = now_datetime()
	d.utilisateur_traitement = frappe.session.user
	d.save()
	frappe.enqueue(
		"aquaworld_ia.documents_produit.traitement.executer",
		queue="long",
		timeout=3600,
		enqueue_after_commit=True,
		job_id="documents-produit-" + token,
		name=name,
		token=token,
		action=action,
		document_name=document_name,
		langue=langue,
		libelle=libelle,
		rtl=cint(rtl),
		utilisateur=frappe.session.user,
		articles=articles if lot else None,
		forcer=cint(forcer),
	)
	return {"token": token}


@frappe.whitelist()
def fiches_variantes(name):
	"""Le suivi des fiches par variante du dossier : une ligne par variante (photos lues, fiche, points, à jour)."""
	from aquaworld_ia.documents_produit import variantes as V

	return V.etat(dossier(name))


@frappe.whitelist()
def observations_photos(name):
	"""Les images distinctes des variantes du dossier, avec ce que l'IA y a vu, pour relecture."""
	from aquaworld_ia.documents_produit import variantes as V

	return V.liste_observations(dossier(name))


@frappe.whitelist()
def enregistrer_observation(name, empreinte, observation):
	"""La correction d'une observation de photo par l'utilisateur : elle ne sera plus relue par l'IA, et les fiches
	des variantes qui montrent cette photo passent « à actualiser »."""
	from aquaworld_ia.documents_produit import observations as O
	from aquaworld_ia.documents_produit import variantes as V

	d = dossier(name, "write")
	photo = next((p for p in V.liste_observations(d) if p["empreinte"] == empreinte), None)
	if not photo:
		frappe.throw(_("Cette photo n’appartient pas aux variantes du dossier."))
	propre = O.normaliser(_json(observation))
	O.enregistrer(photo, propre, corrigee=1)
	return propre


@frappe.whitelist()
def telecharger_fiches_variantes(name):
	"""Le ZIP des derniers PDF des fiches de variante du dossier."""
	from aquaworld_ia.documents_produit import variantes as V

	archive = V.archive_pdf(dossier(name))
	if not archive:
		frappe.throw(_("Aucune fiche de variante n’a encore de PDF."))
	frappe.local.response.filename, frappe.local.response.filecontent = archive
	frappe.local.response.type = "download"


@frappe.whitelist()
def etat(name):
	d = dossier(name)
	return {
		k: d.get(k)
		for k in ("etat_traitement", "progression", "message_traitement", "modified", "debut_traitement")
	}
