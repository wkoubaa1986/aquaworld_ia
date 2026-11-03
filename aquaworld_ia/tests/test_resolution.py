import io
import math
import unittest
from unittest.mock import Mock, patch

import numpy as np
import pymupdf
from PIL import Image, ImageDraw

from aquaworld_ia.emballage import composition as C, exports, resolution as R
from aquaworld_ia.tests.test_contenus_exports import design


def png(image):
	s = io.BytesIO()
	image.save(s, "PNG")
	return s.getvalue()


class TestResolutionImage(unittest.TestCase):
	def test_fidele_preserve_alpha_couleur_et_proportions(self):
		im = Image.new("RGBA", (32, 16), (0, 0, 0, 0))
		ImageDraw.Draw(im).rectangle((8, 4, 23, 11), fill=(20, 70, 120, 255))
		out, rapport = R.agrandir(png(im), 4)
		resultat = Image.open(io.BytesIO(out))
		self.assertEqual(resultat.size, (128, 64))
		self.assertEqual(resultat.getpixel((0, 0))[3], 0)
		self.assertEqual(resultat.getpixel((64, 32)), (20, 70, 120, 255))
		self.assertEqual(rapport["methode"], "fidele")

	def test_ia_reelle_x2_x4_alpha_et_jointures(self):
		import cv2
		from pathlib import Path
		rng = np.random.default_rng(12)
		im = Image.fromarray(rng.integers(0, 256, (32, 230, 3), dtype=np.uint8))
		for facteur in (2, 4):
			out, _ = R.agrandir(png(im), facteur, "ia")
			actual = np.asarray(Image.open(io.BytesIO(out)))
			sr = cv2.dnn_superres.DnnSuperResImpl_create()
			sr.readModel(str(Path(R.__file__).with_name("modeles_resolution") / f"FSRCNN_x{facteur}.pb"))
			sr.setModel("fsrcnn", facteur)
			expected = sr.upsample(np.asarray(im)[:, :, ::-1].copy())[:, :, ::-1]
			self.assertLessEqual(np.abs(actual.astype(int)-expected).max(), 1)
		im = im.convert("RGBA")
		im.putalpha(Image.new("L", im.size, 128))
		out, _ = R.agrandir(png(im), 2, "ia")
		self.assertEqual(Image.open(io.BytesIO(out)).getchannel("A").getextrema(), (128, 128))

	def test_limites_et_svg(self):
		for facteur, methode in ((3, "ia"), ("nan", "fidele"), (4, "inconnu")):
			with self.assertRaises(ValueError):
				R.agrandir(png(Image.new("RGB", (10, 10))), facteur, methode)
		with patch.object(R, "MAX_PIXELS", 1000), self.assertRaises(ValueError):
			R.agrandir(png(Image.new("RGB", (10, 10))), 4)
		with self.assertRaisesRegex(ValueError, "SVG"):
			R.agrandir(b'<svg xmlns="http://www.w3.org/2000/svg"/>')
		with self.assertRaisesRegex(ValueError, "illisible"):
			R.agrandir(b'not an image')


class TestResolutionPDF(unittest.TestCase):
	def test_ppp_rotation_zoom_et_image_partagee(self):
		with pymupdf.open() as pdf:
			page = pdf.new_page(width=600, height=600)
			source = png(Image.new("RGB", (200, 100), "red"))
			C.poser_image(page, (0, 0, 144, 72), source)
			C.poser_image(page, (200, 0, 488, 144), source, rotation=90, zoom=2)
			infos = R.inventorier(pdf)
			# Le même objet PDF peut être dédoublonné par MuPDF ; toutes les
			# utilisations ont une résolution calculée suivant leurs axes réels.
			for im in page.get_image_info(xrefs=True):
				a,b,c,d,*_ = im["transform"]
				attendu = min(im["width"]*72/math.hypot(a,b),im["height"]*72/math.hypot(c,d))
				self.assertLessEqual(next(x for x in infos if x["xref"] == im["xref"])["ppp_avant"], attendu+.01)
			self.assertAlmostEqual(min(x["ppp_avant"] for x in infos), 50)
			out, rapport = R.preparer_pdf(pdf.tobytes())
			self.assertTrue(rapport["insuffisantes"])
			with pymupdf.open(stream=out, filetype="pdf") as apres:
				self.assertAlmostEqual(min(x["ppp_avant"] for x in R.inventorier(apres)), 200)

	def test_transparence_vecteurs_texte_calques_et_geometry_preserves(self):
		with pymupdf.open() as pdf:
			page = pdf.new_page(width=300, height=200)
			ocg = pdf.add_ocg("Découpe et plis")
			page.draw_rect((0,0,300,200), color=(0,0,1), fill=(0,0,1), oc=ocg)
			page.insert_text((10,20), "TEXTE VECTORIEL")
			im = Image.new("RGBA", (32,16), (0,0,0,0))
			ImageDraw.Draw(im).rectangle((8,4,23,11),fill=(220,40,30,255))
			C.poser_image(page,(20,50,164,122),png(im))
			avant = page.get_image_info(xrefs=True)[0]["transform"]
			out, rapport = R.preparer_pdf(pdf.tobytes())
			with pymupdf.open(stream=out,filetype="pdf") as apres:
				p = apres[0]
				self.assertIn("TEXTE VECTORIEL",p.get_text())
				self.assertEqual(len(p.get_drawings()), 1)
				self.assertEqual(list(apres.get_ocgs().values())[0]["name"],"Découpe et plis")
				self.assertEqual(p.get_image_info(xrefs=True)[0]["transform"],avant)
				image = Image.open(io.BytesIO(p.get_pixmap().tobytes("png")))
				self.assertEqual(image.getpixel((22,52)),(0,0,255))
				self.assertEqual(image.getpixel((92,86)),(220,40,30))
			self.assertEqual(rapport["ameliorees"],1)

	def test_images_integrees_aux_svg_et_vecteurs_purs(self):
		import base64
		src = base64.b64encode(png(Image.new("RGB", (100,50), "red"))).decode()
		svg = f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="200" height="100"><rect width="200" height="100" fill="blue"/><image xlink:href="data:image/png;base64,{src}" width="100" height="50"/></svg>'.encode()
		with pymupdf.open() as pdf:
			p = pdf.new_page(width=300,height=200)
			C.poser_svg(p,(0,0,200,100),svg)
			out,r = R.preparer_pdf(pdf.tobytes())
			self.assertEqual(r["ameliorees"],1)
			with pymupdf.open(stream=out,filetype="pdf") as apres:
				self.assertTrue(apres[0].get_drawings())
		with pymupdf.open() as pdf:
			pdf.new_page().insert_text((20,20), "Pur texte")
			_,r = R.preparer_pdf(pdf.tobytes())
			self.assertEqual(r["images"],[])

	def test_budget_et_images_deja_suffisantes(self):
		with pymupdf.open() as pdf:
			p=pdf.new_page()
			p.insert_image((0,0,72,72),stream=png(Image.new("RGB",(400,400),"red")))
			p.insert_image((72,0,144,72),stream=png(Image.new("RGB",(100,100),"blue")))
			with patch.object(R,"MAX_PIXELS_PDF",45000):
				_,r=R.preparer_pdf(pdf.tobytes())
			self.assertEqual([x["facteur"] for x in r["images"]],[1,2])
			self.assertEqual(r["insuffisantes"],1)
			self.assertIn("Limite",r["images"][1]["motif"])

	def test_option_export_perime_pdf_et_3d(self):
		d = design(plan_a_plat="/files/plan.pdf",apercu_3d="/files/3d.png",ameliorer_images_pdf=0)
		d.empreinte_plan=d.empreinte_3d=exports.empreinte(d)
		d.ameliorer_images_pdf=1
		self.assertEqual(exports.etat(d)["pdf"],"a_regenerer")
		self.assertFalse(exports.etat(d)["simulation_a_jour"])


class TestAdoptionResolution(unittest.TestCase):
	def test_adoption_logo_preserve_centrage_sans_modifier_les_logos_propres(self):
		import json
		import frappe
		from aquaworld_ia.emballage import studio
		zone={"zone":"logo","rotation":90,"zoom_image":2,"centre_visuel":{"source":"/source.png","x":.4,"y":.3}}
		doc=design(logo="/source.png",modified="v1",mise_en_page=json.dumps({"avant":[zone,dict(zone,logo="/source.png")]}))
		doc.check_permission=Mock();doc.save=Mock()
		with patch.object(R.frappe,"get_doc",return_value=doc), patch.object(R.frappe,"db",Mock()), \
			patch("aquaworld_ia.ia.fichiers.lire",return_value=png(Image.new("RGBA",(20,10),"red"))), \
			patch.object(studio,"charger",return_value={}):
			R.adopter_image.__wrapped__("TEST","logo","/candidat.png","/source.png","v1")
		zones=json.loads(doc.mise_en_page)["avant"]
		self.assertEqual(doc.logo,"/candidat.png")
		self.assertEqual(zones[0]["centre_visuel"],{"source":"/candidat.png","x":.4,"y":.3})
		self.assertEqual(zones[0]["rotation"],90)
		self.assertEqual(zones[0]["zoom_image"],2)
		self.assertEqual(zones[1]["centre_visuel"]["source"],"/source.png")
		doc.save.assert_called_once()

	def test_export_concurrent_ne_publie_pas_un_pdf_perime(self):
		import frappe
		doc=design(modified="v1",plan_a_plat="/ancien.pdf")
		doc.check_permission=Mock()
		for revision, pdf in (("v2","/ancien.pdf"),("v1","/concurrent.pdf")):
			with patch.object(C.frappe,"get_doc",return_value=doc),patch.object(C,"plan_du_design",return_value={}), \
				patch.object(C.geometrie,"verifier",return_value=[]),patch.object(C,"_langues",return_value={}), \
				patch.object(C,"composer",return_value=b"pdf"),patch.object(C,"save_file") as sauver, \
				patch.object(C.frappe,"db",Mock()) as db,patch.object(C.frappe,"throw",side_effect=ValueError) as erreur,patch.object(C,"_",lambda s:s):
				db.get_value.return_value=frappe._dict(modified=revision,plan_a_plat=pdf)
				with self.assertRaises(ValueError):
					C.composer_et_attacher.__wrapped__("TEST")
				self.assertIn("changé", erreur.call_args.args[0])
				sauver.assert_not_called()

	def test_candidat_obsolete_ou_etranger_refuse(self):
		doc=Mock(modified="v2",photo_produit="/source.png")
		with patch.object(R.frappe,"get_doc",return_value=doc), patch.object(R.frappe,"throw",side_effect=ValueError):
			with self.assertRaises(ValueError):
				R.adopter_image.__wrapped__("TEST","photo_produit","/candidat.png","/source.png","v1")
			with patch.object(R.frappe,"db",Mock()) as db:
				db.exists.return_value=False
				with self.assertRaises(ValueError):
					R.adopter_image.__wrapped__("TEST","photo_produit","/candidat.png","/source.png","v2")
		doc.check_permission.assert_called_with("write")
		doc.save.assert_not_called()
