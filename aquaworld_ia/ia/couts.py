"""Estimation du coût d'un appel — fonctions PURES, grille de tarifs injectée.

Les tarifs OpenAI bougent : ils vivent dans `Aquaworld IA Reglages` (modifiables) et cette grille
n'est qu'un défaut plausible. L'estimation sert au plafond mensuel et à l'affichage, pas à la
facturation.
"""

from __future__ import annotations

# USD par million de jetons (entrée, sortie) selon le modèle texte. gpt-5.2 relevé sur la grille
# OpenAI le 23/09/2026 ; les autres sont la grille de 2025, à vérifier si on les remet en service.
# Correspondance par préfixe, le plus long d'abord : « gpt-5.2-2026-01-15 » prend la ligne gpt-5.2.
TARIFS_TEXTE_PAR_MODELE = {
	"gpt-5.2-pro": (10.50, 84.00),
	"gpt-5.2": (1.75, 14.00),
	"gpt-5-mini": (0.25, 2.00),
	"gpt-5-nano": (0.05, 0.40),
	"gpt-5": (1.25, 10.00),
	"gpt-4.1-mini": (0.40, 1.60),
	"gpt-4o-mini": (0.15, 0.60),
	"gpt-4o": (2.50, 10.00),
}
MODELE_TEXTE_REFERENCE = "gpt-5.2"

TARIFS_DEFAUT = {
	# USD par million de jetons : gpt-5.2, le modèle texte en service (voir TARIFS_TEXTE_PAR_MODELE)
	"entree_par_million": TARIFS_TEXTE_PAR_MODELE[MODELE_TEXTE_REFERENCE][0],
	"sortie_par_million": TARIFS_TEXTE_PAR_MODELE[MODELE_TEXTE_REFERENCE][1],
	# USD par image gpt-image-2 en 1024×1024 (grille OpenAI de septembre 2026) ; gpt-image-1
	# coûtait 0,02 / 0,07 / 0,25. Une image 1536 px coûte un peu plus : l'estimation reste
	# indicative, le plafond se lit sur le journal.
	"image": {"low": 0.006, "medium": 0.053, "high": 0.211},
}


def estimer_cout(jetons_entree: int = 0, jetons_sortie: int = 0, images: int = 0,
                 qualite: str | None = None, tarifs: dict | None = None) -> float:
	t = tarifs or TARIFS_DEFAUT
	cout = (jetons_entree or 0) / 1e6 * float(t.get("entree_par_million") or 0)
	cout += (jetons_sortie or 0) / 1e6 * float(t.get("sortie_par_million") or 0)
	if images:
		grille = t.get("image") or {}
		prix = grille.get((qualite or "medium").lower())
		if prix is None:
			prix = grille.get("medium") or 0
		cout += images * float(prix)
	return round(cout, 4)


def tarifs_texte(modele: str | None) -> tuple[float, float]:
	"""(entrée, sortie) USD / million pour un modèle texte, par préfixe ; inconnu = gpt-5.2."""
	nom = (modele or "").strip().lower()
	for prefixe in sorted(TARIFS_TEXTE_PAR_MODELE, key=len, reverse=True):
		if nom == prefixe or nom.startswith(prefixe + "-"):
			return TARIFS_TEXTE_PAR_MODELE[prefixe]
	return TARIFS_TEXTE_PAR_MODELE[MODELE_TEXTE_REFERENCE]


def tarifs_depuis_reglages(reglages, modele: str | None = None) -> dict:
	"""Lit la grille dans le Single. Jetons : une valeur saisie (> 0) l'emporte, sinon la grille
	intégrée du modèle texte `modele` (celui de l'appel, ou celui des réglages). Images : toute
	valeur vide ou nulle retombe sur le défaut."""

	def val(champ, defaut):
		try:
			v = float(getattr(reglages, champ, None) or 0)
		except (TypeError, ValueError):
			v = 0
		return v if v > 0 else defaut

	d = TARIFS_DEFAUT
	entree, sortie = tarifs_texte(modele or getattr(reglages, "modele_texte", None))
	return {
		"entree_par_million": val("prix_entree_par_million", entree),
		"sortie_par_million": val("prix_sortie_par_million", sortie),
		"image": {
			"low": val("prix_image_low", d["image"]["low"]),
			"medium": val("prix_image_medium", d["image"]["medium"]),
			"high": val("prix_image_high", d["image"]["high"]),
		},
	}


def cout_variantes(nombre: int, qualite: str, tarifs: dict | None = None) -> float:
	"""Ce que coûtera une série de variantes (une image chacune) — affiché AVANT de lancer."""
	return estimer_cout(images=max(0, int(nombre or 0)), qualite=qualite, tarifs=tarifs)
