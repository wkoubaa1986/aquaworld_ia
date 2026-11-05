"""Sélection des pièces jointes, association aux variantes et application aux PDF."""

import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import frappe
import pymupdf
from PIL import Image

from aquaworld_ia.documents_produit import contexte as C
from aquaworld_ia.documents_produit import latex as L
from aquaworld_ia.documents_produit import mise_en_page as M
from aquaworld_ia.documents_produit import service as API
from aquaworld_ia.documents_produit import structure as S
from aquaworld_ia.tests import test_documents_produit as fixtures


class TestPhotosProduit(unittest.TestCase):
	setUp = fixtures.TestDocumentsBase.setUp

	def tearDown(self):
		frappe.set_user("Administrator")
		paths = [frappe.get_doc("File", f.name).get_full_path() for f in frappe.get_all("File", fields=["name", "file_url"])
			if f.file_url not in self.fichiers_avant]
		frappe.db.rollback(save_point="documents_produit_test")
		frappe.clear_cache()
		for path in paths:
			Path(path).unlink(missing_ok=True)

	def image(self, couleur, article=None, nom="photo.png"):
		from frappe.utils.file_manager import save_file

		b = io.BytesIO()
		Image.new("RGB", (250, 180), couleur).save(b, format="PNG")
		return save_file(nom, b.getvalue(), "Item" if article else C.DOSSIER, article or self.name, is_private=1)

	def test_bibliotheque_multiphotos_origines_doublons_et_acces(self):
		v = self.variantes[0]["name"]
		principale = self.image("#123456", v, "face.png")
		detail = self.image("#654321", v, "detail.png")
		commune = self.image("#224466", self.d.article, "produit.png")
		frappe.db.set_value("Item", v, "image", principale.file_url)
		frappe.db.set_value("Item", self.d.article, "image", commune.file_url)
		dossier = self.image("#336699", nom="schema.png")
		autre = frappe.get_all("Item", filters={"variant_of": ["!=", self.d.article], "name": ["!=", self.d.article]}, pluck="name", limit=1)[0]
		hors = self.image("#445566", autre, "interdit.png")
		avant = (frappe.db.count("File"), frappe.db.count(C.DOCUMENT))
		rows = API.photos_disponibles(self.name, [v])
		bykey = {(r["image"], r["article"]): r for r in rows}
		self.assertEqual(len(rows), len(bykey))
		self.assertTrue(bykey[(principale.file_url, v)]["principale_article"])
		self.assertFalse(bykey[(detail.file_url, v)]["principale_article"])
		self.assertIn((commune.file_url, ""), bykey)
		self.assertIn((dossier.file_url, ""), bykey)
		self.assertNotIn(hors.file_url, [r["image"] for r in rows])
		self.assertEqual((frappe.db.count("File"), frappe.db.count(C.DOCUMENT)), avant)
		self.assertNotIn(principale.file_url, [r["image"] for r in API.photos_disponibles(self.name, [])])
		with self.assertRaises(ValueError):
			API.photos_disponibles(self.name, [autre])
		lire = C.fichier_lisible
		def restreindre(url, **kwargs):
			if url == detail.file_url:
				raise frappe.PermissionError()
			return lire(url, **kwargs)
		with patch.object(C, "fichier_lisible", side_effect=restreindre), patch.object(frappe.local, "message_log", []):
			self.assertNotIn(detail.file_url, [r["image"] for r in API.photos_disponibles(self.name, [v])])
			self.assertFalse(frappe.local.message_log)
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			API.photos_disponibles(self.name, [v])

	def test_changement_photos_sans_ia_preserve_textes_legendes_et_versions(self):
		v1, v2 = [v["name"] for v in self.variantes]
		a, b, c = [self.image(color).file_url for color in ("red", "green", "blue")]
		images = [{"image": a, "article": "", "legende": "Vue produit"}, {"image": b, "article": v1, "legende": "Vue de face"}]
		API.enregistrer(self.name, {"images": images})
		ctx = C.contexte(API.dossier(self.name))
		contenu = S.normaliser({"titre": "Fiche conservée", "resume": "Texte relu", "legendes": ["Légende corrigée", "Translated caption"]}, ctx)
		version = API.nouvelle_version(self.name, S.TYPES[0], contenu, ctx, langue="en", libelle="Anglais")
		selection = [images[1], {"image": c, "article": v2, "legende": "Nouvelle vue"}, images[0]]
		API.enregistrer(self.name, {"images": selection, "mises_en_page": {"fiche": {"photos_variantes": 1, "colonnes_photos": 2}}})
		with patch("aquaworld_ia.ia.chat.chat_json") as chat:
			nouveau = API.appliquer_entete(version, API.dossier(self.name))
			chat.assert_not_called()
		self.assertNotEqual(nouveau.name, version.name)
		out = json.loads(nouveau.contenu_json)
		self.assertEqual(out["resume"], "Texte relu")
		self.assertEqual(out["legendes"], ["Translated caption", "Nouvelle vue", "Légende corrigée"])
		self.assertEqual(json.loads(nouveau.contexte_json)["images"][0]["image"], b)
		self.assertEqual(json.loads(API.document(version.name).contexte_json), ctx)
		self.assertEqual(API.appliquer_entete(nouveau, API.dossier(self.name)).name, nouveau.name)
		selection[0]["legende"] = "Nouvelle légende saisie"
		API.enregistrer(self.name, {"images": selection[:1]})
		dernier = API.appliquer_entete(nouveau, API.dossier(self.name))
		self.assertEqual(json.loads(dernier.contenu_json)["legendes"], ["Nouvelle légende saisie"])
		with self.assertRaises(frappe.ValidationError):
			API.enregistrer(self.name, {"variantes": [{"article": v2}]})

	def test_variante_absente_de_la_version_et_limites(self):
		v1, v2 = [v["name"] for v in self.variantes]
		API.enregistrer(self.name, {"variantes": [{"article": v1}]})
		ctx = C.contexte(API.dossier(self.name))
		version = API.nouvelle_version(self.name, S.TYPES[0], S.normaliser({"titre": "Une variante"}, ctx), ctx)
		photo = self.image("orange").file_url
		API.enregistrer(self.name, {"variantes": [{"article": v1}, {"article": v2}], "images": [{"image": photo, "article": v2}]})
		with self.assertRaisesRegex(ValueError, "absente de cette version"):
			API.appliquer_entete(version, API.dossier(self.name))
		with self.assertRaises(frappe.ValidationError):
			API.enregistrer(self.name, {"images": [{"image": photo}] * 21})
		self.assertEqual(M.normaliser(M.PHOTOS_DEFAUTS), M.normaliser())
		for opts in ({"photos_variantes": True}, {"colonnes_photos": 4}, {"colonnes_photos": "2"}):
			with self.assertRaises(ValueError):
				M.normaliser(opts)

	def test_pdf_vues_par_variante_galerie_multipage_et_rtl(self):
		v1, v2 = [v["name"] for v in self.variantes]
		images = [{"image": self.image(color).file_url, "article": article, "legende": legende}
			for color, article, legende in [("red", "", "Vue principale"), ("blue", v1, "Vue face A"),
				("green", v1, "Vue arrière A"), ("orange", v2, "Vue face B"), ("purple", v2, "Vue côté B"),
				("pink", "", "Vue commune")]]
		API.enregistrer(self.name, {"images": images, "mises_en_page": {"fiche": {"photos_variantes": 1, "colonnes_photos": 2}}})
		ctx = M.appliquer(C.contexte(API.dossier(self.name)), API.dossier(self.name), S.TYPES[0])
		c = S.normaliser({"titre": "Fiche avec variantes", "resume": "Présentation du produit"}, ctx)
		tex, pdf, _ = L.composer(c, ctx)
		Path("/tmp/photos-variantes-fiche.pdf").write_bytes(pdf)
		self.assertLess(tex.index("Vue face A"), tex.index(v2 + " —"))
		self.assertLess(tex.index("Vue côté B"), tex.index("Vue commune"))
		with pymupdf.open(stream=pdf, filetype="pdf") as doc:
			self.assertGreater(len(doc), 1)
			photos = [im for page in doc for im in page.get_image_info()]
			self.assertEqual(len(photos), len(images))
			texte = "\n".join(p.get_text() for p in doc)
			for im in images:
				self.assertEqual(texte.count(im["legende"]), 1)
			for reference, legende in ((v1, "Vue face A"), (v2, "Vue face B")):
				page_photo = next(page for page in doc if legende in page.get_text())
				self.assertIn(reference, page_photo.get_text())
			for page in doc:
				for im in page.get_image_info():
					r = pymupdf.Rect(im["bbox"])
					self.assertTrue(page.rect.contains(r))
			for i, page in enumerate(doc):
				page.get_pixmap(matrix=pymupdf.Matrix(1, 1)).save(f"/tmp/photos-variantes-fiche-{i+1}.png")
		c["titre"] = "دليل الاستخدام"
		self.assertTrue(L.composer(c, ctx, langue="ar", rtl=True)[1].startswith(b"%PDF"))
		# Une variante sans photo conserve ses données dans le tableau compact.
		ctx["images"] = ctx["images"][:3]
		c = S.normaliser({"titre": "Fiche avec une variante illustrée"}, ctx)
		tex, pdf, _ = L.composer(c, ctx)
		self.assertNotIn(r"\subsection*{" + v2, tex)
		with pymupdf.open(stream=pdf, filetype="pdf") as doc:
			texte = "\n".join(p.get_text() for p in doc)
			self.assertIn(v1, texte)
			self.assertIn(v2, texte)
