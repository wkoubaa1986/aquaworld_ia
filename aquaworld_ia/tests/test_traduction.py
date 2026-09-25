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
		# sans séparateur : « 2,5 » et « 2.5 » sont le même nombre, « 1,100 » et « 1 100 » aussi
		self.assertEqual(T.nombres("2,5 Nm et 230 V et 3.14"), {"25", "230", "314"})


class TestNombresAvecSeparateurs(unittest.TestCase):
	"""« 1,100 gallons » traduit « 1 100 gallons » (ou « 1.100 ») n'a perdu aucun nombre."""

	def test_milliers(self):
		from aquaworld_ia.manuels.traduction import nombres, verifier_lot

		self.assertEqual(nombres("set the ELI to 1,100 gallons to assure a 1,000 gallon cycle."), {"1100", "1000"})
		self.assertEqual(nombres("régler l'ELI à 1 100 gallons pour un cycle de 1 000 gallons."), {"1100", "1000"})
		self.assertEqual(nombres("1.100 gallons"), nombres("1,100 gallons"))
		ok, _ = verifier_lot(["set the ELI to 1,100 gallons"], {"items": [{"i": 0, "t": "réglez l'ELI à 1\u202f100 gallons"}]})
		self.assertTrue(ok)

	def test_decimales_et_perte(self):
		from aquaworld_ia.manuels.traduction import nombres, verifier_lot

		self.assertEqual(nombres("Add 1TBSP (14.7ML)"), nombres("Ajoutez 1 c. à s. (14,7 ml)"))
		ok, motif = verifier_lot(["wait 20-30 minutes"], {"items": [{"i": 0, "t": "attendez 20 minutes"}]})
		self.assertFalse(ok)
		self.assertIn("30", motif)


class TestLotsParalleles(unittest.TestCase):
	"""Les lots partent en threads sans toucher à Frappe ; résultats remis dans l'ordre, journal différé."""

	def test_parallele_donne_le_meme_resultat(self):
		from unittest import mock

		from aquaworld_ia.manuels import traduction as T2

		def faux_differe(contexte, system, user):
			items = json.loads(user)["items"]
			return {"sortie": {"items": [{"i": it["i"], "t": "FR " + it["t"]} for it in items]}, "journal": {"appel": "chat", "modele": "x", "duree_ms": 1}}

		paras = [{"id": i, "texte": "Paragraph number %d about water" % i} for i in range(9)]
		avancement = []
		with mock.patch.object(T2, "chat_json_differe", faux_differe), \
		     mock.patch("aquaworld_ia.ia.client.client_et_modele", lambda usage="texte": ("client", "x", 0.2)), \
		     mock.patch("aquaworld_ia.ia.journal.enregistrer") as jr:
			trad, laisses = T2.traduire_tout(paras, {"code": "fr", "libelle": "Français"}, taille_lot=2, parallele=3,
			                                 progression=lambda f, t: avancement.append((f, t)))
		self.assertEqual(laisses, [])
		self.assertEqual(trad[4], "FR Paragraph number 4 about water")
		self.assertEqual(len(trad), 9)
		self.assertEqual(avancement[-1], (5, 5))          # 9 textes en lots de 2 = 5 lots
		self.assertEqual(jr.call_count, 5)                # une ligne de journal par lot, écrite après coup

	def test_lot_en_echec_reste_en_anglais(self):
		from unittest import mock

		from aquaworld_ia.manuels import traduction as T2

		with mock.patch.object(T2, "chat_json_differe", lambda c, s, u: {"sortie": None, "journal": {"appel": "chat", "modele": "x", "duree_ms": 1, "erreur": "boom"}}), \
		     mock.patch("aquaworld_ia.ia.client.client_et_modele", lambda usage="texte": ("client", "x", 0.2)), \
		     mock.patch("aquaworld_ia.ia.journal.enregistrer"):
			trad, laisses = T2.traduire_tout([{"id": 1, "texte": "Hello water"}, {"id": 2, "texte": "Bye water"}], {"code": "fr"}, taille_lot=1, parallele=2)
		self.assertEqual(sorted(laisses), [1, 2])
		self.assertEqual(trad, {})
