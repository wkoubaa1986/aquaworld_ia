"""Traduction des paragraphes par lots (chat JSON), avec vérification et replis.

Le modèle rend `{"items": [{"i": 0, "t": "…"}, …]}` avec EXACTEMENT les indices reçus : c'est ce
qui permet de remettre chaque traduction dans sa boîte. Un lot qui ne passe pas la vérification
est réessayé, puis scindé en deux, puis laissé en anglais et signalé — jamais silencieusement
faux.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable

from aquaworld_ia.ia.chat import chat_json
from aquaworld_ia.manuels.extraction import dedoublonner, est_traduisible, repartir_lots


def prompt_systeme(langue: dict, glossaire: str = "", instructions: str = "", contexte: str = "") -> str:
	nom = langue.get("libelle_natif") or langue.get("libelle") or langue.get("code", "")
	lignes = [
		"Tu traduis un MANUEL D'UTILISATION technique de l'anglais vers : %s (code %s)." % (nom, langue.get("code", "")),
		"Règles impératives :",
		"- Traduis chaque item indépendamment ; conserve exactement la numérotation, les puces, les valeurs, "
		"les unités (V, Hz, W, mm, kg, °C), les symboles, les noms de produit et de marque, les références.",
		"- Reste proche de la longueur de l'original : la traduction doit tenir dans la même case du PDF.",
		"- Registre : notice destinée à l'utilisateur final, phrases claires, sans commentaire ni ajout.",
		"- Ne fusionne pas, ne coupe pas, ne réordonne pas les items.",
		"- Réponds UNIQUEMENT en JSON : {\"items\": [{\"i\": <indice reçu>, \"t\": \"<traduction>\"}, …]} "
		"avec exactement les mêmes indices que l'entrée, tous présents, aucun texte vide.",
	]
	if langue.get("rtl"):
		lignes.append("- Écriture de droite à gauche : écris naturellement dans la langue ; garde les chiffres en "
		              "chiffres occidentaux (0-9) et les unités telles quelles.")
	if langue.get("instructions"):
		lignes.append("- Consignes pour cette langue : %s" % langue["instructions"].strip())
	if instructions and instructions.strip():
		lignes.append("- Consignes du demandeur : %s" % instructions.strip())
	if contexte and contexte.strip():
		lignes.append("- Contexte du produit : %s" % contexte.strip())
	entrees = lignes_glossaire(glossaire)
	if entrees:
		lignes.append("- Glossaire imposé (terme anglais = traduction) : " + " ; ".join("%s = %s" % e for e in entrees))
	return "\n".join(lignes)


def lignes_glossaire(glossaire: str) -> list[tuple[str, str]]:
	entrees = []
	for ligne in (glossaire or "").splitlines():
		if "=" in ligne:
			a, b = ligne.split("=", 1)
			if a.strip() and b.strip():
				entrees.append((a.strip(), b.strip()))
	return entrees


def prompt_utilisateur(textes: list[str]) -> str:
	return json.dumps({"items": [{"i": i, "t": t} for i, t in enumerate(textes)]}, ensure_ascii=False)


_NOMBRE = re.compile(r"\d+(?:[.,]\d+)?")


def nombres(texte: str) -> set:
	return {n.replace(",", ".") for n in _NOMBRE.findall(texte or "")}


def verifier_lot(entree: list[str], sortie) -> tuple[bool, str]:
	"""Même nombre d'items, indices exacts et uniques, rien de vide, tous les nombres conservés."""
	items = sortie.get("items") if isinstance(sortie, dict) else None
	if not isinstance(items, list) or len(items) != len(entree):
		return False, "nombre d'items différent"
	vus = {}
	for item in items:
		if not isinstance(item, dict):
			return False, "item mal formé"
		i, t = item.get("i"), item.get("t")
		if not isinstance(i, int) or i in vus or not (0 <= i < len(entree)):
			return False, "indice invalide ou en double : %r" % (i,)
		if not isinstance(t, str) or not t.strip():
			return False, "traduction vide (item %d)" % i
		vus[i] = t
	for i, t in vus.items():
		manquants = nombres(entree[i]) - nombres(t)
		if manquants:
			return False, "nombre(s) perdu(s) dans l'item %d : %s" % (i, ", ".join(sorted(manquants)))
	return True, ""


def traduire_lot(textes: list[str], langue: dict, *, glossaire: str = "", instructions: str = "",
                 contexte: str = "", doc=None, essais: int = 2) -> tuple[list[str], list[int]]:
	"""-> (traductions dans l'ordre, positions laissées en anglais)."""
	systeme = prompt_systeme(langue, glossaire, instructions, contexte)
	for _essai in range(max(1, essais)):
		try:
			sortie = chat_json(systeme, prompt_utilisateur(textes), fonctionnalite="Manuel", doc=doc)
		except Exception:
			continue
		ok, _motif = verifier_lot(textes, sortie)
		if ok:
			return [item["t"] for item in sorted(sortie["items"], key=lambda x: x["i"])], []
	if len(textes) > 1:
		m = len(textes) // 2
		a, na = traduire_lot(textes[:m], langue, glossaire=glossaire, instructions=instructions,
		                     contexte=contexte, doc=doc, essais=essais)
		b, nb = traduire_lot(textes[m:], langue, glossaire=glossaire, instructions=instructions,
		                     contexte=contexte, doc=doc, essais=essais)
		return a + b, na + [m + i for i in nb]
	return list(textes), [0]


def traduire_tout(paragraphes: list[dict], langue: dict, *, glossaire: str = "", instructions: str = "",
                  contexte: str = "", doc=None, taille_lot: int = 25,
                  progression: Callable[[int, int], None] | None = None) -> tuple[dict, list[int]]:
	"""-> ({id paragraphe: traduction}, ids laissés en anglais). Les paragraphes non traduisibles
	(nombres, références…) ne figurent pas dans le dict : ils restent tels quels dans le PDF."""
	cibles = [p for p in paragraphes if est_traduisible(p["texte"])]
	uniques, index = dedoublonner(cibles)
	lots = repartir_lots(uniques, taille_lot)
	resultats, rates = {}, set()
	for k, lot in enumerate(lots):
		trad, non = traduire_lot([uniques[i] for i in lot], langue, glossaire=glossaire,
		                         instructions=instructions, contexte=contexte, doc=doc)
		for pos, i in enumerate(lot):
			resultats[i] = trad[pos]
			if pos in non:
				rates.add(i)
		if progression:
			progression(k + 1, len(lots))
	traductions = {p["id"]: resultats[index[p["id"]]] for p in cibles if index[p["id"]] not in rates}
	laisses = [p["id"] for p in cibles if index[p["id"]] in rates]
	return traductions, laisses
