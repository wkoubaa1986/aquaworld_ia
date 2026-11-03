"""Conversion vectorielle des SVG, y compris leurs fenêtres imbriquées."""
import re


def vers_pdf(svg: bytes):
	import pymupdf

	if len(re.findall(rb"<(?:[\w.-]+:)?svg\b", svg)) > 1:
		# MuPDF ignore le viewBox et la découpe des <svg> internes. CairoSVG
		# conserve ces fenêtres, leurs styles et leurs chemins dans le PDF.
		# unsafe=False n'autorise que les ressources embarquées (data:).
		import cairosvg
		return pymupdf.open("pdf", cairosvg.svg2pdf(bytestring=svg, unsafe=False))
	with pymupdf.open("svg", svg) as source:
		return pymupdf.open("pdf", source.convert_to_pdf())
