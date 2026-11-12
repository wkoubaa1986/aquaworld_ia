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


def retenir_initiales(candidates, maximum=20):
	"""Les lignes « images » d'un nouveau dossier, dans l'ordre des candidates ({image, legende, article, hash}) :
	une même image (même adresse ou même contenu) n'entre qu'une fois, `maximum` au plus (la limite d'un
	dossier). PURE."""
	lignes, vues = [], set()
	for c in candidates:
		cles = {c["image"], c.get("hash") or c["image"]}
		if cles & vues or len(lignes) >= maximum:
			continue
		vues |= cles
		lignes.append({"image": c["image"], "legende": c.get("legende") or "", "article": c.get("article") or ""})
	return lignes


def initiales(parent, article):
	"""Les photos d'un dossier à sa création (demande 12/11/2026 : « s'il y a plusieurs images du produit, pourquoi
	elles ne viennent pas automatiquement dans la fiche ? ») : la photo de la variante d'où part le dossier, puis
	l'image de l'article parent et ses pièces jointes image. La première est la photo principale ; les suivantes
	vont au bloc « Autres illustrations ». Les photos des autres variantes restent à choisir (« Choisir les photos
	des articles ») : chaque fiche de variante prend déjà les siennes."""
	candidates = []

	def proposer(url, legende, portee):
		if not url or PurePosixPath(url.lower()).suffix not in EXTENSIONS:
			return
		try:
			f = C.fichier_lisible(url, silencieux=True)
		except (frappe.PermissionError, frappe.ValidationError, frappe.DoesNotExistError):
			return
		candidates.append({"image": f.file_url, "legende": legende, "article": portee, "hash": f.content_hash})

	if article.variant_of:
		proposer(article.image, article.item_name, article.name)
	for photo in disponibles(frappe._dict(article=parent.name, name=""), []):
		if photo["origine"] == parent.name:
			proposer(photo["image"], photo["legende"], "")
	return retenir_initiales(candidates)


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
