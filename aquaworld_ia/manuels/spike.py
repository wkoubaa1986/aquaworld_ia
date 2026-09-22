"""Spike de faisabilité / outil de diagnostic : traduit quelques pages d'un PDF depuis la ligne
de commande, sans fiche, et rend les statistiques.

    bench --site mysite.localhost execute aquaworld_ia.manuels.spike.executer \\
        --kwargs "{'chemin_pdf': '/workspace/development/ia_samples/manuel.pdf', 'langue': 'ar', 'pages': '1-5'}"

Critères de passage (plan) : ≥ 95 % des blocs posés sans échelle < 0,7 (FR) / 0,6 (AR), images
intactes, arabe façonné à droite, nombres/unités conservés, < 3 min et < 0,10 $ par langue pour
40 pages.
"""

from __future__ import annotations

import io
import os
import time

import frappe

from aquaworld_ia.ia import journal
from aquaworld_ia.manuels.extraction import extraire_paragraphes
from aquaworld_ia.manuels.rendu import reecrire_document
from aquaworld_ia.manuels.traduction import traduire_tout

LANGUES_REPLI = {
	"fr": {"code": "fr", "libelle": "Français", "libelle_natif": "Français", "rtl": 0, "police": "Noto Sans"},
	"ar": {"code": "ar", "libelle": "Arabe", "libelle_natif": "العربية", "rtl": 1, "police": "Noto Naskh Arabic",
	       "instructions": "Arabe standard moderne ; chiffres occidentaux ; unités telles quelles."},
}


def _selection(pdf: bytes, pages: str) -> bytes:
	if not pages:
		return pdf
	import pymupdf

	doc = pymupdf.open(stream=pdf, filetype="pdf")
	indices = []
	for morceau in pages.split(","):
		if "-" in morceau:
			a, b = morceau.split("-", 1)
			indices.extend(range(int(a) - 1, int(b)))
		else:
			indices.append(int(morceau) - 1)
	doc.select([i for i in indices if 0 <= i < len(doc)])
	sortie = io.BytesIO()
	doc.save(sortie)
	return sortie.getvalue()


def executer(chemin_pdf: str, langue: str = "fr", pages: str = "", sortie: str = "", glossaire: str = "") -> dict:
	with open(chemin_pdf, "rb") as fh:
		pdf = _selection(fh.read(), pages)
	infos = None
	try:
		infos = frappe.db.get_value("Aquaworld IA Langue", langue,
		                            ["code", "libelle", "libelle_natif", "rtl", "police", "instructions"], as_dict=True)
	except Exception:
		pass
	infos = infos or LANGUES_REPLI.get(langue) or {"code": langue, "libelle": langue, "rtl": 0}
	debut = time.monotonic()
	cout_avant = journal.cout_du_mois()
	paragraphes, meta = extraire_paragraphes(pdf)
	traductions, laisses = traduire_tout(paragraphes, infos, glossaire=glossaire, taille_lot=25,
	                                     progression=lambda f, t: print("lot %d/%d" % (f, t)))
	resultat, stats = reecrire_document(pdf, paragraphes, traductions, infos)
	dossier = sortie or os.path.dirname(os.path.abspath(chemin_pdf))
	nom = os.path.splitext(os.path.basename(chemin_pdf))[0] + "-%s.pdf" % langue
	chemin = os.path.join(dossier, nom)
	with open(chemin, "wb") as fh:
		fh.write(resultat)
	frappe.db.commit()
	return {
		"fichier": chemin, "pages": meta["pages"], "blocs": meta["blocs"], "traduits": len(traductions),
		"laisses_en_anglais": len(laisses), "poses": stats["poses"], "reduits": stats["reduits"],
		"non_places": stats["non_places"], "pivotes": stats["pivotes"],
		"duree_s": round(time.monotonic() - debut, 1), "cout_usd": round(journal.cout_du_mois() - cout_avant, 4),
	}
