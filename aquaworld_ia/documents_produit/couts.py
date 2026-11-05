"""Consommation estimée du dossier, regroupée par lancement (y compris les reprises)."""

import frappe

from aquaworld_ia.ia.client import modele_texte, reglages
from aquaworld_ia.ia.couts import tarifs_depuis_reglages


def bilan(name):
	"""Appelé uniquement après contrôle des droits du dossier dans le service."""
	r = reglages()
	modeles = []
	for action, libelle, fonctionnalite in (
		("fiche", "Fiche technique", "Document produit — fiche technique"),
		("manuel", "Manuel d’utilisation", "Document produit — manuel"),
		("lecture", "Lecture des sources et scans", "Document produit — lecture"),
		("traduire", "Traduction", "Document produit — traduction"),
	):
		modele = modele_texte(fonctionnalite)
		tarifs = tarifs_depuis_reglages(r, modele)
		modeles.append({
			"action": action, "libelle": libelle, "modele": modele,
			"prix_entree": tarifs["entree_par_million"], "prix_sortie": tarifs["sortie_par_million"],
		})
	totaux = frappe.db.sql(
		"""select coalesce(sum(cout_estime), 0) as cout,
		coalesce(sum(usage_inconnu), 0) as inconnus
		from `tabJournal IA` where dossier_produit = %s""", (name,), as_dict=True,
	)[0]
	historique = frappe.db.sql(
		"""select generation_produit as generation, min(horodatage) as debut,
		max(action_produit) as action, max(langue_produit) as langue,
		group_concat(distinct modele order by modele separator ', ') as modeles,
		count(*) as appels, sum(jetons_entree) as entree, sum(jetons_sortie) as sortie,
		sum(cout_estime) as cout, sum(usage_inconnu) as inconnus,
		sum(statut = 'Erreur') as erreurs
		from `tabJournal IA` where dossier_produit = %s and generation_produit != ''
		group by generation_produit order by debut desc limit 50""", (name,), as_dict=True,
	)
	return {
		"modele": modeles[0]["modele"],
		"prix_entree": modeles[0]["prix_entree"],
		"prix_sortie": modeles[0]["prix_sortie"],
		"modeles": modeles,
		"total": totaux.cout,
		"inconnus": totaux.inconnus,
		"historique": historique,
	}


def details(name, generation):
	"""Les deux identifiants sont filtrés ensemble : aucun accès à un autre dossier."""
	return frappe.get_all(
		"Journal IA",
		filters={"dossier_produit": name, "generation_produit": generation},
		fields=["horodatage", "fonctionnalite", "modele", "jetons_entree", "jetons_sortie",
			"cout_estime", "statut", "usage_inconnu"],
		order_by="horodatage asc",
	)
