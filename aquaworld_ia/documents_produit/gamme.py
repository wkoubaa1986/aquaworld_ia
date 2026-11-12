"""« Gamme et configurations » : le texte qui introduit le tableau des variantes (demande 12/11/2026 : « quand le
produit est parent et a des configurations, je veux que cette partie soit mieux rédigée pour mettre en évidence
ces variétés »).

Avant, l'IA écrivait une rubrique libre qui recopiait les noms des configurations, loin du tableau qui les montre
déjà. Désormais le bloc des variantes porte un seul titre, un texte d'introduction (`contenu["gamme"]`) puis le
tableau. Le texte explique comment la gamme se décline et ce que change chaque option ; il n'énumère pas les
variantes. Les NOMBRES (variantes, valeurs par attribut) sont comptés ici et fournis à l'IA : elle les reprend,
elle ne les compte pas.

Module PUR.
"""

from __future__ import annotations

LIMITE = 3000

CONSIGNE = """Quand contexte.gamme est fourni, le produit se décline en plusieurs variantes : rédige aussi « gamme », le texte d'introduction du tableau des variantes (3 à 6 phrases, en un ou deux paragraphes, sans liste à puces ni titre).
Ce texte dit comment la gamme se décline : les axes de choix (contexte.gamme.axes, un par attribut) et leurs nombres sont comptés par le système — reprends ces nombres tels quels, ne recompte rien ; puis ce que chaque option change pour l'utilisateur, d'après les données fournies ; enfin une phrase qui aide à choisir. Une option dont les données ne disent rien est seulement nommée, sans effet inventé.
N'énumère pas les variantes ni les configurations une à une : le tableau du système, placé juste après, le fait. Ne crée dans sections aucune rubrique qui liste les variantes, les configurations ou les options de la gamme : « gamme » la remplace."""


def axes(variantes):
	"""Ce que le système compte pour l'IA : {"nombre_variantes": n, "axes": [{"attribut", "nombre", "valeurs"}]} —
	un axe par attribut qui prend au moins deux valeurs ; {} sous deux variantes (pas de gamme à présenter)."""
	variantes = list(variantes or [])
	if len(variantes) < 2:
		return {}
	valeurs = {}
	for v in variantes:
		for a in v.get("attributs", []):
			liste = valeurs.setdefault(a.get("nom", ""), [])
			if a.get("valeur") and a["valeur"] not in liste:
				liste.append(a["valeur"])
	marques = list(dict.fromkeys((v.get("marque") or v.get("brand")) for v in variantes if v.get("marque") or v.get("brand")))
	resultat = {"nombre_variantes": len(variantes),
		"axes": [{"attribut": nom, "nombre": len(liste), "valeurs": liste} for nom, liste in valeurs.items() if nom and len(liste) >= 2]}
	if len(marques) >= 2:
		resultat["marques_commerciales"] = marques
	return resultat


def nombres_a_confirmer(texte, connus):
	"""Les nombres du texte absents de `connus` (données fournies à l'IA) -> liste, dans l'ordre. `connus` vient de
	variantes.nombres_connus : chiffres et nombres écrits en lettres."""
	from aquaworld_ia.documents_produit import illustrations as I

	return I.nombres_inconnus(I._nombres(texte or ""), connus)
