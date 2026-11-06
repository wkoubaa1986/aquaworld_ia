"""Rendu, persistance et droits des modèles d'en-tête créés visuellement."""

import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import frappe
import pymupdf
from PIL import Image

from aquaworld_ia.documents_produit import contexte as C
from aquaworld_ia.documents_produit import editeur_entete as V
from aquaworld_ia.documents_produit import entetes as E
from aquaworld_ia.documents_produit import latex as L
from aquaworld_ia.documents_produit import service as API
from aquaworld_ia.documents_produit import structure as S


class TestConfigurationEntete(unittest.TestCase):
	def test_validation_et_texte_echappe(self):
		base = {**V.DEFAUTS, "nom_societe": '<script>alert("x")</script> & Société'}
		haut, bas = V.html(base)
		self.assertIn("&lt;script&gt;", haut)
		self.assertNotIn("<script>", haut)
		self.assertNotIn("Service commercial", haut)
		self.assertEqual(bas, "")
		for choix in ({"largeur_logo": True}, {"largeur_logo": 80}, {"taille_texte": "9"},
			{"couleur": "red;display:none"}, {"logo": "https://example.com/logo.png"},
			{"html": "<script>"}, {"contact_1": "x" * 351}, {"trait": "1"}, {"disposition": "libre"}):
			with self.subTest(choix=choix), self.assertRaises(ValueError):
				V.normaliser({**base, **choix})
		with self.assertRaises(ValueError):
			V.normaliser({})

	def test_quatre_blocs_activite_alignement_et_trait_vertical(self):
		base = {**V.DEFAUTS, "nom_societe": "AquaWorld",
			"contact_1": "sales@example.invalid", "activite_contact_1": "Ventes, B2B",
			"contact_2": "support@example.invalid", "alignement_contact_2": "droite",
			"contact_3": "Bloc trois", "alignement_contact_3": "centre", "separateur_blocs": 1}
		haut, _ = V.html(base)
		self.assertIn("<em>Ventes, B2B</em>", haut)
		self.assertEqual(haut.count("<td "), 4)                      # marque + trois blocs ; bloc 4 vide omis
		self.assertEqual(haut.count("border-left:1px solid #08477C"), 3)  # jamais à gauche du premier élément
		self.assertIn("text-align:right;", haut)
		self.assertIn("text-align:center;", haut)
		# Logo à droite : le trait précède la marque, pas le premier bloc.
		droite, _ = V.html({**base, "disposition": "droite"})
		self.assertEqual(droite.count("border-left:1px solid #08477C"), 3)
		self.assertNotIn('<td style="width:25.00%;vertical-align:middle;padding:2px 5px;color:#08477C;font-size:9pt;line-height:1.2;text-align:left;border-left', droite)
		# Sans trait vertical, rien ne change par rapport aux colonnes classiques.
		self.assertNotIn("border-left", V.html({**base, "separateur_blocs": 0})[0])
		for choix in ({"alignement_contact_1": "justify"}, {"separateur_blocs": "1"},
			{"activite_contact_2": "x" * 121}, {"contact_4": "x" * 351}):
			with self.subTest(choix=choix), self.assertRaises(ValueError):
				V.normaliser({**base, **choix})

	def test_ancien_modele_sans_les_nouveaux_champs_se_rend_a_l_identique(self):
		anciens = ("disposition", "logo", "largeur_logo", "couleur", "taille_texte", "nom_societe", "sous_titre",
			"titre_contact_1", "contact_1", "titre_contact_2", "contact_2", "pied_page", "trait")
		ancien = {k: V.DEFAUTS[k] for k in anciens}
		ancien.update(nom_societe="X", contact_1="a", contact_2="b")
		haut, _ = V.html(ancien)
		self.assertEqual(haut.count("<td "), 3)
		self.assertNotIn("border-left", haut)
		self.assertNotIn("<em>", haut)


class TestEditeurEntete(unittest.TestCase):
	def setUp(self):
		if not getattr(frappe.local, "db", None):
			self.skipTest("Site Frappe connecté requis")
		frappe.set_user("Administrator")
		frappe.db.savepoint("editeur_entete_test")
		self.fichiers_avant = set(frappe.get_all("File", pluck="file_url"))
		parent = frappe.get_all("Item", filters={"has_variants": 1, "disabled": 0}, pluck="name", limit=1)[0]
		self.name = API.creer(parent)["name"]
		API.enregistrer(self.name, {"sources": [], "images": [], "entete": "", "mises_en_page": {}, "marque_document": ""})
		self.cfg = {**V.DEFAUTS, "nom_societe": "Société de test", "sous_titre": "Traitement de l’eau",
			"contact_1": "Ventes et partenariats\ncommercial@example.invalid\n+216 00 000 001",
			"contact_2": "Assistance technique\nsupport@example.invalid\n+216 00 000 002",
			"pied_page": "Adresse de test\nwww.example.invalid"}
		self.titre = "Test visuel " + frappe.generate_hash(length=10)

	def tearDown(self):
		frappe.set_user("Administrator")
		paths = [frappe.get_doc("File", f.name).get_full_path() for f in frappe.get_all("File", fields=["name", "file_url"])
			if f.file_url not in self.fichiers_avant]
		frappe.db.rollback(save_point="editeur_entete_test")
		frappe.clear_cache()
		for path in paths:
			Path(path).unlink(missing_ok=True)

	def sauver(self, configuration=None, modele=None, modified=None, titre=None):
		return API.enregistrer_editeur_entete(self.name, titre or self.titre, configuration or self.cfg,
			modele, modified, API.dossier(self.name).modified)

	def test_rendu_dispositions_creation_reouverture_et_pdf(self):
		from frappe.utils.file_manager import save_file

		im = io.BytesIO()
		Image.new("RGB", (300, 100), "#087E8B").save(im, format="PNG")
		logo = save_file("test-logo-entete-visuel.png", im.getvalue(), C.DOSSIER, self.name, is_private=1)
		self.cfg["logo"] = logo.file_url
		avant = (frappe.db.count("Letter Head"), frappe.db.count(C.DOCUMENT), frappe.db.count("File"))
		with patch("aquaworld_ia.ia.chat.chat_json") as chat:
			for disposition in ("gauche", "droite", "centre"):
				preview = API.apercu_editeur_entete(self.name, {**self.cfg, "disposition": disposition})
				self.assertNotIn("erreur", preview, preview)
				self.assertTrue(preview["haut"]["image"].startswith("data:image/png;base64,"))
				self.assertLessEqual(preview["haut"]["hauteur"], 35)
				self.assertLessEqual(preview["bas"]["hauteur"], 18)
			self.assertEqual((frappe.db.count("Letter Head"), frappe.db.count(C.DOCUMENT), frappe.db.count("File")), avant)
			default_avant = frappe.db.get_value("Letter Head", {"is_default": 1}, "name")
			r = self.sauver()
			self.assertEqual(API.dossier(self.name).entete, r["name"])
			h = frappe.get_doc("Letter Head", r["name"])
			self.assertEqual(h.source, "HTML")
			self.assertEqual(h.footer_source, "HTML")
			self.assertEqual(frappe.db.get_value("Letter Head", {"is_default": 1}, "name"), default_avant)
			charge = API.charger_editeur_entete(self.name, r["name"])
			self.assertTrue(charge["compatible"])
			self.assertEqual(charge["configuration"], self.cfg)
			self.assertTrue(next(x.visuel for x in r["entetes"] if x.name == r["name"]))
			ctx = C.contexte(API.dossier(self.name))
			contenu = S.normaliser({"titre": "Fiche technique", "resume": "Présentation du produit. " * 300}, ctx)
			version = API.nouvelle_version(self.name, S.TYPES[0], contenu, ctx)
			pdf = L.composer(contenu, ctx)[1]
			with pymupdf.open(stream=pdf, filetype="pdf") as doc:
				self.assertGreater(len(doc), 1)
				for page in doc:
					self.assertGreaterEqual(len(page.get_images()), 2)
			cfg2 = {**self.cfg, "contact_1": "Nouveau contact", "disposition": "droite"}
			self.sauver(cfg2, r["name"], charge["modified"])
			self.assertEqual(API.charger_editeur_entete(self.name, r["name"])["configuration"], cfg2)
			self.assertEqual(json.loads(API.document(version.name).contexte_json)["entete"], ctx["entete"])
			chat.assert_not_called()

	def test_logo_haute_resolution_et_portrait_dans_toutes_les_dispositions(self):
		from frappe.utils.file_manager import save_file

		for dimensions in ((1600, 800), (800, 1600)):
			im = io.BytesIO()
			Image.new("RGB", dimensions, "#087E8B").save(im, format="PNG")
			logo = save_file("test-logo-dimensions.png", im.getvalue(), C.DOSSIER, self.name, is_private=1)
			for disposition in ("gauche", "droite", "centre"):
				with self.subTest(dimensions=dimensions, disposition=disposition):
					preview = API.apercu_editeur_entete(self.name, {**self.cfg, "logo": logo.file_url, "disposition": disposition})
					self.assertNotIn("erreur", preview, preview)
					self.assertLessEqual(preview["haut"]["hauteur"], 35)

	def test_conflits_et_modeles_existants_preserves(self):
		r = self.sauver()
		with self.assertRaises(ValueError):
			self.sauver()
		charge = API.charger_editeur_entete(self.name, r["name"])
		self.sauver({**self.cfg, "couleur": "#112233"}, r["name"], charge["modified"])
		with self.assertRaises(frappe.TimestampMismatchError):
			self.sauver(self.cfg, r["name"], charge["modified"])
		h = frappe.get_doc("Letter Head", r["name"])
		h.content = "<p>Modification manuelle à conserver</p>"
		h.save()
		self.assertFalse(API.charger_editeur_entete(self.name, r["name"])["compatible"])
		with self.assertRaises(ValueError):
			self.sauver(self.cfg, r["name"], h.modified)
		self.assertEqual(frappe.db.get_value("Letter Head", r["name"], "content"), h.content)
		copie = self.sauver(titre=self.titre + " copie")
		self.assertNotEqual(copie["name"], r["name"])
		with self.assertRaises(frappe.TimestampMismatchError):
			API.enregistrer_editeur_entete(self.name, "Autre modèle", self.cfg, dossier_modified="2000-01-01")
		self.assertFalse(frappe.db.exists("Letter Head", "Autre modèle"))

	def test_apercu_invalide_et_permissions(self):
		avant = frappe.db.count("Letter Head")
		self.assertIn("erreur", API.apercu_editeur_entete(self.name, {}))
		with self.assertRaises(frappe.PermissionError):
			self.sauver({**self.cfg, "logo": "/files/logo-absent-test-visuel.png"})
		self.assertEqual(frappe.db.count("Letter Head"), avant)
		frappe.set_user("Guest")
		for fn, args in ((API.charger_editeur_entete, (self.name,)),
			(API.apercu_editeur_entete, (self.name, self.cfg)),
			(API.enregistrer_editeur_entete, (self.name, self.titre, self.cfg))):
			with self.assertRaises(frappe.PermissionError):
				fn(*args)
