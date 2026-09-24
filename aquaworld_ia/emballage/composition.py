"""Étape 3 : le plan à plat imprimeur, à l'échelle, en PDF (PyMuPDF).

Page 1 « Artwork » : chaque face imprimable reçoit son visuel (IA) ou un aplat de la couleur
dominante de la face avant + bandeau ; par-dessus, en VECTORIEL : logo, textes par langue,
EAN-13 / QR, pictogrammes. Le fond perdu ne s'étend que sur les arêtes de COUPE (jamais dans un
pli : le panneau voisin y a son propre visuel). Un calque optionnel (OCG) porte coupes, plis et
limite de fond perdu. Page 2 : fiche technique.
"""

from __future__ import annotations

import html
import io
import re
import json

import frappe
from frappe import _
from frappe.utils import cint, flt
from frappe.utils.file_manager import save_file

from aquaworld_ia.emballage import codes, geometrie, pictos
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
                    "code_barres", "photo")


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


#: Ce qu'une zone dessinée à la main transporte en plus de sa géométrie : son style et, pour un
#: logo, le fichier d'une variante propre à cette face.
CLES_ZONE_CONSERVEES = ("style", "logo", "pictos")


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
	import pymupdf

	return pymupdf.open("pdf", pymupdf.open("svg", svg).convert_to_pdf())


def poser_svg(page, rect, svg: bytes) -> None:
	import pymupdf

	src = svg_vers_pdf(svg)
	page.show_pdf_page(pymupdf.Rect(*rect), src, 0, keep_proportion=True)


def poser_image(page, rect, octets: bytes, garder_proportions: bool = True) -> None:
	import pymupdf

	page.insert_image(pymupdf.Rect(*rect), stream=octets, keep_proportion=garder_proportions)


def fond_blanc_en_transparence(octets: bytes, seuil: int = 235) -> bytes:
	"""Un logo donné en PHOTO (JPEG/PNG sur fond blanc) arrive avec son rectangle blanc : posé sur
	un visuel, il ferait une étiquette collée. Si les quatre coins sont blancs, le blanc devient
	transparent (demande utilisateur 23/09/2026 : « la marque, je la donne par photo »). Un logo
	dont les coins sont colorés est laissé tel quel — on ne devine pas. Pur."""
	from PIL import Image

	im = Image.open(io.BytesIO(octets)).convert("RGBA")
	w, h = im.size
	if w < 2 or h < 2:
		return octets
	coins = [im.getpixel((0, 0)), im.getpixel((w - 1, 0)), im.getpixel((0, h - 1)), im.getpixel((w - 1, h - 1))]
	if not all(min(c[:3]) >= seuil and c[3] > 0 for c in coins):
		return octets
	pixels = im.getdata()
	im.putdata([(r, g, b, 0) if min(r, g, b) >= seuil else (r, g, b, a) for r, g, b, a in pixels])
	sortie = io.BytesIO()
	im.save(sortie, format="PNG")
	return sortie.getvalue()


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


def svg_est_monochrome(svg: bytes) -> bool:
	"""Vrai si le SVG n'emploie qu'une seule couleur d'encre (le blanc, none et currentColor ne
	comptent pas) : un pictogramme normalisé, pas un logo de certification en couleurs. Pur."""
	texte = svg.decode("utf-8", "replace")
	encres = set()
	for val in re.findall(r"(?:fill|stroke|stop-color)\s*[=:]\s*[\"']?\s*([^\"';)>]+)", texte):
		c = _rgb(val)
		if c is not None and min(c) < 235:
			encres.add(c)
	return len(encres) <= 1


def recolorer_svg_monochrome(svg: bytes, couleur: str) -> bytes:
	"""Un pictogramme monochrome prend la couleur demandée (celle du texte de la face) : posé sans
	cartouche sur un fond sombre, un picto noir serait invisible. Le blanc et « none » sont gardés
	(les évidements restent des évidements) ; un SVG à plusieurs encres — certification en couleurs —
	revient tel quel. Sans fill explicite, le SVG hérite du noir : la couleur est posée à la racine. Pur."""
	if not svg_est_monochrome(svg):
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


def poser_logo(page, rect, logo: bytes) -> None:
	debut = logo[:300].lstrip().lower()
	if debut.startswith(b"<svg") or (debut.startswith(b"<?xml") and b"<svg" in logo[:2000].lower()):
		poser_svg(page, rect, logo)
	else:
		try:
			logo = fond_blanc_en_transparence(logo)
		except Exception:
			pass
		poser_image(page, rect, logo)


def _rect_pt(x, y, w, h):
	return (MM(x), MM(y), MM(x + w), MM(y + h))


# ------------------------------------------------------------------ textes


def html_bloc(lignes: list[str], *, taille_pt: float, rtl: bool, famille: str, couleur: str = "#111827",
              gras: bool = False, puces: bool = False, align: str | None = None) -> str:
	style = ("font-family:'%s';font-size:%.1fpt;color:%s;direction:%s;%sfont-weight:%d;line-height:1.25"
	         % (famille, taille_pt, couleur, "rtl" if rtl else "ltr", alignement_css(align, rtl),
	            700 if gras else 400))
	# ⚠️ PAS DE <ul> : le moteur d'insert_htmlbox pose le marqueur de liste à GAUCHE quoi qu'en
	# dise `direction:rtl` (constaté sur la fiche EMB-2026-0001 le 23/09/2026 : puces arabes
	# à gauche du texte, bloc collé à gauche). Une puce typographique dans le paragraphe suit,
	# elle, le sens d'écriture.
	prefixe = PUCE + " " if puces else ""
	out = []
	for l in lignes:
		if l.startswith(TITRE):
			# Un intertitre (texte brut de l'utilisateur : « SPECIFICATIONS », « Inlet :») : gras, sans puce.
			out.append("<p style=\"%s;font-weight:700;margin:0.5em 0 0.2em 0\">%s</p>" % (style, html.escape(l[len(TITRE):].strip())))
		else:
			out.append("<p style=\"%s;margin:0 0 0.3em 0\">%s%s</p>" % (style, prefixe, html.escape(l)))
	return "".join(out)


PUCE = "•"
TITRE = "## "


def lignes_brutes(texte: str | None) -> list[str]:
	"""Le texte saisi à l'étape 2, ligne par ligne, prêt pour `html_bloc` : lignes vides
	ignorées, intertitres (tout en capitales, ou terminés par « : ») marqués `## `. Pur."""
	out = []
	for brut in (texte or "").splitlines():
		l = brut.strip()
		if not l:
			continue
		lettres = [c for c in l if c.isalpha()]
		titre = (len(lettres) >= 3 and all(c.isupper() for c in lettres)) or l.endswith(":")
		out.append((TITRE + l.rstrip(":").strip()) if titre else l)
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


def poser_texte(page, rect, contenu_html: str, archive, css: str) -> float:
	import pymupdf

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


def textes_pour_zone(nom_zone: str, textes: dict, langues: dict, taille_pt: float, couleur: str) -> str:
	"""Le HTML d'une zone, toutes langues empilées (première langue plus grande)."""
	morceaux = []
	perso = {f for f, _u in rendu.polices_personnalisees()}
	for k, (code, t) in enumerate(textes.items()):
		lg = langues.get(code) or {}
		rtl, fam = bool(lg.get("rtl")), _famille(lg, rendu.FAMILLE_TEXTES in perso)
		taille = taille_langue(taille_pt, k, rtl)
		if nom_zone == "nom":
			continue
		if nom_zone == "accroche" and t.get("accroche"):
			morceaux.append(html_bloc([t["accroche"]], taille_pt=taille, rtl=rtl, famille=fam, couleur=couleur, gras=True,
			                          align="center"))
		elif nom_zone == "caracteristiques" and t.get("caracteristiques"):
			morceaux.append(html_bloc(t["caracteristiques"], taille_pt=taille, rtl=rtl, famille=fam, couleur=couleur, puces=True))
		elif nom_zone == "avertissements" and t.get("avertissements"):
			morceaux.append(html_bloc(t["avertissements"], taille_pt=taille * 0.85, rtl=rtl, famille=fam, couleur=couleur))
		elif nom_zone == "contact" and t.get("contact"):
			morceaux.append(html_bloc(t["contact"].splitlines(), taille_pt=taille * 0.85, rtl=rtl, famille=fam, couleur=couleur))
	return "".join(morceaux)


# ------------------------------------------------------------------ composition


def composer(doc, variante, plan: dict, textes: dict, langues: dict, options: dict | None = None) -> bytes:
	"""-> le PDF (page artwork + page technique)."""
	import pymupdf

	options = options or {}
	archive, css = polices_archive(), css_base()
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
	if not visuel_avant and photo_url:
		try:
			photo_hero = fond_blanc_en_transparence(fichiers.lire(photo_url))
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
	for face in plan["faces"]:
		if not face["imprimable"]:
			continue
		r = rect_avec_fond_perdu(face, plan)
		src = face_source(plan, face["code"], copies)          # visuel IA de la source, fond de la face
		visuel = visuels.get(src["code"]) or visuels.get(face["code"])
		if visuel:
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
	if photo_hero and not any(z.get("zone") == "photo" for l in (mep_brut or {}).values() if isinstance(l, list) for z in l):
		for f in plan["faces"]:
			if f["code"] == "avant" or (identiques and f["code"] == "arriere" and "cote_droit" in {x["code"] for x in plan["faces"] if x["imprimable"]}):
				poser_image(page, _rect_pt(*hero_photo_rect(f)), photo_hero, garder_proportions=True)

	# 2. contenus vectoriels par face
	logos_par_url = {}
	ean = None
	if doc.type_code_barres in ("EAN-13", "EAN-13 + QR") and doc.code_barres:
		if codes.valider_ean13(doc.code_barres):
			ean = codes.ean13_svg(doc.code_barres)
	qr = codes.qr_svg(doc.url_qr) if doc.type_code_barres in ("QR", "EAN-13 + QR") and doc.url_qr else None
	pictos_svg = [(p.pictogramme, pictos.svg_bytes(p.pictogramme)) for p in (doc.pictogrammes or [])]
	pictos_svg = [(c, s) for c, s in pictos_svg if s]
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
	photo_zone = None
	if any(z["zone"] == "photo" for liste in zones.values() for z in liste):
		try:
			photo_zone = fond_blanc_en_transparence(fichiers.lire(photo_url)) if photo_url else None
		except Exception:
			photo_zone = fichiers.lire(photo_url) if photo_url else None
	for face in plan["faces"]:
		if not face["imprimable"]:
			continue
		for z in zones[face["code"]]:
			rect = _rect_pt(z["x"], z["y"], z["w"], z["h"])
			if z["zone"] == "photo":
				if photo_zone:
					poser_image(page, rect, photo_zone, garder_proportions=True)
			style = style_zone(z)
			couleur_zone = (style or {}).get("texte") or couleur_texte
			if z["zone"] == "logo" and (z.get("logo") or logo):
				# Variante de logo propre à cette face (bibliothèque), sinon le logo du design.
				logo_face = logo
				if z.get("logo"):
					try:
						logo_face = logos_par_url.setdefault(z["logo"], fichiers.lire(z["logo"]))
					except Exception:
						logo_face = logo
				if logo_face:
					poser_logo(page, rect, logo_face)
			elif z["zone"] == "nom":
				interieur = dessiner_cartouche(page, rect, style)
				taille = taille_nom(interieur[2] - interieur[0], interieur[3] - interieur[1], nom_produit)
				poser_texte(page, interieur, html_bloc([nom_produit], taille_pt=taille, rtl=False, famille=fam_titres,
				                                       couleur=couleur_zone, gras=True, align="center"), archive, css)
			elif z["zone"] in ("accroche", "caracteristiques", "avertissements", "contact"):
				base = {"accroche": 11.0, "caracteristiques": 8.5, "avertissements": 7.0, "contact": 7.0}[z["zone"]]
				contenu_html = textes_pour_zone(z["zone"], textes, langues, base, couleur_zone)
				if contenu_html:
					if style and style.get("fond"):
						poser_texte(page, dessiner_cartouche(page, rect, style), contenu_html, archive, css)
						continue
					panneau = panneau_pour(z["zone"], couleur_texte, face["code"] in visuels or bool(image_fond))
					if panneau:
						m = MM(CARTOUCHE_MARGE_MM)
						h_texte = hauteur_texte(rect, contenu_html, archive, css)
						page.draw_rect(pymupdf.Rect(rect[0] - m, rect[1] - m, rect[2] + m, rect[1] + h_texte + m),
						               color=None, fill=panneau[0], fill_opacity=panneau[1])
					poser_texte(page, rect, contenu_html, archive, css)
			elif z["zone"] == "code_barres":
				if ean:
					fond_blanc = pymupdf.Rect(*rect)
					page.draw_rect(fond_blanc, color=None, fill=(1, 1, 1))
					poser_svg(page, rect, ean)
				elif qr:
					cote = min(rect[2] - rect[0], rect[3] - rect[1])
					page.draw_rect(pymupdf.Rect(rect[2] - cote, rect[3] - cote, rect[2], rect[3]), color=None, fill=(1, 1, 1))
					poser_svg(page, (rect[2] - cote, rect[3] - cote, rect[2], rect[3]), qr)
				if ean and qr and face["code"] == "arriere":
					cote = MM(min(18.0, z["h"]))
					page.draw_rect(pymupdf.Rect(rect[0] - cote - MM(2), rect[3] - cote, rect[0] - MM(2), rect[3]), color=None, fill=(1, 1, 1))
					poser_svg(page, (rect[0] - cote - MM(2), rect[3] - cote, rect[0] - MM(2), rect[3]), qr)
			elif z["zone"] == "pictos" and pictos_svg:
				# Une zone peut ne montrer que certains pictogrammes (demande utilisateur 24/09/2026 :
				# « NSF seul sur l'avant ») ; sans sélection, elle les montre tous.
				choisis = z.get("pictos") if isinstance(z.get("pictos"), list) and z.get("pictos") else None
				liste = [(c, s) for c, s in pictos_svg if not choisis or c in choisis]
				taille = MM(taille_pictos(z["w"], z["h"], len(liste)))
				x = rect[0]
				for _code, svg in liste:
					if taille <= 0:
						break
					if sans_cartouche:
						# Demande utilisateur 24/09/2026 : posé en transparence ; un picto monochrome prend
						# la couleur du texte de la face pour rester lisible sur le fond.
						if est_svg(svg):
							svg = recolorer_svg_monochrome(svg, couleur_texte)
					else:
						page.draw_rect(pymupdf.Rect(x, rect[1], x + taille, rect[1] + taille), color=None, fill=(1, 1, 1))
					# Un pictogramme peut être une image à soi (certificat scanné) : même détection que le logo.
					poser_logo(page, (x + 1, rect[1] + 1, x + taille - 1, rect[1] + taille - 1), svg)
					x += taille + MM(PICTOS_ECART_MM)

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
		+ "<table style=\"font-family:'Noto Sans'\"><tr><th>Face</th><th>Dimensions (mm)</th><th>Imprimable</th><th>Visuel</th></tr>%s</table>" % lignes_faces
		+ "<p style=\"font-family:'Noto Sans';font-size:9pt;color:#555\">Couleurs RVB — conversion CMJN, tons directs et surimpressions "
		  "à la charge de l'imprimeur. Plan de découpe générique à valider par le cartonnier. Textes, logo, codes et pictogrammes "
		  "sont vectoriels ; les visuels sont des images IA à la résolution indiquée (300 dpi ≈ 13 cm au plus).</p>"
	)


def _langues(doc) -> dict:
	from aquaworld_ia.emballage.textes import _langues_du_design

	return {l["code"]: l for l in _langues_du_design(doc)}


@frappe.whitelist()
def composer_et_attacher(design: str, variante: int) -> dict:
	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("write")
	v = next((x for x in doc.variantes if x.numero == cint(variante)), None)
	if not v or v.statut != "Prête" or not v.image:
		# Sans variante IA, on compose quand même si l'utilisateur a choisi son fond : couleur
		# ou image, plus la photo du produit en héros. C'est l'emballage « sans IA ».
		if doc.get("couleur_fond") or doc.get("image_fond"):
			v = None
		else:
			frappe.throw(_("Choisissez une variante prête, ou définissez un fond (couleur ou image) pour composer sans IA."))
	plan = plan_du_design(doc)
	problemes = geometrie.verifier(plan)
	if problemes:
		frappe.throw(_("Plan impossible : {0}").format(" ; ".join(problemes)))
	textes = frappe.parse_json(doc.textes_ia) if doc.textes_ia else {}
	langues = _langues(doc)
	if not textes:
		# Rien de préparé par l'IA : le texte brut de l'étape 2 s'imprime tel quel.
		textes = textes_bruts(doc.caracteristiques, doc.avertissements, doc.contact, next(iter(langues), "fr"))
	pdf = composer(doc, v, plan, textes or {}, langues)
	fichier = save_file("%s-plan-a-plat.pdf" % doc.name, pdf, "Design Emballage", doc.name, is_private=1)
	import pymupdf

	apercu = pymupdf.open("pdf", pdf)[0].get_pixmap(dpi=100).tobytes("png")
	apercu_f = save_file("%s-apercu.png" % doc.name, apercu, "Design Emballage", doc.name, is_private=1)
	valeurs = {"plan_a_plat": fichier.file_url, "apercu_plan": apercu_f.file_url, "statut": "Plan prêt"}
	if v is not None:
		valeurs["variante_choisie"] = cint(variante)
	frappe.db.set_value("Design Emballage", design, valeurs, update_modified=False)
	frappe.db.commit()
	return {"plan_a_plat": fichier.file_url, "apercu_plan": apercu_f.file_url, "feuille": plan["feuille"]}
