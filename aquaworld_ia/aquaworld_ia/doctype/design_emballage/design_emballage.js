// Design Emballage : le flux en trois boutons (textes → variantes → plan à plat), la galerie
// des variantes, l'aperçu du plan recalculé à chaque dimension, le suivi des jobs.
frappe.ui.form.on("Design Emballage", {
	setup(frm) {
		frm.set_query("langues", () => ({ filters: { actif: 1 } }));
	},
	onload(frm) {
		if (frm.is_new()) {
			frappe.db.get_single_value("Aquaworld IA Reglages", "fond_perdu_mm").then((v) => { if (v && !frm.doc.fond_perdu_mm) frm.set_value("fond_perdu_mm", v); });
			frappe.db.get_single_value("Aquaworld IA Reglages", "zone_securite_mm").then((v) => { if (v && !frm.doc.zone_securite_mm) frm.set_value("zone_securite_mm", v); });
			frappe.db.get_single_value("Aquaworld IA Reglages", "patte_collage_mm").then((v) => { if (v && !frm.doc.patte_collage_mm) frm.set_value("patte_collage_mm", v); });
		}
	},
	article(frm) {
		if (!frm.doc.article) return;
		frappe.db.get_doc("Item", frm.doc.article).then((item) => {
			if (!frm.doc.photo_produit && item.image) frm.set_value("photo_produit", item.image);
			const ean = (item.barcodes || []).find((b) => /EAN/i.test(b.barcode_type || "") || /^\d{13}$/.test(b.barcode || ""));
			if (!frm.doc.code_barres && ean) frm.set_value("code_barres", ean.barcode);
			if (item.brand && !frm.doc.logo) {
				frappe.db.get_value("Brand", item.brand, "image").then((r) => { if (r.message && r.message.image) frm.set_value("logo", r.message.image); });
			}
		});
	},
	marque(frm) {
		if (frm.doc.marque && !frm.doc.logo) {
			frappe.db.get_value("Brand", frm.doc.marque, "image").then((r) => { if (r.message && r.message.image) frm.set_value("logo", r.message.image); });
		}
	},
	type_boite: aqia_emb_apercu, longueur_mm: aqia_emb_apercu, hauteur_mm: aqia_emb_apercu, profondeur_mm: aqia_emb_apercu,
	fond_perdu_mm: aqia_emb_apercu, zone_securite_mm: aqia_emb_apercu, patte_collage_mm: aqia_emb_apercu,

	refresh(frm) {
		frm._aqia_arreter_suivi && frm._aqia_arreter_suivi();
		aqia_emb_apercu(frm);
		aqia_emb_textes(frm);
		aqia_emb_galerie(frm);
		if (frm.is_new()) return;
		const s = frm.doc.statut;
		const textes_ok = !!frm.doc.textes_ia;
		const variantes_pretes = (frm.doc.variantes || []).some((v) => v.statut === "Prête");
		const grp = __("Aquaworld IA");

		frm.add_custom_button(__("1. Préparer textes et styles"), () => {
			frappe.call({ method: "aquaworld_ia.emballage.textes.preparer", args: { design: frm.doc.name }, freeze: true,
				freeze_message: __("L'IA rédige les textes et propose des styles…") })
				.then(() => { frappe.show_alert({ message: __("Textes et styles prêts : relisez-les, puis générez les variantes."), indicator: "green" }); frm.reload_doc(); });
		}, grp);

		const b2 = frm.add_custom_button(__("2. Générer les variantes"), () => aqia_emb_dialogue_variantes(frm), grp);
		if (!textes_ok) b2.addClass("disabled").attr("title", __("Préparez d'abord les textes (bouton 1)."));

		const b3 = frm.add_custom_button(__("3. Composer le plan à plat"), () => {
			if (!frm.doc.variante_choisie) { frappe.msgprint(__("Choisissez une variante dans la galerie.")); return; }
			frappe.call({ method: "aquaworld_ia.emballage.composition.composer_et_attacher",
				args: { design: frm.doc.name, variante: frm.doc.variante_choisie }, freeze: true, freeze_message: __("Composition du plan à l'échelle…") })
				.then((r) => {
					const m = r.message || {};
					frappe.msgprint({ title: __("Plan à plat prêt"), indicator: "green",
						message: __("Feuille {0} × {1} mm. <a href='{2}' target='_blank'>Ouvrir le PDF</a>", [m.feuille.w, m.feuille.h, m.plan_a_plat]) });
					frm.reload_doc();
				});
		}, grp);
		if (!variantes_pretes) b3.addClass("disabled");

		if (textes_ok) frm.add_custom_button(__("Modifier les textes"), () => aqia_emb_dialogue_textes(frm), grp);
		if (frm.doc.variante_choisie && variantes_pretes) {
			frm.add_custom_button(__("Faces secondaires par IA (5 images)"), () => {
				frappe.confirm(__("Générer les 5 autres faces dans le style de la variante choisie ? (5 images facturées)"), () => {
					frappe.call({ method: "aquaworld_ia.emballage.job.lancer_faces", args: { design: frm.doc.name } })
						.then(() => { aqia_emb_suivre(frm); });
				});
			}, grp);
		}
		if (frm.doc.plan_a_plat) {
			frm.add_custom_button(__("Aperçu 3D (1 image)"), () => {
				frappe.call({ method: "aquaworld_ia.emballage.job.lancer_mockup", args: { design: frm.doc.name } }).then(() => aqia_emb_suivre(frm));
			}, grp);
		}

		frappe.call({ method: "aquaworld_ia.emballage.job.etat_design", args: { design: frm.doc.name } }).then((r) => {
			const e = r.message || {};
			if (e.cout_document) frm.dashboard.add_indicator(__("Coût IA : {0} $", [e.cout_document.toFixed(3)]), "blue");
			if (e.bloque || s === "Variantes en cours") aqia_emb_suivre(frm);
		});
		frm.dashboard.set_headline({
			"Brouillon": __("Renseignez dimensions, contenus et style, puis « 1. Préparer textes et styles »."),
			"Textes prêts": __("Relisez les textes (« Modifier les textes »), puis « 2. Générer les variantes »."),
			"Variantes en cours": __("Génération des variantes en cours…"),
			"Variantes prêtes": __("Choisissez une variante dans la galerie, puis « 3. Composer le plan à plat »."),
			"Plan prêt": __("Plan à plat prêt. Options : faces secondaires par IA, aperçu 3D."),
			"Échec": __("Dernière étape en échec : voir le journal et les erreurs des variantes."),
		}[s] || "");
	},
});

function aqia_emb_apercu(frm) {
	const d = frm.doc;
	const w = frm.fields_dict.format_html && frm.fields_dict.format_html.$wrapper;
	if (!w) return;
	if (!(d.longueur_mm > 0 && d.hauteur_mm > 0 && d.profondeur_mm > 0)) { w.html(`<p class="text-muted">${__("Saisissez les trois dimensions pour voir le plan.")}</p>`); return; }
	frappe.call({ method: "aquaworld_ia.emballage.job.apercu", args: {
		type_boite: d.type_boite, longueur_mm: d.longueur_mm, hauteur_mm: d.hauteur_mm, profondeur_mm: d.profondeur_mm,
		patte_collage_mm: d.patte_collage_mm, fond_perdu_mm: d.fond_perdu_mm, zone_securite_mm: d.zone_securite_mm } })
		.then((r) => {
			const m = r.message || {};
			if (m.erreur) { w.html(`<p class="text-danger">${frappe.utils.escape_html(m.erreur)}</p>`); return; }
			const pb = (m.problemes || []).length ? `<p class="text-danger">⛔ ${m.problemes.map(frappe.utils.escape_html).join(" · ")}</p>` : "";
			w.html(`<p class="text-muted">${__("Feuille : <b>{0} × {1} mm</b> (fond perdu inclus). Bleu = faces imprimables, rouge = coupe, pointillé = pli.", [m.feuille.w, m.feuille.h])}</p>${pb}${m.svg}`);
		});
}

function aqia_emb_textes(frm) {
	const w = frm.fields_dict.textes_ia_html && frm.fields_dict.textes_ia_html.$wrapper;
	if (!w || frm.is_new()) return;
	frappe.call({ method: "aquaworld_ia.emballage.textes.rendu_textes", args: { design: frm.doc.name } }).then((r) => w.html(r.message || ""));
}

function aqia_emb_dialogue_textes(frm) {
	let textes = {};
	try { textes = JSON.parse(frm.doc.textes_ia || "{}"); } catch (e) { textes = {}; }
	const codes = Object.keys(textes);
	const fields = [];
	codes.forEach((c) => {
		const t = textes[c];
		fields.push({ fieldtype: "Section Break", label: c.toUpperCase() });
		fields.push({ fieldtype: "Data", fieldname: `acc_${c}`, label: __("Accroche"), default: t.accroche });
		fields.push({ fieldtype: "Small Text", fieldname: `car_${c}`, label: __("Caractéristiques (une par ligne)"), default: (t.caracteristiques || []).join("\n") });
		fields.push({ fieldtype: "Small Text", fieldname: `ave_${c}`, label: __("Avertissements (un par ligne)"), default: (t.avertissements || []).join("\n") });
		fields.push({ fieldtype: "Small Text", fieldname: `con_${c}`, label: __("Contact"), default: t.contact });
	});
	const d = new frappe.ui.Dialog({ title: __("Textes imprimés"), size: "large", fields, primary_action_label: __("Enregistrer"),
		primary_action(v) {
			const sortie = {};
			codes.forEach((c) => { sortie[c] = { accroche: v[`acc_${c}`] || "", caracteristiques: (v[`car_${c}`] || "").split("\n").filter(Boolean),
				avertissements: (v[`ave_${c}`] || "").split("\n").filter(Boolean), contact: v[`con_${c}`] || "" }; });
			frappe.call({ method: "aquaworld_ia.emballage.textes.enregistrer_textes", args: { design: frm.doc.name, textes: sortie } })
				.then(() => { d.hide(); frm.reload_doc(); });
		} });
	d.show();
}

function aqia_emb_dialogue_variantes(frm) {
	const a_faire = (frm.doc.variantes || []).filter((v) => v.statut === "À générer" || v.statut === "Échec");
	if (!a_faire.length) { frappe.msgprint(__("Toutes les variantes sont générées. Utilisez « Régénérer » dans la galerie ou relancez l'étape 1 avec un autre nombre.")); return; }
	frappe.call({ method: "aquaworld_ia.emballage.job.estimation_variantes", args: { nombre: a_faire.length } }).then((r) => {
		const e = r.message || {};
		frappe.confirm(
			__("Générer {0} variante(s) (face avant, qualité {1}) — coût estimé <b>{2} $</b> ; dépensé ce mois : {3} $ {4}", [
				a_faire.length, e.qualite, (e.cout || 0).toFixed(2), (e.mois || 0).toFixed(2), e.plafond ? __("sur {0} $", [e.plafond]) : ""]),
			() => {
				frappe.call({ method: "aquaworld_ia.emballage.job.lancer_variantes", args: { design: frm.doc.name } })
					.then(() => { frappe.show_alert({ message: __("Génération lancée"), indicator: "green" }); frm.reload_doc(); });
			});
	});
}

function aqia_emb_galerie(frm) {
	const w = frm.fields_dict.galerie_html && frm.fields_dict.galerie_html.$wrapper;
	if (!w) return;
	const esc = frappe.utils.escape_html;
	const vs = frm.doc.variantes || [];
	if (!vs.length) { w.html(`<p class="text-muted">${__("Aucune variante : lancez l'étape 1.")}</p>`); return; }
	w.html(`<div class="aqia-galerie">${vs.map((v) => `
		<div class="aqia-carte ${v.numero === frm.doc.variante_choisie ? "choisie" : ""} statut-${esc((v.statut || "").replace(/\s/g, "_"))}">
			<div class="aqia-image">${v.image ? `<img src="${esc(v.image)}" alt="">` : `<div class="aqia-vide">${esc(v.statut || "")}</div>`}</div>
			<div class="aqia-legende"><b>${v.numero}. ${esc(v.titre || "")}</b><br><span class="text-muted small">${esc(v.description || "")}</span>
			${v.erreur ? `<br><span class="text-danger small">${esc(v.erreur)}</span>` : ""}</div>
			<div class="aqia-actions">
				${v.statut === "Prête" ? `<button class="btn btn-xs btn-primary" data-choisir="${v.numero}">${v.numero === frm.doc.variante_choisie ? "✓ " + __("Choisie") : __("Choisir")}</button>` : ""}
				${v.statut === "Prête" || v.statut === "Échec" ? `<button class="btn btn-xs btn-default" data-regenerer="${v.numero}">${__("Régénérer")}</button>` : ""}
			</div>
		</div>`).join("")}</div>`);
	w.find("[data-choisir]").on("click", (e) => {
		frappe.call({ method: "aquaworld_ia.emballage.job.choisir_variante", args: { design: frm.doc.name, numero: $(e.currentTarget).data("choisir") } }).then(() => frm.reload_doc());
	});
	w.find("[data-regenerer]").on("click", (e) => {
		const n = $(e.currentTarget).data("regenerer");
		frappe.confirm(__("Régénérer la variante {0} ? (1 image facturée)", [n]), () => {
			frappe.call({ method: "aquaworld_ia.emballage.job.regenerer_variante", args: { design: frm.doc.name, numero: n } }).then(() => frm.reload_doc());
		});
	});
}

function aqia_emb_suivre(frm) {
	const nom = frm.doc.name;
	const afficher = (e) => {
		if (!e || (e.nom && e.nom !== nom)) return;
		frm.dashboard.show_progress(__("Aquaworld IA"), e.avancement || 0, e.etape || "");
		if (e.fin || e.avancement >= 100) { arreter(); frm.reload_doc(); }
	};
	frappe.realtime.on("aqia_emballage", afficher);
	const minuteur = setInterval(() => {
		frappe.call({ method: "aquaworld_ia.emballage.job.etat_design", args: { design: nom } }).then((r) => {
			const e = r.message || {};
			if (e.statut && e.statut !== "en cours") { arreter(); frm.reload_doc(); } else afficher(e);
		});
	}, 4000);
	const arreter = () => { frappe.realtime.off("aqia_emballage", afficher); clearInterval(minuteur); frm.dashboard.hide_progress(); };
	frm._aqia_arreter_suivi = arreter;
}
