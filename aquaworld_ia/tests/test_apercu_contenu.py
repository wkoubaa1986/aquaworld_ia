import unittest

from aquaworld_ia.emballage import composition as C


class TestTexteCommunAuPlanEtPdf(unittest.TestCase):
	def test_nom_reel_et_typographie_sans_interpreter_le_html(self):
		z = {"zone": "nom", "w": 100, "h": 20, "typo": {"taille": 18, "align": "left", "gras": False},
		     "style": {"texte": "#123456"}}
		h = C.html_zone({"nom_produit": '<img src=x onerror="alert(1)"> & Robinet'}, z, {}, {}, set())
		self.assertNotIn("<img", h)
		self.assertIn("&lt;img", h)
		self.assertIn("&amp; Robinet", h)
		for propriete in ("font-size:18.0pt", "text-align:left", "font-weight:400", "color:#123456"):
			self.assertIn(propriete, h)
		self.assertIn("ARTICLE", C.html_zone({"article": "ARTICLE"}, z, {}, {}, set()))

	def test_textes_canoniques_multilingues_et_mise_en_forme(self):
		t = {"fr": {"caracteristiques": ["{14pt, gras} Débit 5 L/min"]}, "ar": {"caracteristiques": ["ماء"]}}
		h = C.html_zone({}, {"zone": "caracteristiques"}, t, {"ar": {"rtl": True}}, set())
		for attendu in ("Débit 5 L/min", "font-size:14.0pt", "font-weight:700", "ماء", "direction:rtl"):
			self.assertIn(attendu, h)
		self.assertNotIn("{14pt", h)
		self.assertEqual(C.html_zone({}, {"zone": "contact"}, t, {}, set()), "")

	def test_texte_libre_et_cartouche_du_nom(self):
		z = {"zone": "texte_libre", "texte": "Ligne 1\n\nLigne 3", "typo": {"italique": True}}
		h = C.html_zone({}, z, {}, {}, set())
		self.assertIn("Ligne 1", h)
		self.assertIn("font-style:italic", h)
		self.assertIn("&#160;", h)
		z = {"zone": "nom", "w": 30, "h": 10, "style": {"fond": "#123456"}}
		taille = C.taille_nom(C.MM(26), C.MM(6), "Un produit long")
		self.assertIn("font-size:%.1fpt" % taille, C.html_zone({"nom_produit": "Un produit long"}, z, {}, {}, set()))

	def test_nom_de_police_ne_peut_pas_ouvrir_un_attribut_html(self):
		h = C.html_bloc(["Robinet"], taille_pt=10, rtl=False, famille='Police" onmouseover="alert(1)')
		self.assertNotIn('" onmouseover="', h)
		self.assertIn("&quot;", h)
