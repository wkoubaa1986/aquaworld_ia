"""Photos proposées à partir des liens réels entre fichiers, articles et variantes."""

from pathlib import PurePosixPath

import frappe

from aquaworld_ia.documents_produit import contexte as C

EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".svg"}


def disponibles(dossier, variantes):
	if not isinstance(variantes, list) or len(variantes) > 250 or any(not isinstance(a, str) for a in variantes):
		raise ValueError("Choisissez au maximum 250 variantes.")
	articles = [C.article_lisible(dossier.article)]
	for nom in dict.fromkeys(variantes):
		a = C.article_lisible(nom)
		if a.variant_of != dossier.article or a.disabled:
			raise ValueError("Choisissez les variantes actives de cet article.")
		articles.append(a)
	resultat, vus = [], set()

	def ajouter(url, nom, article, origine, principale=False):
		cle = (url, article)
		if not url or cle in vus or PurePosixPath(url.lower()).suffix not in EXTENSIONS:
			return
		try:
			f = C.fichier_lisible(url, silencieux=True)
		except (frappe.PermissionError, frappe.ValidationError, frappe.DoesNotExistError):
			return
		vus.add(cle)
		resultat.append({"image": f.file_url, "nom": f.file_name, "article": article,
			"legende": nom if principale else PurePosixPath(f.file_name).stem,
			"origine": origine, "principale_article": bool(principale)})

	for a in articles:
		portee = "" if a.name == dossier.article else a.name
		ajouter(a.image, a.item_name, portee, a.name, principale=True)
		for f in frappe.get_all("File", filters={"attached_to_doctype": "Item", "attached_to_name": a.name, "is_folder": 0},
			fields=["file_url", "file_name"], order_by="creation, name"):
			ajouter(f.file_url, f.file_name, portee, a.name)
	for f in frappe.get_all("File", filters={"attached_to_doctype": C.DOSSIER, "attached_to_name": dossier.name, "is_folder": 0},
		fields=["file_url", "file_name"], order_by="creation, name"):
		ajouter(f.file_url, f.file_name, "", "Dossier")
	return resultat


def legendes(contenu, ancien, nouveau):
	"""Conserve les corrections/traductions des vues conservées, même après réordonnancement."""
	restants = list(enumerate(ancien.get("images", [])))
	resultat = []
	for im in nouveau.get("images", []):
		legende = im.get("legende", "")
		for position, (index, avant) in enumerate(restants):
			if (avant["image"], avant.get("article", "")) == (im["image"], im.get("article", "")):
				if avant.get("legende", "") == legende:
					legende = contenu["legendes"][index]
				restants.pop(position)
				break
		resultat.append(legende)
	return {**contenu, "legendes": resultat}
