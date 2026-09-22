"""Géométrie du plan à plat — fonctions pures, tout en mm."""
from __future__ import annotations

import unittest

from aquaworld_ia.emballage import geometrie as G


def _faces(plan):
	return {f["code"]: f for f in plan["faces"]}


class TestEtui(unittest.TestCase):
	def setUp(self):
		self.plan = G.plan_a_plat(G.ETUI, 120, 200, 60, patte=15, fond_perdu=3, securite=3)
		self.f = _faces(self.plan)

	def test_feuille(self):
		# largeur : 2 fp + patte + 2P + 2L ; hauteur : 2 fp + 2T + 2P + H, T = min(20, 0.6P) = 20
		self.assertAlmostEqual(self.plan["feuille"]["w"], 6 + 15 + 120 + 240, places=3)
		self.assertAlmostEqual(self.plan["feuille"]["h"], 6 + 40 + 120 + 200, places=3)

	def test_faces_principales(self):
		self.assertEqual((self.f["avant"]["w"], self.f["avant"]["h"]), (120, 200))
		self.assertEqual((self.f["dessus"]["w"], self.f["dessus"]["h"]), (120, 60))
		self.assertEqual((self.f["cote_gauche"]["w"], self.f["cote_gauche"]["h"]), (60, 200))
		self.assertTrue(self.f["dessus"]["imprimable"])
		self.assertFalse(self.f["patte"]["imprimable"])

	def test_ordre_de_la_bande(self):
		x = [self.f[c]["x"] for c in ("patte", "cote_gauche", "avant", "cote_droit", "arriere")]
		self.assertEqual(x, sorted(x))
		self.assertAlmostEqual(self.f["avant"]["x"], 3 + 15 + 60)

	def test_dessus_au_dessus_de_l_avant(self):
		self.assertAlmostEqual(self.f["dessus"]["y"] + self.f["dessus"]["h"], self.f["avant"]["y"])
		self.assertAlmostEqual(self.f["dessous"]["y"], self.f["avant"]["y"] + self.f["avant"]["h"])

	def test_aucun_chevauchement_et_tout_dans_la_feuille(self):
		self.assertEqual(G.verifier(self.plan), [])

	def test_zone_sure(self):
		z = self.f["avant"]["zone_sure"]
		self.assertEqual((z["w"], z["h"]), (114, 194))

	def test_traits(self):
		t = self.plan["traits"]
		# l'arête avant/côté droit est un pli ; le bord gauche de la patte est une coupe
		self.assertTrue(any(abs(l[0] - self.f["cote_droit"]["x"]) < 0.01 and abs(l[2] - self.f["cote_droit"]["x"]) < 0.01 for l in t["pli"]))
		self.assertTrue(any(abs(l[0] - 3) < 0.01 and abs(l[2] - 3) < 0.01 for l in t["coupe"]))


class TestCaisse(unittest.TestCase):
	def test_feuille_et_rabats(self):
		plan = G.plan_a_plat(G.CAISSE, 300, 200, 150, patte=30, fond_perdu=0, securite=5)
		self.assertAlmostEqual(plan["feuille"]["w"], 30 + 600 + 300)
		self.assertAlmostEqual(plan["feuille"]["h"], 200 + 150)
		self.assertEqual(G.verifier(plan), [])
		rabats = [f for f in plan["faces"] if f["code"].startswith("rabat#")]
		self.assertEqual(len(rabats), 8)
		self.assertTrue(all(abs(r["h"] - 75) < 0.01 for r in rabats))


class TestOutils(unittest.TestCase):
	def test_conversion(self):
		self.assertAlmostEqual(G.mm_vers_pt(25.4), 72.0)
		self.assertAlmostEqual(G.pt_vers_mm(72), 25.4)

	def test_dpi_effectif(self):
		self.assertAlmostEqual(G.dpi_effectif(1536, 130.048), 300.0, places=0)
		self.assertEqual(G.dpi_effectif(100, 0), 0.0)

	def test_taille_image_pour(self):
		self.assertEqual(G.taille_image_pour({"w": 200, "h": 100}), "1536x1024")
		self.assertEqual(G.taille_image_pour({"w": 100, "h": 200}), "1024x1536")
		self.assertEqual(G.taille_image_pour({"w": 120, "h": 110}), "1024x1024")

	def test_cadrage_couvre(self):
		# face 2:1, image carrée -> on garde toute la largeur, on coupe en hauteur
		self.assertEqual(G.cadrage(200, 100, 1000, 1000), (0, 250, 1000, 750))
		# face 1:2, image 3:2 -> on coupe en largeur
		x0, y0, x1, y1 = G.cadrage(100, 200, 1500, 1000)
		self.assertEqual((y0, y1), (0, 1000))
		self.assertEqual(x1 - x0, 500)

	def test_verifier_ean_illogeable(self):
		plan = G.plan_a_plat(G.ETUI, 25, 60, 15, patte=10, fond_perdu=3, securite=3)
		self.assertTrue(any("EAN" in p for p in G.verifier(plan)))

	def test_dimensions_invalides(self):
		with self.assertRaises(ValueError):
			G.plan_a_plat(G.ETUI, 0, 10, 10)
		with self.assertRaises(ValueError):
			G.plan_a_plat("Tube", 10, 10, 10)

	def test_apercu_svg(self):
		svg = G.apercu_svg(G.plan_a_plat(G.ETUI, 120, 200, 60))
		self.assertTrue(svg.startswith("<svg"))
		self.assertIn("Face avant", svg)
