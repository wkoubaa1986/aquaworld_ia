"""Les fichiers des designs et manuels importés (25/09 et 06/10/2026) pointaient une copie suffixée de
l'empreinte : le document affichait « Forbidden ». Voir transfert.reparer_fichiers_doubles."""
from aquaworld_ia.transfert import reparer_fichiers_doubles


def execute():
	print("Aquaworld IA, fichiers en double réparés :", reparer_fichiers_doubles())
