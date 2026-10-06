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

