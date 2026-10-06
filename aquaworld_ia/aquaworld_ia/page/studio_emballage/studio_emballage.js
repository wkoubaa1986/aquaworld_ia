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

	// Les enregistrements partent l'un après l'autre : deux enregistrements simultanés de la même fiche
	// (police du bloc puis sa taille, frappe dans l'éditeur…) faisaient échouer le second
	// (« document modifié entre-temps »).
	enregistrer(valeurs) {
		const tache = (this._file_enreg || Promise.resolve()).catch(() => {}).then(() => this._enregistrer(valeurs));
		this._file_enreg = tache;
		return tache;
	}

	async _enregistrer(valeurs) {
		const r = await frappe.call({ method: "aquaworld_ia.emballage.studio.enregistrer",
			args: { design: this.nom, valeurs }, freeze: false });
		this.data = r.message; this.d = this.data.doc; this._lire_mep();
		this.rendre_scene(); this.rendre_droite(); this.rendre_barre(); this.rendre_etats_etapes(); this.rendre_avert_lignes();
	}
	// (la scène Images lit this.data.images, rechargé par enregistrer())

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
			<button class="btn btn-xs btn-default" data-role="dupliquer" title="${__("Une copie de ce design, pour un autre article ou une autre piste")}">⧉ ${__("Dupliquer")}</button>
			<span class="se-cout">${__("Coût IA de ce design : {0} $", [((this.data.etat || {}).cout_document || 0).toFixed(3)])}</span>`);
		const $sel = this.$barre.find('[data-role="selecteur"]');
		$sel.on("focus", async () => {
			if ($sel.data("charge")) return;
			const r = await frappe.call({ method: "aquaworld_ia.emballage.studio.liste", args: { limite: 30 } });
			$sel.html((r.message || []).map((l) => `<option value="${this._esc(l.name)}" ${l.name === d.name ? "selected" : ""}>${this._esc(l.nom_produit || l.name)} · ${this._esc(l.name)} · ${this._esc(l.statut || "")}</option>`).join(""));
			$sel.data("charge", 1);
		});
		$sel.on("change", () => frappe.set_route("studio-emballage", $sel.val()));
		this.$barre.find('[data-role="dupliquer"]').on("click", () => aqia_dupliquer_design(d, (nom) => frappe.set_route("studio-emballage", nom)));
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
			+ `<span class="c ajout" data-ajouter-picto="1" title="${__("Ajouter un pictogramme ou une certification depuis une image")}">＋ ${__("Ajouter")}</span>`
			+ `<span class="c ajout" data-tampon-ia="1" title="${__("Un tampon / badge vectoriel (SVG) dessiné par l'IA : poids, garantie, « 100 % naturel »…")}">✨ ${__("Tampon IA")}</span>`;
		const fichier = (champ, libelle) => `
			<label>${libelle}</label>
			<div class="se-fichier">
				${d[champ] ? `<img src="${esc(d[champ])}" alt="" data-voir="${champ}" style="cursor:zoom-in" title="${__("Ouvrir en grand — prendre une couleur à la pipette")}">` : `<span class="text-muted small">${__("aucun fichier")}</span>`}
				<button class="btn btn-xs btn-default" data-televerser="${champ}">${d[champ] ? __("Remplacer") : __("Choisir un fichier")}</button>
				${d[champ] ? `<button class="btn btn-xs btn-default" data-effacer="${champ}">✕</button>` : ""}
				${champ === "logo" && (d.logo || d.marque) ? `<button class="btn btn-xs btn-default" data-action="logo_ia" title="${__("Changer les couleurs, épurer, moderniser — par IA, avant de le poser")}">✨ ${__("Retoucher par IA")}</button>` : ""}
				${champ === "logo" && (d.logo || d.marque) ? `<button class="btn btn-xs btn-default" data-action="logo_couleur" title="${__("Le logo en UNE couleur choisie dans une palette, exacte et sans IA, en SVG ou PNG")}">🎨 ${__("Couleur & SVG")}</button>` : ""}
				${champ === "photo_produit" && d.photo_produit ? `<button class="btn btn-xs btn-default" data-action="photo_ia" title="${__("Détourer sur blanc pur, éclairage studio, retirer les accessoires — par IA, plusieurs propositions")}">✨ ${__("Améliorer par IA")}</button>` : ""}
				${StudioEmballage.BIBLIO[champ] ? `<button class="btn btn-xs btn-default" data-bibliotheque="${champ}" title="${__("Reprendre un fond, un motif, une variante de logo ou une photo gardés en bibliothèque")}">📚 ${__("Bibliothèque")}</button>` : ""}
				${StudioEmballage.BIBLIO[champ] && d[champ] ? `<button class="btn btn-xs btn-default" data-garder="${champ}" title="${__("Garder ce fichier en bibliothèque, sous un nom, pour un autre design")}">💾 ${__("Garder")}</button>` : ""}
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
					<label>${__("Caractéristiques (une par ligne)")}</label><div data-role="editeur-car"></div><div data-role="avert-lignes"></div>
					<label>${__("Avertissements (un par ligne)")}</label><textarea data-champ="avertissements">${esc(d.avertissements || "")}</textarea>
					<label>${__("Contact")}</label><textarea data-champ="contact">${esc(d.contact || "")}</textarea>
					<label>${__("Pictogrammes et certifications")}</label><div class="se-chips" data-liste="pictogrammes">${pictos}</div>
					<label class="se-check"><input type="checkbox" data-champ="pictos_sans_cartouche" ${d.pictos_sans_cartouche ? "checked" : ""} title="${__("Posés en transparence ; les pictogrammes monochromes prennent la couleur du texte de la face. Code-barres et QR gardent leur cartouche pour le scan.")}"> ${__("Sans cartouche blanc (en transparence)")}</label>
					<div class="se-3" style="grid-template-columns:1fr 1.4fr">
						<div><label>${__("Code")}</label><select data-champ="type_code_barres">${["EAN-13", "QR", "EAN-13 + QR", "Aucun"].map((o) => `<option ${o === d.type_code_barres ? "selected" : ""}>${o}</option>`).join("")}</select></div>
						<div><label>${__("EAN-13")}</label><input type="text" data-champ="code_barres" value="${esc(d.code_barres || "")}"></div>
					</div>
					<label>${__("URL du QR")}</label><input type="text" data-champ="url_qr" value="${esc(d.url_qr || "")}" placeholder="https://…">
					<label>${__("Couleur du QR")}</label>
					<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap"><input type="color" data-champ="couleur_qr" value="${esc(d.couleur_qr || "#000000")}" style="width:44px;height:26px;padding:1px">
						${this._palette().map((c) => { const ok = this._contraste_blanc(c) >= 3; return `<span class="se-pastille petite" style="background:${esc(c)};${ok ? "" : "opacity:.35;cursor:not-allowed"}" title="${esc(c)}${ok ? "" : " — " + __("trop clair pour un QR")}" ${ok ? `data-qr-couleur="${esc(c)}"` : ""}></span>`; }).join("")}
						${d.couleur_qr && d.couleur_qr !== "#000000" ? `<button class="btn btn-xs btn-default" data-qr-couleur="">${__("Noir")}</button>` : ""}</div>
					<div class="text-muted small">${__("Une teinte foncée : le QR se lit sur son cartouche blanc (les couleurs trop claires sont refusées). Pour le poser sur une face : épinglez-la, puis « Ajouter : QR code ».")}</div>
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
					<div class="se-btns" style="margin-top:6px"><button class="btn btn-sm btn-default" data-action="fond" ${this._dims_ok() ? "" : "disabled"}>${__("Fond IA · 1 image · ≈ {0} $", [(est.cout || 0).toFixed(2)])}</button>
						<button class="btn btn-sm btn-default" data-action="integrer" ${this._dims_ok() ? "" : "disabled"} title="${__("L'IA fond ensemble l'image de fond, la photo du produit et les couleurs du logo sur une face, selon votre consigne")}">✨ ${__("Intégrer photo + fond (IA)")}</button></div>
					<label class="se-check"><input type="checkbox" data-champ="fond_continu" ${d.fond_continu ? "checked" : ""}> ${__("Fond continu sur toutes les faces (panorama découpé aux plis)")}</label>
					<label class="se-check"><input type="checkbox" data-champ="faces_identiques" ${d.faces_identiques ? "checked" : ""}> ${__("Face arrière identique à la face avant")}</label>
					<label class="se-check"><input type="checkbox" data-champ="cotes_identiques" ${d.cotes_identiques ? "checked" : ""} title="${__("Avec le dos identique à l'avant, le code-barres et les avertissements sont dupliqués sur les deux côtés.")}"> ${__("Côtés identiques (gauche = droit)")}</label>
					<p class="text-muted small" style="margin:2px 0 6px">${__("Avec une couleur ou une image de fond et la photo du produit, le plan se compose aussi SANS variante IA.")}</p>
					<label>${__("Brief de style")}</label><textarea data-champ="brief_style" placeholder="${__("ex. haut de gamme, bleu profond, minimaliste")}">${esc(d.brief_style || "")}</textarea>
					<div class="se-3" style="grid-template-columns:1.6fr 1fr">
						<div><label>${__("Palette (hex)")}</label><input type="text" data-champ="palette" value="${esc(d.palette || "")}">
							<div class="se-palette" data-role="palette-pastilles">${this._pastilles_palette()}</div></div>
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
					${d.variante_choisie && d.fond_continu && d.image_fond ? `<p class="text-danger small" style="margin:8px 0 0">⚠ ${__("« Fond continu » est coché avec une image de fond : le panorama remplace la variante IA choisie ({0}). Pour composer avec la variante, décochez « Fond continu » à l'étape 3 (ou retirez l'image de fond), puis recomposez.", [esc(((d.variantes || []).find((v) => v.numero === d.variante_choisie) || {}).titre || d.variante_choisie)])}</p>` : ""}
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
		$g.find("[data-qr-couleur]").on("click", (e) => this.modifier({ couleur_qr: $(e.currentTarget).attr("data-qr-couleur") }, true));
		$g.find("[data-ajouter-picto]").on("click", () => this.ajouter_picto());
		$g.find("[data-tampon-ia]").on("click", () => this.atelier_tampon());
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
		// Une vignette s'ouvre en grand, avec la pipette (demande utilisateur 06/10/2026).
		$g.find("[data-voir]").on("click", (e) => {
			const champ = $(e.currentTarget).attr("data-voir");
			this.visionneuse(this.d[champ], { logo: __("Logo"), photo_produit: __("Photo du produit"), image_fond: __("Image de fond") }[champ] || "");
		});
		// La palette se redessine pendant la frappe ; une pastille cliquée sort de la palette.
		$g.find('[data-champ="palette"]').on("input", (e) => $g.find('[data-role="palette-pastilles"]').html(this._pastilles_palette(e.currentTarget.value)));
		$g.on("click", '[data-role="palette-pastilles"] [data-retirer]', (e) => {
			const c = $(e.currentTarget).attr("data-retirer");
			this.modifier({ palette: this._palette().filter((x) => x !== c).join(", ") }, true);
		});
		this.monter_editeur();
	}

	// ─── caractéristiques : éditeur ligne par ligne, polices ─────────────────────
	monter_editeur() {
		const d = this.d;
		this.injecter_polices();
		this.editeur = new EditeurLignes(this.$root.find('[data-role="editeur-car"]'), d.caracteristiques || "", {
			polices: this.data.polices || [], bloc: { police: d.police_caracteristiques || "", taille: +d.taille_caracteristiques || 0 },
			bloc_modifiable: true,
			on_change: frappe.utils.debounce((val) => this.modifier({ caracteristiques: val }, false), 600),
			on_bloc: (b) => this.modifier({ police_caracteristiques: b.police || "", taille_caracteristiques: b.taille || 0 }, false),
			on_ajouter_police: (apres) => this.ajouter_police(apres),
		});
		this.rendre_avert_lignes();
	}

	rendre_avert_lignes() {
		const d = this.d, des = this.data.desalignes || [];
		let codes = [];
		try { codes = Object.keys(JSON.parse(d.textes_ia || "{}")); } catch (e) { codes = []; }
		let h = "";
		if (d.textes_ia) h += `<p class="text-muted small" style="margin:4px 0 0">${__("Ce sont les textes préparés (étape 3) qui s'impriment : la mise en forme de ces lignes leur est reportée, ligne pour ligne.")}</p>`;
		if (des.length) {
			const detail = des.map((x) => __("{0} : {1} lignes préparées pour {2} ici", [x.code.toUpperCase(), x.lignes, x.brutes])).join(" · ");
			h += `<p class="text-danger small" style="margin:4px 0 0">⚠ ${__("Mise en forme non reportée ({0}). Imprimez vos lignes telles quelles ci-dessous, re-préparez les textes, ou mettez-les en forme dans « Modifier les textes ».", [this._esc(detail)])}</p>`;
		}
		// Vos textes de l'étape 2 non encore imprimés (06/10/2026 : « j'ai changé le texte, je n'arrive pas à l'appliquer »).
		const non_appliques = this.data.textes_non_appliques || [];
		if (non_appliques.length) h += `<p class="text-danger small" style="margin:4px 0 0">⚠ ${__("Vos textes ci-dessus ne sont PAS ceux qui s'impriment ({0}) : l'emballage imprime les textes préparés. Cliquez le bouton bleu pour imprimer les vôtres.", [this._esc(non_appliques.join(", ").toUpperCase())])}</p>`;
		// Vos textes déjà écrits dans la langue de l'emballage : ils remplacent la reformulation de l'IA.
		if (codes.length) h += `<div class="se-btns" style="margin-top:4px">${codes.map((c) => `<button class="btn btn-xs ${des.some((x) => x.code === c) || non_appliques.includes(c) ? "btn-primary" : "btn-default"}" data-lignes-brutes="${this._esc(c)}" title="${__("Les caractéristiques (mise en forme comprise), les avertissements et le contact de l'étape 2 deviennent ceux qui s'impriment pour cette langue. À utiliser quand vous les avez écrits dans cette langue.")}">${__("Imprimer mes textes tels quels ({0})", [this._esc(c.toUpperCase())])}</button>`).join("")}</div>`;
		const $a = this.$root.find('[data-role="avert-lignes"]').html(h);
		$a.find("[data-lignes-brutes]").on("click", (e) => this.imprimer_mes_textes($(e.currentTarget).attr("data-lignes-brutes")));
	}

	// Les textes de l'étape 2 deviennent ceux qui s'impriment pour `langue` (caractéristiques, avertissements, contact).
	async imprimer_mes_textes(langue) {
		try {
			// Les frappes en attente d'abord : c'est le texte à l'écran qui doit partir.
			await this.enregistrer({ caracteristiques: this.editeur ? this.editeur.valeur() : this.d.caracteristiques });
			const r = await frappe.call({ method: "aquaworld_ia.emballage.studio.utiliser_lignes_brutes", args: { design: this.nom, langue }, freeze: true });
			this.data = r.message; this.d = this.data.doc; this._lire_mep();
			this.rendre_scene(); this.rendre_droite(); this.rendre_avert_lignes();
			frappe.show_alert({ message: __("Vos textes s'impriment en {0} : recomposez le plan (étape 4).", [langue.toUpperCase()]), indicator: "green" });
		} catch (e2) { frappe.msgprint(this._msg(e2)); }
	}

	// Les polices dans le navigateur (@font-face), pour que l'éditeur montre chaque ligne dans la sienne.
	injecter_polices() {
		const STYLES = { regulier: [400, "normal"], gras: [700, "normal"], italique: [400, "italic"], gras_italique: [700, "italic"] };
		const css = (this.data.polices || []).map((p) => Object.entries(p.styles || {}).map(([cle, url]) => {
			const [poids, style] = STYLES[cle] || [400, "normal"];
			return `@font-face{font-family:"AQIA ${p.famille}";src:url("${encodeURI(url)}");font-weight:${poids};font-style:${style};font-display:swap}`;
		}).join("")).join("");
		let el = document.getElementById("aqia-polices");
		if (!el) { el = document.createElement("style"); el.id = "aqia-polices"; document.head.appendChild(el); }
		if (el.textContent !== css) el.textContent = css;
	}

	ajouter_police(apres) {
		const police = (nom, libelle, reqd) => ({ fieldtype: "Attach", fieldname: nom, label: libelle, reqd: reqd ? 1 : 0,
			options: { restrictions: { allowed_file_types: [".ttf", ".otf"] } } });
		const dlg = new frappe.ui.Dialog({ title: __("Ajouter une police"),
			fields: [
				{ fieldtype: "Data", fieldname: "nom", label: __("Nom"), reqd: 1, description: __("Tel qu'il apparaîtra dans la liste, ex. « EcoPurium Sans »") },
				police("regulier", __("Normal (TTF ou OTF)"), true),
				police("gras", __("Gras")),
				police("italique", __("Italique")),
				police("gras_italique", __("Gras italique")),
				{ fieldtype: "HTML", options: `<p class="text-muted small">${__("Un fichier par style : sans fichier gras, une ligne en gras s'imprime en normal (le moteur PDF ne fabrique ni le gras ni l'italique). Vérifiez que la licence de la police autorise l'impression commerciale.")}</p>` },
			],
			primary_action_label: __("Ajouter"),
			primary_action: async (v) => {
				let r;
				try {
					r = await frappe.call({ method: "aquaworld_ia.emballage.studio.ajouter_police", args: v, freeze: true });
				} catch (e) { frappe.msgprint(this._msg(e)); return; }
				this.data.polices = r.message || [];
				this.injecter_polices();
				dlg.hide();
				frappe.show_alert({ message: __("Police ajoutée : {0}", [v.nom]), indicator: "green" });
				if (apres) apres(v.nom.trim(), this.data.polices);
			} });
		dlg.show();
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
			["artwork", __("Artwork")], ["3d", __("3D")], ["images", __("Images ({0})", [(this.data.images || []).length])]];
		this.$root.find(".se-onglets").html(onglets.map(([k, l]) => `<div class="o ${k === this.onglet ? "on" : ""}" data-onglet="${k}">${l}</div>`).join(""))
			.find(".o").on("click", (e) => { this.onglet = $(e.currentTarget).attr("data-onglet"); this.rendre_scene(); });
		const $s = this.$root.find(".se-scene");
		if (this.onglet === "plan") return this.scene_plan($s);
		if (this.onglet === "variantes") return this.scene_variantes($s);
		if (this.onglet === "images") return this.scene_images($s);
		if (this.onglet === "artwork") return $s.html(d.apercu_plan ? `<img class="se-img" src="${this._esc(d.apercu_plan)}" alt=""><p class="text-muted small text-center" style="margin-top:8px">${__("Aperçu à l'écran. Le PDF imprimeur est à l'échelle, avec le calque de découpe.")}</p>` : `<div class="se-vide">${__("Pas encore de plan composé : choisissez une variante puis « Composer le plan à plat ».")}</div>`);
		if (this.onglet === "3d") {
			// Pendant la génération (≈ 1 min), l'onglet le DIT : il affichait « Pas encore de rendu 3D : composez le
			// plan… », lu comme un échec (retour utilisateur 06/10/2026 : « ça n'a pas marché », le rendu était en cours).
			const e = this.data.etat || {};
			if (this._mockup_en_cours || (e.tache === "mockup" && e.statut === "en cours"))
				return $s.html(`<div class="se-vide">⏳ ${__("Rendu 3D en cours, environ une minute : l'image s'affichera ici toute seule.")}<br><span class="small text-muted" data-role="attente-txt">${this._esc(e.etape || "")}</span></div>`);
			const echec = e.tache === "mockup" && e.statut === "echec"
				? `<p class="text-danger small text-center">${__("Le dernier rendu 3D a échoué : {0}. Relancez « Aperçu 3D » (étape 4).", [this._esc(e.erreur || __("erreur inconnue"))])}</p>` : "";
			return $s.html(echec + (d.apercu_3d ? `<img class="se-img" src="${this._esc(d.apercu_3d)}" alt=""><p class="text-muted small text-center" style="margin-top:8px">${__("Illustration non contractuelle.")}</p>` : `<div class="se-vide">${__("Pas encore de rendu 3D : composez le plan, puis « Aperçu 3D ».")}</div>`));
		}
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
		const TYPES = ["logo", "nom", "accroche", "caracteristiques", "avertissements", "contact", "texte_libre", "pictos", "code_barres", "qr", "photo"];
		const LIBS = { logo: __("Logo"), nom: __("Nom du produit"), accroche: __("Accroche"), caracteristiques: __("Caractéristiques"), avertissements: __("Avertissements"), contact: __("Contact"), texte_libre: __("Texte libre (sans IA)"), pictos: __("Pictogrammes / certifications"), code_barres: __("Code-barres"), qr: __("QR code"), photo: __("Photo produit") };
		const outils = fe ? `<div class="se-outils" style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;padding:6px 8px;margin-bottom:6px;border:1px solid #bfdbfe;background:#eff6ff;border-radius:8px;font-size:12.5px">
				<b>${this._esc(fe.libelle)}</b> <span class="text-muted">${__("épinglée")}</span>
				<span style="margin-left:8px">${__("Ajouter :")}</span>
				<select class="form-control input-xs" data-role="type-zone-plan" style="height:26px;font-size:12px;width:auto;display:inline-block">${TYPES.map((t) => `<option value="${t}">${LIBS[t]}</option>`).join("")}${this._options_tampons()}</select>
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
		const zones = (face.zones || []).map((z) => ({ zone: z.zone, x: z.x, y: z.y, w: z.w, h: z.h, libelle: z.libelle, style: z.style || null, logo: z.logo || null, pictos: z.pictos || null, typo: z.typo || null, texte: z.texte || "", code: z.code || null, auto: z.auto || 0 }));
		const u = face.utile || face;   // une zone ne va jamais dans une bande réservée (repli agrafé)
		const el = (tag, attrs) => { const n = document.createElementNS(NS, tag); Object.entries(attrs).forEach(([k, v]) => n.setAttribute(k, v)); g.appendChild(n); return n; };
		const point = (e) => { const pt = svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY; return pt.matrixTransform(svg.getScreenCTM().inverse()); };
		const sauver = () => {
			this.mep[face.code] = zones.map((z) => Object.assign({ zone: z.zone, x: z.x, y: z.y, w: z.w, h: z.h }, z.style ? { style: z.style } : {}, z.logo ? { logo: z.logo } : {}, z.pictos && z.pictos.length ? { pictos: z.pictos } : {},
				z.typo && Object.keys(z.typo).length ? { typo: z.typo } : {}, z.zone === "texte_libre" ? { texte: z.texte || "" } : {}, z.code ? { code: z.code } : {}));
			this.modifier({ mise_en_page: this.mep }, false);
		};
		zones.forEach((z, i) => {
			const fond = z.style && z.style.fond;
			const r = el("rect", { x: z.x, y: z.y, width: z.w, height: z.h, rx: fond ? (z.style.rayon || 0) : 0, fill: fond || "#f59e0b", "fill-opacity": fond ? "0.55" : "0.18",
				stroke: this.zone_sel === i ? "#dc2626" : "#d97706", "stroke-width": this.zone_sel === i ? W / 350 : W / 700, style: "cursor:move" });
			const t = el("text", { x: z.x + W / 400, y: z.y + Math.max(2, Math.min(z.w, z.h) / 4), "font-size": Math.max(2, Math.min(Math.min(z.w, z.h) / 4, W / 70)), fill: "#92400e", "font-family": "sans-serif", style: "pointer-events:none" });
			t.textContent = z.libelle || z.zone;
			if (z.zone === "texte_libre") {
				if (z.typo && z.typo.police) t.setAttribute("font-family", `"AQIA ${z.typo.police}", sans-serif`);
				if (z.style && z.style.texte) t.setAttribute("fill", z.style.texte);
			}
			const p = el("rect", { x: z.x + z.w - POIGNEE, y: z.y + z.h - POIGNEE, width: POIGNEE, height: POIGNEE, fill: "#d97706", style: "cursor:nwse-resize" });
			const x = el("text", { x: z.x + z.w - POIGNEE * 0.9, y: z.y + POIGNEE * 1.1, "font-size": POIGNEE * 1.3, fill: "#b91c1c", "font-family": "sans-serif", style: "cursor:pointer;font-weight:bold" });
			x.textContent = "×"; x.addEventListener("click", (e) => {
				e.stopPropagation();
				// La photo posée d'office revient tant qu'une photo produit existe : on le dit au lieu de faire semblant.
				if (z.auto) return frappe.msgprint(__("La photo produit est posée automatiquement. Déplacez-la ou agrandissez-la pour la placer vous-même ; pour ne pas l'imprimer, retirez la photo produit à l'étape 2 (×)."));
				zones.splice(i, 1); sauver();
			});
			if (z.auto) r.setAttribute("stroke-dasharray", `${W / 150},${W / 300}`);
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
		if (String(type || "").startsWith("tampon:")) return this.placer_tampon(type.slice(7), this.epinglee);
		const c = this._zones_en_cours;
		if (!c) return;
		const f = c.face.utile || c.face;
		// Un QR code (06/10/2026 : « si je veux l'ajouter en face ? ») : une zone code-barres qui ne porte que
		// le QR, carrée, 22 mm (le minimum confortable pour un téléphone), en bas à droite de la face.
		if (type === "qr") {
			const t = Math.max(10, Math.min(22, f.w * 0.45, f.h * 0.45));
			c.zones.push({ zone: "code_barres", code: "qr", x: f.x + f.w - t - 3, y: f.y + f.h - t - 3, w: t, h: t, libelle: __("QR code") });
			this.zone_sel = c.zones.length - 1;
			c.sauver();
			if (!["QR", "EAN-13 + QR"].includes(this.d.type_code_barres) || !this.d.url_qr)
				frappe.show_alert({ message: __("Zone QR posée. Pour qu'il s'imprime : étape 2, « Code » = QR (ou EAN-13 + QR) et l'URL du QR."), indicator: "orange" }, 10);
			return;
		}
		// Une photo part grande et centrée (on la réduit ensuite) ; un texte ou un logo, en bandeau.
		const g = type === "photo" ? { x: 0.2, y: 0.25, w: 0.6, h: 0.45 } : { x: 0.3, y: 0.4, w: 0.4, h: 0.15 };
		const z = { zone: type, x: f.x + f.w * g.x, y: f.y + f.h * g.y, w: f.w * g.w, h: f.h * g.h, libelle: type };
		if (type === "texte_libre") z.texte = __("Votre texte");
		c.zones.push(z);
		// Un texte libre s'écrit tout de suite : ses réglages (texte, police, couleur) s'ouvrent.
		if (type === "texte_libre") this.zone_sel = c.zones.length - 1;
		c.sauver();
	}

	// Les tampons cochés sur le design, proposés directement dans « Ajouter » (06/10/2026 : « le tampon généré,
	// comment je peux l'ajouter ? » — il fallait une zone Pictogrammes, la cliquer et ne cocher que lui).
	_options_tampons() {
		const coches = new Set((this.d.pictogrammes || []).map((p) => p.pictogramme));
		const tampons = (this.data.pictos || []).filter((p) => p.categorie === "Tampon" && coches.has(p.code));
		return tampons.length ? `<optgroup label="${__("Tampons")}">${tampons.map((p) => `<option value="tampon:${this._esc(p.code)}">${__("Tampon")} : ${this._esc(p.libelle || p.code)}</option>`).join("")}</optgroup>` : "";
	}

	// Pose un tampon sur une face : une zone « Pictogrammes » qui ne montre que lui, à sa taille (mm), en bas à
	// droite de la partie utile — ensuite on la déplace et on l'agrandit sur le plan comme toute zone.
	async placer_tampon(code, face_code) {
		const f = ((this.data.apercu || {}).faces || []).find((x) => x.code === face_code);
		if (!f) return frappe.msgprint(__("Épinglez d'abord une face du plan (cliquez-la), puis ajoutez le tampon."));
		const u = f.utile || f, p = (this.data.pictos || []).find((x) => x.code === code) || {};
		const t = Math.max(8, Math.min(+p.taille_mm || 25, u.w * 0.45, u.h * 0.45));
		const garder = (z) => Object.assign({ zone: z.zone, x: z.x, y: z.y, w: z.w, h: z.h }, z.style ? { style: z.style } : {}, z.logo ? { logo: z.logo } : {},
			z.pictos && z.pictos.length ? { pictos: z.pictos } : {}, z.typo ? { typo: z.typo } : {}, z.zone === "texte_libre" ? { texte: z.texte || "" } : {}, z.code ? { code: z.code } : {});
		const zones = (this.mep[face_code] || (f.zones || []).map(garder)).slice();
		zones.push({ zone: "pictos", x: u.x + u.w - t - 4, y: Math.min(u.y + u.h * 0.6, u.y + u.h - t - 4), w: t, h: t, pictos: [code] });
		this.mep[face_code] = zones;
		await this.modifier({ mise_en_page: this.mep }, false);
		this.epinglee = face_code; this.zone_sel = zones.length - 1; this.onglet = "plan";
		this.rendre_scene();
		frappe.show_alert({ message: __("Tampon posé sur « {0} » : déplacez-le ou agrandissez-le sur le plan, puis recomposez (étape 4).", [f.libelle]), indicator: "green" }, 8);
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
	scene_images($s) {
		const esc = this._esc, images = this.data.images || [];
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
					<button class="btn btn-xs btn-default" data-garder-url="${esc(im.file_url)}" data-garder-champ="${im.genre.startsWith("Logo") ? "logo" : im.genre.startsWith("Photo") ? "photo_produit" : "image_fond"}" title="${__("Garder en bibliothèque, sous un nom")}">💾</button>
					<a class="btn btn-xs btn-default" href="${esc(im.file_url)}" target="_blank" title="${__("Ouvrir le fichier")}">↗</a>
				</div></div>`).join("")}</div>`);
		$s.find("[data-usage]").on("click", (e) => this.modifier({ [$(e.currentTarget).attr("data-usage")]: $(e.currentTarget).attr("data-url") }, true));
		$s.find("[data-garder-url]").on("click", (e) => this.garder($(e.currentTarget).attr("data-garder-champ"), $(e.currentTarget).attr("data-garder-url")));
		$s.find("[data-voir-url]").on("click", (e) => this.visionneuse($(e.currentTarget).attr("data-voir-url"), ""));
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
			<div class="bloc se-textes"><h6>${__("Textes imprimés")}</h6>
				${(this.data.textes_non_appliques || []).length ? `<div class="small text-danger" style="margin-bottom:6px">⚠ ${__("Ce ne sont pas vos textes de l'étape 2 : ce sont les textes préparés.")}
					<div class="se-btns" style="margin-top:4px">${this.data.textes_non_appliques.map((c) => `<button class="btn btn-xs btn-primary" data-imprimer-mes-textes="${this._esc(c)}">${__("Remplacer par mes textes de l'étape 2 ({0})", [this._esc(c.toUpperCase())])}</button>`).join("")}</div></div>` : ""}
				${this.data.textes_html || ""}
				${this.d.textes_ia ? `<div class="small text-muted" style="margin-top:6px">${__("Pour retoucher ces textes un par un (accroche comprise) : « Modifier les textes », étape 3.")}</div>` : ""}</div>
			<div class="bloc"><h6>${__("Fichiers")}</h6>${fichiers ? `<ul>${fichiers}</ul>` : `<span class="text-muted">${__("Rien encore.")}</span>`}</div>`);
		this.$root.find(".se-droite [data-imprimer-mes-textes]").on("click", (e) => this.imprimer_mes_textes($(e.currentTarget).attr("data-imprimer-mes-textes")));
		// Une face épinglée garde son panneau (zones, « Ajouter », « Revenir ») après chaque
		// enregistrement : sans cela, déplacer une zone effaçait le panneau qui sert à continuer.
		const f = this.epinglee && ((this.data.apercu || {}).faces || []).find((x) => x.code === this.epinglee);
		if (f) this.face_info(f);
	}

	face_info(f) {
		const $b = this.$root.find('[data-role="face"]');
		if (!f) return $b.html(`<span class="text-muted">${__("Survolez une face du plan.")}</span>`);
		const epinglee = this.epinglee === f.code;
		const zones = (f.zones || []).map((z, i) => `<li ${epinglee ? `data-zi="${i}" style="cursor:pointer${this.zone_sel === i ? ";font-weight:600;color:#b91c1c" : ""}"` : ""}>${this._esc(z.libelle)} <span class="text-muted">${z.w.toFixed(0)} × ${z.h.toFixed(0)} mm</span>${z.style && z.style.fond ? ` <span class="se-chip" style="background:${this._esc(z.style.fond)};color:${this._esc((z.style.texte) || "#fff")}">${__("cartouche")}</span>` : ""}${z.logo ? ` <span class="se-chip">${__("logo propre")}</span>` : ""}${z.pictos && z.pictos.length ? ` <span class="se-chip">${__("{0} picto(s)", [z.pictos.length])}</span>` : ""}${this._chip_typo(z)}</li>`).join("");
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
		if (sel && (TEXTES.includes(sel.zone) || sel.zone === "texte_libre")) {
			props += this._panneau_texte(sel);
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
		} else if (sel && sel.zone === "code_barres") {
			const PORTE = [["", __("Automatique (selon « Code », étape 2)")], ["qr", __("QR code")], ["ean", __("EAN-13")]];
			const petit = sel.code === "qr" && Math.min(sel.w, sel.h) < 20;
			props += `<div class="bloc" style="margin-top:8px;padding:8px 10px;background:#f8fafc"><h6>${__("Contenu de cette zone")}</h6>
				<select class="form-control input-xs" data-prop="code_zone" style="height:26px;font-size:12px">${PORTE.map(([v, l]) => `<option value="${v}" ${(sel.code || "") === v ? "selected" : ""}>${l}</option>`).join("")}</select>
				<div class="se-btns" style="margin-top:8px"><button class="btn btn-xs btn-primary" data-role="appliquer-code">${__("Appliquer")}</button></div>
				${petit ? `<div class="text-danger small" style="margin-top:6px">⚠ ${__("Moins de 20 mm de côté : le scan devient incertain. Agrandissez la zone.")}</div>` : ""}
				<div class="text-muted small" style="margin-top:6px">${__("QR code : le QR, carré, au centre de la zone, dans la couleur choisie à l'étape 2. Dès qu'une zone QR code existe, les zones automatiques n'impriment plus de second QR.")}</div></div>`;
		} else if (sel) {
			props += `<div class="text-muted small" style="margin-top:6px">${__("Cette zone n'a pas de réglage : déplacez-la ou redimensionnez-la sur le plan.")}</div>`;
		}
		const types = ["logo", "nom", "accroche", "caracteristiques", "avertissements", "contact", "texte_libre", "pictos", "code_barres", "qr", "photo"];
		const libs = { logo: __("Logo"), nom: __("Nom du produit"), accroche: __("Accroche"), caracteristiques: __("Caractéristiques"), avertissements: __("Avertissements"), contact: __("Contact"), texte_libre: __("Texte libre (sans IA)"), pictos: __("Pictogrammes"), code_barres: __("Code-barres"), qr: __("QR code"), photo: __("Photo produit") };
		const source = f.copie_de && ((this.data.apercu || {}).faces || []).find((x) => x.code === f.copie_de);
		const bloquee = f.copie_bloquee && ((this.data.apercu || {}).faces || []).find((x) => x.code === f.copie_bloquee);
		$b.html(`<h6>${this._esc(f.libelle)} <span class="text-muted">${f.w.toFixed(0)} × ${f.h.toFixed(0)} mm</span>${f.personnalisee ? ` <span class="se-chip encours">${__("personnalisée")}</span>` : ""}${source ? ` <span class="se-chip" title="${__("Modifiez la face source : cette face la suit. Dessinez ici pour la rendre indépendante.")}">${__("copie de {0}", [this._esc(source.libelle)])}</span>` : ""}${bloquee ? ` <span class="se-chip echec" title="${__("Option cochée, mais cette face a sa propre mise en page : « Revenir à la maquette automatique » pour qu'elle recopie.")}">${__("ne copie plus {0}", [this._esc(bloquee.libelle)])}</span>` : ""}</h6>
			${zones ? `<ul>${zones}</ul>` : `<span class="text-muted">${__("Aucun emplacement : renseignez logo, textes, pictogrammes ou code-barres.")}</span>`}
			${props}
			${this.epinglee === f.code ? this._bloc_fond_face(f) : ""}
			${this.epinglee === f.code ? `
				<div class="small" style="margin-top:8px">${__("Sur le plan : glissez une zone pour la déplacer, tirez son coin pour l'agrandir, × pour la supprimer, cliquez-la pour ses réglages (cartouche, logo).")}</div>
				<div style="display:flex;gap:4px;margin-top:6px;align-items:center"><select class="form-control input-xs" data-role="type-zone" style="height:26px;font-size:12px;flex:1;min-width:0">${types.map((t) => `<option value="${t}">${libs[t]}</option>`).join("")}${this._options_tampons()}</select>
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
			// Typographie de la zone (06/10/2026) : police, taille, gras, italique, alignement.
			const ty = {};
			const police = $b.find('[data-prop="police"]').val(); if (police) ty.police = police;
			const taille = parseFloat($b.find('[data-prop="taille"]').val()); if (taille) ty.taille = taille;
			ty.gras = $b.find('[data-prop="gras"]').is(":checked");
			if ($b.find('[data-prop="italique"]').is(":checked")) ty.italique = true;
			const align = $b.find('[data-prop="align"]').val(); if (align) ty.align = align;
			z.typo = ty;
			if (z.zone === "texte_libre") z.texte = $b.find('[data-prop="texte_libre"]').val() || "";
			this._zones_en_cours.sauver();
		});
		// La police choisie se voit tout de suite dans le champ de texte.
		$b.find('[data-prop="police"]').on("change", (e) => {
			const v = $(e.currentTarget).val();
			$b.find('[data-prop="texte_libre"]').css("font-family", v ? `"AQIA ${v}", sans-serif` : "");
		});
		$b.find('[data-prop="texte"], [data-prop="avec_texte"]').on("change", () => {
			const avec = $b.find('[data-prop="avec_texte"]').is(":checked");
			$b.find('[data-prop="texte_libre"]').css("color", avec ? $b.find('[data-prop="texte"]').val() : "");
		});
		$b.find('[data-role="police-zone-ajouter"]').on("click", () => this.ajouter_police(() => this.face_info(f)));
		// Une pastille de la palette du design remplit la couleur (et coche « imposer » / « fond »).
		$b.find("[data-pastille-cible]").on("click", (e) => {
			const $p = $(e.currentTarget), cible = $p.attr("data-pastille-cible");
			$b.find(`[data-prop="${cible}"]`).val($p.attr("data-couleur")).trigger("change");
			$b.find(`[data-prop="${cible === "texte" ? "avec_texte" : "avec_fond"}"]`).prop("checked", true).trigger("change");
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
		$b.find('[data-role="appliquer-code"]').on("click", () => { const z = zone_courante(); if (!z) return; z.code = $b.find('[data-prop="code_zone"]').val() || null; this._zones_en_cours.sauver(); });
		$b.find('[data-role="pictos-tous"]').on("click", () => { const z = zone_courante(); if (!z) return; z.pictos = null; this._zones_en_cours.sauver(); });
		$b.find('[data-role="logo-variante"]').on("click", () => this.bibliotheque("logo", (l) => { const z = zone_courante(); if (!z) return; z.logo = l.image; this._zones_en_cours.sauver(); }));
		$b.find('[data-role="logo-commun"]').on("click", () => { const z = zone_courante(); if (!z) return; z.logo = null; this._zones_en_cours.sauver(); });
		$b.find('[data-role="reinit-face"]').on("click", () => this.reinitialiser_face(f.code));
		// Fond de la face (06/10/2026) : mode, couleur, composition IA.
		const regler = (reg) => {
			const fonds = this._fonds();
			if (reg) fonds[f.code] = Object.assign({}, fonds[f.code] || {}, reg); else delete fonds[f.code];
			this.d.fonds_faces = JSON.stringify(fonds);
			this.modifier({ fonds_faces: fonds }, false).then(() => {
				this.face_info(f);
				frappe.show_alert({ message: __("Fond de la face enregistré : recomposez le plan (étape 4)."), indicator: "green" });
			});
		};
		$b.find("[data-mode-fond]").on("click", (e) => {
			const mode = $(e.currentTarget).attr("data-mode-fond"), actuel = this._fonds()[f.code] || {};
			if (!mode) return regler(null);
			if (mode === "couleur") return regler({ mode, couleur: actuel.couleur || this._palette()[0] || "#e5e7eb" });
			regler({ mode });
		});
		$b.find('[data-role="fond-face-couleur"]').on("change", (e) => regler({ mode: "couleur", couleur: e.currentTarget.value.toLowerCase() }));
		$b.find("[data-fond-face-pastille]").on("click", (e) => regler({ mode: "couleur", couleur: $(e.currentTarget).attr("data-fond-face-pastille") }));
		$b.find('[data-role="fond-face-ia"]').on("click", () => this.atelier_face(f.code));
		$b.find('[data-role="photo-incluse"]').on("change", (e) => regler({ photo_incluse: e.currentTarget.checked }));
		$b.find('[data-role="fond-face-blanc"]').on("click", () => this.blanchir((this._fonds()[f.code] || {}).mode === "image" ? f.code : "fond"));
		$b.find("[data-voir-face]").on("click", (e) => { e.preventDefault(); this.visionneuse($(e.currentTarget).attr("data-voir-face"), f.libelle); });
	}

	async blanchir(cible) {
		let r;
		try {
			r = await frappe.call({ method: "aquaworld_ia.emballage.studio.blanchir", args: { design: this.nom, cible }, freeze: true,
				freeze_message: __("Blanc pur, puis recomposition du plan…") });
		} catch (e) { frappe.msgprint(this._msg(e)); return; }
		const m = r.message || {};
		this.data = m; this.d = m.doc; this._lire_mep(); if (m.recompose) this.onglet = "artwork"; this.rendre();
		frappe.show_alert({ message: __("Blanc pur : {0} % de pixels parfaitement blancs (avant : {1} %). L'ancienne image reste dans l'onglet Images.", [m.blanc_apres, m.blanc_avant]), indicator: "green" }, 8);
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
		return `<div class="bloc" style="margin-top:8px;padding:8px 10px;background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px">
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
			<p class="small text-muted" style="margin-top:8px">${__("Rien ne change avant « Utiliser sur cette face ». Les propositions restent dans l'onglet Images.")}</p>`);
		cmp.fields_dict.galerie.$wrapper.find("[data-voir-prop]").on("click", (e) => { e.preventDefault(); this.visionneuse($(e.currentTarget).attr("data-voir-prop"), ""); });
		cmp.fields_dict.galerie.$wrapper.find("[data-utiliser-face]").on("click", async (e) => {
			let r;
			try {
				r = await frappe.call({ method: "aquaworld_ia.emballage.studio.adopter_face_ia", freeze: true, freeze_message: __("Face posée, recomposition du plan…"),
					args: { design: this.nom, face: m.face, url: $(e.currentTarget).attr("data-utiliser-face"), photo_incluse: m.photo_incluse ? 1 : 0 } });
			} catch (e2) { frappe.msgprint(this._msg(e2)); return; }
			cmp.hide();
			this.data = r.message; this.d = this.data.doc; this._lire_mep();
			if (r.message.recompose) this.onglet = "artwork";
			this.rendre();
			frappe.show_alert({ message: r.message.recompose ? __("Face posée, plan recomposé.") : __("Face posée : composez le plan (étape 4)."), indicator: "green" });
		});
		cmp.show();
	}

	// Une zone de texte : son texte (texte libre, jamais touché par l'IA), sa typographie et sa
	// couleur — demande utilisateur 06/10/2026 : « chaque zone texte je peux contrôler font et couleur ».
	_panneau_texte(sel) {
		this.injecter_polices();   // les polices du studio, pour l'aperçu dans le champ et sur le plan
		const esc = this._esc, st = sel.style || {}, ty = sel.typo || {};
		const libre = sel.zone === "texte_libre";
		const gras = ty.gras !== undefined ? ty.gras : ["nom", "accroche"].includes(sel.zone);
		const polices = (this.data.polices || []).map((p) => p.famille);
		const ALIGN = [["", __("Par défaut")], ["left", __("Gauche")], ["center", __("Centré")], ["right", __("Droite")], ["justify", __("Justifié")]];
		const apercu = `${ty.police ? `font-family:&quot;AQIA ${esc(ty.police)}&quot;, sans-serif;` : ""}${st.texte ? `color:${esc(st.texte)};` : ""}${st.fond ? `background:${esc(st.fond)};` : ""}`;
		const defaut_taille = { nom: __("auto"), accroche: "11", caracteristiques: String(+this.d.taille_caracteristiques || 8.5), avertissements: "7", contact: "7", texte_libre: "10" }[sel.zone];
		return `<div class="bloc" style="margin-top:8px;padding:8px 10px;background:#f8fafc"><h6>${__("Zone « {0} »", [esc(sel.libelle)])}</h6>
			${libre ? `<label class="small" style="margin:0">${__("Texte")}</label>
				<textarea class="form-control" data-prop="texte_libre" rows="4" style="font-size:13px;${apercu}">${esc(sel.texte || "")}</textarea>
				<div class="text-muted small" style="margin:3px 0 8px">${__("Imprimé tel quel, jamais modifié par l'IA. Une ligne peut avoir sa propre mise en forme : « {14pt, gras} Ma ligne ».")}</div>` : ""}
			<div style="display:grid;grid-template-columns:auto minmax(0,1fr);gap:6px 8px;align-items:center;font-size:12px">
				<span>${__("Police")}</span><span style="display:flex;gap:4px;min-width:0"><select class="form-control input-xs" data-prop="police" style="height:26px;font-size:12px;flex:1;min-width:0"><option value="">${__("Par défaut")}</option>${polices.map((p) => `<option value="${esc(p)}" ${p === ty.police ? "selected" : ""}>${esc(p)}</option>`).join("")}</select><button class="btn btn-xs btn-default" data-role="police-zone-ajouter" title="${__("Ajouter une police (TTF/OTF)")}">＋</button></span>
				<span>${__("Taille (pt)")}</span><input type="number" data-prop="taille" min="4" max="120" step="0.5" value="${ty.taille || ""}" placeholder="${esc(defaut_taille)}" style="width:80px">
				<span>${__("Style")}</span><span><label class="se-check" style="margin:0 10px 0 0"><input type="checkbox" data-prop="gras" ${gras ? "checked" : ""}> <b>${__("Gras")}</b></label><label class="se-check" style="margin:0"><input type="checkbox" data-prop="italique" ${ty.italique ? "checked" : ""}> <i>${__("Italique")}</i></label></span>
				<span>${__("Alignement")}</span><select class="form-control input-xs" data-prop="align" style="height:26px;font-size:12px">${ALIGN.map(([v, l]) => `<option value="${v}" ${(ty.align || "") === v ? "selected" : ""}>${l}</option>`).join("")}</select>
				<span>${__("Couleur")}</span><span style="display:flex;gap:8px;align-items:center;flex-wrap:wrap"><input type="color" data-prop="texte" value="${esc(st.texte || "#111827")}" style="width:44px;height:26px;padding:1px"><label class="se-check" style="margin:0"><input type="checkbox" data-prop="avec_texte" ${st.texte ? "checked" : ""}> ${__("imposer")}</label>${this._pastilles_cible("texte")}</span>
				<span>${__("Cartouche")}</span><span style="display:flex;gap:8px;align-items:center;flex-wrap:wrap"><input type="color" data-prop="fond" value="${esc(st.fond || "#1d4ed8")}" style="width:44px;height:26px;padding:1px"><label class="se-check" style="margin:0"><input type="checkbox" data-prop="avec_fond" ${st.fond ? "checked" : ""}> ${__("fond")}</label>${this._pastilles_cible("fond")}</span>
				<span>${__("Coins (mm)")}</span><input type="number" data-prop="rayon" min="0" step="0.5" value="${st.rayon || 0}" style="width:70px">
			</div>
			<div class="se-btns" style="margin-top:8px"><button class="btn btn-xs btn-primary" data-role="appliquer-style">${__("Appliquer")}</button><button class="btn btn-xs btn-default" data-role="style-aucun">${__("Sans cartouche")}</button></div>
			<div class="text-muted small" style="margin-top:6px">${__("La taille est un maximum : si le texte ne tient pas dans la zone, il est réduit (agrandissez la zone sur le plan). « Par défaut » = la police du design. Puis recomposez le plan (étape 4) pour voir le résultat imprimé.")}</div></div>`;
	}

	_chip_typo(z) {
		const ty = z.typo || {}, st = z.style || {};
		if (!ty.police && !ty.taille && !(st.texte && !st.fond)) return "";
		const style = `${ty.police ? `font-family:&quot;AQIA ${this._esc(ty.police)}&quot;, sans-serif;` : ""}${st.texte && !st.fond ? `color:${this._esc(st.texte)};` : ""}`;
		return ` <span class="se-chip" style="${style}">Aa ${this._esc([ty.police, ty.taille ? ty.taille + " pt" : ""].filter(Boolean).join(" · ") || __("couleur"))}</span>`;
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
			} else if (nom === "logo_couleur") {
				this.atelier_couleur();
			} else if (nom === "photo_ia") {
				this.atelier_image("photo_produit");
			} else if (nom === "fond") {
				this.atelier_fond();
			} else if (nom === "integrer") {
				this.atelier_face(this.epinglee || "avant");
			} else if (nom === "composer") {
				const r = await frappe.call({ method: "aquaworld_ia.emballage.composition.composer_et_attacher",
					args: { design: this.nom, variante: this.d.variante_choisie }, freeze: true, freeze_message: __("Composition du plan à l'échelle…") });
				frappe.show_alert({ message: __("Plan à plat prêt : feuille {0} × {1} mm.", [r.message.feuille.w, r.message.feuille.h]), indicator: "green" });
				await this.recharger(); this.etape = 4; this.onglet = "artwork"; this.rendre();
				this.signaler_reductions(r.message.reductions || []);
			} else if (nom === "faces") {
				frappe.confirm(__("Générer les 5 autres faces dans le style de la variante choisie, puis recomposer le plan ? (5 images facturées)"), async () => {
					await frappe.call({ method: "aquaworld_ia.emballage.job.lancer_faces", args: { design: this.nom } });
					this.suivre();
				});
			} else if (nom === "mockup") {
				await frappe.call({ method: "aquaworld_ia.emballage.job.lancer_mockup", args: { design: this.nom } });
				this.suivre(); this._mockup_en_cours = true;
				this.onglet = "3d"; this.rendre_scene();
			}
		} catch (e) {
			frappe.msgprint(this._msg(e));
		}
	}

	// Les tailles choisies ligne par ligne sont des maximums : un bloc trop long pour sa zone est réduit
	// en entier. Le dire, sinon « 14 pt » imprimé plus petit paraît ignoré.
	signaler_reductions(reductions) {
		if (!reductions.length) return;
		const ZONES = { caracteristiques: __("Caractéristiques"), avertissements: __("Avertissements"), contact: __("Contact"), accroche: __("Accroche") };
		const lignes = reductions.map((x) => x.echelle
			? __("{0} · {1} : imprimé à {2} % de la taille demandée", [ZONES[x.zone] || x.zone, this._esc(x.libelle), Math.round(x.echelle * 100)])
			: __("{0} · {1} : ne tient pas, même réduit à 40 % — non imprimé", [ZONES[x.zone] || x.zone, this._esc(x.libelle)]));
		frappe.msgprint({ title: __("Textes réduits pour tenir dans leur zone"), indicator: "orange",
			message: lignes.join("<br>") + `<p class="text-muted small" style="margin-top:8px">${__("Agrandissez la zone sur le plan, raccourcissez le texte ou baissez les tailles.")}</p>` });
	}

	dialogue_textes() {
		let textes = {};
		try { textes = JSON.parse(this.d.textes_ia || "{}"); } catch (e) { textes = {}; }
		const codes = Object.keys(textes), fields = [], editeurs = {};
		codes.forEach((c) => {
			const t = textes[c] || {};
			fields.push({ fieldtype: "Section Break", label: c.toUpperCase() });
			fields.push({ fieldtype: "Data", fieldname: `acc_${c}`, label: __("Accroche"), default: t.accroche });
			fields.push({ fieldtype: "HTML", fieldname: `car_${c}`, options: `<label class="control-label">${__("Caractéristiques (une par ligne)")}</label><div data-car="1"></div>` });
			fields.push({ fieldtype: "Small Text", fieldname: `ave_${c}`, label: __("Avertissements (un par ligne)"), default: (t.avertissements || []).join("\n") });
			fields.push({ fieldtype: "Small Text", fieldname: `con_${c}`, label: __("Contact"), default: t.contact });
		});
		const dlg = new frappe.ui.Dialog({ title: __("Textes imprimés"), size: "large", fields, primary_action_label: __("Enregistrer"),
			primary_action: async (v) => {
				const out = {};
				codes.forEach((c) => { out[c] = { accroche: v[`acc_${c}`] || "", caracteristiques: editeurs[c].valeur().split("\n").filter((x) => x.trim()),
					avertissements: (v[`ave_${c}`] || "").split("\n").filter(Boolean), contact: v[`con_${c}`] || "" }; });
				await frappe.call({ method: "aquaworld_ia.emballage.textes.enregistrer_textes", args: { design: this.nom, textes: out } });
				dlg.hide(); await this.recharger();
			} });
		// Même éditeur qu'à l'étape 2, langue par langue (la police du bloc se règle à l'étape 2).
		this.injecter_polices();
		codes.forEach((c) => {
			const lg = (this.data.langues || []).find((l) => l.code === c) || {};
			editeurs[c] = new EditeurLignes(dlg.get_field(`car_${c}`).$wrapper.find("[data-car]"), ((textes[c] || {}).caracteristiques || []).join("\n"), {
				polices: this.data.polices || [], bloc: { police: this.d.police_caracteristiques || "", taille: +this.d.taille_caracteristiques || 0 },
				rtl: !!lg.rtl, auto_intertitres: false,
				on_ajouter_police: (apres) => this.ajouter_police((nom, polices) => {
					codes.forEach((k) => { editeurs[k].o.polices = polices; if (k !== c) editeurs[k].rendre(); });
					apres(nom, polices);
				}),
			});
		});
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
			<span class="small text-muted" style="flex:1 1 200px">${__("Fond actuel. Les anciens fonds restent dans l'onglet Images (bouton « Fond » pour revenir à l'un d'eux).")}</span>
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
			<p class="small text-muted" style="margin-top:8px">${__("Cliquez une image pour l'ouvrir en grand (pipette comprise). Rien ne change tant que vous n'avez pas cliqué « Utiliser ce fond » ; les propositions restent dans l'onglet Images.")}</p>`);
		cmp.fields_dict.galerie.$wrapper.find("[data-voir-fond]").on("click", (e) => { e.preventDefault(); this.visionneuse($(e.currentTarget).attr("data-voir-fond"), __("Fond")); });
		cmp.fields_dict.galerie.$wrapper.find("[data-utiliser-fond]").on("click", async (e) => {
			const $b = $(e.currentTarget), url = $b.attr("data-utiliser-fond"), retoucher = $b.attr("data-puis-retoucher");
			let r;
			try {
				r = await frappe.call({ method: "aquaworld_ia.emballage.studio.adopter_fond", args: { design: this.nom, url, continu: m.continu },
					freeze: true, freeze_message: __("Fond appliqué, recomposition du plan…") });
			} catch (e2) { frappe.msgprint(this._msg(e2)); return; }
			cmp.hide();
			this.data = r.message; this.d = this.data.doc; this._lire_mep();
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
			.map((c) => c.trim().toLowerCase()).map((c) => (c && !c.startsWith("#") ? "#" + c : c))
			.filter((c) => /^#[0-9a-f]{6}$/.test(c) && !vus.has(c) && vus.add(c));
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

	ajouter_a_la_palette(couleur) {
		const cs = this._palette();
		if (cs.includes(couleur)) return frappe.show_alert({ message: __("{0} est déjà dans la palette.", [couleur]), indicator: "blue" });
		this.modifier({ palette: cs.concat([couleur]).join(", ") }, true);
		frappe.show_alert({ message: __("{0} ajoutée à la palette du design.", [couleur]), indicator: "green" });
	}

	// Une image en grand (photo, logo, fond…) : un clic dessus prend la couleur du point (pipette).
	visionneuse(url, titre) {
		if (!url) return;
		const esc = this._esc;
		const damier = "background:repeating-conic-gradient(#e5e7eb 0% 25%, #fff 0% 50%) 50% / 16px 16px";
		const hex = (r, g, b) => "#" + [r, g, b].map((v) => v.toString(16).padStart(2, "0")).join("");
		let choisie = null;
		const dlg = new frappe.ui.Dialog({ title: titre || __("Image"), size: "extra-large", fields: [{ fieldtype: "HTML", fieldname: "corps" }] });
		const $c = dlg.fields_dict.corps.$wrapper;
		$c.html(`<div style="display:flex;gap:14px;flex-wrap:wrap;align-items:flex-start">
			<div style="flex:1 1 480px;min-width:0;text-align:center">
				<canvas data-role="toile" style="max-width:100%;max-height:62vh;cursor:crosshair;${damier};border:1px solid #e5e7eb;border-radius:8px"></canvas>
				<div class="text-muted small" style="margin-top:4px">${__("Cliquez sur l'image pour prendre la couleur de ce point.")} <a href="${esc(url)}" target="_blank">↗ ${__("ouvrir le fichier")}</a></div>
			</div>
			<div style="flex:0 1 250px;min-width:220px">
				<div class="small text-muted">${__("Survol")}</div>
				<div style="display:flex;gap:8px;align-items:center;margin-bottom:10px"><span data-role="survol" class="se-pastille" style="width:28px;height:28px;cursor:default"></span><code data-role="survol-hex">—</code></div>
				<div class="small text-muted">${__("Couleur prise")}</div>
				<div style="display:flex;gap:8px;align-items:center"><span data-role="prise" class="se-pastille" style="width:44px;height:44px;cursor:default"></span><code data-role="prise-hex" style="font-size:15px">—</code></div>
				<div class="se-btns" style="margin-top:10px;flex-direction:column;align-items:stretch" data-role="actions">
					<button class="btn btn-sm btn-primary" data-geste="palette" disabled>＋ ${__("Ajouter à la palette du design")}</button>
					<button class="btn btn-sm btn-default" data-geste="fond" disabled>${__("Utiliser comme couleur de fond")}</button>
					<button class="btn btn-sm btn-default" data-geste="logo" disabled>🎨 ${__("Colorer le logo avec")}</button>
					<button class="btn btn-sm btn-default" data-geste="copier" disabled>📋 ${__("Copier le code")}</button>
					${window.EyeDropper ? `<button class="btn btn-sm btn-default" data-geste="ecran" title="${__("Prendre une couleur n'importe où à l'écran")}">💧 ${__("Pipette sur tout l'écran")}</button>` : ""}
				</div>
				<div class="small text-muted" style="margin-top:12px">${__("Couleurs principales de l'image")}</div>
				<div data-role="dominantes" style="display:flex;gap:6px;flex-wrap:wrap;margin-top:4px"></div>
			</div></div>`);
		const toile = $c.find('[data-role="toile"]')[0], ctx = toile.getContext("2d", { willReadFrequently: true });
		const choisir = (c) => {
			choisie = c;
			$c.find('[data-role="prise"]').css("background", c);
			$c.find('[data-role="prise-hex"]').text(c);
			$c.find("[data-geste]").prop("disabled", false);
		};
		const lire = (e, rayon) => {
			const r = toile.getBoundingClientRect();
			const x = Math.floor((e.clientX - r.left) * toile.width / r.width), y = Math.floor((e.clientY - r.top) * toile.height / r.height);
			const x0 = Math.max(0, x - rayon), y0 = Math.max(0, y - rayon);
			const d = ctx.getImageData(x0, y0, Math.min(toile.width - x0, 2 * rayon + 1), Math.min(toile.height - y0, 2 * rayon + 1)).data;
			let n = 0, s = [0, 0, 0];
			for (let i = 0; i < d.length; i += 4) if (d[i + 3] > 20) { s[0] += d[i]; s[1] += d[i + 1]; s[2] += d[i + 2]; n++; }
			return n ? hex(...s.map((v) => Math.round(v / n))) : null;      // moyenne 3×3 : un pixel isolé ne trompe pas
		};
		const img = new Image();
		img.onload = () => {
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
		};
		img.onerror = () => $c.find('[data-role="dominantes"]').html(`<span class="text-danger small">${__("Image illisible.")}</span>`);
		img.src = url;
		$(toile).on("mousemove", (e) => { const c = lire(e, 0); if (c) { $c.find('[data-role="survol"]').css("background", c); $c.find('[data-role="survol-hex"]').text(c); } });
		$(toile).on("click", (e) => { const c = lire(e, 1); if (c) choisir(c); });
		$c.find('[data-geste="palette"]').on("click", () => choisie && this.ajouter_a_la_palette(choisie));
		$c.find('[data-geste="fond"]').on("click", () => { if (!choisie) return; this.modifier({ couleur_fond: choisie }, true); frappe.show_alert({ message: __("Couleur de fond : {0}. Recomposez le plan (étape 4).", [choisie]), indicator: "green" }); });
		$c.find('[data-geste="logo"]').on("click", () => { if (!choisie) return; dlg.hide(); this.atelier_couleur(choisie); });
		$c.find('[data-geste="copier"]').on("click", () => choisie && frappe.utils.copy_to_clipboard(choisie));
		$c.find('[data-geste="ecran"]').on("click", async () => {
			try { const r = await new window.EyeDropper().open(); if (r && r.sRGBHex) choisir(r.sRGBHex.toLowerCase()); } catch (e) { /* annulé */ }
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
					<p class="text-muted small" style="margin-top:6px;text-align:center">${__("Rien ne change tant que vous n'avez pas cliqué « Utiliser comme logo ». Le fichier reste aussi dans l'onglet Images.")}</p>`);
				dlg.fields_dict.resultat.$wrapper.find('[data-role="adopter-couleur"]').on("click", async () => {
					const r2 = await frappe.call({ method: "aquaworld_ia.emballage.studio.adopter_image", args: { design: this.nom, champ: "logo", url: c.candidat }, freeze: true });
					dlg.hide(); this.data = r2.message; this.d = this.data.doc; this._lire_mep(); this.rendre();
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
							res.hide(); this.data = r2.message; this.d = this.data.doc; this._lire_mep(); this.rendre();
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
					dlg.hide(); this.data = r2.message; this.d = this.data.doc; this._lire_mep(); this.rendre();
					frappe.show_alert({ message: b.remplace, indicator: "green" });
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

	_esc(v) { return frappe.utils.escape_html(String(v == null ? "" : v)); }
	static get CHAMPS_DIMS() { return { L: "longueur_mm", H: "hauteur_mm", P: "profondeur_mm", R: "repli_mm" }; }
	// Les champs que la bibliothèque sait remplir (mêmes catégories que studio.CHAMPS_BIBLIOTHEQUE).
	static get BIBLIO() {
		return {
			logo: { categories: ["Logo"], garder: __("Garder ce logo en bibliothèque"), liste: __("Variantes de logo"), ratio: "3 / 2", remplace: __("Logo remplacé.") },
			image_fond: { categories: ["Fond", "Motif"], garder: __("Garder ce fond en bibliothèque"), liste: __("Fonds et motifs"), ratio: "4 / 3", remplace: __("Fond remplacé : recomposez le plan.") },
			photo_produit: { categories: ["Photo produit"], garder: __("Garder cette photo en bibliothèque"), liste: __("Photos du produit"), ratio: "1 / 1", remplace: __("Photo remplacée : recomposez le plan.") },
		};
	}
	_msg(e) {
		const m = (e && (e.message || (e._server_messages && JSON.parse(e._server_messages)[0]))) || e;
		try { return typeof m === "string" ? (JSON.parse(m).message || m) : JSON.stringify(m); } catch (_x) { return String(m); }
	}
}

// Éditeur des caractéristiques ligne par ligne (demande utilisateur 24/09/2026 : « plusieurs tailles
// ligne par ligne, italique ou gras, choisir la police »). Il lit et écrit le préfixe de
// emballage/mise_en_forme.py — « {14pt, gras, italique, sans puce, police: Montserrat} Débit » — :
// le texte enregistré reste lisible et se modifie aussi à la main (« Texte brut »).
class EditeurLignes {
	// opts : polices [{famille, styles}], bloc {police, taille}, bloc_modifiable, rtl, puces (défaut vrai),
	// auto_intertitres (lignes en capitales = intertitres, comme au rendu du texte brut), on_change(texte),
	// on_bloc({police, taille}), on_ajouter_police(apres(nom)).
	constructor($parent, texte, opts) {
		this.$p = $parent;
		this.o = Object.assign({ puces: true, rtl: false, bloc: {}, polices: [], auto_intertitres: true }, opts || {});
		this.lignes = String(texte || "").split("\n").map((l) => EditeurLignes.analyser(l));
		this.cur = 0;
		this.brut = false;
		this.rendre();
	}

	// ─── syntaxe (miroir de mise_en_forme.analyser / ecrire) ─────────────────────
	static analyser(ligne) {
		ligne = ligne || "";
		const m = ligne.match(/^\s*\{([^{}]*)\}[ \t]?([\s\S]*)$/);
		if (!m) return { style: null, texte: ligne };
		const style = {};
		for (let j of m[1].replace(/(\d),(\d)/g, "$1.$2").split(",")) {
			j = j.trim();
			const bas = j.toLowerCase(), t = bas.match(/^(\d{1,2}(?:\.\d{1,2})?)\s*pt$/), p = j.match(/^police\s*[:=]\s*(.+)$/i);
			if (!bas || bas === "normal") continue;
			if (t) {
				const v = parseFloat(t[1]);
				if (v < 4 || v > 72) return { style: null, texte: ligne };
				style.taille = v;
			} else if (["gras", "bold"].includes(bas)) style.gras = true;
			else if (["italique", "italic"].includes(bas)) style.italique = true;
			else if (["sans puce", "no bullet"].includes(bas)) style.puce = false;
			else if (["puce", "bullet"].includes(bas)) style.puce = true;
			else if (p && /^[\p{L}\p{N}_][\p{L}\p{N}_ .\-]{0,60}$/u.test(p[1].trim())) style.police = p[1].trim();
			else return { style: null, texte: ligne };
		}
		return { style, texte: m[2].trim() };
	}

	static ecrire(style, texte) {
		texte = String(texte || "");
		// Une ligne vide ne garde pas sa mise en forme : elle compterait comme une caractéristique.
		if (!style || !texte.trim()) return texte;
		const j = [];
		if (style.taille) j.push(`${style.taille}pt`);
		if (style.gras) j.push("gras");
		if (style.italique) j.push("italique");
		if (style.puce === false) j.push("sans puce");
		else if (style.puce === true) j.push("puce");
		if (style.police) j.push(`police: ${style.police}`);
		return `{${j.join(", ") || "normal"}} ${texte.trim()}`;
	}

	static intertitre(texte) {
		const t = String(texte || "").trim(), lettres = [...t].filter((c) => /\p{L}/u.test(c));
		return (lettres.length >= 3 && lettres.every((c) => c === c.toUpperCase() && c !== c.toLowerCase())) || t.endsWith(":");
	}

	static manques(p) {
		const s = p.styles || {}, m = [];
		if (!s.gras) m.push(__("sans gras"));
		if (!s.italique) m.push(__("sans italique"));
		return m.length ? ` (${m.join(", ")})` : "";
	}

	valeur() { return this.lignes.map((l) => EditeurLignes.ecrire(l.style, l.texte)).join("\n"); }

	// Le style qui s'imprimera : le préfixe, sinon celui d'un intertitre automatique.
	effectif(l) {
		if (l.style) return l.style;
		return this.o.auto_intertitres && EditeurLignes.intertitre(l.texte) ? { gras: true, puce: false } : {};
	}
	puce(l) { const s = this.effectif(l); return "puce" in s ? s.puce : this.o.puces; }

	// Un style égal au style implicite de la ligne n'a pas besoin de préfixe.
	normaliser(s, texte) {
		const n = {};
		if (+s.taille) n.taille = +s.taille;
		if (s.gras) n.gras = true;
		if (s.italique) n.italique = true;
		if (s.puce === !this.o.puces) n.puce = s.puce;
		if (s.police) n.police = s.police;
		const impl = this.o.auto_intertitres && EditeurLignes.intertitre(texte) ? { gras: true, puce: false } : {};
		const cle = (x) => JSON.stringify(Object.keys(x).sort().map((k) => [k, x[k]]));
		return cle(n) === cle(impl) ? null : n;
	}

	// ─── rendu ──────────────────────────────────────────────────────────────────
	rendre() {
		const o = this.o, esc = (v) => frappe.utils.escape_html(String(v == null ? "" : v));
		const tailles = [6, 7, 8, 8.5, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 32, 36];
		const opt_tailles = (vide) => `<option value="">${vide}</option>` + tailles.map((t) => `<option value="${t}">${String(t).replace(".", ",")} pt</option>`).join("");
		const polices = (o.polices || []).map((p) => `<option value="${esc(p.famille)}">${esc(p.famille)}${esc(EditeurLignes.manques(p))}</option>`).join("");
		const ajout = o.on_ajouter_police ? `<option value="+">＋ ${__("Ajouter une police…")}</option>` : "";
		this.$p.html(`<div class="se-ed${o.rtl ? " rtl" : ""}">
			${o.bloc_modifiable ? `<div class="se-ed-bloc"><span>${__("Tout le bloc")}</span>
				<select data-bloc="police" title="${__("Police de toutes les lignes ; une ligne peut choisir la sienne")}"><option value="">${__("Noto Sans (par défaut)")}</option>${polices}${ajout}</select>
				<select data-bloc="taille" title="${__("Taille de toutes les lignes, en points")}">${opt_tailles(__("8,5 pt (auto)"))}</select></div>` : ""}
			<div class="se-ed-barre">
				<button type="button" class="b" data-b="gras" title="${__("Gras (Ctrl+B)")}"><b>G</b></button>
				<button type="button" class="b" data-b="italique" title="${__("Italique (Ctrl+I)")}"><i>I</i></button>
				<button type="button" class="b" data-b="puce" title="${__("Puce")}">•</button>
				<select data-b="taille" title="${__("Taille de cette ligne, en points")}">${opt_tailles(__("Taille"))}</select>
				<select data-b="police" ${o.rtl ? "disabled" : ""} title="${o.rtl ? __("Cette langue garde sa police") : __("Police de cette ligne")}"><option value="">${__("Police du bloc")}</option>${polices}${ajout}</select>
				<button type="button" class="b" data-b="effacer" title="${__("Retirer la mise en forme de cette ligne")}">⌫</button>
			</div>
			<div class="se-ed-lignes"></div>
			<textarea class="se-ed-brut" style="display:none" spellcheck="false"></textarea>
			<div class="se-ed-pied"><a href="#" data-b="brut">${__("Texte brut")}</a><span>${__("Entrée : nouvelle ligne · Ctrl+B, Ctrl+I")}</span></div>
		</div>`);
		this.choisir(this.$p.find('[data-bloc="police"]'), (o.bloc || {}).police || "");
		this.choisir(this.$p.find('[data-bloc="taille"]'), +(o.bloc || {}).taille ? String(+o.bloc.taille) : "");
		this.lier();
		this.rendre_lignes();
	}

	rendre_lignes(focus) {
		const $l = this.$p.find(".se-ed-lignes").empty();
		this.lignes.forEach((l, i) => {
			const $r = $(`<div class="se-ed-l"><span class="p"></span><input type="text" spellcheck="true" ${this.o.rtl ? 'dir="rtl"' : ""}></div>`);
			$r.find("input").val(l.texte);
			$l.append($r);
			this.styler(i, $r);
		});
		this.lier_lignes();
		this.maj_barre();
		if (focus) this.focus(focus.i, focus.pos);
	}

	styler(i, $r) {
		$r = $r || this.$p.find(".se-ed-l").eq(i);
		const l = this.lignes[i], s = this.effectif(l), b = this.o.bloc || {};
		const pt = s.taille || +b.taille || 8.5;
		const police = (!this.o.rtl && (s.police || b.police)) || "Noto Sans";
		$r.find("input").css({
			"font-family": `"AQIA ${police}", "AQIA Noto Sans", sans-serif`, "font-weight": s.gras ? 700 : 400,
			"font-style": s.italique ? "italic" : "normal", "font-size": `${Math.max(11, Math.min(28, pt * 1.55))}px`,
		});
		$r.find(".p").text(this.puce(l) && String(l.texte || "").trim() ? "•" : "");   // une ligne vide ne s'imprime pas
		$r.toggleClass("cur", i === this.cur).toggleClass("explicite", !!l.style);
	}

	maj_barre() {
		const l = this.lignes[this.cur] || { style: null, texte: "" }, s = this.effectif(l), $b = this.$p.find(".se-ed-barre");
		$b.find('[data-b="gras"]').toggleClass("on", !!s.gras);
		$b.find('[data-b="italique"]').toggleClass("on", !!s.italique);
		$b.find('[data-b="puce"]').toggleClass("on", this.puce(l));
		$b.find('[data-b="effacer"]').prop("disabled", !l.style);
		this.choisir($b.find('select[data-b="taille"]'), s.taille ? String(s.taille) : "");
		this.choisir($b.find('select[data-b="police"]'), s.police || "");
	}

	// Sélectionne une valeur, en l'ajoutant à la liste si elle n'y est pas (taille tapée à la main,
	// police supprimée depuis).
	choisir($sel, val) {
		if (!$sel.length) return;
		if (val && !$sel.find("option").filter((_i, op) => op.value === val).length) {
			$sel.find("option").first().after($("<option>").val(val).text(val));
		}
		$sel.val(val);
	}

	focus(i, pos) {
		const inp = this.$p.find(".se-ed-l input").get(i);
		if (!inp) return;
		inp.focus();
		const p = Math.min(pos == null ? inp.value.length : pos, inp.value.length);
		inp.setSelectionRange(p, p);
	}

	change() { if (this.o.on_change) this.o.on_change(this.valeur()); }

	// ─── actions ────────────────────────────────────────────────────────────────
	appliquer(modif) {
		const l = this.lignes[this.cur];
		if (!l) return;
		const s = Object.assign({}, this.effectif(l));
		modif(s, l);
		l.style = this.normaliser(s, l.texte);
		this.styler(this.cur);
		this.maj_barre();
		this.change();
	}

	lier() {
		const $e = this.$p.find(".se-ed");
		// mousedown sans défaut : la ligne en cours garde le focus (et son curseur) pendant le clic.
		$e.find(".se-ed-barre .b").on("mousedown", (e) => e.preventDefault()).on("click", (e) => {
			const b = $(e.currentTarget).attr("data-b");
			if (b === "effacer") {
				const l = this.lignes[this.cur];
				if (l) { l.style = null; this.styler(this.cur); this.maj_barre(); this.change(); }
			} else if (b === "puce") this.appliquer((s, l) => { s.puce = !this.puce(l); });
			else this.appliquer((s) => { s[b] = !s[b]; });
		});
		$e.find('.se-ed-barre select[data-b="taille"]').on("change", (e) => {
			const v = $(e.currentTarget).val();
			this.appliquer((s) => { s.taille = v ? +v : 0; });
			this.focus(this.cur);
		});
		$e.find('.se-ed-barre select[data-b="police"]').on("change", (e) => {
			const v = $(e.currentTarget).val();
			if (v === "+") {
				this.maj_barre();
				this.o.on_ajouter_police((nom, polices) => { this.o.polices = polices; this.rendre(); this.appliquer((s) => { s.police = nom; }); });
				return;
			}
			this.appliquer((s) => { s.police = v; });
			this.focus(this.cur);
		});
		$e.find(".se-ed-bloc select").on("change", (e) => {
			const $s = $(e.currentTarget), quoi = $s.attr("data-bloc"), v = $s.val();
			if (v === "+") {
				this.choisir($s, (this.o.bloc || {}).police || "");
				this.o.on_ajouter_police((nom, polices) => { this.o.polices = polices; this.o.bloc = Object.assign({}, this.o.bloc, { police: nom }); this.rendre(); this.o.on_bloc(this.o.bloc); });
				return;
			}
			this.o.bloc = Object.assign({}, this.o.bloc, { [quoi]: quoi === "taille" ? +v || 0 : v });
			this.rendre_lignes();
			if (this.o.on_bloc) this.o.on_bloc(this.o.bloc);
		});
		$e.find('[data-b="brut"]').on("click", (e) => { e.preventDefault(); this.basculer_brut(); });
		$e.find(".se-ed-brut").on("input", (e) => {
			this.lignes = $(e.currentTarget).val().split("\n").map((l) => EditeurLignes.analyser(l));
			this.change();
		});
		// Un clic sous la dernière ligne y place le curseur.
		$e.find(".se-ed-lignes").on("mousedown", (e) => {
			if (e.target === e.currentTarget) { e.preventDefault(); this.focus(this.lignes.length - 1); }
		});
	}

	lier_lignes() {
		const self = this;
		this.$p.find(".se-ed-l input").each(function (i) {
			$(this).on("focus", () => {
				self.cur = i;
				self.$p.find(".se-ed-l").removeClass("cur").eq(i).addClass("cur");
				self.maj_barre();
			}).on("input", () => {
				self.lignes[i].texte = this.value;
				self.styler(i);
				self.maj_barre();
				self.change();
			}).on("keydown", (e) => self.touche(e, i, this))
				.on("paste", (e) => self.coller(e, i, this));
		});
	}

	touche(e, i, input) {
		const debut = input.selectionStart, fin = input.selectionEnd, l = this.lignes[i];
		if ((e.ctrlKey || e.metaKey) && ["b", "i"].includes(e.key.toLowerCase())) {
			e.preventDefault();
			const prop = e.key.toLowerCase() === "b" ? "gras" : "italique";
			this.appliquer((s) => { s[prop] = !s[prop]; });
		} else if (e.key === "Enter") {
			e.preventDefault();
			const apres = l.texte.slice(fin);
			l.texte = l.texte.slice(0, debut);
			// Couper une ligne garde sa mise en forme aux deux morceaux ; une nouvelle ligne après un
			// intertitre (gras sans puce) repart en ligne ordinaire.
			const titre = l.style && l.style.gras && l.style.puce === false;
			const style = l.style && (apres || !titre) ? Object.assign({}, l.style) : null;
			this.lignes.splice(i + 1, 0, { style, texte: apres });
			this.cur = i + 1;
			this.rendre_lignes({ i: i + 1, pos: 0 });
			this.change();
		} else if (e.key === "Backspace" && debut === 0 && fin === 0 && i > 0) {
			e.preventDefault();
			const prec = this.lignes[i - 1], pos = prec.texte.length;
			prec.texte += l.texte;
			this.lignes.splice(i, 1);
			this.cur = i - 1;
			this.rendre_lignes({ i: i - 1, pos });
			this.change();
		} else if (e.key === "Delete" && debut === input.value.length && fin === debut && i < this.lignes.length - 1) {
			e.preventDefault();
			const pos = l.texte.length;
			l.texte += this.lignes[i + 1].texte;
			this.lignes.splice(i + 1, 1);
			this.rendre_lignes({ i, pos });
			this.change();
		} else if (e.key === "ArrowUp" && i > 0) {
			e.preventDefault();
			this.focus(i - 1, debut);
		} else if (e.key === "ArrowDown" && i < this.lignes.length - 1) {
			e.preventDefault();
			this.focus(i + 1, debut);
		}
	}

	// Coller plusieurs lignes les répartit, chacune avec son éventuel préfixe.
	coller(e, i, input) {
		const txt = ((e.originalEvent || e).clipboardData || window.clipboardData).getData("text");
		if (!txt || !txt.includes("\n")) return;
		e.preventDefault();
		const l = this.lignes[i], avant = l.texte.slice(0, input.selectionStart), apres = l.texte.slice(input.selectionEnd);
		const morceaux = txt.replace(/\r/g, "").split("\n").map((x) => EditeurLignes.analyser(x));
		l.texte = avant + morceaux[0].texte;
		if (morceaux[0].style) l.style = morceaux[0].style;
		const suite = morceaux.slice(1), dernier = suite[suite.length - 1], pos = dernier.texte.length;
		dernier.texte += apres;
		this.lignes.splice(i + 1, 0, ...suite);
		this.cur = i + suite.length;
		this.rendre_lignes({ i: this.cur, pos });
		this.change();
	}

	basculer_brut() {
		this.brut = !this.brut;
		const $t = this.$p.find(".se-ed-brut");
		this.$p.find(".se-ed-lignes, .se-ed-barre").toggle(!this.brut);
		$t.toggle(this.brut);
		this.$p.find('[data-b="brut"]').text(this.brut ? __("Lignes mises en forme") : __("Texte brut"));
		if (this.brut) { $t.val(this.valeur()).trigger("focus"); return; }
		if (!this.lignes.length) this.lignes = [{ style: null, texte: "" }];
		this.cur = Math.min(this.cur, this.lignes.length - 1);
		this.rendre_lignes();
	}
}

// Dupliquer un design (studio et fiche) : tout ce qui a été saisi, dessiné et généré suit, sauf le plan
// et les aperçus, à recomposer.
function aqia_dupliquer_design(d, apres) {
	const dlg = new frappe.ui.Dialog({ title: __("Dupliquer {0}", [d.name]),
		fields: [
			{ fieldtype: "Link", options: "Item", fieldname: "article", label: __("Article"), default: d.article, reqd: 1,
			  description: __("Un autre article : son nom, sa photo et son code-barres remplacent ceux de l'original.") },
			{ fieldtype: "HTML", options: `<p class="text-muted small">${__("La copie reprend la forme, les dimensions, les textes et leur mise en forme, les langues, les pictogrammes, le fond, la mise en page dessinée et les variantes IA déjà générées (rien n'est refacturé). Le plan à plat et les aperçus sont à recomposer.")}</p>` },
		],
		primary_action_label: __("Dupliquer"),
		primary_action: async (v) => {
			let r;
			try {
				r = await frappe.call({ method: "aquaworld_ia.emballage.studio.dupliquer", args: { design: d.name, article: v.article }, freeze: true, freeze_message: __("Copie du design…") });
			} catch (e) { return; }
			dlg.hide();
			frappe.show_alert({ message: __("Copie créée : {0}. Recomposez le plan à plat.", [r.message.name]), indicator: "green" });
			apres(r.message.name);
		} });
	dlg.show();
}
