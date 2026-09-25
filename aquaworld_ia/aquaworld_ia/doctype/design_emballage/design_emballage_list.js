// Liste des designs : « Dupliquer » dans le menu Actions des lignes cochées (demande utilisateur 24/09/2026),
// comme le bouton ⧉ Dupliquer de la fiche et du studio (`studio.dupliquer`).
frappe.listview_settings["Design Emballage"] = {
	onload(listview) {
		if (!frappe.model.can_create("Design Emballage")) return;
		listview.page.add_actions_menu_item(__("Dupliquer"), () => aqia_liste_dupliquer(listview), false);
	},
};

function aqia_liste_dupliquer(listview) {
	const coches = listview.get_checked_items();
	if (!coches.length) return;
	if (coches.length === 1) {
		// Un seul design : on peut changer d'article, puis le studio s'ouvre sur la copie.
		const d = coches[0];
		const dlg = new frappe.ui.Dialog({ title: __("Dupliquer {0}", [d.name]),
			fields: [
				{ fieldtype: "Link", options: "Item", fieldname: "article", label: __("Article"), default: d.article, reqd: 1,
				  description: __("Un autre article : son nom, sa photo et son code-barres remplacent ceux de l'original.") },
				{ fieldtype: "HTML", options: `<p class="text-muted small">${__("La copie reprend la forme, les dimensions, les textes et leur mise en forme, les langues, les pictogrammes, le fond, la mise en page dessinée et les variantes IA déjà générées (rien n'est refacturé). Le plan à plat et les aperçus sont à recomposer.")}</p>` },
			],
			primary_action_label: __("Dupliquer"),
			primary_action: async (v) => {
				let r;
				try {
					r = await frappe.call({ method: "aquaworld_ia.emballage.studio.dupliquer", args: { design: d.name, article: v.article }, freeze: true, freeze_message: __("Copie du design…") });
				} catch (e) { return; }
				dlg.hide();
				frappe.show_alert({ message: __("Copie créée : {0}. Recomposez le plan à plat.", [r.message.name]), indicator: "green" });
				frappe.set_route("studio-emballage", r.message.name);
			} });
		dlg.show();
		return;
	}
	// Plusieurs designs : chacun est copié pour son propre article, on reste sur la liste.
	const noms = coches.map((d) => d.name);
	frappe.confirm(__("Dupliquer {0} designs ? Chaque copie garde l'article de son original ; le plan à plat de chacune est à recomposer.", [noms.length]), async () => {
		const faites = [], ratees = [];
		for (const nom of noms) {
			try {
				const r = await frappe.call({ method: "aquaworld_ia.emballage.studio.dupliquer", args: { design: nom }, freeze: true, freeze_message: __("Copie de {0}…", [nom]) });
				faites.push([nom, r.message.name]);
			} catch (e) { ratees.push(nom); }
		}
		listview.clear_checked_items();
		listview.refresh();
		const lien = (n) => `<a href="/app/studio-emballage/${encodeURIComponent(n)}">${frappe.utils.escape_html(n)}</a>`;
		let html = faites.length ? `<p>${__("Copies créées :")}</p><ul>${faites.map(([o, c]) => `<li>${frappe.utils.escape_html(o)} → ${lien(c)}</li>`).join("")}</ul>` : "";
		if (ratees.length) html += `<p class="text-danger">${__("Échec pour : {0}", [ratees.map(frappe.utils.escape_html).join(", ")])}</p>`;
		frappe.msgprint({ title: __("Duplication"), message: html, indicator: ratees.length ? "orange" : "green" });
	});
}
