"""Les formes ajoutées le 23/09/2026 (sacs, étiquette), l'aperçu interactif, les prompts par
famille, le logo photo, les polices personnalisées — tout pur."""
from __future__ import annotations

import io
import unittest

from aquaworld_ia.emballage import composition as C
from aquaworld_ia.emballage import geometrie as G
from aquaworld_ia.emballage import prompts as P
from aquaworld_ia.manuels import rendu as R


def _faces(plan):
	return {f["code"]: f for f in plan["faces"]}


class TestSac(unittest.TestCase):
	def setUp(self):
		self.plan = G.plan_a_plat(G.SAC, 120, 200, 60, patte=15, fond_perdu=3, securite=3)
		self.f = _faces(self.plan)

	def test_famille_et_feuille(self):
		self.assertEqual(self.plan["famille"], "sac")
		self.assertAlmostEqual(self.plan["feuille"]["w"], 6 + 240 + 120 + 15, places=3)
		self.assertAlmostEqual(self.plan["feuille"]["h"], 6 + 24 + 200, places=3)

	def test_quatre_faces_imprimables_et_pas_de_dessus(self):
		for code in ("avant", "arriere", "cote_gauche", "cote_droit"):
			self.assertTrue(self.f[code]["imprimable"], code)
		self.assertNotIn("dessus", self.f)
		self.assertNotIn("dessous", self.f)

	def test_les_soudures_ne_s_impriment_pas_et_sont_des_plis(self):
		soudures = [f for f in self.plan["faces"] if f["code"].startswith("soudure#")]
		self.assertEqual(len(soudures), 10)
		self.assertTrue(all(not f["imprimable"] for f in soudures))
		# l'arête entre la soudure haute et l'avant est partagée : un pli, pas une coupe
		a = self.f["avant"]
		self.assertIn([a["x"], a["y"], a["x"] + a["w"], a["y"]], self.plan["traits"]["pli"])

	def test_pli_median_dans_chaque_soufflet(self):
		c = self.f["cote_droit"]
		xm = round(c["x"] + c["w"] / 2, 3)
		self.assertIn([xm, c["y"], xm, c["y"] + c["h"]], self.plan["traits"]["pli"])

	def test_rien_ne_se_chevauche(self):
		self.assertEqual(G.verifier(self.plan), [])


class TestDoypack(unittest.TestCase):
	def setUp(self):
		self.plan = G.plan_a_plat(G.DOYPACK, 130, 200, 80)
		self.f = _faces(self.plan)

	def test_avant_et_dos_cote_a_cote_fond_sous_l_avant(self):
		self.assertEqual(self.f["avant"]["y"], self.f["arriere"]["y"])
		self.assertAlmostEqual(self.f["arriere"]["x"], self.f["avant"]["x"] + 130, places=3)
		fond = self.f["fond"]
		self.assertFalse(fond["imprimable"])
		self.assertAlmostEqual(fond["y"], self.f["avant"]["y"] + 200, places=3)
		self.assertEqual((fond["w"], fond["h"]), (130, 80))

	def test_feuille_et_pli_du_w(self):
		self.assertAlmostEqual(self.plan["feuille"]["w"], 6 + 260, places=3)
		self.assertAlmostEqual(self.plan["feuille"]["h"], 6 + 12 + 200 + 80, places=3)
		ym = round(self.f["fond"]["y"] + 40, 3)
		self.assertIn([3.0, ym, 133.0, ym], self.plan["traits"]["pli"])

	def test_rien_ne_se_chevauche(self):
		self.assertEqual(G.verifier(self.plan), [])


class TestEtiquette(unittest.TestCase):
	def test_bande_seule_avec_recouvrement(self):
		plan = G.plan_a_plat(G.ETIQUETTE, 90, 120, 60, patte=10)
		f = _faces(plan)
		self.assertEqual(plan["famille"], "etiquette")
		self.assertEqual([x["code"] for x in plan["faces"]], ["avant", "cote_droit", "arriere", "cote_gauche", "patte"])
		self.assertEqual(f["patte"]["libelle"], "Recouvrement")
		self.assertAlmostEqual(plan["feuille"]["h"], 126, places=3)
		self.assertEqual(G.verifier(plan), [])


class TestCatalogueDesTypes(unittest.TestCase):
	def test_cinq_formes_chacune_decrite(self):
		self.assertEqual(len(G.TYPES), 7)   # 5 formes du 23/09 + 2 sacs agrafés du 24/09
		for t in G.TYPES:
			self.assertIn(t, G.FAMILLES)
			self.assertIn(t, G.DESCRIPTIONS)
			self.assertIn(len(G.DIMENSIONS_TYPE[t]), (3, 4))
			ex = G.DIMENSIONS_EXEMPLE[t]
			self.assertEqual(G.verifier(G.plan_a_plat(t, *ex[:3], repli=ex[3] if len(ex) > 3 else 0)), [], t)

	def test_les_anciens_plans_gardent_leur_forme(self):
		plan = G.plan_a_plat(G.ETUI, 120, 200, 60, patte=15, fond_perdu=3, securite=3)
		self.assertEqual(plan["famille"], "boite")
		self.assertAlmostEqual(plan["feuille"]["w"], 381, places=3)


class TestApercuInteractif(unittest.TestCase):
	def test_chaque_face_porte_son_code(self):
		svg = G.apercu_svg(G.plan_a_plat(G.SAC, 120, 200, 60))
		self.assertIn("data-face='avant'", svg)
		self.assertIn("class='aqia-face imprimable'", svg)
		self.assertIn("data-face='soudure#haut_avant'", svg)

	def test_les_zones_sont_des_groupes_masques_par_face(self):
		plan = G.plan_a_plat(G.ETUI, 120, 200, 60)
		zones = {"avant": [{"zone": "logo", "x": 10, "y": 10, "w": 40, "h": 20}]}
		svg = G.apercu_svg(plan, zones=zones)
		self.assertIn("class='aqia-zones' data-face='avant' style='display:none'", svg)
		self.assertIn(">Logo<", svg)

	def test_la_vignette_compacte_n_a_pas_de_texte(self):
		svg = G.apercu_svg(G.plan_a_plat(G.ETUI, 120, 200, 60), 180, compact=True)
		self.assertNotIn("<text", svg)
		self.assertIn("data-face=", svg)


class TestPromptsParFamille(unittest.TestCase):
	def test_la_forme_est_dite(self):
		self.assertIn("flexible pouch", P.prompt_variante({"titre": "x"}, "Sel", famille="sac"))
		self.assertIn("wrap-around label", P.prompt_face_secondaire({"titre": "x"}, "Sel", "arriere", famille="etiquette"))
		self.assertIn("rigid retail box", P.prompt_variante({"titre": "x"}, "Sel"))

	def test_le_mockup_nomme_les_references_reellement_envoyees(self):
		p = P.prompt_mockup("Sel", famille="sac", references=["avant", "cote_droit"])
		self.assertIn("first image = front panel, second image = right side panel", p)
		self.assertNotIn("third", p)
		self.assertIn("standing flexible pouch", p)
		self.assertIn("assembled retail box", P.prompt_mockup("Sel"))


class TestLogoPhoto(unittest.TestCase):
	def _png(self, fond, coin=None):
		from PIL import Image

		im = Image.new("RGB", (20, 20), fond)
		for x in range(6, 14):
			for y in range(6, 14):
				im.putpixel((x, y), (200, 0, 0))
		if coin:
			im.putpixel((0, 0), coin)
		b = io.BytesIO()
		im.save(b, format="PNG")
		return b.getvalue()

	def test_un_fond_blanc_devient_transparent(self):
		from PIL import Image

		out = Image.open(io.BytesIO(C.fond_blanc_en_transparence(self._png((255, 255, 255))))).convert("RGBA")
		self.assertEqual(out.getpixel((0, 0))[3], 0)
		self.assertEqual(out.getpixel((10, 10)), (200, 0, 0, 255))

	def test_un_coin_colore_laisse_le_logo_intact(self):
		octets = self._png((255, 255, 255), coin=(0, 0, 255))
		self.assertEqual(C.fond_blanc_en_transparence(octets), octets)

	def test_un_fond_de_couleur_est_laisse(self):
		octets = self._png((30, 60, 120))
		self.assertEqual(C.fond_blanc_en_transparence(octets), octets)


class TestPolicesPersonnalisees(unittest.TestCase):
	def test_le_nom_de_fichier_est_sur(self):
		self.assertEqual(R.nom_fichier_police("Police titres"), "Police_titres.ttf")
		self.assertEqual(R.nom_fichier_police("Police ar"), "Police_ar.ttf")

	def test_le_css_declare_chaque_police_en_400_et_700(self):
		css = R.css_polices([("Police titres", "/private/files/x.ttf")])
		self.assertIn("font-family:'Noto Sans'", css)
		self.assertEqual(css.count("font-family:'Police titres'"), 2)
		self.assertIn("src:url(Police_titres.ttf)", css)

	def test_la_langue_prend_sa_police_a_elle_d_abord(self):
		self.assertEqual(R.famille({"code": "ar", "rtl": 1, "police_fichier": "/f.ttf"}), "Police ar")
		self.assertEqual(R.famille({"code": "ar", "rtl": 1}), "Noto Naskh Arabic")
		self.assertEqual(C._famille({"code": "fr"}, textes_perso=True), "Police textes")
		self.assertEqual(C._famille({"code": "ar", "rtl": 1}, textes_perso=True), "Noto Naskh Arabic")
		self.assertEqual(C._famille({"code": "fr"}, textes_perso=False), "Noto Sans")

	def test_le_titre_suit_le_reglage(self):
		self.assertEqual(C.famille_titres(True), "Police titres")
		self.assertEqual(C.famille_titres(False), "Noto Sans")


class TestSacAgrafe(unittest.TestCase):
	"""Sac à gueule ouverte fermé par repli agrafé (demande utilisateur 24/09/2026) : L, H, R,
	et S pour la variante à soufflets. Le repli est compris dans H, réservé, sous une ligne de pli."""

	def test_plat_sans_profondeur(self):
		plan = G.plan_a_plat(G.SAC_AGRAFE_PLAT, 250, 400, 0, patte=15, fond_perdu=3, securite=3, repli=60)
		f = _faces(plan)
		self.assertEqual(plan["famille"], "sac_papier")
		self.assertEqual([x["code"] for x in plan["faces"]], ["avant", "arriere", "patte"])
		self.assertAlmostEqual(plan["feuille"]["w"], 6 + 500 + 15, places=3)
		self.assertAlmostEqual(plan["feuille"]["h"], 6 + 400, places=3)
		self.assertEqual((f["avant"]["w"], f["avant"]["h"]), (250, 400))      # H = hauteur totale, repli compris
		self.assertEqual(G.verifier(plan), [])

	def test_repli_reserve_et_ligne_de_pliage(self):
		plan = G.plan_a_plat(G.SAC_AGRAFE_PLAT, 250, 400, 0, patte=15, fond_perdu=3, securite=3, repli=60)
		a = _faces(plan)["avant"]
		# la partie utile et la zone sûre commencent SOUS le repli
		self.assertAlmostEqual(a["utile"]["y"], 3 + 60, places=3)
		self.assertAlmostEqual(a["utile"]["h"], 340, places=3)
		self.assertAlmostEqual(a["zone_sure"]["y"], 3 + 60 + 3, places=3)
		self.assertAlmostEqual(a["zone_sure"]["h"], 340 - 6, places=3)
		# une seule bande réservée sur toute la largeur, haute de R
		self.assertEqual(len(plan["reserves"]), 1)
		rz = plan["reserves"][0]
		self.assertEqual((rz["x"], rz["y"], rz["w"], rz["h"]), (3, 3, 515, 60))
		# la ligne de pliage supérieure traverse la bande à y = R
		self.assertIn([3.0, 63.0, 518.0, 63.0], plan["traits"]["pli"])
		# la maquette automatique ne pose rien dans le repli
		zones = C.maquette_face(a, {"logo": True, "nom": True, "accroche": True, "caracteristiques": True,
		                           "avertissements": True, "contact": True, "pictos": 2, "code_barres": G.EAN_NOMINAL_MM})
		self.assertTrue(zones)
		self.assertTrue(all(z["y"] >= 63 for z in zones), zones)
		# une zone dessinée à la main est repoussée sous le repli
		b = C.borner_zone({"zone": "logo", "x": 10, "y": 10, "w": 50, "h": 20}, a)
		self.assertAlmostEqual(b["y"], 63, places=3)

	def test_soufflets(self):
		plan = G.plan_a_plat(G.SAC_AGRAFE_SOUFFLETS, 250, 400, 80, patte=15, repli=60)
		f = _faces(plan)
		self.assertEqual([x["code"] for x in plan["faces"]], ["avant", "cote_droit", "arriere", "cote_gauche", "patte"])
		self.assertEqual((f["cote_droit"]["w"], f["cote_droit"]["h"]), (80, 400))
		xm = round(f["cote_gauche"]["x"] + 40, 3)
		self.assertIn([xm, 63.0, xm, 403.0], plan["traits"]["pli"])       # pli médian, sous le repli
		self.assertEqual(G.bande(plan)["faces"], ["avant", "cote_droit", "arriere", "cote_gauche"])
		self.assertEqual(G.verifier(plan), [])

	def test_dimensions_manquantes(self):
		self.assertEqual(G.dimensions_manquantes(G.SAC_AGRAFE_PLAT, 250, 400, 0, 60), [])
		self.assertEqual(G.dimensions_manquantes(G.SAC_AGRAFE_PLAT, 250, 400, 0, 0),
		                 ["Hauteur du repli supérieur (R), comprise dans H"])
		self.assertEqual(G.dimensions_manquantes(G.SAC_AGRAFE_SOUFFLETS, 250, 400, 0, 60),
		                 ["Profondeur du soufflet entièrement déployé (S)"])
		self.assertEqual(len(G.dimensions_manquantes(G.SAC_AGRAFE_PLAT, 250, 400, 0, 400)), 1)   # R ≥ H
		self.assertEqual(G.dimensions_manquantes(G.ETUI, 120, 200, 0), ["Profondeur (largeur des côtés)"])
		self.assertEqual(G.dimensions_manquantes(G.ETUI, 120, 200, 60, 0), [])
		with self.assertRaises(ValueError):
			G.plan_a_plat(G.SAC_AGRAFE_PLAT, 250, 400, 0, repli=0)
		with self.assertRaises(ValueError):
			G.plan_a_plat(G.SAC_AGRAFE_PLAT, 250, 400, 0, repli=400)

	def test_hachures_rognees_au_rectangle(self):
		segs = G.hachures(10, 20, 100, 30, pas=10)
		self.assertTrue(segs)
		for x1, y1, x2, y2 in segs:
			self.assertTrue(10 - 1e-6 <= x1 <= 110 + 1e-6 and 10 - 1e-6 <= x2 <= 110 + 1e-6, (x1, x2))
			self.assertTrue(20 - 1e-6 <= y1 <= 50 + 1e-6 and 20 - 1e-6 <= y2 <= 50 + 1e-6, (y1, y2))
			self.assertAlmostEqual(x2 - x1, y2 - y1, places=3)                     # 45°
		self.assertEqual(G.hachures(0, 0, 0, 10), [])

	def test_apercu_svg_montre_le_repli(self):
		plan = G.plan_a_plat(G.SAC_AGRAFE_PLAT, 250, 400, 0, repli=60)
		svg = G.apercu_svg(plan)
		self.assertIn("Repli supérieur et agrafes — ni texte ni logo", svg)
		self.assertIn("#b45309", svg)
		self.assertNotIn("<pattern", svg)
		self.assertNotIn("ni texte ni logo", G.apercu_svg(plan, 180, compact=True))       # vignette : hachures seules

	def test_toutes_les_formes_ont_un_exemple_valide(self):
		for t in G.TYPES:
			ex = G.DIMENSIONS_EXEMPLE[t]
			plan = G.plan_a_plat(t, *ex[:3], repli=ex[3] if len(ex) > 3 else 0)
			self.assertEqual(G.verifier(plan), [], t)
			self.assertEqual("R" in G.DIMENSIONS_REQUISES[t], len(G.DIMENSIONS_TYPE[t]) > 3, t)

	def test_prompts_sac_papier(self):
		self.assertIn("stapled", P.prompt_variante({"titre": "x"}, "Riz", famille="sac_papier"))
		self.assertIn("staples", P.prompt_mockup("Riz", famille="sac_papier", references=["avant"]))
