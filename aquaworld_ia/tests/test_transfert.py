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
		self.assertEqual(src.count("fiche_fichier_existant("), 3)                     # définition + fixtures + travail
		self.assertNotIn('"doctype": "File", "file_name"', src)
