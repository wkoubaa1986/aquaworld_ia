"""Le manuel RECONSTRUIT (demande utilisateur 25/09/2026 : « le résultat n'est pas génial ; utiliser
l'IA sur ce qui est extrait pour rebâtir un manuel prêt à l'emploi ») : au lieu de remplacer le texte
boîte par boîte dans le PDF d'origine (bien pour un PDF texte propre, mauvais pour un PDF aux
lettres en contours ou un scan), on LIT chaque page avec le modèle vision — titres, paragraphes,
listes, étapes, tableaux, figures — puis on traduit ce contenu structuré et on compose un PDF NEUF
avec un gabarit propre (couverture, sommaire, pieds de page, figures découpées dans l'original).

Structure (`Manuel Article.structure`, JSON) :
{"version": 1, "pages": {"0": {"titre_page": "…", "blocs": [
   {"id": "b3f9…", "type": "titre", "niveau": 1, "texte": "Installation"},
   {"id": "…", "type": "paragraphe" | "note" | "legende", "texte": "…"},
   {"id": "…", "type": "liste" | "etapes", "items": ["…", "…"]},
   {"id": "…", "type": "tableau", "lignes": [["…", "…"], …]},
   {"id": "…", "type": "figure", "bbox": [x0, y0, x1, y1] (en % de la page), "legende": "…"}]}}}
Traductions (`Manuel Article Traduction.traductions_structure`, JSON) : {clé de texte: traduction},
la clé = type + empreinte du texte anglais (stable si la page est relue, partagée entre pages).
Tout ce qui ne touche pas au site est pur et testé.
"""

from __future__ import annotations

import hashlib
import html
import io
import json
import re

import frappe
from frappe import _
from frappe.utils import cint
from frappe.utils.file_manager import save_file

from aquaworld_ia.ia import etat, fichiers, journal
from aquaworld_ia.ia.chat import chat_json_image
from aquaworld_ia.manuels import rendu, traduction
from aquaworld_ia.manuels.extraction import est_traduisible

VERSION_STRUCTURE = 1
TYPES = ("titre", "paragraphe", "liste", "etapes", "tableau", "figure", "note", "legende", "image")
LARGEUR_IMAGE_DEFAUT = 40.0   # % de la largeur du texte, pour un bloc image ajouté (logo, certification…)
GENRE_LECTURE = "manuel-lecture"
GENRE_TRADUCTION = "manuel-reconstruit"
EVENEMENT = "aqia_manuel"
FONCTIONNALITE_LECTURE = "Manuel lecture"
COTE_IMAGE_LECTURE = 1600      # px : la page envoyée au modèle vision
DPI_FIGURE = 200
FORMATS_MM = {"A4": (210.0, 297.0), "A5": (148.0, 210.0)}
FORMATS = {k: (round(w * 72 / 25.4, 2), round(h * 72 / 25.4, 2)) for k, (w, h) in FORMATS_MM.items()}   # en points
MARGE = 48.0                   # points


# ------------------------------------------------------------------ structure (pur)


def vide() -> dict:
	return {"version": VERSION_STRUCTURE, "pages": {}}


def lire(texte) -> dict:
	if isinstance(texte, dict):
		s = texte
	else:
		try:
			s = json.loads(texte) if texte else {}
		except (TypeError, ValueError):
			s = {}
	out = vide()
	if isinstance(s, dict) and isinstance(s.get("pages"), dict):
		out["pages"] = {str(k): v for k, v in s["pages"].items() if isinstance(v, dict)}
	return out


def empreinte(texte: str) -> str:
	return hashlib.sha1(" ".join((texte or "").split()).lower().encode("utf-8")).hexdigest()[:12]


def _nettoyer(texte) -> str:
	return " ".join(str(texte or "").split())


def normaliser_blocs(blocs) -> list[dict]:
	"""Les blocs tels que rendus par le modèle (ou saisis dans le studio) -> blocs propres : type
	connu, textes nettoyés, listes sans item vide, tableaux rectangulaires, figures avec une boîte
	valide (0-100 %), identifiant = empreinte du contenu. Un bloc vide disparaît. Pur."""
	out = []
	for b in blocs or []:
		if not isinstance(b, dict):
			continue
		t = b.get("type")
		if t in ("sous_titre", "sous-titre", "heading"):
			t, b = "titre", dict(b, niveau=b.get("niveau") or 2)
		if t == "avertissement":
			t = "note"
		if t not in TYPES:
			continue
		n = {"type": t}
		if t in ("titre", "paragraphe", "note", "legende"):
			texte = _nettoyer(b.get("texte"))
			if not texte:
				continue
			n["texte"] = texte
			if t == "titre":
				n["niveau"] = min(3, max(1, cint(b.get("niveau")) or 1))
		elif t in ("liste", "etapes"):
			items = [_nettoyer(i) for i in (b.get("items") or []) if _nettoyer(i)]
			if not items:
				continue
			n["items"] = items
		elif t == "tableau":
			lignes = [[_nettoyer(c) for c in (l or [])] for l in (b.get("lignes") or []) if isinstance(l, (list, tuple))]
			lignes = [l for l in lignes if any(l)]
			if not lignes:
				continue
			larg = max(len(l) for l in lignes)
			n["lignes"] = [l + [""] * (larg - len(l)) for l in lignes]
			if b.get("entete") is not None:
				n["entete"] = bool(b.get("entete"))
		elif t == "figure":
			bbox = b.get("bbox")
			try:
				x0, y0, x1, y1 = [min(100.0, max(0.0, float(v))) for v in bbox]
			except (TypeError, ValueError):
				continue
			if x1 - x0 < 3 or y1 - y0 < 3:
				continue
			n["bbox"] = [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)]
			# zones effacées à la main (en % de la page, dans le cadre) : une étiquette anglaise, un bout parasite
			masques = []
			for m in b.get("masques") or []:
				try:
					mx0, my0, mx1, my1 = [min(100.0, max(0.0, float(v))) for v in m]
				except (TypeError, ValueError):
					continue
				if mx1 - mx0 >= 0.5 and my1 - my0 >= 0.5:
					masques.append([round(mx0, 1), round(my0, 1), round(mx1, 1), round(my1, 1)])
			if masques:
				n["masques"] = masques
			if _nettoyer(b.get("legende")):
				n["legende"] = _nettoyer(b.get("legende"))
		elif t == "image":
			# une image ajoutée par l'utilisateur (logo, certification, photo) : fichier du site
			fichier = b.get("fichier")
			if not isinstance(fichier, str) or not fichier.startswith(("/files/", "/private/files/")):
				continue
			n["fichier"] = fichier
			try:
				n["largeur"] = round(min(100.0, max(5.0, float(b.get("largeur") or LARGEUR_IMAGE_DEFAUT))), 1)
			except (TypeError, ValueError):
				n["largeur"] = LARGEUR_IMAGE_DEFAUT
			if b.get("align") in ("left", "center", "right"):
				n["align"] = b["align"]
			if _nettoyer(b.get("legende")):
				n["legende"] = _nettoyer(b.get("legende"))
		n["id"] = b.get("id") if isinstance(b.get("id"), str) and re.fullmatch(r"[0-9a-f]{12}", b.get("id") or "") else empreinte(json.dumps(
			{k: v for k, v in n.items() if k != "id"}, sort_keys=True, ensure_ascii=False))
		out.append(n)
	return out


def _aire(b) -> float:
	return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _inter(a, b):
	x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
	return (x0, y0, x1, y1) if x1 > x0 and y1 > y0 else None


def ajuster_figure(bbox_pct: list, candidats_pt: list, fmt: list, part_min: float = 0.3, marge: float = 2.0) -> list:
	"""Le cadre d'une figure donné par l'IA (en % de la page) recalé sur les objets réels de la page
	(images, groupes de dessins, en points) qu'il recouvre : union des objets dont au moins
	`part_min` de l'aire est dans le cadre IA, plus une petite marge. Sans objet recouvert, ou si
	l'union explose (plus de 2,5 × le cadre IA : un objet parasite), le cadre IA est gardé. Pur."""
	W, H = fmt[0], fmt[1]
	ia = (bbox_pct[0] / 100 * W, bbox_pct[1] / 100 * H, bbox_pct[2] / 100 * W, bbox_pct[3] / 100 * H)
	pris = []
	for c in candidats_pt or []:
		i = _inter(ia, c)
		if i and _aire(i) >= part_min * (_aire(c) or 1):
			pris.append(c)
	if not pris:
		return list(bbox_pct)
	u = (min(c[0] for c in pris) - marge, min(c[1] for c in pris) - marge, max(c[2] for c in pris) + marge, max(c[3] for c in pris) + marge)
	if _aire(u) > 2.5 * (_aire(ia) or 1):
		return list(bbox_pct)
	u = (max(0.0, u[0]), max(0.0, u[1]), min(W, u[2]), min(H, u[3]))
	return [round(u[0] / W * 100, 1), round(u[1] / H * 100, 1), round(u[2] / W * 100, 1), round(u[3] / H * 100, 1)]


def ajuster_figures(blocs: list[dict], candidats_pt: list, fmt: list) -> list[dict]:
	"""Les blocs d'une page avec leurs figures recalées (identifiants recalculés). Pur."""
	out = []
	for b in blocs:
		if b.get("type") == "figure" and candidats_pt:
			b = dict(b, bbox=ajuster_figure(b["bbox"], candidats_pt, fmt))
			b.pop("id", None)
		out.append(b)
	return normaliser_blocs(out)


def regions_en_pct(candidats_pt: list, fmt: list) -> list:
	W, H = fmt[0], fmt[1]
	return [[round(c[0] / W * 100, 1), round(c[1] / H * 100, 1), round(c[2] / W * 100, 1), round(c[3] / H * 100, 1)] for c in candidats_pt or []]


def textes_du_bloc(b: dict) -> list[tuple[str, str]]:
	"""[(clé, texte anglais)] des textes traduisibles d'un bloc. Pur."""
	t = b.get("type")
	if t in ("titre", "paragraphe", "note", "legende"):
		return [(t + ":" + empreinte(b["texte"]), b["texte"])]
	if t in ("liste", "etapes"):
		return [("item:" + empreinte(i), i) for i in b.get("items", [])]
	if t == "tableau":
		return [("cellule:" + empreinte(c), c) for l in b.get("lignes", []) for c in l if c]
	if t in ("figure", "image") and b.get("legende"):
		return [("legende:" + empreinte(b["legende"]), b["legende"])]
	return []


def textes_a_traduire(structure: dict, traductions: dict | None = None) -> list[dict]:
	"""Les textes de la structure qui n'ont pas encore de traduction, dédoublonnés, comme des
	pseudo-paragraphes pour `traduction.traduire_tout` (id = clé). Pur."""
	vus, out = set(), []
	for no in sorted(structure.get("pages", {}), key=lambda k: cint(k)):
		for b in structure["pages"][no].get("blocs", []):
			for cle, texte in textes_du_bloc(b):
				if cle in vus or (traductions or {}).get(cle) or not est_traduisible(texte):
					continue
				vus.add(cle)
				out.append({"id": cle, "texte": texte})
	return out


def traduit(texte: str, cle: str, traductions: dict) -> str:
	t = (traductions or {}).get(cle)
	return t if isinstance(t, str) and t.strip() else texte


def bloc_traduit(b: dict, traductions: dict) -> dict:
	"""Le bloc avec ses textes traduits (l'anglais reste quand la traduction manque). Pur."""
	t = b.get("type")
	n = dict(b)
	if t in ("titre", "paragraphe", "note", "legende"):
		n["texte"] = traduit(b["texte"], t + ":" + empreinte(b["texte"]), traductions)
	elif t in ("liste", "etapes"):
		n["items"] = [traduit(i, "item:" + empreinte(i), traductions) for i in b.get("items", [])]
	elif t == "tableau":
		n["lignes"] = [[traduit(c, "cellule:" + empreinte(c), traductions) if c else "" for c in l] for l in b.get("lignes", [])]
	elif t in ("figure", "image") and b.get("legende"):
		n["legende"] = traduit(b["legende"], "legende:" + empreinte(b["legende"]), traductions)
	return n


def cles_du_bloc_traduit(b_source: dict, b_traduit: dict) -> dict:
	"""Ce que le studio enregistre quand on corrige un bloc TRADUIT : {clé: texte corrigé}, en
	regard du bloc source (même forme). Pur."""
	out = {}
	t = b_source.get("type")
	if t in ("titre", "paragraphe", "note", "legende"):
		out[t + ":" + empreinte(b_source["texte"])] = _nettoyer(b_traduit.get("texte"))
	elif t in ("liste", "etapes"):
		for src, tr in zip(b_source.get("items", []), b_traduit.get("items", [])):
			out["item:" + empreinte(src)] = _nettoyer(tr)
	elif t == "tableau":
		for ls, lt in zip(b_source.get("lignes", []), b_traduit.get("lignes", [])):
			for cs, ct in zip(ls, lt):
				if cs:
					out["cellule:" + empreinte(cs)] = _nettoyer(ct)
	elif t in ("figure", "image") and b_source.get("legende"):
		out["legende:" + empreinte(b_source["legende"])] = _nettoyer(b_traduit.get("legende"))
	return {k: v for k, v in out.items() if v}


# ------------------------------------------------------------------ HTML du document (pur)


def _e(t) -> str:
	return html.escape(str(t or ""))


def css_document(couleur: str, famille: str, rtl: bool, taille: float = 10.5) -> str:
	return (
		"body{font-family:'%s';font-size:%spt;line-height:1.38;color:#111;direction:%s;}" % (famille, taille, "rtl" if rtl else "ltr")
		+ "h1{font-size:%spt;color:%s;margin:18pt 0 6pt;line-height:1.15;}" % (round(taille * 1.9, 1), couleur)
		+ "h2{font-size:%spt;color:%s;margin:14pt 0 4pt;line-height:1.2;}" % (round(taille * 1.4, 1), couleur)
		+ "h3{font-size:%spt;color:#222;margin:10pt 0 3pt;}" % round(taille * 1.15, 1)
		+ "p{margin:0 0 6pt;}"
		+ "ul,ol{margin:0 0 6pt;padding-%s:18pt;}li{margin:0 0 2pt;}" % ("right" if rtl else "left")
		+ "table{border-collapse:collapse;margin:4pt 0 8pt;width:100%;}"
		+ "td,th{border:0.6pt solid #9ca3af;padding:3pt 5pt;font-size:%spt;vertical-align:top;}" % round(taille * 0.9, 1)
		+ "th{background:#eef2f7;font-weight:700;text-align:%s;}" % ("right" if rtl else "left")
		+ "p.note{border-%s:2.5pt solid %s;padding:3pt 8pt;background:#f5f7fb;margin:4pt 0 8pt;}" % ("right" if rtl else "left", couleur)
		+ "p.legende{font-size:%spt;color:#555;font-style:italic;margin:2pt 0 10pt;text-align:center;}" % round(taille * 0.85, 1)
		+ "div.figure{text-align:center;margin:6pt 0 4pt;}"
	)


def html_bloc(b: dict, largeur_texte: float, figures: dict | None = None) -> str:
	"""Le HTML d'un bloc traduit. Les figures pointent vers `figures[id]` (nom dans l'archive) et
	prennent une largeur proportionnelle à leur boîte d'origine (au moins 45 % du texte). Pur."""
	t = b.get("type")
	if t == "titre":
		n = b.get("niveau", 1)
		return "<h%d>%s</h%d>" % (n, _e(b["texte"]), n)
	if t == "paragraphe":
		return "<p>%s</p>" % _e(b["texte"])
	if t == "note":
		return "<p class=\"note\">%s</p>" % _e(b["texte"])
	if t == "legende":
		return "<p class=\"legende\">%s</p>" % _e(b["texte"])
	if t in ("liste", "etapes"):
		tag = "ol" if t == "etapes" else "ul"
		return "<%s>%s</%s>" % (tag, "".join("<li>%s</li>" % _e(i) for i in b.get("items", [])), tag)
	if t == "tableau":
		lignes = b.get("lignes", [])
		entete = b.get("entete", True) and len(lignes) > 1
		out = "<table>"
		for k, l in enumerate(lignes):
			cell = "th" if (entete and k == 0) else "td"
			out += "<tr>%s</tr>" % "".join("<%s>%s</%s>" % (cell, _e(c), cell) for c in l)
		return out + "</table>"
	if t in ("figure", "image"):
		nom = (figures or {}).get(b["id"])
		if not nom:
			return ""
		if t == "figure":
			x0, _y0, x1, _y1 = b["bbox"]
			largeur = round(largeur_texte * min(1.0, max(0.45, (x1 - x0) / 100.0 * 1.15)))
		else:
			largeur = round(largeur_texte * b.get("largeur", LARGEUR_IMAGE_DEFAUT) / 100.0)
		align = b.get("align", "center")
		out = "<div class=\"figure\" style=\"text-align:%s\"><img src=\"%s\" width=\"%d\"></div>" % (align, nom, largeur)
		if b.get("legende"):
			out += "<p class=\"legende\">%s</p>" % _e(b["legende"])
		return out
	return ""


def html_corps(structure: dict, traductions: dict, largeur_texte: float, figures: dict | None = None) -> str:
	"""Le HTML du corps : les pages dans l'ordre, chacune ses blocs traduits, sans saut de page
	(document fluide). Pur."""
	out = []
	for no in sorted(structure.get("pages", {}), key=lambda k: cint(k)):
		for b in structure["pages"][no].get("blocs", []):
			out.append(html_bloc(bloc_traduit(b, traductions), largeur_texte, figures))
	return "".join(out)


def titres_de_niveau_1(structure: dict, traductions: dict) -> list[str]:
	return [bloc_traduit(b, traductions)["texte"] for no in sorted(structure.get("pages", {}), key=lambda k: cint(k))
	        for b in structure["pages"][no].get("blocs", []) if b.get("type") == "titre" and b.get("niveau", 1) == 1]


# ------------------------------------------------------------------ PDF (PyMuPDF Story)


def _reglages_gabarit() -> dict:
	from aquaworld_ia.ia.client import reglages

	r = reglages()
	return {"logo": getattr(r, "logo_manuels", None), "couleur": getattr(r, "couleur_manuels", None) or "#1d4ed8",
	        "format": getattr(r, "format_manuels", None) or "Original", "editeur": getattr(r, "editeur_manuels", None) or ""}


def format_sortie(g: dict, fmt_source) -> tuple:
	"""Le format (points) d'une page produite : « Original » = les dimensions de la page d'origine
	(un manuel paysage, une double page, restent tels quels — vu le 25/09/2026 : la couverture
	paysage de l'osmoseur écrasée en A4 portrait) ; A4/A5 = format fixe, dans l'ORIENTATION de la
	page d'origine. Pur."""
	w0, h0 = (fmt_source or [595.28, 841.89])[:2]
	if g.get("format") not in FORMATS:
		return (round(float(w0), 2), round(float(h0), 2))
	w, h = FORMATS[g["format"]]
	return (h, w) if w0 > h0 else (w, h)


COTE_FIGURE_PX = 1400


def figure_jpeg(png: bytes, qualite: int = 82) -> bytes:
	"""Une figure découpée (PNG) -> JPEG : dix fois plus légère dans le PDF, sans perte visible à
	l'impression (le PDF dépassait 10 Mo, refusé par Frappe). Pur."""
	from PIL import Image

	im = Image.open(io.BytesIO(png)).convert("RGB")
	sortie = io.BytesIO()
	im.save(sortie, format="JPEG", quality=qualite, optimize=True)
	return sortie.getvalue()


def appliquer_masques(png: bytes, bbox_pct: list, masques_pct: list) -> bytes:
	"""Blanchit dans la figure découpée les zones effacées (toutes deux en % de la page). Pur."""
	from PIL import Image, ImageDraw

	if not masques_pct:
		return png
	im = Image.open(io.BytesIO(png)).convert("RGB")
	x0, y0, x1, y1 = bbox_pct
	fw, fh = max(1e-6, x1 - x0), max(1e-6, y1 - y0)
	dessin = ImageDraw.Draw(im)
	for mx0, my0, mx1, my1 in masques_pct:
		r = ((mx0 - x0) / fw * im.width, (my0 - y0) / fh * im.height, (mx1 - x0) / fw * im.width, (my1 - y0) / fh * im.height)
		dessin.rectangle(r, fill=(255, 255, 255))
	sortie = io.BytesIO()
	im.save(sortie, format="PNG")
	return sortie.getvalue()


def cle_figure(b: dict) -> str:
	return "figure:" + b["id"]


def octets_figure(pdf_bytes: bytes, b: dict, no: int, fmt: list, traductions: dict | None = None) -> bytes | None:
	"""Les octets d'un bloc figure (découpe de l'original, masques appliqués, JPEG — ou sa version
	REDESSINÉE par l'IA dans la langue si `traductions` en porte une) ou image (fichier du site tel
	quel : un logo PNG garde sa transparence)."""
	if b.get("type") == "image":
		return fichiers.lire(b["fichier"])
	url = (traductions or {}).get(cle_figure(b))
	if isinstance(url, str) and url.startswith(("/files/", "/private/files/")):
		try:
			return fichiers.lire(url)
		except Exception:
			frappe.log_error(title="Aquaworld IA : figure traduite %s" % b["id"], message=frappe.get_traceback())
	x0, y0, x1, y1 = b["bbox"]
	png = rendu.clip_page(pdf_bytes, no, (x0 / 100 * fmt[0], y0 / 100 * fmt[1], x1 / 100 * fmt[0], y1 / 100 * fmt[1]), cote_max_px=COTE_FIGURE_PX)
	return figure_jpeg(appliquer_masques(png, b["bbox"], b.get("masques") or []))


def _figures_archive(pdf_bytes: bytes, structure: dict, formats: list, archive, traductions: dict | None = None) -> dict:
	"""Découpe chaque figure dans la page d'ORIGINE (images et traits vectoriels compris), charge
	les images ajoutées, et les met dans l'archive. -> {id bloc: nom de fichier}."""
	figures = {}
	for no, page in structure.get("pages", {}).items():
		fmt = formats[cint(no)] if cint(no) < len(formats) else [612, 792]
		for b in page.get("blocs", []):
			if b.get("type") not in ("figure", "image"):
				continue
			try:
				octets = octets_figure(pdf_bytes, b, cint(no), fmt, traductions)
			except Exception:
				frappe.log_error(title="Aquaworld IA : figure p%s" % no, message=frappe.get_traceback())
				continue
			nom = "fig-%s-%s.%s" % (no, b["id"], "png" if octets[:4] == b"\x89PNG" else "jpg")
			archive.add(octets, nom)
			figures[b["id"]] = nom
	return figures


def composer_pdf(pdf_source: bytes, structure: dict, traductions: dict, langue: dict, formats: list,
                 titre: str, sous_titre: str = "", gabarit: dict | None = None, habillage: bool = True) -> bytes:
	"""Le manuel reconstruit : couverture, sommaire (titres de niveau 1 avec leur page), corps
	fluide, pied de page (éditeur · page n). Polices de l'app (Noto, arabe façonné).
	`habillage=False` : le corps seul (aperçu d'une page dans le studio)."""
	import pymupdf

	g = dict(_reglages_gabarit(), **(gabarit or {}))
	W, H = format_sortie(g, formats[0] if formats else None)
	rtl = bool(langue.get("rtl"))
	famille = rendu.famille(langue)
	archive = rendu.polices_archive()
	figures = _figures_archive(pdf_source, structure, formats, archive, traductions)
	logo = None
	if g.get("logo"):
		try:
			from aquaworld_ia.ia.images import normaliser_reference

			logo = normaliser_reference(fichiers.lire(g["logo"]))
		except Exception:
			logo = None
	largeur_texte = W - 2 * MARGE
	css = rendu.css_polices(rendu.polices_personnalisees(), rendu.polices_utilisateur()) + css_document(g["couleur"], famille, rtl)
	corps = "<html><body>%s</body></html>" % html_corps(structure, traductions, largeur_texte, figures)

	# 1) le corps, page par page, en retenant sur quelle page tombe chaque titre de niveau 1
	tampon = io.BytesIO()
	writer = pymupdf.DocumentWriter(tampon)
	story = pymupdf.Story(html=corps, user_css=css, archive=archive)
	zone = pymupdf.Rect(MARGE, MARGE + 6, W - MARGE, H - MARGE - 10)
	plus = 1
	while plus:
		dev = writer.begin_page(pymupdf.Rect(0, 0, W, H))
		plus, _ = story.place(zone)
		story.draw(dev)
		writer.end_page()
	writer.close()
	corps_pdf = pymupdf.open(stream=tampon.getvalue(), filetype="pdf")
	if not habillage:
		return corps_pdf.tobytes()
	titres = titres_de_niveau_1(structure, traductions)
	pages_titres = _pages_des_titres(corps_pdf, titres)

	# 2) couverture + sommaire, puis le corps ; numérotation et pied de page sur le tout
	doc = pymupdf.open()
	_couverture(doc, W, H, titre, sous_titre, langue, g, logo, famille, css, archive)
	decalage = 2 if titres else 1
	if titres:
		_sommaire(doc, W, H, titres, [p + decalage + 1 for p in pages_titres], langue, g, famille, css, archive, rtl)
	doc.insert_pdf(corps_pdf)
	_pieds_de_page(doc, W, H, g, logo, famille, css, archive, rtl, depuis=decalage)
	try:
		doc.subset_fonts()
	except Exception:
		pass
	sortie = io.BytesIO()
	doc.save(sortie, garbage=4, deflate=True, deflate_images=True)
	return sortie.getvalue()


def _pages_des_titres(corps_pdf, titres: list[str]) -> list[int]:
	"""L'indice de page (0 = première page du corps) où chaque titre de niveau 1 apparaît."""
	pages, depuis = [], 0
	for t in titres:
		trouve = None
		cle = " ".join(t.split())[:60]
		for no in range(depuis, len(corps_pdf)):
			if cle and corps_pdf[no].search_for(cle):
				trouve = no
				break
		if trouve is None:
			trouve = depuis
		pages.append(trouve)
		depuis = trouve
	return pages


def _htmlbox(page, rect, html_, css, archive, archive_ok=True):
	page.insert_htmlbox(rect, html_, css=css, archive=archive, scale_low=0.4)


def _couverture(doc, W, H, titre, sous_titre, langue, g, logo, famille, css, archive):
	import pymupdf

	page = doc.new_page(width=W, height=H)
	page.draw_rect(pymupdf.Rect(0, 0, W, H * 0.42), color=None, fill=pymupdf.utils.getColor("white"))
	page.draw_rect(pymupdf.Rect(0, H * 0.42, W, H * 0.44), color=None, fill=_rgb(g["couleur"]))
	if logo:
		page.insert_image(pymupdf.Rect(MARGE, MARGE, MARGE + 150, MARGE + 70), stream=logo, keep_proportion=True)
	rtl = bool(langue.get("rtl"))
	al = "right" if rtl else "left"
	_htmlbox(page, pymupdf.Rect(MARGE, H * 0.5, W - MARGE, H * 0.5 + 150),
	         "<p style=\"font-family:'%s';font-size:26pt;font-weight:700;color:%s;text-align:%s;direction:%s\">%s</p>"
	         % (famille, g["couleur"], al, "rtl" if rtl else "ltr", _e(titre)), css, archive)
	if sous_titre:
		_htmlbox(page, pymupdf.Rect(MARGE, H * 0.5 + 150, W - MARGE, H * 0.5 + 220),
		         "<p style=\"font-family:'%s';font-size:14pt;color:#374151;text-align:%s;direction:%s\">%s</p>"
		         % (famille, al, "rtl" if rtl else "ltr", _e(sous_titre)), css, archive)
	bas = "%s · %s" % (g["editeur"], langue.get("libelle_natif") or langue.get("libelle") or langue.get("code", "")) if g["editeur"] else (langue.get("libelle_natif") or langue.get("libelle") or "")
	_htmlbox(page, pymupdf.Rect(MARGE, H - MARGE - 30, W - MARGE, H - MARGE),
	         "<p style=\"font-family:'%s';font-size:10pt;color:#6b7280;text-align:%s\">%s</p>" % (famille, al, _e(bas)), css, archive)


def _sommaire(doc, W, H, titres, pages, langue, g, famille, css, archive, rtl):
	import pymupdf

	page = doc.new_page(width=W, height=H)
	libelle = {"fr": "Sommaire", "ar": "المحتويات", "de": "Inhalt", "es": "Índice", "it": "Indice", "pt": "Índice", "nl": "Inhoud", "en": "Contents"}.get(langue.get("code"), "Contents")
	lignes = "".join("<tr><td style=\"border:none;padding:4pt 0\">%s</td><td style=\"border:none;padding:4pt 0;text-align:%s;width:40pt\">%d</td></tr>"
	                 % (_e(t), "left" if rtl else "right", p) for t, p in zip(titres, pages))
	html_ = ("<h1 style=\"font-family:'%s';color:%s;direction:%s\">%s</h1><table style=\"font-family:'%s';font-size:11pt;direction:%s\">%s</table>"
	         % (famille, g["couleur"], "rtl" if rtl else "ltr", libelle, famille, "rtl" if rtl else "ltr", lignes))
	_htmlbox(page, pymupdf.Rect(MARGE, MARGE, W - MARGE, H - MARGE), html_, css, archive)


def _pieds_de_page(doc, W, H, g, logo, famille, css, archive, rtl, depuis: int):
	import pymupdf

	total = len(doc)
	for no in range(depuis, total):
		page = doc[no]
		page.draw_line(pymupdf.Point(MARGE, H - MARGE + 4), pymupdf.Point(W - MARGE, H - MARGE + 4), color=_rgb("#d1d5db"), width=0.5)
		texte = "%s%s%d / %d" % (_e(g["editeur"]), " · " if g["editeur"] else "", no + 1, total)
		_htmlbox(page, pymupdf.Rect(MARGE, H - MARGE + 6, W - MARGE, H - MARGE + 22),
		         "<p style=\"font-family:'%s';font-size:8.5pt;color:#6b7280;text-align:%s\">%s</p>" % (famille, "left" if rtl else "right", texte), css, archive)
		if logo:
			page.insert_image(pymupdf.Rect(W - MARGE - 40, H - MARGE + 6, W - MARGE, H - MARGE + 20) if rtl else pymupdf.Rect(MARGE, H - MARGE + 6, MARGE + 40, H - MARGE + 20),
			                  stream=logo, keep_proportion=True)


def _rgb(hexa: str):
	h = (hexa or "#1d4ed8").lstrip("#")
	try:
		return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
	except ValueError:
		return (0.11, 0.31, 0.85)


# ------------------------------------------------------------------ lecture par IA (site)


PROMPT_LECTURE = (
	"You read ONE page of an English product manual (image attached) and return its content as structured JSON, "
	"in reading order (for two columns: whole left column, then whole right column). Output: "
	"{\"titre_page\": \"<short label>\", \"blocs\": [ ... ]}. Block types:\n"
	"- {\"type\":\"titre\",\"niveau\":1|2|3,\"texte\":\"...\"}  (section headings; niveau 1 = chapter)\n"
	"- {\"type\":\"paragraphe\",\"texte\":\"...\"}\n"
	"- {\"type\":\"liste\",\"items\":[\"...\"]}  (bullet list)  /  {\"type\":\"etapes\",\"items\":[\"...\"]}  (numbered steps, WITHOUT the numbers)\n"
	"- {\"type\":\"tableau\",\"lignes\":[[\"cell\",...],...],\"entete\":true|false}  (a real table; first row is the header when entete)\n"
	"- {\"type\":\"figure\",\"bbox\":[x0,y0,x1,y1],\"legende\":\"...\"}  (a photo, drawing, diagram, schematic or screenshot; bbox in PERCENT "
	"of the page width/height, tight around the picture and its own labels, EXCLUDING any line of running text above or below it; "
	"legende = the printed caption line under/near the picture if there is one — never the labels inside the picture)\n"
	"- {\"type\":\"note\",\"texte\":\"...\"}  (NOTE, WARNING, CAUTION, IMPORTANT boxes, keep the leading word)\n"
	"Rules: transcribe the English text EXACTLY as printed (a rough OCR transcript is given as a hint; it may contain garbage such as "
	"dot leaders or misread page numbers — trust the image). Keep numbers, units, model codes, symbols. Do NOT translate, do NOT invent, "
	"do NOT summarize. Skip page numbers, running headers/footers and dot leaders. A TABLE OF CONTENTS (a title such as CONTENTS/CATALOGUE/INDEX "
	"followed by section names with page numbers or dot leaders) must NOT be transcribed: return the single block {\"type\":\"sommaire\"} in its place — "
	"the new manual generates its own contents page. Text inside a picture belongs to the figure, not to a paragraph. If the page has no content, "
	"return an empty blocs list."
)


def _doc(manuel: str, droit: str = "write"):
	doc = frappe.get_doc("Manuel Article", manuel)
	doc.check_permission(droit)
	return doc


def _ligne(doc, langue: str):
	for l in doc.traductions:
		if l.langue == langue:
			return l
	frappe.throw(_("La langue {0} n'est pas dans ce manuel.").format(langue))


def image_page_pour_ia(pdf_bytes: bytes, no: int) -> bytes:
	import pymupdf

	d = pymupdf.open(stream=pdf_bytes, filetype="pdf")
	page = d[no]
	dpi = max(50, min(200, int(COTE_IMAGE_LECTURE * 72 / max(page.rect.width, page.rect.height, 1))))
	return page.get_pixmap(dpi=dpi, alpha=False).tobytes("png")


def lire_page_ia(doc, pdf_bytes: bytes, analyse: dict, no: int) -> dict:
	"""La structure d'UNE page, lue par le modèle vision (image + transcription OCR en indice)."""
	indice = "\n".join(p["texte"] for p in analyse.get("paragraphes", []) if p.get("page") == no)[:6000]
	candidats = (analyse.get("figures") or [[]] * (no + 1))[no] if no < len(analyse.get("figures") or []) else []
	fmt = analyse["formats"][no]
	user = "Page %d of %d. OCR transcript (hint only):\n%s" % (no + 1, analyse.get("pages", 0), indice or "(none)")
	if candidats:
		user += ("\n\nPicture regions detected in the PDF (bbox in percent of the page, exact): %s — use them for the figure bboxes "
		         "(merge adjacent ones when they form one illustration)." % json.dumps(regions_en_pct(candidats, fmt)))
	sortie = chat_json_image(PROMPT_LECTURE, user, image_page_pour_ia(pdf_bytes, no), fonctionnalite=FONCTIONNALITE_LECTURE, doc=doc)
	blocs = normaliser_blocs(sortie.get("blocs") if isinstance(sortie, dict) else [])
	blocs = ajuster_figures(blocs, candidats, fmt)
	return {"titre_page": _nettoyer((sortie or {}).get("titre_page"))[:80], "blocs": blocs, "lu": True}


def _enregistrer_structure(doc, structure: dict) -> None:
	frappe.db.set_value("Manuel Article", doc.name, "structure", json.dumps(structure, ensure_ascii=False), update_modified=False)
	doc.structure = json.dumps(structure, ensure_ascii=False)


def _oublier_mises_en_page(doc, no: int) -> None:
	"""Les mises en page IA de la page `no`, dans toutes les langues, ne valent plus rien quand la
	page est relue ou que ses figures changent (elles nomment les figures par identifiant, vu le
	25/09/2026 : deux dessins disparus après une relecture)."""
	for l in doc.traductions:
		m = _mises_en_page(l)
		if str(no) in m:
			m.pop(str(no))
			frappe.db.set_value("Manuel Article Traduction", l.name, "mises_en_page", json.dumps(m, ensure_ascii=False), update_modified=False)
			l.mises_en_page = json.dumps(m, ensure_ascii=False)


def ids_figures(page: dict) -> set:
	return {b["id"] for b in (page or {}).get("blocs", []) if b.get("type") in ("figure", "image")}


@frappe.whitelist()
def lire_page(manuel: str, no: int) -> dict:
	"""Lire (ou relire) UNE page par IA, tout de suite."""
	from aquaworld_ia.manuels.studio import _pdf, analyse_du_manuel

	doc = _doc(manuel)
	journal.verifier_plafond()
	analyse = analyse_du_manuel(doc)
	no = cint(no)
	structure = lire(doc.get("structure"))
	structure["pages"][str(no)] = lire_page_ia(doc, _pdf(doc), analyse, no)
	_enregistrer_structure(doc, structure)
	_oublier_mises_en_page(doc, no)
	frappe.db.commit()
	return structure_page(manuel, None, no)


@frappe.whitelist()
def lire_tout(manuel: str, relire: int = 0) -> dict:
	"""Lire toutes les pages par IA, en tâche de fond (une page ≈ 30-60 s)."""
	doc = _doc(manuel)
	if etat.bloque(etat.lire_etat(GENRE_LECTURE, manuel)):
		frappe.throw(_("Une lecture est déjà en cours."))
	journal.verifier_plafond()
	etat.demarrer(GENRE_LECTURE, manuel)
	frappe.enqueue("aquaworld_ia.manuels.reconstruit.job_lire_tout", queue="long", timeout=7200,
	               job_id="aqia-lecture-%s" % manuel, deduplicate=True, manuel=manuel, relire=cint(relire), utilisateur=frappe.session.user)
	return etat.lire_etat(GENRE_LECTURE, manuel)


def job_lire_tout(manuel: str, relire: int = 0, utilisateur: str | None = None) -> None:
	from aquaworld_ia.manuels.studio import _pdf, analyse_du_manuel

	doc = frappe.get_doc("Manuel Article", manuel)
	try:
		pdf = _pdf(doc)
		analyse = analyse_du_manuel(doc, pdf)
		structure = lire(doc.get("structure"))
		total = analyse["pages"]
		for no in range(total):
			if not relire and structure["pages"].get(str(no), {}).get("lu"):
				continue
			etat.progresser(GENRE_LECTURE, manuel, "lecture de la page %d / %d" % (no + 1, total), int(100 * no / total), EVENEMENT, utilisateur)
			structure["pages"][str(no)] = lire_page_ia(doc, pdf, analyse, no)
			_enregistrer_structure(doc, structure)
			_oublier_mises_en_page(doc, no)
			frappe.db.commit()
		etat.terminer(GENRE_LECTURE, manuel, "termine")
		etat.progresser(GENRE_LECTURE, manuel, "lecture terminée", 100, EVENEMENT, utilisateur, fin=1)
	except Exception as e:
		frappe.log_error(title="Aquaworld IA : lecture %s" % manuel, message=frappe.get_traceback())
		etat.terminer(GENRE_LECTURE, manuel, "echec", erreur=str(e)[:300])
		etat.progresser(GENRE_LECTURE, manuel, "échec : %s" % str(e)[:120], 100, EVENEMENT, utilisateur, fin=1)


# ------------------------------------------------------------------ studio : lecture / édition


@frappe.whitelist()
def structure_page(manuel: str, langue: str | None, no: int) -> dict:
	"""La page structurée : blocs source (anglais) et, si `langue`, les mêmes blocs traduits."""
	from aquaworld_ia.manuels.studio import langue_infos

	doc = _doc(manuel, "read")
	structure = lire(doc.get("structure"))
	page = structure["pages"].get(str(cint(no))) or {"blocs": [], "lu": False}
	trad = {}
	if langue:
		l = _ligne(doc, langue)
		trad = _traductions(l)
	blocs = page.get("blocs", [])
	return {
		"no": cint(no), "lu": bool(page.get("lu")), "titre_page": page.get("titre_page", ""),
		"blocs": blocs, "traduits": [bloc_traduit(b, trad) for b in blocs] if langue else [],
		"manquants": [b["id"] for b in blocs if any(not trad.get(c) and est_traduisible(t) for c, t in textes_du_bloc(b))] if langue else [],
		"pages_lues": sorted(cint(k) for k, v in structure["pages"].items() if v.get("lu")),
		"infos": langue_infos(langue) if langue else None,
		"figures_traduites": {b["id"]: trad[cle_figure(b)] for b in blocs if b.get("type") == "figure" and trad.get(cle_figure(b))} if langue else {},
	}


@frappe.whitelist()
def structure_page_multi(manuel: str, no: int) -> dict:
	"""La page structurée dans TOUTES les langues du manuel à la fois (demande utilisateur
	25/09/2026 : « le même travail simultanément sur toutes les langues »)."""
	from aquaworld_ia.manuels.studio import langue_infos

	doc = _doc(manuel, "read")
	structure = lire(doc.get("structure"))
	page = structure["pages"].get(str(cint(no))) or {"blocs": [], "lu": False}
	blocs = page.get("blocs", [])
	langues = []
	for l in doc.traductions:
		trad = _traductions(l)
		infos = langue_infos(l.langue)
		langues.append({
			"langue": l.langue, "libelle": infos.get("libelle") or l.langue, "rtl": cint(infos.get("rtl")),
			"traduits": [bloc_traduit(b, trad) for b in blocs],
			"manquants": [b["id"] for b in blocs if any(not trad.get(c) and est_traduisible(t) for c, t in textes_du_bloc(b))],
			"figures_traduites": {b["id"]: trad[cle_figure(b)] for b in blocs if b.get("type") == "figure" and trad.get(cle_figure(b))},
		})
	return {"no": cint(no), "lu": bool(page.get("lu")), "blocs": blocs, "langues": langues,
	        "pages_lues": sorted(cint(k) for k, v in structure["pages"].items() if v.get("lu"))}


def _traductions(l) -> dict:
	try:
		t = json.loads(l.get("traductions_structure") or "{}")
	except ValueError:
		t = {}
	return {k: v for k, v in (t or {}).items() if isinstance(v, str)}


@frappe.whitelist()
def enregistrer_page(manuel: str, no: int, blocs, langue: str | None = None) -> dict:
	"""Les blocs d'une page corrigés dans le studio. Sans `langue` : la source anglaise (les blocs
	sont remplacés, identifiants recalculés). Avec `langue` : les textes traduits, bloc pour bloc
	en regard de la source (même nombre de blocs)."""
	doc = _doc(manuel)
	blocs = frappe.parse_json(blocs) if isinstance(blocs, str) else blocs
	structure = lire(doc.get("structure"))
	no = cint(no)
	page = structure["pages"].setdefault(str(no), {"blocs": [], "lu": False})
	if not langue:
		avant = ids_figures(page)
		page["blocs"] = normaliser_blocs(blocs)
		page["lu"] = True
		_enregistrer_structure(doc, structure)
		if ids_figures(page) != avant:
			_oublier_mises_en_page(doc, no)
	else:
		l = _ligne(doc, langue)
		trad = _traductions(l)
		for src, tr in zip(page.get("blocs", []), blocs or []):
			if isinstance(tr, dict) and tr.get("type") == src.get("type"):
				trad.update(cles_du_bloc_traduit(src, tr))
		frappe.db.set_value("Manuel Article Traduction", l.name, "traductions_structure", json.dumps(trad, ensure_ascii=False), update_modified=False)
	return structure_page(manuel, langue, no)


# ------------------------------------------------------------------ traduction et PDF


@frappe.whitelist()
def traduire(manuel: str, langue: str) -> dict:
	"""Traduire les textes de la structure qui ne le sont pas encore (tâche de fond)."""
	doc = _doc(manuel)
	_ligne(doc, langue)
	cle = _cle_traduction(manuel, langue)
	if etat.bloque(etat.lire_etat(GENRE_TRADUCTION, cle)):
		frappe.throw(_("La traduction du contenu en {0} est déjà en cours.").format(langue))
	journal.verifier_plafond()
	etat.demarrer(GENRE_TRADUCTION, cle, langue=langue)
	# une tâche par langue : plusieurs langues se traduisent en même temps (demande utilisateur 25/09/2026)
	frappe.enqueue("aquaworld_ia.manuels.reconstruit.job_traduire", queue="long", timeout=7200,
	               job_id="aqia-reconstruit-%s-%s" % (manuel, langue), deduplicate=True, manuel=manuel, langue=langue, utilisateur=frappe.session.user)
	return etat.lire_etat(GENRE_TRADUCTION, cle)


def _cle_traduction(manuel: str, langue: str) -> str:
	return "%s:%s" % (manuel, langue)


def job_traduire(manuel: str, langue: str, utilisateur: str | None = None) -> None:
	from aquaworld_ia.ia.client import reglages
	from aquaworld_ia.manuels.studio import langue_infos

	doc = frappe.get_doc("Manuel Article", manuel)
	l = _ligne(doc, langue)
	try:
		structure = lire(doc.get("structure"))
		trad = _traductions(l)
		cibles = textes_a_traduire(structure, trad)
		r = reglages()
		glossaire = "\n".join(x for x in (getattr(r, "glossaire_global", "") or "", doc.glossaire or "") if x)

		cle = _cle_traduction(manuel, langue)
		nom_langue = langue_infos(langue).get("libelle") or langue

		def progression(fait, total):
			etat.progresser(GENRE_TRADUCTION, cle, "%s : lot %d / %d" % (nom_langue, fait, total), int(100 * fait / max(1, total)), EVENEMENT, utilisateur, manuel=manuel)

		nouvelles, _laisses = traduction.traduire_tout(cibles, langue_infos(langue), glossaire=glossaire,
		                                               instructions=getattr(r, "instructions_globales", "") or "",
		                                               contexte=doc.contexte or "", doc=doc,
		                                               taille_lot=cint(getattr(r, "lot_paragraphes", 25)) or 25, progression=progression)
		trad.update({str(k): v for k, v in nouvelles.items()})
		frappe.db.set_value("Manuel Article Traduction", l.name, "traductions_structure", json.dumps(trad, ensure_ascii=False), update_modified=False)
		frappe.db.commit()
		etat.terminer(GENRE_TRADUCTION, cle, "termine")
		etat.progresser(GENRE_TRADUCTION, cle, "%s : contenu traduit (%d textes)" % (nom_langue, len(nouvelles)), 100, EVENEMENT, utilisateur, fin=1, manuel=manuel)
	except Exception as e:
		frappe.log_error(title="Aquaworld IA : traduction reconstruite %s (%s)" % (manuel, langue), message=frappe.get_traceback())
		etat.terminer(GENRE_TRADUCTION, _cle_traduction(manuel, langue), "echec", erreur=str(e)[:300])
		etat.progresser(GENRE_TRADUCTION, _cle_traduction(manuel, langue), "%s : échec : %s" % (langue, str(e)[:120]), 100, EVENEMENT, utilisateur, fin=1, manuel=manuel)


@frappe.whitelist()
def etats(manuel: str) -> dict:
	"""L'état de la lecture et de la traduction du contenu de CHAQUE langue."""
	doc = _doc(manuel, "read")
	e = etat.lire_etat(GENRE_LECTURE, manuel)
	e["bloque"] = etat.bloque(e)
	out = {"lecture": e, "traductions": {}}
	out["mep"] = {}
	for l in doc.traductions:
		t = etat.lire_etat(GENRE_TRADUCTION, _cle_traduction(manuel, l.langue))
		t["bloque"] = etat.bloque(t)
		out["traductions"][l.langue] = t
		m = etat.lire_etat(GENRE_MEP, _cle_traduction(manuel, l.langue))
		m["bloque"] = etat.bloque(m)
		out["mep"][l.langue] = m
	return out


@frappe.whitelist()
def generer(manuel: str, langue: str, mode: str = "fluide") -> dict:
	"""Le PDF reconstruit de la langue, sans appel IA : les textes non traduits restent en anglais.
	`mode` : « fluide » (gabarit, document continu) ou « ia » (les pages mises en page par l'IA,
	une page imprimée par page d'origine ; le gabarit comble les pages sans mise en page IA)."""
	from aquaworld_ia.manuels import job as J
	from aquaworld_ia.manuels.studio import _pdf, analyse_du_manuel, langue_infos

	doc = _doc(manuel)
	l = _ligne(doc, langue)
	structure = lire(doc.get("structure"))
	if not any(p.get("blocs") for p in structure["pages"].values()):
		frappe.throw(_("Lisez d'abord les pages par IA (« Lire tout »)."))
	analyse = analyse_du_manuel(doc)
	infos = langue_infos(langue)
	nom_article = frappe.db.get_value("Item", doc.article, "item_name") or doc.article
	titre = doc.titre or nom_article
	sous_titre = nom_article if doc.titre and doc.titre.strip() != (nom_article or "").strip() else ""
	if mode == "ia":
		octets = assembler_ia(doc, l, infos, titre, sous_titre or "")
	else:
		octets = composer_pdf(_pdf(doc), structure, _traductions(l), infos, analyse["formats"], titre, sous_titre or "")
	fichier = save_file("%s-%s-reconstruit.pdf" % (frappe.scrub(doc.titre or doc.article)[:60], langue), octets, "Manuel Article", doc.name, is_private=1)
	frappe.db.set_value("Manuel Article Traduction", l.name, "pdf_reconstruit", fichier.file_url, update_modified=False)
	J._journal(doc, ["%s : manuel reconstruit généré (%s)" % (langue, fichier.file_url)])
	frappe.db.commit()
	return {"fichier": fichier.file_url}


@frappe.whitelist()
def apercu_page(manuel: str, langue: str, no: int) -> dict:
	"""Les blocs d'UNE page composés dans la langue, tels qu'ils sortiront (sans couverture ni
	sommaire) : images PNG pour la colonne de gauche du studio (demande utilisateur 25/09/2026)."""
	import base64

	import pymupdf

	from aquaworld_ia.manuels.studio import _pdf, analyse_du_manuel, langue_infos

	doc = _doc(manuel, "read")
	l = _ligne(doc, langue)
	structure = lire(doc.get("structure"))
	no = cint(no)
	page = structure["pages"].get(str(no))
	if not page or not page.get("blocs"):
		return {"images": [], "lu": False}
	analyse = analyse_du_manuel(doc)
	ia = str(no) in _mises_en_page(l)
	if ia:
		octets, _n = rendre_mise_en_page(doc, l, no)
	else:
		seule = {"version": structure["version"], "pages": {str(no): page}}
		octets = composer_pdf(_pdf(doc), seule, _traductions(l), langue_infos(langue), analyse["formats"], doc.titre or "", habillage=False)
	d = pymupdf.open(stream=octets, filetype="pdf")
	images = ["data:image/png;base64," + base64.b64encode(p.get_pixmap(dpi=110, alpha=False).tobytes("png")).decode() for p in d]
	return {"images": images, "lu": True, "pages": len(d), "ia": ia, "nb_ia": len(_mises_en_page(l))}


# ------------------------------------------------------------------ mise en page par IA, page par page
# (demande utilisateur 25/09/2026 : « que l'IA construise la page, tester page par page — bien mieux
# que le gabarit »). L'IA écrit le HTML d'UNE page imprimée à partir des blocs traduits et de l'image
# de la page d'origine ; wkhtmltopdf (présent dans l'image Frappe, QtWebKit patché) le rend en PDF.
# Stocké par langue dans `Manuel Article Traduction.mises_en_page` : {no: {"html": …, "pages": n}}.

GENRE_MEP = "manuel-mep"
FONCTIONNALITE_MEP = "Manuel mise en page"
_FONTS_CSS = {}

PROMPT_MISE_EN_PAGE = (
	"You are a print layout engine. Write the complete, standalone HTML of exactly ONE printed page that reproduces the LAYOUT of the "
	"reference page image (attached): same column structure, same hierarchy of headings, boxes, emphasis, and the figures at the same "
	"places and similar sizes — but with the TRANSLATED content blocks given in the user message, and nothing else (no invented text, "
	"no lorem ipsum, every block used once, in order). Rules:\n"
	"- Page size and margins are given in mm (they follow the ORIGINAL page: a landscape or double-page original stays so) — use EXACTLY the numbers given, "
	"with their decimals, never rounded up; the <body> must be exactly one page: set .page {width:Wmm;min-height:Hmm;"
	"position:relative;box-sizing:border-box;padding:<margins>} — NEVER overflow:hidden (content must not be cut; if it does not fit, the renderer will "
	"report it and you will be asked to tighten). If the translated text is longer than the original, reduce font sizes (never below 7pt), tighten "
	"line-height (min 1.15) and spacing — the page must not overflow. Absolutely positioned elements must stay inside the page.\n"
	"- The renderer is an OLD WebKit (wkhtmltopdf): NO flexbox, NO grid, NO CSS variables, NO calc(). Use <table> for columns, "
	"floats, or absolutely positioned divs with mm units. Inline <style> only; no external resources, no JavaScript.\n"
	"- Figures: <img src=\"fig:<id>\"> with the ids given (width in mm; keep the aspect ratio of each figure, dimensions are given). "
	"A figure marked \"ajoutee\" (a logo, certification mark or photo added by the user) is not on the reference image: place it where the "
	"block order puts it, at the given size.\n"
	"- Fonts: use font-family '<FAMILLE>' (already available) for everything; keep colours sober (black text; one accent colour for "
	"headings). Right-to-left languages: direction:rtl on .page and text-align:right.\n"
	"- Do NOT add page numbers, running headers or footers (they are added later), nor any text absent from the blocks.\n"
	"- Return JSON only: {\"html\": \"<!doctype html>...\"}."
)


def css_polices_data_uri() -> str:
	"""Les @font-face des polices livrées, en data: URI (wkhtmltopdf ne lit pas les fichiers). Une fois
	par processus."""
	import base64
	import os

	if "css" not in _FONTS_CSS:
		css = ""
		for famille, fichiers_ in rendu.POLICES_LIVREES.items():
			for (_cle, poids, style), fichier in zip(rendu.STYLES_POLICE, fichiers_):
				if not fichier:
					continue
				chemin = os.path.join(rendu.CHEMIN_POLICES, fichier)
				if os.path.exists(chemin):
					with open(chemin, "rb") as f:
						b64 = base64.b64encode(f.read()).decode()
					css += "@font-face{font-family:'%s';src:url(data:font/ttf;base64,%s);font-weight:%d;font-style:%s;}" % (famille, b64, poids, style)
		_FONTS_CSS["css"] = css
	return _FONTS_CSS["css"]


def dimensions_figures_mm(page: dict, fmt: list, tailles_images: dict | None = None, largeur_texte_mm: float = 186.0) -> list[dict]:
	"""[{id, largeur_mm, hauteur_mm}] des figures d'une page structurée ; une image ajoutée prend
	sa largeur réglée (% du texte) et le rapport de ses pixels (`tailles_images` {id: (w, h)}). Pur."""
	out = []
	for b in page.get("blocs", []):
		if b.get("type") == "figure":
			x0, y0, x1, y1 = b["bbox"]
			out.append({"id": b["id"], "largeur_mm": round((x1 - x0) / 100 * fmt[0] * 25.4 / 72, 1),
			            "hauteur_mm": round((y1 - y0) / 100 * fmt[1] * 25.4 / 72, 1)})
		elif b.get("type") == "image":
			w = largeur_texte_mm * b.get("largeur", LARGEUR_IMAGE_DEFAUT) / 100.0
			px = (tailles_images or {}).get(b["id"])
			h = w * px[1] / px[0] if px and px[0] else w * 0.6
			out.append({"id": b["id"], "largeur_mm": round(w, 1), "hauteur_mm": round(h, 1), "ajoutee": True})
	return out


def message_mise_en_page(page: dict, traductions: dict, fmt_source: list, format_sortie: tuple, langue: dict, famille: str,
                         couleur: str, tailles_images: dict | None = None) -> str:
	"""Le message utilisateur : format, marges, langue, police, figures, blocs traduits (JSON). Pur."""
	w_mm, h_mm = mm_page(format_sortie)
	blocs = [{k: v for k, v in bloc_traduit(b, traductions).items() if k not in ("bbox", "masques", "fichier")} for b in page.get("blocs", [])]
	return json.dumps({
		"page_mm": {"width": w_mm, "height": h_mm, "margins_mm": 12},
		"language": {"code": langue.get("code"), "name": langue.get("libelle"), "rtl": bool(langue.get("rtl"))},
		"font_family": famille, "accent_colour": couleur,
		"figures": dimensions_figures_mm(page, fmt_source, tailles_images, largeur_texte_mm=w_mm - 24),
		"blocks": blocs,
	}, ensure_ascii=False)


def mm_page(format_pts) -> tuple:
	"""(largeur, hauteur) en mm, à une décimale, arrondis vers le BAS — les MÊMES nombres pour l'IA
	(.page) et pour wkhtmltopdf (page-width/height) ; l'IA arrondit volontiers 197,9 en 198 et la page
	HTML déborde alors d'un dixième sur une deuxième page blanche (vu le 25/09/2026). Pur."""
	import math

	return tuple(math.floor(v * 25.4 / 72 * 10) / 10 for v in format_pts)


HAUTEUR_DEBORDEMENT_PX = 3   # à 72 dpi (1 px ≈ 0,35 mm) : au-delà, ce qui déborde est du contenu, pas une bande


def page_est_un_debordement(page) -> bool:
	"""Vrai si la page ne porte qu'une bande de quelques dixièmes de millimètre en haut (le fond ou
	le trait d'une page HTML un rien trop haute) : rien d'autre. Une ligne de texte (≥ 2 mm) n'est
	jamais prise pour un débordement vide."""
	import pymupdf

	pix = page.get_pixmap(dpi=72, alpha=False, colorspace=pymupdf.csGRAY)
	larg, octets = pix.width, pix.samples
	derniere = -1
	for y in range(pix.height):
		ligne = octets[y * larg:(y + 1) * larg]
		if any(v < 240 for v in ligne):
			derniere = y
	return derniere < HAUTEUR_DEBORDEMENT_PX


def sans_pages_blanches(pdf_bytes: bytes) -> bytes:
	"""Retire les pages de FIN qui ne sont qu'un débordement d'une bande (voir
	`page_est_un_debordement`). Une page qui porte du contenu n'est jamais retirée."""
	import pymupdf

	d = pymupdf.open(stream=pdf_bytes, filetype="pdf")
	garder = len(d)
	while garder > 1 and page_est_un_debordement(d[garder - 1]):
		garder -= 1
	if garder == len(d):
		return pdf_bytes
	d.select(list(range(garder)))
	return d.tobytes()


def remplacer_figures(html_: str, figures: dict) -> str:
	"""`fig:<id>` -> data: URI PNG. Une figure inconnue devient un cadre vide (pas d'image cassée). Pur."""
	import base64

	def rempl(m):
		ident = m.group(1)
		if ident in figures:
			mime = "image/png" if figures[ident][:4] == b"\x89PNG" else "image/jpeg"
			return 'src="data:%s;base64,%s"' % (mime, base64.b64encode(figures[ident]).decode())
		return 'src="" style="display:none"'
	return re.sub(r'src=["\']fig:([0-9a-f]{12})["\']', rempl, html_)


def injecter_polices(html_: str, css: str) -> str:
	"""Le CSS des polices juste après <head> (ou en tête si absent). Pur."""
	bloc = "<style>%s html,body{margin:0;padding:0;}</style>" % css
	m = re.search(r"<head[^>]*>", html_, flags=re.I)
	if m:
		return html_[:m.end()] + bloc + html_[m.end():]
	return bloc + html_


def html_vers_pdf(html_: str, format_sortie: tuple) -> bytes:
	"""wkhtmltopdf, page au format demandé, sans marges (la page HTML porte les siennes)."""
	import pdfkit

	w_mm, h_mm = mm_page(format_sortie)
	options = {"page-width": "%.1fmm" % w_mm, "page-height": "%.1fmm" % h_mm, "margin-top": "0", "margin-bottom": "0",
	           "margin-left": "0", "margin-right": "0", "disable-smart-shrinking": "", "encoding": "UTF-8", "quiet": "",
	           "dpi": "96", "print-media-type": "", "disable-javascript": "", "disable-local-file-access": "", "load-error-handling": "ignore"}
	return sans_pages_blanches(pdfkit.from_string(html_, False, options=options))


def _normaliser_texte(t: str) -> str:
	return re.sub(r"[^a-z0-9\u00c0-\u024f]+", "", (t or "").lower())


def textes_absents(texte_pdf: str, blocs_traduits: list[dict], longueur: int = 24) -> list[str]:
	"""Les textes des blocs dont le début (24 caractères utiles) n'apparaît pas dans le texte du PDF
	rendu : coupés, cachés ou omis par la mise en page. Comparaison sans espaces ni ponctuation. Pur."""
	corpus = _normaliser_texte(texte_pdf)
	absents = []
	for b in blocs_traduits:
		textes = []
		if b.get("type") in ("titre", "paragraphe", "note", "legende"):
			textes = [b.get("texte", "")]
		elif b.get("type") in ("liste", "etapes"):
			textes = b.get("items", [])
		elif b.get("type") == "tableau":
			textes = [c for l in b.get("lignes", []) for c in l]
		elif b.get("type") == "figure" and b.get("legende"):
			textes = [b["legende"]]
		for t in textes:
			n = _normaliser_texte(t)
			if len(n) >= 4 and n[:longueur] not in corpus:
				absents.append(t)
	return absents


def _figures_png(pdf_bytes: bytes, page: dict, no: int, fmt: list, traductions: dict | None = None) -> dict:
	out = {}
	for b in page.get("blocs", []):
		if b.get("type") not in ("figure", "image"):
			continue
		try:
			out[b["id"]] = octets_figure(pdf_bytes, b, no, fmt, traductions)
		except Exception:
			frappe.log_error(title="Aquaworld IA : figure p%s" % no, message=frappe.get_traceback())
	return out


def _mises_en_page(l) -> dict:
	try:
		m = json.loads(l.get("mises_en_page") or "{}")
	except ValueError:
		m = {}
	return m if isinstance(m, dict) else {}


def rendre_mise_en_page(doc, l, no: int, html_: str | None = None) -> tuple[bytes, int]:
	"""Le PDF d'une page mise en page par IA (HTML stocké ou donné). -> (pdf, nombre de pages)."""
	import pymupdf

	from aquaworld_ia.manuels.studio import _pdf, analyse_du_manuel

	structure = lire(doc.get("structure"))
	page = structure["pages"].get(str(no)) or {}
	if html_ is None:
		html_ = (_mises_en_page(l).get(str(no)) or {}).get("html")
	if not html_:
		frappe.throw(_("Pas de mise en page IA pour la page {0}.").format(no + 1))
	analyse = analyse_du_manuel(doc)
	fmt = analyse["formats"][no]
	figures = _figures_png(_pdf(doc), page, no, fmt, _traductions(l))
	pdf = html_vers_pdf(injecter_polices(remplacer_figures(html_, figures), css_polices_data_uri()), format_sortie(_reglages_gabarit(), fmt))
	return pdf, len(pymupdf.open(stream=pdf, filetype="pdf"))


def mise_en_page_ia(doc, l, no: int) -> dict:
	"""L'IA écrit le HTML de la page `no` dans la langue de `l`, rendu et stocké. -> {html, pages}."""
	from aquaworld_ia.manuels.studio import _pdf, analyse_du_manuel, langue_infos

	structure = lire(doc.get("structure"))
	page = structure["pages"].get(str(no))
	if not page or not page.get("blocs"):
		frappe.throw(_("Lisez d'abord la page {0} par IA.").format(no + 1))
	analyse = analyse_du_manuel(doc)
	infos = langue_infos(l.langue)
	g = _reglages_gabarit()
	famille = rendu.famille(infos)
	systeme = PROMPT_MISE_EN_PAGE.replace("<FAMILLE>", famille)
	user = message_mise_en_page(page, _traductions(l), analyse["formats"][no], format_sortie(g, analyse["formats"][no]), infos, famille,
	                            g["couleur"], tailles_images(page))
	image = image_page_pour_ia(_pdf(doc), no)
	sortie = chat_json_image(systeme, user, image, fonctionnalite=FONCTIONNALITE_MEP, doc=doc)
	html_ = sortie.get("html") if isinstance(sortie, dict) else None
	if not html_ or "<" not in html_:
		frappe.throw(_("L'IA n'a pas rendu de page HTML."))
	pdf_, n = rendre_mise_en_page(doc, l, no, html_)
	absents = _absents_du_rendu(pdf_, page, _traductions(l), infos)
	if n > 1 or absents:
		# la page déborde ou coupe des textes : on la renvoie UNE fois à l'IA pour qu'elle resserre
		# (tailles, interlignes, espaces) — sans rien perdre (demande utilisateur 25/09/2026 : bas de
		# couverture coupé)
		reprise = "Your previous HTML for this page is not acceptable: "
		if n > 1:
			reprise += "it overflowed onto %d printed pages. " % n
		if absents:
			reprise += "these texts are cut off or missing in the rendered page: %s. " % json.dumps(absents[:12], ensure_ascii=False)
		reprise += ("Return the SAME page, same layout and same content, so that EVERYTHING is visible on ONE page: smaller font sizes (min 7pt), "
		            "tighter line-height and margins, smaller figures if needed; no overflow:hidden, no fixed heights that clip content. "
		            "Previous HTML:\n%s" % html_)
		sortie = chat_json_image(systeme, user + "\n\n" + reprise, image, fonctionnalite=FONCTIONNALITE_MEP, doc=doc)
		html2 = sortie.get("html") if isinstance(sortie, dict) else None
		if html2 and "<" in html2:
			pdf2, n2 = rendre_mise_en_page(doc, l, no, html2)
			absents2 = _absents_du_rendu(pdf2, page, _traductions(l), infos)
			if (n2, len(absents2)) <= (n, len(absents)):
				html_, n = html2, n2
	m = _mises_en_page(l)
	m[str(no)] = {"html": html_, "pages": n}
	frappe.db.set_value("Manuel Article Traduction", l.name, "mises_en_page", json.dumps(m, ensure_ascii=False), update_modified=False)
	l.mises_en_page = json.dumps(m, ensure_ascii=False)
	return {"html": html_, "pages": n}


def tailles_images(page: dict) -> dict:
	"""{id: (largeur, hauteur) en pixels} des images ajoutées d'une page (pour le rapport d'aspect)."""
	from PIL import Image

	out = {}
	for b in page.get("blocs", []):
		if b.get("type") == "image":
			try:
				im = Image.open(io.BytesIO(fichiers.lire(b["fichier"])))
				out[b["id"]] = im.size
			except Exception:
				pass
	return out


def _absents_du_rendu(pdf_bytes: bytes, page: dict, traductions: dict, infos: dict) -> list[str]:
	"""Les textes coupés dans le rendu (vide pour une langue RTL : wkhtmltopdf n'en extrait que des
	glyphes)."""
	import pymupdf

	if infos.get("rtl"):
		return []
	d = pymupdf.open(stream=pdf_bytes, filetype="pdf")
	texte = "\n".join(p.get_text() for p in d)
	return textes_absents(texte, [bloc_traduit(b, traductions) for b in page.get("blocs", [])])


@frappe.whitelist()
def composer_page_ia(manuel: str, langue: str, no: int) -> dict:
	"""Mettre en page cette page par IA, tout de suite, et rendre son aperçu."""
	doc = _doc(manuel)
	l = _ligne(doc, langue)
	journal.verifier_plafond()
	r = mise_en_page_ia(doc, l, cint(no))
	frappe.db.commit()
	return dict(apercu_page(manuel, langue, no), pages_ia=r["pages"])


@frappe.whitelist()
def composer_tout_ia(manuel: str, langue: str, refaire: int = 0) -> dict:
	"""Toutes les pages lues, mises en page par IA en tâche de fond (une par une)."""
	doc = _doc(manuel)
	_ligne(doc, langue)
	cle = _cle_traduction(manuel, langue)
	if etat.bloque(etat.lire_etat(GENRE_MEP, cle)):
		frappe.throw(_("La mise en page IA en {0} est déjà en cours.").format(langue))
	journal.verifier_plafond()
	etat.demarrer(GENRE_MEP, cle, langue=langue)
	frappe.enqueue("aquaworld_ia.manuels.reconstruit.job_composer_ia", queue="long", timeout=7200,
	               job_id="aqia-mep-%s-%s" % (manuel, langue), deduplicate=True, manuel=manuel, langue=langue, refaire=cint(refaire), utilisateur=frappe.session.user)
	return etat.lire_etat(GENRE_MEP, cle)


def job_composer_ia(manuel: str, langue: str, refaire: int = 0, utilisateur: str | None = None) -> None:
	from aquaworld_ia.manuels.studio import langue_infos

	doc = frappe.get_doc("Manuel Article", manuel)
	l = _ligne(doc, langue)
	cle = _cle_traduction(manuel, langue)
	nom_langue = langue_infos(langue).get("libelle") or langue
	try:
		structure = lire(doc.get("structure"))
		nos = sorted((cint(k) for k, p in structure["pages"].items() if p.get("blocs")))
		faites = _mises_en_page(l)
		for k, no in enumerate(nos):
			if not refaire and str(no) in faites:
				continue
			etat.progresser(GENRE_MEP, cle, "%s : mise en page de la page %d / %d" % (nom_langue, no + 1, structure["pages"] and max(nos) + 1), int(100 * k / max(1, len(nos))), EVENEMENT, utilisateur, manuel=manuel)
			try:
				mise_en_page_ia(doc, l, no)
			except Exception:
				frappe.log_error(title="Aquaworld IA : mise en page p%d %s" % (no + 1, manuel), message=frappe.get_traceback())
			frappe.db.commit()
		etat.terminer(GENRE_MEP, cle, "termine")
		etat.progresser(GENRE_MEP, cle, "%s : mise en page terminée" % nom_langue, 100, EVENEMENT, utilisateur, fin=1, manuel=manuel)
	except Exception as e:
		frappe.log_error(title="Aquaworld IA : mise en page %s (%s)" % (manuel, langue), message=frappe.get_traceback())
		etat.terminer(GENRE_MEP, cle, "echec", erreur=str(e)[:300])
		etat.progresser(GENRE_MEP, cle, "%s : échec : %s" % (langue, str(e)[:120]), 100, EVENEMENT, utilisateur, fin=1, manuel=manuel)


@frappe.whitelist()
def retirer_mise_en_page(manuel: str, langue: str, no: int) -> dict:
	doc = _doc(manuel)
	l = _ligne(doc, langue)
	m = _mises_en_page(l)
	m.pop(str(cint(no)), None)
	frappe.db.set_value("Manuel Article Traduction", l.name, "mises_en_page", json.dumps(m, ensure_ascii=False), update_modified=False)
	l.mises_en_page = json.dumps(m, ensure_ascii=False)
	return apercu_page(manuel, langue, no)


def assembler_ia(doc, l, langue: dict, titre: str, sous_titre: str) -> bytes:
	"""Le manuel « mise en page IA » : couverture, sommaire, puis chaque page IA dans l'ordre des
	pages lues, pieds de page. Une page sans mise en page IA est composée par le gabarit fluide."""
	import pymupdf

	from aquaworld_ia.manuels.studio import _pdf, analyse_du_manuel

	structure = lire(doc.get("structure"))
	trad = _traductions(l)
	analyse = analyse_du_manuel(doc)
	g = _reglages_gabarit()
	W, H = format_sortie(g, analyse["formats"][0] if analyse["formats"] else None)
	famille = rendu.famille(langue)
	archive = rendu.polices_archive()
	css = rendu.css_polices(rendu.polices_personnalisees(), rendu.polices_utilisateur()) + css_document(g["couleur"], famille, bool(langue.get("rtl")))
	logo = None
	if g.get("logo"):
		try:
			from aquaworld_ia.ia.images import normaliser_reference

			logo = normaliser_reference(fichiers.lire(g["logo"]))
		except Exception:
			logo = None
	mep = _mises_en_page(l)
	corps = pymupdf.open()
	titres, pages_titres = [], []
	for no in sorted((cint(k) for k, p in structure["pages"].items() if p.get("blocs"))):
		page = structure["pages"][str(no)]
		debut = len(corps)
		if str(no) in mep:
			pdf, _n = rendre_mise_en_page(doc, l, no)
		else:
			seule = {"version": structure["version"], "pages": {str(no): page}}
			pdf = composer_pdf(_pdf(doc), seule, trad, langue, analyse["formats"], titre, habillage=False, gabarit=g)
		corps.insert_pdf(pymupdf.open(stream=pdf, filetype="pdf"))
		for b in page.get("blocs", []):
			if b.get("type") == "titre" and b.get("niveau", 1) == 1:
				titres.append(bloc_traduit(b, trad)["texte"])
				pages_titres.append(debut)
	doc_pdf = pymupdf.open()
	_couverture(doc_pdf, W, H, titre, sous_titre, langue, g, logo, famille, css, archive)
	decalage = 2 if titres else 1
	if titres:
		_sommaire(doc_pdf, W, H, titres, [p + decalage + 1 for p in pages_titres], langue, g, famille, css, archive, bool(langue.get("rtl")))
	doc_pdf.insert_pdf(corps)
	_pieds_de_page(doc_pdf, W, H, g, logo, famille, css, archive, bool(langue.get("rtl")), depuis=decalage)
	try:
		doc_pdf.subset_fonts()
	except Exception:
		pass
	sortie = io.BytesIO()
	doc_pdf.save(sortie, garbage=4, deflate=True, deflate_images=True)
	return sortie.getvalue()


# ------------------------------------------------------------------ IA sur UN bloc (demande utilisateur 25/09/2026)


@frappe.whitelist()
def traduire_bloc(manuel: str, langue: str, no: int, ident: str, tout: int = 0) -> dict:
	"""Traduire tout de suite les textes d'UN bloc : ceux qui manquent, ou tous (`tout`, pour
	retraduire). Les autres blocs ne bougent pas."""
	from aquaworld_ia.ia.client import reglages
	from aquaworld_ia.manuels.studio import langue_infos

	doc = _doc(manuel)
	l = _ligne(doc, langue)
	journal.verifier_plafond()
	structure = lire(doc.get("structure"))
	page = structure["pages"].get(str(cint(no))) or {}
	bloc = next((b for b in page.get("blocs", []) if b.get("id") == ident), None)
	if not bloc:
		frappe.throw(_("Bloc introuvable (la page a peut-être été relue)."))
	trad = _traductions(l)
	cibles = [{"id": cle, "texte": texte} for cle, texte in textes_du_bloc(bloc)
	          if est_traduisible(texte) and (cint(tout) or not trad.get(cle))]
	n = 0
	if cibles:
		r = reglages()
		glossaire = "\n".join(x for x in (getattr(r, "glossaire_global", "") or "", doc.glossaire or "") if x)
		nouvelles, _laisses = traduction.traduire_tout(cibles, langue_infos(langue), glossaire=glossaire,
		                                               instructions=getattr(r, "instructions_globales", "") or "",
		                                               contexte=doc.contexte or "", doc=doc)
		trad.update({str(k): v for k, v in nouvelles.items()})
		n = len(nouvelles)
		frappe.db.set_value("Manuel Article Traduction", l.name, "traductions_structure", json.dumps(trad, ensure_ascii=False), update_modified=False)
		frappe.db.commit()
	return dict(structure_page(manuel, langue, no), n=n)


@frappe.whitelist()
def traduire_figure(manuel: str, langue: str, no: int, ident: str, instruction: str = "") -> dict:
	"""Redessiner par IA une figure avec ses mots dans la langue (même atelier que le mode en place :
	`studio.traduire_illustration`), et la garder pour cette langue. Une image facturée."""
	from aquaworld_ia.ia import images
	from aquaworld_ia.ia.client import qualite_image
	from aquaworld_ia.manuels import studio as S
	from aquaworld_ia.manuels.studio import _pdf, analyse_du_manuel, langue_infos

	doc = _doc(manuel)
	l = _ligne(doc, langue)
	journal.verifier_plafond()
	structure = lire(doc.get("structure"))
	page = structure["pages"].get(str(cint(no))) or {}
	bloc = next((b for b in page.get("blocs", []) if b.get("id") == ident and b.get("type") == "figure"), None)
	if not bloc:
		frappe.throw(_("Figure introuvable (la page a peut-être été relue)."))
	analyse = analyse_du_manuel(doc)
	fmt = analyse["formats"][cint(no)]
	infos = langue_infos(langue)
	x0, y0, x1, y1 = bloc["bbox"]
	bbox_pt = (x0 / 100 * fmt[0], y0 / 100 * fmt[1], x1 / 100 * fmt[0], y1 / 100 * fmt[1])
	reference = appliquer_masques(rendu.clip_page(_pdf(doc), cint(no), bbox_pt), bloc["bbox"], bloc.get("masques") or [])
	taille = S.taille_illustration(bbox_pt)
	canevas, cadre = S.poser_sur_canevas(reference, taille)
	pngs = images.editer(S.prompt_illustration(infos, instruction), [("illustration", canevas)], taille=taille,
	                     qualite=qualite_image(), n=1, fonctionnalite=S.FONCTIONNALITE_ILLUSTRATION, doc=doc, fidelite="high")
	resultat = S.recadrer(pngs[0], cadre)
	fichier = save_file("%s-p%d-fig-%s-%s.png" % (doc.name, cint(no) + 1, ident[:8], langue), resultat, "Manuel Article", doc.name, is_private=1).file_url
	trad = _traductions(l)
	trad[cle_figure(bloc)] = fichier
	frappe.db.set_value("Manuel Article Traduction", l.name, "traductions_structure", json.dumps(trad, ensure_ascii=False), update_modified=False)
	frappe.db.commit()
	return dict(structure_page(manuel, langue, no), fichier=fichier)


@frappe.whitelist()
def retirer_figure_traduite(manuel: str, langue: str, no: int, ident: str) -> dict:
	doc = _doc(manuel)
	l = _ligne(doc, langue)
	trad = _traductions(l)
	trad.pop("figure:" + ident, None)
	frappe.db.set_value("Manuel Article Traduction", l.name, "traductions_structure", json.dumps(trad, ensure_ascii=False), update_modified=False)
	return structure_page(manuel, langue, no)
