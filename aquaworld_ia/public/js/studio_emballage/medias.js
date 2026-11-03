// Responsabilité : medias du studio emballage.
class StudioMedias {
	televerser(champ, on_choisir = null) {
		const design = this.nom;
		new frappe.ui.FileUploader({
			doctype: "Design Emballage", docname: design, folder: "Home/Attachments",
			restrictions: { allowed_file_types: ["image/*", ".svg"] },
			on_success: async (file) => {
				try { return await (on_choisir ? on_choisir(file.file_url) : this.modifier({ [champ]: file.file_url }, true, design)); }
				catch (e) { frappe.msgprint(this._msg(e)); }
			},
		});
	}

	// ─── scène (centre) ─────────────────────────────────────────────────────────
	scene_variantes($s) {
		const d = this.d, esc = this._esc;
		const vs = d.variantes || [];
		if (!vs.length) return $s.html(`<div class="se-vide">${__("Aucune variante : préparez les textes et styles, puis générez.")}</div>`);
		$s.html(`<div class="se-aide-variantes">${__("Une <b>variante</b> est une image IA de la <b>face avant entière</b> : votre photo produit mise en scène dans un style (titre et description sous chaque image). La variante <b>choisie</b> devient le visuel de la face avant du plan (et du dos si « face arrière identique ») ; les autres faces prennent la couleur ou l'image de fond. Cliquez « ✓ Choisie » pour la retirer : la face avant redevient fond + photo produit.")}</div>
			<div class="se-galerie">${vs.map((v) => `
			<div class="se-carte ${v.numero === d.variante_choisie ? "choisie" : ""}">
				${v.image ? `<img src="${esc(v.image)}" alt="">` : `<div class="vide">${esc(v.statut || "")}</div>`}
				<div class="leg"><b>${v.numero}. ${esc(v.titre || "")}</b><br><span class="text-muted">${esc(v.description || "")}</span>
				${v.erreur ? `<br><span class="text-danger">${esc(v.erreur)}</span>` : ""}
				${v.cout_estime ? `<br><span class="text-muted">${v.cout_estime.toFixed(3)} $</span>` : ""}</div>
				<div class="act">
					${v.statut === "Prête" ? (v.numero === d.variante_choisie
						? `<button class="btn btn-xs btn-primary" data-retirer-variante="${v.numero}" title="${__("Ne plus utiliser cette variante sur la face avant")}">✓ ${__("Choisie")} — ${__("retirer")}</button>`
						: `<button class="btn btn-xs btn-primary" data-choisir="${v.numero}">${__("Choisir")}</button>`) : ""}
					${["Prête", "Échec"].includes(v.statut) ? `<button class="btn btn-xs btn-default" data-regenerer="${v.numero}">${__("Régénérer")}</button>` : ""}
				</div></div>`).join("")}</div>`);
		$s.find("[data-choisir]").on("click", async (e) => {
			await frappe.call({ method: "aquaworld_ia.emballage.job.choisir_variante", args: { design: this.nom, numero: $(e.currentTarget).data("choisir") } });
			await this.recharger();
		});
		$s.find("[data-retirer-variante]").on("click", () => {
			frappe.confirm(__("Ne plus utiliser de variante IA sur la face avant ? Elle redeviendra fond + photo produit (recomposez ensuite le plan, étape 4)."), async () => {
				await frappe.call({ method: "aquaworld_ia.emballage.job.choisir_variante", args: { design: this.nom, numero: 0 } });
				await this.recharger();
				frappe.show_alert({ message: __("Variante retirée : recomposez le plan (étape 4)."), indicator: "green" });
			});
		});
		$s.find("[data-regenerer]").on("click", (e) => {
			const n = $(e.currentTarget).data("regenerer");
			frappe.confirm(__("Régénérer la variante {0} ? (1 image facturée)", [n]), async () => {
				await frappe.call({ method: "aquaworld_ia.emballage.job.regenerer_variante", args: { design: this.nom, numero: n } });
				this.suivre();
			});
		});
	}

	// ─── images du design : tout ce qui a été téléversé ou produit ───────────────
	scene_images($s, liste = null) {
		const design = this.nom, esc = this._esc, images = liste || this.data.images || [];
		if (!images.length) return $s.html(`<div class="se-vide">${__("Aucune image encore : téléversez un logo ou une photo, générez un fond ou des variantes.")}</div>`);
		const USAGES = { logo: __("logo actuel"), photo_produit: __("photo actuelle"), image_fond: __("fond actuel") };
		$s.html(`<p class="text-muted small">${__("Toutes les images de ce design, la plus récente d'abord : logos et logos retouchés par IA, photos, fonds, variantes, faces IA. Un clic les remet en service ou les garde en bibliothèque.")}</p>
			<div class="se-galerie">${images.map((im) => `
			<div class="se-carte ${im.usage ? "choisie" : ""}">
				<img src="${esc(im.file_url)}" alt="" data-voir-url="${esc(im.file_url)}" title="${__("Ouvrir en grand — prendre une couleur à la pipette")}" style="aspect-ratio:4 / 3;object-fit:contain;background:#fff;cursor:zoom-in">
				<div class="leg"><span class="se-chip">${esc(im.genre)}</span> ${im.usage ? `<span class="se-chip ok">${USAGES[im.usage]}</span>` : ""}<br><span class="text-muted">${esc(frappe.datetime.str_to_user(im.creation).slice(0, 16))}</span></div>
				<div class="act" style="flex-wrap:wrap">
					<button class="btn btn-xs btn-default" data-usage="logo" data-url="${esc(im.file_url)}" title="${__("Utiliser comme logo du design")}">${__("Logo")}</button>
					<button class="btn btn-xs btn-default" data-usage="photo_produit" data-url="${esc(im.file_url)}" title="${__("Utiliser comme photo du produit")}">${__("Photo")}</button>
					<button class="btn btn-xs btn-default" data-usage="image_fond" data-url="${esc(im.file_url)}" title="${__("Utiliser comme image de fond")}">${__("Fond")}</button>
					${this.data.peut_ecrire && /^(Logo|Photo|Téléversé)/.test(im.genre || "") && /\.(png|jpe?g|webp)(?:[?#]|$)/i.test(im.file_url) ? `<button class="btn btn-xs btn-default" data-vectoriser-url="${esc(im.file_url)}" data-champ-svg="${im.genre.startsWith("Logo") ? "logo" : "photo_produit"}">${__("SVG couleur")}</button>` : ""}
					<button class="btn btn-xs btn-default" data-garder-url="${esc(im.file_url)}" data-garder-champ="${im.genre.startsWith("Logo") ? "logo" : im.genre.startsWith("Photo") ? "photo_produit" : "image_fond"}" title="${__("Garder en bibliothèque, sous un nom")}">💾</button>
					<a class="btn btn-xs btn-default" href="${esc(im.file_url)}" target="_blank" title="${__("Ouvrir le fichier")}">↗</a>
				</div></div>`).join("")}</div>`);
		$s.find("[data-usage]").on("click", (e) => this.modifier({ [$(e.currentTarget).attr("data-usage")]: $(e.currentTarget).attr("data-url") }, true, design));
		$s.find("[data-garder-url]").on("click", (e) => this.garder($(e.currentTarget).attr("data-garder-champ"), $(e.currentTarget).attr("data-garder-url")));
		$s.find("[data-voir-url]").on("click", (e) => this.visionneuse($(e.currentTarget).attr("data-voir-url"), ""));
		$s.find("[data-vectoriser-url]").on("click", (e) => {
			const $b = $(e.currentTarget);
			this.atelier_vectorisation($b.attr("data-champ-svg"), $b.attr("data-vectoriser-url"));
		});
	}

	// ─── colonne de droite ──────────────────────────────────────────────────────
	async blanchir(cible) {
		let r;
		try {
			r = await frappe.call({ method: "aquaworld_ia.emballage.studio.blanchir", args: { design: this.nom, cible }, freeze: true,
				freeze_message: __("Blanc pur, puis recomposition du plan…") });
		} catch (e) { frappe.msgprint(this._msg(e)); return; }
		const m = r.message || {};
		this.data = m; this.d = m.doc; this._lire_mep(); if (m.recompose) this.onglet = "artwork"; this.rendre();
		frappe.show_alert({ message: __("Blanc pur : {0} % de pixels parfaitement blancs (avant : {1} %). L'ancienne image reste dans la médiathèque.", [m.blanc_apres, m.blanc_avant]), indicator: "green" }, 8);
	}

	_fonds() {
		try { const o = typeof this.d.fonds_faces === "string" ? JSON.parse(this.d.fonds_faces || "{}") : (this.d.fonds_faces || {}); return o && typeof o === "object" ? o : {}; }
		catch (e) { return {}; }
	}

	// « Fond de cette face » : la règle automatique, l'image de fond du design, une couleur, du blanc, ou une image
	// composée par l'IA (demande utilisateur 06/10/2026 : « l'image de fond, je l'applique sur la face que je veux »).
	_bloc_fond_face(f) {
		const esc = this._esc, reg = this._fonds()[f.code] || {}, mode = reg.mode || "";
		const MODES = [["", __("Automatique")], ["fond", __("Image de fond")], ["couleur", __("Couleur")], ["blanc", __("Blanc")]]
			.concat(reg.image ? [["image", __("Image IA")]] : []);
		// Des boutons et non une liste : la liste grise ne se voyait pas comme un menu (retour utilisateur 06/10/2026).
		return `<div class="bloc" data-section-propriete="fond" style="margin-top:8px;padding:8px 10px;background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px">
			<h6>${__("Fond de cette face")}</h6>
			<div style="display:flex;gap:4px;flex-wrap:wrap">${MODES.map(([v, l]) => `<button class="btn btn-xs ${v === mode ? "btn-primary" : "btn-default"}" data-mode-fond="${v}">${v === mode ? "✓ " : ""}${l}</button>`).join("")}</div>
			${mode === "couleur" ? `<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-top:6px">
				<input type="color" data-role="fond-face-couleur" value="${esc(reg.couleur || "#e5e7eb")}" style="width:44px;height:26px;padding:1px">
				${this._palette().map((c) => `<span class="se-pastille petite" data-fond-face-pastille="${esc(c)}" title="${esc(c)}" style="background:${esc(c)}"></span>`).join("")}</div>` : ""}
			${reg.image ? `<div style="display:flex;gap:8px;align-items:center;margin-top:6px"><a href="#" data-voir-face="${esc(reg.image)}"><img src="${esc(reg.image)}" style="height:54px;max-width:90px;object-fit:cover;border:1px solid #e5e7eb;border-radius:6px"></a>
				<span class="small text-muted">${mode === "image" ? __("Image IA posée sur cette face") : __("Image IA gardée (« Image IA » pour la remettre)")}</span></div>
				${mode === "image" ? `<label class="se-check" style="margin-top:4px"><input type="checkbox" data-role="photo-incluse" ${reg.photo_incluse ? "checked" : ""}> ${__("Le produit est déjà dans cette image (ne pas reposer la photo par-dessus)")}</label>` : ""}` : ""}
			<button class="btn btn-xs btn-default" data-role="fond-face-ia" style="margin-top:6px">✨ ${__("Composer cette face par IA")}</button>
			${(mode === "image" && reg.image) || ((mode === "fond" || !mode) && this.d.image_fond) ? `<button class="btn btn-xs btn-default" data-role="fond-face-blanc" style="margin-top:6px" title="${__("Le presque blanc devient du blanc pur #FFFFFF, comme les faces réglées sur Blanc. Sans IA.")}">⚪ ${__("Blanc pur")}</button>` : ""}
			<div class="text-muted small" style="margin-top:4px">${__("Automatique = l'image de fond (ou la variante sur l'avant) ; Blanc = rien d'imprimé en fond. Recomposez le plan (étape 4) pour voir le résultat.")}</div></div>`;
	}

	// Une face composée par l'IA à partir des composants choisis (fond, image actuelle de la face, photo, logo) et
	// d'une consigne — « quelque chose de plus uniforme » ; propositions comparées, rien n'est posé avant « Utiliser ».
	atelier_face(code, reprise) {
		const esc = this._esc, d = this.d, est = this.data.estimation || {};
		reprise = reprise || {};
		const faces = ((this.data.apercu || {}).faces || []).map((x) => ({ value: x.code, label: x.libelle }));
		const reg_de = (c) => this._fonds()[c] || {};
		const COMPOSANTS = [["fond", __("Image de fond du design"), !!d.image_fond], ["image_face", __("Image actuelle de cette face (pour l'améliorer)"), false],
			["photo", __("Photo du produit (intégrée par l'IA)"), !!d.photo_produit], ["logo", __("Couleurs du logo (jamais dessiné)"), !!(d.logo || d.marque)]];
		const dlg = new frappe.ui.Dialog({ title: __("Composer une face par IA"), size: "large",
			fields: [
				{ fieldtype: "Select", fieldname: "face", label: __("Face"), options: faces, default: reprise.face || code },
				{ fieldtype: "HTML", fieldname: "composants" },
				{ fieldtype: "Small Text", fieldname: "consigne", label: __("Ce que vous voulez"), default: reprise.consigne !== undefined ? reprise.consigne : (reg_de(code).consigne || ""),
				  description: __("ex. « intègre les pastilles dans l'eau des vagues, lumière douce, même bleu que le fond », « plus uniforme, sans démarcation »") },
				{ fieldtype: "Select", fieldname: "nombre", label: __("Propositions à comparer"), options: "1\n2\n3\n4", default: String(reprise.nombre || 2) },
				{ fieldtype: "Section Break", label: __("Texte envoyé à l'IA"), collapsible: 1 },
				{ fieldtype: "HTML", fieldname: "prompt" },
			],
			primary_action_label: __("Générer"),
			primary_action: async (v) => {
				const composants = choisis();
				if (!composants.length) return frappe.msgprint(__("Cochez au moins un composant."));
				let r;
				try {
					r = await frappe.call({ method: "aquaworld_ia.emballage.studio.composer_face_ia", freeze: true,
						freeze_message: __("L'IA compose la face… (environ 30 secondes par proposition)"),
						args: { design: this.nom, face: v.face, composants: JSON.stringify(composants), consigne: v.consigne || "", nombre: v.nombre } });
				} catch (e) { frappe.msgprint(this._msg(e)); return; }
				dlg.hide();
				const fonds = this._fonds(); fonds[v.face] = Object.assign({}, fonds[v.face] || {}, { consigne: v.consigne || "" }); this.d.fonds_faces = JSON.stringify(fonds);
				this.comparer_faces(r.message || {}, Object.assign({}, v, { composants }));
			} });
		const choisis = () => dlg.fields_dict.composants.$wrapper.find("[data-composant]:checked").map((_i, el) => $(el).attr("data-composant")).get();
		const rendre_composants = () => {
			const face = dlg.get_value("face") || code, reg = reg_de(face), pris = new Set(reprise.composants || ["fond", "photo"]);
			dlg.fields_dict.composants.$wrapper.html(`<label class="control-label">${__("Composants envoyés à l'IA")}</label>
				${COMPOSANTS.map(([c, l, dispo]) => {
					const ok = c === "image_face" ? !!reg.image : dispo;
					return `<label class="se-check" style="display:block;margin:2px 0;${ok ? "" : "opacity:.45"}"><input type="checkbox" data-composant="${c}" ${ok && pris.has(c) ? "checked" : ""} ${ok ? "" : "disabled"}> ${l}</label>`;
				}).join("")}
				<div class="small text-muted">${__("La photo cochée : l'IA intègre le produit dans la face, et la photo n'est plus reposée par-dessus. Le logo, le nom et les textes restent ajoutés en vectoriel.")}</div>`);
		};
		const libelle_bouton = () => {
			const n = +(dlg.get_value("nombre") || reprise.nombre || 2);
			dlg.set_primary_action(__("Générer {0} proposition(s) · ≈ {1} $", [n, ((est.cout || 0) * n).toFixed(2)]), dlg.primary_action);
		};
		const apercu = frappe.utils.debounce(async () => {
			const v = dlg.get_values(true) || {};
			try {
				const r = await frappe.call({ method: "aquaworld_ia.emballage.studio.composer_face_ia",
					args: { design: this.nom, face: v.face || code, composants: JSON.stringify(choisis()), consigne: v.consigne || "", apercu: 1 } });
				dlg.fields_dict.prompt.$wrapper.html(`<pre style="white-space:pre-wrap;font-size:11.5px;background:#f8fafc;border:1px solid #e5e7eb;border-radius:6px;padding:8px;margin:0">${esc((r.message || {}).prompt || "")}</pre>`);
			} catch (e) { /* aperçu facultatif */ }
		}, 400);
		dlg.$wrapper.on("input change", "input, select, textarea", apercu);
		dlg.$wrapper.on("change", '[data-fieldname="nombre"] select', libelle_bouton);
		dlg.$wrapper.on("change", '[data-fieldname="face"] select', () => { rendre_composants(); apercu(); });
		rendre_composants();
		dlg.show();
		libelle_bouton();
		apercu();
	}

	comparer_faces(m, reglages) {
		const esc = this._esc, candidats = m.candidats || [];
		const carte = (src, titre, url) => `<div style="flex:1 1 220px;text-align:center;min-width:0"><div class="small text-muted">${titre}</div>
			<a href="#" data-voir-prop="${esc(src || "")}"><img src="${esc(src || "")}" style="width:100%;max-height:300px;object-fit:contain;background:#f1f5f9;border:1px solid #e5e7eb;border-radius:8px"></a>
			${url ? `<div style="margin-top:6px"><button class="btn btn-xs btn-primary" data-utiliser-face="${esc(url)}">${__("Utiliser sur cette face")}</button></div>` : ""}</div>`;
		const cmp = new frappe.ui.Dialog({ title: __("Propositions pour la face"), size: "extra-large",
			fields: [{ fieldtype: "HTML", fieldname: "galerie" }],
			secondary_action_label: __("Réessayer"), secondary_action: () => { cmp.hide(); this.atelier_face(m.face, reglages); } });
		cmp.fields_dict.galerie.$wrapper.html(`<div style="display:flex;gap:14px;flex-wrap:wrap;align-items:flex-start">
				${m.actuel ? carte(m.actuel, __("Actuel"), null) : ""}${candidats.map((u, k) => carte(u, __("Proposition {0}", [k + 1]), u)).join("")}</div>
			<p class="small text-muted" style="margin-top:8px">${__("Rien ne change avant « Utiliser sur cette face ». Les propositions restent dans la médiathèque.")}</p>`);
		cmp.fields_dict.galerie.$wrapper.find("[data-voir-prop]").on("click", (e) => { e.preventDefault(); this.visionneuse($(e.currentTarget).attr("data-voir-prop"), ""); });
		cmp.fields_dict.galerie.$wrapper.find("[data-utiliser-face]").on("click", async (e) => {
			let r;
			try {
				r = await frappe.call({ method: "aquaworld_ia.emballage.studio.adopter_face_ia", freeze: true, freeze_message: __("Face posée, recomposition du plan…"),
					args: { design: this.nom, face: m.face, url: $(e.currentTarget).attr("data-utiliser-face"), photo_incluse: m.photo_incluse ? 1 : 0 } });
			} catch (e2) { frappe.msgprint(this._msg(e2)); return; }
			cmp.hide();
			this.data = Object.assign({}, this.data, r.message); this.d = this.data.doc; this._lire_mep();
			if (r.message.recompose) this.onglet = "artwork";
			this.rendre();
			frappe.show_alert({ message: r.message.recompose ? __("Face posée, plan recomposé.") : __("Face posée : composez le plan (étape 4)."), indicator: "green" });
		});
		cmp.show();
	}

	// Une zone de texte : son texte (texte libre, jamais touché par l'IA), sa typographie et sa
	// couleur — demande utilisateur 06/10/2026 : « chaque zone texte je peux contrôler font et couleur ».
	async modifier_media(champ) {
		try { await this.attendre_sauvegardes(); } catch (e) { frappe.msgprint(this._msg(e)); return; }
		const url = this.d[champ], esc = this._esc;
		if (!url) return this.mediatheque(champ);
		const actions = [{ id: "voir", label: __("Voir et prélever une couleur") }];
		if (!/\.svg(?:[?#]|$)/i.test(url)) actions.push({ id: "resolution", label: __("Améliorer la résolution · gratuit") });
		if (champ === "logo") actions.push({ id: "couleur", label: __("Recolorer le logo") });
		if (["logo", "photo_produit"].includes(champ) && !/\.svg(?:[?#]|$)/i.test(url)) actions.push({ id: "svg", label: __("SVG couleur · gratuit") });
		actions.push({ id: "ia", label: __("Préparer ou retoucher par IA…") });
		if (champ === "photo_produit") actions.push({ id: "mosaique", label: __("Composer une mosaïque") });
		if (champ === "image_fond") actions.push({ id: "blanc", label: __("Nettoyer le fond blanc") });
		actions.push({ id: "garder", label: __("Garder en bibliothèque") }, { id: "retirer", label: __("Retirer du design") });
		const dlg = new frappe.ui.Dialog({ title: __("Modifier l’image"), fields: [{ fieldtype: "HTML", fieldname: "outils", options:
			`<img src="${esc(url)}" alt="" style="display:block;max-width:100%;height:180px;object-fit:contain;margin:0 auto 15px">
			<div class="se-btns">${actions.map(a => `<button class="btn btn-default" data-outil="${a.id}">${a.label}</button>`).join("")}</div>` }] });
		dlg.fields_dict.outils.$wrapper.find("[data-outil]").on("click", e => {
			dlg.hide();
			const action = $(e.currentTarget).attr("data-outil");
			if (action === "voir") this.visionneuse(url, __("Image du design"));
			if (action === "resolution") this.ameliorer_resolution(champ);
			if (action === "couleur") this.atelier_couleur();
			if (action === "svg") this.atelier_vectorisation(champ);
			if (action === "ia") champ === "image_fond" ? this.atelier_fond() : this.atelier_image(champ);
			if (action === "mosaique") this.atelier_mosaique();
			if (action === "blanc") this.blanchir("fond");
			if (action === "garder") this.garder(champ);
			if (action === "retirer") this.modifier({ [champ]: "" }, true);
		});
		dlg.show();
	}

	ouvrir_variantes() {
		const dlg = new frappe.ui.Dialog({ title: __("Variantes de mise en page"), size: "extra-large", fields: [{ fieldtype: "HTML", fieldname: "galerie" }] });
		this.scene_variantes(dlg.fields_dict.galerie.$wrapper);
		dlg.fields_dict.galerie.$wrapper.on("click", "[data-choisir]", () => dlg.hide());
		dlg.show();
	}

	async mediatheque(champ = "photo_produit", on_choisir = null) {
		try { await this.attendre_sauvegardes(); } catch (e) { frappe.msgprint(this._msg(e)); return; }
		const design = this.nom, esc = this._esc;
		let numero = 0;
		const dlg = new frappe.ui.Dialog({ title: on_choisir ? __("Choisir le logo de cette zone") : __("Médiathèque"), size: "extra-large", fields: [
			{ fieldtype: "Select", fieldname: "origine", label: __("Afficher"), options: ["Ce design", "Bibliothèque", "Propositions IA"], default: "Ce design", onchange: () => afficher() },
			{ fieldtype: "Select", fieldname: "usage", label: __("Utiliser comme"), options: [{ value: "photo_produit", label: __("Photo produit") }, { value: "logo", label: __("Logo") }, { value: "image_fond", label: __("Fond") }], default: champ, hidden: !!on_choisir, onchange: () => afficher() },
			{ fieldtype: "HTML", fieldname: "galerie" }], secondary_action_label: __("Importer un fichier"),
			secondary_action: () => { const cible = dlg.get_value("usage"); dlg.hide(); if (this.nom === design) this.televerser(cible, on_choisir); } });
		const afficher = async () => {
			const requete = ++numero, cible = dlg.get_value("usage"), origine = dlg.get_value("origine"), $g = dlg.fields_dict.galerie.$wrapper;
			if (origine === "Bibliothèque") {
				$g.html(`<p class="text-muted">${__("Chargement…")}</p>`);
				try {
					const r = await frappe.call({ method: "aquaworld_ia.emballage.studio.bibliotheque_liste", args: { champ: cible, marque: this.d.marque } });
					if (requete !== numero) return;
					$g.html(`<div class="se-galerie">${(r.message || []).map(im => `<div class="se-carte"><img src="${esc(im.image)}" alt="" style="object-fit:contain;aspect-ratio:4/3"><div class="leg">${esc(im.nom)}</div><div class="act"><button class="btn btn-default btn-sm" data-ressource="${esc(im.name)}">${__("Utiliser")}</button></div></div>`).join("") || __("Aucune ressource pour cet usage.")}</div>`);
					$g.find("[data-ressource]").on("click", async e => {
						try {
							if (on_choisir) {
								const ressource = (r.message || []).find(im => im.name === $(e.currentTarget).attr("data-ressource"));
								if (ressource) { await on_choisir(ressource.image); dlg.hide(); }
								return;
							}
							const r2 = await frappe.call({ method: "aquaworld_ia.emballage.studio.bibliotheque_choisir", args: { design, champ: cible, ressource: $(e.currentTarget).attr("data-ressource") } });
							dlg.hide(); if (this.nom === design) { this.data = Object.assign({}, this.data, r2.message); this.d = this.data.doc; this._lire_mep(); this.rendre(); }
						} catch (e) { frappe.msgprint(this._msg(e)); }
					});
				} catch (e) { if (requete === numero) $g.text(this._msg(e)); }
			} else {
				const images = (this.data.images || []).filter(im => origine !== "Propositions IA" || /IA|Variante/.test(im.genre));
				this.scene_images($g, images);
				$g.find("[data-usage]").each((_i, el) => { $(el).toggle($(el).attr("data-usage") === cible).text(__("Utiliser")); });
				if (on_choisir) {
					$g.find("[data-vectoriser-url], [data-garder-url]").hide();
					$g.find("[data-usage]").off("click").on("click", async e => {
						try { await on_choisir($(e.currentTarget).attr("data-url")); dlg.hide(); }
						catch (erreur) { frappe.msgprint(this._msg(erreur)); }
					});
				} else $g.find("[data-usage]").on("click", () => dlg.hide());
			}
		};
		dlg.show(); afficher();
	}

	atelier_image(champ, options = {}) {
		const design = options.design || this.nom, source_url = options.source_url || this.d[champ] || null;
		const est = this.data.estimation || {}, est_logo = champ === "logo";
		const cible = options.cible_zone, cible_args = cible ? {cible_zone: cible} : {};
		const consigne_svg = __("Préparer une illustration couleur pour vectorisation : contours propres, aplats de couleurs et peu de dégradés, fond blanc uni. Conserver exactement les couleurs, les proportions, les pièces et les inscriptions visibles. Ne rien ajouter ni inventer.");
		const exemples = est_logo
			? __("ex. « passer le bleu en bleu marine et le texte en blanc », « version épurée à plat », « fond blanc, sans dégradé ». Les formes et les lettres sont conservées, mais relisez-les : l'IA redessine.")
			: __("ex. « détourer sur fond blanc pur, éclairage studio doux », « retirer la clé et le support, garder seulement le porte-filtre », « vue de face, bien net ». Le produit est conservé, mais contrôlez chaque détail : l'IA redessine.");
		const dlg = new frappe.ui.Dialog({ title: cible ? __("Retoucher le logo · {0}", [options.libelle_cible || cible.face]) : est_logo ? __("Retoucher le logo par IA") : __("Améliorer la photo du produit par IA"),
			fields: [
				...(cible ? [{fieldtype: "HTML", options: `<p class="text-muted small">${__("La proposition choisie remplacera uniquement ce logo sur « {0} ». Les autres logos resteront en place.", [this._esc(options.libelle_cible || cible.face)])}</p>`}] : []),
				{ fieldtype: "HTML", options: `<img src="${this._esc(source_url || "")}" style="max-height:120px;max-width:100%;background:#fff;border:1px solid #e5e7eb;border-radius:6px;padding:6px">` },
				{ fieldtype: "Small Text", fieldname: "instruction", label: __("Que changer ?"), reqd: 1, description: exemples,
				  default: options.instruction ?? (options.pour_svg ? consigne_svg : est_logo ? "" : __("Détourer sur fond blanc pur, éclairage studio doux, vue de face, net")) },
				...this.champs_couleurs_ia(options),
				{ fieldtype: "Select", fieldname: "nombre", label: __("Propositions"), default: options.pour_svg || cible ? "1" : "3", options: ["1", "2", "3", "4"].join("\n"),
				  description: __("Plusieurs propositions pour la même consigne : vous choisissez la meilleure. Une image facturée par proposition (qualité {0}, ≈ {1} $ chacune).", [est.qualite || "", (est.cout || 0).toFixed(2)]) },
				{ fieldtype: "HTML", options: `<p class="text-muted small">${__("L’IA prépare une image. Vous pourrez ensuite la vectoriser gratuitement en SVG couleur. L’original reste en place tant que vous n’adoptez pas un résultat.")}</p>` },
			],
			primary_action_label: __("Générer"),
			primary_action: async (v) => {
				const couleur_cible = this.normaliser_couleur(v.couleur_cible);
				if (v.couleur_cible?.trim() && !couleur_cible) return frappe.msgprint(__("Couleur invalide : utilisez #RRGGBB, par exemple #008bcd."));
				const couleurs = {couleur_cible: couleur_cible || "", element_couleur: v.element_couleur || "", utiliser_palette: v.utiliser_palette ? 1 : 0};
				let r;
				try {
					r = await frappe.call({ method: "aquaworld_ia.emballage.studio.retoucher_image", args: { design, champ, source_url, instruction: v.instruction, nombre: v.nombre, ...cible_args, ...couleurs }, freeze: true, freeze_message: est_logo ? __("L'IA redessine le logo…") : __("L'IA retravaille la photo…") });
				} catch (e) { frappe.msgprint(this._msg(e)); return; }
				dlg.hide();
				const c = r.message, candidats = c.candidats || [c.candidat];
				const carte = (src, titre, url) => `<div style="flex:1 1 200px;text-align:center;min-width:0"><div class="text-muted small">${titre}</div>
					<img src="${this._esc(src)}" style="max-width:100%;max-height:220px;background:#fff;border:1px solid #e5e7eb;border-radius:6px">
					${url ? `<div class="se-btns" style="justify-content:center"><button class="btn btn-xs btn-primary" data-adopter="${this._esc(url)}">${cible ? __("Utiliser pour ce logo") : __("Utiliser celui-ci")}</button>
						<button class="btn btn-xs btn-default" data-svg-proposition="${this._esc(url)}">${__("Vectoriser en SVG couleur")}</button></div>` : ""}</div>`;
				const cmp = new frappe.ui.Dialog({ title: est_logo ? __("Propositions de logo") : __("Propositions de photo"), size: "large",
					fields: [{ fieldtype: "HTML", fieldname: "galerie", options: `<div style="display:flex;gap:14px;align-items:flex-start;flex-wrap:wrap">
						${carte(c.source, __("Actuel"), null)}${candidats.map((u, i) => carte(u, __("Proposition {0}", [i + 1]), u)).join("")}</div>
						<p class="small text-muted" style="margin-top:8px">${est_logo ? __("Vérifiez chaque lettre. En adoptant, le fond blanc devient transparent.") : __("Comparez chaque détail du produit avec l'original. En adoptant, le fond blanc devient transparent.")}</p>` }],
					secondary_action_label: __("Réessayer"), secondary_action: () => { cmp.hide(); this.atelier_image(champ, { ...options, ...couleurs, design, source_url, instruction: v.instruction }); } });
				cmp.show();
				cmp.get_field("galerie").$wrapper.find("[data-svg-proposition]").on("click", (e) => {
					cmp.hide(); this.atelier_vectorisation(champ, $(e.currentTarget).attr("data-svg-proposition"), design, {...options, ...couleurs});
				});
				cmp.get_field("galerie").$wrapper.find("[data-adopter]").on("click", async (e) => {
					const $bouton = $(e.currentTarget).prop("disabled", true);
					try { await this.adopter_proposition_image(design, champ, $bouton.attr("data-adopter"), options); cmp.hide(); }
					catch (erreur) { frappe.msgprint(this._msg(erreur)); }
					finally { $bouton.prop("disabled", false); }
				});
			} });
		this.lier_couleurs_ia(dlg, {...options, source_url});
		dlg.show();
	}

	async adopter_proposition_image(design, champ, url, options = {}) {
		const cible = options.cible_zone;
		if (cible && this.nom !== design) throw new Error(__("Rouvrez le design concerné pour modifier ce logo."));
		await this.attendre_sauvegardes();
		if (cible && this.nom !== design) throw new Error(__("Rouvrez le design concerné pour modifier ce logo."));
		const r = await frappe.call({method: "aquaworld_ia.emballage.studio.adopter_image",
			args: {design, champ, url, ...(cible ? {cible_zone: cible} : {})}, freeze: true});
		if (this.nom === design) {
			this.data = Object.assign({}, this.data, r.message); this.d = this.data.doc; this._lire_mep();
			if (cible) { this.epinglee = cible.face; this.zone_sel = cible.indice; this.onglet = "plan"; }
			this.rendre();
		}
	}

	// Le fond IA sous contrôle (demande utilisateur 06/10/2026 : « est-ce que je peux contrôler ce que je génère ? »,
	// « comment regénérer une image de fond que je contrôle bien ? ») : un NOUVEAU fond (consigne, style de la
	// variante, logo) ou une RETOUCHE du fond actuel ; plusieurs propositions comparées au fond actuel ; rien n'est
	// remplacé avant « Utiliser ce fond ». La consigne revient pré-remplie pour l'affiner.
	atelier_fond(reprise) {
		const esc = this._esc, d = this.d, est = this.data.estimation || {};
		reprise = reprise || {};
		const choisie = (d.variantes || []).find((v) => v.numero === d.variante_choisie);
		const damier = "background:repeating-conic-gradient(#e5e7eb 0% 25%, #fff 0% 50%) 50% / 16px 16px";
		const MODES = [{ value: "nouveau", label: __("Nouveau fond") }].concat(d.image_fond ? [{ value: "retouche", label: __("Retoucher le fond actuel") }] : []);
		const dlg = new frappe.ui.Dialog({ title: __("Fond d'ambiance par IA"), size: "large",
			fields: [
				{ fieldtype: "HTML", fieldname: "actuel" },
				{ fieldtype: "Select", fieldname: "mode", label: __("Que faire ?"), options: MODES, default: reprise.mode || "nouveau",
				  description: __("« Retoucher » garde votre fond et ne change que ce que vous demandez (plus clair, vagues plus fines…).") },
				{ fieldtype: "Small Text", fieldname: "consigne", label: __("Ce que vous voulez"), default: reprise.consigne !== undefined ? reprise.consigne : (d.consigne_fond || ""),
				  description: __("ex. « vagues bleues seulement en bas, fond blanc pur en haut », « plus clair », « vagues plus fines et plus basses »") },
				{ fieldtype: "Check", fieldname: "suivre_style", default: choisie ? 1 : 0, hidden: choisie ? 0 : 1, depends_on: "eval:doc.mode=='nouveau'",
				  label: choisie ? __("Suivre le style de la variante choisie : « {0} »", [choisie.titre || choisie.numero]) : "" },
				{ fieldtype: "Check", fieldname: "avec_logo", default: (d.logo || d.marque) ? 1 : 0, hidden: (d.logo || d.marque) ? 0 : 1, depends_on: "eval:doc.mode=='nouveau'",
				  label: __("Reprendre les couleurs du logo (le logo est montré à l'IA, jamais dessiné)") },
				{ fieldtype: "Check", fieldname: "continu", default: d.fond_continu ? 1 : 0, label: __("Panorama continu sur toutes les faces (découpé aux plis)") },
				{ fieldtype: "Select", fieldname: "nombre", label: __("Propositions à comparer"), options: "1\n2\n3\n4", default: String(reprise.nombre || 2) },
				{ fieldtype: "HTML", fieldname: "sources" },
				{ fieldtype: "Section Break", label: __("Texte envoyé à l'IA"), collapsible: 1 },
				{ fieldtype: "HTML", fieldname: "prompt" },
			],
			primary_action_label: __("Générer"),
			primary_action: async (v) => {
				const args = { design: this.nom, consigne: v.consigne || "", nombre: v.nombre, mode: v.mode, suivre_style: v.suivre_style ? 1 : 0,
				               avec_logo: v.avec_logo ? 1 : 0, continu: v.continu ? 1 : 0 };
				let r;
				try {
					r = await frappe.call({ method: "aquaworld_ia.emballage.studio.proposer_fonds", args, freeze: true,
						freeze_message: __("L'IA dessine {0} fond(s)… (environ 30 secondes)", [v.nombre]) });
				} catch (e) { frappe.msgprint(this._msg(e)); return; }
				dlg.hide();
				this.d.consigne_fond = v.consigne || "";
				this.comparer_fonds(r.message || {}, Object.assign({}, v));
			} });
		const libelle_bouton = () => {
			const n = +(dlg.get_value("nombre") || reprise.nombre || 2);
			dlg.set_primary_action(__("Générer {0} proposition(s) · ≈ {1} $", [n, ((est.cout || 0) * n).toFixed(2)]), dlg.primary_action);
		};
		dlg.fields_dict.actuel.$wrapper.html(d.image_fond ? `<div style="display:flex;gap:10px;align-items:center;margin-bottom:6px;flex-wrap:wrap">
			<img src="${esc(d.image_fond)}" style="height:70px;max-width:160px;object-fit:cover;${damier};border:1px solid #e5e7eb;border-radius:6px">
			<span class="small text-muted" style="flex:1 1 200px">${__("Fond actuel. Les anciens fonds restent dans la médiathèque (bouton « Fond » pour revenir à l'un d'eux).")}</span>
			<button class="btn btn-xs btn-default" data-role="blanc-pur" title="${__("Le presque blanc de l'image devient du blanc pur #FFFFFF — les couleurs ne bougent pas. Sans IA, gratuit.")}">⚪ ${__("Blanc pur")}</button></div>` : "");
		dlg.fields_dict.actuel.$wrapper.find('[data-role="blanc-pur"]').on("click", () => { dlg.hide(); this.blanchir("fond"); });
		const palette = this._palette();
		dlg.fields_dict.sources.$wrapper.html(`<div class="small" style="margin-top:4px">
			<div><b>${__("Palette")}</b> : ${palette.length ? palette.map((c) => `<span class="se-pastille petite" style="background:${esc(c)};vertical-align:middle;cursor:default" title="${esc(c)}"></span>`).join(" ") : `<span class="text-muted">${__("aucune")}</span>`}</div>
			<div><b>${__("Brief de style")}</b> : ${d.brief_style ? esc(d.brief_style) : `<span class="text-muted">${__("aucun")}</span>`}</div>
			<div class="text-muted">${__("La palette et le brief (étape 3) servent au « Nouveau fond » ; la retouche ne suit que votre consigne.")}</div></div>`);
		const apercu = frappe.utils.debounce(async () => {
			const v = dlg.get_values(true) || {};
			try {
				const r = await frappe.call({ method: "aquaworld_ia.emballage.job.apercu_prompt_fond",
					args: { design: this.nom, consigne: v.consigne || "", suivre_style: v.suivre_style ? 1 : 0, continu: v.continu ? 1 : 0, mode: v.mode } });
				dlg.fields_dict.prompt.$wrapper.html(`<pre style="white-space:pre-wrap;font-size:11.5px;background:#f8fafc;border:1px solid #e5e7eb;border-radius:6px;padding:8px;margin:0">${esc((r.message || {}).prompt || "")}</pre>
					<div class="text-muted small" style="margin-top:4px">${__("En anglais : c'est la langue que le modèle d'image suit le mieux.")}</div>`);
			} catch (e) { /* aperçu facultatif */ }
		}, 400);
		// Écoute au niveau du dialogue : un champ masqué (pas de variante choisie, pas de logo) n'a pas d'$input,
		// et s'y accrocher directement plantait l'ouverture (« Cannot read properties of undefined (reading 'on') »).
		dlg.$wrapper.on("input change", "input, select, textarea", apercu);
		dlg.$wrapper.on("change", '[data-fieldname="nombre"] select', libelle_bouton);
		dlg.show();
		libelle_bouton();      // après show : les valeurs par défaut sont alors en place
		apercu();
	}

	// Les propositions côte à côte avec le fond actuel : « Utiliser » pose le fond et recompose le plan ;
	// « Utiliser puis retoucher » pose le fond et rouvre l'atelier en mode retouche, consigne gardée.
	comparer_fonds(m, reglages) {
		const esc = this._esc, candidats = m.candidats || [];
		const carte = (src, titre, url) => `<div style="flex:1 1 220px;text-align:center;min-width:0"><div class="small text-muted">${titre}</div>
			<a href="#" data-voir-fond="${esc(src || "")}"><img src="${esc(src || "")}" style="width:100%;max-height:260px;object-fit:contain;background:#f1f5f9;border:1px solid #e5e7eb;border-radius:8px"></a>
			${url ? `<div class="se-btns" style="justify-content:center;margin-top:6px">
				<button class="btn btn-xs btn-primary" data-utiliser-fond="${esc(url)}">${__("Utiliser ce fond")}</button>
				<button class="btn btn-xs btn-default" data-utiliser-fond="${esc(url)}" data-puis-retoucher="1">${__("Utiliser puis retoucher")}</button></div>` : ""}</div>`;
		const cmp = new frappe.ui.Dialog({ title: __("Propositions de fond"), size: "extra-large",
			fields: [{ fieldtype: "HTML", fieldname: "galerie" }],
			secondary_action_label: __("Réessayer"), secondary_action: () => { cmp.hide(); this.atelier_fond(reglages); } });
		cmp.fields_dict.galerie.$wrapper.html(`<div style="display:flex;gap:14px;flex-wrap:wrap;align-items:flex-start">
				${m.actuel ? carte(m.actuel, __("Actuel"), null) : ""}${candidats.map((u, k) => carte(u, __("Proposition {0}", [k + 1]), u)).join("")}</div>
			<p class="small text-muted" style="margin-top:8px">${__("Cliquez une image pour l'ouvrir en grand (pipette comprise). Rien ne change tant que vous n'avez pas cliqué « Utiliser ce fond » ; les propositions restent dans la médiathèque.")}</p>`);
		cmp.fields_dict.galerie.$wrapper.find("[data-voir-fond]").on("click", (e) => { e.preventDefault(); this.visionneuse($(e.currentTarget).attr("data-voir-fond"), __("Fond")); });
		cmp.fields_dict.galerie.$wrapper.find("[data-utiliser-fond]").on("click", async (e) => {
			const $b = $(e.currentTarget), url = $b.attr("data-utiliser-fond"), retoucher = $b.attr("data-puis-retoucher");
			let r;
			try {
				r = await frappe.call({ method: "aquaworld_ia.emballage.studio.adopter_fond", args: { design: this.nom, url, continu: m.continu },
					freeze: true, freeze_message: __("Fond appliqué, recomposition du plan…") });
			} catch (e2) { frappe.msgprint(this._msg(e2)); return; }
			cmp.hide();
			this.data = Object.assign({}, this.data, r.message); this.d = this.data.doc; this._lire_mep();
			this.onglet = r.message.recompose ? "artwork" : this.onglet; this.rendre();
			frappe.show_alert({ message: r.message.recompose ? __("Fond appliqué, plan recomposé.") : __("Fond appliqué : composez le plan (étape 4)."), indicator: "green" });
			if (retoucher) this.atelier_fond(Object.assign({}, reglages, { mode: "retouche", consigne: "" }));
		});
		cmp.show();
	}

	// ─── palette du design (champ « Palette (hex) ») et pipette ─────────────────
	_palette(valeur) {
		const vus = new Set();
		return String(valeur === undefined ? (this.d.palette || "") : valeur).split(/[\s,;]+/)
			.map(c => this.normaliser_couleur(c)).filter(c => c && !vus.has(c) && vus.add(c));
	}

	_pastilles_palette(valeur) {
		const esc = this._esc, cs = this._palette(valeur);
		return cs.length ? cs.map((c) => `<span class="se-pastille" style="background:${esc(c)}" title="${esc(c)} — ${__("cliquer pour la retirer")}" data-retirer="${esc(c)}"></span>`).join("")
			: `<span class="text-muted small">${__("Ajoutez des couleurs à la pipette : cliquez la photo, le logo ou le fond.")}</span>`;
	}

	// Rapport de contraste WCAG avec le blanc (comme codes.contraste_sur_blanc côté serveur).
	_contraste_blanc(hex) {
		const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || "").trim());
		if (!m) return 1;
		const lin = [0, 2, 4].map((i) => { const v = parseInt(m[1].slice(i, i + 2), 16) / 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
		return 1.05 / (0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2] + 0.05);
	}

	_pastilles_cible(cible) {
		const esc = this._esc;
		return this._palette().map((c) => `<span class="se-pastille petite" style="background:${esc(c)}" title="${esc(c)}" data-pastille-cible="${cible}" data-couleur="${esc(c)}"></span>`).join("");
	}

	ajouter_a_la_palette(couleur, design = this.nom) {
		return this.changer_palette(couleur, false, design);
	}

	// Une image en grand (photo, logo, fond…) : un clic dessus prend la couleur du point (pipette).
	visionneuse(url, titre, options = {}) {
		if (!url && !options.on_choisir) return;
		const esc = this._esc, design = this.nom, sources = options.sources || [];
		const damier = "background:repeating-conic-gradient(#e5e7eb 0% 25%, #fff 0% 50%) 50% / 16px 16px";
		const hex = (r, g, b) => "#" + [r, g, b].map((v) => v.toString(16).padStart(2, "0")).join("");
		let choisie = null, pret = false, chargement = 0;
		const dlg = new frappe.ui.Dialog({ title: titre || __("Image"), size: "extra-large", fields: [{ fieldtype: "HTML", fieldname: "corps" }] });
		const $c = dlg.fields_dict.corps.$wrapper;
		$c.html(`<div style="display:flex;gap:14px;flex-wrap:wrap;align-items:flex-start">
			<div style="flex:1 1 480px;min-width:0;text-align:center">
				${sources.length ? `<label class="small">${__("Image pour la pipette")}</label><select class="form-control" data-role="source-pipette" style="margin-bottom:10px">${sources.map(s => `<option value="${esc(s.url)}" ${s.url === url ? "selected" : ""}>${esc(s.libelle)}</option>`).join("")}</select>` : ""}
				<canvas data-role="toile" style="max-width:100%;max-height:62vh;cursor:crosshair;${damier};border:1px solid #e5e7eb;border-radius:8px"></canvas>
				<p class="small text-muted" data-role="etat-pipette"></p>
				<div class="text-muted small" style="margin-top:4px">${__("Cliquez sur l'image pour prendre la couleur de ce point.")} <a data-role="fichier-pipette" href="${esc(url)}" target="_blank" ${url ? "" : "hidden"}>↗ ${__("ouvrir le fichier")}</a></div>
			</div>
			<div style="flex:0 1 250px;min-width:220px">
				<div class="small text-muted">${__("Survol")}</div>
				<div style="display:flex;gap:8px;align-items:center;margin-bottom:10px"><span data-role="survol" class="se-pastille" style="width:28px;height:28px;cursor:default"></span><code data-role="survol-hex">—</code></div>
				<div class="small text-muted">${__("Couleur prise")}</div>
				<div style="display:flex;gap:8px;align-items:center"><span data-role="prise" class="se-pastille" style="width:44px;height:44px;cursor:default"></span><code data-role="prise-hex" style="font-size:15px">—</code></div>
				<label class="small" style="margin-top:10px">${__("Choisir ou saisir un code HEX")}</label>
				<div style="display:flex;gap:6px"><input type="color" value="#008bcd" data-role="couleur-pipette" aria-label="${__("Choisir une couleur")}" style="width:44px;height:32px;padding:2px;flex-shrink:0">
					<input type="text" class="form-control" data-role="hex-pipette" aria-label="${__("Code HEX")}" placeholder="#008bcd" style="min-width:0"></div>
				<div class="small text-muted" style="margin-top:10px">${__("Palette du design")}</div>
				<div class="se-palette">${this._palette().map(c => `<button type="button" class="se-pastille" data-palette-couleur="${c}" style="background:${c};padding:0" title="${c}" aria-label="${c}"></button>`).join("") || "—"}</div>
				<div class="se-btns" style="margin-top:10px;flex-direction:column;align-items:stretch" data-role="actions">
					${options.on_choisir ? `<button class="btn btn-sm btn-primary" data-geste="choisir" disabled>${esc(options.label_action || __("Utiliser cette couleur"))}</button>` : `<button class="btn btn-sm btn-primary" data-geste="palette" disabled>＋ ${__("Ajouter à la palette du design")}</button>
					<button class="btn btn-sm btn-default" data-geste="fond" disabled>${__("Utiliser comme couleur de fond")}</button>
					<button class="btn btn-sm btn-default" data-geste="logo" disabled>🎨 ${__("Colorer le logo avec")}</button>`}
					<button class="btn btn-sm btn-default" data-geste="copier" disabled>📋 ${__("Copier le code")}</button>
					${window.EyeDropper ? `<button class="btn btn-sm btn-default" data-geste="ecran" title="${__("Prendre une couleur n'importe où à l'écran")}">💧 ${__("Pipette sur tout l'écran")}</button>` : ""}
				</div>
				<div class="small text-muted" style="margin-top:12px">${__("Couleurs principales de l'image")}</div>
				<div data-role="dominantes" style="display:flex;gap:6px;flex-wrap:wrap;margin-top:4px"></div>
			</div></div>`);
		const toile = $c.find('[data-role="toile"]')[0], ctx = toile.getContext("2d", { willReadFrequently: true });
		const choisir = (c) => {
			c = this.normaliser_couleur(c); choisie = c;
			$c.find('[data-geste]:not([data-geste="ecran"])').prop("disabled", !c);
			if (!c) { $c.find('[data-role="prise-hex"]').text("—"); return; }
			$c.find('[data-role="prise"]').css("background", c);
			$c.find('[data-role="prise-hex"]').text(c);
			$c.find('[data-role="hex-pipette"], [data-role="couleur-pipette"]').val(c);
		};
		const lire = (e, rayon) => {
			if (!pret) return null;
			const r = toile.getBoundingClientRect();
			if (!r.width || !r.height) return null;
			const x = Math.floor((e.clientX - r.left) * toile.width / r.width), y = Math.floor((e.clientY - r.top) * toile.height / r.height);
			const x0 = Math.min(toile.width - 1, Math.max(0, x - rayon)), y0 = Math.min(toile.height - 1, Math.max(0, y - rayon));
			const d = ctx.getImageData(x0, y0, Math.min(toile.width - x0, 2 * rayon + 1), Math.min(toile.height - y0, 2 * rayon + 1)).data;
			let n = 0, s = [0, 0, 0];
			for (let i = 0; i < d.length; i += 4) if (d[i + 3] > 20) { s[0] += d[i]; s[1] += d[i + 1]; s[2] += d[i + 2]; n++; }
			return n ? hex(...s.map((v) => Math.round(v / n))) : null;      // moyenne 3×3 : un pixel isolé ne trompe pas
		};
		const charger = source => {
			url = source; pret = false; const numero = ++chargement;
			toile.width = toile.height = 1;
			$c.find('[data-role="dominantes"]').empty();
			$c.find('[data-role="fichier-pipette"]').attr("href", url).prop("hidden", !url);
			$c.find('[data-role="etat-pipette"]').text(url ? __("Chargement…") : __("Aucune image disponible. Choisissez une couleur ou saisissez son code HEX."));
			if (!url) return;
			const img = new Image();
			img.onload = () => {
				if (numero !== chargement) return;
				try {
					const k = Math.min(1, 1400 / Math.max(img.naturalWidth || 1, img.naturalHeight || 1));
					toile.width = Math.max(1, Math.round((img.naturalWidth || 800) * k));
					toile.height = Math.max(1, Math.round((img.naturalHeight || 600) * k));
					ctx.drawImage(img, 0, 0, toile.width, toile.height);
					// Couleurs principales : histogramme grossier (5 bits par canal) des pixels visibles, blanc exclu.
					const d = ctx.getImageData(0, 0, toile.width, toile.height).data, comptes = new Map(), pas = Math.max(1, Math.floor(d.length / 4 / 60000));
					for (let i = 0; i < d.length; i += 4 * pas) {
						if (d[i + 3] < 128 || Math.min(d[i], d[i + 1], d[i + 2]) > 235) continue;
						const cle = (d[i] >> 3) << 10 | (d[i + 1] >> 3) << 5 | (d[i + 2] >> 3), c = comptes.get(cle) || [0, 0, 0, 0];
						c[0]++; c[1] += d[i]; c[2] += d[i + 1]; c[3] += d[i + 2]; comptes.set(cle, c);
					}
					const top = [...comptes.values()].sort((a, b) => b[0] - a[0]).slice(0, 8).map((c) => hex(Math.round(c[1] / c[0]), Math.round(c[2] / c[0]), Math.round(c[3] / c[0])));
					$c.find('[data-role="dominantes"]').html(top.map((c) => `<span class="se-pastille" style="background:${c}" title="${c}" data-dominante="${c}"></span>`).join("") || `<span class="text-muted small">—</span>`);
					$c.find("[data-dominante]").on("click", (e) => choisir($(e.currentTarget).attr("data-dominante")));
					pret = true; $c.find('[data-role="etat-pipette"]').empty();
				} catch (e) { $c.find('[data-role="etat-pipette"]').text(__("Cette image ne permet pas la pipette. Choisissez une autre image ou saisissez le code HEX.")); }
			};
			img.onerror = () => { if (numero === chargement) $c.find('[data-role="etat-pipette"]').text(__("Image illisible. Choisissez une autre image ou saisissez le code HEX.")); };
			img.src = url;
		};
		$c.find('[data-role="source-pipette"]').on("change", e => charger(e.currentTarget.value));
		$c.find('[data-role="hex-pipette"]').on("change", e => choisir(e.currentTarget.value));
		$c.find('[data-role="couleur-pipette"]').on("input change", e => choisir(e.currentTarget.value));
		$c.find('[data-palette-couleur]').on("click", e => choisir($(e.currentTarget).attr("data-palette-couleur")));
		$c.find('[data-geste="choisir"]').on("click", async e => {
			if (!choisie) return;
			const $b = $(e.currentTarget).prop("disabled", true);
			try { await options.on_choisir(choisie); dlg.hide(); }
			catch (erreur) { frappe.msgprint(this._msg(erreur)); }
			finally { $b.prop("disabled", false); }
		});
		$(toile).on("mousemove", (e) => { const c = lire(e, 0); if (c) { $c.find('[data-role="survol"]').css("background", c); $c.find('[data-role="survol-hex"]').text(c); } });
		$(toile).on("click", (e) => { const c = lire(e, 1); if (c) choisir(c); });
		$c.find('[data-geste="palette"]').on("click", () => choisie && this.ajouter_a_la_palette(choisie, design).catch(e => frappe.msgprint(this._msg(e))));
		$c.find('[data-geste="fond"]').on("click", () => { if (!choisie || this.nom !== design) return; this.modifier({ couleur_fond: choisie }, true, design); frappe.show_alert({ message: __("Couleur de fond : {0}. Recomposez le plan (étape 4).", [choisie]), indicator: "green" }); });
		$c.find('[data-geste="logo"]').on("click", () => { if (!choisie || this.nom !== design) return; dlg.hide(); this.atelier_couleur(choisie); });
		$c.find('[data-geste="copier"]').on("click", () => choisie && frappe.utils.copy_to_clipboard(choisie));
		$c.find('[data-geste="ecran"]').on("click", async () => {
			try { const r = await new window.EyeDropper().open(); if (r && r.sRGBHex) choisir(r.sRGBHex.toLowerCase()); } catch (e) { /* annulé */ }
		});
		dlg.show();
		charger(url);
		return dlg;
	}

	// Un candidat reste séparé de la source jusqu’à l’adoption explicite.
	async atelier_vectorisation(champ, source_url = null, design = this.nom, options = {}) {
		try { await this.attendre_sauvegardes(); }
		catch (e) { frappe.msgprint(this._msg(e)); return; }
		if (this.nom !== design) { frappe.msgprint(__("Rouvrez le design concerné pour vectoriser cette proposition.")); return; }
		const esc = this._esc, sources = new Map();
		if (!this.data.peut_ecrire) return;
		const ajouter_source = (url, label) => {
			if (url && /\.(png|jpe?g|webp)(?:[?#]|$)/i.test(url) && !sources.has(url)) sources.set(url, { value: url, label });
		};
		ajouter_source(source_url, __("Image sélectionnée"));
		ajouter_source(this.d[champ], __("Image actuelle du design"));
		(this.data.images || []).forEach((im) => ajouter_source(im.file_url, `${im.genre} — ${im.file_name}`));
		if (!sources.size) { frappe.msgprint(__("Choisissez une image PNG, JPEG ou WebP dans la médiathèque.")); return; }
		const profils = [
			{ value: "logo", label: __("Logo — aplats et petits détails") },
			{ value: "illustration", label: __("Illustration — formes simplifiées") },
			{ value: "photo", label: __("Photo — davantage de nuances") },
		];
		const dlg = new frappe.ui.Dialog({ title: __("Vectoriser en SVG couleur"), size: "large",
			fields: [
				{ fieldtype: "HTML", fieldname: "aide", options: `<p class="text-muted">${__("Crée des courbes SVG à partir d’un PNG, JPEG ou WebP, sans coût IA. Une photo devient une illustration : les reflets et les détails fins peuvent être simplifiés. L’original reste disponible.")}</p>` },
				{ fieldtype: "Select", fieldname: "source_url", label: __("Image à vectoriser"), options: [...sources.values()],
					default: source_url || this.d[champ] || sources.keys().next().value, reqd: 1,
					onchange: () => dlg.fields_dict.resultat.$wrapper.empty() },
				{ fieldtype: "Select", fieldname: "profil", label: __("Type de visuel"), options: profils,
					default: champ === "logo" ? "logo" : "photo", reqd: 1,
					onchange: () => dlg.set_value("couleurs", { logo: "16", illustration: "32", photo: "64" }[dlg.get_value("profil")]) },
				{ fieldtype: "Select", fieldname: "couleurs", label: __("Nombre maximal de couleurs"),
					options: ["8", "16", "32", "64", "128"].join("\n"), default: champ === "logo" ? "16" : "64", reqd: 1,
					description: __("Moins de couleurs : SVG plus léger. Plus de couleurs : davantage de nuances.") },
				{ fieldtype: "Check", fieldname: "retirer_fond", label: __("Retirer le fond blanc"), default: 0,
					description: __("À activer pour un fond blanc uni. Contrôlez les parties blanches du produit dans l’aperçu.") },
				{ fieldtype: "HTML", fieldname: "resultat" },
			],
			primary_action_label: __("Créer le SVG"),
			secondary_action_label: __("Préparer par IA…"),
			secondary_action: () => {
				const source = dlg.get_value("source_url");
				if (!source) return;
				dlg.hide(); this.atelier_image(champ, { ...options, source_url: source, design, pour_svg: true });
			},
			primary_action: async (v) => {
				const $bouton = dlg.get_primary_btn();
				$bouton.prop("disabled", true);
				try {
					const r = await frappe.call({ method: "aquaworld_ia.emballage.studio.vectoriser_image",
						args: { design, champ, source_url: v.source_url, profil: v.profil, couleurs: Number(v.couleurs), retirer_fond: v.retirer_fond ? 1 : 0 },
						freeze: true, freeze_message: __("Tracé des courbes SVG…") });
					const c = r.message;
					if (this.nom === design) { this.data.images = c.images; this.rendre_scene(); }
					const carte = (url, titre) => `<div style="flex:1 1 220px;min-width:0;text-align:center"><p>${titre}</p>
						<a href="${esc(url)}" target="_blank" rel="noopener"><img src="${esc(url)}" alt="${titre}"
						style="width:100%;height:260px;object-fit:contain;background:repeating-conic-gradient(#e5e7eb 0% 25%, #fff 0% 50%) 50% / 16px 16px"></a></div>`;
					const $resultat = dlg.fields_dict.resultat.$wrapper;
					$resultat.html(`<div style="display:flex;gap:14px;flex-wrap:wrap">${carte(c.source, __("Source à vectoriser"))}${carte(c.candidat, __("SVG vectorisé"))}</div>
						<p class="small text-muted">${__("{0} couleurs · {1} tracés · {2} Ko", [c.couleurs, c.chemins, c.taille_ko])}</p>
						${(c.avertissements || []).map((a) => `<p class="small text-muted">${esc(a)}</p>`).join("")}
						<div class="se-btns"><button class="btn btn-primary btn-sm" data-adopter-svg>${options.cible_zone ? __("Utiliser ce SVG pour ce logo") : __("Utiliser ce SVG")}</button>
						<a class="btn btn-default btn-sm" href="${esc(c.candidat)}" download target="_blank" rel="noopener">${__("Télécharger le SVG")}</a></div>
						<p class="small text-muted">${__("Cliquez sur une image pour vérifier les détails en grand. Le résultat reste aussi dans la médiathèque.")}</p>`);
					$resultat.find("[data-adopter-svg]").on("click", async (e) => {
						const $adopter = $(e.currentTarget).prop("disabled", true);
						try {
							await this.adopter_proposition_image(design, champ, c.candidat, options);
							dlg.hide();
							frappe.show_alert({ message: __("SVG adopté. Recomposez le plan à l’étape 4 pour actualiser le PDF."), indicator: "green" });
						} catch (e) { frappe.msgprint(this._msg(e)); }
						finally { $adopter.prop("disabled", false); }
					});
				} catch (e) { frappe.msgprint(this._msg(e)); }
				finally { $bouton.prop("disabled", false); }
			},
		});
		dlg.show();
	}

	// Le logo en UNE couleur choisie (demande utilisateur 06/10/2026) : palette du design, couleur exacte,
	// sans IA ; sortie SVG (vectoriel : courbes gardées ; image : redessinée en courbes) ou PNG.
	async atelier_couleur(couleur_depart) {
		const esc = this._esc;
		let r;
		try {
			r = await frappe.call({ method: "aquaworld_ia.emballage.studio.palette_logo", args: { design: this.nom }, freeze: true });
		} catch (e) { frappe.msgprint(this._msg(e)); return; }
		const m = r.message || {}, pal = m.palette || [];
		const ORIGINES = { "palette": __("Palette du design"), "photo produit": __("Photo du produit"), logo: __("Couleurs du logo"), fond: __("Fond du design"), zones: __("Zones (cartouches, textes)"), "image de fond": __("Image de fond"), noir: __("Neutres"), blanc: __("Neutres") };
		const groupes = {};
		pal.forEach((p) => { const g = ORIGINES[p.origine] || p.origine; (groupes[g] = groupes[g] || []).push(p.couleur); });
		const depart = couleur_depart || (pal.find((p) => p.origine === "logo") || pal[0] || {}).couleur || "#1d4ed8";
		const damier = "background:repeating-conic-gradient(#e5e7eb 0% 25%, #fff 0% 50%) 50% / 16px 16px";
		const dlg = new frappe.ui.Dialog({ title: __("Logo d'une seule couleur — SVG ou PNG"), size: "large",
			fields: [
				{ fieldtype: "HTML", fieldname: "palette" },
				{ fieldtype: "Data", fieldname: "hex", label: __("Couleur choisie (#RRGGBB)"), default: depart, reqd: 1 },
				{ fieldtype: "Check", fieldname: "garder_blanc", label: __("Garder le blanc du logo (évidements, lettres blanches)"), default: 1 },
				{ fieldtype: "Select", fieldname: "sortie", label: __("Format du résultat"), default: "SVG (vectoriel)", options: ["SVG (vectoriel)", "PNG"].join("\n"),
				  description: m.vectoriel ? __("Votre logo est vectoriel : ses courbes sont gardées telles quelles, seules les couleurs changent.")
				    : __("Votre logo est une image : il est recoloré, puis redessiné en courbes pour le SVG. Vérifiez les petits détails.") },
				{ fieldtype: "HTML", fieldname: "resultat" },
			],
			primary_action_label: __("Appliquer la couleur"),
			primary_action: async (v) => {
				let res;
				try {
					res = await frappe.call({ method: "aquaworld_ia.emballage.studio.logo_couleur", freeze: true, freeze_message: __("Recoloration du logo…"),
						args: { design: this.nom, couleur: v.hex, garder_blanc: v.garder_blanc ? 1 : 0, sortie: (v.sortie || "").startsWith("PNG") ? "png" : "svg" } });
				} catch (e) { frappe.msgprint(this._msg(e)); return; }
				const c = res.message || {};
				const carte = (src, titre) => `<div style="flex:1 1 220px;text-align:center;min-width:0"><div class="text-muted small">${titre}</div>
					<img src="${esc(src)}" style="max-width:100%;max-height:180px;${damier};border:1px solid #e5e7eb;border-radius:6px;padding:6px"></div>`;
				dlg.fields_dict.resultat.$wrapper.html(`<div style="display:flex;gap:14px;flex-wrap:wrap;margin-top:6px">
						${carte(c.source, __("Actuel"))}${carte(c.candidat, __("Résultat — {0} · {1} Ko", [String(c.format || "").toUpperCase(), c.taille_ko]))}</div>
					<div class="se-btns" style="margin-top:10px;justify-content:center">
						<button class="btn btn-sm btn-primary" data-role="adopter-couleur">✅ ${__("Utiliser comme logo")}</button>
						<a class="btn btn-sm btn-default" href="${esc(c.candidat)}" download target="_blank">⬇ ${__("Télécharger")}</a>
						<button class="btn btn-sm btn-default" data-role="garder-couleur">💾 ${__("Garder en bibliothèque")}</button></div>
					<p class="text-muted small" style="margin-top:6px;text-align:center">${__("Rien ne change tant que vous n'avez pas cliqué « Utiliser comme logo ». Le fichier reste aussi dans la médiathèque.")}</p>`);
				dlg.fields_dict.resultat.$wrapper.find('[data-role="adopter-couleur"]').on("click", async () => {
					const r2 = await frappe.call({ method: "aquaworld_ia.emballage.studio.adopter_image", args: { design: this.nom, champ: "logo", url: c.candidat }, freeze: true });
					dlg.hide(); this.data = Object.assign({}, this.data, r2.message); this.d = this.data.doc; this._lire_mep(); this.rendre();
					frappe.show_alert({ message: __("Logo remplacé : recomposez le plan (étape 4)."), indicator: "green" });
				});
				dlg.fields_dict.resultat.$wrapper.find('[data-role="garder-couleur"]').on("click", () => this.garder("logo", c.candidat));
			} });
		const rendre_palette = () => {
			const choisie = (dlg.get_value("hex") || "").toLowerCase();
			dlg.fields_dict.palette.$wrapper.html(`
				<div style="display:flex;gap:10px;align-items:center;margin-bottom:8px"><img src="${esc(m.source)}" style="max-height:60px;max-width:200px;${damier};border:1px solid #e5e7eb;border-radius:6px;padding:4px">
					<span class="text-muted small">${__("Choisissez une couleur : tout le logo la prend, au code près. Sans IA, gratuit.")}</span></div>
				${Object.entries(groupes).map(([g, cs]) => `<div style="margin:4px 0"><div class="small text-muted">${esc(g)}</div>
					<div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:2px">${cs.map((c) => `<button type="button" class="se-pastille-couleur" data-couleur="${esc(c)}" title="${esc(c)}"
						style="width:30px;height:30px;border-radius:50%;background:${esc(c)};cursor:pointer;border:${c === choisie ? "3px solid #111827" : "1px solid #d1d5db"};box-shadow:${c === choisie ? "0 0 0 2px #fff inset" : "none"}"></button>`).join("")}</div></div>`).join("")}
				<div style="display:flex;gap:8px;align-items:center;margin-top:8px"><span class="small text-muted">${__("Autre couleur :")}</span>
					<input type="color" data-role="libre" value="${esc(/^#[0-9a-f]{6}$/.test(choisie) ? choisie : "#1d4ed8")}" style="width:44px;height:28px;padding:1px"></div>`);
			dlg.fields_dict.palette.$wrapper.find("[data-couleur]").on("click", (e) => { dlg.set_value("hex", $(e.currentTarget).attr("data-couleur")); });
			dlg.fields_dict.palette.$wrapper.find('[data-role="libre"]').on("change", (e) => { dlg.set_value("hex", e.currentTarget.value); });
		};
		dlg.fields_dict.hex.$input.on("change input", frappe.utils.debounce(rendre_palette, 150));
		rendre_palette();
		dlg.show();
	}

	// Un tampon SVG dessiné par l'IA (demande utilisateur 06/10/2026 : « un tampon comme le poids ») : le texte,
	// la forme, le style, les couleurs de la palette ; plusieurs propositions vectorielles, on en adopte une, qui
	// devient un pictogramme (catégorie Tampon) coché sur le design.
	atelier_tampon(precedent) {
		const esc = this._esc, palette = this._palette();
		const choisies = new Set((precedent && precedent.couleurs) || (palette.length ? [palette[palette.length - 1]] : ["#1e3a8a"]));
		const damier = "background:repeating-conic-gradient(#e5e7eb 0% 25%, #fff 0% 50%) 50% / 16px 16px";
		const dlg = new frappe.ui.Dialog({ title: __("Tampon dessiné par l'IA (SVG)"),
			fields: [
				{ fieldtype: "Small Text", fieldname: "texte", label: __("Texte du tampon"), reqd: 1, default: (precedent && precedent.texte) || "",
				  description: __("Une idée par ligne, ex. « POIDS NET » puis « 25 KG ». Les mots sont respectés à la lettre.") },
				{ fieldtype: "Select", fieldname: "forme", label: __("Forme"), default: (precedent && precedent.forme) || "",
				  options: [["", __("Au choix de l'IA (variée)")], ["rond", __("Rond")], ["sceau", __("Sceau dentelé")], ["ecusson", __("Écusson")], ["ruban", __("Ruban")], ["rectangle", __("Rectangle arrondi")]].map(([v, l]) => ({ value: v, label: l })) },
				{ fieldtype: "Select", fieldname: "style", label: __("Style"), default: (precedent && precedent.style) || "",
				  options: [["", __("Au choix")], ["plein", __("Plein (fond coloré, texte blanc)")], ["contour", __("Contour (encre seule, fond transparent)")]].map(([v, l]) => ({ value: v, label: l })) },
				{ fieldtype: "HTML", fieldname: "couleurs" },
				{ fieldtype: "Data", fieldname: "idee", label: __("Ambiance (facultatif)"), default: (precedent && precedent.idee) || "", description: __("ex. artisanal, premium, écologique, technique") },
				{ fieldtype: "Select", fieldname: "nombre", label: __("Propositions"), default: "3", options: "1\n2\n3\n4",
				  description: __("Quelques centimes pour l'ensemble : l'IA écrit le SVG, elle ne dessine pas d'image.") },
			],
			primary_action_label: __("Générer"),
			primary_action: async (v) => {
				const args = { design: this.nom, texte: v.texte, forme: v.forme || "", style: v.style || "", couleurs: JSON.stringify([...choisies]), idee: v.idee || "", nombre: v.nombre };
				let r;
				try {
					r = await frappe.call({ method: "aquaworld_ia.emballage.studio.creer_tampons", args, freeze: true, freeze_message: __("L'IA dessine les tampons…") });
				} catch (e) { frappe.msgprint(this._msg(e)); return; }
				dlg.hide();
				const tampons = (r.message || {}).tampons || [];
				const res = new frappe.ui.Dialog({ title: __("Propositions de tampon"), size: "large",
					fields: [{ fieldtype: "HTML", fieldname: "galerie" }],
					secondary_action_label: __("Réessayer"),
					secondary_action: () => { res.hide(); this.atelier_tampon(Object.assign({}, v, { couleurs: [...choisies] })); } });
				res.fields_dict.galerie.$wrapper.html(`<div style="display:flex;gap:14px;flex-wrap:wrap">${tampons.map((t) => `
					<div style="flex:1 1 200px;text-align:center;min-width:0">
						<img src="${esc(t.url)}" style="width:100%;max-height:200px;object-fit:contain;${damier};border:1px solid #e5e7eb;border-radius:8px;padding:6px">
						<div class="small text-muted" style="margin:4px 0">${esc(t.titre)}</div>
						<button class="btn btn-xs btn-primary" data-utiliser="${esc(t.url)}">${__("Utiliser")}</button>
						<a class="btn btn-xs btn-default" href="${esc(t.url)}" download target="_blank">⬇ SVG</a>
					</div>`).join("")}</div>
					<p class="small text-muted" style="margin-top:8px">${__("Relisez le texte de chaque proposition. Le tampon adopté devient un pictogramme (catégorie Tampon), réutilisable sur tous les designs.")}</p>`);
				res.fields_dict.galerie.$wrapper.find("[data-utiliser]").on("click", (e) => {
					const url = $(e.currentTarget).attr("data-utiliser");
					frappe.prompt([
						{ fieldtype: "Data", fieldname: "libelle", label: __("Nom du tampon"), reqd: 1, default: (v.texte || "").split("\n").map((x) => x.trim()).filter(Boolean).join(" ") },
						{ fieldtype: "Float", fieldname: "taille_mm", label: __("Taille sur l'emballage (mm)"), default: 25 },
					], async (p) => {
						try {
							const r2 = await frappe.call({ method: "aquaworld_ia.emballage.studio.adopter_tampon", args: { design: this.nom, url, libelle: p.libelle, taille_mm: p.taille_mm }, freeze: true });
							res.hide(); this.data = Object.assign({}, this.data, r2.message); this.d = this.data.doc; this._lire_mep(); this.rendre();
							this.proposer_placement(r2.message.tampon, p.libelle);
						} catch (e2) { frappe.msgprint(this._msg(e2)); }
					}, __("Adopter ce tampon"), __("Adopter"));
				});
				res.show();
			} });
		const rendre_couleurs = () => {
			const autres = ["#1e3a8a", "#15803d", "#b91c1c", "#000000"].filter((c) => !palette.includes(c));
			dlg.fields_dict.couleurs.$wrapper.html(`<label class="control-label" style="margin-top:4px">${__("Couleurs (1 à 3)")}</label>
				<div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">${palette.concat(autres).map((c) => `<span class="se-pastille" data-couleur-tampon="${esc(c)}" title="${esc(c)}" style="background:${esc(c)};${choisies.has(c) ? "box-shadow:0 0 0 2px #fff,0 0 0 4px #111827" : ""}"></span>`).join("")}
					<input type="color" data-role="autre-tampon" value="#1e3a8a" title="${__("Autre couleur")}" style="width:34px;height:26px;padding:1px"></div>
				<div class="small text-muted" style="margin-top:3px">${palette.length ? __("Les premières viennent de la palette du design.") : __("Astuce : prenez les couleurs de la photo ou du logo à la pipette (cliquez leur vignette).")}</div>`);
			dlg.fields_dict.couleurs.$wrapper.find("[data-couleur-tampon]").on("click", (e) => {
				const c = $(e.currentTarget).attr("data-couleur-tampon");
				if (choisies.has(c)) choisies.delete(c); else if (choisies.size < 3) choisies.add(c);
				rendre_couleurs();
			});
			dlg.fields_dict.couleurs.$wrapper.find('[data-role="autre-tampon"]').on("change", (e) => { if (choisies.size < 3) choisies.add(e.currentTarget.value.toLowerCase()); palette.push(e.currentTarget.value.toLowerCase()); rendre_couleurs(); });
		};
		rendre_couleurs();
		dlg.show();
	}

	proposer_placement(code, libelle) {
		const faces = ((this.data.apercu || {}).faces || []).map((x) => ({ value: x.code, label: x.libelle }));
		if (!faces.length) return frappe.show_alert({ message: __("Tampon ajouté aux pictogrammes du design."), indicator: "green" });
		frappe.prompt([{ fieldtype: "Select", fieldname: "face", label: __("Sur quelle face le poser ?"), options: faces, default: this.epinglee || "avant",
			description: __("Il se pose en bas à droite, à sa taille ; vous le déplacez ensuite sur le plan. Il reste aussi dans « Ajouter » pour d'autres faces.") }],
			(v) => this.placer_tampon(code, v.face), __("« {0} » est prêt", [libelle || code]), __("Poser le tampon"));
	}

	ajouter_picto() {
		const dlg = new frappe.ui.Dialog({ title: __("Nouveau pictogramme ou certification"),
			fields: [
				{ fieldtype: "Data", fieldname: "libelle", label: __("Nom"), reqd: 1 },
				{ fieldtype: "Select", fieldname: "categorie", label: __("Catégorie"), default: "Certification",
				  options: ["Certification", "Qualité de l'eau", "Alimentaire", "Garantie", "Réglementaire", "Manutention", "Recyclage", "Sécurité", "Autre"].join("\n") },
				{ fieldtype: "Float", fieldname: "taille_mm", label: __("Taille sur l'emballage (mm)"), default: 12 },
				{ fieldtype: "Attach", fieldname: "image", label: __("Image (PNG, JPEG ou SVG)"), reqd: 1,
				  description: __("Un fond blanc uniforme devient transparent à l'impression.") },
			],
			primary_action_label: __("Ajouter et cocher"),
			primary_action: async (v) => {
				try {
					const r = await frappe.call({ method: "aquaworld_ia.emballage.studio.ajouter_pictogramme",
						args: { libelle: v.libelle, categorie: v.categorie, image: v.image, taille_mm: v.taille_mm } });
					dlg.hide();
					const codes = (this.d.pictogrammes || []).map((x) => x.pictogramme).concat([r.message.code]);
					this.data.pictos = (this.data.pictos || []).concat([Object.assign({ categorie: v.categorie }, r.message)]);
					await this.modifier({ pictogrammes: codes }, true);
				} catch (e) { frappe.msgprint(this._msg(e)); }
			} });
		dlg.show();
	}

	// ─── bibliothèque : fonds, motifs, variantes de logo, photos du produit ─────
	garder(champ, url) {
		const b = StudioEmballage.BIBLIO[champ], d = this.d;
		url = url || d[champ];
		const nom = { logo: (d.marque || "") + " ", photo_produit: d.nom_produit || d.article || "", image_fond: (d.brief_style || "").slice(0, 40) }[champ];
		const dlg = new frappe.ui.Dialog({ title: b.garder,
			fields: [
				{ fieldtype: "HTML", options: `<img src="${this._esc(url)}" style="max-height:120px;max-width:100%;background:#fff;border:1px solid #e5e7eb;border-radius:6px;padding:6px">` },
				{ fieldtype: "Data", fieldname: "nom", label: __("Nom"), reqd: 1, default: nom },
				{ fieldtype: "Select", fieldname: "categorie", label: __("Catégorie"), default: b.categories[0], options: b.categories.join("\n") },
				{ fieldtype: "Small Text", fieldname: "notes", label: __("Notes"), default: champ === "image_fond" ? [d.brief_style, d.palette].filter(Boolean).join(" · ") : "" },
				{ fieldtype: "HTML", options: `<p class="text-muted small">${__("Marque : {0}. La ressource garde son propre fichier : le design d'origine peut disparaître, elle reste.", [this._esc(this.d.marque || "—")])}</p>` },
			],
			primary_action_label: __("Garder"),
			primary_action: async (v) => {
				try {
					const r = await frappe.call({ method: "aquaworld_ia.emballage.studio.bibliotheque_enregistrer", args: { design: this.nom, champ, nom: v.nom, categorie: v.categorie, notes: v.notes, url } });
					dlg.hide(); frappe.show_alert({ message: __("Gardé en bibliothèque : {0}", [r.message.nom]), indicator: "green" });
				} catch (e) { frappe.msgprint(this._msg(e)); }
			} });
		dlg.show();
	}

	// Mosaïque de variantes (demande 14/10/2026 : « choisir plusieurs variantes du produit et créer une photo avec une
	// mosaïque des produits améliorés choisis », comme la planche TRANSPARENT / OPAQUE BLEU × MODÈLE A / B, « ou une
	// autre disposition »). Les cases viennent des photos du design, de la bibliothèque ou d'un téléversement, chacune
	// améliorable par IA ; l'aperçu se refait au fil des réglages (serveur, 900 px) ; rien ne change avant « Utiliser ».
	atelier_mosaique() {
		const esc = (v) => this._esc(v), d = this.d;
		let cfg = {};
		try { cfg = JSON.parse(d.mosaique || "{}") || {}; } catch (e) { cfg = {}; }
		const etat = { cases: (cfg.cases || []).map((c) => Object.assign({}, c)) };
		if (!etat.cases.length && d.photo_produit) etat.cases.push({ url: d.photo_produit, legende: "" });
		const POLICES = ["Poppins", "Montserrat", "Roboto", "OpenSans", "Lato", "NotoSans", "Oswald", "EBGaramond", "NotoSerif"];
		const AVEC_ENTETES = "eval:['grille','rangee','colonne'].includes(doc.disposition)";
		let dlg = null, jeton = 0;
		const lignes = (t) => String(t || "").split("\n").map((x) => x.trim());
		const config = () => {
			const v = dlg.get_values(true) || {};
			return { disposition: v.disposition, colonnes: cint(v.colonnes), espacement: v.espacement, cadre: v.cadre,
				alignement: v.alignement, ajustement: v.ajustement, titre: v.titre || "", pied: v.pied || "", entetes_colonnes: lignes(v.entetes_colonnes),
				entetes_lignes: lignes(v.entetes_lignes), fond: v.fond, detourer: !!v.detourer, couleur: v.couleur || "#1f3a8a",
				police: v.police || "Poppins", cases: etat.cases };
		};
		const apercu = frappe.utils.debounce(async () => {
			if (!dlg) return;
			const $a = dlg.get_field("apercu").$wrapper;
			if (!etat.cases.length) { $a.html(`<div class="se-vide">${__("Ajoutez des variantes du produit (au moins deux).")}</div>`); return; }
			const moi = ++jeton;
			$a.css("opacity", 0.55);
			try {
				const r = await frappe.call({ method: "aquaworld_ia.emballage.studio.mosaique_apercu", args: { design: this.nom, config: JSON.stringify(config()) } });
				if (moi !== jeton) return;
				const img = (r.message || {}).image;
				$a.html(img ? `<div style="text-align:center;background:repeating-conic-gradient(#e5e7eb 0% 25%, #fff 0% 50%) 50% / 16px 16px;border-radius:8px;padding:10px">
					<img src="${img}" style="max-width:100%;max-height:440px"></div>
					<p class="small text-muted" style="margin-top:6px">${__("Aperçu réduit ; la mosaïque finale fait 2 400 px de large. Le damier = transparent.")}</p>` : "");
			} catch (e) {
				if (moi === jeton) $a.html(`<div class="se-vide">${esc(this._msg(e))}</div>`);
			} finally {
				if (moi === jeton) $a.css("opacity", 1);
			}
		}, 450);
		const rendre_cases = () => {
			const $c = dlg.get_field("cases").$wrapper;
			$c.html(`<div style="font-weight:600;margin-bottom:6px">${__("Variantes ({0})", [etat.cases.length])}</div>
				${etat.cases.map((c, i) => `<div style="display:flex;gap:6px;align-items:center;margin-bottom:6px;border:1px solid #e5e7eb;border-radius:8px;padding:5px">
					<img src="${esc(c.url)}" alt="" style="width:54px;height:54px;object-fit:contain;background:#fff;border-radius:4px;${c.miroir ? "transform:scaleX(-1)" : ""}">
					<input class="form-control input-xs" data-legende="${i}" value="${esc(c.legende || "")}" placeholder="${__("Légende (facultative)")}" style="flex:1;min-width:60px">
					<input class="form-control input-xs" data-taille="${i}" type="number" min="50" max="130" step="5" value="${cint(c.taille) || 100}" style="width:58px;text-align:right" title="${__("Taille de cette variante (%) : à réduire ou agrandir si une pièce qui dépasse (support, clé) la fait paraître plus petite ou plus grande que les autres")}"><span class="small text-muted">%</span>
					<button class="btn btn-xs ${c.miroir ? "btn-primary" : "btn-default"}" data-miroir="${i}" title="${__("Miroir : retourner le produit (entrée à gauche ↔ à droite), sans IA")}">⇋</button>
					<button class="btn btn-xs btn-default" data-ia="${i}" title="${__("Améliorer cette photo par IA (plusieurs propositions)")}">✨</button>
					<button class="btn btn-xs btn-default" data-monter="${i}" ${i ? "" : "disabled"} title="${__("Monter")}">↑</button>
					<button class="btn btn-xs btn-default" data-descendre="${i}" ${i < etat.cases.length - 1 ? "" : "disabled"} title="${__("Descendre")}">↓</button>
					<button class="btn btn-xs btn-default" data-retirer="${i}" title="${__("Retirer")}">✕</button></div>`).join("")}
				<button class="btn btn-sm btn-default" data-role="ajouter">＋ ${__("Ajouter des variantes")}</button>
				${etat.cases.length >= 2 ? `<button class="btn btn-sm btn-default" data-role="orienter" title="${__("L'IA redessine chaque variante sous le même angle que la première (miroir compris). Vous choisissez ensuite, variante par variante.")}">🧭 ${__("Même orientation que la 1re (IA)")}</button>` : ""}
				<p class="small text-muted" style="margin-top:6px">${__("Grille : les cases se remplissent ligne par ligne, dans cet ordre. Héros : la première est la grande.")}</p>
				<div style="font-weight:600;margin:10px 0 6px">${__("Aperçu")}</div>`);
			$c.find("[data-legende]").on("change", (e) => { etat.cases[cint($(e.currentTarget).attr("data-legende"))].legende = e.currentTarget.value; apercu(); });
			$c.find("[data-retirer]").on("click", (e) => { etat.cases.splice(cint($(e.currentTarget).attr("data-retirer")), 1); rendre_cases(); apercu(); });
			$c.find("[data-taille]").on("change", (e) => {
				etat.cases[cint($(e.currentTarget).attr("data-taille"))].taille = Math.max(50, Math.min(130, cint(e.currentTarget.value) || 100));
				apercu();
			});
			const echanger = (i, j) => { const t = etat.cases[i]; etat.cases[i] = etat.cases[j]; etat.cases[j] = t; rendre_cases(); apercu(); };
			$c.find("[data-monter]").on("click", (e) => { const i = cint($(e.currentTarget).attr("data-monter")); echanger(i, i - 1); });
			$c.find("[data-descendre]").on("click", (e) => { const i = cint($(e.currentTarget).attr("data-descendre")); echanger(i, i + 1); });
			$c.find("[data-ia]").on("click", (e) => ameliorer(cint($(e.currentTarget).attr("data-ia"))));
			$c.find("[data-miroir]").on("click", (e) => { const c = etat.cases[cint($(e.currentTarget).attr("data-miroir"))]; c.miroir = !c.miroir; rendre_cases(); apercu(); });
			$c.find('[data-role="orienter"]').on("click", () => orienter());
			$c.find('[data-role="ajouter"]').on("click", () => ajouter());
		};
		const ajouter = async () => {
			const biblio = (await frappe.call({ method: "aquaworld_ia.emballage.studio.bibliotheque_liste", args: { champ: "photo_produit", marque: d.marque } })).message || [];
			// les photos du design (pas le logo ni le fond : un « Téléversé » peut être l'un ou l'autre)
			const photos = (this.data.images || []).filter((im) => /^(Photo|Téléversé)/.test(im.genre || "") && !/\.svg$/i.test(im.file_url || "")
				&& !["logo", "image_fond"].includes(im.usage) && im.file_url !== d.logo && im.file_url !== d.image_fond);
			const choix = new Set();
			const carte = (url, titre) => `<div class="se-carte" data-url="${esc(url)}" style="cursor:pointer">
				<img src="${esc(url)}" alt="" style="aspect-ratio:1/1;object-fit:contain;background:#fff"><div class="leg">${esc(titre)}</div></div>`;
			const pk = new frappe.ui.Dialog({ title: __("Ajouter des variantes"), size: "large", fields: [{ fieldtype: "HTML", fieldname: "g" }],
				primary_action_label: __("Ajouter la sélection"),
				primary_action: () => { choix.forEach((u) => etat.cases.push({ url: u, legende: "" })); pk.hide(); rendre_cases(); apercu(); },
				secondary_action_label: __("Téléverser une photo"),
				secondary_action: () => {
					pk.hide();
					new frappe.ui.FileUploader({ doctype: "Design Emballage", docname: this.nom, folder: "Home/Attachments",
						restrictions: { allowed_file_types: ["image/*"] },
						on_success: (f) => { etat.cases.push({ url: f.file_url, legende: "" }); rendre_cases(); apercu(); } });
				} });
			const $g = pk.get_field("g").$wrapper;
			$g.html(`<p class="small text-muted">${__("Cliquez les photos à ajouter (plusieurs possibles), puis « Ajouter la sélection ».")}</p>
				<h6>${__("Photos de ce design")}</h6>
				<div class="se-galerie">${photos.map((im) => carte(im.file_url, im.genre)).join("") || `<div class="text-muted small">${__("Aucune.")}</div>`}</div>
				<h6 style="margin-top:12px">${__("Bibliothèque (photos du produit)")}</h6>
				<div class="se-galerie">${biblio.map((l) => carte(l.image, l.nom)).join("") || `<div class="text-muted small">${__("Rien en bibliothèque.")}</div>`}</div>
				<h6 style="margin-top:12px">${__("Autres articles")}</h6>
				<input class="form-control input-sm" data-role="cherche-article" placeholder="${__("Code ou nom d'un article (ex. P-F-S-10, porte-filtre bleu)…")}" style="max-width:420px">
				<div data-role="res-articles" style="margin-top:8px"></div>`);
			// délégué : les cartes des autres articles arrivent après la recherche
			$g.on("click", "[data-url]", (e) => {
				const u = $(e.currentTarget).attr("data-url");
				if (choix.has(u)) choix.delete(u); else choix.add(u);
				$(e.currentTarget).css({ outline: choix.has(u) ? "3px solid var(--primary)" : "", "outline-offset": "-3px" });
				pk.set_primary_action(choix.size ? __("Ajouter la sélection ({0})", [choix.size]) : __("Ajouter la sélection"), pk.primary_action);
			});
			const chercher = frappe.utils.debounce(async (texte) => {
				const $r = $g.find('[data-role="res-articles"]');
				if ((texte || "").trim().length < 2) { $r.empty(); return; }
				$r.html(`<div class="text-muted small">${__("Recherche…")}</div>`);
				const res = (await frappe.call({ method: "aquaworld_ia.emballage.studio.photos_autres_articles", args: { recherche: texte, design: this.nom } })).message || [];
				$r.html(res.length ? res.map((a) => `<div style="margin-bottom:10px"><div class="small"><b>${esc(a.article)}</b> · ${esc(a.nom)}</div>
					<div class="se-galerie">${a.photos.map((p) => carte(p.url, p.source)).join("")}</div></div>`).join("")
					: `<div class="text-muted small">${__("Aucun article avec photo pour « {0} ».", [esc(texte)])}</div>`);
				$r.find("[data-url]").each((_i, el) => { if (choix.has($(el).attr("data-url"))) $(el).css({ outline: "3px solid var(--primary)", "outline-offset": "-3px" }); });
			}, 350);
			$g.find('[data-role="cherche-article"]').on("input", (e) => chercher(e.currentTarget.value));
			pk.show();
		};
		const ameliorer = (i) => {
			const c = etat.cases[i], est = this.data.estimation || {};
			const d1 = new frappe.ui.Dialog({ title: __("Améliorer cette variante par IA"), fields: [
				{ fieldtype: "HTML", options: `<img src="${esc(c.url)}" style="max-height:120px;max-width:100%;background:#fff;border:1px solid #e5e7eb;border-radius:6px;padding:6px">` },
				{ fieldtype: "Small Text", fieldname: "instruction", label: __("Que changer ?"), reqd: 1,
				  default: __("Détourer sur fond blanc pur, éclairage studio doux, vue de face, net") },
				{ fieldtype: "Select", fieldname: "nombre", label: __("Propositions"), default: "2", options: "1\n2\n3\n4",
				  description: __("Une image facturée par proposition (≈ {0} $ chacune). L'IA redessine : contrôlez chaque détail.", [(est.cout || 0).toFixed(2)]) }],
				primary_action_label: __("Générer"),
				primary_action: async (v) => {
					let r;
					try {
						r = await frappe.call({ method: "aquaworld_ia.emballage.studio.retoucher_image", freeze: true, freeze_message: __("L'IA retravaille la photo…"),
							args: { design: this.nom, champ: "photo_produit", instruction: v.instruction, nombre: v.nombre, source_url: c.url } });
					} catch (e) { frappe.msgprint(this._msg(e)); return; }
					d1.hide();
					const cands = (r.message || {}).candidats || [];
					const d2 = new frappe.ui.Dialog({ title: __("Propositions pour cette variante"), size: "large", fields: [{ fieldtype: "HTML", fieldname: "g" }] });
					d2.get_field("g").$wrapper.html(`<div style="display:flex;gap:14px;flex-wrap:wrap;align-items:flex-start">${[c.url].concat(cands).map((u, k) => `
						<div style="flex:1 1 180px;text-align:center;min-width:0"><div class="small text-muted">${k ? __("Proposition {0}", [k]) : __("Actuelle")}</div>
						<img src="${esc(u)}" style="max-width:100%;max-height:220px;background:#fff;border:1px solid #e5e7eb;border-radius:6px">
						${k ? `<div style="margin-top:6px"><button class="btn btn-xs btn-primary" data-prendre="${esc(u)}">${__("Prendre celle-ci")}</button></div>` : ""}</div>`).join("")}</div>`);
					d2.get_field("g").$wrapper.find("[data-prendre]").on("click", (e) => { c.url = $(e.currentTarget).attr("data-prendre"); d2.hide(); rendre_cases(); apercu(); });
					d2.show();
				} });
			d1.show();
		};
		// Toutes les variantes sous l'angle de la première : une proposition par variante, comparée à l'actuelle ;
		// « Prendre » remplace la photo de la case (et retire son miroir : la nouvelle image est déjà orientée).
		// Itérer (demande 14/10/2026 : « une erreur visuelle → réitérer ») : sous chaque variante, une correction
		// appliquée à la DERNIÈRE proposition (l'orientation est gardée) ou une nouvelle tentative depuis l'originale.
		const orienter = () => {
			const ref = etat.cases[0], autres = etat.cases.slice(1), est = this.data.estimation || {};
			const lancement = new frappe.ui.Dialog({ title: __("🧭 Même orientation que la première"),
				fields: [
					{ fieldtype: "HTML", options: `<p>${__("L'IA va redessiner {0} variante(s) sous le même angle que la première{1}. Une image facturée par variante (≈ {2} $ chacune), environ une minute. L'IA redessine : contrôlez chaque détail.",
						[autres.length, ref.miroir ? " " + __("(retournée)") : "", (est.cout || 0).toFixed(2)])}</p>` },
					{ fieldtype: "Small Text", fieldname: "consigne", label: __("Consigne en plus, pour toutes les variantes (facultative)"),
					  description: __("ex. « sans la clé ni le support mural », « cuve bien transparente », « même hauteur de tête »") },
				],
				primary_action_label: __("Lancer"),
				primary_action: async (v) => {
					lancement.hide();
					const consigne = (v.consigne || "").trim();
					frappe.dom.freeze(__("L'IA oriente les variantes comme la première…"));
					const res = await Promise.all(autres.map((c) => appel_orienter(c, consigne)
						.then((cands) => ({ c, propositions: cands }), (e) => ({ c, propositions: [], erreur: this._msg(e) }))));
					frappe.dom.unfreeze();
					resultats(res, consigne);
				} });
			lancement.show();
		};
		const appel_orienter = async (c, consigne) => {
			const ref = etat.cases[0];
			const r = await frappe.call({ method: "aquaworld_ia.emballage.studio.orienter_variante",
				args: { design: this.nom, url: c.url, reference: ref.url, reference_miroir: ref.miroir ? 1 : 0, nombre: 1, consigne: consigne || "" } });
			return (r.message || {}).candidats || [];
		};
		const base_de = (x) => (x.base && x.propositions.includes(x.base)) ? x.base : x.propositions[x.propositions.length - 1];
		const resultats = (res, consigne) => {
			const ref = etat.cases[0];
			const d3 = new frappe.ui.Dialog({ title: __("Même orientation que la première"), size: "extra-large", fields: [{ fieldtype: "HTML", fieldname: "g" }],
				primary_action_label: __("Tout prendre (dernières propositions)"),
				primary_action: () => {
					res.forEach((x) => { const u = x.propositions[x.propositions.length - 1]; if (u && !x.pris) { x.c.url = u; x.c.miroir = false; } });
					d3.hide(); rendre_cases(); apercu();
				} });
			const vignette = (u, titre, miroir) => `<div style="flex:0 0 170px;text-align:center"><div class="small text-muted">${titre}</div>
				<img src="${esc(u)}" style="max-width:170px;max-height:180px;background:#fff;border:1px solid #e5e7eb;border-radius:6px;${miroir ? "transform:scaleX(-1)" : ""}"></div>`;
			const ligne = (x, k) => `<div style="padding:10px 0;border-bottom:1px solid #f0f0f0" data-ligne="${k}">
				<div style="display:flex;gap:12px;align-items:flex-start;overflow-x:auto">
					${vignette(x.c.url, __("Variante {0} — actuelle", [k + 2]), x.c.miroir)}
					${x.propositions.map((u, j) => `<div style="flex:0 0 170px;text-align:center;cursor:pointer;border-radius:8px;${base_de(x) === u ? "outline:3px solid var(--primary);outline-offset:2px" : ""}"
						data-base="${k}" data-url="${esc(u)}" title="${__("Cliquer pour corriger CETTE proposition")}">${vignette(u, __("Proposition {0}", [j + 1]) + (base_de(x) === u ? " ✏️" : ""), false).replace(/^<div[^>]*>/, "").replace(/<\/div>$/, "")}
						<div style="margin-top:4px"><button class="btn btn-xs ${x.pris === u ? "btn-success" : "btn-primary"}" data-prendre="${k}" data-url="${esc(u)}" ${x.pris === u ? "disabled" : ""}>${x.pris === u ? __("Pris ✓") : __("Prendre")}</button></div></div>`).join("")}
					${x.erreur ? `<div class="text-danger small" style="align-self:center">${esc(x.erreur)}</div>` : ""}
					${x.en_cours ? `<div class="text-muted small" style="align-self:center">⏳ ${__("L'IA retravaille…")}</div>` : ""}
				</div>
				<div style="display:flex;gap:6px;align-items:center;margin-top:6px;flex-wrap:wrap">
					<input class="form-control input-sm" data-correction="${k}" value="${esc(x.correction || "")}" placeholder="${__("Correction : ex. « retirer la clé et le support », « même tête que l'image de référence »")}" style="flex:1 1 320px" ${x.en_cours ? "disabled" : ""}>
					${x.ref_choisie ? `<span style="display:inline-flex;align-items:center;gap:4px;border:1px solid var(--primary);border-radius:6px;padding:2px 4px" title="${__("Image de référence envoyée à l'IA avec la correction")}">
						<img src="${esc(x.ref_choisie)}" style="height:34px;width:34px;object-fit:contain;background:#fff"><span class="small">${__("réf.")}</span>
						<select data-ref-mode="${k}" class="input-xs" style="font-size:11px;border:1px solid var(--border-color);border-radius:4px" title="${__("Ce que l'IA doit prendre de la référence")}">
							<option value="forme" ${x.ref_mode !== "photo" ? "selected" : ""}>${__("ses proportions / sa forme")}</option>
							<option value="photo" ${x.ref_mode === "photo" ? "selected" : ""}>${__("une pièce, une couleur, une matière")}</option></select>
						<span data-sans-ref="${k}" style="cursor:pointer;color:var(--red-600)" title="${__("Retirer la référence")}">✕</span></span>` : ""}
					<button class="btn btn-xs btn-default" data-choisir-ref="${k}" ${x.en_cours ? "disabled" : ""} title="${__("Choisir une image que l'IA doit regarder pour cette correction (une autre variante, l'image principale, une photo du design)")}">🖼 ${__("Image de référence")}</button>
					<button class="btn btn-xs btn-default" data-corriger="${k}" ${x.propositions.length && !x.en_cours ? "" : "disabled"} title="${__("L'IA reprend la proposition SÉLECTIONNÉE (encadrée ; la dernière par défaut), garde son angle et applique la correction, en revoyant la photo d'origine de la variante — et l'image de référence si vous en avez choisi une")}">✏️ ${__("Corriger la proposition")}</button>
					<button class="btn btn-xs btn-default" data-refaire="${k}" ${x.en_cours ? "disabled" : ""} title="${__("Nouvelle tentative depuis la photo d'origine, sous l'angle de la première, avec la correction")}">↻ ${__("Refaire")}</button>
				</div></div>`;
			const dessiner = () => {
				const $g = d3.get_field("g").$wrapper;
				$g.html(`<div style="display:flex;gap:14px;align-items:flex-start;margin-bottom:6px;padding-bottom:10px;border-bottom:1px solid #e5e7eb">
					${vignette(ref.url, __("Référence (1re variante)"), ref.miroir)}
					<p class="small text-muted" style="align-self:center;flex:1">${__("Une erreur visuelle ? Cliquez la proposition à corriger (encadrée ; la dernière par défaut), écrivez la correction, et au besoin « 🖼 Image de référence » pour montrer à l'IA une autre image (la tête d'une variante, la cuve de l'image principale…). « Corriger » garde l'angle de la proposition et revoit la photo d'origine ; « Refaire » repart de la photo d'origine sous l'angle de l'image principale. Chaque essai est une image facturée ; tout reste dans la médiathèque.")}</p></div>
					${res.map(ligne).join("")}`);
				$g.find("[data-base]").on("click", (e) => {
					if ($(e.target).closest("[data-prendre]").length) return;      // « Prendre » n'est pas une sélection
					const x = res[cint($(e.currentTarget).attr("data-base"))];
					x.correction = $g.find(`[data-correction="${$(e.currentTarget).attr("data-base")}"]`).val();
					x.base = $(e.currentTarget).attr("data-url");
					dessiner();
				});
				$g.find("[data-sans-ref]").on("click", (e) => { const x = res[cint($(e.currentTarget).attr("data-sans-ref"))]; x.ref_choisie = null; dessiner(); });
				$g.find("[data-ref-mode]").on("change", (e) => { res[cint($(e.currentTarget).attr("data-ref-mode"))].ref_mode = e.currentTarget.value; });
				$g.find("[data-choisir-ref]").on("click", (e) => {
					const k = cint($(e.currentTarget).attr("data-choisir-ref")), x = res[k];
					x.correction = $g.find(`[data-correction="${k}"]`).val();
					// toutes les images de la fenêtre, puis les photos du design
					const choix = [{ url: ref.url, titre: __("Image principale (1re variante)") }];
					res.forEach((y, i) => {
						choix.push({ url: (y.c_origine || y.c).url, titre: __("Variante {0} — origine", [i + 2]) });
						y.propositions.forEach((u, j) => choix.push({ url: u, titre: __("Variante {0} — proposition {1}", [i + 2, j + 1]) + (y.pris === u ? " ✓" : "") }));
					});
					(this.data.images || []).filter((im) => /^Photo/.test(im.genre || "")).forEach((im) => choix.push({ url: im.file_url, titre: im.genre }));
					const vus = new Set(), uniques = choix.filter((c) => !vus.has(c.url) && vus.add(c.url));
					const dr = new frappe.ui.Dialog({ title: __("Image de référence pour la correction de la variante {0}", [k + 2]), size: "large",
						fields: [{ fieldtype: "HTML", fieldname: "g" }] });
					dr.get_field("g").$wrapper.html(`<p class="small text-muted">${__("Ensuite, choisissez ce que l'IA doit en prendre : « ses proportions / sa forme » (l'IA ne reçoit qu'une silhouette grise : elle ne peut rien recopier d'autre) ou « une pièce, une couleur, une matière » (la photo, qui peut déteindre un peu). L'angle reste celui de la proposition, le reste celui de la photo d'origine.")}</p>
						<div class="se-galerie">${uniques.map((c) => `<div class="se-carte" data-ref-url="${esc(c.url)}" style="cursor:pointer">
							<img src="${esc(c.url)}" style="aspect-ratio:1/1;object-fit:contain;background:#fff"><div class="leg">${esc(c.titre)}</div></div>`).join("")}</div>`);
					dr.get_field("g").$wrapper.find("[data-ref-url]").on("click", (e2) => { x.ref_choisie = $(e2.currentTarget).attr("data-ref-url"); dr.hide(); dessiner(); });
					dr.show();
				});
				$g.find("[data-prendre]").on("click", (e) => {
					const x = res[cint($(e.currentTarget).attr("data-prendre"))];
					x.pris = $(e.currentTarget).attr("data-url");
					x.c.url = x.pris; x.c.miroir = false;
					dessiner(); rendre_cases(); apercu();
				});
				const lancer = async (k, mode) => {
					const x = res[k], correction = ($g.find(`[data-correction="${k}"]`).val() || "").trim();
					x.correction = correction;
					if (mode === "corriger" && !correction) { frappe.show_alert({ message: __("Écrivez d'abord la correction à apporter."), indicator: "orange" }); return; }
					x.en_cours = true; x.erreur = null; dessiner();
					try {
						let cands;
						if (mode === "corriger") {
							// à chaque correction, l'IA revoit la photo d'ORIGINE de la variante (son apparence) ; l'angle est
							// celui de la proposition (renvoyer l'image principale lui faisait recopier son produit)
							const ref = etat.cases[0];
							const r = await frappe.call({ method: "aquaworld_ia.emballage.studio.corriger_orientation",
								args: { design: this.nom, proposition: base_de(x), original: (x.c_origine || x.c).url,
								        reference: ref.url, reference_miroir: ref.miroir ? 1 : 0, nombre: 1, reference_choisie: x.ref_choisie || "",
								        reference_mode: x.ref_mode || "forme",
								        correction: [consigne, correction].filter(Boolean).join(". ") } });
							cands = (r.message || {}).candidats || [];
						} else {
							cands = await appel_orienter(x.c_origine || x.c, [consigne, correction].filter(Boolean).join(". "));
						}
						x.propositions = x.propositions.concat(cands);
						x.base = null;            // la nouvelle proposition devient la base par défaut
					} catch (e) { x.erreur = this._msg(e); }
					x.en_cours = false; dessiner();
				};
				$g.find("[data-corriger]").on("click", (e) => lancer(cint($(e.currentTarget).attr("data-corriger")), "corriger"));
				$g.find("[data-refaire]").on("click", (e) => lancer(cint($(e.currentTarget).attr("data-refaire")), "refaire"));
				$g.find("[data-correction]").on("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); lancer(cint($(e.currentTarget).attr("data-correction")), "corriger"); } });
			};
			// « Refaire » repart de la photo d'ORIGINE, même après un « Prendre »
			res.forEach((x) => { x.c_origine = { url: x.c.url, miroir: x.c.miroir }; });
			d3.show(); dessiner();
		};
		const creer = async (adopter) => {
			if (etat.cases.length < 2) { frappe.msgprint(__("Choisissez au moins deux variantes du produit.")); return; }
			try {
				const r = await frappe.call({ method: "aquaworld_ia.emballage.studio.mosaique_creer", freeze: true, freeze_message: __("Composition de la mosaïque…"),
					args: { design: this.nom, config: JSON.stringify(config()), adopter } });
				dlg.hide(); this.data = Object.assign({}, this.data, r.message); this.d = this.data.doc; this._lire_mep(); this.rendre();
				frappe.show_alert({ message: adopter ? __("Mosaïque posée comme photo du produit : recomposez le plan.") : __("Mosaïque enregistrée dans la médiathèque."), indicator: "green" }, 7);
			} catch (e) { frappe.msgprint(this._msg(e)); }
		};
		const sur_changement = () => apercu();
		dlg = new frappe.ui.Dialog({ title: __("🧩 Mosaïque de variantes du produit"), size: "extra-large",
			fields: [
				{ fieldtype: "HTML", fieldname: "cases" },
				{ fieldtype: "HTML", fieldname: "apercu" },
				{ fieldtype: "Column Break" },
				{ fieldtype: "Select", fieldname: "disposition", label: __("Disposition"), default: cfg.disposition || "grille", onchange: sur_changement,
				  options: [{ value: "grille", label: __("Grille — en-têtes de colonnes et de lignes") }, { value: "rangee", label: __("Rangée") },
				            { value: "colonne", label: __("Colonne") }, { value: "heros", label: __("Héros + variantes") },
				            { value: "groupe", label: __("Groupe — produits rapprochés") }] },
				{ fieldtype: "Int", fieldname: "colonnes", label: __("Colonnes (0 = automatique)"), default: cfg.colonnes || 0, depends_on: "eval:doc.disposition=='grille'", onchange: sur_changement },
				{ fieldtype: "Select", fieldname: "espacement", label: __("Espacement"), default: cfg.espacement || "normal", onchange: sur_changement,
				  options: [{ value: "serre", label: __("Serré") }, { value: "normal", label: __("Normal") }, { value: "aere", label: __("Aéré") }] },
				{ fieldtype: "Select", fieldname: "cadre", label: __("Cadre de chaque variante"), default: cfg.cadre || "aucun", onchange: sur_changement,
				  options: [{ value: "aucun", label: __("Aucun") }, { value: "carte", label: __("Carte (fond clair arrondi)") }, { value: "trait", label: __("Trait") }] },
				{ fieldtype: "Select", fieldname: "alignement", label: __("Alignement des produits"), default: cfg.alignement || "pied", onchange: sur_changement,
				  options: [{ value: "pied", label: __("Au pied (debout sur la même ligne)") }, { value: "centre", label: __("Au milieu") }] },
				{ fieldtype: "Select", fieldname: "ajustement", label: __("Taille des produits"), default: cfg.ajustement || "largeur", onchange: sur_changement,
				  description: __("Chaque photo est d'abord rognée au contour du produit. Une variante à part ? Réglez son % dans la liste."),
				  options: [{ value: "largeur", label: __("Même largeur") }, { value: "hauteur", label: __("Même hauteur") }],
				  depends_on: "eval:['grille','rangee'].includes(doc.disposition)" },
				{ fieldtype: "Column Break" },
				{ fieldtype: "Data", fieldname: "titre", label: __("Titre"), default: cfg.titre || "", onchange: sur_changement },
				{ fieldtype: "Small Text", fieldname: "entetes_colonnes", label: __("En-têtes de colonnes (un par ligne)"), default: (cfg.entetes_colonnes || []).join("\n"), depends_on: AVEC_ENTETES, onchange: sur_changement },
				{ fieldtype: "Small Text", fieldname: "entetes_lignes", label: __("En-têtes de lignes, en pastilles (un par ligne)"), default: (cfg.entetes_lignes || []).join("\n"), depends_on: AVEC_ENTETES, onchange: sur_changement },
				{ fieldtype: "Data", fieldname: "pied", label: __("Pied"), default: cfg.pied || "", onchange: sur_changement },
				{ fieldtype: "Section Break" },
				{ fieldtype: "Select", fieldname: "fond", label: __("Fond"), default: cfg.fond || "transparent", onchange: sur_changement,
				  options: [{ value: "transparent", label: __("Transparent") }, { value: "blanc", label: __("Blanc") }] },
				{ fieldtype: "Column Break" },
				{ fieldtype: "Check", fieldname: "detourer", label: __("Détourer les produits"), default: cfg.detourer === false ? 0 : 1, onchange: sur_changement,
				  description: __("Décochez pour un produit transparent sur fond blanc : ses parties claires disparaissent au détourage.") },
				{ fieldtype: "Column Break" },
				{ fieldtype: "Color", fieldname: "couleur", label: __("Couleur du texte"), default: cfg.couleur || "#1f3a8a", onchange: sur_changement },
				{ fieldtype: "Column Break" },
				{ fieldtype: "Select", fieldname: "police", label: __("Police"), options: POLICES, default: cfg.police || "Poppins", onchange: sur_changement },
			],
			primary_action_label: __("Utiliser comme photo du produit"),
			primary_action: () => creer(1),
			secondary_action_label: __("Enregistrer dans les images"),
			secondary_action: () => creer(0),
		});
		dlg.show();
		rendre_cases();
		apercu();
	}

	bibliotheque(champ, on_choisir) {
		const b = StudioEmballage.BIBLIO[champ];
		const dlg = new frappe.ui.Dialog({ title: b.liste, size: "large",
			fields: [
				{ fieldtype: "Data", fieldname: "recherche", label: __("Rechercher") },
				{ fieldtype: "HTML", fieldname: "grille" },
			] });
		const $grille = dlg.get_field("grille").$wrapper;
		const charger = async () => {
			const r = await frappe.call({ method: "aquaworld_ia.emballage.studio.bibliotheque_liste", args: { champ, marque: this.d.marque, recherche: dlg.get_value("recherche") } });
			const lignes = r.message || [];
			if (!lignes.length) { $grille.html(`<div class="se-vide">${__("Rien en bibliothèque pour l'instant : gardez un fond, un logo ou une photo avec le bouton « Garder ».")}</div>`); return; }
			$grille.html(`<div class="se-galerie">${lignes.map((l) => `
				<div class="se-carte" data-res="${this._esc(l.name)}" style="cursor:pointer">
					<img src="${this._esc(l.image)}" alt="" style="aspect-ratio:${b.ratio};object-fit:contain;background:#fff">
					<div class="leg"><b>${this._esc(l.nom)}</b> <span class="se-chip">${this._esc(l.categorie)}</span>${l.marque ? `<br><span class="text-muted">${this._esc(l.marque)}</span>` : ""}${l.notes ? `<br><span class="text-muted small">${this._esc(l.notes)}</span>` : ""}</div>
				</div>`).join("")}</div>`);
			$grille.find("[data-res]").on("click", async (e) => {
				if (on_choisir) { const l = lignes.find((x) => x.name === $(e.currentTarget).attr("data-res")); dlg.hide(); if (l) on_choisir(l); return; }
				try {
					const r2 = await frappe.call({ method: "aquaworld_ia.emballage.studio.bibliotheque_choisir", args: { design: this.nom, ressource: $(e.currentTarget).attr("data-res"), champ }, freeze: true });
					dlg.hide(); this.data = Object.assign({}, this.data, r2.message); this.d = this.data.doc; this._lire_mep(); this.rendre();
					frappe.show_alert({ message: b.remplace, indicator: "green" });
				} catch (e2) { frappe.msgprint(this._msg(e2)); }
			});
		};
		dlg.get_field("recherche").$input.on("input", frappe.utils.debounce(charger, 350));
		dlg.show(); charger();
	}

}
