"""Réglages de présentation validés, indépendants de la rédaction IA."""

from __future__ import annotations

import copy
import json
import math
import re

ORDRE = ["presentation", "rubriques", "caracteristiques", "variantes", "illustrations"]
TYPES = {"Fiche technique": "fiche", "Manuel d'utilisation": "manuel"}
MARQUE_DEFAUTS = {
	"position_marque": "avant_titre", "alignement_marque": "gauche",
	"largeur_logo": 32, "afficher_nom_marque": 0,
	"logo_x": 150, "logo_y": 8,
}
PHOTOS_DEFAUTS = {"photos_variantes": 0, "colonnes_photos": 1, "hauteur_vignettes": 55, "style_galerie": "grille", "photo_grande": "",
	"tableau_variantes": "liste", "largeur_grande": 62, "legendes_galerie": 1, "legende_alignement": "gauche", "legende_couleur": "texte",
	"largeur_mosaique": 100, "libelle_croise": "nom_sans_parent"}
# libelle_croise : « nom_sans_parent » (le nom de la variante sans le nom de l'article parent, ex. « AquaJad, Classique
# 5 Stages, Sans mixage »), « nom » (nom complet) ou « reference » (code, ex. AP-M-AJ-5-SM) dans les cellules du croisé.
# largeur_mosaique : % de la ligne occupé par la mosaïque (grande + colonne) ; en dessous de 100, elle est centrée.
# largeur_grande : % de la ligne pour la grande photo de la mosaïque. legendes_galerie : 0 masque les légendes des
# photos (pas celle du QR). legende_alignement / legende_couleur (texte | titres | gris) : présentation des légendes.
# photos_variantes : 0 = vues des variantes dans les illustrations, 1 = regroupées avec la fiche de chaque variante,
# 2 = vignette dans le tableau des variantes. tableau_variantes : « liste » groupée par le premier attribut, ou
# « croise » = attribut le plus varié en lignes × attribut le moins varié en colonnes (demande 06/11/2026).
# hauteur_vignettes : mm des vignettes des galeries à plusieurs colonnes. style_galerie : « grille » régulière, ou
# « mosaique » = une grande photo à gauche et jusqu'à trois petites empilées à droite (demande 06/11/2026), les
# suivantes en grille.
# QR code d'un lien internet (demande utilisateur 06/11/2026 : « le lien du produit en QR code sur mon site »),
# avec une légende sous le code. Absent du PDF tant que l'adresse est vide.
QR_DEFAUTS = {"qr_url": "", "qr_legende": "", "qr_position": "fin_document", "qr_alignement": "droite", "qr_taille": 22}
QR_URL = re.compile(r"https?://[A-Za-z0-9](?:[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]*)")


def qr_valide(disposition):
	"""L'adresse du QR si la disposition en porte une (déjà normalisée), sinon ''."""
	return (disposition or {}).get("qr_url", "")


def hauteur_zone_marque(disposition):
	return disposition.get("largeur_logo", 32) * 18 / 32 + (8 if disposition.get("afficher_nom_marque") else 0)


def normaliser(valeur=None):
	if valeur is None:
		valeur = {}
	if not isinstance(valeur, dict):
		raise ValueError("Mise en page invalide.")
	defauts = {
		"position_photo": "apres", "largeur_photo": 65, "hauteur_photo": 65,
		"alignement_titre": "gauche", "couleur": "#087E8B", "ordre": list(ORDRE),
	}
	if set(valeur) - (set(defauts) | set(MARQUE_DEFAUTS) | set(PHOTOS_DEFAUTS) | set(QR_DEFAUTS)):
		raise ValueError("Réglage de mise en page inconnu.")
	resultat = {**defauts, **copy.deepcopy(valeur)}
	if resultat["position_photo"] not in ("avant", "apres", "gauche", "droite"):
		raise ValueError("Position de photo invalide.")
	if resultat["alignement_titre"] not in ("gauche", "centre", "droite"):
		raise ValueError("Alignement de titre invalide.")
	if not isinstance(resultat["couleur"], str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", resultat["couleur"]):
		raise ValueError("Choisissez une couleur au format #RRGGBB.")
	resultat["couleur"] = resultat["couleur"].upper()
	for champ, maximum in (("largeur_photo", 80), ("hauteur_photo", 120)):
		v = resultat[champ]
		if isinstance(v, bool) or not isinstance(v, int) or not 20 <= v <= maximum:
			raise ValueError(f"{champ} doit être un entier entre 20 et {maximum}.")
	if resultat["position_photo"] in ("gauche", "droite"):
		resultat["largeur_photo"] = min(resultat["largeur_photo"], 55)
	ordre = resultat["ordre"]
	if not isinstance(ordre, list) or len(ordre) != len(ORDRE) or any(not isinstance(k, str) for k in ordre) or set(ordre) != set(ORDRE):
		raise ValueError("Chaque bloc doit apparaître exactement une fois dans la mise en page.")
	marque = {**MARQUE_DEFAUTS, **{k: v for k, v in valeur.items() if k in MARQUE_DEFAUTS}}
	if marque["position_marque"] not in ("avant_titre", "apres_titre", "fin_document", "masquee", "libre"):
		raise ValueError("Position de la zone de marque invalide.")
	if marque["alignement_marque"] not in ("gauche", "centre", "droite"):
		raise ValueError("Alignement de la zone de marque invalide.")
	largeur = marque["largeur_logo"]
	if isinstance(largeur, bool) or not isinstance(largeur, int) or not 10 <= largeur <= 70:
		raise ValueError("La largeur du logo doit être un entier entre 10 et 70 mm.")
	if type(marque["afficher_nom_marque"]) is not int or marque["afficher_nom_marque"] not in (0, 1):
		raise ValueError("L’affichage du nom de marque doit être activé ou désactivé.")
	for cle, limite in (("logo_x", 210), ("logo_y", 297)):
		v = marque[cle]
		if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= limite:
			raise ValueError("Les coordonnées du logo doivent être comprises dans la page A4, en millimètres.")
		marque[cle] = round(v, 1)
	if marque["position_marque"] == "libre":
		marque["logo_x"] = min(marque["logo_x"], 210 - largeur)
		marque["logo_y"] = min(marque["logo_y"], math.floor((297 - hauteur_zone_marque(marque)) * 10) / 10)
	# Ne pas périmer les versions existantes pour un nouveau réglage resté à sa valeur initiale.
	for cle, valeur_marque in marque.items():
		if valeur_marque == MARQUE_DEFAUTS[cle]:
			resultat.pop(cle, None)
		else:
			resultat[cle] = valeur_marque
	for cle, defaut in PHOTOS_DEFAUTS.items():
		v = valeur.get(cle, defaut)
		if cle == "photo_grande":
			# La photo en grand de la mosaïque (fichier de la galerie) ; vide = la première de la galerie.
			if not isinstance(v, str) or len(v) > 500 or (v and not re.fullmatch(r"/(?:private/)?files/[^\s\"'<>]+", v)):
				raise ValueError("Photo de la mosaïque invalide.")
			v = v.strip()
		else:
			admis = {"photos_variantes": (0, 1, 2), "colonnes_photos": (1, 2, 3, 4), "hauteur_vignettes": range(25, 91),
				"style_galerie": ("grille", "mosaique"), "tableau_variantes": ("liste", "croise"), "largeur_grande": range(30, 76),
				"legendes_galerie": (0, 1), "legende_alignement": ("gauche", "centre", "droite"), "largeur_mosaique": range(50, 101), "libelle_croise": ("reference", "nom", "nom_sans_parent"),
				"legende_couleur": ("texte", "titres", "gris")}[cle]
			textuel = cle in ("style_galerie", "tableau_variantes", "legende_alignement", "legende_couleur", "libelle_croise")
			if (type(v) is not int if not textuel else not isinstance(v, str)) or v not in admis:
				raise ValueError("Présentation des photos invalide.")
		if v == defaut:
			resultat.pop(cle, None)
		else:
			resultat[cle] = v
	qr = {**QR_DEFAUTS, **{k: v for k, v in valeur.items() if k in QR_DEFAUTS}}
	for cle, limite in (("qr_url", 500), ("qr_legende", 120)):
		if not isinstance(qr[cle], str) or len(qr[cle]) > limite:
			raise ValueError(f"{cle} doit être un texte de {limite} caractères au maximum.")
		qr[cle] = qr[cle].strip()
	if qr["qr_url"] and not QR_URL.fullmatch(qr["qr_url"]):
		raise ValueError("L’adresse du QR code doit être un lien internet complet (https://…).")
	if qr["qr_position"] not in ("avant_titre", "apres_titre", "fin_document", "illustrations"):
		raise ValueError("Position du QR code invalide.")
	if qr["qr_alignement"] not in ("gauche", "centre", "droite"):
		raise ValueError("Alignement du QR code invalide.")
	t = qr["qr_taille"]
	if isinstance(t, bool) or not isinstance(t, int) or not 15 <= t <= 40:
		raise ValueError("La taille du QR code doit être un entier entre 15 et 40 mm.")
	for cle, v in qr.items():
		if v == QR_DEFAUTS[cle]:
			resultat.pop(cle, None)
		else:
			resultat[cle] = v
	return resultat


def configuration(valeur):
	if valeur in (None, ""):
		return {}
	if isinstance(valeur, str):
		valeur = json.loads(valeur)
	if not isinstance(valeur, dict) or set(valeur) - {"fiche", "manuel"}:
		raise ValueError("Les mises en page doivent correspondre à la fiche et au manuel.")
	return {cle: normaliser(v) for cle, v in valeur.items()}


def pour_document(dossier, genre):
	return normaliser(configuration(dossier.get("mises_en_page")).get(TYPES[genre]))


def appliquer(ctx, dossier, genre):
	resultat = copy.deepcopy(ctx)
	disposition = pour_document(dossier, genre)
	if disposition == normaliser():
		resultat.pop("mise_en_page", None)
	else:
		resultat["mise_en_page"] = disposition
	return resultat
