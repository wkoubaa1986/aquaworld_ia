"""Textes imprimés : une version validée par langue, séparée des propositions IA."""
from __future__ import annotations

import json

from aquaworld_ia.emballage import mise_en_forme


def objet(valeur):
	if isinstance(valeur, str):
		try:
			valeur = json.loads(valeur)
		except (ValueError, TypeError):
			return {}
	return valeur if isinstance(valeur, dict) else {}


def langues(doc):
	return list(dict.fromkeys(l.get("langue") for l in doc.get("langues") or [] if l.get("langue"))) or ["fr"]


def depuis_saisie(doc):
	return {"accroche": "", "caracteristiques": mise_en_forme.lignes_imprimables(doc.get("caracteristiques")),
	        "avertissements": mise_en_forme.lignes_imprimables(doc.get("avertissements")),
	        "contact": doc.get("contact") or ""}


def imprimes(doc):
	"""Les anciens designs gardent leurs textes imprimés jusqu’à leur première validation."""
	valides = objet(doc.get("textes_valides"))
	anciens = objet(doc.get("textes_ia")) if not valides else {}
	codes = langues(doc)
	return {c: dict((valides or anciens).get(c) or (depuis_saisie(doc) if i == 0 and not (valides or anciens) else
	        {"accroche": "", "caracteristiques": [], "avertissements": [], "contact": ""}))
	        for i, c in enumerate(codes)}


def poser(doc, textes):
	"""La saisie historique de la fiche devient le miroir de la première langue imprimée."""
	# Garder les traductions des langues temporairement décochées.
	textes = dict(objet(doc.get("textes_valides")) or objet(doc.get("textes_ia")), **textes)
	doc.textes_valides = json.dumps(textes, ensure_ascii=False)
	principal = textes.get(langues(doc)[0]) or {}
	for champ in ("caracteristiques", "avertissements"):
		doc.set(champ, "\n".join(principal.get(champ) or []))
	doc.contact = principal.get("contact") or ""


def synchroniser_saisie(doc, avant):
	"""Une modification directe depuis la fiche ou le studio modifie le texte réellement imprimé."""
	if not avant:
		return
	champs = [c for c in ("caracteristiques", "avertissements", "contact") if doc.get(c) != avant.get(c)]
	# Un éditeur de textes a déjà posé la version canonique et son miroir.
	if doc.get("textes_valides") != avant.get("textes_valides"):
		return
	langues_changees = langues(doc) != langues(avant)
	if not champs and not langues_changees:
		return
	t = dict(objet(doc.get("textes_valides")) or objet(doc.get("textes_ia")) or imprimes(avant))
	if "caracteristiques" in champs and not langues_changees:
		t, _ = mise_en_forme.reporter_styles(doc.get("caracteristiques"), t, avant=avant.get("caracteristiques"))
	base = t.setdefault(langues(doc)[0], {"accroche": "", "caracteristiques": [], "avertissements": [], "contact": ""})
	saisie = depuis_saisie(doc)
	for champ in champs:
		base[champ] = saisie[champ]
	poser(doc, t)
