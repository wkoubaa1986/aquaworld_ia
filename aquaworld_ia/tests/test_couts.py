from __future__ import annotations

import unittest

from aquaworld_ia.ia import couts as C


class TestCouts(unittest.TestCase):
	def test_texte(self):
		"""Le défaut est la grille gpt-5.2 (1,75 / 14 $ par million, relevée le 23/09/2026)."""
		self.assertAlmostEqual(C.estimer_cout(1_000_000, 0), 1.75)
		self.assertAlmostEqual(C.estimer_cout(0, 1_000_000), 14.0)
		self.assertAlmostEqual(C.estimer_cout(2000, 1000), 0.0175)

	def test_tarifs_texte_par_modele(self):
		"""Préfixe le plus long d'abord ; un modèle daté prend la ligne de sa famille ; inconnu ou
		vide = gpt-5.2 ; « gpt-5 » ne capture pas « gpt-5.2 » ni « gpt-5-mini »."""
		self.assertEqual(C.tarifs_texte("gpt-5.2"), (1.75, 14.0))
		self.assertEqual(C.tarifs_texte("gpt-5.2-2026-01-15"), (1.75, 14.0))
		self.assertEqual(C.tarifs_texte("GPT-5.2-Pro"), (10.5, 84.0))
		self.assertEqual(C.tarifs_texte("gpt-5-mini"), (0.25, 2.0))
		self.assertEqual(C.tarifs_texte("gpt-5"), (1.25, 10.0))
		self.assertEqual(C.tarifs_texte("gpt-4o-mini"), (0.15, 0.60))
		self.assertEqual(C.tarifs_texte("gpt-4o"), (2.5, 10.0))
		self.assertEqual(C.tarifs_texte(None), (1.75, 14.0))
		self.assertEqual(C.tarifs_texte("modele-inconnu"), (1.75, 14.0))

	def test_reglages_vides_suivent_le_modele(self):
		"""Réglages sans prix jetons : la grille suit le modèle de l'appel, sinon celui des
		réglages ; un prix saisi l'emporte sur les deux."""
		class R:
			modele_texte = "gpt-4o-mini"
			prix_entree_par_million = 0
			prix_sortie_par_million = None

		self.assertEqual(C.tarifs_depuis_reglages(R())["entree_par_million"], 0.15)
		self.assertEqual(C.tarifs_depuis_reglages(R(), modele="gpt-5.2")["sortie_par_million"], 14.0)
		R.prix_sortie_par_million = 3.0
		self.assertEqual(C.tarifs_depuis_reglages(R(), modele="gpt-5.2")["sortie_par_million"], 3.0)

	def test_images_par_qualite(self):
		"""Grille gpt-image-2 (septembre 2026) : 0,006 / 0,053 / 0,211 ; une qualité inconnue
		compte comme medium."""
		self.assertAlmostEqual(C.estimer_cout(images=3, qualite="high"), 0.633)
		self.assertAlmostEqual(C.estimer_cout(images=1, qualite="inconnue"), 0.053)
		self.assertAlmostEqual(C.cout_variantes(4, "low"), 0.024)

	def test_tarifs_depuis_reglages(self):
		class R:
			prix_entree_par_million = 1.0
			prix_sortie_par_million = 0
			prix_image_low = None
			prix_image_medium = 0.1
			prix_image_high = "abc"

		t = C.tarifs_depuis_reglages(R())
		self.assertEqual(t["entree_par_million"], 1.0)
		self.assertEqual(t["sortie_par_million"], C.TARIFS_DEFAUT["sortie_par_million"])  # modèle vide = gpt-5.2
		self.assertEqual(t["image"]["medium"], 0.1)
		self.assertEqual(t["image"]["high"], C.TARIFS_DEFAUT["image"]["high"])
		self.assertAlmostEqual(C.estimer_cout(1_000_000, 0, tarifs=t), 1.0)
