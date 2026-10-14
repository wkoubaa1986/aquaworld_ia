"""Mosaïque de variantes du produit (14/10/2026) — géométrie pure et rendu sur des images synthétiques."""
import io
import unittest

from aquaworld_ia.emballage import mosaique as M


def cases(n):
	return [{"url": "/files/p%d.png" % i, "legende": ""} for i in range(n)]


class TestGrille(unittest.TestCase):
	def test_automatique(self):
		self.assertEqual([M.grille(n) for n in (1, 2, 3, 4, 5, 6, 9, 10)],
		                 [(1, 1), (1, 2), (1, 3), (2, 2), (2, 3), (2, 3), (3, 3), (3, 4)])

	def test_dispositions_et_colonnes_imposees(self):
		self.assertEqual(M.grille(4, "rangee"), (1, 4))
		self.assertEqual(M.grille(4, "groupe"), (1, 4))
		self.assertEqual(M.grille(4, "colonne"), (4, 1))
		self.assertEqual(M.grille(5, "grille", 2), (3, 2))
		self.assertEqual(M.grille(3, "grille", 9), (1, 3))       # jamais plus de colonnes que de cases


class TestNormaliser(unittest.TestCase):
	def test_defauts_et_bornes(self):
		c = M.normaliser({"disposition": "spirale", "cases": cases(20) + [{"legende": "sans url"}], "couleur": "rouge",
		                  "entetes_colonnes": "Transparent\nOpaque bleu", "espacement": "?", "detourer": 0})
		self.assertEqual(c["disposition"], "grille")
		self.assertEqual(len(c["cases"]), M.MAX_CASES)
		self.assertEqual(c["couleur"], M.COULEUR_DEFAUT)
		self.assertEqual(c["entetes_colonnes"], ["Transparent", "Opaque bleu"])
		self.assertEqual((c["espacement"], c["cadre"], c["alignement"], c["fond"]), ("normal", "aucun", "pied", "transparent"))
		self.assertFalse(c["detourer"])
		self.assertTrue(M.normaliser({})["detourer"])


class TestPlan(unittest.TestCase):
	def test_planche_de_l_exemple_2x2_avec_en_tetes(self):
		"""TRANSPARENT / OPAQUE BLEU × MODÈLE A / B, titre et pied."""
		g = M.plan({"cases": cases(4), "titre": "For 10\" x 2.5\" cartridge", "pied": "Available range",
		            "entetes_colonnes": ["Transparent", "Opaque blue"], "entetes_lignes": ["Model A", "Model B"]}, [0.5] * 4, 1200)
		self.assertEqual((g["lignes"], g["colonnes"], len(g["cases"])), (2, 2, 4))
		self.assertEqual([e["texte"] for e in g["entetes_colonnes"]], ["Transparent", "Opaque blue"])
		self.assertEqual([e["texte"] for e in g["entetes_lignes"]], ["Model A", "Model B"])
		# les pastilles à gauche des produits, les en-têtes au-dessus des colonnes
		self.assertLess(g["entetes_lignes"][0]["x"] + g["entetes_lignes"][0]["w"], g["cases"][0]["x"])
		self.assertLess(g["entetes_colonnes"][0]["y"], g["cases"][0]["y"])
		self.assertIn("titre", g)
		self.assertGreater(g["pied"]["y"], g["cases"][-1]["y"] + g["cases"][-1]["h_img"])

	def test_meme_echelle_dans_une_rangee(self):
		g = M.plan({"cases": cases(3), "disposition": "rangee"}, [0.4, 0.6, 1.0], 1200)
		self.assertEqual(len({round(c["h_img"], 3) for c in g["cases"]}), 1)

	def test_derniere_ligne_centree(self):
		g = M.plan({"cases": cases(5), "colonnes": 3}, [1.0] * 5, 1200)
		haut = [c["x"] for c in g["cases"][:3]]
		bas = [c["x"] for c in g["cases"][3:]]
		self.assertGreater(bas[0], haut[0])           # 3 + 2 : la ligne du bas est décalée vers le centre
		self.assertAlmostEqual((bas[0] + bas[1] + g["cases"][3]["w"]) / 2, (haut[0] + haut[2] + g["cases"][0]["w"]) / 2, places=3)

	def test_heros_plus_grand_que_les_vignettes(self):
		g = M.plan({"cases": cases(4), "disposition": "heros"}, [0.5] * 4, 1200)
		h = g["cases"][0]
		self.assertTrue(all(h["w"] > c["w"] for c in g["cases"][1:]))
		self.assertTrue(all(c["x"] > h["x"] + h["w"] for c in g["cases"][1:]))

	def test_groupe_se_chevauche_et_le_centre_devant(self):
		g = M.plan({"cases": cases(3), "disposition": "groupe"}, [0.5, 0.5, 0.5], 1200)
		a, b, c = g["cases"]
		self.assertLess(b["x"], a["x"] + a["w"])      # b mord sur a
		self.assertEqual(max(g["cases"], key=lambda x: x["z"])["index"], 1)
		self.assertEqual(g["entetes_colonnes"], [])

	def test_cases_dans_la_planche(self):
		for disposition in M.DISPOSITIONS:
			for n in (2, 3, 4, 5, 7):
				g = M.plan({"cases": cases(n), "disposition": disposition, "cadre": "carte"}, [0.3, 0.8, 1.5, 0.5, 1.0, 0.7, 0.4][:n], 1200)
				for c in g["cases"]:
					self.assertGreaterEqual(c["x"], 0, (disposition, n))
					self.assertLessEqual(c["x"] + c["w"], g["largeur"] + 0.5, (disposition, n))
					self.assertLessEqual(c["y"] + c["h_img"], g["hauteur"], (disposition, n))


class TestRendu(unittest.TestCase):
	def test_png_transparent_aux_bonnes_dimensions(self):
		from PIL import Image

		images = [Image.new("RGBA", (100, 220), (30, 80, 200, 255)) for _ in range(4)]
		png = M.composer({"cases": cases(4), "titre": "Range", "entetes_colonnes": ["A", "B"], "entetes_lignes": ["1", "2"],
		                  "cadre": "trait"}, images, largeur=800)
		im = Image.open(io.BytesIO(png))
		self.assertEqual((im.mode, im.width), ("RGBA", 800))
		self.assertEqual(im.getpixel((2, 2))[3], 0)     # coin transparent

	def test_miroir_retourne_le_produit(self):
		from PIL import Image

		im = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
		im.paste((200, 0, 0, 255), (0, 0, 30, 100))          # bande rouge à GAUCHE
		cfg = {"cases": [{"url": "/files/a.png", "miroir": True}], "fond": "blanc", "disposition": "rangee"}
		out = Image.open(io.BytesIO(M.composer(cfg, [im], largeur=400))).convert("RGBA")
		g = M.plan(cfg, [1.0], 400)["cases"][0]
		milieu_y = round(g["y"] + g["h_img"] - 5)
		gauche = out.getpixel((round(g["x"] + 5), milieu_y))
		droite = out.getpixel((round(g["x"] + g["w"] - 5), milieu_y))
		self.assertGreater(droite[0] - droite[1], 100)        # la bande est passée à DROITE
		self.assertLess(gauche[0] - gauche[1], 50)
		self.assertTrue(M.normaliser(cfg)["cases"][0]["miroir"])
		self.assertFalse(M.normaliser({"cases": [{"url": "x"}]})["cases"][0]["miroir"])

	def test_taille_par_variante_et_meme_hauteur(self):
		from PIL import Image

		def largeur_posee(png, g, k):
			out = Image.open(io.BytesIO(png)).convert("RGBA")
			c = g["cases"][k]
			b = out.crop((round(c["x"]), round(c["y"]), round(c["x"] + c["w"]), round(c["y"] + c["h_img"]) + 1)).getchannel("A").getbbox()
			return (b[2] - b[0], b[3] - b[1]) if b else (0, 0)

		etroit, large = Image.new("RGBA", (100, 300), (0, 0, 200, 255)), Image.new("RGBA", (150, 300), (0, 0, 200, 255))
		cfg = {"cases": [{"url": "a"}, {"url": "b"}], "disposition": "rangee"}
		g = M.plan(cfg, [100 / 300, 150 / 300], 600)
		# même largeur (défaut) : les deux remplissent la largeur de leur case
		png = M.composer(cfg, [etroit, large], largeur=600)
		self.assertAlmostEqual(largeur_posee(png, g, 0)[0], largeur_posee(png, g, 1)[0], delta=2)
		# même hauteur : les deux à la même hauteur
		png = M.composer(dict(cfg, ajustement="hauteur"), [etroit, large], largeur=600)
		self.assertAlmostEqual(largeur_posee(png, g, 0)[1], largeur_posee(png, g, 1)[1], delta=2)
		# 80 % sur la 1re : 20 % plus petite
		png = M.composer({"cases": [{"url": "a", "taille": 80}, {"url": "b"}], "disposition": "rangee"}, [etroit, large], largeur=600)
		self.assertAlmostEqual(largeur_posee(png, g, 0)[0] / largeur_posee(png, g, 1)[0], 0.8, delta=0.03)
		self.assertEqual(M.normaliser({"cases": [{"url": "a", "taille": 500}]})["cases"][0]["taille"], M.TAILLE_MAX)

	def test_produit_detoure_rogne_le_blanc(self):
		from PIL import Image

		fond = Image.new("RGB", (300, 300), (255, 255, 255))
		fond.paste((20, 60, 180), (100, 50, 200, 250))
		buf = io.BytesIO()
		fond.save(buf, format="PNG")
		for detourer in (True, False):
			im = M.produit_detoure(buf.getvalue(), detourer=detourer)
			self.assertLessEqual(abs(im.width - 100), 4, detourer)
			self.assertLessEqual(abs(im.height - 200), 4, detourer)


if __name__ == "__main__":
	unittest.main()
