"""Étape 1 du design : l'IA reformule les caractéristiques saisies (sans en inventer), les
traduit dans les langues demandées et propose N styles graphiques — un seul appel chat JSON.
L'utilisateur relit et corrige les textes AVANT toute image : ce qui s'imprime est validé par
un humain.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cint

from aquaworld_ia.ia import journal
from aquaworld_ia.ia.chat import chat_json
from aquaworld_ia.ia.client import reglages

CLES_TEXTES = ("accroche", "caracteristiques", "avertissements", "contact")


def lignes(texte: str) -> list[str]:
	return [l.strip() for l in (texte or "").splitlines() if l.strip()]


def prompt_preparation(nom_produit: str, marque: str, caracteristiques: list[str], avertissements: list[str],
                       contact: str, langues: list[dict], brief: str, palette: str, nb_styles: int) -> tuple[str, str]:
	"""-> (système, utilisateur). Pur."""
	codes = ", ".join("%s (%s)" % (l.get("code"), l.get("libelle") or l.get("code")) for l in langues)
	systeme = "\n".join([
		"Tu es un concepteur-rédacteur packaging. On te donne un produit, ses caractéristiques brutes et un brief.",
		"Tâche 1 — TEXTES, pour CHACUNE des langues demandées (%s) :" % codes,
		"- accroche : une phrase courte (≤ 8 mots) pour la face avant ;",
		"- caracteristiques : les caractéristiques REFORMULÉES, une par entrée, courtes et imprimables ; "
		"n'invente AUCUNE caractéristique, ne supprime aucune valeur chiffrée ni unité ;",
		"- avertissements : les avertissements fournis, reformulés sans en retirer ; si la liste est vide, "
		"propose les 2 mentions standard les plus pertinentes pour ce type de produit ;",
		"- contact : le contact fourni, tel quel (ne pas traduire les noms, adresses, numéros).",
		"Tâche 2 — STYLES : propose exactement %d directions graphiques distinctes pour l'emballage, chacune avec "
		"titre (2-4 mots), description (2 phrases, en français), ambiance (3 mots en anglais), palette (3-4 couleurs hex)." % nb_styles,
		"Réponds UNIQUEMENT en JSON : {\"textes\": {\"<code langue>\": {\"accroche\": str, \"caracteristiques\": [str], "
		"\"avertissements\": [str], \"contact\": str}}, \"styles\": [{\"titre\": str, \"description\": str, \"ambiance\": str, \"palette\": [str]}]}",
	])
	utilisateur = json.dumps({
		"produit": nom_produit, "marque": marque or "", "caracteristiques": caracteristiques,
		"avertissements": avertissements, "contact": contact or "", "brief": brief or "",
		"palette_imposee": palette or "", "langues": [l.get("code") for l in langues],
	}, ensure_ascii=False)
	return systeme, utilisateur


def normaliser_preparation(sortie: dict, codes: list[str], nb_styles: int, repli: dict | None = None) -> tuple[dict, list]:
	"""Garantit la forme attendue quoi qu'ait rendu le modèle. Pur."""
	textes_brut = sortie.get("textes") if isinstance(sortie, dict) else None
	textes = {}
	for code in codes:
		t = (textes_brut or {}).get(code) if isinstance(textes_brut, dict) else None
		t = t if isinstance(t, dict) else {}
		textes[code] = {
			"accroche": str(t.get("accroche") or (repli or {}).get("accroche") or "").strip(),
			"caracteristiques": [str(x).strip() for x in (t.get("caracteristiques") or (repli or {}).get("caracteristiques") or []) if str(x).strip()],
			"avertissements": [str(x).strip() for x in (t.get("avertissements") or (repli or {}).get("avertissements") or []) if str(x).strip()],
			"contact": str(t.get("contact") or (repli or {}).get("contact") or "").strip(),
		}
	styles_brut = sortie.get("styles") if isinstance(sortie, dict) else None
	styles = []
	for s in (styles_brut or [])[:nb_styles] if isinstance(styles_brut, list) else []:
		if not isinstance(s, dict):
			continue
		palette = s.get("palette")
		if isinstance(palette, list):
			palette = ", ".join(str(c) for c in palette)
		styles.append({"titre": str(s.get("titre") or "Style").strip(), "description": str(s.get("description") or "").strip(),
		               "ambiance": str(s.get("ambiance") or "").strip(), "palette": str(palette or "").strip()})
	while len(styles) < nb_styles:
		styles.append({"titre": "Style %d" % (len(styles) + 1), "description": "", "ambiance": "", "palette": ""})
	return textes, styles


def html_textes(textes: dict, langues: dict) -> str:
	"""Rendu lisible des textes préparés, une colonne par langue. Pur."""
	if not textes:
		return "<p class='text-muted'>%s</p>" % _("Aucun texte préparé : cliquez « 1. Préparer textes et styles ».")
	esc = frappe.utils.escape_html
	cols = []
	for code, t in textes.items():
		info = langues.get(code) or {}
		rtl = " dir='rtl' style='text-align:right'" if info.get("rtl") else ""
		cols.append(
			"<div class='aqia-col'><h6>%s</h6>" % esc(info.get("libelle") or code)
			+ "<p%s><b>%s</b></p>" % (rtl, esc(t.get("accroche") or ""))
			+ "<ul%s>%s</ul>" % (rtl, "".join("<li>%s</li>" % esc(x) for x in t.get("caracteristiques") or []))
			+ "<p class='text-muted small'>%s</p>" % esc(_("Avertissements"))
			+ "<ul%s class='small'>%s</ul>" % (rtl, "".join("<li>%s</li>" % esc(x) for x in t.get("avertissements") or []))
			+ "<p%s class='small'>%s</p></div>" % (rtl, esc(t.get("contact") or ""))
		)
	return "<div class='aqia-textes'>%s</div>" % "".join(cols)


def _langues_du_design(doc) -> list[dict]:
	codes = [l.langue for l in (doc.get("langues") or []) if l.langue] or ["fr"]
	infos = []
	for code in codes:
		d = frappe.db.get_value("Aquaworld IA Langue", code,
		                        ["code", "libelle", "libelle_natif", "rtl", "police", "police_fichier"], as_dict=True)
		infos.append(d or {"code": code, "libelle": code, "rtl": 0})
	return infos


@frappe.whitelist()
def preparer(design: str) -> dict:
	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("write")
	journal.verifier_plafond()
	nb = max(1, min(cint(doc.nb_variantes) or 3, cint(getattr(reglages(), "variantes_max", 4)) or 4))
	langues_infos = _langues_du_design(doc)
	systeme, utilisateur = prompt_preparation(
		doc.nom_produit or doc.article, doc.marque, lignes(doc.caracteristiques), lignes(doc.avertissements),
		doc.contact or getattr(reglages(), "contact_par_defaut", "") or "", langues_infos,
		doc.brief_style, doc.palette, nb)
	sortie = chat_json(systeme, utilisateur, fonctionnalite="Emballage texte", doc=doc)
	repli = {"caracteristiques": lignes(doc.caracteristiques), "avertissements": lignes(doc.avertissements),
	         "contact": doc.contact or ""}
	textes, styles = normaliser_preparation(sortie, [l["code"] for l in langues_infos], nb, repli)
	doc.textes_ia = json.dumps(textes, ensure_ascii=False)
	# On ne touche pas aux variantes déjà générées (elles ont coûté) : on remplace seulement
	# celles encore « À générer » / en échec, et on complète jusqu'au nombre demandé.
	from aquaworld_ia.emballage.prompts import prompt_variante

	for v in [v for v in doc.variantes if v.statut in ("À générer", "Échec")]:
		doc.remove(v)
	numero = max([v.numero or 0 for v in doc.variantes] + [0])
	for s in styles:
		if len(doc.variantes) >= nb:
			break
		numero += 1
		doc.append("variantes", {
			"numero": numero, "titre": s["titre"], "description": s["description"], "statut": "À générer",
			"prompt": prompt_variante(s, doc.nom_produit or doc.article, doc.marque or "",
			                          palette=doc.palette or s.get("palette"), brief=doc.brief_style or ""),
		})
	if doc.statut in ("Brouillon", "Textes prêts", "Échec"):
		doc.statut = "Textes prêts"
	doc.save(ignore_permissions=True)
	return {"textes": textes, "styles": styles, "statut": doc.statut}


@frappe.whitelist()
def enregistrer_textes(design: str, textes) -> dict:
	"""Les textes corrigés par l'utilisateur (dialogue « Modifier les textes »)."""
	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("write")
	textes = frappe.parse_json(textes) if isinstance(textes, str) else textes
	codes = list((textes or {}).keys())
	propres, _styles = normaliser_preparation({"textes": textes}, codes, 0)
	doc.textes_ia = json.dumps(propres, ensure_ascii=False)
	doc.save(ignore_permissions=True)
	return propres


@frappe.whitelist()
def rendu_textes(design: str) -> str:
	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("read")
	textes = frappe.parse_json(doc.textes_ia) if doc.textes_ia else {}
	langues = {l["code"]: l for l in _langues_du_design(doc)}
	return html_textes(textes or {}, langues)
