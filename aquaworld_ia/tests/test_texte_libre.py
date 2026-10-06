"""Zones « texte libre » et typographie par zone (demande utilisateur 06/10/2026) : ajouter une ou
plusieurs zones de texte que l'IA ne touche pas, et choisir pour chaque zone de texte sa police, sa
taille, gras/italique, son alignement et sa couleur."""
from __future__ import annotations

import inspect
import os
import unittest

import aquaworld_ia
from aquaworld_ia.emballage import composition as C
from aquaworld_ia.emballage import geometrie as G

FAMILLES = {"Noto Sans", "Montserrat", "EB Garamond"}


class TestTypoZone(unittest.TestCase):

	def test_normalise_et_borne(self):
		z = {"typo": {"police": " Montserrat ", "taille": "200", "gras": True, "italique": False, "align": "center"}}
		self.assertEqual(C.typo_zone(z, FAMILLES),
		                 {"police": "Montserrat", "taille": 120.0, "gras": True, "italique": False, "align": "center"})

	def test_police_inconnue_et_valeurs_invalides_ignorees(self):
		z = {"typo": {"police": "Police supprimée", "taille": "abc", "gras": "oui", "align": "milieu"}}
		self.assertEqual(C.typo_zone(z, FAMILLES), {})
		self.assertEqual(C.typo_zone({}, FAMILLES), {})
		self.assertEqual(C.typo_zone({"typo": {"taille": 2}}), {"taille": 4.0})


class TestZoneConservee(unittest.TestCase):
	FACE = {"x": 0, "y": 0, "w": 100, "h": 100, "imprimable": True}

	def test_texte_et_typo_survivent_au_bornage(self):
		z = {"zone": "texte_libre", "x": 10, "y": 10, "w": 50, "h": 20, "texte": "Made in Tunisia",
		     "typo": {"police": "Montserrat"}, "style": {"texte": "#ff0000"}}
		b = C.borner_zone(z, self.FACE)
		self.assertEqual((b["texte"], b["typo"], b["style"]), ("Made in Tunisia", {"police": "Montserrat"}, {"texte": "#ff0000"}))

	def test_plusieurs_textes_libres_sur_une_face(self):
		plan = {"faces": [dict(self.FACE, code="avant", libelle="Avant")]}
		mep = {"avant": [{"zone": "texte_libre", "x": 5, "y": 5, "w": 40, "h": 10, "texte": "A"},
		                 {"zone": "texte_libre", "x": 5, "y": 50, "w": 40, "h": 10, "texte": "B"}]}
		zones = C.appliquer_mise_en_page({"avant": []}, plan, mep)
		self.assertEqual([z["texte"] for z in zones["avant"]], ["A", "B"])

	def test_libelle_montre_le_debut_du_texte(self):
		self.assertEqual(G.libelle_zone({"zone": "texte_libre", "texte": "Fabriqué en Tunisie\nLot 12"}),
		                 "Texte libre : Fabriqué en Tunisie")
		self.assertEqual(G.libelle_zone({"zone": "texte_libre"}), "Texte libre")
		self.assertEqual(G.libelle_zone({"zone": "nom"}), "Nom du produit")


class TestHtmlTexteLibre(unittest.TestCase):

	def test_police_taille_couleur_gras_italique_alignement(self):
		h = C.html_texte_libre("Made in Tunisia", {"police": "Montserrat", "taille": 14, "gras": True, "italique": True,
		                                           "align": "right"}, "#ff0000", FAMILLES)
		for attendu in ("font-family:'Montserrat'", "font-size:14.0pt", "color:#ff0000", "font-weight:700",
		                "font-style:italic", "text-align:right", "Made in Tunisia"):
			self.assertIn(attendu, h)

	def test_valeurs_par_defaut_et_ligne_vide(self):
		h = C.html_texte_libre("Ligne 1\n\nLigne 3", {}, "#111827", FAMILLES)
		self.assertIn("font-family:'Noto Sans'", h)
		self.assertIn("font-size:10.0pt", h)
		self.assertEqual(h.count("<p"), 3)
		self.assertEqual(C.html_texte_libre("   ", {}, "#000000"), "")

	def test_arabe_de_droite_a_gauche_dans_la_police_arabe(self):
		h = C.html_texte_libre("صنع في تونس", {"police": "Montserrat"}, "#000000", FAMILLES)
		self.assertIn("direction:rtl", h)
		self.assertIn("Noto Naskh Arabic", h)
		self.assertNotIn("Montserrat", h)

	def test_mise_en_forme_par_ligne(self):
		h = C.html_texte_libre("{18pt, gras} Titre\nCorps", {"taille": 9}, "#000000", FAMILLES)
		self.assertIn("font-size:18.0pt", h)
		self.assertIn("font-size:9.0pt", h)


class TestTypoDesZonesIA(unittest.TestCase):
	TEXTES = {"en": {"accroche": "Pure water", "caracteristiques": ["5 stages"], "avertissements": ["Keep dry"],
	                 "contact": "contact@x.tn"}}
	LANGUES = {"en": {"code": "en", "rtl": 0}}

	def test_police_et_italique_de_la_zone(self):
		h = C.textes_pour_zone("caracteristiques", self.TEXTES, self.LANGUES, 8.5, "#000000", familles=FAMILLES,
		                       typo={"police": "EB Garamond", "italique": True, "align": "center"})
		self.assertIn("font-family:'EB Garamond'", h)
		self.assertIn("font-style:italic", h)
		self.assertIn("text-align:center", h)

	def test_accroche_peut_perdre_son_gras(self):
		gras = C.textes_pour_zone("accroche", self.TEXTES, self.LANGUES, 11, "#000000", familles=FAMILLES)
		maigre = C.textes_pour_zone("accroche", self.TEXTES, self.LANGUES, 11, "#000000", familles=FAMILLES, typo={"gras": False})
		self.assertIn("font-weight:700", gras)
		self.assertIn("font-weight:400", maigre)

	def test_la_police_de_zone_prime_sur_celle_des_caracteristiques(self):
		h = C.textes_pour_zone("caracteristiques", self.TEXTES, self.LANGUES, 8.5, "#000000", police_bloc="Montserrat",
		                       familles=FAMILLES, typo={"police": "EB Garamond"})
		self.assertIn("EB Garamond", h)
		self.assertNotIn("Montserrat", h)


class TestCablageStudio(unittest.TestCase):

	def test_le_studio_propose_le_texte_libre_et_la_typo(self):
		base = os.path.join(os.path.dirname(inspect.getfile(aquaworld_ia)), "aquaworld_ia", "page", "studio_emballage")
		with open(os.path.join(base, "studio_emballage.js"), encoding="utf-8") as fh:
			js = fh.read()
		self.assertEqual(js.count('"texte_libre", "pictos"'), 2)        # barre du plan + panneau de droite
		for morceau in ('data-prop="police"', 'data-prop="taille"', 'data-prop="italique"', 'data-prop="align"',
		                'data-prop="texte_libre"', "z.typo = ty", "_panneau_texte"):
			self.assertIn(morceau, js, morceau)
		self.assertIn("texte_libre", C.ZONES_AJOUTABLES)
		self.assertIn("typo", C.CLES_ZONE_CONSERVEES)


if __name__ == "__main__":
	unittest.main()
