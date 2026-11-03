"""Empreinte du contenu rendu : un ancien PDF reste accessible mais n’est jamais présenté à jour."""
from __future__ import annotations

import hashlib
import json

from aquaworld_ia.emballage import contenus, geometrie

# Une correction du moteur périme aussi le PDF et les textures 3D déjà calculés.
VERSION_RENDU = 2

CHAMPS_RENDU = (
	"article", "nom_produit", "marque", "logo", "photo_produit", "type_boite", "longueur_mm", "hauteur_mm",
	"profondeur_mm", "repli_mm", "fond_perdu_mm", "zone_securite_mm", "patte_collage_mm",
	"type_code_barres", "code_barres", "url_qr", "couleur_qr", "couleur_fond", "image_fond",
	"faces_identiques", "cotes_identiques", "pictos_sans_cartouche", "fond_continu", "palette",
	"police_caracteristiques", "taille_caracteristiques", "ameliorer_images_pdf",
)


def empreinte(doc):
	valeurs = {c: doc.get(c) for c in CHAMPS_RENDU}
	valeurs.update(version_rendu=VERSION_RENDU, textes=contenus.imprimes(doc), langues=contenus.langues(doc),
	               pictogrammes=[p.get("pictogramme") for p in doc.get("pictogrammes") or []],
	               mise_en_page=contenus.objet(doc.get("mise_en_page")),
	               fonds_faces=contenus.objet(doc.get("fonds_faces")))
	v = next((v for v in doc.get("variantes") or [] if v.get("numero") == doc.get("variante_choisie")), None)
	valeurs["variante"] = {k: v.get(k) for k in ("numero", "image", "face_arriere", "face_gauche",
	                      "face_droite", "face_dessus", "face_dessous")} if v else None
	return hashlib.sha256(json.dumps(valeurs, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def etat(doc):
	actuelle = empreinte(doc)
	pret = bool(doc.get("plan_a_plat") and doc.get("empreinte_plan") == actuelle)
	return {"pdf": "a_jour" if pret else "a_regenerer" if doc.get("plan_a_plat") else "absent",
	        "simulation_a_jour": bool(pret and doc.get("apercu_3d") and doc.get("empreinte_3d") == actuelle)}


def verifier(doc):
	problemes = geometrie.dimensions_manquantes(doc.get("type_boite") or geometrie.ETUI,
		float(doc.get("longueur_mm") or 0), float(doc.get("hauteur_mm") or 0),
		float(doc.get("profondeur_mm") or 0), float(doc.get("repli_mm") or 0))
	erreurs = ["Renseignez les dimensions : %s." % ", ".join(problemes)] if problemes else []
	if not (doc.get("nom_produit") or doc.get("article")):
		erreurs.append("Renseignez le nom du produit.")
	return erreurs
