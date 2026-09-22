"""Les prompts envoyés à gpt-image-1 — purs, testés.

Règle absolue : l'IA ne dessine NI texte, NI logo, NI code-barres, NI pictogramme. Tout cela est
posé en vectoriel sur le PDF final (composition.py). L'IA fournit l'illustration et l'ambiance.
"""

from __future__ import annotations

INTERDITS = ("text", "letters", "numbers", "words", "logos", "barcodes", "icons", "watermarks")


def interdits() -> tuple[str, ...]:
	return INTERDITS


def clause_interdiction() -> str:
	return ("Absolutely no " + ", no ".join(INTERDITS) + " anywhere in the image. "
	        "Flat, straight-on front view, edge-to-edge artwork, no box perspective, no mockup, no shadows of a box.")


def _style(style: dict, palette=None) -> str:
	morceaux = []
	if style.get("titre"):
		morceaux.append("Style: %s." % style["titre"])
	if style.get("description"):
		morceaux.append(style["description"].strip().rstrip(".") + ".")
	if style.get("ambiance"):
		morceaux.append("Mood: %s." % style["ambiance"])
	couleurs = palette or style.get("palette")
	if couleurs:
		if isinstance(couleurs, (list, tuple)):
			couleurs = ", ".join(str(c) for c in couleurs)
		morceaux.append("Color palette: %s." % couleurs)
	return " ".join(morceaux)


def prompt_variante(style: dict, produit: str, marque: str = "", face: str = "avant", palette=None,
                    brief: str = "") -> str:
	"""La face AVANT d'une variante : la photo produit est le sujet, le logo n'est qu'une
	référence de couleurs."""
	return (
		"Premium retail packaging FRONT PANEL artwork for the product \"%s\"%s. " % (
			produit, (" by the brand %s" % marque) if marque else "")
		+ _style(style, palette)
		+ (" Client brief: %s." % brief.strip().rstrip(".") if brief and brief.strip() else "")
		+ " The FIRST reference image is the product photo: it must appear as the hero element, "
		"faithfully, well lit, centered in the upper two thirds. The SECOND reference image is the "
		"brand logo: match its colors and spirit but DO NOT draw or reproduce it. "
		"Keep a calm, low-detail area in the bottom third for typography that will be added later. "
		+ clause_interdiction()
	)


def prompt_face_secondaire(style: dict, produit: str, face_code: str, palette=None) -> str:
	"""Une face secondaire dérivée de la face avant choisie (référence) : même univers, plus
	calme, avec de la place pour du texte."""
	noms = {"arriere": "BACK panel", "cote_gauche": "LEFT side panel", "cote_droit": "RIGHT side panel",
	        "dessus": "TOP panel", "dessous": "BOTTOM panel"}
	nom = noms.get(face_code, face_code)
	return (
		"Packaging %s artwork for the product \"%s\", a plain continuation of the FRONT panel "
		"given as reference image: same colors, same textures, same lighting, same style. " % (nom, produit)
		+ _style(style, palette)
		+ " Mostly quiet background suitable for text blocks, a subtle decorative element only, "
		"no product photo. " + clause_interdiction()
	)


def prompt_mockup(produit: str, style: dict | None = None) -> str:
	return (
		"Photorealistic 3D studio render of the assembled retail box for \"%s\", using EXACTLY the "
		"provided flat panel images as printed artwork: first image = front panel, second = right side "
		"panel, third = top panel. Do not alter, redraw or add anything to the panel artwork. "
		"Three-quarter view, soft studio lighting, neutral light grey background, gentle contact shadow. "
		"No extra text, no extra logos, no other objects." % produit
	)
