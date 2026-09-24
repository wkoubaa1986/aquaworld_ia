// Studio emballage — la page plein écran pour concevoir un emballage.
//
// Colonne de gauche : les quatre étapes (forme, contenus, style & variantes, plan). Centre : la
// scène (plan interactif, galerie des variantes, artwork, 3D). Droite : la face survolée, le
// coût, les fichiers. Toute action passe par les mêmes points d'entrée que la fiche : le studio
// n'a aucune règle à lui.
frappe.pages["studio-emballage"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({ parent: wrapper, title: __("Studio emballage"), single_column: true });
	wrapper.studio = new StudioEmballage(wrapper);
};
frappe.pages["studio-emballage"].on_page_show = function (wrapper) {
	if (wrapper.studio) wrapper.studio.depuis_route();
};

class StudioEmballage {
	constructor(wrapper) {
		this.page = wrapper.page;
		this.$root = $(wrapper).find(".layout-main-section");
		this.$root.append(frappe.render_template("studio_emballage", {}));
		this.$barre = this.$root.find('[data-role="barre"]');
		this.$corps = this.$root.find('[data-role="corps"]');
		this.onglet = "plan";
		this.etape = 1;
		this.epinglee = null;
		this.page.set_primary_action(__("Nouveau design"), () => this.nouveau(), "add");
		this.depuis_route();
	}

	// ─── chargement ─────────────────────────────────────────────────────────────
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
		this.nom = nom;
		this.arreter_suivi();
		try {
			const r = await frappe.call({ method: "aquaworld_ia.emballage.studio.charger", args: { design: nom } });
			this.data = r.message;
		} catch (e) {
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
		const r = await frappe.call({ method: "aquaworld_ia.emballage.studio.charger", args: { design: this.nom } });
		this.data = r.message; this.d = this.data.doc; this._lire_mep();
		this.rendre();
	}

	_lire_mep() {
		try { this.mep = JSON.parse(this.d.mise_en_page || "{}") || {}; } catch (e) { this.mep = {}; }
	}

	async enregistrer(valeurs) {
		const r = await frappe.call({ method: "aquaworld_ia.emballage.studio.enregistrer",
			args: { design: this.nom, valeurs }, freeze: false });
		this.data = r.message; this.d = this.data.doc; this._lire_mep();
		this.rendre_scene(); this.rendre_droite(); this.rendre_barre(); this.rendre_etats_etapes();
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
		const d = this.d;
		if (!this._dims_ok()) return 1;
		if (!d.textes_ia) return 2;
		if (!(d.variantes || []).some((v) => v.statut === "Prête") || !d.variante_choisie) return 3;
		return 4;
	}
	_onglet_par_defaut() {
		const d = this.d;
		if (d.plan_a_plat && this.etape === 4) return "artwork";
		if ((d.variantes || []).length && this.etape >= 3) return "variantes";
		return "plan";
	}

	// ─── rendu ──────────────────────────────────────────────────────────────────
	rendre() {
		this.rendre_barre();
		this.$corps.html(`<div class="se-grid">
			<div class="se-col se-gauche"></div>
			<div class="se-col"><div class="se-centre"><div class="se-onglets"></div><div class="se-scene"></div></div></div>
			<div class="se-col se-droite"></div></div>`);
		this.rendre_gauche();
		this.rendre_scene();
		this.rendre_droite();
	}

	rendre_barre() {
		const d = this.d;
		const chip = { "Plan prêt": "ok", "Variantes prêtes": "ok", "Textes prêts": "ok", "Variantes en cours": "encours", "Échec": "echec" }[d.statut] || "";
		this.$barre.html(`
			<select data-role="selecteur"><option value="${this._esc(d.name)}">${this._esc(d.nom_produit || d.name)} · ${this._esc(d.name)}</option></select>
			<span class="se-titre">${this._esc(d.nom_produit || d.article || "")}</span>
			<span class="se-chip ${chip}">${this._esc(d.statut || "")}</span>
			<span class="se-chip">${this._esc(d.type_boite || "")}</span>
			<a class="btn btn-xs btn-default" href="/app/design-emballage/${encodeURIComponent(d.name)}">${__("Fiche")}</a>
			<span class="se-cout">${__("Coût IA de ce design : {0} $", [((this.data.etat || {}).cout_document || 0).toFixed(3)])}</span>`);
		const $sel = this.$barre.find('[data-role="selecteur"]');
		$sel.on("focus", async () => {
			if ($sel.data("charge")) return;
			const r = await frappe.call({ method: "aquaworld_ia.emballage.studio.liste", args: { limite: 30 } });
			$sel.html((r.message || []).map((l) => `<option value="${this._esc(l.name)}" ${l.name === d.name ? "selected" : ""}>${this._esc(l.nom_produit || l.name)} · ${this._esc(l.name)} · ${this._esc(l.statut || "")}</option>`).join(""));
			$sel.data("charge", 1);
		});
		$sel.on("change", () => frappe.set_route("studio-emballage", $sel.val()));
	}

	rendre_gauche() {
		const d = this.d, esc = this._esc;
		const types = (this.data.types || []).map((t) => `
			<div class="se-type${t.type === d.type_boite ? " active" : ""}" data-type="${esc(t.type)}" title="${esc(t.description)}">${t.svg}<div class="nom">${esc(t.type)}</div></div>`).join("");
		const type = (this.data.types || []).find((t) => t.type === d.type_boite);
		const dims = type ? type.dimensions : ["Largeur", "Hauteur", "Profondeur"];
		// Un champ par dimension que la forme connaît (libellé null = sans objet, champ masqué).
		const champs_dims = ["L", "H", "P", "R"].map((k, i) => dims[i]
			? `<div><label>${esc(dims[i])}</label><input type="number" step="0.5" min="1" data-champ="${StudioEmballage.CHAMPS_DIMS[k]}" value="${d[StudioEmballage.CHAMPS_DIMS[k]] || ""}"></div>`
			: "").join("");
		const langues = (this.data.langues || []).map((l) => `<span class="c ${(d.langues || []).some((x) => x.langue === l.code) ? "on" : ""}" data-langue="${esc(l.code)}">${esc(l.libelle)}</span>`).join("");
		const pictos = (this.data.pictos || []).map((p) => `<span class="c pic ${(d.pictogrammes || []).some((x) => x.pictogramme === p.code) ? "on" : ""}" data-picto="${esc(p.code)}" title="${esc(p.categorie || "")}">${p.url ? `<img src="${esc(p.url)}" alt="">` : ""}${esc(p.libelle)}</span>`).join("")
			+ `<span class="c ajout" data-ajouter-picto="1" title="${__("Ajouter un pictogramme ou une certification depuis une image")}">＋ ${__("Ajouter")}</span>`;
		const fichier = (champ, libelle) => `
			<label>${libelle}</label>
			<div class="se-fichier">
				${d[champ] ? `<img src="${esc(d[champ])}" alt="">` : `<span class="text-muted small">${__("aucun fichier")}</span>`}
				<button class="btn btn-xs btn-default" data-televerser="${champ}">${d[champ] ? __("Remplacer") : __("Choisir un fichier")}</button>
				${d[champ] ? `<button class="btn btn-xs btn-default" data-effacer="${champ}">✕</button>` : ""}
				${champ === "logo" && (d.logo || d.marque) ? `<button class="btn btn-xs btn-default" data-action="logo_ia" title="${__("Changer les couleurs, épurer, moderniser — par IA, avant de le poser")}">✨ ${__("Retoucher par IA")}</button>` : ""}
				${champ === "photo_produit" && d.photo_produit ? `<button class="btn btn-xs btn-default" data-action="photo_ia" title="${__("Détourer sur blanc pur, éclairage studio, retirer les accessoires — par IA, plusieurs propositions")}">✨ ${__("Améliorer par IA")}</button>` : ""}
				${champ === "logo" || champ === "image_fond" ? `<button class="btn btn-xs btn-default" data-bibliotheque="${champ}" title="${__("Reprendre un fond, un motif ou une variante de logo gardés en bibliothèque")}">📚 ${__("Bibliothèque")}</button>` : ""}
				${(champ === "logo" || champ === "image_fond") && d[champ] ? `<button class="btn btn-xs btn-default" data-garder="${champ}" title="${__("Garder ce fichier en bibliothèque, sous un nom, pour un autre design")}">💾 ${__("Garder")}</button>` : ""}
			</div>`;
		const pretes = (d.variantes || []).filter((v) => v.statut === "Prête").length;
		const a_generer = (d.variantes || []).filter((v) => ["À générer", "Échec"].includes(v.statut)).length;
		const est = this.data.estimation || {};

		this.$root.find(".se-gauche").html(`
			<div class="se-etape" data-etape="1">
				<div class="se-tete"><span class="num">1</span>${__("Forme et dimensions")}</div>
				<div class="se-corps">
					<div class="se-types">${types}</div>
					<p class="text-muted small" style="margin:6px 0 0">${type ? esc(type.description) : ""}</p>
					<div class="se-3" style="grid-template-columns:repeat(${dims.filter(Boolean).length > 3 ? 2 : 3},1fr)">${champs_dims}</div>
					<details style="margin-top:8px"><summary class="small text-muted">${__("Fond perdu, zone de sécurité, patte")}</summary>
						<div class="se-3">
							<div><label>${__("Fond perdu")}</label><input type="number" step="0.5" min="0" data-champ="fond_perdu_mm" value="${d.fond_perdu_mm}"></div>
							<div><label>${__("Sécurité")}</label><input type="number" step="0.5" min="0" data-champ="zone_securite_mm" value="${d.zone_securite_mm}"></div>
							<div><label>${__("Patte")}</label><input type="number" step="0.5" min="0" data-champ="patte_collage_mm" value="${d.patte_collage_mm}"></div>
						</div></details>
				</div>
			</div>
			<div class="se-etape" data-etape="2">
				<div class="se-tete"><span class="num">2</span>${__("Contenus")}</div>
				<div class="se-corps">
					<label>${__("Nom du produit")}</label><input type="text" data-champ="nom_produit" value="${esc(d.nom_produit || "")}">
					${fichier("logo", __("Logo (photo ou SVG)"))}
					${fichier("photo_produit", __("Photo du produit"))}
					<label>${__("Langues")}</label><div class="se-chips" data-liste="langues">${langues}</div>
					<label>${__("Caractéristiques (une par ligne)")}</label><textarea data-champ="caracteristiques">${esc(d.caracteristiques || "")}</textarea>
					<label>${__("Avertissements (un par ligne)")}</label><textarea data-champ="avertissements">${esc(d.avertissements || "")}</textarea>
					<label>${__("Contact")}</label><textarea data-champ="contact">${esc(d.contact || "")}</textarea>
					<label>${__("Pictogrammes et certifications")}</label><div class="se-chips" data-liste="pictogrammes">${pictos}</div>
					<label class="se-check"><input type="checkbox" data-champ="pictos_sans_cartouche" ${d.pictos_sans_cartouche ? "checked" : ""} title="${__("Posés en transparence ; les pictogrammes monochromes prennent la couleur du texte de la face. Code-barres et QR gardent leur cartouche pour le scan.")}"> ${__("Sans cartouche blanc (en transparence)")}</label>
					<div class="se-3" style="grid-template-columns:1fr 1.4fr">
						<div><label>${__("Code")}</label><select data-champ="type_code_barres">${["EAN-13", "QR", "EAN-13 + QR", "Aucun"].map((o) => `<option ${o === d.type_code_barres ? "selected" : ""}>${o}</option>`).join("")}</select></div>
						<div><label>${__("EAN-13")}</label><input type="text" data-champ="code_barres" value="${esc(d.code_barres || "")}"></div>
					</div>
					<label>${__("URL du QR")}</label><input type="text" data-champ="url_qr" value="${esc(d.url_qr || "")}">
				</div>
			</div>
			<div class="se-etape" data-etape="3">
				<div class="se-tete"><span class="num">3</span>${__("Style et variantes")}</div>
				<div class="se-corps">
					<label>${__("Fond de l'emballage")}</label>
					<div class="se-3" style="grid-template-columns:auto 1fr;align-items:center">
						<input type="color" data-champ="couleur_fond" value="${esc(d.couleur_fond || "#e5e7eb")}" style="width:44px;height:30px;padding:2px" title="${__("Couleur de fond")}">
						<span class="small text-muted">${d.couleur_fond ? esc(d.couleur_fond) + ` <a href="#" data-effacer="couleur_fond">✕</a>` : __("Sans couleur choisie : la dominante du visuel IA.")}</span>
					</div>
					${fichier("image_fond", __("Image de fond (texture, motif)"))}
					<div class="se-btns" style="margin-top:6px"><button class="btn btn-sm btn-default" data-action="fond" ${this._dims_ok() ? "" : "disabled"}>${__("Fond IA · 1 image · ≈ {0} $", [(est.cout || 0).toFixed(2)])}</button></div>
					<label class="se-check"><input type="checkbox" data-champ="fond_continu" ${d.fond_continu ? "checked" : ""}> ${__("Fond continu sur toutes les faces (panorama découpé aux plis)")}</label>
					<label class="se-check"><input type="checkbox" data-champ="faces_identiques" ${d.faces_identiques ? "checked" : ""}> ${__("Face arrière identique à la face avant")}</label>
					<label class="se-check"><input type="checkbox" data-champ="cotes_identiques" ${d.cotes_identiques ? "checked" : ""} title="${__("Avec le dos identique à l'avant, le code-barres et les avertissements sont dupliqués sur les deux côtés.")}"> ${__("Côtés identiques (gauche = droit)")}</label>
					<p class="text-muted small" style="margin:2px 0 6px">${__("Avec une couleur ou une image de fond et la photo du produit, le plan se compose aussi SANS variante IA.")}</p>
					<label>${__("Brief de style")}</label><textarea data-champ="brief_style" placeholder="${__("ex. haut de gamme, bleu profond, minimaliste")}">${esc(d.brief_style || "")}</textarea>
					<div class="se-3" style="grid-template-columns:1.6fr 1fr">
						<div><label>${__("Palette (hex)")}</label><input type="text" data-champ="palette" value="${esc(d.palette || "")}"></div>
						<div><label>${__("Variantes")}</label><input type="number" min="1" max="4" data-champ="nb_variantes" value="${d.nb_variantes || 3}"></div>
					</div>
					<div class="se-btns">
						<button class="btn btn-sm btn-default" data-action="preparer">${d.textes_ia ? __("Re-préparer textes et styles") : __("Préparer textes et styles (IA)")}</button>
						${d.textes_ia ? `<button class="btn btn-sm btn-default" data-action="textes">${__("Modifier les textes")}</button>` : ""}
						<button class="btn btn-sm btn-primary" data-action="generer" ${d.textes_ia && a_generer ? "" : "disabled"} title="${!d.textes_ia ? __("Préparez d'abord les textes.") : ""}">${__("Générer {0} variante(s) · ≈ {1} $", [a_generer, ((est.cout || 0) * a_generer).toFixed(2)])}</button>
					</div>
					<p class="text-muted small" style="margin:6px 0 0">${__("{0} variante(s) prête(s). Choisissez-en une dans la galerie.", [pretes])}</p>
				</div>
			</div>
			<div class="se-etape" data-etape="4">
				<div class="se-tete"><span class="num">4</span>${__("Plan à plat et rendus")}</div>
				<div class="se-corps">
					<div class="se-btns">
						<button class="btn btn-sm btn-primary" data-action="composer" ${d.variante_choisie || d.couleur_fond || d.image_fond ? "" : "disabled"}>${d.variante_choisie ? __("Composer le plan à plat") : __("Composer sans IA (fond + photo)")}</button>
						<button class="btn btn-sm btn-default" data-action="faces" ${d.variante_choisie ? "" : "disabled"}>${__("Faces secondaires par IA · 5 images")}</button>
						<button class="btn btn-sm btn-default" data-action="mockup" ${d.plan_a_plat ? "" : "disabled"}>${__("Aperçu 3D · 1 image")}</button>
					</div>
					${d.plan_a_plat ? `<p class="small" style="margin:8px 0 0"><a href="${esc(d.plan_a_plat)}" target="_blank">${__("Télécharger le PDF imprimeur")}</a></p>` : ""}
					${d.faces_ia ? `<p class="small text-muted" style="margin:4px 0 0">${__("Faces secondaires IA générées.")}</p>` : ""}
				</div>
			</div>`);
		this.rendre_etats_etapes();
		this.lier_gauche();
	}

	rendre_etats_etapes() {
		const d = this.d;
		const faites = {
			1: this._dims_ok(),
			2: !!d.textes_ia || !!(d.caracteristiques || "").trim(),
			3: !!d.variante_choisie,
			4: !!d.plan_a_plat,
		};
		this.$root.find(".se-etape").each((_i, el) => {
			const n = +$(el).attr("data-etape");
			$(el).toggleClass("faite", !!faites[n]).toggleClass("active", n === this.etape);
		});
	}

	lier_gauche() {
		const $g = this.$root.find(".se-gauche");
		$g.find(".se-tete").on("click", (e) => {
			this.etape = +$(e.currentTarget).parent().attr("data-etape");
			this.rendre_etats_etapes();
			const o = { 1: "plan", 2: "plan", 3: "variantes", 4: this.d.plan_a_plat ? "artwork" : "plan" }[this.etape];
			if (o !== this.onglet) { this.onglet = o; this.rendre_scene(); }
		});
		$g.find(".se-type").on("click", (e) => this.modifier({ type_boite: $(e.currentTarget).attr("data-type") }, true));
		const sauver = frappe.utils.debounce((champ, val) => this.modifier({ [champ]: val }, false), 500);
		$g.find("[data-champ]").on("input change", (e) => {
			const $i = $(e.currentTarget), champ = $i.attr("data-champ");
			if ($i.is("input[type=checkbox]")) { if (e.type === "change") this.modifier({ [champ]: $i.is(":checked") ? 1 : 0 }, true); return; }
			if ($i.is("input[type=color]")) { if (e.type === "change") this.modifier({ [champ]: $i.val() }, true); return; }
			if (e.type === "change" || $i.is("textarea, input[type=text]")) sauver(champ, $i.val());
			if (e.type === "input" && $i.is("input[type=number]")) sauver(champ, $i.val());
		});
		$g.find("[data-ajouter-picto]").on("click", () => this.ajouter_picto());
		$g.find("[data-liste] .c").on("click", (e) => {
			const $c = $(e.currentTarget), liste = $c.parent().attr("data-liste");
			$c.toggleClass("on");
			const attr = liste === "langues" ? "data-langue" : "data-picto";
			const codes = $c.parent().find(".c.on").map((_i, el) => $(el).attr(attr)).get();
			this.modifier({ [liste]: codes }, false);
		});
		$g.find("[data-televerser]").on("click", (e) => this.televerser($(e.currentTarget).attr("data-televerser")));
		$g.find("[data-effacer]").on("click", (e) => { e.preventDefault(); this.modifier({ [$(e.currentTarget).attr("data-effacer")]: "" }, true); });
		$g.find("[data-bibliotheque]").on("click", (e) => this.bibliotheque($(e.currentTarget).attr("data-bibliotheque")));
		$g.find("[data-garder]").on("click", (e) => this.garder($(e.currentTarget).attr("data-garder")));
		$g.find("[data-action]").on("click", (e) => this.action($(e.currentTarget).attr("data-action")));
	}

	async modifier(valeurs, redessiner_gauche) {
		try {
			await this.enregistrer(valeurs);
		} catch (e) {
			frappe.msgprint(this._msg(e));
			return;
		}
		if (redessiner_gauche) this.rendre_gauche();
	}

	televerser(champ) {
		new frappe.ui.FileUploader({
			doctype: "Design Emballage", docname: this.nom, folder: "Home/Attachments",
			restrictions: { allowed_file_types: ["image/*", ".svg"] },
			on_success: (file) => this.modifier({ [champ]: file.file_url }, true),
		});
	}

	// ─── scène (centre) ─────────────────────────────────────────────────────────
	rendre_scene() {
		const d = this.d;
		const onglets = [["plan", __("Plan")], ["variantes", __("Variantes ({0})", [(d.variantes || []).length])],
			["artwork", __("Artwork")], ["3d", __("3D")]];
		this.$root.find(".se-onglets").html(onglets.map(([k, l]) => `<div class="o ${k === this.onglet ? "on" : ""}" data-onglet="${k}">${l}</div>`).join(""))
			.find(".o").on("click", (e) => { this.onglet = $(e.currentTarget).attr("data-onglet"); this.rendre_scene(); });
		const $s = this.$root.find(".se-scene");
		if (this.onglet === "plan") return this.scene_plan($s);
		if (this.onglet === "variantes") return this.scene_variantes($s);
		if (this.onglet === "artwork") return $s.html(d.apercu_plan ? `<img class="se-img" src="${this._esc(d.apercu_plan)}" alt=""><p class="text-muted small text-center" style="margin-top:8px">${__("Aperçu à l'écran. Le PDF imprimeur est à l'échelle, avec le calque de découpe.")}</p>` : `<div class="se-vide">${__("Pas encore de plan composé : choisissez une variante puis « Composer le plan à plat ».")}</div>`);
		if (this.onglet === "3d") return $s.html(d.apercu_3d ? `<img class="se-img" src="${this._esc(d.apercu_3d)}" alt=""><p class="text-muted small text-center" style="margin-top:8px">${__("Illustration non contractuelle.")}</p>` : `<div class="se-vide">${__("Pas encore de rendu 3D : composez le plan, puis « Aperçu 3D ».")}</div>`);
	}

	scene_plan($s) {
		const a = this.data.apercu;
		if (!a) return $s.html(`<div class="se-vide">${__("Saisissez les dimensions de la forme pour voir le plan.")}</div>`);
		if (a.erreur) return $s.html(`<div class="se-vide text-danger">${this._esc(a.erreur)}</div>`);
		const pb = (a.problemes || []).length ? `<p class="text-danger small">⛔ ${a.problemes.map(this._esc).join(" · ")}</p>` : "";
		const infos = {};
		(a.faces || []).forEach((f) => { infos[f.code] = f; });
		// Barre d'outils de la face épinglée, AU-DESSUS du plan : ajouter une zone (logo, photo,
		// pictogrammes…), revenir à la maquette, libérer — la colonne de droite n'est pas toujours visible.
		const fe = this.epinglee && infos[this.epinglee];
		const TYPES = ["logo", "nom", "accroche", "caracteristiques", "avertissements", "contact", "pictos", "code_barres", "photo"];
		const LIBS = { logo: __("Logo"), nom: __("Nom du produit"), accroche: __("Accroche"), caracteristiques: __("Caractéristiques"), avertissements: __("Avertissements"), contact: __("Contact"), pictos: __("Pictogrammes / certifications"), code_barres: __("Code-barres"), photo: __("Photo produit") };
		const outils = fe ? `<div class="se-outils" style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;padding:6px 8px;margin-bottom:6px;border:1px solid #bfdbfe;background:#eff6ff;border-radius:8px;font-size:12.5px">
				<b>${this._esc(fe.libelle)}</b> <span class="text-muted">${__("épinglée")}</span>
				<span style="margin-left:8px">${__("Ajouter :")}</span>
				<select class="form-control input-xs" data-role="type-zone-plan" style="height:26px;font-size:12px;width:auto;display:inline-block">${TYPES.map((t) => `<option value="${t}">${LIBS[t]}</option>`).join("")}</select>
				<button class="btn btn-xs btn-primary" data-role="ajouter-zone-plan">＋ ${__("Ajouter la zone")}</button>
				${fe.personnalisee ? `<button class="btn btn-xs btn-default" data-role="reinit-face-plan">${__("Revenir à la maquette automatique")}</button>` : ""}
				<button class="btn btn-xs btn-default" data-role="liberer-face-plan">${__("Libérer")}</button>
				<span class="text-muted" style="flex-basis:100%">${__("Glissez une zone pour la déplacer, tirez son coin pour l'agrandir, × pour la supprimer, cliquez-la pour ses réglages (cartouche, logo, pictogrammes).")}</span>
				${fe.copie_bloquee ? `<span class="text-danger" style="flex-basis:100%">⚠ ${__("Cette face devrait copier « {0} » (option cochée) mais elle a sa propre mise en page dessinée : elle ne suit plus. « Revenir à la maquette automatique » pour qu'elle recopie.", [this._esc((infos[fe.copie_bloquee] || {}).libelle || fe.copie_bloquee)])}</span>` : ""}
			</div>` : "";
		$s.html(`<p class="text-muted small">${__("Feuille <b>{0} × {1} mm</b>, fond perdu inclus. Survolez une face, cliquez pour l'épingler.", [a.feuille.w, a.feuille.h])}</p>${pb}${outils}${a.svg}`);
		$s.find('[data-role="ajouter-zone-plan"]').on("click", () => this.ajouter_zone($s.find('[data-role="type-zone-plan"]').val()));
		$s.find('[data-role="reinit-face-plan"]').on("click", () => this.reinitialiser_face(this.epinglee));
		$s.find('[data-role="liberer-face-plan"]').on("click", () => { this.epinglee = null; this.zone_sel = null; this.rendre_scene(); this.face_info(null); });
		const montrer = (code) => {
			$s.find(".aqia-zones").hide();
			$s.find(`.aqia-zones[data-face="${code}"]`).show();
			this.face_info(infos[code]);
		};
		$s.find("rect.aqia-face.imprimable")
			.on("mouseenter", (e) => { if (!this.epinglee) montrer($(e.currentTarget).attr("data-face")); })
			.on("mouseleave", () => { if (!this.epinglee) { $s.find(".aqia-zones").hide(); this.face_info(null); } })
			.on("click", (e) => {
				// Épingler ou libérer, puis redessiner la scène : c'est le rendu qui pose (ou retire)
				// l'éditeur de zones, jamais le clic seul.
				const code = $(e.currentTarget).attr("data-face");
				this.epinglee = this.epinglee === code ? null : code;
				this.zone_sel = null;
				this.rendre_scene();
				if (!this.epinglee) this.face_info(null);
			});
		if (this.epinglee && infos[this.epinglee]) {
			$s.find(`rect.aqia-face[data-face="${this.epinglee}"]`).addClass("epinglee");
			montrer(this.epinglee);
			this.editer_zones($s, infos[this.epinglee]);
		}
	}

	// ─── éditeur de zones : déplacer, agrandir, supprimer, ajouter ──────────────
	editer_zones($s, face) {
		const svg = $s.find("svg.aqia-plan")[0];
		if (!svg) return;
		$s.find(`.aqia-zones[data-face="${face.code}"]`).hide();
		const NS = "http://www.w3.org/2000/svg";
		const W = svg.viewBox.baseVal.width, POIGNEE = Math.max(2.5, W / 90);
		const g = document.createElementNS(NS, "g"); g.setAttribute("class", "se-edit"); svg.appendChild(g);
		const zones = (face.zones || []).map((z) => ({ zone: z.zone, x: z.x, y: z.y, w: z.w, h: z.h, libelle: z.libelle, style: z.style || null, logo: z.logo || null, pictos: z.pictos || null }));
		const u = face.utile || face;   // une zone ne va jamais dans une bande réservée (repli agrafé)
		const el = (tag, attrs) => { const n = document.createElementNS(NS, tag); Object.entries(attrs).forEach(([k, v]) => n.setAttribute(k, v)); g.appendChild(n); return n; };
		const point = (e) => { const pt = svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY; return pt.matrixTransform(svg.getScreenCTM().inverse()); };
		const sauver = () => {
			this.mep[face.code] = zones.map((z) => Object.assign({ zone: z.zone, x: z.x, y: z.y, w: z.w, h: z.h }, z.style ? { style: z.style } : {}, z.logo ? { logo: z.logo } : {}, z.pictos && z.pictos.length ? { pictos: z.pictos } : {}));
			this.modifier({ mise_en_page: this.mep }, false);
		};
		zones.forEach((z, i) => {
			const fond = z.style && z.style.fond;
			const r = el("rect", { x: z.x, y: z.y, width: z.w, height: z.h, rx: fond ? (z.style.rayon || 0) : 0, fill: fond || "#f59e0b", "fill-opacity": fond ? "0.55" : "0.18",
				stroke: this.zone_sel === i ? "#dc2626" : "#d97706", "stroke-width": this.zone_sel === i ? W / 350 : W / 700, style: "cursor:move" });
			const t = el("text", { x: z.x + W / 400, y: z.y + Math.max(2, Math.min(z.w, z.h) / 4), "font-size": Math.max(2, Math.min(Math.min(z.w, z.h) / 4, W / 70)), fill: "#92400e", "font-family": "sans-serif", style: "pointer-events:none" });
			t.textContent = z.libelle || z.zone;
			const p = el("rect", { x: z.x + z.w - POIGNEE, y: z.y + z.h - POIGNEE, width: POIGNEE, height: POIGNEE, fill: "#d97706", style: "cursor:nwse-resize" });
			const x = el("text", { x: z.x + z.w - POIGNEE * 0.9, y: z.y + POIGNEE * 1.1, "font-size": POIGNEE * 1.3, fill: "#b91c1c", "font-family": "sans-serif", style: "cursor:pointer;font-weight:bold" });
			x.textContent = "×"; x.addEventListener("click", (e) => { e.stopPropagation(); zones.splice(i, 1); sauver(); });
			const glisser = (mode) => (e) => {
				e.preventDefault(); e.stopPropagation();
				const p0 = point(e), z0 = { ...z };
				const bouger = (ev) => {
					const q = point(ev), dx = q.x - p0.x, dy = q.y - p0.y;
					if (mode === "move") { z.x = Math.min(Math.max(z0.x + dx, u.x), u.x + u.w - z.w); z.y = Math.min(Math.max(z0.y + dy, u.y), u.y + u.h - z.h); }
					else { z.w = Math.max(3, Math.min(z0.w + dx, u.x + u.w - z.x)); z.h = Math.max(3, Math.min(z0.h + dy, u.y + u.h - z.y)); }
					r.setAttribute("x", z.x); r.setAttribute("y", z.y); r.setAttribute("width", z.w); r.setAttribute("height", z.h);
					p.setAttribute("x", z.x + z.w - POIGNEE); p.setAttribute("y", z.y + z.h - POIGNEE);
					t.setAttribute("x", z.x + W / 400); t.setAttribute("y", z.y + Math.max(2, Math.min(z.w, z.h) / 4));
					x.setAttribute("x", z.x + z.w - POIGNEE * 0.9); x.setAttribute("y", z.y + POIGNEE * 1.1);
				};
				const lacher = () => {
					document.removeEventListener("mousemove", bouger); document.removeEventListener("mouseup", lacher);
					if (z.x !== z0.x || z.y !== z0.y || z.w !== z0.w || z.h !== z0.h) sauver();
					else if (mode === "move") { this.zone_sel = i; this.rendre_scene(); }   // un clic sans glisser = sélectionner
				};
				document.addEventListener("mousemove", bouger); document.addEventListener("mouseup", lacher);
			};
			r.addEventListener("mousedown", glisser("move")); p.addEventListener("mousedown", glisser("resize"));
		});
		this._zones_en_cours = { face, zones, sauver };
	}

	ajouter_zone(type) {
		const c = this._zones_en_cours;
		if (!c) return;
		const f = c.face.utile || c.face;
		// Une photo part grande et centrée (on la réduit ensuite) ; un texte ou un logo, en bandeau.
		const g = type === "photo" ? { x: 0.2, y: 0.25, w: 0.6, h: 0.45 } : { x: 0.3, y: 0.4, w: 0.4, h: 0.15 };
		c.zones.push({ zone: type, x: f.x + f.w * g.x, y: f.y + f.h * g.y, w: f.w * g.w, h: f.h * g.h, libelle: type });
		c.sauver();
	}

	reinitialiser_face(code) {
		this.zone_sel = null;
		delete this.mep[code];
		this.modifier({ mise_en_page: this.mep }, false);
	}

	scene_variantes($s) {
		const d = this.d, esc = this._esc;
		const vs = d.variantes || [];
		if (!vs.length) return $s.html(`<div class="se-vide">${__("Aucune variante : préparez les textes et styles, puis générez.")}</div>`);
		$s.html(`<div class="se-galerie">${vs.map((v) => `
			<div class="se-carte ${v.numero === d.variante_choisie ? "choisie" : ""}">
				${v.image ? `<img src="${esc(v.image)}" alt="">` : `<div class="vide">${esc(v.statut || "")}</div>`}
				<div class="leg"><b>${v.numero}. ${esc(v.titre || "")}</b><br><span class="text-muted">${esc(v.description || "")}</span>
				${v.erreur ? `<br><span class="text-danger">${esc(v.erreur)}</span>` : ""}
				${v.cout_estime ? `<br><span class="text-muted">${v.cout_estime.toFixed(3)} $</span>` : ""}</div>
				<div class="act">
					${v.statut === "Prête" ? `<button class="btn btn-xs btn-primary" data-choisir="${v.numero}">${v.numero === d.variante_choisie ? "✓ " + __("Choisie") : __("Choisir")}</button>` : ""}
					${["Prête", "Échec"].includes(v.statut) ? `<button class="btn btn-xs btn-default" data-regenerer="${v.numero}">${__("Régénérer")}</button>` : ""}
				</div></div>`).join("")}</div>`);
		$s.find("[data-choisir]").on("click", async (e) => {
			await frappe.call({ method: "aquaworld_ia.emballage.job.choisir_variante", args: { design: this.nom, numero: $(e.currentTarget).data("choisir") } });
			await this.recharger();
		});
		$s.find("[data-regenerer]").on("click", (e) => {
			const n = $(e.currentTarget).data("regenerer");
			frappe.confirm(__("Régénérer la variante {0} ? (1 image facturée)", [n]), async () => {
				await frappe.call({ method: "aquaworld_ia.emballage.job.regenerer_variante", args: { design: this.nom, numero: n } });
				this.suivre();
			});
		});
	}

	// ─── colonne de droite ──────────────────────────────────────────────────────
	rendre_droite() {
		const d = this.d, esc = this._esc;
		const fichiers = [
			d.plan_a_plat ? `<li><a href="${esc(d.plan_a_plat)}" target="_blank">${__("PDF imprimeur")}</a></li>` : "",
			d.apercu_plan ? `<li><a href="${esc(d.apercu_plan)}" target="_blank">${__("Aperçu du plan (PNG)")}</a></li>` : "",
			d.apercu_3d ? `<li><a href="${esc(d.apercu_3d)}" target="_blank">${__("Rendu 3D (PNG)")}</a></li>` : "",
		].join("");
		this.$root.find(".se-droite").html(`
			<div class="bloc" data-role="face"><span class="text-muted">${__("Survolez une face du plan.")}</span></div>
			<div class="bloc se-textes"><h6>${__("Textes imprimés")}</h6>${this.data.textes_html || ""}</div>
			<div class="bloc"><h6>${__("Fichiers")}</h6>${fichiers ? `<ul>${fichiers}</ul>` : `<span class="text-muted">${__("Rien encore.")}</span>`}</div>`);
		// Une face épinglée garde son panneau (zones, « Ajouter », « Revenir ») après chaque
		// enregistrement : sans cela, déplacer une zone effaçait le panneau qui sert à continuer.
		const f = this.epinglee && ((this.data.apercu || {}).faces || []).find((x) => x.code === this.epinglee);
		if (f) this.face_info(f);
	}

	face_info(f) {
		const $b = this.$root.find('[data-role="face"]');
		if (!f) return $b.html(`<span class="text-muted">${__("Survolez une face du plan.")}</span>`);
		const epinglee = this.epinglee === f.code;
		const zones = (f.zones || []).map((z, i) => `<li ${epinglee ? `data-zi="${i}" style="cursor:pointer${this.zone_sel === i ? ";font-weight:600;color:#b91c1c" : ""}"` : ""}>${this._esc(z.libelle)} <span class="text-muted">${z.w.toFixed(0)} × ${z.h.toFixed(0)} mm</span>${z.style && z.style.fond ? ` <span class="se-chip" style="background:${this._esc(z.style.fond)};color:${this._esc((z.style.texte) || "#fff")}">${__("cartouche")}</span>` : ""}${z.logo ? ` <span class="se-chip">${__("logo propre")}</span>` : ""}${z.pictos && z.pictos.length ? ` <span class="se-chip">${__("{0} picto(s)", [z.pictos.length])}</span>` : ""}</li>`).join("");
		const sel = epinglee && this.zone_sel != null ? (f.zones || [])[this.zone_sel] : null;
		const TEXTES = ["nom", "accroche", "caracteristiques", "avertissements", "contact"];
		let props = "";
		// Chevauchements sur la face : un logo posé sur la photo, des pictos sur le nom… (retour utilisateur 24/09/2026)
		const zs = f.zones || [], chev = [];
		for (let i = 0; i < zs.length; i++) for (let j = i + 1; j < zs.length; j++) {
			const a = zs[i], b2 = zs[j];
			if (a.x < b2.x + b2.w - 0.5 && b2.x < a.x + a.w - 0.5 && a.y < b2.y + b2.h - 0.5 && b2.y < a.y + a.h - 0.5) chev.push(`${a.libelle} / ${b2.libelle}`);
		}
		if (chev.length) props += `<div class="text-danger small" style="margin-top:6px">⚠ ${__("Zones qui se chevauchent : {0}. Déplacez-les ou réduisez-les.", [this._esc(chev.join(" · "))])}</div>`;
		if (sel) {
			const u = f.utile || f, mm = (v) => (Math.round(v * 10) / 10).toString();
			props += `<div class="bloc" style="margin-top:8px;padding:8px 10px;background:#f8fafc"><h6>${__("Position de « {0} » (mm, depuis le coin haut-gauche de la face)", [this._esc(sel.libelle)])}</h6>
				<div style="display:grid;grid-template-columns:auto 1fr auto 1fr;gap:6px 8px;align-items:center;font-size:12px">
					<span>X</span><input type="number" step="0.5" data-pos="x" value="${mm(sel.x - u.x)}"><span>Y</span><input type="number" step="0.5" data-pos="y" value="${mm(sel.y - u.y)}">
					<span>${__("Larg.")}</span><input type="number" step="0.5" min="3" data-pos="w" value="${mm(sel.w)}"><span>${__("Haut.")}</span><input type="number" step="0.5" min="3" data-pos="h" value="${mm(sel.h)}">
				</div>
				<div class="se-btns" style="margin-top:8px"><button class="btn btn-xs btn-primary" data-role="appliquer-pos">${__("Appliquer")}</button>
					<button class="btn btn-xs btn-default" data-role="centrer-h" title="${__("Centrer horizontalement sur la face")}">↔ ${__("Centrer")}</button>
					<button class="btn btn-xs btn-default" data-role="centrer-v" title="${__("Centrer verticalement sur la face")}">↕ ${__("Centrer")}</button>
					<button class="btn btn-xs btn-default" data-role="pleine-largeur" title="${__("Toute la largeur utile de la face")}">${__("Pleine largeur")}</button></div></div>`;
		}
		if (sel && TEXTES.includes(sel.zone)) {
			const st = sel.style || {};
			props += `<div class="bloc" style="margin-top:8px;padding:8px 10px;background:#f8fafc"><h6>${__("Zone « {0} »", [this._esc(sel.libelle)])}</h6>
				<div style="display:grid;grid-template-columns:auto 1fr auto;gap:6px 8px;align-items:center;font-size:12px">
					<span>${__("Cartouche")}</span><input type="color" data-prop="fond" value="${this._esc(st.fond || "#1d4ed8")}" style="width:44px;height:26px;padding:1px"><label class="se-check" style="margin:0"><input type="checkbox" data-prop="avec_fond" ${st.fond ? "checked" : ""}> ${__("fond")}</label>
					<span>${__("Texte")}</span><input type="color" data-prop="texte" value="${this._esc(st.texte || "#ffffff")}" style="width:44px;height:26px;padding:1px"><label class="se-check" style="margin:0"><input type="checkbox" data-prop="avec_texte" ${st.texte ? "checked" : ""}> ${__("couleur")}</label>
					<span>${__("Coins (mm)")}</span><input type="number" data-prop="rayon" min="0" step="0.5" value="${st.rayon || 0}" style="width:70px"><span></span>
				</div>
				<div class="se-btns" style="margin-top:8px"><button class="btn btn-xs btn-primary" data-role="appliquer-style">${__("Appliquer")}</button><button class="btn btn-xs btn-default" data-role="style-aucun">${__("Sans cartouche")}</button></div>
				<div class="text-muted small" style="margin-top:6px">${__("Exemple : fond bleu, coins 4 mm, texte blanc. Le cartouche épouse la zone : ajustez sa taille sur le plan.")}</div></div>`;
		} else if (sel && sel.zone === "logo") {
			props += `<div class="bloc" style="margin-top:8px;padding:8px 10px;background:#f8fafc"><h6>${__("Logo de cette face")}</h6>
				<div class="se-fichier"><img src="${this._esc(sel.logo || this.d.logo || "")}" alt="">
					<button class="btn btn-xs btn-default" data-role="logo-variante">📚 ${__("Variante de la bibliothèque")}</button>
					${sel.logo ? `<button class="btn btn-xs btn-default" data-role="logo-commun">${__("Logo du design")}</button>` : ""}</div>
				<div class="text-muted small" style="margin-top:6px">${sel.logo ? __("Cette face a son propre logo.") : __("Cette face utilise le logo du design (étape 2).")}</div></div>`;
		} else if (sel && sel.zone === "pictos") {
			const choisis = sel.pictos || [];
			const cases = (this.d.pictogrammes || []).map((p) => {
				const info = (this.data.pictos || []).find((x) => x.code === p.pictogramme) || {};
				return `<label class="se-check" style="margin:2px 0"><input type="checkbox" data-picto-zone="${this._esc(p.pictogramme)}" ${choisis.includes(p.pictogramme) ? "checked" : ""}> ${info.url ? `<img src="${this._esc(info.url)}" style="width:18px;height:18px;object-fit:contain;background:#fff;border-radius:3px">` : ""}${this._esc(info.libelle || p.pictogramme)}</label>`;
			}).join("");
			props += `<div class="bloc" style="margin-top:8px;padding:8px 10px;background:#f8fafc"><h6>${__("Pictogrammes de cette zone")}</h6>
				${cases || `<span class="text-muted small">${__("Cochez d'abord des pictogrammes à l'étape 2.")}</span>`}
				<div class="se-btns" style="margin-top:8px"><button class="btn btn-xs btn-primary" data-role="appliquer-pictos">${__("Appliquer")}</button><button class="btn btn-xs btn-default" data-role="pictos-tous">${__("Tous")}</button></div>
				<div class="text-muted small" style="margin-top:6px">${__("Rien de coché = tous les pictogrammes. Ils se posent côte à côte à la hauteur de la zone : agrandissez-la pour un logo de certification.")}</div></div>`;
		} else if (sel) {
			props += `<div class="text-muted small" style="margin-top:6px">${__("Cette zone n'a pas de réglage : déplacez-la ou redimensionnez-la sur le plan.")}</div>`;
		}
		const types = ["logo", "nom", "accroche", "caracteristiques", "avertissements", "contact", "pictos", "code_barres", "photo"];
		const libs = { logo: __("Logo"), nom: __("Nom du produit"), accroche: __("Accroche"), caracteristiques: __("Caractéristiques"), avertissements: __("Avertissements"), contact: __("Contact"), pictos: __("Pictogrammes"), code_barres: __("Code-barres"), photo: __("Photo produit") };
		const source = f.copie_de && ((this.data.apercu || {}).faces || []).find((x) => x.code === f.copie_de);
		const bloquee = f.copie_bloquee && ((this.data.apercu || {}).faces || []).find((x) => x.code === f.copie_bloquee);
		$b.html(`<h6>${this._esc(f.libelle)} <span class="text-muted">${f.w.toFixed(0)} × ${f.h.toFixed(0)} mm</span>${f.personnalisee ? ` <span class="se-chip encours">${__("personnalisée")}</span>` : ""}${source ? ` <span class="se-chip" title="${__("Modifiez la face source : cette face la suit. Dessinez ici pour la rendre indépendante.")}">${__("copie de {0}", [this._esc(source.libelle)])}</span>` : ""}${bloquee ? ` <span class="se-chip echec" title="${__("Option cochée, mais cette face a sa propre mise en page : « Revenir à la maquette automatique » pour qu'elle recopie.")}">${__("ne copie plus {0}", [this._esc(bloquee.libelle)])}</span>` : ""}</h6>
			${zones ? `<ul>${zones}</ul>` : `<span class="text-muted">${__("Aucun emplacement : renseignez logo, textes, pictogrammes ou code-barres.")}</span>`}
			${props}
			${this.epinglee === f.code ? `
				<div class="small" style="margin-top:8px">${__("Sur le plan : glissez une zone pour la déplacer, tirez son coin pour l'agrandir, × pour la supprimer, cliquez-la pour ses réglages (cartouche, logo).")}</div>
				<div style="display:flex;gap:4px;margin-top:6px;align-items:center"><select class="form-control input-xs" data-role="type-zone" style="height:26px;font-size:12px;flex:1;min-width:0">${types.map((t) => `<option value="${t}">${libs[t]}</option>`).join("")}</select>
					<button class="btn btn-xs btn-default" data-role="ajouter-zone" style="white-space:nowrap">＋ ${__("Ajouter")}</button></div>
				${f.personnalisee ? `<button class="btn btn-xs btn-default" style="margin-top:6px" data-role="reinit-face">${__("Revenir à la maquette automatique")}</button>` : ""}
				<div class="text-muted small" style="margin-top:6px">${__("Cliquez à nouveau la face pour la libérer.")}</div>`
			: `<div class="text-muted small" style="margin-top:6px">${__("Cliquez la face pour modifier ses zones.")}</div>`}`);
		$b.find('[data-role="ajouter-zone"]').on("click", () => this.ajouter_zone($b.find('[data-role="type-zone"]').val()));
		$b.find("[data-zi]").on("click", (e) => { this.zone_sel = +$(e.currentTarget).attr("data-zi"); this.rendre_scene(); });
		const zone_courante = () => (this._zones_en_cours || {}).zones && this._zones_en_cours.zones[this.zone_sel];
		$b.find('[data-role="appliquer-style"]').on("click", () => {
			const z = zone_courante(); if (!z) return;
			const st = {};
			if ($b.find('[data-prop="avec_fond"]').is(":checked")) st.fond = $b.find('[data-prop="fond"]').val();
			if ($b.find('[data-prop="avec_texte"]').is(":checked")) st.texte = $b.find('[data-prop="texte"]').val();
			const rayon = parseFloat($b.find('[data-prop="rayon"]').val()) || 0;
			if (rayon) st.rayon = rayon;
			z.style = (st.fond || st.texte) ? st : null;
			this._zones_en_cours.sauver();
		});
		$b.find('[data-role="style-aucun"]').on("click", () => { const z = zone_courante(); if (!z) return; z.style = null; this._zones_en_cours.sauver(); });
		const utile = () => { const c = this._zones_en_cours || {}; return c.face ? (c.face.utile || c.face) : null; };
		$b.find('[data-role="appliquer-pos"]').on("click", () => {
			const z = zone_courante(), u = utile(); if (!z || !u) return;
			const v = (k) => parseFloat($b.find(`[data-pos="${k}"]`).val());
			if (!isNaN(v("w"))) z.w = Math.max(3, v("w")); if (!isNaN(v("h"))) z.h = Math.max(3, v("h"));
			if (!isNaN(v("x"))) z.x = u.x + v("x"); if (!isNaN(v("y"))) z.y = u.y + v("y");
			this._zones_en_cours.sauver();   // le serveur borne à la face
		});
		$b.find('[data-role="centrer-h"]').on("click", () => { const z = zone_courante(), u = utile(); if (!z || !u) return; z.x = u.x + (u.w - z.w) / 2; this._zones_en_cours.sauver(); });
		$b.find('[data-role="centrer-v"]').on("click", () => { const z = zone_courante(), u = utile(); if (!z || !u) return; z.y = u.y + (u.h - z.h) / 2; this._zones_en_cours.sauver(); });
		$b.find('[data-role="pleine-largeur"]').on("click", () => { const z = zone_courante(), u = utile(); if (!z || !u) return; z.x = u.x + 3; z.w = Math.max(3, u.w - 6); this._zones_en_cours.sauver(); });
		$b.find('[data-role="appliquer-pictos"]').on("click", () => { const z = zone_courante(); if (!z) return; z.pictos = $b.find("[data-picto-zone]:checked").map((_i, el) => $(el).attr("data-picto-zone")).get(); this._zones_en_cours.sauver(); });
		$b.find('[data-role="pictos-tous"]').on("click", () => { const z = zone_courante(); if (!z) return; z.pictos = null; this._zones_en_cours.sauver(); });
		$b.find('[data-role="logo-variante"]').on("click", () => this.bibliotheque("logo", (l) => { const z = zone_courante(); if (!z) return; z.logo = l.image; this._zones_en_cours.sauver(); }));
		$b.find('[data-role="logo-commun"]').on("click", () => { const z = zone_courante(); if (!z) return; z.logo = null; this._zones_en_cours.sauver(); });
		$b.find('[data-role="reinit-face"]').on("click", () => this.reinitialiser_face(f.code));
	}

	// ─── actions ────────────────────────────────────────────────────────────────
	async action(nom) {
		try {
			if (nom === "preparer") {
				await frappe.call({ method: "aquaworld_ia.emballage.textes.preparer", args: { design: this.nom }, freeze: true,
					freeze_message: __("L'IA rédige les textes et propose des styles…") });
				frappe.show_alert({ message: __("Textes et styles prêts."), indicator: "green" });
				await this.recharger(); this.etape = 3; this.onglet = "variantes"; this.rendre();
			} else if (nom === "textes") {
				this.dialogue_textes();
			} else if (nom === "generer") {
				const a_faire = (this.d.variantes || []).filter((v) => ["À générer", "Échec"].includes(v.statut)).map((v) => v.numero);
				const e = (await frappe.call({ method: "aquaworld_ia.emballage.job.estimation_variantes", args: { nombre: a_faire.length } })).message || {};
				frappe.confirm(__("Générer {0} variante(s), qualité {1}, coût estimé <b>{2} $</b> (dépensé ce mois : {3} $) ?", [a_faire.length, e.qualite, (e.cout || 0).toFixed(2), (e.mois || 0).toFixed(2)]), async () => {
					await frappe.call({ method: "aquaworld_ia.emballage.job.lancer_variantes", args: { design: this.nom, numeros: a_faire } });
					this.onglet = "variantes"; this.rendre_scene(); this.suivre();
				});
			} else if (nom === "logo_ia") {
				this.atelier_image("logo");
			} else if (nom === "photo_ia") {
				this.atelier_image("photo_produit");
			} else if (nom === "fond") {
				const continu = this.$root.find('[data-champ="fond_continu"]').is(":checked") ? 1 : 0;
				frappe.confirm(__("Générer un fond d'ambiance par IA (sans produit) à partir du brief et des couleurs du logo, {0} ? (1 image facturée, puis recomposition du plan)", [continu ? __("en panorama continu autour de l'emballage") : __("pour chaque face séparément")]), async () => {
					await frappe.call({ method: "aquaworld_ia.emballage.job.lancer_fond", args: { design: this.nom, continu } });
					this.onglet = "artwork"; this.rendre_scene(); this.suivre();
				});
			} else if (nom === "composer") {
				const r = await frappe.call({ method: "aquaworld_ia.emballage.composition.composer_et_attacher",
					args: { design: this.nom, variante: this.d.variante_choisie }, freeze: true, freeze_message: __("Composition du plan à l'échelle…") });
				frappe.show_alert({ message: __("Plan à plat prêt : feuille {0} × {1} mm.", [r.message.feuille.w, r.message.feuille.h]), indicator: "green" });
				await this.recharger(); this.etape = 4; this.onglet = "artwork"; this.rendre();
			} else if (nom === "faces") {
				frappe.confirm(__("Générer les 5 autres faces dans le style de la variante choisie, puis recomposer le plan ? (5 images facturées)"), async () => {
					await frappe.call({ method: "aquaworld_ia.emballage.job.lancer_faces", args: { design: this.nom } });
					this.suivre();
				});
			} else if (nom === "mockup") {
				await frappe.call({ method: "aquaworld_ia.emballage.job.lancer_mockup", args: { design: this.nom } });
				this.onglet = "3d"; this.rendre_scene(); this.suivre();
			}
		} catch (e) {
			frappe.msgprint(this._msg(e));
		}
	}

	dialogue_textes() {
		let textes = {};
		try { textes = JSON.parse(this.d.textes_ia || "{}"); } catch (e) { textes = {}; }
		const codes = Object.keys(textes), fields = [];
		codes.forEach((c) => {
			const t = textes[c] || {};
			fields.push({ fieldtype: "Section Break", label: c.toUpperCase() });
			fields.push({ fieldtype: "Data", fieldname: `acc_${c}`, label: __("Accroche"), default: t.accroche });
			fields.push({ fieldtype: "Small Text", fieldname: `car_${c}`, label: __("Caractéristiques (une par ligne)"), default: (t.caracteristiques || []).join("\n") });
			fields.push({ fieldtype: "Small Text", fieldname: `ave_${c}`, label: __("Avertissements (un par ligne)"), default: (t.avertissements || []).join("\n") });
			fields.push({ fieldtype: "Small Text", fieldname: `con_${c}`, label: __("Contact"), default: t.contact });
		});
		const dlg = new frappe.ui.Dialog({ title: __("Textes imprimés"), size: "large", fields, primary_action_label: __("Enregistrer"),
			primary_action: async (v) => {
				const out = {};
				codes.forEach((c) => { out[c] = { accroche: v[`acc_${c}`] || "", caracteristiques: (v[`car_${c}`] || "").split("\n").filter(Boolean),
					avertissements: (v[`ave_${c}`] || "").split("\n").filter(Boolean), contact: v[`con_${c}`] || "" }; });
				await frappe.call({ method: "aquaworld_ia.emballage.textes.enregistrer_textes", args: { design: this.nom, textes: out } });
				dlg.hide(); await this.recharger();
			} });
		dlg.show();
	}

	atelier_image(champ) {
		const est = this.data.estimation || {}, est_logo = champ === "logo";
		const exemples = est_logo
			? __("ex. « passer le bleu en bleu marine et le texte en blanc », « version épurée à plat », « fond blanc, sans dégradé ». Les formes et les lettres sont conservées, mais relisez-les : l'IA redessine.")
			: __("ex. « détourer sur fond blanc pur, éclairage studio doux », « retirer la clé et le support, garder seulement le porte-filtre », « vue de face, bien net ». Le produit est conservé, mais contrôlez chaque détail : l'IA redessine.");
		const dlg = new frappe.ui.Dialog({ title: est_logo ? __("Retoucher le logo par IA") : __("Améliorer la photo du produit par IA"),
			fields: [
				{ fieldtype: "HTML", options: `<img src="${this._esc(this.d[champ] || "")}" style="max-height:120px;max-width:100%;background:#fff;border:1px solid #e5e7eb;border-radius:6px;padding:6px">` },
				{ fieldtype: "Small Text", fieldname: "instruction", label: __("Que changer ?"), reqd: 1, description: exemples,
				  default: est_logo ? "" : __("Détourer sur fond blanc pur, éclairage studio doux, vue de face, net") },
				{ fieldtype: "Select", fieldname: "nombre", label: __("Propositions"), default: "3", options: ["1", "2", "3", "4"].join("\n"),
				  description: __("Plusieurs propositions pour la même consigne : vous choisissez la meilleure. Une image facturée par proposition (qualité {0}, ≈ {1} $ chacune).", [est.qualite || "", (est.cout || 0).toFixed(2)]) },
				{ fieldtype: "HTML", options: `<p class="text-muted small">${__("Rien ne remplace le logo tant que vous n'en adoptez pas un.")}</p>` },
			],
			primary_action_label: __("Générer"),
			primary_action: async (v) => {
				let r;
				try {
					r = await frappe.call({ method: "aquaworld_ia.emballage.studio.retoucher_image", args: { design: this.nom, champ, instruction: v.instruction, nombre: v.nombre }, freeze: true, freeze_message: est_logo ? __("L'IA redessine le logo…") : __("L'IA retravaille la photo…") });
				} catch (e) { frappe.msgprint(this._msg(e)); return; }
				dlg.hide();
				const c = r.message, candidats = c.candidats || [c.candidat];
				const carte = (src, titre, url) => `<div style="flex:1 1 200px;text-align:center;min-width:0"><div class="text-muted small">${titre}</div>
					<img src="${this._esc(src)}" style="max-width:100%;max-height:220px;background:#fff;border:1px solid #e5e7eb;border-radius:6px">
					${url ? `<div style="margin-top:6px"><button class="btn btn-xs btn-primary" data-adopter="${this._esc(url)}">${__("Utiliser celui-ci")}</button></div>` : ""}</div>`;
				const cmp = new frappe.ui.Dialog({ title: est_logo ? __("Propositions de logo") : __("Propositions de photo"), size: "large",
					fields: [{ fieldtype: "HTML", fieldname: "galerie", options: `<div style="display:flex;gap:14px;align-items:flex-start;flex-wrap:wrap">
						${carte(c.source, __("Actuel"), null)}${candidats.map((u, i) => carte(u, __("Proposition {0}", [i + 1]), u)).join("")}</div>
						<p class="small text-muted" style="margin-top:8px">${est_logo ? __("Vérifiez chaque lettre. En adoptant, le fond blanc devient transparent.") : __("Comparez chaque détail du produit avec l'original. En adoptant, le fond blanc devient transparent.")}</p>` }],
					secondary_action_label: __("Réessayer"), secondary_action: () => { cmp.hide(); this.atelier_image(champ); } });
				cmp.show();
				cmp.get_field("galerie").$wrapper.find("[data-adopter]").on("click", async (e) => {
					const r2 = await frappe.call({ method: "aquaworld_ia.emballage.studio.adopter_image", args: { design: this.nom, champ, url: $(e.currentTarget).attr("data-adopter") }, freeze: true });
					cmp.hide(); this.data = r2.message; this.d = this.data.doc; this._lire_mep(); this.rendre();
				});
			} });
		dlg.show();
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
					await this.modifier({ pictogrammes: codes }, true);
				} catch (e) { frappe.msgprint(this._msg(e)); }
			} });
		dlg.show();
	}

	// ─── bibliothèque : fonds, motifs, variantes de logo ────────────────────────
	garder(champ) {
		const est_logo = champ === "logo";
		const dlg = new frappe.ui.Dialog({ title: est_logo ? __("Garder ce logo en bibliothèque") : __("Garder ce fond en bibliothèque"),
			fields: [
				{ fieldtype: "HTML", options: `<img src="${this._esc(this.d[champ])}" style="max-height:120px;max-width:100%;background:#fff;border:1px solid #e5e7eb;border-radius:6px;padding:6px">` },
				{ fieldtype: "Data", fieldname: "nom", label: __("Nom"), reqd: 1, default: est_logo ? (this.d.marque || "") + " " : (this.d.brief_style || "").slice(0, 40) },
				{ fieldtype: "Select", fieldname: "categorie", label: __("Catégorie"), default: est_logo ? "Logo" : "Fond", options: (est_logo ? ["Logo"] : ["Fond", "Motif"]).join("\n") },
				{ fieldtype: "Small Text", fieldname: "notes", label: __("Notes"), default: est_logo ? "" : [this.d.brief_style, this.d.palette].filter(Boolean).join(" · ") },
				{ fieldtype: "HTML", options: `<p class="text-muted small">${__("Marque : {0}. La ressource garde son propre fichier : le design d'origine peut disparaître, elle reste.", [this._esc(this.d.marque || "—")])}</p>` },
			],
			primary_action_label: __("Garder"),
			primary_action: async (v) => {
				try {
					const r = await frappe.call({ method: "aquaworld_ia.emballage.studio.bibliotheque_enregistrer", args: { design: this.nom, champ, nom: v.nom, categorie: v.categorie, notes: v.notes } });
					dlg.hide(); frappe.show_alert({ message: __("Gardé en bibliothèque : {0}", [r.message.nom]), indicator: "green" });
				} catch (e) { frappe.msgprint(this._msg(e)); }
			} });
		dlg.show();
	}

	bibliotheque(champ, on_choisir) {
		const est_logo = champ === "logo";
		const dlg = new frappe.ui.Dialog({ title: est_logo ? __("Variantes de logo") : __("Fonds et motifs"), size: "large",
			fields: [
				{ fieldtype: "Data", fieldname: "recherche", label: __("Rechercher") },
				{ fieldtype: "HTML", fieldname: "grille" },
			] });
		const $grille = dlg.get_field("grille").$wrapper;
		const charger = async () => {
			const r = await frappe.call({ method: "aquaworld_ia.emballage.studio.bibliotheque_liste", args: { champ, marque: this.d.marque, recherche: dlg.get_value("recherche") } });
			const lignes = r.message || [];
			if (!lignes.length) { $grille.html(`<div class="se-vide">${__("Rien en bibliothèque pour l'instant : gardez un fond ou un logo avec le bouton « Garder ».")}</div>`); return; }
			$grille.html(`<div class="se-galerie">${lignes.map((l) => `
				<div class="se-carte" data-res="${this._esc(l.name)}" style="cursor:pointer">
					<img src="${this._esc(l.image)}" alt="" style="aspect-ratio:${est_logo ? "3 / 2" : "4 / 3"};object-fit:contain;background:#fff">
					<div class="leg"><b>${this._esc(l.nom)}</b> <span class="se-chip">${this._esc(l.categorie)}</span>${l.marque ? `<br><span class="text-muted">${this._esc(l.marque)}</span>` : ""}${l.notes ? `<br><span class="text-muted small">${this._esc(l.notes)}</span>` : ""}</div>
				</div>`).join("")}</div>`);
			$grille.find("[data-res]").on("click", async (e) => {
				if (on_choisir) { const l = lignes.find((x) => x.name === $(e.currentTarget).attr("data-res")); dlg.hide(); if (l) on_choisir(l); return; }
				try {
					const r2 = await frappe.call({ method: "aquaworld_ia.emballage.studio.bibliotheque_choisir", args: { design: this.nom, ressource: $(e.currentTarget).attr("data-res"), champ }, freeze: true });
					dlg.hide(); this.data = r2.message; this.d = this.data.doc; this._lire_mep(); this.rendre();
					frappe.show_alert({ message: est_logo ? __("Logo remplacé.") : __("Fond remplacé : recomposez le plan."), indicator: "green" });
				} catch (e2) { frappe.msgprint(this._msg(e2)); }
			});
		};
		dlg.get_field("recherche").$input.on("input", frappe.utils.debounce(charger, 350));
		dlg.show(); charger();
	}

	async nouveau() {
		const dlg = new frappe.ui.Dialog({ title: __("Nouveau design d'emballage"),
			fields: [{ fieldtype: "Link", options: "Item", fieldname: "article", label: __("Article"), reqd: 1 }],
			primary_action_label: __("Créer"),
			primary_action: async (v) => {
				const r = await frappe.call({ method: "aquaworld_ia.emballage.studio.nouveau", args: { article: v.article } });
				dlg.hide(); frappe.set_route("studio-emballage", r.message.name);
			} });
		dlg.show();
	}

	// ─── suivi des jobs ─────────────────────────────────────────────────────────
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
		this._rt = null; this._minuteur = null;
		this.$root.find('[data-role="progress"], [data-role="progress-txt"]').hide();
	}

	_esc(v) { return frappe.utils.escape_html(String(v == null ? "" : v)); }
	static get CHAMPS_DIMS() { return { L: "longueur_mm", H: "hauteur_mm", P: "profondeur_mm", R: "repli_mm" }; }
	_msg(e) {
		const m = (e && (e.message || (e._server_messages && JSON.parse(e._server_messages)[0]))) || e;
		try { return typeof m === "string" ? (JSON.parse(m).message || m) : JSON.stringify(m); } catch (_x) { return String(m); }
	}
}
