"""Zone « QR code » (demande utilisateur 06/10/2026 : « si je veux l'ajouter en face ? ») : une zone
code-barres qui ne porte que le QR, posable sur n'importe quelle face, le QR centré et carré."""
from __future__ import annotations

import inspect
import json
import os
import unittest

import aquaworld_ia
from aquaworld_ia.emballage import composition as C
from aquaworld_ia.emballage import geometrie as G


class TestZoneQr(unittest.TestCase):
	FACE = {"x": 0, "y": 0, "w": 100, "h": 100, "imprimable": True}

	def test_le_contenu_de_la_zone_survit_au_bornage(self):
		b = C.borner_zone({"zone": "code_barres", "code": "qr", "x": 70, "y": 70, "w": 22, "h": 22}, self.FACE)
		self.assertEqual(b["code"], "qr")
		self.assertNotIn("code", C.borner_zone({"zone": "code_barres", "x": 1, "y": 1, "w": 30, "h": 20}, self.FACE))

	def test_libelle(self):
		self.assertEqual(G.libelle_zone({"zone": "code_barres", "code": "qr"}), "QR code")
		self.assertEqual(G.libelle_zone({"zone": "code_barres", "code": "ean"}), "EAN-13")
		self.assertEqual(G.libelle_zone({"zone": "code_barres"}), "Code-barres")

	def test_carre_centre(self):
		self.assertEqual(C.carre_centre((0, 0, 40, 20)), (10, 0, 30, 20))
		self.assertEqual(C.carre_centre((5, 5, 25, 45)), (5, 15, 25, 35))

	def test_une_zone_qr_sur_l_avant(self):
		plan = G.plan_a_plat(G.ETUI, 80, 160, 60)
		mep = {"avant": [{"zone": "nom", "x": 10, "y": 10, "w": 30, "h": 10},
		                 {"zone": "code_barres", "code": "qr", "x": 0, "y": 0, "w": 22, "h": 22}]}
		zones = C.zones_par_face(plan, {"nom": True, "code_barres": G.EAN_NOMINAL_MM}, mise_en_page=mep)
		qr = [z for z in zones["avant"] if z["zone"] == "code_barres"]
		self.assertEqual(len(qr), 1)
		self.assertEqual((qr[0]["code"], qr[0]["w"], qr[0]["h"]), ("qr", 22, 22))
		self.assertTrue(any(z["zone"] == "code_barres" and not z.get("code") for z in zones["arriere"]))  # dos : zone automatique


class TestCablage(unittest.TestCase):

	def test_studio_composition_et_doctype(self):
		racine = os.path.dirname(inspect.getfile(aquaworld_ia))
		with open(os.path.join(racine, "aquaworld_ia", "page", "studio_emballage", "studio_emballage.js"), encoding="utf-8") as fh:
			js = fh.read()
		self.assertEqual(js.count('"code_barres", "qr", "photo"'), 2)          # barre du plan + panneau de droite
		for morceau in ('data-champ="couleur_qr"', "data-qr-couleur", 'code: "qr"', "z.code ? { code: z.code }",
		                'data-role="appliquer-code"', "_contraste_blanc"):
			self.assertIn(morceau, js, morceau)
		with open(inspect.getfile(C), encoding="utf-8") as fh:
			src = fh.read()
		self.assertIn('codes.qr_svg(doc.url_qr, doc.get("couleur_qr"))', src)
		self.assertIn("qr_ici = None if (qr_place or porte == \"ean\") else qr", src)
		with open(os.path.join(racine, "aquaworld_ia", "doctype", "design_emballage", "design_emballage.json"), encoding="utf-8") as fh:
			meta = json.load(fh)
		self.assertIn("couleur_qr", meta["field_order"])
		self.assertEqual(next(f for f in meta["fields"] if f["fieldname"] == "couleur_qr")["fieldtype"], "Color")


if __name__ == "__main__":
	unittest.main()
