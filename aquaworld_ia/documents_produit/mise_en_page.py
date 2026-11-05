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
	if set(valeur) - (set(defauts) | set(MARQUE_DEFAUTS)):
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
