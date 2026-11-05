"""En-têtes ERPNext réutilisables, figés par version et rendus sans réseau ni scripts."""

from __future__ import annotations

import copy
import hashlib
import io
import re

import frappe
from bs4 import BeautifulSoup, Comment

from aquaworld_ia.documents_produit import contexte as C

BALISES = set("div p span strong b em i u br table thead tbody tr td th h1 h2 h3 h4 h5 h6 img ul ol li small".split())
STYLES = set("color background-color font-size font-weight font-style text-align vertical-align width height max-width border border-top border-bottom border-left border-right border-collapse padding padding-top padding-bottom padding-left padding-right margin margin-top margin-bottom line-height".split())


def disponibles():
	modeles = frappe.get_list("Letter Head", filters={"disabled": 0}, fields=["name", "source", "image"], order_by="name", limit_page_length=500)
	return [frappe._dict(name=m.name, a_completer=bool(m.source == "Image" and (not m.image or not frappe.db.exists("File", {"file_url": m.image})))) for m in modeles]


def _ressource(url, ressources):
	if not url.startswith(("/files/", "/private/files/")):
		raise ValueError("Ajoutez les images de l’en-tête aux fichiers ERPNext ; les images distantes ne sont pas prises en charge.")
	if url not in ressources:
		if len(ressources) >= 10:
			raise ValueError("Un en-tête peut contenir au maximum 10 images.")
		try:
			f = C.fichier_lisible(url, silencieux=True)
		except frappe.PermissionError:
			raise frappe.PermissionError("Une image de cet en-tête est absente ou inaccessible. Ouvrez le modèle pour joindre une image accessible.")
		b = C.octets(url)
		ressources[url] = {
			"fichier": f.file_url,
			"sha256": hashlib.sha256(b).hexdigest(),
			"nom": f"asset-{len(ressources)}.png",
		}
	return ressources[url]["nom"]


def nettoyer_html(html, ressources):
	"""Ne conserve que le texte, la mise en page et des images locales autorisées."""
	if len(html or "") > 60000:
		raise ValueError("Cet en-tête HTML est trop long. Utilisez une image de bannière.")
	soup = BeautifulSoup(html or "", "html.parser")
	for tag in soup.find_all(["script", "style", "iframe", "object", "embed", "svg", "link", "meta", "base"]):
		tag.decompose()
	for commentaire in soup.find_all(string=lambda x: isinstance(x, Comment)):
		commentaire.extract()
	for tag in list(soup.find_all(True)):
		if tag.name not in BALISES:
			tag.unwrap()
			continue
		attrs = {}
		if tag.name == "img":
			url = str(tag.get("src") or "")
			if not url:
				tag.decompose()
				continue
			attrs["src"] = _ressource(url, ressources)
		for k in ("width", "height", "colspan", "rowspan"):
			v = str(tag.get(k) or "")
			if re.fullmatch(r"\d{1,4}%?", v):
				attrs[k] = v
		if tag.get("dir") in ("ltr", "rtl"):
			attrs["dir"] = tag["dir"]
		styles = []
		for declaration in str(tag.get("style") or "").split(";"):
			cle, sep, valeur = declaration.partition(":")
			cle, valeur = cle.strip().lower(), valeur.strip()
			if (sep and cle in STYLES and re.fullmatch(r"[a-zA-Z0-9#(),.%\s-]+", valeur)
				and not re.search(r"url|expression", valeur, re.I)):
				styles.append(cle + ":" + valeur)
		if styles:
			attrs["style"] = ";".join(styles)
		tag.attrs = attrs
	if len(ressources) > 10:
		raise ValueError("Un en-tête peut contenir au maximum 10 images.")
	return str(soup)


def instantane(name, autoriser_desactive=False):
	if not name:
		return None
	d = frappe.get_doc("Letter Head", name)
	d.check_permission("read")
	if d.disabled and not autoriser_desactive:
		raise ValueError("Cet en-tête est désactivé. Choisissez un autre modèle.")
	ressources = {}
	snapshot = {"nom": d.name}
	for cle, source, image, contenu, align, largeur, hauteur in (
		("haut", d.source, d.image, d.content, d.align, d.image_width, d.image_height),
		("bas", d.footer_source, d.footer_image, d.footer, d.footer_align, d.footer_image_width, d.footer_image_height),
	):
		if source == "Image" and image:
			snapshot[cle] = {"image": _ressource(image, ressources), "align": align or "Center", "largeur_px": largeur or 0, "hauteur_px": hauteur or 0}
		elif source != "Image" and contenu:
			html = nettoyer_html(contenu, ressources)
			if BeautifulSoup(html, "html.parser").get_text(strip=True) or "<img" in html:
				snapshot[cle] = {"html": html}
	if not snapshot.get("haut") and not autoriser_desactive:
		raise ValueError("Cet en-tête est vide. Ajoutez une image ou du texte dans sa fiche.")
	snapshot["ressources"] = list(ressources.values())
	return snapshot


def contexte_avec_entete(ctx, snapshot):
	ctx = copy.deepcopy(ctx)
	if snapshot:
		ctx["entete"] = snapshot
	else:
		ctx.pop("entete", None)
	return ctx


def rendre(snapshot):
	"""Retourne les bandeaux PNG et leurs dimensions imprimées (mm)."""
	import pymupdf
	from PIL import Image

	from aquaworld_ia.documents_produit.latex import image_png

	if not snapshot:
		return {}
	fichiers = {}
	for r in snapshot.get("ressources", []):
		b = C.octets(r["fichier"])
		if hashlib.sha256(b).hexdigest() != r["sha256"]:
			raise ValueError("Une image de l’en-tête a changé. Réappliquez l’en-tête du dossier.")
		fichiers[r["nom"]] = image_png(b)
	archive = pymupdf.Archive()
	for nom, b in fichiers.items():
		archive.add((b, nom))
	resultat = {}
	for cle, hauteur_max in (("haut", 35), ("bas", 18)):
		partie = snapshot.get(cle)
		if not partie:
			continue
		if partie.get("image"):
			png = fichiers[partie["image"]]
			with Image.open(io.BytesIO(png)) as im:
				echelle = min(174 / im.width, hauteur_max / im.height)
				w, h = partie.get("largeur_px", 0), partie.get("hauteur_px", 0)
				if max(w, h) > 0:
					echelle = min(echelle, (w / im.width if w > h else h / im.height) * 25.4 / 96)
				largeur, hauteur = im.width * echelle, im.height * echelle
		else:
			with pymupdf.open() as pdf:
				pt = 72 / 25.4
				page = pdf.new_page(width=174 * pt, height=hauteur_max * pt)
				reste, _ = page.insert_htmlbox(
					page.rect, partie["html"],
					css="body {font-family: sans-serif; font-size: 9pt; margin: 0;} p {margin: 0;} img {max-width: 100%;}",
					archive=archive, scale_low=0.6,
				)
				if reste < 0:
					raise ValueError("L’en-tête ou son pied de page est trop haut. Réduisez son contenu.")
				hauteur_pt = max(1, page.rect.height - reste)
				png = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), clip=pymupdf.Rect(0, 0, page.rect.width, hauteur_pt), alpha=True).tobytes("png")
				largeur, hauteur = 174, hauteur_pt / pt
		resultat[cle] = {"png": png, "largeur": round(largeur, 2), "hauteur": round(hauteur, 2), "align": partie.get("align", "Center")}
	return resultat
