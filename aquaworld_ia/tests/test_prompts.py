from __future__ import annotations

import json
import unittest

from aquaworld_ia.emballage import prompts as P

STYLE = {"titre": "Bleu profond", "description": "Fond marin, lumière douce.", "ambiance": "calm fresh clean", "palette": ["#0a3d62", "#ffffff"]}


class TestPrompts(unittest.TestCase):
	def test_interdiction_partout(self):
		for p in (P.prompt_variante(STYLE, "Osmoseur AquaPure", "AquaWorld"),
		          P.prompt_face_secondaire(STYLE, "Osmoseur AquaPure", "cote_gauche"),
		          P.prompt_mockup("Osmoseur AquaPure")):
			for mot in ("text", "logo"):
				self.assertIn(mot, p.lower())

	def test_variante_nomme_le_produit_et_la_marque(self):
		p = P.prompt_variante(STYLE, "Osmoseur AquaPure", "AquaWorld", brief="cible : familles")
		self.assertIn("Osmoseur AquaPure", p)
		self.assertIn("AquaWorld", p)
		self.assertIn("#0a3d62", p)
		self.assertIn("cible : familles", p)
		self.assertIn("DO NOT draw", p)

	def test_face_secondaire_nomme_la_face(self):
		self.assertIn("LEFT side panel", P.prompt_face_secondaire(STYLE, "X", "cote_gauche"))
		self.assertIn("TOP panel", P.prompt_face_secondaire(STYLE, "X", "dessus"))

	def test_palette_imposee_prime(self):
		self.assertIn("#123456", P.prompt_variante(STYLE, "X", palette="#123456"))


class TestConsigneDuFond(unittest.TestCase):
	"""06/10/2026 : « lorsque je génère le fond, est-ce que je peux contrôler ce que je génère ? »"""

	def test_la_consigne_part_a_l_ia_et_prime(self):
		from aquaworld_ia.emballage.prompts import prompt_fond
		p = prompt_fond({"titre": "Vagues minimalistes"}, "Sel", palette="#44a7ed, #0264c3", consigne="vagues bleues en bas, blanc en haut")
		self.assertIn("vagues bleues en bas, blanc en haut", p)
		self.assertIn("takes precedence", p)
		self.assertNotIn("no objects", p)                      # la consigne peut demander des éléments (gouttes, cristaux)
		self.assertIn("Vagues minimalistes", p)
		self.assertIn("#44a7ed, #0264c3", p)

	def test_sans_consigne_rien_ne_change(self):
		from aquaworld_ia.emballage.prompts import prompt_fond
		p = prompt_fond(None, "Sel")
		self.assertNotIn("takes precedence", p)
		self.assertIn("No product, no objects, no people", p)


class TestPromptDocumentsProduit(unittest.TestCase):
	def test_les_donnees_de_l_article_sont_des_faits(self):
		"""06/11/2026 : la fiche disait « annoncé avec pompe et socle métallique » — le nom de l'article est
		une donnée de l'entreprise, pas une source à nuancer. La prudence reste pour ce qui manque."""
		import inspect

		from aquaworld_ia.documents_produit import traitement

		systeme = inspect.getsource(traitement.generer) + traitement.REGLES_COMMUNES
		self.assertIn("énonce-les comme des faits", systeme)
		self.assertIn("« annoncé »", systeme)
		self.assertIn("points_a_verifier", systeme)
		self.assertIn("ne crée pas de rubrique « Présentation »", systeme)   # le résumé est déjà la présentation

	def test_connaissances_generales_sur_option_seulement(self):
		import inspect

		from aquaworld_ia.documents_produit import traitement

		src = inspect.getsource(traitement.generer)
		self.assertIn('if ctx.get("connaissances_generales"):', src)
		self.assertIn("Connaissances générales", traitement.CONNAISSANCES_GENERALES)
		self.assertIn("Reste interdit sans source : toute valeur chiffrée", traitement.CONNAISSANCES_GENERALES)


class TestReecriturePartie(unittest.TestCase):
	"""« Changer cette partie par IA en ajoutant une instruction » (06/11/2026) : réécriture d'une rubrique ou du
	résumé, avec les mêmes règles que la rédaction, sans toucher au reste ; appel IA simulé."""

	def _ctx_et_contenu(self):
		from aquaworld_ia.documents_produit import structure as S
		from aquaworld_ia.tests.test_documents_produit import contenu_simple, contexte_simple

		ctx = contexte_simple()
		c = contenu_simple(ctx)
		c["sections"].append({"titre": "Entretien", "texte": "Texte court.", "article": "", "source": "Connaissances générales"})
		return ctx, S.normaliser(c, ctx)

	def test_rubrique_reecrite_avec_regles_et_contexte(self):
		from unittest.mock import patch

		from aquaworld_ia.documents_produit import traitement as T

		ctx, c = self._ctx_et_contenu()
		ctx["connaissances_generales"] = 1
		appels = []

		def faux_chat(system, user, **kw):
			appels.append((system, json.loads(user), kw))
			return {"titre": "Entretien courant", "texte": "Remplacer les cartouches.", "source": "Connaissances générales",
				"points_a_verifier": ["Fréquences à confirmer"]}

		with patch.object(T, "chat_json", faux_chat):
			r = T.reecrire(type("D", (), {"name": "DPR-TEST", "doctype": "Dossier Produit"})(), "Fiche technique", ctx, c,
				{"type": "section", "index": 1}, "Plus détaillé, avec les précautions")
		self.assertEqual(r, {"texte": "Remplacer les cartouches.", "points_a_verifier": ["Fréquences à confirmer"],
			"titre": "Entretien courant", "source": "Connaissances générales"})
		system, user, kw = appels[0]
		self.assertIn("UNE partie", system)
		self.assertIn("jamais « annoncé »", system)                        # règles communes partagées avec la rédaction
		self.assertIn("connaissances générales", system)
		self.assertEqual(user["partie_a_reecrire"]["titre"], "Entretien")
		self.assertEqual(user["instruction"], "Plus détaillé, avec les précautions")
		self.assertEqual([a["titre"] for a in user["document"]["autres_rubriques"]], ["Utilisation"])   # pas la rubrique visée
		self.assertEqual(kw["fonctionnalite"], "Document produit — fiche technique")

	def test_resume_et_refus(self):
		from unittest.mock import patch

		from aquaworld_ia.documents_produit import traitement as T

		ctx, c = self._ctx_et_contenu()
		d = type("D", (), {"name": "DPR-TEST", "doctype": "Dossier Produit"})()
		with patch.object(T, "chat_json", lambda s, u, **kw: {"texte": "Résumé réécrit."}):
			self.assertEqual(T.reecrire(d, "Fiche technique", ctx, c, {"type": "resume"}, "Plus court")["texte"], "Résumé réécrit.")
		with self.assertRaises(ValueError):
			T.reecrire(d, "Fiche technique", ctx, c, {"type": "section", "index": 0}, "   ")
		with self.assertRaises(ValueError):
			T.reecrire(d, "Fiche technique", ctx, c, {"type": "section", "index": 9}, "x")
		with patch.object(T, "chat_json", lambda s, u, **kw: {"texte": ""}), self.assertRaises(ValueError):
			T.reecrire(d, "Fiche technique", ctx, c, {"type": "resume"}, "x")
