"""Estimation du coût d'un appel — fonctions PURES, grille de tarifs injectée.

Les tarifs OpenAI bougent : ils vivent dans `Aquaworld IA Reglages` (modifiables) et cette grille
n'est qu'un défaut plausible. L'estimation sert au plafond mensuel et à l'affichage, pas à la
facturation.
"""

from __future__ import annotations

TARIFS_DEFAUT = {
	# USD par million de jetons (ordre de grandeur gpt-4o-mini)
	"entree_par_million": 0.15,
	"sortie_par_million": 0.60,
	# USD par image gpt-image-1 selon la qualité (1024×1024 à 1536×1024)
	"image": {"low": 0.02, "medium": 0.07, "high": 0.25},
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


def tarifs_depuis_reglages(reglages) -> dict:
	"""Lit la grille dans le Single ; toute valeur vide ou nulle retombe sur le défaut."""

	def val(champ, defaut):
		try:
			v = float(getattr(reglages, champ, None) or 0)
		except (TypeError, ValueError):
			v = 0
		return v if v > 0 else defaut

	d = TARIFS_DEFAUT
	return {
		"entree_par_million": val("prix_entree_par_million", d["entree_par_million"]),
		"sortie_par_million": val("prix_sortie_par_million", d["sortie_par_million"]),
		"image": {
			"low": val("prix_image_low", d["image"]["low"]),
			"medium": val("prix_image_medium", d["image"]["medium"]),
			"high": val("prix_image_high", d["image"]["high"]),
		},
	}


def cout_variantes(nombre: int, qualite: str, tarifs: dict | None = None) -> float:
	"""Ce que coûtera une série de variantes (une image chacune) — affiché AVANT de lancer."""
	return estimer_cout(images=max(0, int(nombre or 0)), qualite=qualite, tarifs=tarifs)
