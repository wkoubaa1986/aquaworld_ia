"""Fichier connu de la base mais absent du disque (base restaurée sans ses fichiers privés)."""
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

import frappe

from aquaworld_ia.emballage import composition as C
from aquaworld_ia.ia import fichiers as F


class TestRetablir(unittest.TestCase):
	def test_ecrit_le_fichier_absent_sans_toucher_au_present(self):
		with tempfile.TemporaryDirectory() as d:
			chemin = os.path.join(d, "files", "apercu.png")
			self.assertTrue(F.ecrire_si_absent(chemin, b"contenu"))
			self.assertFalse(F.ecrire_si_absent(chemin, b"autre"))
			with open(chemin, "rb") as f:
				self.assertEqual(f.read(), b"contenu")
			self.assertEqual(os.listdir(os.path.dirname(chemin)), ["apercu.png"])

	def test_retablit_les_fiches_de_meme_contenu(self):
		with tempfile.TemporaryDirectory() as d:
			absent, present = os.path.join(d, "absent.png"), os.path.join(d, "present.png")
			with open(present, "wb") as f:
				f.write(b"deja la")
			chemins = {"A": absent, "B": present}
			fiches = [frappe._dict(name="A", file_url="/private/files/absent.png"),
			          frappe._dict(name="B", file_url="/private/files/present.png"),
			          frappe._dict(name="C", file_url="https://ailleurs.example/x.png")]
			with patch.object(F.frappe, "get_all", return_value=fiches, create=True) as lister, \
				patch.object(F.frappe, "get_doc", side_effect=lambda dt, nom: Mock(get_full_path=lambda: chemins[nom]), create=True):
				self.assertEqual(F.retablir(b"image"), 1)
			self.assertEqual(lister.call_args.kwargs["filters"]["is_private"], 1)
			self.assertEqual(len(lister.call_args.kwargs["filters"]["content_hash"]), 32)
			with open(absent, "rb") as f:
				self.assertEqual(f.read(), b"image")
			with open(present, "rb") as f:
				self.assertEqual(f.read(), b"deja la")

	def test_export_retablit_avant_d_enregistrer(self):
		"""13/11/2026 : « Actualiser le PDF » d'un design inchangé échouait sur une base restaurée sans fichiers."""
		import pymupdf

		with pymupdf.open() as p:
			p.new_page(width=50, height=50)
			pdf = p.tobytes()
		doc = Mock(modified="v1", variantes=[], variante_choisie=0)
		doc.name = "TEST"
		doc.get = lambda cle, defaut=None: {"plan_a_plat": "/ancien.pdf"}.get(cle, defaut)
		ordre = []
		with patch.object(C.frappe, "get_doc", return_value=doc), patch.object(C, "plan_du_design", return_value={"feuille": {}}), \
			patch.object(C.geometrie, "verifier", return_value=[]), patch.object(C, "_langues", return_value={}), \
			patch("aquaworld_ia.emballage.exports.verifier", return_value=[]), \
			patch("aquaworld_ia.emballage.exports.empreinte", return_value="e"), \
			patch("aquaworld_ia.emballage.contenus.imprimes", return_value={}), \
			patch.object(C, "composer", return_value=pdf), patch.object(C.frappe, "db", Mock()) as db, \
			patch.object(C.fichiers, "retablir", side_effect=lambda contenu: ordre.append(("retablir", contenu[:4]))), \
			patch.object(C, "save_file", side_effect=lambda nom, contenu, *a, **k: ordre.append(("save_file", contenu[:4])) or Mock(file_url="/" + nom)):
			db.get_value.return_value = frappe._dict(modified="v1", plan_a_plat="/ancien.pdf")
			resultat = C.composer_et_attacher.__wrapped__("TEST")
		self.assertEqual(ordre, [("retablir", b"%PDF"), ("save_file", b"%PDF"), ("retablir", b"\x89PNG"), ("save_file", b"\x89PNG")])
		self.assertEqual(resultat["apercu_plan"], "/TEST-apercu.png")


if __name__ == "__main__":
	unittest.main()
