"""Logo d'une seule couleur en SVG / PNG, et photo produit automatique visible sur le plan (demande
utilisateur 06/10/2026). Sans base : images fabriquées en mémoire."""
from __future__ import annotations

import io
import re
import unittest

from aquaworld_ia.emballage import geometrie as G
from aquaworld_ia.emballage import logo_couleur as LC

SVG_ECO = (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 40"><style>.a{fill:#008BCD;}</style>'
           b'<path class="a" d="M0 0h10v10z"/><path fill="#486683" d="M20 0h10v10z"/>'
           b'<path style="fill:#507F53;stroke:#507f53" d="M40 0h10v10z"/><path fill="#ffffff" d="M60 0h10v10z"/>'
           b'<path fill="none" stroke="#000" d="M70 0h10"/><path d="M80 0h10v10z"/>'
           b'<linearGradient id="g"><stop stop-color="#ff0000"/></linearGradient><path fill="url(#g)" d="M90 0h5v5z"/></svg>')


def _png_logo():
	"""Un « O » bleu sur fond blanc, avec un point blanc au centre de la pastille droite."""
	import cv2
	import numpy as np

	img = np.full((200, 400, 3), 255, np.uint8)
	cv2.circle(img, (100, 100), 70, (205, 139, 0), 25)          # anneau bleu (BGR)
	cv2.circle(img, (300, 100), 70, (83, 127, 80), -1)          # pastille verte pleine
	cv2.circle(img, (300, 100), 25, (255, 255, 255), -1)        # évidement blanc
	ok, png = cv2.imencode(".png", img)
	return png.tobytes()


def _png_transparent():
	"""Le même logo, mais déjà détouré (fond transparent) : son évidement blanc est voulu, opaque."""
	import cv2
	import numpy as np

	bgr = cv2.imdecode(np.frombuffer(_png_logo(), np.uint8), cv2.IMREAD_COLOR)
	alpha = np.where(bgr.min(axis=2) < 250, 255, 0).astype(np.uint8)
	cv2.circle(alpha, (300, 100), 25, 255, -1)                 # l'évidement blanc fait partie du logo
	ok, png = cv2.imencode(".png", np.dstack([bgr, alpha]))
	return png.tobytes()


def _pixels(png):
	import numpy as np
	from PIL import Image

	return np.array(Image.open(io.BytesIO(png)).convert("RGBA"))


class TestNormaliser(unittest.TestCase):

	def test_formes_acceptees(self):
		self.assertEqual(LC.normaliser("#1D4ED8"), "#1d4ed8")
		self.assertEqual(LC.normaliser("1d4ed8"), "#1d4ed8")
		self.assertEqual(LC.normaliser("#fff"), "#ffffff")
		self.assertIsNone(LC.normaliser("bleu"))
		self.assertIsNone(LC.normaliser(None))


class TestRecolorerSvg(unittest.TestCase):

	def test_toutes_les_encres_prennent_la_couleur(self):
		svg = LC.recolorer_svg(SVG_ECO, "#c0392b", garder_blanc=True).decode()
		encres = {c.lower() for c in re.findall(r"#[0-9a-fA-F]{3,6}\b", svg)}
		self.assertEqual(encres - {"#ffffff", "#g"}, {"#c0392b"})
		self.assertIn('fill="#ffffff"', svg)                    # le blanc est gardé
		self.assertIn('fill="none"', svg)                       # none reste none
		self.assertIn('fill="url(#g)"', svg)                    # le dégradé garde son appel, ses arrêts changent
		self.assertIn('stop-color="#c0392b"', svg)
		self.assertRegex(svg, r'<svg[^>]*fill="#c0392b"')       # une forme sans remplissage n'est plus noire

	def test_sans_garder_le_blanc(self):
		svg = LC.recolorer_svg(SVG_ECO, "#c0392b", garder_blanc=False).decode()
		self.assertNotIn("#ffffff", svg)

	def test_couleurs_du_logo_vectoriel(self):
		self.assertEqual(set(LC.couleurs_logo(SVG_ECO)), {"#008bcd", "#486683", "#507f53", "#000000", "#ff0000"})
		self.assertTrue(LC.svg_vectoriel(SVG_ECO))
		self.assertFalse(LC.svg_vectoriel(b'<svg xmlns="http://www.w3.org/2000/svg"><image href="x.png"/></svg>'))

	def test_appliquer_un_svg_vectoriel_reste_vectoriel(self):
		octets, ext = LC.appliquer(SVG_ECO, "C0392B", True, "svg")
		self.assertEqual(ext, "svg")
		self.assertEqual(octets.count(b"<path"), SVG_ECO.count(b"<path"))   # aucune courbe retracée

	def test_couleur_invalide(self):
		with self.assertRaises(ValueError):
			LC.appliquer(SVG_ECO, "pas une couleur")


class TestRecolorerImage(unittest.TestCase):

	def test_png_une_couleur_fond_transparent(self):
		a = _pixels(LC.recolorer_png(_png_logo(), "#c0392b", garder_blanc=True))
		self.assertEqual(a[5, 5, 3], 0)                                   # le fond blanc est devenu transparent
		self.assertEqual(tuple(a[100, 30, :3]), (0xc0, 0x39, 0x2b))      # l'anneau bleu
		self.assertEqual(tuple(a[100, 250, :3]), (0xc0, 0x39, 0x2b))     # la pastille verte
		# Image SANS transparence : le blanc pur enfermé devient un trou, comme à l'impression du logo
		# (même détourage que `fond_blanc_en_transparence`, pensé pour l'intérieur des lettres).
		self.assertEqual(a[100, 300, 3], 0)

	def test_blanc_garde_sur_un_logo_deja_detoure(self):
		a = _pixels(LC.recolorer_png(_png_transparent(), "#c0392b", garder_blanc=True))
		self.assertEqual(tuple(a[100, 300, :4]), (255, 255, 255, 255))   # l'évidement blanc voulu reste blanc
		self.assertEqual(tuple(a[100, 250, :3]), (0xc0, 0x39, 0x2b))
		b = _pixels(LC.recolorer_png(_png_transparent(), "#c0392b", garder_blanc=False))
		self.assertEqual(tuple(b[100, 300, :3]), (0xc0, 0x39, 0x2b))     # sans « garder le blanc », tout prend la couleur

	def test_vectoriser_garde_les_trous_et_la_couleur(self):
		import pymupdf

		svg = LC.vectoriser(LC.recolorer_png(_png_logo(), "#c0392b"), "#c0392b", garder_blanc=False)
		self.assertTrue(svg.startswith(b"<svg"))
		self.assertEqual({c.decode() for c in re.findall(rb'fill="([^"]+)"', svg)}, {"#c0392b"})
		pix = pymupdf.open(stream=svg, filetype="svg")[0].get_pixmap(alpha=True)
		k = pix.w / 400
		centre_anneau = pix.pixel(int(100 * k), int(100 * k))
		anneau = pix.pixel(int(30 * k), int(100 * k))
		self.assertEqual(centre_anneau[3], 0)                             # le trou du « O » est resté un trou
		self.assertEqual(anneau[:3], (0xc0, 0x39, 0x2b))

	def test_appliquer_une_image_en_svg_et_en_png(self):
		svg, ext = LC.appliquer(_png_transparent(), "#1d4ed8", True, "svg")
		self.assertEqual(ext, "svg")
		self.assertIn(b'fill="#ffffff"', svg)                            # la couche blanche gardée
		png, ext = LC.appliquer(_png_logo(), "#1d4ed8", True, "png")
		self.assertEqual((ext, png[:4]), ("png", b"\x89PNG"))

	def test_couleurs_d_une_image(self):
		couleurs = LC.couleurs_logo(_png_logo())
		self.assertTrue(couleurs)
		self.assertNotIn("#ffffff", couleurs)


class TestPalette(unittest.TestCase):

	def test_dedoublonnee_dans_l_ordre(self):
		p = LC.palette([("#008BCD", "logo"), ("#008bcd", "fond"), ("bidon", "zones"), ("#000", "noir")])
		self.assertEqual(p, [{"couleur": "#008bcd", "origine": "logo"}, {"couleur": "#000000", "origine": "noir"}])


class TestPhotoAutomatique(unittest.TestCase):

	def plan(self):
		return G.plan_a_plat(G.ETUI, 140, 335, 140, patte=15, fond_perdu=3, securite=3)

	def test_la_photo_posee_d_office_se_voit_sur_le_plan(self):
		from aquaworld_ia.emballage.composition import hero_photo_rect
		from aquaworld_ia.emballage.job import avec_photo_automatique

		plan = self.plan()
		zones = avec_photo_automatique(plan, {"avant": [], "arriere": []})
		auto = [z for z in zones["avant"] if z.get("auto")]
		self.assertEqual(len(auto), 1)
		x, y, w, h = hero_photo_rect(G.face(plan, "avant"))
		self.assertEqual((auto[0]["zone"], auto[0]["x"], auto[0]["w"]), ("photo", round(x, 3), round(w, 3)))
		self.assertEqual(zones["arriere"], [])
		self.assertEqual(G.libelle_zone(auto[0]), "Photo produit (automatique)")

	def test_une_zone_photo_dessinee_remplace_l_automatique(self):
		from aquaworld_ia.emballage.job import avec_photo_automatique

		zones = {"avant": [], "cote_droit": [{"zone": "photo", "x": 0, "y": 0, "w": 10, "h": 10}]}
		self.assertEqual(avec_photo_automatique(self.plan(), zones), zones)

	def test_genre_des_fichiers_recolores(self):
		from aquaworld_ia.emballage.studio import genre_image

		self.assertEqual(genre_image("EMB-2026-0006-logo-couleur-c0392b.svg", "EMB-2026-0006"), "Logo couleur")
		self.assertEqual(genre_image("EMB-2026-0006-logo-ia.png", "EMB-2026-0006"), "Logo IA")


if __name__ == "__main__":
	unittest.main()


class TestFondreBords(unittest.TestCase):
	"""06/10/2026 : la photo (éclaboussure coupée par son cadre) se fond dans le fond de l'emballage."""

	def _png(self, bords_opaques: bool):
		import numpy as np
		from PIL import Image

		a = np.zeros((100, 100, 4), np.uint8)
		a[..., 2] = 200
		if bords_opaques:
			a[..., 3] = 255
		else:
			a[20:80, 20:80, 3] = 255
		b = io.BytesIO()
		Image.fromarray(a, "RGBA").save(b, "PNG")
		return b.getvalue()

	def test_bords_opaques_effaces_centre_intact(self):
		from aquaworld_ia.emballage.composition import fondre_bords

		a = _pixels(fondre_bords(self._png(True)))
		self.assertEqual(a[0, 50, 3], 0)                 # bord : transparent
		self.assertEqual(a[50, 0, 3], 0)
		self.assertEqual(a[50, 50, 3], 255)              # centre : intact
		self.assertTrue(0 < a[50, 6, 3] < 255)           # fondu progressif

	def test_photo_deja_detouree_inchangee(self):
		from aquaworld_ia.emballage.composition import fondre_bords

		png = self._png(False)
		self.assertEqual(fondre_bords(png), png)


class TestBlancPur(unittest.TestCase):
	"""06/10/2026 : « la génération n'est pas vraiment blanche » (#FDFDFD à côté des faces en blanc pur)."""

	def _png(self, couleurs, mode="RGB"):
		import numpy as np
		from PIL import Image

		a = np.array([[c for c in couleurs]], np.uint8)
		b = io.BytesIO()
		Image.fromarray(a, mode).save(b, "PNG")
		return b.getvalue()

	def test_presque_blanc_devient_blanc_couleurs_intactes(self):
		from aquaworld_ia.emballage.composition import blanc_pur

		a = _pixels(blanc_pur(self._png([(253, 253, 253), (250, 251, 252), (68, 167, 237), (228, 238, 250)])))
		self.assertEqual(tuple(a[0, 0, :3]), (255, 255, 255))
		self.assertEqual(tuple(a[0, 1, :3]), (255, 255, 255))
		self.assertEqual(tuple(a[0, 2, :3]), (68, 167, 237))           # le bleu des vagues ne bouge pas
		self.assertEqual(tuple(a[0, 3, :3]), (228, 238, 250))          # un bleu très pâle non plus (min < 232)

	def test_transparence_gardee(self):
		from aquaworld_ia.emballage.composition import blanc_pur

		a = _pixels(blanc_pur(self._png([(252, 252, 252, 120), (10, 20, 30, 255)], "RGBA")))
		self.assertEqual(tuple(a[0, 0]), (255, 255, 255, 120))
		self.assertEqual(tuple(a[0, 1]), (10, 20, 30, 255))
