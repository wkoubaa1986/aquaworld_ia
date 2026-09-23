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
