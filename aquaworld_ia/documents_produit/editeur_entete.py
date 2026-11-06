"""Éditeur visuel d'en-têtes : champs structurés, HTML contrôlé et modèles réutilisables."""

import io
import json
import re
from html import escape

import frappe
from frappe.utils import get_datetime
from PIL import Image

from aquaworld_ia.documents_produit import contexte as C
from aquaworld_ia.documents_produit import entetes as E
from aquaworld_ia.documents_produit import latex as L
from aquaworld_ia.documents_produit import structure as S

CHAMP = "custom_documents_produit_designer"
# Jusqu'à quatre blocs de coordonnées (06/11/2026) : les blocs 3 et 4, la ligne d'activité en italique, l'alignement
# du texte de chaque bloc et le trait vertical entre blocs sont absents des modèles enregistrés avant — DEFAUTS les
# complète, un ancien modèle se rend donc à l'identique.
BLOCS = (1, 2, 3, 4)
ALIGNEMENTS = ("gauche", "centre", "droite")
DEFAUTS = {
	"disposition": "gauche", "logo": "", "largeur_logo": 28, "couleur": "#08477C",
	"taille_texte": 9, "nom_societe": "", "sous_titre": "",
	"titre_contact_1": "Service commercial", "contact_1": "",
	"titre_contact_2": "Support technique", "contact_2": "",
	"titre_contact_3": "", "contact_3": "",
	"titre_contact_4": "", "contact_4": "",
	"activite_contact_1": "", "activite_contact_2": "", "activite_contact_3": "", "activite_contact_4": "",
	"alignement_contact_1": "gauche", "alignement_contact_2": "gauche",
	"alignement_contact_3": "gauche", "alignement_contact_4": "gauche",
	"pied_page": "", "trait": 1, "separateur_blocs": 0,
}


def normaliser(valeur):
	if not isinstance(valeur, dict) or set(valeur) - set(DEFAUTS):
		raise ValueError("Configuration de l’en-tête invalide.")
	c = {**DEFAUTS, **valeur}
	limites = [("nom_societe", 100), ("sous_titre", 150), ("pied_page", 500), ("logo", 500)]
	limites += [(f"titre_contact_{n}", 70) for n in BLOCS] + [(f"contact_{n}", 350) for n in BLOCS]
	limites += [(f"activite_contact_{n}", 120) for n in BLOCS]
	for champ, limite in limites:
		if not isinstance(c[champ], str) or len(c[champ]) > limite:
			raise ValueError(f"Le champ {champ} doit contenir au maximum {limite} caractères.")
		c[champ] = c[champ].strip()
	if c["disposition"] not in ("gauche", "droite", "centre"):
		raise ValueError("Choisissez une disposition proposée.")
	for n in BLOCS:
		if c[f"alignement_contact_{n}"] not in ALIGNEMENTS:
			raise ValueError(f"Alignement du bloc {n} : choisissez gauche, centre ou droite.")
	if not isinstance(c["couleur"], str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", c["couleur"]):
		raise ValueError("Couleur de l’en-tête invalide.")
	for champ, mini, maxi in (("largeur_logo", 12, 50), ("taille_texte", 7, 12)):
		if type(c[champ]) is not int or not mini <= c[champ] <= maxi:
			raise ValueError(f"{champ} doit être compris entre {mini} et {maxi}.")
	for champ in ("trait", "separateur_blocs"):
		if type(c[champ]) is not int or c[champ] not in (0, 1):
			raise ValueError("Le trait de séparation doit être activé ou désactivé.")
	if c["logo"] and not c["logo"].startswith(("/files/", "/private/files/")):
		raise ValueError("Ajoutez le logo aux fichiers de l’outil.")
	if not any(c[k] for k in ("logo", "nom_societe", "sous_titre", *[f"contact_{n}" for n in BLOCS])):
		raise ValueError("Ajoutez au moins un logo, un nom ou des coordonnées dans l’en-tête.")
	return c


def html(configuration):
	c = normaliser(configuration)

	def texte(valeur):
		return escape(valeur, quote=True).replace("\n", "<br>")

	couleur, taille = c["couleur"], c["taille_texte"]
	identite = []
	if c["logo"]:
		# Fixer les deux dimensions : le moteur PDF ne respecte pas toujours max-height.
		C.fichier_lisible(c["logo"], silencieux=True)
		with Image.open(io.BytesIO(L.image_png(C.octets(c["logo"])))) as im:
			echelle = min(c["largeur_logo"] / im.width, 18 / im.height) * 96 / 25.4
			largeur, hauteur = max(1, round(im.width * echelle)), max(1, round(im.height * echelle))
		identite.append(f'<img src="{escape(c["logo"], quote=True)}" width="{largeur}" height="{hauteur}" style="width:{largeur}px;height:{hauteur}px;"><br>')
	if c["nom_societe"]:
		identite.append(f'<strong style="font-size:{taille + 3}pt;">{texte(c["nom_societe"])}</strong>')
	if c["sous_titre"]:
		identite.append(f'<div>{texte(c["sous_titre"])}</div>')
	# Un bloc : titre en gras, activité en italique, puis les lignes saisies ; chacun avec son alignement.
	# Les blocs vides sont omis (les blocs 3 et 4 n'existent qu'une fois remplis).
	alignement = {"gauche": "left", "centre": "center", "droite": "right"}
	blocs = []
	for n in BLOCS:
		if c[f"contact_{n}"]:
			titre = f'<strong>{texte(c[f"titre_contact_{n}"])}</strong><br>' if c[f"titre_contact_{n}"] else ""
			activite = f'<em>{texte(c[f"activite_contact_{n}"])}</em><br>' if c[f"activite_contact_{n}"] else ""
			blocs.append((titre + activite + texte(c[f"contact_{n}"]), f'text-align:{alignement[c[f"alignement_contact_{n}"]]};'))
	marque = "".join(identite)
	style = f'color:{couleur};font-size:{taille}pt;line-height:1.2;'

	def tableau(parties):
		"""parties : [(html, style_propre, trait_a_gauche)] — colonnes de même largeur.

		Le trait vertical est porté par un <div> DANS la cellule : le moteur de rendu des bandeaux (pymupdf
		insert_htmlbox) ignore border-left sur un <td> mais le dessine sur un bloc, à la hauteur du texte —
		ce qui donne le trait « entre les blocs » attendu, pas une ligne sur toute la hauteur du tableau.
		"""
		largeur = 100 / max(1, len(parties))
		cellules = []
		for partie, propre, trait in parties:
			if trait and c["separateur_blocs"]:
				partie = f'<div style="border-left:1px solid {couleur};padding-left:5px;{propre}">{partie}</div>'
				cellules.append(f'<td style="width:{largeur:.2f}%;vertical-align:middle;padding:2px 5px 2px 0;{style}">{partie}</td>')
			else:
				cellules.append(f'<td style="width:{largeur:.2f}%;vertical-align:middle;padding:2px 5px;{style}{propre}">{partie}</td>')
		return '<table style="width:100%;border-collapse:collapse;"><tr>' + "".join(cellules) + "</tr></table>"

	# Le trait vertical sépare les blocs entre eux (jamais à gauche du premier élément de la ligne).
	cellules = [(html_bloc, propre, i > 0) for i, (html_bloc, propre) in enumerate(blocs)]
	if c["disposition"] == "centre":
		haut = f'<div style="text-align:center;{style}">{marque}</div>' + (tableau(cellules) if cellules else "")
	elif c["disposition"] == "gauche":
		haut = tableau(([(marque, "", False)] if marque else []) + [(h, p, bool(marque) or t) for h, p, t in cellules])
	else:
		haut = tableau(cellules + ([(marque, "", bool(cellules))] if marque else []))
	trait = f"border-bottom:1px solid {couleur};padding-bottom:5px;" if c["trait"] else ""
	haut = f'<div style="{trait}">{haut}</div>'
	bas = ""
	if c["pied_page"]:
		trait_bas = f"border-top:1px solid {couleur};padding-top:5px;" if c["trait"] else ""
		bas = f'<div style="text-align:center;{style}{trait_bas}">{texte(c["pied_page"])}</div>'
	return haut, bas


def preparer(configuration):
	c = normaliser(configuration)
	haut, bas = html(c)
	ressources = {}
	snapshot = {"haut": {"html": E.nettoyer_html(haut, ressources)}}
	if bas:
		snapshot["bas"] = {"html": E.nettoyer_html(bas, ressources)}
	snapshot["ressources"] = list(ressources.values())
	return c, haut, bas, snapshot


def empreinte(doc):
	return S.empreinte({k: doc.get(k) or "" for k in
		("source", "content", "footer_source", "footer", "image", "footer_image")})


def configuration_enregistree(doc):
	try:
		stocke = json.loads(doc.get(CHAMP) or "{}")
		if stocke.get("version") == 1 and stocke.get("empreinte") == empreinte(doc):
			return normaliser(stocke["configuration"])
	except (ValueError, TypeError, KeyError, AttributeError):
		pass
	return None


def enregistrer(titre, configuration, modele=None, modified=None):
	# Vérifier le rendu avant toute écriture, y compris le premier enregistrement natif.
	c, haut, bas, snapshot = preparer(configuration)
	E.rendre(snapshot)
	if modele:
		d = frappe.get_doc("Letter Head", modele, for_update=True)
		d.check_permission("write")
		if not modified or get_datetime(modified) != get_datetime(d.modified):
			frappe.throw("Cet en-tête a changé. Fermez l’éditeur et rouvrez-le.", frappe.TimestampMismatchError)
		if not configuration_enregistree(d):
			raise ValueError("Ce modèle a été modifié hors de l’éditeur visuel. Créez une copie pour conserver l’original.")
	else:
		frappe.has_permission("Letter Head", "create", throw=True)
		titre = S.texte(titre, 140)
		if not titre:
			raise ValueError("Donnez un nom au modèle.")
		if frappe.db.exists("Letter Head", titre):
			raise ValueError("Un en-tête porte déjà ce nom. Choisissez un autre nom.")
		d = frappe.get_doc({"doctype": "Letter Head", "letter_head_name": titre, "footer_source": "HTML", "disabled": 1})
		# Frappe impose Image dans before_insert ; passer ensuite à HTML sans l'alerte d'image vide.
		muet = frappe.flags.mute_messages
		try:
			frappe.flags.mute_messages = True
			d.insert()
		finally:
			frappe.flags.mute_messages = muet
	# Ne pas promouvoir implicitement ce modèle comme en-tête global des autres documents ERPNext.
	est_defaut = bool(d.is_default)
	d.update({"source": "HTML", "content": haut, "footer_source": "HTML", "footer": bas,
		"image": None, "footer_image": None, "disabled": 0 if est_defaut else 1})
	d.save()
	if not est_defaut:
		d.db_set("disabled", 0, update_modified=False)
	d.reload()
	# Frappe normalise le HTML à la sauvegarde (ex. ajout de tbody) : signer le contenu stocké.
	d.db_set(CHAMP, json.dumps({"version": 1, "configuration": c, "empreinte": empreinte(d)}, ensure_ascii=False), update_modified=False)
	return d
