// Responsabilité : etat du studio emballage.
class StudioEtat {
	depuis_route() {
		const route = frappe.get_route();
		const nom = (route[1] && decodeURIComponent(route[1])) || (frappe.route_options && frappe.route_options.design);
		frappe.route_options = null;
		if (nom && nom !== this.nom) this.charger(nom);
		else if (!nom && !this.nom) this.choisir_recent();
	}

	async choisir_recent() {
		const r = await frappe.call({ method: "aquaworld_ia.emballage.studio.liste", args: { limite: 1 } });
		const l = (r.message || [])[0];
		if (l) frappe.set_route("studio-emballage", l.name);
		else this.$corps.html(`<div class="se-vide">${__("Aucun design : créez-en un avec « Nouveau design ».")}</div>`);
	}

	async charger(nom) {
		this._glissement_zone?.annuler(false);
		this.nom = nom;
		const requete = this._chargement = (this._chargement || 0) + 1;
		this.arreter_suivi();
		try {
			const r = await frappe.call({ method: "aquaworld_ia.emballage.studio.charger", args: { design: nom } });
			if (requete !== this._chargement) return;
			this.data = Object.assign({}, this.data, r.message);
		} catch (e) {
			if (requete !== this._chargement) return;
			this.$corps.html(`<div class="se-vide">${this._esc(this._msg(e))}</div>`);
			return;
		}
		this.d = this.data.doc;
		this._lire_mep();
		this.etape = this._etape_par_defaut();
		this.onglet = this._onglet_par_defaut();
		this.rendre();
		if (this.data.etat && (this.data.etat.bloque || this.d.statut === "Variantes en cours")) this.suivre();
	}

	async recharger() {
		const design = this.nom;
		await this.attendre_sauvegardes();
		if (design !== this.nom) return;
		const version = this._versions_enreg?.get(design) || 0;
		const r = await frappe.call({ method: "aquaworld_ia.emballage.studio.charger", args: { design, catalogues: 0 } });
		if (design !== this.nom || version !== (this._versions_enreg?.get(design) || 0)) return;
		this._retour_enregistrement = {design, version, message: r.message, complet: true};
		this.appliquer_retour_enregistrement();
	}

	_lire_mep() {
		try { this.mep = JSON.parse(this.d.mise_en_page || "{}") || {}; } catch (e) { this.mep = {}; }
	}

	// Les enregistrements partent l'un après l'autre : deux enregistrements simultanés de la même fiche
	// (police du bloc puis sa taille, frappe dans l'éditeur…) faisaient échouer le second
	// (« document modifié entre-temps »).
	enregistrer(valeurs, design = this.nom) {
		// Chaque requête garde les valeurs présentes au clic, même si le geste suivant les modifie.
		valeurs = JSON.parse(JSON.stringify(valeurs));
		this._versions_enreg ||= new Map();
		const version = (this._versions_enreg.get(design) || 0) + 1;
		this._versions_enreg.set(design, version);
		this._enregistrements ||= new Map(); this._erreurs_enreg ||= new Map();
		this._enregistrements.set(design, (this._enregistrements.get(design) || 0) + 1);
		this.maj_sauvegarde();
		const tache = (this._file_enreg || Promise.resolve()).catch(() => {}).then(() => this._enregistrer(valeurs, design, version))
			.then(() => {
				const erreurs = this._erreurs_enreg.get(design) || {};
				Object.keys(valeurs).forEach(champ => delete erreurs[champ]);
				if (!Object.keys(erreurs).length) this._erreurs_enreg.delete(design);
			})
			.catch(e => { this._erreurs_enreg.set(design, Object.assign({}, this._erreurs_enreg.get(design), valeurs)); throw e; })
			.finally(() => { this._enregistrements.set(design, this._enregistrements.get(design) - 1); this.maj_sauvegarde(); });
		this._file_enreg = tache;
		return tache;
	}

	async _enregistrer(valeurs, design, version) {
		const r = await frappe.call({ method: "aquaworld_ia.emballage.studio.enregistrer",
			args: { design, valeurs }, freeze: false });
		if (design !== this.nom) return;
		if (version !== undefined && version !== this._versions_enreg?.get(design)) return;
		this._retour_enregistrement = {design, version, message: r.message};
		this.appliquer_retour_enregistrement();
	}

	appliquer_retour_enregistrement() {
		const r = this._retour_enregistrement;
		if (!r) return;
		if (r.design !== this.nom || (r.version !== undefined && r.version !== (this._versions_enreg?.get(r.design) || 0))) {
			this._retour_enregistrement = null; return;
		}
		// Le SVG doit rester attaché pendant tout le geste : sa matrice donne les mm du pointeur.
		if (this._glissement_zone) return;
		this._retour_enregistrement = null;
		const saisie = this.capturer_saisie_position();
		this.data = Object.assign({}, this.data, r.message); this.d = this.data.doc; this._lire_mep();
		const gauche = this._gauche_a_redessiner?.delete(r.design);
		if (r.complet) this.rendre();
		else {
			this.rendre_scene(); this.rendre_droite(); this.rendre_barre(); this.rendre_etats_etapes(); this.rendre_avert_lignes(); this.rendre_export();
			if (gauche) this.rendre_gauche();
		}
		this.restaurer_saisie_position(saisie);
	}
	// (la scène Images lit this.data.images, rechargé par enregistrer())

	sauvegarde_differee(design) {
		this._saisies ||= new Map();
		if (!this._saisies.has(design)) {
			const saisie = { valeurs: {} };
			saisie.vider = () => {
				if (!Object.keys(saisie.valeurs).length) return;
				const lot = saisie.valeurs; saisie.valeurs = {};
				return this.modifier(lot, false, design);
			};
			const envoyer = frappe.utils.debounce(saisie.vider, 500);
			saisie.ajouter = (champ, valeur) => { saisie.valeurs[champ] = valeur; this.maj_sauvegarde(); envoyer(); };
			this._saisies.set(design, saisie);
		}
		return this._saisies.get(design).ajouter;
	}

	async attendre_sauvegardes() {
		for (const saisie of this._saisies?.values() || []) await saisie.vider();
		await this._file_enreg;
		if (this._erreurs_enreg?.get(this.nom)) throw new Error(__("Une modification n’a pas été enregistrée. Corrigez-la avant de continuer."));
	}

	maj_sauvegarde() {
		if (!this.$barre) return;
		const attente = Object.keys(this._saisies?.get(this.nom)?.valeurs || {}).length || this._enregistrements?.get(this.nom);
		const erreur = this._erreurs_enreg?.get(this.nom);
		this.$barre.find('[data-role="sauvegarde"]').text(erreur ? __("Échec de sauvegarde") : attente ? __("Enregistrement…") : __("Enregistré"))
			.toggleClass("text-danger", !!erreur);
		this.$barre.find('[data-role="reessayer-sauvegarde"]').toggle(!!erreur);
	}

	async reessayer_sauvegarde() {
		const valeurs = this._erreurs_enreg?.get(this.nom);
		if (valeurs) {
			try { await this.enregistrer({ ...valeurs }); }
			catch (e) { frappe.msgprint(this._msg(e)); }
		}
	}

	// Les dimensions qu'exige la forme (L, H, P, R → champs) : un sac plat n'a pas de P, un sac
	// agrafé a un repli R plus petit que H.
	_dims_ok() {
		const d = this.d, t = (this.data.types || []).find((x) => x.type === d.type_boite);
		const requises = (t && t.requises) || ["L", "H", "P"];
		if (!requises.every((k) => d[StudioEmballage.CHAMPS_DIMS[k]] > 0)) return false;
		return !requises.includes("R") || +d.repli_mm < +d.hauteur_mm;
	}

	_etape_par_defaut() {
		if (!this._dims_ok()) return 1;
		if (!(this.d.nom_produit || this.d.article)) return 2;
		return this.data.exports?.pdf === "a_jour" ? 4 : 3;
	}

	_onglet_par_defaut() { return this.data.exports?.pdf === "a_jour" ? "artwork" : "plan"; }

	async modifier(valeurs, redessiner_gauche, design = this.nom) {
		if (redessiner_gauche) { this._gauche_a_redessiner ||= new Set(); this._gauche_a_redessiner.add(design); }
		try {
			await this.enregistrer(valeurs, design);
		} catch (e) {
			frappe.msgprint(this._msg(e));
			return;
		}
	}

	suivre() {
		this.arreter_suivi();
		const $p = this.$root.find('[data-role="progress"]').show(), $t = this.$root.find('[data-role="progress-txt"]').show();
		const afficher = (e) => {
			if (!e || (e.nom && e.nom !== this.nom)) return;
			$p.find("div").css("width", (e.avancement || 0) + "%");
			$t.text(e.etape || "");
			this.$root.find('[data-role="attente-txt"]').text(e.etape || "");
			if (e.fin || e.avancement >= 100) { this.arreter_suivi(); this.recharger(); }
		};
		this._rt = afficher;
		frappe.realtime.on("aqia_emballage", afficher);
		this._minuteur = setInterval(async () => {
			const r = await frappe.call({ method: "aquaworld_ia.emballage.job.etat_design", args: { design: this.nom } });
			const e = r.message || {};
			if (e.statut && e.statut !== "en cours") { this.arreter_suivi(); this.recharger(); } else afficher(e);
		}, 4000);
	}

	arreter_suivi() {
		if (this._rt) frappe.realtime.off("aqia_emballage", this._rt);
		if (this._minuteur) clearInterval(this._minuteur);
		this._rt = null; this._minuteur = null; this._mockup_en_cours = false;
		this.$root.find('[data-role="progress"], [data-role="progress-txt"]').hide();
	}

}
