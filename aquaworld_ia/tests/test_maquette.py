"""Maquette d'une face et fond perdu — pur."""
from __future__ import annotations

import unittest

from aquaworld_ia.emballage import geometrie as G
from aquaworld_ia.emballage.composition import maquette_face, marges_fond_perdu, rect_avec_fond_perdu, taille_nom

PLAN = G.plan_a_plat(G.ETUI, 120, 200, 60, patte=15, fond_perdu=3, securite=3)
FACES = {f["code"]: f for f in PLAN["faces"]}
CONTENU = {"logo": True, "nom": True, "accroche": True, "caracteristiques": True, "avertissements": True,
           "contact": True, "pictos": 3, "code_barres": G.EAN_NOMINAL_MM}


def _dans(zone, face):
	z = face["zone_sure"]
	return (zone["x"] >= z["x"] - 0.01 and zone["y"] >= z["y"] - 0.01
	        and zone["x"] + zone["w"] <= z["x"] + z["w"] + 0.01 and zone["y"] + zone["h"] <= z["y"] + z["h"] + 0.01)


class TestMaquette(unittest.TestCase):
	def test_toutes_les_zones_dans_la_zone_sure(self):
		for code in ("avant", "arriere", "cote_gauche", "cote_droit", "dessus", "dessous"):
			for z in maquette_face(FACES[code], CONTENU):
				self.assertTrue(_dans(z, FACES[code]), "%s / %s" % (code, z))

	def test_avant_logo_en_haut_nom_en_bas(self):
		zones = {z["zone"]: z for z in maquette_face(FACES["avant"], CONTENU)}
		self.assertLess(zones["logo"]["y"], zones["nom"]["y"])
		self.assertAlmostEqual(zones["nom"]["y"] + zones["nom"]["h"], FACES["avant"]["zone_sure"]["y"] + FACES["avant"]["zone_sure"]["h"], places=2)

	def test_arriere_code_barres_a_taille_nominale(self):
		zones = {z["zone"]: z for z in maquette_face(FACES["arriere"], CONTENU)}
		self.assertAlmostEqual(zones["code_barres"]["w"], G.EAN_NOMINAL_MM[0], places=2)
		self.assertAlmostEqual(zones["code_barres"]["h"], G.EAN_NOMINAL_MM[1], places=2)
		self.assertIn("caracteristiques", zones)
		self.assertIn("pictos", zones)

	def test_sans_contenu_pas_de_zone(self):
		self.assertEqual(maquette_face(FACES["dessus"], {}), [])

	def test_code_barres_reduit_au_plus_a_80_pour_cent(self):
		petite = G.plan_a_plat(G.ETUI, 40, 60, 20, patte=10, fond_perdu=0, securite=2)
		arriere = next(f for f in petite["faces"] if f["code"] == "arriere")
		z = next(z for z in maquette_face(arriere, CONTENU) if z["zone"] == "code_barres")
		self.assertGreaterEqual(z["w"], G.EAN_NOMINAL_MM[0] * 0.8 - 0.01)


class TestTailleNom(unittest.TestCase):
	def test_bornee_par_la_largeur_sur_un_cote_etroit(self):
		# côté de 54 mm (≈153 pt) : 17 caractères ne peuvent pas dépasser ~15,5 pt
		self.assertLessEqual(taille_nom(153, 66, "TEST Aquaworld IA"), 15.6)

	def test_bornee_par_la_hauteur_sur_une_face_large(self):
		self.assertAlmostEqual(taille_nom(330, 20, "AB"), 11.0)

	def test_plafond_et_plancher(self):
		self.assertEqual(taille_nom(2000, 2000, "X"), 40.0)
		self.assertEqual(taille_nom(10, 10, "Un nom très long pour une toute petite case"), 7.0)


class TestFondPerdu(unittest.TestCase):
	def test_seulement_sur_les_aretes_de_coupe(self):
		# la face avant : haut = pli (dessus), bas = pli (dessous), gauche/droite = plis (côtés)
		self.assertEqual(marges_fond_perdu(FACES["avant"], PLAN), {"haut": 0, "bas": 0, "gauche": 0, "droite": 0})
		# la face arrière : bord droit = coupe, haut et bas = coupes, gauche = pli
		self.assertEqual(marges_fond_perdu(FACES["arriere"], PLAN), {"haut": 3, "bas": 3, "gauche": 0, "droite": 3})

	def test_rect_etendu(self):
		x, y, w, h = rect_avec_fond_perdu(FACES["arriere"], PLAN)
		self.assertAlmostEqual(w, 123)
		self.assertAlmostEqual(h, 206)
		self.assertAlmostEqual(x, FACES["arriere"]["x"])
