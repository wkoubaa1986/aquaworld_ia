"""Vérifie la position réelle des images, la pagination et la validation des dispositions."""

import io
import shutil
import unittest

from aquaworld_ia.documents_produit import latex as L
from aquaworld_ia.documents_produit import mise_en_page as M
from aquaworld_ia.tests.test_documents_produit import contenu_simple, contexte_simple


class TestMiseEnPage(unittest.TestCase):
	def test_validation_et_compatibilite(self):
		ctx = contexte_simple()
		self.assertEqual(M.appliquer(ctx, {}, "Fiche technique"), ctx)
		for valeur in (
			{"couleur": "red}\\input{/etc/passwd}"}, {"largeur_photo": float("inf")},
			{"hauteur_photo": True}, {"ordre": ["presentation"] * 5},
			{"ordre": [[], 1, 2, 3, 4]}, {"position_photo": "inconnue"},
			{"commande": "\\input"}, {"largeur_photo": 100},
			{"largeur_logo": 100}, {"largeur_logo": True}, {"largeur_logo": "32"},
			{"position_marque": "ailleurs"}, {"alignement_marque": "\\input"},
			{"afficher_nom_marque": "1"},
			{"logo_x": float("nan")}, {"logo_y": float("inf")}, {"logo_x": "20"},
			{"logo_y": True}, {"logo_x": -1}, {"logo_y": 298},
		):
			with self.subTest(valeur=valeur), self.assertRaises(ValueError):
				M.normaliser(valeur)
		with self.assertRaises(ValueError):
			M.configuration({"inconnu": {}})
		self.assertEqual(M.normaliser({"position_photo": "gauche"})["largeur_photo"], 55)
		ancien = M.normaliser({"position_photo": "droite", "largeur_photo": 40})
		self.assertEqual(M.normaliser({**ancien, **M.MARQUE_DEFAUTS}), ancien)
		ctx["mise_en_page"] = ancien
		self.assertEqual(M.appliquer(ctx, {"mises_en_page": {"fiche": ancien}}, "Fiche technique"), ctx)
		libre = M.normaliser({"position_marque": "libre", "largeur_logo": 70,
			"afficher_nom_marque": 1, "logo_x": 210, "logo_y": 297})
		self.assertEqual(libre["logo_x"], 140)
		self.assertLessEqual(libre["logo_y"] + M.hauteur_zone_marque(libre), 297)

	@unittest.skipUnless(shutil.which("xelatex"), "XeLaTeX requis")
	def test_logo_libre_coordonnees_exactes_premiere_page_et_rtl(self):
		import pymupdf
		from PIL import Image

		im = io.BytesIO()
		Image.new("RGB", (200, 100), "#176b44").save(im, format="PNG")
		ctx = contexte_simple()
		c = contenu_simple(ctx)
		c["sections"][0]["texte"] = "Description technique du produit. " * 500
		pdf_initial, _ = L.compiler(L.source(c, ctx), {})
		ctx["mise_en_page"] = M.normaliser({"position_marque": "libre", "logo_x": 120.4,
			"logo_y": 70.6, "largeur_logo": 32, "afficher_nom_marque": 1})
		pdf, _ = L.compiler(L.source(c, ctx, assets={"logo": "images/logo.png"}), {"images/logo.png": im.getvalue()})
		with pymupdf.open(stream=pdf, filetype="pdf") as doc, pymupdf.open(stream=pdf_initial, filetype="pdf") as initial:
			self.assertEqual(len(doc), len(initial))
			self.assertGreater(len(doc), 1)
			logo = doc[0].get_image_rects(doc[0].get_images()[0][0])[0]
			self.assertAlmostEqual(logo.x0, 120.4 * 72 / 25.4, delta=.3)
			self.assertAlmostEqual(logo.y0, 70.6 * 72 / 25.4, delta=.3)
			self.assertAlmostEqual(logo.width, 32 * 72 / 25.4, delta=.3)
			for page in list(doc)[1:]:
				self.assertTrue(all(not page.get_image_rects(img[0]) for img in page.get_images()))
			self.assertEqual(doc[0].search_for("Fiche technique"), initial[0].search_for("Fiche technique"))
		c.update(titre="دليل الاستخدام", resume="جهاز لتنقية المياه ecoPurium", sections=[])
		pdf, _ = L.compiler(L.source(c, ctx, langue="ar", rtl=True, assets={"logo": "images/logo.png"}), {"images/logo.png": im.getvalue()})
		with pymupdf.open(stream=pdf, filetype="pdf") as doc:
			logo = doc[0].get_image_rects(doc[0].get_images()[0][0])[0]
			self.assertAlmostEqual(logo.x0, 120.4 * 72 / 25.4, delta=.3)
			self.assertAlmostEqual(logo.y0, 70.6 * 72 / 25.4, delta=.3)

	@unittest.skipUnless(shutil.which("xelatex"), "XeLaTeX requis")
	def test_zone_marque_positions_alignement_et_masquage(self):
		import pymupdf
		from PIL import Image

		im = io.BytesIO()
		Image.new("RGB", (200, 100), "#176b44").save(im, format="PNG")
		ctx = contexte_simple()
		ctx["logo"] = "/files/logo-test.png"
		for position, alignement, largeur in (
			("avant_titre", "gauche", 24), ("apres_titre", "centre", 40),
			("fin_document", "droite", 50), ("masquee", "gauche", 32),
		):
			with self.subTest(position=position):
				ctx["mise_en_page"] = M.normaliser({"position_marque": position,
					"alignement_marque": alignement, "largeur_logo": largeur, "afficher_nom_marque": 1})
				tex = L.source(contenu_simple(ctx), ctx, assets={"logo": "images/logo.png"})
				pdf, _ = L.compiler(tex, {"images/logo.png": im.getvalue()})
				with pymupdf.open(stream=pdf, filetype="pdf") as doc:
					if position == "masquee":
						self.assertTrue(all(not p.get_images() for p in doc))
						continue
					page = next(p for p in doc if p.get_images())
					logo = page.get_image_rects(page.get_images()[0][0])[0]
					self.assertTrue(page.rect.contains(logo))
					self.assertAlmostEqual(logo.width, largeur * 72 / 25.4, delta=1)
					if alignement == "gauche":
						self.assertAlmostEqual(logo.x0, 18 * 72 / 25.4, delta=1)
					elif alignement == "centre":
						self.assertAlmostEqual((logo.x0 + logo.x1) / 2, page.rect.width / 2, delta=1)
					else:
						self.assertAlmostEqual(logo.x1, page.rect.width - 18 * 72 / 25.4, delta=1)
					if position == "avant_titre":
						self.assertLess(logo.y1, page.search_for("Fiche technique")[0].y0)
					elif position == "apres_titre":
						self.assertGreater(logo.y0, page.search_for("Fiche technique")[0].y1)
					else:
						self.assertGreater(logo.y0, page.search_for("Variantes couvertes")[0].y1)
				self.assertIn(r"{\bfseries ecoPurium}\par", tex)

	def test_lien_woocommerce_du_produit(self):
		from aquaworld_ia.documents_produit import contexte as C

		# Adresse par identifiant : WordPress la redirige (301) vers la page publique du produit, et elle survit à un
		# changement de slug — ce qui compte pour un QR imprimé. Les variations (id d'une variante) ne sont pas des
		# pages : seul l'article parent est utilisé.
		self.assertEqual(C.url_produit_woocommerce("https://aquaworldservicing.com", 1343),
			"https://aquaworldservicing.com/?post_type=product&p=1343")
		self.assertEqual(C.url_produit_woocommerce("https://aquaworldservicing.com/", "1343"),
			"https://aquaworldservicing.com/?post_type=product&p=1343")
		for serveur, identifiant in (("", 1), ("https://x.com", 0), ("https://x.com", "abc"), ("ftp://x.com", 1), (None, 1)):
			with self.subTest(serveur=serveur, identifiant=identifiant):
				self.assertEqual(C.url_produit_woocommerce(serveur, identifiant), "")
		self.assertTrue(M.QR_URL.fullmatch(C.url_produit_woocommerce("https://aquaworldservicing.com", 1343)))

	def test_qr_code_validation_et_defauts(self):
		base = M.normaliser({"qr_url": "https://example.invalid/p/AP-M?x=1#top", "qr_legende": " Fiche en ligne ", "qr_taille": 30})
		self.assertEqual(base["qr_legende"], "Fiche en ligne")
		self.assertEqual(base["qr_taille"], 30)
		self.assertNotIn("qr_position", base)          # valeur par défaut retirée : ne périme pas les versions
		self.assertEqual(M.qr_valide(base), "https://example.invalid/p/AP-M?x=1#top")
		self.assertEqual(M.qr_valide(M.normaliser({"qr_legende": "x"})), "")
		for mauvais in ({"qr_url": "ftp://x"}, {"qr_url": "javascript:alert(1)"}, {"qr_url": "https://x.com/a b"},
			{"qr_url": "x" * 501}, {"qr_taille": 50}, {"qr_taille": 22.5}, {"qr_position": "libre"},
			{"qr_alignement": "justifie"}, {"qr_legende": "x" * 121}):
			with self.subTest(mauvais=mauvais), self.assertRaises(ValueError):
				M.normaliser(mauvais)

	@unittest.skipUnless(shutil.which("xelatex"), "XeLaTeX requis")
	def test_qr_code_positions_legende_et_lien_cliquable(self):
		import pymupdf

		ctx = contexte_simple()
		url = "https://example.invalid/produit/AP-M?x=1#top"
		for position, alignement in (("fin_document", "droite"), ("avant_titre", "gauche"), ("apres_titre", "centre")):
			with self.subTest(position=position):
				ctx["mise_en_page"] = M.normaliser({"qr_url": url, "qr_legende": "Fiche produit en ligne",
					"qr_position": position, "qr_alignement": alignement, "qr_taille": 25})
				tex, pdf, _ = L.composer(contenu_simple(ctx), ctx)
				self.assertIn(r"\href{https://example.invalid/produit/AP-M?x=1\#top}", tex)
				with pymupdf.open(stream=pdf, filetype="pdf") as doc:
					page = next(p for p in doc if p.get_images())
					qr = page.get_image_rects(page.get_images()[0][0])[0]
					self.assertAlmostEqual(qr.width, 25 * 72 / 25.4, delta=1)
					legende = page.search_for("Fiche produit en ligne")[0]
					self.assertGreaterEqual(legende.y0, qr.y1 - 1)
					self.assertEqual([l["uri"] for l in page.get_links() if l.get("uri")], [url])
					titre = page.search_for("Fiche technique")[0]
					if alignement == "gauche":
						self.assertAlmostEqual(qr.x0, 18 * 72 / 25.4, delta=1)
					elif alignement == "centre":
						self.assertAlmostEqual((qr.x0 + qr.x1) / 2, page.rect.width / 2, delta=1)
					else:
						self.assertAlmostEqual(qr.x1, page.rect.width - 18 * 72 / 25.4, delta=1)
					self.assertEqual(qr.y1 < titre.y0, position == "avant_titre")
		# Dans « Autres illustrations », sans autre photo : le bloc n'a que son titre et le QR, à sa place dans l'ordre.
		ctx["mise_en_page"] = M.normaliser({"qr_url": url, "qr_legende": "Fiche produit en ligne", "qr_position": "illustrations",
			"ordre": ["presentation", "illustrations", "rubriques", "caracteristiques", "variantes"]})
		_, pdf, _ = L.composer(contenu_simple(ctx), ctx)
		with pymupdf.open(stream=pdf, filetype="pdf") as doc:
			page = doc[0]
			qr = page.get_image_rects(page.get_images()[0][0])[0]
			libelle = contenu_simple(ctx)["libelles"]["illustrations"]
			titre_bloc = page.search_for(libelle)[0]
			self.assertLess(titre_bloc.y1, qr.y0)
			self.assertLess(qr.y1, page.search_for("Utilisation")[0].y0)   # avant les rubriques, comme l'ordre le demande
		ctx["mise_en_page"] = M.normaliser({"qr_legende": "Sans lien"})
		_, pdf, _ = L.composer(contenu_simple(ctx), ctx)
		with pymupdf.open(stream=pdf, filetype="pdf") as doc:
			self.assertTrue(all(not p.get_images() for p in doc))
			self.assertFalse(doc[0].search_for(libelle))

	@unittest.skipUnless(shutil.which("xelatex"), "XeLaTeX requis")
	def test_qr_code_vignette_de_la_galerie(self):
		"""Trois autres photos sur deux colonnes : le QR prend la case libre de la seconde ligne, à droite de la 3e photo."""
		import pymupdf
		from PIL import Image

		def png(couleur):
			b = io.BytesIO()
			Image.new("RGB", (300, 200), couleur).save(b, format="PNG")
			return b.getvalue()

		ctx = contexte_simple()
		ctx["images"] = [{"image": f"/files/{i}.png", "legende": f"Vue {i}", "article": ""} for i in range(4)]
		url = "https://example.invalid/?post_type=product&p=1343"
		ctx["mise_en_page"] = M.normaliser({"qr_url": url, "qr_legende": "Voir le produit en ligne",
			"qr_position": "illustrations", "qr_alignement": "centre", "colonnes_photos": 2})
		assets = {"images": [f"images/image-{i}.png" for i in range(4)], "qr": "images/qr.png"}
		fichiers = {f"images/image-{i}.png": png(c) for i, c in enumerate(("red", "green", "blue", "gray"))}
		fichiers["images/qr.png"] = L.qr_png(url)
		pdf, _ = L.compiler(L.source(contenu_simple(ctx), ctx, assets=assets), fichiers)
		with pymupdf.open(stream=pdf, filetype="pdf") as doc:
			page = next(p for p in doc if len(p.get_images()) >= 4)
			rects = [r for x in page.get_images() for r in page.get_image_rects(x[0])]
			qr = min(rects, key=lambda r: r.width)
			self.assertAlmostEqual(qr.width, 22 * 72 / 25.4, delta=1)
			voisines = [r for r in rects if r != qr and abs(r.y0 - qr.y0) < 20]
			self.assertEqual(len(voisines), 1)                    # la 3e photo, seule sur sa ligne avant le QR
			self.assertGreater(qr.x0, voisines[0].x1)             # le QR occupe la case de droite
			self.assertGreater(page.search_for("Voir le produit en ligne")[0].y0, qr.y1 - 1)

	@unittest.skipUnless(shutil.which("xelatex"), "XeLaTeX requis")
	def test_positions_pdf_et_ordre(self):
		import pymupdf
		from PIL import Image

		im = io.BytesIO()
		Image.new("RGB", (180, 120), "teal").save(im, format="PNG")
		for position in ("avant", "apres", "gauche", "droite"):
			with self.subTest(position=position):
				ctx = contexte_simple()
				ctx["images"] = [{"image": "/files/test.png", "legende": "Photo de test", "article": ""}]
				ctx["mise_en_page"] = M.normaliser({"position_photo": position, "largeur_photo": 40,
					"ordre": ["caracteristiques", "presentation", "rubriques", "variantes", "illustrations"]})
				c = contenu_simple(ctx)
				pdf, _ = L.compiler(L.source(c, ctx, assets={"images": ["images/image-0.png"]}), {"images/image-0.png": im.getvalue()})
				with pymupdf.open(stream=pdf, filetype="pdf") as doc:
					page = doc[0]
					photo = page.get_image_rects(page.get_images()[0][0])[0]
					resume = page.search_for("Un produit ecoPurium.")[0]
					self.assertTrue(page.rect.contains(photo))
					self.assertLess(page.search_for("Caractéristiques techniques")[0].y0, min(photo.y0, resume.y0))
					if position == "avant":
						self.assertLess(photo.y1, resume.y0)
					elif position == "apres":
						self.assertLess(resume.y1, photo.y0)
					elif position == "gauche":
						self.assertLess(photo.x1, resume.x0)
					else:
						self.assertLess(resume.x1, photo.x0)

	@unittest.skipUnless(shutil.which("xelatex"), "XeLaTeX requis")
	def test_colonnes_longues_et_arabe(self):
		import pymupdf
		from PIL import Image

		im = io.BytesIO()
		Image.new("RGB", (100, 180), "teal").save(im, format="PNG")
		ctx = contexte_simple()
		ctx["images"] = [{"image": "/files/test.png", "legende": "Illustration", "article": ""}]
		ctx["mise_en_page"] = M.normaliser({"position_photo": "droite", "largeur_photo": 35})
		c = contenu_simple(ctx)
		c["resume"] = "Description détaillée du produit. " * 160 + "FIN DESCRIPTION"
		pdf, _ = L.compiler(L.source(c, ctx, assets={"images": ["images/image-0.png"]}), {"images/image-0.png": im.getvalue()})
		with pymupdf.open(stream=pdf, filetype="pdf") as doc:
			self.assertGreater(len(doc), 1)
			texte = "".join(p.get_text() for p in doc)
			self.assertIn("FIN DESCRIPTION", texte)
			self.assertIn("Caractéristiques techniques", texte)
			for page in doc:
				for block in page.get_text("blocks"):
					self.assertLess(block[3], page.rect.height)
		c.update(titre="دليل الاستخدام", resume="جهاز لتنقية المياه ecoPurium")
		pdf, _ = L.compiler(L.source(c, ctx, langue="ar", rtl=True, assets={"images": ["images/image-0.png"]}), {"images/image-0.png": im.getvalue()})
		self.assertTrue(pdf.startswith(b"%PDF"))


class TestGalerieCompacte(unittest.TestCase):
	"""06/11/2026 : « une partie photos plus petite, en grille, pour tenir sur une seule page »."""

	def test_quatre_colonnes_et_hauteur_des_vignettes(self):
		d = M.normaliser({"colonnes_photos": 4, "hauteur_vignettes": 32})
		self.assertEqual((d["colonnes_photos"], d["hauteur_vignettes"]), (4, 32))
		self.assertNotIn("hauteur_vignettes", M.normaliser({"hauteur_vignettes": 55}))   # défaut retiré
		for mauvais in ({"colonnes_photos": 5}, {"hauteur_vignettes": 24}, {"hauteur_vignettes": 91}, {"hauteur_vignettes": 40.0}):
			with self.subTest(mauvais=mauvais), self.assertRaises(ValueError):
				M.normaliser(mauvais)

	@unittest.skipUnless(shutil.which("xelatex"), "XeLaTeX requis")
	def test_douze_photos_sur_une_page(self):
		import pymupdf
		from PIL import Image

		def png(i):
			b = io.BytesIO()
			Image.new("RGB", (400, 300), (40 * i % 255, 120, 180)).save(b, format="PNG")
			return b.getvalue()

		ctx = contexte_simple()
		ctx["images"] = [{"image": f"/files/{i}.png", "legende": f"Vue {i}", "article": ""} for i in range(13)]
		ctx["mise_en_page"] = M.normaliser({"colonnes_photos": 4, "hauteur_vignettes": 32})
		assets = {"images": [f"images/image-{i}.png" for i in range(13)]}
		pdf, _ = L.compiler(L.source(contenu_simple(ctx), ctx, assets=assets), {f"images/image-{i}.png": png(i) for i in range(13)})
		with pymupdf.open(stream=pdf, filetype="pdf") as doc:
			page = next(p for p in doc if p.search_for("Vue 12"))
			self.assertTrue(page.search_for("Vue 1"))                            # les 12 vignettes sur la même page
			rects = [r for x in page.get_images() for r in page.get_image_rects(x[0])]
			self.assertEqual(len(rects), 12)
			self.assertLessEqual(max(r.height for r in rects), 32 * 72 / 25.4 + 1)
			self.assertEqual(len({round(r.y0) for r in rects}), 3)              # trois lignes de quatre


class TestGalerieMosaique(unittest.TestCase):
	"""06/11/2026 : « une grosse photo et 3 à côté en grille » — style_galerie = mosaique."""

	def test_reglage(self):
		self.assertEqual(M.normaliser({"style_galerie": "mosaique"})["style_galerie"], "mosaique")
		self.assertNotIn("style_galerie", M.normaliser({"style_galerie": "grille"}))
		for mauvais in ({"style_galerie": "libre"}, {"style_galerie": 1}):
			with self.subTest(mauvais=mauvais), self.assertRaises(ValueError):
				M.normaliser(mauvais)

	@unittest.skipUnless(shutil.which("xelatex"), "XeLaTeX requis")
	def test_grande_a_gauche_trois_petites_a_droite_puis_grille(self):
		import pymupdf
		from PIL import Image

		def png(i):
			b = io.BytesIO()
			Image.new("RGB", (400, 300), (60 * i % 255, 110, 170)).save(b, format="PNG")
			return b.getvalue()

		ctx = contexte_simple()
		ctx["images"] = [{"image": f"/files/{i}.png", "legende": f"Vue {i}", "article": ""} for i in range(8)]
		ctx["mise_en_page"] = M.normaliser({"style_galerie": "mosaique", "hauteur_vignettes": 32, "colonnes_photos": 3})
		assets = {"images": [f"images/image-{i}.png" for i in range(8)], "dimensions": {f"images/image-{i}.png": (400, 300) for i in range(8)}}
		pdf, _ = L.compiler(L.source(contenu_simple(ctx), ctx, assets=assets), {f"images/image-{i}.png": png(i) for i in range(8)})
		with pymupdf.open(stream=pdf, filetype="pdf") as doc:
			page = next(p for p in doc if p.search_for("Vue 1"))
			haut = page.search_for("Photos et illustrations")[0].y1
			rects = [r for x in page.get_images() for r in page.get_image_rects(x[0]) if r.y0 > haut]
			grande = max(rects, key=lambda r: r.width * r.height)
			self.assertAlmostEqual(grande.x0, 18 * 72 / 25.4, delta=1)                     # à gauche
			self.assertAlmostEqual(grande.width, 0.62 * 174 * 72 / 25.4, delta=1 * 72 / 25.4)
			petites = [r for r in rects if r.x0 > grande.x1 - 1 and r.y0 < grande.y1]
			self.assertEqual(len(petites), 3)                                               # trois empilées à droite
			# Les petites gardent 32 mm ; la grande est centrée verticalement face à la colonne (06/11/2026).
			self.assertTrue(all(abs(r.height - 32 * 72 / 25.4) < 1 for r in petites))
			milieu_colonne = (min(r.y0 for r in petites) + max(r.y1 for r in petites)) / 2
			self.assertLess(abs((grande.y0 + grande.y1) / 2 - milieu_colonne), 10 * 72 / 25.4)
			self.assertEqual(len([r for r in rects if r.y0 > grande.y1 + 5]), 3)            # vues 5 à 7 en grille dessous
		# Avec une seule autre photo, pas de mosaïque : galerie ordinaire.
		ctx["images"] = ctx["images"][:2]
		assets = {"images": assets["images"][:2], "dimensions": {}}
		pdf, _ = L.compiler(L.source(contenu_simple(ctx), ctx, assets=assets), {f"images/image-{i}.png": png(i) for i in range(2)})
		with pymupdf.open(stream=pdf, filetype="pdf") as doc:
			self.assertTrue(any(p.search_for("Vue 1") for p in doc))

	@unittest.skipUnless(shutil.which("xelatex"), "XeLaTeX requis")
	def test_grande_designee_et_qr_comme_petite(self):
		"""06/11/2026 : « pourquoi le QR n'est pas considéré comme une image, comment changer qui est quoi »."""
		import pymupdf
		from PIL import Image

		def png(i):
			b = io.BytesIO()
			Image.new("RGB", (400, 300), (60 * i % 255, 110, 170)).save(b, format="PNG")
			return b.getvalue()

		self.assertEqual(M.normaliser({"photo_grande": "/files/3.png"})["photo_grande"], "/files/3.png")
		with self.assertRaises(ValueError):
			M.normaliser({"photo_grande": "https://x/y.png"})
		ctx = contexte_simple()
		ctx["images"] = [{"image": f"/files/{i}.png", "legende": f"Vue {i}", "article": ""} for i in range(4)]
		url = "https://example.invalid/?p=1"
		ctx["mise_en_page"] = M.normaliser({"style_galerie": "mosaique", "hauteur_vignettes": 32, "photo_grande": "/files/3.png",
			"qr_url": url, "qr_position": "illustrations", "qr_legende": "Voir en ligne"})
		assets = {"images": [f"images/image-{i}.png" for i in range(4)], "dimensions": {f"images/image-{i}.png": (400, 300) for i in range(4)}, "qr": "images/qr.png"}
		fichiers = {f"images/image-{i}.png": png(i) for i in range(4)}
		fichiers["images/qr.png"] = L.qr_png(url)
		pdf, _ = L.compiler(L.source(contenu_simple(ctx), ctx, assets=assets), fichiers)
		with pymupdf.open(stream=pdf, filetype="pdf") as doc:
			page = next(p for p in doc if p.search_for("Voir en ligne"))
			haut = page.search_for("Photos et illustrations")[0].y1
			rects = [r for x in page.get_images() for r in page.get_image_rects(x[0]) if r.y0 > haut]
			grande = max(rects, key=lambda r: r.width * r.height)
			legende = page.search_for("Vue 3")[0]
			self.assertTrue(abs(legende.x0 - grande.x0) < 30 and legende.y0 > grande.y1 - 1)   # la 3e photo est la grande
			self.assertEqual(len([r for r in rects if r.x0 > grande.x1 - 1 and r.y0 < grande.y1 + 2]), 3)   # 2 photos + QR
			self.assertEqual(len([r for r in rects if r.y0 > grande.y1 + 5]), 0)                             # rien dessous


class TestLegendesEtLargeurGrande(unittest.TestCase):
	"""06/11/2026 : « travailler la taille des photos pour tenir sur la première page, enlever les légendes des
	photos sauf celle du QR, changer le centrage et la couleur des légendes »."""

	def test_reglages(self):
		d = M.normaliser({"largeur_grande": 45, "legendes_galerie": 0, "legende_alignement": "centre", "legende_couleur": "titres"})
		self.assertEqual((d["largeur_grande"], d["legendes_galerie"], d["legende_alignement"], d["legende_couleur"]), (45, 0, "centre", "titres"))
		self.assertEqual(sorted(k for k in M.normaliser({"legendes_galerie": 1, "largeur_grande": 62}) if k.startswith(("legende", "largeur_g"))), [])
		for mauvais in ({"largeur_grande": 29}, {"largeur_grande": 76}, {"legendes_galerie": 2}, {"legende_alignement": "justifie"}, {"legende_couleur": "#FF0000"}):
			with self.subTest(mauvais=mauvais), self.assertRaises(ValueError):
				M.normaliser(mauvais)

	@unittest.skipUnless(shutil.which("xelatex"), "XeLaTeX requis")
	def test_pdf_legendes_masquees_sauf_qr_et_grande_a_45_pour_cent(self):
		import pymupdf
		from PIL import Image

		def png(i):
			b = io.BytesIO()
			Image.new("RGB", (400, 300), (60 * i % 255, 110, 170)).save(b, format="PNG")
			return b.getvalue()

		ctx = contexte_simple()
		ctx["images"] = [{"image": f"/files/{i}.png", "legende": f"Vue {i}", "article": ""} for i in range(5)]
		url = "https://example.invalid/?p=1"
		assets = {"images": [f"images/image-{i}.png" for i in range(5)], "dimensions": {f"images/image-{i}.png": (400, 300) for i in range(5)}, "qr": "images/qr.png"}
		fichiers = {f"images/image-{i}.png": png(i) for i in range(5)}
		fichiers["images/qr.png"] = L.qr_png(url)
		ctx["mise_en_page"] = M.normaliser({"style_galerie": "mosaique", "largeur_grande": 45, "legendes_galerie": 0,
			"qr_url": url, "qr_position": "illustrations", "qr_legende": "Voir en ligne"})
		pdf, _ = L.compiler(L.source(contenu_simple(ctx), ctx, assets=assets), fichiers)
		with pymupdf.open(stream=pdf, filetype="pdf") as doc:
			texte = " ".join(" ".join(p.get_text() for p in doc).split())
			self.assertNotIn("Vue 1", texte)                                  # légendes des photos masquées
			self.assertIn("Voir en ligne", texte)                             # celle du QR reste
			page = next(p for p in doc if p.search_for("Photos et illustrations"))
			haut = page.search_for("Photos et illustrations")[0].y1
			grande = max((r for x in page.get_images() for r in page.get_image_rects(x[0]) if r.y0 > haut), key=lambda r: r.width * r.height)
			self.assertAlmostEqual(grande.width, 0.45 * 174 * 72 / 25.4, delta=1 * 72 / 25.4)
		ctx["mise_en_page"] = M.normaliser({"colonnes_photos": 2, "legende_alignement": "centre", "legende_couleur": "titres"})
		tex = L.source(contenu_simple(ctx), ctx, assets=assets)
		self.assertIn(r"{\centering\color{aqua}\small Vue 1\par}", tex)


class TestLargeurMosaique(unittest.TestCase):
	"""06/11/2026 : « comment je fais pour centrer cette partie » — mosaïque moins large que la ligne, centrée."""

	def test_reglage(self):
		self.assertEqual(M.normaliser({"largeur_mosaique": 70})["largeur_mosaique"], 70)
		self.assertNotIn("largeur_mosaique", M.normaliser({"largeur_mosaique": 100}))
		for mauvais in ({"largeur_mosaique": 49}, {"largeur_mosaique": 101}, {"largeur_mosaique": "70"}):
			with self.subTest(mauvais=mauvais), self.assertRaises(ValueError):
				M.normaliser(mauvais)

	@unittest.skipUnless(shutil.which("xelatex"), "XeLaTeX requis")
	def test_mosaique_a_70_pour_cent_centree(self):
		import pymupdf
		from PIL import Image

		def png(i):
			b = io.BytesIO()
			Image.new("RGB", (400, 300), (60 * i % 255, 110, 170)).save(b, format="PNG")
			return b.getvalue()

		ctx = contexte_simple()
		ctx["images"] = [{"image": f"/files/{i}.png", "legende": f"Vue {i}", "article": ""} for i in range(5)]
		ctx["mise_en_page"] = M.normaliser({"style_galerie": "mosaique", "largeur_mosaique": 70, "largeur_grande": 60, "hauteur_vignettes": 30})
		assets = {"images": [f"images/image-{i}.png" for i in range(5)], "dimensions": {f"images/image-{i}.png": (400, 300) for i in range(5)}}
		pdf, _ = L.compiler(L.source(contenu_simple(ctx), ctx, assets=assets), {f"images/image-{i}.png": png(i) for i in range(5)})
		with pymupdf.open(stream=pdf, filetype="pdf") as doc:
			page = next(p for p in doc if p.search_for("Photos et illustrations"))
			haut = page.search_for("Photos et illustrations")[0].y1
			rects = [r for x in page.get_images() for r in page.get_image_rects(x[0]) if r.y0 > haut]
			grande = max(rects, key=lambda r: r.width * r.height)
			self.assertAlmostEqual(grande.width, 174 * 0.7 * 0.6 * 72 / 25.4, delta=1 * 72 / 25.4)   # 60 % de 70 % de la ligne
			self.assertGreater(grande.x0, (18 + 15) * 72 / 25.4)                                      # décalée vers le centre
