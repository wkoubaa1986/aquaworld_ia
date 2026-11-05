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
DEFAUTS = {
	"disposition": "gauche", "logo": "", "largeur_logo": 28, "couleur": "#08477C",
	"taille_texte": 9, "nom_societe": "", "sous_titre": "",
	"titre_contact_1": "Service commercial", "contact_1": "",
	"titre_contact_2": "Support technique", "contact_2": "",
	"pied_page": "", "trait": 1,
}


def normaliser(valeur):
	if not isinstance(valeur, dict) or set(valeur) - set(DEFAUTS):
		raise ValueError("Configuration de l’en-tête invalide.")
	c = {**DEFAUTS, **valeur}
	for champ, limite in (("nom_societe", 100), ("sous_titre", 150), ("titre_contact_1", 70),
		("titre_contact_2", 70), ("contact_1", 350), ("contact_2", 350), ("pied_page", 500), ("logo", 500)):
		if not isinstance(c[champ], str) or len(c[champ]) > limite:
			raise ValueError(f"Le champ {champ} doit contenir au maximum {limite} caractères.")
		c[champ] = c[champ].strip()
	if c["disposition"] not in ("gauche", "droite", "centre"):
		raise ValueError("Choisissez une disposition proposée.")
	if not isinstance(c["couleur"], str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", c["couleur"]):
		raise ValueError("Couleur de l’en-tête invalide.")
	for champ, mini, maxi in (("largeur_logo", 12, 50), ("taille_texte", 7, 12)):
		if type(c[champ]) is not int or not mini <= c[champ] <= maxi:
			raise ValueError(f"{champ} doit être compris entre {mini} et {maxi}.")
	if type(c["trait"]) is not int or c["trait"] not in (0, 1):
		raise ValueError("Le trait de séparation doit être activé ou désactivé.")
	if c["logo"] and not c["logo"].startswith(("/files/", "/private/files/")):
		raise ValueError("Ajoutez le logo aux fichiers de l’outil.")
	if not any(c[k] for k in ("logo", "nom_societe", "sous_titre", "contact_1", "contact_2")):
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
	blocs = []
	for n in (1, 2):
		if c[f"contact_{n}"]:
			titre = f'<strong>{texte(c[f"titre_contact_{n}"])}</strong><br>' if c[f"titre_contact_{n}"] else ""
			blocs.append(titre + texte(c[f"contact_{n}"]))
	marque = "".join(identite)
	style = f'color:{couleur};font-size:{taille}pt;line-height:1.2;'

	def tableau(parties):
		largeur = 100 / max(1, len(parties))
		return '<table style="width:100%;border-collapse:collapse;"><tr>' + "".join(
			f'<td style="width:{largeur:.2f}%;vertical-align:middle;padding:2px 5px;{style}">{partie}</td>'
			for partie in parties
		) + "</tr></table>"

	if c["disposition"] == "centre":
		haut = f'<div style="text-align:center;{style}">{marque}</div>' + (tableau(blocs) if blocs else "")
	else:
		parties = ([marque] if marque else []) + blocs if c["disposition"] == "gauche" else blocs + ([marque] if marque else [])
		haut = tableau(parties)
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
