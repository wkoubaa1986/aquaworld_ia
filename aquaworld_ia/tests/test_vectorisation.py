"""Le SVG doit conserver les couleurs et les trous, et rester vectoriel dans le PDF."""
import io
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from xml.etree import ElementTree as ET

import pymupdf
from PIL import Image, ImageDraw

from aquaworld_ia.emballage import composition as C
from aquaworld_ia.emballage import studio as S
from aquaworld_ia.emballage import vectorisation as V


def image_test():
	im = Image.new("RGBA", (160, 100), (0, 0, 0, 0))
	dessin = ImageDraw.Draw(im)
	dessin.rectangle((10, 10, 70, 90), fill="#ff0000")
	dessin.rectangle((90, 10, 150, 90), fill="#0000ff")
	dessin.rectangle((25, 30, 55, 70), fill=(0, 0, 0, 0))
	b = io.BytesIO()
	im.save(b, "PNG")
	return b.getvalue()


class TestVectorisation(unittest.TestCase):
	def test_couleurs_transparence_et_vraies_courbes(self):
		svg, info = V.vectoriser(image_test(), "logo", 8)
		racine = ET.fromstring(svg)
		self.assertEqual(racine.get("viewBox"), "0 0 160 100")
		self.assertNotIn(b"<image", svg)
		self.assertNotIn(b"data:", svg)
		self.assertGreater(info["chemins"], 0)
		self.assertLessEqual(info["couleurs"], 8)
		with pymupdf.open(stream=svg, filetype="svg") as doc:
			pix = doc[0].get_pixmap(alpha=True)
			self.assertEqual(pix.pixel(15, 50), (255, 0, 0, 255))
			self.assertEqual(pix.pixel(100, 50), (0, 0, 255, 255))
			self.assertEqual(pix.pixel(40, 50)[3], 0)
			self.assertEqual(pix.pixel(2, 2)[3], 0)

	def test_pdf_garde_les_courbes_et_aucun_bitmap(self):
		svg, _ = V.vectoriser(image_test(), "logo", 8)
		with pymupdf.open() as doc:
			page = doc.new_page(width=320, height=200)
			C.poser_image(page, (0, 0, 320, 200), svg)
			# Relecture du PDF réellement sérialisé, pas seulement de la page en mémoire.
			with pymupdf.open(stream=doc.tobytes(), filetype="pdf") as pdf:
				self.assertEqual(pdf[0].get_images(), [])
				self.assertGreater(len(pdf[0].get_drawings()), 0)
				self.assertEqual(pdf[0].get_pixmap().pixel(30, 100), (255, 0, 0))

	def test_png_reste_une_image_dans_pdf(self):
		with pymupdf.open() as doc:
			page = doc.new_page()
			C.poser_image(page, (0, 0, 160, 100), image_test())
			self.assertEqual(len(page.get_images()), 1)

	def test_les_degrades_respectent_la_limite_de_couleurs(self):
		im = Image.new("RGB", (160, 100))
		im.putdata([(x, y * 2, (x + y) % 256) for y in range(100) for x in range(160)])
		b = io.BytesIO()
		im.save(b, "PNG")
		_, info = V.vectoriser(b.getvalue(), couleurs=8)
		self.assertLessEqual(info["couleurs"], 8)

	def test_reduction_bornee_et_cadrage(self):
		b = io.BytesIO()
		Image.new("RGB", (2000, 1000), "red").save(b, "PNG")
		svg, info = V.vectoriser(b.getvalue())
		root = ET.fromstring(svg)
		self.assertEqual(root.get("viewBox"), "0 0 1600 800")
		self.assertEqual((root.get("width"), root.get("height")), ("2000", "1000"))
		self.assertTrue(any("réduite" in a for a in info["avertissements"]))

	def test_orientation_exif(self):
		im = Image.new("RGB", (120, 80), "red")
		exif = im.getexif()
		exif[274] = 6
		b = io.BytesIO()
		im.save(b, "JPEG", exif=exif)
		_, info = V.vectoriser(b.getvalue())
		self.assertEqual((info["largeur"], info["hauteur"]), (80, 120))

	def test_entrees_invalides_et_limites_avant_tracage(self):
		for octets, options in [
			(b"pas une image", {}), (b"<svg></svg>", {}),
			(image_test(), {"profil": "inconnu"}), (image_test(), {"couleurs": 256}),
		]:
			with self.subTest(options=options), self.assertRaises(ValueError):
				V.vectoriser(octets, **options)
		with patch.object(V, "MAX_PIXELS", 10), self.assertRaisesRegex(ValueError, "mégapixels"):
			V.vectoriser(image_test())
		with patch.object(V, "MAX_OCTETS", 10), self.assertRaisesRegex(ValueError, "20 Mo"):
			V.vectoriser(image_test())

	def test_transparent_vide_refuse(self):
		b = io.BytesIO()
		Image.new("RGBA", (20, 20)).save(b, "PNG")
		with self.assertRaisesRegex(ValueError, "visible"):
			V.vectoriser(b.getvalue())

	def test_fond_blanc_optionnel(self):
		im = Image.new("RGB", (160, 100), "white")
		ImageDraw.Draw(im).rectangle((20, 20, 140, 80), fill="blue")
		b = io.BytesIO()
		im.save(b, "PNG")
		for retirer in (False, True):
			svg, _ = V.vectoriser(b.getvalue(), retirer_fond=retirer)
			with pymupdf.open(stream=svg, filetype="svg") as doc:
				self.assertEqual(doc[0].get_pixmap(alpha=True).pixel(3, 3)[3], 0 if retirer else 255)


class TestAccesImages(unittest.TestCase):
	def test_image_privee_exige_le_droit_sur_le_document_precis(self):
		fichier = SimpleNamespace(attached_to_doctype="Design Emballage", attached_to_name="AUTRE")
		with patch.object(S.frappe, "db", Mock(exists=Mock(return_value=False))), \
				patch.object(S.frappe, "get_all", side_effect=[[fichier], []]), \
				patch.object(S.frappe, "has_permission", return_value=False) as droit, \
				patch.object(S.frappe, "throw", side_effect=PermissionError), patch.object(S, "_", lambda s: s):
			with self.assertRaises(PermissionError):
				S._image_lisible(SimpleNamespace(name="ICI"), "/private/files/autre.png")
			droit.assert_called_once_with("Design Emballage", "read", doc="AUTRE")

	def test_image_autorisee_d_un_autre_document(self):
		fichier = SimpleNamespace(attached_to_doctype="Ressource Emballage", attached_to_name="RESSOURCE")
		with patch.object(S.frappe, "db", Mock(exists=Mock(return_value=False))), \
				patch.object(S.frappe, "get_all", return_value=[fichier]), \
				patch.object(S.frappe, "has_permission", return_value=True) as droit:
			self.assertEqual(S._image_lisible(SimpleNamespace(name="ICI"), "/private/files/a.png"), "/private/files/a.png")
			droit.assert_called_once_with("Ressource Emballage", "read", doc="RESSOURCE")

	def test_adoption_refuse_la_lecture_non_autorisee(self):
		with patch.object(S.frappe, "get_doc", return_value=Mock()), \
				patch.object(S, "_image_lisible", side_effect=PermissionError), \
				patch("aquaworld_ia.ia.fichiers.lire") as lire:
			with self.assertRaises(PermissionError):
				S.adopter_image.__wrapped__("ICI", "photo_produit", "/private/files/interdit.png")
			lire.assert_not_called()

	def test_vectorisation_attache_un_candidat_sans_remplacer_la_photo(self):
		doc = Mock(name="design")
		doc.name = "EMB-2026-0008"
		with patch.object(S.frappe, "get_doc", return_value=doc), \
				patch.object(S, "images_du_design", return_value=[]), \
				patch("aquaworld_ia.emballage.variantes.url_photo", return_value="/files/photo.png"), \
				patch("aquaworld_ia.ia.fichiers.lire", return_value=image_test()), \
				patch("frappe.utils.file_manager.save_file", return_value=SimpleNamespace(file_url="/private/files/resultat.svg")) as sauver:
			resultat = S.vectoriser_image.__wrapped__(doc.name, "photo_produit", couleurs="16")
			doc.check_permission.assert_called_once_with("write")
			doc.save.assert_not_called()
			doc.set.assert_not_called()
			self.assertEqual(resultat["candidat"], "/private/files/resultat.svg")
			self.assertTrue(sauver.call_args.kwargs["is_private"])
			self.assertIn(b"<path", sauver.call_args.args[1])

	def test_vectorise_la_proposition_selectionnee_et_non_la_photo_actuelle(self):
		doc = Mock()
		doc.name = "EMB-2026-0008"
		source = "/private/files/proposition-ia.png"
		with patch.object(S.frappe, "get_doc", return_value=doc), \
				patch.object(S, "images_du_design", return_value=[]), \
				patch.object(S, "_image_lisible", return_value=source) as verifier, \
				patch("aquaworld_ia.emballage.variantes.url_photo", return_value="/files/actuelle.png"), \
				patch("aquaworld_ia.ia.fichiers.lire", return_value=image_test()) as lire, \
				patch("frappe.utils.file_manager.save_file", return_value=SimpleNamespace(file_url="/private/files/resultat.svg")):
			resultat = S.vectoriser_image.__wrapped__(doc.name, "photo_produit", source_url=source)
			verifier.assert_called_once_with(doc, source)
			lire.assert_called_once_with(source)
			self.assertEqual(resultat["source"], source)
			doc.save.assert_not_called()

	def test_une_source_privee_non_autorisee_ne_part_ni_au_traceur_ni_a_l_ia(self):
		for champ in ("logo", "photo_produit"):
			with self.subTest(champ=champ), patch.object(S.frappe, "get_doc", return_value=Mock()), \
					patch.object(S, "_image_lisible", side_effect=PermissionError), \
					patch("aquaworld_ia.emballage.variantes.url_logo", return_value="/files/logo.png"), \
					patch("aquaworld_ia.emballage.variantes.url_photo", return_value="/files/photo.png"), \
					patch("aquaworld_ia.ia.fichiers.lire") as lire, \
					patch("aquaworld_ia.ia.images.editer") as editer:
				with self.assertRaises(PermissionError):
					S.vectoriser_image.__wrapped__("ICI", champ, source_url="/private/files/interdit.png")
				with self.assertRaises(PermissionError):
					S.retoucher_image.__wrapped__("ICI", champ, "Préparer une illustration", source_url="/private/files/interdit.png")
				lire.assert_not_called()
				editer.assert_not_called()


if __name__ == "__main__":
	unittest.main()
