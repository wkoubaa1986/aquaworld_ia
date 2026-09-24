"""Le Studio emballage n'écrit que des SAISIES, jamais des résultats — pur."""
from __future__ import annotations

import unittest

from aquaworld_ia.emballage import studio as S


class TestChampsDuStudio(unittest.TestCase):
	def test_les_resultats_ne_sont_pas_editables(self):
		"""Statut, plan, aperçus, variantes, textes IA : produits par un traitement, pas saisis."""
		for champ in ("statut", "plan_a_plat", "apercu_plan", "apercu_3d", "variante_choisie", "faces_ia",
		              "variantes", "textes_ia", "journal", "name", "article"):
			self.assertNotIn(champ, S.CHAMPS_EDITABLES, champ)

	def test_les_saisies_le_sont(self):
		for champ in ("type_boite", "longueur_mm", "hauteur_mm", "profondeur_mm", "logo", "photo_produit",
		              "caracteristiques", "brief_style", "nb_variantes", "code_barres"):
			self.assertIn(champ, S.CHAMPS_EDITABLES, champ)

	def test_les_dimensions_sont_converties_en_nombres(self):
		self.assertTrue(set(S.CHAMPS_NUMERIQUES) <= set(S.CHAMPS_EDITABLES))
		for champ in ("longueur_mm", "hauteur_mm", "profondeur_mm"):
			self.assertIn(champ, S.CHAMPS_NUMERIQUES)


class TestBibliotheque(unittest.TestCase):
	"""Bibliothèque de fonds, motifs et variantes de logo (demande utilisateur 24/09/2026)."""

	def test_categories_par_champ(self):
		self.assertEqual(S.categorie_par_defaut("image_fond"), "Fond")
		self.assertEqual(S.categorie_par_defaut("logo"), "Logo")
		self.assertIn("Motif", S.CHAMPS_BIBLIOTHEQUE["image_fond"])
		self.assertNotIn("Logo", S.CHAMPS_BIBLIOTHEQUE["image_fond"])
		with self.assertRaises(ValueError):
			S.categorie_par_defaut("photo_produit")
