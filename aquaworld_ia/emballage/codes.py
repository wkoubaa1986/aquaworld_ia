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


def qr_svg(contenu: str) -> bytes:
	"""-> SVG d'un QR (correction M)."""
	import segno

	qr = segno.make(contenu or "", error="m")
	return qr.svg_inline(scale=4, border=2).encode("utf-8")
