"""Extraction des paragraphes traduisibles d'un PDF TEXTE (PyMuPDF).

Un paragraphe = un groupe de lignes d'un bloc MuPDF, avec sa boîte, son texte recollé et son
style dominant. Les images, dessins et fonds ne sont pas touchés : seule la couche texte est lue,
et c'est elle seule qui sera remplacée (voir rendu.py). Tout ce qui ne dépend pas de PyMuPDF est
une fonction pure, testée sans PDF.
"""

from __future__ import annotations

import re

import frappe
from frappe import _

#: Bumper quand la découpe en paragraphes change : le studio refait alors l'analyse mise en cache
#: et reporte les traductions par texte (studio.remapper).
VERSION_ANALYSE = 10
# Sous ce total de caractères, le PDF est un scan ou du texte en contours : rien à traduire.
MIN_CARACTERES_DOCUMENT = 200
# Écart vertical (en hauteurs de ligne) au-delà duquel deux lignes d'un même bloc font deux
# paragraphes (puces, cellules de tableau collées dans un même bloc).
SAUT_PARAGRAPHE = 0.6


# Sous ce nombre de caractères, une page qui porte une image est une « page image » (scan, schéma
# plein) : rien à traduire automatiquement, l'utilisateur y pose ses cases de texte (studio).
MIN_CARACTERES_PAGE = 40
# Une image plus petite que ça (pictos, puces, filets) n'est pas une illustration à traduire.
COTE_MIN_ILLUSTRATION = 40.0


def extraire_paragraphes(pdf_bytes: bytes) -> tuple[list[dict], dict]:
	"""-> (paragraphes, {pages, blocs}). Lève une erreur claire si le PDF n'a pas de texte."""
	analyse = analyser_document(pdf_bytes)
	if not analyse["texte_extractible"]:
		frappe.throw(_("Ce PDF ne contient pas de texte extractible (scan ou texte en contours) : "
		               "traduction impossible."))
	return analyse["paragraphes"], {"pages": analyse["pages"], "blocs": len(analyse["paragraphes"])}


#: OCR (Tesseract via PyMuPDF) pour les pages SANS couche texte : PDF CorelDRAW/Illustrator où chaque
#: lettre est un contour vectoriel, ou scan. Demande utilisateur 25/09/2026 (manuel osmoseur, 12 pages,
#: 0 police). Le binaire `tesseract` + `tesseract-ocr-eng` doivent être dans l'image (apt) ; sans lui,
#: la page reste « image » (cases de texte à la main).
DPI_OCR = 250
_OCR = {}


def ocr_disponible() -> bool:
	if "ok" not in _OCR:
		try:
			import pymupdf

			_OCR["ok"] = bool(pymupdf.get_tessdata())
		except Exception:
			_OCR["ok"] = False
	return _OCR["ok"]


def lignes_ocr(page) -> list[dict]:
	"""Les lignes reconnues par OCR sur la page rendue (texte ET contours vectoriels compris) :
	[{bbox, spans}] au format MuPDF. Vide si Tesseract manque."""
	if not ocr_disponible():
		return []
	tp = page.get_textpage_ocr(flags=0, language="eng", dpi=DPI_OCR, full=True)
	lignes = []
	for bloc in page.get_text("dict", textpage=tp)["blocks"]:
		if bloc.get("type") != 0:
			continue
		for l in bloc.get("lines", []):
			if "".join(sp.get("text", "") for sp in l.get("spans", [])).strip():
				lignes.append({"bbox": tuple(l["bbox"]), "spans": l["spans"], "dir": tuple(l.get("dir", (1, 0)))})
	return lignes


# Détection des figures (25/09/2026 : les cadres de figures donnés par l'IA vision étaient larges ou
# décalés ; PyMuPDF connaît les images et les groupes de dessins au point près).
PART_TEXTE_MAX = 0.6        # au-delà, un groupe de dessins est du texte en contours, pas une figure
AIRE_MAX_FIGURE = 0.7       # part de la page : au-delà, c'est un fond ou un cadre, pas une figure
COTE_MIN_FIGURE = 25.0


def part_couverte(rect, boites) -> float:
	"""Part de l'aire de `rect` couverte par `boites` (approchée : somme des intersections). Pur
	au sens PyMuPDF."""
	aire = rect.get_area() or 1.0
	c = 0.0
	for b in boites:
		i = rect & b
		if not i.is_empty:
			c += i.get_area()
	return min(1.0, c / aire)


def detecter_figures(page, boites_texte: list) -> list:
	"""Les régions d'images ou de dessins d'une page qui ne sont pas du texte : [bbox]. Les fonds
	et cadres pleine page sont écartés, les dessins sont regroupés sans eux, et un groupe couvert
	de texte (lettres en contours) ne compte pas."""
	import pymupdf

	aire_page = page.rect.get_area() or 1.0
	textes = [pymupdf.Rect(*b) for b in boites_texte]
	regions = []
	for info in page.get_image_info():
		r = pymupdf.Rect(info["bbox"]) & page.rect
		if r.width >= COTE_MIN_FIGURE and r.height >= COTE_MIN_FIGURE and r.get_area() < AIRE_MAX_FIGURE * aire_page:
			regions.append(r)
	try:
		dessins = [d for d in page.get_drawings() if d.get("rect") and d["rect"].get_area() < 0.5 * aire_page]
		groupes = page.cluster_drawings(drawings=dessins, x_tolerance=6, y_tolerance=6) if dessins else []
	except Exception:
		groupes = []
	for r in groupes:
		r = r & page.rect
		if (r.width >= COTE_MIN_FIGURE and r.height >= COTE_MIN_FIGURE and r.get_area() < AIRE_MAX_FIGURE * aire_page
		        and part_couverte(r, textes) < PART_TEXTE_MAX):
			regions.append(r)
	return [[round(v, 1) for v in (r.x0, r.y0, r.x1, r.y1)] for r in regions]


def analyser_document(pdf_bytes: bytes) -> dict:
	"""Tout ce que le studio et le job lisent dans le PDF source, en une passe : les paragraphes,
	les illustrations (une entrée par image posée, avec sa boîte sur la page), le format de chaque
	page et les pages « image » (demande utilisateur 24/09/2026 : un studio page par page qui garde
	l'image d'origine). Ne lève jamais pour un scan : `texte_extractible` le dit."""
	import pymupdf

	doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
	paragraphes, images, formats, pages_image, pages_ocr, total, figures = [], [], [], [], [], 0, []
	for no, page in enumerate(doc):
		rect = (page.rect.x0, page.rect.y0, page.rect.x1, page.rect.y1)
		formats.append([round(rect[2] - rect[0], 2), round(rect[3] - rect[1], 2)])
		chars = 0
		nouveaux = []
		for bloc in page.get_text("dict", sort=True)["blocks"]:
			if bloc.get("type") != 0:
				continue
			nouveaux += paragraphes_depuis_bloc(bloc, no, rect)
		chars = sum(len(p["texte"]) for p in nouveaux)
		if chars < MIN_CARACTERES_PAGE and (page.get_drawings() or page.get_images()):
			# pas de couche texte : lettres en contours ou scan → OCR, paragraphes marqués `ocr`
			reconnus = paragraphes_depuis_lignes(lignes_ocr(page), no, rect)
			if reconnus:
				for p in reconnus:
					p["ocr"] = True
				nouveaux, chars = reconnus, sum(len(p["texte"]) for p in reconnus)
				pages_ocr.append(no)
		for p in nouveaux:
			p["id"] = len(paragraphes)
			paragraphes.append(p)
		total += chars
		try:
			figures.append(detecter_figures(page, [p["bbox"] for p in nouveaux]))
		except Exception:
			figures.append([])
		boites = []
		try:
			infos = page.get_image_info(xrefs=True)
		except Exception:
			infos = []
		for k, info in enumerate(infos):
			bbox = tuple(round(v, 2) for v in info.get("bbox", (0, 0, 0, 0)))
			if est_illustration(bbox):
				images.append({"id": "p%d-i%d" % (no, k), "page": no, "bbox": bbox})
				boites.append(bbox)
		if est_page_image(chars, len(boites)) and no not in pages_ocr:
			pages_image.append(no)
	return {
		"version": VERSION_ANALYSE, "pages": len(doc), "formats": formats, "paragraphes": paragraphes, "images": images, "figures": figures,
		"pages_image": pages_image, "pages_ocr": pages_ocr, "texte_extractible": total >= MIN_CARACTERES_DOCUMENT,
	}


# ------------------------------------------------------------------ fonctions pures


def paragraphes_depuis_bloc(bloc: dict, page_no: int, page_rect: tuple) -> list[dict]:
	"""Un bloc MuPDF (dict avec `lines` → `spans`) -> 0..n paragraphes."""
	lignes = [l for l in bloc.get("lines", []) if l.get("spans")]
	if not lignes:
		return []
	sorties = []
	for groupe in grouper_lignes(lignes):
		texte = fusionner_lignes(["".join(s.get("text", "") for s in l["spans"]) for l in groupe])
		if not texte.strip():
			continue
		spans = [s for l in groupe for s in l["spans"]]
		bbox = _union([l["bbox"] for l in groupe])
		sorties.append({
			"page": page_no,
			"bbox": bbox,
			"texte": texte,
			"style": style_dominant(spans, bbox, page_rect, [l["bbox"] for l in groupe]),
			"dir": tuple(groupe[0].get("dir", (1, 0))),
			"lignes": len(groupe),
		})
	return sorties


# Un début d'entrée de liste : « 1. », « 12) », « a. », « (3) », « • », « - », « iv. »…
# Le marqueur peut être seul sur sa ligne (Word pose « 1. » et le texte comme deux lignes à la même
# hauteur) : fin de chaîne acceptée après lui.
# Un numéro peut être collé au mot (OCR : « 2.Operation ») : lettre acceptée juste après lui.
_MARQUEUR_LISTE = re.compile(r"^(?:\(?\d{1,3}[.)](?=\s|$|[A-Za-z])|\(?[a-zA-Z][.)](?=\s|$)|[•\-–—▪●○*·◦■□➢➤►✓](?=\s|$)|[ivxIVX]{1,5}[.)](?=\s|$))")


def commence_une_entree(texte: str) -> bool:
	"""Vrai si la ligne ouvre une entrée de liste (numéro, lettre, puce) : elle fait un paragraphe
	à elle seule, sinon les étapes « 1. … 2. … » d'un même bloc fondent en un seul texte et la
	traduction perd les retours à la ligne (vu le 24/09/2026 sur le manuel David 4000). Pur."""
	return bool(_MARQUEUR_LISTE.match((texte or "").strip()))


def _texte_ligne(ligne: dict) -> str:
	return "".join(s.get("text", "") for s in ligne.get("spans", []))


DECALAGE_COLONNE = 18.0   # en points : deux lignes plus décalées à gauche ne sont pas du même paragraphe
_PUCES_OCR = {"@", "•", "◆", "◇", "■", "□", "●", "○", "▪", "*", "-", "–", "o", "e", "¢", "¢"}


def rattacher_puces(lignes: list[dict]) -> list[dict]:
	"""Tesseract rend le losange d'une puce comme une ligne à part (« @ », « e »…) à la hauteur de la
	ligne qu'il précède : on le fond dans cette ligne, en tête, sous forme de « • ». Pur."""
	sorties = []
	restantes = list(lignes)
	while restantes:
		l = restantes.pop(0)
		texte = _texte_ligne(l).strip()
		if texte in _PUCES_OCR:
			h = max(1.0, l["bbox"][3] - l["bbox"][1])
			cible = next((m for m in restantes if abs(m["bbox"][1] - l["bbox"][1]) < 0.6 * h and m["bbox"][0] > l["bbox"][0]
			              and m["bbox"][0] - l["bbox"][2] < 3 * h), None)
			if cible:
				premier = dict(cible["spans"][0])
				premier["text"] = "• " + premier.get("text", "").lstrip()
				cible["spans"] = [premier] + list(cible["spans"][1:])
				cible["bbox"] = (min(cible["bbox"][0], l["bbox"][0]), min(cible["bbox"][1], l["bbox"][1]),
				                 max(cible["bbox"][2], l["bbox"][2]), max(cible["bbox"][3], l["bbox"][3]))
				continue
		sorties.append(l)
	return sorties


def paragraphes_depuis_lignes(lignes: list[dict], page_no: int, page_rect: tuple) -> list[dict]:
	"""Des LIGNES libres (OCR) -> paragraphes : Tesseract range parfois les deux colonnes d'une page
	dans un même bloc, on regroupe donc nous-mêmes — lecture colonne par colonne (gauche à droite),
	puis de haut en bas ; une ligne rejoint la précédente si elle la suit de près verticalement,
	part du même bord gauche (± DECALAGE_COLONNE) ou en retrait de première ligne, et n'ouvre pas
	une entrée de liste. Pur."""
	lignes = rattacher_puces([l for l in lignes if l.get("spans")])
	if not lignes:
		return []
	# colonnes : on trie par le bord gauche arrondi à la demi-page, puis par y
	demi = (page_rect[0] + page_rect[2]) / 2
	colonne = lambda l: 0 if l["bbox"][0] < demi else 1
	lignes.sort(key=lambda l: (colonne(l), l["bbox"][1], l["bbox"][0]))
	# le bord droit du texte de chaque colonne : une ligne qui y arrive est « pleine », la suivante
	# la continue même en retrait (alinéa de première ligne, paragraphe justifié)
	droite = {}
	for l in lignes:
		droite[colonne(l)] = max(droite.get(colonne(l), 0), l["bbox"][2])
	groupes, courant = [], [lignes[0]]
	for prec, ligne in zip(lignes, lignes[1:]):
		h = max(1.0, prec["bbox"][3] - prec["bbox"][1])
		ecart = ligne["bbox"][1] - prec["bbox"][3]
		meme_colonne = colonne(ligne) == colonne(prec)
		aligne = (abs(ligne["bbox"][0] - courant[0]["bbox"][0]) <= DECALAGE_COLONNE
		          or abs(ligne["bbox"][0] - prec["bbox"][0]) <= DECALAGE_COLONNE
		          or prec["bbox"][2] >= droite[colonne(prec)] - 2.5 * DECALAGE_COLONNE)
		if meme_colonne and -0.3 * h <= ecart <= SAUT_PARAGRAPHE * h and aligne and not commence_une_entree(_texte_ligne(ligne)):
			courant.append(ligne)
		else:
			groupes.append(courant)
			courant = [ligne]
	groupes.append(courant)
	sorties = []
	for groupe in groupes:
		texte = nettoyer_ocr(fusionner_lignes(["".join(sp.get("text", "") for sp in l["spans"]) for l in groupe]))
		if not texte.strip():
			continue
		spans = [sp for l in groupe for sp in l["spans"]]
		bbox = _union([l["bbox"] for l in groupe])
		style = style_dominant(spans, bbox, page_rect, [l["bbox"] for l in groupe])
		# l'OCR estime une taille par ligne (majuscules, descendantes…) : la médiane des lignes, pas
		# la ligne la plus longue, sinon deux morceaux d'un même paragraphe sortent à deux tailles
		tailles = sorted(float(sp.get("size") or 0) for sp in spans if sp.get("size"))
		if tailles:
			# et jamais plus haute que la ligne elle-même (une ligne de déchets lue « géante »)
			hauteur_ligne = (bbox[3] - bbox[1]) / max(1, len(groupe))
			style["taille"] = round(min(tailles[len(tailles) // 2], hauteur_ligne), 2)
		sorties.append({"page": page_no, "bbox": bbox, "texte": texte, "style": style,
		                "dir": tuple(groupe[0].get("dir", (1, 0))), "lignes": len(groupe)})
	return sorties


def grouper_lignes(lignes: list[dict]) -> list[list[dict]]:
	"""Coupe un bloc en paragraphes sur les grands écarts verticaux et aux entrées de liste."""
	groupes, courant = [], [lignes[0]]
	for prec, ligne in zip(lignes, lignes[1:]):
		h = max(1.0, prec["bbox"][3] - prec["bbox"][1])
		ecart = ligne["bbox"][1] - prec["bbox"][3]
		if ecart > SAUT_PARAGRAPHE * h or commence_une_entree(_texte_ligne(ligne)):
			groupes.append(courant)
			courant = [ligne]
		else:
			courant.append(ligne)
	groupes.append(courant)
	return groupes


def _union(boites: list) -> tuple:
	return (min(b[0] for b in boites), min(b[1] for b in boites),
	        max(b[2] for b in boites), max(b[3] for b in boites))


def fusionner_lignes(lignes: list[str]) -> str:
	"""Joint les lignes par un espace et recolle les césures (« instal-» + « lation »)."""
	texte = ""
	for brut in lignes:
		ligne = " ".join(brut.split())
		if not ligne:
			continue
		if texte.endswith("-") and ligne[:1].islower():
			texte = texte[:-1] + ligne
		elif texte:
			texte += " " + ligne
		else:
			texte = ligne
	return texte


def est_illustration(bbox, cote_min: float = COTE_MIN_ILLUSTRATION) -> bool:
	"""Une image assez grande pour porter des mots à traduire. Pur."""
	if not bbox or len(bbox) != 4:
		return False
	return (bbox[2] - bbox[0]) >= cote_min and (bbox[3] - bbox[1]) >= cote_min


def est_page_image(caracteres: int, nb_images: int, minimum: int = MIN_CARACTERES_PAGE) -> bool:
	"""Une page sans texte (ou presque) qui porte au moins une image : un scan, un schéma plein
	page. Le studio y propose des cases de texte plutôt qu'une traduction. Pur."""
	return caracteres < minimum and nb_images > 0


def couleur_hex(valeur) -> str:
	try:
		v = int(valeur or 0)
	except (TypeError, ValueError):
		v = 0
	return "#%06x" % (v & 0xFFFFFF)


def style_dominant(spans: list[dict], bbox=None, page_rect=None, boites_lignes=None) -> dict:
	"""Le style du span le plus long : taille, gras, italique, couleur, police, alignement."""
	if not spans:
		return {"taille": 10.0, "gras": False, "italique": False, "couleur": "#000000", "police": "", "align": "left"}
	principal = max(spans, key=lambda s: len(s.get("text", "")))
	police = str(principal.get("font", "") or "")
	flags = int(principal.get("flags", 0) or 0)
	return {
		"taille": round(float(principal.get("size", 10) or 10), 2),
		"gras": bool(flags & 16) or "bold" in police.lower() or "black" in police.lower(),
		"italique": bool(flags & 2) or "italic" in police.lower() or "oblique" in police.lower(),
		"couleur": couleur_hex(principal.get("color")),
		"police": police,
		"align": alignement(bbox, boites_lignes, page_rect),
	}


def alignement(bbox, boites_lignes, page_rect, tolerance: float = 2.0) -> str:
	"""« center » si chaque ligne est centrée dans le bloc et qu'au moins une est plus courte ;
	« right » si les lignes finissent au même bord droit avec des débuts différents ; sinon « left »."""
	if not bbox or not boites_lignes or len(boites_lignes) < 2:
		return "left"
	cx = (bbox[0] + bbox[2]) / 2
	centres = all(abs((b[0] + b[2]) / 2 - cx) <= tolerance for b in boites_lignes)
	largeurs = {round(b[2] - b[0]) for b in boites_lignes}
	if centres and len(largeurs) > 1:
		return "center"
	droites = all(abs(b[2] - bbox[2]) <= tolerance for b in boites_lignes)
	gauches = all(abs(b[0] - bbox[0]) <= tolerance for b in boites_lignes)
	if droites and not gauches:
		return "right"
	return "left"


_REFERENCE = re.compile(r"[A-Z0-9][A-Z0-9\-_/.]*")


# Points de conduite d'une table des matières lus par l'OCR : « ********** », « """"" », « “eee e eee EE » …
_CONDUITE = re.compile(r"[*\"“”'’`.·_~=\-]{3,}")
_JETON_REPETE = re.compile(r"(?<!\w)([A-Za-z])\1+(?!\w)")


def nettoyer_ocr(texte: str) -> str:
	"""Le texte OCR sans les déchets des points de conduite (suites de symboles, jetons d'une
	lettre répétée comme « eee », « EE », « RRR »). Pur."""
	# le losange « ◆ » d'une puce est lu « @ » : en tête, c'est une puce ; ailleurs, un déchet
	t = re.sub(r"^\s*@\s+", "• ", texte or "")
	t = re.sub(r"(?<!\S)@(?!\S)", " ", t)
	t = _CONDUITE.sub(" ", t)
	t = _JETON_REPETE.sub(" ", t)
	# un jeton fait seulement de guillemets, étoiles ou points (guillemet orphelin) ne vaut rien non plus
	return " ".join(j for j in t.split() if not re.fullmatch(r"[*\"“”'’`.·_~=]+|-{2,}", j))


def est_traduisible(texte: str) -> bool:
	"""Faux pour ce qui ne doit pas passer par l'IA : nombres et unités seuls, URL, e-mails,
	références (AB-1234), lettres isolées, déchets d'OCR (moins de la moitié de lettres)."""
	t = (texte or "").strip()
	if len(t) < 2:
		return False
	if re.search(r"https?://|www\.|\w@\w", t):
		return False
	lettres = re.findall(r"[^\W\d_]", t)
	if len(lettres) < 2:
		return False
	if len(lettres) < 0.5 * len(t.replace(" ", "")):
		return False
	if " " not in t:
		# une référence (AB-1234, RO-50G) : des majuscules AVEC un chiffre ou un tiret — « CATALOGUE »
		# ou « WARNING » est un mot à traduire
		if _REFERENCE.fullmatch(t) and re.search(r"[\d\-_/.]", t):
			return False
		if len(lettres) <= 3 and re.search(r"\d", t):
			return False
	return True


def dedoublonner(paragraphes: list[dict]) -> tuple[list[str], dict]:
	"""-> (textes uniques, {id paragraphe: indice du texte unique}) : un en-tête répété sur
	40 pages se traduit une fois."""
	uniques, positions, index = [], {}, {}
	for p in paragraphes:
		cle = " ".join(p["texte"].split())
		if cle not in positions:
			positions[cle] = len(uniques)
			uniques.append(p["texte"])
		index[p["id"]] = positions[cle]
	return uniques, index


def repartir_lots(textes: list[str], taille_max: int = 25, chars_max: int = 6000) -> list[list[int]]:
	"""Indices des textes, par lots bornés en nombre et en caractères (un très long paragraphe
	fait un lot à lui seul)."""
	lots, courant, chars = [], [], 0
	for i, t in enumerate(textes):
		n = len(t)
		if courant and (len(courant) >= max(1, taille_max) or chars + n > chars_max):
			lots.append(courant)
			courant, chars = [], 0
		courant.append(i)
		chars += n
	if courant:
		lots.append(courant)
	return lots
