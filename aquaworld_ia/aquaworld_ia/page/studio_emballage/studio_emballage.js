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

	_etape_par_defaut() {
		const d = this.d;
		if (!(d.longueur_mm > 0 && d.hauteur_mm > 0 && d.profondeur_mm > 0)) return 1;
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
					<div class="se-3">
						<div><label>${esc(dims[0])}</label><input type="number" step="0.5" min="1" data-champ="longueur_mm" value="${d.longueur_mm || ""}"></div>
						<div><label>${esc(dims[1])}</label><input type="number" step="0.5" min="1" data-champ="hauteur_mm" value="${d.hauteur_mm || ""}"></div>
						<div><label>${esc(dims[2])}</label><input type="number" step="0.5" min="1" data-champ="profondeur_mm" value="${d.profondeur_mm || ""}"></div>
					</div>
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
					<div class="se-btns" style="margin-top:6px"><button class="btn btn-sm btn-default" data-action="fond" ${d.longueur_mm > 0 ? "" : "disabled"}>${__("Fond IA · 1 image · ≈ {0} $", [(est.cout || 0).toFixed(2)])}</button></div>
					<label class="se-check"><input type="checkbox" data-champ="fond_continu" ${d.fond_continu ? "checked" : ""}> ${__("Fond continu sur toutes les faces (panorama découpé aux plis)")}</label>
					<label class="se-check"><input type="checkbox" data-champ="faces_identiques" ${d.faces_identiques ? "checked" : ""}> ${__("Face arrière identique à la face avant")}</label>
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
			1: d.longueur_mm > 0 && d.hauteur_mm > 0 && d.profondeur_mm > 0,
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
		if (!a) return $s.html(`<div class="se-vide">${__("Saisissez les trois dimensions pour voir le plan.")}</div>`);
		if (a.erreur) return $s.html(`<div class="se-vide text-danger">${this._esc(a.erreur)}</div>`);
		const pb = (a.problemes || []).length ? `<p class="text-danger small">⛔ ${a.problemes.map(this._esc).join(" · ")}</p>` : "";
		$s.html(`<p class="text-muted small">${__("Feuille <b>{0} × {1} mm</b>, fond perdu inclus. Survolez une face, cliquez pour l'épingler.", [a.feuille.w, a.feuille.h])}</p>${pb}${a.svg}`);
		const infos = {};
		(a.faces || []).forEach((f) => { infos[f.code] = f; });
		const montrer = (code) => {
			$s.find(".aqia-zones").hide();
			$s.find(`.aqia-zones[data-face="${code}"]`).show();
			this.face_info(infos[code]);
		};
		$s.find("rect.aqia-face.imprimable")
			.on("mouseenter", (e) => { if (!this.epinglee) montrer($(e.currentTarget).attr("data-face")); })
			.on("mouseleave", () => { if (!this.epinglee) { $s.find(".aqia-zones").hide(); this.face_info(null); } })
			.on("click", (e) => {
				const code = $(e.currentTarget).attr("data-face");
				$s.find("rect.aqia-face").removeClass("epinglee");
				if (this.epinglee === code) { this.epinglee = null; $s.find(".aqia-zones").hide(); this.face_info(null); return; }
				this.epinglee = code; $(e.currentTarget).addClass("epinglee"); montrer(code);
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
		const zones = (face.zones || []).map((z) => ({ zone: z.zone, x: z.x, y: z.y, w: z.w, h: z.h, libelle: z.libelle }));
		const el = (tag, attrs) => { const n = document.createElementNS(NS, tag); Object.entries(attrs).forEach(([k, v]) => n.setAttribute(k, v)); g.appendChild(n); return n; };
		const point = (e) => { const pt = svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY; return pt.matrixTransform(svg.getScreenCTM().inverse()); };
		const sauver = () => { this.mep[face.code] = zones.map((z) => ({ zone: z.zone, x: z.x, y: z.y, w: z.w, h: z.h })); this.modifier({ mise_en_page: this.mep }, false); };
		zones.forEach((z, i) => {
			const r = el("rect", { x: z.x, y: z.y, width: z.w, height: z.h, fill: "#f59e0b", "fill-opacity": "0.18", stroke: "#d97706", "stroke-width": W / 700, style: "cursor:move" });
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
					if (mode === "move") { z.x = Math.min(Math.max(z0.x + dx, face.x), face.x + face.w - z.w); z.y = Math.min(Math.max(z0.y + dy, face.y), face.y + face.h - z.h); }
					else { z.w = Math.max(3, Math.min(z0.w + dx, face.x + face.w - z.x)); z.h = Math.max(3, Math.min(z0.h + dy, face.y + face.h - z.y)); }
					r.setAttribute("x", z.x); r.setAttribute("y", z.y); r.setAttribute("width", z.w); r.setAttribute("height", z.h);
					p.setAttribute("x", z.x + z.w - POIGNEE); p.setAttribute("y", z.y + z.h - POIGNEE);
					t.setAttribute("x", z.x + W / 400); t.setAttribute("y", z.y + Math.max(2, Math.min(z.w, z.h) / 4));
					x.setAttribute("x", z.x + z.w - POIGNEE * 0.9); x.setAttribute("y", z.y + POIGNEE * 1.1);
				};
				const lacher = () => { document.removeEventListener("mousemove", bouger); document.removeEventListener("mouseup", lacher); if (z.x !== z0.x || z.y !== z0.y || z.w !== z0.w || z.h !== z0.h) sauver(); };
				document.addEventListener("mousemove", bouger); document.addEventListener("mouseup", lacher);
			};
			r.addEventListener("mousedown", glisser("move")); p.addEventListener("mousedown", glisser("resize"));
		});
		this._zones_en_cours = { face, zones, sauver };
	}

	ajouter_zone(type) {
		const c = this._zones_en_cours;
		if (!c) return;
		const f = c.face;
		c.zones.push({ zone: type, x: f.x + f.w * 0.3, y: f.y + f.h * 0.4, w: f.w * 0.4, h: f.h * 0.15, libelle: type });
		c.sauver();
	}

	reinitialiser_face(code) {
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
	}

	face_info(f) {
		const $b = this.$root.find('[data-role="face"]');
		if (!f) return $b.html(`<span class="text-muted">${__("Survolez une face du plan.")}</span>`);
		const zones = (f.zones || []).map((z) => `<li>${this._esc(z.libelle)} <span class="text-muted">${z.w.toFixed(0)} × ${z.h.toFixed(0)} mm</span></li>`).join("");
		const types = ["logo", "nom", "accroche", "caracteristiques", "avertissements", "contact", "pictos", "code_barres", "photo"];
		const libs = { logo: __("Logo"), nom: __("Nom du produit"), accroche: __("Accroche"), caracteristiques: __("Caractéristiques"), avertissements: __("Avertissements"), contact: __("Contact"), pictos: __("Pictogrammes"), code_barres: __("Code-barres"), photo: __("Photo produit") };
		$b.html(`<h6>${this._esc(f.libelle)} <span class="text-muted">${f.w.toFixed(0)} × ${f.h.toFixed(0)} mm</span>${f.personnalisee ? ` <span class="se-chip encours">${__("personnalisée")}</span>` : ""}</h6>
			${zones ? `<ul>${zones}</ul>` : `<span class="text-muted">${__("Aucun emplacement : renseignez logo, textes, pictogrammes ou code-barres.")}</span>`}
			${this.epinglee === f.code ? `
				<div class="small" style="margin-top:8px">${__("Sur le plan : glissez une zone pour la déplacer, tirez son coin pour l'agrandir, × pour la supprimer.")}</div>
				<div style="display:flex;gap:4px;margin-top:6px"><select class="form-control input-xs" data-role="type-zone" style="height:26px;font-size:12px">${types.map((t) => `<option value="${t}">${libs[t]}</option>`).join("")}</select>
					<button class="btn btn-xs btn-default" data-role="ajouter-zone">＋ ${__("Ajouter")}</button></div>
				${f.personnalisee ? `<button class="btn btn-xs btn-default" style="margin-top:6px" data-role="reinit-face">${__("Revenir à la maquette automatique")}</button>` : ""}
				<div class="text-muted small" style="margin-top:6px">${__("Cliquez à nouveau la face pour la libérer.")}</div>`
			: `<div class="text-muted small" style="margin-top:6px">${__("Cliquez la face pour modifier ses zones.")}</div>`}`);
		$b.find('[data-role="ajouter-zone"]').on("click", () => this.ajouter_zone($b.find('[data-role="type-zone"]').val()));
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
				this.atelier_logo();
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

	atelier_logo() {
		const est = this.data.estimation || {};
		const dlg = new frappe.ui.Dialog({ title: __("Retoucher le logo par IA"),
			fields: [
				{ fieldtype: "HTML", options: `<img src="${this._esc(this.d.logo || "")}" style="max-height:90px;max-width:100%;background:#fff;border:1px solid #e5e7eb;border-radius:6px;padding:6px">` },
				{ fieldtype: "Small Text", fieldname: "instruction", label: __("Que changer ?"), reqd: 1,
				  description: __("ex. « passer le bleu en bleu marine et le texte en blanc », « version épurée à plat », « fond blanc, sans dégradé ». Les formes et les lettres sont conservées, mais relisez-les : l'IA redessine.") },
				{ fieldtype: "HTML", options: `<p class="text-muted small">${__("1 image, qualité {0}, ≈ {1} $. Le résultat ne remplace pas le logo tant que vous ne l'adoptez pas.", [est.qualite || "", (est.cout || 0).toFixed(2)])}</p>` },
			],
			primary_action_label: __("Générer"),
			primary_action: async (v) => {
				let r;
				try {
					r = await frappe.call({ method: "aquaworld_ia.emballage.studio.retoucher_logo", args: { design: this.nom, instruction: v.instruction }, freeze: true, freeze_message: __("L'IA redessine le logo…") });
				} catch (e) { frappe.msgprint(this._msg(e)); return; }
				dlg.hide();
				const c = r.message;
				const cmp = new frappe.ui.Dialog({ title: __("Avant / après"), size: "large",
					fields: [{ fieldtype: "HTML", options: `<div style="display:flex;gap:16px;align-items:flex-start">
						<div style="flex:1;text-align:center"><div class="text-muted small">${__("Actuel")}</div><img src="${this._esc(c.source)}" style="max-width:100%;max-height:260px;background:#fff;border:1px solid #e5e7eb"></div>
						<div style="flex:1;text-align:center"><div class="text-muted small">${__("Proposition IA")}</div><img src="${this._esc(c.candidat)}" style="max-width:100%;max-height:260px;background:#fff;border:1px solid #e5e7eb"></div></div>
						<p class="small text-muted" style="margin-top:8px">${__("Vérifiez chaque lettre. En adoptant, le fond blanc devient transparent.")}</p>` }],
					primary_action_label: __("Utiliser ce logo"),
					primary_action: async () => {
						const r2 = await frappe.call({ method: "aquaworld_ia.emballage.studio.adopter_logo", args: { design: this.nom, url: c.candidat }, freeze: true });
						cmp.hide(); this.data = r2.message; this.d = this.data.doc; this._lire_mep(); this.rendre();
					},
					secondary_action_label: __("Réessayer"), secondary_action: () => { cmp.hide(); this.atelier_logo(); } });
				cmp.show();
			} });
		dlg.show();
	}

	ajouter_picto() {
		const dlg = new frappe.ui.Dialog({ title: __("Nouveau pictogramme ou certification"),
			fields: [
				{ fieldtype: "Data", fieldname: "libelle", label: __("Nom"), reqd: 1 },
				{ fieldtype: "Select", fieldname: "categorie", label: __("Catégorie"), default: "Certification",
				  options: ["Certification", "Réglementaire", "Manutention", "Recyclage", "Sécurité", "Autre"].join("\n") },
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
	_msg(e) {
		const m = (e && (e.message || (e._server_messages && JSON.parse(e._server_messages)[0]))) || e;
		try { return typeof m === "string" ? (JSON.parse(m).message || m) : JSON.stringify(m); } catch (_x) { return String(m); }
	}
}
