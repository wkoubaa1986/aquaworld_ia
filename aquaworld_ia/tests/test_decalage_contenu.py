import io
import unittest

import pymupdf
from PIL import Image, ImageChops

from aquaworld_ia.emballage import composition as C
from aquaworld_ia.tests.test_rotation_maquette import SVG
from aquaworld_ia.tests.test_centrage_logo import SVG as SVG_MARGES


class TestDecalageContenu(unittest.TestCase):
	def test_bornage_et_copie_de_tous_les_contenus(self):
		face = {"x": 10, "y": 20, "w": 100, "h": 40}
		for type_zone in ("logo", "photo", "nom", "texte_libre", "pictos", "code_barres"):
			z = {"zone": type_zone, "x": 20, "y": 25, "w": 30, "h": 20, "decalage_contenu": {"x": -5, "y": 3}}
			self.assertEqual(C.borner_zone(z, face), z)
			copie = C.translater_zones([z], face, dict(face, x=200))[0]
			self.assertEqual(copie["decalage_contenu"], z["decalage_contenu"])
		for valeur in (None, [], "abc", {"x": "abc", "y": float("nan")}, {"x": float("inf")}):
			self.assertEqual(C.decalage_zone(dict(z, decalage_contenu=valeur)), {"x": 0, "y": 0})
		self.assertEqual(C.decalage_zone(dict(z, decalage_contenu={"x": 999, "y": -999})), {"x": 30, "y": -20})

	def test_photo_et_svg_deplaces_avant_decoupe_meme_avec_zoom_et_rotation(self):
		im = Image.new("RGB", (120, 30), "red"); im.paste("blue", (60, 0, 120, 30))
		buf = io.BytesIO(); im.save(buf, format="PNG")
		for image in (SVG, buf.getvalue()):
			for angle in (0, 37, 90):
				for zoom in (.5, 2, 4):
					with self.subTest(svg=image == SVG, angle=angle, zoom=zoom), pymupdf.open() as pdf:
						page = pdf.new_page(width=300, height=300)
						C.poser_image(page, (120, 120, 180, 180), image, rotation=angle, zoom=zoom,
						              decalage={"x": 12/C.MM(1), "y": -9/C.MM(1)})
						pix = page.get_pixmap()
						self.assertEqual(bool(page.get_images()), image != SVG)
						ref = pdf.new_page(width=300, height=300)
						d = 30*zoom
						C.poser_image(ref, (162-d, 141-d, 162+d, 141+d), image, rotation=angle)
						attendu = ref.get_pixmap()
						for x in range(105, 195, 3):
							for y in range(105, 195, 3):
								couleur = attendu.pixel(x, y) if 120 <= x < 180 and 120 <= y < 180 else (255, 255, 255)
								tolerance = 20 if any(v not in (0, 255) for v in couleur) else 2
								self.assertTrue(all(abs(a-b) <= tolerance for a, b in zip(pix.pixel(x, y), couleur)), (x, y, pix.pixel(x, y), couleur))

	def test_decalage_du_centre_visible_reste_dans_les_axes_de_la_feuille(self):
		for angle in (0, 37, 90, 270):
			with self.subTest(angle=angle), pymupdf.open() as pdf:
				page = pdf.new_page(width=200, height=200)
				C.poser_logo(page, (50, 50, 150, 150), SVG_MARGES, rotation=angle, zoom=1.5,
				             centre={"x": .6, "y": .2}, decalage={"x": 10/C.MM(1), "y": -8/C.MM(1)})
				im = Image.open(io.BytesIO(page.get_pixmap().tobytes("png"))).convert("RGB")
				box = ImageChops.difference(im, Image.new("RGB", im.size, "white")).getbbox()
				self.assertAlmostEqual((box[0]+box[2])/2, 110, delta=1)
				self.assertAlmostEqual((box[1]+box[3])/2, 92, delta=1)

	def test_texte_decale_sans_recomposer_ni_deplacer_le_cartouche(self):
		with pymupdf.open() as pdf:
			page = pdf.new_page(width=300, height=300)
			rect = (50, 50, 180, 130)
			interieur = C.dessiner_cartouche(page, rect, {"fond": "#00ff00"})
			html = '<p style="font-size:12pt;margin:0">Texte de contrôle</p>'
			css = "body {margin:0}"
			scale = C.poser_texte(page, interieur, html, None, css, decalage={"x": 5, "y": 8}, cadre=rect)
			mots = page.get_text("words")
			self.assertTrue(mots)
			ref = pdf.new_page(width=300, height=300)
			self.assertEqual(C.poser_texte(ref, interieur, html, None, css), scale)
			originaux = ref.get_text("words")
			self.assertEqual([m[4] for m in mots], [m[4] for m in originaux])
			for avant, apres in zip(originaux, mots):
				self.assertAlmostEqual(apres[0]-avant[0], C.MM(5), delta=.01)
				self.assertAlmostEqual(apres[1]-avant[1], C.MM(8), delta=.01)
			self.assertEqual(pdf[0].get_pixmap().pixel(51, 51), (0, 255, 0))
			self.assertFalse(pdf[0].get_images())

	def test_symboles_decoupes_au_cadre_et_ancien_qr_adjacent_conserve_a_zero(self):
		rect = C._rect_pt(30, 30, 20, 20)
		el = {"rect": (30, 35, 20, 5), "fond": None, "image": SVG, "logo": False}
		with pymupdf.open() as pdf:
			page = pdf.new_page(width=200, height=200)
			C.poser_symboles(page, [el], rect, {"x": 10, "y": -3})
			pix = page.get_pixmap()
			self.assertEqual(pix.pixel(int(C.MM(42)), int(C.MM(34))), (255, 0, 0))
			self.assertEqual(pix.pixel(int(C.MM(52)), int(C.MM(34))), (255, 255, 255))
			self.assertFalse(page.get_images())
			page = pdf.new_page(width=200, height=200)
			C.poser_symboles(page, [dict(el, rect=(20, 35, 20, 5))], rect, {"x": 0, "y": 0})
			self.assertEqual(page.get_pixmap().pixel(int(C.MM(25)), int(C.MM(37))), (255, 0, 0))
