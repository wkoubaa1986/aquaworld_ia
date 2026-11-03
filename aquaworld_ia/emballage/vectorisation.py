"""Vectorisation couleur locale : des courbes SVG, sans image bitmap embarquée ni appel IA."""
from __future__ import annotations

import io
import warnings
from xml.etree import ElementTree as ET

from PIL import Image, ImageColor, ImageOps, UnidentifiedImageError

MAX_OCTETS = 20 * 1024 * 1024
MAX_PIXELS = 25_000_000
MAX_COTE = 1600
MAX_CHEMINS = 30_000
MAX_SVG = 10 * 1024 * 1024
PROFILS = {
	"logo": {"couleurs": 16, "speckle": 2, "longueur": 3.5},
	"illustration": {"couleurs": 32, "speckle": 4, "longueur": 4.0},
	"photo": {"couleurs": 64, "speckle": 4, "longueur": 4.0},
}
SVG_NS = "http://www.w3.org/2000/svg"


def vectoriser(octets: bytes, profil: str = "photo", couleurs: int = 64,
               retirer_fond: bool = False) -> tuple[bytes, dict]:
	"""PNG/JPEG/WebP -> SVG couleur et statistiques. Borné pour une requête interactive.

	La palette est calculée sur les pixels visibles uniquement. Les alpha intermédiaires sont
	seuillés : ce tracé convient à une illustration, pas à la conservation exacte d'une photo.
	"""
	from aquaworld_ia.emballage.composition import est_svg, fond_blanc_en_transparence

	if profil not in PROFILS:
		raise ValueError("Choisissez un profil logo, illustration ou photo.")
	if couleurs not in (8, 16, 32, 64, 128):
		raise ValueError("Choisissez 8, 16, 32, 64 ou 128 couleurs.")
	if len(octets) > MAX_OCTETS:
		raise ValueError("Image trop lourde : maximum 20 Mo.")
	if est_svg(octets):
		raise ValueError("Ce fichier est déjà en SVG. Choisissez son original PNG, JPEG ou WebP pour le retracer.")
	try:
		with warnings.catch_warnings():
			warnings.simplefilter("error", Image.DecompressionBombWarning)
			with Image.open(io.BytesIO(octets)) as source:
				if source.format not in ("PNG", "JPEG", "WEBP"):
					raise ValueError("Utilisez une image PNG, JPEG ou WebP.")
				if source.width * source.height > MAX_PIXELS:
					raise ValueError("Image trop grande : maximum 25 mégapixels.")
				im = ImageOps.exif_transpose(source).convert("RGBA")
	except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
		raise ValueError("Image illisible ou trop grande. Utilisez un PNG, JPEG ou WebP valide.") from exc
	largeur, hauteur = im.size
	im.thumbnail((MAX_COTE, MAX_COTE), Image.Resampling.LANCZOS)
	avertissements = []
	if im.size != (largeur, hauteur):
		avertissements.append("Image réduite à 1 600 px au plus long côté pour limiter le poids du SVG.")
	if retirer_fond:
		b = io.BytesIO()
		im.save(b, "PNG")
		im = Image.open(io.BytesIO(fond_blanc_en_transparence(b.getvalue()))).convert("RGBA")
		avertissements.append("Détourage du fond blanc demandé : vérifiez les parties blanches du produit.")
	alpha = im.getchannel("A")
	if sum(alpha.histogram()[1:255]):
		avertissements.append("Les transparences partielles sont simplifiées en contours opaques ou transparents.")
	masque = alpha.point(lambda a: 255 if a >= 128 else 0)
	if not masque.getbbox():
		raise ValueError("Aucune forme visible à vectoriser.")
	# FASTOCTREE ignore la couleur des pixels transparents ; pas de tramage photographique
	# qui multiplierait les minuscules chemins. Une couleur est réservée au transparent.
	im.putalpha(masque)
	palette = im.quantize(colors=couleurs + int(masque.getextrema()[0] == 0),
	                      method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE).convert("RGBA")
	palette.putalpha(masque)
	b = io.BytesIO()
	palette.save(b, "PNG")
	try:
		import vtracer
	except ImportError as exc:
		raise ValueError("La vectorisation nécessite vtracer sur le serveur. Installez les dépendances de l’application.") from exc
	reglage = PROFILS[profil]
	svg = vtracer.convert_raw_image_to_svg(
		b.getvalue(), img_format="png", colormode="color", hierarchical="stacked", mode="spline",
		filter_speckle=reglage["speckle"], color_precision=8, layer_difference=0,
		corner_threshold=60, length_threshold=reglage["longueur"], splice_threshold=45,
		path_precision=2,
	)
	racine = ET.fromstring(svg)
	chemins = list(racine.iter("{%s}path" % SVG_NS))
	if not chemins:
		raise ValueError("Aucun contour trouvé. Essayez une image plus grande ou le profil logo.")
	if len(chemins) > MAX_CHEMINS or len(svg.encode("utf-8")) > MAX_SVG:
		raise ValueError("SVG trop complexe. Réessayez avec moins de couleurs ou une image plus petite.")
	# Le regroupement hiérarchique du traceur calcule des couleurs moyennes supplémentaires.
	# Les ramener à la palette choisie garantit réellement le maximum annoncé dans le studio.
	encres = sorted({rgba[:3] for _, rgba in palette.getcolors(256) if rgba[3]})
	remplacements = {}
	for chemin in chemins:
		fill = chemin.get("fill")
		if fill not in remplacements:
			rgb = ImageColor.getrgb(fill)
			proche = min(encres, key=lambda c: sum((c[i] - rgb[i]) ** 2 for i in range(3)))
			remplacements[fill] = "#%02x%02x%02x" % proche
		chemin.set("fill", remplacements[fill])
	# Le viewBox permet l’agrandissement dans le studio et conserve le cadrage d’origine.
	racine.set("viewBox", "0 0 %d %d" % im.size)
	racine.set("width", str(largeur))
	racine.set("height", str(hauteur))
	ET.register_namespace("", SVG_NS)
	resultat = ET.tostring(racine, encoding="utf-8")
	if profil == "photo":
		avertissements.append("Le SVG est une illustration : les reflets, dégradés et petits détails sont simplifiés.")
	return resultat, {
		"largeur": largeur, "hauteur": hauteur, "chemins": len(chemins),
		"couleurs": len({p.get("fill") for p in chemins}),
		"taille_ko": round(len(resultat) / 1024, 1), "avertissements": avertissements,
	}
