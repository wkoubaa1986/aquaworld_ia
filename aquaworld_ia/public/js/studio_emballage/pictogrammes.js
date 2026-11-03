// Choix des certifications par zone ; la liste Contenus reste la bibliothèque du design.
class StudioPictogrammes {
	rotations_pictos(z) {
		if (z.zone !== "pictos" || !z.pictos_rotations || typeof z.pictos_rotations !== "object" || Array.isArray(z.pictos_rotations)) return {};
		return Object.fromEntries(Object.entries(z.pictos_rotations)
			.filter(([code, v]) => code && ["number", "string"].includes(typeof v) && String(v).trim() && Number.isFinite(Number(v)))
			.map(([code, v]) => [code, Math.round(this.angle_zone(v) * 1000) / 1000 % 360]).filter(([_c, a]) => a));
	}

	rotation_picto(z, code) { return this.rotations_pictos(z)[code] || 0; }

	source_pictos(face) {
		return face.copie_de && !Object.hasOwn(this.mep, face.code)
			? this.data.apercu.faces.find(f => f.code === face.copie_de) : null;
	}

	async regler_rotation_picto(code, valeur) {
		const contexte = this._zones_en_cours, z = contexte?.zones[this.zone_sel];
		if (!this.data.peut_ecrire || z?.zone !== "pictos" || contexte.face.code !== this.epinglee || !this.pictos_effectifs_zone(z).some(p => p.code === code)) return;
		if (!String(valeur).trim() || !Number.isFinite(Number(valeur))) return frappe.msgprint(__("Saisissez un angle en degrés, par exemple 45 ou −90."));
		const angle = Math.round(this.angle_zone(valeur) * 1000) / 1000 % 360;
		const $input = this.$root.find(".se-droite [data-angle-picto]").filter((_i, el) => el.dataset.anglePicto === code);
		$input.val(angle).removeAttr("data-saisie-position");
		if (this.rotation_picto(z, code) === angle) return;
		const angles = this.rotations_pictos(z);
		if (angle) angles[code] = angle; else delete angles[code];
		z.pictos_rotations = angles;
		const source = this.source_pictos(contexte.face);
		const code_source = source?.code || contexte.face.code;
		// Garder aussi l'aperçu local à jour si l'on change de face avant la réponse réseau.
		for (const face of this.data.apercu.faces.filter(f => f.code === code_source || f.copie_de === code_source)) {
			const liee = face.zones[this.zone_sel];
			if (liee?.zone === "pictos") liee.pictos_rotations = {...angles};
		}
		contexte.actualiser[this.zone_sel]?.();
		// Le geste est appliqué avant l'attente réseau ; les clics rapides s'additionnent.
		try {
			// Une rotation ne détache pas les faces identiques. Depuis la copie,
			// modifier la zone source dans ses propres coordonnées, sans créer de surcharge.
			if (source) {
				const origine = source.zones[this.zone_sel];
				if (origine?.zone !== "pictos") throw new Error(__("La face source a changé. Rechargez le studio."));
				this.mep[source.code] = source.zones.filter(z => !z.auto).map(z => this.zone_a_enregistrer(z));
				await this.modifier({mise_en_page: this.mep}, false, this.nom);
			} else {
				await contexte.sauver();
			}
		}
		catch (e) { frappe.msgprint(this._msg(e)); }
	}

	disposition_pictos(z) {
		return z.pictos_disposition === "vertical" ? "vertical" : "horizontal";
	}

	commandes_disposition_pictos(z) {
		return `<div class="se-pictos-disposition"><span class="small">${__("Disposition dans la zone")}</span>
			<div class="se-btns" role="group" aria-label="${__("Disposition des pictogrammes")}">${[["horizontal", __("↔ Horizontal")], ["vertical", __("↕ Vertical")]].map(([v, libelle]) =>
				`<button type="button" class="btn btn-xs ${this.disposition_pictos(z) === v ? "btn-primary" : "btn-default"}" data-pictos-disposition="${v}" aria-pressed="${this.disposition_pictos(z) === v}">${libelle}</button>`).join("")}</div>
			<p class="text-muted small">${__("Les pictogrammes gardent chacun leur angle et s’ajustent à la zone. Pour déplacer l’ensemble, utilisez « Contenu dans le cadre ».")}</p></div>`;
	}

	async changer_disposition_pictos(disposition) {
		if (this._disposition_pictos_en_cours) return;
		const design = this.nom, face = this.epinglee, indice = this.zone_sel;
		this._disposition_pictos_en_cours = true;
		this.$root.find(".se-droite [data-pictos-disposition]").prop("disabled", true);
		try {
			await this.attendre_sauvegardes();
			if (this.nom !== design || this.epinglee !== face || this.zone_sel !== indice || !this.data.peut_ecrire) return;
			const z = this.data.apercu?.faces?.find(f => f.code === face)?.zones?.[indice];
			if (z?.zone !== "pictos" || this.disposition_pictos(z) === disposition) return;
			await this.appliquer_pictos_zone({design, face, indice, revision: this.d.modified}, this.pictos_selection_zone(z), disposition);
		} catch (e) { frappe.msgprint(this._msg(e)); }
		finally {
			this._disposition_pictos_en_cours = false;
			this.$root.find(".se-droite [data-pictos-disposition]").prop("disabled", false);
		}
	}

	pictos_du_design() {
		const catalogue = new Map((this.data.pictos || []).map(p => [p.code, p]));
		return (this.d.pictogrammes || []).map(p => catalogue.get(p.pictogramme) || {code: p.pictogramme, libelle: p.pictogramme});
	}

	pictos_selection_zone(z) {
		if (Array.isArray(z.pictos) && z.pictos.length) return [...z.pictos];
		return z.pictos_mode === "selection" ? [] : null;
	}

	pictos_effectifs_zone(z) {
		const selection = this.pictos_selection_zone(z);
		return this.pictos_du_design().filter(p => selection === null ? p.categorie !== "Tampon" : selection.includes(p.code))
			.map(p => ({...p, url: z.pictos_images?.[p.code] || p.url}));
	}

	aide_faces_pictos(face) {
		if (face.copie_de) return __("Les couleurs et rotations restent synchronisées avec la face d’origine. Choisir ici d’autres pictogrammes rend cette face indépendante.");
		const copies = (this.data.apercu?.faces || []).filter(f => f.copie_de === face.code);
		return copies.length ? __("Ces facettes suivent cette face, couleurs et rotations comprises : {0}. Pour y choisir d’autres pictogrammes, sélectionnez leur propre zone.", [copies.map(f => f.libelle).join(", ")])
			: __("Le choix s’applique uniquement à cette zone. Les autres zones gardent leur sélection.");
	}

	panneau_pictos_zone(z, face) {
		const choix = this.pictos_effectifs_zone(z), esc = this._esc;
		return `<div class="bloc se-pictos-zone" data-section-propriete="pictos"><h6>${__("Pictogrammes de cette zone")}</h6>
			<p class="text-muted small">${this.pictos_selection_zone(z) === null ? __("Suit la liste Contenus") : __("Sélection propre à cette zone")}</p>
			<div class="se-pictos-selection">${choix.map(p => `<details class="se-picto-variante" data-propriete-picto="${esc(p.code)}"><summary><span>${p.url ? `<img src="${esc(p.url)}" alt="">` : ""}${esc(p.libelle || p.code)}</span></summary><div class="se-picto-reglages">
				<div class="se-angle-picto"><label>${__("Angle (°)")}<input class="form-control input-xs" type="number" step="any" data-angle-picto="${esc(p.code)}" value="${this.rotation_picto(z, p.code)}" aria-label="${esc(__("Angle de {0}", [p.libelle || p.code]))}"></label>
				<button class="btn btn-xs btn-default" data-picto-appliquer-angle>${__("Appliquer")}</button></div>
				<div class="se-btns"><button class="btn btn-xs btn-default" data-picto-tourner="-90" title="${__("Quart de tour à gauche")}">↶ −90°</button>
				<button class="btn btn-xs btn-default" data-picto-tourner="90" title="${__("Quart de tour à droite")}">↷ +90°</button>
				<button class="btn btn-xs btn-default" data-picto-tourner="zero">0°</button></div>
				<div class="se-btns"><button class="btn btn-xs btn-default" data-picto-couleur="${esc(p.code)}">${__("Couleur & SVG")}</button>
				${z.pictos_images?.[p.code] ? `<button class="btn btn-xs btn-default" data-picto-original="${esc(p.code)}">${__("Original")}</button>` : ""}</div></div></details>`).join("") || `<span>${__("Aucun pictogramme choisi")}</span>`}</div>
			<button class="btn btn-xs btn-primary" data-role="choisir-pictos-zone">${__("Choisir pour cette zone")}</button>
			<p class="text-muted small">${__("Chaque angle tourne uniquement ce pictogramme dans cette zone. Son dessin s’ajuste à son emplacement.")}</p>
			<p class="text-muted small">${esc(this.aide_faces_pictos(face))}</p>
			<button class="btn btn-xs btn-default" data-role="liste-pictos-design">${__("Gérer la liste dans Contenus")}</button></div>
			<div class="bloc" data-section-propriete="disposition"><h6>${__("Disposition des pictogrammes")}</h6>${this.commandes_disposition_pictos(z)}</div>`;
	}

	async cible_variante_picto(code) {
		const design = this.nom, face = this.epinglee, indice = this.zone_sel;
		await this.attendre_sauvegardes();
		if (this.nom !== design || this.epinglee !== face || this.zone_sel !== indice || !this.data.peut_ecrire) return;
		const z = this.data.apercu?.faces?.find(f => f.code === face)?.zones?.[indice];
		if (z?.zone !== "pictos" || !this.pictos_effectifs_zone(z).some(p => p.code === code)) return;
		return {design, face, indice, revision: this.d.modified, code, source: z.pictos_images?.[code] || null};
	}

	async appliquer_variante_picto(cible, url) {
		await this.attendre_sauvegardes();
		if (this.nom !== cible.design || this.d.modified !== cible.revision)
			throw new Error(__("Le design a changé. Rouvrez « Couleur & SVG » pour cette zone."));
		const f = this.data.apercu?.faces?.find(f => f.code === cible.face), z = f?.zones?.[cible.indice];
		if (z?.zone !== "pictos" || !this.pictos_effectifs_zone(z).some(p => p.code === cible.code))
			throw new Error(__("Ce pictogramme n’est plus dans cette zone."));
		// Même règle que pour les angles : depuis une face liée, modifier sa source
		// dans ses propres coordonnées. Appliquer / Original conserve le lien.
		const destination = this.source_pictos(f) || f, origine = destination.zones[cible.indice];
		if (origine?.zone !== "pictos" || !this.pictos_effectifs_zone(origine).some(p => p.code === cible.code))
			throw new Error(__("La face source a changé. Rouvrez « Couleur & SVG »."));
		const mep = {...this.mep};
		mep[destination.code] = destination.zones.map((z, i) => {
			const out = this.zone_a_enregistrer(z);
			if (i === cible.indice) {
				const images = {...out.pictos_images};
				if (url) images[cible.code] = url; else delete images[cible.code];
				delete out.pictos_images;
				if (Object.keys(images).length) out.pictos_images = images;
			}
			return out;
		}).filter((_z, i) => !destination.zones[i].auto);
		await this.enregistrer({mise_en_page: mep}, cible.design);
	}

	async restaurer_picto(code) {
		try {
			const cible = await this.cible_variante_picto(code);
			if (cible) await this.appliquer_variante_picto(cible, null);
		} catch (e) { frappe.msgprint(this._msg(e)); }
	}

	async atelier_picto(code) {
		let cible;
		try { cible = await this.cible_variante_picto(code); }
		catch (e) { frappe.msgprint(this._msg(e)); return; }
		if (!cible) return;
		const p = this.pictos_du_design().find(p => p.code === code), source = cible.source || p?.url, esc = this._esc;
		let dlg, candidat = null, en_cours = false, parametres_candidat = null;
		const params = () => ({mode: dlg.get_value("mode"), couleur: dlg.get_value("couleur"),
			garder_blanc: dlg.get_value("garder_blanc"), couleurs: dlg.get_value("couleurs"), retirer_fond: dlg.get_value("retirer_fond")});
		const invalider = () => {
			// Frappe valide aussi les champs avec un délai : ne pas effacer un aperçu
			// déjà calculé pour ces mêmes valeurs quand cette validation arrive ensuite.
			if (candidat && parametres_candidat === JSON.stringify(params())) return;
			candidat = null; dlg?.fields_dict.resultat.$wrapper.empty();
		};
		dlg = new frappe.ui.Dialog({title: __("Couleur & SVG · {0}", [p?.libelle || code]), size: "large", fields: [
			{fieldtype: "HTML", options: `<p>${__("La variante s’applique à ce pictogramme dans cette zone et sur les faces identiques liées. Le fichier d’origine est conservé. « Original » rétablit aussi le dessin sur les faces liées.")}</p>
				<p class="text-muted small">${__("Pour une certification existante, utilisez son fichier SVG d’origine afin de conserver ses lettres et contours. L’IA sert à créer de nouveaux tampons dans Contenus → Tampon IA.")}</p>`},
			{fieldtype: "Select", fieldname: "mode", label: __("Action"), default: "couleur", options: [
				{value: "couleur", label: __("Recolorer sans redessiner le SVG")},
				{value: "vectoriser", label: __("Vectoriser en couleurs (PNG / JPEG)")}], onchange: invalider},
			{fieldtype: "Data", fieldname: "couleur", label: __("Couleur exacte (HEX)"), default: this._palette()[0] || "#000000", depends_on: "eval:doc.mode==='couleur'", onchange: invalider},
			{fieldtype: "HTML", fieldname: "palette", depends_on: "eval:doc.mode==='couleur'"},
			{fieldtype: "Check", fieldname: "garder_blanc", label: __("Conserver les parties blanches"), default: 1, depends_on: "eval:doc.mode==='couleur'", onchange: invalider},
			{fieldtype: "Section Break", label: __("Si la source est une image PNG ou JPEG")},
			{fieldtype: "Select", fieldname: "couleurs", label: __("Nombre de couleurs du tracé"), options: "8\n16\n32\n64\n128", default: "16", onchange: invalider},
			{fieldtype: "Check", fieldname: "retirer_fond", label: __("Retirer le fond blanc avant le tracé"), default: 0, onchange: invalider},
			{fieldtype: "HTML", options: `<p class="text-muted small">${__("La vectorisation d’une image peut changer les petits détails ; elle ne récupère pas une précision absente de l’original. Un vrai SVG est conservé sans retracer ses courbes.")}</p>`},
			{fieldtype: "HTML", fieldname: "resultat"},
		], primary_action_label: __("Prévisualiser"), primary_action: async () => {
			if (en_cours) return;
			const choix = params();
			if (choix.mode === "couleur" && !this.normaliser_couleur(choix.couleur)) return frappe.msgprint(__("Saisissez une couleur au format #RRGGBB."));
			en_cours = true; candidat = null; invalider(); dlg.get_primary_btn().prop("disabled", true);
			try {
				const r = await frappe.call({method: "aquaworld_ia.emballage.pictos_images.preparer", args: {
					design: cible.design, code, source_url: cible.source, ...choix,
				}});
				if (JSON.stringify(choix) !== JSON.stringify(params())) return;
				candidat = r.message.candidat; parametres_candidat = JSON.stringify(choix);
				const $r = dlg.fields_dict.resultat.$wrapper;
				$r.html(`<div class="row">${[[__("Source"), source], [__("Résultat SVG"), candidat]].map(([titre, url]) => `<div class="col-6 text-center"><strong>${titre}</strong><div style="background:repeating-conic-gradient(#eee 0% 25%,white 0% 50%) 50%/16px 16px;border:1px solid #ddd;margin:8px 0"><img src="${esc(url || "")}" alt="${titre}" style="width:100%;height:190px;object-fit:contain;padding:8px"></div></div>`).join("")}</div>
					<p class="small">${r.message.trace ? __("Image retracée : vérifiez le résultat à grande taille.") : __("Source vectorielle : courbes et textes conservés.")}</p>
					${(r.message.avertissements || []).map(s => `<p class="small text-muted">${esc(s)}</p>`).join("")}
					<div class="se-btns"><button class="btn btn-primary btn-sm" data-appliquer-picto>${__("Appliquer à cette zone")}</button>
					<a class="btn btn-default btn-sm" href="${esc(candidat)}" download target="_blank" rel="noopener">${__("Télécharger SVG")}</a></div>`);
				$r.find("[data-appliquer-picto]").on("click", async e => {
					if (!candidat || parametres_candidat !== JSON.stringify(params())) return;
					$(e.currentTarget).prop("disabled", true);
					try { await this.appliquer_variante_picto(cible, candidat); dlg.hide(); }
					catch (e) { frappe.msgprint(this._msg(e)); }
					finally { $r.find("[data-appliquer-picto]").prop("disabled", false); }
				});
			} catch (e) { frappe.msgprint(this._msg(e)); }
			finally { en_cours = false; dlg.get_primary_btn().prop("disabled", false); }
		}});
		const $p = dlg.fields_dict.palette.$wrapper;
		$p.html(`<div class="se-btns"><input type="color" data-picto-teinte value="${esc(this._palette()[0] || "#000000")}" aria-label="${__("Choisir une couleur")}">
			<button class="btn btn-xs btn-default" data-picto-pipette>${__("Pipette / image")}</button>
			${this._palette().map(c => `<button type="button" data-picto-palette="${c}" title="${c}" aria-label="${c}" style="background:${c};width:24px;height:24px;border:1px solid #aaa;border-radius:50%"></button>`).join("")}</div>`);
		$p.find("[data-picto-teinte]").on("input change", e => dlg.set_value("couleur", e.currentTarget.value));
		$p.find("[data-picto-palette]").on("click", e => dlg.set_value("couleur", e.currentTarget.dataset.pictoPalette));
		$p.find("[data-picto-pipette]").on("click", () => this.choisir_couleur({source_url: source, label_action: __("Utiliser cette couleur"), on_choisir: c => dlg.set_value("couleur", c)}));
		dlg.get_field("couleur").$input.on("input", invalider).on("change", () => {
			const c = this.normaliser_couleur(dlg.get_value("couleur"));
			if (c) $p.find("[data-picto-teinte]").val(c);
		});
		dlg.show();
	}

	ouvrir_liste_pictos() {
		this.etape = 2; this.rendre_etats_etapes();
		const $liste = this.$root.find('[data-liste="pictogrammes"]');
		$liste.parents("details").prop("open", true);
		$liste[0]?.scrollIntoView({block: "center", behavior: "smooth"});
	}

	async choisir_pictos_zone() {
		const design = this.nom, face = this.epinglee, indice = this.zone_sel;
		try { await this.attendre_sauvegardes(); }
		catch (e) { frappe.msgprint(this._msg(e)); return; }
		if (this.nom !== design || this.epinglee !== face || this.zone_sel !== indice || !this.data.peut_ecrire) return;
		const f = this.data.apercu?.faces?.find(f => f.code === face), z = f?.zones?.[indice];
		if (z?.zone !== "pictos") return;
		const cible = {design, face, indice, revision: this.d.modified}, catalogue = this.pictos_du_design()
			.map(p => ({...p, url: z.pictos_images?.[p.code] || p.url})), esc = this._esc;
		let suivre = this.pictos_selection_zone(z) === null;
		let disposition = this.disposition_pictos(z);
		const choisis = new Set(this.pictos_effectifs_zone(z).map(p => p.code));
		const dlg = new frappe.ui.Dialog({title: __("Pictogrammes · {0} · zone {1}", [f.libelle, indice + 1]), size: "large",
			fields: [{fieldtype: "HTML", fieldname: "selection", options: `<div class="se-choix-pictos">
				<p>${esc(this.aide_faces_pictos(f))}</p>
				<p class="text-muted small">${__("Cochez les images à afficher dans ce contenant. Tout décocher laisse cette zone vide.")}</p>
				${this.commandes_disposition_pictos(z)}
				<div class="se-btns"><button type="button" class="btn btn-xs btn-default" data-pictos-tout>${__("Tout cocher")}</button>
					<button type="button" class="btn btn-xs btn-default" data-pictos-vide>${__("Tout décocher")}</button>
					<button type="button" class="btn btn-xs btn-default" data-pictos-suivre>${__("Suivre Contenus")}</button></div>
				<p class="text-muted small" data-pictos-resume aria-live="polite"></p>
				<div class="se-pictos-grille">${catalogue.map(p => `<label class="se-picto-choix"><input type="checkbox" data-picto-zone="${esc(p.code)}" ${choisis.has(p.code) ? "checked" : ""}>
					${p.url ? `<img src="${esc(p.url)}" alt="">` : ""}<span>${esc(p.libelle || p.code)}<small>${esc(p.categorie || "")}</small></span></label>`).join("")}</div>
				${catalogue.length ? "" : `<p>${__("Ajoutez d’abord des pictogrammes ou vos images de certification dans Contenus.")}</p>`}
				<button type="button" class="btn btn-xs btn-default" data-pictos-bibliotheque>${__("Gérer la liste dans Contenus")}</button></div>`}],
			primary_action_label: __("Appliquer à cette zone"), primary_action: async () => {
				const codes = dlg.$wrapper.find("[data-picto-zone]:checked").map((_i, el) => el.getAttribute("data-picto-zone")).get();
				dlg.get_primary_btn().prop("disabled", true);
				try { await this.appliquer_pictos_zone(cible, suivre ? null : codes, disposition); dlg.hide(); }
				catch (e) { frappe.msgprint(this._msg(e)); }
				finally { dlg.get_primary_btn().prop("disabled", false); }
			}});
		const $b = dlg.$wrapper, resumer = () => {
			const n = $b.find("[data-picto-zone]:checked").length;
			$b.find("[data-pictos-resume]").text(suivre ? __("Suit Contenus : {0} pictogramme(s), hors tampons.", [n]) : __("Sélection propre à cette zone : {0} pictogramme(s).", [n]));
		};
		$b.find("[data-pictos-disposition]").on("click", e => {
			disposition = e.currentTarget.dataset.pictosDisposition;
			$b.find("[data-pictos-disposition]").each((_i, el) => {
				const actif = el.dataset.pictosDisposition === disposition;
				$(el).toggleClass("btn-primary", actif).toggleClass("btn-default", !actif).attr("aria-pressed", String(actif));
			});
		});
		$b.find("[data-picto-zone]").on("change", () => { suivre = false; resumer(); });
		$b.find("[data-pictos-tout]").on("click", () => { suivre = false; $b.find("[data-picto-zone]").prop("checked", true); resumer(); });
		$b.find("[data-pictos-vide]").on("click", () => { suivre = false; $b.find("[data-picto-zone]").prop("checked", false); resumer(); });
		$b.find("[data-pictos-suivre]").on("click", () => {
			suivre = true;
			$b.find("[data-picto-zone]").each((_i, el) => { el.checked = catalogue.find(p => p.code === el.getAttribute("data-picto-zone"))?.categorie !== "Tampon"; });
			resumer();
		});
		$b.find("[data-pictos-bibliotheque]").on("click", () => { dlg.hide(); this.ouvrir_liste_pictos(); });
		dlg.show(); resumer();
	}

	async appliquer_pictos_zone(cible, selection, disposition) {
		await this.attendre_sauvegardes();
		if (this.nom !== cible.design || this.d.modified !== cible.revision)
			throw new Error(__("Le design a changé. Rouvrez le choix des pictogrammes pour cette zone."));
		const f = this.data.apercu?.faces?.find(f => f.code === cible.face);
		if (f?.zones?.[cible.indice]?.zone !== "pictos") throw new Error(__("Cette zone n’existe plus. Sélectionnez-la à nouveau."));
		const disponibles = new Set(this.pictos_du_design().map(p => p.code));
		const zones = f.zones.map((z, i) => {
			const out = this.zone_a_enregistrer(z);
			if (i === cible.indice) {
				delete out.pictos; delete out.pictos_mode;
				if (selection !== null) { out.pictos_mode = "selection"; out.pictos = [...new Set(selection)].filter(c => disponibles.has(c)); }
				if (disposition !== undefined) {
					delete out.pictos_disposition;
					if (disposition === "vertical") out.pictos_disposition = "vertical";
				}
			}
			return out;
		}).filter((_z, i) => !f.zones[i].auto); // Conserver les photos automatiques en arrière-plan.
		await this.enregistrer({mise_en_page: {...this.mep, [cible.face]: zones}}, cible.design);
	}
}
