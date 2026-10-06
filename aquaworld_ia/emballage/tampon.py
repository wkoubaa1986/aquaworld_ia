"""Tampons (badges) SVG créés par l'IA — demande utilisateur 06/10/2026 : « créer un SVG tampon, comme
le poids par exemple, avec l'IA, dans le studio ».

L'IA ÉCRIT le SVG (formes, anneaux, étoiles, couleurs, textes) : c'est du vrai vectoriel, au code couleur
près, pour quelques centimes. Deux garde-fous, parce que le SVG part à l'imprimeur via MuPDF :
  - le texte COURBE (le propre d'un tampon) : MuPDF ignore `<textPath>` (vérifié : il n'en sortait qu'une
    lettre). L'IA l'écrit donc dans une balise à nous, `<texte-courbe>`, que `courber_textes` remplace par
    une lettre par élément `<text>`, tournée et placée sur le cercle (MuPDF rend bien rotation et
    `text-anchor`) ;
  - `nettoyer_svg` ne garde que des formes et du texte : ni script, ni image, ni lien externe, ni police
    exotique (Helvetica / Times, les polices de base que MuPDF sait toujours rendre).
Chaque proposition est enfin RENDUE par MuPDF : celle qui ne s'affiche pas est écartée.
"""
from __future__ import annotations

import html
import math
import re
import xml.etree.ElementTree as ET

NS = "http://www.w3.org/2000/svg"
FORMES = {
	"rond": "un cercle (tampon rond classique, anneau intérieur, texte courbe en haut et en bas)",
	"sceau": "un sceau dentelé (bord en étoile à nombreuses petites pointes, comme un macaron « garanti »)",
	"ecusson": "un écusson / blason (bouclier) avec un bandeau",
	"ruban": "un ruban horizontal (banderole aux extrémités repliées)",
	"rectangle": "un rectangle aux coins arrondis, façon étiquette ou cachet",
}
STYLES = {
	"plein": "fond plein dans la couleur principale, textes et ornements en blanc",
	"contour": "SANS fond : traits et textes dans la couleur principale, fond transparent (effet tampon encreur)",
}
BALISES = {"svg", "g", "defs", "title", "circle", "ellipse", "rect", "path", "polygon", "polyline", "line",
           "text", "tspan", "lineargradient", "radialgradient", "stop", "use"}
TAILLE_MAX = 120_000


def prompts(texte: str, forme: str | None, style: str | None, couleurs: list[str], idee: str, nombre: int) -> tuple[str, str]:
	"""(system, user) pour `chat_json`. Pur."""
	system = (
		"Tu es graphiste packaging. Tu dessines des tampons / badges en SVG pour un emballage imprimé.\n"
		"Réponds en JSON : {\"tampons\": [{\"titre\": str, \"svg\": str}]} avec exactement %d propositions DIFFÉRENTES "
		"(composition, ornements, hiérarchie du texte).\n"
		"RÈGLES DU SVG (impératives, le fichier part chez l'imprimeur) :\n"
		"- <svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 200 200\"> pour une forme ronde, carrée ou un écusson ; "
		"viewBox=\"0 0 300 120\" pour un ruban ou un rectangle. Tout le dessin tient DANS le viewBox, avec 4 unités de marge.\n"
		"- Éléments permis : g, circle, ellipse, rect, path, polygon, polyline, line, text, tspan, linearGradient, stop. "
		"INTERDITS : textPath, image, foreignObject, script, style, filter, mask, clipPath, liens externes.\n"
		"- Texte droit : <text x=\"..\" y=\"..\" text-anchor=\"middle\" font-family=\"Helvetica\" font-weight=\"bold\" "
		"font-size=\"..\" fill=\"#rrggbb\">. Polices : Helvetica (ou Times pour un style classique), rien d'autre.\n"
		"- Texte COURBE (le long d'un cercle) : UNIQUEMENT avec la balise <texte-courbe cx=\"100\" cy=\"100\" r=\"72\" "
		"centre=\"-90\" sens=\"haut\" taille=\"16\" couleur=\"#ffffff\" graisse=\"bold\" espacement=\"1\">TEXTE</texte-courbe> : "
		"centre = angle en degrés du milieu du texte (-90 = en haut, 90 = en bas), sens = haut (lettres vers l'extérieur, "
		"texte en haut du cercle) ou bas (texte lisible en bas du cercle), r = rayon de la ligne de base.\n"
		"- Couleurs : UNIQUEMENT celles données (codes #rrggbb exacts), plus le blanc #ffffff. Pas de dégradé sauf demande.\n"
		"- Le texte demandé figure EN ENTIER, sans faute ni mot ajouté (tu peux le répartir en lignes droites et courbes, "
		"et ajouter des ornements : anneaux, étoiles, traits, petites icônes géométriques).\n"
		"- Textes lisibles : jamais plus petit que 10 unités, jamais coupé par le bord." % nombre)
	user = (
		"Texte du tampon (respecter les mots) :\n%s\n\nForme : %s\nStyle : %s\nCouleurs à employer : %s\n%s"
		% (texte.strip(), FORMES.get(forme) or "au choix (varie les formes entre propositions)",
		   STYLES.get(style) or "au choix (varie plein / contour)", ", ".join(couleurs) or "#1e3a8a",
		   ("Ambiance voulue : %s\n" % idee.strip()) if (idee or "").strip() else ""))
	return system, user


def _largeur(texte: str, taille: float, gras: bool, serif: bool = False) -> float:
	"""Largeur d'un texte dans la police de base que MuPDF emploiera (métriques exactes)."""
	import pymupdf

	nom = ("tibo" if gras else "tiro") if serif else ("hebo" if gras else "helv")
	return pymupdf.Font(nom).text_length(texte, fontsize=taille)


def courber_textes(svg: str) -> str:
	"""Chaque `<texte-courbe …>TEXTE</texte-courbe>` devient un groupe de `<text>`, une lettre par élément,
	posée sur le cercle et tournée tangente à lui : la lettre reste droite en haut (sens « haut ») comme en
	bas (sens « bas »). Pur, à la police près (métriques Helvetica / Times de PyMuPDF)."""
	def un(m):
		attrs = dict(re.findall(r'([\w-]+)\s*=\s*"([^"]*)"', m.group(1)))
		texte = html.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip()
		if not texte:
			return ""
		try:
			cx, cy, r = float(attrs.get("cx", 100)), float(attrs.get("cy", 100)), float(attrs.get("r", 70))
			centre = float(attrs.get("centre", -90))
			taille = float(attrs.get("taille", 14))
			espacement = float(attrs.get("espacement", 1))
		except ValueError:
			return ""
		bas = attrs.get("sens", "haut") == "bas"
		gras = attrs.get("graisse", "bold") != "normal"
		serif = "times" in attrs.get("police", "").lower()
		couleur = attrs.get("couleur", "#000000")
		famille = "Times" if serif else "Helvetica"
		largeurs = [_largeur(c, taille, gras, serif) + espacement for c in texte]
		# En bas, la ligne de base s'écarte du centre pour que le corps des lettres reste sur le cercle.
		rayon = r + taille * 0.7 if bas else r
		total = sum(largeurs) / rayon                       # angle couvert (radians)
		sens = -1 if bas else 1                             # en bas on lit de gauche à droite en remontant les angles
		a = math.radians(centre) - sens * total / 2
		lettres = []
		for c, w in zip(texte, largeurs):
			milieu = a + sens * (w / 2) / rayon
			x, y = cx + rayon * math.cos(milieu), cy + rayon * math.sin(milieu)
			rot = math.degrees(milieu) + (-90 if bas else 90)
			if c.strip():
				lettres.append('<text transform="translate(%.2f,%.2f) rotate(%.2f)" x="0" y="0" text-anchor="middle" '
				               'font-family="%s" font-weight="%s" font-size="%.2f" fill="%s">%s</text>'
				               % (x, y, rot, famille, "bold" if gras else "normal", taille, html.escape(couleur), html.escape(c)))
			a += sens * w / rayon
		return "<g>%s</g>" % "".join(lettres)

	return re.sub(r"<texte-courbe\b([^>]*)>(.*?)</texte-courbe>", un, svg, flags=re.S | re.I)


def _local(tag: str) -> str:
	return tag.rsplit("}", 1)[-1].lower()


def nettoyer_svg(svg: str) -> str | None:
	"""Un SVG d'IA -> un SVG imprimable : balises permises seulement, aucun script ni attribut on*, aucun
	lien externe, polices ramenées à Helvetica / Times, viewBox présent. None si le SVG est illisible."""
	if not svg or len(svg) > TAILLE_MAX:
		return None
	svg = svg.strip()
	svg = re.sub(r"^```(?:svg|xml)?\s*|\s*```$", "", svg)
	try:
		racine = ET.fromstring(svg)
	except ET.ParseError:
		return None
	if _local(racine.tag) != "svg":
		return None

	def nettoyer(el):
		for enfant in list(el):
			if _local(enfant.tag) not in BALISES:
				el.remove(enfant)
				continue
			nettoyer(enfant)
		for nom in list(el.attrib):
			court, val = _local(nom), el.attrib[nom]
			if court.startswith("on") or court == "style" and re.search(r"url\(|@import|expression", val, re.I):
				del el.attrib[nom]
			elif court == "href" and not val.startswith("#"):
				del el.attrib[nom]
			elif court == "font-family":
				el.attrib[nom] = "Times" if re.search(r"times|serif|garamond|georgia", val, re.I) and "sans" not in val.lower() else "Helvetica"
	nettoyer(racine)
	vb = racine.attrib.get("viewBox")
	if not vb:
		w, h = racine.attrib.get("width", "200"), racine.attrib.get("height", "200")
		try:
			vb = "0 0 %g %g" % (float(re.sub(r"[^\d.]", "", w) or 200), float(re.sub(r"[^\d.]", "", h) or 200))
		except ValueError:
			vb = "0 0 200 200"
		racine.attrib["viewBox"] = vb
	_x, _y, w, h = (vb.replace(",", " ").split() + ["200", "200"])[:4]
	racine.attrib["width"], racine.attrib["height"] = w, h
	ET.register_namespace("", NS)
	if racine.tag == "svg":
		racine.tag = "{%s}svg" % NS
	return ET.tostring(racine, encoding="unicode")


def rendu_ok(svg: str) -> bool:
	"""MuPDF sait-il dessiner ce SVG (ce que fera la composition) ?"""
	import pymupdf

	try:
		page = pymupdf.open(stream=svg.encode("utf-8"), filetype="svg")[0]
		page.get_pixmap(dpi=36)
		return page.rect.width > 0
	except Exception:
		return False


def preparer(reponse: dict) -> list[dict]:
	"""La réponse de l'IA -> [{titre, svg}] imprimables : texte courbe converti, nettoyé, rendu vérifié."""
	out = []
	for t in (reponse or {}).get("tampons") or []:
		if not isinstance(t, dict) or not isinstance(t.get("svg"), str):
			continue
		svg = nettoyer_svg(courber_textes(t["svg"]))
		if svg and rendu_ok(svg):
			out.append({"titre": str(t.get("titre") or "Tampon")[:80], "svg": svg})
	return out
