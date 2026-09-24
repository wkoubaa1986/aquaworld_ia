"""Fond choisi, photo héros sans IA, dos miroir de l'avant, pictos à soi (23/09/2026) — pur."""
from __future__ import annotations

import inspect
import unittest

from aquaworld_ia.emballage import composition as C
from aquaworld_ia.emballage import geometrie as G
from aquaworld_ia.emballage import studio as S

PLAN = G.plan_a_plat(G.ETUI, 120, 200, 60)
CONTENU = {"logo": True, "nom": True, "accroche": True, "caracteristiques": True, "avertissements": True,
           "contact": True, "pictos": 3, "code_barres": G.EAN_NOMINAL_MM}


def _noms(zones):
	return sorted(z["zone"] for z in zones)


class TestDosMiroir(unittest.TestCase):
	def test_sans_miroir_le_dos_garde_sa_maquette(self):
		z = C.zones_par_face(PLAN, CONTENU, faces_identiques=False)
		self.assertIn("code_barres", _noms(z["arriere"]))
		self.assertNotIn("code_barres", _noms(z["cote_droit"]))

	def test_avec_miroir_le_dos_prend_la_maquette_de_l_avant(self):
		z = C.zones_par_face(PLAN, CONTENU, faces_identiques=True)
		self.assertEqual(_noms(z["arriere"]), _noms(z["avant"]))
		self.assertNotIn("code_barres", _noms(z["arriere"]))

	def test_l_ean_et_les_avertissements_demenagent_sur_le_cote_droit(self):
		z = C.zones_par_face(PLAN, CONTENU, faces_identiques=True)
		self.assertIn("code_barres", _noms(z["cote_droit"]))
		self.assertIn("avertissements", _noms(z["cote_droit"]))
		self.assertNotIn("code_barres", _noms(z["cote_gauche"]))
		cd = G.face(PLAN, "cote_droit")["zone_sure"]
		for zone in z["cote_droit"]:
			self.assertLessEqual(zone["x"] + zone["w"], cd["x"] + cd["w"] + 0.01, zone)
			self.assertLessEqual(zone["y"] + zone["h"], cd["y"] + cd["h"] + 0.01, zone)

	def test_sans_cote_le_dos_reste_un_dos(self):
		"""Sachet doypack : pas de côté, l'EAN n'aurait nulle part où aller."""
		plan = G.plan_a_plat(G.DOYPACK, 130, 200, 80)
		z = C.zones_par_face(plan, CONTENU, faces_identiques=True)
		self.assertIn("code_barres", _noms(z["arriere"]))


class TestFondEtPhotoHero(unittest.TestCase):
	def test_la_photo_hero_reste_entre_logo_et_nom(self):
		avant = G.face(PLAN, "avant")
		x, y, w, h = C.hero_photo_rect(avant)
		zones = {z["zone"]: z for z in C.maquette_face(avant, CONTENU)}
		self.assertGreaterEqual(y, zones["logo"]["y"] + zones["logo"]["h"] - 0.01)
		self.assertLessEqual(y + h, zones["accroche"]["y"] + 0.01)
		self.assertGreater(w, 0)

	def test_la_couleur_choisie_prime_sur_la_dominante(self):
		src = inspect.getsource(C.composer)
		self.assertIn('doc.get("couleur_fond") or dominantes[0]', src)
		self.assertIn("recadrer(image_fond", src)
		self.assertIn('visuels["arriere"] = visuel_avant', src)

	def test_on_compose_sans_variante_si_un_fond_est_choisi(self):
		src = inspect.getsource(C.composer_et_attacher)
		self.assertIn('doc.get("couleur_fond") or doc.get("image_fond")', src)
		self.assertIn("v = None", src)


class TestPictosDuStudio(unittest.TestCase):
	def test_la_vignette_vient_de_l_image_sinon_de_l_asset(self):
		self.assertEqual(S.url_pictogramme({"image": "/private/files/iso.png", "fichier": "ce.svg"}), "/private/files/iso.png")
		self.assertEqual(S.url_pictogramme({"image": None, "fichier": "ce.svg"}), "/assets/aquaworld_ia/pictos/ce.svg")
		self.assertIsNone(S.url_pictogramme({"image": None, "fichier": None}))

	def test_les_nouveaux_champs_sont_editables(self):
		for champ in ("couleur_fond", "image_fond", "faces_identiques"):
			self.assertIn(champ, S.CHAMPS_EDITABLES)


class TestMiseEnPagePersonnalisee(unittest.TestCase):
	"""Déplacer, agrandir, supprimer, ajouter des zones — sans jamais sortir de la face."""

	def test_une_face_absente_garde_sa_maquette(self):
		auto = C.zones_par_face(PLAN, CONTENU)
		perso = C.zones_par_face(PLAN, CONTENU, mise_en_page={"arriere": [{"zone": "logo", "x": 200, "y": 100, "w": 30, "h": 10}]})
		self.assertEqual(perso["avant"], auto["avant"])
		self.assertEqual([z["zone"] for z in perso["arriere"]], ["logo"])

	def test_une_zone_ajoutee_hors_face_est_ramenee_dedans(self):
		f = G.face(PLAN, "avant")
		z = C.borner_zone({"zone": "photo", "x": -500, "y": -500, "w": 9999, "h": 9999}, f)
		self.assertEqual((z["x"], z["y"], z["w"], z["h"]), (f["x"], f["y"], f["w"], f["h"]))
		z = C.borner_zone({"zone": "nom", "x": f["x"] + f["w"] - 5, "y": f["y"], "w": 40, "h": 10}, f)
		self.assertAlmostEqual(z["x"] + z["w"], f["x"] + f["w"], places=3)

	def test_une_zone_inconnue_est_ignoree_et_une_supprimee_disparait(self):
		perso = C.zones_par_face(PLAN, CONTENU, mise_en_page={"avant": [{"zone": "n_importe_quoi", "x": 1, "y": 1, "w": 5, "h": 5}]})
		self.assertEqual(perso["avant"], [])

	def test_la_photo_est_une_zone_ajoutable(self):
		self.assertIn("photo", C.ZONES_AJOUTABLES)
		self.assertIn("photo", G.ZONES_LIBELLES)


class TestCotesIdentiques(unittest.TestCase):
	"""Demande utilisateur 24/09/2026 : côté gauche = côté droit, avant = arrière. Le côté gauche
	copie le côté droit ; avec le dos miroir, l'EAN et les avertissements sont sur les DEUX côtés."""

	def _relatives(self, zones, face):
		return [(z["zone"], round(z["x"] - face["x"], 2), round(z["y"] - face["y"], 2), z["w"], z["h"]) for z in zones]

	def test_le_cote_gauche_copie_le_cote_droit(self):
		z = C.zones_par_face(PLAN, CONTENU, faces_identiques=True, cotes_identiques=True)
		self.assertEqual(self._relatives(z["cote_gauche"], G.face(PLAN, "cote_gauche")),
		                 self._relatives(z["cote_droit"], G.face(PLAN, "cote_droit")))
		self.assertIn("code_barres", _noms(z["cote_gauche"]))
		self.assertIn("avertissements", _noms(z["cote_gauche"]))
		self.assertNotIn("code_barres", _noms(z["arriere"]))
		cg = G.face(PLAN, "cote_gauche")
		for zone in z["cote_gauche"]:
			self.assertGreaterEqual(zone["x"], cg["x"] - 0.01)
			self.assertLessEqual(zone["x"] + zone["w"], cg["x"] + cg["w"] + 0.01, zone)

	def test_sans_miroir_les_cotes_sont_deja_pareils_et_sans_ean(self):
		z = C.zones_par_face(PLAN, CONTENU, faces_identiques=False, cotes_identiques=True)
		self.assertEqual(_noms(z["cote_gauche"]), _noms(z["cote_droit"]))
		self.assertNotIn("code_barres", _noms(z["cote_gauche"]))
		self.assertIn("code_barres", _noms(z["arriere"]))

	def test_la_mise_en_page_dessinee_sur_la_source_est_recopiee(self):
		cd, av = G.face(PLAN, "cote_droit"), G.face(PLAN, "avant")
		mep = {"cote_droit": [{"zone": "logo", "x": cd["x"] + 5, "y": cd["y"] + 100, "w": 30, "h": 20}],
		       "avant": [{"zone": "nom", "x": av["x"] + 10, "y": av["y"] + 150, "w": 80, "h": 25}]}
		z = C.zones_par_face(PLAN, CONTENU, faces_identiques=True, cotes_identiques=True, mise_en_page=mep)
		self.assertEqual(self._relatives(z["cote_gauche"], G.face(PLAN, "cote_gauche")), [("logo", 5.0, 100.0, 30.0, 20.0)])
		self.assertEqual(self._relatives(z["arriere"], G.face(PLAN, "arriere")), [("nom", 10.0, 150.0, 80.0, 25.0)])

	def test_une_face_copiee_dessinee_a_la_main_devient_independante(self):
		cg = G.face(PLAN, "cote_gauche")
		mep = {"cote_gauche": [{"zone": "pictos", "x": cg["x"] + 2, "y": cg["y"] + 2, "w": 20, "h": 10}]}
		z = C.zones_par_face(PLAN, CONTENU, faces_identiques=True, cotes_identiques=True, mise_en_page=mep)
		self.assertEqual(_noms(z["cote_gauche"]), ["pictos"])
		self.assertEqual(C.faces_copiees(PLAN, True, True, mep), {"arriere": "avant"})
		self.assertEqual(C.faces_copiees(PLAN, True, True), {"arriere": "avant", "cote_gauche": "cote_droit"})

	def test_sans_cotes_rien_a_copier(self):
		plan = G.plan_a_plat(G.DOYPACK, 130, 200, 80)
		self.assertEqual(C.faces_copiees(plan, True, True), {})
		z = C.zones_par_face(plan, CONTENU, faces_identiques=True, cotes_identiques=True)
		self.assertIn("code_barres", _noms(z["arriere"]))


class TestPictosSansCartouche(unittest.TestCase):
	"""Demande utilisateur 24/09/2026 : pictogrammes posés en transparence, recolorés s'ils sont
	monochromes ; une certification en couleurs n'est pas touchée."""
	NOIR = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><path d="M0 0h10v10z" fill="#000"/><circle r="3" fill="none" stroke="black"/><rect fill="#fff" width="2" height="2"/></svg>'
	SANS_FILL = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><path d="M0 0h10v10z"/></svg>'
	COULEURS = b'<svg xmlns="http://www.w3.org/2000/svg"><rect fill="#e11d48"/><rect fill="#2563eb"/><text style="fill:#000">CE</text></svg>'

	def test_monochrome_recolore_en_gardant_blanc_et_none(self):
		out = C.recolorer_svg_monochrome(self.NOIR, "#ffffff").decode()
		self.assertNotIn("#000", out)
		self.assertNotIn('stroke="black"', out)
		self.assertIn('fill="#ffffff"', out)
		self.assertIn('stroke="#ffffff"', out)
		self.assertIn('fill="none"', out)
		self.assertIn('fill="#fff"', out)

	def test_sans_fill_explicite_la_couleur_est_posee_a_la_racine(self):
		out = C.recolorer_svg_monochrome(self.SANS_FILL, "#123456").decode()
		self.assertRegex(out, r'<svg[^>]*fill="#123456"')

	def test_une_certification_en_couleurs_reste_intacte(self):
		self.assertFalse(C.svg_est_monochrome(self.COULEURS))
		self.assertEqual(C.recolorer_svg_monochrome(self.COULEURS, "#ffffff"), self.COULEURS)

	def test_les_pictos_livres_sont_monochromes(self):
		import glob, os
		dossier = os.path.join(os.path.dirname(C.__file__), "..", "public", "pictos")
		fichiers = glob.glob(os.path.join(dossier, "*.svg"))
		self.assertTrue(fichiers)
		for f in fichiers:
			with open(f, "rb") as fh:
				svg = fh.read()
			self.assertTrue(C.svg_est_monochrome(svg), f)
			self.assertNotIn(b"#000", C.recolorer_svg_monochrome(svg, "#ffffff"), f)

	def test_est_svg(self):
		self.assertTrue(C.est_svg(self.NOIR))
		self.assertTrue(C.est_svg(self.SANS_FILL))
		self.assertFalse(C.est_svg(b"\x89PNG\r\n"))
		self.assertIn("pictos_sans_cartouche", __import__("aquaworld_ia.emballage.studio", fromlist=["x"]).CHAMPS_EDITABLES)


class TestFondDesFacesCopiees(unittest.TestCase):
	def test_la_copie_prend_le_fond_de_sa_source(self):
		copies = C.faces_copiees(PLAN, True, True)
		self.assertEqual(C.face_source(PLAN, "cote_gauche", copies)["code"], "cote_droit")
		self.assertEqual(C.face_source(PLAN, "arriere", copies)["code"], "avant")
		self.assertEqual(C.face_source(PLAN, "avant", copies)["code"], "avant")
		self.assertEqual(C.face_source(PLAN, "dessus", {})["code"], "dessus")


class TestStyleDeZone(unittest.TestCase):
	"""Cartouche par zone (demande utilisateur 24/09/2026) et variante de logo par face."""

	def test_style_normalise(self):
		self.assertIsNone(C.style_zone({"zone": "nom"}))
		self.assertIsNone(C.style_zone({"zone": "nom", "style": {"fond": "bleu", "texte": "rgb(1,2,3)"}}))
		self.assertEqual(C.style_zone({"zone": "nom", "style": {"fond": "#1d4ed8", "texte": "#ffffff", "rayon": "4"}}),
		                 {"fond": "#1d4ed8", "texte": "#ffffff", "rayon": 4.0})
		self.assertEqual(C.style_zone({"zone": "nom", "style": {"texte": "#ffffff", "rayon": -3}}), {"fond": None, "texte": "#ffffff", "rayon": 0.0})

	def test_borner_et_translater_gardent_style_et_logo(self):
		av, ar = G.face(PLAN, "avant"), G.face(PLAN, "arriere")
		z = {"zone": "logo", "x": av["x"] + 5, "y": av["y"] + 5, "w": 30, "h": 12, "logo": "/private/files/blanc.png",
		     "style": {"fond": "#1d4ed8"}}
		b = C.borner_zone(z, av)
		self.assertEqual(b["logo"], "/private/files/blanc.png")
		self.assertEqual(b["style"], {"fond": "#1d4ed8"})
		t = C.translater_zones([b], av, ar)[0]
		self.assertEqual(t["logo"], "/private/files/blanc.png")
		self.assertAlmostEqual(t["x"], ar["x"] + 5, places=3)
		self.assertNotIn("style", C.borner_zone({"zone": "nom", "x": 0, "y": 0, "w": 10, "h": 5}, av))
		p = C.borner_zone({"zone": "pictos", "x": av["x"], "y": av["y"], "w": 40, "h": 12, "pictos": ["nsf"]}, av)
		self.assertEqual(p["pictos"], ["nsf"])

	def test_apercu_svg_teinte_la_zone_stylee(self):
		svg = G.apercu_svg(PLAN, zones={"avant": [{"zone": "nom", "x": 80, "y": 250, "w": 100, "h": 20, "style": {"fond": "#1d4ed8", "rayon": 4}}]})
		self.assertIn("fill='#1d4ed8' fill-opacity='0.6'", svg)
		self.assertIn("rx='4.00'", svg)


class TestTextesBruts(unittest.TestCase):
	"""Sans textes préparés par l'IA, le texte brut de l'étape 2 s'imprime (24/09/2026)."""

	def test_lignes_brutes_titres_et_vides(self):
		self.assertEqual(C.lignes_brutes("SPECIFICATIONS\n\nHousing: Blue\nInlet / outlet port size:\n  1/2\u2033  \n"),
		                 ["## SPECIFICATIONS", "Housing: Blue", "## Inlet / outlet port size", "1/2\u2033"])
		self.assertEqual(C.lignes_brutes(None), [])
		self.assertEqual(C.lignes_brutes("CE"), ["CE"])     # 2 lettres : pas un titre

	def test_textes_bruts_langue_et_vide(self):
		t = C.textes_bruts("Débit 5 l/min\nGarantie 2 ans", None, "AquaWorld", "en")
		self.assertEqual(list(t), ["en"])
		self.assertEqual(t["en"]["caracteristiques"], ["Débit 5 l/min", "Garantie 2 ans"])
		self.assertEqual(t["en"]["contact"], "AquaWorld")
		self.assertEqual(C.textes_bruts("", "\n", " ", "fr"), {})

	def test_html_bloc_intertitre_sans_puce(self):
		html_ = C.html_bloc(["## SPECS", "Housing: Blue"], taille_pt=8, rtl=False, famille="Noto Sans", puces=True)
		self.assertIn("font-weight:700", html_)
		self.assertIn(">SPECS</p>", html_)
		self.assertIn("• Housing: Blue", html_)
