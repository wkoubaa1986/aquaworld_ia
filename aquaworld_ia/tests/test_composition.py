"""Composition du plan à plat — les règles PURES de rendu des textes (23/09/2026)."""
from __future__ import annotations

import inspect
import unittest

from aquaworld_ia.emballage import composition as C


class TestPucesEtSens(unittest.TestCase):
	def test_pas_de_ul_les_puces_sont_typographiques(self):
		"""Le marqueur de liste d'insert_htmlbox reste à gauche sous direction:rtl."""
		h = C.html_bloc(["a", "b"], taille_pt=8, rtl=True, famille="Noto Naskh Arabic", puces=True)
		self.assertNotIn("<ul", h)
		self.assertNotIn("<li", h)
		self.assertEqual(h.count(C.PUCE), 2)
		self.assertIn("direction:rtl", h)

	def test_un_paragraphe_rtl_ne_demande_jamais_right(self):
		"""⚠️ MuPDF inverse l'alignement sous direction:rtl : « right » collerait à gauche."""
		self.assertEqual(C.alignement_css("right", rtl=True), "")
		self.assertEqual(C.alignement_css(None, rtl=True), "")
		self.assertEqual(C.alignement_css("center", rtl=True), "text-align:center;")
		self.assertNotIn("text-align:right", C.html_bloc(["x"], taille_pt=8, rtl=True, famille="F"))

	def test_un_paragraphe_ltr_garde_son_alignement(self):
		self.assertEqual(C.alignement_css(None, rtl=False), "text-align:left;")
		self.assertEqual(C.alignement_css("center", rtl=False), "text-align:center;")
		self.assertIn("text-align:center", C.html_bloc(["x"], taille_pt=8, rtl=False, famille="F", align="center"))

	def test_le_texte_est_echappe(self):
		self.assertIn("&lt;b&gt;", C.html_bloc(["<b>"], taille_pt=8, rtl=False, famille="F"))


class TestTailleParLangue(unittest.TestCase):
	def test_la_premiere_langue_est_la_plus_grande(self):
		self.assertGreater(C.taille_langue(8.5, 0, False), C.taille_langue(8.5, 1, False))

	def test_l_arabe_est_releve(self):
		"""Noto Naskh Arabic paraît plus petit que Noto Sans à corps égal."""
		self.assertGreater(C.taille_langue(8.5, 1, True), C.taille_langue(8.5, 1, False))
		self.assertAlmostEqual(C.taille_langue(10, 0, True), 11.5)


class TestCartouche(unittest.TestCase):
	def test_seul_le_petit_texte_sur_visuel_a_un_cartouche(self):
		self.assertIsNone(C.panneau_pour("nom", "#111827", True))
		self.assertIsNone(C.panneau_pour("accroche", "#111827", True))
		self.assertIsNone(C.panneau_pour("caracteristiques", "#111827", False))
		self.assertIsNotNone(C.panneau_pour("caracteristiques", "#111827", True))
		self.assertIsNotNone(C.panneau_pour("avertissements", "#ffffff", True))

	def test_le_cartouche_est_du_cote_oppose_au_texte(self):
		rgb_clair, _ = C.panneau_pour("contact", "#111827", True)
		rgb_sombre, _ = C.panneau_pour("contact", "#ffffff", True)
		self.assertEqual(rgb_clair, (1.0, 1.0, 1.0))
		self.assertLess(sum(rgb_sombre), 1.0)

	def test_le_cartouche_epouse_le_texte_pas_la_zone(self):
		src = inspect.getsource(C.composer)
		self.assertIn("hauteur_texte(rect, contenu_html", src)
		self.assertIn("rect[1] + h_texte + m", src)


class TestRienDePerime(unittest.TestCase):
	"""Une variante régénérée repart de zéro ; des faces générées recomposent le plan."""

	def test_regenerer_efface_faces_plan_et_3d(self):
		from aquaworld_ia.emballage import job

		src = inspect.getsource(job.regenerer_variante)
		self.assertIn("CHAMPS_FACES.values()", src)
		for champ in ("plan_a_plat", "apercu_plan", "apercu_3d", "faces_ia"):
			self.assertIn(champ, src)

	def test_les_faces_recomposent_le_plan_et_perime_le_3d(self):
		from aquaworld_ia.emballage import variantes

		src = inspect.getsource(variantes.generer_faces_secondaires)
		self.assertIn("composer_et_attacher(design, v.numero)", src)
		self.assertIn('"apercu_3d": None', src)
