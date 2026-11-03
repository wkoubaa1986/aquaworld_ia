"""Étape 3 : le plan à plat imprimeur, à l'échelle, en PDF (PyMuPDF).

Page 1 « Artwork » : chaque face imprimable reçoit son visuel (IA) ou un aplat de la couleur
dominante de la face avant + bandeau ; par-dessus, en VECTORIEL : logo, textes par langue,
EAN-13 / QR, pictogrammes. Le fond perdu ne s'étend que sur les arêtes de COUPE (jamais dans un
pli : le panneau voisin y a son propre visuel). Un calque optionnel (OCG) porte coupes, plis et
limite de fond perdu. Page 2 : fiche technique.
"""

from __future__ import annotations

import html
import base64
import io
import re
import json
import math

import frappe
from frappe import _
from frappe.utils import cint, flt
from frappe.utils.file_manager import save_file

from aquaworld_ia.emballage import codes, geometrie, mise_en_forme, pictos
from aquaworld_ia.emballage.variantes import CHAMPS_FACES, plan_du_design, url_logo, url_photo
from aquaworld_ia.ia import fichiers
from aquaworld_ia.manuels import rendu
from aquaworld_ia.manuels.rendu import css_base, polices_archive

MM = geometrie.mm_vers_pt


# ------------------------------------------------------------------ pur : maquette d'une face


def maquette_face(face: dict, contenu: dict) -> list[dict]:
	"""Les zones (mm, coordonnées feuille) d'une face selon son rôle et ce qu'il y a à poser.
	`contenu` : {logo, nom, accroche, caracteristiques, avertissements, contact: bool,
	pictos: int, code_barres: (w, h) mm ou None}. Pur."""
	z = face["zone_sure"]
	x, y, w, h = z["x"], z["y"], z["w"], z["h"]
	zones = []
	code = face["code"]

	def zone(nom, zx, zy, zw, zh):
		if zw > 0.5 and zh > 0.5:
			zones.append({"zone": nom, "x": round(zx, 3), "y": round(zy, 3), "w": round(zw, 3), "h": round(zh, 3)})

	if code == "avant":
		if contenu.get("logo"):
			zone("logo", x, y, min(w * 0.4, h * 0.6), h * 0.12)
		bas = y + h
		if contenu.get("nom"):
			zone("nom", x, bas - h * 0.14, w, h * 0.14)
			bas -= h * 0.14
		if contenu.get("accroche"):
			zone("accroche", x, bas - h * 0.08, w, h * 0.08)
	elif code == "arriere":
		haut = y
		if contenu.get("logo"):
			zone("logo", x, y, min(w * 0.3, h * 0.4), h * 0.09)
			haut += h * 0.11
		cb = contenu.get("code_barres")
		bas = y + h
		if cb:
			cw, ch = _taille_code(cb, w * 0.5, h * 0.25)
			zone("code_barres", x + w - cw, bas - ch, cw, ch)
		if contenu.get("pictos"):
			taille = min(h * 0.09, w / max(1, contenu["pictos"]) * 0.8)
			zone("pictos", x, bas - taille, (w * 0.5) if cb else w, taille)
		bas -= max(h * 0.25 if cb else 0, h * 0.10 if contenu.get("pictos") else 0) + h * 0.02
		if contenu.get("avertissements"):
			zone("avertissements", x, bas - h * 0.22, w, h * 0.22)
			bas -= h * 0.24
		if contenu.get("caracteristiques"):
			zone("caracteristiques", x, haut, w, max(h * 0.2, bas - haut))
	elif code in ("cote_gauche", "cote_droit"):
		haut = y
		if contenu.get("logo"):
			zone("logo", x, y, w, h * 0.12)
			haut += h * 0.14
		if contenu.get("nom"):
			zone("nom", x, haut, w, h * 0.12)
			haut += h * 0.14
		bas = y + h
		# Quand le dos est le miroir de l'avant, l'EAN et les avertissements déménagent ici.
		cb = contenu.get("code_barres_cote")
		if cb:
			cw, ch = _taille_code(cb, w, h * 0.2)
			zone("code_barres", x + w - cw, bas - ch, cw, ch)
			bas -= ch + h * 0.02
		if contenu.get("pictos"):
			taille = min(w / max(1, contenu["pictos"]) * 0.8, h * 0.1)
			zone("pictos", x, bas - taille, w, taille)
			bas -= taille + h * 0.02
		if contenu.get("avertissements_cote"):
			zone("avertissements", x, bas - h * 0.18, w, h * 0.18)
			bas -= h * 0.2
		if contenu.get("contact"):
			zone("contact", x, bas - h * 0.22, w, h * 0.22)
			bas -= h * 0.24
		if contenu.get("caracteristiques"):
			zone("caracteristiques", x, haut, w, max(h * 0.15, bas - haut))
	elif code == "dessus":
		if contenu.get("logo"):
			zone("logo", x + w * 0.25, y, w * 0.5, h * 0.45)
		if contenu.get("nom"):
			zone("nom", x, y + h * 0.5, w, h * 0.45)
	elif code == "dessous":
		if contenu.get("contact"):
			zone("contact", x, y, w * 0.6, h)
		if contenu.get("pictos"):
			zone("pictos", x + w * 0.62, y + h * 0.3, w * 0.38, h * 0.4)
	return zones


ZONES_AJOUTABLES = ("logo", "nom", "accroche", "caracteristiques", "avertissements", "contact", "pictos",
                    "code_barres", "photo", "texte_libre")

#: Les zones qui impriment du texte : chacune accepte sa police, sa taille, gras/italique,
#: son alignement (`typo`) et sa couleur (`style.texte`) — demande utilisateur 06/10/2026.
#: « texte_libre » : un texte saisi dans le studio, jamais touché par l'IA ; plusieurs par face.
ZONES_TEXTE = ("nom", "accroche", "caracteristiques", "avertissements", "contact", "texte_libre")
ALIGNEMENTS = ("left", "center", "right", "justify")
TAILLE_TEXTE_LIBRE = 10.0


_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def style_zone(zone: dict) -> dict | None:
	"""Le style « cartouche » d'une zone dessinée à la main (demande utilisateur 24/09/2026 :
	« un peu arrondi, bleu, écriture en blanc ») : {fond, texte, rayon} normalisé — couleurs en
	#rrggbb ou None, rayon en mm ≥ 0 — ou None s'il n'y a rien à styler. Pur."""
	s = zone.get("style")
	if not isinstance(s, dict):
		return None
	fond = s.get("fond") if isinstance(s.get("fond"), str) and _HEX.match(s.get("fond")) else None
	texte = s.get("texte") if isinstance(s.get("texte"), str) and _HEX.match(s.get("texte")) else None
	try:
		rayon = max(0.0, min(50.0, float(s.get("rayon") or 0)))
	except (TypeError, ValueError):
		rayon = 0.0
	if not fond and not texte:
		return None
	return {"fond": fond, "texte": texte, "rayon": rayon}


def typo_zone(zone: dict, familles: set | None = None) -> dict:
	"""La typographie choisie pour une zone de texte, normalisée : {police, taille, gras, italique,
	align} — seules les clés réglées sont rendues. Une police inconnue (supprimée depuis) est
	ignorée quand `familles` est fourni ; taille bornée à 4–120 pt. Pur."""
	t = zone.get("typo")
	if not isinstance(t, dict):
		return {}
	out = {}
	police = t.get("police")
	if isinstance(police, str) and police.strip() and len(police) <= 80 and (familles is None or police.strip() in familles):
		out["police"] = police.strip()
	try:
		taille = float(t.get("taille") or 0)
	except (TypeError, ValueError):
		taille = 0.0
	if taille:
		out["taille"] = round(max(4.0, min(120.0, taille)), 1)
	for cle in ("gras", "italique"):
		if isinstance(t.get(cle), bool):
			out[cle] = t[cle]
	if t.get("align") in ALIGNEMENTS:
		out["align"] = t["align"]
	return out


#: Ce qu'une zone dessinée à la main transporte en plus de sa géométrie : son style, sa
#: typographie, le texte d'un « texte libre », pour un logo le fichier d'une variante propre
#: à cette face et, pour un code-barres, ce qu'elle porte (« qr » ou « ean », 06/10/2026).
CLES_ZONE_CONSERVEES = ("style", "logo", "pictos", "typo", "texte", "code")


def rotation_zone(zone: dict) -> float:
	"""Angle horaire du visuel dans son cadre, en degrés ; le cadre reste borné à la face."""
	if zone.get("zone") not in ("logo", "photo"):
		return 0.0
	try:
		angle = float(zone.get("rotation") or 0)
		return round(angle % 360, 3) if math.isfinite(angle) else 0.0
	except (TypeError, ValueError):
		return 0.0


def zoom_zone(zone: dict) -> float:
	"""Grossissement du visuel, indépendant de la taille du cadre (1 = ajusté)."""
	if zone.get("zone") not in ("logo", "photo"):
		return 1.0
	try:
		zoom = float(zone.get("zoom_image", 1))
		return round(max(0.25, min(4.0, zoom)), 3) if math.isfinite(zoom) else 1.0
	except (TypeError, ValueError):
		return 1.0


def decalage_zone(zone: dict) -> dict:
	"""Déplacement en mm dans les axes de la feuille, indépendant du cadre et de la rotation."""
	d = zone.get("decalage_contenu")
	d = d if isinstance(d, dict) else {}
	out = {}
	for axe, taille in (("x", "w"), ("y", "h")):
		try:
			v, limite = float(d.get(axe) or 0), max(0, float(zone.get(taille) or 0))
			out[axe] = round(max(-limite, min(limite, v)), 3) if math.isfinite(v) and math.isfinite(limite) else 0.0
		except (TypeError, ValueError):
			out[axe] = 0.0
	return out


def centre_zone(zone: dict, source: str | None = None) -> dict | None:
	"""Centre visible normalisé, valable uniquement pour le logo qui a été mesuré."""
	c = zone.get("centre_visuel")
	if zone.get("zone") != "logo" or not isinstance(c, dict) or not isinstance(c.get("source"), str):
		return None
	if not c["source"] or (source is not None and c["source"] != source):
		return None
	try:
		x, y = float(c["x"]), float(c["y"])
	except (KeyError, TypeError, ValueError):
		return None
	if not all(math.isfinite(v) and 0 <= v <= 1 for v in (x, y)):
		return None
	return {"x": round(x, 6), "y": round(y, 6), "source": c["source"]}


def borner_zone(zone: dict, face: dict) -> dict:
	"""Une zone dessinée à la main reste DANS la partie utile de la face (jamais dans le fond
	perdu, chez le voisin, ni dans une bande réservée comme le repli agrafé d'un sac) et garde
	une taille minimale. Pur."""
	u = face.get("utile") or face
	w = max(3.0, min(float(zone.get("w", 0)), u["w"]))
	h = max(3.0, min(float(zone.get("h", 0)), u["h"]))
	x = min(max(float(zone.get("x", u["x"])), u["x"]), u["x"] + u["w"] - w)
	y = min(max(float(zone.get("y", u["y"])), u["y"]), u["y"] + u["h"] - h)
	out = {"zone": zone.get("zone"), "x": round(x, 3), "y": round(y, 3), "w": round(w, 3), "h": round(h, 3)}
	for cle in CLES_ZONE_CONSERVEES:
		if zone.get(cle):
			out[cle] = zone[cle]
	if zone.get("zone") == "pictos" and zone.get("pictos_mode") == "selection":
		out["pictos_mode"] = "selection"
		out["pictos"] = selection_pictos(zone)
	if zone.get("zone") == "pictos" and zone.get("pictos_disposition") == "vertical":
		out["pictos_disposition"] = "vertical"
	from aquaworld_ia.emballage.pictos_images import variantes
	if variantes(zone):
		out["pictos_images"] = variantes(zone)
	if rotations_pictos(zone):
		out["pictos_rotations"] = rotations_pictos(zone)
	if rotation_zone(zone):
		out["rotation"] = rotation_zone(zone)
	if zoom_zone(zone) != 1:
		out["zoom_image"] = zoom_zone(zone)
	if centre_zone(zone):
		out["centre_visuel"] = centre_zone(zone)
	if zone.get("decalage_contenu") is not None:
		out["decalage_contenu"] = decalage_zone({**zone, "w": w, "h": h})
	return out


def appliquer_mise_en_page(zones: dict, plan: dict, mise_en_page: dict | None) -> dict:
	"""Les zones dessinées par l'utilisateur REMPLACENT celles de la maquette, face par face
	(demande utilisateur 23/09/2026 : agrandir, déplacer, supprimer, ajouter). Une face absente
	de `mise_en_page` garde sa maquette. Pur."""
	if not mise_en_page:
		return zones
	out = dict(zones)
	for code, liste in mise_en_page.items():
		f = geometrie.face(plan, code)
		if not f or not f["imprimable"] or not isinstance(liste, list):
			continue
		out[code] = [borner_zone(z, f) for z in liste if z.get("zone") in ZONES_AJOUTABLES]
	return out


def translater_zones(zones: list[dict], de: dict, vers: dict) -> list[dict]:
	"""Les zones d'une face recopiées sur une autre de même taille (dos ← avant, côté gauche ←
	côté droit), puis bornées à la face d'arrivée. Pur."""
	dx, dy = vers["x"] - de["x"], vers["y"] - de["y"]
	return [borner_zone(dict(z, x=z["x"] + dx, y=z["y"] + dy), vers) for z in zones]


def faces_copiees(plan: dict, faces_identiques: bool = False, cotes_identiques: bool = False,
                  mise_en_page: dict | None = None) -> dict:
	"""{face copiée: face source} : le dos copie l'avant, le côté gauche copie le côté droit, sauf
	si la face copiée a sa propre mise en page (une main qui l'a dessinée a raison). Pur."""
	codes = {f["code"] for f in plan["faces"] if f["imprimable"]}
	mep = mise_en_page or {}
	out = {}
	if faces_identiques and "cote_droit" in codes and "arriere" in codes and "arriere" not in mep:
		out["arriere"] = "avant"
	if cotes_identiques and {"cote_droit", "cote_gauche"} <= codes and "cote_gauche" not in mep:
		out["cote_gauche"] = "cote_droit"
	return out


def face_source(plan: dict, code: str, copies: dict) -> dict:
	"""La face dont `code` reprend le contenu ET le fond : sa source si elle est copiée, elle-même
	sinon. Pur."""
	return geometrie.face(plan, copies.get(code, code)) or geometrie.face(plan, code)


def zones_par_face(plan: dict, contenu: dict, faces_identiques: bool = False, mise_en_page: dict | None = None,
                   cotes_identiques: bool = False) -> dict:
	"""{code: zones} pour toutes les faces imprimables. Pur.

	`faces_identiques` (demande utilisateur 23/09/2026 : « face avant et arrière la même ») : le
	dos reçoit la MAQUETTE DE L'AVANT (logo, nom, accroche) ; l'EAN et les avertissements, qui
	vivaient au dos, passent sur le côté droit s'il existe. Sans côté (sachet doypack), le dos
	garde sa maquette : mieux vaut un dos différent qu'un EAN nulle part.
	`cotes_identiques` (demande utilisateur 24/09/2026 : « côté gauche et côté droit les mêmes ») :
	le côté gauche est la copie du côté droit — EAN et avertissements compris quand le dos est le
	miroir de l'avant : ils sont alors DUPLIQUÉS sur les deux côtés, l'emballage reste symétrique.
	Une face copiée reprend aussi la mise en page dessinée à la main sur sa source ; une face
	copiée qui a sa propre mise en page la garde."""
	codes = {f["code"] for f in plan["faces"] if f["imprimable"]}
	miroir = faces_identiques and "cote_droit" in codes
	out = {}
	for f in plan["faces"]:
		if not f["imprimable"]:
			continue
		c = dict(contenu)
		if miroir and f["code"] == "arriere":
			out[f["code"]] = maquette_face(dict(f, code="avant"), c)
			continue
		if miroir and f["code"] == "cote_droit":
			c["code_barres_cote"] = contenu.get("code_barres")
			c["avertissements_cote"] = contenu.get("avertissements")
		out[f["code"]] = maquette_face(f, c)
	out = appliquer_mise_en_page(out, plan, mise_en_page)
	for cible, source in faces_copiees(plan, faces_identiques, cotes_identiques, mise_en_page).items():
		out[cible] = translater_zones(out[source], geometrie.face(plan, source), geometrie.face(plan, cible))
	return out


def hero_photo_rect(face: dict) -> tuple:
	"""Où poser la photo produit sur une face avant SANS visuel IA : entre le logo (haut) et le
	nom + accroche (bas), avec de l'air. (x, y, w, h) en mm. Pur."""
	z = face["zone_sure"]
	return (z["x"] + z["w"] * 0.08, z["y"] + z["h"] * 0.16, z["w"] * 0.84, z["h"] * 0.56)


def taille_nom(w_pt: float, h_pt: float, texte: str, maximum: float = 40.0, minimum: float = 7.0) -> float:
	"""La taille de police (pt) du nom du produit pour tenir sur UNE ligne dans la zone : bornée
	par la hauteur et par la largeur (≈ 0,58 em par caractère en Noto Sans gras). Pur."""
	n = max(1, len(texte or ""))
	return round(max(minimum, min(maximum, h_pt * 0.55, w_pt / (0.58 * n))), 1)


def _taille_code(nominal: tuple, w_max: float, h_max: float) -> tuple[float, float]:
	"""Un EAN garde ses proportions ; il se réduit jusqu'à 80 % du nominal au plus, sinon on
	le laisse dépasser (le contrôle `verifier` a déjà prévenu)."""
	w, h = nominal
	k = min(1.0, w_max / w, h_max / h)
	k = max(k, 0.8)
	return w * k, h * k


def marges_fond_perdu(face: dict, plan: dict) -> dict:
	"""Extension (mm) du visuel sur chaque bord : le fond perdu sur les arêtes de coupe, 0 sur
	les plis. Pur."""
	fp = plan.get("fond_perdu", 0) or 0
	coupes = {tuple(round(v, 2) for v in t) for t in plan["traits"]["coupe"]}
	x0, y0, x1, y1 = face["x"], face["y"], face["x"] + face["w"], face["y"] + face["h"]

	def est_coupe(a, b):
		pts = sorted([(round(a[0], 2), round(a[1], 2)), (round(b[0], 2), round(b[1], 2))])
		return (pts[0][0], pts[0][1], pts[1][0], pts[1][1]) in coupes

	return {
		"haut": fp if est_coupe((x0, y0), (x1, y0)) else 0,
		"bas": fp if est_coupe((x0, y1), (x1, y1)) else 0,
		"gauche": fp if est_coupe((x0, y0), (x0, y1)) else 0,
		"droite": fp if est_coupe((x1, y0), (x1, y1)) else 0,
	}


def rect_avec_fond_perdu(face: dict, plan: dict) -> tuple:
	m = marges_fond_perdu(face, plan)
	return (face["x"] - m["gauche"], face["y"] - m["haut"], face["w"] + m["gauche"] + m["droite"],
	        face["h"] + m["haut"] + m["bas"])


# ------------------------------------------------------------------ images


def couleurs_dominantes(png: bytes, n: int = 3) -> list[str]:
	from PIL import Image

	im = Image.open(io.BytesIO(png)).convert("RGB")
	im.thumbnail((160, 160))
	pal = im.quantize(colors=max(2, n), method=Image.Quantize.MEDIANCUT)
	couleurs = pal.getpalette()[: 3 * max(2, n)]
	comptes = sorted(pal.getcolors() or [], reverse=True)
	sortie = []
	for _nb, idx in comptes[:n]:
		r, g, b = couleurs[3 * idx: 3 * idx + 3]
		sortie.append("#%02x%02x%02x" % (r, g, b))
	return sortie or ["#e5e7eb"]


def _hex_rgb(h: str) -> tuple:
	h = (h or "#e5e7eb").lstrip("#")
	return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def recadrer(png: bytes, face_w: float, face_h: float) -> bytes:
	from PIL import Image

	im = Image.open(io.BytesIO(png)).convert("RGB")
	x0, y0, x1, y1 = geometrie.cadrage(face_w, face_h, im.width, im.height)
	sortie = io.BytesIO()
	im.crop((x0, y0, x1, y1)).save(sortie, format="JPEG", quality=92)
	return sortie.getvalue()


def boite_tranche(bande: dict, face_rect: tuple, img_w: int, img_h: int) -> tuple[int, int, int, int]:
	"""La boîte (pixels) à découper dans le panorama pour UNE face : le panorama couvre la bande
	(recadré « couvrant » sur son ratio), la face en prend la tranche située à sa place. Deux
	faces voisines reçoivent deux tranches contiguës : le motif se poursuit au pli. Pur."""
	x0, y0, x1, y1 = geometrie.cadrage(bande["w"], bande["h"], img_w, img_h)
	k = (x1 - x0) / bande["w"]
	fx, fy, fw, fh = face_rect
	bx0 = x0 + (fx - bande["x"]) * k
	by0 = y0 + (fy - bande["y"]) * k
	return (int(round(bx0)), int(round(by0)), int(round(bx0 + fw * k)), int(round(by0 + fh * k)))


def tranche_panorama(png: bytes, bande: dict, face_rect: tuple) -> bytes:
	from PIL import Image

	im = Image.open(io.BytesIO(png)).convert("RGB")
	boite = boite_tranche(bande, face_rect, im.width, im.height)
	boite = (max(0, boite[0]), max(0, boite[1]), min(im.width, boite[2]), min(im.height, boite[3]))
	sortie = io.BytesIO()
	im.crop(boite).save(sortie, format="JPEG", quality=92)
	return sortie.getvalue()


def bandeau(png: bytes, fraction: float = 0.28) -> bytes:
	"""Le tiers supérieur du visuel avant, en bandeau décoratif pour les faces dérivées."""
	from PIL import Image

	im = Image.open(io.BytesIO(png)).convert("RGB")
	sortie = io.BytesIO()
	im.crop((0, 0, im.width, max(1, int(im.height * fraction)))).save(sortie, format="JPEG", quality=90)
	return sortie.getvalue()


def svg_vers_pdf(svg: bytes):
	from aquaworld_ia.emballage.svg_impression import vers_pdf

	return vers_pdf(svg)


def image_vers_pdf(octets: bytes):
	import pymupdf

	if est_svg(octets):
		return svg_vers_pdf(octets)
	with pymupdf.open(stream=octets) as image:
		return pymupdf.open("pdf", image.convert_to_pdf())


def carre_centre(rect) -> tuple:
	"""Le plus grand carré centré dans `rect` (x0, y0, x1, y1) : la place d'un QR dans sa zone. Pur."""
	x0, y0, x1, y1 = rect
	cote = min(x1 - x0, y1 - y0)
	x, y = x0 + (x1 - x0 - cote) / 2, y0 + (y1 - y0 - cote) / 2
	return (x, y, x + cote, y + cote)


def poser_svg(page, rect, svg: bytes, garder_proportions: bool = True, rotation: float = 0) -> None:
	import pymupdf

	with svg_vers_pdf(svg) as src:
		page.show_pdf_page(pymupdf.Rect(*rect), src, 0, keep_proportion=garder_proportions, rotate=-rotation)


def poser_image(page, rect, octets: bytes, garder_proportions: bool = True, rotation: float = 0, zoom: float = 1,
                centre: dict | None = None, decalage: dict | None = None) -> None:
	import pymupdf

	if centre:
		# Une translation du contenu, puis une découpe au cadre. Le centre mesuré suit la
		# rotation et le zoom ; les tracés SVG restent des tracés dans le PDF intermédiaire.
		with image_vers_pdf(octets) as src, pymupdf.open() as cadre:
			r, original = pymupdf.Rect(*rect), src[0].rect
			angle = math.radians(rotation)
			c, s = math.cos(angle), math.sin(angle)
			facteur = min(r.width / (original.width * abs(c) + original.height * abs(s)),
			              r.height / (original.width * abs(s) + original.height * abs(c))) * zoom
			x = (centre["x"] - .5) * original.width * facteur
			y = (centre["y"] - .5) * original.height * facteur
			dx, dy = c*x - s*y, s*x + c*y
			dx -= MM((decalage or {}).get("x", 0))
			dy -= MM((decalage or {}).get("y", 0))
			mx, my = r.width * (1-zoom) / 2, r.height * (1-zoom) / 2
			p = cadre.new_page(width=r.width, height=r.height)
			p.show_pdf_page(pymupdf.Rect(mx-dx, my-dy, r.width-mx-dx, r.height-my-dy), src, 0, rotate=-rotation)
			page.show_pdf_page(r, cadre, 0)
		return
	if zoom != 1 or (decalage and any(decalage.values())):
		# La page intermédiaire découpe le débordement au cadre, même après rotation.
		# show_pdf_page conserve les tracés des SVG, sans les transformer en pixels.
		r = pymupdf.Rect(*rect)
		with pymupdf.open() as cadre:
			p = cadre.new_page(width=r.width, height=r.height)
			dx, dy = r.width * (1 - zoom) / 2, r.height * (1 - zoom) / 2
			tx, ty = MM((decalage or {}).get("x", 0)), MM((decalage or {}).get("y", 0))
			poser_image(p, (dx+tx, dy+ty, r.width-dx+tx, r.height-dy+ty), octets,
			            garder_proportions=garder_proportions, rotation=rotation)
			page.show_pdf_page(r, cadre, 0)
		return
	if est_svg(octets):
		poser_svg(page, rect, octets, garder_proportions=garder_proportions, rotation=rotation)
		return
	if rotation:
		# show_pdf_page accepte les angles libres ; insert_image se limite aux quarts de tour.
		with image_vers_pdf(octets) as src:
			page.show_pdf_page(pymupdf.Rect(*rect), src, 0, keep_proportion=garder_proportions, rotate=-rotation)
		return
	r = pymupdf.Rect(*rect)
	if garder_proportions:
		# MuPDF 1.28 étire les bitmaps carrés malgré keep_proportion=True.
		# Calculer explicitement le même « contain » centré que l'aperçu navigateur.
		from PIL import Image
		with Image.open(io.BytesIO(octets)) as image:
			w, h = image.size
		facteur = min(r.width/w, r.height/h)
		dx, dy = (r.width-w*facteur)/2, (r.height-h*facteur)/2
		r = pymupdf.Rect(r.x0+dx, r.y0+dy, r.x1-dx, r.y1-dy)
	page.insert_image(r, stream=octets, keep_proportion=False)


def fond_blanc_en_transparence(octets: bytes, seuil: int = 235) -> bytes:
	"""Un logo ou une photo donnés sur fond blanc (JPEG/PNG) arrivent avec leur rectangle blanc :
	posés sur un visuel, ils feraient une étiquette collée. Si les quatre coins sont blancs, le fond
	devient transparent (demande utilisateur 23/09/2026). Un fichier dont les coins sont colorés est
	laissé tel quel — on ne devine pas.

	Détourage (24/09/2026, « pourquoi j'ai ça ? » : liseré de points sombres et bords crénelés sur
	la clé du porte-filtre) : le fond est la zone presque blanche CONNEXE AU BORD — un blanc à
	l'intérieur du produit reste ; les poussières de compression JPEG isolées dans le fond
	disparaissent (composantes minuscules) ; sur la frange de 2 px, les pixels presque blancs
	s'estompent (défrange) ; le bord est adouci d'un pixel. Sans OpenCV, repli pixel par pixel."""
	from PIL import Image

	im = Image.open(io.BytesIO(octets)).convert("RGBA")
	w, h = im.size
	if w < 2 or h < 2:
		return octets
	coins = [im.getpixel((0, 0)), im.getpixel((w - 1, 0)), im.getpixel((0, h - 1)), im.getpixel((w - 1, h - 1))]
	if not all(min(c[:3]) >= seuil and c[3] > 0 for c in coins):
		return octets
	try:
		im = _detourer(im, seuil)
	except Exception:
		pixels = im.getdata()
		im.putdata([(r, g, b, 0) if min(r, g, b) >= seuil else (r, g, b, a) for r, g, b, a in pixels])
	sortie = io.BytesIO()
	im.save(sortie, format="PNG")
	return sortie.getvalue()


MODES_FOND_FACE = ("fond", "image", "couleur", "blanc")


def reglage_fond(fonds_faces, code: str) -> dict | None:
	"""Le fond choisi pour UNE face dans le studio (demande utilisateur 06/10/2026 : « l'image de fond, je
	l'applique sur la face que je veux, ou je la laisse blanche, ou autre chose »), normalisé : {mode, image,
	couleur, photo_incluse} ; None = règle automatique. Pur."""
	r = (fonds_faces or {}).get(code) if isinstance(fonds_faces, dict) else None
	if not isinstance(r, dict) or r.get("mode") not in MODES_FOND_FACE:
		return None
	out = {"mode": r["mode"], "photo_incluse": bool(r.get("photo_incluse"))}
	if r["mode"] == "couleur":
		if not (isinstance(r.get("couleur"), str) and _HEX.match(r["couleur"])):
			return None
		out["couleur"] = r["couleur"]
	if r["mode"] == "image":
		if not (isinstance(r.get("image"), str) and r["image"].startswith(("/files/", "/private/files/"))):
			return None
		out["image"] = r["image"]
	return out


def couleur_texte_sur(fond_hex: str) -> str:
	"""Le texte lisible sur un aplat : sombre sur clair, blanc sur foncé. Pur."""
	return "#111827" if _luminance(fond_hex) > 0.5 else "#ffffff"


def blanc_pur(png: bytes, debut: int = 232, fin: int = 248) -> bytes:
	"""Le « presque blanc » d'une image IA devient du BLANC PUR (retour utilisateur 06/10/2026 : « la génération
	n'est pas vraiment blanche » — le fond de EMB-2026-0006 valait #FDFDFD en moyenne, 25 % de pixels blancs, et
	paraissait gris à côté des faces réglées sur Blanc). Un pixel dont le canal le plus FAIBLE dépasse `debut`
	glisse vers 255 (courbe en S jusqu'à `fin`) : les couleurs franches ne bougent pas, la transition reste douce.
	Sans IA, au pixel près."""
	import numpy as np
	from PIL import Image

	im = Image.open(io.BytesIO(png))
	alpha = im.getchannel("A") if im.mode in ("RGBA", "LA") else None
	a = np.array(im.convert("RGB")).astype(np.float32)
	t = np.clip((a.min(axis=2) - debut) / float(max(1, fin - debut)), 0.0, 1.0)
	t = (t * t * (3 - 2 * t))[..., None]
	sortie = Image.fromarray(np.clip(a + (255.0 - a) * t, 0, 255).round().astype(np.uint8), "RGB")
	if alpha is not None:
		sortie.putalpha(alpha)
	b = io.BytesIO()
	sortie.save(b, "PNG")
	return b.getvalue()


def part_blanc_pur(png: bytes) -> float:
	"""Part des pixels exactement blancs (0..1) — pour dire à l'utilisateur ce que le blanc pur a changé."""
	import numpy as np
	from PIL import Image

	a = np.array(Image.open(io.BytesIO(png)).convert("RGB"))
	return float((a.min(axis=2) >= 255).mean())


#: Largeur du fondu des bords d'une photo, en part de son petit côté.
FONDU_BORDS = 0.12


def fondre_bords(png: bytes, part: float = FONDU_BORDS) -> bytes:
	"""Les bords OPAQUES d'une photo s'effacent en douceur dans le fond (retour utilisateur 06/10/2026 : « une
	meilleure intégration entre la photo produit et le fond ») — l'eau d'une éclaboussure coupée net par le cadre
	de la photo laissait deux arêtes verticales sur l'emballage. Une photo déjà détourée (bords transparents) revient
	telle quelle. Courbe en S (smoothstep) sur `part` du petit côté."""
	import numpy as np
	from PIL import Image

	a = np.array(Image.open(io.BytesIO(png)).convert("RGBA"))
	h, w = a.shape[:2]
	al = a[..., 3]
	if max((b > 200).mean() for b in (al[:, :2], al[:, -2:], al[:2, :], al[-2:, :])) < 0.05:
		return png
	m = max(2.0, min(h, w) * part)
	ys, xs = np.mgrid[0:h, 0:w]
	t = np.clip(np.minimum.reduce([xs, w - 1 - xs, ys, h - 1 - ys]) / m, 0.0, 1.0)
	a[..., 3] = (al.astype(np.float32) * (t * t * (3 - 2 * t))).astype(np.uint8)
	sortie = io.BytesIO()
	Image.fromarray(a, "RGBA").save(sortie, "PNG")
	return sortie.getvalue()


def _detourer(im, seuil: int):
	"""Le détourage propre (voir `fond_blanc_en_transparence`) : OpenCV + numpy. Pur."""
	import cv2
	import numpy as np
	from PIL import Image

	rgba = np.array(im)
	h, w = rgba.shape[:2]
	mn = rgba[..., :3].min(axis=2)
	blanc = (mn >= seuil).astype(np.uint8)
	# 1. le fond = les composantes presque blanches qui touchent le bord
	_n, labels = cv2.connectedComponents(blanc, connectivity=4)
	bord = set(int(x) for x in np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]])) if x != 0)
	# … plus les zones blanches ENFERMÉES qui sont du blanc pur (trou d'une clé, contre-forme
	# d'une lettre) : c'est le fond vu à travers ; un blanc de produit ou de logo (éclairé,
	# jamais tout à fait 255) reste opaque.
	aires = np.bincount(labels.ravel())
	sommes = np.bincount(labels.ravel(), weights=mn.ravel().astype(np.float64))
	purs = [i for i in range(1, len(aires)) if i not in bord and aires[i] >= 16 and sommes[i] / aires[i] >= 250]
	fond = np.isin(labels, list(bord) + purs)
	opaque = ~fond
	# 2. poussières : composantes opaques minuscules (0,02 % de l'image, 16 px au moins)
	aire_min = max(16, int(0.0002 * w * h))
	n2, lab2, stats, _c = cv2.connectedComponentsWithStats(opaque.astype(np.uint8), connectivity=8)
	petites = [i for i in range(1, n2) if stats[i, cv2.CC_STAT_AREA] < aire_min]
	if petites:
		opaque[np.isin(lab2, petites)] = False
	alpha = opaque.astype(np.float32) * 255.0
	# 3. défrange : sur 2 px le long du fond, les pixels presque blancs (halo JPEG) s'estompent
	frange = cv2.dilate(fond.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool) & opaque
	bas = max(0, seuil - 35)
	clarte = np.clip((seuil - mn.astype(np.float32)) / float(max(1, seuil - bas)), 0.0, 1.0)
	alpha[frange] = alpha[frange] * clarte[frange]
	# 4. bord adouci d'un pixel
	alpha = cv2.GaussianBlur(alpha, (3, 3), 0)
	rgba[..., 3] = np.minimum(rgba[..., 3].astype(np.float32), alpha).astype(np.uint8)
	return Image.fromarray(rgba, "RGBA")


_COULEURS_NOMMEES = {"black": (0, 0, 0), "white": (255, 255, 255)}


def _rgb(valeur: str):
	"""'#000', '#1a2b3c', 'rgb(0,0,0)', 'black' -> (r, g, b) ; None si ce n'est pas une couleur
	(none, transparent, url(#…), currentColor, inherit)."""
	v = (valeur or "").strip().lower()
	if v in _COULEURS_NOMMEES:
		return _COULEURS_NOMMEES[v]
	if v.startswith("#") and len(v) in (4, 7):
		h = v[1:]
		if len(h) == 3:
			h = "".join(c * 2 for c in h)
		try:
			return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
		except ValueError:
			return None
	m = re.match(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", v)
	if m:
		return tuple(int(x) for x in m.groups())
	return None


def encres_svg(svg: bytes) -> set:
	"""Les couleurs d'encre d'un SVG (le blanc, none et currentColor ne comptent pas). Pur."""
	texte = svg.decode("utf-8", "replace")
	encres = set()
	for val in re.findall(r"(?:fill|stroke|stop-color)\s*[=:]\s*[\"']?\s*([^\"';)>]+)", texte):
		c = _rgb(val)
		if c is not None and min(c) < 235:
			encres.add(c)
	return encres


def svg_est_monochrome(svg: bytes) -> bool:
	"""Vrai si le SVG n'emploie qu'une seule couleur d'encre : un pictogramme normalisé, pas un
	logo de certification en couleurs. Pur."""
	return len(encres_svg(svg)) <= 1


def svg_est_recolorable(svg: bytes) -> bool:
	"""Ne se recolore qu'un pictogramme NOIR (ou presque) sans image embarquée. Un logo monochrome
	de couleur (le bleu Water Quality Association, constaté le 24/09/2026 : il sortait noir) garde
	sa couleur de marque ; un SVG « hybride » avec bitmap n'est pas touché. Pur."""
	if re.search(r"<image\b", svg.decode("utf-8", "replace"), re.IGNORECASE):
		return False
	encres = encres_svg(svg)
	if len(encres) > 1:
		return False
	return all(max(c) <= 70 for c in encres)


def recolorer_svg_monochrome(svg: bytes, couleur: str) -> bytes:
	"""Un pictogramme monochrome prend la couleur demandée (celle du texte de la face) : posé sans
	cartouche sur un fond sombre, un picto noir serait invisible. Le blanc et « none » sont gardés
	(les évidements restent des évidements) ; un SVG à plusieurs encres — certification en couleurs —
	revient tel quel. Sans fill explicite, le SVG hérite du noir : la couleur est posée à la racine. Pur."""
	if not svg_est_recolorable(svg):
		return svg
	texte = svg.decode("utf-8", "replace")

	def remplacer(m):
		prefixe, val = m.group(1), m.group(2)
		c = _rgb(val)
		if val.strip().lower() == "currentcolor" or (c is not None and min(c) < 235):
			return prefixe + couleur
		return m.group(0)

	texte = re.sub(r"((?:fill|stroke|stop-color)\s*[=:]\s*[\"']?\s*)([^\"';)>]+)", remplacer, texte)
	racine = re.search(r"<svg\b[^>]*>", texte, re.IGNORECASE)
	if racine and not re.search(r"\bfill\s*=", racine.group(0)):
		texte = texte[:racine.end() - 1] + ' fill="%s"' % couleur + texte[racine.end() - 1:]
	return texte.encode("utf-8")


def est_svg(octets: bytes) -> bool:
	debut = octets[:300].lstrip().lower()
	return debut.startswith(b"<svg") or (debut.startswith(b"<?xml") and b"<svg" in octets[:2000].lower())


_BLANC_SVG = r"(?:#fff\b|#ffffff\b|white\b|rgb\(\s*255\s*,\s*255\s*,\s*255\s*\))"


def _viewbox(svg: str):
	m = re.search(r"viewBox\s*=\s*[\"']\s*([-\d.]+)[\s,]+([-\d.]+)[\s,]+([-\d.]+)[\s,]+([-\d.]+)", svg)
	if m:
		return tuple(float(v) for v in m.groups())
	w = re.search(r"<svg\b[^>]*\swidth\s*=\s*[\"']([\d.]+)", svg)
	h = re.search(r"<svg\b[^>]*\sheight\s*=\s*[\"']([\d.]+)", svg)
	return (0.0, 0.0, float(w.group(1)), float(h.group(1))) if w and h else None


def _attr(tag: str, nom: str):
	m = re.search(r"\b%s\s*=\s*[\"']([^\"']*)[\"']" % nom, tag)
	if m:
		return m.group(1).strip()
	m = re.search(r"\b%s\s*:\s*([^;\"']+)" % nom, tag)      # style="fill:…"
	return m.group(1).strip() if m else None


def svg_sans_fond_blanc(svg: bytes) -> bytes:
	"""Un SVG posé sur un visuel ne doit pas apporter son fond blanc (question utilisateur
	24/09/2026 : « pourquoi avec un SVG ça ne devient pas transparent ? ») :
	- une image bitmap embarquée (`<image href="data:image/…">`, SVG « hybride » exporté d'un outil
	  en ligne) reçoit le même détourage qu'une photo — fond blanc connexe au bord effacé ;
	- un `<rect>` blanc SANS contour qui couvre presque tout le dessin (fond d'export) est retiré ;
	  un cadre blanc à contour (carte, badge) est un dessin voulu et reste.
	Pur."""
	texte = svg.decode("utf-8", "replace")

	def image(m):
		tag = m.group(0)
		mm = re.search(r"(href\s*=\s*[\"'])data:image/(png|jpe?g|webp);base64,([A-Za-z0-9+/=\s]+)([\"'])", tag)
		if not mm:
			return tag
		try:
			octets = base64.b64decode(mm.group(3))
			nouveau = fond_blanc_en_transparence(octets)
		except Exception:
			return tag
		if nouveau == octets:
			return tag
		return tag.replace(mm.group(0), "%sdata:image/png;base64,%s%s" % (mm.group(1), base64.b64encode(nouveau).decode(), mm.group(4)))

	texte = re.sub(r"<image\b[^>]*>", image, texte)
	vb = _viewbox(texte)
	if vb:
		def rect(m):
			tag = m.group(0)
			fill = (_attr(tag, "fill") or "").lower()
			if not re.fullmatch(_BLANC_SVG, fill):
				return tag
			stroke = (_attr(tag, "stroke") or "none").lower()
			if stroke not in ("none", "", "transparent"):
				return tag
			try:
				w = _attr(tag, "width") or ""
				h = _attr(tag, "height") or ""
				aire = (vb[2] if w.endswith("%") and float(w[:-1]) >= 99 else float(w)) * (vb[3] if h.endswith("%") and float(h[:-1]) >= 99 else float(h))
			except ValueError:
				return tag
			return "" if aire >= 0.9 * vb[2] * vb[3] else tag
		texte = re.sub(r"<rect\b[^>]*/>|<rect\b[^>]*>\s*</rect>", rect, texte)
	return texte.encode("utf-8")


def preparer_logo(logo: bytes) -> bytes:
	"""Même traitement du fond blanc pour l'éditeur et l'impression."""
	if est_svg(logo):
		return svg_sans_fond_blanc(logo)
	try:
		return fond_blanc_en_transparence(logo)
	except Exception:
		return logo


def poser_logo(page, rect, logo: bytes, rotation: float = 0, zoom: float = 1, centre: dict | None = None,
               decalage: dict | None = None) -> None:
	poser_image(page, rect, preparer_logo(logo), rotation=rotation, zoom=zoom, centre=centre, decalage=decalage)


def _rect_pt(x, y, w, h):
	return (MM(x), MM(y), MM(x + w), MM(y + h))


# ------------------------------------------------------------------ textes


def html_bloc(lignes: list[str], *, taille_pt: float, rtl: bool, famille: str, couleur: str = "#111827",
              gras: bool = False, puces: bool = False, align: str | None = None, facteur: float = 1.0,
              police_libre: bool = True, familles: set | None = None, italique: bool = False) -> str:
	"""Les paragraphes d'un bloc. Chaque ligne peut porter sa mise en forme (`mise_en_forme`) :
	taille en pt (multipliée par `facteur`, le rapport de la langue — 2e langue plus petite, arabe
	relevé), gras, italique, puce, police. La police d'une ligne ne s'applique que si
	`police_libre` (pas en arabe : une police latine n'a pas ses glyphes) et si elle existe
	(`familles`) ; sinon `famille`. Pur."""
	# ⚠️ PAS DE <ul> : le moteur d'insert_htmlbox pose le marqueur de liste à GAUCHE quoi qu'en
	# dise `direction:rtl` (constaté sur la fiche EMB-2026-0001 le 23/09/2026 : puces arabes
	# à gauche du texte, bloc collé à gauche). Une puce typographique dans le paragraphe suit,
	# elle, le sens d'écriture.
	out = []
	for l in lignes:
		st, texte = mise_en_forme.analyser(l)
		titre = st is None and texte.startswith(TITRE)
		if titre:
			# Un intertitre (texte brut de l'utilisateur : « SPECIFICATIONS », « Inlet :») : gras, sans puce.
			st, texte = dict(mise_en_forme.STYLE_INTERTITRE), texte[len(TITRE):]
		st, texte = st or {}, texte.strip()
		if not texte:
			continue
		police = st.get("police")
		fam = police if (police_libre and police and (familles is None or police in familles)) else famille
		taille = round(st["taille"] * facteur, 2) if st.get("taille") else taille_pt
		en_gras = gras or bool(st.get("gras"))
		puce = st["puce"] if "puce" in st else puces
		style = ("font-family:'%s';font-size:%.1fpt;color:%s;direction:%s;%sfont-weight:%d;font-style:%s;line-height:1.25"
		         % (fam.replace("\\", "\\\\").replace("'", "\\'"), taille, couleur, "rtl" if rtl else "ltr", alignement_css(align, rtl),
		            700 if en_gras else 400, "italic" if (st.get("italique") or italique) else "normal"))
		# Un intertitre (ou, dans une liste à puces, une ligne grasse sans puce) : un peu d'air au-dessus.
		marge = "0.5em 0 0.2em 0" if (titre or (en_gras and not puce and puces)) else "0 0 0.3em 0"
		out.append("<p style=\"%s;margin:%s\">%s%s</p>" % (html.escape(style, quote=False).replace('"', "&quot;"), marge, (PUCE + " ") if puce else "", html.escape(texte)))
	return "".join(out)


PUCE = "•"
TITRE = "## "


def lignes_brutes(texte: str | None) -> list[str]:
	"""Le texte saisi à l'étape 2, ligne par ligne, prêt pour `html_bloc` : lignes vides
	ignorées, intertitres (tout en capitales, ou terminés par « : ») marqués `## ` — sauf les
	lignes mises en forme, dont le préfixe dit déjà tout. Pur."""
	out = []
	for brut in (texte or "").splitlines():
		l = brut.strip()
		if not l:
			continue
		if mise_en_forme.analyser(l)[0] is not None:
			out.append(l)
			continue
		out.append((TITRE + l.rstrip(":").strip()) if mise_en_forme.est_intertitre(l) else l)
	return out


def textes_bruts(caracteristiques: str | None, avertissements: str | None, contact: str | None, code_langue: str = "fr") -> dict:
	"""Les textes à imprimer quand rien n'a été préparé par l'IA (demande utilisateur 24/09/2026 :
	« j'ai recomposé mais il n'a pas appliqué les caractéristiques ») : le texte brut de la fiche,
	dans la première langue du design. Pur."""
	t = {"accroche": "", "caracteristiques": lignes_brutes(caracteristiques), "avertissements": lignes_brutes(avertissements),
	     "contact": (contact or "").strip()}
	return {code_langue: t} if (t["caracteristiques"] or t["avertissements"] or t["contact"]) else {}


def alignement_css(align: str | None, rtl: bool) -> str:
	"""⚠️ MUPDF INVERSE L'ALIGNEMENT SOUS `direction:rtl` : `text-align:right` y colle le texte à
	GAUCHE, et l'absence de consigne (ou `left`) le range à droite — mesuré le 23/09/2026 sur
	insert_htmlbox (x0=20 avec right, x1=380 sans). On ne demande donc jamais « right » à un
	paragraphe RTL : son alignement naturel EST la droite. Seul « center » se dit. Pur."""
	if rtl:
		return "text-align:center;" if align == "center" else ""
	return "text-align:%s;" % (align or "left")


def taille_langue(base_pt: float, rang: int, rtl: bool) -> float:
	"""La taille d'une langue dans une zone : la première un peu plus grande, et l'arabe
	relevé — Noto Naskh Arabic paraît nettement plus petit que Noto Sans à corps égal (les
	caractéristiques arabes étaient illisibles à 0,85 × 8,5 pt). Pur."""
	taille = base_pt if rang == 0 else base_pt * 0.9
	if rtl:
		taille *= 1.15
	return round(taille, 2)


#: Les zones de PETIT texte posées sur un visuel reçoivent un cartouche translucide : sans
#: lui, un texte sombre sur un bleu moyen (ou clair sur un ciel pâle) ne se lit pas — le
#: contraste dépend du visuel IA, que personne ne contrôle. Le nom et l'accroche, gros et
#: gras, s'en passent.
ZONES_CARTOUCHE = ("caracteristiques", "avertissements", "contact")
CARTOUCHE_MARGE_MM = 2.0


def panneau_pour(zone: str, couleur_texte: str, sur_visuel: bool):
	"""-> (rgb 0..1, opacité) du cartouche derrière une zone de texte, ou None. Pur."""
	if not sur_visuel or zone not in ZONES_CARTOUCHE:
		return None
	if couleur_texte.lower() == "#ffffff":
		return ((0.04, 0.07, 0.13), 0.45)
	return ((1.0, 1.0, 1.0), 0.82)


CARTOUCHE_STYLE_MARGE_MM = 2.0


PICTOS_ECART_MM = 2.0


def taille_pictos(w_mm: float, h_mm: float, n: int) -> float:
	"""Le côté (mm) de chaque pictogramme d'une zone : la hauteur de la zone, réduite s'il le faut
	pour que les `n` pictos tiennent TOUS en largeur avec leur écart (retour utilisateur 24/09/2026 :
	« pas tous les trucs sélectionnés ne figurent » — le dernier était abandonné). Pur."""
	if n <= 0:
		return 0.0
	return round(max(0.0, min(float(h_mm), (float(w_mm) - PICTOS_ECART_MM * (n - 1)) / n)), 3)


def selection_pictos(zone: dict) -> list | None:
	"""None suit Contenus ; une sélection explicite vide n'imprime aucun pictogramme.

	Les anciennes listes vides signifiaient « tous » : conserver ce rendu tant que
	l'utilisateur ne choisit pas explicitement le nouveau mode sélection.
	"""
	choix = zone.get("pictos")
	if isinstance(choix, list) and choix:
		return list(dict.fromkeys(c for c in choix if isinstance(c, str) and c))
	return [] if zone.get("pictos_mode") == "selection" else None


def rotations_pictos(zone: dict) -> dict:
	"""Angles horaires par code dans cette zone, indépendants des images du catalogue."""
	valeurs = zone.get("pictos_rotations")
	if zone.get("zone") != "pictos" or not isinstance(valeurs, dict):
		return {}
	out = {}
	for code, valeur in valeurs.items():
		if not isinstance(code, str) or not code or type(valeur) not in (int, float, str):
			continue
		try:
			angle = float(valeur)
			if math.isfinite(angle):
				angle = round(angle % 360, 3) % 360
				if angle:
					out[code] = angle
		except (ValueError, OverflowError):
			pass
	return out


def elements_symboles(zone: dict, face: str, *, pictos_svg=(), images_pictos=None, tampons=(), sans_cartouche=False,
                       couleur="#111827", ean=None, qr=None, qr_place=False) -> list[dict]:
	"""Symboles à poser (rectangles en mm), communs au plan interactif et au PDF."""
	x, y, w, h = (zone[k] for k in ("x", "y", "w", "h"))
	out = []

	def ajouter(image, rect, code, logo=False, fond=None):
		out.append({"image": image, "rect": rect, "code": code, "logo": logo, "fond": fond})

	if zone["zone"] == "pictos":
		choisis = selection_pictos(zone)
		liste = [(c, s) for c, s in pictos_svg if (c in choisis if choisis is not None else c not in tampons)]
		vertical = zone.get("pictos_disposition") == "vertical"
		# Une colonne ajuste ses symboles à la largeur ET à la hauteur disponible.
		# L'orientation de chacun reste indépendante de la disposition de la rangée.
		taille = taille_pictos(h, w, len(liste)) if vertical else taille_pictos(w, h, len(liste))
		if taille <= 0:
			return []
		marge = min(25.4 / 72, taille / 4)  # retrait de 1 pt, également dans les petites zones
		from aquaworld_ia.emballage.pictos_images import variantes
		variantes_zone = variantes(zone)
		angles = rotations_pictos(zone)
		for code, image in liste:
			fond = None
			personnalisee = (images_pictos or {}).get(variantes_zone.get(code))
			if personnalisee:
				image = personnalisee
			elif code not in tampons and sans_cartouche:
				if est_svg(image):
					image = recolorer_svg_monochrome(image, couleur)
				else:
					fond = [x, y, taille, taille]
			ajouter(image, [x + marge, y + marge, taille - 2*marge, taille - 2*marge], code, not bool(personnalisee), fond)
			if code in angles:
				out[-1]["rotation"] = angles[code]
			if vertical:
				y += taille + PICTOS_ECART_MM
			else:
				x += taille + PICTOS_ECART_MM
	elif zone["zone"] == "code_barres":
		porte = zone.get("code")
		if porte == "qr":
			if qr:
				c = min(w, h)
				r = [x + (w-c)/2, y + (h-c)/2, c, c]
				ajouter(qr, r, "qr", fond=r)
			return out
		qr_ici = None if (qr_place or porte == "ean") else qr
		if ean:
			r = [x, y, w, h]
			ajouter(ean, r, "ean", fond=r)
		elif qr_ici:
			c = min(w, h)
			r = [x + w-c, y + h-c, c, c]
			ajouter(qr_ici, r, "qr", fond=r)
		if ean and qr_ici and face == "arriere":
			c = min(18.0, h)
			r = [x - c - 2, y + h-c, c, c]
			ajouter(qr_ici, r, "qr", fond=r)
	return out


def poser_symboles(page, elements: list[dict], rect=None, decalage: dict | None = None) -> None:
	import pymupdf

	if rect and decalage and any(decalage.values()) and elements:
		def dessiner(p, cible):
			dx, dy = (cible[0] - rect[0]) / MM(1), (cible[1] - rect[1]) / MM(1)
			def decaler(r):
				return (r[0] + dx, r[1] + dy, r[2], r[3]) if r else r
			poser_symboles(p, [{**el, "rect": decaler(el["rect"]), "fond": decaler(el["fond"])} for el in elements])
		poser_contenu_decale(page, rect, decalage, dessiner)
		return
	for el in elements:
		if el["fond"]:
			page.draw_rect(pymupdf.Rect(*_rect_pt(*el["fond"])), color=None, fill=(1, 1, 1))
		poser = poser_logo if el["logo"] else poser_svg
		poser(page, _rect_pt(*el["rect"]), el["image"], rotation=el.get("rotation", 0))


def dessiner_cartouche(page, rect, style: dict) -> tuple:
	"""Le fond de couleur, coins arrondis, d'une zone stylée ; -> le rectangle intérieur (pt) où
	poser le texte, en retrait de 2 mm. Sans fond, la zone est rendue telle quelle."""
	import pymupdf

	if not style or not style.get("fond"):
		return rect
	r = pymupdf.Rect(*rect)
	rayon_pt = MM(style.get("rayon") or 0)
	fraction = min(0.5, rayon_pt / max(1.0, min(r.width, r.height))) if rayon_pt else None
	page.draw_rect(r, color=None, fill=_hex_rgb(style["fond"]), radius=fraction)
	m = min(MM(CARTOUCHE_STYLE_MARGE_MM), r.width / 4, r.height / 4)
	return (r.x0 + m, r.y0 + m, r.x1 - m, r.y1 - m)


def _poser_fond_regle(page, reg: dict, r, face: dict, image_fond, bande, dpi: dict) -> bool:
	"""Pose le fond CHOISI pour une face (studio, « Fond de cette face ») ; False = rien de posable (image
	illisible, pas d'image de fond) : la règle automatique reprend la main."""
	import pymupdf

	rect = _rect_pt(*r)
	if reg["mode"] == "blanc":
		page.draw_rect(pymupdf.Rect(*rect), color=None, fill=(1, 1, 1))
		return True
	if reg["mode"] == "couleur":
		page.draw_rect(pymupdf.Rect(*rect), color=None, fill=_hex_rgb(reg["couleur"]))
		return True
	if reg["mode"] == "image":
		try:
			img = fichiers.lire(reg["image"])
		except Exception:
			return False
		from PIL import Image

		im = Image.open(io.BytesIO(img))
		x0, y0, x1, y1 = geometrie.cadrage(r[2], r[3], im.width, im.height)
		dpi[face["code"]] = geometrie.dpi_effectif(x1 - x0, r[2])
		poser_image(page, rect, recadrer(img, r[2], r[3]), garder_proportions=False)
		return True
	if reg["mode"] == "fond" and image_fond:
		if bande and face["code"] in bande["faces"]:
			poser_image(page, rect, tranche_panorama(image_fond, bande, r), garder_proportions=False)
		else:
			poser_image(page, rect, recadrer(image_fond, r[2], r[3]), garder_proportions=False)
		return True
	return False


def poser_contenu_decale(page, rect, decalage: dict, dessiner, cadre=None):
	"""Décale le contenu avant de découper au cadre fixe, en conservant textes et SVG vectoriels.

	La marge de la page temporaire permet aussi les décalages négatifs, sans modifier
	la largeur de composition du texte. Les cartouches restent sur la page destination.
	"""
	import pymupdf

	if not any(decalage.values()):
		return dessiner(page, rect)
	r = pymupdf.Rect(*(cadre or rect))
	dx, dy = MM(decalage.get("x", 0)), MM(decalage.get("y", 0))
	px, py = r.width + abs(dx), r.height + abs(dy)
	with pymupdf.open() as temporaire:
		p = temporaire.new_page(width=r.width + 2*px, height=r.height + 2*py)
		tx, ty = px - r.x0 + dx, py - r.y0 + dy
		resultat = dessiner(p, (rect[0]+tx, rect[1]+ty, rect[2]+tx, rect[3]+ty))
		if p.get_contents():
			page.show_pdf_page(r, temporaire, 0, clip=pymupdf.Rect(px, py, px+r.width, py+r.height))
		return resultat


def poser_texte(page, rect, contenu_html: str, archive, css: str, decalage: dict | None = None, cadre=None) -> float:
	import pymupdf

	if decalage and any(decalage.values()):
		return poser_contenu_decale(page, rect, decalage,
		                           lambda p, r: poser_texte(p, r, contenu_html, archive, css), cadre=cadre)
	spare, echelle = page.insert_htmlbox(pymupdf.Rect(*rect), contenu_html, css=css, scale_low=0.4, archive=archive)
	return echelle if spare >= 0 else 0.0


def hauteur_texte(rect, contenu_html: str, archive, css: str) -> float:
	"""La hauteur (pt) qu'occupera le texte dans `rect`, mesurée sur une page jetable — le
	cartouche se dessine AVANT le texte et doit épouser le contenu, pas la zone : la zone des
	caractéristiques prend tout le milieu de la face, et un cartouche à sa taille effaçait le
	visuel (constaté le 23/09/2026)."""
	import pymupdf

	r = pymupdf.Rect(*rect)
	brouillon = pymupdf.open().new_page(width=max(r.x1, 1) + 10, height=max(r.y1, 1) + 10)
	spare, _ = brouillon.insert_htmlbox(r, contenu_html, css=css, scale_low=0.4, archive=archive)
	return r.height if spare < 0 else r.height - spare


def _famille(langue: dict, textes_perso: bool = False) -> str:
	"""La police d'une langue sur l'emballage : la sienne (fiche Langue) d'abord ; sinon la police
	des textes des Réglages pour les langues de gauche à droite ; sinon Noto. Pur."""
	if langue.get("police_fichier"):
		return rendu.famille_langue_perso(langue.get("code") or "x")
	if textes_perso and not langue.get("rtl") and not langue.get("police"):
		return rendu.FAMILLE_TEXTES
	return rendu.famille(langue)


def famille_titres(titres_perso: bool) -> str:
	return rendu.FAMILLE_TITRES if titres_perso else "Noto Sans"


def police_libre(langue: dict) -> bool:
	"""Une langue accepte-t-elle la police choisie pour un bloc ou une ligne ? Pas l'arabe (sens
	de droite à gauche), ni une langue qui a SON fichier de police (écriture que les polices
	latines ne couvrent pas). Pur."""
	return not langue.get("rtl") and not langue.get("police_fichier")


_ARABE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")


def html_texte_libre(texte: str | None, typo: dict, couleur: str, familles: set | None = None) -> str:
	"""Le HTML d'une zone « texte libre » : le texte tel que saisi, ligne par ligne (une ligne
	vide garde son espace), dans la typographie de la zone. Chaque ligne accepte la même mise en
	forme que les caractéristiques (« {14pt, gras} … »). Un texte en arabe passe de droite à
	gauche, dans la police arabe : une police latine n'a pas ses glyphes. Pur."""
	texte = (texte or "").replace("\r\n", "\n").strip("\n")
	if not texte.strip():
		return ""
	rtl = bool(_ARABE.search(texte))
	taille = typo.get("taille") or TAILLE_TEXTE_LIBRE
	famille = "Noto Naskh Arabic" if rtl else (typo.get("police") or "Noto Sans")
	morceaux = []
	for ligne in texte.split("\n"):
		if not ligne.strip():
			morceaux.append("<p style=\"font-size:%.1fpt;line-height:1.25;margin:0\">&#160;</p>" % taille)
			continue
		morceaux.append(html_bloc([ligne], taille_pt=taille, rtl=rtl, famille=famille, couleur=couleur,
		                          gras=bool(typo.get("gras")), italique=bool(typo.get("italique")),
		                          align=typo.get("align"), police_libre=not rtl, familles=familles))
	return "".join(morceaux)


def textes_pour_zone(nom_zone: str, textes: dict, langues: dict, taille_pt: float, couleur: str,
                     police_bloc: str | None = None, familles: set | None = None, typo: dict | None = None) -> str:
	"""Le HTML d'une zone, toutes langues empilées (première langue plus grande). `police_bloc` :
	la police choisie pour les caractéristiques du design. `typo` : la typographie choisie pour
	CETTE zone dans le studio (police, gras, italique, alignement) — elle prime ; la police ne
	vaut que pour les langues qui l'acceptent (`police_libre`)."""
	morceaux = []
	typo = typo or {}
	perso = {f for f, _u in rendu.polices_personnalisees()}
	familles = rendu.familles_disponibles() if familles is None else familles
	police_zone = typo.get("police") if typo.get("police") in familles else None
	for k, (code, t) in enumerate(textes.items()):
		lg = langues.get(code) or {}
		rtl, fam, libre = bool(lg.get("rtl")), _famille(lg, rendu.FAMILLE_TEXTES in perso), police_libre(lg)
		taille = taille_langue(taille_pt, k, rtl)
		facteur = taille_langue(1.0, k, rtl)
		if libre and police_zone:
			fam = police_zone
		commun = dict(rtl=rtl, couleur=couleur, facteur=facteur, police_libre=libre, familles=familles,
		              italique=bool(typo.get("italique")))
		if nom_zone == "nom":
			continue
		if nom_zone == "accroche" and t.get("accroche"):
			morceaux.append(html_bloc([t["accroche"]], taille_pt=taille, famille=fam, gras=typo.get("gras", True),
			                          align=typo.get("align") or "center", **commun))
		elif nom_zone == "caracteristiques" and t.get("caracteristiques"):
			if libre and not police_zone and police_bloc and police_bloc in familles:
				fam = police_bloc
			morceaux.append(html_bloc(t["caracteristiques"], taille_pt=taille, famille=fam, puces=True,
			                          gras=bool(typo.get("gras")), align=typo.get("align"), **commun))
		elif nom_zone == "avertissements" and t.get("avertissements"):
			morceaux.append(html_bloc(t["avertissements"], taille_pt=taille * 0.85, famille=fam,
			                          gras=bool(typo.get("gras")), align=typo.get("align"), **commun))
		elif nom_zone == "contact" and t.get("contact"):
			morceaux.append(html_bloc(t["contact"].splitlines(), taille_pt=taille * 0.85, famille=fam,
			                          gras=bool(typo.get("gras")), align=typo.get("align"), **commun))
	return "".join(morceaux)


# ------------------------------------------------------------------ composition


def html_zone(doc, zone: dict, textes: dict, langues: dict, familles: set,
              couleur: str = "#111827", fam_titres: str = "Noto Sans") -> str:
	"""Contenu et typographie communs à l'éditeur et au PDF, sans les repères techniques."""
	nom = zone["zone"]
	ty = typo_zone(zone, familles)
	style = style_zone(zone) or {}
	couleur = style.get("texte") or couleur
	if nom == "nom":
		texte = doc.get("nom_produit") or doc.get("article") or ""
		marge = min(CARTOUCHE_STYLE_MARGE_MM, zone["w"] / 4, zone["h"] / 4) if style.get("fond") else 0
		taille = ty.get("taille") or taille_nom(MM(zone["w"] - 2 * marge), MM(zone["h"] - 2 * marge), texte)
		return html_bloc([texte], taille_pt=taille, rtl=False, famille=ty.get("police") or fam_titres,
		                 couleur=couleur, gras=ty.get("gras", True), italique=bool(ty.get("italique")),
		                 align=ty.get("align") or "center")
	if nom == "texte_libre":
		return html_texte_libre(zone.get("texte"), ty, couleur, familles)
	if nom not in ZONES_TEXTE:
		return ""
	base = ty.get("taille") or {"accroche": 11.0, "caracteristiques": flt(doc.get("taille_caracteristiques")) or 8.5,
	                            "avertissements": 7.0, "contact": 7.0}[nom]
	return textes_pour_zone(nom, textes, langues, base, couleur,
	                       police_bloc=doc.get("police_caracteristiques"), familles=familles, typo=ty)


def composer(doc, variante, plan: dict, textes: dict, langues: dict, options: dict | None = None,
             rapport: dict | None = None) -> bytes:
	"""-> le PDF (page artwork + page technique). `rapport` (facultatif) reçoit les zones de texte
	que MuPDF a dû réduire pour les faire tenir : {"reductions": [{face, zone, echelle}]}."""
	import pymupdf

	options = options or {}
	rapport = rapport if rapport is not None else {}
	rapport.setdefault("reductions", [])
	archive, css = polices_archive(), css_base()
	familles = rendu.familles_disponibles()
	W, H = geometrie.format_page_pt(plan)
	pdf = pymupdf.open()
	page = pdf.new_page(width=W, height=H)

	identiques = bool(cint(doc.get("faces_identiques")))
	cotes = bool(cint(doc.get("cotes_identiques")))
	sans_cartouche = bool(cint(doc.get("pictos_sans_cartouche")))
	image_fond_url = doc.get("image_fond")
	# ⚠️ LE FOND CONTINU REMPLACE LES VISUELS IA DES FACES : c'est tout son sens — un seul motif
	# qui fait le tour. La variante IA (scène avec le produit) reste disponible en décochant
	# « fond continu » ; ici la photo du produit devient le héros posé sur le fond.
	continu = bool(cint(doc.get("fond_continu"))) and bool(image_fond_url)
	if continu:
		variante = None
	bande = geometrie.bande(plan) if continu else None
	# En mode continu, la bande est prise AVEC son fond perdu : les tranches tuilent exactement
	# les rectangles peints, et le motif déborde en coupe comme il se doit.
	if bande:
		rects = [rect_avec_fond_perdu(f, plan) for f in plan["faces"] if f["code"] in bande["faces"]]
		bx0, by0 = min(r[0] for r in rects), min(r[1] for r in rects)
		bx1, by1 = max(r[0] + r[2] for r in rects), max(r[1] + r[3] for r in rects)
		bande = dict(bande, x=bx0, y=by0, w=bx1 - bx0, h=by1 - by0)
	visuel_avant = fichiers.lire(variante.image) if (variante is not None and variante.image) else None
	image_fond = fichiers.lire(image_fond_url) if image_fond_url else None
	# Le fond : la couleur CHOISIE d'abord (demande utilisateur 23/09/2026 : « le background,
	# comment je le fais ? »), sinon la dominante du visuel IA, sinon celle de l'image de fond.
	dominantes = (couleurs_dominantes(visuel_avant) if visuel_avant
	              else couleurs_dominantes(image_fond) if image_fond else ["#e5e7eb", "#ffffff"])
	base = doc.get("couleur_fond") or dominantes[0]
	fond = _hex_rgb(base)
	couleur_texte = "#111827" if _luminance(base) > 0.5 else "#ffffff"
	logo = fichiers.lire(url_logo(doc)) if url_logo(doc) else None
	visuels = {}
	for code, champ in CHAMPS_FACES.items():
		url = getattr(variante, champ, None) if variante is not None else None
		if url:
			visuels[code] = fichiers.lire(url)
	if visuel_avant:
		visuels["avant"] = visuel_avant
		if identiques:
			visuels["arriere"] = visuel_avant
	if cotes and visuels.get("cote_droit"):
		visuels["cote_gauche"] = visuels["cote_droit"]     # côtés identiques : même visuel IA à gauche
	photo_hero = None
	photo_url = url_photo(doc)   # la photo de la fiche, sinon l'image de l'article
	fonds_faces = frappe.parse_json(doc.get("fonds_faces")) if doc.get("fonds_faces") else {}
	reglages = {f["code"]: reglage_fond(fonds_faces, f["code"]) for f in plan["faces"] if f["imprimable"]}
	# La photo héros sert dès qu'une face avant ne porte PAS de visuel IA : pas de variante, ou une face
	# avant réglée sur un autre fond dans le studio.
	if photo_url and (not visuel_avant or reglages.get("avant")):
		try:
			photo_hero = fondre_bords(fond_blanc_en_transparence(fichiers.lire(photo_url)))
		except Exception:
			photo_hero = fichiers.lire(photo_url)
	dpi = {}

	# Faces copiées (dos = avant, côté gauche = côté droit) : même CONTENU (zones, logo, cartouches,
	# pictos) et même visuel IA de face, mais le FOND CONTINU garde sa propre tranche de panorama :
	# précision utilisateur 24/09/2026 — « identique, c'est le contenu que je superpose ; les faces
	# peuvent différer pour la continuité de la vague ».
	mep_copies = frappe.parse_json(doc.get("mise_en_page")) if doc.get("mise_en_page") else None
	copies = faces_copiees(plan, identiques, cotes, mep_copies)
	# 1. fonds : rabats et pattes (aplat), puis faces imprimables (visuel ou aplat + bandeau)
	for face in plan["faces"]:
		r = rect_avec_fond_perdu(face, plan)
		if face["code"] == "patte":
			continue  # la patte de collage reste blanche : la colle n'aime pas l'encre
		page.draw_rect(pymupdf.Rect(*_rect_pt(*r)), color=None, fill=fond)
	avec_visuel, textes_face = set(), {}
	for face in plan["faces"]:
		if not face["imprimable"]:
			continue
		r = rect_avec_fond_perdu(face, plan)
		reg = reglages.get(face["code"])
		if reg and _poser_fond_regle(page, reg, r, face, image_fond, bande, dpi):
			if reg["mode"] in ("couleur", "blanc"):
				textes_face[face["code"]] = couleur_texte_sur(reg.get("couleur") or "#ffffff")
			continue
		src = face_source(plan, face["code"], copies)          # visuel IA de la source, fond de la face
		visuel = visuels.get(src["code"]) or visuels.get(face["code"])
		if visuel:
			avec_visuel.add(face["code"])
			from PIL import Image

			im = Image.open(io.BytesIO(visuel))
			x0, y0, x1, y1 = geometrie.cadrage(r[2], r[3], im.width, im.height)
			dpi[face["code"]] = geometrie.dpi_effectif(x1 - x0, r[2])
			poser_image(page, _rect_pt(*r), recadrer(visuel, r[2], r[3]), garder_proportions=False)
		elif image_fond and bande and face["code"] in bande["faces"]:
			# Fond continu : la tranche du panorama située à la place de CETTE face — jamais celle de sa
			# source, sinon la vague se rompt au pli.
			poser_image(page, _rect_pt(*r), tranche_panorama(image_fond, bande, r), garder_proportions=False)
		elif image_fond:
			# L'image de fond choisie couvre la face entière (recadrée, jamais déformée).
			poser_image(page, _rect_pt(*r), recadrer(image_fond, r[2], r[3]), garder_proportions=False)
		elif visuel_avant:
			hb = min(r[3] * 0.3, 40.0)
			poser_image(page, _rect_pt(r[0], r[1], r[2], hb), recadrer(bandeau(visuel_avant), r[2], hb), garder_proportions=False)
	# Sans visuel IA, la photo du produit est le héros de la face avant (et du dos miroir).
	mep_brut = frappe.parse_json(doc.get("mise_en_page")) if doc.get("mise_en_page") else {}
	sans_photo = avec_visuel | {c for c, reg in reglages.items() if reg and reg.get("photo_incluse")}
	if photo_hero and not any(z.get("zone") == "photo" for l in (mep_brut or {}).values() if isinstance(l, list) for z in l):
		for f in plan["faces"]:
			if f["code"] in sans_photo:
				continue      # un visuel IA (variante, face composée) montre déjà le produit
			if f["code"] == "avant" or (identiques and f["code"] == "arriere" and "cote_droit" in {x["code"] for x in plan["faces"] if x["imprimable"]}):
				poser_image(page, _rect_pt(*hero_photo_rect(f)), photo_hero, garder_proportions=True)

	# 2. contenus vectoriels par face
	logos_par_url = {}
	ean = None
	if doc.type_code_barres in ("EAN-13", "EAN-13 + QR") and doc.code_barres:
		if codes.valider_ean13(doc.code_barres):
			ean = codes.ean13_svg(doc.code_barres)
	qr = codes.qr_svg(doc.url_qr, doc.get("couleur_qr")) if doc.type_code_barres in ("QR", "EAN-13 + QR") and doc.url_qr else None
	pictos_svg = [(p.pictogramme, pictos.svg_bytes(p.pictogramme)) for p in (doc.pictogrammes or [])]
	pictos_svg = [(c, s) for c, s in pictos_svg if s]
	from aquaworld_ia.emballage import pictos_images
	images_pictos = pictos_images.charger(doc)
	# Un tampon (badge IA, 06/10/2026) a sa propre forme : jamais de carré blanc derrière lui.
	tampons = set(frappe.get_all("Aquaworld IA Pictogramme", filters={"categorie": "Tampon", "code": ["in", [c for c, _s in pictos_svg] or [""]]},
	                             pluck="code")) if pictos_svg else set()
	nom_produit = doc.nom_produit or doc.article
	fam_titres = famille_titres(rendu.FAMILLE_TITRES in {f for f, _u in rendu.polices_personnalisees()})
	premiere = next(iter(langues.values()), {}) if langues else {}
	contenu = {
		"logo": bool(logo), "nom": True, "accroche": bool(textes), "caracteristiques": bool(textes),
		"avertissements": bool(textes), "contact": bool(textes), "pictos": len(pictos_svg),
		"code_barres": geometrie.EAN_NOMINAL_MM if (ean or qr) else None,
	}
	mise_en_page = frappe.parse_json(doc.get("mise_en_page")) if doc.get("mise_en_page") else None
	zones = zones_par_face(plan, contenu, identiques, mise_en_page, cotes)
	# Un QR posé à la main (zone « QR code », 06/10/2026 : « si je veux l'ajouter en face ? ») est LE QR de
	# l'emballage : les zones code-barres automatiques n'en impriment plus un second.
	qr_place = any(z["zone"] == "code_barres" and z.get("code") == "qr" for liste in zones.values() for z in liste)
	photo_zone = None
	if any(z["zone"] == "photo" for liste in zones.values() for z in liste):
		try:
			photo_zone = fondre_bords(fond_blanc_en_transparence(fichiers.lire(photo_url))) if photo_url else None
		except Exception:
			photo_zone = fichiers.lire(photo_url) if photo_url else None
	for face in plan["faces"]:
		if not face["imprimable"]:
			continue
		for z in zones[face["code"]]:
			rect = _rect_pt(z["x"], z["y"], z["w"], z["h"])
			decalage = decalage_zone(z)
			if z["zone"] == "photo":
				# Une face qui porte un visuel IA (variante de face avant, faces IA) montre déjà le produit :
				# une zone « photo » dessus le doublerait (constaté sur EMB-2026-0002 le 24/09/2026).
				if photo_zone and face["code"] not in sans_photo:
					poser_image(page, rect, photo_zone, garder_proportions=True, rotation=rotation_zone(z), zoom=zoom_zone(z), decalage=decalage)
			style = style_zone(z)
			couleur_zone = (style or {}).get("texte") or textes_face.get(face["code"], couleur_texte)
			if z["zone"] == "logo" and (z.get("logo") or logo):
				# Variante de logo propre à cette face (bibliothèque), sinon le logo du design.
				logo_face = logo
				source_logo = url_logo(doc)
				if z.get("logo"):
					try:
						logo_face = logos_par_url.setdefault(z["logo"], fichiers.lire(z["logo"]))
						source_logo = z["logo"]
					except Exception:
						logo_face = logo
				if logo_face:
					poser_logo(page, rect, logo_face, rotation=rotation_zone(z), zoom=zoom_zone(z), centre=centre_zone(z, source_logo), decalage=decalage)
			elif z["zone"] == "nom":
				interieur = dessiner_cartouche(page, rect, style)
				poser_texte(page, interieur, html_zone(doc, z, textes, langues, familles, couleur_zone, fam_titres), archive, css, decalage=decalage, cadre=rect)
			elif z["zone"] in ("accroche", "caracteristiques", "avertissements", "contact", "texte_libre"):
				contenu_html = html_zone(doc, z, textes, langues, familles, couleur_zone, fam_titres)
				if contenu_html:
					if style and style.get("fond"):
						echelle = poser_texte(page, dessiner_cartouche(page, rect, style), contenu_html, archive, css, decalage=decalage, cadre=rect)
					else:
						panneau = panneau_pour(z["zone"], couleur_texte, face["code"] in visuels or bool(image_fond))
						if panneau:
							m = MM(CARTOUCHE_MARGE_MM)
							h_texte = hauteur_texte(rect, contenu_html, archive, css)
							page.draw_rect(pymupdf.Rect(rect[0] - m, rect[1] - m, rect[2] + m, rect[1] + h_texte + m),
							               color=None, fill=panneau[0], fill_opacity=panneau[1])
						echelle = poser_texte(page, rect, contenu_html, archive, css, decalage=decalage, cadre=rect)
					# Les tailles choisies ligne par ligne sont des MAXIMUMS : MuPDF réduit tout le bloc s'il ne
					# tient pas dans sa zone. Le dire, sinon « 14 pt » imprimé en 9 pt paraît ignoré.
					if echelle < 0.9:
						rapport["reductions"].append({"face": face["code"], "libelle": face.get("libelle") or face["code"],
						                              "zone": z["zone"], "echelle": round(echelle, 2)})
			elif z["zone"] in ("code_barres", "pictos"):
				poser_symboles(page, elements_symboles(z, face["code"], pictos_svg=pictos_svg,
				                                      images_pictos=images_pictos,
				                                      tampons=tampons, sans_cartouche=sans_cartouche,
				                                      couleur=couleur_texte, ean=ean, qr=qr, qr_place=qr_place), rect=rect, decalage=decalage)

	# 3. calque « Découpe et plis » (activable dans le lecteur, imprimé par l'imprimeur sur demande)
	ocg = pdf.add_ocg("Découpe et plis", on=True)
	for x1, y1, x2, y2 in plan["traits"]["coupe"]:
		page.draw_line((MM(x1), MM(y1)), (MM(x2), MM(y2)), color=(1, 0, 0), width=0.25, oc=ocg)
	for x1, y1, x2, y2 in plan["traits"]["pli"]:
		page.draw_line((MM(x1), MM(y1)), (MM(x2), MM(y2)), color=(0, 0.3, 1), width=0.25, dashes="[2 2] 0", oc=ocg)
	fp = plan.get("fond_perdu", 0) or 0
	page.draw_rect(pymupdf.Rect(MM(fp), MM(fp), W - MM(fp), H - MM(fp)), color=(1, 0, 1), width=0.25, dashes="[1 1] 0", oc=ocg)
	for rz in plan.get("reserves") or []:
		# Bande réservée (repli agrafé) : hachurée en ocre sur le calque, pour l'imprimeur et le contrôle.
		ocre = (0.71, 0.33, 0.04)
		page.draw_rect(pymupdf.Rect(MM(rz["x"]), MM(rz["y"]), MM(rz["x"] + rz["w"]), MM(rz["y"] + rz["h"])),
		               color=ocre, width=0.25, dashes="[2 1] 0", oc=ocg)
		for x1, y1, x2, y2 in geometrie.hachures(rz["x"], rz["y"], rz["w"], rz["h"], 6.0):
			page.draw_line((MM(x1), MM(y1)), (MM(x2), MM(y2)), color=ocre, width=0.2, oc=ocg)
		page.insert_text((MM(rz["x"]) + 6, MM(rz["y"] + rz["h"] / 2) + 2.5),
		                 "%s : ni texte ni logo" % rz.get("libelle", "Réservé"), fontsize=7, color=ocre, oc=ocg)

	# 4. page technique
	fiche = pdf.new_page(width=595.28, height=841.89)
	fiche.insert_htmlbox(pymupdf.Rect(36, 36, 559, 806), fiche_technique_html(doc, variante, plan, textes, langues, dpi, pictos_svg, ean, qr),
	                     css=css + "table{border-collapse:collapse}td,th{border:0.5pt solid #999;padding:3pt 5pt;font-size:9pt}",
	                     archive=archive)
	pdf.set_metadata({"title": "Plan à plat — %s" % nom_produit, "subject": doc.name, "creator": "Aquaworld IA"})
	sortie = io.BytesIO()
	pdf.save(sortie, garbage=3, deflate=True)
	return sortie.getvalue()


def _luminance(hexa: str) -> float:
	r, g, b = _hex_rgb(hexa)
	return 0.2126 * r + 0.7152 * g + 0.0722 * b


def fiche_technique_html(doc, variante, plan, textes, langues, dpi, pictos_svg, ean, qr) -> str:
	esc = html.escape
	lignes_faces = "".join(
		"<tr><td>%s</td><td>%.1f × %.1f</td><td>%s</td><td>%s</td></tr>" % (
			esc(f["libelle"]), f["w"], f["h"], "oui" if f["imprimable"] else "—",
			("%.0f dpi" % dpi[f["code"]]) if f["code"] in dpi else ("aplat + bandeau" if f["imprimable"] else "—"))
		for f in plan["faces"])
	return (
		"<h2 style=\"font-family:'Noto Sans'\">Fiche technique — %s</h2>" % esc(doc.nom_produit or doc.article)
		+ "<p style=\"font-family:'Noto Sans';font-size:10pt\">Fiche %s · Article %s · %s · Type : %s%s</p>" % (
			esc(doc.name), esc(doc.article),
			("Variante %s « %s »" % (variante.numero, esc(variante.titre or ""))) if variante is not None
			else "Sans visuel IA (fond choisi + photo produit)",
			esc(plan["type"]), (" · Dos identique à l'avant" if cint(doc.get("faces_identiques")) else "")
			+ (" · Côtés identiques (EAN et avertissements sur les deux côtés)" if cint(doc.get("cotes_identiques")) else "")
			+ (" · Pictogrammes sans cartouche (monochromes recolorés à la couleur du texte)" if cint(doc.get("pictos_sans_cartouche")) else ""))
		+ "<p style=\"font-family:'Noto Sans';font-size:10pt\">Feuille : <b>%.1f × %.1f mm</b> (fond perdu %.1f mm inclus) · "
		  "Dimensions : L %.1f × H %.1f × P %.1f mm%s · Langues : %s · EAN : %s · QR : %s · Pictogrammes : %s</p>" % (
			plan["feuille"]["w"], plan["feuille"]["h"], plan.get("fond_perdu", 0), plan["dimensions"]["L"],
			plan["dimensions"]["H"], plan["dimensions"]["P"],
			(" · Repli supérieur agrafé R %.1f mm, compris dans H : fond imprimé, ni texte ni logo" % plan["dimensions"]["R"])
			if plan["dimensions"].get("R") else "",
			esc(", ".join(langues.keys()) or "—"),
			esc(doc.code_barres or "—") if ean else "—", esc(doc.url_qr or "—") if qr else "—",
			esc(", ".join(c for c, _s in pictos_svg) or "—"))
		+ "<table style=\"font-family:'Noto Sans'\"><tr><th>Face</th><th>Dimensions (mm)</th><th>Imprimable</th><th>Visuel source</th></tr>%s</table>" % lignes_faces
		+ "<p style=\"font-family:'Noto Sans';font-size:9pt;color:#555\">Couleurs RVB — conversion CMJN, tons directs et surimpressions "
		  "à la charge de l'imprimeur. Plan de découpe générique à valider par le cartonnier. Les textes et les tracés SVG "
		  "restent vectoriels. Les photos, logos bitmap et images intégrées dans les SVG dépendent de leur résolution "
		  "à la taille imprimée. L’agrandissement ne restitue pas nécessairement les détails absents de la source.</p>"
	)


def _langues(doc) -> dict:
	from aquaworld_ia.emballage.textes import _langues_du_design

	return {l["code"]: l for l in _langues_du_design(doc)}


@frappe.whitelist()
def composer_et_attacher(design: str, variante: int = 0) -> dict:
	from aquaworld_ia.emballage import contenus, exports

	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("write")
	revision, ancien_pdf = str(doc.modified), doc.get("plan_a_plat")
	erreurs = exports.verifier(doc)
	if erreurs:
		frappe.throw(" ".join(erreurs))
	v = next((x for x in doc.variantes if x.numero == cint(variante)), None)
	if not v or v.statut != "Prête" or not v.image:
		# Le contenu manuel suffit ; une variante IA est facultative.
		v = None
	# Un emballage simple est composable sans génération IA ni sélection de couleur.
	doc.variante_choisie = v.numero if v else 0
	plan = plan_du_design(doc)
	problemes = geometrie.verifier(plan)
	if problemes:
		frappe.throw(_("Plan impossible : {0}").format(" ; ".join(problemes)))
	textes = contenus.imprimes(doc)
	langues = _langues(doc)
	rapport = {}
	pdf = composer(doc, v, plan, textes or {}, langues, rapport=rapport)
	rapport_resolution = None
	if cint(doc.get("ameliorer_images_pdf")):
		from aquaworld_ia.emballage import resolution
		from aquaworld_ia.emballage.variantes import GENRE, EVENEMENT
		from aquaworld_ia.ia import etat

		def progression(i, total):
			if etat.lire_etat(GENRE, design).get("tache") == "resolution_pdf":
				etat.progresser(GENRE, design, f"Image {i+1}/{total} : préparation pour l’impression…",
					10 + int(80*i/max(1, total)), EVENEMENT, frappe.session.user)

		pdf, rapport_resolution = resolution.preparer_pdf(pdf, progression)
	# Verrou bref après le calcul : ne jamais publier un export issu d'une autre
	# révision, ni écraser un PDF concurrent terminé pendant le traitement.
	actuel = frappe.db.get_value("Design Emballage", design, ["modified", "plan_a_plat"], as_dict=True, for_update=True)
	if not actuel or str(actuel.modified) != revision or actuel.plan_a_plat != ancien_pdf:
		frappe.throw(_("Le design ou son PDF a changé pendant la préparation. Relancez l’export."))
	fichier = save_file("%s-plan-a-plat.pdf" % doc.name, pdf, "Design Emballage", doc.name, is_private=1)
	import pymupdf

	with pymupdf.open("pdf", pdf) as document:
		apercu = document[0].get_pixmap(dpi=100).tobytes("png")
	apercu_f = save_file("%s-apercu.png" % doc.name, apercu, "Design Emballage", doc.name, is_private=1)
	valeurs = {"plan_a_plat": fichier.file_url, "apercu_plan": apercu_f.file_url, "statut": "Plan prêt",
	           "empreinte_plan": exports.empreinte(doc), "variante_choisie": doc.variante_choisie,
	           "rapport_resolution": json.dumps(rapport_resolution, ensure_ascii=False) if rapport_resolution else None}
	frappe.db.set_value("Design Emballage", design, valeurs, update_modified=False)
	frappe.db.commit()
	return {"plan_a_plat": fichier.file_url, "apercu_plan": apercu_f.file_url, "feuille": plan["feuille"],
	        "reductions": rapport.get("reductions") or [], "resolution": rapport_resolution}
