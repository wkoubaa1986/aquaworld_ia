"""Transfert du contenu de référence et des documents de travail — parties pures."""
from __future__ import annotations

import unittest

from aquaworld_ia import transfert as T


class TestTransfert(unittest.TestCase):
	def test_numero_serie(self):
		self.assertEqual(T.numero_serie("MAN-2026-0004"), ("MAN-2026-", 4))
		self.assertEqual(T.numero_serie("EMB-2026-0012"), ("EMB-2026-", 12))
		self.assertIsNone(T.numero_serie("sans-numero"))
		self.assertIsNone(T.numero_serie(""))

	def test_doc_exportable_sans_identifiants(self):
		d = T._doc_exportable({"doctype": "Manuel Article", "name": "MAN-2026-0004", "titre": "Osmoseur", "owner": "x", "modified": "2026",
		                       "traductions": [{"name": "abc", "parent": "MAN-2026-0004", "parentfield": "traductions", "idx": 1, "langue": "fr", "statut": "Terminé"}]})
		self.assertEqual(d["name"], "MAN-2026-0004")
		self.assertEqual(d["titre"], "Osmoseur")
		self.assertNotIn("owner", d); self.assertNotIn("modified", d)
		self.assertEqual(d["traductions"], [{"idx": 1, "langue": "fr", "statut": "Terminé"}])


class TestCopieDesign(unittest.TestCase):
	"""13/11/2026 : un design terminé sur le dev arrive tel quel sur la prod, sans écraser un travail fait sur place."""

	COPIE = {"base_modifie": "2026-11-04 13:12:52.399041", "modifie": "2026-11-13 16:20:00.000000"}

	def test_fichiers_cites_par_la_fiche(self):
		doc = {"logo": "/private/files/logo.svg", "photo": None, "titre": "Sel <b>pur</b>",
		       "fonds_faces": '{"avant": {"mode": "image", "image": "/private/files/EMB-2026-0006-aplats-avant1.svg"}}',
		       "mise_en_page": '{"avant": [{"zone": "logo", "logo": "/files/sel photo.png"}, {"zone": "logo", "logo": "/private/files/logo.svg"}]}'}
		self.assertEqual(T.urls_fichiers(doc), ["/files/sel photo.png", "/private/files/EMB-2026-0006-aplats-avant1.svg", "/private/files/logo.svg"])

	def test_valeurs_comparees_sans_leur_ecriture(self):
		for a, b in ((None, ""), ("", None), (1, 1.0), (0, 0.0), (True, 1), ("2026-11-13", "2026-11-13"), (0.85, 0.85)):
			self.assertTrue(T.memes_valeurs(a, b), (a, b))
		for a, b in ((None, 0), ("", "0"), (1, 2), ("a", "b"), (0, ""), ("#0264c3", "#0264C3")):
			self.assertFalse(T.memes_valeurs(a, b), (a, b))

	def test_decision(self):
		self.assertEqual(T.decision_design(self.COPIE, None), "introuvable")
		self.assertEqual(T.decision_design(self.COPIE, "2026-11-04 13:12:52.399041"), "appliquer")
		self.assertEqual(T.decision_design(self.COPIE, "2026-11-13 16:20:00.000000"), "deja_a_jour")
		# modifié en prod après la copie prise par le dev : on n'écrase pas
		self.assertEqual(T.decision_design(self.COPIE, "2026-11-10 09:00:00.000000"), "modifie_sur_place")
		self.assertEqual(T.decision_design(self.COPIE, "2026-11-10 09:00:00.000000", forcer=True), "appliquer")
		self.assertEqual(T.decision_design(self.COPIE, "2026-11-13 16:20:00.000000", forcer=True), "deja_a_jour")
		# la base rend « …16:20:00 » pour un horodatage sans microsecondes
		self.assertEqual(T.decision_design(self.COPIE, "2026-11-13 16:20:00"), "deja_a_jour")
		self.assertEqual(T.decision_design({"base_modifie": "2026-11-01 08:00:00.000000", "modifie": "x"}, "2026-11-01 08:00:00"), "appliquer")

	def test_la_copie_rangee_est_complete(self):
		"""Chaque design rangé dans l'app a ses fichiers, et le patch qui l'applique est inscrit."""
		import json
		import os

		for nom in sorted(os.listdir(T.DOSSIER_DESIGNS)) if os.path.isdir(T.DOSSIER_DESIGNS) else []:
			with open(os.path.join(T.DOSSIER_DESIGNS, nom, "design.json"), encoding="utf-8") as f:
				copie = json.load(f)
			self.assertEqual((copie["name"], copie["doctype"]), (nom, T.DESIGN))
			self.assertNotEqual(copie["base_modifie"], copie["modifie"])
			self.assertFalse([k for k, v in copie["champs"].items() if isinstance(v, list)])
			for e in copie["fichiers"]:
				self.assertTrue(os.path.getsize(os.path.join(T.DOSSIER_DESIGNS, nom, "fichiers", e["fichier"])) > 0, e)
				self.assertEqual(os.path.basename(e["url"]), e["fichier"])
			# tout fichier « nouveau » cité par la fiche est du voyage : PDF, aperçu, décor
			cites = set(T.urls_fichiers(copie["champs"]))
			for champ in ("plan_a_plat", "apercu_plan"):
				if copie["champs"].get(champ):
					self.assertIn(copie["champs"][champ], {e["url"] for e in copie["fichiers"]} & cites, champ)
		with open(os.path.join(os.path.dirname(T.DOSSIER), "patches.txt"), encoding="utf-8") as f:
			self.assertIn("aquaworld_ia.patches.v0_55.design_sel_en_pastilles", f.read())


class TestFichiersDoubles(unittest.TestCase):
	"""06/10/2026 : l'import posait le fichier PUIS l'insérait comme un envoi ; Frappe en écrivait une copie
	suffixée de l'empreinte, la fiche pointait la copie, le document l'original → « Forbidden »."""

	def test_url_d_origine(self):
		h = "5d41402abc4b2a76b9719d911009a609"
		self.assertEqual(T.url_d_origine("/private/files/EMB-2026-0002-apercu-3d09a60909a609.png", h),
		                 "/private/files/EMB-2026-0002-apercu-3d09a609.png")
		self.assertEqual(T.url_d_origine("/files/poids_net_25_kgf25124f25124.svg", "0" * 26 + "f25124"), "/files/poids_net_25_kgf25124.svg")

	def test_pas_une_copie(self):
		h = "5d41402abc4b2a76b9719d911009a609"
		self.assertIsNone(T.url_d_origine("/private/files/EMB-2026-0002-apercu-3d09a609.png", h))      # nom normal
		self.assertIsNone(T.url_d_origine("/private/files/X0000000000000.png", h))                       # pas son empreinte
		self.assertIsNone(T.url_d_origine("/private/files/X09a60909a609.png", None))

	def test_l_import_ne_reecrit_plus_les_fichiers(self):
		import inspect

		src = inspect.getsource(T)
		self.assertIn("f.flags.copy_from_existing_file = True", src)
		self.assertEqual(src.count("fiche_fichier_existant("), 6)                     # définition + fixtures + travail + copie d'un design + design à côté + dossier d'exemple
		self.assertNotIn('"doctype": "File", "file_name"', src)


class TestCopieDesignComplete(unittest.TestCase):
	"""16/11/2026 : le design du dev est créé à côté de celui de la prod ; sa copie porte tous les fichiers qu'il cite."""

	def test_tous_les_fichiers_cites_sont_dans_la_copie(self):
		import json
		import os

		chemin = T._fiche_copie("EMB-2026-0006")
		with open(chemin, encoding="utf-8") as f:
			copie = json.load(f)
		ranges = {e["url"] for e in copie["fichiers"]}
		self.assertTrue(set(T.urls_fichiers(copie["champs"])) <= ranges)
		for e in copie["fichiers"]:
			self.assertTrue(os.path.getsize(os.path.join(os.path.dirname(chemin), "fichiers", e["fichier"])) > 0, e["fichier"])
		for cle in ("article", "fonds_faces", "plan_a_plat"):                      # les repères du « déjà créé »
			self.assertTrue(copie["champs"].get(cle), cle)


class TestDossierExemple(unittest.TestCase):
	"""16/11/2026 : le dossier AP-M et sa fiche validée arrivent en prod comme exemple pour l'équipe."""

	def test_lignes_ajoutees_sans_doublon(self):
		existantes = [{"article": "AP-M-A"}, {"article": "AP-M-B"}]
		copie = [{"article": "AP-M-B"}, {"article": "AP-M-C"}, {"article": "AP-M-C"}, {"article": ""}, {"article": "AP-M-D"}]
		self.assertEqual(T.lignes_a_ajouter(existantes, copie, "article"), [{"article": "AP-M-C"}, {"article": "AP-M-D"}])
		self.assertEqual(T.lignes_a_ajouter([], [{"image": "/files/a.jpg", "legende": "x"}], "image"), [{"image": "/files/a.jpg", "legende": "x"}])
		self.assertEqual(T.lignes_a_ajouter(existantes, [], "article"), [])
		ajouts = T.lignes_a_ajouter([], copie[:1], "article")
		self.assertIsNot(ajouts[0], copie[0])                                    # la copie n'est pas modifiée par le dossier

	def test_copie_comparee_sans_la_date_de_l_export(self):
		a = {"article": "AP-M", "depuis": "2026-11-11", "exporte_de": {"modifie": "x"}, "dossier": {"consignes": "c"}, "marque": None, "documents": [], "fichiers": []}
		self.assertEqual(T.copie_comparable(a), T.copie_comparable({**a, "exporte_de": {"modifie": "y"}}))
		self.assertNotEqual(T.copie_comparable(a), T.copie_comparable({**a, "dossier": {"consignes": "d"}}))
		self.assertNotEqual(T.copie_comparable(a), T.copie_comparable({**a, "documents": [{"origine": "DOC-P-2026-00042"}]}))

	def test_la_copie_d_ap_m_rangee_dans_l_app_est_complete(self):
		import json
		import os

		from aquaworld_ia.documents_produit import mise_en_page as M
		from aquaworld_ia.documents_produit import structure as S

		chemin = T._fiche_dossier("AP-M")
		with open(chemin, encoding="utf-8") as f:
			copie = json.load(f)
		racine = os.path.join(os.path.dirname(chemin), "fichiers")
		self.assertEqual(copie["article"], "AP-M")
		self.assertEqual(M.configuration(copie["dossier"]["mises_en_page"]), copie["dossier"]["mises_en_page"])   # enregistrable telle quelle
		self.assertTrue(copie["dossier"]["variantes"] and copie["dossier"]["images"] and copie["dossier"]["entete"])
		self.assertTrue(copie["documents"])
		for doc in copie["documents"]:
			# Le contenu est déjà dans la forme enregistrée : c'est ce qui fait reconnaître la version déjà présente.
			self.assertEqual(S.normaliser(doc["contenu"], doc["contexte"]), doc["contenu"])
			self.assertEqual(doc["contenu"]["points_a_verifier"], [])
			self.assertEqual(doc["langue"], "fr")
			if doc["statut"] == "Validé":
				self.assertIn("pdf", doc)                                          # une version validée arrive avec son PDF
			for champ, _extension in T._PIECES:
				if doc.get(champ):
					self.assertTrue(os.path.getsize(os.path.join(racine, doc[champ])) > 0, doc[champ])
		with open(os.path.join(racine, copie["documents"][0]["pdf"]), "rb") as f:
			self.assertEqual(f.read(5), b"%PDF-")
		for e in copie["fichiers"]:
			self.assertTrue(os.path.getsize(os.path.join(racine, e["fichier"])) > 0, e["fichier"])
		cites = set(T.urls_fichiers(copie["dossier"]))
		self.assertTrue({e["url"] for e in copie["fichiers"]} >= {u for u in cites if u.startswith("/private/")})   # les fichiers privés du dossier voyagent
		if copie["marque"]:
			self.assertIn(copie["marque"]["image"], {e["url"] for e in copie["fichiers"]})
		# La présentation de base tirée de la copie ne porte ni le QR ni les photos d'AP-M.
		for disposition in M.base(copie["dossier"]["mises_en_page"]).values():
			self.assertFalse({"qr_url", "qr_legende", "photo_grande", "largeurs_photos"} & set(disposition))
