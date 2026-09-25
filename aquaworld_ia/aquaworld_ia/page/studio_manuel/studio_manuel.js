// Studio manuel — la page plein écran pour traduire un manuel page par page (demande utilisateur
// 24/09/2026 : « un studio où je change page par page, en gardant l'image du manuel d'origine »).
//
// Gauche : les pages (vignettes de l'original). Centre : la page telle qu'elle sortira dans le PDF de
// la langue, avec ses blocs à cliquer, déplacer, agrandir ; ses illustrations ; ses cases ajoutées.
// Droite : l'élément sélectionné (texte anglais, traduction, taille, traitement, IA).
// Tout ce qui est modifié va dans l'édition de la langue (manuels/edition.py) ; le PDF de la fiche et
// celui du studio sortent du même moteur (manuels/rendu.py).
frappe.pages["studio-manuel"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({ parent: wrapper, title: __("Studio manuel"), single_column: true });
	wrapper.studio = new StudioManuel(wrapper);
};
frappe.pages["studio-manuel"].on_page_show = function (wrapper) {
	if (wrapper.studio) wrapper.studio.depuis_route();
};

class StudioManuel {
	constructor(wrapper) {
		this.page = wrapper.page;
		this.$root = $(wrapper).find(".layout-main-section");
		this.$root.append(frappe.render_template("studio_manuel", {}));
		this.$barre = this.$root.find('[data-role="barre"]');
		this.$corps = this.$root.find('[data-role="corps"]');
		this.no = 0; this.zoom = "ajuster"; this.sel = null; this.original = false; this.mode = "place"; this.source_en = false;
		this.page.set_primary_action(__("Nouveau manuel"), () => this.nouveau(), "add");
		this.depuis_route();
	}

	// ─── chargement ─────────────────────────────────────────────────────────────
	depuis_route() {
		const route = frappe.get_route();
		const nom = (route[1] && decodeURIComponent(route[1])) || (frappe.route_options && frappe.route_options.manuel);
		const langue = frappe.route_options && frappe.route_options.langue;
		frappe.route_options = null;
		if (nom && nom !== this.nom) this.charger(nom, langue);
		else if (!nom && !this.nom) this.choisir_recent();
	}

	async choisir_recent() {
		const r = await frappe.call({ method: "aquaworld_ia.manuels.studio.liste", args: { limite: 1 } });
		const l = (r.message || [])[0];
		if (l) frappe.set_route("studio-manuel", l.name);
		else this.$corps.html(`<div class="sm-vide">${__("Aucun manuel : « Nouveau manuel » en haut à droite, avec le PDF anglais du fabricant.")}</div>`);
	}

	// Un manuel neuf depuis le studio : article, PDF, titre, langues ; puis le studio s'ouvre dessus.
	nouveau() {
		const dlg = new frappe.ui.Dialog({ title: __("Nouveau manuel à traduire"),
			fields: [
				{ fieldtype: "Link", options: "Item", fieldname: "article", label: __("Article"), reqd: 1 },
				{ fieldtype: "Data", fieldname: "titre", label: __("Titre"), description: __("Sinon, le nom de l'article.") },
				{ fieldtype: "Attach", fieldname: "pdf", label: __("PDF du manuel (anglais)"), reqd: 1,
				  description: __("Un PDF texte : les scans n'ont pas de blocs à traduire (on peut quand même y poser des cases de texte).") },
				{ fieldtype: "HTML", fieldname: "langues_html", options: `<label style="font-size:11px;text-transform:uppercase;color:#6b7683">${__("Langues à préparer")}</label>
					<div class="sm-langues" data-role="choix-langues"></div>` },
			],
			primary_action_label: __("Créer et ouvrir"),
			primary_action: async (v) => {
				const langues = dlg.$wrapper.find('[data-role="choix-langues"] .l.on').map((_i, e) => $(e).attr("data-code")).get();
				let r;
				try {
					r = await frappe.call({ method: "aquaworld_ia.manuels.studio.nouveau", args: { article: v.article, titre: v.titre, pdf: v.pdf, langues }, freeze: true, freeze_message: __("Analyse du PDF…") });
				} catch (e) { frappe.msgprint(this._msg(e)); return; }
				dlg.hide();
				if (!r.message.texte_extractible) frappe.msgprint(__("Ce PDF n'a pas de texte extractible (scan ou contours) : la traduction IA n'est pas possible, mais vous pouvez poser des cases de texte sur chaque page."));
				frappe.set_route("studio-manuel", r.message.name);
			} });
		dlg.show();
		frappe.call({ method: "frappe.client.get_list", args: { doctype: "Aquaworld IA Langue", filters: { actif: 1 }, fields: ["name", "libelle"], order_by: "name" } }).then((r) => {
			const $c = dlg.$wrapper.find('[data-role="choix-langues"]');
			$c.html((r.message || []).filter((l) => l.name !== "en").map((l) => `<span class="l on" data-code="${this._esc(l.name)}">${this._esc(l.libelle || l.name)}</span>`).join(""));
			$c.find(".l").on("click", (e) => $(e.currentTarget).toggleClass("on"));
		});
	}

	async charger(nom, langue) {
		this.nom = nom; this.no = 0; this.sel = null; this.vignettes = null; this.trad = {}; this.edition = this._edition_vide();
		this.arreter_suivi();
		try {
			const r = await frappe.call({ method: "aquaworld_ia.manuels.studio.charger", args: { manuel: nom } });
			this.data = r.message;
		} catch (e) {
			this.$corps.html(`<div class="sm-vide">${this._esc(this._msg(e))}</div>`);
			return;
		}
		this.langue = (this.data.langues.find((l) => l.langue === langue) || this.data.langues[0] || {}).langue || null;
		this.rendre();
		if (this.langue) await this.charger_langue(this.langue);
		else this.rendre_page();
		this.charger_vignettes();
		if (this.data.etat && this.data.etat.bloque) this.suivre();
	}

	async recharger() {
		const r = await frappe.call({ method: "aquaworld_ia.manuels.studio.charger", args: { manuel: this.nom } });
		this.data = r.message;
		if (this.langue && !this.data.langues.some((l) => l.langue === this.langue)) this.langue = (this.data.langues[0] || {}).langue || null;
		this.rendre_barre(); this.rendre_gauche();
		if (this.langue) await this.charger_langue(this.langue);
	}

	async charger_langue(code) {
		this.langue = code;
		const r = await frappe.call({ method: "aquaworld_ia.manuels.studio.langue", args: { manuel: this.nom, langue: code } });
		this.trad = r.message.traductions || {}; this.edition = this._lire_edition(r.message.edition); this.infos = r.message.infos || {};
		const i = this.data.langues.findIndex((l) => l.langue === code);
		if (i >= 0) this.data.langues[i] = r.message.ligne;
		this.sel = null;
		this.rendre_barre(); this.rendre_gauche();
		await this.rendre_page();
	}

	async charger_vignettes() {
		try {
			const r = await frappe.call({ method: "aquaworld_ia.manuels.studio.vignettes", args: { manuel: this.nom } });
			this.vignettes = r.message || [];
			this.rendre_gauche();
		} catch (e) { /* les vignettes sont un confort */ }
	}

	_edition_vide() { return { textes: {}, blocs: {}, libres: [], images: {} }; }
	_lire_edition(e) { return Object.assign(this._edition_vide(), e || {}); }

	// L'édition part entière à chaque changement, un enregistrement après l'autre. Chaque changement
	// local porte un numéro : un enregistrement dépassé par un changement plus récent ne part pas
	// (le suivant emporte tout), et sa réponse ne remplace jamais un état plus récent — sinon la
	// réponse d'un vieil enregistrement effaçait la taille ou la case modifiée entre-temps (vu au
	// test navigateur du 24/09/2026).
	enregistrer(redessiner = true) {
		this._version = (this._version || 0) + 1;
		const v = this._version;
		const tache = (this._file || Promise.resolve()).catch(() => {}).then(async () => {
			if (v !== this._version) return;
			const r = await frappe.call({ method: "aquaworld_ia.manuels.studio.enregistrer",
				args: { manuel: this.nom, langue: this.langue, edition: this.edition }, freeze: false });
			if (v === this._version) this.edition = this._lire_edition(r.message.edition);
		});
		this._file = tache;
		if (redessiner) tache.then(() => this.rendre_page_differee());
		return tache;
	}

	rendre_page_differee() {
		clearTimeout(this._minuteur_page);
		this._minuteur_page = setTimeout(() => this.rendre_page(), 250);
	}

	// ─── rendu ──────────────────────────────────────────────────────────────────
	rendre() {
		this.rendre_barre();
		this.$corps.html(`<div class="sm-grid">
			<div class="sm-col"><div class="sm-pages" data-role="pages"></div></div>
			<div class="sm-col"><div class="sm-centre"><div class="sm-outils" data-role="outils"></div><div class="sm-scene" data-role="scene"></div></div></div>
			<div class="sm-col sm-droite" data-role="droite"></div></div>`);
		this.rendre_gauche();
	}

	rendre_barre() {
		const d = this.data.doc, langues = this.data.langues || [];
		const ligne = langues.find((l) => l.langue === this.langue) || {};
		const chip = { "Terminé": "ok", "En cours": "encours", "Échec": "echec", "Partiel": "encours" }[d.statut] || "";
		const dispo = this.data.langues_dispo || [];
		this.$barre.html(`
			<select data-role="selecteur"><option value="${this._esc(d.name)}">${this._esc(d.titre || d.article || d.name)} · ${this._esc(d.name)}</option></select>
			<span class="sm-titre">${this._esc(d.titre || d.article || "")}</span>
			<span class="sm-chip ${chip}">${this._esc(d.statut || "")}</span>
			<span class="sm-chip">${__("{0} pages", [d.pages || 0])}</span>
			<span class="sm-langues" data-role="langues">${langues.map((l) => `<span class="l ${l.langue === this.langue && !this.multi ? "on" : ""}" data-langue="${this._esc(l.langue)}" title="${this._esc(l.statut || "")}">${this._esc(l.libelle || l.langue)}</span>`).join("")}
				${langues.length > 1 ? `<span class="l ${this.multi ? "on" : ""}" data-role="toutes-langues" title="${__("Mode Reconstruit : chaque bloc de la page dans toutes les langues à la fois")}">${__("Toutes")}</span>` : ""}
				${dispo.length ? `<span class="l ajout" data-role="ajouter-langue">＋ ${__("langue")}</span>` : ""}</span>
			<a class="btn btn-xs btn-default" href="/app/manuel-article/${encodeURIComponent(d.name)}">${__("Fiche")}</a>
			${this.langue ? `<button class="btn btn-xs btn-default" data-role="traduire-tout" title="${__("Traduire par IA tous les blocs du manuel dans cette langue (les corrections faites ici sont gardées)")}">🤖 ${__("Traduire tout")}</button>
			<button class="btn btn-xs btn-primary" data-role="composer" title="${__("Produire le PDF de cette langue avec tout ce qui est fait ici, sans appel IA")}">📄 ${__("Générer le PDF")}</button>
			${ligne.fichier ? `<a class="btn btn-xs btn-default" href="${this._esc(ligne.fichier)}" target="_blank">⬇ ${__("Télécharger")}</a>` : ""}` : ""}
			${langues.some((l) => l.statut === "Terminé" && l.fichier) ? `<button class="btn btn-xs btn-default" data-role="combiner" title="${__("Un seul PDF : le manuel source puis chaque langue traduite, un signet par langue. Sans IA.")}">📚 ${__("PDF toutes langues")}</button>` : ""}
			${d.pdf_combine ? `<a class="btn btn-xs btn-default" href="${this._esc(d.pdf_combine)}" target="_blank" title="${__("Le dernier PDF toutes langues généré")}">⬇ ${__("Toutes langues")}</a>` : ""}
			<span class="sm-cout">${__("Coût IA de ce manuel : {0} $", [((this.data.etat || {}).cout_document || 0).toFixed(3)])}</span>`);
		this.$barre.find('[data-role="combiner"]').on("click", () => this.combiner());
		const $sel = this.$barre.find('[data-role="selecteur"]');
		$sel.on("focus", async () => {
			if ($sel.data("charge")) return;
			const r = await frappe.call({ method: "aquaworld_ia.manuels.studio.liste", args: { limite: 30 } });
			$sel.html((r.message || []).map((l) => `<option value="${this._esc(l.name)}" ${l.name === d.name ? "selected" : ""}>${this._esc(l.titre || l.article || l.name)} · ${this._esc(l.name)} · ${this._esc(l.statut || "")}</option>`).join(""));
			$sel.data("charge", 1);
		}).on("change", () => frappe.set_route("studio-manuel", $sel.val()));
		this.$barre.find('[data-role="langues"] .l[data-langue]').on("click", (e) => { this.multi = false; this.charger_langue($(e.currentTarget).attr("data-langue")); });
		this.$barre.find('[data-role="toutes-langues"]').on("click", () => { this.multi = true; this.mode = "reconstruit"; this.source_en = false; this.rendre_barre(); this.rendre_page(); });
		this.$barre.find('[data-role="ajouter-langue"]').on("click", () => this.ajouter_langue());
		this.$barre.find('[data-role="traduire-tout"]').on("click", () => this.traduire_tout());
		this.$barre.find('[data-role="composer"]').on("click", () => this.composer());
	}

	rendre_gauche() {
		const $p = this.$corps.find('[data-role="pages"]');
		if (!$p.length) return;
		$p.html((this.data.pages || []).map((p) => {
			const ids = p.ids || [], faits = ids.filter((i) => this._statut(i) !== "non_traduit").length;
			const libres = this.edition.libres.filter((l) => l.page === p.no).length;
			const badges = [];
			if (p.image) badges.push(`<span class="b img" title="${__("Page image : sans texte à extraire, posez des cases de texte")}">🖼</span>`);
			if (p.ocr) badges.push(`<span class="b img" title="${__("Texte lu par OCR (pas de couche texte dans le PDF) : à relire")}">🔍</span>`);
			if (ids.length) badges.push(`<span class="b ${faits === ids.length ? "ok" : "reste"}" title="${__("{0} blocs sur {1} traduits ou traités", [faits, ids.length])}">${faits}/${ids.length}</span>`);
			if (libres) badges.push(`<span class="b ok" title="${__("cases ajoutées")}">+${libres}</span>`);
			const v = this.vignettes && this.vignettes[p.no];
			return `<div class="sm-pg ${p.no === this.no ? "on" : ""}" data-no="${p.no}">${v ? `<img src="${v}" alt="">` : `<div class="vide"></div>`}
				<div class="leg"><span>p. ${p.no + 1}</span>${badges.join("")}</div></div>`;
		}).join(""));
		$p.find(".sm-pg").on("click", (e) => this.aller(+$(e.currentTarget).attr("data-no")));
	}

	_statut(id) {
		const k = String(id), b = this.edition.blocs[k] || {};
		if (b.traitement === "anglais" || b.traitement === "efface") return b.traitement;
		if (this.edition.textes[k]) return "corrige";
		return this.trad[k] ? "traduit" : "non_traduit";
	}

	aller(no) {
		const total = (this.data.pages || []).length;
		if (no < 0 || no >= total || no === this.no) return;
		this.no = no; this.sel = null;
		this.$corps.find(".sm-pg").removeClass("on").filter(`[data-no="${no}"]`).addClass("on");
		this.rendre_page();
	}

	async rendre_page() {
		const $o = this.$corps.find('[data-role="outils"]'), $s = this.$corps.find('[data-role="scene"]');
		if (!this.langue) {
			$o.html(""); $s.html(`<div class="sm-vide">${__("Ajoutez une langue (bouton « ＋ langue » en haut) pour commencer.")}</div>`);
			this.rendre_droite(); return;
		}
		const jeton = (this._jeton = (this._jeton || 0) + 1);
		$s.css("opacity", 0.6);
		if (this.mode === "reconstruit") { await this.rendre_page_reconstruit(jeton); return; }
		let r;
		try {
			r = await frappe.call({ method: "aquaworld_ia.manuels.studio.page", args: { manuel: this.nom, langue: this.langue, no: this.no, original: this.original ? 1 : 0 } });
		} catch (e) { $s.css("opacity", 1).html(`<div class="sm-vide">${this._esc(this._msg(e))}</div>`); return; }
		if (jeton !== this._jeton) return;   // une page plus récente a été demandée entre-temps
		this.pg = r.message;
		this.rendre_outils();
		this.dessiner();
		// Pendant une saisie (traduction en cours de frappe), le panneau n'est pas reconstruit : on
		// perdrait le curseur à chaque enregistrement. Seule sa ligne d'état est rafraîchie.
		if (this._en_saisie()) this.maj_etat_panneau(); else this.rendre_droite();
		this.rendre_gauche();
		$s.css("opacity", 1);
	}

	_en_saisie() {
		const a = document.activeElement, d = this.$corps.find(".sm-droite")[0];
		return !!(a && d && d.contains(a) && /^(TEXTAREA|INPUT|SELECT)$/.test(a.tagName));
	}

	maj_etat_panneau() {
		const s = this.sel, $e = this.$corps.find(".sm-droite .sm-etat");
		if (!s || !$e.length || !this.pg) return;
		const st = ((this.pg.stats || {}).blocs || {})[String(s.id)];
		if (!st) return;
		$e.attr("class", "sm-etat " + (!st.place ? "alerte" : (st.echelle < 0.8 ? "reduit" : "")));
		$e.text(!st.place ? __("Non placé : le texte ne tient pas, même réduit. Agrandissez la boîte (coin) ou raccourcissez.")
			: (st.echelle < 1 ? __("Posé réduit à {0} %.", [Math.round(st.echelle * 100)]) : __("Posé à sa taille.")));
	}

	rendre_outils() {
		const $o = this.$corps.find('[data-role="outils"]'), total = (this.data.pages || []).length, pg = this.pg;
		const nb = pg.blocs.filter((b) => !b.pivote).length, non = pg.blocs.filter((b) => b.statut === "non_traduit" && b.traduisible && !b.pivote).length;
		$o.html(`
			${this._html_mode()}
			<button class="btn btn-xs btn-default" data-role="prec" ${this.no <= 0 ? "disabled" : ""}>◀</button>
			<span>${__("Page")}</span> <input type="number" min="1" max="${total}" value="${this.no + 1}" data-role="no"> <span>/ ${total}</span>
			<button class="btn btn-xs btn-default" data-role="suiv" ${this.no >= total - 1 ? "disabled" : ""}>▶</button>
			<span class="sep"></span>
			<select data-role="zoom"><option value="ajuster" ${this.zoom === "ajuster" ? "selected" : ""}>${__("Ajuster")}</option><option value="1" ${this.zoom === "1" ? "selected" : ""}>100 %</option><option value="1.5" ${this.zoom === "1.5" ? "selected" : ""}>150 %</option><option value="2" ${this.zoom === "2" ? "selected" : ""}>200 %</option></select>
			<label class="sm-check" style="margin:0"><input type="checkbox" data-role="original" ${this.original ? "checked" : ""}> ${__("Voir l'original")}</label>
			<span class="sep"></span>
			<button class="btn btn-xs btn-default" data-role="traduire-page" title="${__("Traduire par IA les blocs de cette page qui ne le sont pas encore")}">🤖 ${__("Traduire la page")}${non ? ` (${non})` : ""}</button>
			<button class="btn btn-xs btn-default" data-role="case-texte" title="${__("Une case de texte libre, posée sur la page (utile sur une page image)")}">＋ ${__("Case de texte")}</button>
			<button class="btn btn-xs btn-default" data-role="zone-image" title="${__("Une zone à redessiner par IA avec ses mots traduits")}">＋ ${__("Zone d'illustration")}</button>
			<span class="droite">${pg.image_page ? `🖼 ${__("page image")}` : __("{0} blocs", [nb])}${pg.ocr ? ` · <span title="${__("Pas de couche texte dans le PDF (lettres en contours ou scan) : texte lu par OCR, à relire")}">🔍 OCR</span>` : ""}${pg.stats && pg.stats.non_places && pg.stats.non_places.length ? ` · <span style="color:#b91c1c">${__("{0} non placés", [pg.stats.non_places.length])}</span>` : ""}</span>`);
		this._lier_mode($o);
		$o.find('[data-role="prec"]').on("click", () => this.aller(this.no - 1));
		$o.find('[data-role="suiv"]').on("click", () => this.aller(this.no + 1));
		$o.find('[data-role="no"]').on("change", (e) => this.aller(Math.min(total, Math.max(1, +e.target.value || 1)) - 1));
		$o.find('[data-role="zoom"]').on("change", (e) => { this.zoom = e.target.value; this.dessiner(); });
		$o.find('[data-role="original"]').on("change", (e) => { this.original = e.target.checked; this.rendre_page(); });
		$o.find('[data-role="traduire-page"]').on("click", () => this.traduire_page());
		$o.find('[data-role="case-texte"]').on("click", () => this.ajouter_libre("texte"));
		$o.find('[data-role="zone-image"]').on("click", () => this.ajouter_libre("image"));
	}

	// La page : l'image rendue par le moteur (le fond), et par-dessus un SVG en points PDF avec un
	// rectangle par bloc, case et illustration. Cliquer sélectionne ; glisser déplace ; la poignée agrandit.
	dessiner() {
		const $s = this.$corps.find('[data-role="scene"]'), pg = this.pg;
		if (!pg) return;
		const [W, H] = pg.format;
		const largeur = this.zoom === "ajuster" ? "100%" : `${Math.round(W * 96 / 72 * parseFloat(this.zoom))}px`;
		$s.html(`<div class="sm-page" style="width:${largeur};max-width:${this.zoom === "ajuster" ? "100%" : "none"}"><img src="${pg.png}" alt=""><svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg"></svg></div>`);
		const svg = $s.find("svg")[0], NS = "http://www.w3.org/2000/svg";
		const el = (tag, attrs, parent) => { const n = document.createElementNS(NS, tag); Object.entries(attrs).forEach(([k, v]) => n.setAttribute(k, v)); (parent || svg).appendChild(n); return n; };
		const point = (e) => { const pt = svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY; return pt.matrixTransform(svg.getScreenCTM().inverse()); };
		const POIGNEE = Math.max(4, W / 90), TRAIT = W / 600;
		const stats = (pg.stats && pg.stats.blocs) || {};
		const est_sel = (type, id) => this.sel && this.sel.type === type && String(this.sel.id) === String(id);

		// Un élément : rectangle + étiquette + (si mobile) poignée et glisser-déposer.
		const poser = (type, id, bbox, couleurs, opts) => {
			const z = { x: bbox[0], y: bbox[1], w: bbox[2] - bbox[0], h: bbox[3] - bbox[1] };
			const sel = est_sel(type, id);
			const r = el("rect", { class: "el" + (opts.mobile ? " mobile" : ""), x: z.x, y: z.y, width: z.w, height: z.h, fill: couleurs.fill, "fill-opacity": sel ? 0.22 : couleurs.op,
				stroke: sel ? "#dc2626" : couleurs.stroke, "stroke-width": sel ? TRAIT * 2.2 : TRAIT * 1.2, "stroke-dasharray": couleurs.tirets || "none" });
			if (opts.etiquette) {
				const t = el("text", { class: "etiq", x: z.x + TRAIT * 3, y: z.y - TRAIT * 2, "font-size": Math.max(5, W / 110), fill: couleurs.stroke, "font-weight": "bold" });
				t.textContent = opts.etiquette;
			}
			let p = null;
			if (opts.mobile) p = el("rect", { x: z.x + z.w - POIGNEE, y: z.y + z.h - POIGNEE, width: POIGNEE, height: POIGNEE, fill: sel ? "#dc2626" : couleurs.stroke, "fill-opacity": 0.9, style: "cursor:nwse-resize" });
			const glisser = (mode) => (e) => {
				if (e.button !== 0) return;
				e.preventDefault(); e.stopPropagation();
				const p0 = point(e), z0 = { ...z };
				let bouge = false;
				const bouger = (ev) => {
					const q = point(ev), dx = q.x - p0.x, dy = q.y - p0.y;
					if (Math.abs(dx) + Math.abs(dy) > 0.5) bouge = true;
					if (mode === "move") { z.x = Math.min(Math.max(z0.x + dx, 0), W - z.w); z.y = Math.min(Math.max(z0.y + dy, 0), H - z.h); }
					else { z.w = Math.max(4, Math.min(z0.w + dx, W - z.x)); z.h = Math.max(4, Math.min(z0.h + dy, H - z.y)); }
					r.setAttribute("x", z.x); r.setAttribute("y", z.y); r.setAttribute("width", z.w); r.setAttribute("height", z.h);
					if (p) { p.setAttribute("x", z.x + z.w - POIGNEE); p.setAttribute("y", z.y + z.h - POIGNEE); }
				};
				const lacher = () => {
					document.removeEventListener("mousemove", bouger); document.removeEventListener("mouseup", lacher);
					if (bouge && opts.mobile) opts.deposer([this._r(z.x), this._r(z.y), this._r(z.x + z.w), this._r(z.y + z.h)]);
					else { this.sel = { type, id }; this.dessiner(); this.rendre_droite(); }
				};
				document.addEventListener("mousemove", bouger); document.addEventListener("mouseup", lacher);
			};
			r.addEventListener("mousedown", glisser("move"));
			if (p) p.addEventListener("mousedown", glisser("resize"));
		};

		// Les illustrations détectées (fixes : leur boîte est celle de l'image), en dessous des blocs.
		(pg.images || []).forEach((im) => {
			const ia = this.edition.images[im.id];
			poser("image", im.id, im.bbox, { fill: "#f59e0b", op: ia ? 0.14 : 0.05, stroke: ia ? "#d97706" : "#f59e0b", tirets: ia ? "none" : `${TRAIT * 4} ${TRAIT * 3}` },
				{ mobile: false, etiquette: ia ? __("IA") : "" });
		});
		const COULEURS = {
			traduit: { fill: "#2563eb", op: 0.10, stroke: "#2563eb" },
			corrige: { fill: "#16a34a", op: 0.12, stroke: "#16a34a" },
			non_traduit: { fill: "#94a3b8", op: 0.10, stroke: "#94a3b8", tirets: `${TRAIT * 4} ${TRAIT * 3}` },
			anglais: { fill: "#64748b", op: 0.03, stroke: "#64748b", tirets: `${TRAIT * 2} ${TRAIT * 3}` },
			efface: { fill: "#ef4444", op: 0.10, stroke: "#ef4444", tirets: `${TRAIT * 4} ${TRAIT * 3}` },
			pivote: { fill: "#a855f7", op: 0.05, stroke: "#a855f7", tirets: `${TRAIT * 2} ${TRAIT * 3}` },
		};
		pg.blocs.forEach((b) => {
			const k = String(b.id), ov = this.edition.blocs[k] || {}, st = stats[k];
			const bbox = ov.bbox || b.bbox, statut = this._statut(b.id) === "non_traduit" && b.pivote ? "pivote" : this._statut(b.id);
			const c = Object.assign({}, COULEURS[statut] || COULEURS.non_traduit);
			let etiquette = "";
			if (st && !st.place) { c.stroke = "#dc2626"; etiquette = __("non placé"); }
			else if (st && st.echelle < 0.8) etiquette = Math.round(st.echelle * 100) + " %";
			const mobile = !b.pivote && statut !== "anglais";
			poser("bloc", b.id, bbox, c, { mobile, etiquette, deposer: (nb) => this.modifier_bloc(b.id, { bbox: nb }) });
			if (ov.bbox && mobile) el("rect", { x: b.bbox[0], y: b.bbox[1], width: b.bbox[2] - b.bbox[0], height: b.bbox[3] - b.bbox[1], fill: "none", stroke: "#94a3b8", "stroke-width": TRAIT * 0.8, "stroke-dasharray": `${TRAIT * 2} ${TRAIT * 2}`, style: "pointer-events:none" });
		});
		this.edition.libres.filter((l) => l.page === this.no).forEach((l) => {
			const image = l.type === "image", st = stats[l.id];
			poser("libre", l.id, l.bbox, image ? { fill: "#f59e0b", op: l.fichier ? 0.14 : 0.08, stroke: "#d97706", tirets: l.fichier ? "none" : `${TRAIT * 4} ${TRAIT * 3}` }
				: { fill: "#16a34a", op: 0.10, stroke: st && !st.place ? "#dc2626" : "#15803d" },
				{ mobile: true, etiquette: image ? (l.fichier ? __("IA") : __("zone IA")) : __("case"), deposer: (nb) => this.modifier_libre(l.id, { bbox: nb }) });
		});
	}

	_r(v) { return Math.round(v * 100) / 100; }

	// ─── édition ────────────────────────────────────────────────────────────────
	modifier_bloc(id, valeurs, redessiner = true) {
		const k = String(id), b = Object.assign({}, this.edition.blocs[k] || {}, valeurs);
		Object.keys(b).forEach((c) => { if (b[c] == null || b[c] === "" || (c === "traitement" && b[c] === "traduit")) delete b[c]; });
		if (Object.keys(b).length) this.edition.blocs[k] = b; else delete this.edition.blocs[k];
		return this.enregistrer(redessiner);
	}

	modifier_texte(id, texte, redessiner = true) {
		const k = String(id);
		if (texte && texte.trim() && texte !== this.trad[k]) this.edition.textes[k] = texte; else delete this.edition.textes[k];
		return this.enregistrer(redessiner);
	}

	modifier_libre(id, valeurs, redessiner = true) {
		const l = this.edition.libres.find((x) => x.id === id);
		if (!l) return Promise.resolve();
		Object.assign(l, valeurs);
		return this.enregistrer(redessiner);
	}

	supprimer_libre(id) {
		this.edition.libres = this.edition.libres.filter((x) => x.id !== id);
		this.sel = null;
		return this.enregistrer();
	}

	ajouter_libre(type) {
		const [W, H] = this.pg.format;
		const ids = new Set(this.edition.libres.map((l) => l.id));
		let n = ids.size + 1; while (ids.has("L" + n)) n++;
		const g = type === "image" ? { x: 0.2, y: 0.3, w: 0.6, h: 0.35 } : { x: 0.15, y: 0.45, w: 0.5, h: 0.06 };
		const l = { id: "L" + n, type, page: this.no, bbox: [this._r(W * g.x), this._r(H * g.y), this._r(W * (g.x + g.w)), this._r(H * (g.y + g.h))] };
		if (type === "texte") Object.assign(l, { texte: "", taille: 10, gras: false, fond: true, align: "left" });
		this.edition.libres.push(l);
		this.sel = { type: "libre", id: l.id };
		this.enregistrer(false).then(() => { this.dessiner(); this.rendre_droite(); });
		this.dessiner(); this.rendre_droite();
	}

	// ─── mode « Reconstruit » ────────────────────────────────────────────────────
	// L'IA lit chaque page (titres, paragraphes, listes, tableaux, figures) ; on corrige ce contenu,
	// on le traduit, puis un PDF NEUF est composé avec un gabarit propre (manuels/reconstruit.py).
	_html_mode() {
		return `<select data-role="mode" title="${__("En place : le texte est remplacé dans le PDF d'origine. Reconstruit : l'IA lit la page et un PDF neuf est composé.")}">
			<option value="place" ${this.mode === "place" ? "selected" : ""}>${__("En place")}</option>
			<option value="reconstruit" ${this.mode === "reconstruit" ? "selected" : ""}>${__("Reconstruit")}</option></select><span class="sep"></span>`;
	}
	_lier_mode($o) {
		$o.find('[data-role="mode"]').on("change", (e) => { this.mode = e.target.value; this.sel = null; this.rendre_page(); });
	}

	async rendre_page_reconstruit(jeton) {
		const $o = this.$corps.find('[data-role="outils"]'), $s = this.$corps.find('[data-role="scene"]'), total = (this.data.pages || []).length;
		let st, orig;
		try {
			[st, orig] = await Promise.all([
				this.multi ? frappe.call({ method: "aquaworld_ia.manuels.reconstruit.structure_page_multi", args: { manuel: this.nom, no: this.no } })
					: frappe.call({ method: "aquaworld_ia.manuels.reconstruit.structure_page", args: { manuel: this.nom, langue: this.source_en ? null : this.langue, no: this.no } }),
				frappe.call({ method: "aquaworld_ia.manuels.studio.page", args: { manuel: this.nom, langue: this.langue, no: this.no, original: 1 } }),
			]);
		} catch (e) { $s.css("opacity", 1).html(`<div class="sm-vide">${this._esc(this._msg(e))}</div>`); return; }
		if (jeton !== this._jeton) return;
		this.st = st.message; this.pg = orig.message;
		if (this.multi) { this.st.traduits = []; this.st.manquants = []; this.st.figures_traduites = {}; }
		const ligne = this.data.langues.find((l) => l.langue === this.langue) || {};
		const lues = this.st.pages_lues.length;
		$o.html(`
			${this._html_mode()}
			<button class="btn btn-xs btn-default" data-role="prec" ${this.no <= 0 ? "disabled" : ""}>◀</button>
			<span>${__("Page")}</span> <input type="number" min="1" max="${total}" value="${this.no + 1}" data-role="no"> <span>/ ${total}</span>
			<button class="btn btn-xs btn-default" data-role="suiv" ${this.no >= total - 1 ? "disabled" : ""}>▶</button>
			<span class="sep"></span>
			<button class="btn btn-xs btn-default" data-role="lire-page" title="${__("L'IA lit cette page (image) et en donne le contenu structuré. Relire remplace la lecture précédente.")}">🤖 ${this.st.lu ? __("Relire la page") : __("Lire la page")}</button>
			<button class="btn btn-xs btn-default" data-role="lire-tout" title="${lues >= total ? __("Relire par IA toutes les pages (remplace la lecture actuelle ; les traductions des textes inchangés sont gardées)") : __("Lire par IA toutes les pages pas encore lues, en tâche de fond (≈ 10 s par page)")}">🤖 ${lues >= total ? __("Relire tout") : __("Lire tout")} (${lues}/${total})</button>
			<span class="sep"></span>
			<button class="btn btn-xs btn-default" data-role="traduire-contenu" title="${__("Traduire par IA les textes du contenu lu qui ne le sont pas encore, en tâche de fond")}">🤖 ${__("Traduire le contenu")}</button>
			<button class="btn btn-xs btn-default" data-role="mep-page" title="${__("L'IA écrit la mise en page de cette page (colonnes, figures, titres comme l'original) avec les textes traduits ; aperçu à gauche. Quelques centimes.")}">🎨 ${__("Mettre en page (IA)")}</button>
			<button class="btn btn-xs btn-default" data-role="mep-tout" title="${__("Mise en page IA de toutes les pages lues, en tâche de fond")}">🎨 ${__("Toutes les pages")}</button>
			<button class="btn btn-xs btn-primary" data-role="generer" title="${__("Composer le PDF neuf : couverture, sommaire, pages, figures découpées dans l'original. Sans IA.")}">📄 ${__("Générer le manuel")}</button>
			${ligne.pdf_reconstruit ? `<a class="btn btn-xs btn-default" href="${this._esc(ligne.pdf_reconstruit)}" target="_blank">⬇ ${__("Manuel reconstruit")}</a>` : ""}
			<label class="sm-check" style="margin:0 0 0 6px"><input type="checkbox" data-role="source-en" ${this.source_en ? "checked" : ""} ${this.multi ? "disabled" : ""}> ${__("Corriger l'anglais")}</label>
			<span class="sep"></span>
			<span title="${__("Zoom de l'original")}">🔍</span> <select data-role="zoom-orig"><option value="ajuster" ${this.zoom_orig === "ajuster" ? "selected" : ""}>${__("Ajuster")}</option><option value="1" ${this.zoom_orig === "1" ? "selected" : ""}>100 %</option><option value="1.5" ${this.zoom_orig === "1.5" ? "selected" : ""}>150 %</option><option value="2" ${this.zoom_orig === "2" ? "selected" : ""}>200 %</option><option value="3" ${this.zoom_orig === "3" ? "selected" : ""}>300 %</option></select>
			<span class="droite">${this.st.lu ? __("{0} blocs", [this.st.blocs.length]) : __("page pas encore lue")}</span>`);
		$o.find('[data-role="zoom-orig"]').on("change", (e) => { this.zoom_orig = e.target.value; this.appliquer_zoom_orig(); });
		this._lier_mode($o);
		$o.find('[data-role="prec"]').on("click", () => this.aller(this.no - 1));
		$o.find('[data-role="suiv"]').on("click", () => this.aller(this.no + 1));
		$o.find('[data-role="no"]').on("change", (e) => this.aller(Math.min(total, Math.max(1, +e.target.value || 1)) - 1));
		$o.find('[data-role="lire-page"]').on("click", () => this.lire_page());
		$o.find('[data-role="lire-tout"]').on("click", () => this.lire_tout());
		$o.find('[data-role="traduire-contenu"]').on("click", () => this.traduire_contenu());
		$o.find('[data-role="generer"]').on("click", () => this.generer_reconstruit());
		$o.find('[data-role="mep-page"]').on("click", () => this.mep_page());
		$o.find('[data-role="mep-tout"]').on("click", () => this.mep_tout());
		$o.find('[data-role="source-en"]').on("change", (e) => { this.source_en = e.target.checked; this.rendre_page(); });
		this.dessiner_structure();
		this.rendre_droite_reconstruit();
		$s.css("opacity", 1);
		if (!this._minuteur) this.reprendre_suivi_reconstruit();
	}

	// La page structurée : l'original à gauche (repère), les blocs à droite, éditables.
	dessiner_structure() {
		if (this.multi) return this.dessiner_structure_multi();
		const $s = this.$corps.find('[data-role="scene"]'), st = this.st, en = this.source_en;
		const blocs = en ? st.blocs : st.traduits, manquants = new Set(st.manquants || []);
		const rtl = !en && this.infos && this.infos.rtl;
		const LIB = { titre: __("Titre"), paragraphe: __("Paragraphe"), liste: __("Liste"), etapes: __("Étapes"), tableau: __("Tableau"), figure: __("Figure"), note: __("Note / avertissement"), legende: __("Légende"), image: __("Image ajoutée") };
		const carte = (b, i) => {
			const src = st.blocs[i] || b;
			let corps = "";
			if (["titre", "paragraphe", "note", "legende"].includes(b.type)) corps = `<textarea data-champ="texte" class="${rtl ? "rtl" : ""}" rows="${b.type === "titre" ? 1 : 3}">${this._esc(b.texte)}</textarea>`;
			else if (b.type === "liste" || b.type === "etapes") corps = `<textarea data-champ="items" class="${rtl ? "rtl" : ""}" rows="${Math.min(10, b.items.length + 1)}" placeholder="${__("un élément par ligne")}">${this._esc(b.items.join("\n"))}</textarea>`;
			else if (b.type === "tableau") corps = `<textarea data-champ="lignes" class="${rtl ? "rtl" : ""}" rows="${Math.min(10, b.lignes.length + 1)}" placeholder="${__("une ligne par rangée, cellules séparées par |")}">${this._esc(b.lignes.map((l) => l.join(" | ")).join("\n"))}</textarea>`;
			else if (b.type === "figure") corps = `<canvas class="sm-crop" data-crop="${i}"></canvas>
				<div class="sm-btns" style="margin-top:4px"><button class="btn btn-xs btn-default" data-cadrer="${i}" title="${__("Déplacer ou redimensionner le cadre sur l'original, effacer des zones (une étiquette, un morceau parasite)")}">✎ ${__("Cadrer / effacer")}</button>${(src.masques || []).length ? `<span class="sm-chip">${__("{0} zone(s) effacée(s)", [src.masques.length])}</span>` : ""}</div>
				<input type="text" data-champ="legende" class="${rtl ? "rtl" : ""}" placeholder="${__("légende (facultatif)")}" value="${this._esc(b.legende || "")}" style="margin-top:4px">`;
			else if (b.type === "image") corps = `<img src="${this._esc(src.fichier)}" class="sm-crop" style="max-height:120px;width:auto;margin:0 auto">
				<div class="sm-2" style="margin-top:4px"><div><label style="font-size:10px;text-transform:uppercase;color:#6b7683">${__("Largeur (% du texte)")}</label><input type="number" data-champ="largeur" min="5" max="100" step="5" value="${src.largeur || 40}" ${en ? "" : "disabled"}></div>
				<div><label style="font-size:10px;text-transform:uppercase;color:#6b7683">${__("Alignement")}</label><select data-champ="align" ${en ? "" : "disabled"}><option value="center" ${(src.align || "center") === "center" ? "selected" : ""}>${__("Centré")}</option><option value="left" ${src.align === "left" ? "selected" : ""}>${__("Gauche")}</option><option value="right" ${src.align === "right" ? "selected" : ""}>${__("Droite")}</option></select></div></div>
				<input type="text" data-champ="legende" class="${rtl ? "rtl" : ""}" placeholder="${__("légende (facultatif)")}" value="${this._esc(b.legende || "")}" style="margin-top:4px">`;
			// en mode traduction, le texte anglais lu reste visible sous le bloc (demande utilisateur 25/09/2026)
			let original = "";
			if (!en && src) {
				const txt = src.texte || (src.items ? src.items.map((x) => "• " + x).join("\n") : "") || (src.lignes ? src.lignes.map((l) => l.join(" | ")).join("\n") : "") || src.legende || "";
				if (txt) original = `<div class="sm-orig sm-orig-st">${this._esc(txt)}</div>`;
			}
			const niveau = b.type === "titre" && en ? `<select data-champ="niveau" style="width:auto;display:inline-block;margin-left:6px"><option value="1" ${b.niveau === 1 ? "selected" : ""}>H1</option><option value="2" ${b.niveau === 2 ? "selected" : ""}>H2</option><option value="3" ${b.niveau === 3 ? "selected" : ""}>H3</option></select>` : "";
			const a_textes = ["titre", "paragraphe", "note", "legende", "liste", "etapes", "tableau"].includes(b.type) || ((b.type === "figure" || b.type === "image") && src.legende);
			const traduite = b.type === "figure" && (st.figures_traduites || {})[src.id];
			if (traduite) corps = corps.replace(/<canvas class="sm-crop" data-crop="\d+"><\/canvas>/, `<img src="${this._esc(traduite)}" class="sm-crop" style="max-height:200px;width:auto;margin:0 auto">`);
			const acts_trad = !en ? `${a_textes ? `<button class="btn btn-xs btn-default" data-act="traduire" title="${manquants.has(src.id) ? __("Traduire par IA les textes manquants de ce seul bloc, tout de suite") : __("Retraduire par IA ce seul bloc (remplace la traduction actuelle)")}">🤖 ${manquants.has(src.id) ? __("Traduire") : __("Retraduire")}</button>` : ""}
				${b.type === "figure" ? (traduite ? `<span class="sm-chip ok">🎨 ${__("mots traduits")}</span><button class="btn btn-xs btn-default" data-act="fig-retirer" title="${__("Revenir à la figure d'origine")}">${__("Retirer")}</button><button class="btn btn-xs btn-default" data-act="fig-traduire" title="${__("Réessayer (une image facturée)")}">↺</button>`
					: `<button class="btn btn-xs btn-default" data-act="fig-traduire" title="${__("L'IA redessine la figure à l'identique avec ses mots dans la langue (une image facturée, ≈ 30 s ; relire chaque mot)")}">🎨 ${__("Traduire les mots de l'image")}</button>`) : ""}` : "";
			return `<div class="sm-bloc-st ${manquants.has(src.id) && !en ? "manque" : ""}" data-i="${i}">
				<div class="tete"><span class="type">${LIB[b.type] || b.type}</span>${niveau}
					${manquants.has(src.id) && !en ? `<span class="sm-chip encours">${__("à traduire")}</span>` : ""}
					<span class="acts">${acts_trad}${en ? `<button class="btn btn-xs btn-default" data-act="haut" title="${__("Monter")}">↑</button><button class="btn btn-xs btn-default" data-act="bas" title="${__("Descendre")}">↓</button><button class="btn btn-xs btn-default" data-act="suppr" title="${__("Supprimer ce bloc")}">✕</button>` : ""}</span></div>
				${corps}${original}</div>`;
		};
		$s.html(`<div class="sm-recon">
			<div class="sm-recon-orig">
				<div class="sm-onglets" style="padding:0 0 6px;border:none"><span class="o ${this.vue_gauche !== "apercu" ? "on" : ""}" data-vue="original">${__("Original")}</span><span class="o ${this.vue_gauche === "apercu" ? "on" : ""}" data-vue="apercu" title="${__("Les blocs de cette page composés dans la langue, comme dans le manuel généré")}">${__("Aperçu")}</span></div>
				<div class="cadre" data-role="cadre-original" ${this.vue_gauche === "apercu" ? "hidden" : ""}><img src="${this.pg.png}" alt="" data-role="orig-grand" title="${__("Cliquer pour voir en grand ; molette + Ctrl pour zoomer")}"></div>
				<div class="cadre" data-role="cadre-apercu" ${this.vue_gauche === "apercu" ? "" : "hidden"}><div class="sm-vide">${__("Aperçu…")}</div></div>
				<div class="text-muted small" style="text-align:center;margin-top:4px">${this.vue_gauche === "apercu" ? __("Aperçu de la page composée — se met à jour après chaque modification") : __("Original — cliquer pour agrandir")}</div></div>
			<div class="sm-recon-blocs">
				${!st.lu ? `<div class="sm-vide">${__("Cette page n'a pas encore été lue par l'IA : « Lire la page » ou « Lire tout ».")}</div>` : ""}
				${blocs.map(carte).join("")}
				${en ? `<div class="sm-btns"><select data-role="type-ajout"><option value="titre">${__("Titre")}</option><option value="paragraphe" selected>${__("Paragraphe")}</option><option value="liste">${__("Liste")}</option><option value="etapes">${__("Étapes")}</option><option value="tableau">${__("Tableau")}</option><option value="note">${__("Note")}</option><option value="image">${__("Image (logo, certification, photo)")}</option></select> <button class="btn btn-xs btn-default" data-role="ajouter-bloc">＋ ${__("Ajouter un bloc")}</button></div>` : `<p class="text-muted small">${__("Pour ajouter un bloc (image, logo, certification, texte), cochez « Corriger l'anglais ».")}</p>`}
			</div></div>`);
		this.appliquer_zoom_orig();
		$s.find(".sm-recon-orig [data-vue]").on("click", (e) => { this.vue_gauche = $(e.currentTarget).attr("data-vue"); this.dessiner_structure(); });
		if (this.vue_gauche === "apercu") this.rafraichir_apercu();
		// molette + Ctrl sur l'original : zoom (sans Ctrl, on défile normalement)
		$s.find(".sm-recon-orig .cadre").on("wheel", (e) => {
			if (!e.ctrlKey) return;
			e.preventDefault();
			const paliers = ["ajuster", "1", "1.5", "2", "3"], i = Math.max(0, paliers.indexOf(this.zoom_orig || "ajuster"));
			this.zoom_orig = paliers[Math.min(paliers.length - 1, Math.max(0, i + (e.originalEvent.deltaY < 0 ? 1 : -1)))];
			this.$corps.find('[data-role="zoom-orig"]').val(this.zoom_orig); this.appliquer_zoom_orig();
		});
		$s.find('[data-role="orig-grand"]').on("click", () => this.voir_en_grand([this.pg.png], __("Page {0} — original", [this.no + 1])));
		// figures : découpe de l'original
		const img_orig = $s.find(".sm-recon-orig img")[0];
		const pct = (bb) => { const [W, H] = this.pg.format; return [bb[0] / 100 * W, bb[1] / 100 * H, bb[2] / 100 * W, bb[3] / 100 * H]; };
		$s.find("canvas[data-crop]").each((_k, c) => {
			const b = st.blocs[+c.getAttribute("data-crop")];
			if (b && b.bbox) this.dessiner_crop(c, pct(b.bbox), img_orig, (b.masques || []).map(pct));
		});
		$s.find("[data-cadrer]").on("click", (e) => this.cadrer_figure(+$(e.currentTarget).attr("data-cadrer")));
		const lire_blocs = () => $s.find(".sm-bloc-st").map((_k, el) => {
			const i = +el.getAttribute("data-i"), b = Object.assign({}, blocs[i]);
			const v = (champ) => { const f = el.querySelector(`[data-champ="${champ}"]`); return f ? f.value : null; };
			if (v("texte") !== null) b.texte = v("texte");
			if (v("items") !== null) b.items = v("items").split("\n").map((x) => x.trim()).filter(Boolean);
			if (v("lignes") !== null) b.lignes = v("lignes").split("\n").filter((l) => l.trim()).map((l) => l.split("|").map((x) => x.trim()));
			if (v("legende") !== null) b.legende = v("legende");
			if (v("niveau") !== null) b.niveau = +v("niveau");
			if (v("largeur") !== null) b.largeur = +v("largeur");
			if (v("align") !== null) b.align = v("align");
			return b;
		}).get();
		let minuteur;
		$s.find("textarea, input[data-champ], select[data-champ]").on("input change", (e) => {
			clearTimeout(minuteur);
			minuteur = setTimeout(() => this.enregistrer_structure(lire_blocs()), e.type === "change" ? 0 : 900);
		});
		$s.find("[data-act]").on("click", (e) => {
			const $b = $(e.currentTarget).closest(".sm-bloc-st"), i = +$b.attr("data-i"), act = $(e.currentTarget).attr("data-act");
			if (act === "traduire") return this.traduire_bloc(st.blocs[i], !manquants.has(st.blocs[i].id));
			if (act === "fig-traduire") return this.traduire_figure(st.blocs[i]);
			if (act === "fig-retirer") return this.appel_structure("retirer_figure_traduite", { ident: st.blocs[i].id }, null);
			const l = lire_blocs();
			if (act === "suppr") l.splice(i, 1);
			else if (act === "haut" && i > 0) [l[i - 1], l[i]] = [l[i], l[i - 1]];
			else if (act === "bas" && i < l.length - 1) [l[i + 1], l[i]] = [l[i], l[i + 1]];
			this.enregistrer_structure(l, true);
		});
		$s.find('[data-role="ajouter-bloc"]').on("click", () => {
			const t = $s.find('[data-role="type-ajout"]').val(), l = lire_blocs();
			if (t === "image") {
				// un fichier du site (logo, certification, photo) : téléversé et rattaché à la fiche
				new frappe.ui.FileUploader({ doctype: "Manuel Article", docname: this.nom, folder: "Home/Attachments", restrictions: { allowed_file_types: ["image/*"] },
					on_success: (f) => { l.push({ type: "image", fichier: f.file_url, largeur: 40, align: "center" }); this.enregistrer_structure(l, true); } });
				return;
			}
			l.push(t === "liste" || t === "etapes" ? { type: t, items: [__("nouvel élément")] } : t === "tableau" ? { type: t, lignes: [["", ""]] } : { type: t, texte: t === "titre" ? __("Nouveau titre") : __("Nouveau texte"), niveau: 2 });
			this.enregistrer_structure(l, true);
		});
	}

	// Une ou plusieurs images de page en grand, avec zoom (− / ＋ / Ajuster, ou Ctrl + molette).
	voir_en_grand(images, titre) {
		let z = 1;
		const dlg = new frappe.ui.Dialog({ title: titre, size: "extra-large",
			fields: [{ fieldtype: "HTML", fieldname: "vue", options: `<div class="sm-btns" style="margin:0 0 6px"><button class="btn btn-xs btn-default" data-z="-">−</button><button class="btn btn-xs btn-default" data-z="+">＋</button><button class="btn btn-xs btn-default" data-z="1">${__("Ajuster")}</button><span class="text-muted small" data-role="pct" style="align-self:center">100 %</span></div>
				<div style="max-height:78vh;overflow:auto" data-role="vue-grand">${images.map((src) => `<img src="${src}" style="width:100%;display:block;margin-bottom:8px">`).join("")}</div>` }] });
		dlg.show();
		const $w = dlg.get_field("vue").$wrapper, $imgs = $w.find("img");
		const poser = () => { $imgs.css("width", Math.round(z * 100) + "%"); $w.find('[data-role="pct"]').text(Math.round(z * 100) + " %"); };
		$w.find("[data-z]").on("click", (e) => {
			const a = $(e.currentTarget).attr("data-z");
			z = a === "1" ? 1 : Math.min(4, Math.max(0.5, z + (a === "+" ? 0.25 : -0.25)));
			poser();
		});
		$w.find('[data-role="vue-grand"]').on("wheel", (e) => {
			if (!e.ctrlKey) return;
			e.preventDefault(); z = Math.min(4, Math.max(0.5, z + (e.originalEvent.deltaY < 0 ? 0.25 : -0.25))); poser();
		});
	}

	async rafraichir_apercu() {
		const $c = this.$corps.find('[data-role="cadre-apercu"]'), jeton = (this._jeton_apercu = (this._jeton_apercu || 0) + 1);
		if (!$c.length) return;
		try {
			const r = await frappe.call({ method: "aquaworld_ia.manuels.reconstruit.apercu_page", args: { manuel: this.nom, langue: this.langue, no: this.no } });
			if (jeton !== this._jeton_apercu) return;
			const a = r.message;
			this.apercu = a;
			const entete = a.lu ? `<div class="sm-btns" style="margin:0 0 6px;align-items:center">${a.ia ? `<span class="sm-chip ok">🎨 ${__("mise en page IA")}</span><button class="btn btn-xs btn-default" data-role="mep-retirer" title="${__("Revenir au gabarit automatique pour cette page")}">${__("Retirer")}</button>` : `<span class="sm-chip">${__("gabarit automatique")}</span>`}${a.pages > 1 ? `<span class="sm-chip encours">${__("{0} pages", [a.pages])}</span>` : ""}</div>` : "";
			$c.html(entete + (a.lu && a.images.length ? a.images.map((src) => `<img src="${src}" alt="" style="margin-bottom:8px;cursor:zoom-in" data-role="apercu-grand" title="${__("Cliquer pour voir en grand ; molette + Ctrl pour zoomer")}">`).join("") : `<div class="sm-vide">${__("Rien à composer : page pas encore lue.")}</div>`));
			$c.find('[data-role="apercu-grand"]').on("click", () => this.voir_en_grand(a.images, __("Page {0} — aperçu ({1})", [this.no + 1, a.ia ? __("mise en page IA") : __("gabarit")])));
			$c.find('[data-role="mep-retirer"]').on("click", async () => {
				await frappe.call({ method: "aquaworld_ia.manuels.reconstruit.retirer_mise_en_page", args: { manuel: this.nom, langue: this.langue, no: this.no }, freeze: true });
				this.rafraichir_apercu();
			});
			this.appliquer_zoom_orig();
		} catch (e) { $c.html(`<div class="sm-vide">${this._esc(this._msg(e))}</div>`); }
	}

	appliquer_zoom_orig() {
		const $img = this.$corps.find(".sm-recon-orig img"), z = this.zoom_orig || "ajuster";
		if (!$img.length || !this.pg) return;
		$img.css("width", z === "ajuster" ? "100%" : `${Math.round(this.pg.format[0] * 96 / 72 * parseFloat(z))}px`);
	}

	// La page dans TOUTES les langues : par bloc, l'anglais puis une case par langue (corrigeable),
	// « Traduire » par langue ou pour toutes ; les figures avec leurs mots traduits par langue.
	dessiner_structure_multi() {
		const $s = this.$corps.find('[data-role="scene"]'), st = this.st, langues = st.langues || [];
		const champ = (b, code, rtl, i) => {
			const cls = rtl ? "rtl" : "";
			if (["titre", "paragraphe", "note", "legende"].includes(b.type)) return `<textarea data-champ="texte" data-langue="${code}" data-i="${i}" class="${cls}" rows="${b.type === "titre" ? 1 : 2}">${this._esc(b.texte)}</textarea>`;
			if (b.type === "liste" || b.type === "etapes") return `<textarea data-champ="items" data-langue="${code}" data-i="${i}" class="${cls}" rows="${Math.min(8, b.items.length + 1)}">${this._esc(b.items.join("\n"))}</textarea>`;
			if (b.type === "tableau") return `<textarea data-champ="lignes" data-langue="${code}" data-i="${i}" class="${cls}" rows="${Math.min(8, b.lignes.length + 1)}">${this._esc(b.lignes.map((l) => l.join(" | ")).join("\n"))}</textarea>`;
			if (b.type === "figure" || b.type === "image") return `<input type="text" data-champ="legende" data-langue="${code}" data-i="${i}" class="${cls}" placeholder="${__("légende (facultatif)")}" value="${this._esc(b.legende || "")}">`;
			return "";
		};
		const carte = (src, i) => {
			const en = src.texte || (src.items ? src.items.map((x) => "• " + x).join("\n") : "") || (src.lignes ? src.lignes.map((l) => l.join(" | ")).join("\n") : "") || src.legende || "";
			const lignes = langues.map((L) => {
				const b = L.traduits[i], manque = (L.manquants || []).includes(src.id), fig = src.type === "figure" && (L.figures_traduites || {})[src.id];
				return `<div class="sm-ml"><div class="sm-ml-tete"><span class="sm-chip ${manque ? "encours" : "ok"}" title="${this._esc(L.langue)}">${this._esc(L.libelle)}</span>
					${src.type === "figure" ? (fig ? `<span class="sm-chip ok">🎨 ${__("mots traduits")}</span><button class="btn btn-xs btn-default" data-ml="fig-retirer" data-langue="${L.langue}" data-i="${i}">${__("Retirer")}</button>` : `<button class="btn btn-xs btn-default" data-ml="fig-traduire" data-langue="${L.langue}" data-i="${i}" title="${__("Redessiner la figure avec ses mots en {0} (une image facturée)", [L.libelle])}">🎨</button>`) : ""}
					${champ(b, L.langue, L.rtl, i) ? `<button class="btn btn-xs btn-default" data-ml="traduire" data-langue="${L.langue}" data-i="${i}" title="${manque ? __("Traduire ce bloc en {0}", [L.libelle]) : __("Retraduire ce bloc en {0}", [L.libelle])}">🤖</button>` : ""}</div>
					${fig ? `<img src="${this._esc(fig)}" class="sm-crop" style="max-height:120px;width:auto;margin:2px 0">` : ""}${champ(b, L.langue, L.rtl, i)}</div>`;
			}).join("");
			const crop = src.type === "figure" ? `<canvas class="sm-crop" data-crop="${i}" style="max-height:140px"></canvas>` : src.type === "image" ? `<img src="${this._esc(src.fichier)}" class="sm-crop" style="max-height:100px;width:auto">` : "";
			return `<div class="sm-bloc-st" data-i="${i}"><div class="tete"><span class="type">${this._esc(src.type)}</span>
				<span class="acts">${src.type !== "image" ? `<button class="btn btn-xs btn-default" data-ml="traduire-tout" data-i="${i}" title="${__("Traduire ce bloc dans toutes les langues où il manque")}">🤖 ${__("Toutes les langues")}</button>` : ""}</span></div>
				${crop}${en ? `<div class="sm-orig sm-orig-st">${this._esc(en)}</div>` : ""}${lignes}</div>`;
		};
		$s.html(`<div class="sm-recon">
			<div class="sm-recon-orig"><div class="cadre" data-role="cadre-original"><img src="${this.pg.png}" alt="" data-role="orig-grand"></div><div class="text-muted small" style="text-align:center;margin-top:4px">${__("Original")}</div></div>
			<div class="sm-recon-blocs">${!st.lu ? `<div class="sm-vide">${__("Cette page n'a pas encore été lue par l'IA : « Lire la page » ou « Lire tout ».")}</div>` : ""}
				<p class="text-muted small">${__("Toutes les langues : corrigez chaque langue dans sa case ; 🤖 traduit un bloc dans une langue, « Toutes les langues » là où il manque. L'aperçu et la mise en page IA se font depuis l'onglet d'une langue.")}</p>
				${st.blocs.map(carte).join("")}</div></div>`);
		this.appliquer_zoom_orig();
		$s.find('[data-role="orig-grand"]').on("click", () => this.voir_en_grand([this.pg.png], __("Page {0} — original", [this.no + 1])));
		const img_orig = $s.find(".sm-recon-orig img")[0], pct = (bb) => { const [W, H] = this.pg.format; return [bb[0] / 100 * W, bb[1] / 100 * H, bb[2] / 100 * W, bb[3] / 100 * H]; };
		$s.find("canvas[data-crop]").each((_k, c) => { const b = st.blocs[+c.getAttribute("data-crop")]; if (b && b.bbox) this.dessiner_crop(c, pct(b.bbox), img_orig, (b.masques || []).map(pct)); });
		// enregistrement : la langue du champ modifié, bloc pour bloc
		const blocs_langue = (code) => {
			const L = langues.find((x) => x.langue === code);
			return L.traduits.map((b, i) => {
				const n = Object.assign({}, b), v = (champ_) => { const f = $s.find(`[data-champ="${champ_}"][data-langue="${code}"][data-i="${i}"]`)[0]; return f ? f.value : null; };
				if (v("texte") !== null) n.texte = v("texte");
				if (v("items") !== null) n.items = v("items").split("\n").map((x) => x.trim()).filter(Boolean);
				if (v("lignes") !== null) n.lignes = v("lignes").split("\n").filter((l) => l.trim()).map((l) => l.split("|").map((x) => x.trim()));
				if (v("legende") !== null) n.legende = v("legende");
				return n;
			});
		};
		const minuteurs = {};
		$s.find("[data-champ][data-langue]").on("input change", (e) => {
			const code = e.currentTarget.getAttribute("data-langue");
			clearTimeout(minuteurs[code]);
			minuteurs[code] = setTimeout(() => this.enregistrer_structure_langue(code, blocs_langue(code)), e.type === "change" ? 0 : 900);
		});
		$s.find("[data-ml]").on("click", async (e) => {
			const act = e.currentTarget.getAttribute("data-ml"), i = +e.currentTarget.getAttribute("data-i"), code = e.currentTarget.getAttribute("data-langue"), b = st.blocs[i];
			if (act === "traduire") await this.appel_multi("traduire_bloc", code, { ident: b.id, tout: (langues.find((x) => x.langue === code).manquants || []).includes(b.id) ? 0 : 1 }, __("L'IA traduit ce bloc…"));
			else if (act === "fig-traduire") await this.appel_multi("traduire_figure", code, { ident: b.id, instruction: "" }, __("L'IA redessine la figure (≈ 30 s)…"));
			else if (act === "fig-retirer") await this.appel_multi("retirer_figure_traduite", code, { ident: b.id }, null);
			else if (act === "traduire-tout") {
				const cibles = langues.filter((L) => (L.manquants || []).includes(b.id));
				if (!cibles.length) { frappe.show_alert({ message: __("Ce bloc est déjà traduit dans toutes les langues."), indicator: "blue" }); return; }
				for (const L of cibles) await this.appel_multi("traduire_bloc", L.langue, { ident: b.id, tout: 0 }, __("L'IA traduit ce bloc en {0}…", [L.libelle]), true);
				this.rendre_page();
			}
		});
	}

	enregistrer_structure_langue(code, blocs) {
		const tache = (this._file_st || Promise.resolve()).catch(() => {}).then(async () => {
			await frappe.call({ method: "aquaworld_ia.manuels.reconstruit.enregistrer_page", args: { manuel: this.nom, no: this.no, blocs, langue: code }, freeze: false });
		});
		this._file_st = tache;
		return tache;
	}

	async appel_multi(methode, code, args, freeze_message, sans_redessin) {
		try {
			await frappe.call({ method: "aquaworld_ia.manuels.reconstruit." + methode, args: Object.assign({ manuel: this.nom, langue: code, no: this.no }, args), freeze: !!freeze_message, freeze_message });
			if (!sans_redessin) this.rendre_page();
		} catch (e) { frappe.msgprint(this._msg(e)); }
	}

	// Cadrer une figure à la main sur l'original : le cadre (bleu) se déplace et se redimensionne, les
	// zones à effacer (rouges) s'ajoutent, se déplacent, se suppriment ; OK enregistre dans la source.
	cadrer_figure(i) {
		const src = this.st.blocs[i];
		if (!src || src.type !== "figure") return;
		this.vue_gauche = "original"; this.dessiner_structure();
		const $cadre = this.$corps.find('[data-role="cadre-original"]'), img = $cadre.find("img")[0];
		if (!img) return;
		const [W, H] = this.pg.format, NS = "http://www.w3.org/2000/svg";
		$cadre.find(".sm-fig-edit").remove();
		// inline-block : le calque épouse l'image, zoomée ou non (cadrage possible à 200-300 %, demande du 25/09/2026)
		const $wrap = $(`<div class="sm-fig-edit" style="position:relative;display:inline-block;line-height:0;vertical-align:top"></div>`);
		$(img).wrap($wrap);
		const $w = $cadre.find(".sm-fig-edit");
		const svg = document.createElementNS(NS, "svg"); svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("style", "position:absolute;left:0;top:0;width:100%;height:100%");
		$w.append(svg);
		const pct = (bb) => [bb[0] / 100 * W, bb[1] / 100 * H, bb[2] / 100 * W, bb[3] / 100 * H];
		const en_pct = (r) => [this._r(r[0] / W * 100), this._r(r[1] / H * 100), this._r(r[2] / W * 100), this._r(r[3] / H * 100)];
		const etat = { bbox: pct(src.bbox), masques: (src.masques || []).map(pct) };
		const el = (tag, attrs) => { const n = document.createElementNS(NS, tag); Object.entries(attrs).forEach(([k, v]) => n.setAttribute(k, v)); svg.appendChild(n); return n; };
		const point = (e) => { const pt = svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY; return pt.matrixTransform(svg.getScreenCTM().inverse()); };
		const POIGNEE = Math.max(4, W / 90), TRAIT = W / 500;
		const rendre = () => {
			while (svg.firstChild) svg.removeChild(svg.firstChild);
			const poser = (r, couleur, deposer, supprimer) => {
				const z = { x: r[0], y: r[1], w: r[2] - r[0], h: r[3] - r[1] };
				const rect = el("rect", { x: z.x, y: z.y, width: z.w, height: z.h, fill: couleur, "fill-opacity": 0.15, stroke: couleur, "stroke-width": TRAIT * 1.5, style: "cursor:move" });
				const p = el("rect", { x: z.x + z.w - POIGNEE, y: z.y + z.h - POIGNEE, width: POIGNEE, height: POIGNEE, fill: couleur, style: "cursor:nwse-resize" });
				let x = null;
				if (supprimer) { x = el("text", { x: z.x + z.w - POIGNEE * 0.9, y: z.y + POIGNEE * 1.1, "font-size": POIGNEE * 1.4, fill: "#b91c1c", "font-family": "sans-serif", style: "cursor:pointer;font-weight:bold" }); x.textContent = "×"; x.addEventListener("click", (e) => { e.stopPropagation(); supprimer(); rendre(); }); }
				const glisser = (mode) => (e) => {
					if (e.button !== 0) return;
					e.preventDefault(); e.stopPropagation();
					const p0 = point(e), z0 = { ...z };
					const bouger = (ev) => {
						const q = point(ev), dx = q.x - p0.x, dy = q.y - p0.y;
						if (mode === "move") { z.x = Math.min(Math.max(z0.x + dx, 0), W - z.w); z.y = Math.min(Math.max(z0.y + dy, 0), H - z.h); }
						else { z.w = Math.max(4, Math.min(z0.w + dx, W - z.x)); z.h = Math.max(4, Math.min(z0.h + dy, H - z.y)); }
						rect.setAttribute("x", z.x); rect.setAttribute("y", z.y); rect.setAttribute("width", z.w); rect.setAttribute("height", z.h);
						p.setAttribute("x", z.x + z.w - POIGNEE); p.setAttribute("y", z.y + z.h - POIGNEE);
						if (x) { x.setAttribute("x", z.x + z.w - POIGNEE * 0.9); x.setAttribute("y", z.y + POIGNEE * 1.1); }
					};
					const lacher = () => { document.removeEventListener("mousemove", bouger); document.removeEventListener("mouseup", lacher); deposer([z.x, z.y, z.x + z.w, z.y + z.h]); };
					document.addEventListener("mousemove", bouger); document.addEventListener("mouseup", lacher);
				};
				rect.addEventListener("mousedown", glisser("move")); p.addEventListener("mousedown", glisser("resize"));
			};
			poser(etat.bbox, "#2563eb", (r) => { etat.bbox = r; }, null);
			etat.masques.forEach((m, k) => poser(m, "#dc2626", (r) => { etat.masques[k] = r; }, () => etat.masques.splice(k, 1)));
		};
		rendre();
		const $barre = $(`<div class="sm-btns" style="margin:6px 0"><span class="sm-chip">${__("Cadrage de la figure")}</span>
			<button class="btn btn-xs btn-default" data-role="masque-plus" title="${__("Une zone blanche qui efface une partie de la figure (étiquette, morceau parasite)")}">＋ ${__("Zone à effacer")}</button>
			<button class="btn btn-xs btn-primary" data-role="cadrer-ok">${__("OK")}</button><button class="btn btn-xs btn-default" data-role="cadrer-annuler">${__("Annuler")}</button>
			<span class="text-muted small">${__("Glissez le cadre bleu, tirez son coin ; les zones rouges seront blanches dans le manuel.")}</span></div>`);
		$cadre.before($barre);
		$barre.append(`<span class="text-muted small">${__("Zoomez (🔍 ou Ctrl + molette) pour cadrer au plus juste.")}</span>`);
		$barre.find('[data-role="masque-plus"]').on("click", () => {
			const b = etat.bbox, w = (b[2] - b[0]) * 0.3, h = (b[3] - b[1]) * 0.2;
			etat.masques.push([b[0] + w, b[1] + h, b[0] + 2 * w, b[1] + 2 * h]); rendre();
		});
		const fermer = () => { $barre.remove(); $(img).unwrap(); };
		$barre.find('[data-role="cadrer-annuler"]').on("click", () => { fermer(); this.dessiner_structure(); });
		$barre.find('[data-role="cadrer-ok"]').on("click", () => {
			const blocs = this.st.blocs.map((b, k) => k === i ? Object.assign({}, b, { bbox: en_pct(etat.bbox), masques: etat.masques.map(en_pct) }) : b);
			fermer();
			// la source est enregistrée quel que soit le mode : le cadre appartient à la page, pas à la langue
			const tache = (this._file_st || Promise.resolve()).catch(() => {}).then(async () => {
				await frappe.call({ method: "aquaworld_ia.manuels.reconstruit.enregistrer_page", args: { manuel: this.nom, no: this.no, blocs, langue: null }, freeze: true });
				const r = await frappe.call({ method: "aquaworld_ia.manuels.reconstruit.structure_page", args: { manuel: this.nom, langue: this.source_en ? null : this.langue, no: this.no } });
				this.st = r.message; this.dessiner_structure(); this.rendre_droite_reconstruit();
				frappe.show_alert({ message: __("Cadre enregistré. Une page déjà mise en page par l'IA est à refaire pour en tenir compte."), indicator: "green" });
			});
			this._file_st = tache;
		});
	}

	// Un appel IA sur un seul bloc, puis la page structurée rafraîchie.
	async appel_structure(methode, args, freeze_message) {
		try {
			const r = await frappe.call({ method: "aquaworld_ia.manuels.reconstruit." + methode, args: Object.assign({ manuel: this.nom, langue: this.langue, no: this.no }, args), freeze: !!freeze_message, freeze_message });
			this.st = r.message; this.dessiner_structure(); this.rendre_droite_reconstruit();
			if (this.vue_gauche === "apercu") this.rafraichir_apercu();
			return r.message;
		} catch (e) { frappe.msgprint(this._msg(e)); }
	}

	async traduire_bloc(bloc, tout) {
		const r = await this.appel_structure("traduire_bloc", { ident: bloc.id, tout: tout ? 1 : 0 }, __("L'IA traduit ce bloc…"));
		if (r) frappe.show_alert({ message: r.n ? __("{0} texte(s) traduit(s).", [r.n]) : __("Rien à traduire dans ce bloc."), indicator: r.n ? "green" : "blue" });
	}

	traduire_figure(bloc) {
		const est = this.data.estimation_image || {};
		const dlg = new frappe.ui.Dialog({ title: __("Traduire les mots de la figure"),
			fields: [{ fieldtype: "HTML", options: `<p class="text-muted small">${__("L'IA redessine la figure à l'identique en traduisant les mots qu'elle contient (qualité {0}, ≈ {1} $). Relisez chaque mot et chaque numéro : l'IA redessine. Les zones effacées le restent.", [est.qualite || "", (est.cout || 0).toFixed(2)])}</p>` },
			         { fieldtype: "Data", fieldname: "instruction", label: __("Consigne (facultatif)"), placeholder: __("ex. garder les numéros dans les cercles") }],
			primary_action_label: __("Traduire"),
			primary_action: async (v) => {
				dlg.hide();
				const r = await this.appel_structure("traduire_figure", { ident: bloc.id, instruction: v.instruction || "" }, __("L'IA redessine la figure (≈ 30 s)…"));
				if (r) frappe.show_alert({ message: __("Figure redessinée : relisez chaque mot."), indicator: "green" });
			} });
		dlg.show();
	}

	enregistrer_structure(blocs, redessiner = false) {
		const tache = (this._file_st || Promise.resolve()).catch(() => {}).then(async () => {
			const r = await frappe.call({ method: "aquaworld_ia.manuels.reconstruit.enregistrer_page", args: { manuel: this.nom, no: this.no, blocs, langue: this.source_en ? null : this.langue }, freeze: false });
			this.st = r.message;
			if (redessiner) { this.dessiner_structure(); this.rendre_droite_reconstruit(); }
			else if (this.vue_gauche === "apercu") this.rafraichir_apercu();
		});
		this._file_st = tache;
		return tache;
	}

	rendre_droite_reconstruit() {
		const $d = this.$corps.find('[data-role="droite"]'), st = this.st, total = (this.data.pages || []).length, ligne = this.data.langues.find((l) => l.langue === this.langue) || {};
		if (this.multi) {
			$d.html(`<div class="bloc"><h6>${__("Toutes les langues")}</h6>
				<p class="text-muted" style="margin:0">${__("Chaque bloc de la page dans chaque langue. Pages lues : {0} / {1}.", [st.pages_lues.length, total])}</p>
				<ul class="sm-liste" style="margin-top:6px">${(st.langues || []).map((L) => `<li>${this._esc(L.libelle)} : ${L.manquants.length ? `<span style="color:#b45309">${__("{0} bloc(s) à traduire", [L.manquants.length])}</span>` : `<span style="color:#166534">${__("complet")}</span>`}</li>`).join("")}</ul>
				<p class="text-muted small" style="margin-top:8px">${__("Pour l'aperçu, la mise en page IA et la génération, passez par l'onglet d'une langue (les actions proposent alors toutes les langues).")}</p></div>`);
			return;
		}
		$d.html(`<div class="bloc"><h6>${__("Manuel reconstruit")} <span class="sm-chip">${this._esc(ligne.libelle || this.langue)}</span></h6>
			<p class="text-muted" style="margin:0">${__("1. « Lire tout » : l'IA lit chaque page (titres, textes, listes, tableaux, figures). 2. Corrigez ce qu'elle a lu (cochez « Corriger l'anglais » pour la source). 3. « Traduire le contenu ». 4. Relisez la traduction bloc par bloc. 5. « Générer le manuel » : un PDF neuf, propre, avec couverture, sommaire et vos figures.")}</p>
			<div style="margin-top:8px">${__("Pages lues : {0} / {1}", [st.pages_lues.length, total])}${st.manquants && st.manquants.length ? ` · <span style="color:#b45309">${__("{0} blocs à traduire sur cette page", [st.manquants.length])}</span>` : ""}</div>
			${ligne.pdf_reconstruit ? `<div style="margin-top:6px"><a href="${this._esc(ligne.pdf_reconstruit)}" target="_blank">⬇ ${__("Manuel reconstruit actuel")}</a></div>` : ""}
			<p class="text-muted small" style="margin-top:8px">${__("Le gabarit (logo, couleur des titres, A4/A5, éditeur) se règle dans Aquaworld IA Réglages.")}</p>
		</div>`);
	}

	async lire_page() {
		try {
			const r = await frappe.call({ method: "aquaworld_ia.manuels.reconstruit.lire_page", args: { manuel: this.nom, no: this.no }, freeze: true, freeze_message: __("L'IA lit la page {0} (≈ 30 à 60 s)…", [this.no + 1]) });
			frappe.show_alert({ message: __("Page lue : {0} blocs.", [r.message.blocs.length]), indicator: "green" });
			this.rendre_page(); this.rafraichir_langue();
		} catch (e) { frappe.msgprint(this._msg(e)); }
	}

	lire_tout() {
		const total = (this.data.pages || []).length, lues = (this.st && this.st.pages_lues.length) || 0, relire = lues >= total;
		frappe.confirm(relire ? __("Relire par IA les {0} pages ? La lecture actuelle est remplacée (vos corrections de l'anglais aussi) ; les traductions des textes inchangés sont gardées. Environ 2 à 4 centimes et 10 s par page.", [total])
			: __("Lire par IA les {0} pages pas encore lues ? Environ 2 à 4 centimes et 10 s par page, en tâche de fond.", [total - lues]), async () => {
			try {
				await frappe.call({ method: "aquaworld_ia.manuels.reconstruit.lire_tout", args: { manuel: this.nom, relire: relire ? 1 : 0 }, freeze: true });
				this.suivre_reconstruit();
			} catch (e) { frappe.msgprint(this._msg(e)); }
		});
	}

	// à l'ouverture du mode reconstruit : reprendre le suivi d'une tâche qui tourne déjà
	async reprendre_suivi_reconstruit() {
		try {
			const r = await frappe.call({ method: "aquaworld_ia.manuels.reconstruit.etats", args: { manuel: this.nom } });
			const e = r.message || {};
			if ([e.lecture, ...Object.values(e.traductions || {}), ...Object.values(e.mep || {})].some((x) => x && x.bloque)) this.suivre_reconstruit();
		} catch (_e) { /* rien */ }
	}

	traduire_contenu() {
		this.choisir_langues(__("Traduire le contenu"), __("Les textes du contenu lu pas encore traduits, dans chaque langue cochée : une tâche de fond par langue, en parallèle. Quelques centimes par langue ; vos corrections sont gardées."), __("Traduire"), async (codes) => {
			const rates = [];
			for (const code of codes) {
				try { await frappe.call({ method: "aquaworld_ia.manuels.reconstruit.traduire", args: { manuel: this.nom, langue: code }, freeze: false }); }
				catch (e) { rates.push(code + " : " + this._msg(e)); }
			}
			if (rates.length) frappe.msgprint(rates.join("<br>"));
			this.suivre_reconstruit();
		});
	}

	mep_page() {
		if ((this.data.langues || []).length <= 1) return this._mep_page_langues([this.langue]);
		this.choisir_langues(__("Mettre en page cette page par IA"), __("La page {0}, mise en page par l'IA dans chaque langue cochée, l'une après l'autre (≈ 20 à 40 s et 2 à 4 centimes par langue).", [this.no + 1]), __("Mettre en page"), (codes) => this._mep_page_langues(codes));
	}

	async _mep_page_langues(codes) {
		this.vue_gauche = "apercu";
		const rates = [];
		for (let k = 0; k < codes.length; k++) {
			const code = codes[k], lib = (this.data.langues.find((l) => l.langue === code) || {}).libelle || code;
			try {
				const r = await frappe.call({ method: "aquaworld_ia.manuels.reconstruit.composer_page_ia", args: { manuel: this.nom, langue: code, no: this.no }, freeze: true, freeze_message: __("L'IA met en page la page {0} en {1} ({2}/{3})…", [this.no + 1, lib, k + 1, codes.length]) });
				if (r.message.pages_ia > 1) rates.push(__("{0} : sur {1} pages, à relancer ou raccourcir.", [lib, r.message.pages_ia]));
			} catch (e) { rates.push(lib + " : " + this._msg(e)); }
		}
		if (rates.length) frappe.msgprint(rates.join("<br>")); else frappe.show_alert({ message: __("Page mise en page par l'IA ({0} langue(s)).", [codes.length]), indicator: "green" });
		this.dessiner_structure();
	}

	mep_tout() {
		this.choisir_langues(__("Mettre en page toutes les pages par IA"), __("Toutes les pages lues, dans chaque langue cochée : une tâche de fond par langue, en parallèle (≈ 20 à 40 s et 2 à 4 centimes par page et par langue). Les pages déjà mises en page ne sont pas refaites."), __("Lancer"), async (codes) => {
			const rates = [];
			for (const code of codes) {
				try { await frappe.call({ method: "aquaworld_ia.manuels.reconstruit.composer_tout_ia", args: { manuel: this.nom, langue: code }, freeze: false }); }
				catch (e) { rates.push(code + " : " + this._msg(e)); }
			}
			if (rates.length) frappe.msgprint(rates.join("<br>"));
			this.suivre_reconstruit();
		});
	}

	generer_reconstruit() {
		const langues = this.data.langues || [], nb_ia = (this.apercu && this.apercu.nb_ia) || 0;
		const d = new frappe.ui.Dialog({ title: __("Générer le manuel"),
			fields: [
				{ fieldtype: "Select", fieldname: "mode", label: __("Mise en page"), default: nb_ia ? "ia" : "fluide",
				  options: [{ value: "ia", label: __("Pages mises en page par l'IA (les autres par le gabarit)") }, { value: "fluide", label: __("Gabarit automatique (document fluide)") }] },
				{ fieldtype: "Section Break", label: __("Langues") },
				...langues.map((l) => ({ fieldtype: "Check", fieldname: "l_" + l.langue, label: `${l.libelle || l.langue}${l.langue === this.langue ? " — " + __("langue affichée") : ""}`, default: 1 })),
				{ fieldtype: "Check", fieldname: "combiner", label: __("Puis assembler le PDF toutes langues"), default: langues.length > 1 ? 1 : 0 },
			],
			primary_action_label: __("Générer"),
			primary_action: async (v) => {
				const codes = langues.map((l) => l.langue).filter((c) => v["l_" + c]);
				if (!codes.length) { frappe.msgprint(__("Cochez au moins une langue.")); return; }
				d.hide();
				const liens = [], rates = [];
				for (let k = 0; k < codes.length; k++) {
					const lib = (langues.find((l) => l.langue === codes[k]) || {}).libelle || codes[k];
					try {
						const r = await frappe.call({ method: "aquaworld_ia.manuels.reconstruit.generer", args: { manuel: this.nom, langue: codes[k], mode: v.mode }, freeze: true, freeze_message: __("Composition du manuel en {0} ({1}/{2})…", [lib, k + 1, codes.length]) });
						liens.push(`<li>${this._esc(lib)} : <a href="${this._esc(r.message.fichier)}" target="_blank">⬇ ${__("Ouvrir le PDF")}</a></li>`);
					} catch (e) { rates.push(lib + " : " + this._msg(e)); }
				}
				let combine = "";
				if (v.combiner && liens.length) {
					try {
						const c = await frappe.call({ method: "aquaworld_ia.manuels.studio.combiner", args: { manuel: this.nom }, freeze: true, freeze_message: __("Assemblage du PDF toutes langues…") });
						combine = `<p><a href="${this._esc(c.message.fichier)}" target="_blank">📚 ${__("PDF toutes langues")}</a> — ${this._esc(c.message.parties.join(" → "))}</p>`;
					} catch (e) { rates.push(this._msg(e)); }
				}
				await this.rafraichir_langue();
				this.rendre_page();
				frappe.msgprint({ title: __("Manuel reconstruit"), indicator: rates.length ? "orange" : "green", message: `<ul>${liens.join("")}</ul>${combine}${rates.length ? `<p class="text-danger">${rates.join("<br>")}</p>` : ""}` });
			} });
		d.show();
	}

	// Suivi des tâches de fond du mode reconstruit (lecture, traduction du contenu) : même bandeau.
	suivre_reconstruit() {
		this.arreter_suivi();
		const $p = this.$root.find('[data-role="progress"]').show(), $t = this.$root.find('[data-role="progress-txt"]').show();
		const afficher = (e) => {
			// les tâches par langue ont pour clé « MAN:langue » : l'événement porte aussi `manuel`
			if (!e || (e.nom && e.nom !== this.nom && e.manuel !== this.nom)) return;
			$p.find("div").css("width", (e.avancement || 0) + "%");
			$t.text(e.etape || "");
		};
		this._rt = afficher;
		frappe.realtime.on("aqia_manuel", afficher);
		this._minuteur = setInterval(async () => {
			const r = await frappe.call({ method: "aquaworld_ia.manuels.reconstruit.etats", args: { manuel: this.nom } });
			const e = r.message || {}, actif = [e.lecture, ...Object.values(e.traductions || {}), ...Object.values(e.mep || {})].find((x) => x && x.bloque);
			if (!actif) { this.arreter_suivi(); await this.rafraichir_langue(); this.rendre_page(); } else afficher(actif);
		}, 4000);
	}

	// ─── colonne de droite ──────────────────────────────────────────────────────
	rendre_droite() {
		const $d = this.$corps.find('[data-role="droite"]');
		if (!this.langue || !this.pg) { $d.html(""); return; }
		const s = this.sel;
		if (s && s.type === "bloc") { this.panneau_bloc($d, this.pg.blocs.find((b) => String(b.id) === String(s.id))); return; }
		if (s && s.type === "libre") { this.panneau_libre($d, this.edition.libres.find((l) => l.id === s.id)); return; }
		if (s && s.type === "image") { this.panneau_image($d, s.id, (this.pg.images.find((i) => i.id === s.id) || {}).bbox, null); return; }
		this.panneau_page($d);
	}

	panneau_page($d) {
		const pg = this.pg, ligne = this.data.langues.find((l) => l.langue === this.langue) || {};
		const nb = pg.blocs.filter((b) => !b.pivote).length, non = pg.blocs.filter((b) => b.statut === "non_traduit" && b.traduisible && !b.pivote).length;
		const corriges = pg.blocs.filter((b) => b.statut === "corrige").length, pivotes = pg.blocs.filter((b) => b.pivote).length;
		const alertes = (pg.stats && pg.stats.non_places) || [];
		const reduits = Object.entries((pg.stats && pg.stats.blocs) || {}).filter(([, v]) => v.place && v.echelle < 0.8);
		$d.html(`<div class="bloc">
			<h6>${__("Page {0}", [this.no + 1])} <span class="sm-chip">${this._esc(ligne.libelle || this.langue)}</span></h6>
			${pg.image_page ? `<p class="text-muted">${__("Cette page est une image (scan ou schéma) : rien à extraire. Posez des cases de texte par-dessus, ou une zone d'illustration à redessiner par IA.")}</p>` : `<p class="text-muted" style="margin:0">${__("{0} blocs, {1} corrigés, {2} à traduire{3}.", [nb, corriges, non, pivotes ? __(", {0} tournés (laissés en anglais)", [pivotes]) : ""])}</p>`}
			<div class="sm-legende"><span><i style="border-color:#2563eb;background:#2563eb22"></i>${__("traduit")}</span><span><i style="border-color:#16a34a;background:#16a34a22"></i>${__("corrigé")}</span><span><i style="border-color:#94a3b8;border-style:dashed"></i>${__("à traduire")}</span><span><i style="border-color:#ef4444;border-style:dashed"></i>${__("effacé")}</span><span><i style="border-color:#f59e0b;border-style:dashed"></i>${__("illustration")}</span></div>
			${alertes.length ? `<div class="sm-etat alerte">${__("Non placés (texte trop long pour sa boîte) : agrandissez la boîte ou raccourcissez le texte.")}<ul class="sm-liste">${alertes.map((a) => `<li data-bloc="${this._esc(a.id)}">${this._esc(a.texte)}</li>`).join("")}</ul></div>` : ""}
			${reduits.length ? `<div class="sm-etat reduit">${__("Réduits sous 80 % :")} ${reduits.map(([k, v]) => `<a href="#" data-bloc="${this._esc(k)}">${Math.round(v.echelle * 100)} %</a>`).join(", ")}</div>` : ""}
			<p class="text-muted small" style="margin-top:8px">${__("Cliquez un bloc pour le corriger. Glissez-le pour le déplacer, tirez son coin pour l'agrandir.")}</p>
		</div>
		<div class="bloc"><h6>${__("Cette langue")}</h6>
			<div>${__("{0} blocs traduits par IA, {1} corrigés, {2} cases, {3} illustrations IA", [ligne.nb_traduits || 0, ligne.nb_corriges || 0, ligne.nb_libres || 0, ligne.nb_images || 0])}</div>
			${ligne.fichier ? `<div style="margin-top:6px"><a href="${this._esc(ligne.fichier)}" target="_blank">⬇ ${__("PDF actuel")}</a> · ${__("{0} réduits, {1} non placés", [ligne.blocs_reduits || 0, ligne.blocs_non_places || 0])}</div>` : `<div class="text-muted" style="margin-top:6px">${__("Pas encore de PDF : « Générer le PDF » en haut.")}</div>`}
		</div>`);
		$d.find("[data-bloc]").on("click", (e) => { e.preventDefault(); const id = $(e.currentTarget).attr("data-bloc"); this.sel = { type: this.edition.libres.some((l) => l.id === id) ? "libre" : "bloc", id }; this.dessiner(); this.rendre_droite(); });
	}

	panneau_bloc($d, b) {
		if (!b) { this.sel = null; this.panneau_page($d); return; }
		const k = String(b.id), ov = this.edition.blocs[k] || {}, st = ((this.pg.stats || {}).blocs || {})[k];
		const texte = this.edition.textes[k] != null ? this.edition.textes[k] : (this.trad[k] || "");
		const rtl = !!(this.infos && this.infos.rtl);
		const trait = ov.traitement || "traduit";
		$d.html(`<div class="bloc">
			<h6>${__("Bloc")} <span class="sm-chip">${__("page {0}", [this.no + 1])}</span> ${b.pivote ? `<span class="sm-chip echec">${__("tourné")}</span>` : ""} ${this.edition.textes[k] ? `<span class="sm-chip ok">${__("corrigé")}</span>` : (this.trad[k] ? `<span class="sm-chip">${__("IA")}</span>` : `<span class="sm-chip encours">${__("à traduire")}</span>`)}</h6>
			<label>${__("Original (anglais)")}</label><div class="sm-orig">${this._esc(b.texte)}</div>
			${b.pivote ? `<p class="text-muted" style="margin-top:8px">${__("Texte écrit de biais ou à la verticale : le moteur le laisse en anglais. Pour le traduire, effacez-le et posez une case de texte.")}</p>` : ""}
			<label>${__("Traduction ({0})", [this._esc((this.infos || {}).libelle || this.langue)])}</label>
			<textarea data-champ="texte" class="${rtl ? "rtl" : ""}" placeholder="${b.traduisible ? __("Pas encore traduit : « Traduire la page » ou écrivez ici.") : __("Nombre, référence ou adresse : pas traduit par l'IA. Écrivez ici si besoin.")}" ${trait !== "traduit" ? "disabled" : ""}>${this._esc(texte)}</textarea>
			<div class="sm-2"><div><label>${__("Taille max (pt)")}</label><input type="number" step="0.5" min="3" max="72" data-champ="taille" value="${ov.taille || b.style.taille || 10}"></div>
			<div><label>${__("Traitement")}</label><select data-champ="traitement"><option value="traduit" ${trait === "traduit" ? "selected" : ""}>${__("Traduire")}</option><option value="anglais" ${trait === "anglais" ? "selected" : ""}>${__("Laisser en anglais")}</option><option value="efface" ${trait === "efface" ? "selected" : ""}>${__("Effacer (blanc)")}</option></select></div></div>
			${st ? `<div class="sm-etat ${!st.place ? "alerte" : (st.echelle < 0.8 ? "reduit" : "")}">${!st.place ? __("Non placé : le texte ne tient pas, même réduit à 50 %. Agrandissez la boîte (coin) ou raccourcissez.") : (st.echelle < 1 ? __("Posé réduit à {0} %.", [Math.round(st.echelle * 100)]) : __("Posé à sa taille."))}</div>` : ""}
			<div class="sm-btns">
				${b.traduisible && !b.pivote ? `<button class="btn btn-xs btn-default" data-role="retraduire" title="${__("Une nouvelle traduction IA de ce seul bloc (remplace la version IA ; votre correction est retirée)")}">🤖 ${__("Retraduire")}</button>` : ""}
				${this.edition.textes[k] && this.trad[k] ? `<button class="btn btn-xs btn-default" data-role="retablir">${__("Rétablir la version IA")}</button>` : ""}
				${ov.bbox ? `<button class="btn btn-xs btn-default" data-role="position">${__("Position d'origine")}</button>` : ""}
			</div>
			<div class="sm-btns"><button class="btn btn-xs btn-default" data-role="fermer">${__("Fermer")}</button></div>
		</div>`);
		const $t = $d.find('[data-champ="texte"]');
		let minuteur;
		$t.on("input", () => { clearTimeout(minuteur); minuteur = setTimeout(() => this.modifier_texte(b.id, $t.val()), 900); });
		$t.on("change", () => { clearTimeout(minuteur); this.modifier_texte(b.id, $t.val()); });
		$d.find('[data-champ="taille"]').on("change", (e) => this.modifier_bloc(b.id, { taille: parseFloat(e.target.value) || null }));
		$d.find('[data-champ="traitement"]').on("change", (e) => this.modifier_bloc(b.id, { traitement: e.target.value }).then(() => this.rendre_droite()));
		$d.find('[data-role="retraduire"]').on("click", () => this.retraduire_bloc(b.id));
		$d.find('[data-role="retablir"]').on("click", () => { delete this.edition.textes[k]; this.enregistrer().then(() => this.rendre_droite()); });
		$d.find('[data-role="position"]').on("click", () => this.modifier_bloc(b.id, { bbox: null }).then(() => this.rendre_droite()));
		$d.find('[data-role="fermer"]').on("click", () => { this.sel = null; this.dessiner(); this.rendre_droite(); });
	}

	panneau_libre($d, l) {
		if (!l) { this.sel = null; this.panneau_page($d); return; }
		if (l.type === "image") { this.panneau_image($d, l.id, l.bbox, l); return; }
		const st = ((this.pg.stats || {}).blocs || {})[l.id], rtl = !!(this.infos && this.infos.rtl);
		$d.html(`<div class="bloc">
			<h6>${__("Case de texte")} <span class="sm-chip">${__("page {0}", [this.no + 1])}</span></h6>
			<label>${__("Texte")}</label><textarea data-champ="texte" class="${rtl ? "rtl" : ""}" placeholder="${__("Écrivez le texte à poser sur la page")}">${this._esc(l.texte || "")}</textarea>
			<div class="sm-2"><div><label>${__("Taille max (pt)")}</label><input type="number" step="0.5" min="3" max="72" data-champ="taille" value="${l.taille || 10}"></div>
			<div><label>${__("Alignement")}</label><select data-champ="align"><option value="left" ${l.align === "left" ? "selected" : ""}>${__("Gauche")}</option><option value="center" ${l.align === "center" ? "selected" : ""}>${__("Centré")}</option><option value="right" ${l.align === "right" ? "selected" : ""}>${__("Droite")}</option></select></div></div>
			<label class="sm-check"><input type="checkbox" data-champ="gras" ${l.gras ? "checked" : ""}> ${__("Gras")}</label>
			<label class="sm-check"><input type="checkbox" data-champ="fond" ${l.fond !== false ? "checked" : ""}> ${__("Fond blanc (cache ce qu'il y a dessous)")}</label>
			${st ? `<div class="sm-etat ${!st.place ? "alerte" : ""}">${!st.place ? __("Le texte ne tient pas dans la case, même réduit : agrandissez-la.") : (st.echelle < 1 ? __("Posé réduit à {0} %.", [Math.round(st.echelle * 100)]) : __("Posé à sa taille."))}</div>` : ""}
			<div class="sm-btns"><button class="btn btn-xs btn-danger" data-role="supprimer">${__("Supprimer la case")}</button><button class="btn btn-xs btn-default" data-role="fermer">${__("Fermer")}</button></div>
		</div>`);
		const $t = $d.find('[data-champ="texte"]');
		let minuteur;
		$t.on("input", () => { clearTimeout(minuteur); minuteur = setTimeout(() => this.modifier_libre(l.id, { texte: $t.val() }), 900); });
		$t.on("change", () => { clearTimeout(minuteur); this.modifier_libre(l.id, { texte: $t.val() }); });
		if (!l.texte) $t.focus();
		$d.find('[data-champ="taille"]').on("change", (e) => this.modifier_libre(l.id, { taille: parseFloat(e.target.value) || 10 }));
		$d.find('[data-champ="align"]').on("change", (e) => this.modifier_libre(l.id, { align: e.target.value }));
		$d.find('[data-champ="gras"]').on("change", (e) => this.modifier_libre(l.id, { gras: e.target.checked }));
		$d.find('[data-champ="fond"]').on("change", (e) => this.modifier_libre(l.id, { fond: e.target.checked }));
		$d.find('[data-role="supprimer"]').on("click", () => this.supprimer_libre(l.id));
		$d.find('[data-role="fermer"]').on("click", () => { this.sel = null; this.dessiner(); this.rendre_droite(); });
	}

	// Une illustration (détectée dans le PDF, ou zone dessinée) : la redessiner par IA avec ses mots traduits.
	panneau_image($d, id, bbox, libre) {
		if (!bbox) { this.sel = null; this.panneau_page($d); return; }
		const fichier = libre ? libre.fichier : (this.edition.images[id] || {}).fichier;
		const est = this.data.estimation_image || {};
		$d.html(`<div class="bloc">
			<h6>${libre ? __("Zone d'illustration") : __("Illustration")} <span class="sm-chip">${__("page {0}", [this.no + 1])}</span> ${fichier ? `<span class="sm-chip ok">${__("version IA")}</span>` : ""}</h6>
			<canvas class="sm-crop" data-role="crop"></canvas>
			<p class="text-muted small" style="margin-top:6px">${__("L'IA redessine cette région à l'identique en traduisant les mots qu'elle contient. Une image facturée (qualité {0}, ≈ {1} $). Relisez chaque mot et chaque numéro : l'IA redessine.", [est.qualite || "", (est.cout || 0).toFixed(2)])}</p>
			<label>${__("Consigne (facultatif)")}</label><input type="text" data-champ="instruction" placeholder="${__("ex. garder les numéros dans les cercles")}">
			<div class="sm-btns">
				<button class="btn btn-xs btn-primary" data-role="traduire-image">🤖 ${fichier ? __("Réessayer") : __("Traduire les mots de l'image")}</button>
				${fichier ? `<button class="btn btn-xs btn-default" data-role="retirer">${__("Retirer la version IA")}</button>` : ""}
				${libre ? `<button class="btn btn-xs btn-danger" data-role="supprimer">${__("Supprimer la zone")}</button>` : ""}
				<button class="btn btn-xs btn-default" data-role="fermer">${__("Fermer")}</button>
			</div>
			${libre ? `<p class="text-muted small" style="margin-top:6px">${__("Glissez la zone et tirez son coin pour cadrer exactement l'illustration.")}</p>` : ""}
		</div>`);
		this.dessiner_crop($d.find('[data-role="crop"]')[0], bbox);
		$d.find('[data-role="traduire-image"]').on("click", () => this.traduire_illustration(id, bbox, $d.find('[data-champ="instruction"]').val()));
		$d.find('[data-role="retirer"]').on("click", () => {
			if (libre) libre.fichier = null; else delete this.edition.images[id];
			this.enregistrer().then(() => this.rendre_droite());
		});
		$d.find('[data-role="supprimer"]').on("click", () => this.supprimer_libre(id));
		$d.find('[data-role="fermer"]').on("click", () => { this.sel = null; this.dessiner(); this.rendre_droite(); });
	}

	// La région, découpée dans l'image de la page affichée (donc déjà la version IA si elle est posée).
	dessiner_crop(canvas, bbox, img, masques) {
		// en mode En place l'image de la page est dans .sm-page ; en mode Reconstruit, dans .sm-recon-orig
		img = img || this.$corps.find(".sm-page img, .sm-recon-orig img")[0];
		if (!canvas || !img) return;
		const [W, H] = this.pg.format;
		const dess = () => {
			// l'échelle se calcule ICI : avant le décodage, naturalWidth vaut 0 (canvas 1×1 vide, vu le 25/09/2026)
			const sx = img.naturalWidth / W, sy = img.naturalHeight / H;
			const w = Math.max(1, (bbox[2] - bbox[0]) * sx), h = Math.max(1, (bbox[3] - bbox[1]) * sy);
			canvas.width = Math.round(w); canvas.height = Math.round(h);
			const ctx = canvas.getContext("2d");
			ctx.drawImage(img, bbox[0] * sx, bbox[1] * sy, w, h, 0, 0, canvas.width, canvas.height);
			ctx.fillStyle = "#fff";
			(masques || []).forEach((m) => ctx.fillRect((m[0] - bbox[0]) * sx, (m[1] - bbox[1]) * sy, (m[2] - m[0]) * sx, (m[3] - m[1]) * sy));
		};
		// une image data: est « complete » avant d'être décodée (naturalWidth 0 → canvas 1×1 vide, vu le 25/09/2026)
		if (img.naturalWidth) dess();
		else if (img.decode) img.decode().then(dess).catch(() => img.addEventListener("load", dess, { once: true }));
		else img.addEventListener("load", dess, { once: true });
	}

	// ─── actions IA et PDF ──────────────────────────────────────────────────────
	async traduire_page() {
		try {
			const r = await frappe.call({ method: "aquaworld_ia.manuels.studio.traduire_page", args: { manuel: this.nom, langue: this.langue, no: this.no }, freeze: true, freeze_message: __("L'IA traduit la page {0}…", [this.no + 1]) });
			this.trad = r.message.traductions || this.trad;
			frappe.show_alert({ message: r.message.n ? __("{0} blocs traduits.", [r.message.n]) : __("Rien à traduire sur cette page."), indicator: r.message.n ? "green" : "blue" });
			if (r.message.laisses && r.message.laisses.length) frappe.msgprint(__("{0} blocs n'ont pas pu être traduits (laissés en anglais) : réessayez plus tard.", [r.message.laisses.length]));
			this.rendre_page(); this.rafraichir_langue();
		} catch (e) { frappe.msgprint(this._msg(e)); }
	}

	async retraduire_bloc(id) {
		try {
			const r = await frappe.call({ method: "aquaworld_ia.manuels.studio.traduire_page", args: { manuel: this.nom, langue: this.langue, no: this.no, ids: [id] }, freeze: true, freeze_message: __("L'IA retraduit le bloc…") });
			this.trad = r.message.traductions || this.trad;
			delete this.edition.textes[String(id)];
			await this.enregistrer(false);
			this.rendre_page(); this.rafraichir_langue();
		} catch (e) { frappe.msgprint(this._msg(e)); }
	}

	async traduire_illustration(id, bbox, instruction) {
		try {
			const r = await frappe.call({ method: "aquaworld_ia.manuels.studio.traduire_illustration", args: { manuel: this.nom, langue: this.langue, no: this.no, ident: id, bbox, instruction: instruction || "" }, freeze: true, freeze_message: __("L'IA redessine l'illustration (≈ 30 s)…") });
			this._version = (this._version || 0) + 1;
			this.edition = this._lire_edition(r.message.edition);
			frappe.show_alert({ message: __("Illustration redessinée : relisez chaque mot."), indicator: "green" });
			this.rendre_page(); this.rafraichir_langue();
		} catch (e) { frappe.msgprint(this._msg(e)); }
	}

	async rafraichir_langue() {
		try {
			const r = await frappe.call({ method: "aquaworld_ia.manuels.studio.charger", args: { manuel: this.nom } });
			this.data = r.message; this.rendre_barre();
		} catch (e) { /* le prochain chargement corrigera */ }
	}

	traduire_tout() {
		const ligne = this.data.langues.find((l) => l.langue === this.langue) || {};
		frappe.confirm(__("Traduire par IA tous les blocs du manuel en {0} ? Quelques centimes et une à trois minutes pour 40 pages. Vos corrections, cases et illustrations sont gardées ; les traductions IA existantes sont refaites.", [ligne.libelle || this.langue]), async () => {
			try {
				await frappe.call({ method: "aquaworld_ia.manuels.job.lancer", args: { manuel: this.nom, langues: [this.langue] }, freeze: true });
				this.suivre();
			} catch (e) { frappe.msgprint(this._msg(e)); }
		});
	}

	async composer() {
		try {
			const r = await frappe.call({ method: "aquaworld_ia.manuels.studio.composer", args: { manuel: this.nom, langue: this.langue }, freeze: true, freeze_message: __("Mise en page du PDF…") });
			const l = r.message.ligne, i = this.data.langues.findIndex((x) => x.langue === l.langue);
			if (i >= 0) this.data.langues[i] = l;
			this.rendre_barre(); this.rendre_droite();
			const s = r.message.stats || {};
			frappe.msgprint({ title: __("PDF généré"), indicator: "green", message: `${__("{0} blocs posés, {1} réduits, {2} non placés.", [s.poses || 0, s.reduits || 0, (s.non_places || []).length])} <a href="${this._esc(l.fichier)}" target="_blank">⬇ ${__("Ouvrir le PDF")}</a>` });
		} catch (e) { frappe.msgprint(this._msg(e)); }
	}

	async combiner() {
		try {
			const r = await frappe.call({ method: "aquaworld_ia.manuels.studio.combiner", args: { manuel: this.nom }, freeze: true, freeze_message: __("Assemblage du PDF toutes langues…") });
			this.data.doc.pdf_combine = r.message.fichier; this.rendre_barre();
			frappe.msgprint({ title: __("PDF toutes langues"), indicator: "green", message: `${this._esc(r.message.parties.join(" → "))} <br><a href="${this._esc(r.message.fichier)}" target="_blank">⬇ ${__("Ouvrir le PDF")}</a>` });
		} catch (e) { frappe.msgprint(this._msg(e)); }
	}

	ajouter_langue() {
		const dispo = this.data.langues_dispo || [];
		const dlg = new frappe.ui.Dialog({ title: __("Ajouter des langues"),
			fields: [{ fieldtype: "HTML", options: `<p class="text-muted small">${__("Cochez toutes les langues voulues : chacune aura son onglet, et les actions (traduire, mettre en page, générer) se lancent pour plusieurs langues à la fois.")}</p>` },
			         ...dispo.map((l) => ({ fieldtype: "Check", fieldname: "l_" + l.code, label: `${l.libelle} (${l.code})`, default: 1 }))],
			primary_action_label: __("Ajouter"),
			primary_action: async (v) => {
				const codes = dispo.map((l) => l.code).filter((c) => v["l_" + c]);
				if (!codes.length) { frappe.msgprint(__("Cochez au moins une langue.")); return; }
				dlg.hide();
				try {
					const r = await frappe.call({ method: "aquaworld_ia.manuels.studio.ajouter_langues", args: { manuel: this.nom, codes }, freeze: true });
					this.data = r.message; this.rendre_barre(); this.rendre_gauche();
					await this.charger_langue(codes[0]);
				} catch (e) { frappe.msgprint(this._msg(e)); }
			} });
		dlg.show();
	}

	// Un choix de langues (toutes cochées par défaut, la langue courante en tête) pour une action collective.
	choisir_langues(titre, note, action_label, sur_choix) {
		const langues = this.data.langues || [];
		const dlg = new frappe.ui.Dialog({ title: titre,
			fields: [{ fieldtype: "HTML", options: `<p class="text-muted small">${note}</p>` },
			         ...langues.map((l) => ({ fieldtype: "Check", fieldname: "l_" + l.langue, label: `${l.libelle || l.langue}${l.langue === this.langue ? " — " + __("langue affichée") : ""}`, default: 1 }))],
			primary_action_label: action_label,
			primary_action: (v) => {
				const codes = langues.map((l) => l.langue).filter((c) => v["l_" + c]);
				if (!codes.length) { frappe.msgprint(__("Cochez au moins une langue.")); return; }
				dlg.hide(); sur_choix(codes);
			} });
		dlg.show();
	}

	// ─── suivi du job « Traduire tout » ────────────────────────────────────────
	suivre() {
		this.arreter_suivi();
		const $p = this.$root.find('[data-role="progress"]').show(), $t = this.$root.find('[data-role="progress-txt"]').show();
		const afficher = (e) => {
			if (!e || (e.nom && e.nom !== this.nom)) return;
			$p.find("div").css("width", (e.avancement || 0) + "%");
			$t.text(e.etape || "");
			if (e.fin || e.avancement >= 100) { this.arreter_suivi(); this.recharger(); }
		};
		this._rt = afficher;
		frappe.realtime.on("aqia_manuel", afficher);
		this._minuteur = setInterval(async () => {
			const r = await frappe.call({ method: "aquaworld_ia.manuels.job.etat_manuel", args: { manuel: this.nom } });
			const e = r.message || {};
			if (e.statut && e.statut !== "en cours") { this.arreter_suivi(); this.recharger(); } else afficher(e);
		}, 4000);
	}

	arreter_suivi() {
		if (this._rt) frappe.realtime.off("aqia_manuel", this._rt);
		if (this._minuteur) clearInterval(this._minuteur);
		this._rt = null; this._minuteur = null;
		this.$root.find('[data-role="progress"], [data-role="progress-txt"]').hide();
	}

	_esc(v) { return frappe.utils.escape_html(String(v == null ? "" : v)); }
	_msg(e) {
		const m = (e && (e.message || (e._server_messages && JSON.parse(e._server_messages)[0]))) || e;
		try { return typeof m === "string" ? (JSON.parse(m).message || m) : JSON.stringify(m); } catch (_x) { return String(m); }
	}
}
