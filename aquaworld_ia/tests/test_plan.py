"""Plan du document : les rubriques et sous-rubriques choisies à l'étape Préparer sont suivies par la rédaction."""

import json
import unittest
from unittest.mock import patch

from aquaworld_ia.documents_produit import latex as L
from aquaworld_ia.documents_produit import plan as PL
from aquaworld_ia.documents_produit import structure as S
from aquaworld_ia.tests.test_documents_produit import contenu_simple, contexte_simple

PLAN = [{"titre": "Applications", "sous": []}, {"titre": "Entretien", "sous": ["Remplacement des cartouches", "Désinfection"]}]


class Dossier(dict):
	"""Ce que plan.py lit d'un dossier : `get("plans")`."""


class TestNormaliserLePlan(unittest.TestCase):
	def test_titres_nettoyes_doublons_et_vides_ecartes(self):
		plan = PL.normaliser([
			{"titre": "  Applications  ", "sous": []},
			"Entretien",                                                     # un simple titre est admis
			{"titre": "applications"},                                       # doublon à la casse près
			{"titre": "   "}, {"sous": ["x"]}, 12, None,
			{"titre": "## Dépannage", "sous": ["Fuites", " fuites ", "", "Bruit", 3]},
		])
		self.assertEqual(plan, [{"titre": "Applications", "sous": []}, {"titre": "Entretien", "sous": []},
			{"titre": "Dépannage", "sous": ["Fuites", "Bruit"]}])
		self.assertEqual(PL.normaliser("Applications"), [])
		self.assertEqual(len(PL.normaliser([f"Rubrique {i}" for i in range(40)])), PL.MAX_RUBRIQUES)
		self.assertEqual(len(PL.normaliser([{"titre": "A", "sous": [f"s{i}" for i in range(30)]}])[0]["sous"]), PL.MAX_SOUS)

	def test_meme_rubrique_a_la_casse_aux_accents_et_a_la_ponctuation_pres(self):
		self.assertEqual(PL.cle("  Dépannage : "), PL.cle("depannage"))
		self.assertNotEqual(PL.cle("Entretien"), PL.cle("Entretien courant"))

	def test_configuration_par_type_de_document(self):
		conf = PL.configuration(json.dumps({"fiche": PLAN, "manuel": [{"titre": " "}]}))
		self.assertEqual(conf, {"fiche": PLAN})                              # un plan vide n'est pas gardé
		self.assertEqual(PL.configuration(""), {})
		self.assertEqual(PL.configuration(None), {})
		with self.assertRaises(ValueError):
			PL.configuration({"autre": PLAN})

	def test_le_plan_entre_dans_le_contexte_de_son_type_seulement(self):
		d = Dossier(plans=json.dumps({"fiche": PLAN}))
		ctx = contexte_simple()
		self.assertEqual(PL.appliquer(ctx, d, "Fiche technique")["plan"], PLAN)
		self.assertNotIn("plan", PL.appliquer(ctx, d, "Manuel d'utilisation"))
		self.assertNotIn("plan", ctx)                                        # le contexte reçu n'est pas modifié
		# Sans plan : pas de clé, l'empreinte des versions existantes ne bouge pas.
		self.assertEqual(S.empreinte(PL.appliquer(ctx, Dossier(), "Fiche technique")), S.empreinte(ctx))
		self.assertNotIn("plan", PL.appliquer({**ctx, "plan": PLAN}, Dossier(), "Fiche technique"))


class TestSousTitres(unittest.TestCase):
	TEXTE = "Introduction.\n## Remplacement des cartouches\nTous les six mois.\n\nSuite.\n###  Désinfection ##\nUne fois par an.\n#1 n’est pas un titre\n##"

	def test_une_ligne_diese_diese_est_un_sous_titre(self):
		self.assertEqual(PL.sous_titres(self.TEXTE), ["Remplacement des cartouches", "Désinfection"])
		self.assertIsNone(PL.sous_titre("#1 n’est pas un titre"))
		self.assertIsNone(PL.sous_titre("##"))
		self.assertIsNone(PL.sous_titre("Prix : 12 ## 13"))
		self.assertEqual(PL.sous_titre("  ##Entretien"), "Entretien")

	def test_decoupage_dans_l_ordre(self):
		self.assertEqual(PL.decouper(self.TEXTE), [
			("texte", "Introduction."), ("titre", "Remplacement des cartouches"), ("texte", "Tous les six mois.\n\nSuite."),
			("titre", "Désinfection"), ("texte", "Une fois par an.\n#1 n’est pas un titre\n##")])
		self.assertEqual(PL.decouper("Un seul paragraphe."), [("texte", "Un seul paragraphe.")])
		self.assertEqual(PL.decouper(""), [])

	def test_le_pdf_imprime_le_sous_titre(self):
		ctx = contexte_simple()
		c = contenu_simple(ctx)
		sans = L.source(c, ctx)
		self.assertNotIn(r"\docsoustitre{", sans)
		self.assertIn(r"Le modèle TEST-P-V utilise une membrane Vontron.\par", sans)   # un texte simple reste rendu comme avant
		c["sections"][0]["texte"] = "Rincer avant usage.\n## Remplacement des cartouches\nTous les six mois."
		tex = L.source(S.normaliser(c, ctx), ctx)
		self.assertIn(r"\docsoustitre{Remplacement des cartouches}", tex)
		self.assertNotIn("\\#\\#", tex)                                        # les dièses ne s'impriment pas
		self.assertLess(tex.index(r"Rincer avant usage.\par"), tex.index(r"\docsoustitre{Remplacement"))
		self.assertLess(tex.index(r"\docsoustitre{Remplacement"), tex.index(r"Tous les six mois.\par"))

	def test_le_pdf_se_compose_avec_des_sous_titres(self):
		ctx = contexte_simple()
		c = contenu_simple(ctx)
		c["sections"][0]["texte"] = "Rincer avant usage.\n## Remplacement des cartouches\nTous les six mois.\n## Désinfection & rinçage\nUne fois par an."
		pdf, _ = L.compiler(L.source(S.normaliser(c, ctx), ctx), {})
		self.assertTrue(pdf.startswith(b"%PDF"))


class TestSuivreLePlan(unittest.TestCase):
	SECTIONS = [
		{"titre": "Fonctionnement", "texte": "Osmose inverse."},
		{"titre": "ENTRETIEN", "texte": "## Désinfection\nUne fois par an."},
		{"titre": "applications", "texte": "Eau de boisson."},
	]

	def test_ordre_et_titres_du_plan_retablis(self):
		ordonnees, hors_plan = PL.ordonner(self.SECTIONS, PLAN)
		self.assertEqual([s["titre"] for s in ordonnees], ["Applications", "Entretien", "Fonctionnement"])
		self.assertEqual(hors_plan, ["Fonctionnement"])
		self.assertEqual(ordonnees[0]["texte"], "Eau de boisson.")
		self.assertEqual(self.SECTIONS[2]["titre"], "applications")           # l'entrée n'est pas modifiée

	def test_une_rubrique_du_plan_par_modele_reste_groupee(self):
		sections = [{"titre": "Entretien", "texte": "A", "article": "V1"}, {"titre": "Applications", "texte": "B"},
			{"titre": "Entretien", "texte": "C", "article": "V2"}]
		ordonnees, hors_plan = PL.ordonner(sections, PLAN)
		self.assertEqual([(s["titre"], s["texte"]) for s in ordonnees], [("Applications", "B"), ("Entretien", "A"), ("Entretien", "C")])
		self.assertEqual(hors_plan, [])

	def test_ce_qui_manque_ou_sort_du_plan_devient_un_point(self):
		points = PL.points(self.SECTIONS, PLAN)
		self.assertEqual(len(points), 2)
		self.assertIn("Sous-rubrique(s) du plan sans information dans « Entretien » : Remplacement des cartouches.", points)
		self.assertTrue(any(p.startswith("Rubrique ajoutée hors du plan : « Fonctionnement »") for p in points))
		points = PL.points([{"titre": "Entretien", "texte": "  "}], PLAN)
		self.assertTrue(any(p.startswith("Rubrique du plan sans information : « Applications »") for p in points))
		self.assertTrue(any(p.startswith("Rubrique du plan sans information : « Entretien »") for p in points))
		complet = [{"titre": "Applications", "texte": "x"},
			{"titre": "Entretien", "texte": "## Remplacement des cartouches\nx\n## désinfection\ny"}]
		self.assertEqual(PL.points(complet, PLAN), [])

	def test_plan_d_une_version_existante_et_resume(self):
		plan = PL.depuis_contenu({"sections": [{"titre": "Applications", "texte": "x"},
			{"titre": "Entretien", "texte": "## Remplacement des cartouches\nx\n## Désinfection\ny"}, {"titre": ""}]})
		self.assertEqual(plan, PLAN)
		self.assertEqual(PL.depuis_contenu(None), [])
		self.assertEqual(PL.resume(PLAN), "Applications → Entretien (Remplacement des cartouches ; Désinfection)")


class TestRedactionAvecPlan(unittest.TestCase):
	def _generer(self, ctx, sections):
		from aquaworld_ia.documents_produit import traitement as T

		base = contenu_simple(contexte_simple())
		reponse = {"titre": base["titre"], "resume": base["resume"], "caracteristiques": base["caracteristiques"],
			"sections": [{"article": "", "source": "Article TEST-P", **s} for s in sections]}
		with patch.object(T, "chat_json", return_value=reponse) as chat:
			contenu = T.generer(None, "Fiche technique", ctx)
		system, user = chat.call_args.args[:2]
		return contenu, system, json.loads(user)

	def test_l_ia_recoit_le_plan_et_la_redaction_le_suit(self):
		ctx = {**contexte_simple(), "plan": PLAN}
		contenu, system, user = self._generer(ctx, [
			{"titre": "Fonctionnement", "texte": "Osmose inverse."},
			{"titre": "Entretien", "texte": "## Désinfection\nNettoyer le réservoir."},
			{"titre": "applications", "texte": "Eau de boisson."}])
		self.assertEqual(user["contexte"]["plan"], PLAN)
		self.assertIn("EXACTEMENT ces rubriques", system)
		self.assertIn("« ## »", system)
		self.assertEqual([s["titre"] for s in contenu["sections"]], ["Applications", "Entretien", "Fonctionnement"])
		points = contenu["points_a_verifier"]
		self.assertTrue(any("Remplacement des cartouches" in p for p in points))
		self.assertTrue(any("hors du plan : « Fonctionnement »" in p for p in points))

	def test_sans_plan_rien_ne_change(self):
		contenu, system, user = self._generer(contexte_simple(), [
			{"titre": "Fonctionnement", "texte": "Osmose inverse."}, {"titre": "Applications", "texte": "Eau de boisson."}])
		self.assertNotIn("plan", user["contexte"])
		self.assertNotIn("EXACTEMENT ces rubriques", system)
		self.assertIn("Conserve ceux qui existent", system)                    # la convention des sous-titres reste connue
		self.assertEqual([s["titre"] for s in contenu["sections"]], ["Fonctionnement", "Applications"])
		self.assertFalse([p for p in contenu["points_a_verifier"] if "plan" in p])

	def test_la_traduction_garde_les_sous_titres(self):
		import inspect

		from aquaworld_ia.documents_produit import traitement as T

		self.assertIn("garde « ## » au début de cette ligne", inspect.getsource(T.traduire))


if __name__ == "__main__":
	unittest.main()
