"""Rendu LaTeX déterministe : textes échappés, images locales, commandes externes désactivées."""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile

from PIL import Image
from pathlib import Path

import frappe
from frappe.utils.file_manager import save_file

from aquaworld_ia.documents_produit import contexte as C
from aquaworld_ia.documents_produit import mise_en_page as M

ECHAPPE = {
	"\\": r"\textbackslash{}",
	"{": r"\{",
	"}": r"\}",
	"$": r"\$",
	"&": r"\&",
	"#": r"\#",
	"%": r"\%",
	"_": r"\_",
	"~": r"\textasciitilde{}",
	"^": r"\textasciicircum{}",
}
POLICES = {
	"ar": "Noto Naskh Arabic",
	"fa": "Noto Naskh Arabic",
	"ur": "Noto Naskh Arabic",
	"he": "Noto Sans Hebrew",
	"zh": "Noto Sans CJK SC",
	"ja": "Noto Sans CJK JP",
	"ko": "Noto Sans CJK KR",
	"hi": "Noto Sans Devanagari",
	"bn": "Noto Sans Bengali",
	"ta": "Noto Sans Tamil",
	"te": "Noto Sans Telugu",
	"th": "Noto Sans Thai",
	"ka": "Noto Sans Georgian",
	"hy": "Noto Sans Armenian",
	"km": "Noto Sans Khmer",
	"lo": "Noto Sans Lao",
	"ml": "Noto Sans Malayalam",
	"gu": "Noto Sans Gujarati",
	"kn": "Noto Sans Kannada",
	"pa": "Noto Sans Gurmukhi",
	"si": "Noto Sans Sinhala",
	"my": "Noto Sans Myanmar",
	"am": "Noto Sans Ethiopic",
}


def echapper(s):
	return "".join(ECHAPPE.get(c, c) for c in str(s or "") if ord(c) >= 32 or c in "\n\t").replace(
		"\n", "\n\n"
	)


# Symboles absents de Noto Sans (flèches, ≤ ≥ ≈ ≠ ∞, formes, coches, dingbats) : l'IA en écrit volontiers
# (« ↔ », « → », « ≥ 3 bar ») et XeLaTeX signalait « Missing character » — PDF refusé (06/11/2026, AP-M).
# Ils passent dans une police de secours présente sur le serveur ; sans police, un équivalent texte.
SYMBOLES = re.compile(r"[\u2190-\u21ff\u2200-\u22ff\u2300-\u23ff\u2460-\u24ff\u2500-\u27bf\u2b00-\u2bff]+")
POLICES_SYMBOLES = ("Noto Sans Symbols2", "Noto Sans Symbols", "DejaVu Sans", "Noto Sans Math", "Noto Sans CJK SC")
SYMBOLES_TEXTE = {"↔": "<->", "→": "->", "←": "<-", "⇒": "=>", "⇐": "<=", "⇔": "<=>", "↑": "^", "↓": "v",
	"≤": "<=", "≥": ">=", "≠": "!=", "≈": "~", "∞": "infini", "✓": "v", "✔": "v", "✗": "x", "✘": "x",
	"★": "*", "☆": "*", "●": "-", "○": "o", "■": "-", "□": "-", "▪": "-", "►": ">", "▶": ">", "•": "-"}


def police_symboles():
	"""La première police de secours installée qui couvre flèches et opérateurs ; None si aucune. Mise en cache."""
	if not hasattr(police_symboles, "cache"):
		police_symboles.cache = None
		if shutil.which("fc-list"):
			for famille in POLICES_SYMBOLES:
				try:
					sortie = subprocess.run(["fc-list", f":family={famille}:charset=2194 2264", "family"],
						capture_output=True, text=True, timeout=10).stdout
				except (OSError, subprocess.SubprocessError):
					sortie = ""
				if famille in sortie.splitlines():
					police_symboles.cache = famille
					break
	return police_symboles.cache


def symboles(s):
	"""Les symboles hors Noto Sans en police de secours, ou en texte s'il n'y en a pas."""
	if police_symboles():
		return SYMBOLES.sub(lambda m: r"{\symbolfont " + m.group(0) + "}", s)
	return SYMBOLES.sub(lambda m: "".join(SYMBOLES_TEXTE.get(c, "") for c in m.group(0)), s)


def texte(s, rtl=False):
	if not rtl:
		return symboles(echapper(s))
	# Les références et valeurs latines gardent leur sens de lecture dans un paragraphe RTL.
	morceaux = re.split(r"([^\u0590-\u08ff\ufb1d-\ufdff\ufe70-\ufeff\n]+)", str(s or ""))
	return "".join(
		(r"{\LR{\latinfont " + symboles(echapper(v)) + "}}") if i % 2 and v.strip() else symboles(echapper(v))
		for i, v in enumerate(morceaux)
	)


def image_png(octets):
	import pymupdf
	from PIL import Image, ImageOps

	try:
		with Image.open(io.BytesIO(octets)) as im:
			if im.width * im.height > 40_000_000:
				raise ValueError("Illustration trop grande.")
			im = ImageOps.exif_transpose(im).convert("RGBA")
			im.thumbnail((2400, 2400))
			out = io.BytesIO()
			im.save(out, format="PNG")
			return out.getvalue()
	except (OSError, SyntaxError):
		# Les SVG sont rasterisés en local sans exécuter de script ni de commande externe.
		if b"<svg" not in octets[:2000].lower() or re.search(
			rb"(?:href\s*=\s*[\"\']\s*(?:https?:|file:|/)|<!ENTITY|<!DOCTYPE)", octets, re.I
		):
			raise ValueError("Image non prise en charge. Utilisez PNG, JPEG, WebP ou SVG autonome.")
		with pymupdf.open(stream=octets, filetype="svg") as svg:
			pdf = svg.convert_to_pdf()
		with pymupdf.open(stream=pdf, filetype="pdf") as p:
			return (
				p[0]
				.get_pixmap(
					matrix=pymupdf.Matrix(
						min(2, 2400 / max(p[0].rect.width, p[0].rect.height)),
						min(2, 2400 / max(p[0].rect.width, p[0].rect.height)),
					),
					alpha=True,
				)
				.tobytes("png")
			)


def qr_png(url):
	"""QR (correction M, noir sur blanc) d'un lien, en PNG net : 10 px par module, marge de 2 modules."""
	import segno

	buffer = io.BytesIO()
	segno.make(url, error="m").save(buffer, kind="png", scale=10, border=2)
	return buffer.getvalue()


def plan_tableau_variantes(variantes, caracteristiques, labels, max_caracteristiques=3, seuil_groupes=6):
	"""Le tableau des variantes résumé par caractéristiques (demande 06/11/2026). PURE.

	- une colonne par attribut de variante (membrane, configuration, mixage…) au lieu d'une phrase
	  « nom : valeur ; nom : valeur » par ligne ;
	- les caractéristiques techniques propres à une variante (portée = cette variante) deviennent des colonnes
	  (les plus renseignées d'abord, `max_caracteristiques` au plus) ;
	- au-delà de `seuil_groupes` variantes et avec au moins deux attributs, les lignes sont regroupées par la
	  valeur du premier attribut (titre de groupe, colonne retirée) ;
	- la marque n'est une colonne que si elle varie ; sans attribut, le nom de la variante tient lieu de configuration.
	-> {"entetes": [...], "groupes": [(titre ou "", [[cellules]...]) ...]}
	"""
	if not variantes:
		return {"entetes": [labels["reference"]], "groupes": []}
	noms = []
	for v in variantes:
		for a in v.get("attributs", []):
			if a["nom"] not in noms:
				noms.append(a["nom"])
	valeur = lambda v, nom: next((a["valeur"] for a in v.get("attributs", []) if a["nom"] == nom), "")
	marques = {v.get("marque", "") for v in variantes}
	# Caractéristiques pivotées : nom -> {article: "valeur unité"}, les plus renseignées d'abord.
	pivot = {}
	for c in caracteristiques:
		if c.get("article") and c.get("nom"):
			pivot.setdefault(c["nom"], {})[c["article"]] = (c.get("valeur", "") + (" " + c["unite"] if c.get("unite") else "")).strip()
	colonnes_carac = sorted(pivot, key=lambda k: (-len(pivot[k]), k))[:max_caracteristiques]
	grouper = len(variantes) > seuil_groupes and len(noms) >= 2 and len({valeur(v, noms[0]) for v in variantes}) >= 2
	attributs_colonnes = noms[1:] if grouper else noms
	entetes = [labels["reference"]] + ([labels["marque"]] if len(marques) > 1 else []) + attributs_colonnes
	if not noms:
		entetes.append(labels["configuration"])
	entetes += colonnes_carac
	def ligne(v):
		cellules = [v["article"]] + ([v.get("marque", "")] if len(marques) > 1 else []) + [valeur(v, nom) for nom in attributs_colonnes]
		if not noms:
			cellules.append(v.get("nom", ""))
		cellules += [pivot[nom].get(v["article"], "") for nom in colonnes_carac]
		return cellules
	if not grouper:
		return {"entetes": entetes, "groupes": [("", [ligne(v) for v in variantes])]}
	groupes = []
	for v in variantes:
		cle = valeur(v, noms[0])
		if not groupes or groupes[-1][0] != noms[0] + " : " + cle:
			groupes.append((noms[0] + " : " + cle, []))
		groupes[-1][1].append(ligne(v))
	return {"entetes": entetes, "groupes": groupes}


def source(contenu, ctx, langue="fr", rtl=False, numero=1, valide=False, assets=None):
	assets = assets or {}
	disposition = M.normaliser(ctx.get("mise_en_page"))

	def t(s):
		return texte(s, rtl)

	labels = contenu["libelles"]
	police = POLICES.get(langue.split("-")[0], "Noto Sans")
	en_tete = r"""\documentclass[10pt,a4paper]{article}
\usepackage[margin=18mm,headheight=16pt]{geometry}
\usepackage{fontspec}
\usepackage{graphicx}
\usepackage{eso-pic,adjustbox}
\usepackage{paracol}
\usepackage{needspace}
\usepackage[table]{xcolor}
\usepackage{array,longtable,booktabs}
\usepackage{fancyhdr}
\usepackage{hyperref}
\definecolor{aqua}{HTML}{087E8B}
\hypersetup{hidelinks}
\setlength{\parindent}{0pt}
\setlength{\parskip}{6pt}
\setlength{\emergencystretch}{4em}
\newcommand{\docsection}[1]{\section*{\color{aqua}#1}}
\pagestyle{fancy}
\fancyhf{}
\renewcommand{\headrulewidth}{0pt}
\fancyfoot[C]{\thepage}
"""
	en_tete = en_tete.replace("{087E8B}", "{" + disposition["couleur"][1:] + "}")
	script = "[Script=Arabic]" if langue.split("-")[0] in ("ar", "fa", "ur") else ""
	en_tete += "\\setmainfont" + script + "{" + police + "}\n\\newfontfamily\\latinfont{Noto Sans}\n"
	if police_symboles():
		en_tete += "\\newfontfamily\\symbolfont{" + police_symboles() + "}\n"
	if rtl:
		en_tete += "\\usepackage{bidi}\n"
	if langue.split("-")[0] in ("zh", "ja", "ko"):
		en_tete += '\\XeTeXlinebreaklocale "' + langue.split("-")[0] + '"\n'
	bandeaux = assets.get("entete", {})
	if bandeaux:
		haut, bas = bandeaux.get("haut"), bandeaux.get("bas")
		hh, hb = (haut["hauteur"] if haut else 0), (bas["hauteur"] if bas else 0)
		en_tete += (
			f"\\geometry{{top={18 + hh:.2f}mm,headheight={max(6, hh):.2f}mm,headsep=6mm,"
			f"bottom={22 + hb:.2f}mm,footskip={12 + hb:.2f}mm}}\n"
		)
		if haut:
			position = {"Left": "L", "Right": "R"}.get(haut.get("align"), "C")
			en_tete += (f"\\fancyhead[{position}]{{\\includegraphics[width={haut['largeur']:.2f}mm,"
				f"height={hh:.2f}mm,keepaspectratio]{{{haut['fichier']}}}}}\n")
		if bas:
			alignement = {"Left": r"\raggedright", "Right": r"\raggedleft"}.get(bas.get("align"), r"\centering")
			en_tete += (r"\fancyfoot[C]{\begin{minipage}[b]{\textwidth}" + alignement
				+ f"\\includegraphics[width={bas['largeur']:.2f}mm,height={hb:.2f}mm,keepaspectratio]{{{bas['fichier']}}}"
				+ r"\par\centering\small\thepage\end{minipage}}" + "\n")
	body = [en_tete, "\\begin{document}", "\\setRTL" if rtl else ""]
	alignement = {"gauche": r"\raggedright", "centre": r"\centering", "droite": r"\raggedleft"}
	marque = {**M.MARQUE_DEFAUTS, **disposition}
	if marque["position_marque"] == "libre":
		positions = []

		def placer(element, y):
			return (
				r"\put(\LenToUnit{" + f"{marque['logo_x']:.1f}" + r"mm},\LenToUnit{-"
				+ f"{y:.1f}" + r"mm}){\makebox(0,0)[lt]{" + element + "}}"
			)

		if assets.get("logo"):
			positions.append(placer(
				r"\includegraphics[width=" + str(marque["largeur_logo"]) + "mm,height="
				+ f"{marque['largeur_logo'] * 18 / 32:.2f}"
				+ "mm,keepaspectratio]{" + assets["logo"] + "}", marque["logo_y"],
			))
		nom = ctx.get("marque_document") or ctx["article"].get("brand") or ""
		if marque["afficher_nom_marque"] and nom:
			positions.append(placer(
				r"\adjustbox{max width=" + str(marque["largeur_logo"])
				+ r"mm,max height=6mm}{\strut\small\bfseries " + t(nom.replace("\n", " ")) + "}",
				marque["logo_y"] + marque["largeur_logo"] * 18 / 32 + 1,
			))
		if positions:
			body.append(r"\AddToShipoutPictureFG*{\AtPageUpperLeft{" + "\n".join(positions) + "}}")
	zone_marque = []
	if marque["position_marque"] not in ("masquee", "libre"):
		if assets.get("logo"):
			largeur = marque["largeur_logo"]
			zone_marque.append(
				r"\includegraphics[width=" + str(largeur) + "mm,height="
				+ f"{largeur * 18 / 32:.2f}" + "mm,keepaspectratio]{" + assets["logo"] + r"}\par"
			)
		if marque["afficher_nom_marque"]:
			nom_marque = ctx.get("marque_document") or ctx["article"].get("brand") or ""
			if nom_marque:
				zone_marque.append(r"{\bfseries " + t(nom_marque) + r"}\par")
	if zone_marque:
		zone_marque = [r"\begingroup" + alignement[marque["alignement_marque"]], *zone_marque, r"\endgroup"]
	# QR code d'un lien internet, légende dessous ; l'image est aussi un lien cliquable dans le PDF.
	qr = {**M.QR_DEFAUTS, **disposition}
	zone_qr = []
	if qr["qr_url"] and assets.get("qr"):
		url_tex = qr["qr_url"].replace("\\", "").replace("%", r"\%").replace("#", r"\#")
		image = r"\includegraphics[width=" + str(qr["qr_taille"]) + "mm]{" + assets["qr"] + "}"
		zone_qr = [r"\begingroup" + alignement[qr["qr_alignement"]], r"\href{" + url_tex + "}{" + image + r"}\par"]
		if qr["qr_legende"]:
			zone_qr.append(r"{\small " + t(qr["qr_legende"]) + r"}\par")
		zone_qr.append(r"\endgroup")

	def zones(position):
		return (zone_marque if marque["position_marque"] == position else []) + (zone_qr if qr["qr_position"] == position else [])

	body.extend(zones("avant_titre"))
	body.append(r"\begingroup" + alignement[disposition["alignement_titre"]])
	body += [
		r"{\LARGE\bfseries\color{aqua} " + t(contenu["titre"]) + r"}\par",
		t(ctx.get("marque_document") or ctx["article"].get("brand") or "") + r"\quad " + t(ctx["article"]["name"]) + r"\par",
		t(labels["version"]) + " " + str(numero) + r"\par",
	]
	if not valide:
		body.append(r"{\color{red}\bfseries " + t(labels["brouillon"]) + r"}\par")
	body.append(r"\endgroup")
	body.extend(zones("apres_titre"))
	blocs = {cle: [] for cle in M.ORDRE}

	def photo(index, largeur, hauteur, portee=True):
		lignes = [
			r"\begin{center}\includegraphics[width=" + f"{largeur:.2f}"
			+ r"\linewidth,height=" + str(hauteur) + "mm,keepaspectratio]{"
			+ assets["images"][index] + r"}\end{center}",
			t(contenu["legendes"][index]) + r"\par",
		]
		if portee and ctx["images"][index].get("article"):
			lignes.append(t(labels["portee"] + " : " + ctx["images"][index]["article"]) + r"\par")
		return "\n".join(lignes)

	def galerie(indices, portee=True, extra=None):
		"""Les photos `indices` en galerie ; `extra` (LaTeX) devient une vignette de plus, en dernier — le QR
		prend ainsi la case libre de la grille au lieu de pendre sous la galerie (demande 06/11/2026)."""
		colonnes = disposition.get("colonnes_photos", 1)
		hauteur = disposition.get("hauteur_vignettes", 55)
		tete = []
		if disposition.get("style_galerie") == "mosaique" and len(indices) >= 2:
			# Mosaïque : la première photo en grand à gauche (hauteur des trois petites), jusqu'à trois petites empilées
			# à droite ; le reste de la galerie suit en grille.
			petites = indices[1:4]
			# Les petites et leurs légendes (~7 mm chacune) font la hauteur de la grande. Quand les dimensions de la
			# grande sont connues (composer les fournit), sa hauteur réelle à 62 % de la largeur fixe celle des
			# petites, pour que les bas s'alignent ; sinon la grande suit la colonne des petites.
			dims = (assets.get("dimensions") or {}).get(assets["images"][indices[0]])
			if dims and dims[0] > 0:
				# Entre deux petites : légende, \par et marges du centrage ≈ 11 mm (mesuré sur le PDF).
				hauteur_grande = min(108 * dims[1] / dims[0], 160)
				petite = max(18, min(hauteur, (hauteur_grande - 11 * (len(petites) - 1)) / len(petites)))
			else:
				petite = hauteur
				hauteur_grande = petite * len(petites) + 11 * (len(petites) - 1)
			grande = photo(indices[0], 1, round(hauteur_grande, 1), portee)
			colonne = "\n".join(photo(i, 1, round(petite, 1), portee) for i in petites)
			tete = [r"\noindent\begin{minipage}[t]{0.62\linewidth}\vspace{0pt}\small " + grande + r"\end{minipage}\hfill"
				+ r"\begin{minipage}[t]{0.35\linewidth}\vspace{0pt}\small " + colonne + r"\end{minipage}\par\medskip"]
			indices = indices[4:]
			if not indices and not extra:
				return tete
			colonnes = max(colonnes, 2)
		if colonnes == 1:
			return tete + [photo(i, .8, 85 if disposition.get("photos_variantes") else 120, portee) for i in indices] + ([extra] if extra else [])
		contenus = [photo(i, 1, hauteur, portee) for i in indices] + ([extra] if extra else [])
		lignes = list(tete)
		for debut in range(0, len(contenus), colonnes):
			cellules = [r"\begin{minipage}[t]{" + f"{(1 - .04 * (colonnes - 1)) / colonnes:.3f}"
				+ r"\linewidth}\vspace{0pt}\small " + cellule + r"\end{minipage}"
				for cellule in contenus[debut:debut + colonnes]]
			# Une dernière ligne incomplète garde ses cases alignées à gauche : des cellules vides complètent la ligne.
			cellules += [r"\begin{minipage}[t]{" + f"{(1 - .04 * (colonnes - 1)) / colonnes:.3f}" + r"\linewidth}\strut\end{minipage}"] * (colonnes - len(cellules))
			lignes.append(r"\noindent " + r"\hfill ".join(cellules) + r"\par\medskip")
		return lignes

	resume = t(contenu["resume"]) + r"\par"
	position = disposition["position_photo"]
	largeur = disposition["largeur_photo"] / 100
	if not assets.get("images"):
		blocs["presentation"] = [resume]
	elif position in ("gauche", "droite"):
		image = photo(0, 1, disposition["hauteur_photo"])
		gauche, droite = (image, resume) if position == "gauche" else (resume, image)
		ratio = largeur if position == "gauche" else 1 - largeur
		blocs["presentation"] = [
			r"\setlength{\columnsep}{6mm}\columnratio{" + f"{ratio:.2f}" + "}",
			r"\begin{paracol}{2}", gauche, r"\switchcolumn", droite, r"\end{paracol}",
		]
	else:
		image = photo(0, largeur, disposition["hauteur_photo"])
		blocs["presentation"] = [image, resume] if position == "avant" else [resume, image]
	def tableau_rubrique(lignes):
		"""Tableau saisi dans une rubrique : première ligne en gras, colonnes de même largeur, lignes fines."""
		n = len(lignes[0])
		colonnes = (r">{\raggedright\arraybackslash}p{" + f"{(1 - .03 * (n - 1)) / n:.3f}" + r"\linewidth}") * n
		tex = [r"\begin{longtable}{" + colonnes + "}", r"\toprule"]
		tex.append(" & ".join(r"\bfseries " + t(c) for c in lignes[0]) + r"\\\midrule\endhead")
		tex += [" & ".join(t(c) for c in ligne) + r"\\\addlinespace" for ligne in lignes[1:]]
		tex.append(r"\bottomrule\end{longtable}")
		return "\n".join(tex)

	for i, s in enumerate(contenu["sections"]):
		blocs["rubriques"].append(r"\docsection{" + t(s["titre"]) + "}")
		if s.get("article"):
			blocs["rubriques"].append(r"{\small " + t(labels["portee"] + " : " + s["article"]) + r"}\par")
		corps = t(s["texte"]) + r"\par"
		fichier = (assets.get("sections") or {}).get(i)
		if s.get("image") and fichier:
			# Image de rubrique (graphe, schéma) : à côté du texte en deux colonnes, ou au-dessus / en dessous.
			legende = (r"{\small " + t(s.get("image_legende", "")) + r"}\par") if s.get("image_legende") else ""
			largeur = s.get("image_largeur", 40) / 100
			if s["image_position"] in ("droite", "gauche"):
				image = (r"\begin{center}\includegraphics[width=\linewidth,height=90mm,keepaspectratio]{" + fichier
					+ r"}\end{center}" + legende)
				gauche, droite = (corps, image) if s["image_position"] == "droite" else (image, corps)
				ratio = 1 - largeur if s["image_position"] == "droite" else largeur
				corps = "\n".join([r"\setlength{\columnsep}{6mm}\columnratio{" + f"{ratio:.2f}" + "}",
					r"\begin{paracol}{2}", gauche, r"\switchcolumn", droite, r"\end{paracol}"])
			else:
				image = (r"\begin{center}\includegraphics[width=" + f"{largeur:.2f}"
					+ r"\linewidth,height=120mm,keepaspectratio]{" + fichier + r"}\end{center}" + legende)
				corps = image + "\n" + corps if s["image_position"] == "dessus" else corps + "\n" + image
		blocs["rubriques"].append(corps)
		if s.get("tableau"):
			blocs["rubriques"].append(tableau_rubrique(s["tableau"]))
	if contenu["caracteristiques"]:
		blocs["caracteristiques"] += [
			r"\docsection{" + t(labels["caracteristiques"]) + "}",
			r"\begin{longtable}{p{.27\linewidth}p{.42\linewidth}p{.19\linewidth}}",
			r"\toprule "
			+ " & ".join(t(labels[k]) for k in ("parametre", "valeur", "portee"))
			+ r"\\\midrule\endhead",
		]
		for c in contenu["caracteristiques"]:
			blocs["caracteristiques"].append(
				" & ".join(
					t(s)
					for s in [
						c["nom"],
						c["valeur"] + (" " + c["unite"] if c["unite"] else ""),
						c["article"] or labels["commun"],
					]
				)
				+ r"\\\addlinespace"
			)
		blocs["caracteristiques"].append(r"\bottomrule\end{longtable}")
	regrouper = disposition.get("photos_variantes", 0)
	photos_variantes = {v["article"]: [] for v in contenu["variantes"]}
	for i, im in enumerate(ctx.get("images", [])):
		if i and regrouper and im.get("article") in photos_variantes:
			photos_variantes[im["article"]].append(i)
	illustrees = [v for v in contenu["variantes"] if photos_variantes[v["article"]]] if regrouper else []
	tabulees = [v for v in contenu["variantes"] if v not in illustrees]
	if illustrees:
		blocs["variantes"].append(r"\docsection{" + t(labels["variantes"]) + "}")
		for v in illustrees:
			blocs["variantes"].append(r"\Needspace{" + ("110" if photos_variantes[v["article"]] else "35") + "mm}")
			blocs["variantes"].append(r"\subsection*{" + t(v["article"] + " — " + v["nom"]) + "}")
			blocs["variantes"].append(t(v["marque"]) + r"\par")
			blocs["variantes"].extend(t(a["nom"] + " : " + a["valeur"]) + r"\par" for a in v["attributs"])
			blocs["variantes"].extend(galerie(photos_variantes[v["article"]], portee=False))
	if tabulees:
		if not illustrees:
			blocs["variantes"].append(r"\docsection{" + t(labels["variantes"]) + "}")
		plan = plan_tableau_variantes(tabulees, contenu.get("caracteristiques", []), labels)
		n = len(plan["entetes"])
		largeurs = [.2] + [(.78 - .2) / (n - 1)] * (n - 1) if n > 1 else [.98]
		colonnes = "".join(r">{\raggedright\arraybackslash}p{" + f"{l:.3f}" + r"\linewidth}" for l in largeurs)
		blocs["variantes"] += [
			r"\begin{longtable}{" + colonnes + "}",
			r"\toprule " + " & ".join(r"\bfseries " + t(e) for e in plan["entetes"]) + r"\\\midrule\endhead",
		]
		for titre_groupe, lignes in plan["groupes"]:
			if titre_groupe:
				blocs["variantes"].append(r"\multicolumn{" + str(n) + r"}{l}{\bfseries\color{aqua} " + t(titre_groupe) + r"}\\\addlinespace")
			for ligne in lignes:
				blocs["variantes"].append(" & ".join(t(c) for c in ligne) + r"\\\addlinespace")
		blocs["variantes"].append(r"\bottomrule\end{longtable}")
	regroupees = {i for indices in photos_variantes.values() for i in indices}
	illustrations = [i for i in range(1, len(assets.get("images", []))) if i not in regroupees]
	# Le QR peut rejoindre le bloc « Autres illustrations » (demande 06/11/2026) : après la galerie, ou seul
	# sous le titre du bloc quand il n'y a pas d'autre illustration — le bloc suit alors l'ordre choisi.
	qr_illustrations = "\n".join(zone_qr) if qr["qr_position"] == "illustrations" and zone_qr else None
	if illustrations or qr_illustrations:
		if regrouper or disposition.get("colonnes_photos", 1) > 1 or (qr_illustrations and not illustrations):
			blocs["illustrations"].append(r"\docsection{" + t(labels["illustrations"]) + "}")
		blocs["illustrations"].extend(galerie(illustrations, extra=qr_illustrations))
	for cle in disposition["ordre"]:
		body.extend(blocs[cle])
	if contenu.get("points_a_verifier"):
		body += [r"\docsection{" + t(labels["brouillon"]) + "}"]
		body += [t("• " + p) + r"\par" for p in contenu["points_a_verifier"]]
	if ctx.get("sources"):
		body += [r"\docsection{" + t(labels["sources"]) + "}"]
		body += [
			t("S{} — {}{}".format(i + 1, s["nom"], (" — " + s["pages"]) if s["pages"] else "")) + r"\par"
			for i, s in enumerate(ctx["sources"])
		]
	body.extend(zones("fin_document"))
	body.append(r"\end{document}")
	return "\n".join(body)


def compiler(tex, fichiers):
	moteur = shutil.which("xelatex")
	if not moteur:
		raise ValueError("XeLaTeX est absent du serveur. Installez les dépendances LaTeX du module.")
	with tempfile.TemporaryDirectory(prefix="doc-produit-") as temp:
		p = Path(temp)
		(p / "images").mkdir()
		(p / "document.tex").write_text(tex, encoding="utf-8")
		for name, b in fichiers.items():
			if not re.fullmatch(r"images/(?:logo|qr|image-[0-9]+|section-[0-9]+|entete-(?:haut|bas))\.png", name):
				raise ValueError("Nom de fichier LaTeX invalide.")
			(p / name).write_bytes(b)
		env = {**os.environ, "openin_any": "p", "openout_any": "p", "shell_escape": "f", "TEXMFOUTPUT": temp}
		for _ in range(2):
			r = subprocess.run(
				[moteur, "-no-shell-escape", "-halt-on-error", "-interaction=nonstopmode", "document.tex"],
				cwd=temp,
				env=env,
				stdout=subprocess.PIPE,
				stderr=subprocess.STDOUT,
				timeout=100,
			)
			if r.returncode:
				raise ValueError(
					"Composition LaTeX impossible : " + r.stdout.decode(errors="replace")[-1300:]
				)
		log = (p / "document.log").read_text(errors="replace")
		if "Missing character:" in log:
			manquants = re.findall(r"Missing character:.*", log)[:3]
			raise ValueError(
				"La police ne couvre pas tous les caractères de cette langue : " + " ; ".join(manquants)
			)
		pdf = (p / "document.pdf").read_bytes()
		archive = io.BytesIO()
		with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
			z.writestr("document.tex", tex)
			z.writestr(
				"README.txt",
				"Compiler avec XeLaTeX (2 passages), texlive-xetex, texlive-latex-extra, texlive-fonts-recommended, texlive-lang-arabic, fonts-noto-core et fonts-noto-cjk.\n",
			)
			for name, b in fichiers.items():
				z.writestr(name, b)
		return pdf, archive.getvalue()


def composer(contenu, ctx, langue="fr", rtl=False, numero=1, valide=False):
	"""Compose en mémoire, pour le PDF enregistré comme pour son aperçu sans écriture."""
	from aquaworld_ia.documents_produit.entetes import rendre

	fichiers = {}
	assets = {"images": []}
	if ctx.get("logo") and (not ctx.get("entete") or ctx.get("logo_marque_avec_entete")) and ctx.get("mise_en_page", {}).get("position_marque") != "masquee":
		fichiers["images/logo.png"] = image_png(C.octets(ctx["logo"]))
		assets["logo"] = "images/logo.png"
	if ctx.get("entete"):
		assets["entete"] = {}
		for cle, bandeau in rendre(ctx["entete"]).items():
			name = "images/entete-" + cle + ".png"
			fichiers[name] = bandeau["png"]
			assets["entete"][cle] = {k: v for k, v in bandeau.items() if k != "png"}
			assets["entete"][cle]["fichier"] = name
	assets["dimensions"] = {}
	for i, im in enumerate(ctx.get("images", [])):
		name = f"images/image-{i}.png"
		fichiers[name] = image_png(C.octets(im["image"]))
		assets["images"].append(name)
		try:
			with Image.open(io.BytesIO(fichiers[name])) as pil:
				assets["dimensions"][name] = pil.size     # (largeur, hauteur) px : mosaïque de la galerie
		except Exception:
			pass
	assets["sections"] = {}
	for i, s in enumerate(contenu.get("sections", [])):
		if s.get("image"):
			name = f"images/section-{i}.png"
			fichiers[name] = image_png(C.octets(s["image"]))
			assets["sections"][i] = name
	url_qr = M.qr_valide(M.normaliser(ctx.get("mise_en_page")))
	if url_qr:
		fichiers["images/qr.png"] = qr_png(url_qr)
		assets["qr"] = "images/qr.png"
	tex = source(contenu, ctx, langue, bool(rtl), numero, valide, assets)
	pdf, archive = compiler(tex, fichiers)
	return tex, pdf, archive


def generer_pdf(doc, valider=False):
	contenu, ctx = json.loads(doc.contenu_json), json.loads(doc.contexte_json)
	if valider and contenu["points_a_verifier"]:
		raise ValueError("Résolvez les points à vérifier avant de valider le document.")
	tex, pdf, archive = composer(contenu, ctx, doc.langue, doc.rtl, doc.numero, valider or doc.statut == "Validé")
	prefixe = doc.name + "-" + doc.langue
	urls = {}
	for champ, suffixe, b in (
		("pdf", ".pdf", pdf),
		("source_latex", ".tex", tex.encode("utf-8")),
		("archive_latex", ".zip", archive),
	):
		urls[champ] = save_file(prefixe + suffixe, b, C.DOCUMENT, doc.name, is_private=1).file_url
	doc.update(urls)
	if valider:
		doc.statut = "Validé"
	doc.flags.document_produit_interne = True
	doc.save()
	return urls
