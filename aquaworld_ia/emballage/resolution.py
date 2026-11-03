"""Résolution des images : candidats comparables et préparation fidèle du PDF.

Le PDF est inspecté APRÈS composition : les matrices comprennent le zoom, les
rotations, les fenêtres SVG et les faces copiées. Seuls ses XObjects image sont
remplacés ; le texte, les tracés, les masques de découpe et les calques restent.
"""
from __future__ import annotations

import io
import json
import math
import base64
from pathlib import Path

import frappe
from PIL import Image, ImageOps

CIBLE_PPP = 300
MAX_PIXELS = 40_000_000
MAX_PIXELS_PDF = 120_000_000
MAX_OCTETS = 40_000_000


def ouvrir_image(octets):
	from aquaworld_ia.emballage.composition import est_svg
	if len(octets) > MAX_OCTETS:
		raise ValueError("Image trop volumineuse (40 Mo maximum).")
	if est_svg(octets):
		raise ValueError("Un SVG vectoriel n’a pas besoin d’agrandissement. Les images intégrées seront contrôlées dans le PDF.")
	try:
		with Image.open(io.BytesIO(octets)) as im:
			if im.width * im.height > MAX_PIXELS:
				raise ValueError("Image trop grande (40 millions de pixels maximum).")
			return ImageOps.exif_transpose(im).convert("RGBA" if "A" in im.getbands() or "transparency" in im.info else "RGB")
	except (OSError, Image.DecompressionBombError) as exc:
		raise ValueError("Image illisible ou trop grande.") from exc


def _photo_ia(im, facteur):
	"""Tuiles bornées en mémoire ; alpha conservé et dématage sur les bords."""
	import cv2
	import numpy as np
	if not hasattr(cv2, "dnn_superres"):
		raise ValueError("La super-résolution locale nécessite opencv-contrib-python-headless sur le serveur.")
	sr = cv2.dnn_superres.DnnSuperResImpl_create()
	sr.readModel(str(Path(__file__).with_name("modeles_resolution") / f"FSRCNN_x{facteur}.pb"))
	sr.setModel("fsrcnn", facteur)
	alpha = im.getchannel("A") if im.mode == "RGBA" else None
	rgb = Image.new("RGB", im.size, "white")
	rgb.paste(im, mask=alpha)
	src = np.asarray(rgb)[:, :, ::-1].copy()
	w, h = im.size
	dest = Image.new("RGB", (w * facteur, h * facteur))
	# 16 px > rayon du champ réceptif FSRCNN : pas de joint entre les tuiles.
	for y in range(0, h, 192):
		for x in range(0, w, 192):
			x1, y1 = min(x + 192, w), min(y + 192, h)
			x0, y0, x2, y2 = max(0, x - 16), max(0, y - 16), min(w, x1 + 16), min(h, y1 + 16)
			out = sr.upsample(src[y0:y2, x0:x2])[:, :, ::-1]
			tile = Image.fromarray(out).crop(((x-x0)*facteur, (y-y0)*facteur, (x1-x0)*facteur, (y1-y0)*facteur))
			dest.paste(tile, (x*facteur, y*facteur))
	if alpha is not None:
		alpha = alpha.resize(dest.size, Image.Resampling.LANCZOS)
		# Dématage par bandes pour éviter plusieurs matrices float de 40 MP.
		for y in range(0, dest.height, 128):
			box = (0, y, dest.width, min(y+128, dest.height))
			a = np.asarray(alpha.crop(box), dtype=np.float32)[:, :, None] / 255
			color = np.asarray(dest.crop(box), dtype=np.float32)
			color = np.clip((color - 255*(1-a)) / np.maximum(a, 1/255), 0, 255).astype(np.uint8)
			dest.paste(Image.fromarray(color), (0, y))
		dest.putalpha(alpha)
	return dest


def agrandir(octets, facteur=2, methode="fidele"):
	if str(facteur) not in ("2", "4") or methode not in ("fidele", "ia"):
		raise ValueError("Choisissez ×2 ou ×4, en mode fidèle ou IA locale.")
	facteur = int(facteur)
	im = ouvrir_image(octets)
	w, h = im.size
	if w*h*facteur**2 > MAX_PIXELS:
		raise ValueError("Le résultat dépasserait 40 millions de pixels. Choisissez un facteur plus petit.")
	out = _photo_ia(im, facteur) if methode == "ia" else im.resize((w*facteur, h*facteur), Image.Resampling.LANCZOS)
	stream = io.BytesIO()
	out.save(stream, "PNG", dpi=(CIBLE_PPP, CIBLE_PPP))
	if stream.tell() > MAX_OCTETS:
		raise ValueError("Le résultat dépasse 40 Mo. Choisissez un facteur plus petit.")
	return stream.getvalue(), {"avant": [w, h], "apres": list(out.size), "facteur": facteur, "methode": methode}


def inventorier(pdf):
	"""Une entrée par image partagée, au plus faible PPP de toutes ses utilisations."""
	import pymupdf
	images = {}
	identites = {}
	for numero, page in enumerate(pdf):
		ressources = {}
		for res in page.get_images(full=True):
			xref = res[0]
			if xref not in identites:
				pix = pymupdf.Pixmap(pdf, xref)
				identites[xref] = (pix.digest, pix.width, pix.height)
			ressources.setdefault(identites[xref], set()).add(xref)
		for im in page.get_image_info(xrefs=True):
			xref = im["xref"]
			a, b, c, d, _e, _f = im["transform"]
			largeur, hauteur = math.hypot(a, b), math.hypot(c, d)
			if not largeur or not hauteur:
				continue
			ppp = min(im["width"]*72/largeur, im["height"]*72/hauteur)
			# Les images inline éventuelles sont signalées, jamais prétendues corrigées.
			identite = (im["digest"], im["width"], im["height"])
			cle = identite if xref else (numero, im["number"])
			if cle not in images:
				images[cle] = {"xref": xref, "page": numero, "avant": [im["width"], im["height"]],
				               "ppp_avant": ppp, "occurrences": 0, "xrefs": []}
			# MuPDF associe le digest à UN xref, même si plusieurs objets portent
			# ces pixels (formes imbriquées, faces liées). Tous doivent suivre.
			images[cle]["xrefs"] = sorted(set(images[cle]["xrefs"]) | ressources.get(identite, {xref} if xref else set()))
			images[cle]["ppp_avant"] = min(ppp, images[cle]["ppp_avant"])
			images[cle]["occurrences"] += 1
	return list(images.values())


def _pixels_pdf(pdf, xref):
	import pymupdf
	pix = pymupdf.Pixmap(pdf, xref)
	if pix.colorspace is None:
		return None
	if pix.colorspace.n not in (1, 3):
		pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
	kind, masque = pdf.xref_get_key(xref, "SMask")
	if kind == "xref":
		pix = pymupdf.Pixmap(pix, pymupdf.Pixmap(pdf, int(masque.split()[0])))
	return pix


def preparer_pdf(octets, progression=None):
	"""Agrandissement fidèle en lot, sans inventer de lettres ni changer un sceau."""
	import pymupdf
	rapport = {"cible_ppp": CIBLE_PPP, "methode": "fidele", "images": [], "ameliorees": 0, "insuffisantes": 0}
	budget = MAX_PIXELS_PDF
	with pymupdf.open(stream=octets, filetype="pdf") as pdf:
		inventaire = inventorier(pdf)
		for i, info in enumerate(inventaire):
			if progression:
				progression(i, len(inventaire))
			ppp = info["ppp_avant"]
			facteur = 1 if ppp >= CIBLE_PPP else 2 if ppp*2 >= CIBLE_PPP else 4
			pixels = math.prod(info["avant"])
			cout = pixels * max(1, len(info["xrefs"]))
			motif = ""
			while facteur > 1 and (pixels*facteur**2 > MAX_PIXELS or cout*facteur**2 > budget):
				facteur //= 2
				motif = "Limite de taille atteinte."
			if not info["xref"]:
				facteur, motif = 1, "Image intégrée non remplaçable."
			vignette = None
			if info["xref"]:
				pix = _pixels_pdf(pdf, info["xref"])
				if pix is None:
					facteur, motif = 1, "Masque monochrome conservé."
				else:
					# Une vignette permet de retrouver le composant dans le bilan.
					# Ne pas shrink() un Pixmap issu du PDF : MuPDF partage parfois
					# ses pixels avec le cache du document et rétrécirait la source.
					with Image.open(io.BytesIO(pix.tobytes("png"))) as petit:
						petit.thumbnail((128, 128))
						mini = io.BytesIO()
						petit.save(mini, "PNG")
					vignette = "data:image/png;base64," + base64.b64encode(mini.getvalue()).decode()
			if facteur > 1:
				for xref in info["xrefs"]:
					pix = _pixels_pdf(pdf, xref)
					if pix is None:
						raise ValueError("Masque monochrome non pris en charge pour l’agrandissement.")
					png, _ = agrandir(pix.tobytes("png"), facteur, "fidele")
					pdf[info["page"]].replace_image(xref, stream=png)
				budget -= cout*facteur**2
				rapport["ameliorees"] += 1
			ppp_apres = ppp*facteur
			if ppp_apres < CIBLE_PPP:
				rapport["insuffisantes"] += 1
				motif = motif or "Source plus définie nécessaire (agrandissement limité à ×4)."
			rapport["images"].append(dict(info, numero=i+1, facteur=facteur, vignette=vignette,
				apres=[v*facteur for v in info["avant"]], ppp_avant=round(ppp, 1), ppp_apres=round(ppp_apres, 1), motif=motif))
		return pdf.tobytes(garbage=3, deflate=True), rapport


def _source(doc, champ):
	from aquaworld_ia.emballage.variantes import url_logo, url_photo
	if champ not in ("logo", "photo_produit", "image_fond"):
		frappe.throw("Choisissez un logo, une photo ou une image de fond.")
	return url_logo(doc) if champ == "logo" else url_photo(doc) if champ == "photo_produit" else doc.get(champ)


@frappe.whitelist()
def ameliorer_image(design, champ, facteur=2, methode="fidele", source_url=None):
	from aquaworld_ia.emballage.ressources import image_lisible
	from aquaworld_ia.ia import fichiers
	from frappe.utils.file_manager import save_file
	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("write")
	source = _source(doc, champ)
	if source_url and source_url != source:
		frappe.throw("L’image a changé. Rouvrez l’outil d’amélioration.")
	try:
		png, infos = agrandir(fichiers.lire(image_lisible(doc, source)), facteur, methode)
	except ValueError as exc:
		frappe.throw(str(exc))
	fichier = save_file(f"{doc.name}-{champ}-resolution-x{facteur}.png", png, "Design Emballage", doc.name, is_private=1)
	return dict(infos, source=source, candidat=fichier.file_url, modifie_le=str(doc.modified))


@frappe.whitelist()
def adopter_image(design, champ, candidat, source, modifie_le):
	from aquaworld_ia.emballage import studio
	from aquaworld_ia.ia import fichiers
	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("write")
	if str(doc.modified) != modifie_le or _source(doc, champ) != source:
		frappe.throw("Le design a changé. Rouvrez l’outil ; le candidat reste dans la médiathèque.")
	if not frappe.db.exists("File", {"file_url": candidat, "attached_to_doctype": "Design Emballage", "attached_to_name": design}):
		frappe.throw("Le candidat n’appartient pas à ce design.")
	try:
		ouvrir_image(fichiers.lire(candidat))
	except ValueError as exc:
		frappe.throw(str(exc))
	# Pas de nouveau détourage : préserver exactement la transparence du candidat.
	if champ == "logo":
		mep = frappe.parse_json(doc.get("mise_en_page")) or {}
		for zones in mep.values():
			for zone in zones:
				centre = zone.get("centre_visuel")
				if zone.get("zone") == "logo" and not zone.get("logo") and centre and centre.get("source") == source:
					centre["source"] = candidat
		doc.mise_en_page = json.dumps(mep, ensure_ascii=False)
	doc.set(champ, candidat)
	doc.save()
	return studio.charger(design)


@frappe.whitelist()
def lancer_pdf(design):
	from aquaworld_ia.emballage import exports, job
	from aquaworld_ia.emballage.variantes import GENRE
	from aquaworld_ia.ia import etat
	doc = job._doc(design)
	job._verifier_libre(design)
	if exports.verifier(doc):
		frappe.throw(" ".join(exports.verifier(doc)))
	etat.demarrer(GENRE, design, tache="resolution_pdf", erreur=None, fin=None)
	try:
		frappe.enqueue("aquaworld_ia.emballage.resolution.exporter_pdf", queue="long", timeout=900,
			job_id=f"aqia-resolution-{design}", deduplicate=True, enqueue_after_commit=True,
			design=design, utilisateur=frappe.session.user, revision=str(doc.modified))
	except Exception:
		etat.terminer(GENRE, design, statut="echec", erreur="Impossible de lancer la préparation du PDF.")
		raise
	return etat.lire_etat(GENRE, design)


def exporter_pdf(design, utilisateur, revision):
	from aquaworld_ia.emballage import composition
	from aquaworld_ia.emballage.variantes import GENRE, EVENEMENT
	from aquaworld_ia.ia import etat
	frappe.set_user(utilisateur)
	try:
		doc = frappe.get_doc("Design Emballage", design)
		doc.check_permission("write")
		if str(doc.modified) != revision:
			raise ValueError("Le design a changé depuis le lancement. Relancez l’export.")
		etat.progresser(GENRE, design, "Composition et préparation des images du PDF…", 5, EVENEMENT, utilisateur)
		composition.composer_et_attacher(design, doc.variante_choisie)
		etat.terminer(GENRE, design)
	except Exception as exc:
		frappe.db.rollback()
		frappe.log_error(title="Préparation des images du PDF", message=frappe.get_traceback())
		etat.terminer(GENRE, design, statut="echec", erreur=str(exc))
