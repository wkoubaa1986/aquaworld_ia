"""Réécriture EN PLACE d'un PDF : on efface la couche texte de chaque paragraphe et on pose la
traduction dans la même boîte (PyMuPDF `insert_htmlbox`, qui réduit la police jusqu'à ce que ça
tienne et façonne l'arabe de droite à gauche).

Images, dessins et fonds restent intacts : la redaction ne retire QUE le texte (`images=0,
graphics=0`), sans aplat blanc (`fill=False`). Un texte sur fond coloré garde son fond.
"""

from __future__ import annotations

import html
import io
import os

# ⚠️ Cet import manquait jusqu'à la v0.20.0 : `polices_personnalisees` levait un NameError avalé
# par son `except`, et les polices des Réglages (titres, textes) comme celles des langues n'ont
# jamais été appliquées.
import frappe

CHEMIN_POLICES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public", "fonts")
ECHELLE_MIN = 0.5           # en dessous, on ne pose pas : le bloc est signalé « non placé »
ECHELLE_REDUIT = 0.8        # en dessous, le bloc compte comme « réduit » (à relire)
EXTENSION_MAX = 0.4         # une boîte peut s'allonger vers le bas de 40 % au plus


#: Les familles des polices PERSONNALISÉES (demande utilisateur 23/09/2026 : « je peux choisir la
#: police ? »). Réglages : titres et textes latins ; Langue : une police par langue.
FAMILLE_TITRES = "Police titres"
FAMILLE_TEXTES = "Police textes"


def famille_langue_perso(code: str) -> str:
	return "Police %s" % code


#: Les polices LIVRÉES (licence OFL, fichiers dans public/fonts, construits par
#: outils/construire_polices.py, copyrights dans public/fonts/POLICES.txt) : famille -> fichiers (normal, gras, italique, gras italique),
#: None quand le style n'existe pas. MuPDF ne fabrique NI gras NI italique (vérifié le 24/09/2026 :
#: `font-style:italic` sur une police sans fichier italique sort droit) — d'où quatre fichiers.
POLICES_LIVREES = {
	"Noto Sans": ("NotoSans-Regular.ttf", "NotoSans-Bold.ttf", "NotoSans-Italic.ttf", "NotoSans-BoldItalic.ttf"),
	"Noto Serif": ("NotoSerif-Regular.ttf", "NotoSerif-Bold.ttf", "NotoSerif-Italic.ttf", "NotoSerif-BoldItalic.ttf"),
	"Montserrat": ("Montserrat-Regular.ttf", "Montserrat-Bold.ttf", "Montserrat-Italic.ttf", "Montserrat-BoldItalic.ttf"),
	"Poppins": ("Poppins-Regular.ttf", "Poppins-Bold.ttf", "Poppins-Italic.ttf", "Poppins-BoldItalic.ttf"),
	"Open Sans": ("OpenSans-Regular.ttf", "OpenSans-Bold.ttf", "OpenSans-Italic.ttf", "OpenSans-BoldItalic.ttf"),
	"Lato": ("Lato-Regular.ttf", "Lato-Bold.ttf", "Lato-Italic.ttf", "Lato-BoldItalic.ttf"),
	"Roboto": ("Roboto-Regular.ttf", "Roboto-Bold.ttf", "Roboto-Italic.ttf", "Roboto-BoldItalic.ttf"),
	"EB Garamond": ("EBGaramond-Regular.ttf", "EBGaramond-Bold.ttf", "EBGaramond-Italic.ttf", "EBGaramond-BoldItalic.ttf"),
	"Oswald": ("Oswald-Regular.ttf", "Oswald-Bold.ttf", None, None),
	"Noto Naskh Arabic": ("NotoNaskhArabic-Regular.ttf", "NotoNaskhArabic-Bold.ttf", None, None),
}
#: Les quatre styles d'une famille : (clé, font-weight, font-style). La clé est aussi le nom du
#: champ Attach de la fiche « Police Emballage ».
STYLES_POLICE = (("regulier", 400, "normal"), ("gras", 700, "normal"), ("italique", 400, "italic"),
                 ("gras_italique", 700, "italic"))


def polices_utilisateur() -> list[tuple[str, dict]]:
	"""[(famille, {style: url})] des polices ajoutées depuis le studio (DocType « Police
	Emballage ») — vide hors site. Ne lève jamais."""
	try:
		lignes = frappe.get_all("Police Emballage", fields=["name"] + [c for c, _p, _s in STYLES_POLICE])
	except Exception:
		return []
	return [(l.name, {c: l.get(c) for c, _p, _s in STYLES_POLICE if l.get(c)}) for l in lignes if l.get("regulier")]


def familles_disponibles() -> set[str]:
	"""Les familles qu'un texte peut demander : livrées + ajoutées. Une famille inconnue (police
	supprimée depuis) retombe sur la police par défaut de la langue."""
	return set(POLICES_LIVREES) | {f for f, _s in polices_utilisateur()}


def polices_personnalisees() -> list[tuple[str, str]]:
	"""[(famille, url du fichier)] — vide hors site ou sans réglage. Ne lève jamais."""
	out = []
	try:
		r = frappe.get_cached_doc("Aquaworld IA Reglages")
		if getattr(r, "police_titres", None):
			out.append((FAMILLE_TITRES, r.police_titres))
		if getattr(r, "police_textes", None):
			out.append((FAMILLE_TEXTES, r.police_textes))
		for lg in frappe.get_all("Aquaworld IA Langue", filters={"police_fichier": ("!=", "")},
		                         fields=["code", "police_fichier"]):
			out.append((famille_langue_perso(lg.code), lg.police_fichier))
	except Exception:
		return []
	return out


def nom_fichier_police(famille: str) -> str:
	"""Le nom sous lequel la police entre dans l'archive : sans espace ni accent, .ttf. Pur."""
	import re

	return re.sub(r"[^A-Za-z0-9_-]+", "_", famille).strip("_") + ".ttf"


def polices_archive():
	"""L'archive des polices : celles livrées, plus les personnalisées (lues depuis les fichiers du
	site). Une police illisible est ignorée, jamais bloquante : le PDF sort avec Noto."""
	import pymupdf

	from aquaworld_ia.ia import fichiers

	archive = pymupdf.Archive(CHEMIN_POLICES)
	for famille, url in polices_personnalisees():
		try:
			archive.add(fichiers.lire(url), nom_fichier_police(famille))
		except Exception:
			frappe.log_error(title="Aquaworld IA : police %s" % famille, message=frappe.get_traceback())
	for famille, styles in polices_utilisateur():
		for cle, url in styles.items():
			try:
				archive.add(fichiers.lire(url), nom_fichier_police("%s %s" % (famille, cle)))
			except Exception:
				frappe.log_error(title="Aquaworld IA : police %s (%s)" % (famille, cle)[:140], message=frappe.get_traceback())
	return archive


def _font_face(famille: str, fichier: str, poids: int, style: str) -> str:
	return "@font-face{font-family:'%s';src:url(%s);font-weight:%d;font-style:%s;}" % (famille, fichier, poids, style)


def css_polices(personnalisees: list[tuple[str, str]] | None = None, utilisateur: list[tuple[str, dict]] | None = None) -> str:
	"""Les @font-face : les polices livrées (chaque style qui a son fichier), les polices des
	Réglages et des langues (un seul fichier pour 400 et 700 : le gras n'est alors pas plus épais,
	mais la police est bien celle demandée), puis celles ajoutées depuis le studio. Pur."""
	css = ""
	for famille, fichiers_ in POLICES_LIVREES.items():
		for (_cle, poids, style), fichier in zip(STYLES_POLICE, fichiers_):
			if fichier:
				css += _font_face(famille, fichier, poids, style)
	for famille, _url in personnalisees or []:
		f = nom_fichier_police(famille)
		css += _font_face(famille, f, 400, "normal") + _font_face(famille, f, 700, "normal")
	for famille, styles in utilisateur or []:
		for cle, poids, style in STYLES_POLICE:
			if styles.get(cle):
				css += _font_face(famille, nom_fichier_police("%s %s" % (famille, cle)), poids, style)
	return css


def css_base() -> str:
	return (css_polices(polices_personnalisees(), polices_utilisateur())
	        + "body{margin:0;padding:0;}p{margin:0;padding:0;line-height:1.15;}")


def famille(langue: dict) -> str:
	"""La famille de police d'une langue : sa police personnalisée d'abord, sinon son choix,
	sinon Noto selon le sens d'écriture. Pur."""
	if langue.get("police_fichier"):
		return famille_langue_perso(langue.get("code") or "x")
	return langue.get("police") or ("Noto Naskh Arabic" if langue.get("rtl") else "Noto Sans")


def html_paragraphe(texte: str, style: dict, rtl: bool = False, famille_police: str = "Noto Sans") -> str:
	"""Un <p> stylé comme l'original (taille, gras, italique, couleur, alignement). Pur."""
	align = "right" if rtl else (style.get("align") or "left")
	if rtl and style.get("align") == "center":
		align = "center"
	regles = [
		"font-family:'%s'" % famille_police,
		"font-size:%spt" % style.get("taille", 10),
		"font-weight:%d" % (700 if style.get("gras") else 400),
		"font-style:%s" % ("italic" if style.get("italique") else "normal"),
		"color:%s" % (style.get("couleur") or "#000000"),
		"text-align:%s" % align,
		"direction:%s" % ("rtl" if rtl else "ltr"),
	]
	contenu = html.escape(texte or "").replace("\n", "<br>")
	return "<p style=\"%s\">%s</p>" % (";".join(regles), contenu)


def rect_insertion(bbox, page_rect, voisins, marge: float = 1.5, extension_max: float = EXTENSION_MAX,
                   une_ligne: bool = False, limite_droite: float | None = None) -> tuple:
	"""La boîte élargie vers le bas jusqu'au voisin suivant (au plus +extension_max de sa
	hauteur), pour absorber l'allongement du français ou de l'arabe. Un bloc d'UNE ligne (titre,
	entrée de liste) s'élargit d'abord vers la droite, jusqu'au voisin de la même ligne ou à
	`limite_droite` (le bord droit du texte de la page) : sa boîte a exactement la largeur de
	l'anglais, sinon le titre sort minuscule (vu le 24/09/2026). Pur."""
	x0, y0, x1, y1 = bbox
	h = y1 - y0
	if une_ligne:
		droite = min(page_rect[2] - marge, limite_droite) if limite_droite else page_rect[2] - marge
		for v in voisins or []:
			# un voisin sur la même ligne, à droite : on s'arrête avant lui
			if v[0] >= x1 - 0.5 and v[3] > y0 and v[1] < y1:
				droite = min(droite, v[0] - marge)
		x1 = max(x1, droite)
	limite = min(page_rect[3] - marge, y1 + h * extension_max)
	for v in voisins or []:
		# un voisin = une boîte située plus bas et qui chevauche horizontalement
		if v[1] >= y1 - 0.5 and v[2] > x0 and v[0] < x1:
			limite = min(limite, v[1] - marge)
	return (x0, y0, x1, max(y1, limite))


def est_pivote(p: dict) -> bool:
	"""Un paragraphe écrit de biais ou à la verticale : il reste en anglais (pas de pose tournée). Pur."""
	return tuple(p.get("dir", (1, 0))) != (1, 0)


def plan_page(no: int, paragraphes: list[dict], traductions: dict, edition: dict | None = None,
              images: list[dict] | None = None) -> dict:
	"""Ce qu'il y a à faire sur la page `no`, avant tout PDF (pur, testé) :
	- `redactions` : les boîtes d'origine dont on efface le texte anglais ;
	- `textes` : les paragraphes à reposer (boîte déplacée ou d'origine, texte corrigé ou IA, taille
	  bornée, `auto` = la boîte peut encore s'allonger vers le bas) ;
	- `libres` : les cases de texte ajoutées ; `images` : les illustrations remplacées ;
	- `pivotes` : les paragraphes tournés, laissés tels quels.
	Traitement d'un bloc (édition) : « anglais » = on n'y touche pas ; « efface » = on efface sans
	rien poser ; sinon on pose le texte effectif, et sans texte le bloc reste en anglais."""
	from aquaworld_ia.manuels import edition as E

	edition = E.lire(edition)
	trad = E.traductions_str(traductions)
	plan = {"redactions": [], "redactions_ocr": [], "textes": [], "libres": [], "images": [], "pivotes": 0}
	for p in paragraphes:
		if p.get("page") != no:
			continue
		b = edition["blocs"].get(str(p["id"]), {})
		traitement = b.get("traitement", "traduit")
		if traitement == "anglais":
			continue
		# un paragraphe reconnu par OCR (lettres en contours, scan) s'efface autrement : on retire
		# les tracés vectoriels de sa boîte et on la blanchit
		cible = plan["redactions_ocr"] if p.get("ocr") else plan["redactions"]
		if traitement == "efface":
			cible.append(list(p["bbox"]))
			continue
		texte = E.texte_effectif(p["id"], trad, edition)
		if texte is None:
			continue
		if est_pivote(p):
			plan["pivotes"] += 1
			continue
		cible.append(list(p["bbox"]))
		style = dict(p["style"])
		if b.get("taille"):
			style["taille"] = b["taille"]
		plan["textes"].append({"id": p["id"], "bbox": list(b.get("bbox") or p["bbox"]), "origine": list(p["bbox"]),
		                       "texte": texte, "style": style, "auto": not b.get("bbox"), "lignes": p.get("lignes", 1)})
	for l in edition["libres"]:
		if l.get("page") != no:
			continue
		if l.get("type", "texte") == "image":
			if l.get("fichier"):
				plan["images"].append({"id": l["id"], "bbox": list(l["bbox"]), "fichier": l["fichier"]})
		elif (l.get("texte") or "").strip():
			plan["libres"].append({"id": l["id"], "bbox": list(l["bbox"]), "texte": l["texte"], "fond": bool(l.get("fond", True)),
			                       "style": {"taille": l.get("taille") or 10, "gras": bool(l.get("gras")), "italique": False,
			                                 "couleur": l.get("couleur") or "#000000", "align": l.get("align") or "left"}})
	boites = {im["id"]: im["bbox"] for im in images or [] if im.get("page") == no}
	for ident, im in edition["images"].items():
		if ident in boites and im.get("fichier"):
			plan["images"].append({"id": ident, "bbox": list(boites[ident]), "fichier": im["fichier"]})
	plan["textes"] = grouper_entrees(plan["textes"])
	return plan


ECART_ENTREES = 1.5      # en hauteurs de ligne : au-delà, deux entrées de liste ne se suivent plus
DECALAGE_ENTREES = 30.0  # en points : des entrées d'une même liste partent du même bord gauche


def _hauteur_ligne(t: dict) -> float:
	o = t["origine"]
	return max(1.0, (o[3] - o[1]) / max(1, t.get("lignes", 1)))


def _se_suivent(a: dict, b: dict) -> bool:
	oa, ob = a["origine"], b["origine"]
	return (ob[1] - oa[3]) < ECART_ENTREES * _hauteur_ligne(a) and abs(ob[0] - oa[0]) <= DECALAGE_ENTREES


def grouper_entrees(textes: list[dict]) -> list[dict]:
	"""Les entrées de liste qui se suivent (« 1. … », « 2. … », puces) partagent UNE boîte — l'union
	des leurs — et un HTML à un <p> par entrée : chaque entrée garde sa ligne, et toute la liste se
	réduit ensemble, au lieu que chaque étape se batte seule dans sa petite boîte (vu le 24/09/2026 :
	6 étapes réduites à 70 % sur une page). Une entrée déplacée ou agrandie à la main (`auto`
	faux) reste seule. Pur."""
	from aquaworld_ia.manuels.extraction import commence_une_entree

	sorties, groupe = [], []

	def vider():
		if not groupe:
			return
		if len(groupe) == 1:
			sorties.append(groupe[0])
		else:
			boites = [t["origine"] for t in groupe]
			union = [min(b[0] for b in boites), min(b[1] for b in boites), max(b[2] for b in boites), max(b[3] for b in boites)]
			sorties.append({"id": groupe[0]["id"], "groupe": [t["id"] for t in groupe], "bbox": list(union), "origine": list(union),
			                "texte": "\n".join(t["texte"] for t in groupe), "style": dict(groupe[0]["style"]),
			                "styles": [t["style"] for t in groupe], "auto": True, "lignes": sum(t.get("lignes", 1) for t in groupe)})
		groupe.clear()

	for t in textes:
		entree = t.get("auto") and commence_une_entree(t["texte"])
		if entree and (not groupe or _se_suivent(groupe[-1], t)):
			groupe.append(t)
			continue
		vider()
		if entree:
			groupe.append(t)
		else:
			sorties.append(t)
	vider()
	return sorties


def html_groupe(textes: list[str], styles: list[dict], rtl: bool, famille_police: str) -> str:
	"""Un <p> par entrée, chacun dans son style, un petit espace entre deux entrées. Pur."""
	out = []
	for k, (texte, style) in enumerate(zip(textes, styles)):
		p = html_paragraphe(texte, style, rtl, famille_police)
		if k:
			p = p.replace("<p style=\"", "<p style=\"margin-top:0.25em;", 1)
		out.append(p)
	return "".join(out)


def executer_plan(page, plan: dict, langue: dict, archive, css: str, voisins: list | None = None,
                  lire_fichier=None) -> dict:
	"""Applique un `plan_page` sur une page PyMuPDF. -> stats {poses, reduits, non_places, pivotes,
	blocs: {id: {echelle, place}}}. Les images passent par `lire_fichier(url) -> octets`."""
	import pymupdf

	rtl = bool(langue.get("rtl"))
	police = famille(langue)
	stats = {"poses": 0, "reduits": 0, "non_places": [], "pivotes": plan.get("pivotes", 0), "blocs": {}}
	if plan.get("redactions_ocr"):
		for bbox in plan["redactions_ocr"]:
			page.add_redact_annot(pymupdf.Rect(*bbox), fill=(1, 1, 1))
		page.apply_redactions(images=0, graphics=1, text=0)   # graphics=1 : les tracés entièrement dans la boîte
	for bbox in plan["redactions"]:
		page.add_redact_annot(pymupdf.Rect(*bbox), fill=False)
	if plan["redactions"]:
		page.apply_redactions(images=0, graphics=0, text=0)
	page_rect = (page.rect.x0, page.rect.y0, page.rect.x1, page.rect.y1)
	# le bord droit du texte de la page : un titre s'élargit jusque-là, jamais dans la marge
	limite_droite = max((b[2] for b in (voisins or [])), default=None)
	for t in plan["textes"]:
		if t.get("groupe"):
			contenu = html_groupe(t["texte"].split("\n"), t["styles"], rtl, police)
		else:
			contenu = html_paragraphe(t["texte"], t["style"], rtl, police)
		ids = [str(i) for i in t.get("groupe") or [t["id"]]]
		rect = pymupdf.Rect(*t["bbox"])
		spare, echelle = page.insert_htmlbox(rect, contenu, css=css, scale_low=ECHELLE_MIN, archive=archive)
		if (spare < 0 or echelle < 1) and t.get("auto"):
			autres = [b for b in (voisins or []) if list(b) != t["origine"]]
			plus_grand = pymupdf.Rect(*rect_insertion(t["origine"], page_rect, autres, une_ligne=t.get("lignes", 1) == 1,
			                                          limite_droite=limite_droite))
			if plus_grand != rect:
				# on repart de la page propre : le premier essai a déjà posé le texte réduit
				page.add_redact_annot(rect, fill=False)
				page.apply_redactions(images=0, graphics=0, text=0)
				rect = plus_grand
				spare, echelle = page.insert_htmlbox(rect, contenu, css=css, scale_low=ECHELLE_MIN, archive=archive)
		if spare < 0:
			stats["non_places"].append({"id": t["id"], "texte": t["texte"][:80]})
			for i in ids:
				stats["blocs"][i] = {"echelle": round(echelle, 2), "place": False}
			# On pose quand même, réduit au maximum : un texte trop petit se relit, un trou non.
			page.insert_htmlbox(rect, contenu, css=css, scale_low=0.25, archive=archive)
			continue
		stats["poses"] += len(ids)
		for i in ids:
			stats["blocs"][i] = {"echelle": round(echelle, 2), "place": True}
		if echelle < ECHELLE_REDUIT:
			stats["reduits"] += len(ids)
	for l in plan["libres"]:
		rect = pymupdf.Rect(*l["bbox"])
		if l.get("fond"):
			page.draw_rect(rect, color=None, fill=(1, 1, 1), overlay=True)
		contenu = html_paragraphe(l["texte"], l["style"], rtl, police)
		spare, echelle = page.insert_htmlbox(rect, contenu, css=css, scale_low=0.25, archive=archive)
		stats["blocs"][str(l["id"])] = {"echelle": round(echelle, 2), "place": spare >= 0}
		if spare < 0:
			stats["non_places"].append({"id": l["id"], "texte": l["texte"][:80]})
	for im in plan["images"]:
		if not lire_fichier:
			continue
		rect = pymupdf.Rect(*im["bbox"])
		try:
			octets = lire_fichier(im["fichier"])
			page.draw_rect(rect, color=None, fill=(1, 1, 1), overlay=True)
			page.insert_image(rect, stream=octets, keep_proportion=True, overlay=True)
		except Exception:
			frappe.log_error(title="Aquaworld IA : illustration %s" % im["id"], message=frappe.get_traceback())
	return stats


def reecrire_page(page, paragraphes: list[dict], traductions: dict, langue: dict, archive, css: str,
                  edition: dict | None = None, images: list[dict] | None = None, lire_fichier=None) -> dict:
	"""Efface puis repose les paragraphes traduits de cette page (édition du studio comprise). -> stats."""
	no = page.number if not paragraphes else paragraphes[0]["page"]
	plan = plan_page(no, paragraphes, traductions, edition, images)
	return executer_plan(page, plan, langue, archive, css, voisins=[q["bbox"] for q in paragraphes],
	                     lire_fichier=lire_fichier)


def _lire_fichier_site(url: str) -> bytes:
	from aquaworld_ia.ia import fichiers

	return fichiers.lire(url)


def reecrire_document(pdf_bytes: bytes, paragraphes: list[dict], traductions: dict, langue: dict,
                      edition: dict | None = None, images: list[dict] | None = None) -> tuple[bytes, dict]:
	"""-> (PDF traduit, stats globales {poses, reduits, non_places[{page,id,texte}], pivotes})."""
	import pymupdf

	doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
	archive, css = polices_archive(), css_base()
	total = {"poses": 0, "reduits": 0, "non_places": [], "pivotes": 0}
	par_page = {}
	for p in paragraphes:
		par_page.setdefault(p["page"], []).append(p)
	for no, page in enumerate(doc):
		plan = plan_page(no, par_page.get(no, []), traductions, edition, images)
		s = executer_plan(page, plan, langue, archive, css, voisins=[q["bbox"] for q in par_page.get(no, [])],
		                  lire_fichier=_lire_fichier_site)
		total["poses"] += s["poses"]
		total["reduits"] += s["reduits"]
		total["pivotes"] += s["pivotes"]
		total["non_places"].extend(dict(n, page=no + 1) for n in s["non_places"])
	try:
		doc.subset_fonts()
	except Exception:
		pass
	sortie = io.BytesIO()
	doc.save(sortie, garbage=3, deflate=True)
	return sortie.getvalue(), total


def dpi_pour(format_page, cote_max_px: int = 1400) -> int:
	"""Le dpi qui rend la page au plus `cote_max_px` de côté (72 pt = 1 pouce). Pur."""
	w, h = (format_page or [612, 792])[:2]
	return max(24, min(150, int(cote_max_px * 72 / max(w, h, 1))))


def rendre_page(pdf_bytes: bytes, no: int, paragraphes: list[dict], traductions: dict, langue: dict,
                edition: dict | None = None, images: list[dict] | None = None, dpi: int = 96,
                original: bool = False) -> tuple[bytes, dict, list]:
	"""L'image PNG d'UNE page, telle qu'elle sortira dans le PDF (ou l'original si `original`) — le
	fond du studio. -> (png, stats, [largeur, hauteur] en points)."""
	import pymupdf

	doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
	doc.select([no])
	page = doc[0]
	fmt = [round(page.rect.width, 2), round(page.rect.height, 2)]
	stats = {"poses": 0, "reduits": 0, "non_places": [], "pivotes": 0, "blocs": {}}
	if not original:
		sur_page = [p for p in paragraphes if p.get("page") == no]
		plan = plan_page(no, sur_page, traductions, edition, images)
		stats = executer_plan(page, plan, langue, polices_archive(), css_base(), voisins=[q["bbox"] for q in sur_page],
		                      lire_fichier=_lire_fichier_site)
	png = page.get_pixmap(dpi=dpi, alpha=False).tobytes("png")
	return png, stats, fmt


def clip_page(pdf_bytes: bytes, no: int, bbox, cote_max_px: int = 1536) -> bytes:
	"""Le PNG d'une région de la page d'ORIGINE (la référence envoyée à l'IA pour redessiner une
	illustration : images ET traits vectoriels compris)."""
	import pymupdf

	doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
	page = doc[no]
	rect = pymupdf.Rect(*bbox) & page.rect
	dpi = max(72, min(400, int(cote_max_px * 72 / max(rect.width, rect.height, 1))))
	return page.get_pixmap(dpi=dpi, clip=rect, alpha=False).tobytes("png")
