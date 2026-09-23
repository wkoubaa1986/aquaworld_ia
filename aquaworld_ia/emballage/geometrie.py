"""Géométrie du plan à plat (dieline) — 100 % pur, tout en millimètres, origine en haut à gauche
de la feuille (comme le PDF composé ensuite).

Cinq formes, trois familles :
- BOÎTES — « Étui à rabats » (tuck-end droit) : bande [patte][côté G][AVANT][côté D][ARRIÈRE] de
  hauteur H ; au-dessus de l'avant, le DESSUS (L×P) puis sa languette ; en dessous, le DESSOUS et
  sa languette ; pattes anti-poussière au-dessus et en dessous des deux côtés. « Caisse
  américaine » (RSC) : [patte][AVANT][côté][ARRIÈRE][côté], rabats haut/bas de P/2.
- SACS (demande utilisateur 23/09/2026) — « Sac à soufflets latéraux » (sachet café) : bande
  [AVANT][soufflet D][ARRIÈRE][soufflet G][recouvrement] de hauteur H, soudures haute et basse
  de 12 mm, pli médian dans chaque soufflet. « Sachet doypack » (stand-up pouch) : les trois lés
  regroupés sur une feuille — AVANT et ARRIÈRE côte à côte, soudure/zip au-dessus, FOND (soufflet
  plié en W, L×P) sous l'avant. Le dos n'est PAS retourné : ce sont des lés séparés.
- ÉTIQUETTE — « Étiquette enveloppante » : bande [AVANT][côté D][ARRIÈRE][côté G][recouvrement],
  sans dessus ni dessous, pour un flacon ou un bidon.

Un plan = {feuille{w,h}, fond_perdu, faces[...], traits{coupe, pli}}. Les traits se déduisent des
faces : une arête partagée par deux faces est un pli, une arête libre est une coupe.
"""

from __future__ import annotations

ETUI = "Étui à rabats"
CAISSE = "Caisse américaine"
SAC = "Sac à soufflets latéraux"
DOYPACK = "Sachet doypack (fond plat)"
ETIQUETTE = "Étiquette enveloppante"
TYPES = (ETUI, CAISSE, SAC, DOYPACK, ETIQUETTE)

#: La famille pilote le prompt IA (boîte, sachet souple, étiquette) et le rendu 3D.
FAMILLES = {ETUI: "boite", CAISSE: "boite", SAC: "sac", DOYPACK: "sac", ETIQUETTE: "etiquette"}

#: Ce que veulent dire L, H, P pour chaque forme — affiché sous les champs de dimensions.
DIMENSIONS_TYPE = {
	ETUI: ("Largeur de la face avant", "Hauteur", "Profondeur (largeur des côtés)"),
	CAISSE: ("Largeur de la face avant", "Hauteur", "Profondeur (largeur des côtés)"),
	SAC: ("Largeur de la face avant", "Hauteur hors soudures", "Largeur d'un soufflet"),
	DOYPACK: ("Largeur du sachet", "Hauteur hors soudure", "Profondeur du fond (soufflet)"),
	ETIQUETTE: ("Largeur de la face avant", "Hauteur de l'étiquette", "Largeur des côtés"),
}

DESCRIPTIONS = {
	ETUI: "Boîte carton pliante fermée par des languettes : dessus, dessous et 4 faces imprimés.",
	CAISSE: "Carton d'expédition à rabats : 4 faces imprimées, rabats laissés en aplat.",
	SAC: "Sachet souple type café : avant, dos et deux soufflets imprimés, soudures haut et bas.",
	DOYPACK: "Sachet debout à fond plat : avant et dos imprimés, fond en soufflet, zip en haut.",
	ETIQUETTE: "Étiquette à enrouler autour d'un flacon ou d'un bidon : 4 faces, sans dessus.",
}

#: Dimensions d'exemple (L, H, P) pour les vignettes du sélecteur de type.
DIMENSIONS_EXEMPLE = {ETUI: (120, 200, 60), CAISSE: (120, 200, 60), SAC: (120, 200, 60),
                      DOYPACK: (130, 200, 80), ETIQUETTE: (90, 120, 60)}

SOUDURE_MM = 12.0

# Code-barres EAN-13 : taille nominale et minimum admis (80 %).
EAN_NOMINAL_MM = (37.29, 25.93)
EAN_MIN_MM = (EAN_NOMINAL_MM[0] * 0.8, EAN_NOMINAL_MM[1] * 0.8)

LIBELLES = {
	"avant": "Face avant", "arriere": "Face arrière", "cote_gauche": "Côté gauche", "cote_droit": "Côté droit",
	"dessus": "Dessus", "dessous": "Dessous", "patte": "Patte de collage", "languette_haut": "Languette (dessus)",
	"languette_bas": "Languette (dessous)", "rabat": "Rabat", "poussiere": "Patte anti-poussière",
	"soudure": "Soudure", "fond": "Fond (soufflet plié)",
}

ZONES_LIBELLES = {
	"logo": "Logo", "nom": "Nom du produit", "accroche": "Accroche", "caracteristiques": "Caractéristiques",
	"avertissements": "Avertissements", "contact": "Contact", "pictos": "Pictogrammes", "code_barres": "Code-barres",
	"photo": "Photo produit",
}


def _face(code, x, y, w, h, imprimable, securite, libelle=None):
	inset = min(securite, w / 4, h / 4)
	return {
		"code": code, "libelle": libelle or LIBELLES.get(code.split("#")[0], code),
		"x": round(x, 3), "y": round(y, 3), "w": round(w, 3), "h": round(h, 3),
		"imprimable": bool(imprimable),
		"zone_sure": {"x": round(x + inset, 3), "y": round(y + inset, 3),
		              "w": round(w - 2 * inset, 3), "h": round(h - 2 * inset, 3)},
	}


def plan_a_plat(type_boite: str, L: float, H: float, P: float, *, patte: float = 15.0,
                fond_perdu: float = 3.0, securite: float = 3.0) -> dict:
	"""L = largeur de la face avant, H = hauteur, P = profondeur (largeur des côtés)."""
	L, H, P, patte = float(L), float(H), float(P), float(patte)
	if min(L, H, P) <= 0:
		raise ValueError("Dimensions nulles ou négatives")
	constructeurs = {CAISSE: _caisse, ETUI: _etui, SAC: _sac, DOYPACK: _doypack, ETIQUETTE: _etiquette}
	if type_boite not in constructeurs:
		raise ValueError("Type d'emballage inconnu : %r" % type_boite)
	resultat = constructeurs[type_boite](L, H, P, patte, fond_perdu, securite)
	faces, w, h = resultat[:3]
	plis_extra = resultat[3] if len(resultat) > 3 else []
	t = traits(faces)
	t["pli"].extend([[round(v, 3) for v in pli] for pli in plis_extra])
	return {
		"type": type_boite, "famille": FAMILLES[type_boite],
		"dimensions": {"L": L, "H": H, "P": P, "patte": patte},
		"feuille": {"w": round(w, 3), "h": round(h, 3)}, "fond_perdu": float(fond_perdu),
		"faces": faces, "traits": t,
	}


def _etui(L, H, P, patte, fp, sec):
	T = min(20.0, 0.6 * P)                       # languettes de fermeture
	D = 0.8 * P                                   # pattes anti-poussière
	haut = fp + T + P                             # y du bord haut de la bande principale
	x = fp
	faces = [_face("patte", x, haut, patte, H, False, sec)]
	x += patte
	faces.append(_face("cote_gauche", x, haut, P, H, True, sec))
	faces.append(_face("poussiere#1", x, haut - D, P, D, False, sec, "Patte anti-poussière (haut G)"))
	faces.append(_face("poussiere#2", x, haut + H, P, D, False, sec, "Patte anti-poussière (bas G)"))
	x += P
	faces.append(_face("avant", x, haut, L, H, True, sec))
	faces.append(_face("dessus", x, haut - P, L, P, True, sec))
	faces.append(_face("languette_haut", x, haut - P - T, L, T, False, sec))
	faces.append(_face("dessous", x, haut + H, L, P, True, sec))
	faces.append(_face("languette_bas", x, haut + H + P, L, T, False, sec))
	x += L
	faces.append(_face("cote_droit", x, haut, P, H, True, sec))
	faces.append(_face("poussiere#3", x, haut - D, P, D, False, sec, "Patte anti-poussière (haut D)"))
	faces.append(_face("poussiere#4", x, haut + H, P, D, False, sec, "Patte anti-poussière (bas D)"))
	x += P
	faces.append(_face("arriere", x, haut, L, H, True, sec))
	x += L
	return faces, x + fp, haut + H + P + T + fp


def _caisse(L, H, P, patte, fp, sec):
	R = P / 2.0
	haut = fp + R
	x = fp
	faces = [_face("patte", x, haut, patte, H, False, sec)]
	x += patte
	for code, largeur in (("avant", L), ("cote_droit", P), ("arriere", L), ("cote_gauche", P)):
		faces.append(_face(code, x, haut, largeur, H, True, sec))
		faces.append(_face("rabat#h_" + code, x, haut - R, largeur, R, False, sec, "Rabat haut (%s)" % LIBELLES[code]))
		faces.append(_face("rabat#b_" + code, x, haut + H, largeur, R, False, sec, "Rabat bas (%s)" % LIBELLES[code]))
		x += largeur
	return faces, x + fp, haut + H + R + fp


def _sac(L, H, P, patte, fp, sec):
	"""Sachet à soufflets latéraux : une bande, deux soudures, un pli au milieu de chaque soufflet."""
	S = SOUDURE_MM
	haut = fp + S
	x = fp
	faces, plis = [], []
	colonnes = [("avant", L, True), ("cote_droit", P, True), ("arriere", L, True), ("cote_gauche", P, True),
	            ("patte", patte, False)]
	for code, largeur, imprimable in colonnes:
		libelle = "Recouvrement (soudure dos)" if code == "patte" else None
		faces.append(_face(code, x, haut, largeur, H, imprimable, sec, libelle))
		# Une soudure PAR colonne : une seule bande longue n'aurait pas d'arête commune avec les
		# faces, et `traits` la dessinerait en coupe au lieu d'un pli.
		faces.append(_face("soudure#haut_" + code, x, fp, largeur, S, False, sec, "Soudure haute"))
		faces.append(_face("soudure#bas_" + code, x, haut + H, largeur, S, False, sec, "Soudure basse"))
		if code in ("cote_droit", "cote_gauche"):
			xm = x + largeur / 2.0
			plis.append([xm, haut, xm, haut + H])
		x += largeur
	return faces, x + fp, haut + H + S + fp, plis


def _doypack(L, H, P, patte, fp, sec):
	"""Stand-up pouch, trois lés regroupés : avant et dos côte à côte, fond sous l'avant."""
	S = SOUDURE_MM
	haut = fp + S
	x = fp
	faces = []
	for code in ("avant", "arriere"):
		faces.append(_face("soudure#haut_" + code, x, fp, L, S, False, sec, "Soudure haute (zip)"))
		faces.append(_face(code, x, haut, L, H, True, sec))
		x += L
	faces.append(_face("fond", fp, haut + H, L, P, False, sec))
	ym = haut + H + P / 2.0
	return faces, x + fp, haut + H + P + fp, [[fp, ym, fp + L, ym]]


def _etiquette(L, H, P, patte, fp, sec):
	"""Étiquette enveloppante : la bande seule, un recouvrement, ni dessus ni dessous."""
	x = fp
	faces = []
	for code, largeur in (("avant", L), ("cote_droit", P), ("arriere", L), ("cote_gauche", P)):
		faces.append(_face(code, x, fp, largeur, H, True, sec))
		x += largeur
	faces.append(_face("patte", x, fp, patte, H, False, sec, "Recouvrement"))
	x += patte
	return faces, x + fp, fp + H + fp


def _aretes(face):
	x0, y0, x1, y1 = face["x"], face["y"], face["x"] + face["w"], face["y"] + face["h"]
	return [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x0, y1), (x1, y1)), ((x0, y0), (x0, y1))]


def _cle(arete):
	(a, b) = arete
	pts = sorted([(round(a[0], 2), round(a[1], 2)), (round(b[0], 2), round(b[1], 2))])
	return (pts[0], pts[1])


def traits(faces: list[dict]) -> dict:
	"""Une arête partagée par deux faces = pli ; libre = coupe. -> {coupe: [[x1,y1,x2,y2]], pli: [...]}."""
	compte = {}
	for face in faces:
		for arete in _aretes(face):
			compte[_cle(arete)] = compte.get(_cle(arete), 0) + 1
	coupe = [[*k[0], *k[1]] for k, n in compte.items() if n == 1]
	pli = [[*k[0], *k[1]] for k, n in compte.items() if n > 1]
	return {"coupe": coupe, "pli": pli}


def mm_vers_pt(mm: float) -> float:
	return float(mm) * 72.0 / 25.4


def pt_vers_mm(pt: float) -> float:
	return float(pt) * 25.4 / 72.0


def format_page_pt(plan: dict) -> tuple[float, float]:
	return mm_vers_pt(plan["feuille"]["w"]), mm_vers_pt(plan["feuille"]["h"])


def dpi_effectif(px: int, mm: float) -> float:
	"""La résolution qu'auront `px` pixels étalés sur `mm` millimètres."""
	if not mm or mm <= 0:
		return 0.0
	return round(px / (float(mm) / 25.4), 1)


def taille_image_pour(face: dict) -> str:
	"""La taille gpt-image-1 la plus proche du ratio de la face (avec le fond perdu, la face
	est ensuite recadrée « couvrant »)."""
	ratio = face["w"] / face["h"] if face["h"] else 1.0
	if ratio >= 1.25:
		return "1536x1024"
	if ratio <= 0.8:
		return "1024x1536"
	return "1024x1024"


def cadrage(face_w: float, face_h: float, img_w: int, img_h: int) -> tuple[int, int, int, int]:
	"""Le recadrage centré (x0, y0, x1, y1 en pixels) qui COUVRE la face sans la déformer."""
	if min(face_w, face_h, img_w, img_h) <= 0:
		return (0, 0, int(img_w), int(img_h))
	cible = face_w / face_h
	actuel = img_w / img_h
	if actuel > cible:
		w = int(round(img_h * cible))
		x0 = (img_w - w) // 2
		return (x0, 0, x0 + w, img_h)
	h = int(round(img_w / cible))
	y0 = (img_h - h) // 2
	return (0, y0, img_w, y0 + h)


def bande(plan: dict) -> dict | None:
	"""La BANDE : les faces imprimables alignées sur la face avant (même y, même hauteur),
	de gauche à droite — celles qui se suivent autour de l'objet et où un fond doit se
	raccorder aux plis. {x, y, w, h, faces: [codes dans l'ordre]}. Pur.

	Étui / caisse / sac / étiquette : côté G, avant, côté D, arrière (ou avant, côté, arrière,
	côté). Doypack : avant, arrière. Le dessus et le dessous, hors bande, reçoivent le même
	fond recadré : aucune continuité n'y est possible, il n'y a pas d'arête commune."""
	avant = face(plan, "avant")
	if not avant:
		return None
	faces = sorted((f for f in plan["faces"] if f["imprimable"] and abs(f["y"] - avant["y"]) < 0.01
	                and abs(f["h"] - avant["h"]) < 0.01), key=lambda f: f["x"])
	x0 = min(f["x"] for f in faces)
	x1 = max(f["x"] + f["w"] for f in faces)
	return {"x": round(x0, 3), "y": avant["y"], "w": round(x1 - x0, 3), "h": avant["h"], "faces": [f["code"] for f in faces]}


def face(plan: dict, code: str) -> dict | None:
	return next((f for f in plan["faces"] if f["code"] == code), None)


def verifier(plan: dict) -> list[str]:
	"""Anomalies bloquantes : chevauchement de faces, face hors feuille, EAN illogeable."""
	problemes = []
	faces = plan["faces"]
	W, Hf = plan["feuille"]["w"], plan["feuille"]["h"]
	for f in faces:
		if f["x"] < -0.01 or f["y"] < -0.01 or f["x"] + f["w"] > W + 0.01 or f["y"] + f["h"] > Hf + 0.01:
			problemes.append("%s dépasse de la feuille" % f["libelle"])
	for i, a in enumerate(faces):
		for b in faces[i + 1:]:
			if (a["x"] < b["x"] + b["w"] - 0.01 and b["x"] < a["x"] + a["w"] - 0.01
					and a["y"] < b["y"] + b["h"] - 0.01 and b["y"] < a["y"] + a["h"] - 0.01):
				problemes.append("%s et %s se chevauchent" % (a["libelle"], b["libelle"]))
	arriere = face(plan, "arriere")
	if arriere and (arriere["zone_sure"]["w"] < EAN_MIN_MM[0] or arriere["zone_sure"]["h"] < EAN_MIN_MM[1]):
		problemes.append("La face arrière ne peut pas loger un EAN-13 (min. %.0f × %.0f mm)" % EAN_MIN_MM)
	return problemes


def apercu_svg(plan: dict, largeur_px: int = 640, zones: dict | None = None, compact: bool = False) -> str:
	"""Le SVG du plan pour la fiche : faces nommées, coupes rouges, plis bleus pointillés.

	Chaque face porte `data-face` (le JS s'en sert pour le survol et le clic) ; `zones`
	({code: [zone…]}) ajoute, par face, un groupe masqué des emplacements (logo, nom, EAN…) que
	l'écran révèle au survol. `compact` : la vignette du sélecteur de type, sans texte."""
	W, Hf = plan["feuille"]["w"], plan["feuille"]["h"]
	k = largeur_px / W
	h_px = Hf * k
	parts = ["<svg xmlns='http://www.w3.org/2000/svg' class='aqia-plan' width='%d' height='%d' viewBox='0 0 %.1f %.1f' "
	         "style='max-width:100%%;background:#fafafa;%s'>" % (
		largeur_px, h_px, W, Hf, "" if compact else "border:1px solid #ddd")]
	for f in plan["faces"]:
		fond = "#dbeafe" if f["imprimable"] else "#f1f5f9"
		parts.append("<rect class='aqia-face%s' data-face='%s' x='%.2f' y='%.2f' width='%.2f' height='%.2f' fill='%s' stroke='none'/>" % (
			" imprimable" if f["imprimable"] else "", f["code"], f["x"], f["y"], f["w"], f["h"], fond))
		if compact:
			continue
		if f["imprimable"] or f["w"] * f["h"] > 0.02 * W * Hf:
			parts.append("<text x='%.2f' y='%.2f' font-size='%.2f' text-anchor='middle' fill='#334155' "
			             "font-family='sans-serif'>%s</text>" % (
				f["x"] + f["w"] / 2, f["y"] + f["h"] / 2, max(2.5, min(f["w"], f["h"]) / 6), f["libelle"]))
			parts.append("<text x='%.2f' y='%.2f' font-size='%.2f' text-anchor='middle' fill='#64748b' "
			             "font-family='sans-serif'>%.0f × %.0f mm</text>" % (
				f["x"] + f["w"] / 2, f["y"] + f["h"] / 2 + max(2.5, min(f["w"], f["h"]) / 6) * 1.2,
				max(2.0, min(f["w"], f["h"]) / 8), f["w"], f["h"]))
	for x1, y1, x2, y2 in plan["traits"]["pli"]:
		parts.append("<line x1='%.2f' y1='%.2f' x2='%.2f' y2='%.2f' stroke='#2563eb' stroke-width='%.2f' "
		             "stroke-dasharray='%.1f,%.1f'/>" % (x1, y1, x2, y2, W / 640, W / 160, W / 320))
	for x1, y1, x2, y2 in plan["traits"]["coupe"]:
		parts.append("<line x1='%.2f' y1='%.2f' x2='%.2f' y2='%.2f' stroke='#dc2626' stroke-width='%.2f'/>" % (
			x1, y1, x2, y2, W / 640))
	for code, liste in (zones or {}).items():
		parts.append("<g class='aqia-zones' data-face='%s' style='display:none'>" % code)
		for z in liste:
			# `fill-opacity` et non rgba() : le rendu SVG de MuPDF (vignettes, contrôles) ignore rgba.
			parts.append("<rect x='%.2f' y='%.2f' width='%.2f' height='%.2f' fill='#2563eb' fill-opacity='0.12' "
			             "stroke='#2563eb' stroke-width='%.2f' stroke-dasharray='%.1f,%.1f'/>" % (
				z["x"], z["y"], z["w"], z["h"], W / 900, W / 240, W / 480))
			corps = max(2.0, min(min(z["w"], z["h"]) / 4, W / 70))
			parts.append("<text x='%.2f' y='%.2f' font-size='%.2f' fill='#1d4ed8' font-family='sans-serif'>%s</text>" % (
				z["x"] + W / 400, z["y"] + corps, corps, ZONES_LIBELLES.get(z["zone"], z["zone"])))
		parts.append("</g>")
	parts.append("</svg>")
	return "".join(parts)
