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
						self.assertGreater(logo.y0, page.search_for("Gamme et configurations")[0].y1)
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
		# Dans le bloc des photos, sans autre photo : le bloc n'a que son titre et le QR, à sa place dans l'ordre.
		# C'est la position par défaut depuis le 12/11/2026 (« toujours intégré dans photos et illustrations ») :
		# elle n'est pas écrite, alors que « fin_document », devenu un choix, l'est.
		ctx["mise_en_page"] = M.normaliser({"qr_url": url, "qr_legende": "Fiche produit en ligne",
			"ordre": ["presentation", "illustrations", "rubriques", "caracteristiques", "variantes"]})
		self.assertNotIn("qr_position", ctx["mise_en_page"])
		self.assertNotIn("qr_position", M.normaliser({"qr_url": url, "qr_position": "illustrations"}))
		self.assertEqual(M.normaliser({"qr_url": url, "qr_position": "fin_document"})["qr_position"], "fin_document")
		self.assertEqual(M.QR_DEFAUTS["qr_position"], "illustrations")
		self.assertNotIn("qr_position", M.initiale(url)["fiche"])                      # le QR posé d'office y va aussi
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
			"qr_position": "illustrations", "qr_alignement": "centre", "colonnes_photos": 2, "style_galerie": "grille"})
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


class TestLeProduitEnImages(unittest.TestCase):
	"""12/11/2026 : la section s'appelle « Le produit en images », vient en deuxième par défaut, titre toujours imprimé."""

	def test_ordre_par_defaut_et_libelle(self):
		from aquaworld_ia.documents_produit import structure as S

		self.assertEqual(M.normaliser()["ordre"], ["presentation", "illustrations", "rubriques", "caracteristiques", "variantes"])
		self.assertEqual(sorted(M.ORDRE_DEFAUT), sorted(M.ORDRE))
		ancien = M.normaliser({"ordre": list(M.ORDRE)})                         # un ordre choisi est respecté
		self.assertEqual(ancien["ordre"][-1], "illustrations")
		ctx = contexte_simple()
		c = contenu_simple(ctx)
		self.assertEqual(c["libelles"]["illustrations"], "Le produit en images")
		# Une version enregistrée sous l'ancien nom suit le nouveau ; une traduction garde le sien.
		self.assertEqual(S.normaliser({**c, "libelles": {**c["libelles"], "illustrations": "Photos et illustrations"}}, ctx)["libelles"]["illustrations"], "Le produit en images")
		self.assertEqual(S.normaliser({**c, "libelles": {**c["libelles"], "illustrations": "Product pictures"}}, ctx)["libelles"]["illustrations"], "Product pictures")

	def test_titre_imprime_et_bloc_avant_les_rubriques(self):
		ctx = contexte_simple()
		ctx["images"] = [{"image": "/files/a.png", "legende": "Principale", "article": ""}, {"image": "/files/b.png", "legende": "Vue arrière", "article": ""}]
		tex = L.source(contenu_simple(ctx), ctx, assets={"images": ["images/image-0.png", "images/image-1.png"]})
		titre = r"\docsectionsouple{Le produit en images}"
		self.assertIn(titre, tex)                                               # même avec une photo par ligne
		self.assertLess(tex.index(titre), tex.index(r"\docsection{Utilisation}"))
		self.assertLess(tex.index(titre), tex.index(r"\docsection{Caractéristiques techniques}"))
		ctx["images"] = ctx["images"][:1]                                       # rien à montrer : pas de titre
		self.assertNotIn(titre, L.source(contenu_simple(ctx), ctx, assets={"images": ["images/image-0.png"]}))


class TestDossierPrerempli(unittest.TestCase):
	"""12/11/2026 : à la création d'un dossier, les photos de l'article et le QR code du produit sur le site."""

	def test_qr_du_site_sur_la_fiche_et_le_manuel(self):
		url = "https://aquaworldservicing.com/?post_type=product&p=1343"
		depart = M.initiale(url)
		self.assertEqual(set(depart), {"fiche", "manuel"})
		for disposition in depart.values():
			self.assertEqual((disposition["qr_url"], disposition["qr_legende"]), (url, "Voir le produit en ligne"))
		self.assertEqual(M.configuration(depart), depart)                       # enregistrable tel quel
		self.assertEqual(M.pour_document({"mises_en_page": __import__("json").dumps(depart)}, "Fiche technique")["qr_url"], url)
		self.assertIsNot(depart["fiche"], depart["manuel"])
		for absent in ("", None, "aquaworldservicing.com", "javascript:alert(1)", "https://a.tn/" + "x" * 500):
			with self.subTest(absent=absent):
				self.assertEqual(M.initiale(absent), {})                          # article hors du site : rien

	def test_photos_sans_doublon_et_dans_la_limite(self):
		from aquaworld_ia.documents_produit.photos import retenir_initiales

		lignes = retenir_initiales([
			{"image": "/files/variante.jpg", "legende": "Variante", "article": "P-V", "hash": "a"},
			{"image": "/files/parent.jpg", "legende": "Produit", "article": "", "hash": "b"},
			{"image": "/files/parent-copie.jpg", "legende": "copie", "article": "", "hash": "b"},   # même contenu
			{"image": "/files/parent.jpg", "legende": "encore", "article": "", "hash": ""},        # même adresse
			{"image": "/files/vue.jpg", "legende": None, "article": None, "hash": None},
			{"image": "/files/vue.jpg", "legende": "bis", "article": "", "hash": None},
		])
		self.assertEqual(lignes, [
			{"image": "/files/variante.jpg", "legende": "Variante", "article": "P-V"},
			{"image": "/files/parent.jpg", "legende": "Produit", "article": ""},
			{"image": "/files/vue.jpg", "legende": "", "article": ""},
		])
		beaucoup = [{"image": f"/files/{i}.jpg", "legende": "", "article": "", "hash": str(i)} for i in range(30)]
		self.assertEqual(len(retenir_initiales(beaucoup)), 20)                  # limite d'un dossier
		self.assertEqual(retenir_initiales([]), [])

	def test_photos_manquantes_d_un_dossier_existant(self):
		"""12/11/2026 : les dossiers déjà créés reçoivent les images de l'article qui leur manquent, à la suite."""
		from aquaworld_ia.documents_produit.photos import manquantes

		existantes = [{"image": "/files/AP-M.jpg", "hash": "a"}, {"image": "/files/choisie.jpg", "hash": "c"}]
		candidates = [
			{"image": "/files/AP-M.jpg", "legende": "Osmoseur", "article": "", "hash": "a"},        # déjà là (adresse)
			{"image": "/files/AP-M-copie.jpg", "legende": "", "article": "", "hash": "c"},         # déjà là (contenu)
			{"image": "/files/AP-M-A.jpg", "legende": "", "article": "", "hash": "b"},
		]
		self.assertEqual(manquantes(existantes, candidates), [{"image": "/files/AP-M-A.jpg", "legende": "", "article": ""}])
		self.assertEqual(manquantes(existantes, candidates[:2]), [])                             # rien à ajouter
		self.assertEqual(manquantes([], candidates[2:]), [{"image": "/files/AP-M-A.jpg", "legende": "", "article": ""}])
		pleines = [{"image": f"/files/{i}.jpg", "hash": str(i)} for i in range(19)]
		deux = [{"image": f"/files/n{i}.jpg", "legende": "", "article": "", "hash": f"n{i}"} for i in range(2)]
		self.assertEqual(len(manquantes(pleines, deux)), 1)                                      # 20 photos au plus par dossier
		self.assertEqual(manquantes(pleines + [{"image": "/files/19.jpg", "hash": "19"}], deux), [])


class TestCentrageVertical(unittest.TestCase):
	"""12/11/2026 : « centrer l'écriture par rapport à l'image verticalement » (présentation en deux colonnes)."""

	def test_reglage(self):
		self.assertEqual(M.normaliser({"alignement_vertical_photo": "centre"})["alignement_vertical_photo"], "centre")
		# Le défaut est retiré : les versions déjà enregistrées ne deviennent pas « à actualiser ».
		self.assertNotIn("alignement_vertical_photo", M.normaliser({"alignement_vertical_photo": "haut"}))
		self.assertEqual(M.normaliser({"alignement_vertical_photo": "haut"}), M.normaliser())
		self.assertEqual(M.portable({"alignement_vertical_photo": "centre"})["alignement_vertical_photo"], "centre")
		for mauvais in ("bas", "", 1, None):
			with self.subTest(mauvais=mauvais), self.assertRaises(ValueError):
				M.normaliser({"alignement_vertical_photo": mauvais})

	def test_source_inchangee_sans_le_reglage(self):
		ctx = contexte_simple()
		ctx["images"] = [{"image": "/files/test.png", "legende": "Photo", "article": ""}]
		sources = {}
		for valign in ("haut", "centre"):
			ctx["mise_en_page"] = M.normaliser({"position_photo": "droite", "alignement_vertical_photo": valign})
			sources[valign] = L.source(contenu_simple(ctx), ctx, assets={"images": ["images/image-0.png"]})
		self.assertNotIn("dpboitetexte", sources["haut"])
		self.assertIn(r"\usebox{\dpboitetexte}", sources["centre"])
		# En une colonne, le réglage n'a pas d'effet.
		ctx["mise_en_page"] = M.normaliser({"position_photo": "apres", "alignement_vertical_photo": "centre"})
		self.assertNotIn("dpboitetexte", L.source(contenu_simple(ctx), ctx, assets={"images": ["images/image-0.png"]}))

	def _pdf(self, position, valign, resume, legende="Photo de test", **kw):
		from PIL import Image

		im = io.BytesIO()
		Image.new("RGB", (120, 180), "teal").save(im, format="PNG")
		ctx = contexte_simple()
		ctx["images"] = [{"image": "/files/test.png", "legende": legende, "article": ""}]
		ctx["mise_en_page"] = M.normaliser({"position_photo": position, "largeur_photo": 40, "hauteur_photo": 80,
			"alignement_vertical_photo": valign})
		c = contenu_simple(ctx)
		c["resume"] = resume
		return L.compiler(L.source(c, ctx, assets={"images": ["images/image-0.png"]}, **kw), {"images/image-0.png": im.getvalue()})[0]

	@unittest.skipUnless(shutil.which("xelatex"), "XeLaTeX requis")
	def test_texte_au_milieu_de_la_photo(self):
		import pymupdf

		court = "Osmoseur compact pour la cuisine. " * 6
		for position in ("gauche", "droite"):
			for legende in ("Photo de test", ""):
				with self.subTest(position=position, legende=legende):
					milieux = {}
					for valign in ("haut", "centre"):
						with pymupdf.open(stream=self._pdf(position, valign, court, legende), filetype="pdf") as doc:
							page = doc[0]
							photo = page.get_image_rects(page.get_images()[0][0])[0]
							lignes = page.search_for("Osmoseur compact")
							haut, bas = min(r.y0 for r in lignes), max(r.y1 for r in lignes)
							milieux[valign] = ((haut + bas) / 2, (photo.y0 + photo.y1) / 2, haut, photo.y0)
							if position == "gauche":
								self.assertLess(photo.x1, min(r.x0 for r in lignes))
							else:
								self.assertLess(max(r.x1 for r in lignes), photo.x0)
					texte, image, haut, haut_photo = milieux["centre"]
					self.assertLess(abs(texte - image), 6)             # milieu du texte = milieu de l'image, légende non comptée
					texte, image, haut, haut_photo = milieux["haut"]
					self.assertLess(abs(haut - haut_photo), 20)         # sans le réglage : alignés par le haut, comme avant
					self.assertGreater(image - texte, 40)

	@unittest.skipUnless(shutil.which("xelatex"), "XeLaTeX requis")
	def test_description_longue_reste_secable_et_arabe(self):
		import pymupdf

		pdf = self._pdf("droite", "centre", "Description détaillée du produit. " * 160 + "XYZ9")
		with pymupdf.open(stream=pdf, filetype="pdf") as doc:
			self.assertGreater(len(doc), 1)                        # un bloc insécable aurait débordé de la page
			self.assertIn("XYZ9", "".join(p.get_text() for p in doc))
			for page in doc:
				for block in page.get_text("blocks"):
					self.assertLess(block[3], page.rect.height)
		pdf = self._pdf("droite", "centre", "جهاز لتنقية المياه ecoPurium", langue="ar", rtl=True)
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
		ctx["mise_en_page"] = M.normaliser({"style_galerie": "grille", "colonnes_photos": 4, "hauteur_vignettes": 32, "ordre": list(M.ORDRE)})   # galerie en fin de document
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
		# La mosaïque est la disposition par défaut depuis le 12/11/2026 : elle n'est pas écrite, la grille l'est.
		self.assertNotIn("style_galerie", M.normaliser({"style_galerie": "mosaique"}))
		self.assertEqual(M.normaliser({"style_galerie": "grille"})["style_galerie"], "grille")
		self.assertEqual(M.valeur(M.normaliser(), "style_galerie"), "mosaique")
		self.assertEqual(M.valeur({"style_galerie": "grille"}, "style_galerie"), "grille")
		for mauvais in ({"style_galerie": "colonnes"}, {"style_galerie": 1}):
			with self.subTest(mauvais=mauvais), self.assertRaises(ValueError):
				M.normaliser(mauvais)

	def _mosaique(self, images, resume, **reglages):
		import pymupdf
		from PIL import Image

		def png(i):
			b = io.BytesIO()
			Image.new("RGB", (300, 400), (60 * i % 255, 110, 170)).save(b, format="PNG")   # portrait : la hauteur commande
			return b.getvalue()

		ctx = contexte_simple()
		ctx["images"] = [{"image": f"/files/{i}.png", "legende": f"Vue {i}", "article": ""} for i in range(images)]
		ctx["mise_en_page"] = M.normaliser(reglages)                                      # mosaïque et 2e position : les défauts
		c = contenu_simple(ctx)
		c["resume"] = resume
		assets = {"images": [f"images/image-{i}.png" for i in range(images)], "dimensions": {}}
		pdf, _ = L.compiler(L.source(c, ctx, assets=assets), {f"images/image-{i}.png": png(i) for i in range(images)})
		doc = pymupdf.open(stream=pdf, filetype="pdf")
		page = next(p for p in doc if p.search_for("Le produit en images"))
		haut = page.search_for("Le produit en images")[0].y1
		rects = [r for x in page.get_images() for r in page.get_image_rects(x[0]) if r.y0 > haut]
		return doc, page, rects

	@unittest.skipUnless(shutil.which("xelatex"), "XeLaTeX requis")
	def test_par_defaut_et_reduite_a_la_place_qui_reste(self):
		"""12/11/2026 : mosaïque par défaut ; « resizer automatiquement les photos dans l'espace de la page d'avant »."""
		mm = 72 / 25.4
		# Assez de place : les petites ont la hauteur réglée (ici 28 mm), la mosaïque n'est pas réduite.
		doc, page, rects = self._mosaique(5, "Un produit ecoPurium.", hauteur_vignettes=28)
		self.assertEqual(page.number, 0)
		self.assertEqual(len(rects), 4)                                                   # une grande et trois petites
		self.assertAlmostEqual(sorted(r.height for r in rects)[0], 28 * mm, delta=1.5 * mm)
		doc.close()
		# Hauteur réglée à 55 mm (le défaut) : la colonne ferait 187 mm, il en reste moins sur la page. La mosaïque
		# reste sur cette page, réduite, au lieu de passer à la suivante.
		doc, page, rects = self._mosaique(5, "Un produit ecoPurium.")
		self.assertEqual(page.number, 0)
		self.assertEqual(len(rects), 4)
		peu_de_texte = sorted(r.height for r in rects)[0]
		self.assertLess(peu_de_texte, 50 * mm)
		self.assertGreaterEqual(peu_de_texte, L.MOSAIQUE_MIN * mm - 2)
		self.assertLessEqual(max(r.y1 for r in rects), page.rect.height - 18 * mm)        # dans la page, marge du bas respectée
		doc.close()
		# Plus de texte au-dessus : elle se réduit davantage, toujours sur la même page.
		doc, page, rects = self._mosaique(5, "Description détaillée du produit. " * 12)
		self.assertEqual(page.number, 0)
		self.assertEqual(len(rects), 4)
		self.assertLess(sorted(r.height for r in rects)[0], peu_de_texte - 1)
		self.assertLessEqual(max(r.y1 for r in rects), page.rect.height - 18 * mm)
		doc.close()
		# Plus assez de place pour une mosaïque lisible : titre et mosaïque passent ensemble à la page suivante.
		doc, page, rects = self._mosaique(5, "Description détaillée du produit. " * 150)
		self.assertGreaterEqual(page.number, 1)
		self.assertEqual(len(rects), 4)
		doc.close()

	@unittest.skipUnless(shutil.which("xelatex"), "XeLaTeX requis")
	def test_plus_de_quatre_photos_les_suivantes_en_grille_de_trois(self):
		doc, page, rects = self._mosaique(8, "Un produit ecoPurium.", hauteur_vignettes=30)   # 7 photos dans la galerie
		self.assertEqual(len(rects), 4)                                                   # la mosaïque : une grande, trois petites
		# Les trois suivantes : en une rangée de trois, sous la mosaïque ou en haut de la page suivante.
		suite = [r for r in rects if r.y0 > max(rects, key=lambda r: r.width * r.height).y1]
		if not suite:
			suivante = doc[page.number + 1]
			suite = [r for x in suivante.get_images() for r in suivante.get_image_rects(x[0])]
		self.assertEqual(len(suite), 3)
		self.assertLess(max(r.y0 for r in suite) - min(r.y0 for r in suite), 2)           # sur une même rangée
		doc.close()

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
		ctx["mise_en_page"] = M.normaliser({"style_galerie": "mosaique", "hauteur_vignettes": 32, "colonnes_photos": 3, "ordre": list(M.ORDRE)})
		assets = {"images": [f"images/image-{i}.png" for i in range(8)], "dimensions": {f"images/image-{i}.png": (400, 300) for i in range(8)}}
		pdf, _ = L.compiler(L.source(contenu_simple(ctx), ctx, assets=assets), {f"images/image-{i}.png": png(i) for i in range(8)})
		with pymupdf.open(stream=pdf, filetype="pdf") as doc:
			page = next(p for p in doc if p.search_for("Vue 1"))
			haut = page.search_for("Le produit en images")[0].y1
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
			haut = page.search_for("Le produit en images")[0].y1
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
			page = next(p for p in doc if p.search_for("Le produit en images"))
			haut = page.search_for("Le produit en images")[0].y1
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
			page = next(p for p in doc if p.search_for("Le produit en images"))
			haut = page.search_for("Le produit en images")[0].y1
			rects = [r for x in page.get_images() for r in page.get_image_rects(x[0]) if r.y0 > haut]
			grande = max(rects, key=lambda r: r.width * r.height)
			self.assertAlmostEqual(grande.width, 174 * 0.7 * 0.6 * 72 / 25.4, delta=1 * 72 / 25.4)   # 60 % de 70 % de la ligne
			self.assertGreater(grande.x0, (18 + 15) * 72 / 25.4)                                      # décalée vers le centre


class TestStyleTitresEtSommaire(unittest.TestCase):
	"""06/11/2026 : « je veux que toutes les sections soient soulignées… TOC ? » — style des titres et sommaire."""

	def test_reglages(self):
		m = M.normaliser({"style_titres": "souligne", "sommaire": 1})
		self.assertEqual((m["style_titres"], m["sommaire"]), ("souligne", 1))
		m = M.normaliser({"style_titres": "simple", "sommaire": 0})
		self.assertNotIn("style_titres", m)   # défauts non stockés : empreinte des versions existantes inchangée
		self.assertNotIn("sommaire", m)
		for mauvais in ({"style_titres": "gras"}, {"style_titres": 1}, {"sommaire": 3}, {"sommaire": "1"}):
			with self.subTest(mauvais=mauvais), self.assertRaises(ValueError):
				M.normaliser(mauvais)

	@unittest.skipUnless(shutil.which("xelatex"), "XeLaTeX requis")
	def test_sommaire_cliquable_et_titres_soulignes(self):
		import pymupdf

		ctx = contexte_simple()
		contenu = contenu_simple(ctx)
		contenu["sections"] = [{"titre": f"Rubrique {i}", "texte": "Texte. " * 30, "article": "", "source": "Article"} for i in range(1, 4)]
		sans = L.compiler(L.source(contenu, ctx), {})[0]
		ctx["mise_en_page"] = M.normaliser({"style_titres": "souligne", "sommaire": 1})
		avec = L.compiler(L.source(contenu, ctx), {})[0]
		with pymupdf.open(stream=sans, filetype="pdf") as doc:
			self.assertFalse(doc[0].search_for("Sommaire"))
			filets_sans = len([d for d in doc[0].get_drawings() if d["rect"].width > 400 and d["rect"].height < 2])
		with pymupdf.open(stream=avec, filetype="pdf") as doc:
			page = doc[0]
			self.assertTrue(page.search_for("Sommaire"))
			self.assertEqual(len(page.search_for("Rubrique 2")), 2)   # au sommaire et comme titre
			liens = [l for l in page.get_links() if l.get("kind") in (pymupdf.LINK_GOTO, pymupdf.LINK_NAMED)]
			self.assertGreaterEqual(len(liens), 3)
			# Un filet fin sur toute la largeur du texte sous chaque titre (5 titres : 3 rubriques, caractéristiques,
			# variantes), comptés sur tout le document car le sommaire repousse les derniers blocs en page 2.
			filets = [d for d in page.get_drawings() if d["rect"].width > 400 and d["rect"].height < 2]
			tous = [d for p in doc for d in p.get_drawings() if d["rect"].width > 400 and d["rect"].height < 2]
			self.assertGreaterEqual(len(tous) - filets_sans, 5)
			titre = page.search_for("Rubrique 1")[-1]
			self.assertTrue(any(titre.y1 - 2 <= d["rect"].y0 <= titre.y1 + 18 for d in filets))


class TestGalerieLibreEtPolices(unittest.TestCase):
	"""07/11/2026 : galerie libre (une largeur par photo), alignement et largeur de la galerie, page entière, polices
	livrées et taille du texte, reprise de la présentation d'un autre dossier."""

	def test_validation_des_nouveaux_reglages(self):
		m = M.normaliser({"style_galerie": "libre", "largeurs_photos": {"/files/a.png": 50, "/private/files/b.png": 100},
			"alignement_galerie": "centre", "largeur_galerie": 80, "galerie_pleine_page": 1, "police": "montserrat",
			"police_titres": "oswald", "taille_police": 11})
		self.assertEqual(m["largeurs_photos"], {"/files/a.png": 50})          # 100 = défaut, non stocké
		self.assertEqual((m["alignement_galerie"], m["largeur_galerie"], m["galerie_pleine_page"]), ("centre", 80, 1))
		self.assertEqual((m["police"], m["police_titres"], m["taille_police"]), ("montserrat", "oswald", 11))
		# Les défauts n'apparaissent pas : une ancienne mise en page garde son empreinte.
		self.assertNotIn("police", M.normaliser({"police": ""}))
		self.assertNotIn("taille_police", M.normaliser({"taille_police": 10}))
		self.assertNotIn("largeurs_photos", M.normaliser({"largeurs_photos": {}}))
		for mauvais in ({"police": "Comic Sans"}, {"taille_police": 14}, {"alignement_galerie": "droite"}, {"largeur_galerie": 40},
			{"largeurs_photos": {"https://x/a.png": 50}}, {"largeurs_photos": {"/files/a.png": 5}}, {"largeurs_photos": {"/files/a.png": 50.5}},
			{"largeurs_photos": [50]}, {"style_galerie": "colonnes"}):
			with self.subTest(mauvais=mauvais), self.assertRaises(ValueError):
				M.normaliser(mauvais)

	def test_portable(self):
		m = M.portable({"photo_grande": "/files/a.png", "largeurs_photos": {"/files/a.png": 50}, "police": "lato", "colonnes_photos": 3})
		self.assertEqual((m.get("police"), m.get("colonnes_photos")), ("lato", 3))
		self.assertNotIn("photo_grande", m)
		self.assertNotIn("largeurs_photos", m)

	def test_empaquetage_polices_et_hauteur_pleine_page(self):
		self.assertEqual(L.empaqueter([(1, 50), (2, 50), (3, 30), (4, 30), (5, 40), (6, 100), (None, 25)]),
			[[(1, 50), (2, 50)], [(3, 30), (4, 30), (5, 40)], [(6, 100)], [(None, 25)]])
		self.assertEqual(L.empaqueter([(1, 60), (2, 60)]), [[(1, 60)], [(2, 60)]])     # 120 % : deux lignes
		self.assertEqual(L.hauteur_pleine_page(6, 3), 102)
		self.assertEqual(L.hauteur_pleine_page(12, 4, legendes=False), 71)
		self.assertEqual(L.hauteur_pleine_page(1, 1), 150)                        # borné
		self.assertEqual(L.hauteur_pleine_page(40, 2), 25)
		montserrat = L.police_fontspec("montserrat")
		self.assertIn(r"\setmainfont{Montserrat}[Path=", montserrat)
		self.assertIn("BoldItalicFont=*-BoldItalic", montserrat)
		self.assertNotIn("ItalicFont=*-Italic", L.police_fontspec("oswald"))      # Oswald n'a pas d'italique
		self.assertEqual(L.police_fontspec("inconnue"), "")
		self.assertEqual(L.police_fontspec(""), "")
		for cle in L.POLICES_LIVREES:
			self.assertTrue(L.police_fontspec(cle), cle)                            # chaque famille annoncée est livrée

	@unittest.skipUnless(shutil.which("xelatex"), "XeLaTeX requis")
	def test_rendu_galerie_libre_centree_polices_et_page_entiere(self):
		import pymupdf
		from PIL import Image
		from unittest.mock import patch

		from aquaworld_ia.documents_produit import contexte as C
		from aquaworld_ia.documents_produit import structure as S

		def png(couleur, w, h):
			b = io.BytesIO()
			Image.new("RGB", (w, h), couleur).save(b, format="PNG")
			return b.getvalue()

		ctx = contexte_simple()
		ctx["images"] = [{"image": f"/files/p{i}.png", "legende": f"Vue {i}", "article": ""} for i in range(5)]
		c = contenu_simple(ctx)
		c["legendes"] = [f"Vue {i}" for i in range(5)]
		c = S.normaliser(c, ctx)
		# Une couleur par photo : des PNG identiques partageraient un même objet image dans le PDF (un seul rectangle lu).
		octets = {f"/files/p{i}.png": png(["orange", "teal", "purple", "gray", "navy"][i], 600, 400) for i in range(5)}
		m = {"style_galerie": "libre", "alignement_galerie": "centre", "largeur_galerie": 90, "police": "montserrat", "police_titres": "oswald",
			"taille_police": 11, "largeurs_photos": {"/files/p1.png": 30, "/files/p2.png": 30, "/files/p3.png": 40, "/files/p4.png": 50}}
		with patch.object(C, "octets", side_effect=lambda u: octets[u]):
			tex, pdf, _ = L.composer(c, {**ctx, "mise_en_page": m})
		self.assertIn(r"\documentclass[11pt,a4paper]", tex)
		self.assertIn(r"\setmainfont{Montserrat}[Path=", tex)
		self.assertIn(r"\newfontfamily\titrefontfamille{Oswald}[Path=", tex)
		with pymupdf.open(stream=pdf, filetype="pdf") as doc:
			rects = sorted(((p.number, r) for p in doc for x in p.get_images() for r in p.get_image_rects(x[0])),
				key=lambda pr: (pr[0], pr[1].y0, pr[1].x0))
			self.assertEqual(len(rects), 5)                                       # principale + 4 de la galerie
			galerie = [r for _, r in rects[1:]]
			ligne1 = sorted((r for r in galerie if abs(r.y0 - galerie[0].y0) < 2), key=lambda r: r.x0)
			self.assertEqual(len(ligne1), 3)                                      # 30 + 30 + 40 : une seule ligne
			self.assertAlmostEqual(ligne1[0].width / ligne1[2].width, 0.75, delta=0.03)   # proportions 30 / 40 conservées
			page_w = doc[rects[1][0]].rect.width
			seul = galerie[3]
			self.assertAlmostEqual((seul.x0 + seul.x1) / 2, page_w / 2, delta=6)   # la photo à 50 %, seule, est centrée
			polices = {f[3] for p in doc for f in p.get_fonts()}
			self.assertTrue(any("Montserrat" in f for f in polices), polices)
			self.assertTrue(any("Oswald" in f for f in polices), polices)
		# Page entière : le bloc commence sur une page neuve, la grille prend la hauteur calculée.
		m2 = {"style_galerie": "grille", "colonnes_photos": 2, "galerie_pleine_page": 1, "ordre": list(M.ORDRE)}
		with patch.object(C, "octets", side_effect=lambda u: octets[u]):
			tex2, pdf2, _ = L.composer(c, {**ctx, "mise_en_page": m2})
		self.assertEqual(tex2.count(r"\clearpage"), 2)                            # une page réservée : saut avant et après
		self.assertIn(f"height={L.hauteur_pleine_page(4, 2)}mm", tex2)
		with pymupdf.open(stream=pdf2, filetype="pdf") as doc:
			self.assertEqual(len(doc), 2)
			self.assertEqual(len(doc[1].get_images()), 4)

	def test_sommaire_sur_sa_propre_page(self):
		"""07/11/2026 : « lorsque je mets le sommaire, il doit être sur une page séparée, le document commence sur une
		nouvelle page » : sommaire = 2 -> saut de page après la table ; 1 reste dans le fil."""
		self.assertEqual(M.normaliser({"sommaire": 2})["sommaire"], 2)
		with self.assertRaises(ValueError):
			M.normaliser({"sommaire": 3})
		ctx = contexte_simple()
		c = contenu_simple(ctx)
		tex = L.source(c, {**ctx, "mise_en_page": {"sommaire": 2}})
		self.assertIn(r"\tableofcontents\endgroup\par\medskip" + "\n" + r"\clearpage", tex)
		self.assertNotIn(r"\clearpage", L.source(c, {**ctx, "mise_en_page": {"sommaire": 1}}))
		if shutil.which("xelatex"):
			import pymupdf

			_tex, pdf, _ = L.composer(c, {**ctx, "mise_en_page": {"sommaire": 2}})
			with pymupdf.open(stream=pdf, filetype="pdf") as doc:
				self.assertEqual(len(doc), 2)
				self.assertTrue(doc[0].search_for("Sommaire"))
				self.assertTrue(doc[1].search_for("Utilisation"))          # la première rubrique ouvre la page 2
				self.assertFalse(doc[0].search_for("Le modèle TEST-P-V"))



class TestPresentationDeBase(unittest.TestCase):
	"""16/11/2026 : la mise en page d'un dossier (AP-M) devient celle dont part tout nouveau dossier."""

	AP_M = {"fiche": {"position_photo": "droite", "largeur_photo": 55, "hauteur_photo": 100, "style_titres": "souligne", "sommaire": 2,
			"photos_variantes": 2, "filigrane": 1, "filigrane_largeur": 85, "qr_alignement": "centre", "qr_legende": "Voir le produit en ligne",
			"qr_url": "https://aquaworldservicing.com/?post_type=product&p=1343", "photo_grande": "/files/AP-M.jpg",
			"style_galerie": "libre", "largeurs_photos": {"/files/AP-M.jpg": 60}},
		"manuel": {"qr_url": "https://aquaworldservicing.com/?post_type=product&p=1343", "qr_legende": "Voir le produit en ligne"}}

	def test_la_base_ne_garde_rien_du_produit(self):
		base = M.base(__import__("json").dumps(self.AP_M))
		self.assertEqual(set(base), {"fiche", "manuel"})
		for disposition in base.values():
			for cle in ("qr_url", "qr_legende", "photo_grande", "largeurs_photos"):
				self.assertNotIn(cle, disposition)
		self.assertEqual((base["fiche"]["style_titres"], base["fiche"]["sommaire"], base["fiche"]["filigrane"], base["fiche"]["qr_alignement"]),
			("souligne", 2, 1, "centre"))
		self.assertEqual(base["manuel"], M.normaliser())                         # un manuel resté d'origine : rien de particulier
		self.assertEqual(M.base(base), base)                                    # relue des Réglages : inchangée
		self.assertEqual(M.base(""), {}); self.assertEqual(M.base(None), {}); self.assertEqual(M.base({}), {})
		for invalide in ("pas du json", '{"affiche": {}}', '{"fiche": {"couleur": "rouge"}}', "[]"):
			with self.subTest(invalide=invalide), self.assertRaises(ValueError):
				M.base(invalide)

	def test_un_nouveau_dossier_part_de_la_base_avec_son_propre_qr(self):
		base, url = M.base(self.AP_M), "https://aquaworldservicing.com/?post_type=product&p=77"
		depart = M.initiale(url, base)
		self.assertEqual(set(depart), {"fiche", "manuel"})
		self.assertEqual((depart["fiche"]["qr_url"], depart["fiche"]["qr_legende"], depart["fiche"]["qr_alignement"]), (url, "Voir le produit en ligne", "centre"))
		self.assertEqual({k: v for k, v in depart["fiche"].items() if k not in ("qr_url", "qr_legende")}, base["fiche"])
		self.assertEqual(M.configuration(depart), depart)                       # enregistrable tel quel
		sans_site = M.initiale("", base)                                        # article hors du site : la base, sans QR
		self.assertEqual(sans_site, base)
		self.assertIsNot(sans_site["fiche"], base["fiche"])
		self.assertEqual(M.initiale(url, {"fiche": base["fiche"]})["manuel"], M.initiale(url)["manuel"])   # base de la fiche seule
		self.assertEqual(M.initiale("", {"fiche": base["fiche"]}), {"fiche": base["fiche"]})
		self.assertEqual(M.initiale(url), M.initiale(url, {}))                  # sans base : comme avant
		self.assertEqual(M.initiale("", None), {})
		# Une base qui porterait encore une adresse (saisie à la main) ne la donne jamais à un autre produit.
		self.assertNotIn("qr_url", M.initiale("", {"fiche": self.AP_M["fiche"]})["fiche"])
