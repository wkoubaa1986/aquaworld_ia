"""Traduction — prompts et vérification des lots (pur, aucun appel IA)."""
from __future__ import annotations

import json
import unittest

from aquaworld_ia.manuels import traduction as T

AR = {"code": "ar", "libelle": "Arabe", "libelle_natif": "العربية", "rtl": 1, "instructions": "chiffres occidentaux"}
FR = {"code": "fr", "libelle": "Français", "rtl": 0}


class TestPrompt(unittest.TestCase):
	def test_glossaire_et_rtl(self):
		p = T.prompt_systeme(AR, glossaire="pump = مضخة\nfilter = مرشح", contexte="pompe de piscine")
		self.assertIn("pump = مضخة", p)
		self.assertIn("droite à gauche", p)
		self.assertIn("chiffres occidentaux", p)
		self.assertIn("pompe de piscine", p)
		self.assertIn("العربية", p)

	def test_sans_rtl(self):
		self.assertNotIn("droite à gauche", T.prompt_systeme(FR))

	def test_glossaire_ignore_les_lignes_mal_formees(self):
		self.assertEqual(T.lignes_glossaire("a = b\nsans egal\n = vide\nc=d"), [("a", "b"), ("c", "d")])

	def test_prompt_utilisateur_json(self):
		self.assertEqual(json.loads(T.prompt_utilisateur(["x", "y"])), {"items": [{"i": 0, "t": "x"}, {"i": 1, "t": "y"}]})


class TestVerification(unittest.TestCase):
	entree = ["Connect the 230 V supply.", "Tighten to 2.5 Nm"]

	def test_ok(self):
		ok, motif = T.verifier_lot(self.entree, {"items": [{"i": 0, "t": "Branchez le 230 V."}, {"i": 1, "t": "Serrez à 2,5 Nm"}]})
		self.assertTrue(ok, motif)

	def test_compte_different(self):
		self.assertFalse(T.verifier_lot(self.entree, {"items": [{"i": 0, "t": "x"}]})[0])

	def test_indice_manquant_ou_double(self):
		self.assertFalse(T.verifier_lot(self.entree, {"items": [{"i": 0, "t": "a 230"}, {"i": 0, "t": "b 2.5"}]})[0])
		self.assertFalse(T.verifier_lot(self.entree, {"items": [{"i": 0, "t": "a 230"}, {"i": 5, "t": "b 2.5"}]})[0])

	def test_nombre_perdu(self):
		ok, motif = T.verifier_lot(self.entree, {"items": [{"i": 0, "t": "Branchez l'alimentation."}, {"i": 1, "t": "Serrez à 2.5 Nm"}]})
		self.assertFalse(ok)
		self.assertIn("230", motif)

	def test_vide(self):
		self.assertFalse(T.verifier_lot(["a"], {"items": [{"i": 0, "t": "  "}]})[0])
		self.assertFalse(T.verifier_lot(["a"], {"nope": 1})[0])

	def test_nombres(self):
		self.assertEqual(T.nombres("2,5 Nm et 230 V et 3.14"), {"2.5", "230", "3.14"})
