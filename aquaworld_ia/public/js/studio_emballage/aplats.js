// Impression en aplats : le décor d’une face ramené à quelques couleurs d’impression, en tracés SVG.
class StudioAplats {
	_encres(texte) {
		return String(texte === undefined ? (this.d.encres_impression || "") : texte).split(/[\s,;]+/).filter(Boolean)
			.map((c) => (c.startsWith("#") ? c : "#" + c).toLowerCase());
	}

	_pastilles_encres(couleurs) {
		const esc = this._esc;
		return couleurs.map((c) => `<span class="se-pastille petite" title="${esc(c)}" style="background:${esc(c)};cursor:default"></span>`).join("");
	}

	// Étape 4 : les couleurs d’impression du design et le contrôle du PDF.
	bloc_aplats() {
		const esc = this._esc, encres = this._encres();
		return `<div class="bloc" style="margin-top:10px;padding:8px 10px;background:#f8fafc;border:1px solid #e5e7eb;border-radius:8px">
			<h6 style="margin:0 0 4px">${__("Impression en aplats")}</h6>
			${encres.length
				? `<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">${this._pastilles_encres(encres)}<span class="small">${esc(encres.join(", "))}</span></div>`
				: `<p class="small text-muted" style="margin:0">${__("Pour un emballage imprimé en quelques couleurs (flexographie) : indiquez les couleurs de l’imprimeur. Sans couleur indiquée, l’impression est en photo.")}</p>`}
			<div class="se-btns" style="margin-top:6px">
				<button class="btn btn-xs btn-default" data-action="encres_aplats">${encres.length ? __("Changer les couleurs") : __("Indiquer les couleurs d’impression")}</button>
				${encres.length ? `<button class="btn btn-xs btn-default" data-action="controle_aplats">${__("Contrôler les couleurs du PDF")}</button>` : ""}
			</div>
			${encres.length ? `<div class="se-btns" style="margin-top:6px"><button class="btn btn-xs btn-primary" data-action="creer_aplats">${__("Créer le décor en aplats…")}</button></div>
				<p class="small text-muted" style="margin:6px 0 0">${__("1. Créer le décor en aplats d’une face. 2. Contrôler les couleurs du PDF. 3. Télécharger le PDF imprimeur.")}</p>` : ""}</div>`;
	}

	/** Faces dont le décor est une image, donc à passer en aplats ; à défaut, toutes les faces. */
	_faces_aplats() {
		const faces = (this.data.apercu || {}).faces || [], fonds = this._fonds();
		const imagees = faces.filter((f) => (fonds[f.code] || {}).image);
		return imagees.length ? imagees : faces;
	}

	/** Depuis l’étape 4 : ouvre l’atelier des aplats sans passer par l’étape 3 (13/11/2026 : « je fais quoi ? »). */
	creer_aplats() {
		const faces = this._faces_aplats();
		if (!faces.length) return frappe.msgprint(__("Renseignez d’abord le format de l’emballage (étape 1)."));
		if (faces.length === 1) return this.atelier_aplats(faces[0].code);
		frappe.prompt([{ fieldtype: "Select", fieldname: "face", label: __("Face à passer en aplats"), reqd: 1, default: faces[0].code,
			options: faces.map((f) => ({ value: f.code, label: f.libelle || f.code })) }],
		(v) => this.atelier_aplats(v.face), __("Décor en aplats"), __("Continuer"));
	}

	regler_encres() {
		const design = this.nom;
		frappe.prompt([{ fieldtype: "Data", fieldname: "couleurs", label: __("Couleurs d’impression (codes HEX)"), default: this.d.encres_impression || "",
			description: __("1 à 4 couleurs, séparées par des virgules, par exemple « #0264c3, #5badf0 ». Le blanc du support ne se compte pas. Laisser vide pour une impression photo.") }],
		async (v) => {
			try {
				await this.enregistrer({ encres_impression: (v.couleurs || "").trim() }, design);
				if (this.nom === design) this.rendre();
			} catch (e) { frappe.msgprint(this._msg(e)); }
		}, __("Couleurs d’impression"), __("Enregistrer"));
	}

	async controler_aplats() {
		const design = this.nom, esc = this._esc;
		let r;
		try {
			r = await frappe.call({ method: "aquaworld_ia.emballage.aplats.controler", args: { design }, freeze: true,
				freeze_message: __("Lecture des couleurs du PDF…") });
		} catch (e) { frappe.msgprint(this._msg(e)); return; }
		const m = r.message || {}, ecarts = m.ecarts || [];
		const pastille = (c) => `<span class="se-pastille petite" style="background:${esc(c)};cursor:default;vertical-align:middle"></span> <code>${esc(c)}</code>`;
		const lignes = ecarts.map((e) => `<tr><td>${pastille(e.couleur)}</td>
			<td>${[e.textes.length ? esc(e.textes.slice(0, 3).map((t) => "« " + t + " »").join(", ")) + (e.textes.length > 3 ? " …" : "") : "",
				e.traces ? __("{0} tracé(s) : logo, pictogramme ou décor", [e.traces]) : ""].filter(Boolean).join("<br>")}</td>
			<td>${pastille(e.proche)}</td></tr>`).join("");
		const dlg = new frappe.ui.Dialog({ title: __("Couleurs du PDF imprimeur"), size: "large", fields: [{ fieldtype: "HTML", fieldname: "bilan" }],
			primary_action_label: __("Aligner les couleurs"),
			primary_action: async () => {
				let r2;
				try {
					r2 = await frappe.call({ method: "aquaworld_ia.emballage.aplats.aligner_couleurs", args: { design }, freeze: true });
				} catch (e) { frappe.msgprint(this._msg(e)); return; }
				dlg.hide();
				const n = (r2.message.changements || []).length;
				if (this.nom === design) { this.data = Object.assign({}, this.data, r2.message); this.d = this.data.doc; this._lire_mep(); this.rendre(); }
				frappe.show_alert({ message: n ? __("{0} couleur(s) alignée(s). Actualisez le PDF, puis relancez le contrôle.", [n])
					: __("Rien à aligner automatiquement : ce qui reste vient du logo, d’un pictogramme ou d’une image."), indicator: n ? "green" : "orange" }, 8);
			} });
		dlg.fields_dict.bilan.$wrapper.html(`
			<p>${__("Couleurs d’impression :")} ${(m.encres || []).map(pastille).join(" &nbsp; ")} ${__("et le blanc du support.")}</p>
			${m.a_jour ? "" : `<p class="text-warning small">${__("Ce contrôle porte sur le PDF précédent : actualisez le PDF pour contrôler le contenu actuel.")}</p>`}
			${m.conforme ? `<p class="text-success">✓ ${__("Tout ce qui s’imprime est en tracés, aux couleurs d’impression.")}</p>` : ""}
			${m.pixels ? `<p class="text-danger">${__("{0} image(s) en pixels sur la page imprimable (photo, fond ou logo non vectoriel) : à passer en aplats.", [m.pixels])}</p>` : ""}
			${ecarts.length ? `<table class="table table-bordered small"><thead><tr><th>${__("Couleur trouvée")}</th><th>${__("Où")}</th><th>${__("Couleur d’impression la plus proche")}</th></tr></thead><tbody>${lignes}</tbody></table>
				<p class="small text-muted">${__("« Aligner les couleurs » ramène à la couleur la plus proche les textes, cartouches, aplats de fond et le QR. Le logo, les pictogrammes et les images se corrigent dans leurs propres outils.")}</p>` : ""}`);
		if (m.conforme) dlg.get_primary_btn().hide();
		dlg.show();
	}

	// Le décor d’une face en aplats : tracé direct (gratuit) ou redessiné par l’IA puis tracé.
	async atelier_aplats(code, options = {}) {
		try { await this.attendre_sauvegardes(); } catch (e) { frappe.msgprint(this._msg(e)); return; }
		const design = this.nom, esc = this._esc, est = this.data.estimation || {};
		const reg = this._fonds()[code] || {};
		const source = options.source_url || reg.image || this.d.image_fond || "";
		const face = ((this.data.apercu || {}).faces || []).find((f) => f.code === code) || {};
		const damier = "background:#fff;border:1px solid #e5e7eb;border-radius:8px";
		let occupe = false;
		const dlg = new frappe.ui.Dialog({ title: __("Aplats pour l’impression — {0}", [face.libelle || code]), size: "extra-large",
			fields: [
				{ fieldtype: "HTML", fieldname: "depart" },
				{ fieldtype: "Data", fieldname: "couleurs", label: __("Couleurs d’impression (codes HEX)"), reqd: 1,
					default: options.couleurs || this.d.encres_impression || "",
					description: __("Celles de l’imprimeur, 1 à 4, séparées par des virgules : « #0264c3, #5badf0 ». Le blanc du support ne se compte pas.") },
				{ fieldtype: "HTML", fieldname: "palette" },
				{ fieldtype: "Select", fieldname: "lissage", label: __("Finesse du tracé"), default: options.lissage || "normal",
					options: [{ value: "fin", label: __("Fin — garde les petits détails") }, { value: "normal", label: __("Normal") }, { value: "fort", label: __("Fort — formes simples, moins de taches") }] },
				{ fieldtype: "Section Break", label: __("Redessiner par IA (facultatif, payant)"), collapsible: 1, collapsed: options.consigne ? 0 : 1 },
				{ fieldtype: "Small Text", fieldname: "consigne", label: __("Précision pour l’IA"), default: options.consigne || "",
					description: __("ex. « pastilles bien visibles, contour épais », « garder seulement la goutte et les feuilles ». L’IA reçoit l’image de départ et vos couleurs.") },
				{ fieldtype: "Select", fieldname: "nombre", label: __("Propositions à comparer"), options: "1\n2\n3\n4", default: String(options.nombre || 1) },
				{ fieldtype: "Section Break" },
				{ fieldtype: "HTML", fieldname: "resultat" },
			],
			primary_action_label: __("Tracer aux couleurs · gratuit"),
			primary_action: () => lancer("vectoriser_face"),
			secondary_action_label: __("Redessiner par IA…"),
			secondary_action: () => {
				const n = +(dlg.get_value("nombre") || 1);
				frappe.confirm(__("Faire redessiner cette image en aplats par l’IA : {0} proposition(s), coût estimé <b>{1} $</b> ?", [n, ((est.cout || 0) * n).toFixed(2)]),
					() => lancer("redessiner_face"));
			} });
		const reprise = () => Object.assign({}, dlg.get_values(true) || {}, { source_url: source });
		dlg.fields_dict.depart.$wrapper.html(source
			? `<div style="display:flex;gap:12px;align-items:center;margin-bottom:8px"><img src="${esc(source)}" alt="" style="height:110px;max-width:160px;object-fit:contain;${damier}">
				<div><b>${__("Image de départ")}</b><br><span class="small text-muted">${__("Un dessin déjà en aplats se trace très bien. Une photo donne un tracé approximatif : faites-la d’abord redessiner par IA, ici ou dans ChatGPT.")}</span><br>
				<button class="btn btn-xs btn-default" data-autre-image style="margin-top:4px">${__("Choisir ou importer une autre image…")}</button></div></div>`
			: `<p>${__("Aucune image sur cette face.")} <button class="btn btn-xs btn-default" data-autre-image>${__("Choisir ou importer une image…")}</button></p>`);
		dlg.fields_dict.depart.$wrapper.find("[data-autre-image]").on("click", () => {
			const valeurs = reprise();
			dlg.hide();
			this.mediatheque("image_fond", async (url) => { if (this.nom === design) this.atelier_aplats(code, Object.assign(valeurs, { source_url: url })); },
				__("Image à passer en aplats"));
		});
		const palette = this._palette();
		dlg.fields_dict.palette.$wrapper.html(palette.length ? `<div class="small text-muted" style="margin:-6px 0 8px">${__("Ajouter une couleur de la palette du design :")}
			${palette.map((c) => `<span class="se-pastille petite" data-ajouter-encre="${esc(c)}" title="${esc(c)}" style="background:${esc(c)}"></span>`).join("")}</div>` : "");
		dlg.fields_dict.palette.$wrapper.find("[data-ajouter-encre]").on("click", (e) => {
			const c = $(e.currentTarget).attr("data-ajouter-encre").toLowerCase(), actuelles = this._encres(dlg.get_value("couleurs") || "");
			if (!actuelles.includes(c)) dlg.set_value("couleurs", actuelles.concat(c).join(", "));
		});
		const lancer = async (route) => {
			const v = dlg.get_values();
			if (!v || occupe) return;
			if (!source) return frappe.msgprint(__("Choisissez d’abord l’image à passer en aplats."));
			occupe = true;
			let r;
			try {
				r = await frappe.call({ method: "aquaworld_ia.emballage.aplats." + route, freeze: true,
					freeze_message: route === "redessiner_face" ? __("L’IA redessine en aplats… (environ 30 secondes par proposition)") : __("Tracé aux couleurs d’impression…"),
					args: { design, face: code, couleurs: v.couleurs, lissage: v.lissage, source_url: source, consigne: v.consigne || "", nombre: v.nombre || 1 } });
			} catch (e) { frappe.msgprint(this._msg(e)); return; }
			finally { occupe = false; }
			const m = r.message || {};
			if (this.nom === design) { this.d.encres_impression = (m.encres || []).join(", "); this.data.images = m.images || this.data.images; }
			afficher(m);
		};
		const afficher = (m) => {
			const carte = (url, titre, corps) => `<div style="flex:1 1 240px;min-width:0;text-align:center"><div class="small text-muted">${titre}</div>
				<a href="${esc(url)}" target="_blank" rel="noopener"><img src="${esc(url)}" alt="" style="width:100%;height:320px;object-fit:contain;${damier}"></a>${corps || ""}</div>`;
			const bilan = (c) => `<div class="small" style="margin-top:4px">${(m.encres || []).map((e) => `<span class="se-pastille petite" style="background:${esc(e)};cursor:default;vertical-align:middle"></span> ${(c.couverture || {})[e] || 0} %`).join(" &nbsp; ")}
				&nbsp; ${__("blanc {0} %", [c.blanc])} · ${__("{0} tracés · {1} Ko", [c.chemins, c.taille_ko])}</div>
				${(c.avertissements || []).map((a) => `<p class="small text-warning" style="margin:4px 0 0">${esc(a)}</p>`).join("")}
				<div class="se-btns" style="justify-content:center;margin-top:6px"><button class="btn btn-xs btn-primary" data-utiliser-aplats="${esc(c.url)}">${__("Utiliser sur cette face")}</button>
				<a class="btn btn-xs btn-default" href="${esc(c.url)}" download target="_blank" rel="noopener">${__("Télécharger le SVG")}</a>
				${c.dessin ? `<a class="btn btn-xs btn-default" href="${esc(c.dessin)}" target="_blank" rel="noopener">${__("Voir le dessin de l’IA")}</a>` : ""}</div>`;
			const $r = dlg.fields_dict.resultat.$wrapper;
			$r.html(`<div style="display:flex;gap:14px;flex-wrap:wrap;align-items:flex-start">${carte(m.source, __("Image de départ"))}
				${(m.candidats || []).map((c, k) => carte(c.url, (m.candidats || []).length > 1 ? __("Tracé en aplats {0}", [k + 1]) : __("Tracé en aplats"), bilan(c))).join("")}</div>
				<p class="small text-muted" style="margin-top:8px">${__("Rien ne change avant « Utiliser sur cette face ». Cliquez une image pour la voir en grand ; les tracés restent dans la médiathèque. Sur cette face, la photo du produit ne sera plus posée par-dessus : une photo ne s’imprime pas en aplats.")}</p>`);
			$r.find("[data-utiliser-aplats]").on("click", async (e) => {
				const $b = $(e.currentTarget).prop("disabled", true);
				let r;
				try {
					r = await frappe.call({ method: "aquaworld_ia.emballage.studio.adopter_face_ia", freeze: true, freeze_message: __("Décor posé, recomposition du plan…"),
						args: { design, face: code, url: $b.attr("data-utiliser-aplats"), photo_incluse: 1 } });
				} catch (e2) { frappe.msgprint(this._msg(e2)); return; }
				finally { $b.prop("disabled", false); }
				dlg.hide();
				if (this.nom !== design) return;
				this.data = Object.assign({}, this.data, r.message); this.d = this.data.doc; this._lire_mep();
				if (r.message.recompose) this.onglet = "artwork";
				this.rendre();
				frappe.show_alert({ message: r.message.recompose ? __("Décor en aplats posé, plan recomposé.") : __("Décor en aplats posé : composez le plan (étape 4)."), indicator: "green" });
			});
		};
		dlg.show();
	}
}
