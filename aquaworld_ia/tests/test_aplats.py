"""Impression en aplats : seules les couleurs d’impression sortent, en tracés, et le PDF se contrôle."""
import io
import json
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

import frappe
import pymupdf
from PIL import Image, ImageDraw, ImageFilter

from aquaworld_ia.emballage import aplats as A
from aquaworld_ia.emballage import composition as C

FONCE, CLAIR = "#0264c3", "#5badf0"


def png(im) -> bytes:
	b = io.BytesIO()
	im.save(b, "PNG")
	return b.getvalue()


def dessin(flou: float = 1.5) -> bytes:
	"""Un disque clair troué, barré d’une bande foncée, aux bords adoucis comme une image générée."""
	im = Image.new("RGB", (400, 400), "white")
	d = ImageDraw.Draw(im)
	d.ellipse((50, 50, 350, 350), fill=CLAIR)
	d.ellipse((150, 150, 250, 250), fill="white")
	d.rectangle((180, 20, 220, 380), fill=FONCE)
	return png(im.filter(ImageFilter.GaussianBlur(flou)))


def rendu(svg: bytes):
	with pymupdf.open(stream=svg, filetype="svg") as doc:
		return doc[0].get_pixmap(alpha=True)


class TestEncres(unittest.TestCase):
	def test_normalise_dedoublonne_et_ignore_le_blanc(self):
		self.assertEqual(A.encres("#0264C3, 5badf0 ; #fff #0264c3"), [FONCE, CLAIR])
		self.assertEqual(A.encres([CLAIR, "#FFFFFF"]), [CLAIR])
		self.assertEqual(A.encres('["#0264c3"]'), [FONCE])

	def test_refuse_vide_invalide_ou_trop_nombreux(self):
		for valeur in ("", "#ffffff", "bleu", "#111, #222, #333, #444, #555"):
			with self.assertRaises(ValueError):
				A.encres(valeur)

	def test_plus_proche_compte_le_blanc(self):
		self.assertEqual(A.plus_proche("#44a7ed", [FONCE, CLAIR]), CLAIR)
		self.assertEqual(A.plus_proche("#fafafa", [FONCE, CLAIR]), "#ffffff")
		self.assertEqual(A.plus_proche("#000000", [FONCE, CLAIR]), FONCE)


class TestVectoriser(unittest.TestCase):
	def test_seules_les_couleurs_d_impression_et_les_trous_restent(self):
		svg, infos = A.vectoriser(dessin(), [FONCE, CLAIR])
		racine = ET.fromstring(svg)
		self.assertNotIn(b"<image", svg)
		self.assertEqual({p.get("fill") for p in racine.iter("{%s}path" % A.SVG_NS)}, {FONCE, CLAIR})
		# La plus claire d’abord : la plus foncée est posée par-dessus.
		self.assertEqual([g.get("id") for g in racine.iter("{%s}g" % A.SVG_NS)], ["encre-1-5badf0", "encre-2-0264c3"])
		pix = rendu(svg)
		self.assertEqual(pix.pixel(200, 200), (2, 100, 195, 255))    # la bande foncée traverse le trou
		self.assertEqual(pix.pixel(100, 200), (91, 173, 240, 255))   # le disque clair
		self.assertEqual(pix.pixel(165, 200)[3], 0)                  # le trou laisse voir le support
		self.assertEqual(pix.pixel(5, 5)[3], 0)
		self.assertEqual(infos["avertissements"], [])
		self.assertAlmostEqual(infos["couverture"][CLAIR] + infos["couverture"][FONCE] + infos["blanc"], 100, delta=0.2)

	def test_aucun_lisere_clair_autour_d_une_forme_foncee(self):
		# Le bord adouci d’une forme foncée passe par des bleus clairs : ils ne doivent pas devenir un contour.
		im = Image.new("RGB", (300, 300), "white")
		ImageDraw.Draw(im).rectangle((80, 80, 220, 220), fill=FONCE)
		svg, infos = A.vectoriser(png(im.filter(ImageFilter.GaussianBlur(1.2))), [FONCE, CLAIR])
		self.assertLess(infos["couverture"][CLAIR], 0.5)
		self.assertNotIn(CLAIR.encode(), svg)

	def test_couleur_absente_signalee(self):
		im = Image.new("RGB", (120, 120), "white")
		ImageDraw.Draw(im).rectangle((20, 20, 100, 100), fill=FONCE)
		svg, infos = A.vectoriser(png(im), [FONCE, "#e11d48"])
		self.assertNotIn(b"e11d48", svg)
		self.assertTrue(any("#e11d48" in a for a in infos["avertissements"]))

	def test_photo_signalee_comme_approximative(self):
		im = Image.new("RGB", (200, 200))
		im.putdata([(x, (x + y) % 256, 255 - y) for y in range(200) for x in range(200)])
		_, infos = A.vectoriser(png(im), [FONCE, CLAIR])
		self.assertGreater(infos["nuances"], 25)
		self.assertTrue(any("nuances" in a for a in infos["avertissements"]))

	def test_un_grand_fond_blanc_ne_cache_pas_les_nuances(self):
		im = Image.new("RGB", (400, 400), "white")
		im.paste(Image.linear_gradient("L").resize((60, 60)).convert("RGB"), (10, 10))
		_, infos = A.vectoriser(png(im), [FONCE])
		self.assertGreater(infos["nuances"], 25)

	def test_un_svg_se_retrace_aux_nouvelles_couleurs(self):
		svg, _ = A.vectoriser(dessin(), [FONCE, CLAIR])
		une_couleur, infos = A.vectoriser(svg, [FONCE])
		self.assertEqual({p.get("fill") for p in ET.fromstring(une_couleur).iter("{%s}path" % A.SVG_NS)}, {FONCE})
		self.assertEqual(infos["encres"], [FONCE])

	def test_image_vide_ou_reglage_invalide(self):
		with self.assertRaises(ValueError):
			A.vectoriser(png(Image.new("RGB", (50, 50), "white")), [FONCE])
		with self.assertRaises(ValueError):
			A.vectoriser(dessin(), [FONCE], "extra")

	def test_consigne_ia_porte_les_couleurs(self):
		texte = A.prompt("#0264c3, #5badf0", "SEL EN PASTILLES", "contour épais.")
		self.assertIn("EXACTLY 2 solid ink colours", texte)
		self.assertIn("#0264C3, #5BADF0", texte)
		self.assertIn("SEL EN PASTILLES", texte)
		self.assertTrue(texte.endswith("contour épais."))
		self.assertIn("EXACTLY 1 solid ink colour ", A.prompt("#000000"))


class TestPdf(unittest.TestCase):
	def test_le_decor_couvre_la_face_sans_bitmap(self):
		# Un SVG carré sur une face en hauteur : il déborde en largeur, coupé au cadre, sans bande vide.
		svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100" height="100"><rect width="100" height="100" fill="#0264c3"/><circle cx="50" cy="50" r="10" fill="#5badf0"/></svg>'
		with pymupdf.open() as doc:
			page = doc.new_page(width=300, height=400)
			C.poser_svg_couvrant(page, (50, 100, 150, 300), svg)
			with pymupdf.open(stream=doc.tobytes(), filetype="pdf") as pdf:
				self.assertEqual(pdf[0].get_images(), [])
				self.assertTrue(pdf[0].get_drawings())
				pix = pdf[0].get_pixmap()
				for point in ((52, 102), (148, 298), (52, 298), (148, 102)):
					self.assertEqual(pix.pixel(*point), (2, 100, 195), point)
				self.assertEqual(pix.pixel(100, 200), (91, 173, 240))
				for dehors in ((40, 200), (160, 200), (100, 90), (100, 310)):
					self.assertEqual(pix.pixel(*dehors), (255, 255, 255), dehors)

	def test_fond_de_face_svg_pose_en_traces(self):
		svg, _ = A.vectoriser(dessin(), [FONCE, CLAIR])
		dpi = {}
		with pymupdf.open() as doc, patch.object(C.fichiers, "lire", return_value=svg):
			page = doc.new_page(width=400, height=600)
			pose = C._poser_fond_regle(page, {"mode": "image", "image": "/private/files/x.svg"}, (10, 10, 100, 150),
			                           {"code": "avant"}, None, None, dpi)
			self.assertTrue(pose)
			self.assertEqual(dpi, {"avant": None})
			self.assertEqual(page.get_images(), [])
			self.assertTrue(page.get_drawings())

	def pdf_de_controle(self) -> bytes:
		with pymupdf.open() as doc:
			page = doc.new_page(width=300, height=300)
			page.draw_rect((10, 10, 100, 100), color=None, fill=(2 / 255, 100 / 255, 195 / 255))
			page.draw_rect((120, 10, 200, 100), color=None, fill=(1, 1, 1))
			page.draw_rect((10, 120, 100, 200), color=None, fill=(0xe6 / 255, 0x1a / 255, 0x1a / 255))
			page.insert_text((20, 250), "Contact hors couleur", color=(0x44 / 255, 0xa7 / 255, 0xed / 255))
			page.insert_text((20, 270), "Texte conforme", color=(0x5b / 255, 0xad / 255, 0xf0 / 255))
			calque = doc.add_ocg(C.COUCHE_DECOUPE, on=True)
			page.draw_line((0, 0), (300, 300), color=(1, 0, 0), width=0.25, oc=calque)
			page.insert_text((150, 290), "Repli : ni texte ni logo", color=(0.71, 0.33, 0.04), oc=calque)
			doc.new_page().insert_text((50, 50), "Fiche technique", color=(0, 0, 0))
			return doc.tobytes()

	def test_controle_liste_les_ecarts_et_ignore_la_decoupe(self):
		bilan = A.controle_pdf(self.pdf_de_controle(), [FONCE, CLAIR])
		self.assertFalse(bilan["conforme"])
		self.assertEqual(bilan["pixels"], 0)
		ecarts = {e["couleur"]: e for e in bilan["ecarts"]}
		self.assertEqual(set(ecarts), {"#e61a1a", "#44a7ed"})
		self.assertEqual(ecarts["#44a7ed"]["textes"], ["Contact hors couleur"])
		self.assertEqual(ecarts["#44a7ed"]["proche"], CLAIR)
		self.assertEqual(ecarts["#e61a1a"]["traces"], 1)

	def test_controle_conforme_et_image_en_pixels(self):
		with pymupdf.open() as doc:
			page = doc.new_page(width=200, height=200)
			page.draw_rect((10, 10, 100, 100), color=None, fill=(2 / 255, 100 / 255, 195 / 255))
			propre = doc.tobytes()
			page.insert_image((110, 110, 190, 190), stream=png(Image.new("RGB", (20, 20), FONCE)))
			avec_image = doc.tobytes()
		self.assertTrue(A.controle_pdf(propre, [FONCE])["conforme"])
		bilan = A.controle_pdf(avec_image, [FONCE])
		self.assertEqual(bilan["pixels"], 1)
		self.assertFalse(bilan["conforme"])

	def test_un_qr_au_trait_n_est_pas_un_aplat_noir(self):
		P = pymupdf.Point
		self.assertTrue(A._sans_surface([("l", P(0, 0), P(5, 0)), ("l", P(0, 2), P(5, 2))]))
		self.assertFalse(A._sans_surface([("l", P(0, 0), P(5, 0)), ("l", P(5, 0), P(0, 5)), ("l", P(0, 5), P(0, 0))]))
		self.assertFalse(A._sans_surface([("re", None, None)]))


class TestAligner(unittest.TestCase):
	def design(self, **valeurs):
		return frappe._dict(dict({
			"mise_en_page": json.dumps({"avant": [
				{"zone": "nom", "style": {"texte": "#5badf0"}},
				{"zone": "contact", "style": {"texte": "#44A7ED", "fond": "#fdfdfd"}},
				{"zone": "logo"}]}),
			"fonds_faces": json.dumps({"arriere": {"mode": "couleur", "couleur": "#0b5cab"}, "avant": {"mode": "image", "image": "/files/a.svg"}}),
			"couleur_fond": None, "type_code_barres": "QR", "couleur_qr": "#111111"}, **valeurs))

	def test_les_couleurs_choisies_rejoignent_la_plus_proche(self):
		doc = self.design()
		changements = A.aligner(doc, [FONCE, CLAIR])
		mep = json.loads(doc.mise_en_page)
		self.assertEqual(mep["avant"][0]["style"], {"texte": "#5badf0"})
		self.assertEqual(mep["avant"][1]["style"], {"texte": CLAIR, "fond": "#fdfdfd"})   # presque blanc : toléré
		self.assertEqual(json.loads(doc.fonds_faces)["arriere"]["couleur"], FONCE)
		self.assertEqual(json.loads(doc.fonds_faces)["avant"], {"mode": "image", "image": "/files/a.svg"})
		self.assertEqual(doc.couleur_qr, FONCE)
		self.assertEqual({c["quoi"] for c in changements}, {"avant · contact (texte)", "arriere · fond", "QR"})

	def test_un_qr_ne_prend_pas_une_couleur_trop_claire(self):
		doc = self.design(couleur_qr="#111111")
		A.aligner(doc, ["#cfe8fb"])
		self.assertEqual(doc.couleur_qr, "#111111")
		conforme = self.design(couleur_qr=FONCE)
		self.assertNotIn("QR", {c["quoi"] for c in A.aligner(conforme, [FONCE, CLAIR])})


if __name__ == "__main__":
	unittest.main()
