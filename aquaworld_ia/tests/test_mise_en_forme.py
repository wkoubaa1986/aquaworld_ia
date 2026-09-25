"""Mise en forme ligne par ligne des caractéristiques (demande utilisateur 24/09/2026 : « plusieurs
tailles ligne par ligne, italique ou gras, et choisir la police »)."""
from __future__ import annotations

import os
import unittest

from aquaworld_ia.emballage import composition as C
from aquaworld_ia.emballage import mise_en_forme as M
from aquaworld_ia.emballage import textes as T
from aquaworld_ia.manuels import rendu as R


class TestPrefixe(unittest.TestCase):
	def test_analyser(self):
		self.assertEqual(M.analyser("{14pt, gras, italique, sans puce, police: EB Garamond} Débit 500 L/h"),
		                 ({"taille": 14.0, "gras": True, "italique": True, "puce": False, "police": "EB Garamond"},
		                  "Débit 500 L/h"))
		self.assertEqual(M.analyser("{9,5 pt} a"), ({"taille": 9.5}, "a"))
		self.assertEqual(M.analyser("{normal} SPECS"), ({}, "SPECS"))
		self.assertEqual(M.analyser("Housing: Blue"), (None, "Housing: Blue"))

	def test_un_prefixe_illisible_reste_du_texte(self):
		for l in ("{fett} x", "{200pt} x", "{police: a,b} x", "{police: \"x\"} x", "{gras x"):
			self.assertIsNone(M.analyser(l)[0], l)
			self.assertEqual(M.analyser(l)[1], l)

	def test_aller_retour(self):
		for l in ("{14pt, gras, italique, sans puce, police: Montserrat} Débit", "{puce} x", "{normal} ABC", "texte seul"):
			self.assertEqual(M.ecrire(*M.analyser(l)), l)
		self.assertEqual(M.ecrire({"taille": 9.0}, " a "), "{9pt} a")

	def test_style_a_reporter(self):
		self.assertEqual(M.style_a_reporter("SPECIFICATIONS"), {"gras": True, "puce": False})
		self.assertEqual(M.style_a_reporter("Inlet :"), {"gras": True, "puce": False})
		self.assertIsNone(M.style_a_reporter("Housing: Blue"))
		self.assertEqual(M.style_a_reporter("{italique} SPECS"), {"italique": True})


class TestReport(unittest.TestCase):
	"""Ce sont les textes préparés par l'IA qui s'impriment : la mise en forme doit les suivre."""

	def test_rang_pour_rang(self):
		self.assertEqual(M.reporter(["{gras} a", "b"], ["{italique} A", "B"]), ["{gras} A", "B"])
		self.assertIsNone(M.reporter(["a", "b"], ["A"]))

	def test_seuls_les_rangs_modifies(self):
		textes = {"en": {"caracteristiques": ["A", "{italique} B"]}, "nl": {"caracteristiques": ["x"]}}
		sortie, non = M.reporter_styles("{gras} a\nb", textes, avant="a\nb")
		self.assertEqual(sortie["en"]["caracteristiques"], ["{gras} A", "{italique} B"])   # la retouche EN reste
		self.assertEqual(non, ["nl"])
		self.assertEqual(sortie["nl"]["caracteristiques"], ["x"])

	def test_texte_change_sans_mise_en_forme(self):
		textes = {"en": {"caracteristiques": ["{italique} A"]}}
		sortie, non = M.reporter_styles("aa", textes, avant="a")
		self.assertIs(sortie, textes)
		self.assertEqual(non, [])

	def test_lignes_ajoutees_rien_n_est_reporte(self):
		textes = {"en": {"caracteristiques": ["A", "B"]}}
		self.assertIs(M.reporter_styles("{gras} a\nb", textes, avant="a\nb\nc")[0], textes)
		# Sans « avant » (textes tout juste préparés par l'IA) : tout est reporté.
		self.assertEqual(M.reporter_styles("{gras} a\nb", textes)[0]["en"]["caracteristiques"], ["{gras} A", "B"])

	def test_desalignes_seulement_avec_une_mise_en_forme_explicite(self):
		textes = {"en": {"caracteristiques": ["A"]}}
		self.assertEqual(M.desalignes("SPECS\nb", textes), [])
		self.assertEqual(M.desalignes("{gras} a\nb", textes), [{"code": "en", "lignes": 1, "brutes": 2}])

	def test_lignes_imprimables(self):
		self.assertEqual(M.lignes_imprimables("SPECS\n\nHousing: Blue\n{sans puce} ☐ 1/2″\nInlet :"),
		                 ["{gras, sans puce} SPECS", "Housing: Blue", "{sans puce} ☐ 1/2″", "{gras, sans puce} Inlet :"])

	def test_le_prompt_exige_une_entree_par_ligne(self):
		systeme, _u = T.prompt_preparation("P", "", ["a", "b", "c"], [], "", [{"code": "en"}], "", "", 1)
		self.assertIn("EXACTEMENT une entrée par ligne fournie (3 entrées)", systeme)


class TestRendu(unittest.TestCase):
	def test_taille_gras_italique_police_par_ligne(self):
		h = C.html_bloc(["{14pt, gras, italique, police: Montserrat} Titre", "b"], taille_pt=8.5, rtl=False,
		                famille="Noto Sans", puces=True, facteur=0.9, familles={"Montserrat", "Noto Sans"})
		premier, second = h.split("</p>")[:2]
		self.assertIn("font-family:'Montserrat';font-size:12.6pt", premier)
		self.assertIn("font-weight:700;font-style:italic", premier)
		self.assertIn("• Titre", premier)
		self.assertIn("font-family:'Noto Sans';font-size:8.5pt", second)
		self.assertIn("font-weight:400;font-style:normal", second)

	def test_police_inconnue_ou_langue_rtl(self):
		h = C.html_bloc(["{police: Disparue} a"], taille_pt=8, rtl=False, famille="Noto Sans", familles={"Noto Sans"})
		self.assertIn("font-family:'Noto Sans'", h)
		h = C.html_bloc(["{police: Montserrat, gras} a"], taille_pt=8, rtl=True, famille="Noto Naskh Arabic",
		                police_libre=False, familles={"Montserrat"})
		self.assertIn("font-family:'Noto Naskh Arabic'", h)
		self.assertIn("font-weight:700", h)
		self.assertFalse(C.police_libre({"rtl": 1}))
		self.assertFalse(C.police_libre({"police_fichier": "/files/x.ttf"}))
		self.assertTrue(C.police_libre({"police": "Noto Sans"}))

	def test_sans_puce_et_puce_forcee(self):
		self.assertNotIn(C.PUCE, C.html_bloc(["{sans puce} a"], taille_pt=8, rtl=False, famille="F", puces=True))
		self.assertIn(C.PUCE, C.html_bloc(["{puce} a"], taille_pt=8, rtl=False, famille="F", puces=False))

	def test_une_ligne_mise_en_forme_n_est_pas_un_intertitre_automatique(self):
		self.assertEqual(C.lignes_brutes("{normal} SPECS\nSPECS"), ["{normal} SPECS", "## SPECS"])
		self.assertIn("• SPECS", C.html_bloc(C.lignes_brutes("{normal} SPECS"), taille_pt=8, rtl=False, famille="F", puces=True))

	def test_police_du_bloc(self):
		t = {"fr": {"caracteristiques": ["a", "{police: Lato} b"]}, "ar": {"caracteristiques": ["ج"]}}
		langues = {"fr": {"code": "fr", "police": "Noto Sans"}, "ar": {"code": "ar", "rtl": 1, "police": "Noto Naskh Arabic"}}
		h = C.textes_pour_zone("caracteristiques", t, langues, 8.5, "#000", police_bloc="Oswald",
		                       familles={"Oswald", "Lato", "Noto Sans", "Noto Naskh Arabic"})
		self.assertIn("font-family:'Oswald';font-size:8.5pt", h)
		self.assertIn("font-family:'Lato'", h)
		self.assertIn("font-family:'Noto Naskh Arabic'", h)


class TestPolicesLivrees(unittest.TestCase):
	def test_les_fichiers_existent(self):
		for famille, fichiers in R.POLICES_LIVREES.items():
			for f in fichiers:
				if f:
					self.assertTrue(os.path.exists(os.path.join(R.CHEMIN_POLICES, f)), f)

	def test_css_italique(self):
		css = R.css_polices([], [("Ma Police", {"regulier": "/files/a.ttf", "italique": "/files/b.ttf"})])
		self.assertIn("font-family:'Montserrat';src:url(Montserrat-BoldItalic.ttf);font-weight:700;font-style:italic;", css)
		self.assertIn("font-family:'Ma Police';src:url(Ma_Police_italique.ttf);font-weight:400;font-style:italic;", css)
		self.assertNotIn("Ma_Police_gras.ttf", css)
		self.assertNotIn("Oswald-Italic", css)

	def test_frappe_est_importe_dans_rendu(self):
		"""Sans lui, les polices des Réglages étaient ignorées en silence (NameError avalé)."""
		self.assertTrue(hasattr(R, "frappe"))


if __name__ == "__main__":
	unittest.main()
