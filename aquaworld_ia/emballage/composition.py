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
import json

import frappe
from frappe import _
from frappe.utils import cint, flt
from frappe.utils.file_manager import save_file

from aquaworld_ia.emballage import codes, geometrie, pictos
from aquaworld_ia.emballage.variantes import CHAMPS_FACES, plan_du_design, url_logo
from aquaworld_ia.ia import fichiers
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
		if contenu.get("pictos"):
			taille = min(w / max(1, contenu["pictos"]) * 0.8, h * 0.1)
			zone("pictos", x, bas - taille, w, taille)
			bas -= taille + h * 0.02
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


def poser_logo(page, rect, logo: bytes) -> None:
	debut = logo[:300].lstrip().lower()
	if debut.startswith(b"<svg") or (debut.startswith(b"<?xml") and b"<svg" in logo[:2000].lower()):
		poser_svg(page, rect, logo)
	else:
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
	return "".join("<p style=\"%s;margin:0 0 0.3em 0\">%s%s</p>" % (style, prefixe, html.escape(l)) for l in lignes)


PUCE = "•"


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


def _famille(langue: dict) -> str:
	return langue.get("police") or ("Noto Naskh Arabic" if langue.get("rtl") else "Noto Sans")


def textes_pour_zone(nom_zone: str, textes: dict, langues: dict, taille_pt: float, couleur: str) -> str:
	"""Le HTML d'une zone, toutes langues empilées (première langue plus grande)."""
	morceaux = []
	for k, (code, t) in enumerate(textes.items()):
		lg = langues.get(code) or {}
		rtl, fam = bool(lg.get("rtl")), _famille(lg)
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

	visuel_avant = fichiers.lire(variante.image) if variante.image else None
	dominantes = couleurs_dominantes(visuel_avant) if visuel_avant else ["#e5e7eb", "#ffffff"]
	fond = _hex_rgb(dominantes[0])
	couleur_texte = "#111827" if _luminance(dominantes[0]) > 0.5 else "#ffffff"
	logo = fichiers.lire(url_logo(doc)) if url_logo(doc) else None
	visuels = {}
	for code, champ in CHAMPS_FACES.items():
		url = getattr(variante, champ, None)
		if url:
			visuels[code] = fichiers.lire(url)
	if visuel_avant:
		visuels["avant"] = visuel_avant
	dpi = {}

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
		visuel = visuels.get(face["code"])
		if visuel:
			from PIL import Image

			im = Image.open(io.BytesIO(visuel))
			x0, y0, x1, y1 = geometrie.cadrage(r[2], r[3], im.width, im.height)
			dpi[face["code"]] = geometrie.dpi_effectif(x1 - x0, r[2])
			poser_image(page, _rect_pt(*r), recadrer(visuel, r[2], r[3]), garder_proportions=False)
		elif visuel_avant:
			hb = min(r[3] * 0.3, 40.0)
			poser_image(page, _rect_pt(r[0], r[1], r[2], hb), recadrer(bandeau(visuel_avant), r[2], hb), garder_proportions=False)

	# 2. contenus vectoriels par face
	ean = None
	if doc.type_code_barres in ("EAN-13", "EAN-13 + QR") and doc.code_barres:
		if codes.valider_ean13(doc.code_barres):
			ean = codes.ean13_svg(doc.code_barres)
	qr = codes.qr_svg(doc.url_qr) if doc.type_code_barres in ("QR", "EAN-13 + QR") and doc.url_qr else None
	pictos_svg = [(p.pictogramme, pictos.svg_bytes(p.pictogramme)) for p in (doc.pictogrammes or [])]
	pictos_svg = [(c, s) for c, s in pictos_svg if s]
	nom_produit = doc.nom_produit or doc.article
	premiere = next(iter(langues.values()), {}) if langues else {}
	for face in plan["faces"]:
		if not face["imprimable"]:
			continue
		contenu = {
			"logo": bool(logo), "nom": True, "accroche": bool(textes), "caracteristiques": bool(textes),
			"avertissements": bool(textes), "contact": bool(textes), "pictos": len(pictos_svg),
			"code_barres": geometrie.EAN_NOMINAL_MM if (ean or qr) else None,
		}
		for z in maquette_face(face, contenu):
			rect = _rect_pt(z["x"], z["y"], z["w"], z["h"])
			if z["zone"] == "logo" and logo:
				poser_logo(page, rect, logo)
			elif z["zone"] == "nom":
				taille = taille_nom(MM(z["w"]), MM(z["h"]), nom_produit)
				poser_texte(page, rect, html_bloc([nom_produit], taille_pt=taille, rtl=False, famille="Noto Sans",
				                                  couleur=couleur_texte, gras=True, align="center"), archive, css)
			elif z["zone"] in ("accroche", "caracteristiques", "avertissements", "contact"):
				base = {"accroche": 11.0, "caracteristiques": 8.5, "avertissements": 7.0, "contact": 7.0}[z["zone"]]
				contenu_html = textes_pour_zone(z["zone"], textes, langues, base, couleur_texte)
				if contenu_html:
					panneau = panneau_pour(z["zone"], couleur_texte, face["code"] in visuels)
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
				taille = MM(z["h"])
				x = rect[0]
				for _code, svg in pictos_svg:
					if x + taille > rect[2] + 0.5:
						break
					page.draw_rect(pymupdf.Rect(x, rect[1], x + taille, rect[1] + taille), color=None, fill=(1, 1, 1))
					poser_svg(page, (x + 1, rect[1] + 1, x + taille - 1, rect[1] + taille - 1), svg)
					x += taille + MM(2)

	# 3. calque « Découpe et plis » (activable dans le lecteur, imprimé par l'imprimeur sur demande)
	ocg = pdf.add_ocg("Découpe et plis", on=True)
	for x1, y1, x2, y2 in plan["traits"]["coupe"]:
		page.draw_line((MM(x1), MM(y1)), (MM(x2), MM(y2)), color=(1, 0, 0), width=0.25, oc=ocg)
	for x1, y1, x2, y2 in plan["traits"]["pli"]:
		page.draw_line((MM(x1), MM(y1)), (MM(x2), MM(y2)), color=(0, 0.3, 1), width=0.25, dashes="[2 2] 0", oc=ocg)
	fp = plan.get("fond_perdu", 0) or 0
	page.draw_rect(pymupdf.Rect(MM(fp), MM(fp), W - MM(fp), H - MM(fp)), color=(1, 0, 1), width=0.25, dashes="[1 1] 0", oc=ocg)

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
		+ "<p style=\"font-family:'Noto Sans';font-size:10pt\">Fiche %s · Article %s · Variante %s « %s » · Type : %s</p>" % (
			esc(doc.name), esc(doc.article), variante.numero, esc(variante.titre or ""), esc(plan["type"]))
		+ "<p style=\"font-family:'Noto Sans';font-size:10pt\">Feuille : <b>%.1f × %.1f mm</b> (fond perdu %.1f mm inclus) · "
		  "Boîte : L %.1f × H %.1f × P %.1f mm · Langues : %s · EAN : %s · QR : %s · Pictogrammes : %s</p>" % (
			plan["feuille"]["w"], plan["feuille"]["h"], plan.get("fond_perdu", 0), plan["dimensions"]["L"],
			plan["dimensions"]["H"], plan["dimensions"]["P"], esc(", ".join(langues.keys()) or "—"),
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
		frappe.throw(_("Choisissez une variante prête (avec son visuel)."))
	plan = plan_du_design(doc)
	problemes = geometrie.verifier(plan)
	if problemes:
		frappe.throw(_("Plan impossible : {0}").format(" ; ".join(problemes)))
	textes = frappe.parse_json(doc.textes_ia) if doc.textes_ia else {}
	pdf = composer(doc, v, plan, textes or {}, _langues(doc))
	fichier = save_file("%s-plan-a-plat.pdf" % doc.name, pdf, "Design Emballage", doc.name, is_private=1)
	import pymupdf

	apercu = pymupdf.open("pdf", pdf)[0].get_pixmap(dpi=100).tobytes("png")
	apercu_f = save_file("%s-apercu.png" % doc.name, apercu, "Design Emballage", doc.name, is_private=1)
	frappe.db.set_value("Design Emballage", design, {
		"plan_a_plat": fichier.file_url, "apercu_plan": apercu_f.file_url, "variante_choisie": cint(variante),
		"statut": "Plan prêt",
	}, update_modified=False)
	frappe.db.commit()
	return {"plan_a_plat": fichier.file_url, "apercu_plan": apercu_f.file_url, "feuille": plan["feuille"]}
