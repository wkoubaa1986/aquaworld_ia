"""Le « Studio manuel » (demande utilisateur 24/09/2026 : « un studio où je change page par page,
en gardant l'image du manuel d'origine, et je change le texte dans l'autre langue ») : la page
Desk plein écran qui montre chaque page telle qu'elle sortira dans le PDF traduit, avec ses
blocs de texte à corriger, déplacer, masquer ou ajouter, et ses illustrations à redessiner par
IA dans la langue.

Ici ne vivent que la LECTURE (tout ce que la page affiche), l'ENREGISTREMENT de l'édition
(`manuels/edition.py`) et les actions à la page (traduire une page, une illustration, produire le
PDF). Le moteur reste celui du job : extraction.py, traduction.py, rendu.py — la fiche et le
studio produisent exactement le même PDF.
"""

from __future__ import annotations

import base64
import io
import json

import frappe
from frappe import _
from frappe.utils import cint
from frappe.utils.file_manager import save_file

from aquaworld_ia.ia import etat, fichiers, images, journal
from aquaworld_ia.ia.client import qualite_image
from aquaworld_ia.manuels import edition as E
from aquaworld_ia.manuels import extraction, job, rendu, traduction

FONCTIONNALITE_ILLUSTRATION = "Manuel illustration"
DPI_VIGNETTE = 26
COTE_PAGE_PX = 1400


# ------------------------------------------------------------------ accès


def _doc(manuel: str, droit: str = "read"):
	doc = frappe.get_doc("Manuel Article", manuel)
	doc.check_permission(droit)
	return doc


def _ligne(doc, langue: str):
	for l in doc.traductions:
		if l.langue == langue:
			return l
	frappe.throw(_("La langue {0} n'est pas dans ce manuel : ajoutez-la d'abord.").format(langue))


def _pdf(doc) -> bytes:
	if not doc.pdf_source:
		frappe.throw(_("Attachez d'abord le PDF source à la fiche."))
	return fichiers.lire(doc.pdf_source)


def langue_infos(code: str) -> dict:
	d = frappe.db.get_value("Aquaworld IA Langue", code,
	                        ["code", "libelle", "libelle_natif", "rtl", "police", "police_fichier", "instructions"], as_dict=True)
	return d or {"code": code, "libelle": code, "rtl": 0}


def analyse_du_manuel(doc, pdf: bytes | None = None, forcer: bool = False) -> dict:
	"""L'analyse du PDF source (paragraphes, illustrations, formats, pages image), mise en cache
	sur la fiche : refaite quand le PDF change, quand la découpe a évolué (VERSION_ANALYSE) ou sur
	demande. Les traductions et l'édition de chaque langue sont alors reportées par texte
	(`remapper`) : une analyse refaite ne perd pas le travail fait."""
	cache = None
	if doc.get("analyse"):
		try:
			cache = json.loads(doc.analyse)
		except ValueError:
			cache = None
	if cache and not forcer and cache.get("source") == doc.pdf_source and cache.get("version") == extraction.VERSION_ANALYSE:
		return cache
	analyse = extraction.analyser_document(pdf if pdf is not None else _pdf(doc))
	analyse["source"] = doc.pdf_source
	if cache and cache.get("paragraphes"):
		for l in doc.traductions:
			if not (l.get("traductions") or l.get("edition")):
				continue
			trad, ed = remapper(cache, analyse, E.traductions_str(l.get("traductions")), E.lire(l.get("edition")))
			_ecrire_ligne(l, traductions=json.dumps(trad, ensure_ascii=False), edition=E.ecrire(ed))
	frappe.db.set_value("Manuel Article", doc.name, {
		"analyse": json.dumps(analyse, ensure_ascii=False), "pages": analyse["pages"], "blocs": len(analyse["paragraphes"]),
	}, update_modified=False)
	doc.analyse = json.dumps(analyse, ensure_ascii=False)
	return analyse


def _cle_paragraphe(p: dict) -> tuple:
	return (p.get("page"), " ".join((p.get("texte") or "").split()))


def remapper(ancienne: dict, nouvelle: dict, traductions: dict, edition: dict) -> tuple[dict, dict]:
	"""Reporte traductions et édition d'une ancienne analyse vers une nouvelle : un paragraphe
	est reconnu par (page, texte anglais). Ce qui n'a plus de correspondant (texte redécoupé,
	page retirée) est abandonné ; les cases libres, posées par page, sont gardées ; une
	illustration redessinée l'est si l'image existe encore sous le même identifiant. Pur."""
	anciens = {str(p["id"]): _cle_paragraphe(p) for p in ancienne.get("paragraphes", [])}
	nouveaux = {}
	for p in nouvelle.get("paragraphes", []):
		nouveaux.setdefault(_cle_paragraphe(p), str(p["id"]))
	corr = {k: nouveaux[c] for k, c in anciens.items() if c in nouveaux}
	trad = {corr[k]: v for k, v in (traductions or {}).items() if k in corr}
	ed = E.lire(edition)
	ed["textes"] = {corr[k]: v for k, v in ed["textes"].items() if k in corr}
	ed["blocs"] = {corr[k]: v for k, v in ed["blocs"].items() if k in corr}
	ids_images = {im["id"] for im in nouvelle.get("images", [])}
	ed["images"] = {k: v for k, v in ed["images"].items() if k in ids_images}
	ed["libres"] = [l for l in ed["libres"] if l.get("page", 0) < nouvelle.get("pages", 0)]
	return trad, ed


def _paragraphes_page(analyse: dict, no: int) -> list[dict]:
	return [p for p in analyse["paragraphes"] if p.get("page") == no]


# ------------------------------------------------------------------ lecture


@frappe.whitelist()
def liste(limite: int = 30) -> list:
	return frappe.get_list("Manuel Article", fields=["name", "titre", "article", "statut", "modified"],
	                       order_by="modified desc", limit_page_length=cint(limite) or 30)


def _resume_langue(l, analyse: dict) -> dict:
	infos = langue_infos(l.langue)
	trad = E.traductions_str(l.get("traductions"))
	ed = E.lire(l.get("edition"))
	return {
		"langue": l.langue, "libelle": infos.get("libelle") or l.langue, "rtl": cint(infos.get("rtl")),
		"statut": l.statut, "fichier": l.fichier, "blocs_reduits": l.blocs_reduits, "blocs_non_places": l.blocs_non_places,
		"cout_estime": l.cout_estime, "erreur": l.erreur, "pdf_reconstruit": l.get("pdf_reconstruit"),
		"nb_traduits": len(trad), "nb_corriges": len(ed["textes"]), "nb_libres": len(ed["libres"]),
		"nb_images": len(ed["images"]) + sum(1 for x in ed["libres"] if x.get("type") == "image" and x.get("fichier")),
	}


@frappe.whitelist()
def charger(manuel: str) -> dict:
	"""Tout ce que la page affiche à l'ouverture, en UN appel : la fiche, le résumé de chaque page,
	les langues et leur avancement. Les pages elles-mêmes se chargent une à une (`page`)."""
	doc = _doc(manuel)
	analyse = analyse_du_manuel(doc) if doc.pdf_source else None
	pages = []
	if analyse:
		par_page = {}
		for p in analyse["paragraphes"]:
			par_page.setdefault(p["page"], []).append(p)
		for no in range(analyse["pages"]):
			ps = par_page.get(no, [])
			pages.append({
				"no": no, "format": analyse["formats"][no], "ids": [p["id"] for p in ps if not rendu.est_pivote(p)],
				"pivotes": sum(1 for p in ps if rendu.est_pivote(p)),
				"images": [im for im in analyse["images"] if im["page"] == no], "image": no in analyse["pages_image"],
				"ocr": no in analyse.get("pages_ocr", []),
			})
	presentes = {l.langue for l in doc.traductions} | {(doc.langue_source or "en").strip().lower()}
	from aquaworld_ia.emballage.job import estimation_variantes

	return {
		"doc": {k: doc.get(k) for k in ("name", "titre", "article", "langue_source", "statut", "pdf_source", "pages", "blocs", "glossaire", "contexte", "pdf_combine")},
		"peut_ecrire": doc.has_permission("write"),
		"analyse": {"pages": analyse["pages"], "texte_extractible": analyse["texte_extractible"],
		            "pages_image": analyse["pages_image"], "pages_ocr": analyse.get("pages_ocr", []),
		            "ocr_disponible": extraction.ocr_disponible()} if analyse else None,
		"pages": pages,
		"langues": [_resume_langue(l, analyse) for l in doc.traductions],
		"langues_dispo": [l for l in frappe.get_all("Aquaworld IA Langue", filters={"actif": 1}, fields=["code", "libelle", "rtl"],
		                                             order_by="code") if l.code not in presentes],
		"etat": job.etat_manuel(manuel),
		"estimation_image": estimation_variantes(1),
	}


@frappe.whitelist()
def langue(manuel: str, langue: str) -> dict:
	"""Ce qui change quand on passe d'une langue à l'autre : les traductions IA et l'édition."""
	doc = _doc(manuel)
	l = _ligne(doc, langue)
	analyse = analyse_du_manuel(doc)
	return {"traductions": E.traductions_str(l.get("traductions")), "edition": E.lire(l.get("edition")),
	        "ligne": _resume_langue(l, analyse), "infos": langue_infos(langue)}


@frappe.whitelist()
def page(manuel: str, langue: str, no: int, original: int = 0) -> dict:
	"""UNE page, telle qu'elle sortira dans le PDF de cette langue (ou l'original) : l'image de
	fond du studio, ses blocs (texte anglais, traduction, état) et ses illustrations."""
	doc = _doc(manuel)
	l = _ligne(doc, langue)
	analyse = analyse_du_manuel(doc)
	no = cint(no)
	if not 0 <= no < analyse["pages"]:
		frappe.throw(_("Page {0} inexistante.").format(no + 1))
	trad = E.traductions_str(l.get("traductions"))
	ed = E.lire(l.get("edition"))
	infos = langue_infos(langue)
	fmt = analyse["formats"][no]
	png, stats, fmt = rendu.rendre_page(_pdf(doc), no, analyse["paragraphes"], trad, infos, edition=ed,
	                                    images=analyse["images"], dpi=rendu.dpi_pour(fmt, COTE_PAGE_PX), original=bool(cint(original)))
	blocs = []
	for p in _paragraphes_page(analyse, no):
		pivote = rendu.est_pivote(p)
		blocs.append({"id": p["id"], "bbox": list(p["bbox"]), "texte": p["texte"], "style": p["style"], "pivote": pivote,
		              "traduisible": extraction.est_traduisible(p["texte"]), "traduction": trad.get(str(p["id"])),
		              "statut": E.statut_bloc(p["id"], trad, ed, pivote)})
	return {
		"no": no, "format": fmt, "png": "data:image/png;base64," + base64.b64encode(png).decode(), "stats": stats,
		"blocs": blocs, "images": [im for im in analyse["images"] if im["page"] == no], "image_page": no in analyse["pages_image"],
		"ocr": no in analyse.get("pages_ocr", []), "original": bool(cint(original)),
	}


@frappe.whitelist()
def vignettes(manuel: str) -> list:
	"""Les vignettes des pages d'ORIGINE (colonne de gauche), petites : une par page."""
	import pymupdf

	doc = _doc(manuel)
	pdf = pymupdf.open(stream=_pdf(doc), filetype="pdf")
	return ["data:image/png;base64," + base64.b64encode(p.get_pixmap(dpi=DPI_VIGNETTE, alpha=False).tobytes("png")).decode()
	        for p in pdf]


# ------------------------------------------------------------------ écriture


def _ecrire_ligne(l, **valeurs) -> None:
	frappe.db.set_value("Manuel Article Traduction", l.name, valeurs, update_modified=False)
	for k, v in valeurs.items():
		l.set(k, v)


@frappe.whitelist()
def enregistrer(manuel: str, langue: str, edition) -> dict:
	"""L'édition complète de la langue (le navigateur envoie tout, à chaque changement) : normalisée
	puis enregistrée. Rend l'édition telle qu'enregistrée."""
	doc = _doc(manuel, "write")
	l = _ligne(doc, langue)
	analyse = analyse_du_manuel(doc)
	edition = frappe.parse_json(edition) if isinstance(edition, str) else edition
	page_par_bloc = {str(p["id"]): p["page"] for p in analyse["paragraphes"]}
	ed = E.normaliser(edition, analyse["formats"], page_par_bloc)
	_ecrire_ligne(l, edition=E.ecrire(ed))
	return {"edition": ed}


@frappe.whitelist()
def nouveau(article: str, pdf: str, titre: str | None = None, langues=None) -> dict:
	"""Un manuel créé DEPUIS le studio (demande utilisateur 25/09/2026 : « comment ajouter un
	nouveau document à traduire ? ») : l'article, le PDF téléversé dans le dialogue (rattaché à la
	fiche), les langues cochées. Le studio s'ouvre dessus."""
	frappe.has_permission("Manuel Article", "create", throw=True)
	if not pdf:
		frappe.throw(_("Téléversez le PDF du manuel (texte, en anglais)."))
	langues = frappe.parse_json(langues) if isinstance(langues, str) else (langues or [])
	doc = frappe.get_doc({
		"doctype": "Manuel Article", "article": article, "pdf_source": pdf, "langue_source": "en",
		"titre": (titre or "").strip() or frappe.db.get_value("Item", article, "item_name") or article,
		"traductions": [{"langue": c, "statut": "En attente"} for c in langues if frappe.db.exists("Aquaworld IA Langue", c)],
	}).insert()
	for f in frappe.get_all("File", filters={"file_url": pdf, "attached_to_name": ("is", "not set")}, pluck="name"):
		frappe.db.set_value("File", f, {"attached_to_doctype": "Manuel Article", "attached_to_name": doc.name,
		                                "attached_to_field": "pdf_source"})
	analyse = analyse_du_manuel(doc)
	return {"name": doc.name, "pages": analyse["pages"], "texte_extractible": analyse["texte_extractible"]}


@frappe.whitelist()
def ajouter_langue(manuel: str, code: str) -> dict:
	doc = _doc(manuel, "write")
	if not frappe.db.exists("Aquaworld IA Langue", code):
		frappe.throw(_("Langue inconnue : {0}").format(code))
	if any(l.langue == code for l in doc.traductions):
		frappe.throw(_("La langue {0} est déjà là.").format(code))
	doc.append("traductions", {"langue": code, "statut": "En attente"})
	doc.save()
	return charger(manuel)


@frappe.whitelist()
def ajouter_langues(manuel: str, codes) -> dict:
	"""Plusieurs langues d'un coup (demande utilisateur 25/09/2026 : « travailler sur 5 traductions en
	même temps »)."""
	doc = _doc(manuel, "write")
	codes = frappe.parse_json(codes) if isinstance(codes, str) else (codes or [])
	presentes = {l.langue for l in doc.traductions}
	for code in codes:
		if code not in presentes and frappe.db.exists("Aquaworld IA Langue", code):
			doc.append("traductions", {"langue": code, "statut": "En attente"})
			presentes.add(code)
	doc.save()
	return charger(manuel)


@frappe.whitelist()
def analyser(manuel: str) -> dict:
	"""Refaire l'analyse du PDF (après un remplacement du fichier source, par exemple)."""
	doc = _doc(manuel, "write")
	analyse_du_manuel(doc, forcer=True)
	return charger(manuel)


# ------------------------------------------------------------------ IA à la page


@frappe.whitelist()
def traduire_page(manuel: str, langue: str, no: int, ids=None, forcer: int = 0) -> dict:
	"""Traduire par IA les blocs d'UNE page : ceux sans traduction (ou tous, `forcer`), ou les
	`ids` donnés (un bloc à retraduire). Les corrections de l'utilisateur ne sont pas touchées :
	elles priment toujours, « Rétablir » les retire."""
	doc = _doc(manuel, "write")
	l = _ligne(doc, langue)
	journal.verifier_plafond()
	analyse = analyse_du_manuel(doc)
	no = cint(no)
	ids = frappe.parse_json(ids) if isinstance(ids, str) else ids
	voulus = {str(i) for i in ids} if ids else None
	trad = E.traductions_str(l.get("traductions"))
	cibles = [p for p in _paragraphes_page(analyse, no)
	          if not rendu.est_pivote(p) and extraction.est_traduisible(p["texte"])
	          and (voulus is None or str(p["id"]) in voulus) and (voulus is not None or cint(forcer) or str(p["id"]) not in trad)]
	if not cibles:
		return {"traductions": trad, "n": 0}
	from aquaworld_ia.ia.client import reglages

	r = reglages()
	glossaire = "\n".join(x for x in (getattr(r, "glossaire_global", "") or "", doc.glossaire or "") if x)
	nouvelles, laisses = traduction.traduire_tout(cibles, langue_infos(langue), glossaire=glossaire,
	                                              instructions=getattr(r, "instructions_globales", "") or "",
	                                              contexte=doc.contexte or "", doc=doc,
	                                              taille_lot=cint(getattr(r, "lot_paragraphes", 25)) or 25)
	for k, v in nouvelles.items():
		trad[str(k)] = v
	_ecrire_ligne(l, traductions=json.dumps(trad, ensure_ascii=False))
	if l.statut == "En attente":
		_ecrire_ligne(l, statut="Terminé" if not laisses else "Échec")
	return {"traductions": trad, "n": len(nouvelles), "laisses": [str(i) for i in laisses]}


# --- illustrations redessinées par l'IA (mots traduits dans l'image)


def taille_illustration(bbox) -> str:
	"""Le format d'image demandé à l'IA pour une région : carré, paysage ou portrait selon la
	région, pour perdre le moins possible au recadrage. Pur."""
	w, h = max(1.0, bbox[2] - bbox[0]), max(1.0, bbox[3] - bbox[1])
	if w > h * 1.25:
		return "1536x1024"
	if h > w * 1.25:
		return "1024x1536"
	return "1024x1024"


def cadre_relatif(largeur: float, hauteur: float, taille: str) -> tuple:
	"""Où la région (l × h) se place, centrée, dans un canevas blanc au format `taille` :
	(x0, y0, x1, y1) en fractions du canevas. La référence est envoyée ainsi et le résultat
	recadré sur ce même cadre, pour remplir exactement la boîte de la page. Pur."""
	tw, th = (int(v) for v in taille.split("x"))
	ratio_canevas, ratio_region = tw / th, largeur / max(hauteur, 1e-6)
	if ratio_region >= ratio_canevas:
		fw, fh = 1.0, ratio_canevas / ratio_region
	else:
		fw, fh = ratio_region / ratio_canevas, 1.0
	return (round((1 - fw) / 2, 4), round((1 - fh) / 2, 4), round((1 + fw) / 2, 4), round((1 + fh) / 2, 4))


def poser_sur_canevas(png: bytes, taille: str) -> tuple[bytes, tuple]:
	"""La région posée, centrée, sur un canevas blanc au format demandé. -> (png, cadre relatif)."""
	from PIL import Image

	tw, th = (int(v) for v in taille.split("x"))
	src = Image.open(io.BytesIO(png)).convert("RGB")
	cadre = cadre_relatif(src.width, src.height, taille)
	boite = (int(cadre[0] * tw), int(cadre[1] * th), int(cadre[2] * tw), int(cadre[3] * th))
	canevas = Image.new("RGB", (tw, th), (255, 255, 255))
	canevas.paste(src.resize((max(1, boite[2] - boite[0]), max(1, boite[3] - boite[1]))), (boite[0], boite[1]))
	sortie = io.BytesIO()
	canevas.save(sortie, format="PNG")
	return sortie.getvalue(), cadre


def recadrer(png: bytes, cadre: tuple) -> bytes:
	from PIL import Image

	im = Image.open(io.BytesIO(png)).convert("RGB")
	boite = (int(cadre[0] * im.width), int(cadre[1] * im.height), int(cadre[2] * im.width), int(cadre[3] * im.height))
	sortie = io.BytesIO()
	im.crop(boite).save(sortie, format="PNG")
	return sortie.getvalue()


def prompt_illustration(langue: dict, instruction: str = "") -> str:
	"""Le prompt de redessin d'une illustration : tout identique, seuls les mots changent de
	langue. Pur."""
	nom = langue.get("libelle") or langue.get("code", "")
	p = ("Reproduce the technical illustration in the reference image EXACTLY: same drawing, line art, layout, "
	     "colors, proportions, arrows, callouts and part numbers, on the same white background, nothing added, "
	     "removed or restyled. Change ONLY the language of the written words: translate every English word, "
	     "label and caption into %s (language code %s), placed where the English was, in a similar font and size. "
	     "Keep all numbers, units, part codes and symbols unchanged. No extra text, no watermark, no frame."
	     % (nom, langue.get("code", "")))
	if langue.get("rtl"):
		p += " The language is written right to left; render the words correctly shaped and readable."
	if instruction and instruction.strip():
		p += " Additional instruction: %s." % instruction.strip().rstrip(".")
	return p


@frappe.whitelist()
def traduire_illustration(manuel: str, langue: str, no: int, ident: str, bbox, instruction: str = "") -> dict:
	"""Redessiner par IA la région `bbox` de la page d'origine avec ses mots traduits, et la poser
	à la place dans l'édition (`images[ident]` pour une illustration détectée, `libres[…].fichier`
	pour une zone dessinée à la main). Une image facturée, journalisée « Manuel illustration »."""
	doc = _doc(manuel, "write")
	l = _ligne(doc, langue)
	journal.verifier_plafond()
	analyse = analyse_du_manuel(doc)
	no = cint(no)
	bbox = frappe.parse_json(bbox) if isinstance(bbox, str) else bbox
	bbox = E.borner_bbox(bbox, analyse["formats"][no])
	if not bbox:
		frappe.throw(_("Région illisible."))
	infos = langue_infos(langue)
	taille = taille_illustration(bbox)
	reference, cadre = poser_sur_canevas(rendu.clip_page(_pdf(doc), no, bbox), taille)
	pngs = images.editer(prompt_illustration(infos, instruction), [("illustration", reference)], taille=taille,
	                     qualite=qualite_image(), n=1, fonctionnalite=FONCTIONNALITE_ILLUSTRATION, doc=doc, fidelite="high")
	resultat = recadrer(pngs[0], cadre)
	fichier = save_file("%s-p%d-%s-%s.png" % (doc.name, no + 1, frappe.scrub(ident)[:20], langue), resultat,
	                    "Manuel Article", doc.name, is_private=1).file_url
	ed = E.lire(l.get("edition"))
	pose = False
	for x in ed["libres"]:
		if x.get("id") == ident and x.get("type") == "image":
			x["fichier"], pose = fichier, True
	if not pose:
		ed["images"][ident] = {"fichier": fichier}
	_ecrire_ligne(l, edition=E.ecrire(ed))
	return {"edition": ed, "fichier": fichier}


# ------------------------------------------------------------------ PDF


@frappe.whitelist()
def composer(manuel: str, langue: str) -> dict:
	"""Le PDF de la langue, avec l'édition du studio, sans nouvel appel IA (les traductions déjà
	faites servent ; les blocs sans traduction restent en anglais)."""
	doc = _doc(manuel, "write")
	l = _ligne(doc, langue)
	analyse = analyse_du_manuel(doc)
	trad = E.traductions_str(l.get("traductions"))
	ed = E.lire(l.get("edition"))
	sortie, stats = rendu.reecrire_document(_pdf(doc), analyse["paragraphes"], trad, langue_infos(langue),
	                                        edition=ed, images=analyse["images"])
	nom_fichier = "%s-%s.pdf" % (frappe.scrub(doc.titre or doc.article)[:60], langue)
	fichier = save_file(nom_fichier, sortie, "Manuel Article", doc.name, is_private=1)
	_ecrire_ligne(l, statut="Terminé", fichier=fichier.file_url, blocs_reduits=stats["reduits"],
	              blocs_non_places=len(stats["non_places"]), erreur=None)
	job._journal(doc, ["%s (studio) : %d blocs posés, %d réduits, %d non placés, %d pivotés ignorés" % (
		langue, stats["poses"], stats["reduits"], len(stats["non_places"]), stats["pivotes"])])
	frappe.db.commit()
	return {"ligne": _resume_langue(l, analyse), "stats": stats}


def combiner_pdfs(parties: list[tuple[str, bytes]]) -> bytes:
	"""Un seul PDF qui enchaîne `parties` [(titre, pdf)], un signet de premier niveau par partie
	(les signets de chaque partie passent en dessous). Pur au sens PyMuPDF : sans site."""
	import pymupdf

	sortie, toc = pymupdf.open(), []
	for titre, octets in parties:
		src = pymupdf.open(stream=octets, filetype="pdf")
		debut = len(sortie)
		sortie.insert_pdf(src)
		toc.append([1, titre, debut + 1])
		for niveau, t, page, *reste in src.get_toc(simple=True):
			toc.append([min(niveau + 1, 8), t, page + debut])
	sortie.set_toc(toc)
	tampon = io.BytesIO()
	sortie.save(tampon, garbage=3, deflate=True)
	return tampon.getvalue()


def parties_combine(doc, langues_infos: dict, avec_source: bool = True) -> list[tuple[str, str]]:
	"""[(titre, url)] dans l'ordre : le PDF source (anglais) d'abord si demandé, puis les langues
	terminées dans l'ordre de la grille. Pur."""
	parties = []
	if avec_source and doc.get("pdf_source"):
		src = (doc.get("langue_source") or "en").strip().lower()
		parties.append((langues_infos.get(src, {}).get("libelle") or "English", doc.get("pdf_source")))
	for l in doc.get("traductions") or []:
		# le manuel reconstruit prime quand il existe (c'est lui qu'on a voulu) ; sinon le PDF en place
		fichier = l.get("pdf_reconstruit") or (l.get("fichier") if l.get("statut") == "Terminé" else None)
		if fichier:
			parties.append((langues_infos.get(l.get("langue"), {}).get("libelle") or l.get("langue"), fichier))
	return parties


@frappe.whitelist()
def combiner(manuel: str, avec_source: int = 1) -> dict:
	"""Le manuel « toutes langues » (demande utilisateur 25/09/2026) : le PDF source puis chaque
	langue traduite, à la suite, un signet par langue. Aucun appel IA. Attaché à la fiche
	(`pdf_combine`) ; refait à chaque appel (les PDF de langue changent avec le studio)."""
	doc = _doc(manuel, "write")
	infos = {l.name: l for l in frappe.get_all("Aquaworld IA Langue", fields=["name", "libelle"])}
	parties = parties_combine(doc, infos, bool(cint(avec_source)))
	if len(parties) < (2 if cint(avec_source) else 1):
		frappe.throw(_("Aucune langue terminée : générez d'abord au moins un PDF traduit (en place ou reconstruit)."))
	octets = combiner_pdfs([(titre, fichiers.lire(url)) for titre, url in parties])
	nom = "%s-toutes-langues.pdf" % frappe.scrub(doc.titre or doc.article)[:60]
	fichier = save_file(nom, octets, "Manuel Article", doc.name, is_private=1)
	frappe.db.set_value("Manuel Article", doc.name, "pdf_combine", fichier.file_url, update_modified=False)
	job._journal(doc, ["PDF toutes langues : %s" % " + ".join(t for t, _u in parties)])
	frappe.db.commit()
	return {"fichier": fichier.file_url, "parties": [t for t, _u in parties]}


def etat_studio(manuel: str) -> dict:
	return dict(etat.lire_etat(job.GENRE, manuel), bloque=etat.bloque(etat.lire_etat(job.GENRE, manuel)))
