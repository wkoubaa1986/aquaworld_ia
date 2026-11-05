frappe.ui.form.on('Document Produit', { refresh(frm) { if (!frm.is_new()) frm.add_custom_button("Ouvrir le studio", () => frappe.set_route("documents-produit", frm.doc.dossier)); } });
