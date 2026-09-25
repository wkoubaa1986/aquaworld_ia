"""Studio manuel — l'édition d'une langue (corrections, déplacements, cases, illustrations) et le
plan d'une page : tout est pur, sans PDF ni site."""
from __future__ import annotations

import unittest

from aquaworld_ia.manuels import edition as E
from aquaworld_ia.manuels import extraction as X
from aquaworld_ia.manuels import rendu as R
from aquaworld_ia.manuels import studio as S

FORMATS = [[612, 792], [612, 792]]
PARAS = [
	{"id": 0, "page": 0, "bbox": (50, 50, 300, 80), "texte": "Filter cartridge life", "style": {"taille": 12, "gras": True, "italique": False, "couleur": "#000000", "align": "left"}, "dir": (1, 0)},
	{"id": 1, "page": 0, "bbox": (50, 100, 300, 160), "texte": "Replace every 12 months.", "style": {"taille": 10, "gras": False, "italique": False, "couleur": "#000000", "align": "left"}, "dir": (1, 0)},
	{"id": 2, "page": 0, "bbox": (500, 50, 520, 400), "texte": "Installation Manual", "style": {"taille": 20, "gras": False, "italique": False, "couleur": "#000000", "align": "left"}, "dir": (0, -1)},
	{"id": 3, "page": 1, "bbox": (50, 50, 300, 80), "texte": "Parts list", "style": {"taille": 12, "gras": True, "italique": False, "couleur": "#000000", "align": "left"}, "dir": (1, 0)},
]
TRAD = {0: "Durée de vie de la cartouche", 1: "Remplacer tous les 12 mois.", 2: "Manuel d'installation", 3: "Liste des pièces"}
IMAGES = [{"id": "p0-i0", "page": 0, "bbox": (320, 50, 560, 300)}, {"id": "p1-i0", "page": 1, "bbox": (50, 100, 300, 300)}]


class TestEdition(unittest.TestCase):
	def test_lire_tolere_vide_et_illisible(self):
		for v in (None, "", "pas du json", "[]", "{}"):
			e = E.lire(v)
			self.assertEqual(e, {"textes": {}, "blocs": {}, "libres": [], "images": {}}, v)

	def test_normaliser_garde_les_saisies_et_borne(self):
		e = E.normaliser({
			"textes": {0: "Durée", "1": "   ", "9": "Sans bloc"},
			"blocs": {"0": {"bbox": [-10, 40, 700, 90], "taille": 200, "traitement": "traduit", "inconnu": 1},
			          "1": {"traitement": "efface"}, "3": {"traitement": "n_importe_quoi"}},
			"libres": [{"id": "L1", "type": "texte", "page": 0, "bbox": [10, 10, 100, 40], "texte": "Bonjour", "taille": 1},
			           {"type": "image", "page": 5, "bbox": [0, 0, 10, 10]},
			           {"type": "texte", "page": 1, "bbox": [0, 0, 100, 20]},
			           {"id": "L1", "type": "image", "page": 1, "bbox": [0, 0, 100, 100], "fichier": "/private/files/x.png"}],
			"images": {"p0-i0": {"fichier": "/private/files/y.png", "autre": 1}, "p1-i0": {}},
			"inconnu": {},
		}, FORMATS, {"0": 0, "1": 0, "2": 0, "3": 1})
		self.assertEqual(e["textes"], {"0": "Durée", "9": "Sans bloc"})
		self.assertEqual(e["blocs"]["0"], {"bbox": [0, 40, 612, 90], "taille": 72.0})
		self.assertEqual(e["blocs"]["1"], {"traitement": "efface"})
		self.assertNotIn("3", e["blocs"])
		self.assertEqual([l["id"] for l in e["libres"]], ["L1", "L2", "L3"])
		self.assertEqual(e["libres"][0]["taille"], E.TAILLE_MIN)
		self.assertTrue(e["libres"][0]["fond"])
		self.assertEqual(e["libres"][1]["texte"], "")
		self.assertEqual(e["libres"][2], {"id": "L3", "type": "image", "page": 1, "bbox": [0, 0, 100, 100], "fichier": "/private/files/x.png"})
		self.assertEqual(e["images"], {"p0-i0": {"fichier": "/private/files/y.png"}})
		self.assertNotIn("inconnu", e)

	def test_borner_bbox(self):
		self.assertEqual(E.borner_bbox([300, 80, 50, 50], [612, 792]), [50, 50, 300, 80])
		self.assertEqual(E.borner_bbox([600, 780, 700, 900], [612, 792]), [600, 780, 612, 792])
		self.assertIsNone(E.borner_bbox([1, 2, 3], [612, 792]))
		self.assertIsNone(E.borner_bbox(["a", 0, 1, 1], [612, 792]))

	def test_texte_effectif_et_statut(self):
		trad = E.traductions_str(TRAD)
		ed = E.lire({"textes": {"1": "Corrigé"}, "blocs": {"3": {"traitement": "anglais"}}})
		self.assertEqual(E.texte_effectif(0, trad, ed), TRAD[0])
		self.assertEqual(E.texte_effectif(1, trad, ed), "Corrigé")
		self.assertIsNone(E.texte_effectif(7, trad, ed))
		self.assertEqual(E.statut_bloc(0, trad, ed), "traduit")
		self.assertEqual(E.statut_bloc(1, trad, ed), "corrige")
		self.assertEqual(E.statut_bloc(3, trad, ed), "anglais")
		self.assertEqual(E.statut_bloc(7, trad, ed), "non_traduit")
		self.assertEqual(E.statut_bloc(0, trad, ed, pivote=True), "pivote")

	def test_traductions_str_depuis_json_ou_dict(self):
		self.assertEqual(E.traductions_str('{"1": "a", "2": 3}'), {"1": "a"})
		self.assertEqual(E.traductions_str({1: "a"}), {"1": "a"})
		self.assertEqual(E.traductions_str(None), {})


class TestPlanPage(unittest.TestCase):
	def test_sans_edition_tout_traduit_sauf_pivote(self):
		plan = R.plan_page(0, PARAS, TRAD)
		self.assertEqual([t["id"] for t in plan["textes"]], [0, 1])
		self.assertEqual(plan["pivotes"], 1)
		self.assertEqual(len(plan["redactions"]), 2)
		self.assertTrue(all(t["auto"] for t in plan["textes"]))
		self.assertEqual(plan["textes"][0]["texte"], TRAD[0])

	def test_page_suivante_seulement_ses_blocs(self):
		plan = R.plan_page(1, PARAS, TRAD)
		self.assertEqual([t["id"] for t in plan["textes"]], [3])

	def test_correction_boite_et_taille(self):
		ed = {"textes": {"0": "Corrigé"}, "blocs": {"0": {"bbox": [60, 60, 400, 120], "taille": 9}}}
		t = R.plan_page(0, PARAS, TRAD, ed)["textes"][0]
		self.assertEqual(t["texte"], "Corrigé")
		self.assertEqual(t["bbox"], [60, 60, 400, 120])
		self.assertEqual(t["origine"], [50, 50, 300, 80])
		self.assertEqual(t["style"]["taille"], 9)
		self.assertTrue(t["style"]["gras"])          # le reste du style d'origine est gardé
		self.assertFalse(t["auto"])                   # une boîte dessinée ne s'allonge pas toute seule

	def test_traitements(self):
		ed = {"blocs": {"0": {"traitement": "anglais"}, "1": {"traitement": "efface"}}}
		plan = R.plan_page(0, PARAS, TRAD, ed)
		self.assertEqual(plan["textes"], [])
		self.assertEqual(plan["redactions"], [[50, 100, 300, 160]])   # effacé, pas reposé ; anglais intouché

	def test_sans_traduction_le_bloc_reste_en_anglais(self):
		plan = R.plan_page(0, PARAS, {1: TRAD[1]})
		self.assertEqual([t["id"] for t in plan["textes"]], [1])
		self.assertEqual(plan["redactions"], [[50, 100, 300, 160]])

	def test_cases_libres_et_illustrations(self):
		ed = {"libres": [{"id": "L1", "type": "texte", "page": 0, "bbox": [10, 700, 300, 740], "texte": "Note", "taille": 11, "gras": True, "fond": False, "align": "center"},
		                 {"id": "L2", "type": "texte", "page": 0, "bbox": [10, 750, 300, 780], "texte": "  "},
		                 {"id": "L3", "type": "image", "page": 0, "bbox": [10, 400, 200, 600], "fichier": "/private/files/z.png"},
		                 {"id": "L4", "type": "image", "page": 0, "bbox": [10, 400, 200, 600]},
		                 {"id": "L5", "type": "texte", "page": 1, "bbox": [10, 700, 300, 740], "texte": "Autre page"}],
		      "images": {"p0-i0": {"fichier": "/private/files/y.png"}, "p1-i0": {"fichier": "/private/files/w.png"}}}
		plan = R.plan_page(0, PARAS, TRAD, ed, IMAGES)
		self.assertEqual([l["id"] for l in plan["libres"]], ["L1"])
		self.assertEqual(plan["libres"][0]["style"], {"taille": 11, "gras": True, "italique": False, "couleur": "#000000", "align": "center"})
		self.assertFalse(plan["libres"][0]["fond"])
		self.assertEqual([i["id"] for i in plan["images"]], ["L3", "p0-i0"])
		self.assertEqual(plan["images"][1]["bbox"], [320, 50, 560, 300])   # la boîte de l'image détectée


class TestPlanOCR(unittest.TestCase):
	def test_un_paragraphe_ocr_s_efface_a_part(self):
		paras = [dict(PARAS[0], ocr=True), PARAS[1]]
		plan = R.plan_page(0, paras, TRAD)
		self.assertEqual(plan["redactions_ocr"], [[50, 50, 300, 80]])
		self.assertEqual(plan["redactions"], [[50, 100, 300, 160]])
		self.assertEqual([t["id"] for t in plan["textes"]], [0, 1])


class TestGroupeEntrees(unittest.TestCase):
	def _t(self, i, y0, y1, texte, x0=87, auto=True, lignes=1):
		return {"id": i, "bbox": [x0, y0, 560, y1], "origine": [x0, y0, 560, y1], "texte": texte,
		        "style": {"taille": 10, "gras": False}, "auto": auto, "lignes": lignes}

	def test_les_etapes_qui_se_suivent_partagent_une_boite(self):
		ops = [self._t(0, 40, 52, "Filter Cartridge Replacement"), self._t(1, 60, 84, "1. Turn off water.", lignes=2),
		       self._t(2, 86, 98, "2. Unscrew housing."), self._t(3, 100, 112, "3. Discard."), self._t(4, 130, 142, "Caution: read the label.")]
		out = R.grouper_entrees(ops)
		self.assertEqual([o["id"] for o in out], [0, 1, 4])
		g = out[1]
		self.assertEqual(g["groupe"], [1, 2, 3])
		self.assertEqual(g["bbox"], [87, 60, 560, 112])
		self.assertEqual(g["texte"], "1. Turn off water.\n2. Unscrew housing.\n3. Discard.")
		self.assertEqual(g["lignes"], 4)
		self.assertEqual(len(g["styles"]), 3)

	def test_une_entree_deplacee_reste_seule(self):
		ops = [self._t(1, 60, 72, "1. A"), self._t(2, 74, 86, "2. B", auto=False), self._t(3, 88, 100, "3. C")]
		out = R.grouper_entrees(ops)
		self.assertEqual([o.get("groupe") for o in out], [None, None, None])

	def test_un_grand_ecart_ou_une_autre_colonne_coupe_la_liste(self):
		ops = [self._t(1, 60, 72, "1. A"), self._t(2, 120, 132, "2. B"), self._t(3, 134, 146, "3. C", x0=300)]
		out = R.grouper_entrees(ops)
		self.assertEqual([o.get("groupe") for o in out], [None, None, None])

	def test_html_groupe_un_p_par_entree(self):
		h = R.html_groupe(["1. A", "2. B"], [{"taille": 10}, {"taille": 9, "gras": True}], False, "Noto Sans")
		self.assertEqual(h.count("<p "), 2)
		self.assertIn("margin-top:0.25em;font-family", h)
		self.assertIn("font-size:9pt", h)

	def test_plan_page_groupe_les_entrees(self):
		paras = [dict(PARAS[1], texte="1. Replace every 12 months."),
		         {"id": 9, "page": 0, "bbox": (50, 162, 300, 180), "texte": "2. Rinse.", "style": PARAS[1]["style"], "dir": (1, 0)}]
		plan = R.plan_page(0, paras, {1: "1. Remplacer.", 9: "2. Rincer."})
		self.assertEqual(len(plan["textes"]), 1)
		self.assertEqual(plan["textes"][0]["groupe"], [1, 9])
		self.assertEqual(len(plan["redactions"]), 2)


class TestAnalyse(unittest.TestCase):
	def test_page_image(self):
		self.assertTrue(X.est_page_image(0, 1))
		self.assertTrue(X.est_page_image(21, 7))
		self.assertFalse(X.est_page_image(0, 0))        # page blanche : rien à poser d'office
		self.assertFalse(X.est_page_image(502, 10))

	def test_illustration_assez_grande(self):
		self.assertTrue(X.est_illustration((0, 0, 40, 40)))
		self.assertFalse(X.est_illustration((0, 0, 39, 400)))
		self.assertFalse(X.est_illustration(None))

	def test_dpi_pour_borne_la_page(self):
		self.assertEqual(R.dpi_pour([612, 792], 1400), 127)
		self.assertEqual(R.dpi_pour([2000, 2000], 1400), 50)
		self.assertEqual(R.dpi_pour([100, 100], 1400), 150)

	def test_est_pivote(self):
		self.assertFalse(R.est_pivote({"dir": (1, 0)}))
		self.assertFalse(R.est_pivote({}))
		self.assertTrue(R.est_pivote({"dir": (0, -1)}))
		self.assertTrue(R.est_pivote({"dir": [0, 1]}))


class TestRemapper(unittest.TestCase):
	def test_report_par_texte_et_page(self):
		ancienne = {"pages": 2, "paragraphes": [
			{"id": 0, "page": 0, "texte": "Filter  Cartridges"}, {"id": 1, "page": 0, "texte": "1. Turn off water. 2. Unscrew."},
			{"id": 2, "page": 1, "texte": "Parts list"}], "images": [{"id": "p1-i0"}]}
		nouvelle = {"pages": 2, "paragraphes": [
			{"id": 0, "page": 0, "texte": "Filter Cartridges"}, {"id": 1, "page": 0, "texte": "1. Turn off water."},
			{"id": 2, "page": 0, "texte": "2. Unscrew."}, {"id": 3, "page": 1, "texte": "Parts list"}], "images": [{"id": "p1-i0"}]}
		trad, ed = S.remapper(ancienne, nouvelle, {"0": "Cartouches", "1": "1. Coupez. 2. Dévissez.", "2": "Pièces"},
		                      {"textes": {"2": "Liste des pièces"}, "blocs": {"0": {"taille": 9}, "1": {"traitement": "efface"}},
		                       "libres": [{"id": "L1", "type": "texte", "page": 1, "bbox": [0, 0, 10, 10], "texte": "x"}],
		                       "images": {"p1-i0": {"fichier": "/a.png"}, "p0-i9": {"fichier": "/b.png"}}})
		self.assertEqual(trad, {"0": "Cartouches", "3": "Pièces"})         # le bloc redécoupé est retraduit
		self.assertEqual(ed["textes"], {"3": "Liste des pièces"})
		self.assertEqual(ed["blocs"], {"0": {"taille": 9}})
		self.assertEqual(len(ed["libres"]), 1)
		self.assertEqual(ed["images"], {"p1-i0": {"fichier": "/a.png"}})

	def test_meme_texte_sur_une_autre_page_ne_se_confond_pas(self):
		ancienne = {"pages": 2, "paragraphes": [{"id": 0, "page": 0, "texte": "NOTE"}, {"id": 1, "page": 1, "texte": "NOTE"}]}
		nouvelle = {"pages": 2, "paragraphes": [{"id": 5, "page": 1, "texte": "NOTE"}]}
		trad, _ = S.remapper(ancienne, nouvelle, {"0": "REMARQUE p1", "1": "REMARQUE p2"}, {})
		self.assertEqual(trad, {"5": "REMARQUE p2"})


class TestIllustrationIA(unittest.TestCase):
	def test_taille_selon_la_region(self):
		self.assertEqual(S.taille_illustration([0, 0, 300, 100]), "1536x1024")
		self.assertEqual(S.taille_illustration([0, 0, 100, 300]), "1024x1536")
		self.assertEqual(S.taille_illustration([0, 0, 110, 100]), "1024x1024")

	def test_cadre_relatif_centre_la_region(self):
		# région 2:1 dans un canevas 3:2 : toute la largeur, hauteur 2/3
		x0, y0, x1, y1 = S.cadre_relatif(200, 100, "1536x1024")
		self.assertEqual((x0, x1), (0.0, 1.0))
		self.assertAlmostEqual(y1 - y0, (1536 / 1024) / 2, places=3)
		self.assertAlmostEqual(y0, (1 - (y1 - y0)) / 2, places=3)
		# région carrée dans un canevas carré : tout le canevas
		self.assertEqual(S.cadre_relatif(100, 100, "1024x1024"), (0.0, 0.0, 1.0, 1.0))
		# région haute dans un canevas paysage : toute la hauteur
		x0, y0, x1, y1 = S.cadre_relatif(100, 300, "1536x1024")
		self.assertEqual((y0, y1), (0.0, 1.0))
		self.assertLess(x1 - x0, 0.3)

	def test_prompt_illustration(self):
		p = S.prompt_illustration({"code": "fr", "libelle": "Français"}, "garder les numéros")
		self.assertIn("Français", p)
		self.assertIn("(language code fr)", p)
		self.assertIn("Additional instruction: garder les numéros.", p)
		self.assertNotIn("right to left", p)
		self.assertIn("right to left", S.prompt_illustration({"code": "ar", "libelle": "Arabe", "rtl": 1}))


if __name__ == "__main__":
	unittest.main()


class TestCombine(unittest.TestCase):
	def test_parties_source_puis_langues_terminees(self):
		doc = {"pdf_source": "/private/files/src.pdf", "langue_source": "en",
		       "traductions": [_L("fr", "Terminé", "/private/files/fr.pdf"), _L("ar", "En attente", None), _L("de", "Terminé", "/private/files/de.pdf")]}
		infos = {"en": {"libelle": "Anglais"}, "fr": {"libelle": "Français"}}
		self.assertEqual(S.parties_combine(doc, infos), [("Anglais", "/private/files/src.pdf"), ("Français", "/private/files/fr.pdf"), ("de", "/private/files/de.pdf")])
		self.assertEqual([t for t, _u in S.parties_combine(doc, infos, avec_source=False)], ["Français", "de"])

	def test_combiner_pdfs_enchaine_et_signe(self):
		try:
			import pymupdf
		except ImportError:
			self.skipTest("PyMuPDF absent")

		def pdf(n, texte):
			d = pymupdf.open()
			for i in range(n):
				d.new_page().insert_text((72, 72), "%s %d" % (texte, i + 1))
			return d.tobytes()
		out = pymupdf.open(stream=S.combiner_pdfs([("Anglais", pdf(2, "EN")), ("Français", pdf(3, "FR"))]), filetype="pdf")
		self.assertEqual(len(out), 5)
		self.assertEqual(out.get_toc(), [[1, "Anglais", 1], [1, "Français", 3]])
		self.assertIn("FR 1", out[2].get_text())


def _L(langue, statut, fichier):
	return {"langue": langue, "statut": statut, "fichier": fichier}
