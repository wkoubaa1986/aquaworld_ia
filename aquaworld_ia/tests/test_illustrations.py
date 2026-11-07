"""Illustrations d'une rubrique par IA (demande 07/11/2026) : graphe depuis les données, tableau rédigé, image
générée ou retouchée. Les nombres ne viennent jamais du modèle : tout chiffre absent des données fait refuser."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from aquaworld_ia.documents_produit import illustrations as I
from aquaworld_ia.documents_produit import latex as L
from aquaworld_ia.documents_produit import structure as S
from aquaworld_ia.tests.test_documents_produit import contenu_simple, contexte_simple


def _dossier():
	return SimpleNamespace(name="DP-1", doctype="Dossier Produit", consignes="")


def _contenu():
	ctx = contexte_simple()
	c = contenu_simple(ctx)
	c["sections"][0]["texte"] = "Le modèle 5 étages donne 75 GPD, le 6 étages 100 GPD, à 3 bar."
	c["caracteristiques"].append({"nom": "Débit", "valeur": "125", "unite": "GPD", "article": "", "source": "S1"})
	return ctx, S.normaliser(c, ctx)


class TestNombresConnus(unittest.TestCase):
	def test_corpus_et_inconnus(self):
		ctx, c = _contenu()
		connus = I.corpus_nombres(c, ctx, "ajoute 7 étages à 130,5 GPD")
		for n in (5, 75, 6, 100, 3, 125, 7, 130.5):
			self.assertIn(n, connus)
		self.assertEqual(I.nombres_inconnus([75, 99, 130.5, 99, 42], connus), [99, 42])
		self.assertEqual(I.nombres_du_tableau([["Étages", "Débit"], ["5", "75 GPD"], ["1 234,5", "x"]]), [5, 75, 1234.5])
		self.assertEqual(I.formater(130.5), "130,5")

	def test_entete_et_mise_en_page_hors_corpus(self):
		"""Les dimensions de l'en-tête ou la largeur du logo ne « justifient » pas une valeur du graphe."""
		ctx, c = _contenu()
		ctx["entete"] = {"hauteur": 999}
		ctx["mise_en_page"] = {"largeur_logo": 888}
		connus = I.corpus_nombres(c, ctx)
		self.assertNotIn(999, connus)
		self.assertNotIn(888, connus)


class TestPrompts(unittest.TestCase):
	def test_requete_et_prompt_image_purs(self):
		ctx, c = _contenu()
		ctx["entete"] = {"png": "x"}
		r = I.requete("Fiche technique", ctx, c, 0, "Débit par variante", existant=None)
		self.assertEqual(r["rubrique"]["titre"], "Utilisation")
		self.assertNotIn("entete", r["contexte"])
		self.assertEqual(r["document"]["autres_rubriques"], [])
		p = I.prompt_image("Fiche technique", ctx, c["sections"][0], "schéma en vue éclatée")
		self.assertIn("Osmoseur compact (ecoPurium)", p)
		self.assertIn("Aucun texte", p)
		self.assertIn("Modifie l'image fournie", I.prompt_image("Fiche technique", ctx, c["sections"][0], "fond blanc", retouche=True))
		with self.assertRaises(ValueError):
			I.requete("Fiche technique", ctx, c, 3, "x")


class TestGrapheIA(unittest.TestCase):
	def _appel(self, reponse, instruction="Débit par nombre d'étages"):
		ctx, c = _contenu()
		with patch.object(I, "chat_json", return_value=reponse) as chat, patch.object(I.journal, "suivre_generation"):
			r = I.graphe_ia(_dossier(), "Fiche technique", ctx, c, 0, instruction)
		self.assertIn("Réponds uniquement en JSON", chat.call_args[0][0])
		return r

	def test_graphe_accepte_quand_les_valeurs_sont_dans_les_donnees(self):
		r = self._appel({"graphe": {"type": "barres", "titre": "Débit", "unite": "GPD", "categories": ["5 étages", "6 étages"],
			"series": [{"nom": "Débit", "valeurs": ["75", 100]}]}, "legende": "Débit nominal", "points_a_verifier": ["Pression à confirmer"]})
		self.assertEqual(r["graphe"]["series"][0]["valeurs"], [75, 100])
		self.assertEqual(r["legende"], "Débit nominal")
		self.assertEqual(r["points_a_verifier"], ["Pression à confirmer"])

	def test_graphe_refuse_une_valeur_inventee(self):
		with self.assertRaises(ValueError) as cm:
			self._appel({"graphe": {"type": "courbe", "categories": ["5", "6"], "series": [{"nom": "", "valeurs": [75, 150]}]}})
		self.assertIn("150", str(cm.exception))

	def test_graphe_accepte_une_valeur_de_l_instruction(self):
		r = self._appel({"graphe": {"type": "courbe", "categories": ["5", "6"], "series": [{"nom": "", "valeurs": [75, 150]}]}},
			instruction="ajoute 150 pour le 6 étages")
		self.assertEqual(r["graphe"]["series"][0]["valeurs"], [75, 150])

	def test_sans_graphe_ou_sans_instruction(self):
		with self.assertRaises(ValueError):
			self._appel({"texte": "pas de graphe"})
		ctx, c = _contenu()
		with self.assertRaises(ValueError):
			I.graphe_ia(_dossier(), "Fiche technique", ctx, c, 0, "  ")


class TestTableauIA(unittest.TestCase):
	def test_tableau_valide_et_refus(self):
		ctx, c = _contenu()
		with patch.object(I, "chat_json", return_value={"tableau": [["Étages", "Débit"], [5, "75 GPD"], ["6", "100 GPD"]]}), \
				patch.object(I.journal, "suivre_generation"):
			r = I.tableau_ia(_dossier(), "Fiche technique", ctx, c, 0, "une ligne par modèle")
		self.assertEqual(r["tableau"], [["Étages", "Débit"], ["5", "75 GPD"], ["6", "100 GPD"]])
		with patch.object(I, "chat_json", return_value={"tableau": [["Étages", "Débit"], ["8", "200 GPD"]]}), \
				patch.object(I.journal, "suivre_generation"), self.assertRaises(ValueError) as cm:
			I.tableau_ia(_dossier(), "Fiche technique", ctx, c, 0, "une ligne par modèle")
		self.assertIn("8, 200", str(cm.exception))


class TestImageIA(unittest.TestCase):
	def test_generation_puis_retouche(self):
		ctx, c = _contenu()
		enregistre = []

		def save_file(nom, octets, doctype, name, is_private=1):
			enregistre.append((nom, octets, doctype, name, is_private))
			return SimpleNamespace(file_url="/private/files/" + nom)

		with patch("frappe.utils.file_manager.save_file", save_file), \
				patch("aquaworld_ia.ia.images.generer", return_value=[b"PNG1"]) as generer, \
				patch("aquaworld_ia.ia.client.qualite_image", return_value="medium"), \
				patch.object(I.journal, "suivre_generation"):
			r = I.image_ia(_dossier(), "Fiche technique", ctx, c, 0, "schéma en vue éclatée", "paysage")
		self.assertEqual(r["image"], "/private/files/DP-1-rubrique-1-ia.png")
		self.assertEqual(generer.call_args.kwargs["taille"], "1536x1024")
		self.assertEqual(enregistre[0][1:], (b"PNG1", "Dossier Produit", "DP-1", 1))
		c["sections"][0].update(image=r["image"], image_position="droite", image_largeur=40, image_legende="")
		with patch("frappe.utils.file_manager.save_file", save_file), \
				patch("aquaworld_ia.ia.images.editer", return_value=[b"PNG2"]) as editer, \
				patch("aquaworld_ia.documents_produit.contexte.fichier_lisible"), \
				patch("aquaworld_ia.documents_produit.contexte.octets", return_value=b"PNG1"), \
				patch("aquaworld_ia.ia.client.qualite_image", return_value="medium"), \
				patch.object(I.journal, "suivre_generation"):
			r2 = I.image_ia(_dossier(), "Fiche technique", ctx, c, 0, "retire le fond", None, retouche=True)
		self.assertEqual(editer.call_args[0][1], [("rubrique", b"PNG1")])
		self.assertEqual(editer.call_args.kwargs["taille"], "1024x1024")
		self.assertEqual(r2["image"], "/private/files/DP-1-rubrique-1-ia.png")

	def test_retouche_sans_image(self):
		ctx, c = _contenu()
		with patch.object(I.journal, "suivre_generation"), self.assertRaises(ValueError):
			I.image_ia(_dossier(), "Fiche technique", ctx, c, 0, "retire le fond", retouche=True)


class TestGrapheTikz(unittest.TestCase):
	"""Le code pgfplots est pur : libellés échappés, positions 1..n, valeurs en nombres."""

	def test_barres_et_secteurs(self):
		g = S.graphe({"type": "barres", "titre": "Débit & co", "axe_y": "Débit", "unite": "GPD", "categories": ["5 étages", "A, B"],
			"series": [{"nom": "V", "valeurs": [75, 130.5]}, {"nom": "F", "valeurs": [80, 100]}]})
		tex = L.graphe_tikz(g, L.texte)
		self.assertIn(r"title={Débit \& co}", tex)
		self.assertIn("xticklabels={{5 étages}, {A, B}}", tex)
		self.assertIn("ylabel={Débit (GPD)}", tex)
		self.assertIn(r"\addplot[fill=aqua, draw=none] coordinates {(1,75) (2,130.5)};", tex)
		self.assertIn(r"\addlegendentry{F}", tex)
		pie = L.graphe_tikz(S.graphe({"type": "secteurs", "categories": ["Pros, B2B", "Export"], "series": [{"valeurs": [30, 0]}]}), L.texte)
		self.assertIn(r"\pie[", pie)
		self.assertIn("{30/{Pros, B2B}}", pie)          # la part nulle est omise, la virgule du libellé protégée

	def test_barres_horizontales_et_courbe(self):
		h = L.graphe_tikz(S.graphe({"type": "barres_horizontales", "axe_x": "Pression (bar)", "categories": ["A", "B"],
			"series": [{"valeurs": [3, 4.5]}]}), L.texte)
		self.assertIn("xlabel={Pression (bar)}", h)       # en horizontal, l'axe x porte les valeurs
		self.assertIn("y dir=reverse", h)
		self.assertIn("coordinates {(3,1) (4.5,2)}", h)
		courbe = L.graphe_tikz(S.graphe({"type": "courbe", "categories": ["2", "3"], "series": [{"nom": "5 étages", "valeurs": [-1, 11]}]}), L.texte)
		self.assertIn("mark=*", courbe)
		self.assertNotIn("ymin=0", courbe)                # une valeur négative : l'axe n'est pas forcé à zéro
