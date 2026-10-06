from __future__ import annotations

import unittest

from aquaworld_ia.emballage import prompts as P

STYLE = {"titre": "Bleu profond", "description": "Fond marin, lumière douce.", "ambiance": "calm fresh clean", "palette": ["#0a3d62", "#ffffff"]}


class TestPrompts(unittest.TestCase):
	def test_interdiction_partout(self):
		for p in (P.prompt_variante(STYLE, "Osmoseur AquaPure", "AquaWorld"),
		          P.prompt_face_secondaire(STYLE, "Osmoseur AquaPure", "cote_gauche"),
		          P.prompt_mockup("Osmoseur AquaPure")):
			for mot in ("text", "logo"):
				self.assertIn(mot, p.lower())

	def test_variante_nomme_le_produit_et_la_marque(self):
		p = P.prompt_variante(STYLE, "Osmoseur AquaPure", "AquaWorld", brief="cible : familles")
		self.assertIn("Osmoseur AquaPure", p)
		self.assertIn("AquaWorld", p)
		self.assertIn("#0a3d62", p)
		self.assertIn("cible : familles", p)
		self.assertIn("DO NOT draw", p)

	def test_face_secondaire_nomme_la_face(self):
		self.assertIn("LEFT side panel", P.prompt_face_secondaire(STYLE, "X", "cote_gauche"))
		self.assertIn("TOP panel", P.prompt_face_secondaire(STYLE, "X", "dessus"))

	def test_palette_imposee_prime(self):
		self.assertIn("#123456", P.prompt_variante(STYLE, "X", palette="#123456"))


class TestConsigneDuFond(unittest.TestCase):
	"""06/10/2026 : « lorsque je génère le fond, est-ce que je peux contrôler ce que je génère ? »"""

	def test_la_consigne_part_a_l_ia_et_prime(self):
		from aquaworld_ia.emballage.prompts import prompt_fond
		p = prompt_fond({"titre": "Vagues minimalistes"}, "Sel", palette="#44a7ed, #0264c3", consigne="vagues bleues en bas, blanc en haut")
		self.assertIn("vagues bleues en bas, blanc en haut", p)
		self.assertIn("takes precedence", p)
		self.assertNotIn("no objects", p)                      # la consigne peut demander des éléments (gouttes, cristaux)
		self.assertIn("Vagues minimalistes", p)
		self.assertIn("#44a7ed, #0264c3", p)

	def test_sans_consigne_rien_ne_change(self):
		from aquaworld_ia.emballage.prompts import prompt_fond
		p = prompt_fond(None, "Sel")
		self.assertNotIn("takes precedence", p)
		self.assertIn("No product, no objects, no people", p)
