// Fiche Article : outils IA et liens permanents vers les documents produit.
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
		if (frappe.model.can_read("Dossier Produit")) {
			const ouvrir_dossier = async () => {
				const r = await frappe.call({method: "aquaworld_ia.documents_produit.service.creer", args: {article: frm.doc.name}});
				frappe.set_route("documents-produit", r.message.name);
			};
			if (frappe.model.can_create("Dossier Produit")) frm.add_custom_button(__("Documents produit IA"), ouvrir_dossier, __("Aquaworld IA"));
			frappe.call({method: "aquaworld_ia.documents_produit.service.lister", args: {article: frm.doc.name}}).then(r => {
				const zone = frm.fields_dict.custom_documents_produit?.$wrapper;
				if (!zone) return;
				const esc = frappe.utils.escape_html;
				zone.empty();
				for (const dossier of r.message || []) {
					zone.append(`<p><a href="/app/documents-produit/${encodeURIComponent(dossier.name)}"><b>Ouvrir les fiches techniques et manuels</b></a></p>`);
					const groupes = new Map();
					for (const d of dossier.documents) {
						const key = d.type_document + ':' + d.langue;
						if (!groupes.has(key)) groupes.set(key, {dernier: d, pdf: null});
						const groupe = groupes.get(key);
						if (!groupe.pdf && d.statut === 'Validé' && d.pdf) groupe.pdf = d;
					}
					for (const {dernier: d, pdf} of groupes.values()) {
						const url = pdf && /^\/(private\/)?files\//.test(pdf.pdf) ? pdf.pdf : null;
						zone.append(`<p>${esc(d.type_document)} · ${esc(d.libelle_langue)} · v${d.numero} · ${esc(d.statut)} ${url ? `— <a href="${esc(url)}" target="_blank" rel="noopener">PDF validé</a> (v${pdf.numero})` : ''}</p>`);
					}
				}
				if (!(r.message || []).length) {
					zone.append('<p class="text-muted">Aucune fiche technique ou manuel créé pour cet article.</p>');
					if (frappe.model.can_create("Dossier Produit")) $('<button type="button" class="btn btn-default btn-sm">Créer la fiche technique ou le manuel</button>').appendTo(zone).on('click', ouvrir_dossier);
				}
			});
		}
	},
});
