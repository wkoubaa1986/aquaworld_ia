from __future__ import annotations

import unittest

from aquaworld_ia.ia import couts as C


class TestCouts(unittest.TestCase):
	def test_texte(self):
		self.assertAlmostEqual(C.estimer_cout(1_000_000, 0), 0.15)
		self.assertAlmostEqual(C.estimer_cout(0, 1_000_000), 0.60)
		self.assertAlmostEqual(C.estimer_cout(2000, 1000), 0.0009)

	def test_images_par_qualite(self):
		self.assertAlmostEqual(C.estimer_cout(images=3, qualite="high"), 0.75)
		self.assertAlmostEqual(C.estimer_cout(images=1, qualite="inconnue"), 0.07)
		self.assertAlmostEqual(C.cout_variantes(4, "low"), 0.08)

	def test_tarifs_depuis_reglages(self):
		class R:
			prix_entree_par_million = 1.0
			prix_sortie_par_million = 0
			prix_image_low = None
			prix_image_medium = 0.1
			prix_image_high = "abc"

		t = C.tarifs_depuis_reglages(R())
		self.assertEqual(t["entree_par_million"], 1.0)
		self.assertEqual(t["sortie_par_million"], C.TARIFS_DEFAUT["sortie_par_million"])
		self.assertEqual(t["image"]["medium"], 0.1)
		self.assertEqual(t["image"]["high"], C.TARIFS_DEFAUT["image"]["high"])
		self.assertAlmostEqual(C.estimer_cout(1_000_000, 0, tarifs=t), 1.0)
