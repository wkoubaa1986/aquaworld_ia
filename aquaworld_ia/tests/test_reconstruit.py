"""Manuel reconstruit — structure, clés de traduction, HTML, PDF (pur ; le PDF via PyMuPDF sans site)."""
from __future__ import annotations

import json
import unittest

from aquaworld_ia.manuels import reconstruit as R


class TestNormaliser(unittest.TestCase):
	def test_types_et_nettoyage(self):
		blocs = R.normaliser_blocs([
			{"type": "titre", "niveau": 7, "texte": "  Installation  "}, {"type": "sous_titre", "texte": "Saddle valve"},
			{"type": "paragraphe", "texte": ""}, {"type": "liste", "items": ["a", " ", "b"]}, {"type": "etapes", "items": []},
			{"type": "tableau", "lignes": [["Model", "Flow"], ["RO-50", "50 GPD", "extra"], ["", ""]]},
			{"type": "figure", "bbox": [10, 20, 60, 70], "legende": "Fig. 1"}, {"type": "figure", "bbox": [10, 20, 11, 70]},
			{"type": "figure", "bbox": "n/a"}, {"type": "sommaire"}, {"type": "inconnu", "texte": "x"}, "pas un dict",
			{"type": "avertissement", "texte": "WARNING: hot"},
		])
		self.assertEqual([b["type"] for b in blocs], ["titre", "titre", "liste", "tableau", "figure", "note"])
		self.assertEqual(blocs[0]["niveau"], 3)
		self.assertEqual(blocs[1]["niveau"], 2)
		self.assertEqual(blocs[2]["items"], ["a", "b"])
		self.assertEqual(blocs[3]["lignes"], [["Model", "Flow", ""], ["RO-50", "50 GPD", "extra"]])
		self.assertEqual(blocs[4]["bbox"], [10.0, 20.0, 60.0, 70.0])
		self.assertTrue(all(len(b["id"]) == 12 for b in blocs))

	def test_id_stable_par_contenu(self):
		a = R.normaliser_blocs([{"type": "paragraphe", "texte": "Turn off the water."}])[0]
		b = R.normaliser_blocs([{"type": "paragraphe", "texte": "Turn  off the water. "}])[0]
		self.assertEqual(a["id"], b["id"])

	def test_lire_tolere(self):
		self.assertEqual(R.lire(None), {"version": 1, "pages": {}})
		self.assertEqual(R.lire('{"pages": {"0": {"blocs": []}, "x": 3}}')["pages"], {"0": {"blocs": []}})


class TestTraductions(unittest.TestCase):
	structure = {"version": 1, "pages": {
		"0": {"blocs": R.normaliser_blocs([{"type": "titre", "niveau": 1, "texte": "Installation"}, {"type": "etapes", "items": ["Turn off water.", "Unscrew."]},
		                                   {"type": "tableau", "lignes": [["Model", "Flow"], ["RO-50", "50 GPD"]]}, {"type": "figure", "bbox": [0, 0, 50, 50], "legende": "Exploded view"}])},
		"1": {"blocs": R.normaliser_blocs([{"type": "titre", "niveau": 1, "texte": "Installation"}, {"type": "paragraphe", "texte": "Turn off water."}])},
	}}

	def test_textes_a_traduire_dedoublonnes_et_sans_references(self):
		t = R.textes_a_traduire(self.structure)
		# « RO-50 » (référence) n'y est pas ; « Turn off water. » revient comme paragraphe (clé typée) ; « Installation » une seule fois
		self.assertEqual([x["texte"] for x in t], ["Installation", "Turn off water.", "Unscrew.", "Model", "Flow", "50 GPD", "Exploded view", "Turn off water."])
		self.assertTrue(all(":" in x["id"] for x in t))
		# RO-50 et 50 GPD ne passent pas par l'IA ; déjà traduit = non redemandé
		t2 = R.textes_a_traduire(self.structure, {t[0]["id"]: "Installation (fr)"})
		self.assertEqual(t2[0]["texte"], "Turn off water.")

	def test_bloc_traduit_et_retour(self):
		trad = {"titre:" + R.empreinte("Installation"): "Installation FR", "item:" + R.empreinte("Unscrew."): "Dévissez.",
		        "cellule:" + R.empreinte("Flow"): "Débit"}
		b0 = R.bloc_traduit(self.structure["pages"]["0"]["blocs"][0], trad)
		self.assertEqual(b0["texte"], "Installation FR")
		b1 = R.bloc_traduit(self.structure["pages"]["0"]["blocs"][1], trad)
		self.assertEqual(b1["items"], ["Turn off water.", "Dévissez."])
		b2 = R.bloc_traduit(self.structure["pages"]["0"]["blocs"][2], trad)
		self.assertEqual(b2["lignes"], [["Model", "Débit"], ["RO-50", "50 GPD"]])
		# correction dans le studio : les clés reviennent en regard de la source
		cles = R.cles_du_bloc_traduit(self.structure["pages"]["0"]["blocs"][1], {"type": "etapes", "items": ["Coupez l'eau.", "Dévissez."]})
		self.assertEqual(cles, {"item:" + R.empreinte("Turn off water."): "Coupez l'eau.", "item:" + R.empreinte("Unscrew."): "Dévissez."})

	def test_html(self):
		trad = {"titre:" + R.empreinte("Installation"): "Installation FR"}
		h = R.html_corps(self.structure, trad, 500, {self.structure["pages"]["0"]["blocs"][3]["id"]: "fig.png"})
		self.assertIn("<h1>Installation FR</h1>", h)
		self.assertIn("<ol><li>Turn off water.</li><li>Unscrew.</li></ol>", h)
		self.assertIn("<th>Model</th>", h)
		self.assertIn('<img src="fig.png" width="288">', h)      # 50 % de la page × 1,15 × 500
		self.assertEqual(h.count("<h1>"), 2)
		self.assertEqual(R.titres_de_niveau_1(self.structure, trad), ["Installation FR", "Installation FR"])
		self.assertIn("direction:rtl", R.css_document("#123456", "Noto Naskh Arabic", True))


class TestPdf(unittest.TestCase):
	def test_composer_pdf(self):
		try:
			import pymupdf
		except ImportError:
			self.skipTest("PyMuPDF absent")
		src = pymupdf.open()
		pg = src.new_page(width=612, height=792)
		pg.draw_rect(pymupdf.Rect(50, 400, 300, 600), color=(0, 0, 1), width=3)
		structure = {"version": 1, "pages": {"0": {"blocs": R.normaliser_blocs([
			{"type": "titre", "niveau": 1, "texte": "Installation"}, {"type": "paragraphe", "texte": "Turn off the water supply. " * 30},
			{"type": "etapes", "items": ["Turn off water.", "Unscrew the housing."]}, {"type": "note", "texte": "WARNING: hot surface."},
			{"type": "tableau", "lignes": [["Model", "Flow"], ["RO-50", "50 GPD"]]},
			{"type": "figure", "bbox": [8, 50, 50, 76], "legende": "Exploded view"},
			{"type": "titre", "niveau": 1, "texte": "Maintenance"}, {"type": "paragraphe", "texte": "Replace the filter yearly. " * 200}])}}}
		trad = {"titre:" + R.empreinte("Installation"): "Installation", "note:" + R.empreinte("WARNING: hot surface."): "ATTENTION : surface chaude."}
		octets = R.composer_pdf(src.tobytes(), structure, trad, {"code": "fr", "libelle": "Français", "rtl": 0}, [[612, 792]],
		                        "Osmoseur domestique", "AP-M", gabarit={"logo": None, "couleur": "#1d4ed8", "format": "A4", "editeur": "Aquaworld"})
		doc = pymupdf.open(stream=octets, filetype="pdf")
		self.assertGreaterEqual(len(doc), 4)              # couverture, sommaire, ≥ 2 pages de corps
		self.assertIn("Osmoseur domestique", doc[0].get_text())
		self.assertIn("Sommaire", doc[1].get_text())
		self.assertIn("Maintenance", doc[1].get_text())
		self.assertIn("ATTENTION", doc[2].get_text())
		self.assertIn("Aquaworld", doc[2].get_text())
		self.assertIn("3 / %d" % len(doc), doc[2].get_text())
		self.assertGreaterEqual(len(doc[2].get_images()), 1)   # la figure découpée


class TestMiseEnPageIA(unittest.TestCase):
	page = {"blocs": R.normaliser_blocs([{"type": "titre", "niveau": 1, "texte": "Installation"},
	                                    {"type": "figure", "bbox": [10, 20, 60, 70], "legende": "Vue"}])}

	def test_dimensions_figures_et_message(self):
		f = R.dimensions_figures_mm(self.page, [612, 792])
		self.assertEqual(len(f), 1)
		self.assertAlmostEqual(f[0]["largeur_mm"], 0.5 * 612 * 25.4 / 72, places=0)
		m = json.loads(R.message_mise_en_page(self.page, {"titre:" + R.empreinte("Installation"): "Installation FR"}, [612, 792], (595, 842),
		                                      {"code": "fr", "libelle": "Français", "rtl": 0}, "Noto Sans", "#1d4ed8"))
		self.assertEqual(m["page_mm"], {"width": 209.9, "height": 297.0, "margins_mm": 12})
		self.assertEqual(m["blocks"][0]["texte"], "Installation FR")
		self.assertNotIn("bbox", m["blocks"][1])
		self.assertEqual(m["figures"][0]["id"], self.page["blocs"][1]["id"])

	def test_remplacer_figures_et_polices(self):
		ident = self.page["blocs"][1]["id"]
		h = R.remplacer_figures('<img src="fig:%s"><img src="fig:0123456789ab">' % ident, {ident: b"PNGDATA"})
		self.assertIn('src="data:image/jpeg;base64,UE5HREFUQQ=="', h)
		self.assertIn('src="data:image/png;base64,', R.remplacer_figures('<img src="fig:%s">' % ident, {ident: b"\x89PNG\r\n"}))
		self.assertIn('style="display:none"', h)
		self.assertTrue(R.injecter_polices("<html><head><title>x</title></head><body></body></html>", "@font-face{}").startswith("<html><head><style>@font-face{} html,body{margin:0;padding:0;}</style><title>"))
		self.assertTrue(R.injecter_polices("<p>sans head</p>", "X").startswith("<style>X html,body"))

	def test_rendu_wkhtmltopdf(self):
		try:
			import pdfkit, pymupdf
		except ImportError:
			self.skipTest("pdfkit absent")
		html = "<!doctype html><html><head><meta charset=\"utf-8\"><style>.page{width:210mm;height:297mm;overflow:hidden;padding:12mm;box-sizing:border-box}</style></head><body><div class=\"page\"><h1>Installation</h1><table><tr><td>gauche</td><td>droite</td></tr></table></div></body></html>"
		pdf = R.html_vers_pdf(R.injecter_polices(html, R.css_polices_data_uri()), (595.0, 842.0))
		d = pymupdf.open(stream=pdf, filetype="pdf")
		self.assertEqual(len(d), 1)
		self.assertEqual([round(d[0].rect.width), round(d[0].rect.height)], [595, 842])
		self.assertEqual(R.FORMATS["A4"], (595.28, 841.89))
		self.assertIn("droite", d[0].get_text())


class TestFormatSortie(unittest.TestCase):
	def test_original_et_orientation(self):
		self.assertEqual(R.format_sortie({"format": "Original"}, [794, 561]), (794.0, 561.0))
		self.assertEqual(R.format_sortie({"format": "A4"}, [794, 561]), (841.89, 595.28))     # paysage gardé
		self.assertEqual(R.format_sortie({"format": "A4"}, [612, 792]), (595.28, 841.89))
		self.assertEqual(R.format_sortie({"format": "A5"}, None), (419.53, 595.28))
		self.assertEqual(R.mm_page((794, 561)), (280.1, 197.9))
		self.assertEqual(R.mm_page((595.28, 841.89)), (210.0, 297.0))

	def test_sans_pages_blanches(self):
		try:
			import pymupdf
		except ImportError:
			self.skipTest("PyMuPDF absent")
		d = pymupdf.open()
		d.new_page().insert_text((72, 72), "Contenu")
		pg = d.new_page(); pg.draw_rect(pymupdf.Rect(0, 0, 612, 0.4), fill=(0, 0, 0), color=None)   # bande de 0,15 mm en haut
		d.new_page()
		out = pymupdf.open(stream=R.sans_pages_blanches(d.tobytes()), filetype="pdf")
		self.assertEqual(len(out), 1)          # la bande et la page vide sont des débordements
		d3 = pymupdf.open(); d3.new_page().insert_text((72, 72), "A"); d3.new_page().insert_text((72, 12), "une ligne qui a débordé")
		self.assertEqual(len(pymupdf.open(stream=R.sans_pages_blanches(d3.tobytes()), filetype="pdf")), 2)   # du texte : on garde
		d2 = pymupdf.open(); d2.new_page().insert_text((72, 72), "A"); pg = d2.new_page(); pg.draw_rect(pymupdf.Rect(50, 50, 500, 700), fill=(0, 0, 0))
		self.assertEqual(len(pymupdf.open(stream=R.sans_pages_blanches(d2.tobytes()), filetype="pdf")), 2)


class TestTextesAbsents(unittest.TestCase):
	def test_detecte_les_textes_coupes(self):
		blocs = [{"type": "titre", "texte": "Mode de fonctionnement :"}, {"type": "liste", "items": ["Manuel", "18S", "Automatique"]},
		         {"type": "figure", "legende": "Vue"}, {"type": "tableau", "lignes": [["Modèle", "Débit"]]}]
		pdf = "MANUEL D’INSTALLATION\nMode de\nfonctionnement :\nManuel\nModèle Débit"
		self.assertEqual(R.textes_absents(pdf, blocs), ["Automatique"])   # « 18S » et « Vue » trop courts pour compter
		self.assertEqual(R.textes_absents(pdf + " 18S Automatique", blocs), [])


class TestAjusterFigure(unittest.TestCase):
	fmt = [800, 600]

	def test_recale_sur_les_objets_recouverts(self):
		# cadre IA large et décalé ; objet réel [71,273,326,371] recouvert à 58 %
		out = R.ajuster_figure([5, 52.3, 46.6, 69.2], [[71, 273, 326, 371], [600, 50, 700, 100]], self.fmt)
		# → union de l'objet + marge 2 pt, en %
		self.assertEqual(out, [round(69 / 8, 1), round(271 / 6, 1), round(328 / 8, 1), round(373 / 6, 1)])

	def test_sans_objet_ou_union_trop_grande_on_garde(self):
		self.assertEqual(R.ajuster_figure([10, 10, 20, 20], [], self.fmt), [10, 10, 20, 20])
		self.assertEqual(R.ajuster_figure([10, 10, 20, 20], [[700, 500, 750, 550]], self.fmt), [10, 10, 20, 20])
		# un objet parasite quasi pleine page recouvert à 30 % ferait exploser l'union : on garde le cadre IA
		self.assertEqual(R.ajuster_figure([10, 10, 60, 60], [[0, 0, 800, 600]], self.fmt), [10, 10, 60, 60])

	def test_ajuster_blocs_recalcule_l_id(self):
		blocs = R.normaliser_blocs([{"type": "figure", "bbox": [5, 50, 47, 70]}, {"type": "paragraphe", "texte": "x y"}])
		out = R.ajuster_figures(blocs, [[71, 273, 326, 371]], self.fmt)
		self.assertNotEqual(out[0]["id"], blocs[0]["id"])
		self.assertEqual(out[1]["id"], blocs[1]["id"])
		self.assertEqual(R.regions_en_pct([[80, 60, 160, 120]], self.fmt), [[10.0, 10.0, 20.0, 20.0]])


class TestFiguresManuelles(unittest.TestCase):
	def test_masques_et_image(self):
		blocs = R.normaliser_blocs([
			{"type": "figure", "bbox": [10, 10, 50, 50], "masques": [[12, 12, 20, 15], [0, 0, 0.1, 0.1], "x"]},
			{"type": "image", "fichier": "/files/logo.png", "largeur": 250, "legende": "Certifié NSF"},
			{"type": "image", "fichier": "http://ailleurs/x.png"}])
		self.assertEqual(blocs[0]["masques"], [[12.0, 12.0, 20.0, 15.0]])
		self.assertEqual(len(blocs), 2)
		self.assertEqual(blocs[1]["largeur"], 100.0)
		self.assertEqual(R.textes_du_bloc(blocs[1]), [("legende:" + R.empreinte("Certifié NSF"), "Certifié NSF")])
		h = R.html_bloc(blocs[1], 500, {blocs[1]["id"]: "fig.png"})
		self.assertIn('width="500"', h); self.assertIn("Certifié NSF", h)
		d = R.dimensions_figures_mm({"blocs": blocs}, [612, 792], {blocs[1]["id"]: (200, 100)}, largeur_texte_mm=186)
		self.assertEqual(d[1], {"id": blocs[1]["id"], "largeur_mm": 186.0, "hauteur_mm": 93.0, "ajoutee": True})

	def test_appliquer_masques(self):
		from PIL import Image
		im = Image.new("RGB", (100, 50), (0, 0, 0)); buf = __import__("io").BytesIO(); im.save(buf, format="PNG")
		out = Image.open(__import__("io").BytesIO(R.appliquer_masques(buf.getvalue(), [10, 10, 50, 30], [[10, 10, 30, 20]])))
		self.assertEqual(out.getpixel((10, 10)), (255, 255, 255))   # dans le masque (moitié gauche, moitié haute)
		self.assertEqual(out.getpixel((80, 40)), (0, 0, 0))
		self.assertEqual(R.appliquer_masques(buf.getvalue(), [10, 10, 50, 30], []), buf.getvalue())


class TestIdsFigures(unittest.TestCase):
	def test_ids(self):
		blocs = R.normaliser_blocs([{"type": "figure", "bbox": [0, 0, 10, 10]}, {"type": "paragraphe", "texte": "x y"}, {"type": "image", "fichier": "/files/a.png"}])
		self.assertEqual(R.ids_figures({"blocs": blocs}), {blocs[0]["id"], blocs[2]["id"]})
		self.assertEqual(R.ids_figures(None), set())
