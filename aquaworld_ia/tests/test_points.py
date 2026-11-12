"""Traiter un point à vérifier avec l'IA : l'information de l'utilisateur est écrite au bon endroit du document."""

import json
import unittest
from unittest.mock import patch

from aquaworld_ia.documents_produit import points as P
from aquaworld_ia.documents_produit import structure as S
from aquaworld_ia.tests.test_documents_produit import contenu_simple, contexte_simple
from aquaworld_ia.tests.test_tableau_variantes import gamme

POINT = "Vérifier la pression d’entrée admissible."
ARTICLES = {"TEST-P", "TEST-P-V"}
SOURCE = "Information de l’entreprise (12/11/2026)"


def contenu():
	c = contenu_simple()
	c["points_a_verifier"] = [POINT, "Autre point."]
	return c


class TestAppliquerLesModifications(unittest.TestCase):
	def test_chaque_type_de_modification(self):
		c = contenu()
		rubrique = c["sections"][0]["titre"]
		data = {"modifications": [
			{"type": "caracteristique", "nom": "Pression d’entrée", "valeur": "1 à 4", "unite": "bar", "article": ""},
			{"type": "section", "index": 0, "texte": "Texte complété : pression d’entrée de 1 à 4 bar."},
			{"type": "nouvelle_section", "titre": "Raccordement", "texte": "Raccords rapides 1/4 pouce.", "article": "TEST-P-V"},
			{"type": "resume", "texte": "Nouvelle présentation."},
		]}
		nouveau, changements, textes = P.appliquer(c, data, ARTICLES, SOURCE)
		self.assertEqual([m["type"] for m in changements], ["caracteristique", "section", "section", "resume"])
		ajoutee = nouveau["caracteristiques"][changements[0]["index"]]
		self.assertEqual((ajoutee["nom"], ajoutee["valeur"], ajoutee["unite"], ajoutee["source"]), ("Pression d’entrée", "1 à 4", "bar", SOURCE))
		self.assertEqual(changements[0]["libelle"], "Caractéristique « Pression d’entrée » ajoutée")
		self.assertEqual(nouveau["sections"][0]["texte"], "Texte complété : pression d’entrée de 1 à 4 bar.")
		self.assertEqual(nouveau["sections"][0]["titre"], rubrique)                       # titre gardé s'il n'est pas rendu
		self.assertEqual(changements[1]["libelle"], f"Rubrique « {rubrique} » modifiée")
		nouvelle = nouveau["sections"][changements[2]["index"]]
		self.assertEqual((nouvelle["titre"], nouvelle["article"], nouvelle["source"]), ("Raccordement", "TEST-P-V", SOURCE))
		self.assertEqual(nouveau["resume"], "Nouvelle présentation.")
		self.assertEqual(len(textes), 5)                                                  # titre + texte de la nouvelle rubrique
		self.assertEqual(c["sections"][0]["texte"], contenu()["sections"][0]["texte"])    # le contenu d'origine n'est pas touché
		S.normaliser(nouveau, contexte_simple())                                          # reste un contenu valide

	def test_remplace_la_caracteristique_de_meme_nom(self):
		c = contenu()
		existante = c["caracteristiques"][0]
		data = {"modifications": [{"type": "caracteristique", "nom": existante["nom"].upper(), "valeur": "9", "unite": "bar", "article": existante["article"]}]}
		nouveau, changements, _ = P.appliquer(c, data, ARTICLES, SOURCE)
		self.assertEqual(len(nouveau["caracteristiques"]), len(c["caracteristiques"]))
		self.assertEqual(nouveau["caracteristiques"][0]["valeur"], "9")
		self.assertIn("modifiée", changements[0]["libelle"])

	def test_modifications_mal_formees_ignorees(self):
		c = contenu()
		for data in (None, {}, {"modifications": "x"}, {"modifications": [
			"texte", {"type": "inconnu", "texte": "x"}, {"type": "section", "index": 9, "texte": "x"},
			{"type": "section", "index": True, "texte": "x"}, {"type": "section", "index": 0, "texte": ""},
			{"type": "caracteristique", "nom": "Débit", "valeur": ""}, {"type": "nouvelle_section", "titre": "", "texte": "x"},
			{"type": "gamme", "texte": "Une seule variante : pas de gamme."}, {"type": "resume", "texte": None}]}):
			with self.subTest(data=data):
				nouveau, changements, textes = P.appliquer(c, data, ARTICLES, SOURCE)
				self.assertEqual((changements, textes), ([], []))
				self.assertEqual(nouveau, c)
		# Une portée inconnue devient « toute la gamme » plutôt que de faire refuser le document.
		nouveau, changements, _ = P.appliquer(c, {"modifications": [{"type": "caracteristique", "nom": "Tension", "valeur": "24", "unite": "V", "article": "AUTRE"}]}, ARTICLES, SOURCE)
		self.assertEqual(nouveau["caracteristiques"][-1]["article"], "")

	def test_destination_imposee_et_gamme(self):
		c = contenu()
		data = {"modifications": [{"type": "resume", "texte": "Présentation."}, {"type": "section", "index": 0, "texte": "Rubrique."},
			{"type": "caracteristique", "nom": "Débit", "valeur": "5", "unite": "L/h"}]}
		_, changements, _ = P.appliquer(c, data, ARTICLES, SOURCE, {"type": "caracteristique"})
		self.assertEqual([m["type"] for m in changements], ["caracteristique"])
		_, changements, _ = P.appliquer(c, data, ARTICLES, SOURCE, {"type": "section", "index": 0})
		self.assertEqual([(m["type"], m["index"]) for m in changements], [("section", 0)])
		_, changements, _ = P.appliquer(c, data, ARTICLES, SOURCE, {"type": "nimporte"})  # destination invalide : au choix
		self.assertEqual(len(changements), 3)
		ctx, cg = gamme()
		nouveau, changements, _ = P.appliquer(cg, {"modifications": [{"type": "gamme", "texte": "La gamme compte 12 variantes."}]}, set(), SOURCE)
		self.assertEqual(nouveau["gamme"], "La gamme compte 12 variantes.")
		self.assertEqual(changements[0]["type"], "gamme")

	def test_point_range_parmi_les_traites(self):
		c = contenu()
		P.marquer_traite(c, POINT, "Pression ajoutée aux caractéristiques.", "1 à 4 bar")
		self.assertEqual(c["points_a_verifier"], ["Autre point."])
		self.assertEqual(c["points_traites"], [{"texte": POINT, "action": "Pression ajoutée aux caractéristiques.", "information": "1 à 4 bar"}])
		P.marquer_traite(c, POINT, "Complété.", "1 à 6 bar")                              # retraité : une seule entrée, la dernière
		self.assertEqual([t["action"] for t in c["points_traites"]], ["Complété."])
		propre = S.normaliser(c, contexte_simple())
		self.assertEqual(propre["points_traites"][0]["information"], "1 à 6 bar")
		self.assertNotIn("points_traites", S.normaliser(contenu(), contexte_simple()))     # clé absente tant qu'elle est vide
		with self.assertRaises(ValueError):
			S.normaliser({**contenu(), "points_traites": "x"}, contexte_simple())


class TestTraiterUnPoint(unittest.TestCase):
	def _traiter(self, reponse, information="La pression d’entrée va de 1 à 4 bar.", destination=None):
		from aquaworld_ia.documents_produit import traitement as T

		with patch.object(T, "chat_json", return_value=reponse) as chat, \
				patch.object(T.journal, "suivre_generation"), patch.object(T.frappe, "generate_hash", return_value="x"):
			r = T.traiter_point(type("D", (), {"name": "DPR-TEST"})(), "Fiche technique", contexte_simple(), contenu(), POINT, information, destination)
		return r, chat.call_args.args[0], json.loads(chat.call_args.args[1])

	def test_le_point_passe_au_vert_et_le_document_est_complete(self):
		r, system, user = self._traiter({"modifications": [{"type": "caracteristique", "nom": "Pression d’entrée", "valeur": "1 à 4", "unite": "bar", "article": ""}],
			"action": "Pression d’entrée ajoutée aux caractéristiques.", "reste_a_verifier": []})
		c = r["contenu"]
		self.assertNotIn(POINT, c["points_a_verifier"])
		self.assertEqual(c["points_a_verifier"], ["Autre point."])
		self.assertEqual(c["points_traites"][0]["texte"], POINT)
		self.assertEqual(c["points_traites"][0]["action"], "Pression d’entrée ajoutée aux caractéristiques.")
		self.assertIn("1 à 4 bar", c["points_traites"][0]["information"])
		self.assertEqual(c["caracteristiques"][-1]["nom"], "Pression d’entrée")
		self.assertTrue(c["caracteristiques"][-1]["source"].startswith("Information de l’entreprise ("))
		self.assertEqual(r["changements"][0]["type"], "caracteristique")
		self.assertEqual(user["point_a_verifier"], POINT)
		self.assertEqual(user["destination"], "au choix")
		self.assertIn("sections", user["document"])
		self.assertIn("n'ajoute rien qu'elle ne dise pas", system)
		self.assertIn("Ne convertis pas", system)                                         # l'app calcule l'équivalent métrique

	def test_nombre_invente_et_reste_a_verifier_redeviennent_des_points_rouges(self):
		r, _, _ = self._traiter({"modifications": [{"type": "caracteristique", "nom": "Pression d’entrée", "valeur": "1 à 6", "unite": "bar"}],
			"action": "Ajouté.", "reste_a_verifier": ["La pression maximale reste à confirmer."]})
		ouverts = r["contenu"]["points_a_verifier"]
		self.assertIn("La pression maximale reste à confirmer.", ouverts)
		self.assertTrue(any("absents de votre information" in p and "6" in p for p in ouverts))   # 6 n'était pas dans l'information
		self.assertEqual(r["contenu"]["points_traites"][0]["texte"], POINT)

	def test_refus_sans_information_ou_sans_modification(self):
		for reponse, information in (({"modifications": []}, "1 à 4 bar"), ({"modifications": [{"type": "section", "index": 0, "texte": "x"}]}, "  ")):
			with self.subTest(information=information), self.assertRaises(ValueError):
				self._traiter(reponse, information)
		# Destination imposée : une modification ailleurs est écartée, donc rien n'est fait.
		with self.assertRaises(ValueError):
			self._traiter({"modifications": [{"type": "resume", "texte": "Pression de 1 à 4 bar."}]}, destination={"type": "caracteristique"})
