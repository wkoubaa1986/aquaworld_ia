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
