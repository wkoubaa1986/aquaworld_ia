"""Une certification recolorée reste vectorielle et propre à la zone choisie."""
import copy
import io
import json
import unittest
from unittest.mock import Mock, patch
from xml.etree import ElementTree as ET

import frappe
import pymupdf
from PIL import Image, ImageDraw

from aquaworld_ia.emballage import composition as C, pictos_images as P, apercu_elements as A


SVG = b'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 60">
<style>.a{fill:rgb(10,20,30)!important;stroke:#000;stroke-width:2}</style>
<path class="a" d="M5 5h35v50H5z" transform="translate(1 0)"/>
<rect x="50" y="5" width="40" height="50" fill="rgb(20,40,60)" fill-opacity=".7"/>
<text x="12" y="32" fill="rgb(255,255,255)" font-size="9">CERTIF</text></svg>'''
URL = "/private/files/certification.svg"


class TestPictosImages(unittest.TestCase):
	def test_courbes_textes_et_opacites_conserves_sans_bitmap(self):
		resultat, infos = P.transformer(SVG, couleur="#A020F0")
		avant, apres = ET.fromstring(SVG), ET.fromstring(resultat)
		for a, b in zip(avant.iter(), apres.iter()):
			self.assertEqual(a.tag, b.tag)
			if not a.tag.endswith("style"):
				self.assertEqual(a.text, b.text)
				for cle, valeur in a.attrib.items():
					if cle not in ("fill", "stroke"):
						self.assertEqual(b.attrib[cle], valeur)
		self.assertIn(b'fill="#a020f0"', resultat)
		self.assertIn(b'fill="rgb(255,255,255)"', resultat)
		self.assertIn(b'fill:#a020f0!important', resultat)
		self.assertNotIn(b"<image", resultat)
		self.assertFalse(infos["trace"])
		pymupdf.open(stream=resultat, filetype="svg")[0].get_pixmap()
		self.assertEqual(P.transformer(SVG, mode="vectoriser")[0], SVG)

	def test_rgba_et_textes_ressemblant_a_du_css(self):
		s = b'<svg xmlns="http://www.w3.org/2000/svg"><path fill="rgba(0,0,0,0.5)" d="M0 0h10v10z"/><text>fill:red</text></svg>'
		r, _ = P.transformer(s, couleur="#ff0000")
		self.assertIn(b'fill="rgba(255,0,0,0.5)"', r)
		self.assertIn(b'<text>fill:red</text>', r)
		with self.assertRaisesRegex(ValueError, "masque"):
			P.transformer(s.replace(b"<path", b"<mask/><path"))

	def test_bitmap_trace_et_recolore_en_svg_reel(self):
		im = Image.new("RGBA", (80, 80), "white")
		ImageDraw.Draw(im).ellipse((10, 10, 70, 70), fill="#004488")
		b = io.BytesIO(); im.save(b, "PNG")
		svg, infos = P.transformer(b.getvalue(), couleur="#b00020", retirer_fond=True)
		self.assertTrue(infos["trace"])
		self.assertTrue(infos["avertissements"])
		self.assertIn(b"<path", svg)
		self.assertNotIn(b"<image", svg)
		self.assertIn(b"#b00020", svg)
		with self.assertRaises(ValueError):
			P.transformer(b.getvalue(), couleur="red")

	def test_variante_prioritaire_sur_recoloration_automatique_et_pdf_vectoriel(self):
		z = dict(zone="pictos", x=10, y=10, w=40, h=20, pictos_images={"ce": URL}, pictos_disposition="vertical")
		variant, _ = P.transformer(SVG, couleur="#a020f0")
		catalogue = [("ce", SVG), ("eau", SVG)]
		elements = C.elements_symboles(z, "avant", pictos_svg=catalogue, images_pictos={URL: variant}, sans_cartouche=True, couleur="#111111")
		self.assertEqual(elements[0]["image"], variant)
		self.assertFalse(elements[0]["logo"])  # Le blanc voulu n'est pas détouré.
		self.assertEqual(C.elements_symboles(dict(z, pictos_images={}), "arriere", pictos_svg=catalogue)[0]["image"], SVG)
		pdf = pymupdf.open(); page = pdf.new_page()
		C.poser_symboles(page, elements)
		self.assertFalse(page.get_images())
		self.assertTrue(page.get_drawings())
		self.assertIn("CERTIF", page.get_text())
		self.assertTrue(any(d["fill"] and abs(d["fill"][0] - 160/255) < .01 for d in page.get_drawings()))

	def test_apercu_et_bornage_gardent_la_variante_sans_changer_les_autres_zones(self):
		zone = dict(zone="pictos", x=10, y=10, w=40, h=20, pictos_images={"ce": URL})
		face = dict(code="avant", x=0, y=0, w=150, h=300, zones=[zone, dict(zone, pictos_images={})])
		self.assertEqual(C.borner_zone(zone, face)["pictos_images"], {"ce": URL})
		doc = frappe._dict(name="TEST", pictogrammes=[frappe._dict(pictogramme="ce")])
		apercu = {"faces": [copy.deepcopy(face)]}
		with patch.object(P, "charger", return_value={URL: P.transformer(SVG, couleur="#ff0000")[0]}), \
			patch.object(A.pictos, "svg_bytes", return_value=SVG), patch.object(A.frappe, "get_all", return_value=[]):
			A.enrichir(doc, apercu)
		self.assertEqual(len(apercu["images_zones"]), 2)
		a, b = apercu["faces"][0]["zones"]
		self.assertNotEqual(a["apercu_elements"][0]["image"], b["apercu_elements"][0]["image"])

	def test_les_urls_sont_verifiees_avant_lecture(self):
		doc = frappe._dict(name="TEST", mise_en_page=json.dumps({"avant": [dict(zone="pictos", pictos_images={"ce": URL})]}))
		self.assertEqual(P.urls_du_design(doc), {URL})
		with patch.object(P.frappe, "throw", side_effect=ValueError), patch.object(P, "_", side_effect=lambda s: s), \
			patch.object(P.frappe, "db", Mock(exists=Mock(return_value=False))), patch("aquaworld_ia.ia.fichiers.lire") as lire:
			with self.assertRaises(ValueError): P.charger(doc)
			lire.assert_not_called()

	def test_preparer_attache_un_candidat_sans_modifier_catalogue_ni_design(self):
		doc = frappe._dict(name="TEST", pictogrammes=[frappe._dict(pictogramme="ce")], check_permission=Mock(), save=Mock())
		with patch.object(P.frappe, "get_doc", return_value=doc), \
			patch("aquaworld_ia.emballage.pictos.svg_bytes", return_value=SVG), \
			patch("frappe.utils.file_manager.save_file", return_value=frappe._dict(file_url=URL)) as fichier:
			res = P.preparer.__wrapped__("TEST", "ce", couleur="#abcdef")
		self.assertEqual(res["candidat"], URL)
		self.assertEqual(fichier.call_args.args[2:], ("Design Emballage", "TEST"))
		self.assertTrue(fichier.call_args.kwargs["is_private"])
		doc.check_permission.assert_called_once_with("write")
		doc.save.assert_not_called()
