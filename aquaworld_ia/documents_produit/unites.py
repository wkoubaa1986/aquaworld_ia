"""Unités métriques dans les caractéristiques techniques (demande 12/11/2026 : « toutes les valeurs dans
caractéristiques en système international, par exemple 3.2 G transcrit en litres automatiquement »).

La conversion est un CALCUL, fait au moment de composer le document : l'IA n'y touche pas (un nombre qu'elle
aurait converti elle-même ne figurerait pas dans les données de l'article et serait refusé par les contrôles), et
le contenu enregistré garde la valeur d'origine. La valeur d'origine reste entre parenthèses — « 12,1 L (3.2 G) » —,
car le métier désigne ses produits ainsi (membrane 75 GPD, réservoir 3,2 G, tube 1/4").

Ne sont converties que les valeurs faites d'un nombre (ou d'une plage) et d'une unité connue : une référence
(« PFC-1812-75G »), un texte ou une valeur déjà métrique restent tels quels. Les pouces d'un raccord ou d'un
filetage sont une désignation, pas une longueur (un filetage 1/4" ne mesure pas 6,35 mm) : ils ne sont pas convertis.

Module PUR.
"""

from __future__ import annotations

import re
from fractions import Fraction

GALLON_US = 3.785411784   # litres
JOUR = {"fr": "jour", "en": "day"}   # autre langue : symbole international « d »

# (motif de l'unité, respecter la casse, conversion, unité métrique) — le premier motif reconnu l'emporte.
UNITES = (
	(r"GPD|gal(?:lons?)?\s*/\s*(?:j|jour|day|d)", False, lambda x: x * GALLON_US, "L/{jour}"),
	(r"GPM|gal(?:lons?)?\s*/\s*min", False, lambda x: x * GALLON_US, "L/min"),
	(r"G", True, lambda x: x * GALLON_US, "L"),                       # « 3,2 G » ; « g » minuscule = gramme
	(r"gal\.?|gallons?|galons?", False, lambda x: x * GALLON_US, "L"),
	(r"psi", False, lambda x: x * 0.0689475729, "bar"),
	(r"\"|″|”|''|inch(?:es)?|pouces?", False, lambda x: x * 25.4, "mm"),
	(r"°\s*F", False, lambda x: (x - 32) * 5 / 9, "°C"),
	(r"lbs?", False, lambda x: x * 0.45359237, "kg"),
	(r"ft|pieds?", False, lambda x: x * 0.3048, "m"),
)
POUCES = UNITES[5][0]
# Un raccord ou un filetage en pouces est une désignation nominale.
DESIGNATION_NOMINALE = re.compile(r"raccord|filet|taraud|connex|connect|entr[ée]e|sortie|\bports?\b|npt|bsp|inlet|outlet|thread|fitting", re.I)
_NOMBRE = r"(?:\d+\s+\d+\s*/\s*\d+|\d+\s*/\s*\d+|\d{1,3}(?:[   ]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)"
_VALEUR = re.compile(r"^\s*(" + _NOMBRE + r")(?:\s*(?:-|–|—|à|to)\s*(" + _NOMBRE + r"))?\s*(.+?)\s*$")


def _nombre(texte):
	"""« 3,2 », « 3.2 », « 1 500 », « 1/4 », « 1 1/2 » -> float."""
	texte = texte.strip()
	if "/" in texte:
		entier, _, fraction = texte.rpartition(" ")
		return float((Fraction(entier.strip()) if entier.strip() else 0) + Fraction(re.sub(r"\s+", "", fraction)))
	return float(re.sub(r"[   ]", "", texte).replace(",", "."))


def _ecrire(x, langue):
	"""Trois chiffres significatifs, sans zéros inutiles, virgule décimale hors de l'anglais."""
	if x == 0:
		return "0"
	texte = f"{float(f'{x:.3g}'):f}".rstrip("0").rstrip(".")
	return texte if (langue or "fr").lower().startswith("en") else texte.replace(".", ",")


def convertir(valeur, unite="", nom="", langue="fr"):
	"""-> « valeur métrique unité », ou None si rien n'est à convertir."""
	texte = " ".join(f"{valeur or ''} {unite or ''}".split())
	m = _VALEUR.match(texte)
	if not m:
		return None
	for motif, casse, conversion, metrique in UNITES:
		if not re.fullmatch(motif, m.group(3), 0 if casse else re.I):
			continue
		if motif == POUCES and DESIGNATION_NOMINALE.search(nom or ""):
			return None
		try:
			nombres = [_ecrire(conversion(_nombre(n)), langue) for n in (m.group(1), m.group(2)) if n]
		except (ValueError, ZeroDivisionError):
			return None
		code = (langue or "fr").lower().split("-")[0]
		return "–".join(nombres) + " " + metrique.replace("{jour}", JOUR.get(code, "d"))
	return None


def afficher(valeur, unite="", nom="", langue="fr"):
	"""La valeur d'une caractéristique telle qu'elle est imprimée : métrique d'abord, valeur d'origine entre
	parenthèses ; inchangée si elle n'est pas à convertir."""
	origine = " ".join(f"{valeur or ''} {unite or ''}".split())
	metrique = convertir(valeur, unite, nom, langue)
	return f"{metrique} ({origine})" if metrique else origine
