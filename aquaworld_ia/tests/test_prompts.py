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
