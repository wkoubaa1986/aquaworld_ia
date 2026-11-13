"""Logo en filigrane des fiches et manuels (demandes 09/11 et 13/11/2026 : « mon logo de l'entreprise très
transparent en arrière-plan sur toute la page », « le logo de la goutte sans le nom »)."""

import io
import shutil
import unittest
from unittest.mock import patch

from PIL import Image

from aquaworld_ia.documents_produit import latex as L
from aquaworld_ia.documents_produit import mise_en_page as M
from aquaworld_ia.documents_produit import structure as S
from aquaworld_ia.tests.test_documents_produit import contenu_simple, contexte_simple


def logo(taille=(400, 300), fond=(255, 255, 255, 255)):
	im = Image.new("RGBA", taille, fond)
	l, h = taille
	im.paste((0, 60, 200, 255), (l // 4, h * 4 // 15, l * 3 // 4, h * 11 // 15))      # un rectangle bleu au milieu (200 × 140 sur 400 × 300)
	b = io.BytesIO()
	im.save(b, "PNG")
	return b.getvalue()


class TestReglage(unittest.TestCase):
	def test_desactive_par_defaut_et_valeurs_par_defaut_non_ecrites(self):
		self.assertEqual(M.normaliser({"filigrane": 0, "filigrane_opacite": 8, "filigrane_largeur": 60, "filigrane_rotation": 0,
			"filigrane_pages": "toutes", "filigrane_gris": 0, "filigrane_plan": "dessus"}), M.normaliser())
		self.assertFalse([k for k in M.normaliser() if k.startswith("filigrane")])
		d = M.normaliser({"filigrane": 1, "filigrane_opacite": 12, "filigrane_rotation": 45, "filigrane_pages": "premiere"})
		self.assertEqual({k: v for k, v in d.items() if k.startswith("filigrane")},
			{"filigrane": 1, "filigrane_opacite": 12, "filigrane_rotation": 45, "filigrane_pages": "premiere"})
		self.assertEqual((M.valeur(d, "filigrane_largeur"), M.valeur(d, "filigrane_gris"), M.valeur({}, "filigrane"), M.valeur(None, "filigrane_opacite")), (60, 0, 0, 8))
		self.assertEqual((M.valeur(d, "filigrane_plan"), M.normaliser({"filigrane_plan": "fond"})["filigrane_plan"]), ("dessus", "fond"))
		self.assertEqual(M.valeur({}, "colonnes_photos"), 1)                             # les autres réglages se lisent comme avant

	def test_valeurs_refusees(self):
		for invalide in ({"filigrane": 2}, {"filigrane": True}, {"filigrane_opacite": 2}, {"filigrane_opacite": 21}, {"filigrane_opacite": 8.5},
				{"filigrane_largeur": 10}, {"filigrane_rotation": 90}, {"filigrane_pages": "paires"}, {"filigrane_pages": 1}, {"filigrane_gris": "oui"}, {"filigrane_plan": "devant"}, {"filigrane_plan": 0}):
			with self.subTest(invalide=invalide), self.assertRaises(ValueError):
				M.normaliser(invalide)

	def test_le_filigrane_suit_la_mise_en_page_du_dossier(self):
		dossier = {"mises_en_page": '{"fiche": {"filigrane": 1, "filigrane_largeur": 80}}'}
		self.assertEqual(M.appliquer({}, dossier, "Fiche technique")["mise_en_page"]["filigrane_largeur"], 80)
		self.assertNotIn("mise_en_page", M.appliquer({}, dossier, "Manuel d'utilisation"))
		self.assertEqual(M.portable({"filigrane": 1, "filigrane_gris": 1})["filigrane_gris"], 1)      # repris pour un autre produit


class TestImage(unittest.TestCase):
	def test_en_fond_rogne_et_eclairci_sur_blanc(self):
		for fond in ((255, 255, 255, 255), (0, 0, 0, 0)):                              # logo sur blanc, ou sur transparent
			im = Image.open(io.BytesIO(L.filigrane_png(logo(fond=fond), opacite=10, transparent=False)))
			self.assertEqual((im.mode, im.size), ("RGB", (200, 140)), fond)             # rogné au dessin
			for obtenu, attendu in zip(im.getpixel((100, 70)), (229.5, 235.5, 249.5)):    # 10 % de (0, 60, 200) sur blanc
				self.assertAlmostEqual(obtenu, attendu, delta=1, msg=fond)
		plus = Image.open(io.BytesIO(L.filigrane_png(logo(), opacite=20, transparent=False))).getpixel((100, 70))
		for obtenu, attendu in zip(plus, (204, 216, 244)):
			self.assertAlmostEqual(obtenu, attendu, delta=1)

	def test_par_dessus_transparent(self):
		"""Le blanc du logo ne cache rien ; le dessin, vu sur blanc, a la même teinte que la version fondue."""
		im = Image.open(io.BytesIO(L.filigrane_png(logo(), opacite=10)))
		self.assertEqual((im.mode, im.size), ("RGBA", (200, 140)))
		r, g, b, a = im.getpixel((100, 70))
		self.assertAlmostEqual(a, 25.5, delta=1)                                        # 10 % d'une encre pleine
		sur_blanc = Image.alpha_composite(Image.new("RGBA", im.size, "white"), im).convert("RGB").getpixel((100, 70))
		fondu = Image.open(io.BytesIO(L.filigrane_png(logo(), opacite=10, transparent=False))).getpixel((100, 70))
		for x, y in zip(sur_blanc, fondu):
			self.assertAlmostEqual(x, y, delta=2)
		# un logo avec du blanc AUTOUR du dessin dans son cadre : ce blanc est transparent
		large = Image.new("RGBA", (400, 300), "white")
		large.paste((0, 60, 200, 255), (100, 80, 200, 220)); large.paste((0, 60, 200, 255), (260, 80, 300, 220))
		tampon = io.BytesIO(); large.save(tampon, "PNG")
		troue = Image.open(io.BytesIO(L.filigrane_png(tampon.getvalue(), opacite=10)))
		self.assertEqual(troue.getpixel((130, 70))[3], 0)                              # entre les deux rectangles
		self.assertGreater(troue.getpixel((10, 70))[3], 20)

	def test_gris_et_taille_bornee(self):
		r, g, b, _a = Image.open(io.BytesIO(L.filigrane_png(logo(), opacite=10, gris=True))).getpixel((100, 70))
		self.assertTrue(r == g == b)
		r, g, b = Image.open(io.BytesIO(L.filigrane_png(logo(), opacite=10, gris=True, transparent=False))).getpixel((100, 70))
		self.assertTrue(r == g == b and 225 < r < 255)
		grand = Image.open(io.BytesIO(L.filigrane_png(logo((4000, 3000)), max_cote=1400)))
		self.assertEqual(max(grand.size), 1400)

	def test_logo_livre_avec_l_app(self):
		self.assertTrue(L.FILIGRANE_LIVRE.exists())
		with patch("aquaworld_ia.ia.client.reglages", return_value={}):
			octets = L.logo_filigrane()
		self.assertEqual(octets, L.FILIGRANE_LIVRE.read_bytes())
		pale = Image.open(io.BytesIO(L.filigrane_png(octets, transparent=False)))
		self.assertGreater(min(pale.size), 300)
		self.assertGreater(min(pale.convert("L").getextrema()), 225)                    # très pâle : rien de plus foncé que du gris clair
		dessus = Image.open(io.BytesIO(L.filigrane_png(octets)))
		self.assertLessEqual(dessus.getchannel("A").getextrema()[1], 21)                # 8 % au plus : ce qui est dessous reste lisible

	def test_logo_des_reglages_puis_repli(self):
		with patch("aquaworld_ia.ia.client.reglages", return_value={"logo_filigrane": "/files/mon-logo.png"}):
			with patch("aquaworld_ia.ia.fichiers.lire", return_value=b"octets du logo") as lire:
				self.assertEqual(L.logo_filigrane(), b"octets du logo")
				lire.assert_called_once_with("/files/mon-logo.png")
			with patch("aquaworld_ia.ia.fichiers.lire", side_effect=OSError("fichier absent")):
				self.assertEqual(L.logo_filigrane(), L.FILIGRANE_LIVRE.read_bytes())


class TestPdf(unittest.TestCase):
	def source(self, **reglages):
		ctx = contexte_simple()
		ctx["mise_en_page"] = M.normaliser(reglages)
		return L.source(contenu_simple(ctx), ctx, assets={"filigrane": "images/filigrane.png"} if reglages.get("filigrane") else {})

	def test_pose_en_fond_de_page(self):
		tex = self.source(filigrane=1)
		# par défaut : par-dessus le contenu, visible sur toute la page
		self.assertIn(r"\AddToShipoutPictureFG{\AtPageCenter{\makebox(0,0){\includegraphics[width=0.60\paperwidth]{images/filigrane.png}}}}", tex)
		fond = self.source(filigrane=1, filigrane_plan="fond")
		self.assertIn(r"\AddToShipoutPictureBG{\AtPageCenter{\makebox(0,0){\includegraphics[width=0.60\paperwidth]{images/filigrane.png}}}}", fond)
		self.assertNotIn("filigrane", self.source())
		self.assertNotIn("\\AtPageCenter", self.source(filigrane_opacite=15))            # réglé mais non activé

	def test_premiere_page_inclinaison_et_largeur(self):
		tex = self.source(filigrane=1, filigrane_pages="premiere", filigrane_rotation=45, filigrane_largeur=85)
		self.assertIn(r"\AddToShipoutPictureFG*{\AtPageCenter{\makebox(0,0){\rotatebox[origin=c]{45}{\includegraphics[width=0.85\paperwidth]{images/filigrane.png}}}}}", tex)

	def test_composition_avec_et_sans(self):
		ctx = contexte_simple()
		vus = {}

		def faux_compiler(tex, fichiers):
			vus["tex"], vus["fichiers"] = tex, dict(fichiers)
			return b"%PDF", b"zip"

		with patch.object(L, "compiler", side_effect=faux_compiler), patch("aquaworld_ia.ia.client.reglages", return_value={}):
			L.composer(contenu_simple(ctx), {**ctx, "mise_en_page": M.normaliser({"filigrane": 1, "filigrane_opacite": 5, "filigrane_gris": 1})})
			self.assertIn("images/filigrane.png", vus["fichiers"])
			image = Image.open(io.BytesIO(vus["fichiers"]["images/filigrane.png"]))
			r, g, b, _a = image.getpixel((200, 200))
			self.assertTrue(image.mode == "RGBA" and r == g == b)                        # par-dessus : transparent, ici en gris
			self.assertIn(r"\AtPageCenter", vus["tex"])
			L.composer(contenu_simple(ctx), {**ctx, "mise_en_page": M.normaliser({"filigrane": 1, "filigrane_plan": "fond"})})
			self.assertEqual(Image.open(io.BytesIO(vus["fichiers"]["images/filigrane.png"])).mode, "RGB")   # en fond : fondu sur blanc
			L.composer(contenu_simple(ctx), ctx)
			self.assertNotIn("images/filigrane.png", vus["fichiers"])
			self.assertNotIn(r"\AtPageCenter", vus["tex"])
			# un logo illisible : le document sort sans filigrane
			with patch.object(L, "logo_filigrane", return_value=b"pas une image"):
				L.composer(contenu_simple(ctx), {**ctx, "mise_en_page": M.normaliser({"filigrane": 1})})
			self.assertNotIn("images/filigrane.png", vus["fichiers"])
			self.assertNotIn(r"\AtPageCenter", vus["tex"])

	@unittest.skipUnless(shutil.which("xelatex"), "XeLaTeX absent")
	def test_compilation_reelle(self):
		import pymupdf

		ctx = contexte_simple()
		ctx["mise_en_page"] = M.normaliser({"filigrane": 1, "filigrane_opacite": 20, "filigrane_rotation": 30})
		with patch("aquaworld_ia.ia.client.reglages", return_value={}):
			_tex, pdf, _zip = L.composer(contenu_simple(ctx), ctx)
		with pymupdf.open(stream=pdf, filetype="pdf") as doc:
			page = doc[0]
			images = page.get_image_info()
			self.assertEqual(len(images), 1)
			x0, y0, x1, y1 = images[0]["bbox"]
			self.assertAlmostEqual((x0 + x1) / 2, page.rect.width / 2, delta=3)         # centré sur la page
			self.assertAlmostEqual((y0 + y1) / 2, page.rect.height / 2, delta=3)
			self.assertIn("Osmoseur", page.get_text())                                  # le texte reste du texte, par-dessus


if __name__ == "__main__":
	unittest.main()
