"""Rendu — HTML d'un paragraphe et boîte d'insertion (pur)."""
from __future__ import annotations

import unittest

from aquaworld_ia.manuels import rendu as R


class TestHtml(unittest.TestCase):
	style = {"taille": 9.5, "gras": True, "italique": False, "couleur": "#112233", "align": "left"}

	def test_echappe_et_style(self):
		h = R.html_paragraphe("a < b & c", self.style)
		self.assertIn("a &lt; b &amp; c", h)
		self.assertIn("font-size:9.5pt", h)
		self.assertIn("font-weight:700", h)
		self.assertIn("color:#112233", h)
		self.assertIn("direction:ltr", h)

	def test_rtl(self):
		h = R.html_paragraphe("مرحبا", self.style, rtl=True, famille_police="Noto Naskh Arabic")
		self.assertIn("direction:rtl", h)
		self.assertIn("text-align:right", h)
		self.assertIn("Noto Naskh Arabic", h)

	def test_centre_conserve_en_rtl(self):
		h = R.html_paragraphe("x", dict(self.style, align="center"), rtl=True)
		self.assertIn("text-align:center", h)

	def test_retours_ligne(self):
		self.assertIn("<br>", R.html_paragraphe("a\nb", self.style))

	def test_famille(self):
		self.assertEqual(R.famille({"rtl": 1}), "Noto Naskh Arabic")
		self.assertEqual(R.famille({"rtl": 0}), "Noto Sans")
		self.assertEqual(R.famille({"police": "Noto Sans", "rtl": 1}), "Noto Sans")


class TestRectInsertion(unittest.TestCase):
	def test_s_allonge_vers_le_bas_au_plus_40_pour_cent(self):
		self.assertEqual(R.rect_insertion((10, 100, 200, 120), (0, 0, 600, 800), []), (10, 100, 200, 128))

	def test_borne_par_le_voisin(self):
		r = R.rect_insertion((10, 100, 200, 120), (0, 0, 600, 800), [(10, 124, 200, 140)])
		self.assertAlmostEqual(r[3], 122.5)

	def test_voisin_a_cote_n_est_pas_un_obstacle(self):
		r = R.rect_insertion((10, 100, 200, 120), (0, 0, 600, 800), [(300, 122, 400, 140)])
		self.assertEqual(r[3], 128)

	def test_bas_de_page(self):
		r = R.rect_insertion((10, 790, 200, 798), (0, 0, 600, 800), [])
		self.assertAlmostEqual(r[3], 798.5)

	def test_css_declare_les_quatre_polices(self):
		css = R.css_base()
		for f in ("NotoSans-Regular.ttf", "NotoSans-Bold.ttf", "NotoNaskhArabic-Regular.ttf", "NotoNaskhArabic-Bold.ttf"):
			self.assertIn(f, css)
