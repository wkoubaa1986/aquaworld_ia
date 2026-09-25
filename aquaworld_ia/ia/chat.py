"""L'unique point d'appel des complétions texte (JSON) — journalisé."""

from __future__ import annotations

import json
import time

import frappe
from frappe import _

from aquaworld_ia.ia import journal
from aquaworld_ia.ia.client import client_et_modele


def _completer(client, modele: str, temperature, messages: list):
	"""L'appel brut, avec le repli sans température des modèles raisonneurs."""
	params = {"model": modele, "messages": messages, "response_format": {"type": "json_object"}}
	try:
		return client.chat.completions.create(temperature=temperature, **params)
	except Exception as e:
		if "temperature" in str(e):
			return client.chat.completions.create(**params)
		raise


def chat_json_differe(contexte: tuple, system: str, user: str) -> dict:
	"""Un appel chat SANS toucher à Frappe (utilisable dans un thread) : `contexte` =
	(client, modèle, température) préparé par `client_et_modele` dans le thread principal.
	-> {"sortie": dict|None, "journal": {...}} ; le journal est à écrire ensuite par
	`journal.enregistrer(**journal)` depuis le thread principal (la connexion Frappe n'est pas
	partageable entre threads — parallélisation des lots de traduction, 25/09/2026)."""
	client, modele, temperature = contexte
	debut = time.monotonic()
	try:
		reponse = _completer(client, modele, temperature, [{"role": "system", "content": system}, {"role": "user", "content": user}])
	except Exception as e:
		return {"sortie": None, "journal": {"appel": "chat", "modele": modele, "duree_ms": (time.monotonic() - debut) * 1000, "erreur": str(e)}}
	entree = {"appel": "chat", "modele": modele, "usage": getattr(reponse, "usage", None), "duree_ms": (time.monotonic() - debut) * 1000}
	try:
		return {"sortie": json.loads(reponse.choices[0].message.content), "journal": entree}
	except Exception:
		return {"sortie": None, "journal": dict(entree, erreur="réponse illisible")}


def chat_json(system: str, user: str, *, fonctionnalite: str, doc=None, modele: str | None = None) -> dict:
	"""Un appel chat.completions en mode JSON -> dict. Lève une erreur claire si la réponse
	n'est pas du JSON. Les modèles « raisonneurs » refusent une température : on la retire et
	on réessaie (même repli que liste_commande_import._chat_json)."""
	client, modele_defaut, temperature = client_et_modele("texte")
	modele = modele or modele_defaut
	params = {
		"model": modele,
		"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
		"response_format": {"type": "json_object"},
	}
	debut = time.monotonic()
	try:
		try:
			reponse = client.chat.completions.create(temperature=temperature, **params)
		except Exception as e:
			if "temperature" in str(e):
				reponse = client.chat.completions.create(**params)
			else:
				raise
	except Exception as e:
		journal.enregistrer(fonctionnalite=fonctionnalite, appel="chat", modele=modele, doc=doc,
		                    duree_ms=(time.monotonic() - debut) * 1000, erreur=str(e))
		raise
	journal.enregistrer(fonctionnalite=fonctionnalite, appel="chat", modele=modele, doc=doc,
	                    usage=getattr(reponse, "usage", None), duree_ms=(time.monotonic() - debut) * 1000)
	contenu = reponse.choices[0].message.content
	try:
		return json.loads(contenu)
	except Exception:
		frappe.throw(_("Réponse IA illisible : {0}").format((contenu or "")[:300]))


def chat_json_image(system: str, user: str, image_png: bytes, *, fonctionnalite: str, doc=None,
                    modele: str | None = None, detail: str = "high") -> dict:
	"""Comme `chat_json`, avec UNE image jointe au message utilisateur (lecture d'une page de
	manuel par le modèle « vision »). Même modèle texte, même journal (appel « chat » : le Select du
	Journal IA ne connaît que chat / responses / images.* — « chat+image » y était refusé et les
	lectures vision n'étaient pas comptées, vu le 25/09/2026)."""
	import base64

	client, modele_defaut, temperature = client_et_modele("texte")
	modele = modele or modele_defaut
	contenu = [
		{"type": "text", "text": user},
		{"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(image_png).decode(), "detail": detail}},
	]
	params = {
		"model": modele,
		"messages": [{"role": "system", "content": system}, {"role": "user", "content": contenu}],
		"response_format": {"type": "json_object"},
	}
	debut = time.monotonic()
	try:
		try:
			reponse = client.chat.completions.create(temperature=temperature, **params)
		except Exception as e:
			if "temperature" in str(e):
				reponse = client.chat.completions.create(**params)
			else:
				raise
	except Exception as e:
		journal.enregistrer(fonctionnalite=fonctionnalite, appel="chat", modele=modele, doc=doc,
		                    duree_ms=(time.monotonic() - debut) * 1000, erreur=str(e))
		raise
	journal.enregistrer(fonctionnalite=fonctionnalite, appel="chat", modele=modele, doc=doc,
	                    usage=getattr(reponse, "usage", None), duree_ms=(time.monotonic() - debut) * 1000)
	texte = reponse.choices[0].message.content
	try:
		return json.loads(texte)
	except Exception:
		frappe.throw(_("Réponse IA illisible : {0}").format((texte or "")[:300]))
