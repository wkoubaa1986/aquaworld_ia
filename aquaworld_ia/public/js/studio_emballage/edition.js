// Responsabilité : edition du studio emballage.
class StudioEdition {
	monter_editeur() {
		const d = this.d;
		this.injecter_polices();
		this.editeur = new EditeurLignes(this.$root.find('[data-role="editeur-car"]'), d.caracteristiques || "", {
			polices: this.data.polices || [], bloc: { police: d.police_caracteristiques || "", taille: +d.taille_caracteristiques || 0 },
			bloc_modifiable: true,
			on_change: (val) => this.sauvegarde_differee(d.name)("caracteristiques", val),
			on_bloc: (b) => this.modifier({ police_caracteristiques: b.police || "", taille_caracteristiques: b.taille || 0 }, false),
			on_ajouter_police: (apres) => this.ajouter_police(apres),
		});
		this.rendre_avert_lignes();
	}

	rendre_avert_lignes() {
		const code = Object.keys(this.data.textes_imprimes || {})[0] || "fr";
		this.$root.find('[data-role="avert-lignes"]').html(`<p class="small text-muted">${__("Textes imprimés en {0}. Pour les autres langues et l’accroche : « Textes par langue ».", [this._esc(code.toUpperCase())])}</p>`);
	}

	// Les polices dans le navigateur (@font-face), pour que l'éditeur montre chaque ligne dans la sienne.
	injecter_polices() {
		const STYLES = { regulier: [400, "normal"], gras: [700, "normal"], italique: [400, "italic"], gras_italique: [700, "italic"] };
		const css = [...(this.data.polices || []), ...(this.data.polices_apercu || [])].map((p) => Object.entries(p.styles || {}).map(([cle, url]) => {
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
		const logo_selectionne = fe?.zones?.[this.zone_sel];
		const TYPES = ["logo", "nom", "accroche", "caracteristiques", "avertissements", "contact", "texte_libre", "pictos", "code_barres", "qr", "photo"];
		const LIBS = { logo: __("Logo"), nom: __("Nom du produit"), accroche: __("Accroche"), caracteristiques: __("Caractéristiques"), avertissements: __("Avertissements"), contact: __("Contact"), texte_libre: __("Texte libre (sans IA)"), pictos: __("Pictogrammes / certifications"), code_barres: __("Code-barres"), qr: __("QR code"), photo: __("Photo produit") };
		const outils = fe ? `<div class="se-outils" style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;padding:6px 8px;margin-bottom:6px;border:1px solid #bfdbfe;background:#eff6ff;border-radius:8px;font-size:12.5px">
				<b>${this._esc(fe.libelle)}</b> <span class="text-muted">${__("épinglée")}</span>
				<span style="margin-left:8px">${__("Ajouter :")}</span>
				<select class="form-control" data-role="type-zone-plan" style="width:auto;display:inline-block">${TYPES.map((t) => `<option value="${t}">${LIBS[t]}</option>`).join("")}${this._options_tampons()}</select>
				<button class="btn btn-xs btn-primary" data-role="ajouter-zone-plan">＋ ${__("Ajouter la zone")}</button>
				${fe.personnalisee ? `<button class="btn btn-xs btn-default" data-role="reinit-face-plan">${__("Revenir à la maquette automatique")}</button>` : ""}
				<button class="btn btn-xs btn-default" data-role="liberer-face-plan">${__("Libérer")}</button>
				<div class="se-mode-deplacement" role="group" aria-label="${__("Déplacer à la souris")}"><span>${__("Déplacer :")}</span>
					${[["cadre", __("Le cadre")], ["contenu", __("Le contenu")]].map(([mode, libelle]) => `<button type="button" class="btn btn-xs ${(mode === "contenu") === !!this._deplacer_contenu ? "btn-primary" : "btn-default"}" data-mode-deplacement="${mode}" aria-pressed="${(mode === "contenu") === !!this._deplacer_contenu}">${libelle}</button>`).join("")}</div>
				${logo_selectionne?.zone === "logo" ? `<button class="btn btn-xs btn-default" data-role="logo-zone-ia" ${this.data.peut_ecrire && this.url_image_zone(logo_selectionne) ? "" : "disabled"}>✨ ${__("Retoucher ce logo par IA")}</button>` : ""}
				${logo_selectionne?.zone === "pictos" ? `<button class="btn btn-xs btn-primary" data-role="choisir-pictos-zone">${__("Choisir les pictogrammes de cette zone")}</button>` : ""}
				<div data-role="apercu-ajout" class="se-apercu-ajout"></div>
				<span class="text-muted" style="flex-basis:100%">${__("Glissez une zone pour la déplacer, tirez son coin pour l'agrandir, × pour la supprimer, cliquez-la pour ses réglages (cartouche, logo, pictogrammes).")}</span>
				${fe.copie_bloquee ? `<span class="text-muted" style="flex-basis:100%">${__("Cette facette a sa propre mise en page. « Revenir à la maquette automatique » réactive la copie de « {0} ».", [this._esc((infos[fe.copie_bloquee] || {}).libelle || fe.copie_bloquee)])}</span>` : ""}
			</div>` : "";
		$s.html(`<p class="text-muted small">${__("Feuille <b>{0} × {1} mm</b>, fond perdu inclus. Survolez une face, cliquez pour l'épingler.", [a.feuille.w, a.feuille.h])}</p>${pb}${outils}${a.svg}`);
		this.dessiner_contenus_plan($s);
		const $choix = $s.find('[data-role="type-zone-plan"]');
		if (this._type_ajout && [...($choix[0]?.options || [])].some(o => o.value === this._type_ajout)) $choix.val(this._type_ajout);
		$choix.on("change", () => {
			this._type_ajout = $choix.val(); this.rendre_apercu_ajout($s, this._type_ajout);
			this.$root.find('[data-role="type-zone"]').val(this._type_ajout);
		});
		if (fe) this.rendre_apercu_ajout($s, $choix.val());
		$s.find('[data-role="ajouter-zone-plan"]').on("click", () => this.ajouter_zone($s.find('[data-role="type-zone-plan"]').val()));
		$s.find('[data-role="logo-zone-ia"]').on("click", () => this.retoucher_logo_zone());
		$s.find('[data-role="choisir-pictos-zone"]').on("click", () => this.choisir_pictos_zone());
		$s.find("[data-mode-deplacement]").on("click", e => this.regler_mode_deplacement(e.currentTarget.dataset.modeDeplacement === "contenu"));
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
		$s.find(`[data-face-label="${face.code}"]`).hide();
		const NS = "http://www.w3.org/2000/svg";
		const W = svg.viewBox.baseVal.width, POIGNEE = Math.max(2.5, W / 90);
		const racine = document.createElementNS(NS, "g"); racine.setAttribute("class", "se-edit"); svg.appendChild(racine);
		let g = racine;
		const zones = (face.zones || []).map((z) => ({ zone: z.zone, x: z.x, y: z.y, w: z.w, h: z.h, rotation: this.angle_zone(z.rotation), zoom_image: this.zoom_image(z.zoom_image), centre_visuel: z.centre_visuel, apercu_texte: z.apercu_texte, apercu_elements: z.apercu_elements, apercu_message: z.apercu_message, libelle: z.libelle, style: z.style || null, logo: z.logo || null, pictos: z.pictos || null, typo: z.typo || null, texte: z.texte || "", code: z.code || null, auto: z.auto || 0 }));
		zones.forEach((z, i) => {
			z.decalage_contenu = this.decalage_contenu(face.zones[i]);
			z.pictos_mode = face.zones[i].pictos_mode; z.pictos_disposition = face.zones[i].pictos_disposition;
			z.pictos_images = face.zones[i].pictos_images;
			z.pictos_rotations = this.rotations_pictos(face.zones[i]);
			z._origine_apercu = {x: z.x, y: z.y, w: z.w, h: z.h};
		});
		const actualiser = [];
		const el = (tag, attrs) => { const n = document.createElementNS(NS, tag); Object.entries(attrs).forEach(([k, v]) => n.setAttribute(k, v)); g.appendChild(n); return n; };
		const design = this.nom;
		const sauver = () => {
			if (this.nom !== design) return;
			this.mep[face.code] = zones.map(z => this.zone_a_enregistrer(z));
			this.memoriser_apercu_zones(face, zones);
			return this.modifier({ mise_en_page: this.mep }, false, design);
		};
		const selectionner = () => {
			racine.querySelectorAll("[data-zone-cadre]").forEach(n => {
				const actif = Number(n.dataset.zoneCadre) === this.zone_sel;
				n.setAttribute("stroke", actif ? "#dc2626" : "#d97706"); n.setAttribute("stroke-width", actif ? W/350 : W/700);
			});
		};
		this.ordre_zones(zones).forEach(({z, i}) => {
			g = document.createElementNS(NS, "g"); g.setAttribute("class", "se-zone"); g.setAttribute("data-zone", i); racine.appendChild(g);
			const groupe = g;
			const fond = z.style && z.style.fond;
			const r = el("rect", { x: z.x, y: z.y, width: z.w, height: z.h, rx: fond ? (z.style.rayon || 0) : 0, fill: fond || "#f59e0b", "fill-opacity": fond ? "1" : "0.12",
				stroke: this.zone_sel === i ? "#dc2626" : "#d97706", "stroke-width": this.zone_sel === i ? W / 350 : W / 700, "data-zone-cadre": i, style: `cursor:${this._deplacer_contenu ? "grab" : "move"}` });
			const actualiser_contenu = this.dessiner_contenu_zone(el, z, i);
			actualiser[i] = actualiser_contenu;
			const t = el("text", { x: z.x + W / 400, y: z.y + Math.max(2, Math.min(z.w, z.h) / 4), "font-size": Math.max(2, Math.min(Math.min(z.w, z.h) / 4, W / 70)), fill: "#92400e", "font-family": "sans-serif", style: "pointer-events:none" });
			t.textContent = this.url_image_zone(z) ? (z.libelle || z.zone) + (z.rotation ? ` · ${z.rotation}°` : "") : "";
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
			const actualiser_cadre = () => {
				r.setAttribute("x", z.x); r.setAttribute("y", z.y); r.setAttribute("width", z.w); r.setAttribute("height", z.h);
				p.setAttribute("x", z.x + z.w - POIGNEE); p.setAttribute("y", z.y + z.h - POIGNEE);
				t.setAttribute("x", z.x + W / 400); t.setAttribute("y", z.y + Math.max(2, Math.min(z.w, z.h) / 4));
				x.setAttribute("x", z.x + z.w - POIGNEE * 0.9); x.setAttribute("y", z.y + POIGNEE * 1.1);
				actualiser_contenu();
			};
			this.installer_glissement_zone({svg, groupe, cadre: r, poignee: p, face, zones, z, indice: i, actualiser: actualiser_cadre, sauver, selectionner});
		});
		const choisi = racine.querySelector(`[data-zone="${this.zone_sel}"]`);
		if (choisi) racine.appendChild(choisi);
		this._zones_en_cours = { face, zones, sauver, actualiser };
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
		// Tout ajout ouvre ses réglages, y compris les contenus encore à renseigner.
		this.zone_sel = c.zones.length - 1;
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
		const garder = z => this.zone_a_enregistrer(z);
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

	face_info(f) {
		this.memoriser_panneau_proprietes();
		const $b = this.$root.find('[data-role="face"]');
		if (!f) {
			delete this.$root.find(".se-droite")[0].dataset.sectionsContexte;
			return $b.html(`<span class="text-muted">${__("Survolez une face du plan.")}</span>`);
		}
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
		if (chev.length) props += `<div class="bloc" data-section-propriete="verifications"><h6><span class="text-danger">⚠ ${__("Chevauchements ({0})", [chev.length])}</span></h6><div class="text-danger small">${__("Zones qui se chevauchent : {0}. Déplacez-les ou réduisez-les.", [this._esc(chev.join(" · "))])}</div></div>`;
		if (sel) {
			const disponible = this.contenu_zone_disponible(sel);
			if (sel.zone !== "pictos") props += `<div class="bloc se-contenu-zone" data-section-propriete="contenu"><h6>${this._esc(sel.libelle)}</h6>
				${disponible ? "" : `<p class="text-warning small">${this._esc(this.message_zone_vide(sel))}</p>`}
				<button class="btn btn-xs btn-primary" data-role="modifier-contenu-zone">${disponible ? __("Modifier le contenu") : __("Renseigner le contenu")}</button></div>`;
			if (sel.zone === "pictos") props += this.panneau_pictos_zone(sel, f);
			const u = f.utile || f, mm = (v) => (Math.round(v * 10) / 10).toString();
			props += `<div class="bloc se-position" data-section-propriete="position"><h6>${__("Position et dimensions")}</h6>
				<p class="text-muted small">${__("En mm, depuis le coin haut-gauche de la face.")}</p>
				<div class="se-position-grid">
					<label>X<input type="number" step="0.5" data-pos="x" value="${mm(sel.x - u.x)}"></label><label>Y<input type="number" step="0.5" data-pos="y" value="${mm(sel.y - u.y)}"></label>
					<label>${__("Largeur")}<input type="number" step="0.5" min="3" data-pos="w" value="${mm(sel.w)}"></label><label>${__("Hauteur")}<input type="number" step="0.5" min="3" data-pos="h" value="${mm(sel.h)}"></label>
					${["logo", "photo"].includes(sel.zone) ? `<label class="se-angle">${__("Rotation (°)")}<input type="number" step="1" min="0" max="359" data-pos="rotation" value="${this.angle_zone(sel.rotation)}"></label>` : ""}
				</div>
				${["logo", "photo"].includes(sel.zone) ? `<div class="se-btns"><button class="btn btn-xs btn-default" data-tourner="-90" title="${__("Quart de tour à gauche")}">↶ 90°</button><button class="btn btn-xs btn-default" data-tourner="90" title="${__("Quart de tour à droite")}">↷ 90°</button><button class="btn btn-xs btn-default" data-rotation-zero>${__("0°")}</button></div><p class="text-muted small">${__("Le visuel tourne dans son cadre. Les quarts de tour échangent largeur et hauteur si la face le permet.")}</p>` : ""}
				<div class="se-btns" style="margin-top:8px"><button class="btn btn-xs btn-primary" data-role="appliquer-pos">${__("Appliquer")}</button>
					<button class="btn btn-xs btn-default" data-role="centrer-h" title="${__("Centrer horizontalement sur la face")}">↔ ${__("Centrer")}</button>
					<button class="btn btn-xs btn-default" data-role="centrer-v" title="${__("Centrer verticalement sur la face")}">↕ ${__("Centrer")}</button>
					<button class="btn btn-xs btn-default" data-role="pleine-largeur" title="${__("Toute la largeur utile de la face")}">${__("Pleine largeur")}</button></div></div>`;
			const decalage = this.decalage_contenu(sel);
			props += `<div class="bloc se-decalage-contenu" data-section-propriete="decalage"><h6>${__("Contenu dans le cadre")}</h6>
				<div class="se-position-grid">
					<label>${__("Horizontal (mm)")}<input type="number" step="0.5" min="${-sel.w}" max="${sel.w}" data-decalage="x" value="${decalage.x}"></label>
					<label>${__("Vertical (mm)")}<input type="number" step="0.5" min="${-sel.h}" max="${sel.h}" data-decalage="y" value="${decalage.y}"></label>
				</div><div class="se-btns" style="margin-top:8px">
					${[["x", -1, "←", __("Gauche : 1 mm")], ["x", 1, "→", __("Droite : 1 mm")], ["y", -1, "↑", __("Haut : 1 mm")], ["y", 1, "↓", __("Bas : 1 mm")]].map(([axe, pas, fleche, titre]) => `<button class="btn btn-xs btn-default" data-decaler-axe="${axe}" data-decaler-pas="${pas}" title="${titre}" aria-label="${titre}">${fleche}</button>`).join("")}
					<button class="btn btn-xs btn-primary" data-decalage-appliquer>${__("Appliquer")}</button>
					<button class="btn btn-xs btn-default" data-decalage-zero>${__("Réinitialiser")}</button>
				</div><label class="se-check" style="margin-top:8px"><input type="checkbox" data-glisser-contenu ${this._deplacer_contenu ? "checked" : ""}> ${__("Glisser le contenu à la souris")}</label>
				<p class="text-muted small">${__("Le cadre reste fixe. Positif : droite / bas ; négatif : gauche / haut. Ce qui dépasse est coupé. Alt + glisser fonctionne aussi.")}</p></div>`;
			if (["logo", "photo"].includes(sel.zone)) props += `<div class="bloc se-zoom-image" data-section-propriete="zoom"><h6>${__("Zoom et centrage")}</h6>
				<label for="se-zoom-image">${__("Zoom du visuel")} <span data-zoom-valeur>${Math.round(this.zoom_image(sel.zoom_image) * 100)} %</span></label>
				<input id="se-zoom-image" type="range" min="25" max="400" step="5" value="${Math.round(this.zoom_image(sel.zoom_image) * 100)}" data-zoom-image>
				<button class="btn btn-xs btn-default" data-zoom-ajuster>${__("Ajuster (100 %)")}</button>
				<p class="text-muted small">${__("Agrandit ou réduit l’image à l’intérieur du cadre, sans déplacer ses bords. Ce qui dépasse est coupé.")}</p>
				${sel.zone === "logo" ? `<div class="se-btns" style="margin-top:10px"><button class="btn btn-xs btn-primary" data-centrer-visible>${__("Centrer le logo visible")}</button>
					${this.centre_image(sel, this.url_image_zone(sel)) ? `<button class="btn btn-xs btn-default" data-centrer-fichier>${__("Centrage du fichier entier")}</button>` : ""}</div>
					<p class="text-muted small">${__("Détecte l’écriture et le symbole, ignore les marges blanches ou transparentes, puis les centre sur la facette. Gratuit.")}</p>` : ""}</div>`;
		}
		if (sel && (TEXTES.includes(sel.zone) || sel.zone === "texte_libre")) {
			props += this._panneau_texte(sel);
		} else if (sel && sel.zone === "logo") {
			props += `<div class="bloc" data-section-propriete="logo" style="margin-top:8px;padding:8px 10px;background:#f8fafc"><h6>${__("Logo de cette zone")}</h6>
				<div class="se-fichier"><img src="${this._esc(sel.logo || this.d.logo || this.data.visuels?.logo || "")}" alt="">
					<button class="btn btn-xs btn-primary" data-role="logo-variante">${__("Choisir un autre logo")}</button>
					<button class="btn btn-xs btn-default" data-role="logo-zone-ia" ${this.data.peut_ecrire && this.url_image_zone(sel) ? "" : "disabled"}>✨ ${__("Retoucher par IA")}</button>
					${sel.logo ? `<button class="btn btn-xs btn-default" data-role="logo-commun">${__("Logo du design")}</button>` : ""}</div>
				<div class="text-muted small" style="margin-top:6px">${sel.logo ? __("Cette zone utilise son propre logo.") : __("Cette zone utilise le logo du design (étape 2).")} ${__("Ajoutez plusieurs zones Logo pour placer plusieurs logos sur la même face.")}</div></div>`;
		} else if (sel && sel.zone === "code_barres") {
			const PORTE = [["", __("Automatique (selon « Code », étape 2)")], ["qr", __("QR code")], ["ean", __("EAN-13")]];
			const petit = sel.code === "qr" && Math.min(sel.w, sel.h) < 20;
			props += `<div class="bloc" data-section-propriete="code" style="margin-top:8px;padding:8px 10px;background:#f8fafc"><h6>${__("Contenu de cette zone")}</h6>
				<select class="form-control" data-prop="code_zone">${PORTE.map(([v, l]) => `<option value="${v}" ${(sel.code || "") === v ? "selected" : ""}>${l}</option>`).join("")}</select>
				<div class="se-btns" style="margin-top:8px"><button class="btn btn-xs btn-primary" data-role="appliquer-code">${__("Appliquer")}</button></div>
				${petit ? `<div class="text-danger small" style="margin-top:6px">⚠ ${__("Moins de 20 mm de côté : le scan devient incertain. Agrandissez la zone.")}</div>` : ""}
				<div class="text-muted small" style="margin-top:6px">${__("QR code : le QR, carré, au centre de la zone, dans la couleur choisie à l'étape 2. Dès qu'une zone QR code existe, les zones automatiques n'impriment plus de second QR.")}</div></div>`;
		}
		const types = ["logo", "nom", "accroche", "caracteristiques", "avertissements", "contact", "texte_libre", "pictos", "code_barres", "qr", "photo"];
		const libs = { logo: __("Logo"), nom: __("Nom du produit"), accroche: __("Accroche"), caracteristiques: __("Caractéristiques"), avertissements: __("Avertissements"), contact: __("Contact"), texte_libre: __("Texte libre (sans IA)"), pictos: __("Pictogrammes"), code_barres: __("Code-barres"), qr: __("QR code"), photo: __("Photo produit") };
		const source = f.copie_de && ((this.data.apercu || {}).faces || []).find((x) => x.code === f.copie_de);
		const bloquee = f.copie_bloquee && ((this.data.apercu || {}).faces || []).find((x) => x.code === f.copie_bloquee);
		$b.html(`<h6>${this._esc(f.libelle)} <span class="text-muted">${f.w.toFixed(0)} × ${f.h.toFixed(0)} mm</span>${f.personnalisee ? ` <span class="se-chip encours">${__("personnalisée")}</span>` : ""}${source ? ` <span class="se-chip" title="${__("Modifiez la face source : cette face la suit. Dessinez ici pour la rendre indépendante.")}">${__("copie de {0}", [this._esc(source.libelle)])}</span>` : ""}${bloquee ? ` <span class="se-chip" title="${__("Cette face a sa propre mise en page. « Revenir à la maquette automatique » réactive la copie.")}">${__("indépendante")}</span>` : ""}</h6>
			<div class="bloc" data-section-propriete="elements"><h6>${__("Éléments de la face")}</h6>${zones ? `<ul>${zones}</ul>` : `<span class="text-muted">${__("Aucun emplacement : renseignez logo, textes, pictogrammes ou code-barres.")}</span>`}</div>
			${props}
			${this.epinglee === f.code ? this._bloc_fond_face(f) : ""}
			${this.epinglee === f.code ? `
				<div class="bloc" data-section-propriete="gestion"><h6>${__("Ajouter et gérer les zones")}</h6>
				<div class="small" style="margin-top:8px">${__("Sur le plan : glissez une zone pour la déplacer, tirez son coin pour l'agrandir, × pour la supprimer, cliquez-la pour ses réglages (cartouche, logo).")}</div>
				<div class="se-ajout-zone"><select class="form-control" data-role="type-zone">${types.map((t) => `<option value="${t}">${libs[t]}</option>`).join("")}${this._options_tampons()}</select>
					<button class="btn btn-xs btn-default" data-role="ajouter-zone" style="white-space:nowrap">＋ ${__("Ajouter")}</button></div>
				${f.personnalisee ? `<button class="btn btn-xs btn-default" style="margin-top:6px" data-role="reinit-face">${__("Revenir à la maquette automatique")}</button>` : ""}
				<div class="text-muted small" style="margin-top:6px">${__("Cliquez à nouveau la face pour la libérer.")}</div></div>`
			: `<div class="text-muted small" style="margin-top:6px">${__("Cliquez la face pour modifier ses zones.")}</div>`}`);
		this.monter_sections_proprietes($b, f, sel);
		$b.find('[data-role="ajouter-zone"]').on("click", () => this.ajouter_zone($b.find('[data-role="type-zone"]').val()));
		const $choix = $b.find('[data-role="type-zone"]');
		if (this._type_ajout && [...($choix[0]?.options || [])].some(o => o.value === this._type_ajout)) $choix.val(this._type_ajout);
		$choix.on("change", () => this.$root.find('[data-role="type-zone-plan"]').val($choix.val()).trigger("change"));
		$b.find('[data-role="modifier-contenu-zone"]').on("click", () => this.ouvrir_contenu_zone(sel));
		$b.find('[data-role="choisir-pictos-zone"]').on("click", () => this.choisir_pictos_zone());
		$b.find("[data-picto-couleur]").on("click", e => this.atelier_picto(e.currentTarget.dataset.pictoCouleur));
		$b.find("[data-picto-original]").on("click", e => this.restaurer_picto(e.currentTarget.dataset.pictoOriginal));
		$b.find("[data-angle-picto]").on("input", e => e.currentTarget.setAttribute("data-saisie-position", "1"))
			.on("keydown", e => {
				if (e.key === "Enter") { e.preventDefault(); this.regler_rotation_picto(e.currentTarget.dataset.anglePicto, e.currentTarget.value); }
			});
		$b.find("[data-picto-appliquer-angle]").on("click", e => {
			const input = e.currentTarget.closest(".se-picto-variante").querySelector("[data-angle-picto]");
			this.regler_rotation_picto(input.dataset.anglePicto, input.value);
		});
		$b.find("[data-picto-tourner]").on("click", e => {
			const input = e.currentTarget.closest(".se-picto-variante").querySelector("[data-angle-picto]");
			const valeur = e.currentTarget.dataset.pictoTourner;
			this.regler_rotation_picto(input.dataset.anglePicto, valeur === "zero" ? 0 : Number(input.value) + Number(valeur));
		});
		$b.find('[data-role="liste-pictos-design"]').on("click", () => this.ouvrir_liste_pictos());
		$b.find("[data-pictos-disposition]").on("click", e => this.changer_disposition_pictos(e.currentTarget.dataset.pictosDisposition));
		$b.find("[data-zi]").on("click", (e) => { this.zone_sel = +$(e.currentTarget).attr("data-zi"); this.rendre_scene(); });
		const zone_courante = () => (this._zones_en_cours || {}).zones && this._zones_en_cours.zones[this.zone_sel];
		$b.find("[data-pos], [data-decalage]").on("input", e => e.currentTarget.setAttribute("data-saisie-position", "1"));
		const appliquer_decalage = (d) => {
			const z = zone_courante(); if (!z) return;
			$b.find("[data-decalage]").removeAttr("data-saisie-position");
			z.decalage_contenu = this.decalage_contenu({...z, decalage_contenu: d});
			this.afficher_decalage_contenu(z);
			this._zones_en_cours.actualiser[this.zone_sel]?.();
			return this._zones_en_cours.sauver();
		};
		const saisie_decalage = () => ({x: $b.find('[data-decalage="x"]').val(), y: $b.find('[data-decalage="y"]').val()});
		$b.find("[data-decalage-appliquer]").on("click", () => appliquer_decalage(saisie_decalage()));
		$b.find("[data-decalage]").on("keydown", e => { if (e.key === "Enter") { e.preventDefault(); appliquer_decalage(saisie_decalage()); } });
		$b.find("[data-decaler-axe]").on("click", e => {
			const z = zone_courante(); if (!z) return;
			const d = this.decalage_contenu({...z, decalage_contenu: saisie_decalage()});
			d[e.currentTarget.dataset.decalerAxe] += Number(e.currentTarget.dataset.decalerPas);
			appliquer_decalage(d);
		});
		$b.find("[data-decalage-zero]").on("click", () => appliquer_decalage({x: 0, y: 0}));
		$b.find("[data-glisser-contenu]").on("change", e => this.regler_mode_deplacement(e.currentTarget.checked));
		$b.find("[data-zoom-image]").on("input", e => {
			const z = zone_courante(); if (!z) return;
			z.zoom_image = this.zoom_image(Number(e.currentTarget.value) / 100);
			$b.find("[data-zoom-valeur]").text(`${Math.round(z.zoom_image * 100)} %`);
			this._zones_en_cours.actualiser[this.zone_sel]?.();
		}).on("change", () => this._zones_en_cours?.sauver());
		$b.find("[data-zoom-ajuster]").on("click", () => {
			const z = zone_courante(); if (!z) return;
			z.zoom_image = 1; this._zones_en_cours.sauver();
		});
		$b.find("[data-centrer-visible]").on("click", () => this.centrer_logo_visible());
		$b.find("[data-centrer-fichier]").on("click", () => {
			const z = zone_courante(); if (!z) return;
			delete z.centre_visuel; this._zones_en_cours.sauver();
		});
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
			$b.find("[data-pos]").removeAttr("data-saisie-position");
			const v = (k) => parseFloat($b.find(`[data-pos="${k}"]`).val());
			if (!isNaN(v("w"))) z.w = Math.max(3, v("w")); if (!isNaN(v("h"))) z.h = Math.max(3, v("h"));
			if (!isNaN(v("x"))) z.x = u.x + v("x"); if (!isNaN(v("y"))) z.y = u.y + v("y");
			if (["logo", "photo"].includes(z.zone)) z.rotation = this.angle_zone(v("rotation"));
			this._zones_en_cours.sauver();   // le serveur borne à la face
		});
		$b.find("[data-tourner]").on("click", e => this.tourner_zone(Number($(e.currentTarget).attr("data-tourner"))));
		$b.find("[data-rotation-zero]").on("click", () => { const z = zone_courante(); if (!z) return; z.rotation = 0; this._zones_en_cours.sauver(); });
		$b.find('[data-role="centrer-h"]').on("click", () => { const z = zone_courante(), u = utile(); if (!z || !u) return; z.x = u.x + (u.w - z.w) / 2; this._zones_en_cours.sauver(); });
		$b.find('[data-role="centrer-v"]').on("click", () => { const z = zone_courante(), u = utile(); if (!z || !u) return; z.y = u.y + (u.h - z.h) / 2; this._zones_en_cours.sauver(); });
		$b.find('[data-role="pleine-largeur"]').on("click", () => { const z = zone_courante(), u = utile(); if (!z || !u) return; z.x = u.x + 3; z.w = Math.max(3, u.w - 6); this._zones_en_cours.sauver(); });
		$b.find('[data-role="appliquer-code"]').on("click", () => { const z = zone_courante(); if (!z) return; z.code = $b.find('[data-prop="code_zone"]').val() || null; this._zones_en_cours.sauver(); });
		$b.find('[data-role="logo-variante"]').on("click", () => this.choisir_logo_zone());
		$b.find('[data-role="logo-zone-ia"]').on("click", () => this.retoucher_logo_zone());
		$b.find('[data-role="logo-commun"]').on("click", () => this.appliquer_logo_zone(f.code, this.zone_sel, null).catch(e => frappe.msgprint(this._msg(e))));
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

	zone_a_enregistrer(z) {
		const out = {zone: z.zone, x: z.x, y: z.y, w: z.w, h: z.h};
		for (const cle of ["style", "logo", "typo", "code", "centre_visuel"]) if (z[cle]) out[cle] = z[cle];
		if (Array.isArray(z.pictos) && z.pictos.length) out.pictos = [...z.pictos];
		if (z.zone === "pictos" && z.pictos_mode === "selection") { out.pictos_mode = "selection"; out.pictos ||= []; }
		if (z.zone === "pictos" && z.pictos_disposition === "vertical") out.pictos_disposition = "vertical";
		if (z.zone === "pictos" && z.pictos_images && Object.keys(z.pictos_images).length) out.pictos_images = {...z.pictos_images};
		const rotations = this.rotations_pictos(z);
		if (Object.keys(rotations).length) out.pictos_rotations = rotations;
		if (z.zone === "texte_libre") out.texte = z.texte || "";
		if (z.rotation) out.rotation = this.angle_zone(z.rotation);
		if (["logo", "photo"].includes(z.zone) && this.zoom_image(z.zoom_image) !== 1) out.zoom_image = this.zoom_image(z.zoom_image);
		if (z.decalage_contenu) out.decalage_contenu = this.decalage_contenu(z);
		return out;
	}

	angle_zone(angle) { return Number.isFinite(Number(angle)) ? ((Number(angle) % 360) + 360) % 360 : 0; }

	zoom_image(valeur) {
		return valeur == null || valeur === "" || !Number.isFinite(Number(valeur)) ? 1 : Math.round(Math.max(0.25, Math.min(4, Number(valeur))) * 1000) / 1000;
	}

	decalage_contenu(z) {
		const d = z.decalage_contenu || {}, out = {};
		for (const [axe, taille] of [["x", z.w], ["y", z.h]]) {
			const v = Number(d[axe]), limite = Math.max(0, Number(taille) || 0);
			out[axe] = Number.isFinite(v) ? Math.round(Math.max(-limite, Math.min(limite, v)) * 1000) / 1000 : 0;
		}
		return out;
	}

	afficher_decalage_contenu(z) {
		const d = this.decalage_contenu(z);
		for (const axe of ["x", "y"]) this.$root.find(`.se-droite [data-decalage="${axe}"]`).val(d[axe]);
	}

	url_image_zone(z) {
		return z.zone === "logo" ? (z.logo || this.d.logo || this.data.visuels?.logo) : z.zone === "photo" ? (this.d.photo_produit || this.data.visuels?.photo) : null;
	}

	centre_image(z, url) {
		const p = z.centre_visuel;
		return z.zone === "logo" && p && typeof p.source === "string" && p.source === url && [p.x, p.y].every(v => Number.isFinite(v) && v >= 0 && v <= 1) ? p : null;
	}

	cadre_image(z, largeur, hauteur, url) {
		const angle = this.angle_zone(z.rotation), a = angle * Math.PI / 180;
		const c = Math.abs(Math.cos(a)), s = Math.abs(Math.sin(a));
		const facteur = Math.min(z.w / (largeur * c + hauteur * s), z.h / (largeur * s + hauteur * c)) * this.zoom_image(z.zoom_image);
		const d = this.decalage_contenu(z);
		const w = largeur * facteur, h = hauteur * facteur, cx = z.x + z.w / 2 + d.x, cy = z.y + z.h / 2 + d.y;
		const centre = this.centre_image(z, url) || { x: .5, y: .5 };
		return { x: cx - w * centre.x, y: cy - h * centre.y, w, h, cx, cy, angle };
	}

	async centrer_logo_visible() {
		const design = this.nom, face = this.epinglee, indice = this.zone_sel;
		try {
			await this.attendre_sauvegardes();
			if (this.nom !== design || this.epinglee !== face || this.zone_sel !== indice) return;
			const contexte = this._zones_en_cours, z = contexte?.zones[indice];
			if (z?.zone !== "logo") return;
			const r = await frappe.call({ method: "aquaworld_ia.emballage.centrage.analyser_logo",
				args: { design, face, indice }, freeze: true, freeze_message: __("Détection du contenu visible du logo…") });
			if (this.nom !== design || this._zones_en_cours !== contexte || this.zone_sel !== indice) return;
			const centre = this.centre_image({ ...z, centre_visuel: r.message?.centre }, this.url_image_zone(z));
			if (!centre) throw new Error(__("Le logo a changé. Relancez le centrage."));
			const u = contexte.face.utile || contexte.face;
			z.centre_visuel = centre;
			z.decalage_contenu = {x: 0, y: 0};
			z.x = u.x + (u.w - z.w) / 2; z.y = u.y + (u.h - z.h) / 2;
			await contexte.sauver();
		} catch (e) { frappe.msgprint(this._msg(e)); }
	}


	tourner_zone(delta) {
		const c = this._zones_en_cours, z = c?.zones[this.zone_sel];
		if (!z || !["logo", "photo"].includes(z.zone)) return;
		const u = c.face.utile || c.face, cx = z.x + z.w / 2, cy = z.y + z.h / 2;
		z.rotation = this.angle_zone((z.rotation || 0) + delta);
		const facteur = Math.min(1, u.w / z.h, u.h / z.w);
		const w = Math.max(3, z.h * facteur), h = Math.max(3, z.w * facteur);
		z.w = Math.min(w, u.w); z.h = Math.min(h, u.h);
		z.x = Math.max(u.x, Math.min(cx - z.w / 2, u.x + u.w - z.w));
		z.y = Math.max(u.y, Math.min(cy - z.h / 2, u.y + u.h - z.h));
		return c.sauver();
	}

	async retoucher_logo_zone() {
		const design = this.nom, face = this.epinglee, indice = this.zone_sel;
		try { await this.attendre_sauvegardes(); }
		catch (e) { frappe.msgprint(this._msg(e)); return; }
		if (this.nom !== design || this.epinglee !== face || this.zone_sel !== indice || !this.data.peut_ecrire) return;
		const f = this.data.apercu?.faces?.find(f => f.code === face), z = f?.zones?.[indice];
		if (z?.zone !== "logo") return;
		const source_url = this.url_image_zone(z);
		if (!source_url) return this.choisir_logo_zone();
		return this.atelier_image("logo", {design, source_url, libelle_cible: f.libelle,
			cible_zone: {face, indice, modifie_le: this.d.modified}});
	}

	async choisir_logo_zone() {
		try { await this.attendre_sauvegardes(); }
		catch (e) { frappe.msgprint(this._msg(e)); return; }
		const design = this.nom, face = this.epinglee, indice = this.zone_sel;
		return this.mediatheque("logo", url => this.appliquer_logo_zone(face, indice, url, design));
	}

	async appliquer_logo_zone(face, indice, url, design = this.nom) {
		if (this.nom !== design) throw new Error(__("Rouvrez le design concerné pour modifier ce logo."));
		await this.attendre_sauvegardes();
		if (this.nom !== design) throw new Error(__("Rouvrez le design concerné pour modifier ce logo."));
		// La cible est capturée à l’ouverture du sélecteur ; un retour réseau ne doit pas changer une autre zone.
		const f = (this.data.apercu?.faces || []).find(f => f.code === face);
		const zones = JSON.parse(JSON.stringify(this.mep[face] || f?.zones || []));
		if (zones[indice]?.zone !== "logo") throw new Error(__("Cette zone Logo n’existe plus. Sélectionnez-la à nouveau."));
		if (url) zones[indice].logo = url;
		else delete zones[indice].logo;
		delete zones[indice].centre_visuel;
		const mise_en_page = { ...this.mep, [face]: zones };
		await this.enregistrer({ mise_en_page }, design);
	}

	_panneau_texte(sel) {
		this.injecter_polices();   // les polices du studio, pour l'aperçu dans le champ et sur le plan
		const esc = this._esc, st = sel.style || {}, ty = sel.typo || {};
		const libre = sel.zone === "texte_libre";
		const gras = ty.gras !== undefined ? ty.gras : ["nom", "accroche"].includes(sel.zone);
		const polices = (this.data.polices || []).map((p) => p.famille);
		const ALIGN = [["", __("Par défaut")], ["left", __("Gauche")], ["center", __("Centré")], ["right", __("Droite")], ["justify", __("Justifié")]];
		const apercu = `${ty.police ? `font-family:&quot;AQIA ${esc(ty.police)}&quot;, sans-serif;` : ""}${st.texte ? `color:${esc(st.texte)};` : ""}${st.fond ? `background:${esc(st.fond)};` : ""}`;
		const defaut_taille = { nom: __("auto"), accroche: "11", caracteristiques: String(+this.d.taille_caracteristiques || 8.5), avertissements: "7", contact: "7", texte_libre: "10" }[sel.zone];
		return `<div class="bloc" data-section-propriete="texte" style="margin-top:8px;padding:8px 10px;background:#f8fafc"><h6>${__("Texte et apparence")}</h6>
			${libre ? `<label class="small" style="margin:0">${__("Texte")}</label>
				<textarea class="form-control" data-prop="texte_libre" rows="4" style="font-size:13px;${apercu}">${esc(sel.texte || "")}</textarea>
				<div class="text-muted small" style="margin:3px 0 8px">${__("Imprimé tel quel, jamais modifié par l'IA. Une ligne peut avoir sa propre mise en forme : « {14pt, gras} Ma ligne ».")}</div>` : ""}
			<div class="se-texte-grille">
				<label class="se-select-large" for="se-police-zone">${__("Police")}</label><span class="se-select-large se-select-ajout"><select class="form-control" id="se-police-zone" data-prop="police"><option value="">${__("Par défaut")}</option>${polices.map((p) => `<option value="${esc(p)}" ${p === ty.police ? "selected" : ""}>${esc(p)}</option>`).join("")}</select><button class="btn btn-xs btn-default" data-role="police-zone-ajouter" title="${__("Ajouter une police (TTF/OTF)")}">＋</button></span>
				<span>${__("Taille (pt)")}</span><input type="number" data-prop="taille" min="4" max="120" step="0.5" value="${ty.taille || ""}" placeholder="${esc(defaut_taille)}" style="width:80px">
				<span>${__("Style")}</span><span><label class="se-check" style="margin:0 10px 0 0"><input type="checkbox" data-prop="gras" ${gras ? "checked" : ""}> <b>${__("Gras")}</b></label><label class="se-check" style="margin:0"><input type="checkbox" data-prop="italique" ${ty.italique ? "checked" : ""}> <i>${__("Italique")}</i></label></span>
				<label class="se-select-large" for="se-alignement-zone">${__("Alignement")}</label><select class="form-control se-select-large" id="se-alignement-zone" data-prop="align">${ALIGN.map(([v, l]) => `<option value="${v}" ${(ty.align || "") === v ? "selected" : ""}>${l}</option>`).join("")}</select>
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
	signaler_reductions(reductions) {
		if (!reductions.length) return;
		const ZONES = { caracteristiques: __("Caractéristiques"), avertissements: __("Avertissements"), contact: __("Contact"), accroche: __("Accroche") };
		const lignes = reductions.map((x) => x.echelle
			? __("{0} · {1} : imprimé à {2} % de la taille demandée", [ZONES[x.zone] || x.zone, this._esc(x.libelle), Math.round(x.echelle * 100)])
			: __("{0} · {1} : ne tient pas, même réduit à 40 % — non imprimé", [ZONES[x.zone] || x.zone, this._esc(x.libelle)]));
		frappe.msgprint({ title: __("Textes réduits pour tenir dans leur zone"), indicator: "orange",
			message: lignes.join("<br>") + `<p class="text-muted small" style="margin-top:8px">${__("Agrandissez la zone sur le plan, raccourcissez le texte ou baissez les tailles.")}</p>` });
	}

	ouvrir_contenu_zone(z) {
		if (!z) return;
		if (["accroche", "caracteristiques", "avertissements", "contact"].includes(z.zone)) return this.dialogue_textes(false, z.zone);
		if (z.zone === "logo") return this.choisir_logo_zone();
		if (z.zone === "photo") return this.mediatheque("photo_produit");
		if (z.zone === "pictos") return this.choisir_pictos_zone();
		const cible = z.zone === "texte_libre" ? '[data-prop="texte_libre"]'
			: `[data-champ="${z.zone === "nom" ? "nom_produit" : z.code === "qr" || this.d.type_code_barres === "QR" ? "url_qr" : "code_barres"}"]`;
		if (z.zone !== "texte_libre") { this.etape = 2; this.rendre_etats_etapes(); }
		const $cible = this.$root.find(cible);
		$cible.parents("details").prop("open", true);
		$cible[0]?.scrollIntoView({block: "center", behavior: "smooth"});
		$cible[0]?.focus({preventScroll: true});
	}

	async dialogue_textes(proposition = false, champ = null) {
		const design = this.nom;
		await this.attendre_sauvegardes();
		if (this.nom !== design) return;
		let textes = this.data.textes_imprimes || {};
		if (proposition) { try { textes = JSON.parse(this.d.textes_ia || "{}"); } catch (e) { textes = {}; } }
		const codes = Object.keys(textes), fields = [], editeurs = {};
		const inclut = c => !champ || champ === c;
		codes.forEach((c) => {
			const t = textes[c] || {};
			fields.push({ fieldtype: "Section Break", label: c.toUpperCase() });
			if (inclut("accroche")) fields.push({ fieldtype: "Data", fieldname: `acc_${c}`, label: __("Accroche"), default: t.accroche });
			if (inclut("caracteristiques")) fields.push({ fieldtype: "HTML", fieldname: `car_${c}`, options: `<label class="control-label">${__("Caractéristiques (une par ligne)")}</label><div data-car="1"></div>` });
			if (inclut("avertissements")) fields.push({ fieldtype: "Small Text", fieldname: `ave_${c}`, label: __("Avertissements (un par ligne)"), default: (t.avertissements || []).join("\n") });
			if (inclut("contact")) fields.push({ fieldtype: "Small Text", fieldname: `con_${c}`, label: __("Contact"), default: t.contact });
		});
		const dlg = new frappe.ui.Dialog({ title: proposition ? __("Relire les propositions IA") : __("Textes imprimés"), size: "large", fields, primary_action_label: proposition ? __("Appliquer ces textes à l’impression") : __("Enregistrer"),
			primary_action: async (v) => {
				const out = {};
				codes.forEach((c) => {
					out[c] = {...textes[c]};
					if (inclut("accroche")) out[c].accroche = v[`acc_${c}`] || "";
					if (inclut("caracteristiques")) out[c].caracteristiques = editeurs[c].valeur().split("\n").filter(x => x.trim());
					if (inclut("avertissements")) out[c].avertissements = (v[`ave_${c}`] || "").split("\n").filter(Boolean);
					if (inclut("contact")) out[c].contact = v[`con_${c}`] || "";
				});
				await frappe.call({ method: "aquaworld_ia.emballage.textes.enregistrer_textes", args: { design, textes: out } });
				dlg.hide(); if (this.nom === design) await this.recharger();
			} });
		// Même éditeur qu'à l'étape 2, langue par langue (la police du bloc se règle à l'étape 2).
		this.injecter_polices();
		if (inclut("caracteristiques")) codes.forEach((c) => {
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

}
