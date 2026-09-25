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

from aquaworld_ia.ia.chat import chat_json, chat_json_differe
from aquaworld_ia.manuels.extraction import dedoublonner, est_traduisible, repartir_lots

#: Lots traduits en même temps (appels OpenAI = attente réseau) : une langue de 12 pages passait de
#: ~100 s à ~30 s (25/09/2026, « pourquoi c'est si long ? »). 1 = comme avant.
PARALLELE = 4


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


_SEPARATEUR_CHIFFRES = re.compile(r"(?<=\d)[.,\s\u00a0\u202f](?=\d)")


def nombres(texte: str) -> set:
	"""Les nombres d'un texte, sans leurs séparateurs : « 1,100 gallons » et « 1 100 gallons »
	(ou « 1.100 », « 1100 ») sont le même nombre. Vu le 24/09/2026 sur le manuel David 4000 :
	le français écrit les milliers avec une espace, et la vérification laissait ces blocs en
	anglais. Comparer sans séparateur garde l'essentiel : aucun chiffre perdu ni inventé."""
	return set(re.findall(r"\d+", _SEPARATEUR_CHIFFRES.sub("", texte or "")))


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
                 contexte: str = "", doc=None, essais: int = 2, contexte_ia=None, journal_differe: list | None = None) -> tuple[list[str], list[int]]:
	"""-> (traductions dans l'ordre, positions laissées en anglais). Avec `contexte_ia`
	(client, modèle, température), l'appel ne touche pas à Frappe et ses lignes de journal vont
	dans `journal_differe` : c'est la forme qui tourne dans un thread."""
	systeme = prompt_systeme(langue, glossaire, instructions, contexte)
	for _essai in range(max(1, essais)):
		if contexte_ia is not None:
			r = chat_json_differe(contexte_ia, systeme, prompt_utilisateur(textes))
			if journal_differe is not None:
				journal_differe.append(r["journal"])
			sortie = r["sortie"]
			if sortie is None:
				continue
		else:
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
		                     contexte=contexte, doc=doc, essais=essais, contexte_ia=contexte_ia, journal_differe=journal_differe)
		b, nb = traduire_lot(textes[m:], langue, glossaire=glossaire, instructions=instructions,
		                     contexte=contexte, doc=doc, essais=essais, contexte_ia=contexte_ia, journal_differe=journal_differe)
		return a + b, na + [m + i for i in nb]
	return list(textes), [0]


def traduire_tout(paragraphes: list[dict], langue: dict, *, glossaire: str = "", instructions: str = "",
                  contexte: str = "", doc=None, taille_lot: int = 25,
                  progression: Callable[[int, int], None] | None = None, parallele: int | None = None) -> tuple[dict, list[int]]:
	"""-> ({id paragraphe: traduction}, ids laissés en anglais). Les paragraphes non traduisibles
	(nombres, références…) ne figurent pas dans le dict : ils restent tels quels dans le PDF.
	Les lots partent `parallele` à la fois (threads : appels réseau) ; journal et progression
	restent dans le thread principal."""
	cibles = [p for p in paragraphes if est_traduisible(p["texte"])]
	uniques, index = dedoublonner(cibles)
	lots = repartir_lots(uniques, taille_lot)
	resultats, rates = {}, set()
	parallele = PARALLELE if parallele is None else max(1, int(parallele))
	if parallele > 1 and len(lots) > 1:
		_traduire_lots_paralleles(lots, uniques, langue, glossaire, instructions, contexte, doc, parallele, progression, resultats, rates)
	else:
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


def _traduire_lots_paralleles(lots, uniques, langue, glossaire, instructions, contexte, doc, parallele, progression, resultats, rates):
	from concurrent.futures import ThreadPoolExecutor, as_completed

	from aquaworld_ia.ia import journal
	from aquaworld_ia.ia.client import client_et_modele

	contexte_ia = client_et_modele("texte")
	journaux = {k: [] for k in range(len(lots))}

	def un_lot(k):
		return k, traduire_lot([uniques[i] for i in lots[k]], langue, glossaire=glossaire, instructions=instructions,
		                       contexte=contexte, doc=None, contexte_ia=contexte_ia, journal_differe=journaux[k])

	faits = 0
	with ThreadPoolExecutor(max_workers=parallele) as pool:
		for fut in as_completed([pool.submit(un_lot, k) for k in range(len(lots))]):
			k, (trad, non) = fut.result()
			for pos, i in enumerate(lots[k]):
				resultats[i] = trad[pos]
				if pos in non:
					rates.add(i)
			for entree in journaux[k]:
				journal.enregistrer(fonctionnalite="Manuel", doc=doc, **entree)
			faits += 1
			if progression:
				progression(faits, len(lots))
