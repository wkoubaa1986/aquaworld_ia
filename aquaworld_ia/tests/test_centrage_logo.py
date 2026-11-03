import io
import unittest
from unittest.mock import Mock, patch

import pymupdf
from PIL import Image, ImageDraw, ImageChops

from aquaworld_ia.emballage import centrage as D, composition as C


SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100" viewBox="0 0 200 100"><rect width="200" height="100" fill="white"/><rect x="80" y="10" width="80" height="20" fill="#0000ff"/></svg>'


def bitmap(fond="white", encre="blue"):
	im = Image.new("RGBA", (200, 100), fond)
	ImageDraw.Draw(im).rectangle((80, 10, 159, 29), fill=encre)
	f = io.BytesIO(); im.save(f, "PNG")
	return f.getvalue()


class TestDetection(unittest.TestCase):
	def test_marges_asymetriques_svg_png_blanc_et_transparent(self):
		for octets in (SVG, bitmap(), bitmap((0, 0, 0, 0))):
			mesure = D.detecter_contenu(octets)
			self.assertAlmostEqual(mesure["x"], .6, places=2)
			self.assertAlmostEqual(mesure["y"], .2, places=2)
			self.assertEqual(mesure["limites"], [.4, .1, .8, .3])

	def test_encre_blanche_sur_transparent_et_fond_colore_sont_conserves(self):
		mesure = D.detecter_contenu(bitmap((255, 255, 255, 0), "white"))
		self.assertEqual((mesure["x"], mesure["y"]), (.6, .2))
		self.assertFalse(mesure["fond_blanc"])
		mesure = D.detecter_contenu(bitmap("navy", "white"))
		self.assertEqual(mesure["limites"], [0, 0, 1, 1])

	def test_images_vides_invalides_ou_trop_lourdes_ne_donnent_pas_un_faux_centre(self):
		for octets in (bitmap("white", "white"), bitmap((0, 0, 0, 0), (0, 0, 0, 0)), b"illisible"):
			with self.assertRaises(ValueError):
				D.detecter_contenu(octets)
		with patch.object(D, "MAX_OCTETS", 10), self.assertRaises(ValueError):
			D.detecter_contenu(SVG)

	def test_permission_verifiee_avant_lecture_du_fichier(self):
		doc = Mock(); doc.check_permission.side_effect = PermissionError
		with patch.object(D.frappe, "get_doc", return_value=doc), patch("aquaworld_ia.ia.fichiers.lire") as lire:
			with self.assertRaises(PermissionError):
				D.analyser_logo.__wrapped__("INTERDIT", "avant", 0)
			lire.assert_not_called()


class TestCentragePdf(unittest.TestCase):
	def test_centre_valide_seulement_pour_sa_source_et_conserve_sur_une_copie(self):
		centre = {"x": .6, "y": .2, "source": "/logo.svg"}
		z = {"zone": "logo", "x": 10, "y": 10, "w": 60, "h": 20, "centre_visuel": centre}
		f = {"x": 0, "y": 0, "w": 100, "h": 100}
		borne = C.borner_zone(z, f)
		self.assertEqual(borne["centre_visuel"], centre)
		self.assertEqual(C.translater_zones([borne], f, dict(f, x=100))[0]["centre_visuel"], centre)
		self.assertEqual(C.centre_zone(z, "/logo.svg"), centre)
		self.assertIsNone(C.centre_zone(z, "/autre.svg"))
		for mauvais in ({}, {"x": float("nan"), "y": .2, "source": "/logo.svg"}, {"x": 2, "y": .2, "source": "/logo.svg"}):
			self.assertIsNone(C.centre_zone(dict(z, centre_visuel=mauvais)))

	def test_encre_centree_apres_rotation_et_zoom_svg_reste_vectoriel(self):
		for octets in (SVG, bitmap()):
			centre = D.detecter_contenu(octets)
			for angle in (0, 37, 90, 180, 270):
				for zoom in (.5, 1, 1.5):
					with self.subTest(svg=octets == SVG, angle=angle, zoom=zoom), pymupdf.open() as pdf:
						page = pdf.new_page(width=200, height=200)
						C.poser_logo(page, (50, 50, 150, 150), octets, rotation=angle, zoom=zoom, centre=centre)
						pix = page.get_pixmap()
						im = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
						box = ImageChops.difference(im, Image.new("RGB", im.size, "white")).getbbox()
						self.assertIsNotNone(box)
						self.assertAlmostEqual((box[0]+box[2])/2, 100, delta=1)
						self.assertAlmostEqual((box[1]+box[3])/2, 100, delta=1)
						self.assertEqual(bool(page.get_images()), octets != SVG)
						self.assertGreaterEqual(box[0], 50); self.assertLessEqual(box[2], 150)
						self.assertGreaterEqual(box[1], 50); self.assertLessEqual(box[3], 150)
