"""Impression en aplats : un décor ramené à quelques couleurs d’impression, en tracés SVG.

Un sac imprimé en flexographie reçoit un cliché par couleur : une photo, même vectorisée, ne se
sépare pas. Ici chaque pixel rejoint la couleur d’impression la plus proche (ou le blanc du support),
puis chaque couleur est tracée seule : un groupe SVG par couleur, trous compris. Les couleurs
s’empilent de la plus claire à la plus foncée ; chacune glisse un peu sous sa voisine plus foncée,
sans jour blanc entre les deux.
"""
from __future__ import annotations

import io
import json
from xml.etree import ElementTree as ET

import frappe
from frappe import _
from frappe.utils import cint

MAX_ENCRES = 4
BLANC = "#ffffff"
#: Par finesse : filtre majoritaire (px), taches ignorées par le traceur (px), liserés retirés (px).
LISSAGES = {"fin": (3, 4, 3), "normal": (5, 8, 5), "fort": (9, 16, 7)}
#: Recouvrement (px) d’une couleur sous sa voisine plus foncée : pas de jour blanc entre deux couleurs.
RECOUVREMENT = 5
#: Distance RVB au-delà de laquelle un pixel n’est proche d’aucune couleur d’impression.
ECART_NUANCE = 60
PART_NUANCES_PHOTO = 0.25
SVG_NS = "http://www.w3.org/2000/svg"


def encres(valeur) -> list[str]:
	"""« #0264C3, 5badf0 » ou une liste -> ["#0264c3", "#5badf0"]. Le blanc est le support : ignoré. Pur."""
	import re

	from aquaworld_ia.emballage.logo_couleur import normaliser

	if isinstance(valeur, str):
		texte = valeur.strip()
		if texte.startswith("["):
			valeur = json.loads(texte)
		else:
			valeur = [v for v in re.split(r"[\s,;]+", texte) if v]
	out = []
	for brut in valeur or []:
		couleur = normaliser(brut)
		if not couleur:
			raise ValueError("Couleur d’impression invalide : « %s ». Utilisez un code HEX comme #0264c3." % brut)
		if couleur != BLANC and couleur not in out:
			out.append(couleur)
	if not out:
		raise ValueError("Indiquez au moins une couleur d’impression (code HEX), en plus du blanc du support.")
	if len(out) > MAX_ENCRES:
		raise ValueError("%d couleurs d’impression au maximum." % MAX_ENCRES)
	return out


def _rvb(couleur: str) -> tuple[int, int, int]:
	return tuple(int(couleur[i:i + 2], 16) for i in (1, 3, 5))


def _luminance(couleur: str) -> float:
	r, g, b = _rvb(couleur)
	return 0.2126 * r + 0.7152 * g + 0.0722 * b


def plus_proche(couleur: str, liste: list[str]) -> str:
	"""La couleur d’impression (ou le blanc) la plus proche d’une couleur donnée. Pur."""
	c = _rvb(couleur)
	return min([BLANC] + list(liste), key=lambda e: sum((a - b) ** 2 for a, b in zip(c, _rvb(e))))


def _ouvrir(octets: bytes):
	"""PNG/JPEG/WebP ou SVG -> image RGBA de 1 600 px au plus, et sa taille d’origine."""
	from PIL import Image

	from aquaworld_ia.emballage import vectorisation as V
	from aquaworld_ia.emballage.composition import est_svg

	if len(octets) > V.MAX_OCTETS:
		raise ValueError("Image trop lourde : maximum 20 Mo.")
	if est_svg(octets):
		import pymupdf

		from aquaworld_ia.emballage.svg_impression import vers_pdf

		with vers_pdf(octets) as pdf:
			page = pdf[0]
			if min(page.rect.width, page.rect.height) <= 0:
				raise ValueError("SVG vide ou sans dimensions.")
			zoom = V.MAX_COTE / max(page.rect.width, page.rect.height)
			pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=True)
			im = Image.frombytes("RGBA", (pix.width, pix.height), pix.samples)
		return im, im.size
	im = V.ouvrir(octets)
	taille = im.size
	im.thumbnail((V.MAX_COTE, V.MAX_COTE), Image.Resampling.LANCZOS)
	return im, taille


def separer(im, liste: list[str]):
	"""Image RGBA -> (indices, part de nuances, distances) : 0 = blanc du support, k = k-ième couleur de `liste`.
	La part de nuances mesure, hors blanc, les pixels qui ne ressemblent à aucune couleur : élevée sur une photo."""
	import numpy as np

	pixels = np.asarray(im.convert("RGBA"), dtype=np.int32)
	rvb, alpha = pixels[..., :3], pixels[..., 3]
	# Un pixel transparent laisse voir le support.
	rvb = np.where(alpha[..., None] >= 128, rvb, 255)
	palette = np.array([_rvb(BLANC)] + [_rvb(c) for c in liste], dtype=np.int32)
	distances = ((rvb[:, :, None, :] - palette[None, None, :, :]) ** 2).sum(axis=3)
	indices = distances.argmin(axis=2).astype(np.uint8)
	# Les nuances se mesurent sur ce qui n’est pas le blanc du support : un grand fond blanc ne les dilue pas.
	hors_blanc = distances[..., 0] > ECART_NUANCE ** 2
	douteux = distances.min(axis=2) > ECART_NUANCE ** 2
	return indices, float(douteux.sum() / max(1, hors_blanc.sum())), distances


def _morpho(masque, taille: int, dilater: bool):
	import numpy as np
	from PIL import Image, ImageFilter

	im = Image.fromarray(np.where(masque, 255, 0).astype(np.uint8), "L")
	return np.asarray(im.filter(ImageFilter.MaxFilter(taille) if dilater else ImageFilter.MinFilter(taille))) > 0


def retirer_liseres(indices, distances, ordre: list[int], epaisseur: int):
	"""Le bord adouci d’une forme foncée passe par des teintes proches d’une couleur plus claire : sans
	correction, chaque forme foncée porterait un liseré clair. Ces bandes fines collées à une couleur plus
	foncée sont rendues au blanc ou à la couleur foncée, selon leur teinte. `ordre` : du clair au foncé."""
	import numpy as np

	for rang, k in enumerate(ordre[:-1]):
		plus_fonces = [j + 1 for j in ordre[rang + 1:]]
		propre, fonce = indices == k + 1, np.isin(indices, plus_fonces)
		if not propre.any() or not fonce.any():
			continue
		fin = propre & ~_morpho(_morpho(propre, epaisseur, False), epaisseur, True)
		lisere = fin & _morpho(fonce, epaisseur, True)
		if lisere.any():
			candidats = np.array([0] + plus_fonces, dtype=np.uint8)
			indices = np.where(lisere, candidats[distances[..., candidats].argmin(axis=2)], indices)
	return indices


def _tracer(masque, taches: int) -> list[tuple[str, str]]:
	"""Un masque booléen -> les chemins (d, transform) de ses formes, trous compris."""
	import numpy as np
	import vtracer
	from PIL import Image

	gris = np.where(masque, 0, 255).astype(np.uint8)
	b = io.BytesIO()
	Image.fromarray(gris, "L").convert("RGBA").save(b, "PNG")
	svg = vtracer.convert_raw_image_to_svg(
		b.getvalue(), img_format="png", colormode="binary", mode="spline", filter_speckle=taches,
		corner_threshold=60, length_threshold=4.0, splice_threshold=45, path_precision=2)
	return [(p.get("d"), p.get("transform") or "") for p in ET.fromstring(svg).iter("{%s}path" % SVG_NS) if p.get("d")]


def vectoriser(octets: bytes, couleurs, lissage: str = "normal") -> tuple[bytes, dict]:
	"""Image -> SVG aux seules couleurs d’impression, et son bilan. Sans appel IA."""
	import numpy as np
	from PIL import Image, ImageFilter

	from aquaworld_ia.emballage import vectorisation as V

	liste = encres(couleurs)
	if lissage not in LISSAGES:
		raise ValueError("Choisissez un lissage fin, normal ou fort.")
	filtre, taches, epaisseur = LISSAGES[lissage]
	im, (largeur, hauteur) = _ouvrir(octets)
	indices, nuances, distances = separer(im, liste)
	# Du plus clair au plus foncé : l’ordre d’empilement des couleurs.
	ordre = sorted(range(len(liste)), key=lambda k: -_luminance(liste[k]))
	indices = retirer_liseres(indices, distances, ordre, epaisseur)
	# Le filtre majoritaire retire les pixels isolés et adoucit les contours.
	indices = np.asarray(Image.fromarray(indices, "L").filter(ImageFilter.ModeFilter(filtre)))
	racine = ET.Element("{%s}svg" % SVG_NS, {"viewBox": "0 0 %d %d" % im.size, "width": str(largeur), "height": str(hauteur)})
	total, chemins, avertissements, couverture = indices.size, 0, [], {}
	for rang, k in enumerate(ordre):
		couleur = liste[k]
		part = float((indices == k + 1).mean())
		couverture[couleur] = round(part * 100, 1)
		if not part:
			avertissements.append("La couleur %s n’apparaît pas dans le résultat." % couleur)
			continue
		# Chaque couleur garde ses formes visibles et glisse un peu sous ses voisines plus foncées.
		propre = indices == k + 1
		masque = propre | (_morpho(propre, RECOUVREMENT, True) & np.isin(indices, [j + 1 for j in ordre[rang + 1:]]))
		traces = _tracer(masque, taches)
		if not traces:
			avertissements.append("La couleur %s ne forme que des taches trop petites : elle est absente du tracé." % couleur)
			continue
		groupe = ET.SubElement(racine, "{%s}g" % SVG_NS, {"id": "encre-%d-%s" % (rang + 1, couleur[1:]), "fill": couleur})
		for d, transform in traces:
			attributs = {"d": d, "fill": couleur}
			if transform:
				attributs["transform"] = transform
			ET.SubElement(groupe, "{%s}path" % SVG_NS, attributs)
		chemins += len(traces)
	if not chemins:
		raise ValueError("Aucune forme aux couleurs d’impression. Vérifiez les couleurs ou choisissez une autre image.")
	ET.register_namespace("", SVG_NS)
	resultat = ET.tostring(racine, encoding="utf-8")
	if chemins > V.MAX_CHEMINS or len(resultat) > V.MAX_SVG:
		raise ValueError("Tracé trop complexe. Essayez un lissage plus fort ou une image plus simple.")
	if nuances > PART_NUANCES_PHOTO:
		avertissements.append("L’image de départ contient beaucoup de nuances (photo ou dégradés) : le tracé est "
			"approximatif. Faites-la d’abord redessiner en aplats.")
	return resultat, {
		"largeur": largeur, "hauteur": hauteur, "chemins": chemins, "encres": liste, "couverture": couverture,
		"blanc": round(float((indices == 0).mean()) * 100, 1), "nuances": round(nuances * 100, 1),
		"taille_ko": round(len(resultat) / 1024, 1), "pixels": total, "avertissements": avertissements,
	}


def prompt(couleurs, produit: str = "", consigne: str = "") -> str:
	"""La consigne de redessin en aplats envoyée à l’IA, avec l’image de départ en référence. Pur."""
	liste = encres(couleurs)
	texte = (
		"Redraw the reference image as a FLAT spot-colour illustration for flexographic printing on white packaging. "
		"Use EXACTLY %d solid ink colour%s and nothing else: %s, on a PURE WHITE (#FFFFFF) background. "
		"Every shape is one solid flat fill of one of these inks: no gradients, no soft shadows, no glow, no transparency, "
		"no texture, no photographic rendering, no blended or intermediate colours. "
		"Bold simple shapes with crisp clean edges; no tiny details and no hairlines. "
		"Keep the composition of the reference: the same elements at the same places and proportions. "
		"White objects are drawn as white shapes defined by an ink outline and one flat ink shadow. "
		"No text, no lettering, no logo, no watermark, no frame."
	) % (len(liste), "" if len(liste) == 1 else "s", ", ".join(c.upper() for c in liste))
	if (produit or "").strip():
		texte += " The product shown is: %s." % produit.strip()[:120]
	if (consigne or "").strip():
		texte += " Additional request: %s." % consigne.strip()[:600].rstrip(".")
	return texte


# ─── studio ──────────────────────────────────────────────────────────────────

def _face(doc, face: str):
	from aquaworld_ia.emballage import geometrie
	from aquaworld_ia.emballage.variantes import plan_du_design

	f = geometrie.face(plan_du_design(doc), face)
	if not f or not f.get("imprimable"):
		frappe.throw(_("Face inconnue ou non imprimable : {0}").format(face))
	return f


def source_face(doc, face: str, source_url: str | None = None) -> str:
	"""L’image de départ : celle choisie, sinon l’image de la face, sinon l’image de fond du design."""
	from aquaworld_ia.emballage.ressources import image_lisible

	fonds = frappe.parse_json(doc.fonds_faces) if doc.get("fonds_faces") else {}
	reg = fonds.get(face) if isinstance(fonds.get(face), dict) else {}
	url = source_url or reg.get("image") or doc.get("image_fond")
	if not url:
		frappe.throw(_("Choisissez d’abord l’image à passer en aplats."))
	return image_lisible(doc, url)


def _encres_ou_erreur(couleurs) -> list[str]:
	try:
		return encres(couleurs)
	except ValueError as exc:
		frappe.throw(str(exc))


def _memoriser(doc, liste: list[str]) -> None:
	valeur = ", ".join(liste)
	if (doc.get("encres_impression") or "") != valeur:
		frappe.db.set_value("Design Emballage", doc.name, "encres_impression", valeur, update_modified=False)


def _candidat(doc, face: str, octets: bytes, liste: list[str], lissage: str) -> dict:
	from frappe.utils.file_manager import save_file

	try:
		svg, infos = vectoriser(octets, liste, lissage)
	except ValueError as exc:
		frappe.throw(str(exc))
	fichier = save_file("%s-aplats-%s.svg" % (doc.name, face), svg, "Design Emballage", doc.name, is_private=1)
	return dict(infos, url=fichier.file_url)


@frappe.whitelist()
def vectoriser_face(design: str, face: str, couleurs, lissage: str = "normal", source_url: str | None = None) -> dict:
	"""L’image de la face ramenée aux couleurs d’impression : un candidat SVG à comparer avant adoption.
	Aucun appel IA."""
	from aquaworld_ia.emballage.studio import images_du_design
	from aquaworld_ia.ia import fichiers

	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("write")
	_face(doc, face)
	liste = _encres_ou_erreur(couleurs)
	source = source_face(doc, face, source_url)
	candidat = _candidat(doc, face, fichiers.lire(source), liste, lissage)
	_memoriser(doc, liste)
	return {"face": face, "source": source, "encres": liste, "candidats": [candidat], "images": images_du_design(doc)}


@frappe.whitelist()
def redessiner_face(design: str, face: str, couleurs, consigne: str | None = None, nombre=1, lissage: str = "normal",
                    source_url: str | None = None) -> dict:
	"""L’IA redessine l’image de la face en aplats aux couleurs d’impression, puis chaque proposition est
	tracée en SVG. Une image facturée par proposition."""
	from aquaworld_ia.emballage import geometrie
	from aquaworld_ia.emballage.studio import images_du_design
	from aquaworld_ia.ia import couts, fichiers, images, journal
	from aquaworld_ia.ia.client import qualite_image, reglages
	from frappe.utils.file_manager import save_file

	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("write")
	f = _face(doc, face)
	liste = _encres_ou_erreur(couleurs)
	texte = prompt(liste, doc.nom_produit or doc.article or "", consigne or "")
	if lissage not in LISSAGES:
		frappe.throw(_("Choisissez un lissage fin, normal ou fort."))
	source = source_face(doc, face, source_url)
	n = max(1, min(4, cint(nombre) or 1))
	qualite = qualite_image()
	journal.verifier_plafond(couts.cout_variantes(n, qualite, couts.tarifs_depuis_reglages(reglages())))
	pngs = images.editer(texte, [("image", fichiers.lire(source))], taille=geometrie.taille_image_pour(f), qualite=qualite,
	                     n=n, fonctionnalite="Emballage faces", doc=doc, fidelite="high")
	_memoriser(doc, liste)
	candidats = []
	for png in pngs:
		dessin = save_file("%s-aplats-ia-%s.png" % (doc.name, face), png, "Design Emballage", doc.name, is_private=1).file_url
		candidats.append(dict(_candidat(doc, face, png, liste, lissage), dessin=dessin))
	return {"face": face, "source": source, "encres": liste, "candidats": candidats, "images": images_du_design(doc)}


# ─── contrôle des couleurs du PDF ────────────────────────────────────────────

#: Écart RVB toléré entre une couleur du PDF et une couleur d’impression (arrondis d’écriture).
TOLERANCE = 10


def _hex(rvb) -> str:
	return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(v * 255)))) for v in rvb[:3])


def _admise(couleur: str, liste: list[str]) -> bool:
	c = _rvb(couleur)
	return any(sum((a - b) ** 2 for a, b in zip(c, _rvb(e))) <= TOLERANCE ** 2 for e in [BLANC] + list(liste))


def _sans_surface(items) -> bool:
	"""Un tracé fait de segments isolés (les modules d’un QR dessinés au trait) ne remplit rien."""
	if not items or any(it[0] != "l" for it in items):
		return False
	aire, debut, precedent, somme = 0.0, None, None, 0.0
	for _type, a, b in items:
		if precedent is None or abs(a.x - precedent.x) > 1e-6 or abs(a.y - precedent.y) > 1e-6:
			aire += abs(somme + ((precedent.x * debut.y - debut.x * precedent.y) if precedent is not None else 0)) / 2
			debut, somme = a, 0.0
		somme += a.x * b.y - b.x * a.y
		precedent = b
	aire += abs(somme + (precedent.x * debut.y - debut.x * precedent.y)) / 2
	return aire < 1e-3


def controle_pdf(pdf: bytes, couleurs) -> dict:
	"""Ce que la page imprimable contient hors des couleurs d’impression : images en pixels, tracés et
	textes d’une autre couleur. Le calque de découpe et la fiche technique ne s’impriment pas : ignorés."""
	import pymupdf

	from aquaworld_ia.emballage.composition import COUCHE_DECOUPE

	liste = encres(couleurs)
	ecarts: dict[str, dict] = {}

	def noter(couleur: str, texte: str | None = None):
		if _admise(couleur, liste):
			return
		e = ecarts.setdefault(couleur, {"couleur": couleur, "proche": plus_proche(couleur, liste), "traces": 0, "textes": []})
		if texte is None:
			e["traces"] += 1
		elif texte not in e["textes"]:
			e["textes"].append(texte)

	with pymupdf.open("pdf", pdf) as document:
		page = document[0]
		pixels = len(page.get_image_info())
		for trace in page.get_drawings():
			if trace.get("layer") == COUCHE_DECOUPE:
				continue
			if trace.get("fill") and trace.get("fill_opacity", 1) > 0 and not _sans_surface(trace.get("items")):
				noter(_hex(trace["fill"]))
			if trace.get("color") and trace.get("stroke_opacity", 1) > 0 and (trace.get("width") or 0) > 0:
				noter(_hex(trace["color"]))
		for span in page.get_texttrace():
			texte = "".join(chr(c[0]) for c in span.get("chars") or []).strip()
			if span.get("layer") == COUCHE_DECOUPE or not texte or not span.get("opacity", 1):
				continue
			couleur = span.get("color") or (0, 0, 0)
			# Une icône isolée (téléphone, repère) compte comme un tracé : son caractère ne dit rien à lire.
			noter(_hex(couleur if isinstance(couleur, (tuple, list)) else (couleur,) * 3), texte[:60] if len(texte) > 1 else None)
	liste_ecarts = sorted(ecarts.values(), key=lambda e: -(e["traces"] + len(e["textes"])))
	return {"encres": liste, "pixels": pixels, "ecarts": liste_ecarts, "conforme": not pixels and not liste_ecarts}


@frappe.whitelist()
def controler(design: str) -> dict:
	"""Contrôle le PDF imprimeur actuel contre les couleurs d’impression du design."""
	from aquaworld_ia.emballage import exports
	from aquaworld_ia.ia import fichiers

	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("read")
	liste = _encres_ou_erreur(doc.get("encres_impression"))
	if not doc.get("plan_a_plat"):
		frappe.throw(_("Créez d’abord le PDF imprimeur."))
	try:
		pdf = fichiers.lire(doc.plan_a_plat)
	except Exception:
		frappe.throw(_("Le PDF imprimeur est introuvable : actualisez-le, puis relancez le contrôle."))
	return dict(controle_pdf(pdf, liste), a_jour=exports.etat(doc)["pdf"] == "a_jour")


def aligner(doc, liste: list[str]) -> list[dict]:
	"""Ramène à la couleur d’impression la plus proche les couleurs CHOISIES dans le design : textes et
	cartouches des zones, aplats de fond, QR. Modifie `doc` en mémoire ; -> [{quoi, avant, apres}]."""
	from aquaworld_ia.emballage import codes
	from aquaworld_ia.emballage.logo_couleur import normaliser

	changements = []

	def cible(valeur, quoi):
		couleur = normaliser(valeur)
		if not couleur or _admise(couleur, liste):
			return valeur
		nouvelle = plus_proche(couleur, liste)
		changements.append({"quoi": quoi, "avant": couleur, "apres": nouvelle})
		return nouvelle

	mep = frappe.parse_json(doc.mise_en_page) if doc.get("mise_en_page") else None
	if isinstance(mep, dict):
		for face, zones in mep.items():
			for zone in zones if isinstance(zones, list) else []:
				style = zone.get("style") if isinstance(zone, dict) else None
				if isinstance(style, dict):
					for cle, nom in (("texte", "texte"), ("fond", "cartouche")):
						if style.get(cle):
							style[cle] = cible(style[cle], "%s · %s (%s)" % (face, zone.get("zone"), nom))
		doc.mise_en_page = json.dumps(mep, ensure_ascii=False)
	fonds = frappe.parse_json(doc.fonds_faces) if doc.get("fonds_faces") else None
	if isinstance(fonds, dict):
		for face, reg in fonds.items():
			if isinstance(reg, dict) and reg.get("mode") == "couleur" and reg.get("couleur"):
				reg["couleur"] = cible(reg["couleur"], "%s · fond" % face)
		doc.fonds_faces = json.dumps(fonds, ensure_ascii=False)
	if doc.get("couleur_fond"):
		doc.couleur_fond = cible(doc.couleur_fond, "couleur de fond")
	if doc.get("type_code_barres") in ("QR", "EAN-13 + QR"):
		actuelle = codes.couleur_qr(doc.get("couleur_qr"))
		if not _admise(actuelle, liste):
			# Un QR doit rester lisible : la couleur d’impression la plus proche parmi les assez foncées.
			lisibles = [c for c in liste if codes.contraste_sur_blanc(c) >= codes.CONTRASTE_QR_MIN]
			if lisibles:
				proche = plus_proche(actuelle, lisibles)
				nouvelle = proche if proche != BLANC else min(lisibles, key=_luminance)
				changements.append({"quoi": "QR", "avant": actuelle, "apres": nouvelle})
				doc.couleur_qr = nouvelle
	return changements


@frappe.whitelist()
def aligner_couleurs(design: str) -> dict:
	"""« Aligner les couleurs » : les couleurs choisies dans le design rejoignent les couleurs d’impression.
	Le logo, les pictogrammes et les images ne sont pas touchés. Le PDF est à actualiser ensuite."""
	from aquaworld_ia.emballage.studio import charger

	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("write")
	changements = aligner(doc, _encres_ou_erreur(doc.get("encres_impression")))
	if changements:
		doc.save()
	return dict(charger(design, catalogues=0), changements=changements)
