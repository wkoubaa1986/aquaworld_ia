"""Réglages de présentation validés, indépendants de la rédaction IA."""

from __future__ import annotations

import copy
import json
import math
import re

ORDRE = ["presentation", "rubriques", "caracteristiques", "variantes", "illustrations"]   # les blocs (clés, ordre canonique)
# Ordre d'un document neuf (demande 12/11/2026 : « Le produit en images » par défaut en deuxième position, juste
# après la présentation). ORDRE reste l'ancien défaut : un dossier qui le porte tel quel n'a jamais été réordonné.
ORDRE_DEFAUT = ["presentation", "illustrations", "rubriques", "caracteristiques", "variantes"]
TYPES = {"Fiche technique": "fiche", "Manuel d'utilisation": "manuel"}
MARQUE_DEFAUTS = {
	"position_marque": "avant_titre", "alignement_marque": "gauche",
	"largeur_logo": 32, "afficher_nom_marque": 0,
	"logo_x": 150, "logo_y": 8,
}
PHOTOS_DEFAUTS = {"photos_variantes": 0, "colonnes_photos": 1, "hauteur_vignettes": 55, "style_galerie": "mosaique", "photo_grande": "",
	"tableau_variantes": "croise", "largeur_grande": 62, "legendes_galerie": 1, "legende_alignement": "gauche", "legende_couleur": "texte",
	"largeur_mosaique": 100, "libelle_croise": "nom_sans_parent", "style_titres": "simple", "sommaire": 0,
	"alignement_galerie": "gauche", "largeur_galerie": 100, "galerie_pleine_page": 0, "largeurs_photos": {},
	"police": "", "police_titres": "", "taille_police": 10, "sauts_page": [], "alignement_vertical_photo": "haut"}
# alignement_vertical_photo (demande 12/11/2026 : « centrer l'écriture par rapport à l'image verticalement ») : en deux
# colonnes, « haut » = photo et description alignées par le haut, « centre » = centrées l'une par rapport à l'autre
# (voir latex.source : une description trop longue pour tenir d'un bloc reste alignée par le haut).
# style_galerie : « mosaique » par défaut depuis le 12/11/2026 (« par défaut, le produit en images en mode grande photo
# et autres photos ») ; elle se réduit d'elle-même pour tenir dans la place restante de la page (latex.galerie).
# tableau_variantes : « croise » par défaut depuis le 12/11/2026 (« je veux que le tableau croisé soit par défaut ») ;
# sans deux attributs à croiser, ou au-delà de six colonnes, le rendu revient de lui-même à la liste groupée.
# sauts_page : les blocs (clés de ORDRE) qui commencent sur une nouvelle page (demande 07/11/2026).
# 07/11/2026 (« une façon plus libre de gérer dimensions et positions des images, centrer les images ou tout le
# grid, remplir la page, choisir la police de tout le document ») :
# style_galerie « libre » : chaque photo a sa largeur (largeurs_photos : {fichier: % de la ligne}, 100 par défaut) ;
# les photos s'enchaînent de gauche à droite et passent à la ligne quand la somme dépasse 100.
# alignement_galerie : « gauche » (lignes alignées à gauche) ou « centre » (chaque ligne centrée, dernière ligne
# incomplète comprise). largeur_galerie : % de la ligne occupé par la grille ou la galerie libre, centrée en dessous
# de 100. galerie_pleine_page : le bloc « Le produit en images » commence sur une nouvelle page et la hauteur des
# vignettes de la grille est calculée pour remplir cette page.
# police / police_titres : une des familles livrées (public/fonts, voir latex.POLICES_LIVREES), vide = Noto Sans ;
# police_titres vide = la police du texte. taille_police : corps du texte en points (9, 10, 11, 12).
POLICES = ("", "noto_sans", "open_sans", "lato", "montserrat", "roboto", "poppins", "oswald", "noto_serif", "eb_garamond")
IMAGE = re.compile(r"/(?:private/)?files/[^\s\"'<>]+")
# sommaire : 0 = aucun, 1 = au début, dans le fil de la première page, 2 = sur sa propre page avec le titre, le document
# commence sur une page neuve (demande 07/11/2026).
# style_titres : simple | souligne (filet sous le titre) | barre (barre latérale) | fond (bandeau) ; sommaire : table des
# titres de blocs et de rubriques au début du document (demande 06/11/2026).
# libelle_croise : « nom_sans_parent » (le nom de la variante sans le nom de l'article parent, ex. « AquaJad, Classique
# 5 Stages, Sans mixage »), « nom » (nom complet) ou « reference » (code, ex. AP-M-AJ-5-SM) dans les cellules du croisé.
# largeur_mosaique : % de la ligne occupé par la mosaïque (grande + colonne) ; en dessous de 100, elle est centrée.
# largeur_grande : % de la ligne pour la grande photo de la mosaïque. legendes_galerie : 0 masque les légendes des
# photos (pas celle du QR). legende_alignement / legende_couleur (texte | titres | gris) : présentation des légendes.
# photos_variantes : 0 = vues des variantes dans les illustrations, 1 = regroupées avec la fiche de chaque variante,
# 2 = vignette dans le tableau des variantes. tableau_variantes : « liste » groupée par le premier attribut, ou
# « croise » = attribut le plus varié en lignes × attribut le moins varié en colonnes (demande 06/11/2026).
# hauteur_vignettes : mm des vignettes des galeries à plusieurs colonnes. style_galerie : « grille » régulière, ou
# « mosaique » = une grande photo à gauche et jusqu'à trois petites empilées à droite (demande 06/11/2026), les
# suivantes en grille.
# QR code d'un lien internet (demande utilisateur 06/11/2026 : « le lien du produit en QR code sur mon site »),
# avec une légende sous le code. Absent du PDF tant que l'adresse est vide.
# Position par défaut : dans le bloc des photos (demande 12/11/2026 : « le QR code du lien, je veux qu'il soit toujours
# intégré, s'il existe, dans photos et illustrations ») — il y prend une case de la galerie. Une disposition
# enregistrée sans position (l'ancien défaut « fin_document » n'était pas écrit) suit ce nouveau défaut ; les autres
# positions restent au choix dans l'étape Présenter.
QR_DEFAUTS = {"qr_url": "", "qr_legende": "", "qr_position": "illustrations", "qr_alignement": "droite", "qr_taille": 22}
# Logo en filigrane (demandes 09/11 et 13/11/2026 : « mon logo de l'entreprise très transparent en arrière-plan sur
# toute la page », « le logo de la goutte sans le nom »). filigrane : 0/1 ; filigrane_opacite : % de la couleur du
# logo gardé (3 à 20) ; filigrane_largeur : % de la largeur de la page ; filigrane_rotation : degrés ;
# filigrane_pages : toutes les pages ou la première seulement ; filigrane_gris : le logo passé en gris ;
# filigrane_plan : « fond » (défaut) = en arrière-plan : le texte, les tableaux et leurs lignes colorées le laissent
# voir, les photos le recouvrent ; « dessus » = par-dessus tout, en transparence, donc visible aussi sur les photos
# (premier essai du 13/11/2026, retour de l'utilisateur : « j'ai l'impression qu'il est au-dessus, non en background »).
# filigrane_detourer (13/11/2026 : « et les photos, comment j'enlève le background, le rendre transparent ? ») : en
# arrière-plan, le fond blanc des photos est rendu transparent — le logo se voit autour du produit, pas à travers.
# L'image vient des Réglages (« Logo du filigrane »), sinon de la goutte livrée avec l'app (latex.logo_filigrane).
FILIGRANE_DEFAUTS = {"filigrane": 0, "filigrane_opacite": 8, "filigrane_largeur": 60, "filigrane_rotation": 0,
	"filigrane_pages": "toutes", "filigrane_gris": 0, "filigrane_plan": "fond", "filigrane_detourer": 1}
FILIGRANE_ADMIS = {"filigrane": (0, 1), "filigrane_opacite": range(3, 21), "filigrane_largeur": range(20, 101),
	"filigrane_rotation": (0, 30, 45), "filigrane_pages": ("toutes", "premiere"), "filigrane_gris": (0, 1),
	"filigrane_plan": ("fond", "dessus"), "filigrane_detourer": (0, 1)}
QR_URL = re.compile(r"https?://[A-Za-z0-9](?:[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]*)")


def qr_valide(disposition):
	"""L'adresse du QR si la disposition en porte une (déjà normalisée), sinon ''."""
	return (disposition or {}).get("qr_url", "")


def hauteur_zone_marque(disposition):
	return disposition.get("largeur_logo", 32) * 18 / 32 + (8 if disposition.get("afficher_nom_marque") else 0)


def normaliser(valeur=None):
	if valeur is None:
		valeur = {}
	if not isinstance(valeur, dict):
		raise ValueError("Mise en page invalide.")
	defauts = {
		"position_photo": "apres", "largeur_photo": 65, "hauteur_photo": 65,
		"alignement_titre": "gauche", "couleur": "#087E8B", "ordre": list(ORDRE_DEFAUT),
	}
	if set(valeur) - (set(defauts) | set(MARQUE_DEFAUTS) | set(PHOTOS_DEFAUTS) | set(QR_DEFAUTS) | set(FILIGRANE_DEFAUTS)):
		raise ValueError("Réglage de mise en page inconnu.")
	resultat = {**defauts, **copy.deepcopy(valeur)}
	if resultat["position_photo"] not in ("avant", "apres", "gauche", "droite"):
		raise ValueError("Position de photo invalide.")
	if resultat["alignement_titre"] not in ("gauche", "centre", "droite"):
		raise ValueError("Alignement de titre invalide.")
	if not isinstance(resultat["couleur"], str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", resultat["couleur"]):
		raise ValueError("Choisissez une couleur au format #RRGGBB.")
	resultat["couleur"] = resultat["couleur"].upper()
	for champ, maximum in (("largeur_photo", 80), ("hauteur_photo", 120)):
		v = resultat[champ]
		if isinstance(v, bool) or not isinstance(v, int) or not 20 <= v <= maximum:
			raise ValueError(f"{champ} doit être un entier entre 20 et {maximum}.")
	if resultat["position_photo"] in ("gauche", "droite"):
		resultat["largeur_photo"] = min(resultat["largeur_photo"], 55)
	ordre = resultat["ordre"]
	if not isinstance(ordre, list) or len(ordre) != len(ORDRE) or any(not isinstance(k, str) for k in ordre) or set(ordre) != set(ORDRE):
		raise ValueError("Chaque bloc doit apparaître exactement une fois dans la mise en page.")
	marque = {**MARQUE_DEFAUTS, **{k: v for k, v in valeur.items() if k in MARQUE_DEFAUTS}}
	if marque["position_marque"] not in ("avant_titre", "apres_titre", "fin_document", "masquee", "libre"):
		raise ValueError("Position de la zone de marque invalide.")
	if marque["alignement_marque"] not in ("gauche", "centre", "droite"):
		raise ValueError("Alignement de la zone de marque invalide.")
	largeur = marque["largeur_logo"]
	if isinstance(largeur, bool) or not isinstance(largeur, int) or not 10 <= largeur <= 70:
		raise ValueError("La largeur du logo doit être un entier entre 10 et 70 mm.")
	if type(marque["afficher_nom_marque"]) is not int or marque["afficher_nom_marque"] not in (0, 1):
		raise ValueError("L’affichage du nom de marque doit être activé ou désactivé.")
	for cle, limite in (("logo_x", 210), ("logo_y", 297)):
		v = marque[cle]
		if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= limite:
			raise ValueError("Les coordonnées du logo doivent être comprises dans la page A4, en millimètres.")
		marque[cle] = round(v, 1)
	if marque["position_marque"] == "libre":
		marque["logo_x"] = min(marque["logo_x"], 210 - largeur)
		marque["logo_y"] = min(marque["logo_y"], math.floor((297 - hauteur_zone_marque(marque)) * 10) / 10)
	# Ne pas périmer les versions existantes pour un nouveau réglage resté à sa valeur initiale.
	for cle, valeur_marque in marque.items():
		if valeur_marque == MARQUE_DEFAUTS[cle]:
			resultat.pop(cle, None)
		else:
			resultat[cle] = valeur_marque
	for cle, defaut in PHOTOS_DEFAUTS.items():
		v = valeur.get(cle, defaut)
		if cle == "photo_grande":
			# La photo en grand de la mosaïque (fichier de la galerie) ; vide = la première de la galerie.
			if not isinstance(v, str) or len(v) > 500 or (v and not IMAGE.fullmatch(v)):
				raise ValueError("Photo de la mosaïque invalide.")
			v = v.strip()
		elif cle == "sauts_page":
			if not isinstance(v, list) or any(b not in ORDRE for b in v):
				raise ValueError("Sauts de page invalides.")
			v = [b for b in ORDRE if b in v]
		elif cle == "largeurs_photos":
			# Galerie libre : {fichier: largeur en % de la ligne}. Un fichier absent de la galerie est ignoré au rendu.
			if not isinstance(v, dict) or len(v) > 20:
				raise ValueError("Largeurs de photos invalides.")
			propre = {}
			for fichier, largeur in v.items():
				if not isinstance(fichier, str) or len(fichier) > 500 or not IMAGE.fullmatch(fichier):
					raise ValueError("Largeurs de photos invalides.")
				if isinstance(largeur, bool) or not isinstance(largeur, int) or not 10 <= largeur <= 100:
					raise ValueError("La largeur d’une photo est un entier entre 10 et 100 %.")
				if largeur != 100:
					propre[fichier] = largeur
			v = propre
		else:
			admis = {"photos_variantes": (0, 1, 2), "colonnes_photos": (1, 2, 3, 4), "hauteur_vignettes": range(25, 91),
				"style_galerie": ("grille", "mosaique", "libre"), "tableau_variantes": ("liste", "croise"), "largeur_grande": range(30, 76),
				"legendes_galerie": (0, 1), "legende_alignement": ("gauche", "centre", "droite"), "largeur_mosaique": range(50, 101), "libelle_croise": ("reference", "nom", "nom_sans_parent"), "style_titres": ("simple", "souligne", "barre", "fond"), "sommaire": (0, 1, 2),
				"legende_couleur": ("texte", "titres", "gris"), "alignement_galerie": ("gauche", "centre"), "largeur_galerie": range(50, 101),
				"galerie_pleine_page": (0, 1), "police": POLICES, "police_titres": POLICES, "taille_police": (9, 10, 11, 12),
				"alignement_vertical_photo": ("haut", "centre")}[cle]
			textuel = cle in ("style_galerie", "tableau_variantes", "legende_alignement", "legende_couleur", "libelle_croise", "style_titres",
				"alignement_galerie", "police", "police_titres", "alignement_vertical_photo")
			if (type(v) is not int if not textuel else not isinstance(v, str)) or v not in admis:
				raise ValueError("Présentation des photos invalide.")
		if v == defaut:
			resultat.pop(cle, None)
		else:
			resultat[cle] = v
	for cle, defaut in FILIGRANE_DEFAUTS.items():
		v = valeur.get(cle, defaut)
		if (not isinstance(v, str) if cle in ("filigrane_pages", "filigrane_plan") else type(v) is not int) or v not in FILIGRANE_ADMIS[cle]:
			raise ValueError("Réglage du filigrane invalide.")
		# Comme les autres réglages : la valeur par défaut n'est pas écrite, une version existante ne se périme pas.
		if v == defaut:
			resultat.pop(cle, None)
		else:
			resultat[cle] = v
	qr = {**QR_DEFAUTS, **{k: v for k, v in valeur.items() if k in QR_DEFAUTS}}
	for cle, limite in (("qr_url", 500), ("qr_legende", 120)):
		if not isinstance(qr[cle], str) or len(qr[cle]) > limite:
			raise ValueError(f"{cle} doit être un texte de {limite} caractères au maximum.")
		qr[cle] = qr[cle].strip()
	if qr["qr_url"] and not QR_URL.fullmatch(qr["qr_url"]):
		raise ValueError("L’adresse du QR code doit être un lien internet complet (https://…).")
	if qr["qr_position"] not in ("avant_titre", "apres_titre", "fin_document", "illustrations"):
		raise ValueError("Position du QR code invalide.")
	if qr["qr_alignement"] not in ("gauche", "centre", "droite"):
		raise ValueError("Alignement du QR code invalide.")
	t = qr["qr_taille"]
	if isinstance(t, bool) or not isinstance(t, int) or not 15 <= t <= 40:
		raise ValueError("La taille du QR code doit être un entier entre 15 et 40 mm.")
	for cle, v in qr.items():
		if v == QR_DEFAUTS[cle]:
			resultat.pop(cle, None)
		else:
			resultat[cle] = v
	return resultat


def configuration(valeur):
	if valeur in (None, ""):
		return {}
	if isinstance(valeur, str):
		valeur = json.loads(valeur)
	if not isinstance(valeur, dict) or set(valeur) - {"fiche", "manuel"}:
		raise ValueError("Les mises en page doivent correspondre à la fiche et au manuel.")
	return {cle: normaliser(v) for cle, v in valeur.items()}


LEGENDE_QR_SITE = "Voir le produit en ligne"


def initiale(url_site, base=None):
	"""Les mises en page d'un nouveau dossier (demande 12/11/2026 : « si le produit est sur le site web, pourquoi le QR
	code ne se crée pas automatiquement ? ») : le QR du lien de la boutique, avec sa légende, sur la fiche et le
	manuel. Position, taille et légende se règlent ensuite à l'étape Présenter ; vider l'adresse retire le QR.
	`base` (16/11/2026) : la mise en page de base des Réglages ({"fiche": …, "manuel": …}, voir `base`), dont le
	nouveau dossier part ; le QR du produit s'y ajoute. {} sans lien valide ni base. PURE."""
	base = {cle: de_base(v) for cle, v in (base or {}).items() if cle in TYPES.values()}
	qr = {}
	if isinstance(url_site, str) and QR_URL.fullmatch(url_site.strip()) and len(url_site.strip()) <= 500:
		qr = {"qr_url": url_site.strip(), "qr_legende": LEGENDE_QR_SITE}
	return {cle: normaliser({**base.get(cle, {}), **qr}) for cle in TYPES.values() if qr or cle in base}


def valeur(disposition, cle):
	"""Un réglage des photos tel qu'il s'applique : la valeur par défaut n'est jamais enregistrée, il faut donc la
	lire ici plutôt que par `disposition.get(cle)`."""
	return (disposition or {}).get(cle, PHOTOS_DEFAUTS[cle] if cle in PHOTOS_DEFAUTS else FILIGRANE_DEFAUTS[cle])


def pour_document(dossier, genre):
	return normaliser(configuration(dossier.get("mises_en_page")).get(TYPES[genre]))


def appliquer(ctx, dossier, genre):
	resultat = copy.deepcopy(ctx)
	disposition = pour_document(dossier, genre)
	if disposition == normaliser():
		resultat.pop("mise_en_page", None)
	else:
		resultat["mise_en_page"] = disposition
	return resultat


def portable(disposition):
	"""La mise en page d'un dossier reprise pour un autre produit (demande 07/11/2026) : tout, sauf ce qui désigne un
	fichier de la galerie du dossier d'origine (photo en grand de la mosaïque, largeurs par photo)."""
	m = normaliser(disposition)
	m.pop("photo_grande", None)
	m.pop("largeurs_photos", None)
	return m


def de_base(disposition):
	"""Ce qu'une mise en page a de commun à tous les produits (demande 16/11/2026 : « le setting de mise en page, je
	le veux le setting de base, celui d'AP-M ») : sa partie portable, sans l'adresse du QR ni sa légende, propres au
	produit — sa position, sa taille et son alignement sont gardés."""
	m = portable(disposition)
	m.pop("qr_url", None)
	m.pop("qr_legende", None)
	return m


def base(valeur):
	"""La mise en page de base des nouveaux dossiers, tirée des mises en page d'un dossier ou relue des Réglages :
	{"fiche": …, "manuel": …}, {} si elle est vide. Lève ValueError si elle est invalide."""
	return {cle: de_base(v) for cle, v in configuration(valeur).items()}
