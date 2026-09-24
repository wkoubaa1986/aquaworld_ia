"""Fond continu : un panorama pour la bande, une tranche par face, raccord aux plis — pur."""
from __future__ import annotations

import inspect
import unittest

from aquaworld_ia.emballage import composition as C
from aquaworld_ia.emballage import geometrie as G
from aquaworld_ia.emballage import prompts as P


class TestBande(unittest.TestCase):
	def test_etui_la_bande_fait_le_tour_dans_l_ordre(self):
		b = G.bande(G.plan_a_plat(G.ETUI, 120, 200, 60, patte=15, fond_perdu=3, securite=3))
		self.assertEqual(b["faces"], ["cote_gauche", "avant", "cote_droit", "arriere"])
		self.assertAlmostEqual(b["w"], 360, places=3)
		self.assertAlmostEqual(b["h"], 200, places=3)
		self.assertAlmostEqual(b["x"], 3 + 15, places=3)

	def test_caisse_et_sac(self):
		self.assertEqual(G.bande(G.plan_a_plat(G.CAISSE, 120, 200, 60))["faces"], ["avant", "cote_droit", "arriere", "cote_gauche"])
		self.assertEqual(G.bande(G.plan_a_plat(G.SAC, 120, 200, 60))["faces"], ["avant", "cote_droit", "arriere", "cote_gauche"])

	def test_doypack_avant_et_dos(self):
		self.assertEqual(G.bande(G.plan_a_plat(G.DOYPACK, 130, 200, 80))["faces"], ["avant", "arriere"])

	def test_le_dessus_n_est_pas_dans_la_bande(self):
		self.assertNotIn("dessus", G.bande(G.plan_a_plat(G.ETUI, 120, 200, 60))["faces"])


class TestTranches(unittest.TestCase):
	def setUp(self):
		self.bande = {"x": 18.0, "y": 100.0, "w": 360.0, "h": 200.0, "faces": ["cote_gauche", "avant", "cote_droit", "arriere"]}

	def test_les_tranches_de_deux_faces_voisines_sont_contigues(self):
		"""C'est la continuité même : là où la tranche du côté gauche s'arrête, celle de l'avant
		commence, au pixel près."""
		img = (1536, 1024)
		gauche = C.boite_tranche(self.bande, (18.0, 100.0, 60.0, 200.0), *img)
		avant = C.boite_tranche(self.bande, (78.0, 100.0, 120.0, 200.0), *img)
		self.assertEqual(gauche[2], avant[0])
		self.assertEqual(gauche[1], avant[1])
		self.assertEqual(gauche[3], avant[3])

	def test_la_bande_entiere_couvre_le_panorama_recadre(self):
		img = (1536, 1024)
		x0, y0, x1, y1 = G.cadrage(360.0, 200.0, *img)
		tout = C.boite_tranche(self.bande, (18.0, 100.0, 360.0, 200.0), *img)
		self.assertEqual(tout, (x0, y0, x1, y1))

	def test_la_tranche_garde_le_ratio_de_la_face(self):
		b = C.boite_tranche(self.bande, (78.0, 100.0, 120.0, 200.0), 1536, 1024)
		self.assertAlmostEqual((b[2] - b[0]) / (b[3] - b[1]), 120 / 200, places=1)


class TestPromptFond(unittest.TestCase):
	def test_un_fond_n_a_ni_produit_ni_point_focal_en_continu(self):
		p = P.prompt_fond({"titre": "Bleu profond"}, "Osmoseur", famille="boite", continu=True)
		self.assertIn("panorama", p)
		self.assertIn("No product", p)
		self.assertIn("NO centered focal point", p)
		for mot in P.interdits():
			self.assertIn(mot, p)

	def test_sans_continu_pas_de_panorama(self):
		self.assertNotIn("panorama", P.prompt_fond(None, "X", continu=False))


class TestCompositionContinue(unittest.TestCase):
	def test_la_bande_est_prise_avec_son_fond_perdu(self):
		src = inspect.getsource(C.composer)
		self.assertIn("rect_avec_fond_perdu(f, plan) for f in plan[\"faces\"] if f[\"code\"] in bande[\"faces\"]", src)
		# la tranche est TOUJOURS celle de la face elle-même (continuité de la vague), même copiée ;
		# seul le visuel IA suit la source (précision utilisateur 24/09/2026)
		self.assertIn("tranche_panorama(image_fond, bande, r)", src)
		self.assertNotIn("r_src", src)
		self.assertIn("face_source(plan, face[\"code\"], copies)", src)
		# zone photo ignorée sur une face qui a un visuel IA (le produit y est déjà)
		self.assertIn('if photo_zone and face["code"] not in visuels:', src)
