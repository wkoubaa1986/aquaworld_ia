"""Fiches par variante : observations de photos, choix des photos, dérivation depuis la fiche du produit, reprise
des spécificités corrigées, garde sur les nombres, empreintes et composition. Fonctions pures : aucun site, aucun
appel IA."""

import copy
import shutil
import unittest

from aquaworld_ia.documents_produit import illustrations as I
from aquaworld_ia.documents_produit import latex as L
from aquaworld_ia.documents_produit import observations as O
from aquaworld_ia.documents_produit import structure as S
from aquaworld_ia.documents_produit import variantes as V


def contexte_mere():
	variante = lambda ref, couleur: {"name": ref, "item_name": "Mini fontaine, " + couleur, "brand": "ecoPurium",
		"description": "Fontaine " + couleur + ", réservoir 2.8 G", "image": "/files/" + ref + ".jpg",
		"attributs": [{"nom": "Couleur", "valeur": couleur}]}
	return {
		"article": {"name": "FF", "item_name": "Mini fontaine", "brand": "ecoPurium", "description": "Fontaine 75 GPD", "image": "", "attributs": []},
		"variantes": [variante("FF-BD", "beige doré"), variante("FF-ND", "noir doré")],
		"images": [{"image": "/files/gamme.jpg", "nom": "gamme.jpg", "hash": "h0", "pages": "", "legende": "La gamme", "article": ""}],
		"sources": [], "consignes": "", "logo": "",
		"preuves": [{"source": "S1 p.1", "texte": "à ne pas recopier"}],
	}


def contenu_mere(ctx=None):
	ctx = ctx or contexte_mere()
	return S.normaliser({
		"titre": "Fiche technique — Mini fontaine",
		"resume": "Une fontaine à eau osmosée de 75 GPD.",
		"sections": [
			{"titre": "Applications", "texte": "Bureaux et cuisines.", "article": "FF", "source": "Article FF"},
			{"titre": "Finition dorée claire", "texte": "Propre au modèle beige.", "article": "FF-BD", "source": "Article FF-BD"},
			{"titre": "Finition noire", "texte": "Propre au modèle noir.", "article": "FF-ND", "source": "Article FF-ND"},
		],
		"caracteristiques": [
			{"nom": "Débit", "valeur": "75", "unite": "GPD", "article": "", "source": "Article FF"},
			{"nom": "Réservoir", "valeur": "2.8", "unite": "G", "article": "FF-ND", "source": "Article FF-ND"},
		],
		"points_a_verifier": ["Point de la gamme"],
	}, ctx)


def photos_nd():
	return [
		{"image": "/files/FF-ND_pack.jpg", "nom": "FF-ND_pack.jpg", "empreinte": "e-pack", "principale": False},
		{"image": "/files/FF-ND.jpg", "nom": "FF-ND.jpg", "empreinte": "e-face", "principale": True},
		{"image": "/files/FF-ND-copie.jpg", "nom": "FF-ND-copie.jpg", "empreinte": "e-face", "principale": False},
		{"image": "/files/FF-ND_rear.jpg", "nom": "FF-ND_rear.jpg", "empreinte": "e-arriere", "principale": False},
		{"image": "/files/FF-ND_x.jpg", "nom": "FF-ND_x.jpg", "empreinte": "e-nonlue", "principale": False},
	]


def observations_nd():
	return {
		"e-face": O.normaliser({"vue": "Face", "legende": "Vue de face", "description": "Fontaine noire à façade dorée.",
			"elements": ["2 robinets", "façade dorée"], "textes_lus": ["ecoPurium"]}),
		"e-arriere": O.normaliser({"vue": "arrière", "description": "Raccords à l'arrière.", "elements": ["3 raccords"]}),
		"e-pack": O.normaliser({"vue": "emballage", "legende": "Carton d’expédition", "description": "Carton."}),
	}


def specificites(article="FF-ND"):
	return V.normaliser_specificites({
		"resume": "La mini fontaine en finition noir doré.",
		"specificites": {"titre": "Un titre choisi par l’IA", "texte": "• Couleur noir doré\n• 2 robinets en façade", "source": "Article FF-ND ; Photo P1"},
		"caracteristiques": [
			{"nom": "Réservoir", "valeur": "2.8", "unite": "G", "source": "Article FF-ND"},
			{"nom": "Robinets", "valeur": "2", "unite": "", "source": "Photo P1"},
			{"nom": "Inventée", "valeur": "x", "unite": "", "source": "Catalogue"},
			{"nom": "", "valeur": "ligne vide"},
		],
		"points_a_verifier": [{"texte": "Couleur exacte à confirmer"}],
	}, article, O.choisir_photos(photos_nd(), observations_nd()))


class TestObservations(unittest.TestCase):
	def test_normaliser_est_tolerant_sur_la_forme_et_borne_les_tailles(self):
		obs = O.normaliser({"vue": "Côté", "legende": "  Vue   de côté ", "description": "x" * 2000,
			"elements": ["• a", "a", {"pas": 1, "du": 2}, None, 5, {"texte": "en objet"}, "b" * 500] + ["e%d" % i for i in range(40)],
			"textes_lus": "ligne 1\n\nligne 2", "incertitudes": "pas une liste"})
		self.assertEqual(obs["vue"], "cote")
		self.assertEqual(obs["legende"], "Vue de côté")
		self.assertEqual(len(obs["description"]), 900)
		self.assertEqual(obs["elements"][:3], ["a", "5", "en objet"])
		self.assertEqual(len(obs["elements"]), 25)
		self.assertTrue(all(len(e) <= 200 for e in obs["elements"]))
		self.assertEqual(obs["textes_lus"], ["ligne 1", "ligne 2"])
		self.assertEqual(obs["incertitudes"], ["pas une liste"])
		self.assertEqual(O.normaliser({"vue": "radiographie"})["vue"], "autre")
		with self.assertRaises(ValueError):
			O.normaliser(["pas", "un", "objet"])

	def test_champs_du_document_et_empreinte(self):
		class Doc(dict):
			set = dict.__setitem__

		doc, obs = Doc(), observations_nd()["e-face"]
		O.vers_document(doc, obs)
		self.assertEqual(doc["elements"], "2 robinets\nfaçade dorée")
		self.assertEqual(O.normaliser(O.depuis_document(doc)), obs)
		self.assertEqual(O.empreinte_observation(obs), O.empreinte_observation(copy.deepcopy(obs)))
		self.assertNotEqual(O.empreinte_observation(obs), O.empreinte_observation({**obs, "elements": ["1 robinet"]}))
		self.assertEqual(O.empreinte_observation(None), "")

	def test_choix_des_photos_face_d_abord_sans_doublon_de_contenu(self):
		choisies = O.choisir_photos(photos_nd(), observations_nd())
		self.assertEqual([p["empreinte"] for p in choisies], ["e-face", "e-arriere", "e-pack", "e-nonlue"])
		self.assertEqual([p["id"] for p in choisies], ["P1", "P2", "P3", "P4"])
		self.assertEqual(choisies[0]["image"], "/files/FF-ND.jpg")
		# Légende : celle de l'observation, sinon le libellé de la vue, sinon le nom du fichier.
		self.assertEqual([p["legende"] for p in choisies], ["Vue de face", "Vue arrière", "Carton d’expédition", "FF-ND_x"])
		self.assertEqual(len(O.choisir_photos(photos_nd(), observations_nd(), maximum=2)), 2)
		self.assertEqual(O.choisir_photos([], {}), [])

	def test_sans_observation_l_image_de_l_article_passe_en_premier(self):
		choisies = O.choisir_photos(photos_nd(), {})
		self.assertEqual(choisies[0]["empreinte"], "e-face")
		self.assertEqual([p["empreinte"] for p in choisies[1:]], ["e-pack", "e-arriere", "e-nonlue"])

	def test_images_a_lire(self):
		obs = {"e-face": {**observations_nd()["e-face"], "corrigee": 1}, "e-pack": {**observations_nd()["e-pack"], "corrigee": 0},
			"e-arriere": {**observations_nd()["e-arriere"], "perimee": 1}}
		self.assertEqual([p["empreinte"] for p in O.a_lire(photos_nd(), obs)], ["e-arriere", "e-nonlue"])
		# Forcer relit tout, sauf ce que l'utilisateur a corrigé.
		self.assertEqual([p["empreinte"] for p in O.a_lire(photos_nd(), obs, forcer=True)], ["e-pack", "e-arriere", "e-nonlue"])


class TestDerivation(unittest.TestCase):
	def setUp(self):
		self.ctx_mere, self.info = contexte_mere(), contexte_mere()["variantes"][1]
		self.mere = contenu_mere(self.ctx_mere)
		self.observations = observations_nd()
		self.photos = O.choisir_photos(photos_nd(), self.observations)
		self.ctx = V.contexte_variante(self.ctx_mere, self.info, self.photos, "DOC-1", "emp-spec")

	def test_contexte_reduit_a_la_variante_et_a_ses_photos(self):
		self.assertEqual([v["name"] for v in self.ctx["variantes"]], ["FF-ND"])
		self.assertEqual(self.ctx["variante"], "FF-ND")
		self.assertEqual(self.ctx["article"]["name"], "FF")
		self.assertEqual([im["image"] for im in self.ctx["images"]], [p["image"] for p in self.photos])
		self.assertTrue(all(im["article"] == "" for im in self.ctx["images"]))
		self.assertNotIn("preuves", self.ctx)
		self.assertEqual(self.ctx["fiche_variante"], {"mere": "DOC-1", "empreinte_specifiques": "emp-spec"})
		self.assertEqual(len(self.ctx_mere["variantes"]), 2, "le contexte de la fiche du produit n'est pas modifié")

	def test_fiche_derivee_specificites_puis_partie_commune(self):
		c = V.deriver(self.mere, self.ctx, specificites())
		self.assertEqual(c["titre"], "Mini fontaine, noir doré")
		self.assertEqual(c["resume"], "La mini fontaine en finition noir doré.")
		self.assertEqual([s["titre"] for s in c["sections"]], ["Spécificités de ce modèle", "Applications", "Finition noire"])
		# Portée : la variante pour ce qui lui est propre, vide pour ce qui vient de la fiche du produit.
		self.assertEqual([s["article"] for s in c["sections"]], ["FF-ND", "", ""])
		# La caractéristique propre « Réservoir » remplace celle de même nom reprise de la fiche du produit.
		self.assertEqual([(x["nom"], x["article"]) for x in c["caracteristiques"]], [("Réservoir", "FF-ND"), ("Débit", "")])
		self.assertEqual([v["article"] for v in c["variantes"]], ["FF-ND"])
		self.assertEqual(c["libelles"]["variantes"], V.LIBELLE_REFERENCE)
		self.assertEqual(c["legendes"], [p["legende"] for p in self.photos])
		# Les points de la gamme ne suivent pas.
		self.assertEqual(c["points_a_verifier"], ["Couleur exacte à confirmer"])
		self.assertEqual(S.normaliser(c, self.ctx), c)

	def test_fiche_du_produit_non_validee_bloque_la_validation(self):
		c = V.deriver(self.mere, self.ctx, specificites(), mere_validee=False, numero_mere=3)
		self.assertTrue(c["points_a_verifier"][-1].startswith(V.POINT_MERE + " (version 3)"))

	def test_sans_resume_propre_celui_de_la_gamme(self):
		spec = {**specificites(), "resume": ""}
		self.assertEqual(V.deriver(self.mere, self.ctx, spec)["resume"], self.mere["resume"])

	def test_sources_des_specificites(self):
		spec = specificites()
		self.assertEqual(spec["sections"][0]["source"], "Article FF-ND ; Photo P1")
		# Une caractéristique vient de l'article de la variante : celle tirée d'une photo seule, d'une source
		# inconnue ou sans nom est écartée.
		self.assertEqual([(c["nom"], c["source"]) for c in spec["caracteristiques"]], [("Réservoir", "Article FF-ND")])
		# Un texte seul devient la rubrique.
		autre = V.normaliser_specificites({"specificites": "Texte seul", "caracteristiques": [{"nom": "A", "valeur": "b", "source": "Photo P9"}]},
			"FF-ND", self.photos)
		self.assertEqual(autre["sections"][0]["titre"], V.TITRE_SPECIFICITES)
		self.assertEqual(autre["sections"][0]["source"], "Article FF-ND")
		# Des lignes rendues en liste (ou en objets) deviennent des puces.
		liste = V.normaliser_specificites({"specificites": ["Couleur noire", {"texte": "• Deux robinets"}]}, "FF-ND", self.photos)
		self.assertEqual(liste["sections"][0]["texte"], "• Couleur noire\n• Deux robinets")
		self.assertEqual(autre["caracteristiques"], [])
		self.assertEqual(autre["points_a_verifier"], [])
		# Un attribut de la variante rendu en caractéristique ferait doublon avec le bloc de référence.
		doublon = V.normaliser_specificites({"specificites": "x", "caracteristiques": [
			{"nom": " couleur ", "valeur": "noir doré", "source": "Article FF-ND"}, {"nom": "Réservoir", "valeur": "2.8", "source": "Article FF-ND"}]},
			"FF-ND", self.photos, ["Couleur"])
		self.assertEqual([c["nom"] for c in doublon["caracteristiques"]], ["Réservoir"])
		with self.assertRaises(ValueError):
			V.normaliser_specificites("texte", "FF-ND", self.photos)

	def test_reprise_des_specificites_corrigees_sur_une_fiche_du_produit_modifiee(self):
		c = V.deriver(self.mere, self.ctx, specificites(), mere_validee=False)
		# L'utilisateur corrige la rubrique propre, résout un point et retouche (à tort) une rubrique reprise.
		c["sections"][0]["texte"] = "Texte corrigé par l’utilisateur."
		c["sections"][1]["texte"] = "Retouche locale d’une rubrique reprise."
		c["points_resolus"] = ["Couleur exacte à confirmer"]
		c["points_a_verifier"] = [p for p in c["points_a_verifier"] if p != "Couleur exacte à confirmer"]
		c = S.normaliser(c, self.ctx)
		reprise = V.reprendre_specificites(c, "FF-ND")
		self.assertEqual([s["texte"] for s in reprise["sections"]], ["Texte corrigé par l’utilisateur."])
		self.assertFalse(any(p.startswith(V.POINT_MERE) for p in reprise["points_a_verifier"]))
		nouvelle_mere = copy.deepcopy(self.mere)
		nouvelle_mere["sections"][0]["texte"] = "Bureaux, cuisines et salles d’attente."
		nouvelle_mere["caracteristiques"].append({"nom": "Tension", "valeur": "220", "unite": "V", "article": "", "source": "Article FF"})
		d = V.deriver(nouvelle_mere, self.ctx, reprise)
		self.assertEqual(d["sections"][0]["texte"], "Texte corrigé par l’utilisateur.")
		self.assertEqual(d["sections"][1]["texte"], "Bureaux, cuisines et salles d’attente.")
		self.assertIn("Tension", [x["nom"] for x in d["caracteristiques"]])
		self.assertEqual(d["points_resolus"], ["Couleur exacte à confirmer"])
		self.assertEqual(d["points_a_verifier"], [])

	def test_nombres_des_specificites_verifies_contre_les_donnees(self):
		requete = V.requete_specificites(self.ctx_mere, self.mere, self.info, self.photos, self.observations)
		connus = V.nombres_connus(requete)
		self.assertEqual(V.verifier_nombres(specificites(), connus)["points_a_verifier"], specificites()["points_a_verifier"])
		# « 3 raccords » dans une observation, « trois » ailleurs : un nombre en lettres des données vaut ses chiffres.
		self.assertNotIn(3, I.corpus_nombres({"t": "Trois leviers"}, None))
		self.assertIn(3, V.nombres_connus({"t": "Trois leviers et douze voyants"}))
		self.assertIn(12, V.nombres_connus({"t": "Trois leviers et douze voyants"}))
		spec = specificites()
		spec["sections"][0]["texte"] += " Débit de 100 GPD sous 4,5 bar."
		verifie = V.verifier_nombres(spec, connus)
		self.assertIn("100, 4,5", verifie["points_a_verifier"][-1])
		with self.assertRaises(ValueError):
			V.specificites_depuis_reponse({"resume": "", "caracteristiques": []}, requete, self.info, self.photos)

	def test_mention_de_conformite_lue_sur_une_photo(self):
		observations = {**self.observations, "e-face": O.normaliser({"vue": "face", "textes_lus": ["CE", "ecoPurium"]})}
		requete = V.requete_specificites(self.ctx_mere, self.mere, self.info, self.photos, observations)
		spec = specificites()
		spec["sections"][0]["texte"] += "\n• Marquage CE et référence AP-CE-5"
		verifie = V.verifier_mentions(spec, requete)
		self.assertEqual(verifie["points_a_verifier"][-1], "Mention de conformité absente des données de l’article, à confirmer ou à retirer : CE")
		# La même mention écrite dans la description de la variante est une donnée de l'entreprise.
		info = {**self.info, "description": "Fontaine noir doré, conforme CE"}
		requete = V.requete_specificites(self.ctx_mere, self.mere, info, self.photos, observations)
		self.assertEqual(V.verifier_mentions(spec, requete)["points_a_verifier"], spec["points_a_verifier"])
		self.assertEqual(V.verifier_mentions(specificites(), requete)["points_a_verifier"], specificites()["points_a_verifier"])

	def test_galerie_compacte_par_defaut_et_disposition_choisie_respectee(self):
		def colonnes(nombre_images, mise_en_page=None):
			ctx = {"images": [{}] * nombre_images, **({"mise_en_page": mise_en_page} if mise_en_page else {})}
			return V.mise_en_page_variante(ctx).get("mise_en_page", {}).get("colonnes_photos", 1)

		self.assertEqual([colonnes(n) for n in (0, 1, 2, 3, 4, 8)], [1, 1, 1, 2, 3, 3])
		self.assertEqual(colonnes(6, {"colonnes_photos": 2}), 2)
		self.assertEqual(colonnes(6, {"style_galerie": "mosaique"}), 1)
		ctx = {"images": [{}] * 5, "mise_en_page": {"couleur": "#112233"}}
		self.assertEqual(V.mise_en_page_variante(ctx)["mise_en_page"]["couleur"], "#112233")
		self.assertEqual(V.mise_en_page_variante(V.mise_en_page_variante(ctx)), V.mise_en_page_variante(ctx))
		self.assertNotIn("colonnes_photos", ctx["mise_en_page"], "le contexte d'origine n'est pas modifié")

	def test_requete_ne_repete_que_ce_qui_concerne_la_variante(self):
		r = V.requete_specificites(self.ctx_mere, self.mere, self.info, self.photos, self.observations)
		self.assertEqual(r["variante"]["reference"], "FF-ND")
		self.assertEqual(r["gamme"]["valeurs_attributs"], {"Couleur": ["beige doré", "noir doré"]})
		self.assertEqual([p["id"] for p in r["photos"]], ["P1", "P2", "P3", "P4"])
		self.assertEqual(r["photos"][0]["elements"], ["2 robinets", "façade dorée"])
		self.assertEqual(r["photos"][3]["description"], "", "une photo non lue n'apporte que son nom")
		self.assertEqual([s["titre"] for s in r["fiche_produit"]["rubriques"]], ["Applications", "Finition noire"])
		self.assertNotIn("Finition dorée claire", str(r))
		self.assertIn("Tu rédiges en français ce qu'UNE variante a de propre", V.systeme())
		self.assertIn("N'invente aucune valeur", V.systeme())
		self.assertIn("aucune estimation", V.systeme())

	def test_empreintes(self):
		e = V.empreinte_variante("DOC-1", True, self.info, self.photos, self.observations)
		self.assertEqual(e, V.empreinte_variante("DOC-1", True, copy.deepcopy(self.info), list(self.photos), dict(self.observations)))
		# Périmée si la fiche du produit change ou est validée, si la variante, ses photos ou une observation changent.
		autres = [
			V.empreinte_variante("DOC-2", True, self.info, self.photos, self.observations),
			V.empreinte_variante("DOC-1", False, self.info, self.photos, self.observations),
			V.empreinte_variante("DOC-1", True, {**self.info, "description": "autre"}, self.photos, self.observations),
			V.empreinte_variante("DOC-1", True, self.info, self.photos[:2], self.observations),
			V.empreinte_variante("DOC-1", True, self.info, self.photos, {**self.observations, "e-face": O.normaliser({"vue": "face", "elements": ["1 robinet"]})}),
		]
		self.assertEqual(len({e, *autres}), 6)
		# Les spécificités, elles, ne dépendent pas de la fiche du produit : elles sont reprises quand elle seule change.
		self.assertEqual(V.empreinte_specifiques(self.info, self.photos, self.observations),
			V.empreinte_specifiques(copy.deepcopy(self.info), self.photos, self.observations))

	def test_titre_long_tronque(self):
		self.assertEqual(len(V.titre_variante({"name": "X", "item_name": "n" * 300})), 140)
		self.assertEqual(V.titre_variante({"name": "X", "item_name": ""}), "X")


class TestReponseIA(unittest.TestCase):
	def test_nombres_et_null_rendus_par_le_modele_deviennent_du_texte(self):
		ctx = contexte_mere()
		brut = {"titre": "Fiche", "resume": None, "sections": [{"titre": "Usage", "texte": "Texte", "article": None, "source": "Article FF"}],
			"caracteristiques": [{"nom": "Débit", "valeur": 75, "unite": None, "article": "", "source": "Article FF"},
				{"nom": "Réservoir", "valeur": 2.8, "unite": "G", "article": "FF-ND", "source": "Article FF-ND"}],
			"points_a_verifier": ["À vérifier", None, {"texte": "Point rendu en objet"}, {"point": "Autre forme", "gravite": 2}]}
		with self.assertRaises(ValueError):
			S.normaliser(brut, ctx)
		c = S.normaliser(S.depuis_ia(brut), ctx)
		self.assertEqual([(x["valeur"], x["unite"]) for x in c["caracteristiques"]], [("75", ""), ("2.8", "G")])
		self.assertEqual(c["resume"], "")
		self.assertEqual(c["points_a_verifier"], ["À vérifier", "Point rendu en objet", "Autre forme"])
		self.assertEqual(brut["caracteristiques"][0]["valeur"], 75, "la réponse d'origine n'est pas modifiée")
		# Un objet là où un texte est attendu reste refusé.
		with self.assertRaises(ValueError):
			S.normaliser(S.depuis_ia({**brut, "sections": [{"titre": {"x": 1}, "texte": "t"}]}), ctx)


class TestCompositionVariante(unittest.TestCase):
	def setUp(self):
		ctx_mere = contexte_mere()
		self.ctx = V.contexte_variante(ctx_mere, ctx_mere["variantes"][1], [], "DOC-1", "e")
		self.contenu = V.deriver(contenu_mere(ctx_mere), self.ctx, specificites())

	def test_source_latex_bloc_de_reference_sans_modeles_concernes(self):
		tex = L.source(self.contenu, self.ctx)
		self.assertIn(r"\docsection{" + V.LIBELLE_REFERENCE + "}", tex)
		self.assertIn(r"ecoPurium\quad FF-ND\par", tex)
		self.assertIn(r"Couleur & noir doré\\", tex)
		self.assertNotIn("Modèles concernés", tex)
		self.assertNotIn("Toute la gamme", tex)
		# La fiche du produit garde ses trois colonnes et son tableau des variantes.
		gamme = L.source(contenu_mere(), {k: v for k, v in contexte_mere().items() if k != "images"} | {"images": []})
		self.assertIn("Modèles concernés", gamme)
		self.assertIn("Variantes couvertes", gamme)

	@unittest.skipUnless(shutil.which("xelatex"), "XeLaTeX requis pour les tests PDF")
	def test_pdf_d_une_fiche_de_variante(self):
		import pymupdf

		pdf, _archive = L.compiler(L.source(self.contenu, self.ctx), {})
		with pymupdf.open(stream=pdf, filetype="pdf") as doc:
			texte = "".join(page.get_text() for page in doc)
		for attendu in ("Mini fontaine, noir doré", "FF-ND", "Spécificités de ce modèle", "Référence et configuration", "Réservoir"):
			self.assertIn(attendu, texte)
		self.assertNotIn("Modèles concernés", texte)


if __name__ == "__main__":
	unittest.main()
