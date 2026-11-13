"""Tableau des caractéristiques par catégories (demande 13/11/2026 : « est-ce que l'IA peut les organiser et créer
par catégories, électrique ou autre, en gardant la possibilité d'entrer manuellement ? »)."""

import copy
import json
import unittest
from unittest.mock import patch

from aquaworld_ia.documents_produit import latex as L
from aquaworld_ia.documents_produit import points as P
from aquaworld_ia.documents_produit import service as API
from aquaworld_ia.documents_produit import structure as S
from aquaworld_ia.documents_produit import traitement as T
from aquaworld_ia.tests.test_documents_produit import contenu_simple, contexte_simple

LISTE = ["Performances", "Filtration", "Hydraulique", "Électrique"]
SOURCE = "Information de l’entreprise (13/11/2026)"


def ligne(nom, categorie="", valeur="1", unite="", article=""):
	l = {"nom": nom, "valeur": valeur, "unite": unite, "article": article, "source": "Article TEST-P"}
	if categorie:
		l["categorie"] = categorie
	return l


def contenu(lignes):
	return S.normaliser({**contenu_simple(), "caracteristiques": lignes}, contexte_simple())


def noms(lignes):
	return [l["nom"] for l in lignes]


class TestListeDesCategories(unittest.TestCase):
	def test_dossier_puis_reglages_puis_defaut(self):
		self.assertEqual(S.categories("", ""), list(S.CATEGORIES_DEFAUT))
		self.assertEqual(S.categories("", "Débit\nPression"), ["Débit", "Pression"])
		self.assertEqual(S.categories("Électrique\nFiltration", "Débit"), ["Électrique", "Filtration"])
		self.assertEqual(S.categories(None, None, ["A", "B"]), ["A", "B"])

	def test_saisie_nettoyee(self):
		self.assertEqual(S.lire_categories("  Électrique \n\n électrique\nDimensions   et  poids\n"), ["Électrique", "Dimensions et poids"])
		self.assertEqual(len(S.lire_categories("\n".join("C%d" % i for i in range(60)))), S.MAX_CATEGORIES)
		self.assertEqual(S.lire_categories(""), [])

	def test_categorie_admise_ecrite_comme_dans_la_liste(self):
		self.assertEqual(S.categorie_admise(" électrique ", LISTE), "Électrique")
		for refusee in ("Électricité", "", None, "Garantie"):
			self.assertEqual(S.categorie_admise(refusee, LISTE), "", refusee)

	def test_liste_du_dossier_et_des_reglages(self):
		dossier = type("D", (), {"categories_caracteristiques": "Débit\nPression"})()
		with patch("aquaworld_ia.ia.client.reglages", return_value={"categories_caracteristiques": "Réglage A\nRéglage B"}):
			self.assertEqual(API.categories_caracteristiques(dossier), ["Débit", "Pression"])
			self.assertEqual(API.categories_caracteristiques(type("D", (), {})()), ["Réglage A", "Réglage B"])
			self.assertEqual(API.categories_caracteristiques(), ["Réglage A", "Réglage B"])
		with patch("aquaworld_ia.ia.client.reglages", return_value={}):
			self.assertEqual(API.categories_caracteristiques(), list(S.CATEGORIES_DEFAUT))


class TestRangement(unittest.TestCase):
	LIGNES = [ligne("tension", "Électrique"), ligne("libre"), ligne("garantie", "Garantie"), ligne("filtre", "Filtration"), ligne("courant", "Électrique")]

	def test_ordre_de_la_liste_puis_autres_puis_sans_categorie(self):
		self.assertEqual(noms(S.ranger_caracteristiques(self.LIGNES, LISTE)), ["filtre", "tension", "courant", "garantie", "libre"])
		# sans liste : les groupes dans leur ordre d'apparition, l'ordre dans un groupe conservé
		self.assertEqual(noms(S.ranger_caracteristiques(self.LIGNES)), ["tension", "courant", "garantie", "filtre", "libre"])

	def test_sans_aucune_categorie_rien_ne_bouge(self):
		lignes = [ligne("b"), ligne("a"), ligne("c")]
		self.assertEqual(noms(S.ranger_caracteristiques(lignes, LISTE)), ["b", "a", "c"])

	def test_normaliser_garde_la_cle_seulement_remplie(self):
		c = contenu([ligne("Pression", valeur="3", unite="bar"), {**ligne("Tension"), "categorie": "  Électrique  "}, {**ligne("Poids"), "categorie": ""}])
		self.assertEqual([(l["nom"], l.get("categorie")) for l in c["caracteristiques"]], [("Tension", "Électrique"), ("Pression", None), ("Poids", None)])
		self.assertNotIn("categorie", c["caracteristiques"][1])
		# une version sans catégories ne change pas : même contenu, donc même empreinte
		ancien = contenu_simple()
		self.assertEqual(S.empreinte(S.normaliser(copy.deepcopy(ancien), contexte_simple())), S.empreinte(ancien))
		self.assertTrue(all("categorie" not in l for l in ancien["caracteristiques"]))

	def test_normaliser_regroupe_sans_changer_l_ordre_choisi(self):
		c = contenu([ligne("a", "Hydraulique"), ligne("b", "Électrique"), ligne("c", "Hydraulique"), ligne("d")])
		self.assertEqual(noms(c["caracteristiques"]), ["a", "c", "b", "d"])
		self.assertEqual(noms(contenu(c["caracteristiques"])["caracteristiques"]), ["a", "c", "b", "d"])   # stable
		with self.assertRaises(ValueError):
			contenu([{**ligne("a"), "categorie": 12}])


class TestIA(unittest.TestCase):
	def test_caracteristique_ajoutee_dans_sa_categorie(self):
		c = contenu([ligne("Débit", "Performances"), ligne("Tension", "Électrique"), ligne("Poids")])
		data = {"modifications": [
			{"type": "caracteristique", "nom": "Pression d’entrée", "valeur": "1 à 3", "unite": "bar", "categorie": "hydraulique"},
			{"type": "caracteristique", "nom": "Courant", "valeur": "1,3", "unite": "A", "categorie": "Électrique"},
			{"type": "caracteristique", "nom": "Garantie", "valeur": "2", "unite": "ans", "categorie": "Catégorie inventée"},
			{"type": "caracteristique", "nom": "Tension", "valeur": "24", "unite": "V", "categorie": "Hydraulique"},
		]}
		nouveau, changements, _ = P.appliquer(c, data, {"TEST-P", "TEST-P-V"}, SOURCE, categories=LISTE)
		self.assertEqual([(l["nom"], l.get("categorie")) for l in nouveau["caracteristiques"]],
			[("Débit", "Performances"), ("Pression d’entrée", "Hydraulique"), ("Tension", "Électrique"), ("Courant", "Électrique"), ("Poids", None), ("Garantie", None)])
		# les index des changements désignent les lignes du tableau regroupé — l'écran les surligne
		self.assertEqual([nouveau["caracteristiques"][m["index"]]["nom"] for m in changements], ["Pression d’entrée", "Courant", "Garantie", "Tension"])
		self.assertEqual(nouveau["caracteristiques"][2]["valeur"], "24")              # valeur corrigée, catégorie gardée
		self.assertEqual(noms(S.normaliser(nouveau, contexte_simple())["caracteristiques"]), noms(nouveau["caracteristiques"]))

	def test_sans_categories_le_tableau_reste_a_plat(self):
		c = contenu([ligne("Débit"), ligne("Tension")])
		nouveau, changements, _ = P.appliquer(c, {"modifications": [{"type": "caracteristique", "nom": "Poids", "valeur": "4", "unite": "kg"}]}, {"TEST-P"}, SOURCE)
		self.assertEqual((noms(nouveau["caracteristiques"]), changements[0]["index"]), (["Débit", "Tension", "Poids"], 2))
		self.assertTrue(all("categorie" not in l for l in nouveau["caracteristiques"]))

	def test_classer_ne_change_que_la_categorie(self):
		c = contenu([ligne("Tension", valeur="24", unite="V"), ligne("Débit", valeur="75", unite="GPD"), ligne("Préfiltre", "Filtration", valeur="PP"), ligne("Poids")])
		self.assertEqual(noms(c["caracteristiques"]), ["Préfiltre", "Tension", "Débit", "Poids"])      # tel que l'IA le reçoit
		data = {"classement": [{"index": 1, "categorie": "Électrique", "nom": "Tension modifiée", "valeur": "999"}, {"index": 2, "categorie": "performances"},
			{"index": 0, "categorie": "Filtration"}, {"index": 3, "categorie": "Inventée"}, {"index": 9, "categorie": "Électrique"}, {"index": True, "categorie": "Électrique"}, "x"],
			"suggestions": ["« Préfiltre » : la valeur répète le nom.", "", 12] + ["remarque"] * 9}
		nouveau, changements, suggestions = P.classer(c, data, LISTE)
		self.assertEqual([(l["nom"], l["valeur"], l.get("categorie")) for l in nouveau["caracteristiques"]],
			[("Débit", "75", "Performances"), ("Préfiltre", "PP", "Filtration"), ("Tension", "24", "Électrique"), ("Poids", "1", None)])
		self.assertEqual([(m["index"], m["libelle"]) for m in changements], [(0, "« Débit » → Performances"), (2, "« Tension » → Électrique")])
		self.assertEqual((suggestions[0], len(suggestions)), ("« Préfiltre » : la valeur répète le nom.", 6))
		self.assertEqual(noms(c["caracteristiques"]), ["Préfiltre", "Tension", "Débit", "Poids"])      # l'original n'est pas touché
		# une ligne que l'IA sort de sa catégorie perd la clé
		nouveau, changements, _ = P.classer(c, {"classement": [{"index": 0, "categorie": ""}]}, LISTE)
		self.assertTrue(all("categorie" not in l for l in nouveau["caracteristiques"]))
		self.assertEqual(changements[0]["libelle"], "« Préfiltre » → sans catégorie")
		self.assertEqual(P.classer(c, None, LISTE)[1:], ([], []))

	def test_organiser_avec_l_ia(self):
		c = contenu([ligne("Tension", valeur="24", unite="V"), ligne("Débit", valeur="75", unite="GPD")])
		dossier = type("D", (), {"name": "DPR-TEST", "categories_caracteristiques": "\n".join(LISTE)})()
		reponse = {"classement": [{"index": 0, "categorie": "Électrique"}, {"index": 1, "categorie": "Performances"}], "suggestions": []}
		with patch.object(T, "chat_json", return_value=reponse) as chat, patch.object(T.journal, "suivre_generation"), \
			patch.object(T.frappe, "generate_hash", return_value="x"), patch("aquaworld_ia.ia.client.reglages", return_value={}):
			r = T.organiser_caracteristiques(dossier, "Fiche technique", contexte_simple(), c)
			envoye = json.loads(chat.call_args.args[1])
			self.assertEqual(envoye["categories_caracteristiques"], LISTE)
			self.assertEqual([(l["index"], l["nom"], l["valeur"]) for l in envoye["lignes"]], [(0, "Tension", "24"), (1, "Débit", "75")])
			self.assertIn("EXACTEMENT parmi", chat.call_args.args[0])
			self.assertEqual([(l["nom"], l["categorie"]) for l in r["contenu"]["caracteristiques"]], [("Débit", "Performances"), ("Tension", "Électrique")])
			self.assertEqual((len(r["changements"]), r["categories"]), (2, LISTE))
			# déjà rangé, rien à signaler : un message, pas une proposition vide
			chat.return_value = {"classement": [], "suggestions": []}
			with self.assertRaises(ValueError) as e:
				T.organiser_caracteristiques(dossier, "Fiche technique", contexte_simple(), r["contenu"])
			self.assertIn("déjà rangé", str(e.exception))
			with self.assertRaises(ValueError):
				T.organiser_caracteristiques(dossier, "Fiche technique", contexte_simple(), contenu([ligne("Seule")]))

	def test_redaction_classe_dans_la_liste_du_dossier(self):
		dossier = type("D", (), {"name": "DPR-TEST", "categories_caracteristiques": "\n".join(LISTE)})()
		reponse = {"titre": "Fiche technique — Osmoseur", "resume": "Un produit.", "sections": [{"titre": "Utilisation", "texte": "Texte.", "article": "", "source": "Article TEST-P"}],
			"caracteristiques": [{"nom": "Tension", "valeur": "24", "unite": "V", "article": "", "source": "Article TEST-P", "categorie": "électrique"},
				{"nom": "Poids", "valeur": "4", "unite": "kg", "article": "", "source": "Article TEST-P", "categorie": "Catégorie inventée"},
				{"nom": "Débit", "valeur": "75", "unite": "GPD", "article": "", "source": "Article TEST-P", "categorie": "Performances"}, "ligne illisible"],
			"points_a_verifier": []}
		with patch.object(T, "chat_json", return_value=reponse) as chat, patch("aquaworld_ia.ia.client.reglages", return_value={}):
			c = T.generer(dossier, "Fiche technique", contexte_simple())
		self.assertEqual([(l["nom"], l.get("categorie")) for l in c["caracteristiques"]], [("Débit", "Performances"), ("Tension", "Électrique"), ("Poids", None)])
		self.assertEqual(json.loads(chat.call_args.args[1])["categories_caracteristiques"], LISTE)
		self.assertIn(P.REGLE_CATEGORIES, chat.call_args.args[0])

	def test_les_consignes_donnent_la_regle_et_la_liste(self):
		for consigne in (P.CONSIGNE, P.CONSIGNE_CARACTERISTIQUES, P.CONSIGNE_ORGANISER):
			self.assertIn(P.REGLE_CATEGORIES, consigne)
			self.assertIn("categories_caracteristiques", consigne)
		self.assertEqual(P.document_pour_ia(contenu([ligne("Tension", "Électrique"), ligne("Poids")]))["caracteristiques"],
			[{"nom": "Tension", "valeur": "1", "unite": "", "article": "", "categorie": "Électrique"}, {"nom": "Poids", "valeur": "1", "unite": "", "article": ""}])

	def test_reponse_de_redaction_avec_categories(self):
		data = S.depuis_ia({"titre": "T", "resume": "R", "caracteristiques": [{"nom": "Tension", "valeur": 24, "unite": "V", "article": None, "source": "Article TEST-P", "categorie": None},
			{"nom": "Débit", "valeur": "75", "unite": "GPD", "article": "", "source": "Article TEST-P", "categorie": "Performances"}]})
		c = S.normaliser(data, contexte_simple())
		self.assertEqual([(l["nom"], l["valeur"], l.get("categorie")) for l in c["caracteristiques"]], [("Débit", "75", "Performances"), ("Tension", "24", None)])


class TestTraduction(unittest.TestCase):
	def test_une_categorie_se_traduit_une_fois(self):
		c = contenu([ligne("Tension", "Électrique"), ligne("Courant", "Électrique"), ligne("Débit", "Performances"), ligne("Poids")])
		chemins = [p for p in S.champs_traduisibles(c) if p[-1] == "categorie"]
		self.assertEqual(chemins, [("caracteristiques", 0, "categorie"), ("caracteristiques", 2, "categorie")])
		self.assertIn(("libelles", "autres"), S.champs_traduisibles(c))
		traduit = copy.deepcopy(c)
		traduit["caracteristiques"][0]["categorie"] = "Electrical"
		traduit["caracteristiques"][2]["categorie"] = "Performance"
		S.propager_categories(traduit, c)
		self.assertEqual([l.get("categorie") for l in traduit["caracteristiques"]], ["Electrical", "Electrical", "Performance", None])
		self.assertEqual(noms(S.normaliser(traduit, contexte_simple())["caracteristiques"]), noms(c["caracteristiques"]))


class TestPdf(unittest.TestCase):
	def tableau(self, lignes, ctx=None):
		ctx = ctx or contexte_simple()
		tex = L.source(S.normaliser({**contenu_simple(), "caracteristiques": lignes}, ctx), ctx)
		debut = tex.index(r"\begin{longtable}")
		return tex[debut:tex.index(r"\end{longtable}", debut)]

	def test_une_bande_par_categorie_et_autres_en_dernier(self):
		t = self.tableau([ligne("Tension", "Électrique"), ligne("Poids"), ligne("Débit", "Performances"), ligne("Courant", "Électrique")])
		ordre = [t.index(x) for x in ("Électrique}", "Tension", "Courant", "Performances}", "Débit", S.LIBELLES["autres"] + "}", "Poids")]
		self.assertEqual(ordre, sorted(ordre))
		self.assertEqual(t.count(r"\rowcolor{white}\multicolumn{2}{l}"), 3)
		self.assertEqual(t.count(r"}\\*"), 3)                                         # une bande ne reste pas seule en bas de page

	def test_sans_categorie_le_tableau_est_d_un_seul_tenant(self):
		t = self.tableau([ligne("Tension"), ligne("Poids")])
		self.assertNotIn(r"\multicolumn", t)
		self.assertNotIn(S.LIBELLES["autres"], t)

	def test_colonne_des_modeles_seulement_si_elle_sert(self):
		commun = self.tableau([ligne("Tension"), ligne("Poids")])
		self.assertNotIn(S.LIBELLES["portee"], commun)
		self.assertNotIn(S.LIBELLES["commun"], commun)
		self.assertEqual(commun.count("linewidth}"), 2)
		propre = self.tableau([ligne("Tension", "Électrique"), ligne("Poids", "Électrique", article="TEST-P-V")])
		self.assertIn(S.LIBELLES["portee"], propre)
		self.assertIn("TEST-P-V", propre)
		self.assertIn(S.LIBELLES["commun"], propre)
		self.assertEqual((propre.count("linewidth}"), propre.count(r"\multicolumn{3}{l}")), (3, 1))

	def test_ancienne_version_sans_le_libelle(self):
		ctx = contexte_simple()
		c = S.normaliser({**contenu_simple(), "caracteristiques": [ligne("Tension", "Électrique"), ligne("Poids")]}, ctx)
		del c["libelles"]["autres"]
		self.assertIn(S.LIBELLES["autres"], L.source(c, ctx))


if __name__ == "__main__":
	unittest.main()
