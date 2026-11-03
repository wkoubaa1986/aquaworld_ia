"""Ateliers d’images du studio : propositions, transformations et adoption explicite.

Les anciennes routes studio.* restent des alias pour la fiche et les clients existants.
"""
from __future__ import annotations
import io
import json
import re
import frappe
from frappe import _
from frappe.utils import cint, flt
from aquaworld_ia.emballage import codes, geometrie, job

def charger(*args, **kwargs):
	from aquaworld_ia.emballage.studio import charger as appel
	return appel(*args, **kwargs)

def enregistrer(*args, **kwargs):
	from aquaworld_ia.emballage.studio import enregistrer as appel
	return appel(*args, **kwargs)

def images_du_design(doc):
	from aquaworld_ia.emballage.studio import images_du_design as appel
	return appel(doc)

def _image_lisible(doc, url):
	from aquaworld_ia.emballage.studio import _image_lisible as appel
	return appel(doc, url)

@frappe.whitelist()
def retoucher_logo(design: str, instruction: str, nombre=1) -> dict:
	"""L'atelier logo (demande utilisateur 23/09/2026) : redessiner le logo par IA d'après le
	logo actuel — changer ses couleurs, l'épurer — SANS le poser encore. Le résultat est un
	candidat attaché à la fiche ; l'utilisateur compare et adopte, ou réessaie. `nombre` (1 à 4,
	demande du 24/09/2026 : « en voir plusieurs avant de choisir ») candidats pour la même consigne.

	⚠️ L'IA redessine les LETTRES à sa façon : le candidat se relit lettre par lettre."""
	from aquaworld_ia.emballage.variantes import url_logo
	from aquaworld_ia.ia import fichiers, images
	from aquaworld_ia.ia.client import qualite_image
	from frappe.utils.file_manager import save_file

	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("write")
	source = url_logo(doc)
	if not source:
		frappe.throw(_("Attachez d'abord un logo."))
	instruction = (instruction or "").strip()
	if not instruction:
		frappe.throw(_("Dites ce que vous voulez changer : couleurs, épuration, style…"))
	prompt = (
		"Redraw the logo given as the reference image as a clean, flat, vector-style logo on a PURE WHITE background, "
		"centered, filling the frame, keeping its shapes, proportions and lettering EXACTLY as in the reference. "
		"Apply only this change: %s. No background scene, no shadows, no extra elements, no extra text." % instruction)
	n = max(1, min(4, cint(nombre) or 1))
	pngs = images.editer(prompt, [("logo", fichiers.lire(source))], taille="1024x1024", qualite=qualite_image(),
	                     n=n, fonctionnalite="Logo IA", doc=doc, fidelite="high")
	candidats = [save_file("%s-logo-ia.png" % doc.name, png, "Design Emballage", doc.name, is_private=1).file_url for png in pngs]
	return {"candidats": candidats, "candidat": candidats[0] if candidats else None, "source": source}


PROMPTS_RETOUCHE = {
	"logo": (
		"Redraw the logo given as the reference image as a clean, flat, vector-style logo on a PURE WHITE background, "
		"centered, filling the frame, keeping its shapes, proportions and lettering EXACTLY as in the reference. "
		"Apply only this change: %s. No background scene, no shadows, no extra elements, no extra text."),
	"photo_produit": (
		"Professional packshot of the product shown in the reference image, for a retail packaging: the product itself "
		"must stay EXACTLY as in the reference (shape, proportions, colors, materials, fittings, labels, text on it), "
		"no redesign, no added parts. Clean cut-out on a PURE WHITE background, soft even studio lighting, sharp focus, "
		"straight front view, product centered and filling the frame, no props, no hands, no text, no logo, no shadow scene. "
		"Apply only this change: %s."),
}


def prompt_retouche(champ: str, instruction: str, couleur_cible=None, element_couleur="", palette=None) -> str:
	"""Le prompt de l'atelier IA d'une image du design (logo, photo produit). Pur."""
	from aquaworld_ia.emballage.logo_couleur import normaliser

	if champ not in PROMPTS_RETOUCHE:
		raise ValueError("Pas d'atelier IA pour %r" % champ)
	prompt = PROMPTS_RETOUCHE[champ] % (instruction or "").strip().rstrip(".")
	if couleur_cible and str(couleur_cible).strip():
		couleur = normaliser(couleur_cible)
		if not couleur:
			raise ValueError("Couleur invalide : utilisez un code HEX comme #008bcd.")
		cible = str(element_couleur or "").strip()[:200] or "the elements explicitly identified in the requested change"
		prompt += (" Colour reference supplied by the user: sRGB HEX %s. Apply this colour to: %s. "
			"Match the supplied HEX reference as closely as possible; do not substitute a similar hue. "
			"This explicit recolouring request overrides colour preservation only for these elements; "
			"preserve the colours of everything else." % (couleur, cible))
	if palette is not None:
		couleurs = []
		for valeur in re.split(r"[\s,;]+", str(palette or "").strip()):
			if not valeur:
				continue
			couleur = normaliser(valeur)
			if not couleur:
				raise ValueError("La palette doit contenir des codes HEX valides, séparés par des virgules.")
			if couleur not in couleurs:
				couleurs.append(couleur)
		if not couleurs:
			raise ValueError("Ajoutez une couleur à la palette du design ou désactivez son utilisation.")
		prompt += (" For any other colours introduced or modified by the requested edit, use this user palette "
			"(sRGB HEX): %s. Preserve unmodified reference colours. The specific target colour above, if provided, "
			"takes precedence over this palette." % ", ".join(couleurs))
	return prompt


def taille_retouche(champ: str, octets: bytes | None) -> str:
	"""Le format d'image de l'atelier : carré pour un logo ; pour une photo, portrait ou paysage
	si le produit l'est nettement (un porte-filtre est haut et étroit). Pur."""
	if champ != "photo_produit" or not octets:
		return "1024x1024"
	try:
		from PIL import Image

		im = Image.open(io.BytesIO(octets))
		ratio = im.width / max(1, im.height)
	except Exception:
		return "1024x1024"
	if ratio < 0.8:
		return "1024x1536"
	if ratio > 1.25:
		return "1536x1024"
	return "1024x1024"


@frappe.whitelist()
def retoucher_image(design: str, champ: str, instruction: str, nombre=1, source_url: str | None = None,
                    cible_zone=None, couleur_cible=None, element_couleur="", utiliser_palette=0) -> dict:
	"""L'atelier IA d'une image du design — logo, ou photo produit (demande utilisateur 24/09/2026 :
	« améliorer avec l'IA la photo du produit ») : détourage sur blanc pur, éclairage studio, retrait
	des accessoires… `nombre` propositions (1 à 4) attachées à la fiche, rien n'est posé tant que
	l'utilisateur n'adopte pas. ⚠️ L'IA REDESSINE : la photo se contrôle détail par détail."""
	from aquaworld_ia.emballage.variantes import url_logo, url_photo
	from aquaworld_ia.ia import fichiers, images
	from aquaworld_ia.ia.client import qualite_image
	from frappe.utils.file_manager import save_file

	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("write")
	cible = _cible_logo_zone(doc, champ, cible_zone) if cible_zone is not None else None
	source = url_logo(doc) if champ == "logo" else url_photo(doc) if champ == "photo_produit" else None
	if cible:
		source = cible[0]["zones"][cible[1]].get("logo") or source
		if source:
			source = _image_lisible(doc, source)
	if source_url and champ in PROMPTS_RETOUCHE:
		# Mosaïque, galerie ou préparation pour SVG : retoucher la source choisie sans l’adopter.
		source = _image_lisible(doc, source_url)
	if champ not in PROMPTS_RETOUCHE:
		frappe.throw(_("Pas d'atelier IA pour ce champ."))
	if not source:
		frappe.throw(_("Attachez d'abord un logo.") if champ == "logo" else _("Attachez d'abord une photo du produit."))
	instruction = (instruction or "").strip()
	if not instruction:
		frappe.throw(_("Dites ce que vous voulez changer."))
	try:
		prompt = prompt_retouche(champ, instruction, couleur_cible, element_couleur,
			palette=(doc.get("palette") or "") if cint(utiliser_palette) else None)
	except ValueError as exc:
		frappe.throw(str(exc))
	octets = fichiers.lire(source)
	n = max(1, min(4, cint(nombre) or 1))
	pngs = images.editer(prompt, [(champ, octets)], taille=taille_retouche(champ, octets),
	                     qualite=qualite_image(), n=n, fonctionnalite="Logo IA" if champ == "logo" else "Emballage image",
	                     doc=doc, fidelite="high")
	suffixe = "logo-ia" if champ == "logo" else "photo-ia"
	candidats = [save_file("%s-%s.png" % (doc.name, suffixe), png, "Design Emballage", doc.name, is_private=1).file_url for png in pngs]
	return {"candidats": candidats, "candidat": candidats[0] if candidats else None, "source": source}


def _cible_logo_zone(doc, champ, cible_zone):
	"""Résout la zone sur le serveur. Un résultat tardif ne doit pas remplacer un autre logo."""
	from aquaworld_ia.emballage.studio import apercu_du_doc

	cible = frappe.parse_json(cible_zone) if isinstance(cible_zone, str) else cible_zone
	if champ != "logo" or not isinstance(cible, dict):
		frappe.throw(_("Sélectionnez une zone Logo."))
	if not cible.get("modifie_le") or str(doc.modified) != cible["modifie_le"]:
		frappe.throw(_("Le design a changé. Rouvrez la zone Logo ; les propositions restent dans la médiathèque."))
	apercu = apercu_du_doc(doc) or {}
	face = next((f for f in apercu.get("faces", []) if f["code"] == cible.get("face")), None)
	indice = cible.get("indice")
	if (not face or type(indice) is not int or indice < 0 or indice >= len(face["zones"])
			or face["zones"][indice]["zone"] != "logo"):
		frappe.throw(_("Cette zone Logo n’existe plus. Sélectionnez-la à nouveau."))
	return face, indice, apercu


def _poser_logo_zone(doc, cible, url):
	from aquaworld_ia.emballage.composition import borner_zone

	face, indice, apercu = cible
	mep = frappe.parse_json(doc.get("mise_en_page")) or {}
	# Si d'autres faces copient celle-ci, conserver leur dessin avant de remplacer ce seul logo.
	for f in apercu.get("faces", []):
		if f.get("copie_de") == face["code"]:
			mep[f["code"]] = [borner_zone(z, f) for z in f["zones"] if not z.get("auto")]
	zones = []
	for i, z in enumerate(face["zones"]):
		if z.get("auto"):
			continue  # Garder la photo automatique en arrière-plan.
		z = borner_zone(z, face)
		if i == indice:
			z["logo"] = url
			z.pop("centre_visuel", None)
		zones.append(z)
	mep[face["code"]] = zones
	doc.mise_en_page = json.dumps(mep, ensure_ascii=False)


@frappe.whitelist()
def adopter_image(design: str, champ: str, url: str, cible_zone=None) -> dict:
	"""Le candidat devient le logo ou la photo produit : fond blanc rendu transparent, fichier propre (un
	SVG est gardé tel quel)."""
	from aquaworld_ia.emballage.composition import est_svg, fond_blanc_en_transparence
	from aquaworld_ia.ia import fichiers
	from frappe.utils.file_manager import save_file

	if champ not in PROMPTS_RETOUCHE:
		frappe.throw(_("Pas d'atelier IA pour ce champ."))
	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("write")
	cible = _cible_logo_zone(doc, champ, cible_zone) if cible_zone is not None else None
	octets = fichiers.lire(_image_lisible(doc, url))
	if not est_svg(octets):
		png = fond_blanc_en_transparence(octets)
		fichier = save_file("%s-%s.png" % (doc.name, "logo" if champ == "logo" else "photo"), png, "Design Emballage", doc.name, is_private=1)
		url = fichier.file_url
	if cible:
		_poser_logo_zone(doc, cible, url)
	else:
		doc.set(champ, url)
	doc.save()
	return charger(design)


@frappe.whitelist()
def vectoriser_image(design: str, champ: str, profil: str = "photo", couleurs=64, retirer_fond=0,
                     source_url: str | None = None) -> dict:
	"""Vectorise l’image actuelle ou une source lisible choisie (galerie / proposition IA).
	Un candidat SVG couleur privé, à comparer avant adoption. Aucun appel IA ici.
	"""
	from aquaworld_ia.emballage import vectorisation
	from aquaworld_ia.emballage.variantes import url_logo, url_photo
	from aquaworld_ia.ia import fichiers
	from frappe.utils.file_manager import save_file

	if champ not in ("logo", "photo_produit"):
		frappe.throw(_("Seuls le logo et la photo produit peuvent être vectorisés."))
	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("write")
	source = source_url or (url_logo(doc) if champ == "logo" else url_photo(doc))
	if not source:
		frappe.throw(_("Choisissez d’abord une image à vectoriser."))
	try:
		svg, infos = vectorisation.vectoriser(fichiers.lire(_image_lisible(doc, source)),
		                                      profil, cint(couleurs), bool(cint(retirer_fond)))
	except ValueError as exc:
		frappe.throw(str(exc))
	suffixe = "logo" if champ == "logo" else "photo"
	fichier = save_file("%s-%s-vectorise.svg" % (doc.name, suffixe), svg,
	                    "Design Emballage", doc.name, is_private=1)
	return dict(infos, candidat=fichier.file_url, source=source, format="svg", images=images_du_design(doc))


@frappe.whitelist()
def palette_logo(design: str) -> dict:
	"""La palette proposée pour recolorer le logo : ses propres encres, les couleurs du design (fond,
	cartouches et textes des zones, image de fond), puis noir et blanc."""
	from aquaworld_ia.emballage import logo_couleur as LC
	from aquaworld_ia.emballage.composition import couleurs_dominantes
	from aquaworld_ia.emballage.variantes import url_logo, url_photo
	from aquaworld_ia.ia import fichiers

	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("read")
	source = url_logo(doc)
	if not source:
		frappe.throw(_("Attachez d'abord un logo."))
	octets = fichiers.lire(source)
	# La palette du design d'abord (couleurs prises à la pipette, ou saisies) ; puis le logo, la photo, le reste.
	couleurs = [(c, "palette") for c in re.split(r"[\s,;]+", doc.get("palette") or "") if c]
	couleurs += [(c, "logo") for c in LC.couleurs_logo(octets)]
	photo = url_photo(doc)
	if photo:
		try:
			couleurs += [(c, "photo produit") for c in LC.couleurs_logo(fichiers.lire(photo), 5)]
		except Exception:
			pass
	if doc.get("couleur_fond"):
		couleurs.append((doc.couleur_fond, "fond"))
	mep = frappe.parse_json(doc.mise_en_page) if doc.get("mise_en_page") else {}
	for liste in (mep or {}).values():
		for z in liste if isinstance(liste, list) else []:
			st = (z or {}).get("style") if isinstance(z, dict) else None
			for cle in ("fond", "texte"):
				if isinstance(st, dict) and st.get(cle):
					couleurs.append((st[cle], "zones"))
	if doc.get("image_fond"):
		try:
			couleurs += [(c, "image de fond") for c in couleurs_dominantes(fichiers.lire(doc.image_fond), 4)]
		except Exception:
			pass
	couleurs += [("#000000", "noir"), ("#ffffff", "blanc")]
	return {"source": source, "vectoriel": LC.svg_vectoriel(octets), "palette": LC.palette(couleurs)}


@frappe.whitelist()
def logo_couleur(design: str, couleur: str, garder_blanc=1, sortie: str = "svg") -> dict:
	"""Le logo en UNE couleur choisie, en SVG (ou PNG) — un candidat attaché à la fiche, posé seulement si
	l'utilisateur l'adopte. Sans IA : couleur exacte, gratuit (demande utilisateur 06/10/2026)."""
	from aquaworld_ia.emballage import logo_couleur as LC
	from aquaworld_ia.emballage.variantes import url_logo
	from aquaworld_ia.ia import fichiers
	from frappe.utils.file_manager import save_file

	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("write")
	source = url_logo(doc)
	if not source:
		frappe.throw(_("Attachez d'abord un logo."))
	try:
		octets, ext = LC.appliquer(fichiers.lire(source), couleur, bool(cint(garder_blanc)), sortie)
	except ValueError as e:
		frappe.throw(str(e))
	nom = "%s-logo-couleur-%s.%s" % (doc.name, LC.normaliser(couleur)[1:], ext)
	fichier = save_file(nom, octets, "Design Emballage", doc.name, is_private=1)
	return {"candidat": fichier.file_url, "source": source, "format": ext, "taille_ko": round(len(octets) / 1024, 1)}


@frappe.whitelist()
def proposer_fonds(design: str, consigne: str | None = None, nombre=2, mode: str = "nouveau", suivre_style=1,
                   avec_logo=1, continu=None) -> dict:
	"""Des fonds IA À COMPARER, rien n'est remplacé (demande utilisateur 06/10/2026 : « regénérer une image de fond
	que je contrôle bien ») : `mode` « nouveau » (consigne + palette + brief [+ style de la variante] [+ logo en
	référence]) ou « retouche » (le fond ACTUEL en référence, seule la consigne change). La consigne est gardée sur
	la fiche pour être affinée au tour suivant."""
	from aquaworld_ia.emballage import prompts
	from aquaworld_ia.emballage.variantes import plan_du_design, prompt_fond_du_design, url_logo
	from aquaworld_ia.ia import couts, fichiers, images, journal
	from aquaworld_ia.ia.client import qualite_image, reglages
	from frappe.utils.file_manager import save_file

	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("write")
	manque = geometrie.dimensions_manquantes(doc.type_boite or geometrie.ETUI, flt(doc.longueur_mm), flt(doc.hauteur_mm),
	                                         flt(doc.profondeur_mm), flt(doc.get("repli_mm")))
	if manque:
		frappe.throw(_("Renseignez d'abord les dimensions : {0}.").format(", ".join(manque)))
	if continu is not None:
		doc.fond_continu = cint(continu)
	plan = plan_du_design(doc)
	cible = (geometrie.bande(plan) or geometrie.face(plan, "avant")) if cint(doc.fond_continu) else geometrie.face(plan, "avant")
	taille = geometrie.taille_image_pour(cible)
	n = max(1, min(4, cint(nombre) or 2))
	qualite = qualite_image()
	journal.verifier_plafond(couts.cout_variantes(n, qualite, couts.tarifs_depuis_reglages(reglages())))
	consigne = (consigne or "").strip()[:600]
	if mode == "retouche":
		if not doc.image_fond:
			frappe.throw(_("Pas encore de fond à retoucher : générez-en un nouveau."))
		pngs = images.editer(prompts.prompt_retouche_fond(consigne), [("fond", fichiers.lire(doc.image_fond))], taille=taille,
		                     qualite=qualite, n=n, fonctionnalite="Emballage fond", doc=doc, fidelite="high")
	else:
		prompt = prompt_fond_du_design(doc, plan, consigne, bool(cint(suivre_style)))
		logo = url_logo(doc) if cint(avec_logo) else None
		pngs = (images.editer(prompt, [("logo", fichiers.lire(logo))], taille=taille, qualite=qualite, n=n,
		                      fonctionnalite="Emballage fond", doc=doc, fidelite=None) if logo
		        else images.generer(prompt, taille=taille, qualite=qualite, n=n, fonctionnalite="Emballage fond", doc=doc))
	frappe.db.set_value("Design Emballage", design, "consigne_fond", consigne, update_modified=False)
	return {"candidats": [save_file("%s-fond.png" % doc.name, png, "Design Emballage", doc.name, is_private=1).file_url for png in pngs],
	        "actuel": doc.image_fond, "continu": cint(doc.fond_continu)}


COMPOSANTS_FACE = ("fond", "image_face", "photo", "logo")


def _references_face(doc, plan: dict, face: dict, composants: list[str]) -> list[tuple[str, bytes]]:
	"""Les images envoyées à l'IA pour composer UNE face, dans l'ordre des rôles du prompt. Le fond est pris tel
	que la face le porte : sa tranche du panorama en mode continu, sinon l'image recadrée à la face — la
	continuité aux plis est ainsi gardée."""
	from aquaworld_ia.emballage import composition as C
	from aquaworld_ia.emballage.variantes import url_logo, url_photo
	from aquaworld_ia.ia import fichiers

	refs = []
	for c in composants:
		if c == "fond" and doc.image_fond:
			img = fichiers.lire(doc.image_fond)
			bande = geometrie.bande(plan) if cint(doc.fond_continu) else None
			r = C.rect_avec_fond_perdu(face, plan)
			if bande and face["code"] in bande["faces"]:
				rects = [C.rect_avec_fond_perdu(f, plan) for f in plan["faces"] if f["code"] in bande["faces"]]
				bx0, by0 = min(x[0] for x in rects), min(x[1] for x in rects)
				bande = dict(bande, x=bx0, y=by0, w=max(x[0] + x[2] for x in rects) - bx0, h=max(x[1] + x[3] for x in rects) - by0)
				refs.append(("fond", C.tranche_panorama(img, bande, r)))
			else:
				refs.append(("fond", C.recadrer(img, r[2], r[3])))
		elif c == "image_face":
			reg = C.reglage_fond(frappe.parse_json(doc.fonds_faces) if doc.get("fonds_faces") else {}, face["code"])
			if reg and reg.get("image"):
				refs.append(("image_face", fichiers.lire(reg["image"])))
		elif c == "photo" and url_photo(doc):
			refs.append(("photo", fichiers.lire(url_photo(doc))))
		elif c == "logo" and url_logo(doc):
			refs.append(("logo", fichiers.lire(url_logo(doc))))
	return refs


@frappe.whitelist()
def composer_face_ia(design: str, face: str, composants=None, consigne: str | None = None, nombre=2, apercu=0) -> dict:
	"""Une face composée par l'IA à partir des composants choisis (fond, image actuelle de la face, photo, logo) et
	d'une consigne : `nombre` propositions à comparer, rien n'est posé avant « Utiliser ». `apercu` : seulement le
	texte qui partirait à l'IA (rien n'est facturé)."""
	from aquaworld_ia.emballage import prompts
	from aquaworld_ia.emballage.variantes import plan_du_design
	from aquaworld_ia.ia import couts, images, journal
	from aquaworld_ia.ia.client import qualite_image, reglages
	from frappe.utils.file_manager import save_file

	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("read" if cint(apercu) else "write")
	plan = plan_du_design(doc)
	f = geometrie.face(plan, face)
	if not f or not f.get("imprimable"):
		frappe.throw(_("Face inconnue ou non imprimable : {0}").format(face))
	liste = frappe.parse_json(composants) if isinstance(composants, str) else (composants or [])
	liste = [c for c in COMPOSANTS_FACE if c in liste]
	consigne = (consigne or "").strip()[:600]
	prompt = prompts.prompt_composition("%s panel" % (f.get("libelle") or face), doc.nom_produit or doc.article, liste, consigne,
	                                    palette=doc.palette, brief=doc.brief_style or "", famille=plan.get("famille"))
	if cint(apercu):
		return {"prompt": prompt}
	refs = _references_face(doc, plan, f, liste)
	if not refs:
		frappe.throw(_("Choisissez au moins un composant disponible (fond, photo, logo…)."))
	n = max(1, min(4, cint(nombre) or 2))
	qualite = qualite_image()
	journal.verifier_plafond(couts.cout_variantes(n, qualite, couts.tarifs_depuis_reglages(reglages())))
	pngs = images.editer(prompt, refs, taille=geometrie.taille_image_pour(f), qualite=qualite, n=n,
	                     fonctionnalite="Emballage faces", doc=doc, fidelite="high")
	fonds = frappe.parse_json(doc.fonds_faces) if doc.get("fonds_faces") else {}
	reg = fonds.get(face) if isinstance(fonds.get(face), dict) else {}
	frappe.db.set_value("Design Emballage", design, "fonds_faces",
	                    json.dumps(dict(fonds, **{face: dict(reg, consigne=consigne)}), ensure_ascii=False), update_modified=False)
	envoyes = [r[0] for r in refs]
	return {"candidats": [save_file("%s-face-%s.png" % (doc.name, face), png, "Design Emballage", doc.name, is_private=1).file_url
	                      for png in pngs],
	        "actuel": reg.get("image") if reg.get("mode") == "image" else doc.image_fond, "face": face,
	        # Le produit est dans la nouvelle image si la photo a été envoyée, OU si l'image de la face qui sert de base le
	        # contenait déjà (06/10/2026 : recomposée sans cocher la photo, la face a montré DEUX fois le produit).
	        "photo_incluse": "photo" in envoyes or ("image_face" in envoyes and bool(reg.get("photo_incluse")))}


@frappe.whitelist()
def adopter_face_ia(design: str, face: str, url: str, photo_incluse=0) -> dict:
	"""L'image composée devient le fond de CETTE face ; si elle contient le produit, la photo n'y est plus posée
	par-dessus. Le plan se recompose."""
	from aquaworld_ia.emballage.composition import composer_et_attacher

	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("write")
	_image_lisible(doc, url)
	fonds = frappe.parse_json(doc.fonds_faces) if doc.get("fonds_faces") else {}
	reg = fonds.get(face) if isinstance(fonds.get(face), dict) else {}
	fonds[face] = dict(reg, mode="image", image=url, photo_incluse=bool(cint(photo_incluse)))
	doc.fonds_faces = json.dumps(fonds, ensure_ascii=False)
	doc.apercu_3d = None
	doc.save()
	recompose = False
	try:
		composer_et_attacher(design, cint(doc.variante_choisie))
		recompose = True
	except Exception:
		frappe.log_error(title="Aquaworld IA : recomposition après face %s" % design, message=frappe.get_traceback())
	return dict(charger(design), recompose=recompose)


@frappe.whitelist()
def blanchir(design: str, cible: str = "fond") -> dict:
	"""« ⚪ Blanc pur » : le presque blanc de l'image de fond (`cible` = « fond ») ou de l'image IA d'une face
	(`cible` = code de la face) devient du blanc pur. Nouvelle version posée à la place (l'ancienne reste dans
	l'onglet Images), plan recomposé. Sans IA."""
	from aquaworld_ia.emballage import composition as C
	from aquaworld_ia.ia import fichiers
	from frappe.utils.file_manager import save_file

	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("write")
	fonds = frappe.parse_json(doc.fonds_faces) if doc.get("fonds_faces") else {}
	if cible == "fond":
		url = doc.image_fond
	else:
		reg = C.reglage_fond(fonds, cible)
		url = reg.get("image") if reg else None
	if not url:
		frappe.throw(_("Pas d'image à blanchir ici."))
	avant = fichiers.lire(url)
	apres = C.blanc_pur(avant)
	nom = "%s-fond.png" % doc.name if cible == "fond" else "%s-face-%s.png" % (doc.name, cible)
	nouvelle = save_file(nom, apres, "Design Emballage", doc.name, is_private=1).file_url
	if cible == "fond":
		doc.image_fond = nouvelle
	else:
		fonds[cible] = dict(fonds[cible], image=nouvelle)
		doc.fonds_faces = json.dumps(fonds, ensure_ascii=False)
	doc.apercu_3d = None
	doc.save()
	recompose = False
	try:
		C.composer_et_attacher(design, cint(doc.variante_choisie))
		recompose = True
	except Exception:
		frappe.log_error(title="Aquaworld IA : recomposition après blanc pur %s" % design, message=frappe.get_traceback())
	return dict(charger(design), recompose=recompose,
	            blanc_avant=round(C.part_blanc_pur(avant) * 100), blanc_apres=round(C.part_blanc_pur(apres) * 100))


@frappe.whitelist()
def adopter_fond(design: str, url: str, continu=None) -> dict:
	"""Le fond choisi devient l'image de fond, et le plan se recompose (s'il peut l'être)."""
	from aquaworld_ia.emballage.composition import composer_et_attacher

	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("write")
	_image_lisible(doc, url)
	doc.image_fond = url
	if continu is not None:
		doc.fond_continu = cint(continu)
	doc.apercu_3d = None
	doc.save()
	recompose = False
	if geometrie.dimensions_manquantes(doc.type_boite or geometrie.ETUI, flt(doc.longueur_mm), flt(doc.hauteur_mm),
	                                   flt(doc.profondeur_mm), flt(doc.get("repli_mm"))) == []:
		try:
			composer_et_attacher(design, cint(doc.variante_choisie))
			recompose = True
		except Exception:
			frappe.log_error(title="Aquaworld IA : recomposition après fond %s" % design, message=frappe.get_traceback())
	return dict(charger(design), recompose=recompose)


@frappe.whitelist()
def creer_tampons(design: str, texte: str, forme: str | None = None, style: str | None = None, couleurs=None,
                  idee: str | None = None, nombre=3) -> dict:
	"""Des tampons SVG dessinés par l'IA (demande utilisateur 06/10/2026 : « un tampon comme le poids ») :
	`nombre` propositions vectorielles, aux couleurs données, chacune attachée à la fiche — rien n'est posé
	tant que l'utilisateur n'en adopte pas une."""
	from aquaworld_ia.emballage import logo_couleur as LC
	from aquaworld_ia.emballage import tampon as T
	from aquaworld_ia.ia.chat import chat_json
	from frappe.utils.file_manager import save_file

	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("write")
	texte = (texte or "").strip()
	if not texte:
		frappe.throw(_("Écrivez le texte du tampon (ex. « POIDS NET » puis « 25 KG »)."))
	liste = frappe.parse_json(couleurs) if isinstance(couleurs, str) and couleurs.startswith("[") else (couleurs or [])
	if isinstance(liste, str):
		liste = re.split(r"[\s,;]+", liste)
	liste = [c for c in (LC.normaliser(x) for x in liste) if c][:4] or ["#1e3a8a"]
	n = max(1, min(4, cint(nombre) or 3))
	system, user = T.prompts(texte, forme, style, liste, idee or "", n)
	tampons = T.preparer(chat_json(system, user, fonctionnalite="Tampon IA", doc=doc))
	if not tampons:
		frappe.throw(_("L'IA n'a rendu aucun tampon imprimable : réessayez (ou simplifiez le texte)."))
	return {"tampons": [{"titre": t["titre"],
	                     "url": save_file("%s-tampon.svg" % doc.name, t["svg"].encode("utf-8"), "Design Emballage", doc.name,
	                                      is_private=1).file_url} for t in tampons]}


@frappe.whitelist()
def adopter_tampon(design: str, url: str, libelle: str, taille_mm=25) -> dict:
	"""Le tampon choisi devient un PICTOGRAMME (catégorie « Tampon ») réutilisable par tous les designs, et
	il est coché sur celui-ci : il se pose ensuite par une zone « Pictogrammes »."""
	from aquaworld_ia.ia import fichiers
	from frappe.utils.file_manager import save_file

	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("write")
	frappe.only_for(("System Manager", "Aquaworld IA", "Item Manager", "Stock Manager", "Sales Manager"))
	libelle = (libelle or "").strip() or _("Tampon")
	octets = fichiers.lire(url)
	base = frappe.scrub(libelle)[:40] or "tampon"
	code, n = base, 2
	while frappe.db.exists("Aquaworld IA Pictogramme", code):
		code = "%s_%d" % (base, n)
		n += 1
	picto = frappe.get_doc({"doctype": "Aquaworld IA Pictogramme", "code": code, "libelle": libelle, "categorie": "Tampon",
	                        "taille_mm": flt(taille_mm) or 25, "actif": 1}).insert()
	fichier = save_file("%s.svg" % code, octets, "Aquaworld IA Pictogramme", picto.name, is_private=0)
	picto.db_set("image", fichier.file_url)
	doc.append("pictogrammes", {"pictogramme": picto.name})
	doc.save()
	return dict(charger(design), tampon=picto.name)


@frappe.whitelist()
def adopter_logo(design: str, url: str) -> dict:
	"""Le candidat devient le logo : fond blanc rendu transparent, fichier propre attaché."""
	from aquaworld_ia.emballage.composition import fond_blanc_en_transparence
	from aquaworld_ia.ia import fichiers
	from frappe.utils.file_manager import save_file

	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("write")
	png = fond_blanc_en_transparence(fichiers.lire(url))
	fichier = save_file("%s-logo.png" % doc.name, png, "Design Emballage", doc.name, is_private=1)
	doc.logo = fichier.file_url
	doc.save()
	return charger(design)


#: Champs du design que la bibliothèque sait remplir, et les catégories qui leur correspondent.

def _mosaique_images(doc, cfg: dict, max_px: int | None):
	"""Les images détourées des cases ; en aperçu (`max_px`), gardées 10 min en cache (un réglage changé ne relit pas
	quatre photos de 4 Mo)."""
	import base64
	import io as _io

	from PIL import Image

	from aquaworld_ia.emballage import mosaique as M
	from aquaworld_ia.ia import fichiers

	out = []
	for c in cfg["cases"]:
		url = _image_lisible(doc, c["url"])
		cle = "aqia:mosaique:%s:%s:%s" % (url, int(cfg["detourer"]), max_px or 0)
		en_cache = frappe.cache().get_value(cle) if max_px else None
		if en_cache:
			out.append(Image.open(_io.BytesIO(base64.b64decode(en_cache))).convert("RGBA"))
			continue
		im = M.produit_detoure(fichiers.lire(url), detourer=cfg["detourer"], max_px=max_px)
		if max_px:
			buf = _io.BytesIO()
			im.save(buf, format="PNG")
			frappe.cache().set_value(cle, base64.b64encode(buf.getvalue()).decode(), expires_in_sec=600)
		out.append(im)
	return out


@frappe.whitelist()
def mosaique_apercu(design: str, config) -> dict:
	"""L'aperçu de la mosaïque (900 px de large, data URI) — rien n'est enregistré."""
	import base64

	from aquaworld_ia.emballage import mosaique as M

	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("read")
	cfg = M.normaliser(json.loads(config) if isinstance(config, str) else config)
	if not cfg["cases"]:
		return {"image": None}
	png = M.composer(cfg, _mosaique_images(doc, cfg, max_px=700), largeur=900)
	return {"image": "data:image/png;base64," + base64.b64encode(png).decode()}


@frappe.whitelist()
def mosaique_creer(design: str, config, adopter=1) -> dict:
	"""La mosaïque en pleine définition (2 400 px), attachée au design (onglet Images) ; ses réglages gardés sur la
	fiche ; `adopter` : elle devient la photo du produit."""
	from aquaworld_ia.emballage import mosaique as M
	from frappe.utils.file_manager import save_file

	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("write")
	cfg = M.normaliser(json.loads(config) if isinstance(config, str) else config)
	if len(cfg["cases"]) < 2:
		frappe.throw(_("Choisissez au moins deux variantes du produit."))
	png = M.composer(cfg, _mosaique_images(doc, cfg, max_px=None))
	url = save_file("%s-mosaique.png" % doc.name, png, "Design Emballage", doc.name, is_private=1).file_url
	valeurs = {"mosaique": json.dumps(cfg, ensure_ascii=False)}
	if cint(adopter):
		valeurs["photo_produit"] = url
	doc.update(valeurs)
	doc.save()
	frappe.db.commit()
	out = charger(design)
	out["mosaique_url"] = url
	return out


EXTENSIONS_IMAGE = ("png", "jpg", "jpeg", "webp")


@frappe.whitelist()
def photos_autres_articles(recherche: str, design: str | None = None, limite: int = 12) -> list:
	"""Les photos d'autres produits, pour une mosaïque (14/10/2026) : par article trouvé (code ou nom), son image ERPNext,
	ses pièces jointes images, et les photos de ses designs d'emballage (photo produit, photos IA).
	[{article, nom, photos: [{url, source}]}] — seulement les articles qui ont au moins une photo."""
	frappe.has_permission("Item", "read", throw=True)
	recherche = (recherche or "").strip()
	if len(recherche) < 2:
		return []
	q = "%%%s%%" % recherche
	articles = frappe.get_all("Item", or_filters={"item_code": ["like", q], "item_name": ["like", q]},
	                          fields=["name", "item_name", "image"], limit_page_length=int(limite or 12) * 3)
	est_image = lambda u: (u or "").rsplit(".", 1)[-1].lower() in EXTENSIONS_IMAGE
	# Import local : studio importe ce module en fin de fichier, un import de tête serait circulaire.
	from aquaworld_ia.emballage.studio import genre_image
	out = []
	for a in articles:
		photos, vus = [], set()

		def ajouter(url, source):
			if url and est_image(url) and url not in vus:
				vus.add(url)
				photos.append({"url": url, "source": source})

		ajouter(a.image, _("Article"))
		for f in frappe.get_all("File", filters={"attached_to_doctype": "Item", "attached_to_name": a.name, "is_folder": 0},
		                        fields=["file_url"], order_by="creation desc", limit_page_length=8):
			ajouter(f.file_url, _("Pièce jointe"))
		for dz in frappe.get_all("Design Emballage", filters={"article": a.name, "name": ["!=", design or ""]},
		                         fields=["name", "photo_produit"], limit_page_length=5):
			ajouter(dz.photo_produit, dz.name)
			for f in frappe.get_all("File", filters={"attached_to_doctype": "Design Emballage", "attached_to_name": dz.name, "is_folder": 0},
			                        fields=["file_name", "file_url"], order_by="creation desc", limit_page_length=40):
				genre = genre_image(f.file_name, dz.name) or ""
				if genre.startswith("Photo"):
					ajouter(f.file_url, "%s · %s" % (dz.name, genre))
		if photos:
			out.append({"article": a.name, "nom": a.item_name or a.name, "photos": photos[:12]})
		if len(out) >= int(limite or 12):
			break
	return out


PROMPT_ORIENTATION = (
	"Two reference images. Image 1 (\"produit\") is THE product to show: keep it EXACTLY as it is (shape, proportions, "
	"colors, transparency, materials, fittings, labels, text on it) — no redesign, no added or removed parts. Image 2 "
	"(\"orientation\") is ONLY a reference for the point of view: redraw the product of image 1 seen from exactly the same "
	"camera angle and orientation as the product of image 2 — same side facing the camera, inlet/outlet ports, bracket and "
	"handles pointing the same direction, same tilt — with the same framing and soft even studio lighting. Never copy the "
	"product, colors, transparency or parts of image 2: they all come from image 1. Clean cut-out on a PURE WHITE "
	"background, no shadow scene, no text, no logo.")


@frappe.whitelist()
def orienter_variante(design: str, url: str, reference: str, reference_miroir=0, nombre=1, consigne: str | None = None) -> dict:
	"""Une variante de la mosaïque redessinée sous le MÊME angle que la référence (14/10/2026 : « que tous les modèles
	soient orientés de la même façon »). La référence ne sert qu'au point de vue ; `reference_miroir` : elle est
	retournée dans la mosaïque, c'est donc l'orientation retournée qu'on vise. Propositions attachées au design
	(« Photo IA »), rien n'est remplacé avant le choix."""
	from aquaworld_ia.ia import fichiers, images
	from aquaworld_ia.ia.client import qualite_image
	from frappe.utils.file_manager import save_file

	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("write")
	source, ref = _image_lisible(doc, url), _image_lisible(doc, reference)
	octets, octets_ref = fichiers.lire(source), fichiers.lire(ref)
	if cint(reference_miroir):
		from PIL import Image, ImageOps

		buf = io.BytesIO()
		ImageOps.mirror(Image.open(io.BytesIO(octets_ref)).convert("RGBA")).save(buf, format="PNG")
		octets_ref = buf.getvalue()
	n = max(1, min(4, cint(nombre) or 1))
	prompt = PROMPT_ORIENTATION
	consigne = (consigne or "").strip().rstrip(".")
	if consigne:
		# une correction après une erreur visuelle (« sans la clé ni le support ») : en plus, jamais à la place
		prompt += " Additionally, apply this change requested by the user: %s." % consigne
	pngs = images.editer(prompt, [("produit", octets), ("orientation", octets_ref)],
	                     taille=taille_retouche("photo_produit", octets), qualite=qualite_image(), n=n,
	                     fonctionnalite="Emballage image", doc=doc, fidelite="high")
	candidats = [save_file("%s-photo-ia.png" % doc.name, png, "Design Emballage", doc.name, is_private=1).file_url for png in pngs]
	return {"candidats": candidats, "source": source}


PROMPT_CORRECTION_ORIENTATION = (
	"Two reference images. Image 1 (\"proposition\") is the current rendering: its camera angle and orientation are "
	"CORRECT and must be kept exactly (same side facing the camera, ports, bracket and handles pointing the same way, same "
	"tilt, same framing). Image 2 (\"produit\") is the original photo of the product: the ground truth for its look — "
	"shape, proportions, colors, transparency, materials, fittings, labels and text. Redraw image 1 applying ONLY this "
	"correction: %s; and remove any difference of look with image 2, without changing the angle of image 1. Clean cut-out "
	"on a PURE WHITE background, soft even studio lighting, sharp focus, no shadow scene, no text, no logo.")


PROMPT_REFERENCE_SILHOUETTE = (
	" Image 3 (\"silhouette\") is a FLAT GRAY SILHOUETTE of another product, chosen by the user: it has no colors, no "
	"materials and no details on purpose. Use it ONLY to match the overall proportions and outline the correction asks for "
	"(height to width ratio, relative size of the head, the bowl, the bracket). Every color, material, transparency, part "
	"and detail stays exactly that of image 2 (the product) — the result must still clearly be the product of image 2.")


def silhouette_png(octets: bytes) -> bytes:
	"""Une référence réduite à sa SILHOUETTE grise unie (14/10/2026) : demandée « pour les proportions », la photo de
	l'image principale faisait recopier son produit entier (cuve transparente sur le porte-filtre noir et bleu) ; une
	silhouette ne porte que le contour — ni couleur, ni matière, ni transparence, rien à recopier. PNG gris sur blanc."""
	from PIL import Image

	from aquaworld_ia.emballage.mosaique import produit_detoure

	im = produit_detoure(octets, detourer=True)
	masque = im.getchannel("A").point(lambda a: 255 if a > 40 else 0)
	marge = max(20, round(max(im.size) * 0.08))
	fond = Image.new("RGB", (im.width + 2 * marge, im.height + 2 * marge), (255, 255, 255))
	fond.paste(Image.new("RGB", im.size, (150, 150, 150)), (marge, marge), masque)
	buf = io.BytesIO()
	fond.save(buf, format="PNG")
	return buf.getvalue()


def consigne_proportions(ratio_reference: float, ratio_produit: float) -> str:
	"""La cible CHIFFRÉE des proportions, mesurée sur les deux images détourées (hauteur / largeur). PUR.
	Essai réel du 14/10/2026 : avec « les proportions comme la référence » en toutes lettres, l'IA rendait le produit à
	l'identique (2,64 → 2,64, silhouette à 2,18) ; avec un chiffre et un sens (« plus court et plus large »), 2,64 → 2,06.
	Rien si l'écart est sous 5 % (l'IA ne sait pas faire plus fin)."""
	if not ratio_reference or not ratio_produit or abs(ratio_produit / ratio_reference - 1) < 0.05:
		return ""
	sens = ("shorter and wider (mostly the bowl/body)" if ratio_produit > ratio_reference
	        else "taller and narrower (mostly the bowl/body)")
	return (" MEASURED TARGET: the product in image 1 is currently %.2f times as tall as it is wide (bracket included); "
	        "the silhouette is %.2f. Make the product %s until it is about %.2f times as tall as wide, keeping its head, "
	        "its bracket and every part, color and material." % (ratio_produit, ratio_reference, sens, ratio_reference))


def _ratio_hauteur_largeur(octets: bytes) -> float:
	from aquaworld_ia.emballage.mosaique import produit_detoure

	try:
		im = produit_detoure(octets, detourer=True, max_px=768)
		return im.height / im.width if im.width else 0
	except Exception:
		return 0


PROMPT_REFERENCE_CHOISIE = (
	" Image 3 (\"reference\") was chosen by the user for this correction: use it ONLY for what the correction "
	"refers to (a part, a color, a material, a shape), and copy nothing else from it — the rest of the product comes from "
	"image 2 and the camera angle from image 1.")


@frappe.whitelist()
def corriger_orientation(design: str, proposition: str, original: str, correction: str, reference: str | None = None,
                         reference_miroir=0, nombre=1, reference_choisie: str | None = None,
                         reference_mode: str = "forme") -> dict:
	"""Corriger une proposition « même orientation » (14/10/2026 : « à chaque correction, lui redonner les références »).
	L'IA reçoit la proposition (son ANGLE fait foi, il est déjà le bon) et, à chaque fois, la photo d'ORIGINE de la
	variante (son APPARENCE fait foi), plus la correction écrite. L'image principale n'est PAS renvoyée : essai du
	14/10, donnée en photo, l'IA a recopié sa cuve transparente sur le porte-filtre bleu opaque ; donnée au trait, l'angle
	n'était plus suivi. `reference` est accepté pour compatibilité, non utilisé. Propositions attachées au design."""
	from aquaworld_ia.ia import fichiers, images
	from aquaworld_ia.ia.client import qualite_image
	from frappe.utils.file_manager import save_file

	doc = frappe.get_doc("Design Emballage", design)
	doc.check_permission("write")
	correction = (correction or "").strip().rstrip(".")
	if not correction:
		frappe.throw(_("Écrivez la correction à apporter."))
	octets_prop = fichiers.lire(_image_lisible(doc, proposition))
	octets_orig = fichiers.lire(_image_lisible(doc, original))
	n = max(1, min(4, cint(nombre) or 1))
	prompt, refs = PROMPT_CORRECTION_ORIENTATION % correction, [("proposition", octets_prop), ("produit", octets_orig)]
	fidelite = "high"
	if reference_choisie:
		# une image désignée par l'utilisateur pour CETTE correction (14/10/2026 : « corriger en faisant référence à une
		# autre image ») : la tête d'une autre variante, la cuve de l'image principale… — pour ce que dit la correction
		# seulement ; le reste vient toujours de l'image 1 (angle) et de l'image 2 (apparence).
		octets_choisie = fichiers.lire(_image_lisible(doc, reference_choisie))
		if reference_mode == "photo":
			# une PIÈCE, une couleur, une matière à reprendre : il faut la photo (elle « fuit » un peu)
			refs.append(("reference", octets_choisie))
			prompt += PROMPT_REFERENCE_CHOISIE
		else:
			# des PROPORTIONS, une forme : la silhouette suffit, et elle ne peut rien faire recopier d'autre. Fidélité
			# BASSE : en « high », l'IA collait à l'image d'entrée et ne changeait pas la forme (essai réel du 14/10,
			# porte-filtre noir et bleu : identique) ; en « low », cuve raccourcie et élargie comme la silhouette, tête
			# noire, corps bleu opaque et support gardés.
			refs.append(("silhouette", silhouette_png(octets_choisie)))
			prompt += PROMPT_REFERENCE_SILHOUETTE + consigne_proportions(_ratio_hauteur_largeur(octets_choisie),
			                                                             _ratio_hauteur_largeur(octets_prop))
			fidelite = "low"
	pngs = images.editer(prompt, refs,
	                     taille=taille_retouche("photo_produit", octets_prop), qualite=qualite_image(), n=n,
	                     fonctionnalite="Emballage image", doc=doc, fidelite=fidelite)
	candidats = [save_file("%s-photo-ia.png" % doc.name, png, "Design Emballage", doc.name, is_private=1).file_url for png in pngs]
	return {"candidats": candidats}
