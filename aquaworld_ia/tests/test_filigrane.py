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
			"filigrane_pages": "toutes", "filigrane_gris": 0, "filigrane_plan": "fond", "filigrane_detourer": 1}), M.normaliser())
		self.assertFalse([k for k in M.normaliser() if k.startswith("filigrane")])
		d = M.normaliser({"filigrane": 1, "filigrane_opacite": 12, "filigrane_rotation": 45, "filigrane_pages": "premiere"})
		self.assertEqual({k: v for k, v in d.items() if k.startswith("filigrane")},
			{"filigrane": 1, "filigrane_opacite": 12, "filigrane_rotation": 45, "filigrane_pages": "premiere"})
		self.assertEqual((M.valeur(d, "filigrane_largeur"), M.valeur(d, "filigrane_gris"), M.valeur({}, "filigrane"), M.valeur(None, "filigrane_opacite")), (60, 0, 0, 8))
		self.assertEqual((M.valeur(d, "filigrane_plan"), M.normaliser({"filigrane_plan": "dessus"})["filigrane_plan"]), ("fond", "dessus"))
		self.assertEqual(M.valeur({}, "colonnes_photos"), 1)                             # les autres réglages se lisent comme avant

	def test_valeurs_refusees(self):
		for invalide in ({"filigrane": 2}, {"filigrane": True}, {"filigrane_opacite": 2}, {"filigrane_opacite": 21}, {"filigrane_opacite": 8.5},
				{"filigrane_largeur": 10}, {"filigrane_rotation": 90}, {"filigrane_pages": "paires"}, {"filigrane_pages": 1}, {"filigrane_gris": "oui"}, {"filigrane_plan": "devant"}, {"filigrane_plan": 0}, {"filigrane_detourer": 2}):
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
			im = Image.open(io.BytesIO(L.filigrane_png(logo(fond=fond), opacite=10)))
			self.assertEqual((im.mode, im.size), ("RGB", (200, 140)), fond)             # rogné au dessin
			for obtenu, attendu in zip(im.getpixel((100, 70)), (229.5, 235.5, 249.5)):    # 10 % de (0, 60, 200) sur blanc
				self.assertAlmostEqual(obtenu, attendu, delta=1, msg=fond)
		plus = Image.open(io.BytesIO(L.filigrane_png(logo(), opacite=20))).getpixel((100, 70))
		for obtenu, attendu in zip(plus, (204, 216, 244)):
			self.assertAlmostEqual(obtenu, attendu, delta=1)

	def test_par_dessus_transparent(self):
		"""Le blanc du logo ne cache rien ; le dessin, vu sur blanc, a la même teinte que la version fondue."""
		im = Image.open(io.BytesIO(L.filigrane_png(logo(), opacite=10, transparent=True)))
		self.assertEqual((im.mode, im.size), ("RGBA", (200, 140)))
		r, g, b, a = im.getpixel((100, 70))
		self.assertAlmostEqual(a, 25.5, delta=1)                                        # 10 % d'une encre pleine
		sur_blanc = Image.alpha_composite(Image.new("RGBA", im.size, "white"), im).convert("RGB").getpixel((100, 70))
		fondu = Image.open(io.BytesIO(L.filigrane_png(logo(), opacite=10))).getpixel((100, 70))
		for x, y in zip(sur_blanc, fondu):
			self.assertAlmostEqual(x, y, delta=2)
		# un logo avec du blanc AUTOUR du dessin dans son cadre : ce blanc est transparent
		large = Image.new("RGBA", (400, 300), "white")
		large.paste((0, 60, 200, 255), (100, 80, 200, 220)); large.paste((0, 60, 200, 255), (260, 80, 300, 220))
		tampon = io.BytesIO(); large.save(tampon, "PNG")
		troue = Image.open(io.BytesIO(L.filigrane_png(tampon.getvalue(), opacite=10, transparent=True)))
		self.assertEqual(troue.getpixel((130, 70))[3], 0)                              # entre les deux rectangles
		self.assertGreater(troue.getpixel((10, 70))[3], 20)

	def test_gris_et_taille_bornee(self):
		r, g, b, _a = Image.open(io.BytesIO(L.filigrane_png(logo(), opacite=10, gris=True, transparent=True))).getpixel((100, 70))
		self.assertTrue(r == g == b)
		r, g, b = Image.open(io.BytesIO(L.filigrane_png(logo(), opacite=10, gris=True))).getpixel((100, 70))
		self.assertTrue(r == g == b and 225 < r < 255)
		grand = Image.open(io.BytesIO(L.filigrane_png(logo((4000, 3000)), max_cote=1400)))
		self.assertEqual(max(grand.size), 1400)

	def test_logo_livre_avec_l_app(self):
		self.assertTrue(L.FILIGRANE_LIVRE.exists())
		with patch("aquaworld_ia.ia.client.reglages", return_value={}):
			octets = L.logo_filigrane()
		self.assertEqual(octets, L.FILIGRANE_LIVRE.read_bytes())
		pale = Image.open(io.BytesIO(L.filigrane_png(octets)))
		self.assertGreater(min(pale.size), 300)
		self.assertGreater(min(pale.convert("L").getextrema()), 225)                    # très pâle : rien de plus foncé que du gris clair
		dessus = Image.open(io.BytesIO(L.filigrane_png(octets, transparent=True)))
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

	IMAGE = r"\AtPageCenter{\makebox(0,0){%s[width=0.60\paperwidth]{images/filigrane.png}}}"

	def test_en_arriere_plan_par_defaut(self):
		"""13/11/2026 : « j'ai l'impression qu'il est au-dessus, non en background ». Le logo est en fond de page ;
		le contenu est dessiné en mode « produit » (les aplats le laissent voir), les images en mode normal."""
		tex = self.source(filigrane=1)
		self.assertIn(r"\AddToShipoutPictureBG{\AWnormal " + self.IMAGE % r"\AWimage" + r"\AWproduit}", tex)
		self.assertIn(r"\renewcommand{\includegraphics}[2][]{\AWnormal\AWimage[#1]{#2}\AWproduit}", tex)
		self.assertIn("/AWproduit << /Type /ExtGState /BM /Multiply >>", tex)
		self.assertIn("/AWnormal << /Type /ExtGState /BM /Normal >>", tex)
		self.assertNotIn("AddToShipoutPictureFG{\\AtPageCenter", tex)
		# les modes sont déclarés sur chaque page, avant le logo
		self.assertLess(tex.index("pdf:put @resources"), tex.index(r"\AddToShipoutPictureBG{\AWnormal"))
		self.assertGreater(tex.index(r"\let\AWimage\includegraphics"), tex.index(r"\begin{document}"))
		for sans in (self.source(), self.source(filigrane_opacite=15)):                 # absent, ou réglé mais non activé
			self.assertNotIn("AWproduit", sans)
			self.assertNotIn(r"\AtPageCenter", sans)

	def test_par_dessus_tout(self):
		tex = self.source(filigrane=1, filigrane_plan="dessus")
		self.assertIn(r"\AddToShipoutPictureFG{" + self.IMAGE % r"\includegraphics" + "}", tex)
		self.assertNotIn("AWproduit", tex)

	def test_premiere_page_inclinaison_et_largeur(self):
		tex = self.source(filigrane=1, filigrane_pages="premiere", filigrane_rotation=45, filigrane_largeur=85)
		self.assertIn(r"\AddToShipoutPictureBG*{\AWnormal \AtPageCenter{\makebox(0,0){\rotatebox[origin=c]{45}{\AWimage[width=0.85\paperwidth]{images/filigrane.png}}}}\AWproduit}", tex)
		# les modes restent déclarés sur toutes les pages : les images des pages suivantes s'en servent
		self.assertIn(r"\AddToShipoutPictureBG{\special{pdf:put @resources", tex)
		dessus = self.source(filigrane=1, filigrane_pages="premiere", filigrane_plan="dessus")
		self.assertIn(r"\AddToShipoutPictureFG*{", dessus)

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
			r, g, b = image.getpixel((200, 200))
			self.assertTrue(image.mode == "RGB" and r == g == b)                         # en fond : fondu sur blanc, ici en gris
			self.assertIn(r"\AtPageCenter", vus["tex"])
			L.composer(contenu_simple(ctx), {**ctx, "mise_en_page": M.normaliser({"filigrane": 1, "filigrane_plan": "dessus"})})
			self.assertEqual(Image.open(io.BytesIO(vus["fichiers"]["images/filigrane.png"])).mode, "RGBA")  # par-dessus : transparent
			L.composer(contenu_simple(ctx), ctx)
			self.assertNotIn("images/filigrane.png", vus["fichiers"])
			self.assertNotIn(r"\AtPageCenter", vus["tex"])
			# un logo illisible : le document sort sans filigrane
			with patch.object(L, "logo_filigrane", return_value=b"pas une image"):
				L.composer(contenu_simple(ctx), {**ctx, "mise_en_page": M.normaliser({"filigrane": 1})})
			self.assertNotIn("images/filigrane.png", vus["fichiers"])
			self.assertNotIn(r"\AtPageCenter", vus["tex"])

	@unittest.skipUnless(shutil.which("xelatex"), "XeLaTeX absent")
	def test_compilation_reelle_tableau_et_photo(self):
		"""Le logo se voit à travers une ligne colorée du tableau ; une photo, elle, le recouvre."""
		import pymupdf

		ctx = contexte_simple()
		tampon = io.BytesIO()
		Image.new("RGB", (600, 600), "white").save(tampon, "PNG")                      # une « photo » toute blanche
		lignes = [{"nom": "Ligne %d" % i, "valeur": str(i), "unite": "", "article": "", "source": "Article TEST-P"} for i in range(34)]
		contenu = S.normaliser({**contenu_simple(ctx), "sections": [], "caracteristiques": lignes}, ctx)

		def page(reglages, photo=False):
			c = {**ctx, "mise_en_page": M.normaliser({"filigrane_largeur": 100, "filigrane_opacite": 20, **reglages}), "images": []}
			with patch("aquaworld_ia.ia.client.reglages", return_value={}), patch.object(L, "logo_filigrane", return_value=logo((400, 400))):
				tex = L.source(contenu, c, assets={"filigrane": "images/filigrane.png"} if reglages.get("filigrane") else {})
				fichiers = {"images/filigrane.png": L.filigrane_png(logo((400, 400)), 20)} if reglages.get("filigrane") else {}
				if photo:
					# une photo posée au milieu de la page, là où passe le logo
					tex = tex.replace(r"\end{document}", r"\AddToShipoutPictureFG*{\AtPageCenter{\makebox(0,0){\includegraphics[width=40mm]{images/image-0.png}}}}\end{document}")
					fichiers["images/image-0.png"] = tampon.getvalue()
				pdf, _zip = L.compiler(tex, fichiers)
			with pymupdf.open(stream=pdf, filetype="pdf") as doc:
				p = doc[0]
				texte = p.get_text()
				return p.get_pixmap(dpi=50), texte

		def bleu(pix, x_mm, y_mm):
			r, g, b = pix.pixel(int(x_mm / 25.4 * 50), int(y_mm / 25.4 * 50))[:3]
			return b - r                                                                 # le logo d'essai est bleu

		sans, _ = page({})
		avec, texte = page({"filigrane": 1})
		self.assertIn("Ligne 12", texte)                                                # le texte reste du texte
		# dans le tableau (ligne colorée), au cœur du logo : la teinte du logo s'ajoute à celle de la ligne
		point = (60, 150)
		self.assertGreater(bleu(avec, *point), bleu(sans, *point) + 20)


class TestPhotosDetourees(unittest.TestCase):
	"""13/11/2026 : « et les photos, comment j'enlève le background, le rendre transparent ? » — en arrière-plan, le
	fond blanc d'une photo cachait le logo : il est rendu transparent, le produit reste opaque."""

	def photo(self, fond="white", taille=(600, 500)):
		im = Image.new("RGB", taille, fond)
		im.paste((40, 40, 40), (200, 150, 400, 350))          # le produit, sombre
		im.paste((255, 255, 255), (260, 210, 340, 290))       # une partie blanche DANS le produit
		im.paste((240, 240, 240), (200, 360, 400, 380))       # son ombre portée, gris très clair, sur le fond
		b = io.BytesIO()
		im.save(b, "PNG")
		return b.getvalue()

	def test_seul_le_blanc_relie_au_bord_devient_transparent(self):
		L._CACHE_DETOURE.clear()
		im = Image.open(io.BytesIO(L.detourer_fond_blanc(self.photo())))
		self.assertEqual((im.mode, im.size), ("RGBA", (600, 500)))
		alpha = im.getchannel("A")
		for point in ((5, 5), (595, 495), (100, 250), (300, 60), (300, 450)):
			self.assertEqual(alpha.getpixel(point), 0, point)                           # le fond
		self.assertEqual(alpha.getpixel((230, 250)), 255)                               # le produit
		self.assertEqual(alpha.getpixel((300, 250)), 255)                               # son blanc intérieur reste opaque
		self.assertEqual(im.getpixel((300, 250))[:3], (255, 255, 255))
		self.assertTrue(60 < alpha.getpixel((300, 370)) < 200)                          # l'ombre : à moitié gardée
		self.assertEqual(im.getpixel((230, 250))[:3], (40, 40, 40))                     # les couleurs ne changent pas

	def test_images_laissees_telles_quelles(self):
		L._CACHE_DETOURE.clear()
		ambiance = self.photo(fond=(90, 140, 60))                                       # pas de fond blanc au bord
		self.assertEqual(L.detourer_fond_blanc(ambiance), ambiance)
		deja = Image.new("RGBA", (200, 200), (0, 0, 0, 0)); deja.paste((10, 20, 30, 255), (60, 60, 140, 140))
		tampon = io.BytesIO(); deja.save(tampon, "PNG")
		self.assertEqual(L.detourer_fond_blanc(tampon.getvalue()), tampon.getvalue())   # déjà détourée
		self.assertEqual(L.detourer_fond_blanc(b"pas une image"), b"pas une image")     # illisible : rendue telle quelle

	def test_grande_photo_rapide(self):
		import time

		L._CACHE_DETOURE.clear()
		grande = self.photo(taille=(2400, 2000))
		debut = time.time()
		im = Image.open(io.BytesIO(L.detourer_fond_blanc(grande)))
		self.assertLess(time.time() - debut, 6)
		self.assertEqual((im.size, im.getchannel("A").getpixel((20, 20))), ((2400, 2000), 0))
		debut = time.time(); L.detourer_fond_blanc(grande)
		self.assertLess(time.time() - debut, 0.2)                                       # en cache

	def test_seulement_avec_le_filigrane_en_arriere_plan(self):
		ctx = {**contexte_simple(), "images": [{"image": "/files/produit.png", "legende": "Vue", "article": "", "nom": "produit.png", "pages": ""}]}
		contenu = S.normaliser({**contenu_simple(), "legendes": ["Vue"]}, ctx)
		vus = {}

		def faux_compiler(tex, fichiers):
			vus["fichiers"] = dict(fichiers)
			return b"%PDF", b"zip"

		def mode(**reglages):
			with patch.object(L, "compiler", side_effect=faux_compiler), patch("aquaworld_ia.ia.client.reglages", return_value={}), \
				patch.object(L.C, "octets", return_value=self.photo()):
				L.composer(contenu, {**ctx, "mise_en_page": M.normaliser(reglages)})
			return Image.open(io.BytesIO(vus["fichiers"]["images/image-0.png"])).convert("RGBA").getpixel((5, 5))[3]   # opacité du fond

		self.assertEqual(mode(filigrane=1), 0)                                          # arrière-plan : fond de la photo transparent
		self.assertEqual(mode(filigrane=1, filigrane_detourer=0), 255)                  # option décochée
		self.assertEqual(mode(filigrane=1, filigrane_plan="dessus"), 255)               # par-dessus tout : inutile
		self.assertEqual(mode(), 255)                                                   # sans filigrane : photos inchangées
		self.assertEqual(mode(filigrane_detourer=1), 255)


if __name__ == "__main__":
	unittest.main()
