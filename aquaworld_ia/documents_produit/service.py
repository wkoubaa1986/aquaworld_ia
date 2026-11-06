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
		row["documents"] = frappe.get_list(
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
			],
			limit_page_length=500,
			order_by="numero desc, creation desc",
		)
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
	photo = a.image or parent.image
	if photo and photo.startswith(("/files/", "/private/files/")):
		C.fichier_lisible(photo)
		d.append(
			"images", {"image": photo, "legende": a.item_name, "article": a.name if a.variant_of else ""}
		)
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
	empreintes = {genre: S.empreinte(M.appliquer(ctx, d, genre)) for genre in S.TYPES}
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
		],
		limit_page_length=1000,
		order_by="numero desc, creation desc",
	)
	references = {}
	for v in versions:
		if v.langue == "fr":
			references.setdefault(v.type_document, v.name)
	for v in versions:
		v["a_actualiser"] = v.empreinte_context != empreintes[v.type_document] or (
			v.langue != "fr" and v.source_fr != references.get(v.type_document)
		)
	sources = []
	membres = [d.article] + [r.article for r in d.variantes]
	for a in membres:
		for f in frappe.get_all(
			"File",
			filters={"attached_to_doctype": "Item", "attached_to_name": a},
			fields=["file_url", "file_name"],
		):
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
	for k in ("consignes", "entete", "marque_document", "logo_marque_avec_entete"):
		if k in data:
			d.set(k, data[k])
	if "mises_en_page" in data:
		d.mises_en_page = json.dumps(M.configuration(data["mises_en_page"]), ensure_ascii=False)
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
def lire_document(name):
	d = document(name)
	return {
		"doc": d.as_dict(),
		"contenu": json.loads(d.contenu_json),
		"contexte": json.loads(d.contexte_json),
	}


def nouvelle_version(parent, genre, contenu, ctx, langue="fr", libelle="Français", rtl=0, source_fr=None):
	dossier(parent, "write", True)
	contenu = S.normaliser(contenu, ctx)
	maximum = frappe.db.sql(
		"select coalesce(max(numero),0) from `tabDocument Produit` where dossier=%s and type_document=%s and langue=%s",
		(parent, genre, langue),
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
	if S.empreinte(contenu) == S.empreinte(json.loads(v.contenu_json)):
		return {"name": v.name}
	nouv = nouvelle_version(
		v.dossier, v.type_document, contenu, ctx, v.langue, v.libelle_langue, v.rtl, v.source_fr
	)
	return {"name": nouv.name}


def _contexte_presentation(v, d):
	"""Actualise la présentation sans modifier le contenu ni enregistrer de version."""
	from aquaworld_ia.documents_produit import marques
	from aquaworld_ia.documents_produit.entetes import contexte_avec_entete, instantane

	ctx = json.loads(v.contexte_json)
	snapshot = instantane(d.get("entete"))
	nouveau_ctx = contexte_avec_entete(ctx, snapshot)
	nouveau_ctx = M.appliquer(nouveau_ctx, d, v.type_document)
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
		nouveau_ctx, v.langue, v.libelle_langue, v.rtl, v.source_fr,
	)


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
def lancer(name, action, document_name=None, langue=None, libelle=None, rtl=0):
	from aquaworld_ia.ia import journal

	d = dossier(name, "write", True)
	if action not in ("fiche", "manuel", "les_deux", "traduire", "pdf", "valider"):
		frappe.throw(_("Action inconnue."))
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
	if action in ("fiche", "manuel", "les_deux", "traduire"):
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
	)
	return {"token": token}


@frappe.whitelist()
def etat(name):
	d = dossier(name)
	return {
		k: d.get(k)
		for k in ("etat_traitement", "progression", "message_traitement", "modified", "debut_traitement")
	}
