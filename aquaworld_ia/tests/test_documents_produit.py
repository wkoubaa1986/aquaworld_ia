"""Documents produit : périmètres des variantes, versions durables, traductions, LaTeX et permissions."""

import copy
import io
import json
import shutil
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from aquaworld_ia.documents_produit import (
	contexte as C,
)
from aquaworld_ia.documents_produit import (
	entetes as E,
)
from aquaworld_ia.documents_produit import (
	latex as L,
)
from aquaworld_ia.documents_produit import (
	service as API,
)
from aquaworld_ia.documents_produit import (
	structure as S,
)
from aquaworld_ia.documents_produit import (
	traitement as T,
)


def contexte_simple():
	return {
		"article": {"name": "TEST-P", "item_name": "Osmoseur compact", "brand": "ecoPurium", "attributs": []},
		"variantes": [
			{
				"name": "TEST-P-V",
				"item_name": "Osmoseur avec membrane Vontron",
				"brand": "ecoPurium",
				"attributs": [{"nom": "Marque de membrane", "valeur": "Vontron"}],
			}
		],
		"images": [],
		"sources": [],
		"consignes": "",
		"logo": "",
	}


def contenu_simple(ctx=None):
	ctx = ctx or contexte_simple()
	return S.normaliser(
		{
			"titre": "Fiche technique — Osmoseur",
			"resume": "Un produit ecoPurium.",
			"sections": [
				{
					"titre": "Utilisation",
					"texte": "Le modèle TEST-P-V utilise une membrane Vontron.",
					"article": "",
					"source": "Article TEST-P",
				}
			],
			"caracteristiques": [
				{"nom": "Pression", "valeur": "3", "unite": "bar", "article": "", "source": "S1 p.2"}
			],
			"points_a_verifier": [],
		},
		ctx,
	)


class TestStructureDocuments(unittest.TestCase):
	def test_entete_html_sans_script_ni_ressource_distante(self):
		html = E.nettoyer_html('<script>alert(1)</script><style>@import "https://example.org";</style><p onclick="x()" style="color:#125678;background-image:url(https://example.org)">Aqua &amp; World</p>', {})
		self.assertNotIn("script", html)
		self.assertNotIn("onclick", html)
		self.assertNotIn("url(", html)
		self.assertIn("color:#125678", html)
		with self.assertRaises(ValueError):
			E.nettoyer_html('<img src="https://example.org/a.png">', {})
		with self.assertRaises(ValueError):
			E.nettoyer_html('<img src="file:///etc/passwd">', {})

	@unittest.skipUnless(shutil.which("xelatex"), "XeLaTeX requis pour les tests PDF")
	def test_entete_et_pied_repetes_sur_plusieurs_pages(self):
		import zipfile

		import pymupdf

		ctx = contexte_simple()
		ctx["entete"] = {"nom": "En-tête de test", "haut": {"html": '<div style="text-align:center;color:#087e8b"><h2>Aqua World</h2><p>Documents produit</p></div>'}, "bas": {"html": '<p style="text-align:center">Service technique — Contact</p>'}, "ressources": []}
		bandeaux = E.rendre(ctx["entete"])
		assets, fichiers = {"entete": {}}, {}
		for cle, b in bandeaux.items():
			fichier = "images/entete-" + cle + ".png"
			fichiers[fichier] = b["png"]
			assets["entete"][cle] = {**{k: v for k, v in b.items() if k != "png"}, "fichier": fichier}
		contenu = contenu_simple(ctx)
		contenu["sections"] = [{"titre": "Rubrique " + str(i), "texte": "Texte technique à relire. " * 60, "article": "", "source": "Article TEST-P"} for i in range(5)]
		pdf, archive = L.compiler(L.source(contenu, ctx, assets=assets), fichiers)
		with pymupdf.open(stream=pdf, filetype="pdf") as doc:
			self.assertGreater(len(doc), 1)
			for page in doc:
				self.assertEqual(len(page.get_images()), 2)
				for image in page.get_images():
					self.assertTrue(page.get_image_rects(image[0]))
					for rect in page.get_image_rects(image[0]):
						self.assertTrue(page.rect.contains(rect))
		with zipfile.ZipFile(io.BytesIO(archive)) as z:
			self.assertIn("images/entete-haut.png", z.namelist())
			self.assertIn("images/entete-bas.png", z.namelist())
		# Les bandeaux rasterisés conservent leur sens dans un document arabe.
		contenu["sections"] = []
		contenu["titre"] = "دليل الاستخدام"
		pdf, _ = L.compiler(L.source(contenu, ctx, langue="ar", rtl=True, assets=assets), fichiers)
		self.assertTrue(pdf.startswith(b"%PDF"))

	def test_variantes_et_marques_conservees(self):
		ctx = contexte_simple()
		c = contenu_simple(ctx)
		self.assertEqual(c["variantes"][0]["marque"], "ecoPurium")
		self.assertEqual(c["variantes"][0]["attributs"][0]["valeur"], "Vontron")
		c["caracteristiques"][0]["article"] = "HORS-GAMME"
		with self.assertRaises(ValueError):
			S.normaliser(c, ctx)
		c = contenu_simple(ctx)
		c["variantes"][0]["marque"] = "Vontron"
		with self.assertRaises(ValueError):
			S.normaliser(c, ctx)

	def test_marque_du_document_preserve_composants_et_traductions(self):
		ctx = contexte_simple()
		ctx["marque_document"] = "Marque choisie"
		c = contenu_simple(ctx)
		self.assertEqual(c["variantes"][0]["marque"], "Marque choisie")
		self.assertEqual(c["variantes"][0]["attributs"][0]["valeur"], "Vontron")
		self.assertEqual(ctx["article"]["brand"], "ecoPurium")
		c["resume"] = "Produit Marque choisie avec membrane Vontron."
		paths = S.champs_traduisibles(c)
		out = {"items": [{"i": i, "t": "EN " + S.lire_chemin(c, p)} for i, p in enumerate(paths)]}
		self.assertIn("Marque choisie", S.appliquer_traduction(c, paths, out, ctx)["resume"])
		out["items"][paths.index(("resume",))]["t"] = "Produit autre avec membrane Vontron."
		with self.assertRaises(ValueError):
			S.appliquer_traduction(c, paths, out, ctx)
		self.assertIn("Marque choisie", L.source(c, ctx))

	def test_traduction_preserve_donnees_et_structure(self):
		ctx = contexte_simple()
		c = contenu_simple(ctx)
		paths = S.champs_traduisibles(c)
		out = {"items": [{"i": i, "t": "EN " + S.lire_chemin(c, p)} for i, p in enumerate(paths)]}
		result = S.appliquer_traduction(c, paths, out, ctx)
		self.assertEqual(result["caracteristiques"][0]["unite"], "bar")
		self.assertEqual(result["sections"][0]["source"], "Article TEST-P")
		self.assertEqual(result["variantes"][0]["article"], "TEST-P-V")
		self.assertEqual(result["variantes"][0]["marque"], "ecoPurium")
		self.assertEqual(c["resume"], "Un produit ecoPurium.")
		mauvais = copy.deepcopy(out)
		i = paths.index(("caracteristiques", 0, "valeur"))
		mauvais["items"][i]["t"] = "4"
		with self.assertRaises(ValueError):
			S.appliquer_traduction(c, paths, mauvais, ctx)
		mauvais = copy.deepcopy(out)
		i = paths.index(("sections", 0, "texte"))
		mauvais["items"][i]["t"] = mauvais["items"][i]["t"].replace("Vontron", "Autre")
		with self.assertRaises(ValueError):
			S.appliquer_traduction(c, paths, mauvais, ctx)
		with self.assertRaises(ValueError):
			S.appliquer_traduction(c, paths, {"items": out["items"][:-1]}, ctx)
		self.assertNotEqual(S.tokens_proteges("-5 °C", ctx), S.tokens_proteges("5 °C", ctx))

	def test_pages_et_limites(self):
		self.assertEqual(C.pages_selection("1-3,5,3", 7), [0, 1, 2, 4])
		for expr in ("0", "8", "3-1", "1;cat", "1-2-3"):
			with self.assertRaises(ValueError):
				C.pages_selection(expr, 7)
		with self.assertRaises(ValueError):
			C.pages_selection("", 41)

	def test_latex_echappe_commandes_et_urls(self):
		ctx = contexte_simple()
		c = contenu_simple(ctx)
		c["resume"] = r"\input{/etc/passwd} & 50% {texte} $a_1$"
		tex = L.source(c, ctx)
		self.assertNotIn(r"\input{", tex)
		self.assertIn(r"\textbackslash{}input\{/etc/passwd\}", tex)
		self.assertIn(r"50\%", tex)
		self.assertIn("BROUILLON", tex)

	def test_source_de_variante_ne_justifie_pas_toute_la_gamme(self):
		ctx = contexte_simple()
		ctx["preuves"] = [{"source": "S1 p.2", "article": "TEST-P-V", "incertitudes": []}]
		with patch.object(T, "chat_json", return_value=contenu_simple(ctx)):
			resultat = T.generer(None, S.TYPES[0], ctx)
		self.assertTrue(any("ne justifie que TEST-P-V" in p for p in resultat["points_a_verifier"]))
		with patch.object(T, "chat_json", return_value={"titre": "Document vide"}):
			with self.assertRaises(ValueError):
				T.generer(None, S.TYPES[0], ctx)

	@unittest.skipUnless(shutil.which("xelatex"), "XeLaTeX requis pour les tests PDF")
	def test_compilation_pdf_francais_et_archive(self):
		import zipfile

		import pymupdf

		ctx = contexte_simple()
		tex = L.source(contenu_simple(ctx), ctx)
		pdf, archive = L.compiler(tex, {})
		with pymupdf.open(stream=pdf, filetype="pdf") as d:
			texte = "\n".join(p.get_text() for p in d)
		self.assertIn("ecoPurium", texte)
		self.assertIn("Vontron", texte)
		self.assertIn("3", texte)
		with zipfile.ZipFile(io.BytesIO(archive)) as z:
			self.assertIn("document.tex", z.namelist())

	@unittest.skipUnless(shutil.which("xelatex"), "XeLaTeX requis pour les tests PDF")
	def test_compilation_arabe_et_chinois(self):
		import pymupdf

		ctx = contexte_simple()
		c = contenu_simple(ctx)
		c.update(titre="دليل الاستخدام", resume="جهاز لتنقية المياه ecoPurium")
		c["sections"][0].update(titre="الاستخدام", texte="الغشاء Vontron للموديل TEST-P-V")
		pdf, _ = L.compiler(L.source(c, ctx, "ar", True), {})
		with pymupdf.open(stream=pdf, filetype="pdf") as d:
			self.assertGreater(len(d), 0)
		c = contenu_simple(ctx)
		c.update(titre="使用说明书", resume="产品技术资料 ecoPurium")
		pdf, _ = L.compiler(L.source(c, ctx, "zh", False), {})
		self.assertTrue(pdf.startswith(b"%PDF"))


class TestDocumentsBase(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		if not getattr(frappe.local, "db", None):
			raise unittest.SkipTest("Un site Frappe connecté est requis pour les tests de persistance")

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("documents_produit_test")
		self.fichiers_avant = set(frappe.get_all("File", pluck="file_url"))
		parent = frappe.get_all("Item", filters={"has_variants": 1, "disabled": 0}, pluck="name", limit=1)[0]
		self.name = API.creer(parent)["name"]
		self.d = API.dossier(self.name, "write")
		self.variantes = C.variantes_disponibles(parent)[:2]
		API.enregistrer(
			self.name,
			{
				"variantes": [{"article": a["name"]} for a in self.variantes],
				"entete": "",
				"marque_document": "",
				"logo_marque_avec_entete": 0,
				"sources": [],
				"images": [],
				"consignes": "",
				"mises_en_page": {},
			},
		)
		self.d = API.dossier(self.name, "write")
		self.ctx = C.contexte(self.d)
		self.contenu = S.normaliser(
			{
				"titre": "Document de test",
				"resume": "Produit " + (self.ctx["article"]["brand"] or ""),
				"sections": [
					{"titre": "Présentation", "texte": "Données article", "source": "Article " + parent}
				],
				"caracteristiques": [
					{"nom": "Pression", "valeur": "3", "unite": "bar", "source": "Saisie manuelle"}
				],
			},
			self.ctx,
		)

	def tearDown(self):
		frappe.set_user("Administrator")
		nouveaux = []
		for f in frappe.get_all(
			"File",
			filters={"attached_to_doctype": ["in", [C.DOSSIER, C.DOCUMENT, "Brand"]]},
			fields=["name", "file_url"],
		):
			if f.file_url not in self.fichiers_avant:
				nouveaux.append(frappe.get_doc("File", f.name).get_full_path())
		frappe.db.rollback(save_point="documents_produit_test")
		frappe.clear_cache()
		for f in nouveaux:
			Path(f).unlink(missing_ok=True)

	def version(self):
		return API.nouvelle_version(self.name, S.TYPES[0], self.contenu, self.ctx)

	def test_liens_depuis_parent_et_variantes(self):
		v = self.version()
		for article in [self.d.article] + [r["name"] for r in self.variantes]:
			dossiers = API.lister(article)
			self.assertIn(self.name, [r.name for r in dossiers])
			self.assertIn(v.name, [x.name for r in dossiers for x in r.documents])
		self.assertTrue(frappe.get_meta("Item").has_field("custom_documents_produit"))

	def test_correction_cree_version_sans_ecraser(self):
		v = self.version()
		c = copy.deepcopy(self.contenu)
		c["resume"] = "Texte corrigé"
		r = API.corriger(v.name, c)
		v2 = API.document(r["name"])
		self.assertEqual(v2.numero, v.numero + 1)
		self.assertEqual(json.loads(API.document(v.name).contenu_json)["resume"], self.contenu["resume"])
		self.assertEqual(API.corriger(v2.name, c)["name"], v2.name)
		v.titre = "Contournement"
		with self.assertRaises(frappe.ValidationError):
			v.save()

	def test_mise_en_page_independante_et_version_pdf_sans_ia(self):
		from aquaworld_ia.documents_produit import mise_en_page as M

		fiche = self.version()
		manuel = API.nouvelle_version(self.name, S.TYPES[1], self.contenu, self.ctx)
		choix = M.normaliser({"position_photo": "droite", "largeur_photo": 40, "couleur": "#123456",
			"position_marque": "apres_titre", "alignement_marque": "centre", "largeur_logo": 40, "afficher_nom_marque": 1})
		API.enregistrer(self.name, {"mises_en_page": {"fiche": choix}})
		data = API.charger(self.name)
		self.assertEqual(json.loads(data["dossier"].mises_en_page)["fiche"], choix)
		etat = {v.name: v.a_actualiser for v in data["documents"]}
		self.assertTrue(etat[fiche.name])
		self.assertFalse(etat[manuel.name])
		with patch.object(T, "chat_json") as chat:
			nouveau = API.appliquer_entete(fiche, API.dossier(self.name))
			self.assertNotEqual(nouveau.name, fiche.name)
			self.assertEqual(nouveau.contenu_json, fiche.contenu_json)
			self.assertEqual(json.loads(nouveau.contexte_json)["mise_en_page"], choix)
			self.assertNotIn("mise_en_page", json.loads(API.document(fiche.name).contexte_json))
			self.assertEqual(API.appliquer_entete(nouveau, API.dossier(self.name)).name, nouveau.name)
			self.assertEqual(API.appliquer_entete(manuel, API.dossier(self.name)).name, manuel.name)
			chat.assert_not_called()
		self.assertFalse(next(v.a_actualiser for v in API.charger(self.name)["documents"] if v.name == nouveau.name))
		with self.assertRaises(ValueError):
			API.enregistrer(self.name, {"mises_en_page": {"fiche": {"couleur": "\\input{secret}"}}})

	def test_apercu_placement_logo_sans_ia_sans_version_ni_fichier(self):
		import base64

		from aquaworld_ia.documents_produit import mise_en_page as M

		v = self.version()
		avant = (frappe.db.count(C.DOCUMENT), frappe.db.count("File"))
		m = M.normaliser({"position_marque": "libre", "logo_x": 110.2, "logo_y": 70.5})
		with patch.object(T, "chat_json") as chat:
			for version in (v.name, None):
				r = API.apercu_placement_logo(self.name, S.TYPES[0], m, version)
				self.assertTrue(base64.b64decode(r["image"].split(",", 1)[1]).startswith(b"\x89PNG"))
				self.assertEqual(r["exemple"], version is None)
			chat.assert_not_called()
		self.assertEqual((frappe.db.count(C.DOCUMENT), frappe.db.count("File")), avant)
		self.assertFalse(API.document(v.name).pdf)
		with self.assertRaises(frappe.ValidationError):
			API.apercu_placement_logo(self.name, S.TYPES[1], m, v.name)
		API.enregistrer(self.name, {"mises_en_page": {"fiche": m}})
		nouveau = API.appliquer_entete(v, API.dossier(self.name))
		self.assertEqual(json.loads(nouveau.contexte_json)["mise_en_page"]["logo_x"], 110.2)

	def test_modeles_par_outil_persistants_et_tarifs_affiches(self):
		from aquaworld_ia.ia.client import modele_texte

		r = frappe.get_doc("Aquaworld IA Reglages")
		r.update({
			"modele_texte": "gpt-5.2", "modele_fiche_technique": "gpt-5-mini",
			"modele_manuel_produit": "gpt-4o-mini", "modele_lecture_documents": "gpt-5.2",
			"modele_traduction_documents": "gpt-5-mini",
			"prix_entree_par_million": 0, "prix_sortie_par_million": 0,
		})
		r.save()
		self.assertEqual(frappe.get_doc("Aquaworld IA Reglages").modele_fiche_technique, "gpt-5-mini")
		couts = API.charger(self.name)["couts_ia"]
		modeles = {m["action"]: m for m in couts["modeles"]}
		self.assertEqual(couts["modele"], "gpt-5-mini")
		self.assertEqual(modeles["manuel"]["modele"], "gpt-4o-mini")
		self.assertEqual(modeles["lecture"]["modele"], "gpt-5.2")
		self.assertEqual(modeles["traduire"]["modele"], "gpt-5-mini")
		self.assertEqual(modeles["fiche"]["prix_entree"], 0.25)
		self.assertEqual(modeles["manuel"]["prix_sortie"], 0.60)
		self.assertEqual(modeles["lecture"]["prix_sortie"], 14.0)
		self.assertEqual(modele_texte("Emballage texte"), r.modele_texte_emballage or "gpt-5.2")
		r.modele_fiche_technique = ""
		r.save()
		self.assertEqual(API.charger(self.name)["couts_ia"]["modele"], "gpt-5.2")
		self.assertEqual(modele_texte("Document produit — manuel"), "gpt-4o-mini")

	def test_marque_et_logo_depuis_generateur_sans_modifier_article(self):
		import zipfile

		import pymupdf
		from frappe.utils.file_manager import save_file
		from PIL import Image

		avant = self.version()
		marque_article = frappe.db.get_value("Item", self.d.article, "brand")
		nom = "Test Marque " + frappe.generate_hash(length=10)
		self.assertEqual(API.creer_marque(self.name, nom)["name"], nom)
		self.assertEqual(API.creer_marque(self.name, nom)["name"], nom)
		API.enregistrer(self.name, {"marque_document": nom})
		data = API.charger(self.name)
		self.assertIn(nom, [b.name for b in data["marques"]])
		self.assertEqual(data["contexte"]["marque_document"], nom)
		self.assertTrue(API.info_marque(self.name, nom)["peut_modifier"])
		self.assertEqual(frappe.db.get_value("Item", self.d.article, "brand"), marque_article)
		self.assertEqual(API.appliquer_entete(avant, API.dossier(self.name)).name, avant.name)
		self.assertNotIn("marque_document", json.loads(API.document(avant.name).contexte_json))
		ctx = data["contexte"]
		ctx["preuves"] = []
		versions = []
		for genre in S.TYPES:
			with patch.object(T, "chat_json", return_value=copy.deepcopy(self.contenu)) as chat:
				c = T.generer(API.dossier(self.name), genre, ctx)
				self.assertEqual(json.loads(chat.call_args.args[1])["contexte"]["marque_document"], nom)
			self.assertTrue(all(v["marque"] == nom for v in c["variantes"]))
			versions.append(API.nouvelle_version(self.name, genre, c, ctx))
		im = io.BytesIO()
		Image.new("RGB", (113, 47), "#1287a6").save(im, format="PNG")
		f = save_file("test-logo-marque.png", im.getvalue(), "Brand", nom, is_private=1)
		API.enregistrer_logo_marque(self.name, nom, f.file_url)
		self.assertEqual(API.info_marque(self.name, nom)["logo"], f.file_url)
		self.assertEqual(frappe.db.get_value("Brand", nom, "image"), f.file_url)
		with self.assertRaises(frappe.ValidationError):
			API.enregistrer_logo_marque(self.name, "Autre marque", f.file_url)
		with self.assertRaises((frappe.ValidationError, frappe.PermissionError)):
			API.enregistrer_logo_marque(self.name, nom, "https://example.org/logo.png")
		entete = frappe.get_doc({"doctype": "Letter Head", "letter_head_name": "Test-" + frappe.generate_hash(length=10)}).insert()
		entete.source, entete.content = "HTML", "<h2>En-tête société</h2>"
		entete.save()
		API.enregistrer(self.name, {"entete": entete.name, "logo_marque_avec_entete": 1})
		with patch.object(T, "chat_json") as chat:
			for v in versions:
				nouveau = API.appliquer_entete(v, API.dossier(self.name))
				self.assertNotEqual(nouveau.name, v.name)
				self.assertEqual(nouveau.contenu_json, v.contenu_json)
				self.assertFalse(json.loads(API.document(v.name).contexte_json)["logo"])
				self.assertEqual(API.appliquer_entete(nouveau, API.dossier(self.name)).name, nouveau.name)
				urls = L.generer_pdf(nouveau)
				with zipfile.ZipFile(io.BytesIO(C.octets(urls["archive_latex"]))) as archive:
					self.assertEqual(archive.read("images/logo.png"), L.image_png(im.getvalue()))
					self.assertIn("images/entete-haut.png", archive.namelist())
				with pymupdf.open(stream=C.octets(urls["pdf"]), filetype="pdf") as pdf:
					self.assertIn(nom, "".join(p.get_text() for p in pdf))
					self.assertGreaterEqual(len(pdf[0].get_images()), 2)
			chat.assert_not_called()

	def test_traduction_enregistree_avant_pdf(self):
		v = self.version()

		def chat(system, user, **kwargs):
			return {"items": [dict(i=x["i"], t="EN " + x["t"]) for x in json.loads(user)["items"]]}

		with patch.object(T, "chat_json", side_effect=chat):
			contenu = T.traduire(v, "en", "Anglais")
		en = API.nouvelle_version(self.name, v.type_document, contenu, self.ctx, "en", "Anglais", 0, v.name)
		reread = API.document(en.name)
		self.assertEqual(reread.source_fr, v.name)
		self.assertEqual(reread.langue, "en")
		self.assertFalse(reread.pdf)
		self.assertIn("EN ", reread.contenu_json)
		self.assertEqual(reread.statut, "Brouillon")
		self.assertFalse(
			next(r for r in API.charger(self.name)["documents"] if r.name == en.name)["a_actualiser"]
		)
		c = copy.deepcopy(self.contenu)
		c["resume"] = "Nouvelle base française"
		API.corriger(v.name, c)
		self.assertTrue(
			next(r for r in API.charger(self.name)["documents"] if r.name == en.name)["a_actualiser"]
		)

	def test_pdf_prive_persistant_et_validation(self):
		import zipfile

		from frappe.utils.file_manager import save_file
		from PIL import Image

		im = io.BytesIO()
		Image.new("RGB", (120, 80), "teal").save(im, format="PNG")
		image = save_file("illustration-test-pdf.png", im.getvalue(), C.DOSSIER, self.name, is_private=1)
		API.enregistrer(self.name, {"images": [{"image": image.file_url, "legende": "Photo de test"}]})
		self.ctx = C.contexte(API.dossier(self.name))
		self.contenu = S.normaliser({k: v for k, v in self.contenu.items() if k != "legendes"}, self.ctx)
		v = self.version()
		urls = L.generer_pdf(v, True)
		self.assertEqual(API.document(v.name).statut, "Validé")
		self.assertTrue(all(u.startswith("/private/files/") for u in urls.values()))
		self.assertTrue(C.octets(urls["pdf"]).startswith(b"%PDF"))
		with zipfile.ZipFile(io.BytesIO(C.octets(urls["archive_latex"]))) as archive:
			self.assertEqual(archive.read("images/image-0.png"), L.image_png(im.getvalue()))
		v = self.version()
		c = copy.deepcopy(self.contenu)
		c["points_a_verifier"] = ["Débit à confirmer"]
		bloque = API.document(API.corriger(v.name, c)["name"])
		with self.assertRaises(ValueError):
			L.generer_pdf(bloque, True)

	def test_permissions_et_fichiers_distants_refuses(self):
		v = self.version()
		frappe.set_user("Guest")
		for fn, args in (
			(API.charger, (self.name,)),
			(API.lire_document, (v.name,)),
			(API.corriger, (v.name, self.contenu)),
			(API.lancer, (self.name, "fiche")),
			(API.detail_cout, (self.name, "generation-inconnue")),
			(API.apercu_entete, (self.name, "Aqua World")),
			(API.info_marque, (self.name, "ecoPurium")),
			(API.creer_marque, (self.name, "Test marque")),
			(API.enregistrer_logo_marque, (self.name, "ecoPurium", "/files/logo.png")),
		):
			with self.assertRaises(frappe.PermissionError):
				fn(*args)
		frappe.set_user("Administrator")
		for url in (
			"https://example.org/manual.pdf",
			"file:///etc/passwd",
			"/private/files/../../site_config.json",
		):
			with self.assertRaises((frappe.ValidationError, frappe.PermissionError)):
				C.fichier_lisible(url)

	def test_restrictions_article_protegent_listes_et_fichiers(self):
		from frappe.utils.file_manager import save_file

		v = self.version()
		fichier = save_file("test-droits-document.txt", b"document prive", C.DOCUMENT, v.name, is_private=1)
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": "test-document-" + frappe.generate_hash(length=8) + "@example.invalid",
				"first_name": "Test documents",
				"enabled": 1,
				"send_welcome_email": 0,
				"roles": [{"role": "System Manager"}, {"role": "Stock User"}, {"role": "Aquaworld IA"}],
			}
		).insert(ignore_permissions=True)
		droit = frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": user.name,
				"allow": "Item",
				"for_value": self.d.article,
				"apply_to_all_doctypes": 1,
			}
		).insert(ignore_permissions=True)
		for variante in self.variantes:
			frappe.get_doc(
				{
					"doctype": "User Permission",
					"user": user.name,
					"allow": "Item",
					"for_value": variante["name"],
					"apply_to_all_doctypes": 1,
				}
			).insert(ignore_permissions=True)
		frappe.clear_cache(user=user.name)
		frappe.set_user(user.name)
		self.assertIn(self.name, [r.name for r in API.lister()])
		self.assertIn(v.name, frappe.get_list(C.DOCUMENT, pluck="name"))
		self.assertEqual(C.octets(fichier.file_url), b"document prive")
		frappe.set_user("Administrator")
		frappe.db.set_value("File", fichier.name, "owner", user.name)
		autre = frappe.get_all("Item", filters={"name": ["!=", self.d.article]}, pluck="name", limit=1)[0]
		droit.for_value = autre
		droit.save(ignore_permissions=True)
		frappe.clear_cache(user=user.name)
		frappe.set_user(user.name)
		self.assertNotIn(self.name, [r.name for r in API.lister()])
		self.assertNotIn(v.name, frappe.get_list(C.DOCUMENT, pluck="name"))
		for fn, arg in ((API.charger, self.name), (API.lire_document, v.name), (C.octets, fichier.file_url)):
			with self.assertRaises(frappe.PermissionError):
				fn(arg)

	def test_pdf_source_native_et_photo_vision(self):
		import pymupdf
		from frappe.utils.file_manager import save_file
		from PIL import Image

		with pymupdf.open() as pdf:
			page = pdf.new_page()
			page.insert_text(
				(60, 60),
				"Manual: pressure 3 bar. Model TEST. Technical data verified in the manufacturer documentation. Installation instructions follow on the next page.",
			)
			b = pdf.tobytes()
		f = save_file("source-test-doc-produit.pdf", b, C.DOSSIER, self.name, is_private=1)
		im = io.BytesIO()
		Image.new("RGB", (100, 100), "white").save(im, format="PNG")
		photo = save_file("photo-test-doc-produit.png", im.getvalue(), C.DOSSIER, self.name, is_private=1)
		API.enregistrer(
			self.name,
			{
				"sources": [
					{"fichier": f.file_url, "pages": "1", "article": ""},
					{"fichier": photo.file_url, "pages": "", "article": self.variantes[0]["name"]},
				]
			},
		)
		ctx = C.contexte(API.dossier(self.name))
		with patch.object(
			C,
			"chat_json_image",
			return_value={"texte": "Pression 3 bar", "incertitudes": ["Ligne illisible"]},
		) as vision:
			preuves = C.lire_sources(ctx, self.d)
		self.assertEqual(len(preuves), 2)
		self.assertEqual(vision.call_count, 1)
		self.assertIn("3 bar", preuves[0]["texte"])
		self.assertEqual(preuves[1]["article"], self.variantes[0]["name"])
		self.assertEqual(preuves[1]["incertitudes"], ["Ligne illisible"])
		image = API.illustrer_page(self.name, f.file_url, 1)["image"]
		self.assertTrue(C.octets(image).startswith(b"\x89PNG"))

	def test_worker_double_generation_et_traduction_durable(self):
		def fake_chat(system, user, **kwargs):
			if "items" in json.loads(user):
				return {"items": [{"i": i["i"], "t": "EN " + i["t"]} for i in json.loads(user)["items"]]}
			return copy.deepcopy(self.contenu)

		with (
			patch("frappe.enqueue") as enqueue,
			patch("frappe.db.commit"),
			patch.object(T, "chat_json", side_effect=fake_chat),
		):
			r = API.lancer(self.name, "les_deux")
			self.assertTrue(enqueue.call_args.kwargs["enqueue_after_commit"])
			with self.assertRaises(frappe.ValidationError):
				API.lancer(self.name, "fiche")
			T.executer(self.name, r["token"], "les_deux", utilisateur="Administrator")
			self.assertEqual(API.etat(self.name)["etat_traitement"], "Terminé")
			docs = API.charger(self.name)["documents"]
			self.assertTrue(set(S.TYPES) <= {d.type_document for d in docs})
			fr = next(d for d in docs if d.type_document == S.TYPES[0] and d.langue == "fr")
			r = API.lancer(self.name, "traduire", document_name=fr.name, langue="en", libelle="Anglais")
			T.executer(
				self.name,
				r["token"],
				"traduire",
				document_name=fr.name,
				langue="en",
				libelle="Anglais",
				utilisateur="Administrator",
			)
			self.assertEqual(API.etat(self.name)["etat_traitement"], "Terminé")
			en = next(d for d in API.charger(self.name)["documents"] if d.langue == "en")
			self.assertEqual(API.document(en.name).source_fr, fr.name)
			self.assertFalse(en.pdf)

	def test_worker_echec_ne_detruit_pas_la_version_existante(self):
		v = self.version()
		with (
			patch("frappe.enqueue"),
			patch("frappe.db.commit"),
			patch("frappe.db.rollback"),
			patch.object(T, "chat_json", side_effect=RuntimeError("API indisponible")),
		):
			r = API.lancer(self.name, "fiche")
			T.executer(self.name, r["token"], "fiche", utilisateur="Administrator")
		self.assertEqual(API.etat(self.name)["etat_traitement"], "Échec")
		self.assertEqual(API.document(v.name).contenu_json, v.contenu_json)

	def test_couts_groupes_par_generation_et_traduction(self):
		from aquaworld_ia.ia import journal

		usage = SimpleNamespace(prompt_tokens=10000, completion_tokens=2000)
		v = self.version()
		with patch("frappe.db.commit") as commit, patch.object(journal, "reglages", return_value=frappe._dict()):
			with journal.suivre_generation(self.name, "test-cout-double", "les_deux", "fr"):
				for etape in ("lecture", "fiche technique", "manuel"):
					self.assertTrue(journal.enregistrer(
						fonctionnalite="Document produit — " + etape, appel="chat",
						modele="gpt-5.2", doc=self.d, usage=usage,
					))
			with journal.suivre_generation(self.name, "test-cout-traduction", "traduire", "ar"):
				for erreur, consommation in ((None, usage), ("Connexion interrompue", None)):
					self.assertTrue(journal.enregistrer(
						fonctionnalite="Document produit — traduction", appel="chat",
						modele="gpt-5.2", doc=v, usage=consommation, erreur=erreur,
					))
			self.assertEqual(commit.call_count, 5)
			self.assertIsNone(journal._generation_produit.get())
		couts = API.charger(self.name)["couts_ia"]
		generations = {g.generation: g for g in couts["historique"]}
		self.assertEqual(generations["test-cout-double"].appels, 3)
		self.assertAlmostEqual(generations["test-cout-double"].cout, 0.1365)
		self.assertEqual(generations["test-cout-traduction"].langue, "ar")
		self.assertEqual(generations["test-cout-traduction"].inconnus, 1)
		self.assertEqual(generations["test-cout-traduction"].erreurs, 1)
		self.assertAlmostEqual(couts["total"], 0.182)
		self.assertEqual(len(API.detail_cout(self.name, "test-cout-double")), 3)
		self.assertEqual(API.detail_cout(self.name, "hors-dossier"), [])

	def test_choix_entetes_et_nouvelles_versions_sans_ia(self):
		v = self.version()
		modeles = []
		for titre in ("Marque A", "Marque B"):
			doc = frappe.get_doc({"doctype": "Letter Head", "letter_head_name": "Test-" + frappe.generate_hash(length=10)}).insert(ignore_permissions=True)
			doc.source, doc.content = "HTML", "<h2>" + titre + "</h2>"
			doc.save(ignore_permissions=True)
			modeles.append(doc)
		API.enregistrer(self.name, {"entete": modeles[0].name})
		self.assertIn(modeles[1].name, [x.name for x in API.charger(self.name)["entetes"]])
		with patch("frappe.enqueue") as enqueue, patch.object(T, "chat_json") as chat:
			API.lancer(self.name, "pdf", document_name=v.name)
			nom_nouveau = enqueue.call_args.kwargs["document_name"]
			chat.assert_not_called()
		nouveau = API.document(nom_nouveau)
		self.assertNotEqual(nouveau.name, v.name)
		self.assertEqual(nouveau.contenu_json, v.contenu_json)
		self.assertNotIn("entete", json.loads(API.document(v.name).contexte_json))
		self.assertIn("Marque A", nouveau.contexte_json)
		self.assertEqual(API.appliquer_entete(nouveau, API.dossier(self.name)).name, nouveau.name)
		API.enregistrer(self.name, {"entete": modeles[1].name})
		second = API.appliquer_entete(nouveau, API.dossier(self.name))
		self.assertIn("Marque B", second.contexte_json)
		self.assertIn("Marque A", API.document(nouveau.name).contexte_json)
		preview = API.apercu_entete(self.name, modeles[1].name)
		self.assertTrue(preview["haut"].startswith("data:image/png;base64,"))
		modeles[1].content = "<h2>Nouvelle présentation B</h2>"
		modeles[1].save(ignore_permissions=True)
		self.assertNotIn("Nouvelle présentation", API.document(second.name).contexte_json)
		troisieme = API.appliquer_entete(second, API.dossier(self.name))
		self.assertIn("Nouvelle présentation", troisieme.contexte_json)
		urls = L.generer_pdf(troisieme)
		self.assertTrue(C.octets(urls["pdf"]).startswith(b"%PDF"))
		modeles[1].content = '<img src="/files/test-image-entete-inexistante.png">'
		modeles[1].save(ignore_permissions=True)
		self.assertTrue(API.charger(self.name)["erreur_entete"])
		API.enregistrer(self.name, {"entete": ""})
		sans = API.appliquer_entete(troisieme, API.dossier(self.name))
		self.assertNotIn("entete", json.loads(sans.contexte_json))

	def test_consommation_enregistree_avant_validation_reponse(self):
		from aquaworld_ia.ia import chat, journal

		reponse = SimpleNamespace(
			usage=SimpleNamespace(prompt_tokens=10000, completion_tokens=2000),
			choices=[SimpleNamespace(message=SimpleNamespace(content="JSON invalide"))],
		)
		client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: reponse)))
		with (
			patch("frappe.db.commit") as commit,
			patch.object(chat, "client_et_modele", return_value=(client, "gpt-5.2", 0.2)),
			journal.suivre_generation(self.name, "test-cout-invalide", "fiche", "fr"),
		):
			with self.assertRaises(frappe.ValidationError):
				chat.chat_json("test", "test", fonctionnalite="Document produit — fiche technique", doc=self.d)
			commit.assert_called_once()
		lignes = API.detail_cout(self.name, "test-cout-invalide")
		self.assertEqual(len(lignes), 1)
		self.assertAlmostEqual(lignes[0].cout_estime, 0.0455)
