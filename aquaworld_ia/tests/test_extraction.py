"""Extraction des paragraphes — la partie pure (sans PDF)."""
from __future__ import annotations

import unittest

from aquaworld_ia.manuels import extraction as E


def _ligne(texte, y0, y1, x0=50, x1=300, size=10, flags=0, font="Helvetica", color=0):
	return {"bbox": (x0, y0, x1, y1), "dir": (1, 0),
	        "spans": [{"text": texte, "size": size, "flags": flags, "font": font, "color": color, "bbox": (x0, y0, x1, y1)}]}


class TestFusion(unittest.TestCase):
	def test_cesure_recollee(self):
		self.assertEqual(E.fusionner_lignes(["The instal-", "lation must be", "done."]), "The installation must be done.")

	def test_tiret_conserve_devant_majuscule(self):
		self.assertEqual(E.fusionner_lignes(["Anti-", "Corrosion coating"]), "Anti- Corrosion coating")

	def test_espaces_normalises(self):
		self.assertEqual(E.fusionner_lignes(["  a   b ", "", " c"]), "a b c")


class TestStyle(unittest.TestCase):
	def test_gras_par_flag_et_par_nom(self):
		self.assertTrue(E.style_dominant([{"text": "x", "size": 12, "flags": 16, "font": "Arial", "color": 0}])["gras"])
		self.assertTrue(E.style_dominant([{"text": "x", "size": 12, "flags": 0, "font": "Arial-BoldMT", "color": 0}])["gras"])
		self.assertFalse(E.style_dominant([{"text": "x", "size": 12, "flags": 0, "font": "Arial", "color": 0}])["gras"])

	def test_couleur_et_taille_du_span_dominant(self):
		s = E.style_dominant([{"text": "a", "size": 20, "flags": 0, "font": "A", "color": 0xFF0000},
		                      {"text": "un long texte", "size": 9.5, "flags": 0, "font": "B", "color": 0x0000FF}])
		self.assertEqual(s["taille"], 9.5)
		self.assertEqual(s["couleur"], "#0000ff")

	def test_alignement(self):
		bbox = (0, 0, 100, 30)
		centre = [(10, 0, 90, 10), (30, 10, 70, 20)]
		self.assertEqual(E.alignement(bbox, centre, (0, 0, 200, 300)), "center")
		droite = [(40, 0, 100, 10), (0, 10, 100, 20)]
		self.assertEqual(E.alignement(bbox, droite, (0, 0, 200, 300)), "right")
		gauche = [(0, 0, 90, 10), (0, 10, 60, 20)]
		self.assertEqual(E.alignement(bbox, gauche, (0, 0, 200, 300)), "left")


class TestTraduisible(unittest.TestCase):
	def test_non_traduisibles(self):
		for t in ("230 V", "50Hz", "12mm", "AB-1234", "www.example.com", "mail@ex.com", "3.5", "-", "A"):
			self.assertFalse(E.est_traduisible(t), t)

	def test_traduisibles(self):
		for t in ("Warning: do not open the cover.", "Installation", "Step 3: connect the hose (12 mm)."):
			self.assertTrue(E.est_traduisible(t), t)


class TestBlocs(unittest.TestCase):
	def test_un_bloc_deux_paragraphes_sur_grand_ecart(self):
		bloc = {"lines": [_ligne("First line", 0, 10), _ligne("second line", 11, 21), _ligne("New paragraph", 40, 50)]}
		ps = E.paragraphes_depuis_bloc(bloc, 0, (0, 0, 400, 600))
		self.assertEqual([p["texte"] for p in ps], ["First line second line", "New paragraph"])
		self.assertEqual(ps[0]["bbox"], (50, 0, 300, 21))
		self.assertEqual(ps[0]["lignes"], 2)

	def test_bloc_vide(self):
		self.assertEqual(E.paragraphes_depuis_bloc({"lines": [_ligne("   ", 0, 10)]}, 0, (0, 0, 400, 600)), [])


class TestLots(unittest.TestCase):
	def test_dedoublonner(self):
		ps = [{"id": 0, "texte": "Header"}, {"id": 1, "texte": "Body"}, {"id": 2, "texte": "Header "}]
		uniques, index = E.dedoublonner(ps)
		self.assertEqual(uniques, ["Header", "Body"])
		self.assertEqual(index, {0: 0, 1: 1, 2: 0})

	def test_repartir_lots(self):
		self.assertEqual(E.repartir_lots(["a"] * 7, taille_max=3), [[0, 1, 2], [3, 4, 5], [6]])
		self.assertEqual(E.repartir_lots(["x" * 5000, "y" * 5000, "z"], taille_max=10, chars_max=6000), [[0], [1, 2]])
		self.assertEqual(E.repartir_lots([]), [])
