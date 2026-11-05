"""Les réglages par outil atteignent les appels IA, sans appel réseau dans les tests."""

import base64
import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from aquaworld_ia.ia import chat, client, images
from aquaworld_ia.manuels import traduction


class TestModelesOutils(unittest.TestCase):
	def setUp(self):
		self.reglages = SimpleNamespace(
			modele_texte="texte-general", modele_image="image-generale",
			modele_fiche_technique="texte-fiche", modele_manuel_produit="texte-manuel-produit",
			modele_lecture_documents="vision-documents", modele_traduction_documents="traduction-documents",
			modele_traduction_manuels="traduction-manuels", modele_studio_manuel="vision-studio-manuel",
			modele_texte_emballage="texte-emballage", modele_image_manuels="image-manuel",
			modele_image_emballage="image-emballage", modele_logo="image-logo", modele_mockup="image-mockup",
		)
		self.ai_settings = SimpleNamespace(open_ai_model="texte-herite", open_ai_temperature="0.2")
		self.api = Mock()
		self.api.chat.completions.create.return_value = SimpleNamespace(
			usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
			choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))],
		)
		image = SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(b"image").decode())])
		self.api.images.edit.return_value = image
		self.api.images.generate.return_value = image
		for p in (
			patch.object(client, "reglages", return_value=self.reglages),
			patch.object(client, "_ai_settings", return_value=self.ai_settings),
			patch.object(client, "cle_api", return_value="cle-factice-test"),
			patch("openai.OpenAI", return_value=self.api),
		):
			p.start()
			self.addCleanup(p.stop)
		p = patch("aquaworld_ia.ia.journal.enregistrer")
		self.journal = p.start()
		self.addCleanup(p.stop)

	def test_appels_texte_independants_et_modele_journalise(self):
		for fonction, attendu in (
			("Document produit — fiche technique", "texte-fiche"),
			("Document produit — manuel", "texte-manuel-produit"),
			("Document produit — traduction", "traduction-documents"),
			("Manuel", "traduction-manuels"),
			("Emballage texte", "texte-emballage"),
			("Tampon IA", "texte-emballage"),
		):
			with self.subTest(fonction=fonction):
				self.assertEqual(chat.chat_json("system", "texte", fonctionnalite=fonction), {"ok": True})
				self.assertEqual(self.api.chat.completions.create.call_args.kwargs["model"], attendu)
				self.assertEqual(self.journal.call_args.kwargs["modele"], attendu)

	def test_lectures_vision_suivent_leur_outil(self):
		for fonction, attendu in (
			("Document produit — lecture", "vision-documents"),
			("Manuel lecture", "vision-studio-manuel"),
			("Manuel mise en page", "vision-studio-manuel"),
		):
			with self.subTest(fonction=fonction):
				chat.chat_json_image("system", "texte", b"image", fonctionnalite=fonction)
				self.assertEqual(self.api.chat.completions.create.call_args.kwargs["model"], attendu)
				self.assertEqual(self.journal.call_args.kwargs["modele"], attendu)

	def test_images_creation_et_retouche_suivent_leur_outil(self):
		from PIL import Image

		png = io.BytesIO()
		Image.new("RGB", (8, 8), "white").save(png, format="PNG")
		for fonction, attendu in (
			("Manuel illustration", "image-manuel"),
			("Emballage image", "image-emballage"),
			("Emballage fond", "image-emballage"),
			("Emballage faces", "image-emballage"),
			("Logo IA", "image-logo"),
			("Mockup 3D", "image-mockup"),
		):
			with self.subTest(fonction=fonction):
				self.assertEqual(images.generer("test", taille="1024x1024", qualite="low", fonctionnalite=fonction), [b"image"])
				self.assertEqual(self.api.images.generate.call_args.kwargs["model"], attendu)
				self.assertEqual(images.editer("test", [("source", png.getvalue())], taille="1024x1024", qualite="low", fonctionnalite=fonction), [b"image"])
				self.assertEqual(self.api.images.edit.call_args.kwargs["model"], attendu)
				self.assertEqual(self.journal.call_args.kwargs["modele"], attendu)

	def test_champ_vide_retablit_defaut_sans_changer_autres_outils(self):
		self.reglages.modele_fiche_technique = "   "
		self.assertEqual(client.modele_texte("Document produit — fiche technique"), "texte-general")
		self.assertEqual(client.modele_texte("Document produit — manuel"), "texte-manuel-produit")
		self.reglages.modele_texte = ""
		self.assertEqual(client.modele_texte("Document produit — fiche technique"), "texte-herite")
		self.reglages.modele_logo = ""
		self.assertEqual(client.modele_image("Logo IA"), "image-generale")
		self.assertEqual(client.modele_image("Mockup 3D"), "image-mockup")
		self.reglages.modele_image = ""
		self.assertEqual(client.modele_image("Logo IA"), client.MODELE_IMAGE_DEFAUT)
		self.assertEqual(client.modele_texte("Nouvel outil"), "texte-herite")

	def test_anciens_reglages_sans_nouveaux_champs_restent_valides(self):
		with patch.object(client, "reglages", return_value=SimpleNamespace(modele_texte="ancien-texte", modele_image="ancienne-image")):
			self.assertEqual(client.modele_texte("Document produit — fiche technique"), "ancien-texte")
			self.assertEqual(client.modele_image("Manuel illustration"), "ancienne-image")

	def test_modele_explicite_et_reprise_sans_temperature(self):
		reponse = self.api.chat.completions.create.return_value
		self.api.chat.completions.create.side_effect = [ValueError("temperature non acceptée"), reponse]
		chat.chat_json("system", "texte", fonctionnalite="Document produit — fiche technique", modele="modele-explicite")
		self.assertEqual([a.kwargs["model"] for a in self.api.chat.completions.create.call_args_list], ["modele-explicite"] * 2)
		self.assertNotIn("temperature", self.api.chat.completions.create.call_args.kwargs)
		self.assertEqual(self.journal.call_args.kwargs["modele"], "modele-explicite")

	def test_gpt6_et_gpt56_acceptent_json_et_vision_sans_temperature(self):
		for modele in ("gpt-6-astra", "gpt-6.1-sol", "gpt-6.1-terra", "gpt-6-luna", "gpt-6-sol", "gpt-5.6-sol"):
			with self.subTest(modele=modele):
				self.reglages.modele_fiche_technique = modele
				self.reglages.modele_lecture_documents = modele
				self.api.chat.completions.create.reset_mock()
				chat.chat_json("JSON", "texte", fonctionnalite="Document produit — fiche technique")
				chat.chat_json_image("JSON", "texte", b"scan", fonctionnalite="Document produit — lecture")
				resultat = chat.chat_json_differe((self.api, modele, 0.2), "JSON", "texte")
				self.assertEqual(resultat["sortie"], {"ok": True})
				self.assertEqual(self.api.chat.completions.create.call_count, 3)
				for appel in self.api.chat.completions.create.call_args_list:
					self.assertEqual(appel.kwargs["model"], modele)
					self.assertEqual(appel.kwargs["response_format"], {"type": "json_object"})
					self.assertNotIn("temperature", appel.kwargs)
				self.assertEqual(self.journal.call_args.kwargs["modele"], modele)

	def test_traduction_sequentielle_et_parallele_utilisent_meme_reglage(self):
		def reponse(**kw):
			items = json.loads(kw["messages"][-1]["content"])["items"]
			contenu = {"items": [{"i": i["i"], "t": "FR " + i["t"]} for i in items]}
			return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(contenu)))])

		self.api.chat.completions.create.side_effect = reponse
		paragraphes = [{"id": i, "texte": f"Paragraph number {i} about water"} for i in range(5)]
		for parallele in (1, 3):
			with self.subTest(parallele=parallele):
				self.api.chat.completions.create.reset_mock()
				trad, laisses = traduction.traduire_tout(paragraphes, {"code": "fr", "libelle": "Français"}, taille_lot=1, parallele=parallele)
				self.assertEqual(laisses, [])
				self.assertEqual(len(trad), 5)
				self.assertEqual([a.kwargs["model"] for a in self.api.chat.completions.create.call_args_list], ["traduction-manuels"] * 5)
