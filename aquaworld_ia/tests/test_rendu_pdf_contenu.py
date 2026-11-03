"""Régressions de parité navigateur/PDF : bitmap carré et SVG à fenêtres imbriquées."""
import io
import base64
import math
import unittest
from unittest.mock import patch

import pymupdf
from PIL import Image, ImageChops

from aquaworld_ia.emballage import composition as C, centrage, exports
from aquaworld_ia.tests.test_contenus_exports import design


def png(im):
	sortie = io.BytesIO()
	im.save(sortie, "PNG")
	return sortie.getvalue()


def encre(page):
	im = Image.open(io.BytesIO(page.get_pixmap().tobytes("png"))).convert("RGB")
	return ImageChops.difference(im, Image.new("RGB", im.size, "white")).getbbox()


def svg_interne(contenu, **attributs):
	attrs = " ".join('%s="%s"' % (k, v) for k, v in attributs.items())
	return ('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200" viewBox="0 0 400 200">'
	        '<svg x="50" y="30" width="200" height="80" viewBox="10 20 100 100" %s>%s</svg></svg>'
	        % (attrs, contenu)).encode()


class TestRenduPDFContenu(unittest.TestCase):
	def assertEncre(self, page, attendu):
		# La conversion px -> pt -> px peut ajouter une frange d'anticrénelage de 1 px.
		for a, b in zip(encre(page), attendu):
			self.assertAlmostEqual(a, b, delta=1)

	def test_bitmap_carre_garde_ses_proportions_dans_une_zone_rectangulaire(self):
		for alpha in (False, True):
			for taille in ((100, 100), (200, 100), (100, 200)):
				with self.subTest(alpha=alpha, taille=taille), pymupdf.open() as pdf:
					page = pdf.new_page(width=500, height=200)
					image = png(Image.new("RGBA" if alpha else "RGB", taille, "blue"))
					C.poser_image(page, (20, 30, 420, 110), image)
					w, h = taille
					k = min(400/w, 80/h)
					attendu = (220-w*k/2, 70-h*k/2, 220+w*k/2, 70+h*k/2)
					for a, b in zip(page.get_image_info()[0]["bbox"], attendu):
						self.assertAlmostEqual(a, b, places=3)

	def test_fond_peut_toujours_remplir_la_zone_sans_garder_les_proportions(self):
		with pymupdf.open() as pdf:
			page = pdf.new_page(width=500, height=200)
			C.poser_image(page, (20, 30, 420, 110), png(Image.new("RGB", (100, 100), "blue")), garder_proportions=False)
			self.assertEqual(encre(page), (20, 30, 420, 110))

	def test_logo_carre_transparent_zoom_rotation_et_decalage(self):
		im = Image.new("RGBA", (100, 100))
		im.paste("blue", (10, 35, 90, 55))
		for angle in (0, 37, 90):
			for centre in (None, {"x": .5, "y": .5}):
				with self.subTest(angle=angle, centre=centre), pymupdf.open() as pdf:
					page = pdf.new_page(width=500, height=450)
					C.poser_image(page, (40, 50, 440, 350), png(im), zoom=1.3, rotation=angle,
					              centre=centre, decalage={"x": 5, "y": -2})
					c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
					k = min(400/(100*(abs(c)+abs(s))), 300/(100*(abs(c)+abs(s))))*1.3
					coins = [(240+C.MM(5)+k*(c*x-s*y), 200-C.MM(2)+k*(s*x+c*y)) for x in (-40, 40) for y in (-15, 5)]
					attendu = (min(x for x, y in coins), min(y for x, y in coins), max(x for x, y in coins), max(y for x, y in coins))
					attendu = (max(40, attendu[0]), max(50, attendu[1]), min(440, attendu[2]), min(350, attendu[3]))
					for a, b in zip(encre(page), attendu):
						self.assertAlmostEqual(a, b, delta=1.5)

	def test_viewbox_interne_decale_avec_alignement_et_decoupe(self):
		for align, attendu in (("xMidYMid meet", (110, 30, 190, 110)), ("xMaxYMin meet", (170, 30, 250, 110)),
		                       ("none", (50, 30, 250, 110)), ("xMidYMid slice", (50, 30, 250, 110))):
			svg = svg_interne('<path d="M10 20h100v100H10z" fill="blue"/>', preserveAspectRatio=align)
			with self.subTest(align=align), pymupdf.open() as pdf:
				page = pdf.new_page(width=400, height=200)
				C.poser_svg(page, (0, 0, 400, 200), svg)
				self.assertEncre(page, attendu)
				self.assertTrue(page.get_drawings())
				self.assertFalse(page.get_images(), "Les chemins doivent rester vectoriels")

	def test_svg_imbriques_pourcentages_et_transformations_conserves(self):
		svg = b'''<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200" viewBox="0 0 400 200">
		<g transform="translate(10 5)"><svg x="10%" y="10%" width="50%" height="50%" viewBox="0 0 100 50">
		<svg x="25%" y="20%" width="50%" height="60%" viewBox="0 0 50 30" fill="blue">
		<rect width="100%" height="100%"/></svg></svg></g></svg>'''
		with pymupdf.open() as pdf:
			page = pdf.new_page(width=400, height=200)
			C.poser_svg(page, (0, 0, 400, 200), svg)
			self.assertEncre(page, (100, 45, 200, 105))
			self.assertFalse(page.get_images())

	def test_overflow_visible_et_styles_du_groupe_preserves(self):
		svg = svg_interne('<rect x="0" y="10" width="120" height="120"/>', style="fill:blue;overflow:visible")
		with pymupdf.open() as pdf:
			page = pdf.new_page(width=400, height=200)
			C.poser_svg(page, (0, 0, 400, 200), svg)
			self.assertEncre(page, (102, 22, 198, 118))

	def test_svg_hybride_garde_image_embarquee_et_chemins_vectoriels(self):
		image = base64.b64encode(png(Image.new("RGB", (20, 20), "red"))).decode()
		svg = svg_interne('<image xmlns:xlink="http://www.w3.org/1999/xlink" x="10" y="20" width="20" height="20" '
		                  'xlink:href="data:image/png;base64,%s"/><path d="M50 60h20v20H50z" fill="blue"/>' % image)
		with C.svg_vers_pdf(svg) as pdf:
			self.assertEqual(len(pdf[0].get_images()), 1)
			self.assertTrue(any(d.get("fill") == (0, 0, 1) for d in pdf[0].get_drawings()))
			im = Image.open(io.BytesIO(pdf[0].get_pixmap().tobytes("png"))).convert("RGB")
			couleurs = {c for n, c in im.getcolors(im.width * im.height)}
			self.assertIn((255, 0, 0), couleurs)
			self.assertIn((0, 0, 255), couleurs)

	def test_centrage_mesure_le_meme_svg_que_le_navigateur(self):
		svg = svg_interne('<rect x="10" y="20" width="100" height="100" fill="blue"/>')
		mesure = centrage.detecter_contenu(svg)
		self.assertAlmostEqual(mesure["x"], 150/400, places=3)
		self.assertAlmostEqual(mesure["y"], 70/200, places=3)
		for angle in (0, 37, 90):
			with self.subTest(angle=angle), pymupdf.open() as pdf:
				page = pdf.new_page(width=240, height=240)
				C.poser_image(page, (20, 20, 220, 220), svg, centre=mesure, zoom=1.4, rotation=angle,
				              decalage={"x": 5, "y": -2})
				box = encre(page)
				self.assertAlmostEqual((box[0]+box[2])/2, 120+C.MM(5), delta=1)
				self.assertAlmostEqual((box[1]+box[3])/2, 120-C.MM(2), delta=1)
				self.assertFalse(page.get_images())

	def test_svg_sans_imbrication_inchange(self):
		svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 337 820 350"><path d="M0 337h820v350H0z"/></svg>'
		with C.svg_vers_pdf(svg) as pdf, pymupdf.open("svg", svg) as original:
			self.assertEqual(pdf[0].rect, original[0].rect)
			self.assertEqual(pdf[0].get_pixmap().samples, original[0].get_pixmap().samples)

	def test_correction_moteur_perime_les_pdf_et_simulations_precedents(self):
		d = design(plan_a_plat="plan.pdf", apercu_3d="3d.png")
		with patch.object(exports, "VERSION_RENDU", exports.VERSION_RENDU-1):
			d.empreinte_plan = d.empreinte_3d = exports.empreinte(d)
		self.assertEqual(exports.etat(d), {"pdf": "a_regenerer", "simulation_a_jour": False})
		d.empreinte_plan = exports.empreinte(d)
		self.assertEqual(exports.etat(d), {"pdf": "a_jour", "simulation_a_jour": False})
