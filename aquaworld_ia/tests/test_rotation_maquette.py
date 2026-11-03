import io
import unittest
from unittest.mock import Mock, patch

import pymupdf
from PIL import Image, ImageDraw

from aquaworld_ia.emballage import composition as C, mockup as M


SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="120" height="30" viewBox="0 0 120 30"><rect width="60" height="30" fill="#ff0000"/><rect x="60" width="60" height="30" fill="#0000ff"/></svg>'


class TestRotation(unittest.TestCase):
	def test_zoom_borne_conserve_et_independant_du_cadre(self):
		face = {"x": 10, "y": 20, "w": 100, "h": 40}
		z = {"zone": "logo", "x": 20, "y": 25, "w": 30, "h": 20, "zoom_image": 2.5, "rotation": 37}
		borne = C.borner_zone(z, face)
		self.assertEqual(borne, z)
		self.assertEqual(C.translater_zones([borne], face, dict(face, x=200))[0]["zoom_image"], 2.5)
		for valeur, attendu in ((None, 1), ("", 1), ("abc", 1), (float("inf"), 1), (float("nan"), 1), (0, .25), (10, 4)):
			self.assertEqual(C.zoom_zone(dict(z, zoom_image=valeur)), attendu)
		self.assertEqual(C.zoom_zone(dict(z, zone="nom")), 1)

	def test_zoom_decoupe_svg_et_photo_au_cadre_apres_rotation(self):
		im = Image.new("RGBA", (120, 30), "red")
		ImageDraw.Draw(im).rectangle((60, 0, 120, 30), fill="blue")
		buffer = io.BytesIO(); im.save(buffer, format="PNG")
		for image in (SVG, buffer.getvalue()):
			for angle in (0, 37, 90):
				for zoom in (.5, 2, 4):
					with self.subTest(svg=image == SVG, angle=angle, zoom=zoom), pymupdf.open() as pdf:
						page = pdf.new_page(width=300, height=300)
						C.poser_image(page, (120, 120, 180, 180), image, rotation=angle, zoom=zoom)
						pix = page.get_pixmap()
						self.assertEqual(bool(page.get_images()), image != SVG)
						# Référence : la même image dans un rectangle agrandi, puis masquée au cadre.
						ref = pdf.new_page(width=300, height=300)
						d = 30 * zoom
						C.poser_image(ref, (150-d, 150-d, 150+d, 150+d), image, rotation=angle)
						attendu = ref.get_pixmap()
						for x in range(105, 195, 3):
							for y in range(105, 195, 3):
								couleur = attendu.pixel(x, y) if 120 <= x < 180 and 120 <= y < 180 else (255, 255, 255)
								# Les deux matrices PDF arrondissent différemment l'anticrénelage des diagonales.
								tolerance = 16 if any(c not in (0, 255) for c in couleur) else 2
								self.assertTrue(all(abs(a-b) <= tolerance for a, b in zip(pix.pixel(x, y), couleur)), (x, y))

	def test_angle_normalise_et_conserve_apres_bornage_et_copie(self):
		face = {"x": 10, "y": 20, "w": 100, "h": 40}
		z = {"zone": "logo", "x": -10, "y": -20, "w": 10, "h": 30, "rotation": -90}
		borne = C.borner_zone(z, face)
		self.assertEqual(borne["rotation"], 270)
		copie = C.translater_zones([borne], face, dict(face, x=200))[0]
		self.assertEqual(copie["rotation"], 270)
		self.assertEqual(copie["x"], 200)
		for angle in ("abc", float("nan"), float("inf")):
			self.assertEqual(C.rotation_zone(dict(z, rotation=angle)), 0)
		self.assertEqual(C.rotation_zone(dict(z, rotation=450)), 90)

	def test_svg_vertical_reste_vectoriel_et_tourne_dans_le_sens_horaire(self):
		with pymupdf.open() as pdf:
			p = pdf.new_page(width=150, height=150)
			C.poser_logo(p, (20, 10, 50, 130), SVG, rotation=90)
			pix = p.get_pixmap()
			self.assertEqual(pix.pixel(35, 25), (255, 0, 0))
			self.assertEqual(pix.pixel(35, 110), (0, 0, 255))
			self.assertEqual(p.get_images(), [])
			self.assertTrue(p.get_drawings())

	def test_photo_verticale_et_angle_libre_restent_dans_le_cadre(self):
		im = Image.new("RGB", (120, 30), "red")
		ImageDraw.Draw(im).rectangle((60, 0, 120, 30), fill="blue")
		buffer = io.BytesIO(); im.save(buffer, format="PNG")
		with pymupdf.open() as pdf:
			p = pdf.new_page(width=150, height=150)
			C.poser_image(p, (20, 10, 50, 130), buffer.getvalue(), rotation=90)
			self.assertEqual(p.get_pixmap().pixel(35, 25), (255, 0, 0))
			self.assertEqual(p.get_pixmap().pixel(35, 110), (0, 0, 255))
			p = pdf.new_page(width=150, height=150)
			C.poser_image(p, (20, 20, 130, 130), buffer.getvalue(), rotation=37)
			self.assertTrue(p.get_images())
			for _type, box in p.get_bboxlog():
				self.assertGreaterEqual(box[0], 19.9)
				self.assertGreaterEqual(box[1], 19.9)
				self.assertLessEqual(box[2], 130.1)
				self.assertLessEqual(box[3], 130.1)


class TestTextures3D(unittest.TestCase):
	def test_textures_sans_decoupe_et_resolution_bornee(self):
		with pymupdf.open() as pdf:
			p = pdf.new_page(width=100, height=200)
			p.draw_rect(p.rect, color=None, fill=(0, 0, 1))
			calque = pdf.add_ocg("Découpe et plis", on=True)
			p.draw_rect(p.rect, color=None, fill=(1, 0, 0), oc=calque)
			source = pdf.tobytes()
		plan = {"faces": [{"code": "avant", "x": 0, "y": 0, "w": 100 * 25.4 / 72, "h": 200 * 25.4 / 72}]}
		textures = M.faces_rendues(source, plan, codes=("avant", "arriere"), max_pixels=100)
		self.assertEqual([code for code, _ in textures], ["avant"])
		im = Image.open(io.BytesIO(textures[0][1]))
		self.assertLessEqual(max(im.size), 101)
		self.assertEqual(im.getpixel((10, 10)), (0, 0, 255))
		with pymupdf.open("pdf", source) as original:
			self.assertEqual(original[0].get_pixmap().pixel(10, 10), (255, 0, 0))

	def test_permission_verifiee_avant_lecture_du_pdf(self):
		doc = Mock()
		doc.check_permission.side_effect = PermissionError
		with patch.object(M.frappe, "get_doc", return_value=doc), patch.object(M.fichiers, "lire") as lire:
			with self.assertRaises(PermissionError):
				M.apercu_interactif.__wrapped__("INTERDIT")
			lire.assert_not_called()


if __name__ == "__main__":
	unittest.main()
