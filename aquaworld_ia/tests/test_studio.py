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


class TestAtelierImage(unittest.TestCase):
	def test_prompt_et_taille(self):
		self.assertIn("EXACTLY", S.prompt_retouche("photo_produit", "détourer."))
		self.assertTrue(S.prompt_retouche("photo_produit", "détourer.").endswith("Apply only this change: détourer."))
		self.assertIn("lettering EXACTLY", S.prompt_retouche("logo", "bleu marine"))
		with self.assertRaises(ValueError):
			S.prompt_retouche("image_fond", "x")
		import io as _io
		from PIL import Image
		def png(w, h):
			b = _io.BytesIO(); Image.new("RGB", (w, h), "white").save(b, format="PNG"); return b.getvalue()
		self.assertEqual(S.taille_retouche("photo_produit", png(500, 1000)), "1024x1536")
		self.assertEqual(S.taille_retouche("photo_produit", png(1000, 500)), "1536x1024")
		self.assertEqual(S.taille_retouche("photo_produit", png(800, 800)), "1024x1024")
		self.assertEqual(S.taille_retouche("logo", png(500, 1000)), "1024x1024")


class TestImagesDuDesign(unittest.TestCase):
	def test_genre_par_nom(self):
		g = S.genre_image
		self.assertEqual(g("EMB-2026-0002-logo-iabb9f89.png", "EMB-2026-0002"), "Logo IA")
		self.assertEqual(g("EMB-2026-0002-logobb9f89.png", "EMB-2026-0002"), "Logo")
		self.assertEqual(g("EMB-2026-0002-photo-ia369d07.png", "EMB-2026-0002"), "Photo IA")
		self.assertEqual(g("EMB-2026-0002-photodf9f28.png", "EMB-2026-0002"), "Photo")
		self.assertEqual(g("EMB-2026-0002-fond07aafa.png", "EMB-2026-0002"), "Fond IA")
		self.assertEqual(g("EMB-2026-0002-v2a011e0.png", "EMB-2026-0002"), "Variante")
		self.assertEqual(g("EMB-2026-0002-v1-cote_gauche2c8064.png", "EMB-2026-0002"), "Face IA")
		self.assertEqual(g("EMB-2026-0002-apercu-3d70159d.png", "EMB-2026-0002"), "Aperçu 3D")
		self.assertIsNone(g("EMB-2026-0002-apercu56dace.png", "EMB-2026-0002"))
		self.assertEqual(g("P-F-S-10'-O-SC_13b865a.jpg", "EMB-2026-0002"), "Téléversé")
		self.assertEqual(g("ecopurium.png", "EMB-2026-0002"), "Téléversé")
