"""Rôle « Aquaworld IA » pour Salma, Jamel et Sadok (demande 07/11/2026) : l'accès complet à l'app, réglages IA
compris. Sans effet pour un compte absent, désactivé ou déjà pourvu ; le rôle est créé s'il manque (la fixture
Role n'est synchronisée qu'après les patches sur une installation neuve)."""
import frappe

ROLE = "Aquaworld IA"
COMPTES = (
	"salmaaquaworldservicing@gmail.com",   # Salma Ben Saïd
	"jimmyks007@gmail.com",                # Jamel Aloui
	"sadokaquaworld@gmail.com",            # Sadok Bouziri
)


def execute():
	if not frappe.db.exists("Role", ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 1}).insert(ignore_permissions=True)
	resultat = []
	for email in COMPTES:
		if not frappe.db.exists("User", email):
			resultat.append(f"{email} : compte absent")
			continue
		if not frappe.db.get_value("User", email, "enabled"):
			resultat.append(f"{email} : compte désactivé, rien fait")
			continue
		if frappe.db.exists("Has Role", {"parent": email, "parenttype": "User", "role": ROLE}):
			resultat.append(f"{email} : avait déjà le rôle")
			continue
		frappe.get_doc("User", email).add_roles(ROLE)
		resultat.append(f"{email} : rôle ajouté")
	frappe.db.commit()
	print("Aquaworld IA, rôle « " + ROLE + " » :", "; ".join(resultat))
