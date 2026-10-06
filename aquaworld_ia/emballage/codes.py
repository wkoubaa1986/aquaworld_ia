"""EAN-13 et QR en SVG (vectoriels, posés tels quels sur le plan à plat)."""

from __future__ import annotations

import re


def valider_ean13(code: str) -> bool:
	"""13 chiffres et clé de contrôle exacte. Pur."""
	c = re.sub(r"\D", "", code or "")
	if len(c) != 13:
		return False
	somme = sum(int(ch) * (1 if i % 2 == 0 else 3) for i, ch in enumerate(c[:12]))
	return (10 - somme % 10) % 10 == int(c[12])


def cle_ean13(douze: str) -> str:
	c = re.sub(r"\D", "", douze or "")[:12]
	somme = sum(int(ch) * (1 if i % 2 == 0 else 3) for i, ch in enumerate(c))
	return str((10 - somme % 10) % 10)


def ean13_svg(code: str) -> bytes:
	"""-> SVG d'un EAN-13 (zone de silence et chiffres inclus). Le code doit être valide."""
	import barcode
	from barcode.writer import SVGWriter

	c = re.sub(r"\D", "", code or "")
	if not valider_ean13(c):
		raise ValueError("EAN-13 invalide : %r" % code)
	ean = barcode.get("ean13", c[:12], writer=SVGWriter())
	return ean.render({"module_width": 0.33, "module_height": 22.0, "quiet_zone": 3.0,
	                   "font_size": 8, "text_distance": 3.0, "write_text": True})


#: Contraste minimal (rapport WCAG) entre l'encre du QR et le blanc de son cartouche : en dessous, un
#: téléphone le lit mal (jaune, orange clair, pastel).
CONTRASTE_QR_MIN = 3.0
NOIR = "#000000"


def _luminance(couleur: str) -> float:
	r, g, b = (int(couleur[i:i + 2], 16) / 255 for i in (1, 3, 5))
	lin = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in (r, g, b)]
	return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def normaliser_couleur(couleur) -> str | None:
	"""« #1D4ED8 » / « 1d4ed8 » / « #fff » -> « #1d4ed8 » ; None si ce n'est pas une couleur. Pur."""
	c = str(couleur or "").strip().lower()
	if c and not c.startswith("#"):
		c = "#" + c
	if re.match(r"^#[0-9a-f]{3}$", c):
		c = "#" + "".join(x * 2 for x in c[1:])
	return c if re.match(r"^#[0-9a-f]{6}$", c) else None


def contraste_sur_blanc(couleur: str) -> float:
	"""Rapport de contraste WCAG entre `couleur` et le blanc (1 à 21). Pur."""
	c = normaliser_couleur(couleur)
	return 1.0 if not c else 1.05 / (_luminance(c) + 0.05)


def couleur_qr(couleur) -> str:
	"""La couleur d'encre du QR (demande utilisateur 06/10/2026 : « la couleur du QR, je peux la
	choisir ») : celle demandée si elle se scanne sur le cartouche blanc, le noir sinon. Pur."""
	c = normaliser_couleur(couleur)
	return c if c and contraste_sur_blanc(c) >= CONTRASTE_QR_MIN else NOIR


def qr_svg(contenu: str, couleur: str | None = None) -> bytes:
	"""-> SVG d'un QR (correction M), dans la couleur demandée (noir par défaut ou si trop clair)."""
	import segno

	qr = segno.make(contenu or "", error="m")
	return qr.svg_inline(scale=4, border=2, dark=couleur_qr(couleur)).encode("utf-8")
