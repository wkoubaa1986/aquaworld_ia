from __future__ import annotations

import unittest

from aquaworld_ia.emballage import codes as C


class TestEan13(unittest.TestCase):
	def test_valide(self):
		self.assertTrue(C.valider_ean13("4006381333931"))
		self.assertTrue(C.valider_ean13("6191234567890"[:12] + C.cle_ean13("619123456789")))

	def test_invalide(self):
		self.assertFalse(C.valider_ean13("4006381333932"))
		self.assertFalse(C.valider_ean13("400638133393"))
		self.assertFalse(C.valider_ean13(""))
		self.assertFalse(C.valider_ean13(None))

	def test_cle(self):
		self.assertEqual(C.cle_ean13("400638133393"), "1")

	def test_svg(self):
		svg = C.ean13_svg("4006381333931")
		self.assertIn(b"<svg", svg)
		with self.assertRaises(ValueError):
			C.ean13_svg("123")

	def test_qr(self):
		self.assertIn(b"<svg", C.qr_svg("https://aquaworldservicing.com"))


class TestCouleurQr(unittest.TestCase):
	"""La couleur du QR (06/10/2026) : celle choisie si elle se scanne sur le cartouche blanc, le noir sinon."""

	def test_couleur_foncee_gardee(self):
		self.assertEqual(C.couleur_qr("#1D4ED8"), "#1d4ed8")
		self.assertEqual(C.couleur_qr("0b3d2e"), "#0b3d2e")
		self.assertIn(b'stroke="#1d4ed8"', C.qr_svg("https://aquaworld.tn", "#1d4ed8"))

	def test_trop_clair_ou_invalide_donne_du_noir(self):
		for c in ("#ffeb3b", "#f9a8d4", "#ffffff", "bleu", "", None):
			self.assertEqual(C.couleur_qr(c), "#000000", c)
		self.assertIn(b'stroke="#000"', C.qr_svg("https://aquaworld.tn", "#ffeb3b").replace(b"#000000", b"#000"))

	def test_contraste(self):
		self.assertAlmostEqual(C.contraste_sur_blanc("#000000"), 21, places=1)
		self.assertAlmostEqual(C.contraste_sur_blanc("#ffffff"), 1, places=2)
		self.assertGreaterEqual(C.contraste_sur_blanc("#1d4ed8"), C.CONTRASTE_QR_MIN)
		self.assertLess(C.contraste_sur_blanc("#fbbf24"), C.CONTRASTE_QR_MIN)       # ambre : refusé

	def test_le_qr_colore_se_lit(self):
		"""Rendu par MuPDF (comme sur le plan) puis lu par OpenCV : l'URL revient intacte."""
		import cv2
		import numpy as np
		import pymupdf

		url = "https://aquaworld.tn/sel-pastilles"
		svg = C.qr_svg(url, "#1d4ed8")
		svg = svg.replace(b"<svg ", b'<svg xmlns="http://www.w3.org/2000/svg" ', 1) if b"xmlns" not in svg else svg
		page = pymupdf.open(stream=svg, filetype="svg")[0]
		pix = page.get_pixmap(matrix=pymupdf.Matrix(4, 4), alpha=False)
		img = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)
		img = cv2.copyMakeBorder(img, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=(255, 255, 255))
		texte, _pts, _x = cv2.QRCodeDetector().detectAndDecode(img)
		self.assertEqual(texte, url)
