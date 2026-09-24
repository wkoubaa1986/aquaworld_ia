"""Traduction d'un Manuel Article : lancement, état, worker.

Une langue = une itération commit-ée : un job qui tombe à la 3e langue laisse les deux PDF déjà
produits. Un échec de langue n'arrête pas les suivantes ; le statut final le dit (Partiel).
"""

from __future__ import annotations

import time

import frappe
from frappe import _
from frappe.utils import cint, now_datetime
from frappe.utils.file_manager import save_file

from aquaworld_ia.ia import etat, fichiers, journal
from aquaworld_ia.ia.client import reglages
from aquaworld_ia.manuels.extraction import extraire_paragraphes
from aquaworld_ia.manuels.rendu import reecrire_document
from aquaworld_ia.manuels.traduction import traduire_tout

GENRE = "manuel"
EVENEMENT = "aqia_manuel"


def _doc(manuel: str, droit: str = "write"):
	doc = frappe.get_doc("Manuel Article", manuel)
	doc.check_permission(droit)
	return doc


def langue_infos(code: str) -> dict:
	d = frappe.db.get_value("Aquaworld IA Langue", code, ["code", "libelle", "libelle_natif", "rtl", "police", "instructions"], as_dict=True)
	return d or {"code": code, "libelle": code, "rtl": 0}


@frappe.whitelist()
def ajouter_langues_actives(manuel: str) -> list:
	doc = _doc(manuel)
	presentes = {l.langue for l in doc.traductions}
	# La langue source du manuel (anglais, active depuis le 24/09/2026 pour les emballages) ne se
	# traduit pas vers elle-même.
	presentes.add((doc.langue_source or "en").strip().lower())
	ajoutees = []
	for code in frappe.get_all("Aquaworld IA Langue", filters={"actif": 1}, pluck="name", order_by="name"):
		if code not in presentes:
			doc.append("traductions", {"langue": code, "statut": "En attente"})
			ajoutees.append(code)
	if ajoutees:
		doc.save(ignore_permissions=True)
	return ajoutees


@frappe.whitelist()
def lancer(manuel: str, langues=None) -> dict:
	doc = _doc(manuel)
	if not doc.pdf_source:
		frappe.throw(_("Attachez d'abord le PDF source."))
	if etat.bloque(etat.lire_etat(GENRE, manuel)):
		frappe.throw(_("Une traduction est déjà en cours pour ce manuel."))
	journal.verifier_plafond()
	langues = frappe.parse_json(langues) if isinstance(langues, str) else langues
	cibles = [l for l in doc.traductions if (not langues or l.langue in langues) and l.statut != "En cours"]
	if langues is None:
		cibles = [l for l in cibles if l.statut != "Terminé"]
	if not cibles:
		frappe.throw(_("Aucune langue à traduire : ajoutez des langues ou sélectionnez-en."))
	for l in cibles:
		l.statut, l.erreur = "En attente", None
	doc.statut = "En cours"
	doc.save(ignore_permissions=True)
	etat.demarrer(GENRE, manuel, langues=[l.langue for l in cibles])
	frappe.enqueue("aquaworld_ia.manuels.job.traduire_manuel", queue="long", timeout=3600,
	               job_id="aqia-manuel-%s" % manuel, deduplicate=True,
	               manuel=manuel, langues=[l.langue for l in cibles], utilisateur=frappe.session.user)
	return etat.lire_etat(GENRE, manuel)


@frappe.whitelist()
def etat_manuel(manuel: str) -> dict:
	_doc(manuel, "read")
	e = etat.lire_etat(GENRE, manuel)
	e["bloque"] = etat.bloque(e)
	e["cout_document"] = journal.cout_document("Manuel Article", manuel)
	return e


def _ligne(manuel: str, code: str):
	nom = frappe.db.get_value("Manuel Article Traduction", {"parent": manuel, "langue": code}, "name")
	return nom


def _journal(doc, lignes: list[str]) -> None:
	horodatage = now_datetime().strftime("%d/%m/%Y %H:%M")
	texte = "\n".join(["[%s]" % horodatage] + lignes)
	ancien = frappe.db.get_value("Manuel Article", doc.name, "journal") or ""
	frappe.db.set_value("Manuel Article", doc.name, "journal", (texte + "\n\n" + ancien)[:20000], update_modified=False)


def traduire_manuel(manuel: str, langues: list[str], utilisateur: str | None = None) -> None:
	doc = frappe.get_doc("Manuel Article", manuel)
	r = reglages()
	taille_lot = cint(getattr(r, "lot_paragraphes", 25)) or 25
	glossaire = "\n".join(x for x in (getattr(r, "glossaire_global", "") or "", doc.glossaire or "") if x)
	instructions = getattr(r, "instructions_globales", "") or ""
	rapport = []
	try:
		pdf = fichiers.lire(doc.pdf_source)
		etat.progresser(GENRE, manuel, "extraction du texte", 2, EVENEMENT, utilisateur)
		paragraphes, meta = extraire_paragraphes(pdf)
		frappe.db.set_value("Manuel Article", manuel, {"pages": meta["pages"], "blocs": meta["blocs"]}, update_modified=False)
		frappe.db.commit()
	except Exception as e:
		frappe.log_error(title="Aquaworld IA : extraction %s" % manuel, message=frappe.get_traceback())
		for code in langues:
			nom = _ligne(manuel, code)
			if nom:
				frappe.db.set_value("Manuel Article Traduction", nom, {"statut": "Échec", "erreur": str(e)[:500]}, update_modified=False)
		frappe.db.set_value("Manuel Article", manuel, "statut", "Échec", update_modified=False)
		_journal(doc, ["Extraction impossible : %s" % str(e)[:300]])
		frappe.db.commit()
		etat.terminer(GENRE, manuel, "echec", erreur=str(e)[:300])
		etat.progresser(GENRE, manuel, "échec", 100, EVENEMENT, utilisateur, fin=1)
		return

	reussies = 0
	for k, code in enumerate(langues):
		nom = _ligne(manuel, code)
		if not nom:
			continue
		langue = langue_infos(code)
		frappe.db.set_value("Manuel Article Traduction", nom, {"statut": "En cours", "erreur": None}, update_modified=False)
		frappe.db.commit()
		base = int(100 * k / len(langues))
		part = int(100 / len(langues))
		debut = time.monotonic()
		cout_avant = journal.cout_document("Manuel Article", manuel)

		def progression(fait, total, base=base, part=part, langue=langue):
			etat.progresser(GENRE, manuel, "%s : lot %d / %d" % (langue["libelle"], fait, total),
			                base + int(part * 0.8 * fait / max(1, total)), EVENEMENT, utilisateur, langue=langue["code"])

		try:
			traductions, laisses = traduire_tout(paragraphes, langue, glossaire=glossaire, instructions=instructions,
			                                     contexte=doc.contexte or "", doc=doc, taille_lot=taille_lot,
			                                     progression=progression)
			etat.progresser(GENRE, manuel, "%s : mise en page" % langue["libelle"], base + int(part * 0.85), EVENEMENT,
			                utilisateur, langue=code)
			sortie, stats = reecrire_document(pdf, paragraphes, traductions, langue)
			nom_fichier = "%s-%s.pdf" % (frappe.scrub(doc.titre or doc.article)[:60], code)
			fichier = save_file(nom_fichier, sortie, "Manuel Article", manuel, is_private=1)
			frappe.db.set_value("Manuel Article Traduction", nom, {
				"statut": "Terminé", "fichier": fichier.file_url, "blocs_reduits": stats["reduits"],
				"blocs_non_places": len(stats["non_places"]), "duree_s": int(time.monotonic() - debut),
				"cout_estime": journal.cout_document("Manuel Article", manuel) - cout_avant,
			}, update_modified=False)
			detail = ", ".join("p.%s « %s »" % (n["page"], n["texte"][:40]) for n in stats["non_places"][:8])
			rapport.append("%s : %d blocs posés, %d réduits, %d non placés%s, %d laissés en anglais, %d pivotés ignorés" % (
				langue["libelle"], stats["poses"], stats["reduits"], len(stats["non_places"]),
				(" (%s)" % detail) if detail else "", len(laisses), stats["pivotes"]))
			reussies += 1
		except Exception as e:
			frappe.log_error(title="Aquaworld IA : traduction %s (%s)" % (manuel, code), message=frappe.get_traceback())
			frappe.db.set_value("Manuel Article Traduction", nom, {"statut": "Échec", "erreur": str(e)[:500]}, update_modified=False)
			rapport.append("%s : ÉCHEC — %s" % (langue["libelle"], str(e)[:200]))
		frappe.db.commit()

	statut = "Terminé" if reussies == len(langues) else ("Partiel" if reussies else "Échec")
	frappe.db.set_value("Manuel Article", manuel, "statut", statut, update_modified=False)
	_journal(doc, rapport)
	frappe.db.commit()
	etat.terminer(GENRE, manuel, "termine" if reussies else "echec")
	etat.progresser(GENRE, manuel, "terminé", 100, EVENEMENT, utilisateur, fin=1)
