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
