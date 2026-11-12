"""« Gamme et configurations » : texte d'introduction du tableau des variantes, nombres comptés par l'app."""

import json
import unittest
from unittest.mock import patch

from aquaworld_ia.documents_produit import gamme as G
from aquaworld_ia.documents_produit import latex as L
from aquaworld_ia.documents_produit import structure as S
from aquaworld_ia.tests.test_documents_produit import contenu_simple, contexte_simple
from aquaworld_ia.tests.test_tableau_variantes import gamme

INTRO = ("La gamme se décline en 12 variantes, selon trois marques de membrane, trois configurations de filtration "
	"et la présence ou non d’un mixage.\nChoisissez d’abord la configuration, puis la membrane.")


class TestAxesDeLaGamme(unittest.TestCase):
	def test_nombres_comptes_par_l_app(self):
		ctx, _ = gamme()
		axes = G.axes(ctx["variantes"])
		self.assertEqual(axes["nombre_variantes"], 12)
		self.assertEqual([(a["attribut"], a["nombre"]) for a in axes["axes"]],
			[("Marque de membrane", 3), ("Configuration de filtration", 3), ("Système de mélange", 2)])
		self.assertEqual(axes["axes"][0]["valeurs"], ["AquaJad", "DowFilmtec", "Vontron"])
		self.assertNotIn("marques_commerciales", axes)               # une seule marque commerciale : rien à dire
		self.assertEqual(G.axes(ctx["variantes"][:1]), {})           # une variante : pas de gamme à présenter
		self.assertEqual(G.axes([]), {})
		self.assertEqual(G.axes(None), {})
		# Un attribut qui ne varie pas n'est pas un axe de choix.
		fixes = [{"name": "A", "attributs": [{"nom": "Couleur", "valeur": "Blanc"}, {"nom": "Taille", "valeur": "S"}]},
			{"name": "B", "attributs": [{"nom": "Couleur", "valeur": "Blanc"}, {"nom": "Taille", "valeur": "M"}]}]
		self.assertEqual([a["attribut"] for a in G.axes(fixes)["axes"]], ["Taille"])


class TestContenuGamme(unittest.TestCase):
	def test_cle_facultative_traduisible_et_libelle(self):
		ctx, c = gamme()
		self.assertNotIn("gamme", c)                                  # absente tant qu'elle est vide : empreintes inchangées
		self.assertNotIn("gamme", S.normaliser({**c, "gamme": "  "}, ctx))
		avec = S.normaliser({**c, "gamme": INTRO}, ctx)
		self.assertEqual(avec["gamme"], INTRO)
		self.assertIn(("gamme",), S.champs_traduisibles(avec))
		self.assertNotIn(("gamme",), S.champs_traduisibles(c))
		self.assertEqual(S.depuis_ia({"gamme": None})["gamme"], "")
		with self.assertRaises(ValueError):
			S.normaliser({**c, "gamme": "x" * 3001}, ctx)
		self.assertEqual(c["libelles"]["variantes"], "Gamme et configurations")
		ancien = S.normaliser({**c, "libelles": {**c["libelles"], "variantes": "Variantes couvertes"}}, ctx)
		self.assertEqual(ancien["libelles"]["variantes"], "Gamme et configurations")
		variante = S.normaliser({**c, "libelles": {**c["libelles"], "variantes": "Référence et configuration"}}, ctx)
		self.assertEqual(variante["libelles"]["variantes"], "Référence et configuration")   # fiche de variante : inchangé

	def test_pdf_titre_introduction_puis_tableau(self):
		ctx, c = gamme()
		tex = L.source(S.normaliser({**c, "gamme": INTRO}, ctx), ctx)
		titre = tex.index(r"\docsection{Gamme et configurations}")
		intro = tex.index("La gamme se décline en 12 variantes")
		tableau = tex.index(r"\begin{longtable}", titre)
		self.assertLess(titre, intro)
		self.assertLess(intro, tableau)                               # juste avant le tableau des variantes
		self.assertEqual(tex.count("La gamme se décline en 12 variantes"), 1)
		self.assertNotIn("La gamme se décline", L.source(c, ctx))     # sans texte : le titre et le tableau seuls
		# Fiche d'UNE variante : pas d'introduction de gamme.
		ctx_v = {**ctx, "variantes": ctx["variantes"][:1], "variante": ctx["variantes"][0]["name"]}
		c_v = S.normaliser({**contenu_simple(ctx_v), "gamme": INTRO}, ctx_v)
		self.assertNotIn("La gamme se décline", L.source(c_v, ctx_v))


class TestRedactionGamme(unittest.TestCase):
	def _generer(self, ctx, reponse):
		from aquaworld_ia.documents_produit import traitement as T

		with patch.object(T, "chat_json", return_value=reponse) as chat:
			contenu = T.generer(None, "Fiche technique", ctx)
		system, user = chat.call_args.args[:2]
		return contenu, system, json.loads(user)

	def test_l_ia_recoit_les_nombres_et_la_consigne(self):
		ctx, c = gamme()
		reponse = {k: v for k, v in c.items() if k in ("titre", "resume", "sections", "caracteristiques")}
		contenu, system, user = self._generer(ctx, {**reponse, "gamme": INTRO})
		self.assertEqual(user["contexte"]["gamme"]["nombre_variantes"], 12)
		self.assertEqual([a["nombre"] for a in user["contexte"]["gamme"]["axes"]], [3, 3, 2])
		self.assertIn("gamme:texte", system)
		self.assertIn("N'énumère pas les variantes", system)
		self.assertEqual(contenu["gamme"], INTRO)
		self.assertFalse([p for p in contenu["points_a_verifier"] if "Gamme et configurations" in p])   # 12, trois, trois : comptés
		# Un nombre que l'app n'a pas compté est signalé.
		contenu, _, _ = self._generer(ctx, {**reponse, "gamme": "La gamme compte 15 variantes et 4 membranes."})
		point = [p for p in contenu["points_a_verifier"] if "Gamme et configurations" in p]
		self.assertEqual(len(point), 1)
		self.assertIn("15", point[0])
		self.assertIn("4", point[0])

	def test_une_seule_variante_pas_de_gamme(self):
		ctx = contexte_simple()
		c = contenu_simple(ctx)
		reponse = {k: v for k, v in c.items() if k in ("titre", "resume", "sections", "caracteristiques")}
		contenu, _, user = self._generer(ctx, {**reponse, "gamme": INTRO})
		self.assertNotIn("gamme", user["contexte"])
		self.assertNotIn("gamme", contenu)                            # un texte rendu quand même n'est pas gardé

	def test_reecrire_la_gamme_sans_instruction(self):
		from aquaworld_ia.documents_produit import traitement as T

		ctx, c = gamme()
		with patch.object(T, "chat_json", return_value={"texte": INTRO, "points_a_verifier": []}) as chat, \
				patch.object(T.journal, "suivre_generation"), patch.object(T.frappe, "generate_hash", return_value="x"):
			r = T.reecrire(type("D", (), {"name": "DPR-TEST"})(), "Fiche technique", ctx, c, {"type": "gamme"}, "")
		system, user = chat.call_args.args[:2]
		self.assertEqual(r["texte"], INTRO)
		self.assertNotIn("titre", r)
		self.assertIn("La partie à réécrire est « gamme »", system)
		user = json.loads(user)
		self.assertEqual(user["partie_a_reecrire"]["type"], "gamme")
		self.assertEqual(user["instruction"], "Rédige cette introduction.")
		self.assertEqual(user["contexte"]["gamme"]["nombre_variantes"], 12)
		with self.assertRaises(ValueError):                           # une seule variante : rien à présenter
			T.reecrire(None, "Fiche technique", contexte_simple(), contenu_simple(), {"type": "gamme"}, "")
