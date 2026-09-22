// Fiche Article : deux boutons vers les fiches IA liées (existante, sinon nouvelle).
frappe.ui.form.on("Item", {
	refresh(frm) {
		if (frm.is_new()) return;
		const ouvrir = (doctype, champ_article) => {
			frappe.db.get_list(doctype, { filters: { [champ_article]: frm.doc.name }, fields: ["name"], limit: 1, order_by: "modified desc" })
				.then((r) => {
					if (r && r.length) frappe.set_route("Form", doctype, r[0].name);
					else frappe.new_doc(doctype, { article: frm.doc.name });
				});
		};
		frm.add_custom_button(__("Manuel multilingue"), () => ouvrir("Manuel Article", "article"), __("Aquaworld IA"));
		frm.add_custom_button(__("Design d'emballage"), () => ouvrir("Design Emballage", "article"), __("Aquaworld IA"));
	},
});
