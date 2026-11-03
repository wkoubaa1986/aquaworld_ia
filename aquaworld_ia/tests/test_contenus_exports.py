import copy
import json
import unittest

import frappe

from aquaworld_ia.emballage import contenus as C, exports as E


class Document(frappe._dict):
	def set(self, key, value):
		self[key] = value


def design(**valeurs):
	return Document(dict(name="TEST", article="ROBINET", nom_produit="Robinet", type_boite="Étui à rabats",
		longueur_mm=140, hauteur_mm=350, profondeur_mm=30, langues=[{"langue": "fr"}],
		caracteristiques="Débit 5 L/min", avertissements="", contact="", variantes=[], pictogrammes=[], **valeurs))


class TestContenus(unittest.TestCase):
	def test_ancien_design_garde_ses_textes_imprimes(self):
		d = design(textes_ia=json.dumps({"fr": {"caracteristiques": ["Version déjà imprimée"]}}))
		self.assertEqual(C.imprimes(d)["fr"]["caracteristiques"], ["Version déjà imprimée"])

	def test_proposition_ia_ne_change_pas_la_version_validee(self):
		d = design()
		C.poser(d, C.imprimes(d))
		d.textes_ia = json.dumps({"fr": {"caracteristiques": ["Proposition différente"]}})
		self.assertEqual(C.imprimes(d)["fr"]["caracteristiques"], ["Débit 5 L/min"])

	def test_saisie_modifie_texte_imprime_y_compris_suppression(self):
		d = design()
		C.poser(d, C.imprimes(d))
		avant = copy.deepcopy(d)
		d.caracteristiques = ""
		d.contact = "Nouveau contact"
		C.synchroniser_saisie(d, avant)
		self.assertEqual(C.imprimes(d)["fr"]["caracteristiques"], [])
		self.assertEqual(C.imprimes(d)["fr"]["contact"], "Nouveau contact")

	def test_langue_ajoutee_ne_recoit_pas_une_fausse_traduction(self):
		d = design()
		C.poser(d, C.imprimes(d))
		d.langues = [{"langue": "en"}, {"langue": "fr"}]
		self.assertEqual(C.imprimes(d)["en"]["caracteristiques"], [])
		self.assertEqual(C.imprimes(d)["fr"]["caracteristiques"], ["Débit 5 L/min"])

	def test_edition_par_langue_met_a_jour_le_miroir_de_la_fiche(self):
		d = design()
		t = C.imprimes(d)
		t["fr"]["caracteristiques"] = ["Texte corrigé"]
		C.poser(d, t)
		self.assertEqual(d.caracteristiques, "Texte corrigé")

	def test_changer_langue_principale_ne_retraduit_pas_le_texte_brut(self):
		d = design()
		avant = copy.deepcopy(d)
		d.langues = [{"langue": "en"}, {"langue": "fr"}]
		C.synchroniser_saisie(d, avant)
		self.assertEqual(d.caracteristiques, "")
		self.assertEqual(C.imprimes(d)["fr"]["caracteristiques"], ["Débit 5 L/min"])

	def test_decocher_puis_recocher_une_langue_preserve_sa_traduction(self):
		d = design()
		C.poser(d, {"fr": {"contact": "FR"}, "en": {"contact": "EN"}})
		C.poser(d, {"fr": {"contact": "FR corrigé"}})
		d.langues = [{"langue": "fr"}, {"langue": "en"}]
		self.assertEqual(C.imprimes(d)["en"]["contact"], "EN")

	def test_mise_en_forme_reportee_sans_remplacer_les_traductions(self):
		d = design()
		d.langues.append({"langue": "en"})
		C.poser(d, {"fr": {"caracteristiques": ["Débit 5 L/min"]}, "en": {"caracteristiques": ["Flow 5 L/min"]}})
		avant = copy.deepcopy(d)
		d.caracteristiques = "{gras} Débit 5 L/min"
		C.synchroniser_saisie(d, avant)
		self.assertEqual(C.imprimes(d)["en"]["caracteristiques"], ["{gras} Flow 5 L/min"])


class TestExports(unittest.TestCase):
	def test_pdf_inconnu_ou_ancien_est_a_regenerer(self):
		d = design()
		self.assertEqual(E.etat(d)["pdf"], "absent")
		d.plan_a_plat = "/private/files/ancien.pdf"
		self.assertEqual(E.etat(d)["pdf"], "a_regenerer")

	def test_edition_de_texte_ou_image_perime_pdf_et_simulation(self):
		for champ, valeur in (("nom_produit", "Autre nom"), ("photo_produit", "/files/nouveau.png"),
		                      ("caracteristiques", "Texte corrigé"), ("longueur_mm", 160)):
			with self.subTest(champ=champ):
				d = design(plan_a_plat="plan.pdf", apercu_3d="vue.png")
				d.empreinte_plan = d.empreinte_3d = E.empreinte(d)
				self.assertEqual(E.etat(d)["pdf"], "a_jour")
				d[champ] = valeur
				self.assertEqual(E.etat(d)["pdf"], "a_regenerer")
				self.assertFalse(E.etat(d)["simulation_a_jour"])

	def test_catalogues_et_nouvelles_propositions_non_adoptees_ne_periment_pas_pdf(self):
		d = design(plan_a_plat="plan.pdf")
		C.poser(d, C.imprimes(d))
		d.empreinte_plan = E.empreinte(d)
		d.textes_ia = '{"fr":{"contact":"Suggestion"}}'
		d.brief_style = "Autre idée"
		d.variantes = [{"numero": 1, "image": "proposition.png"}]
		self.assertEqual(E.etat(d)["pdf"], "a_jour")

	def test_face_de_variante_choisie_compte_dans_empreinte(self):
		d = design(plan_a_plat="plan.pdf")
		d.variantes = [{"numero": 1, "image": "avant.png", "face_gauche": "gauche.png"}]
		d.variante_choisie = 1
		d.empreinte_plan = E.empreinte(d)
		d.variantes[0]["face_gauche"] = "nouvelle.png"
		self.assertEqual(E.etat(d)["pdf"], "a_regenerer")

	def test_aucune_ia_requise_pour_exporter(self):
		self.assertEqual(E.verifier(design()), [])

	def test_revenir_au_contenu_exporte_retablit_le_statut_de_la_fiche(self):
		from aquaworld_ia.aquaworld_ia.doctype.design_emballage.design_emballage import DesignEmballage
		d = design(plan_a_plat="plan.pdf", statut="Plan prêt")
		d.empreinte_plan = E.empreinte(d)
		avant = copy.deepcopy(d)
		d.get_doc_before_save = lambda: avant
		d.contact = "Modification temporaire"
		DesignEmballage.validate(d)
		self.assertEqual(d.statut, "À recomposer")
		avant = copy.deepcopy(d)
		d.contact = ""
		DesignEmballage.validate(d)
		self.assertEqual(d.statut, "Plan prêt")


if __name__ == "__main__":
	unittest.main()
