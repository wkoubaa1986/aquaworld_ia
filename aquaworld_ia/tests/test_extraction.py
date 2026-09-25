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


class TestEntreesDeListe(unittest.TestCase):
	"""Les étapes « 1. … 2. … » d'un même bloc font des paragraphes séparés (manuel David 4000, 24/09/2026)."""

	def test_marqueurs(self):
		from aquaworld_ia.manuels.extraction import commence_une_entree

		for oui in ("1. Turn off", "12) Do this", "a. Drill", "(3) Attach", "• Safety glasses", "- item", "iv. step", "d)  Place", "1.", "•", "2.Operation principle"):
			self.assertTrue(commence_une_entree(oui), oui)
		for non in ("4001 First Stage", "1/2-inch tubing", "2 adjustable wrenches", "Turn off 1. then", "", "A dog", "v6 engine", "3.14 bar", "a.m. today"):
			self.assertFalse(commence_une_entree(non), non)

	def test_grouper_coupe_aux_entrees(self):
		from aquaworld_ia.manuels.extraction import grouper_lignes

		def ligne(y, texte):
			return {"bbox": (50, y, 300, y + 10), "spans": [{"text": texte}]}
		lignes = [ligne(0, "1. Turn off water supply"), ligne(11, "and release pressure."), ligne(22, "2. Unscrew housing."), ligne(33, "3. Discard.")]
		groupes = grouper_lignes(lignes)
		self.assertEqual([len(g) for g in groupes], [2, 1, 1])

	def test_marqueur_seul_sur_sa_ligne(self):
		"""Word : « 1. » et la phrase sont deux lignes à la même hauteur ; « 2. » ouvre l'entrée suivante."""
		from aquaworld_ia.manuels.extraction import fusionner_lignes, grouper_lignes

		def ligne(y, x, texte):
			return {"bbox": (x, y, x + 200, y + 10), "spans": [{"text": texte}]}
		lignes = [ligne(0, 87, "1."), ligne(0, 105, "Turn off water."), ligne(12, 105, "NOTE: place a pan."), ligne(24, 87, "2."), ligne(24, 105, "Unscrew.")]
		groupes = grouper_lignes(lignes)
		self.assertEqual([len(g) for g in groupes], [3, 2])
		self.assertEqual(fusionner_lignes(["".join(s["text"] for s in l["spans"]) for l in groupes[1]]), "2. Unscrew.")


class TestParagraphesOCR(unittest.TestCase):
	"""Lignes OCR libres -> paragraphes, colonne par colonne (Tesseract mélange les deux colonnes)."""

	def _l(self, x, y, texte, w=200, h=10):
		return {"bbox": (x, y, x + w, y + h), "spans": [{"text": texte, "size": 10, "flags": 0, "font": "GlyphLessFont", "color": 0}]}

	def test_deux_colonnes_et_paragraphes(self):
		from aquaworld_ia.manuels.extraction import paragraphes_depuis_lignes

		lignes = [self._l(440, 30, "Something to respectable clients"), self._l(35, 30, "CATALOGUE"),
		          self._l(440, 42, "Thank you for your purchase"), self._l(440, 54, "of the water purifier."),
		          self._l(35, 60, "1.Function characteristic *** 1"), self._l(35, 72, "2.Operation principle *** 2-10"),
		          self._l(440, 80, "Now you own an advanced unit.")]
		paras = paragraphes_depuis_lignes(lignes, 1, (0, 0, 794, 561))
		self.assertEqual([p["texte"] for p in paras], [
			"CATALOGUE", "1.Function characteristic 1", "2.Operation principle 2-10",
			"Something to respectable clients Thank you for your purchase of the water purifier.", "Now you own an advanced unit."])
		self.assertEqual(paras[3]["lignes"], 3)
		self.assertEqual(paras[3]["bbox"], (440, 30, 640, 64))

	def test_alinea_et_ligne_pleine_continuent_le_paragraphe(self):
		"""Alinéa de première ligne (OCR) puis lignes au bord gauche ; une ligne pleine continue même en retrait."""
		from aquaworld_ia.manuels.extraction import paragraphes_depuis_lignes

		lignes = [self._l(460, 30, "Thank you for your purchase of the", w=280), self._l(440, 42, "Reverse Osmosis Water Purifier", w=300),
		          self._l(440, 54, "System.", w=60), self._l(500, 66, "Now you own an advanced unit", w=240)]
		paras = paragraphes_depuis_lignes(lignes, 0, (0, 0, 794, 561))
		self.assertEqual([p["texte"] for p in paras], ["Thank you for your purchase of the Reverse Osmosis Water Purifier System.", "Now you own an advanced unit"])

	def test_taille_mediane(self):
		from aquaworld_ia.manuels.extraction import paragraphes_depuis_lignes

		l1, l2, l3 = self._l(35, 30, "a b c"), self._l(35, 42, "d e f"), self._l(35, 54, "g h i")
		l1["spans"][0]["size"], l2["spans"][0]["size"], l3["spans"][0]["size"] = 9.5, 10.0, 16.0
		self.assertEqual(paragraphes_depuis_lignes([l1, l2, l3], 0, (0, 0, 794, 561))[0]["style"]["taille"], 10.0)
		l1["spans"][0]["size"] = 40.0   # ligne de 10 pt de haut lue « géante » : bornée à la hauteur de ligne
		self.assertEqual(paragraphes_depuis_lignes([l1], 0, (0, 0, 794, 561))[0]["style"]["taille"], 10.0)

	def test_decalage_de_colonne_coupe(self):
		from aquaworld_ia.manuels.extraction import paragraphes_depuis_lignes

		paras = paragraphes_depuis_lignes([self._l(35, 30, "Titre"), self._l(120, 42, "loin à droite")], 0, (0, 0, 794, 561))
		self.assertEqual(len(paras), 2)

	def test_vide(self):
		from aquaworld_ia.manuels.extraction import paragraphes_depuis_lignes

		self.assertEqual(paragraphes_depuis_lignes([], 0, (0, 0, 10, 10)), [])


class TestDechetsOCR(unittest.TestCase):
	def test_nettoyer(self):
		from aquaworld_ia.manuels.extraction import nettoyer_ocr

		self.assertEqual(nettoyer_ocr("3.Main technical parameter “eee e eee EE EE 10"), "3.Main technical parameter e 10")
		self.assertEqual(nettoyer_ocr("**********\"\"\"\"\" 4"), "4")
		self.assertEqual(nettoyer_ocr("@ Using imported membrane"), "• Using imported membrane")
		self.assertEqual(nettoyer_ocr("reliable quality. @"), "reliable quality.")
		self.assertEqual(nettoyer_ocr("info@site.com"), "info@site.com")
		self.assertEqual(nettoyer_ocr("Reverse osmosis (RO) system - see p. 3"), "Reverse osmosis (RO) system - see p. 3")
		self.assertEqual(nettoyer_ocr("Operation principle & technical process 2-10"), "Operation principle & technical process 2-10")

	def test_non_traduisible(self):
		from aquaworld_ia.manuels.extraction import est_traduisible

		self.assertFalse(est_traduisible("**********\"\"\"\"\" 4"))
		self.assertFalse(est_traduisible("¥ ** 12"))
		self.assertTrue(est_traduisible("Using imported famous brand reverse osmosis membrane"))
		self.assertTrue(est_traduisible("CATALOGUE"))
		self.assertTrue(est_traduisible("• Using imported membrane"))
		self.assertFalse(est_traduisible("info@bdavidwater.com"))
		self.assertTrue(est_traduisible("WARNING"))
		self.assertFalse(est_traduisible("RO-50G"))
		self.assertFalse(est_traduisible("AB1234"))


class TestPucesOCR(unittest.TestCase):
	def test_le_losange_rejoint_sa_ligne(self):
		from aquaworld_ia.manuels.extraction import paragraphes_depuis_lignes, rattacher_puces

		def l(x, y, texte, w=200):
			return {"bbox": (x, y, x + w, y + 10), "spans": [{"text": texte, "size": 10}]}
		lignes = [l(440, 40, "reliable quality.", w=80), l(428, 52, "@", w=6), l(444, 52, "Pre treating cartridge can be replaced")]
		out = rattacher_puces(lignes)
		self.assertEqual(len(out), 2)
		self.assertEqual(out[1]["spans"][0]["text"], "• Pre treating cartridge can be replaced")
		self.assertEqual(out[1]["bbox"][0], 428)
		paras = paragraphes_depuis_lignes(lignes, 0, (0, 0, 794, 561))
		self.assertEqual([p["texte"] for p in paras], ["reliable quality.", "• Pre treating cartridge can be replaced"])

	def test_un_losange_sans_ligne_reste(self):
		from aquaworld_ia.manuels.extraction import rattacher_puces

		self.assertEqual(len(rattacher_puces([{"bbox": (10, 10, 16, 20), "spans": [{"text": "@"}]}])), 1)
