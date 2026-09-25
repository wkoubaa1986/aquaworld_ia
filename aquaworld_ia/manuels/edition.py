"""L'édition d'une traduction dans le Studio manuel (demande utilisateur 24/09/2026 : « un studio
page par page, qui garde l'image du manuel d'origine et change le texte dans l'autre langue ») :
ce que l'utilisateur a corrigé, déplacé, masqué ou ajouté, par langue. JSON sur la ligne « Manuel
Article Traduction » (champ `edition`). La traduction de l'IA vit à part (`traductions`) : relancer
l'IA ne perd jamais une correction, et « Rétablir » retrouve toujours la version IA.

{
  "textes": {"12": "…"},                      # traduction corrigée à la main (prime sur l'IA)
  "blocs":  {"12": {"bbox": [x0, y0, x1, y1],  # boîte déplacée / agrandie (points PDF)
                    "taille": 9.5,             # taille maximale en points (sinon celle de l'original)
                    "traitement": "traduit" | "anglais" | "efface"}},
  "libres": [{"id": "L1", "type": "texte", "page": 8, "bbox": [...], "texte": "…", "taille": 10,
              "gras": false, "fond": true, "align": "left", "couleur": "#000000"},
             {"id": "L2", "type": "image", "page": 8, "bbox": [...], "fichier": "/private/files/…"}],
  "images": {"p8-i2": {"fichier": "/private/files/…png"}}   # illustration redessinée par l'IA
}

Tout ici est pur (testé sans PDF ni site).
"""

from __future__ import annotations

import json

TRAITEMENTS = ("traduit", "anglais", "efface")
TYPES_LIBRES = ("texte", "image")
COTE_MIN = 4.0          # une boîte plus petite (en points) n'est pas éditable
TAILLE_MIN, TAILLE_MAX = 3.0, 72.0


def vide() -> dict:
	return {"textes": {}, "blocs": {}, "libres": [], "images": {}}


def lire(texte) -> dict:
	"""Le JSON du champ -> dict complet (clés manquantes ajoutées). Un champ vide ou illisible = édition vide."""
	if isinstance(texte, dict):
		brut = texte
	else:
		try:
			brut = json.loads(texte) if texte else {}
		except (TypeError, ValueError):
			brut = {}
	if not isinstance(brut, dict):
		brut = {}
	e = vide()
	for cle in e:
		v = brut.get(cle)
		if isinstance(v, type(e[cle])):
			e[cle] = v
	return e


def ecrire(edition: dict) -> str:
	return json.dumps(edition, ensure_ascii=False)


def _nombre(v, defaut=None):
	try:
		return float(v)
	except (TypeError, ValueError):
		return defaut


def borner_bbox(bbox, format_page, cote_min: float = COTE_MIN):
	"""Une boîte [x0, y0, x1, y1] ramenée dans la page (format = [largeur, hauteur] en points), d'au
	moins `cote_min` de côté ; None si illisible."""
	if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
		return None
	vals = [_nombre(v) for v in bbox]
	if any(v is None for v in vals):
		return None
	x0, y0, x1, y1 = vals
	if x1 < x0:
		x0, x1 = x1, x0
	if y1 < y0:
		y0, y1 = y1, y0
	w, h = (format_page or [None, None])[:2]
	if w and h:
		x0 = min(max(x0, 0.0), max(0.0, w - cote_min))
		y0 = min(max(y0, 0.0), max(0.0, h - cote_min))
		x1 = min(max(x1, x0 + cote_min), w)
		y1 = min(max(y1, y0 + cote_min), h)
	else:
		x1 = max(x1, x0 + cote_min)
		y1 = max(y1, y0 + cote_min)
	return [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)]


def _taille(v):
	t = _nombre(v)
	if t is None:
		return None
	return round(min(max(t, TAILLE_MIN), TAILLE_MAX), 2)


def normaliser(edition, formats: list, page_par_bloc: dict) -> dict:
	"""L'édition telle qu'envoyée par le navigateur -> l'édition telle qu'on l'enregistre : clés
	connues seulement, identifiants en texte, boîtes bornées à leur page, tailles bornées,
	traitement connu, cases libres avec un identifiant unique. Une entrée vide disparaît."""
	e = lire(edition)
	out = vide()
	for k, t in e["textes"].items():
		if isinstance(t, str) and t.strip():
			out["textes"][str(k)] = t
	for k, b in e["blocs"].items():
		if not isinstance(b, dict):
			continue
		k = str(k)
		fmt = _format(formats, page_par_bloc.get(k))
		entree = {}
		bbox = borner_bbox(b.get("bbox"), fmt)
		if bbox:
			entree["bbox"] = bbox
		taille = _taille(b.get("taille"))
		if taille:
			entree["taille"] = taille
		if b.get("traitement") in TRAITEMENTS and b["traitement"] != "traduit":
			entree["traitement"] = b["traitement"]
		if entree:
			out["blocs"][k] = entree
	vus = set()
	for l in e["libres"]:
		if not isinstance(l, dict) or l.get("type", "texte") not in TYPES_LIBRES:
			continue
		page = int(_nombre(l.get("page"), -1))
		if page < 0 or (formats and page >= len(formats)):
			continue
		bbox = borner_bbox(l.get("bbox"), _format(formats, page))
		if not bbox:
			continue
		ident = str(l.get("id") or "").strip() or nouvel_id_libre(out)
		while ident in vus:
			ident = nouvel_id_libre(out, vus)
		vus.add(ident)
		entree = {"id": ident, "type": l.get("type", "texte"), "page": page, "bbox": bbox}
		if entree["type"] == "texte":
			entree["texte"] = l.get("texte") if isinstance(l.get("texte"), str) else ""
			entree["taille"] = _taille(l.get("taille")) or 10.0
			entree["gras"] = bool(l.get("gras"))
			entree["fond"] = bool(l.get("fond", True))
			entree["align"] = l.get("align") if l.get("align") in ("left", "center", "right") else "left"
			if isinstance(l.get("couleur"), str) and l["couleur"].startswith("#") and len(l["couleur"]) == 7:
				entree["couleur"] = l["couleur"]
		elif isinstance(l.get("fichier"), str) and l["fichier"]:
			entree["fichier"] = l["fichier"]
		out["libres"].append(entree)
	for k, im in e["images"].items():
		if isinstance(im, dict) and isinstance(im.get("fichier"), str) and im["fichier"]:
			out["images"][str(k)] = {"fichier": im["fichier"]}
	return out


def _format(formats, page):
	if page is None or not formats:
		return None
	try:
		return formats[int(page)]
	except (IndexError, TypeError, ValueError):
		return None


def nouvel_id_libre(edition: dict, pris: set | None = None) -> str:
	ids = {l.get("id") for l in edition.get("libres", [])} | set(pris or ())
	n = len(ids) + 1
	while "L%d" % n in ids:
		n += 1
	return "L%d" % n


def texte_effectif(ident, traductions: dict, edition: dict):
	"""Le texte qui s'imprime pour un paragraphe : la correction, sinon la traduction IA, sinon
	None (le bloc reste en anglais)."""
	k = str(ident)
	t = edition.get("textes", {}).get(k)
	if isinstance(t, str) and t.strip():
		return t
	t = traductions.get(k)
	return t if isinstance(t, str) and t.strip() else None


def statut_bloc(ident, traductions: dict, edition: dict, pivote: bool = False) -> str:
	"""Pour la couleur du bloc dans le studio : pivote | anglais | efface | corrige | traduit | non_traduit."""
	if pivote:
		return "pivote"
	b = edition.get("blocs", {}).get(str(ident), {})
	if b.get("traitement") in ("anglais", "efface"):
		return b["traitement"]
	if str(ident) in edition.get("textes", {}):
		return "corrige"
	return "traduit" if texte_effectif(ident, traductions, edition) else "non_traduit"


def traductions_str(traductions) -> dict:
	"""Le dict des traductions IA avec des clés texte (le JSON les rend ainsi, le job les crée en entiers)."""
	if isinstance(traductions, str):
		try:
			traductions = json.loads(traductions or "{}")
		except ValueError:
			traductions = {}
	return {str(k): v for k, v in (traductions or {}).items() if isinstance(v, str)}
