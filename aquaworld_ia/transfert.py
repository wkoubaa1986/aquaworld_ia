"""Le contenu de référence qui voyage avec l'app (demande utilisateur 25/09/2026 : « une fixture qui
amène sa base actuelle en prod ») : les fichiers rattachés aux fixtures (images de pictogrammes,
polices, fonds et logos de la bibliothèque) et les Réglages sans secret.

- `exporter()` (en dev, avant de pousser) : copie ces fichiers dans `contenu/fichiers/` avec un
  manifeste, et écrit `contenu/reglages.json`. Se lance avec `bench export-fixtures` via le hook
  `export_fixtures`… ou à la main : `bench --site <site> execute aquaworld_ia.transfert.exporter`.
- `restaurer()` (après migration, partout) : recrée les fiches File manquantes et pose les fichiers
  sur le site ; applique les Réglages ; donne le rôle « Aquaworld IA » aux utilisateurs listés.
Les documents de travail (manuels, designs) ne sont PAS des fixtures : voir `exporter_travail`.
"""

from __future__ import annotations

import json
import os
import re
import shutil

import frappe

# ⚠️ PAS dans fixtures/ : Frappe importe chaque .json de ce dossier comme un document (le deploy du
# 25/09/2026 a échoué sur reglages.json → KeyError 'doctype'). Les fichiers et les réglages vivent
# dans contenu/, à côté.
DOSSIER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "contenu")
DOSSIER_FICHIERS = os.path.join(DOSSIER, "fichiers")
MANIFESTE = os.path.join(DOSSIER_FICHIERS, "manifeste.json")
REGLAGES = os.path.join(DOSSIER, "reglages.json")
ROLE = "Aquaworld IA"
#: Les comptes qui reçoivent le rôle après migration, s'ils existent sur le site.
UTILISATEURS_ROLE = ["koubaawassim@gmail.com"]
#: DocTypes en fixtures dont les champs Attach référencent des fichiers du site.
CHAMPS_FICHIERS = {
	"Aquaworld IA Pictogramme": ["image"],
	"Police Emballage": ["regulier", "gras", "italique", "gras_italique"],
	"Ressource Emballage": ["image"],
	"Aquaworld IA Langue": ["police_fichier"],
}
#: Champs des Réglages jamais exportés (secrets, ou propres au site).
REGLAGES_EXCLUS = {"email_alerte"}


def _chemin_site(url: str) -> str:
	if url.startswith("/private/files/"):
		return frappe.get_site_path("private", "files", url.split("/private/files/", 1)[1])
	return frappe.get_site_path("public", "files", url.split("/files/", 1)[1])


def exporter() -> dict:
	"""Emballe les fichiers des fixtures et les Réglages dans l'app. -> {fichiers, reglages}."""
	os.makedirs(DOSSIER_FICHIERS, exist_ok=True)
	manifeste = []
	for doctype, champs in CHAMPS_FICHIERS.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		for row in frappe.get_all(doctype, fields=["name"] + champs):
			for champ in champs:
				url = row.get(champ)
				if not url or not url.startswith(("/files/", "/private/files/")):
					continue
				src = _chemin_site(url)
				if not os.path.exists(src):
					continue
				nom = url.rsplit("/", 1)[-1]
				shutil.copyfile(src, os.path.join(DOSSIER_FICHIERS, nom))
				manifeste.append({"doctype": doctype, "name": row.name, "champ": champ, "url": url, "fichier": nom,
				                  "prive": url.startswith("/private/")})
	with open(MANIFESTE, "w", encoding="utf-8") as f:
		json.dump(manifeste, f, ensure_ascii=False, indent=1)
	reglages = {}
	if frappe.db.exists("DocType", "Aquaworld IA Reglages"):
		doc = frappe.get_single("Aquaworld IA Reglages")
		for df in doc.meta.fields:
			if df.fieldtype in ("Section Break", "Column Break", "Tab Break", "HTML") or df.fieldname in REGLAGES_EXCLUS:
				continue
			v = doc.get(df.fieldname)
			if v not in (None, ""):
				reglages[df.fieldname] = v
		for url in [v for v in reglages.values() if isinstance(v, str) and v.startswith(("/files/", "/private/files/"))]:
			src = _chemin_site(url)
			if os.path.exists(src):
				nom = url.rsplit("/", 1)[-1]
				shutil.copyfile(src, os.path.join(DOSSIER_FICHIERS, nom))
				manifeste.append({"doctype": "Aquaworld IA Reglages", "name": "Aquaworld IA Reglages", "champ": None, "url": url,
				                  "fichier": nom, "prive": url.startswith("/private/")})
		with open(MANIFESTE, "w", encoding="utf-8") as f:
			json.dump(manifeste, f, ensure_ascii=False, indent=1)
	with open(REGLAGES, "w", encoding="utf-8") as f:
		json.dump(reglages, f, ensure_ascii=False, indent=1)
	return {"fichiers": len(manifeste), "reglages": len(reglages)}


def restaurer() -> dict:
	"""Après migration : fichiers des fixtures, Réglages, rôle. Idempotent, ne lève jamais."""
	out = {"fichiers": 0, "reglages": 0, "roles": 0}
	try:
		out["fichiers"] = restaurer_fichiers()
	except Exception:
		frappe.log_error(title="Aquaworld IA : fichiers des fixtures", message=frappe.get_traceback())
	try:
		out["reglages"] = appliquer_reglages()
	except Exception:
		frappe.log_error(title="Aquaworld IA : réglages des fixtures", message=frappe.get_traceback())
	try:
		out["roles"] = donner_le_role()
	except Exception:
		frappe.log_error(title="Aquaworld IA : rôle", message=frappe.get_traceback())
	return out


def restaurer_fichiers() -> int:
	if not os.path.exists(MANIFESTE):
		return 0
	with open(MANIFESTE, encoding="utf-8") as f:
		manifeste = json.load(f)
	poses = 0
	for e in manifeste:
		src = os.path.join(DOSSIER_FICHIERS, e["fichier"])
		if not os.path.exists(src):
			continue
		dest = _chemin_site(e["url"])
		if not os.path.exists(dest):
			os.makedirs(os.path.dirname(dest), exist_ok=True)
			shutil.copyfile(src, dest)
			poses += 1
		if not frappe.db.exists("File", {"file_url": e["url"]}):
			rattache = e["doctype"] != "Aquaworld IA Reglages" and frappe.db.exists(e["doctype"], e["name"])
			fiche_fichier_existant({
				"file_name": e["fichier"], "file_url": e["url"], "is_private": 1 if e["prive"] else 0,
				"attached_to_doctype": e["doctype"] if rattache else None, "attached_to_name": e["name"] if rattache else None,
				"attached_to_field": e["champ"] if rattache else None,
			})
	return poses


def fiche_fichier_existant(valeurs: dict):
	"""La fiche File d'un fichier DÉJÀ posé sur le site, sous SON nom. Un `insert()` ordinaire relit le
	fichier et le réécrit : trouvant un fichier du même nom, Frappe en pose une copie suffixée de
	l'empreinte (« …apercu-3d09a609.png » → « …apercu-3d09a60909a609.png ») et la fiche pointe la copie ;
	le document, lui, pointe l'original, sans fiche → « Forbidden » pour un fichier privé (constaté en
	prod le 06/10/2026 sur EMB-2026-0006, et sur 0002-0005 depuis le transfert du 25/09)."""
	from frappe.core.doctype.file.utils import get_content_hash

	f = frappe.get_doc(dict(valeurs, doctype="File"))
	chemin = _chemin_site(f.file_url)
	if os.path.exists(chemin):
		with open(chemin, "rb") as fh:
			contenu = fh.read()
		f.content_hash = get_content_hash(contenu)
		f.file_size = len(contenu)
	f.flags.copy_from_existing_file = True       # Frappe ≥ 15.10x : ni relecture ni réécriture du fichier
	return f.insert(ignore_permissions=True)


def appliquer_reglages() -> int:
	if not os.path.exists(REGLAGES) or not frappe.db.exists("DocType", "Aquaworld IA Reglages"):
		return 0
	with open(REGLAGES, encoding="utf-8") as f:
		valeurs = json.load(f)
	doc = frappe.get_single("Aquaworld IA Reglages")
	n = 0
	for k, v in valeurs.items():
		if doc.meta.has_field(k) and doc.get(k) != v:
			doc.set(k, v)
			n += 1
	if n:
		doc.save(ignore_permissions=True)
	return n


def donner_le_role() -> int:
	if not frappe.db.exists("Role", ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 1}).insert(ignore_permissions=True)
	n = 0
	for email in UTILISATEURS_ROLE:
		if not frappe.db.exists("User", email):
			continue
		user = frappe.get_doc("User", email)
		if not any(r.role == ROLE for r in user.roles):
			user.append("roles", {"role": ROLE})
			user.save(ignore_permissions=True)
			n += 1
	return n


# ------------------------------------------------------------------ documents de travail (manuels, designs)
# Demande utilisateur 25/09/2026 : « les designs et le manuel créés en dev n'ont pas migré ». Ce ne
# sont pas des fixtures (gros fichiers, données vivantes) : une archive zip exportée du dev et
# importée en prod, mêmes noms (MAN-2026-0004, EMB-2026-0002…), fichiers rattachés compris.

DOCTYPES_TRAVAIL = ("Manuel Article", "Design Emballage")
_CHAMPS_ENFANT_IGNORES = ("name", "owner", "creation", "modified", "modified_by", "parent", "parentfield", "parenttype", "docstatus", "doctype")
_CHAMPS_DOC_IGNORES = ("owner", "creation", "modified", "modified_by", "docstatus", "_user_tags", "_comments", "_assign", "_liked_by")


def _doc_exportable(doc) -> dict:
	"""Le document et ses lignes, sans identifiants ni horodatages (le nom est gardé à part). Pur."""
	d = doc.as_dict() if hasattr(doc, "as_dict") else dict(doc)
	out = {"doctype": d["doctype"], "name": d["name"]}
	for k, v in d.items():
		if k in _CHAMPS_DOC_IGNORES or k in ("doctype", "name"):
			continue
		if isinstance(v, list):
			out[k] = [{ck: cv for ck, cv in (l if isinstance(l, dict) else l.as_dict()).items() if ck not in _CHAMPS_ENFANT_IGNORES} for l in v]
		else:
			out[k] = v
	return out


# ─── un design, tel qu'il est sur le dev, vers un site qui en a une version plus ancienne ─────────────────────
#
# Demande du 13/11/2026 : « quand je pousse en prod, je veux l'équivalent de mon document du dev, pour l'emballage
# du sel seulement ». `exporter_design` (en dev) range dans l'app les champs de la fiche et les fichiers qu'elle
# utilise et que l'autre site n'a pas ; un patch appelle `appliquer_design` après la migration.

DESIGN = "Design Emballage"
DOSSIER_DESIGNS = os.path.join(DOSSIER, "designs")
_URL_FICHIER = re.compile(r'/(?:private/)?files/[^"\\<>]+')


def urls_fichiers(document) -> list[str]:
	"""Les fichiers du site que cite un document, où que ce soit (champ, JSON de mise en page…). Pur."""
	return sorted(set(_URL_FICHIER.findall(json.dumps(document, ensure_ascii=False, default=str))))


def memes_valeurs(a, b) -> bool:
	"""Deux valeurs de champ égales, à la façon de les écrire près (None et vide, 1 et 1.0, date et texte). Pur."""
	if a in (None, "") or b in (None, ""):
		return a in (None, "") and b in (None, "")
	if isinstance(a, bool | int | float) and isinstance(b, bool | int | float):
		return float(a) == float(b)
	return str(a) == str(b)


def decision_design(copie: dict, sur_place: str | None, forcer: bool = False) -> str:
	"""Que faire de la copie d'un design sur ce site ? Pur.

	- `introuvable` : le design n'existe pas ici, rien n'est créé ;
	- `deja_a_jour` : la fiche est déjà celle de la copie (le dev lui-même, ou un second passage) ;
	- `modifie_sur_place` : la fiche a changé ici depuis que le dev l'a copiée — on n'écrase pas ce travail ;
	- `appliquer` : la fiche est restée telle que le dev l'avait prise (ou `forcer`)."""
	if sur_place is None:
		return "introuvable"
	if _instant(sur_place) == _instant(copie.get("modifie")):
		return "deja_a_jour"
	if _instant(sur_place) != _instant(copie.get("base_modifie")) and not forcer:
		return "modifie_sur_place"
	return "appliquer"


def _instant(valeur):
	"""Un horodatage comparable quelle que soit son écriture (« …08:00:00 » et « …08:00:00.000000 »). Pur."""
	from datetime import datetime

	try:
		return datetime.fromisoformat(str(valeur))
	except ValueError:
		return str(valeur)


def _fiche_copie(nom: str, dossier: str | None = None) -> str:
	return os.path.join(dossier or DOSSIER_DESIGNS, nom, "design.json")


def exporter_design(nom: str, base_modifie: str, depuis: str, en_plus=None, dossier: str | None = None) -> dict:
	"""Range dans l'app l'état actuel d'un design : ses champs (les tables ne voyagent pas) et, parmi les
	fichiers qu'il cite, ceux apparus sur ce site depuis `depuis` — l'autre site a déjà les précédents.
	`base_modifie` : le « modifié le » de la fiche sur l'autre site, tel qu'il était quand ce site l'a copiée.
	`en_plus` : d'autres fichiers du design à emporter (un dessin de départ, par exemple)."""
	doc = frappe.get_doc(DESIGN, nom)
	champs = {k: v for k, v in _doc_exportable(doc).items() if k not in ("doctype", "name") and not isinstance(v, list)}
	cible = os.path.join(dossier or DOSSIER_DESIGNS, nom)
	if os.path.isdir(cible):
		shutil.rmtree(cible)
	os.makedirs(os.path.join(cible, "fichiers"))
	fichiers, poids = [], 0
	for url in sorted(set(urls_fichiers(champs)) | set(en_plus or [])):
		fiches = frappe.get_all("File", filters={"file_url": url, "attached_to_doctype": DESIGN, "attached_to_name": nom},
		                        fields=["file_name", "is_private", "attached_to_field", "creation"], order_by="creation asc")
		if not fiches or (str(fiches[0].creation) < depuis and url not in (en_plus or [])):
			continue
		src = _chemin_site(url)
		if not os.path.exists(src):
			frappe.throw(f"Fichier absent du disque : {url}")
		fichier = os.path.basename(url)
		shutil.copyfile(src, os.path.join(cible, "fichiers", fichier))
		poids += os.path.getsize(src)
		fichiers.append({"fichier": fichier, "url": url, "prive": int(fiches[0].is_private or 0), "champ": fiches[0].attached_to_field})
	copie = {"doctype": DESIGN, "name": nom, "base_modifie": str(base_modifie), "modifie": str(doc.modified), "champs": champs, "fichiers": fichiers}
	with open(_fiche_copie(nom, dossier), "w", encoding="utf-8") as f:
		json.dump(copie, f, ensure_ascii=False, indent=1, sort_keys=True, default=str)
		f.write("\n")
	return {"design": nom, "modifie": copie["modifie"], "champs": len(champs), "fichiers": [x["fichier"] for x in fichiers], "mo": round(poids / 1048576, 2)}


def etat_copie_design(nom: str, dossier: str | None = None) -> dict:
	"""La copie rangée dans l'app est-elle encore celle de la fiche de ce site ? À regarder avant de pousser :
	un design retouché après l'export part en prod dans son état de l'export."""
	if not os.path.exists(_fiche_copie(nom, dossier)):
		return {"copie": None, "a_jour": False}
	with open(_fiche_copie(nom, dossier), encoding="utf-8") as f:
		copie = json.load(f)
	sur_place = frappe.db.get_value(DESIGN, nom, "modified")
	return {"copie": copie["modifie"], "site": str(sur_place) if sur_place else None, "a_jour": bool(sur_place) and _instant(sur_place) == _instant(copie["modifie"])}


def appliquer_design(nom: str, dossier: str | None = None, forcer: int = 0) -> dict:
	"""Amène la fiche d'un design à l'état de sa copie : fichiers posés (jamais écrasés) avec leur fiche File,
	champs différents réécrits, « modifié le » repris de la copie. Ne crée pas le design, n'écrit rien si la
	fiche a changé sur place depuis la copie (sauf `forcer`). -> {etat, champs, fichiers}."""
	if not os.path.exists(_fiche_copie(nom, dossier)):
		return {"etat": "sans_copie"}
	with open(_fiche_copie(nom, dossier), encoding="utf-8") as f:
		copie = json.load(f)
	sur_place = frappe.db.get_value(DESIGN, nom, "modified") if frappe.db.exists(DESIGN, nom) else None
	etat = decision_design(copie, str(sur_place) if sur_place else None, bool(int(forcer or 0)))
	if etat != "appliquer":
		return {"etat": etat, "sur_place": str(sur_place) if sur_place else None}
	poses = 0
	for e in copie["fichiers"]:
		src, dest = os.path.join(os.path.dirname(_fiche_copie(nom, dossier)), "fichiers", e["fichier"]), _chemin_site(e["url"])
		if not os.path.exists(src):
			frappe.throw(f"Fichier absent de la copie du design : {e['fichier']}")
		if not os.path.exists(dest):
			os.makedirs(os.path.dirname(dest), exist_ok=True)
			shutil.copyfile(src, dest)
			poses += 1
		if not frappe.db.exists("File", {"file_url": e["url"], "attached_to_doctype": DESIGN, "attached_to_name": nom}):
			fiche_fichier_existant({"file_name": e["fichier"], "file_url": e["url"], "is_private": e["prive"],
			                        "attached_to_doctype": DESIGN, "attached_to_name": nom, "attached_to_field": e.get("champ")})
	meta, actuel = frappe.get_meta(DESIGN), frappe.db.get_value(DESIGN, nom, "*", as_dict=True)
	valeurs = {k: v for k, v in copie["champs"].items() if meta.has_field(k) and not memes_valeurs(actuel.get(k), v)}
	frappe.db.set_value(DESIGN, nom, dict(valeurs, modified=copie["modifie"]), update_modified=False)
	frappe.clear_document_cache(DESIGN, nom)
	frappe.get_doc(DESIGN, nom).add_comment("Info", "Fiche mise à jour depuis la copie rangée dans l’app (état du %s)." % copie["modifie"][:16])
	return {"etat": "applique", "champs": sorted(valeurs), "fichiers": poses}


# ------------------------------------------------------------------ un dossier produit emporté comme exemple
# Demande 16/11/2026 : « la version actuelle d'AP-M, je veux qu'elle soit patchée pour que, lorsque je pousse en
# prod, elle soit poussée comme exemple pour mes employés ». Le dossier (présentation, variantes, photos) et la
# dernière version française de chaque document, avec son PDF, sont rangés dans `contenu/dossiers/<clé>/` ; un patch
# les recrée sur l'autre site. Les autres versions, les fiches par variante et les traductions ne voyagent pas.

DOSSIER_PRODUIT, DOCUMENT_PRODUIT = "Dossier Produit", "Document Produit"
DOSSIER_EXEMPLES = os.path.join(DOSSIER, "dossiers")
_CHAMPS_DOSSIER = ("entete", "marque_document", "logo_marque_avec_entete", "consignes", "connaissances_generales",
                   "categories_caracteristiques", "mises_en_page", "plans")
_TABLES_DOSSIER = {"variantes": ("article",), "sources": ("fichier", "pages", "article"), "images": ("image", "legende", "article")}
_CHAMPS_JSON = ("mises_en_page", "plans")
_PIECES = (("pdf", ".pdf"), ("source_latex", ".tex"))   # l'archive LaTeX (aussi lourde que le PDF) se refait sur place


def _fiche_dossier(cle: str, dossier: str | None = None) -> str:
	return os.path.join(dossier or DOSSIER_EXEMPLES, cle, "dossier.json")


def lignes_a_ajouter(existantes: list[dict], copie: list[dict], cle: str) -> list[dict]:
	"""Les lignes de la copie absentes d'une table (comparées sur `cle`), dans l'ordre de la copie, sans doublon. Pur."""
	vues, ajouts = {r.get(cle) for r in existantes}, []
	for r in copie:
		if r.get(cle) and r[cle] not in vues:
			vues.add(r[cle])
			ajouts.append(dict(r))
	return ajouts


def copie_comparable(copie: dict) -> dict:
	"""Ce qui, dans une copie de dossier, dit si elle est encore celle du site (pas la date de l'export). Pur."""
	return {k: copie.get(k) for k in ("article", "dossier", "marque", "documents", "fichiers")}


def _copie_dossier(nom: str, depuis: str) -> tuple[dict, list[tuple[str, str]]]:
	"""(la copie, les fichiers à ranger [(chemin sur le site, nom dans la copie)]) d'un dossier de ce site."""
	from aquaworld_ia.documents_produit import marques

	d = frappe.get_doc(DOSSIER_PRODUIT, nom)
	cle = d.article
	champs = {}
	for k in _CHAMPS_DOSSIER:
		v = d.get(k)
		champs[k] = (json.loads(v) if v else {}) if k in _CHAMPS_JSON else (v if v not in (None, "") else (0 if d.meta.get_field(k).fieldtype == "Check" else ""))
	for table, cles in _TABLES_DOSSIER.items():
		champs[table] = [{c: r.get(c) or "" for c in cles} for r in d.get(table)]
	documents, a_ranger = [], []
	for genre, court in (("Fiche technique", "fiche"), ("Manuel d'utilisation", "manuel")):
		versions = frappe.get_all(DOCUMENT_PRODUIT, filters={"dossier": nom, "type_document": genre, "langue": "fr", "variante": ["is", "not set"]},
		                          fields=["name"], order_by="numero desc, creation desc", limit=1)
		if not versions:
			continue
		v = frappe.get_doc(DOCUMENT_PRODUIT, versions[0].name)
		doc = {"origine": v.name, "type_document": v.type_document, "langue": v.langue, "libelle_langue": v.libelle_langue, "rtl": int(v.rtl or 0),
		       "numero": int(v.numero), "statut": v.statut, "contenu": json.loads(v.contenu_json), "contexte": json.loads(v.contexte_json)}
		for champ, extension in _PIECES:
			if v.get(champ):
				src = _chemin_site(v.get(champ))
				if not os.path.exists(src):
					frappe.throw(f"Fichier absent du disque : {v.get(champ)}")
				doc[champ] = f"{court}-{v.langue}{extension}"
				doc[champ + "_origine"] = v.get(champ)
				a_ranger.append((src, doc[champ]))
		documents.append(doc)
	marque = marques.effective(d)
	logo = frappe.db.get_value("Brand", marque, "image") if marque else None
	# Parmi les fichiers cités, ceux apparus sur ce site depuis `depuis` : l'autre site a déjà les précédents.
	fichiers = []
	for url in urls_fichiers({"dossier": champs, "documents": [{"contenu": x["contenu"], "contexte": x["contexte"]} for x in documents], "logo": logo}):
		fiches = frappe.get_all("File", filters={"file_url": url}, fields=["file_name", "is_private", "creation"], order_by="creation asc")
		if not fiches or str(fiches[0].creation) < depuis:
			continue
		src = _chemin_site(url)
		if not os.path.exists(src):
			frappe.throw(f"Fichier absent du disque : {url}")
		fichiers.append({"fichier": os.path.basename(url), "url": url, "prive": int(fiches[0].is_private or 0)})
		a_ranger.append((src, os.path.basename(url)))
	if len({n for _, n in a_ranger}) != len(a_ranger):
		frappe.throw("Deux fichiers de ce dossier portent le même nom : la copie ne peut pas les ranger côte à côte.")
	copie = {"article": cle, "depuis": str(depuis), "exporte_de": {"dossier": nom, "modifie": str(d.modified)}, "dossier": champs,
	         "marque": {"name": marque, "image": logo} if marque and logo and any(f["url"] == logo for f in fichiers) else None,
	         "documents": documents, "fichiers": fichiers}
	return json.loads(json.dumps(copie, ensure_ascii=False, default=str)), a_ranger


def exporter_dossier(nom: str, depuis: str, dossier: str | None = None) -> dict:
	"""Range dans l'app l'état actuel d'un dossier produit : sa présentation, ses variantes, ses photos, et la
	dernière version française de la fiche et du manuel du produit avec son PDF. `depuis` : la date de la copie de
	l'autre site vers celui-ci (« 2026-11-11 ») — parmi les fichiers cités, seuls ceux apparus depuis voyagent, les
	photos des articles y sont déjà. La copie porte la référence de l'article, pas le nom du dossier."""
	copie, a_ranger = _copie_dossier(nom, depuis)
	cible = os.path.join(dossier or DOSSIER_EXEMPLES, copie["article"])
	if os.path.isdir(cible):
		shutil.rmtree(cible)
	os.makedirs(os.path.join(cible, "fichiers"))
	poids = 0
	for src, fichier in a_ranger:
		shutil.copyfile(src, os.path.join(cible, "fichiers", fichier))
		poids += os.path.getsize(src)
	with open(_fiche_dossier(copie["article"], dossier), "w", encoding="utf-8") as f:
		json.dump(copie, f, ensure_ascii=False, indent=1, sort_keys=True)
		f.write("\n")
	return {"cle": copie["article"], "dossier": nom, "documents": [f"{x['origine']} ({x['type_document']} v{x['numero']}, {x['statut']})" for x in copie["documents"]],
	        "fichiers": [n for _, n in a_ranger], "mo": round(poids / 1048576, 2)}


def etat_copie_dossier(cle: str, dossier: str | None = None) -> dict:
	"""La copie rangée dans l'app est-elle encore l'état du dossier de ce site ? À regarder avant de pousser : un
	dossier retouché, ou une version plus récente, part dans son état de l'export — relancer `exporter_dossier`."""
	if not os.path.exists(_fiche_dossier(cle, dossier)):
		return {"copie": None, "a_jour": False}
	with open(_fiche_dossier(cle, dossier), encoding="utf-8") as f:
		copie = json.load(f)
	nom = frappe.db.get_value(DOSSIER_PRODUIT, {"article": copie["article"]}, "name")
	if not nom:
		return {"copie": [x["origine"] for x in copie["documents"]], "site": None, "a_jour": False}
	actuelle = _copie_dossier(nom, copie["depuis"])[0]
	differences = [k for k, v in copie_comparable(copie).items() if v != copie_comparable(actuelle)[k]]
	return {"copie": [x["origine"] for x in copie["documents"]], "site": [x["origine"] for x in actuelle["documents"]],
	        "a_jour": not differences, "differences": differences}


def appliquer_dossier(cle: str, dossier: str | None = None) -> dict:
	"""Recrée sur ce site le dossier produit rangé dans l'app, comme exemple : fichiers posés (jamais écrasés) avec
	leur fiche File, logo de la marque s'il manque, dossier créé — ou complété s'il existe déjà pour cet article :
	sa présentation devient celle de la copie, ses variantes et photos sont gardées —, puis chaque version ajoutée
	à la suite avec son PDF. Rien n'est écrit si l'article n'existe pas ici, ou si ces versions y sont déjà (le dev
	lui-même, un second passage). Ne valide pas la transaction. -> {etat, dossier, documents, remarques}."""
	if not os.path.exists(_fiche_dossier(cle, dossier)):
		return {"etat": "sans_copie"}
	with open(_fiche_dossier(cle, dossier), encoding="utf-8") as f:
		copie = json.load(f)
	from frappe.utils.file_manager import save_file

	from aquaworld_ia.documents_produit import service as API
	from aquaworld_ia.documents_produit import structure as S
	from aquaworld_ia.documents_produit.entetes import instantane

	racine, article = os.path.join(os.path.dirname(_fiche_dossier(cle, dossier)), "fichiers"), copie["article"]
	a = frappe.db.get_value("Item", article, ["disabled", "variant_of"], as_dict=True)
	if not a or a.disabled or a.variant_of:
		return {"etat": "article_absent", "article": article}
	nom = frappe.db.get_value(DOSSIER_PRODUIT, {"article": article}, "name")
	deja = set()
	if nom:
		deja = {S.empreinte(json.loads(c)) for c in frappe.get_all(DOCUMENT_PRODUIT, filters={"dossier": nom}, pluck="contenu_json")}
	manquants = [x for x in copie["documents"] if S.empreinte(S.normaliser(x["contenu"], x["contexte"])) not in deja]
	if nom and not manquants:
		return {"etat": "deja_present", "dossier": nom}
	remarques = []

	# 1. Les fichiers apparus sur le site d'origine, à leur adresse, avec leur fiche File (rattachée plus bas).
	for e in copie["fichiers"]:
		src, dest = os.path.join(racine, e["fichier"]), _chemin_site(e["url"])
		if not os.path.exists(src):
			frappe.throw(f"Fichier absent de la copie du dossier : {e['fichier']}")
		if not os.path.exists(dest):
			os.makedirs(os.path.dirname(dest), exist_ok=True)
			shutil.copyfile(src, dest)
		if not frappe.db.exists("File", {"file_url": e["url"]}):
			fiche_fichier_existant({"file_name": e["fichier"], "file_url": e["url"], "is_private": e["prive"]})

	# 2. Le logo de la marque, lu sur la fiche Brand à chaque composition : posé seulement s'il n'y en a pas.
	marque = copie.get("marque")
	if marque and frappe.db.exists("Brand", marque["name"]):
		actuel = frappe.db.get_value("Brand", marque["name"], "image")
		if not actuel:
			frappe.db.set_value("Brand", marque["name"], "image", marque["image"])
			frappe.clear_document_cache("Brand", marque["name"])
			remarques.append(f"logo posé sur la marque {marque['name']}")
		elif actuel != marque["image"]:
			remarques.append(f"la marque {marque['name']} a déjà un autre logo ({actuel}) : gardé")

	# 3. Le dossier.
	champs = copie["dossier"]
	entete = champs.get("entete") or ""
	if entete:
		try:
			instantane(entete)
		except Exception:
			remarques.append(f"en-tête « {entete} » absent ou inutilisable ici : dossier laissé sans en-tête")
			entete = ""
	d = frappe.get_doc(DOSSIER_PRODUIT, nom) if nom else frappe.new_doc(DOSSIER_PRODUIT)
	avant = d.get("mises_en_page") if nom else None
	d.article = article
	for k in _CHAMPS_DOSSIER:
		if not d.meta.has_field(k):
			continue
		v = entete if k == "entete" else champs.get(k)
		d.set(k, (json.dumps(v, ensure_ascii=False) if v else "") if k in _CHAMPS_JSON else v)
	actives = set(frappe.get_all("Item", filters={"variant_of": article, "disabled": 0}, pluck="name"))
	ecartees = [r["article"] for r in champs.get("variantes", []) if r["article"] not in actives]
	if ecartees:
		remarques.append(f"{len(ecartees)} variante(s) absente(s) ou désactivée(s) ici, non reprise(s) : " + ", ".join(ecartees[:10]))
	for r in lignes_a_ajouter([x.as_dict() for x in d.variantes], [r for r in champs.get("variantes", []) if r["article"] in actives], "article"):
		d.append("variantes", r)
	retenues = {r.article for r in d.variantes}
	for table, colonne in (("sources", "fichier"), ("images", "image")):
		for r in lignes_a_ajouter([x.as_dict() for x in d.get(table)], champs.get(table, []), colonne):
			if not frappe.db.exists("File", {"file_url": r[colonne]}):
				remarques.append(f"fichier absent ici, non repris : {r[colonne]}")
			elif r.get("article") and r["article"] not in retenues:
				remarques.append(f"fichier d’une variante non reprise, laissé : {r[colonne]}")
			else:
				d.append(table, r)
	d.save() if nom else d.insert()
	if nom and avant and avant != d.get("mises_en_page"):
		d.add_comment("Info", "Mise en page remplacée par celle du dossier d’exemple. Ancienne : " + avant)
	for e in copie["fichiers"]:
		for f in frappe.get_all("File", filters={"file_url": e["url"], "attached_to_name": ["is", "not set"]}, pluck="name"):
			frappe.db.set_value("File", f, {"attached_to_doctype": DOSSIER_PRODUIT, "attached_to_name": d.name}, update_modified=False)

	# 4. Les versions, à la suite de celles du site, avec leur PDF.
	crees = []
	for x in manquants:
		v = API.nouvelle_version(d.name, x["type_document"], x["contenu"], x["contexte"], x["langue"], x["libelle_langue"], x["rtl"],
		                         numero_minimum=x["numero"])
		urls = {}
		for champ, extension in _PIECES:
			if x.get(champ):
				with open(os.path.join(racine, x[champ]), "rb") as f:
					urls[champ] = save_file(f"{v.name}-{v.langue}{extension}", f.read(), DOCUMENT_PRODUIT, v.name, is_private=1).file_url
		if urls:
			v.update(urls)
			if urls.get("pdf") and x["statut"] == "Validé":
				v.statut = "Validé"
			v.flags.document_produit_interne = True
			v.save()
		crees.append(f"{v.name} ({v.type_document} v{v.numero}, {v.statut})")
	d.add_comment("Info", "Dossier d’exemple apporté depuis la copie rangée dans l’application (" + ", ".join(crees) + ").")
	return {"etat": "applique", "dossier": d.name, "cree": not nom, "documents": crees, "remarques": remarques}


def design_a_cote(nom: str, dossier: str | None = None) -> dict:
	"""Le design du dev arrive À CÔTÉ de celui du site, sans y toucher (demande 16/11/2026 : en prod, la fiche
	EMB-2026-0006 avait été retravaillée et `appliquer_design` ne l'a donc pas écrasée — « je ne vois pas ce que
	j'ai fait en dev, je veux garder ça en prod comme historique »). Une copie de la fiche du site est créée par le
	chemin habituel (`studio.dupliquer` : langues, pictogrammes, variantes, fichiers rattachés), puis reçoit les
	champs et les fichiers de la copie du dev. Rien n'est créé si la fiche du site est déjà celle du dev, ou si ce
	design d'à-côté existe déjà. Ne valide pas la transaction. -> {etat, design?}"""
	if not os.path.exists(_fiche_copie(nom, dossier)):
		return {"etat": "sans_copie"}
	with open(_fiche_copie(nom, dossier), encoding="utf-8") as f:
		copie = json.load(f)
	if not frappe.db.exists(DESIGN, nom):
		return {"etat": "introuvable"}
	if _instant(frappe.db.get_value(DESIGN, nom, "modified")) == _instant(copie["modifie"]):
		return {"etat": "deja_a_jour"}
	champs, meta = copie["champs"], frappe.get_meta(DESIGN)
	# Déjà créé (second passage) : un autre design du même article porte le décor et le plan de la copie.
	reperes = {k: champs[k] for k in ("article", "fonds_faces", "plan_a_plat") if champs.get(k) and meta.has_field(k)}
	deja = frappe.db.get_value(DESIGN, {**reperes, "name": ["!=", nom]}, "name") if len(reperes) == 3 else None
	if deja:
		return {"etat": "deja_cree", "design": deja}
	from aquaworld_ia.emballage import studio

	nouveau = studio.dupliquer(nom)["name"]
	racine = os.path.join(os.path.dirname(_fiche_copie(nom, dossier)), "fichiers")
	for e in copie["fichiers"]:
		src, dest = os.path.join(racine, e["fichier"]), _chemin_site(e["url"])
		if not os.path.exists(src):
			frappe.throw(f"Fichier absent de la copie du design : {e['fichier']}")
		if not os.path.exists(dest):
			os.makedirs(os.path.dirname(dest), exist_ok=True)
			shutil.copyfile(src, dest)
	valeurs = {k: v for k, v in champs.items() if meta.has_field(k) and k != "idx"}
	frappe.db.set_value(DESIGN, nouveau, valeurs)
	frappe.clear_document_cache(DESIGN, nouveau)
	# Chaque fichier que cite le nouveau design lui est rattaché par sa propre fiche File : il reste lisible
	# même si l'autre design est supprimé, et l'onglet Images le reconnaît.
	manquants = []
	for url in urls_fichiers(valeurs):
		if not os.path.exists(_chemin_site(url)):
			manquants.append(url)
		elif not frappe.db.exists("File", {"file_url": url, "attached_to_doctype": DESIGN, "attached_to_name": nouveau}):
			fiche_fichier_existant({"file_name": os.path.basename(url), "file_url": url, "is_private": int(url.startswith("/private/")),
			                        "attached_to_doctype": DESIGN, "attached_to_name": nouveau})
	etat_dev = copie["modifie"][:16]
	frappe.get_doc(DESIGN, nouveau).add_comment("Info", f"Design apporté du site de développement (état du {etat_dev}), créé à côté de {nom}, qui n’a pas été modifié.")
	frappe.get_doc(DESIGN, nom).add_comment("Info", f"La version de ce design faite sur le site de développement (état du {etat_dev}) a été créée à côté : {nouveau}. Cette fiche n’a pas été modifiée.")
	return {"etat": "cree", "design": nouveau, "fichiers_absents": manquants}


def numero_serie(nom: str):
	"""(préfixe, numéro) d'un nom de série « MAN-2026-0004 » → ("MAN-2026-", 4) ; None sinon. Pur."""
	import re

	m = re.fullmatch(r"(.*?)(\d+)", nom or "")
	return (m.group(1), int(m.group(2))) if m else None


def exporter_travail(chemin: str, noms=None, doctypes=None) -> dict:
	"""Écrit `chemin` (zip) : docs.json (manuels et designs, `noms` pour n'en prendre que certains)
	+ files/ (tout fichier rattaché à ces documents) + files.json (leurs fiches File)."""
	import json as _json
	import zipfile

	noms = set(noms or [])
	doctypes = doctypes or DOCTYPES_TRAVAIL
	docs, fiches, poids = [], [], 0
	with zipfile.ZipFile(chemin, "w", zipfile.ZIP_DEFLATED) as z:
		deja = set()
		for dt in doctypes:
			for nom in frappe.get_all(dt, pluck="name", order_by="name"):
				if noms and nom not in noms:
					continue
				docs.append(_doc_exportable(frappe.get_doc(dt, nom)))
				for f in frappe.get_all("File", filters={"attached_to_doctype": dt, "attached_to_name": nom, "is_folder": 0},
				                        fields=["file_name", "file_url", "is_private", "attached_to_doctype", "attached_to_name", "attached_to_field"]):
					if not f.file_url or not f.file_url.startswith(("/files/", "/private/files/")):
						continue
					src = _chemin_site(f.file_url)
					if not os.path.exists(src):
						continue
					arc = "files/" + f.file_url.lstrip("/")
					if arc not in deja:
						z.write(src, arc)
						deja.add(arc)
						poids += os.path.getsize(src)
					fiches.append(dict(f))
		z.writestr("docs.json", _json.dumps(docs, ensure_ascii=False, default=str))
		z.writestr("files.json", _json.dumps(fiches, ensure_ascii=False, default=str))
	return {"documents": len(docs), "fichiers": len(deja), "mo": round(poids / 1048576, 1), "chemin": chemin}


def importer_travail(chemin: str, remplacer: int = 0) -> dict:
	"""Lit une archive d'`exporter_travail` : crée les documents qui n'existent pas (mêmes noms),
	ou les remplace si `remplacer` ; pose les fichiers manquants et leurs fiches File ; aligne les
	compteurs de série pour que les prochains numéros ne heurtent pas ceux importés."""
	import json as _json
	import zipfile

	crees, sautes, fichiers = [], [], 0
	with zipfile.ZipFile(chemin) as z:
		docs = _json.loads(z.read("docs.json"))
		fiches = _json.loads(z.read("files.json"))
		for d in docs:
			dt, nom = d["doctype"], d["name"]
			if frappe.db.exists(dt, nom):
				if not int(remplacer or 0):
					sautes.append(nom)
					continue
				frappe.delete_doc(dt, nom, force=True, ignore_permissions=True)
			doc = frappe.get_doc(d)
			doc.flags.ignore_permissions = True
			doc.flags.ignore_links = True
			doc.insert(set_name=nom)
			crees.append(nom)
		for f in fiches:
			if f["attached_to_name"] in sautes:
				continue
			arc = "files/" + f["file_url"].lstrip("/")
			dest = _chemin_site(f["file_url"])
			if not os.path.exists(dest) and arc in z.namelist():
				os.makedirs(os.path.dirname(dest), exist_ok=True)
				with z.open(arc) as src, open(dest, "wb") as out:
					shutil.copyfileobj(src, out)
				fichiers += 1
			if not frappe.db.exists("File", {"file_url": f["file_url"], "attached_to_name": f["attached_to_name"]}):
				fiche_fichier_existant({"file_name": f["file_name"], "file_url": f["file_url"], "is_private": f.get("is_private") or 0,
				                        "attached_to_doctype": f["attached_to_doctype"], "attached_to_name": f["attached_to_name"],
				                        "attached_to_field": f.get("attached_to_field")})
	aligner_series(crees)
	frappe.db.commit()
	return {"crees": crees, "sautes": sautes, "fichiers": fichiers}


def aligner_series(noms) -> dict:
	"""Le compteur `tabSeries` de chaque préfixe monte au plus grand numéro importé : sans ça, le
	prochain manuel créé en prod reprendrait un numéro déjà pris."""
	maxima = {}
	for nom in noms:
		ns = numero_serie(nom)
		if ns:
			maxima[ns[0]] = max(maxima.get(ns[0], 0), ns[1])
	for prefixe, n in maxima.items():
		actuel = frappe.db.get_value("Series", prefixe, "current", order_by=None) or 0
		if n > actuel:
			if actuel == 0 and not frappe.db.exists("Series", prefixe):
				frappe.db.sql("INSERT INTO `tabSeries` (name, current) VALUES (%s, %s)", (prefixe, n))
			else:
				frappe.db.sql("UPDATE `tabSeries` SET current = %s WHERE name = %s", (n, prefixe))
	return maxima


# ------------------------------------------------------------------ réparation des copies suffixées
_DOUBLE = re.compile(r"^(.*?)([0-9a-f]{6})\2(\.[A-Za-z0-9]+)$")


def url_d_origine(file_url: str, content_hash: str | None) -> str | None:
	"""« /private/files/X09a60909a609.png » (empreinte 09a609 en double) -> « /private/files/X09a609.png » :
	la copie qu'un ancien import a fabriquée, et le nom d'origine que le document emploie. None si l'URL
	n'est pas une telle copie. Pur."""
	m = _DOUBLE.match(file_url or "")
	if not m or not content_hash or not content_hash.endswith(m.group(2)):
		return None
	return m.group(1) + m.group(2) + m.group(3)


def reparer_fichiers_doubles(appliquer: int = 1) -> dict:
	"""Les fiches File qui pointent une copie suffixée (voir `fiche_fichier_existant`) reprennent le nom
	d'origine — même contenu, déjà sur le disque, et c'est lui que les documents emploient — puis la
	copie devenue orpheline est effacée. Idempotent. `appliquer=0` : ne fait que compter."""
	from frappe.core.doctype.file.utils import get_content_hash

	# Seulement ce que l'app a transféré : ses documents de travail, ses fixtures, et les fichiers de design /
	# manuel restés sans rattachement. Les autres modules ne passent pas par cet import : on n'y touche pas.
	doctypes = list(DOCTYPES_TRAVAIL) + list(CHAMPS_FICHIERS)
	fiches = frappe.db.sql("""select name, file_url, content_hash from `tabFile`
		where is_folder = 0 and file_url regexp '[0-9a-f]{6}[0-9a-f]{6}[.][A-Za-z0-9]+$'
		  and (attached_to_doctype in %(doctypes)s
		       or (ifnull(attached_to_doctype, '') = '' and (file_name like 'EMB-%%' or file_name like 'MAN-%%')))""",
		{"doctypes": doctypes}, as_dict=True)
	reparees, copies = [], set()
	for f in fiches:
		origine = url_d_origine(f.file_url, f.content_hash)
		if not origine:
			continue
		chemin = _chemin_site(origine)
		if not os.path.exists(chemin):
			continue
		with open(chemin, "rb") as fh:
			if get_content_hash(fh.read()) != f.content_hash:
				continue                                  # même nom, autre contenu : on n'y touche pas
		reparees.append(f.name)
		copies.add(f.file_url)
		if int(appliquer):
			frappe.db.set_value("File", f.name, {"file_url": origine, "file_name": origine.rsplit("/", 1)[-1]}, update_modified=False)
	effacees = 0
	if int(appliquer):
		for url in copies:
			chemin = _chemin_site(url)
			if not frappe.db.exists("File", {"file_url": url}) and os.path.exists(chemin):
				os.remove(chemin)
				effacees += 1
		frappe.db.commit()
	return {"fiches": len(reparees), "copies": len(copies), "copies_effacees": effacees}

