"""Mosaïque de variantes du produit (14/10/2026).

Demande : « choisir plusieurs variantes du produit et créer une photo avec une mosaïque des produits améliorés
choisis » — comme la planche « Pour cartouche 10" × 2,5" » : colonnes TRANSPARENT / OPAQUE BLEU, lignes MODÈLE A /
MODÈLE B, « Gamme disponible · 1 porte-filtre par boîte » en pied ; ou une autre disposition.

Une configuration (JSON, gardée sur le design dans `mosaique` pour la reprendre) :
    {"disposition": "grille" | "rangee" | "colonne", "colonnes": 0 (auto) | n,
     "cases": [{"url": "...", "legende": "...", "miroir": false}],
     "titre": "...", "pied": "...", "entetes_colonnes": ["...", ...], "entetes_lignes": ["...", ...],
     "fond": "transparent" | "blanc", "couleur": "#1f3a8a", "police": "Poppins"}
Les produits sont détourés (fond blanc → transparent) et posés au PIED de leur case, à la même échelle d'une case à
l'autre : quatre porte-filtres de même hauteur restent de même hauteur. Le résultat est un PNG transparent qui
devient la photo du produit (le composeur l'imprime comme n'importe quelle photo).
"""

from __future__ import annotations

import io
import math
import os

DISPOSITIONS = ("grille", "rangee", "colonne", "heros", "groupe")
ESPACEMENTS = {"serre": 0.015, "normal": 0.035, "aere": 0.06}     # entre cases, fraction de la largeur
CADRES = ("aucun", "carte", "trait")
ALIGNEMENTS = ("pied", "centre")
#: « même largeur » : chaque produit prend la largeur de sa case (le défaut, ce que faisait déjà le contain) ;
#: « même hauteur » : tous les produits d'une rangée à la hauteur du plus contraint.
AJUSTEMENTS = ("largeur", "hauteur")
TAILLE_MIN, TAILLE_MAX = 50, 130
LARGEUR = 2400          # px : ~300 dpi sur une zone photo de 200 mm
MARGE = 0.03            # de la largeur
CHEVAUCHEMENT = 0.18    # disposition « groupe » : part de la largeur moyenne d'un produit cachée par le voisin
COULEUR_DEFAUT = "#1f3a8a"
POLICE_DEFAUT = "Poppins"
MAX_CASES = 12


# ─── fonctions pures ─────────────────────────────────────────────────────────

def grille(n: int, disposition: str = "grille", colonnes: int = 0) -> tuple[int, int]:
	"""(lignes, colonnes) pour `n` cases. Grille automatique : 2 → 1×2, 3 → 1×3, 4 → 2×2, 5–6 → 2×3, 7–9 → 3×3. PUR."""
	n = max(1, int(n or 1))
	if disposition in ("rangee", "groupe"):
		return 1, n
	if disposition == "colonne":
		return n, 1
	c = int(colonnes or 0)
	if c <= 0:
		c = n if n <= 3 else (2 if n == 4 else 3 if n <= 9 else 4)
	c = max(1, min(c, n))
	return math.ceil(n / c), c


def normaliser(config: dict | None) -> dict:
	"""La configuration bornée et complétée (valeurs par défaut, listes nettoyées). PUR."""
	c = dict(config or {})
	cases = [x for x in (c.get("cases") or []) if isinstance(x, dict) and x.get("url")][:MAX_CASES]

	def liste(v):
		if isinstance(v, str):
			v = v.replace(";", "\n").split("\n")
		return [str(x).strip() for x in (v or [])]

	def choix(cle, valeurs, defaut):
		return c.get(cle) if c.get(cle) in valeurs else defaut

	return {"disposition": choix("disposition", DISPOSITIONS, "grille"), "colonnes": max(0, int(c.get("colonnes") or 0)),
	        "cases": [{"url": x["url"], "legende": str(x.get("legende") or "").strip(),
	                   "miroir": x.get("miroir") not in (None, False, 0, "0", ""),
	                   # retouche à la main de la taille d'UNE variante (14/10/2026 : « même largeur ») : un produit dont
	                   # une pièce dépasse (support, clé) paraît plus petit une fois aligné sur son contour
	                   "taille": max(TAILLE_MIN, min(TAILLE_MAX, int(float(x.get("taille") or 100))))} for x in cases],
	        "titre": str(c.get("titre") or "").strip(), "pied": str(c.get("pied") or "").strip(),
	        "entetes_colonnes": liste(c.get("entetes_colonnes")), "entetes_lignes": liste(c.get("entetes_lignes")),
	        "fond": "blanc" if c.get("fond") == "blanc" else "transparent",
	        "couleur": c.get("couleur") if str(c.get("couleur") or "").startswith("#") else COULEUR_DEFAUT,
	        "police": str(c.get("police") or POLICE_DEFAUT),
	        "espacement": choix("espacement", ESPACEMENTS, "normal"), "cadre": choix("cadre", CADRES, "aucun"),
	        "alignement": choix("alignement", ALIGNEMENTS, "pied"),
	        "ajustement": choix("ajustement", AJUSTEMENTS, "largeur"),
	        "centrer_derniere": c.get("centrer_derniere", True) not in (False, 0, "0"),
	        # un produit transparent (bol de porte-filtre) sur blanc perd ses parties claires au détourage : décochable
	        "detourer": c.get("detourer", True) not in (False, 0, "0")}


def _hauteur_image(larg, ratios, plafond=1.8):
	"""La hauteur d'image commune d'une rangée de cases de largeur `larg` : la plus élancée tient en largeur,
	bornée à `plafond` × la largeur (un tube très fin ne fait pas une case de 3 m). PUR.

	⚠️ Un porte-filtre est ~2,2 fois plus haut que large : borné à 1,8, la rangée imposait la HAUTEUR et deux produits
	de proportions voisines n'avaient plus la même largeur. En « même largeur », le plafond monte à 3,5."""
	return min(max(larg / max(r, 0.05) for r in ratios) if ratios else larg, larg * plafond)


def plan(config: dict, ratios: list[float], largeur: int = LARGEUR) -> dict:
	"""La géométrie de la planche, en px : cases (x, y, w, h_img, z), en-têtes, titre, pied, hauteur totale. PUR.

	`ratios` : largeur / hauteur de chaque image (détourée, rognée). Dans une rangée, la hauteur suit l'image la plus
	élancée : les produits gardent la même échelle d'une case à l'autre."""
	cfg = normaliser(config)
	n = len(cfg["cases"])
	disposition = cfg["disposition"] if n > 1 else "grille"
	lignes, colonnes = grille(n, disposition, cfg["colonnes"])
	marge, espace = round(largeur * MARGE), round(largeur * ESPACEMENTS[cfg["espacement"]])
	cadre = cfg["cadre"] != "aucun"
	t_titre, t_entete, t_legende, t_pied = (round(largeur * k) for k in (0.042, 0.032, 0.026, 0.026))
	a_legendes = any(x["legende"] for x in cfg["cases"]) and disposition != "groupe"
	h_leg = round(t_legende * 1.6) if a_legendes else 0
	avec_entetes = disposition in ("grille", "rangee", "colonne")
	a_entetes_lignes = avec_entetes and any(cfg["entetes_lignes"][:lignes])
	a_entetes_colonnes = avec_entetes and any(cfg["entetes_colonnes"][:colonnes])
	col_lignes = round(largeur * 0.17) if a_entetes_lignes else 0      # bande des pastilles « MODÈLE A »
	utile = largeur - 2 * marge
	out = {"largeur": largeur, "lignes": lignes, "colonnes": colonnes, "disposition": disposition, "cases": [],
	       "entetes_colonnes": [], "entetes_lignes": [], "cadre": cfg["cadre"],
	       "tailles": {"titre": t_titre, "entete": t_entete, "legende": t_legende, "pied": t_pied}}
	y = marge
	if cfg["titre"]:
		out["titre"] = {"x": largeur / 2, "y": y, "h": t_titre}
		y += round(t_titre * 1.6)

	def case(k, x, y_, w, h_img, z=0):
		out["cases"].append({"index": k, "x": x, "y": y_, "w": w, "h_img": h_img, "legende_y": y_ + h_img + round(t_legende * 0.3), "z": z})

	if disposition == "groupe":
		# côte à côte, à la même hauteur, chaque produit mordant un peu sur son voisin ; le centre devant
		somme, moy = sum(ratios), sum(ratios) / n
		h = min(utile / max(somme - CHEVAUCHEMENT * moy * (n - 1), 0.05), utile * 0.9)
		x = marge + (utile - (somme - CHEVAUCHEMENT * moy * (n - 1)) * h) / 2
		centre = (n - 1) / 2
		for k, r in enumerate(ratios):
			case(k, x, y, r * h, h, z=-abs(k - centre))
			x += r * h - CHEVAUCHEMENT * moy * h
		y += h
	elif disposition == "heros":
		# le premier en grand à gauche, les autres en vignettes à droite (1 colonne jusqu'à 3, 2 au-delà)
		reste = list(range(1, n))
		k_col = 1 if len(reste) <= 3 else 2
		w_heros = utile * 0.58
		w_droite = utile - w_heros - espace
		w_v = (w_droite - espace * (k_col - 1)) / k_col
		r_lignes = math.ceil(len(reste) / k_col)
		h_v = _hauteur_image(w_v, [ratios[k] for k in reste])
		h_droite = r_lignes * (h_v + h_leg) + espace * (r_lignes - 1)
		h_heros = max(h_droite - h_leg, min(w_heros / max(ratios[0], 0.05), w_heros * 1.6))
		case(0, marge, y, w_heros, h_heros)
		y0 = y + max(0, (h_heros + h_leg - h_droite) / 2)
		for i, k in enumerate(reste):
			l_, c_ = divmod(i, k_col)
			case(k, marge + w_heros + espace + c_ * (w_v + espace), y0 + l_ * (h_v + h_leg + espace), w_v, h_v)
		y += max(h_heros + h_leg, h_droite)
	else:
		x0 = marge + (col_lignes + espace if col_lignes else 0)
		larg_case = (largeur - x0 - marge - espace * (colonnes - 1)) / colonnes
		if a_entetes_colonnes:
			for j in range(colonnes):
				out["entetes_colonnes"].append({"x": x0 + j * (larg_case + espace) + larg_case / 2, "y": y, "h": t_entete,
				                                "texte": cfg["entetes_colonnes"][j] if j < len(cfg["entetes_colonnes"]) else ""})
			y += round(t_entete * 1.7)
		for i in range(lignes):
			rang = list(range(i * colonnes, min(n, (i + 1) * colonnes)))
			h_img = _hauteur_image(larg_case, [ratios[k] for k in rang], 3.5 if cfg["ajustement"] == "largeur" else 1.8)
			if a_entetes_lignes:
				out["entetes_lignes"].append({"x": marge, "y": y + h_img / 2, "w": col_lignes, "h": t_entete,
				                              "texte": cfg["entetes_lignes"][i] if i < len(cfg["entetes_lignes"]) else ""})
			# une dernière ligne incomplète se centre (5 produits = 3 + 2 centrés) — sauf sous des en-têtes de colonnes
			decalage = 0
			if cfg["centrer_derniere"] and not a_entetes_colonnes and len(rang) < colonnes:
				decalage = (colonnes - len(rang)) * (larg_case + espace) / 2
			for jj, k in enumerate(rang):
				case(k, x0 + decalage + jj * (larg_case + espace), y, larg_case, h_img)
			y += h_img + h_leg + (espace if i < lignes - 1 else 0)
	if cadre:
		# la carte déborde un peu autour du produit : on garde de l'air entre cartes et bords
		for c_ in out["cases"]:
			c_["pad"] = round(min(c_["w"], c_["h_img"]) * 0.06)
	if cfg["pied"]:
		y += round(max(espace, largeur * 0.02) * 0.8)
		out["pied"] = {"x": largeur / 2, "y": y, "h": t_pied}
		y += round(t_pied * 1.4)
	out["hauteur"] = round(y + marge)
	return out


# ─── rendu ───────────────────────────────────────────────────────────────────

def _police(nom: str, gras: bool, taille: int):
	from PIL import ImageFont

	dossier = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public", "fonts")
	for candidat in ("%s-%s.ttf" % (nom, "Bold" if gras else "Regular"), "%s-Regular.ttf" % nom,
	                 "%s-%s.ttf" % (POLICE_DEFAUT, "Bold" if gras else "Regular")):
		chemin = os.path.join(dossier, candidat)
		if os.path.exists(chemin):
			return ImageFont.truetype(chemin, max(8, int(taille)))
	return ImageFont.load_default()


def produit_detoure(octets: bytes, detourer: bool = True, max_px: int | None = None):
	"""L'image du produit, RGBA : fond blanc rendu transparent (si `detourer`) puis rognée au produit (sans marge vide).
	`max_px` réduit d'abord l'image (aperçu rapide)."""
	from PIL import Image

	from aquaworld_ia.emballage.composition import fond_blanc_en_transparence

	im = Image.open(io.BytesIO(octets))
	if max_px and max(im.size) > max_px:
		im.thumbnail((max_px, max_px), Image.LANCZOS)
		buf = io.BytesIO()
		im.convert("RGBA").save(buf, format="PNG")
		octets = buf.getvalue()
	if detourer:
		try:
			octets = fond_blanc_en_transparence(octets)
		except Exception:
			pass
	im = Image.open(io.BytesIO(octets)).convert("RGBA")
	if detourer:
		boite = im.getchannel("A").point(lambda a: 255 if a > 12 else 0).getbbox()
	else:
		# sans détourage, on rogne le blanc autour du produit (pas le blanc DANS le produit)
		from PIL import ImageChops
		gris = im.convert("L")
		boite = ImageChops.invert(gris).point(lambda v: 255 if v > 20 else 0).getbbox()
	return im.crop(boite) if boite else im


def _texte_centre(dessin, x, y, texte, police, couleur):
	l = dessin.textlength(texte, font=police)
	dessin.text((x - l / 2, y), texte, font=police, fill=couleur)


def composer(config: dict, images: list, largeur: int = LARGEUR) -> bytes:
	"""La planche en PNG. `images` : les images RGBA détourées, dans l'ordre des cases."""
	from PIL import Image, ImageDraw

	cfg = normaliser(config)
	ratios = [im.width / max(1, im.height) for im in images]
	g = plan(cfg, ratios, largeur)
	fond = (255, 255, 255, 255) if cfg["fond"] == "blanc" else (255, 255, 255, 0)
	planche = Image.new("RGBA", (g["largeur"], g["hauteur"]), fond)
	d = ImageDraw.Draw(planche)
	couleur = cfg["couleur"]
	T = g["tailles"]
	if g.get("titre"):
		_texte_centre(d, g["titre"]["x"], g["titre"]["y"], cfg["titre"], _police(cfg["police"], True, T["titre"]), couleur)
	for e in g["entetes_colonnes"]:
		if e["texte"]:
			_texte_centre(d, e["x"], e["y"], e["texte"].upper(), _police(cfg["police"], True, T["entete"]), couleur)
	for e in g["entetes_lignes"]:
		if not e["texte"]:
			continue
		# une pastille pleine, texte blanc — « MODÈLE A »
		police = _police(cfg["police"], True, T["entete"])
		h = round(T["entete"] * 2.0)
		y0 = e["y"] - h / 2
		d.rounded_rectangle((e["x"], y0, e["x"] + e["w"], y0 + h), radius=round(h * 0.28), fill=couleur)
		_texte_centre(d, e["x"] + e["w"] / 2, y0 + (h - T["entete"]) / 2 - T["entete"] * 0.1, e["texte"].upper(), police, "#ffffff")
	# « même hauteur » : par rangée (même y), la hauteur que TOUS peuvent tenir dans leur case
	hauteur_commune = {}
	if cfg["ajustement"] == "hauteur" and g["disposition"] in ("grille", "rangee"):
		for c in g["cases"]:
			im = images[c["index"]]
			pad = c.get("pad", 0)
			h = min(c["h_img"] - 2 * pad, (c["w"] - 2 * pad) * im.height / max(1, im.width))
			cle = round(c["y"])
			hauteur_commune[cle] = min(hauteur_commune.get(cle, h), h)
	for c in sorted(g["cases"], key=lambda c: c["z"]):      # « groupe » : les bords d'abord, le centre devant
		im = images[c["index"]]
		if cfg["cases"][c["index"]]["miroir"]:
			# même orientation que les autres sans IA : le produit retourné (entrée à gauche ↔ à droite)
			from PIL import ImageOps
			im = ImageOps.mirror(im)
		pad = c.get("pad", 0)
		if cfg["cadre"] != "aucun":
			boite = (round(c["x"]), round(c["y"]), round(c["x"] + c["w"]), round(c["y"] + c["h_img"]))
			rayon = round(min(c["w"], c["h_img"]) * 0.06)
			if cfg["cadre"] == "carte":
				d.rounded_rectangle(boite, radius=rayon, fill=(243, 246, 251, 255))
			else:
				d.rounded_rectangle(boite, radius=rayon, outline=couleur, width=max(2, round(largeur * 0.0015)))
		w_dispo, h_dispo = c["w"] - 2 * pad, c["h_img"] - 2 * pad
		echelle = min(w_dispo / max(1, im.width), h_dispo / max(1, im.height))
		if cfg["ajustement"] == "largeur" and g["disposition"] in ("grille", "rangee", "colonne"):
			# même largeur : toute la largeur de la case, tant que la hauteur tient
			echelle = w_dispo / max(1, im.width)
			if im.height * echelle > h_dispo:
				echelle = h_dispo / max(1, im.height)
		if round(c["y"]) in hauteur_commune:
			echelle = hauteur_commune[round(c["y"])] / max(1, im.height)
		echelle *= cfg["cases"][c["index"]]["taille"] / 100       # au-delà de 100 %, le produit déborde un peu de sa case
		w, h = max(1, round(im.width * echelle)), max(1, round(im.height * echelle))
		pose = im.resize((w, h), Image.LANCZOS)
		# au pied de la case (des produits debout sur la même ligne), ou au milieu ; toujours centré en largeur
		y_pose = c["y"] + pad + (h_dispo - h if cfg["alignement"] == "pied" else (h_dispo - h) / 2)
		x_pose = round(c["x"] + pad + (w_dispo - w) / 2)
		# un produit agrandi au-delà de sa case ne doit jamais sortir de la planche
		x_pose, y_pose = max(0, min(x_pose, planche.width - w)), max(0, min(round(y_pose), planche.height - h))
		planche.alpha_composite(pose, (x_pose, y_pose))
		legende = cfg["cases"][c["index"]]["legende"] if g["disposition"] != "groupe" else ""
		if legende:
			_texte_centre(d, c["x"] + c["w"] / 2, c["legende_y"], legende, _police(cfg["police"], False, T["legende"]), couleur)
	if g.get("pied"):
		_texte_centre(d, g["pied"]["x"], g["pied"]["y"], cfg["pied"], _police(cfg["police"], False, T["pied"]), couleur)
	buf = io.BytesIO()
	planche.save(buf, format="PNG", optimize=True)
	return buf.getvalue()
