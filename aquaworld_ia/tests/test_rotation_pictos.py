"""Chaque pictogramme tourne dans son propre emplacement, avec le même angle dans le PDF."""
import io
import unittest
from unittest.mock import patch

import frappe
import pymupdf
from PIL import Image, ImageDraw

from aquaworld_ia.emballage import composition as C, apercu_elements as A


SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 30"><rect width="60" height="30" fill="#ff0000"/><rect x="60" width="60" height="30" fill="#0000ff"/></svg>'


class TestRotationPictos(unittest.TestCase):
	def test_angles_normalises_et_conserves_par_zone_et_copie(self):
		f = dict(x=0, y=0, w=140, h=355)
		z = dict(zone="pictos", x=10, y=20, w=60, h=30, pictos_rotations={
			"ce": -90, "tampon": "397.25", "tour": 720, "arrondi": 359.9999,
			"vide": "", "nul": None, "booleen": True, "inf": float("inf"), "nan": float("nan"), "liste": [],
		}, pictos_images={"ce": "/files/couleur.svg"}, decalage_contenu={"x": 2, "y": -1})
		attendu = {"ce": 270, "tampon": 37.25}
		self.assertEqual(C.rotations_pictos(z), attendu)
		borne = C.borner_zone(z, f)
		self.assertEqual(borne["pictos_rotations"], attendu)
		self.assertEqual(borne["pictos_images"], z["pictos_images"])
		self.assertEqual(borne["decalage_contenu"], z["decalage_contenu"])
		self.assertEqual(C.translater_zones([borne], f, dict(f, x=200))[0]["pictos_rotations"], attendu)
		self.assertNotIn("pictos_rotations", C.borner_zone(dict(z, zone="code_barres"), f))
		for invalide in ([], "90", 90, None):
			self.assertEqual(C.rotations_pictos(dict(z, pictos_rotations=invalide)), {})

	def test_angle_individuel_compatible_avec_couleur_selection_et_colonne(self):
		z = dict(zone="pictos", x=10, y=10, w=30, h=100, pictos_disposition="vertical",
			pictos_rotations={"ce": 45, "tampon": 90}, pictos_images={"tampon": "/variante.svg"}, pictos=["ce", "tampon"])
		catalogue = [("ce", SVG), ("tampon", SVG), ("eau", SVG)]
		for disposition in ("horizontal", "vertical"):
			e = C.elements_symboles(dict(z, pictos_disposition=disposition), "avant", pictos_svg=catalogue,
				tampons={"tampon"}, images_pictos={"/variante.svg": SVG.replace(b"#ff0000", b"#008bcd")})
			self.assertEqual([s["code"] for s in e], ["ce", "tampon"])
			self.assertEqual([s["rotation"] for s in e], [45, 90])
			self.assertIn(b"#008bcd", e[1]["image"])
			self.assertFalse(e[1]["logo"])
			neutres = C.elements_symboles(dict(z, pictos_disposition=disposition, pictos_rotations={}), "avant", pictos_svg=catalogue)
			self.assertEqual([s["rect"] for s in e], [s["rect"] for s in neutres])
			self.assertTrue(all("rotation" not in s for s in neutres))

	def test_pdf_svg_et_png_tournent_dans_le_sens_horaire_un_par_un(self):
		im = Image.new("RGB", (120, 30), "red")
		ImageDraw.Draw(im).rectangle((60, 0, 120, 30), fill="blue")
		b = io.BytesIO(); im.save(b, "PNG")
		for source in (SVG, b.getvalue()):
			with self.subTest(vectoriel=source == SVG), pymupdf.open() as pdf:
				z = dict(zone="pictos", x=10, y=10, w=64, h=30, pictos_rotations={"a": 90})
				elements = C.elements_symboles(z, "avant", pictos_svg=[("a", source), ("b", source)])
				p = pdf.new_page(width=250, height=150)
				C.poser_symboles(p, elements)
				pix = p.get_pixmap()
				def pixel(r, rx, ry):
					return pix.pixel(round(C.MM(r[0]+r[2]*rx)), round(C.MM(r[1]+r[3]*ry)))
				self.assertEqual(pixel(elements[0]["rect"], .5, .25), (255, 0, 0))
				self.assertEqual(pixel(elements[0]["rect"], .5, .75), (0, 0, 255))
				self.assertEqual(pixel(elements[1]["rect"], .25, .5), (255, 0, 0))
				self.assertEqual(pixel(elements[1]["rect"], .75, .5), (0, 0, 255))
				self.assertEqual(bool(p.get_images()), source != SVG)

	def test_angle_libre_ajuste_au_cadre_et_decalage_conserve(self):
		z = dict(zone="pictos", x=10, y=10, w=20, h=20, pictos_rotations={"a": 37.5})
		e = C.elements_symboles(z, "avant", pictos_svg=[("a", SVG)])
		with pymupdf.open() as pdf:
			page = pdf.new_page(width=150, height=150)
			C.poser_symboles(page, e)
			r = pymupdf.Rect(C._rect_pt(*e[0]["rect"]))
			for d in page.get_drawings():
				self.assertTrue((r + (-.01, -.01, .01, .01)).contains(d["rect"]))
			decale = pdf.new_page(width=150, height=150)
			C.poser_symboles(decale, e, C._rect_pt(10, 10, 20, 20), {"x": 1, "y": -1})
			self.assertFalse(decale.get_images())
			self.assertTrue(decale.get_drawings())

	def test_apercu_transmet_les_angles_sans_dupliquer_les_images(self):
		doc = frappe._dict(pictogrammes=[frappe._dict(pictogramme="ce")])
		z = dict(zone="pictos", x=10, y=20, w=30, h=30, pictos_rotations={"ce": 37.5})
		a = {"faces": [{"code": "avant", "zones": [dict(z)]}, {"code": "arriere", "zones": [dict(z, pictos_rotations={})]}]}
		with patch.object(A.pictos, "svg_bytes", return_value=SVG), patch.object(A.frappe, "get_all", return_value=[]):
			A.enrichir(doc, a)
		e1, e2 = [f["zones"][0]["apercu_elements"][0] for f in a["faces"]]
		self.assertEqual(e1["rotation"], 37.5)
		self.assertNotIn("rotation", e2)
		self.assertEqual(e1["image"], e2["image"])
		self.assertEqual(len(a["images_zones"]), 1)
