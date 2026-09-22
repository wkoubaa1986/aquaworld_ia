"""Journal IA : chaque appel OpenAI y laisse une ligne (jetons, images, coût estimé, durée).

C'est la seule comptabilité des dépenses IA de l'app : le plafond mensuel des réglages se
vérifie ici, et les fiches affichent leur coût cumulé. Règle de revue : AUCUN appel OpenAI hors
de `ia/chat.py` et `ia/images.py`, qui passent tous les deux par `enregistrer`.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from aquaworld_ia.ia import couts
from aquaworld_ia.ia.client import PlafondAtteint, reglages


def _reference(doc):
	"""`doc` : un Document, un tuple (doctype, name) ou None -> (doctype, name)."""
	if doc is None:
		return None, None
	if isinstance(doc, (tuple, list)) and len(doc) == 2:
		return doc[0], doc[1]
	return getattr(doc, "doctype", None), getattr(doc, "name", None)


def _jetons(usage) -> tuple[int, int]:
	if not usage:
		return 0, 0
	lire = (lambda *n: next((int(getattr(usage, x)) for x in n if getattr(usage, x, None) is not None), 0))
	return lire("prompt_tokens", "input_tokens"), lire("completion_tokens", "output_tokens")


def enregistrer(*, fonctionnalite: str, appel: str, modele: str, doc=None, usage=None,
                images: int = 0, taille: str | None = None, qualite: str | None = None,
                duree_ms: int = 0, erreur: str | None = None) -> str | None:
	"""Insère une ligne de Journal IA. Ne lève jamais : un journal qui casse l'appel qu'il
	trace serait pire que pas de journal (l'erreur part dans Error Log)."""
	entree, sortie = _jetons(usage)
	tarifs = couts.tarifs_depuis_reglages(reglages())
	doctype, name = _reference(doc)
	try:
		ligne = frappe.get_doc({
			"doctype": "Journal IA",
			"horodatage": now_datetime(),
			"utilisateur": frappe.session.user,
			"fonctionnalite": fonctionnalite,
			"document_type": doctype,
			"document_name": name,
			"appel": appel,
			"modele": modele,
			"jetons_entree": entree,
			"jetons_sortie": sortie,
			"images": images or 0,
			"taille_image": taille,
			"qualite": qualite,
			"cout_estime": couts.estimer_cout(entree, sortie, images, qualite, tarifs),
			"duree_ms": int(duree_ms or 0),
			"statut": "Erreur" if erreur else "OK",
			"erreur": (erreur or "")[:1000] or None,
		}).insert(ignore_permissions=True)
		return ligne.name
	except Exception:
		frappe.log_error(title="Journal IA : écriture impossible", message=frappe.get_traceback())
		return None


def cout_du_mois(mois: str | None = None) -> float:
	"""Somme des coûts estimés du mois (AAAA-MM, mois courant par défaut)."""
	mois = mois or now_datetime().strftime("%Y-%m")
	lignes = frappe.db.sql(
		"""SELECT COALESCE(SUM(cout_estime), 0) FROM `tabJournal IA`
		   WHERE DATE_FORMAT(horodatage, '%%Y-%%m') = %s""", (mois,))
	return flt(lignes[0][0] if lignes else 0, 4)


def cout_document(doctype: str, name: str) -> float:
	lignes = frappe.db.sql(
		"""SELECT COALESCE(SUM(cout_estime), 0) FROM `tabJournal IA`
		   WHERE document_type = %s AND document_name = %s""", (doctype, name))
	return flt(lignes[0][0] if lignes else 0, 4)


def verifier_plafond(cout_a_venir: float = 0.0) -> None:
	"""Lève PlafondAtteint si le mois dépasserait le plafond des réglages ; envoie une alerte
	(une fois par mois) au franchissement du seuil. Un plafond à 0 = pas de limite."""
	r = reglages()
	plafond = flt(getattr(r, "plafond_mensuel_usd", 0))
	if plafond <= 0:
		return
	actuel = cout_du_mois()
	if actuel + flt(cout_a_venir) > plafond:
		frappe.throw(
			_("Plafond IA mensuel atteint : {0} $ dépensés sur {1} $ autorisés (Aquaworld IA Réglages).")
			.format(round(actuel, 2), round(plafond, 2)),
			PlafondAtteint,
		)
	seuil = plafond * flt(getattr(r, "alerte_pourcentage", 80) or 80) / 100.0
	if actuel + flt(cout_a_venir) >= seuil:
		_alerter_une_fois(actuel, plafond, getattr(r, "email_alerte", None))


def _alerter_une_fois(actuel: float, plafond: float, email: str | None) -> None:
	cle = "aqia:alerte-plafond:%s" % now_datetime().strftime("%Y-%m")
	if not email or frappe.cache().get_value(cle, expires=True):
		return
	frappe.cache().set_value(cle, 1, expires_in_sec=40 * 24 * 3600)
	try:
		frappe.sendmail(
			recipients=[email],
			subject=_("Aquaworld IA : {0} % du plafond mensuel atteint").format(int(100 * actuel / plafond)),
			message=_("Dépense IA estimée ce mois : {0} $ sur {1} $.").format(round(actuel, 2), round(plafond, 2)),
			delayed=True,
		)
	except Exception:
		frappe.log_error(title="Aquaworld IA : alerte plafond non envoyée", message=frappe.get_traceback())
