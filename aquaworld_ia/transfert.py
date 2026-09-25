"""Le contenu de référence qui voyage avec l'app (demande utilisateur 25/09/2026 : « une fixture qui
amène sa base actuelle en prod ») : les fichiers rattachés aux fixtures (images de pictogrammes,
polices, fonds et logos de la bibliothèque) et les Réglages sans secret.

- `exporter()` (en dev, avant de pousser) : copie ces fichiers dans `fixtures/fichiers/` avec un
  manifeste, et écrit `fixtures/reglages.json`. Se lance avec `bench export-fixtures` via le hook
  `export_fixtures`… ou à la main : `bench --site <site> execute aquaworld_ia.transfert.exporter`.
- `restaurer()` (après migration, partout) : recrée les fiches File manquantes et pose les fichiers
  sur le site ; applique les Réglages ; donne le rôle « Aquaworld IA » aux utilisateurs listés.
Les documents de travail (manuels, designs) ne sont PAS des fixtures : voir `exporter_travail`.
"""

from __future__ import annotations

import json
import os
import shutil

import frappe

DOSSIER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
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
			frappe.get_doc({
				"doctype": "File", "file_name": e["fichier"], "file_url": e["url"], "is_private": 1 if e["prive"] else 0,
				"attached_to_doctype": e["doctype"] if rattache else None, "attached_to_name": e["name"] if rattache else None,
				"attached_to_field": e["champ"] if rattache else None,
			}).insert(ignore_permissions=True)
	return poses


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
