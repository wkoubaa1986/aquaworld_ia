// Manuel Article : ajouter les langues actives, lancer la traduction, suivre l'avancement,
// télécharger les PDF depuis la grille.
frappe.ui.form.on("Manuel Article", {
	refresh(frm) {
		frm._aqia_arreter_suivi && frm._aqia_arreter_suivi();
		if (frm.is_new()) return;
		const en_cours = frm.doc.statut === "En cours";

		frm.add_custom_button(__("Ajouter les langues actives"), () => {
			frappe.call({ method: "aquaworld_ia.manuels.job.ajouter_langues_actives", args: { manuel: frm.doc.name } })
				.then((r) => {
					const n = (r.message || []).length;
					frappe.show_alert({ message: n ? __("{0} langue(s) ajoutée(s)", [n]) : __("Toutes les langues actives sont déjà là."), indicator: n ? "green" : "blue" });
					frm.reload_doc();
				});
		}, __("Aquaworld IA"));

		frm.add_custom_button(__("Traduire"), () => aqia_manuel_dialogue_traduire(frm), __("Aquaworld IA"));

		frappe.call({ method: "aquaworld_ia.manuels.job.etat_manuel", args: { manuel: frm.doc.name } }).then((r) => {
			const e = r.message || {};
			if (e.cout_document) frm.dashboard.add_indicator(__("Coût IA : {0} $", [e.cout_document.toFixed(3)]), "blue");
			if (e.bloque || en_cours) aqia_manuel_suivre(frm);
		});

		frm.fields_dict.traductions.grid.wrapper.on("click", ".grid-row", () => {});
		frm.dashboard.set_headline(en_cours
			? __("Traduction en cours — vous pouvez quitter la fiche, elle se met à jour toute seule.")
			: __("Attachez le PDF anglais, ajoutez les langues, puis « Traduire »."));
	},
});

function aqia_manuel_dialogue_traduire(frm) {
	const lignes = (frm.doc.traductions || []);
	if (!lignes.length) {
		frappe.msgprint(__("Ajoutez d'abord des langues (bouton « Ajouter les langues actives »)."));
		return;
	}
	const d = new frappe.ui.Dialog({
		title: __("Traduire le manuel"),
		fields: [
			{ fieldtype: "HTML", fieldname: "info", options: `<p class="text-muted">${__("Chaque langue coûte quelques centimes et prend une à trois minutes pour 40 pages. Les langues déjà terminées sont refaites seulement si vous les cochez.")}</p>` },
			...lignes.map((l) => ({
				fieldtype: "Check", fieldname: "l_" + l.langue,
				label: `${l.langue} — ${l.statut}${l.fichier ? " ✓" : ""}`,
				default: l.statut !== "Terminé" ? 1 : 0,
			})),
		],
		primary_action_label: __("Lancer"),
		primary_action(v) {
			const langues = lignes.map((l) => l.langue).filter((c) => v["l_" + c]);
			if (!langues.length) { frappe.msgprint(__("Cochez au moins une langue.")); return; }
			d.hide();
			frappe.call({ method: "aquaworld_ia.manuels.job.lancer", args: { manuel: frm.doc.name, langues }, freeze: true })
				.then(() => { frappe.show_alert({ message: __("Traduction lancée"), indicator: "green" }); frm.reload_doc(); });
		},
	});
	d.show();
}

function aqia_manuel_suivre(frm) {
	const nom = frm.doc.name;
	const afficher = (e) => {
		if (!e || e.nom && e.nom !== nom) return;
		frm.dashboard.show_progress(__("Traduction"), e.avancement || 0, e.etape || "");
		if (e.fin || e.avancement >= 100) { arreter(); frm.reload_doc(); frappe.show_alert({ message: __("Traduction terminée"), indicator: "green" }); }
	};
	const sur_evenement = (e) => afficher(e);
	frappe.realtime.on("aqia_manuel", sur_evenement);
	const minuteur = setInterval(() => {
		frappe.call({ method: "aquaworld_ia.manuels.job.etat_manuel", args: { manuel: nom } }).then((r) => {
			const e = r.message || {};
			if (e.statut && e.statut !== "en cours") { arreter(); frm.reload_doc(); }
			else afficher(e);
		});
	}, 4000);
	const arreter = () => { frappe.realtime.off("aqia_manuel", sur_evenement); clearInterval(minuteur); frm.dashboard.hide_progress(); };
	frm._aqia_arreter_suivi = arreter;
}
