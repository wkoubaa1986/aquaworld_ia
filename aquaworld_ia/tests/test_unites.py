"""Unités métriques des caractéristiques : conversion calculée à la composition, valeur d'origine conservée."""

import unittest

from aquaworld_ia.documents_produit import unites as U


class TestUnitesMetriques(unittest.TestCase):
	def test_unites_du_catalogue(self):
		for valeur, unite, attendu in (
			("3.2", "G", "12,1 L (3.2 G)"),                 # l'exemple de la demande : réservoir en litres
			("3,2", "G", "12,1 L (3,2 G)"),
			("3,2 G", "", "12,1 L (3,2 G)"),                 # unité écrite dans la valeur
			("20G", "", "75,7 L (20G)"),
			("11", "gallons", "41,6 L (11 gallons)"),
			("75", "GPD", "284 L/jour (75 GPD)"),
			("400GPD", "", "1510 L/jour (400GPD)"),
			("12", "GPM", "45,4 L/min (12 GPM)"),
			("116", "psi", "8 bar (116 psi)"),
			("300", "PSI", "20,7 bar (300 PSI)"),
			("40 - 80", "psi", "2,76–5,52 bar (40 - 80 psi)"),
			("10", '"', '254 mm (10 ")'),
			("2.5", "pouces", "63,5 mm (2.5 pouces)"),
			('1/4"', "", '6,35 mm (1/4")'),
			('1 1/2"', "", '38,1 mm (1 1/2")'),
			("100", "°F", "37,8 °C (100 °F)"),
			("5", "lbs", "2,27 kg (5 lbs)"),
		):
			with self.subTest(valeur=valeur, unite=unite):
				self.assertEqual(U.afficher(valeur, unite, "Capacité"), attendu)

	def test_ce_qui_ne_se_convertit_pas(self):
		for nom, valeur, unite in (
			("Modèle", "PFC-1812-75G", ""),                  # une référence, pas une valeur
			("Capacité réservoir", "12", "L"),               # déjà métrique
			("Débit", "5", "L/h"),
			("Poids", "500", "g"),                           # « g » minuscule : des grammes
			("Pompe", "oui", ""),
			("Nombre de portes-filtres", "3", ""),
			("Marquage", "CE", ""),
			("Membrane", "Vontron 75 GPD", ""),              # du texte autour : laissé à l'auteur
			("Raccord d’entrée", "1/4", '"'),                # désignation nominale d'un raccord
			("Filetage", "3/4", "pouces"),
			("Sortie", '1/2"', ""),
			("Tension", "220", "V"),
			("", "", ""),
		):
			with self.subTest(nom=nom, valeur=valeur):
				self.assertIsNone(U.convertir(valeur, unite, nom))
				self.assertEqual(U.afficher(valeur, unite, nom), " ".join(f"{valeur} {unite}".split()))
		self.assertEqual(U.afficher("10", '"', "Longueur de cartouche"), '254 mm (10 ")')   # une vraie longueur en pouces

	def test_langue_et_deja_converti(self):
		self.assertEqual(U.afficher("3.2", "G", "Tank", "en"), "12.1 L (3.2 G)")
		self.assertEqual(U.afficher("75", "GPD", "Membrane", "en"), "284 L/day (75 GPD)")
		self.assertEqual(U.afficher("75", "GPD", "Membrane", "ar"), "284 L/d (75 GPD)")
		self.assertEqual(U.afficher("75", "GPD", "Membrane", "fr-TN"), "284 L/jour (75 GPD)")
		deja = U.afficher("3.2", "G", "Réservoir")
		self.assertEqual(U.afficher(deja, "", "Réservoir"), deja)                            # jamais converti deux fois
