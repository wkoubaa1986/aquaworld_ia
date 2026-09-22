"""Géométrie du plan à plat (dieline) — 100 % pur, tout en millimètres, origine en haut à gauche
de la feuille (comme le PDF composé ensuite).

Deux formes v1 :
- « Étui à rabats » (tuck-end droit) : bande [patte][côté G][AVANT][côté D][ARRIÈRE] de hauteur H ;
  au-dessus de l'avant, le DESSUS (L×P) puis sa languette ; en dessous, le DESSOUS et sa languette ;
  pattes anti-poussière au-dessus et en dessous des deux côtés. Le dessus est un vrai panneau
  imprimable, ce que l'utilisateur demandait (« face avant, dessus, côtés »).
- « Caisse américaine » (RSC) : [patte][AVANT][côté][ARRIÈRE][côté], rabats haut/bas de P/2.

Un plan = {feuille{w,h}, fond_perdu, faces[...], traits{coupe, pli}}. Les traits se déduisent des
faces : une arête partagée par deux faces est un pli, une arête libre est une coupe.
"""

from __future__ import annotations

ETUI = "Étui à rabats"
CAISSE = "Caisse américaine"
TYPES = (ETUI, CAISSE)

# Code-barres EAN-13 : taille nominale et minimum admis (80 %).
EAN_NOMINAL_MM = (37.29, 25.93)
EAN_MIN_MM = (EAN_NOMINAL_MM[0] * 0.8, EAN_NOMINAL_MM[1] * 0.8)

LIBELLES = {
	"avant": "Face avant", "arriere": "Face arrière", "cote_gauche": "Côté gauche", "cote_droit": "Côté droit",
	"dessus": "Dessus", "dessous": "Dessous", "patte": "Patte de collage", "languette_haut": "Languette (dessus)",
	"languette_bas": "Languette (dessous)", "rabat": "Rabat", "poussiere": "Patte anti-poussière",
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
	if type_boite == CAISSE:
		faces, w, h = _caisse(L, H, P, patte, fond_perdu, securite)
	elif type_boite == ETUI:
		faces, w, h = _etui(L, H, P, patte, fond_perdu, securite)
	else:
		raise ValueError("Type de boîte inconnu : %r" % type_boite)
	return {
		"type": type_boite, "dimensions": {"L": L, "H": H, "P": P, "patte": patte},
		"feuille": {"w": round(w, 3), "h": round(h, 3)}, "fond_perdu": float(fond_perdu),
		"faces": faces, "traits": traits(faces),
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


def apercu_svg(plan: dict, largeur_px: int = 640) -> str:
	"""Un SVG simple du plan (faces nommées, coupes rouges, plis bleus pointillés) pour la fiche."""
	W, Hf = plan["feuille"]["w"], plan["feuille"]["h"]
	k = largeur_px / W
	h_px = Hf * k
	parts = ["<svg xmlns='http://www.w3.org/2000/svg' width='%d' height='%d' viewBox='0 0 %.1f %.1f' "
	         "style='max-width:100%%;background:#fafafa;border:1px solid #ddd'>" % (largeur_px, h_px, W, Hf)]
	for f in plan["faces"]:
		fond = "#dbeafe" if f["imprimable"] else "#f1f5f9"
		parts.append("<rect x='%.2f' y='%.2f' width='%.2f' height='%.2f' fill='%s' stroke='none'/>" % (
			f["x"], f["y"], f["w"], f["h"], fond))
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
	parts.append("</svg>")
	return "".join(parts)
