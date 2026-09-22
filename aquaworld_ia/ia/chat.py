"""L'unique point d'appel des complétions texte (JSON) — journalisé."""

from __future__ import annotations

import json
import time

import frappe
from frappe import _

from aquaworld_ia.ia import journal
from aquaworld_ia.ia.client import client_et_modele


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
