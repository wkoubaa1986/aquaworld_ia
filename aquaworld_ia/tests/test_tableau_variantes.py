"""Tableau des variantes résumé par caractéristiques (demande 06/11/2026 : « le tableau de variantes doit
être plus intelligent, bien résumer les variantes sur les caractéristiques »)."""

import shutil
import unittest

from aquaworld_ia.documents_produit import latex as L
from aquaworld_ia.documents_produit import structure as S
from aquaworld_ia.tests.test_documents_produit import contenu_simple, contexte_simple


def gamme():
	variantes = []
	for m in ("AquaJad", "DowFilmtec", "Vontron"):
		for cfg, mix in (("Classique 5 Stages", "Avec mixage"), ("Classique 5 Stages", "Sans mixage"),
			("UV 6 Stages", "Sans mixage"), ("Alcaline 6 Stages", "Sans mixage")):
			variantes.append({"name": f"AP-M-{m[:2].upper()}-{cfg.split()[1]}-{'AM' if 'Avec' in mix else 'SM'}-{cfg[:2]}",
				"item_name": "Osmoseur " + m, "brand": "ecoPurium",
				"attributs": [{"nom": "Marque de membrane", "valeur": m}, {"nom": "Configuration de filtration", "valeur": cfg},
					{"nom": "Système de mélange", "valeur": mix}]})
	ctx = contexte_simple()
	ctx["variantes"] = variantes
	c = contenu_simple(ctx)
	c["caracteristiques"] += [
		{"nom": "Débit", "valeur": "75", "unite": "GPD", "article": variantes[0]["name"], "source": "S1"},
		{"nom": "Débit", "valeur": "100", "unite": "GPD", "article": variantes[2]["name"], "source": "S1"},
		{"nom": "Pression", "valeur": "3", "unite": "bar", "article": "", "source": "S1"},   # commune : pas une colonne
	]
	return ctx, S.normaliser(c, ctx)


class TestPlanTableauVariantes(unittest.TestCase):
	def test_colonnes_par_attribut_groupes_et_caracteristiques_pivotees(self):
		_, c = gamme()
		plan = L.plan_tableau_variantes(c["variantes"], c["caracteristiques"], c["libelles"])
		self.assertEqual(plan["entetes"], ["Référence", "Configuration de filtration", "Système de mélange", "Débit"])
		self.assertEqual([(g, len(l)) for g, l in plan["groupes"]],
			[("Marque de membrane : AquaJad", 4), ("Marque de membrane : DowFilmtec", 4), ("Marque de membrane : Vontron", 4)])
		self.assertEqual(plan["groupes"][0][1][0], [c["variantes"][0]["article"], "Classique 5 Stages", "Avec mixage", "75 GPD"])
		self.assertEqual(plan["groupes"][0][1][1][3], "")                         # pas de débit propre : cellule vide

	def test_petite_gamme_sans_groupe_marques_differentes_et_sans_attributs(self):
		_, c = gamme()
		plan = L.plan_tableau_variantes(c["variantes"][:3], [], c["libelles"])
		self.assertEqual(plan["entetes"][:2], ["Référence", "Marque de membrane"])   # ≤ 6 variantes : pas de groupe
		self.assertEqual([g for g, _ in plan["groupes"]], [""])
		deux = [dict(v, marque="Autre") if i else v for i, v in enumerate(c["variantes"][:2])]
		self.assertIn("Marque", L.plan_tableau_variantes(deux, [], c["libelles"])["entetes"])
		sans = L.plan_tableau_variantes([{"article": "X", "nom": "Modèle X", "marque": "M", "attributs": []}], [], c["libelles"])
		self.assertEqual(sans, {"entetes": ["Référence", "Configuration"], "groupes": [("", [["X", "Modèle X"]])]})
		self.assertEqual(L.plan_tableau_variantes([], [], c["libelles"])["groupes"], [])

	def test_au_plus_trois_caracteristiques_les_plus_renseignees(self):
		_, c = gamme()
		refs = [v["article"] for v in c["variantes"]]
		caracs = [{"nom": n, "valeur": "1", "unite": "", "article": r, "source": ""} for n, k in (("A", 5), ("B", 4), ("C", 3), ("D", 2)) for r in refs[:k]]
		plan = L.plan_tableau_variantes(c["variantes"], caracs, c["libelles"])
		self.assertEqual(plan["entetes"][-3:], ["A", "B", "C"])


@unittest.skipUnless(shutil.which("xelatex"), "XeLaTeX requis")
class TestRenduTableauVariantes(unittest.TestCase):
	def test_pdf_groupes_et_colonnes(self):
		import pymupdf

		ctx, c = gamme()
		_tex, pdf, _ = L.composer(c, ctx)
		with pymupdf.open(stream=pdf, filetype="pdf") as doc:
			texte = " ".join("".join(p.get_text() for p in doc).split())
			self.assertIn("Marque de membrane : AquaJad", texte)
			self.assertIn("Système de mélange", texte)
			self.assertIn("75 GPD", texte)
			self.assertNotIn("Marque de membrane : AquaJad; ", texte)        # l'ancienne phrase « nom : valeur ; … »


@unittest.skipUnless(shutil.which("xelatex"), "XeLaTeX requis")
class TestLignesColorees(unittest.TestCase):
	"""06/11/2026 : lignes des tableaux colorées en alternance, deux teintes de la couleur des titres."""

	def test_trois_teintes_derivees_de_la_couleur_des_titres(self):
		import pymupdf

		from aquaworld_ia.documents_produit import mise_en_page as M

		ctx, c = gamme()
		c["sections"][0]["tableau"] = [["Étages", "Débit"], ["5", "75 GPD"], ["6", "100 GPD"]]
		ctx["mise_en_page"] = M.normaliser({"couleur": "#1F5FBF"})
		_tex, pdf, _ = L.composer(c, ctx)
		with pymupdf.open(stream=pdf, filetype="pdf") as doc:
			fonds = {}
			for page in doc:
				for d in page.get_drawings():
					if d.get("fill") and tuple(d["fill"]) != (1.0, 1.0, 1.0):
						cle = tuple(round(x, 2) for x in d["fill"])
						fonds[cle] = fonds.get(cle, 0) + 1
			# Trois teintes (5 %, 13 %, 22 %) d'un bleu : rouge < bleu dans chacune, toutes claires.
			teintes = [k for k in fonds if k[0] < k[2] and min(k) > 0.7]
			self.assertGreaterEqual(len(teintes), 3, fonds)
			self.assertGreaterEqual(sum(fonds[k] for k in teintes), 20)          # une bande par ligne de tableau
