app_name = "aquaworld_ia"
app_title = "Aquaworld IA"
app_publisher = "Wassim Koubaa"
app_description = "Manuels multilingues et design d'emballage par IA (OpenAI)"
app_email = "koubaawassim@gmail.com"
app_license = "mit"

# L'app ne dépend d'aucune autre app custom : elle relit elle-même la clé OpenAI
# (Aquaworld IA Reglages → AI Settings → site_config). Voir aquaworld_ia/ia/client.py.
required_apps = ["erpnext"]

# Langues prédéfinies et pictogrammes sont SEMÉS (jamais des fixtures : un fixture de DocType
# fait delete+insert et exige developer_mode en prod). Idempotent : ajoute ce qui manque,
# n'écrase rien que l'utilisateur aurait modifié.
after_install = "aquaworld_ia.install.after_migrate"
after_migrate = "aquaworld_ia.install.after_migrate"

# Boutons « Manuel multilingue » / « Design d'emballage » sur la fiche Article. Deux autres
# apps posent déjà un doctype_js sur Item (customization_app, woocommerce_fusion) : Frappe
# concatène, ça ne gêne pas.
doctype_js = {"Item": "public/js/item.js"}

app_include_css = "/assets/aquaworld_ia/css/aquaworld_ia.css"

fixtures = []
