// Choix de couleurs commun à la palette et aux ateliers IA.
class StudioCouleurs {
	normaliser_couleur(valeur) {
		let c = String(valeur || "").trim().toLowerCase().replace(/^#/, "");
		if (/^[0-9a-f]{3}$/.test(c)) c = [...c].map(x => x + x).join("");
		return /^[0-9a-f]{6}$/.test(c) ? "#" + c : null;
	}

	sources_pipette(source_url) {
		const sources = new Map(), ajouter = (url, libelle) => { if (url && !sources.has(url)) sources.set(url, {url, libelle}); };
		ajouter(source_url, __("Image sélectionnée"));
		ajouter(this.d.logo || this.data.visuels?.logo, __("Logo du design"));
		ajouter(this.d.photo_produit || this.data.visuels?.photo, __("Photo du produit"));
		ajouter(this.d.image_fond, __("Image de fond"));
		for (const face of this.data.apercu?.faces || []) for (const z of face.zones || []) {
			if (z.logo) ajouter(z.logo, __("Logo · {0}", [face.libelle]));
		}
		for (const im of this.data.images || []) ajouter(im.file_url, im.file_name || im.genre || __("Image"));
		return [...sources.values()];
	}

	choisir_couleur(options = {}) {
		const sources = this.sources_pipette(options.source_url);
		return this.visionneuse(sources[0]?.url || "", options.titre || __("Choisir une couleur à la pipette"), {...options, sources});
	}

	async ouvrir_palette() {
		const design = this.nom;
		try {
			await this.attendre_sauvegardes();
			if (this.nom !== design) return;
			return this.choisir_couleur({titre: __("Ajouter une couleur à la palette"), label_action: __("Ajouter à la palette"),
				on_choisir: couleur => this.ajouter_a_la_palette(couleur, design)});
		} catch (e) { frappe.msgprint(this._msg(e)); }
	}

	changer_palette(couleur, retirer = false, design = this.nom) {
		// Les ajouts successifs attendent les saisies et se fusionnent sans perdre une couleur.
		const operation = async () => {
			const c = this.normaliser_couleur(couleur);
			if (!c) throw new Error(__("Saisissez une couleur au format #RRGGBB."));
			if (this.nom !== design) throw new Error(__("Rouvrez le design concerné pour modifier sa palette."));
			await this.attendre_sauvegardes();
			if (this.nom !== design) throw new Error(__("Rouvrez le design concerné pour modifier sa palette."));
			const cs = this._palette();
			if (retirer ? !cs.includes(c) : cs.includes(c)) return;
			const ouvert = this.$root?.find('[data-champ="palette"]').parents("details").prop("open");
			const palette = (retirer ? cs.filter(x => x !== c) : cs.concat(c)).join(", ");
			await this.enregistrer({palette}, design);
			if (this.nom === design) {
				this.rendre_gauche();
				if (ouvert) this.$root.find('[data-champ="palette"]').parents("details").prop("open", true);
				frappe.show_alert({message: retirer ? __("Couleur retirée de la palette.") : __("{0} ajoutée à la palette du design.", [c]), indicator: "green"});
			}
		};
		this._file_palette = (this._file_palette || Promise.resolve()).catch(() => {}).then(operation);
		return this._file_palette;
	}

	champs_couleurs_ia(options = {}) {
		return [
			{fieldtype: "Data", fieldname: "couleur_cible", label: __("Couleur demandée à l’IA (HEX, facultatif)"),
				default: options.couleur_cible || "", placeholder: "#008bcd"},
			{fieldtype: "HTML", fieldname: "outils_couleur"},
			{fieldtype: "Data", fieldname: "element_couleur", label: __("Élément à recolorer"), default: options.element_couleur || "",
				depends_on: "eval:doc.couleur_cible", description: __("Ex. le texte du logo, son symbole, le fond. Vide = suivre votre consigne.")},
			{fieldtype: "Check", fieldname: "utiliser_palette", label: __("Utiliser aussi la palette du design pour les autres couleurs modifiées"),
				default: options.utiliser_palette ? 1 : 0},
			{fieldtype: "HTML", options: `<p class="small text-muted">${__("Le code HEX est transmis à l’IA, qui peut produire de légères variations. Pour une couleur uniforme exacte, utilisez la recoloration du logo sans IA.")}</p>`},
		];
	}

	lier_couleurs_ia(dlg, options = {}) {
		const $c = dlg.get_field("outils_couleur").$wrapper;
		$c.html(`<div class="se-btns" style="align-items:center;flex-wrap:wrap">
			<input type="color" data-couleur-libre value="${this.normaliser_couleur(options.couleur_cible) || "#008bcd"}" aria-label="${__("Choisir une couleur")}" style="width:44px;height:30px;padding:2px">
			<button class="btn btn-xs btn-default" data-pipette-ia>${__("Pipette / image")}</button>
			<button class="btn btn-xs btn-default" data-effacer-couleur>${__("Sans couleur imposée")}</button></div>
			<div class="small text-muted" style="margin-top:8px">${__("Palette du design : cliquez une couleur pour la reprendre.")}</div>
			<div class="se-palette">${this._palette().map(c => `<button type="button" class="se-pastille" style="background:${c};padding:0" data-couleur-ia="${c}" title="${c}" aria-label="${c}"></button>`).join("") || `<span class="small text-muted">${__("Aucune couleur enregistrée : ajoutez-en dans Mise en page → Palette.")}</span>`}</div>
			<p class="small text-danger" data-erreur-couleur hidden>${__("Couleur invalide : utilisez #RRGGBB, par exemple #008bcd.")}</p>`);
		const choisir = c => dlg.set_value("couleur_cible", c);
		$c.find("[data-couleur-libre]").on("input change", e => choisir(e.currentTarget.value));
		$c.find("[data-couleur-ia]").on("click", e => choisir($(e.currentTarget).attr("data-couleur-ia")));
		$c.find("[data-effacer-couleur]").on("click", () => choisir(""));
		$c.find("[data-pipette-ia]").on("click", () => this.choisir_couleur({source_url: options.source_url,
			label_action: __("Utiliser cette couleur pour l’IA"), on_choisir: choisir}));
		const actualiser = () => {
			const valeur = dlg.get_value("couleur_cible") || "", c = this.normaliser_couleur(valeur);
			if (c) $c.find("[data-couleur-libre]").val(c);
			$c.find("[data-erreur-couleur]").prop("hidden", !valeur.trim() || !!c);
		};
		dlg.get_field("couleur_cible").$input.on("input change", actualiser);
		actualiser();
	}
}
