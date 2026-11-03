import base64
import unittest
from unittest.mock import patch
from xml.etree import ElementTree

import frappe
import pymupdf

from aquaworld_ia.emballage import apercu_elements as A, composition as C, codes


ROUGE = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10" fill="#ff0000"/></svg>'
BLEU = ROUGE.replace(b"#ff0000", b"#0000ff")


class TestPlacementSymboles(unittest.TestCase):
	def test_selection_explicitement_choisie_et_tampons(self):
		z = {"zone": "pictos", "x": 10, "y": 20, "w": 60, "h": 20}
		catalogue = [("rouge", ROUGE), ("bleu", BLEU), ("tampon", ROUGE)]
		def elements(zone):
			return C.elements_symboles(zone, "avant", pictos_svg=catalogue, tampons={"tampon"})
		self.assertEqual([e["code"] for e in elements(z)], ["rouge", "bleu"])
		self.assertEqual([e["code"] for e in elements(dict(z, pictos=["bleu"]))], ["bleu"])
		self.assertEqual([e["code"] for e in elements(dict(z, pictos=["tampon"]))], ["tampon"])
		self.assertEqual(elements(dict(z, pictos=["absent"])), [])
		self.assertEqual([e["code"] for e in elements(dict(z, pictos=[]))], ["rouge", "bleu"])
		self.assertEqual(elements(dict(z, pictos=[], pictos_mode="selection")), [])
		self.assertEqual(elements(dict(z, pictos_mode="selection")), [])

	def test_selection_vide_sur_une_face_et_heritage_des_autres(self):
		from aquaworld_ia.emballage import geometrie
		plan = geometrie.plan_a_plat(geometrie.ETUI, 142, 355, 30)
		contenu = {"pictos": 3, "nom": True}
		face = geometrie.face(plan, "avant")
		avant = [{"zone": "pictos", "x": face["x"]+10, "y": face["y"]+30, "w": 60, "h": 20}]
		arriere = C.zones_par_face(plan, contenu, faces_identiques=True, mise_en_page={"avant": avant})["arriere"]
		i = next(i for i, z in enumerate(arriere) if z["zone"] == "pictos")
		arriere[i].update(pictos=[], pictos_mode="selection", decalage_contenu={"x": 2, "y": -1})
		zones = C.zones_par_face(plan, contenu, faces_identiques=True, mise_en_page={"avant": avant, "arriere": arriere})
		self.assertEqual(zones["avant"], avant)
		self.assertEqual(zones["arriere"][i]["pictos_mode"], "selection")
		self.assertEqual(C.selection_pictos(zones["arriere"][i]), [])
		self.assertEqual(zones["arriere"][i]["decalage_contenu"], {"x": 2, "y": -1})
		self.assertEqual(C.elements_symboles(zones["arriere"][i], "arriere", pictos_svg=[("rouge", ROUGE)]), [])

	def test_symboles_cote_a_cote_tous_dans_la_zone(self):
		z = {"zone": "pictos", "x": 20, "y": 30, "w": 20, "h": 10}
		elements = C.elements_symboles(z, "avant", pictos_svg=[(str(i), ROUGE) for i in range(5)])
		self.assertEqual(len(elements), 5)
		for e in elements:
			x, y, w, h = e["rect"]
			self.assertGreater(w, 0); self.assertEqual(w, h)
			self.assertGreaterEqual(x, 20); self.assertLessEqual(x + w, 40)
			self.assertGreaterEqual(y, 30); self.assertLessEqual(y + h, 40)
		self.assertEqual(C.elements_symboles(dict(z, w=3), "avant", pictos_svg=[(str(i), ROUGE) for i in range(5)]), [])

	def test_qr_centre_et_dedoublonne_ean_preserve(self):
		z = {"zone": "code_barres", "x": 50, "y": 20, "w": 40, "h": 20}
		e = C.elements_symboles(dict(z, code="qr"), "avant", qr=BLEU, ean=ROUGE)
		self.assertEqual([(x["code"], x["rect"]) for x in e], [("qr", [60, 20, 20, 20])])
		e = C.elements_symboles(z, "arriere", qr=BLEU, ean=ROUGE)
		self.assertEqual([x["code"] for x in e], ["ean", "qr"])
		self.assertEqual(e[1]["rect"], [30, 22, 18, 18])
		self.assertEqual([x["code"] for x in C.elements_symboles(z, "arriere", qr=BLEU, ean=ROUGE, qr_place=True)], ["ean"])
		self.assertEqual(C.elements_symboles(dict(z, code="ean"), "avant", qr=BLEU), [])

	def test_colonne_ajustee_au_cadre_sans_changer_selection_ni_ordre(self):
		z = {"zone": "pictos", "x": 20, "y": 30, "w": 15, "h": 80, "pictos_disposition": "vertical"}
		catalogue = [("rouge", ROUGE), ("bleu", BLEU), ("tampon", ROUGE)]
		for w, h in ((15, 80), (50, 15), (3, 20)):
			with self.subTest(w=w, h=h):
				elements = C.elements_symboles(dict(z, w=w, h=h), "avant", pictos_svg=catalogue)
				self.assertEqual([e["code"] for e in elements], [c for c, _ in catalogue])
				self.assertEqual(len({e["rect"][0] for e in elements}), 1)
				for i, el in enumerate(elements):
					x, y, largeur, hauteur = el["rect"]
					self.assertGreater(largeur, 0); self.assertEqual(largeur, hauteur)
					self.assertGreaterEqual(x, 20); self.assertLessEqual(x+largeur, 20+w+.001)
					self.assertGreaterEqual(y, 30); self.assertLessEqual(y+hauteur, 30+h+.001)
					if i: self.assertGreater(y, elements[i-1]["rect"][1]+elements[i-1]["rect"][3])
		self.assertEqual(C.elements_symboles(dict(z, h=3), "avant", pictos_svg=catalogue), [])
		self.assertEqual(C.elements_symboles(dict(z, pictos_mode="selection", pictos=[]), "avant", pictos_svg=catalogue), [])
		e = C.elements_symboles(dict(z, pictos=["bleu", "tampon"]), "avant", pictos_svg=catalogue, tampons={"tampon"})
		self.assertEqual([el["code"] for el in e], ["bleu", "tampon"])
		for invalide in (None, "horizontal", "inconnu", 1):
			self.assertEqual(C.elements_symboles(dict(z, pictos_disposition=invalide), "avant", pictos_svg=catalogue),
			                 C.elements_symboles({k: v for k, v in z.items() if k != "pictos_disposition"}, "avant", pictos_svg=catalogue))

	def test_disposition_conservee_apres_bornage_et_copie(self):
		f = {"x": 0, "y": 0, "w": 100, "h": 200}
		z = {"zone": "pictos", "x": 10, "y": 30, "w": 25, "h": 100, "pictos_disposition": "vertical", "decalage_contenu": {"x": 2, "y": -3}}
		self.assertEqual(C.borner_zone(z, f), z)
		copie = C.translater_zones([z], f, dict(f, x=200))[0]
		self.assertEqual(copie["pictos_disposition"], "vertical")
		self.assertEqual(copie["decalage_contenu"], z["decalage_contenu"])
		self.assertNotIn("pictos_disposition", C.borner_zone(dict(z, zone="code_barres"), f))

	def test_pdf_vertical_vectoriel_avec_decalage_et_cartouches(self):
		z = {"zone": "pictos", "x": 10, "y": 10, "w": 20, "h": 50, "pictos_disposition": "vertical"}
		elements = C.elements_symboles(z, "avant", pictos_svg=[("rouge", ROUGE), ("bleu", BLEU)])
		with pymupdf.open() as pdf:
			p = pdf.new_page(width=200, height=220)
			C.poser_symboles(p, elements, C._rect_pt(10, 10, 20, 50), {"x": 2, "y": 3})
			pix = p.get_pixmap()
			self.assertEqual(pix.pixel(round(C.MM(22)), round(C.MM(23))), (255, 0, 0))
			self.assertEqual(pix.pixel(round(C.MM(22)), round(C.MM(45))), (0, 0, 255))
			self.assertEqual(pix.pixel(round(C.MM(33)), round(C.MM(23))), (255, 255, 255))
			self.assertFalse(p.get_images())

	def test_placements_partages_impriment_les_bons_pictos_vectoriels(self):
		z = {"zone": "pictos", "x": 10, "y": 10, "w": 40, "h": 20, "pictos": ["bleu"]}
		with pymupdf.open() as pdf:
			page = pdf.new_page(width=200, height=200)
			C.poser_symboles(page, C.elements_symboles(z, "avant", pictos_svg=[("rouge", ROUGE), ("bleu", BLEU)]))
			self.assertEqual(page.get_images(), [])
			self.assertEqual(page.get_pixmap().pixel(round(C.MM(20)), round(C.MM(20))), (0, 0, 255))


class TestApercuSymboles(unittest.TestCase):
	def test_apercu_vertical_et_pdf_partagent_les_memes_emplacements(self):
		doc = frappe._dict(pictogrammes=[frappe._dict(pictogramme=c) for c in ("rouge", "bleu")])
		z = {"zone": "pictos", "x": 10, "y": 20, "w": 15, "h": 60, "pictos_disposition": "vertical"}
		a = {"faces": [{"code": "avant", "zones": [z]}]}
		with patch.object(A.pictos, "svg_bytes", side_effect=lambda c: BLEU if c == "bleu" else ROUGE), patch.object(A.frappe, "get_all", return_value=[]):
			A.enrichir(doc, a)
		exportes = C.elements_symboles(z, "avant", pictos_svg=[("rouge", ROUGE), ("bleu", BLEU)])
		self.assertEqual([e["rect"] for e in z["apercu_elements"]], [e["rect"] for e in exportes])
		self.assertEqual(z["apercu_elements"][0]["rect"][0], z["apercu_elements"][1]["rect"][0])

	def test_chaque_choix_a_son_contenu_reel_avant_ajout_sans_changer_le_plan(self):
		d = frappe._dict(nom_produit="Robinet de test", type_code_barres="EAN-13 + QR", code_barres="4006381333931",
			url_qr="https://example.com/test", pictogrammes=[frappe._dict(pictogramme="tampon")])
		textes = {"fr": {"accroche": "Eau fraîche", "caracteristiques": ["Débit 5 L/min"],
			"avertissements": ["Conserver au sec"], "contact": "Atelier de test"}}
		choix = A.choix_zones(d, textes, {}, set(), "Noto Sans")
		self.assertEqual(set(choix), set(C.ZONES_AJOUTABLES) | {"qr"})
		for zone, texte in {"nom": d.nom_produit, "accroche": "Eau fraîche", "caracteristiques": "Débit 5 L/min",
			"avertissements": "Conserver au sec", "contact": "Atelier de test"}.items():
			self.assertIn(texte, choix[zone]["apercu_texte"])
		self.assertEqual(choix["texte_libre"]["apercu_texte"], "")
		zone_auto = {"zone": "code_barres", "x": 50, "y": 0, "w": 40, "h": 20}
		a = {"choix_zones": choix, "faces": [{"code": "arriere", "zones": [zone_auto]}]}
		with patch.object(A.pictos, "svg_bytes", return_value=ROUGE), patch.object(A.frappe, "get_all", return_value=["tampon"]):
			A.enrichir(d, a)
		self.assertEqual([e["code"] for e in zone_auto["apercu_elements"]], ["ean", "qr"])
		self.assertEqual([e["code"] for e in choix["qr"]["apercu_elements"]], ["qr"])
		self.assertEqual([e["code"] for e in choix["tampon:tampon"]["apercu_elements"]], ["tampon"])
		self.assertEqual(len(a["faces"][0]["zones"]), 1)
		self.assertEqual(choix["pictos"]["apercu_elements"], [])  # Le tampon reste un choix distinct.
		self.assertEqual(len(a["images_zones"]), 3)

	def test_choix_vide_ne_fabrique_aucun_contenu_imprime(self):
		d = frappe._dict(pictogrammes=[])
		choix = A.choix_zones(d, {"fr": {}}, {}, set(), "Noto Sans")
		a = {"choix_zones": choix, "faces": []}
		A.enrichir(d, a)
		for z in choix.values():
			self.assertFalse(z.get("apercu_texte"))
			self.assertFalse(z.get("apercu_elements"))
			self.assertFalse(z.get("texte"))
		self.assertEqual(a["images_zones"], {})

	def test_images_dedoublonnees_et_selection_a_jour_sans_catalogue(self):
		doc = frappe._dict(pictogrammes=[frappe._dict(pictogramme=c) for c in ("rouge", "bleu", "tampon")])
		z = {"zone": "pictos", "x": 0, "y": 0, "w": 40, "h": 20, "pictos": ["bleu"]}
		a = {"faces": [{"code": "avant", "zones": [dict(z)]}, {"code": "arriere", "zones": [dict(z, x=100)]}]}
		with patch.object(A.pictos, "svg_bytes", side_effect=lambda c: BLEU if c == "bleu" else ROUGE), patch.object(A.frappe, "get_all", return_value=["tampon"]):
			A.enrichir(doc, a)
			self.assertEqual(len(a["images_zones"]), 1)
			for f in a["faces"]:
				self.assertEqual([el["code"] for el in f["zones"][0]["apercu_elements"]], ["bleu"])
			url = next(iter(a["images_zones"].values()))
			self.assertIn(b"#0000ff", base64.b64decode(url.split(",", 1)[1]))
			a["faces"][0]["zones"][0]["pictos"] = []
			A.enrichir(doc, a)
			self.assertEqual([el["code"] for el in a["faces"][0]["zones"][0]["apercu_elements"]], ["rouge", "bleu"])
			a["faces"][0]["zones"][0]["pictos_mode"] = "selection"
			A.enrichir(doc, a)
			self.assertEqual(a["faces"][0]["zones"][0]["apercu_elements"], [])
			self.assertEqual([el["code"] for el in a["faces"][1]["zones"][0]["apercu_elements"]], ["bleu"])
			self.assertIn("Aucun pictogramme choisi", a["faces"][0]["zones"][0]["apercu_message"])

	def test_codes_invalides_ne_bloquent_pas_la_saisie_et_qr_colore_est_visible(self):
		z = {"zone": "code_barres", "code": "qr", "x": 0, "y": 0, "w": 22, "h": 22}
		a = {"faces": [{"code": "avant", "zones": [z]}]}
		d = frappe._dict(type_code_barres="EAN-13", code_barres="123", pictogrammes=[])
		A.enrichir(d, a)
		self.assertEqual(z["apercu_elements"], [])
		self.assertIn("Code absent", z["apercu_message"])
		d.update(type_code_barres="QR", url_qr="https://example.com/test", couleur_qr="#1d4ed8")
		A.enrichir(d, a)
		self.assertEqual(len(z["apercu_elements"]), 1)
		self.assertNotIn("apercu_message", z)
		url = a["images_zones"][z["apercu_elements"][0]["image"]]
		svg = base64.b64decode(url.split(",", 1)[1])
		self.assertEqual(svg, codes.qr_svg(d.url_qr, d.couleur_qr))
		self.assertEqual(ElementTree.fromstring(svg).tag, "{http://www.w3.org/2000/svg}svg")
