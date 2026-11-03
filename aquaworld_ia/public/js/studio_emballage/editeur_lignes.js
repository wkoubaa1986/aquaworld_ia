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