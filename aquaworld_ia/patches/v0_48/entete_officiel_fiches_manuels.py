"""Modèle d'en-tête « AquaWorld — En-tête officiel · Fiches techniques & manuels » (demande 12/11/2026 : « j'ai créé
un modèle d'en-tête, change son nom et crée-le en patch pour la prod »).

Le modèle a été composé dans l'éditeur visuel du site de développement ; ce patch le recrée à l'identique par le
même chemin (`editeur_entete.enregistrer`), il reste donc modifiable dans l'éditeur. Le logo voyage avec l'app
(`contenu/entetes/`) : il est posé dans les fichiers privés du site et rattaché au modèle, pour que tout
utilisateur qui peut lire l'en-tête puisse lire son image.

Sans effet si le modèle existe déjà (ses réglages ne sont pas écrasés) ; un modèle resté sous l'ancien nom est
renommé. Il n'est ni activé par défaut pour les autres documents ERPNext, ni appliqué aux dossiers existants.
Une erreur est consignée (Error Log) sans bloquer la migration.
"""
import os
import shutil

import frappe

NOM = "AquaWorld — En-tête officiel · Fiches techniques & manuels"
ANCIEN_NOM = "Entete officiel Fiche technique et manuelle"
LOGO = "/private/files/Logo-AquaWorld-2e58c3c.png"
CONFIGURATION = {
	"disposition": "gauche", "logo": LOGO, "largeur_logo": 50, "couleur": "#08477c", "taille_texte": 8,
	"nom_societe": "", "sous_titre": "",
	"titre_contact_1": "Service commercial", "activite_contact_1": "Ventes, B2B, Partenariats",
	"contact_1": "sales@aquaworldservicing.com\n+216 51 511 918", "alignement_contact_1": "droite",
	"titre_contact_2": "Support technique", "activite_contact_2": "Assistance, Diagnostic, Études",
	"contact_2": "support@aquaworldservicing.com\n+216 56 511 406", "alignement_contact_2": "gauche",
	"pied_page": "Aqua World & Servicing : 22 rue du parc, La soukra Ariana, Tunisie\nwww.aquaworldservicing.com",
	"trait": 1, "separateur_blocs": 0,
}


def execute():
	try:
		print("Aquaworld IA, en-tête « " + NOM + " » :", creer())
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="Aquaworld IA : en-tête officiel des fiches et manuels", message=frappe.get_traceback())
		print("Aquaworld IA, en-tête « " + NOM + " » : ÉCHEC, voir Error Log — à créer dans l'éditeur d'en-tête")


def creer(nom=NOM, logo=LOGO):
	"""-> ce qui a été fait. `nom` et `logo` ne changent que pour les essais."""
	if frappe.db.exists("Letter Head", nom):
		return "déjà présent, rien fait"
	if nom == NOM and frappe.db.exists("Letter Head", ANCIEN_NOM):
		frappe.rename_doc("Letter Head", ANCIEN_NOM, NOM, force=True, show_alert=False)
		frappe.db.commit()
		return "renommé depuis « " + ANCIEN_NOM + " »"
	from aquaworld_ia.documents_produit import editeur_entete
	from aquaworld_ia.install import installer_documents_produit

	installer_documents_produit()   # le champ de l'éditeur visuel sur Letter Head (site neuf : créé après les patches)
	fichier = poser_logo(logo)
	d = editeur_entete.enregistrer(nom, {**CONFIGURATION, "logo": logo})
	if not fichier.attached_to_name:
		fichier.db_set({"attached_to_doctype": "Letter Head", "attached_to_name": d.name}, update_modified=False)
	frappe.db.commit()
	return "créé"


def poser_logo(url):
	"""La fiche File du logo, à l'adresse attendue par le modèle ; le fichier vient de l'app s'il manque sur le site."""
	from aquaworld_ia import transfert

	source = os.path.join(transfert.DOSSIER, "entetes", os.path.basename(LOGO))
	destination = transfert._chemin_site(url)
	if not os.path.exists(destination):
		os.makedirs(os.path.dirname(destination), exist_ok=True)
		shutil.copyfile(source, destination)
	nom = frappe.db.get_value("File", {"file_url": url}, "name")
	if nom:
		return frappe.get_doc("File", nom)
	return transfert.fiche_fichier_existant({"file_name": os.path.basename(url), "file_url": url, "is_private": 1})
