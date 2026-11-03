"""Une proposition IA doit remplacer uniquement le logo ciblé, jamais le logo du design."""
import copy
import json
import unittest
from unittest.mock import Mock, patch

import frappe

from aquaworld_ia.emballage import atelier_images as A, studio as S


SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 10"><rect width="20" height="10" fill="green"/></svg>'


class TestLogoZoneIA(unittest.TestCase):
	def setUp(self):
		self.doc = frappe._dict(name="TEST", modified="2026-11-03 10:00:00", logo="/files/global.svg", mise_en_page="{}",
			check_permission=Mock(), save=Mock(), set=Mock())
		self.logo = dict(zone="logo", x=20, y=25, w=50, h=15, rotation=90, zoom_image=1.5,
			logo="/files/dessus.svg", centre_visuel={"x": .4, "y": .5, "source": "/files/dessus.svg"})
		self.face = dict(code="dessus", x=10, y=20, w=142, h=30,
			zones=[dict(zone="nom", x=80, y=25, w=60, h=15), self.logo, dict(self.logo, x=80, logo="/files/second.svg")])
		self.apercu = {"faces": [self.face]}
		self.cible = dict(face="dessus", indice=1, modifie_le=self.doc.modified)
		for objet, nom, valeur in [(A.frappe, "get_doc", self.doc), (S, "apercu_du_doc", self.apercu), (A, "charger", {})]:
			p = patch.object(objet, nom, return_value=valeur); p.start(); self.addCleanup(p.stop)
		p = patch.object(A, "_", lambda s: s); p.start(); self.addCleanup(p.stop)
		p = patch.object(A.frappe, "throw", side_effect=ValueError); p.start(); self.addCleanup(p.stop)

	def test_la_reference_est_le_logo_de_la_zone_et_aucun_logo_n_est_adopte(self):
		with patch("aquaworld_ia.emballage.variantes.url_logo", return_value=self.doc.logo), \
				patch.object(A, "_image_lisible", side_effect=lambda d, u: u), \
				patch("aquaworld_ia.ia.fichiers.lire", return_value=SVG) as lire, \
				patch("aquaworld_ia.ia.client.qualite_image", return_value="low"), \
				patch("aquaworld_ia.ia.images.editer", return_value=[b"png"]) as ia, \
				patch("frappe.utils.file_manager.save_file", return_value=frappe._dict(file_url="/private/files/proposition.png")):
			m = A.retoucher_image.__wrapped__(self.doc.name, "logo", "Couleur verte", cible_zone=json.dumps(self.cible))
		lire.assert_called_once_with("/files/dessus.svg")
		self.assertEqual(ia.call_args.args[1], [("logo", SVG)])
		self.assertIn("Couleur verte", ia.call_args.args[0])
		self.assertEqual(m["source"], "/files/dessus.svg")
		self.doc.save.assert_not_called()
		self.doc.set.assert_not_called()

	def test_couleur_et_palette_sont_transmises_a_l_ia_sans_changer_la_cible(self):
		self.doc.palette = "#123456; #FFF, #123456"
		with patch("aquaworld_ia.emballage.variantes.url_logo", return_value=self.doc.logo), \
				patch.object(A, "_image_lisible", side_effect=lambda d, u: u), \
				patch("aquaworld_ia.ia.fichiers.lire", return_value=SVG), \
				patch("aquaworld_ia.ia.client.qualite_image", return_value="low"), \
				patch("aquaworld_ia.ia.images.editer", return_value=[b"png"]) as ia, \
				patch("frappe.utils.file_manager.save_file", return_value=frappe._dict(file_url="/private/files/proposition.png")):
			A.retoucher_image.__wrapped__("TEST", "logo", "Recolorer le texte", cible_zone=self.cible,
				couleur_cible="#AbC", element_couleur="le texte ecoPurium", utiliser_palette=1)
		prompt = ia.call_args.args[0]
		for attendu in ("#aabbcc", "#123456, #ffffff", "le texte ecoPurium", "sRGB", "takes precedence"):
			self.assertIn(attendu, prompt)
		self.assertEqual(prompt.count("#123456"), 1)
		self.assertEqual(ia.call_args.args[1], [("logo", SVG)])
		self.doc.save.assert_not_called()

	def test_une_couleur_invalide_ne_declenche_pas_un_appel_ia(self):
		with patch("aquaworld_ia.emballage.variantes.url_logo", return_value=self.doc.logo), \
				patch("aquaworld_ia.ia.fichiers.lire") as lire, patch("aquaworld_ia.ia.images.editer") as ia:
			for couleur, utiliser, palette in [("bleu", 0, ""), ("#12345z", 0, ""), ("", 1, ""), ("", 1, "#fff, invalide")]:
				self.doc.palette = palette
				with self.subTest(couleur=couleur, palette=palette), self.assertRaises(ValueError):
					A.retoucher_image.__wrapped__("TEST", "logo", "Recolorer", couleur_cible=couleur, utiliser_palette=utiliser)
		lire.assert_not_called(); ia.assert_not_called()

	def test_la_palette_est_facultative_et_la_retouche_historique_est_conservee(self):
		ancien = A.prompt_retouche("logo", "Changer la forme")
		self.assertEqual(ancien, A.prompt_retouche("logo", "Changer la forme", couleur_cible=" "))
		self.assertNotIn("sRGB", ancien)
		self.assertIn("#ff0000", A.prompt_retouche("logo", "Changer la forme", palette="#F00"))
		self.assertNotIn("supplied by the user", A.prompt_retouche("logo", "Changer la forme", palette="#F00"))

	def test_adoption_svg_conserve_position_rotation_zoom_et_autres_logos(self):
		avant = copy.deepcopy(self.apercu)
		with patch.object(A, "_image_lisible", side_effect=lambda d, u: u), \
				patch("aquaworld_ia.ia.fichiers.lire", return_value=SVG), \
				patch("frappe.utils.file_manager.save_file") as fichier:
			A.adopter_image.__wrapped__("TEST", "logo", "/files/proposition.svg", cible_zone=self.cible)
		zones = json.loads(self.doc.mise_en_page)["dessus"]
		self.assertEqual(zones[0], self.face["zones"][0])
		self.assertEqual(zones[2], self.face["zones"][2])
		self.assertEqual(zones[1], {**{k: v for k, v in self.logo.items() if k != "centre_visuel"}, "logo": "/files/proposition.svg"})
		self.assertEqual(self.apercu, avant)
		self.assertEqual(self.doc.logo, "/files/global.svg")
		self.doc.set.assert_not_called(); fichier.assert_not_called()
		self.doc.save.assert_called_once(); self.doc.check_permission.assert_called_once_with("write")

	def test_adoption_png_detoure_la_proposition_sans_remplacer_le_logo_general(self):
		with patch.object(A, "_image_lisible", side_effect=lambda d, u: u), \
				patch("aquaworld_ia.ia.fichiers.lire", return_value=b"png original"), \
				patch("aquaworld_ia.emballage.composition.fond_blanc_en_transparence", return_value=b"png transparent") as detourer, \
				patch("frappe.utils.file_manager.save_file", return_value=frappe._dict(file_url="/private/files/detoure.png")) as fichier:
			A.adopter_image.__wrapped__("TEST", "logo", "/files/proposition.png", cible_zone=self.cible)
		detourer.assert_called_once_with(b"png original")
		self.assertEqual(fichier.call_args.args[1], b"png transparent")
		self.assertTrue(fichier.call_args.kwargs["is_private"])
		self.assertEqual(json.loads(self.doc.mise_en_page)["dessus"][1]["logo"], "/private/files/detoure.png")
		self.doc.set.assert_not_called()

	def test_les_faces_miroirs_gardent_le_logo_precedent_et_la_photo_reste_automatique(self):
		self.face["zones"].append(dict(zone="photo", x=20, y=25, w=50, h=15, auto=1))
		miroir = dict(copy.deepcopy(self.face), code="dessous", copie_de="dessus")
		self.apercu["faces"].append(miroir)
		A._poser_logo_zone(self.doc, A._cible_logo_zone(self.doc, "logo", self.cible), "/files/nouveau.svg")
		mep = json.loads(self.doc.mise_en_page)
		self.assertEqual(mep["dessous"][1]["logo"], "/files/dessus.svg")
		self.assertEqual(mep["dessus"][1]["logo"], "/files/nouveau.svg")
		self.assertFalse(any(z["zone"] == "photo" for zones in mep.values() for z in zones))

	def test_une_cible_invalide_ou_perimee_est_refusee_avant_lecture_ou_appel_ia(self):
		cibles = [{}, dict(self.cible, modifie_le="ancien"), dict(self.cible, face="inconnue"),
			dict(self.cible, indice=-1), dict(self.cible, indice=99), dict(self.cible, indice=0),
			dict(self.cible, indice="1"), dict(self.cible, indice=True)]
		with patch("aquaworld_ia.ia.fichiers.lire") as lire, patch("aquaworld_ia.ia.images.editer") as ia:
			for cible in cibles:
				with self.subTest(cible=cible), self.assertRaises(ValueError):
					A.adopter_image.__wrapped__("TEST", "logo", "/files/a.svg", cible_zone=cible)
				with self.subTest(cible=cible), self.assertRaises(ValueError):
					A.retoucher_image.__wrapped__("TEST", "logo", "Vert", cible_zone=cible)
			with self.assertRaises(ValueError):
				A.adopter_image.__wrapped__("TEST", "photo_produit", "/files/a.svg", cible_zone=self.cible)
		lire.assert_not_called(); ia.assert_not_called(); self.doc.save.assert_not_called()

	def test_une_image_privee_non_autorisee_ne_peut_pas_etre_adoptee_sur_une_zone(self):
		with patch.object(A, "_image_lisible", side_effect=PermissionError), patch("aquaworld_ia.ia.fichiers.lire") as lire:
			with self.assertRaises(PermissionError):
				A.adopter_image.__wrapped__("TEST", "logo", "/private/files/autre.svg", cible_zone=self.cible)
		lire.assert_not_called(); self.doc.save.assert_not_called()
