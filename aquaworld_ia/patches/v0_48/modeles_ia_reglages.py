"""Modèles IA des Réglages (demande 12/11/2026 : « paramètre tout en dev et crée-moi un patch pour le réglage en
prod ») : Terra par défaut, Sol pour les fiches techniques et les manuels produit, Sunburst 2.6 pour les images,
Flare 2.6 pour les illustrations de manuels ; les autres outils, laissés vides, suivent le modèle par défaut.

Ces valeurs ont été posées sur le site de développement et essayées le 12/11/2026 par les fonctions de l'app
(rédaction d'une fiche de variante, lecture d'une photo, images.generate et images.edit) : le compte OpenAI les
accepte. Le patch écrit les treize champs de modèle, une seule fois : un réglage changé ensuite à la main dans
« Aquaworld IA Réglages » est conservé — sauf `modele_image`, que `contenu/reglages.json` repose à chaque
migration (transfert.appliquer_reglages). Les autres réglages (qualité, plafond, tarifs) ne sont pas touchés.
Une erreur est consignée (Error Log) sans bloquer la migration.
"""
import frappe

REGLAGES = "Aquaworld IA Reglages"
MODELES = {
	# texte
	"modele_texte": "gpt-6.1-terra",
	"modele_fiche_technique": "gpt-6.1-sol",
	"modele_manuel_produit": "gpt-6.1-sol",
	"modele_lecture_documents": "",
	"modele_traduction_documents": "",
	"modele_traduction_manuels": "",
	"modele_studio_manuel": "",
	"modele_texte_emballage": "",
	# image
	"modele_image": "gpt-image-2.6-sunburst",
	"modele_image_manuels": "gpt-image-2.6-flare",
	"modele_image_emballage": "",
	"modele_logo": "",
	"modele_mockup": "",
}


def execute():
	try:
		changes = appliquer()
		print("Aquaworld IA, modèles des Réglages :", "; ".join(changes) or "déjà en place, rien fait")
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="Aquaworld IA : modèles IA des Réglages", message=frappe.get_traceback())
		print("Aquaworld IA, modèles des Réglages : ÉCHEC, voir Error Log — à saisir dans Aquaworld IA Réglages")


def appliquer(modeles=None):
	"""-> les changements faits (« champ : avant → après »). `modeles` ne change que pour les essais."""
	if not frappe.db.exists("DocType", REGLAGES):
		return []
	doc = frappe.get_single(REGLAGES)
	changes = []
	for champ, valeur in (MODELES if modeles is None else modeles).items():
		avant = (doc.get(champ) or "").strip()
		if not doc.meta.has_field(champ) or avant == valeur:
			continue
		doc.set(champ, valeur)
		changes.append(f"{champ} : {avant or 'vide'} → {valeur or 'vide'}")
	if changes:
		doc.save(ignore_permissions=True)
		frappe.db.commit()
	return changes
