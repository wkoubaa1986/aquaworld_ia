"""Tampons SVG dessinés par l'IA (06/10/2026) : texte courbe converti lettre par lettre (MuPDF ignore
textPath), SVG nettoyé, rendu vérifié. Sans base ni appel IA : réponses fabriquées."""
from __future__ import annotations

import re
import unittest

from aquaworld_ia.emballage import tampon as T

REPONSE = {"tampons": [
	{"titre": "Rond plein", "svg": (
		'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" onload="alert(1)">'
		'<circle cx="100" cy="100" r="92" fill="#1e3a8a"/><circle cx="100" cy="100" r="80" fill="none" stroke="#ffffff" stroke-width="2"/>'
		'<texte-courbe cx="100" cy="100" r="66" centre="-90" sens="haut" taille="16" couleur="#ffffff">POIDS NET</texte-courbe>'
		'<texte-courbe cx="100" cy="100" r="66" centre="90" sens="bas" taille="12" couleur="#ffffff">SEL EN PASTILLES</texte-courbe>'
		'<text x="100" y="115" text-anchor="middle" font-family="Comic Sans MS" font-weight="bold" font-size="44" fill="#ffffff">25 KG</text>'
		'<script>alert(2)</script><image href="http://exemple.tn/x.png" width="10" height="10"/>'
		'<foreignObject><div>x</div></foreignObject></svg>')},
	{"titre": "Illisible", "svg": "<svg><circle"},
	{"titre": "Pas un svg", "svg": "<html></html>"},
]}


class TestTexteCourbe(unittest.TestCase):

	def test_une_lettre_par_element_sur_le_cercle(self):
		svg = T.courber_textes('<texte-courbe cx="100" cy="100" r="70" centre="-90" taille="14" couleur="#fff">ABC</texte-courbe>')
		lettres = re.findall(r'translate\(([-\d.]+),([-\d.]+)\) rotate\(([-\d.]+)\)[^>]*>(\w)<', svg)
		self.assertEqual([l[3] for l in lettres], ["A", "B", "C"])
		(xa, ya, ra, _a), (xb, yb, rb, _b), (xc, yc, rc, _c) = [(float(x), float(y), float(r), c) for x, y, r, c in lettres]
		self.assertAlmostEqual(xb, 100, delta=1.5)                        # la lettre du milieu est en haut du cercle
		self.assertAlmostEqual(yb, 30, delta=1)
		self.assertAlmostEqual(rb, 0, delta=2)                            # droite en haut
		self.assertLess(xa, xb)
		self.assertLess(xb, xc)
		self.assertAlmostEqual(ya, yc, delta=0.5)                         # symétrique

	def test_en_bas_le_texte_se_lit_de_gauche_a_droite(self):
		svg = T.courber_textes('<texte-courbe cx="100" cy="100" r="70" centre="90" sens="bas" taille="14">AB</texte-courbe>')
		(xa, ya, ra), (xb, yb, rb) = [(float(x), float(y), float(r)) for x, y, r in
		                              re.findall(r'translate\(([-\d.]+),([-\d.]+)\) rotate\(([-\d.]+)\)', svg)]
		self.assertLess(xa, xb)                                           # A à gauche de B
		self.assertGreater(ya, 100)                                       # en bas du cercle
		self.assertLess(abs(ra), 30)                                      # lettres droites, pas à l'envers

	def test_espaces_et_texte_vide(self):
		self.assertEqual(T.courber_textes('<texte-courbe>  </texte-courbe>'), "")
		svg = T.courber_textes('<texte-courbe>A B</texte-courbe>')
		self.assertEqual(len(re.findall(r"<text ", svg)), 2)              # l'espace compte dans l'angle, sans élément


class TestNettoyer(unittest.TestCase):

	def test_ne_garde_que_formes_et_texte(self):
		svg = T.nettoyer_svg(T.courber_textes(REPONSE["tampons"][0]["svg"]))
		for interdit in ("script", "onload", "image", "foreignObject", "exemple.tn", "Comic"):
			self.assertNotIn(interdit, svg)
		self.assertIn('font-family="Helvetica"', svg)
		self.assertIn("25 KG", svg)
		self.assertRegex(svg, r'<svg[^>]*width="200"[^>]*height="200"|<svg[^>]*height="200"[^>]*width="200"')

	def test_textpath_et_svg_illisible_rejetes(self):
		svg = T.nettoyer_svg('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><text><textPath href="#a">X</textPath></text></svg>')
		self.assertNotIn("textPath", svg)
		self.assertIsNone(T.nettoyer_svg("<svg><circle"))
		self.assertIsNone(T.nettoyer_svg("<html></html>"))

	def test_viewbox_ajoute_si_absent(self):
		svg = T.nettoyer_svg('<svg xmlns="http://www.w3.org/2000/svg" width="300" height="120"><rect width="300" height="120" fill="#000"/></svg>')
		self.assertIn('viewBox="0 0 300 120"', svg)


class TestPreparer(unittest.TestCase):

	def test_seules_les_propositions_imprimables_restent(self):
		import pymupdf

		tampons = T.preparer(REPONSE)
		self.assertEqual([t["titre"] for t in tampons], ["Rond plein"])
		page = pymupdf.open(stream=tampons[0]["svg"].encode(), filetype="svg")[0]
		texte = page.get_text()
		self.assertIn("25 KG", texte)
		for lettre in "POIDSNET":                                          # le texte courbe est bien rendu
			self.assertIn(lettre, texte)

	def test_prompt_porte_le_texte_les_couleurs_et_les_regles(self):
		system, user = T.prompts("POIDS NET\n25 KG", "rond", "plein", ["#1e3a8a", "#ffffff"], "artisanal", 3)
		self.assertIn("exactement 3 propositions", system)
		self.assertIn("texte-courbe", system)
		self.assertIn("INTERDITS : textPath", system)
		self.assertIn("POIDS NET\n25 KG", user)
		self.assertIn("#1e3a8a, #ffffff", user)
		self.assertIn("artisanal", user)


if __name__ == "__main__":
	unittest.main()
