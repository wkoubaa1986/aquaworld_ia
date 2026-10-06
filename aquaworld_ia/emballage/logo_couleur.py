"""Un logo d'une seule couleur, et sa sortie en SVG (demande utilisateur 06/10/2026 : « uniformiser la
couleur du logo par rapport à une couleur que je choisis d'une palette ; le résultat en SVG »).

SANS IA, volontairement : la couleur est EXACTE (le code choisi, au chiffre près), gratuite et
immédiate — l'IA, elle, redessine les lettres et n'atteint jamais une couleur précise.
  - un logo SVG vectoriel est recoloré tel quel : ses courbes ne bougent pas ;
  - un logo PNG / JPEG (ou un SVG qui embarque une image) est recoloré pixel par pixel, puis
    VECTORISÉ par vtracer quand la sortie demandée est le SVG (courbes de Bézier, trous des lettres
    conservés).
Le blanc peut être gardé : l'évidement d'un logo (lettre blanche sur une pastille) reste blanc.
"""
from __future__ import annotations

import io
import re
from collections import Counter

from aquaworld_ia.emballage import composition as C

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
#: Au-dessus de ce niveau sur R, G ET B, un pixel opaque du logo est « blanc » (gardé si demandé).
SEUIL_BLANC = 225
#: Un petit PNG est agrandi jusqu'à ce côté (px) avant la vectorisation : les courbes en sont plus justes.
COTE_TRACE = 1600
_PAS_UNE_ENCRE = ("none", "transparent", "inherit")


def normaliser(couleur) -> str | None:
	"""« #1D4ED8 » / « 1d4ed8 » / « #fff » -> « #1d4ed8 » ; None si ce n'est pas une couleur. Pur."""
	c = str(couleur or "").strip().lower()
	if c and not c.startswith("#"):
		c = "#" + c
	if re.match(r"^#[0-9a-f]{3}$", c):
		c = "#" + "".join(x * 2 for x in c[1:])
	return c if HEX.match(c) else None


def _hex(rgb) -> str:
	return "#%02x%02x%02x" % tuple(int(v) for v in rgb[:3])


def svg_vectoriel(octets: bytes) -> bool:
	"""Un SVG fait de formes (recolorable tel quel), pas une image emballée dans un SVG. Pur."""
	return C.est_svg(octets) and not re.search(rb"<image\b", octets, re.IGNORECASE)


def recolorer_svg(svg: bytes, couleur: str, garder_blanc: bool = True) -> bytes:
	"""Toutes les encres du SVG (remplissages, contours, dégradés, feuilles de style) prennent `couleur` ;
	« none », les dégradés appelés par url(#…) et — si demandé — le blanc sont gardés. Une forme sans
	remplissage explicite hérite du noir : la couleur est posée sur la racine. Pur."""
	texte = svg.decode("utf-8", "replace")

	def remplacer(m):
		prefixe, val = m.group(1), m.group(2)
		v = val.strip().lower()
		if not v or v in _PAS_UNE_ENCRE or v.startswith("url("):
			return m.group(0)
		rgb = C._rgb(v)
		if garder_blanc and rgb is not None and min(rgb) >= 235:
			return m.group(0)
		return prefixe + couleur

	texte = re.sub(r"((?:fill|stroke|stop-color)\s*[=:]\s*[\"']?\s*)([^\"';)>}]+)", remplacer, texte)
	racine = re.search(r"<svg\b[^>]*>", texte, re.IGNORECASE)
	if racine and not re.search(r"\sfill\s*=", racine.group(0)):
		texte = texte[:racine.end() - 1].rstrip("/") + ' fill="%s"' % couleur + texte[racine.end() - 1:]
	return texte.encode("utf-8")


def rasteriser_svg(svg: bytes, cote: int = COTE_TRACE) -> bytes:
	"""Un SVG (avec image embarquée, typiquement) -> PNG à fond transparent, `cote` px au plus long."""
	import pymupdf

	doc = pymupdf.open(stream=svg, filetype="svg")
	page = doc[0]
	zoom = cote / max(page.rect.width, page.rect.height, 1)
	return page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=True).tobytes("png")


def _rgba(octets: bytes):
	"""Le logo en tableau RGBA ; une image SANS transparence perd d'abord son fond blanc."""
	import numpy as np
	from PIL import Image

	a = np.array(Image.open(io.BytesIO(octets)).convert("RGBA"))
	if a[..., 3].min() == 255:
		a = np.array(Image.open(io.BytesIO(C.fond_blanc_en_transparence(octets))).convert("RGBA"))
	return a


def _masques(a, garder_blanc: bool, opaque_min: int):
	import numpy as np

	alpha = a[..., 3]
	blanc = ((a[..., :3].min(axis=2) >= SEUIL_BLANC) & (alpha >= 200)) if garder_blanc else np.zeros(alpha.shape, bool)
	encre = (alpha >= opaque_min) & ~blanc
	return encre, blanc


def recolorer_png(octets: bytes, couleur: str, garder_blanc: bool = True) -> bytes:
	"""Chaque pixel visible du logo prend `couleur` (sa transparence est gardée : les bords restent
	lisses) ; le blanc opaque reste blanc si demandé. -> PNG à fond transparent."""
	from PIL import Image

	a = _rgba(octets)
	encre, blanc = _masques(a, garder_blanc, 1)
	a[encre, :3] = [int(couleur[i:i + 2], 16) for i in (1, 3, 5)]
	a[blanc, :3] = 255
	sortie = io.BytesIO()
	Image.fromarray(a, "RGBA").save(sortie, "PNG", optimize=True)
	return sortie.getvalue()


def vectoriser(png: bytes, couleur: str, garder_blanc: bool = True) -> bytes:
	"""PNG -> SVG d'une couleur (+ le blanc gardé) : chaque couche est tracée par vtracer en mode
	binaire (courbes, trous des lettres conservés), puis recolorée."""
	import cv2
	import numpy as np
	import vtracer

	a = _rgba(png)
	h, w = a.shape[:2]
	k = COTE_TRACE / max(h, w)
	if k > 1:
		a = cv2.resize(a, (round(w * k), round(h * k)), interpolation=cv2.INTER_CUBIC)
	encre, blanc = _masques(a, garder_blanc, 128)
	H, W = encre.shape
	chemins = []
	for remplissage, masque in (("#ffffff", blanc), (couleur, encre)):
		if not masque.any():
			continue
		ok, image = cv2.imencode(".png", np.where(masque, 0, 255).astype(np.uint8))
		svg = vtracer.convert_raw_image_to_svg(image.tobytes(), img_format="png", colormode="binary", mode="spline",
		                                       filter_speckle=4, corner_threshold=60, length_threshold=4.0,
		                                       splice_threshold=45, path_precision=2)
		for p in re.findall(r"<path\b[^>]*>", svg):
			chemins.append(re.sub(r'fill="[^"]*"', 'fill="%s"' % remplissage, p))
	return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d">%s</svg>'
	        % (W, H, W, H, "".join(chemins))).encode("utf-8")


def appliquer(octets: bytes, couleur: str, garder_blanc: bool = True, sortie: str = "svg") -> tuple[bytes, str]:
	"""Le logo en une couleur, au format demandé (« svg » ou « png ») -> (octets, extension)."""
	couleur = normaliser(couleur)
	if not couleur:
		raise ValueError("Couleur invalide : choisissez-la dans la palette ou saisissez un code #RRGGBB.")
	sortie = "png" if sortie == "png" else "svg"
	if svg_vectoriel(octets):
		svg = recolorer_svg(octets, couleur, garder_blanc)
		return (svg, "svg") if sortie == "svg" else (rasteriser_svg(svg), "png")
	png = recolorer_png(rasteriser_svg(octets) if C.est_svg(octets) else octets, couleur, garder_blanc)
	return (vectoriser(png, couleur, garder_blanc), "svg") if sortie == "svg" else (png, "png")


def couleurs_logo(octets: bytes, n: int = 6) -> list[str]:
	"""Les encres du logo, la plus employée d'abord (le blanc et le transparent ne comptent pas)."""
	if svg_vectoriel(octets):
		texte = octets.decode("utf-8", "replace")
		comptes = Counter()
		for val in re.findall(r"(?:fill|stroke|stop-color)\s*[=:]\s*[\"']?\s*([^\"';)>}]+)", texte):
			rgb = C._rgb(val)
			if rgb is not None and min(rgb) < 235:
				comptes[_hex(rgb)] += 1
		return [c for c, _n in comptes.most_common(n)]
	from PIL import Image

	a = _rgba(rasteriser_svg(octets, 400) if C.est_svg(octets) else octets)
	encre, _blanc = _masques(a, True, 128)
	pixels = a[encre][:, :3]
	if not len(pixels):
		return []
	im = Image.fromarray(pixels[None, :min(len(pixels), 200000)].astype("uint8"), "RGB")
	pal = im.quantize(colors=n, method=Image.Quantize.MEDIANCUT)
	valeurs = pal.getpalette()
	return [_hex(valeurs[3 * i: 3 * i + 3]) for _nb, i in sorted(pal.getcolors() or [], reverse=True)][:n]


def palette(couleurs: list[tuple[str, str]]) -> list[dict]:
	"""[(couleur, origine)] -> [{couleur, origine}] sans doublon, dans l'ordre reçu. Pur."""
	vues, out = set(), []
	for c, origine in couleurs:
		c = normaliser(c)
		if c and c not in vues:
			vues.add(c)
			out.append({"couleur": c, "origine": origine})
	return out
