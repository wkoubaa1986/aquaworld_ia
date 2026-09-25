"""Mise en forme ligne par ligne des textes imprimés (demande utilisateur 24/09/2026 : « plusieurs
tailles ligne par ligne, italique ou gras, et choisir la police »).

Une ligne mise en forme commence par un préfixe entre accolades :

	{14pt, gras, italique, sans puce, police: Montserrat} Débit 500 L/h

Le préfixe voyage AVEC son texte (champ brut, textes préparés par l'IA, dialogue « Modifier les
textes ») : insérer une ligne ne décale aucune mise en forme. Une ligne sans préfixe garde la règle
automatique (intertitre = tout en capitales, ou terminé par « : »). Un préfixe illisible n'en est
pas un : la ligne s'imprime telle quelle, accolades comprises.

L'éditeur du studio (studio_emballage.js, `EditeurLignes`) lit et écrit exactement cette syntaxe.
"""

from __future__ import annotations

import re

TAILLE_MIN, TAILLE_MAX = 4.0, 72.0
_PREFIXE = re.compile(r"^\s*\{([^{}]*)\}[ \t]?(.*)$", re.S)
_TAILLE = re.compile(r"(\d{1,2}(?:\.\d{1,2})?)\s*pt")
_POLICE = re.compile(r"police\s*[:=]\s*(.+)", re.I)
#: Une police se nomme en lettres, chiffres, espaces, points et tirets : ni virgule ni accolade,
#: qui casseraient le préfixe, ni guillemet, qui casserait le CSS.
NOM_POLICE = re.compile(r"[\w][\w .\-]{0,60}")

#: Le style implicite d'un intertitre sans préfixe : gras, sans puce.
STYLE_INTERTITRE = {"gras": True, "puce": False}


def analyser(ligne: str | None) -> tuple[dict | None, str]:
	"""-> (style, texte). `style` vaut None pour une ligne sans préfixe (règles automatiques), sinon
	un dict {taille?, gras?, italique?, puce?, police?} — {} pour « {normal} ». Pur."""
	ligne = ligne or ""
	m = _PREFIXE.match(ligne)
	if not m:
		return None, ligne
	style = {}
	# « 9,5 pt » : la virgule décimale n'est pas un séparateur de jetons.
	for jeton in (j.strip() for j in re.sub(r"(\d),(\d)", r"\1.\2", m.group(1)).split(",")):
		bas = jeton.lower()
		if not bas or bas == "normal":
			continue
		taille = _TAILLE.fullmatch(bas)
		police = _POLICE.fullmatch(jeton)
		if taille:
			valeur = float(taille.group(1))
			if not TAILLE_MIN <= valeur <= TAILLE_MAX:
				return None, ligne
			style["taille"] = valeur
		elif bas in ("gras", "bold"):
			style["gras"] = True
		elif bas in ("italique", "italic"):
			style["italique"] = True
		elif bas in ("sans puce", "no bullet"):
			style["puce"] = False
		elif bas in ("puce", "bullet"):
			style["puce"] = True
		elif police and NOM_POLICE.fullmatch(police.group(1).strip()):
			style["police"] = police.group(1).strip()
		else:
			return None, ligne
	return style, m.group(2).strip()


def ecrire(style: dict | None, texte: str) -> str:
	"""La ligne avec son préfixe ; sans style (None), le texte seul. Pur."""
	texte = (texte or "").strip()
	if style is None:
		return texte
	jetons = []
	if style.get("taille"):
		jetons.append("%gpt" % float(style["taille"]))
	if style.get("gras"):
		jetons.append("gras")
	if style.get("italique"):
		jetons.append("italique")
	if style.get("puce") is False:
		jetons.append("sans puce")
	elif style.get("puce") is True:
		jetons.append("puce")
	if style.get("police"):
		jetons.append("police: %s" % style["police"])
	return "{%s} %s" % (", ".join(jetons) or "normal", texte)


def texte_seul(ligne: str | None) -> str:
	return analyser(ligne)[1].strip()


def est_intertitre(texte: str) -> bool:
	"""Un intertitre du texte brut : tout en capitales (3 lettres au moins) ou terminé par « : »
	(« SPECIFICATIONS », « Inlet : »). Pur."""
	t = (texte or "").strip()
	lettres = [c for c in t if c.isalpha()]
	return (len(lettres) >= 3 and all(c.isupper() for c in lettres)) or t.endswith(":")


def style_a_reporter(ligne: str) -> dict | None:
	"""Le style qu'une ligne BRUTE transmet à sa traduction : son préfixe, sinon le style implicite
	d'un intertitre, sinon rien. Pur."""
	style, texte = analyser(ligne)
	if style is not None:
		return style
	return dict(STYLE_INTERTITRE) if est_intertitre(texte) else None


def reporter(brutes: list[str], cibles: list[str], indices: list[int] | None = None) -> list[str] | None:
	"""Les lignes `cibles` (une langue des textes préparés) avec la mise en forme des lignes
	`brutes`, rang pour rang ; None si les deux listes n'ont pas le même nombre de lignes — une
	traduction fusionnée ou éclatée par l'IA ne se laisse pas apparier. `indices` : ne reporter
	que ces rangs (les lignes dont la mise en forme brute vient de changer). Pur."""
	if len(brutes) != len(cibles):
		return None
	out = list(cibles)
	for k in range(len(brutes)) if indices is None else indices:
		out[k] = ecrire(style_a_reporter(brutes[k]), texte_seul(cibles[k]))
	return out


def lignes_non_vides(texte: str | None) -> list[str]:
	return [l.strip() for l in (texte or "").splitlines() if l.strip()]


def lignes_imprimables(brut: str | None) -> list[str]:
	"""Les caractéristiques brutes prêtes à remplacer celles d'une langue préparée : les intertitres
	automatiques (capitales, « : ») reçoivent un préfixe explicite, car dans les textes préparés
	seul le préfixe compte. Pur."""
	return [ecrire(style_a_reporter(l), texte_seul(l)) for l in lignes_non_vides(brut)]


def reporter_styles(brut: str | None, textes: dict, avant: str | None = None) -> tuple[dict, list[str]]:
	"""Reporte la mise en forme des caractéristiques brutes sur chaque langue des textes préparés.
	Avec `avant` (le brut précédent), seuls les rangs dont la mise en forme a changé sont reportés :
	une retouche faite langue par langue dans « Modifier les textes » n'est pas écrasée par une
	modification sans rapport ; et rien n'est reporté quand des lignes ont été ajoutées ou retirées
	(l'appariement rang pour rang n'est plus sûr). -> (textes, codes des langues non appariées). Pur."""
	brutes = lignes_non_vides(brut)
	indices = None
	if avant is not None:
		anciennes = lignes_non_vides(avant)
		if len(anciennes) != len(brutes):
			return textes, []
		indices = [k for k in range(len(brutes)) if style_a_reporter(anciennes[k]) != style_a_reporter(brutes[k])]
		if not indices:
			return textes, []
	sortie, non_apparies = {}, []
	for code, t in (textes or {}).items():
		t = dict(t or {})
		cibles = list(t.get("caracteristiques") or [])
		nouvelles = reporter(brutes, cibles, indices)
		if nouvelles is None:
			non_apparies.append(code)
		else:
			t["caracteristiques"] = nouvelles
		sortie[code] = t
	return sortie, non_apparies


def desalignes(brut: str | None, textes: dict) -> list[dict]:
	"""Les langues préparées dont le nombre de caractéristiques diffère du brut, quand le brut porte
	une mise en forme explicite (sinon il n'y a rien à reporter) : le studio le signale. Pur."""
	brutes = lignes_non_vides(brut)
	if not any(analyser(l)[0] is not None for l in brutes):
		return []
	return [{"code": code, "lignes": len((t or {}).get("caracteristiques") or []), "brutes": len(brutes)}
	        for code, t in (textes or {}).items() if len((t or {}).get("caracteristiques") or []) != len(brutes)]
