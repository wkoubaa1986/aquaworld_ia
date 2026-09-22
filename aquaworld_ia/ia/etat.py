"""État d'un job long (traduction d'un manuel, variantes d'un emballage), en cache Redis.

Copie du modèle de bank_retenue_sync/facturation/dossier.py : le résultat DURABLE (fichiers,
statuts) vit dans les DocTypes ; le cache ne porte que l'avancement et le verrou anti-double
lancement, avec un garde-fou « job mort » — un worker qui tombe ne doit pas griser un bouton
pendant six heures sans explication.
"""

from __future__ import annotations

import frappe
from frappe.utils import get_datetime, now_datetime

DUREE_ETAT = 6 * 3600
JOB_MORT_APRES = 2 * 3600


def _cle(genre: str, nom: str) -> str:
	return "aqia:%s:%s" % (genre, nom)


def lire_etat(genre: str, nom: str) -> dict:
	# `expires=True` : posé avec une durée de vie, donc absent du cache local de la requête.
	return frappe.cache().get_value(_cle(genre, nom), expires=True) or {}


def poser_etat(genre: str, nom: str, **valeurs) -> dict:
	etat = dict(lire_etat(genre, nom), **valeurs)
	frappe.cache().set_value(_cle(genre, nom), etat, expires_in_sec=DUREE_ETAT)
	return etat


def effacer_etat(genre: str, nom: str) -> None:
	frappe.cache().delete_value(_cle(genre, nom))


def bloque(etat: dict) -> bool:
	"""Vrai si un job vivant est en cours. Passé JOB_MORT_APRES, on considère le job perdu."""
	if etat.get("statut") != "en cours":
		return False
	debut = etat.get("debut")
	if not debut:
		return True
	try:
		age = (now_datetime() - get_datetime(debut)).total_seconds()
	except Exception:
		return True
	return age < JOB_MORT_APRES


def demarrer(genre: str, nom: str, **valeurs) -> dict:
	return poser_etat(genre, nom, statut="en cours", etape="en file d'attente", avancement=0,
	                  debut=str(now_datetime()), **valeurs)


def progresser(genre: str, nom: str, etape: str, avancement: int, evenement: str, utilisateur: str | None, **extra) -> None:
	"""Met à jour le cache ET prévient l'écran (realtime) ; le JS a un polling de repli."""
	poser_etat(genre, nom, etape=etape, avancement=int(avancement))
	charge = dict({"nom": nom, "etape": etape, "avancement": int(avancement)}, **extra)
	try:
		frappe.publish_realtime(evenement, charge, user=utilisateur) if utilisateur else \
			frappe.publish_realtime(evenement, charge)
	except Exception:
		pass


def terminer(genre: str, nom: str, statut: str = "termine", **valeurs) -> dict:
	return poser_etat(genre, nom, statut=statut, avancement=100, fin=str(now_datetime()), **valeurs)
