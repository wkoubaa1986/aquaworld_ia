"""Image (graphe, schéma) et tableau dans une rubrique — demande 06/11/2026 : « texte à gauche et graphe à
droite, ou ajouter un tableau ». Validation pure, puis géométrie réelle du PDF."""

import io
import shutil
import unittest
from unittest.mock import patch

from aquaworld_ia.documents_produit import latex as L
from aquaworld_ia.documents_produit import structure as S
from aquaworld_ia.tests.test_documents_produit import contenu_simple, contexte_simple


def _rubrique(**extra):
	return S.rubrique({"titre": "Performances", "texte": "Texte.", "article": "", "source": "Article", **extra}, lambda v: v or "")


class TestStructureRubrique(unittest.TestCase):
	def test_image_et_tableau_valides(self):
		s = _rubrique(image="/private/files/graphe.png", image_position="gauche", image_largeur=55, image_legende=" Débit ",
			tableau=[["Étages", "Débit"], [5, "75 GPD"], [None, ""]])
		self.assertEqual(s["image_legende"], "Débit")
		self.assertEqual(s["tableau"], [["Étages", "Débit"], ["5", "75 GPD"], ["", ""]])
		self.assertEqual(s["image_largeur"], 55)

	def test_sans_image_ni_tableau_aucune_cle_ajoutee(self):
		"""Une version antérieure relue sans changement garde la même empreinte (pas de nouvelle version)."""
		self.assertEqual(sorted(_rubrique()), ["article", "source", "texte", "titre"])
		self.assertEqual(sorted(_rubrique(image="", tableau=[])), ["article", "source", "texte", "titre"])

	def test_refus(self):
		for mauvais in ({"image": "https://x/y.png"}, {"image": "/files/a b.png"}, {"image": "/files/a.png", "image_position": "centre"},
			{"image": "/files/a.png", "image_largeur": 80}, {"image": "/files/a.png", "image_position": "dessous", "image_largeur": 101},
			{"image": "/files/a.png", "image_largeur": 40.5}, {"tableau": [["a"], ["b", "c"]]}, {"tableau": [["a"] * 9]},
			{"tableau": "x"}, {"tableau": [["a"]] * 41}):
			with self.subTest(mauvais=mauvais), self.assertRaises(ValueError):
				_rubrique(**mauvais)

	def test_disposition_du_tableau(self):
		"""07/11/2026 : le tableau a sa disposition (dessous par défaut, dessus, à côté du texte avec sa largeur) ;
		les clés n'existent qu'hors défaut, pour l'empreinte des anciennes versions."""
		base = {"tableau": [["a", "b"], ["1", "2"]]}
		self.assertNotIn("tableau_position", _rubrique(**base))
		self.assertNotIn("tableau_position", _rubrique(**base, tableau_position="dessous"))
		s = _rubrique(**base, tableau_position="gauche", tableau_largeur=45)
		self.assertEqual((s["tableau_position"], s["tableau_largeur"]), ("gauche", 45))
		self.assertEqual(_rubrique(**base, tableau_position="droite")["tableau_largeur"], 50)
		self.assertNotIn("tableau_largeur", _rubrique(**base, tableau_position="dessus"))
		for mauvais in ({"tableau_position": "centre"}, {"tableau_position": "droite", "tableau_largeur": 20},
			{"tableau_position": "droite", "tableau_largeur": 50.5}):
			with self.subTest(mauvais=mauvais), self.assertRaises(ValueError):
				_rubrique(**base, **mauvais)
		# Illustration et tableau ne sont pas tous deux à côté du texte (un paracol ne s'imbrique pas).
		with self.assertRaises(ValueError):
			_rubrique(**base, image="/files/a.png", image_position="droite", tableau_position="gauche")
		_rubrique(**base, image="/files/a.png", image_position="dessous", tableau_position="gauche")

	def test_graphe_de_donnees(self):
		"""07/11/2026 : un graphe est une structure de données (catégories, séries), jamais une image."""
		spec = {"type": "barres", "titre": "Débit", "categories": ["5 étages", 6], "series": [{"nom": "V", "valeurs": ["75", 100.0]}]}
		s = _rubrique(graphe=spec, image_position="gauche", image_largeur=50, image_legende="Débit")
		self.assertEqual(s["graphe"]["categories"], ["5 étages", "6"])
		self.assertEqual(s["graphe"]["series"][0]["valeurs"], [75, 100])
		self.assertEqual((s["image_position"], s["image_largeur"], s["image_legende"]), ("gauche", 50, "Débit"))
		self.assertNotIn("image", s)
		self.assertEqual(_rubrique(graphe=spec)["image_position"], "droite")
		for mauvais in ({"type": "radar"}, {"categories": []}, {"categories": ["a"] * 13}, {"series": []},
			{"series": [{"valeurs": [1]}]}, {"series": [{"valeurs": ["x", 1]}]}, {"series": [{"valeurs": [True, 1]}]},
			{"type": "secteurs", "series": [{"valeurs": [1, 2]}, {"valeurs": [1, 2]}]}, {"type": "secteurs", "series": [{"valeurs": [0, 0]}]},
			{"type": "secteurs", "series": [{"valeurs": [-1, 2]}]}):
			with self.subTest(mauvais=mauvais), self.assertRaises(ValueError):
				S.graphe({**spec, **mauvais})
		with self.assertRaises(ValueError):
			_rubrique(graphe=spec, image="/files/a.png")
		with self.assertRaises(ValueError):
			_rubrique(graphe=spec, image_largeur=70)
		self.assertEqual(S.nombre("1 234,5"), 1234.5)
		self.assertEqual(S.nombre(3.0), 3)

	def test_libelles_du_graphe_sont_traduits(self):
		ctx = contexte_simple()
		c = contenu_simple(ctx)
		c["sections"][0].update(graphe={"type": "courbe", "titre": "Débit", "axe_x": "Pression", "axe_y": "", "categories": ["2 bar", "3 bar"],
			"series": [{"nom": "5 étages", "valeurs": [8, 11]}]}, image_legende="Courbe")
		chemins = S.champs_traduisibles(S.normaliser(c, ctx))
		for chemin in (("sections", 0, "graphe", "titre"), ("sections", 0, "graphe", "axe_x"), ("sections", 0, "graphe", "categories", 1),
			("sections", 0, "graphe", "series", 0, "nom"), ("sections", 0, "image_legende")):
			self.assertIn(chemin, chemins)
		self.assertNotIn(("sections", 0, "graphe", "axe_y"), chemins)      # vide : rien à traduire

	def test_legende_et_cellules_sont_traduites(self):
		ctx = contexte_simple()
		c = contenu_simple(ctx)
		c["sections"][0].update(image="/files/g.png", image_legende="Débit", tableau=[["Étages", "Débit"], ["5", "75 GPD"]])
		chemins = S.champs_traduisibles(S.normaliser(c, ctx))
		self.assertIn(("sections", 0, "image_legende"), chemins)
		self.assertIn(("sections", 0, "tableau", 1, 1), chemins)
		# Les valeurs et unités des cellules restent protégées à la traduction.
		self.assertEqual(S.tokens_proteges("75 GPD", ctx), S.tokens_proteges("75 GPD", ctx))


@unittest.skipUnless(shutil.which("xelatex"), "XeLaTeX requis")
class TestRenduRubrique(unittest.TestCase):
	def test_image_a_droite_tableau_dessous_image_sous_le_texte(self):
		import pymupdf
		from PIL import Image

		def png(couleur, w=600, h=300):
			b = io.BytesIO()
			Image.new("RGB", (w, h), couleur).save(b, format="PNG")
			return b.getvalue()

		ctx = contexte_simple()
		c = contenu_simple(ctx)
		c["sections"] = [
			{"titre": "Performances", "texte": "Le débit dépend du nombre d’étages. " * 6, "article": "", "source": "Article",
				"image": "/files/graphe.png", "image_position": "droite", "image_largeur": 40, "image_legende": "Débit selon les étages",
				"tableau": [["Étages", "Débit", "Pression"], ["5", "75 GPD", "3 bar"], ["6", "100 GPD", "3 bar"]]},
			{"titre": "Installation", "texte": "Texte.", "article": "", "source": "Article",
				"image": "/files/schema.png", "image_position": "dessous", "image_largeur": 70},
		]
		c = S.normaliser(c, ctx)
		assets = {"images": [], "sections": {0: "images/section-0.png", 1: "images/section-1.png"}}
		pdf, _ = L.compiler(L.source(c, ctx, assets=assets), {"images/section-0.png": png("orange"), "images/section-1.png": png("purple", 800, 200)})
		with pymupdf.open(stream=pdf, filetype="pdf") as doc:
			page = doc[0]
			graphe, schema = [page.get_image_rects(x[0])[0] for x in page.get_images()]
			texte = page.search_for("Le débit dépend")[0]
			self.assertLess(texte.x1, graphe.x0)                               # texte à gauche, graphe à droite
			self.assertLess(abs(graphe.y0 - texte.y0), 30)                     # sur la même ligne
			self.assertAlmostEqual(graphe.width, 0.4 * 174 * 72 / 25.4, delta=4 * 72 / 25.4)
			self.assertGreater(page.search_for("Débit selon les étages")[0].y0, graphe.y1 - 1)
			entete = page.search_for("Étages")[0]
			self.assertGreater(entete.y0, graphe.y1)                           # tableau sous texte et image
			self.assertTrue(page.search_for("100 GPD"))
			self.assertGreater(schema.y0, page.search_for("Installation")[0].y1)
			self.assertAlmostEqual(schema.width, 0.7 * 174 * 72 / 25.4, delta=1)


def _png(couleur, w=600, h=300):
	from PIL import Image

	b = io.BytesIO()
	Image.new("RGB", (w, h), couleur).save(b, format="PNG")
	return b.getvalue()


@unittest.skipUnless(shutil.which("xelatex"), "XeLaTeX requis")
class TestRenduDispositions(unittest.TestCase):
	"""07/11/2026 : tableau à côté du texte, graphe de données composé par pgfplots."""

	def test_tableau_a_gauche_graphe_a_droite_et_dessous(self):
		import pymupdf

		ctx = contexte_simple()
		c = contenu_simple(ctx)
		texte = "Le débit dépend du nombre d’étages et de la pression d’entrée. " * 4
		c["sections"] = [
			{"titre": "Entretien", "texte": texte, "article": "", "source": "Article",
				"tableau": [["Étape", "Fréquence"], ["Préfiltre", "6 mois"]], "tableau_position": "gauche", "tableau_largeur": 40},
			{"titre": "Performances", "texte": texte, "article": "", "source": "Article", "image_position": "droite", "image_largeur": 50,
				"image_legende": "Débit nominal", "graphe": {"type": "barres", "titre": "Débit", "unite": "GPD", "categories": ["5 étages", "6 étages"],
				"series": [{"nom": "Vontron", "valeurs": [75, 100]}]}, "tableau": [["Modèle", "Débit"], ["A", "75 GPD"]], "tableau_position": "dessus"},
			{"titre": "Répartition", "texte": texte, "article": "", "source": "Article", "image_position": "dessous", "image_largeur": 60,
				"graphe": {"type": "secteurs", "categories": ["Pros", "Export"], "series": [{"valeurs": [70, 30]}]}},
		]
		# Une photo du dossier : la galerie et ses légendes (fonction `legende`) doivent cohabiter avec la légende
		# d'une illustration de rubrique (07/11/2026 : « 'str' object is not callable » à l'ouverture d'un dossier avec photos).
		ctx["images"] = [{"image": "/files/photo.png", "legende": "Vue de face", "article": ""}]
		c["legendes"] = ["Vue de face"]
		c = S.normaliser(c, ctx)
		with patch.object(L.C, "octets", return_value=_png("gray")):
			tex, pdf, _ = L.composer(c, ctx)
		self.assertIn(r"\usepackage{pgfplots}", tex)
		self.assertIn(r"\begin{tabular}", tex)            # tableau en colonne : tabular, pas longtable
		with pymupdf.open(stream=pdf, filetype="pdf") as doc:
			page = doc[0]
			entretien = page.search_for("Préfiltre")[0]
			texte1 = page.search_for("Le débit dépend")[0]
			self.assertLess(entretien.x1, texte1.x0)                           # tableau à gauche, texte à droite
			self.assertLess(abs(entretien.y0 - texte1.y0), 40)
			modele = page.search_for("Modèle")[0]
			perf = page.search_for("Performances")[0]
			self.assertGreater(modele.y0, perf.y1)                              # tableau « dessus » : entre le titre et le texte
			texte2 = [r for r in page.search_for("Le débit dépend") if r.y0 > modele.y1][0]
			etages = page.search_for("5 étages")[0]                             # libellé du graphe, à droite du texte
			self.assertGreater(etages.x0, texte2.x1)
			self.assertTrue(page.search_for("Vontron"))                         # légende de série
			self.assertTrue(page.search_for("Débit nominal"))                   # légende sous le graphe
			secteurs = [r for p in doc for r in p.search_for("Export")]
			self.assertTrue(secteurs)                                           # secteurs : libellé en légende

	def test_sans_graphe_pas_de_pgfplots(self):
		ctx = contexte_simple()
		tex, _pdf, _ = L.composer(contenu_simple(ctx), ctx)
		self.assertNotIn("pgfplots", tex)


class TestSymbolesHorsPolice(unittest.TestCase):
	"""« Missing character: There is no ↔ (U+2194) in font Noto Sans » (06/11/2026) : les symboles que Noto Sans
	ne couvre pas passent dans une police de secours, ou en texte s'il n'y en a aucune."""

	def tearDown(self):
		if hasattr(L.police_symboles, "cache"):
			delattr(L.police_symboles, "cache")

	def test_police_de_secours_ou_repli_texte(self):
		L.police_symboles.cache = "DejaVu Sans"
		self.assertEqual(L.texte("A ↔ B ≥ 3 → C"), r"A {\symbolfont ↔} B {\symbolfont ≥} 3 {\symbolfont →} C")
		self.assertEqual(L.texte("50 % & ±2"), r"50 \% \& ±2")      # ± est dans Noto Sans : inchangé
		L.police_symboles.cache = None
		self.assertEqual(L.texte("A ↔ B ≥ 3 → C ✓ ∞"), "A <-> B >= 3 -> C v infini")

	@unittest.skipUnless(shutil.which("xelatex") and shutil.which("fc-list"), "XeLaTeX et fontconfig requis")
	def test_pdf_avec_fleches_et_operateurs(self):
		import pymupdf

		ctx = contexte_simple()
		c = contenu_simple(ctx)
		c["sections"][0]["texte"] = "Pression ≥ 3 bar ↔ 5 bar → OK ✓"
		_tex, pdf, _ = L.composer(c, ctx)
		if L.police_symboles():
			with pymupdf.open(stream=pdf, filetype="pdf") as doc:
				for s in ("≥", "↔", "→", "✓"):
					self.assertTrue(doc[0].search_for(s), s)


class TestCaracteristiquesVides(unittest.TestCase):
	def test_les_lignes_vides_ne_comptent_pas_dans_la_limite(self):
		"""06/11/2026 : 144 caractéristiques + 135 lignes vides/`{}` capturées par erreur → « Liste documentaire
		invalide : caracteristiques ». Les vides sont ignorées, les autres gardées."""
		ctx = contexte_simple()
		c = contenu_simple(ctx)
		c["caracteristiques"] = [{"nom": "Débit", "valeur": "75", "unite": "GPD", "article": "", "source": "S1"}] \
			+ [{"nom": "", "valeur": "", "unite": "", "article": "", "source": ""}] * 200 + [{}] * 60
		out = S.normaliser(c, ctx)
		self.assertEqual([x["nom"] for x in out["caracteristiques"]], ["Débit"])
		c["caracteristiques"] = [{"nom": f"C{i}", "valeur": "1", "unite": "", "article": "", "source": ""} for i in range(251)]
		with self.assertRaises(ValueError):
			S.normaliser(c, ctx)
