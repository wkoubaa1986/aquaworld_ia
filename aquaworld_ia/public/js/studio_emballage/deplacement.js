// Gestes du plan : coordonnées en mm, sélection, capture du pointeur et sauvegarde à la fin.
class StudioDeplacement {
	capturer_saisie_position() {
		if (!this.$root) return null;
		const champs = [];
		this.$root.find('.se-droite [data-saisie-position="1"]').each((_i, el) => {
			const attribut = el.hasAttribute("data-pos") ? "data-pos" : el.hasAttribute("data-angle-picto") ? "data-angle-picto" : "data-decalage";
			champs.push({attribut, nom: el.getAttribute(attribut), valeur: el.value, focus: document.activeElement === el});
		});
		return {design: this.nom, face: this.epinglee, indice: this.zone_sel, champs};
	}

	restaurer_saisie_position(saisie) {
		if (!saisie || saisie.design !== this.nom || saisie.face !== this.epinglee || saisie.indice !== this.zone_sel) return;
		for (const c of saisie.champs) {
			const $champ = this.$root.find(`.se-droite [${c.attribut}]`).filter((_i, el) => el.getAttribute(c.attribut) === c.nom);
			$champ.val(c.valeur).attr("data-saisie-position", "1");
			if (c.focus) $champ[0]?.focus({preventScroll: true});
		}
	}

	regler_mode_deplacement(contenu) {
		this._deplacer_contenu = !!contenu;
		this.$root.find("[data-glisser-contenu]").prop("checked", !!contenu);
		this.$root.find("[data-mode-deplacement]").each((_i, el) => {
			const actif = (el.dataset.modeDeplacement === "contenu") === !!contenu;
			$(el).toggleClass("btn-primary", actif).toggleClass("btn-default", !actif).attr("aria-pressed", String(actif));
		});
		this.$root.find("[data-zone-cadre]").css("cursor", contenu ? "grab" : "move");
	}

	zone_pour_apercu(z) {
		const out = {...z}, origine = z._origine_apercu || z;
		delete out._origine_apercu;
		const rect = r => r && [z.x + (r[0]-origine.x)*z.w/origine.w, z.y + (r[1]-origine.y)*z.h/origine.h,
			r[2]*z.w/origine.w, r[3]*z.h/origine.h];
		if (z.apercu_elements) out.apercu_elements = z.apercu_elements.map(e => ({...e, rect: rect(e.rect), fond: rect(e.fond)}));
		return out;
	}

	memoriser_apercu_zones(face, zones) {
		// Une sélection immédiate d'une autre zone doit retrouver le dernier geste local.
		const f = this.data.apercu?.faces?.find(f => f.code === face.code);
		if (f) Object.assign(f, {zones: zones.map(z => this.zone_pour_apercu(z)), personnalisee: true, copie_de: null});
	}

	installer_glissement_zone({svg, groupe, cadre, poignee, face, zones, z, indice, actualiser, sauver, selectionner}) {
		const debut = mode => e => {
			if (e.button !== 0 || e.isPrimary === false || !this.data.peut_ecrire) return;
			e.preventDefault(); e.stopPropagation();
			this._glissement_zone?.annuler(false);
			const cible = e.currentTarget, pointeur = e.pointerId, design = this.nom;
			const point = ev => {
				if (!svg.isConnected) return null;
				const matrice = svg.getScreenCTM(); if (!matrice) return null;
				const p = svg.createSVGPoint(); p.x = ev.clientX; p.y = ev.clientY;
				return p.matrixTransform(matrice.inverse());
			};
			const p0 = point(e); if (!p0) return;
			const z0 = {...z}, d0 = this.decalage_contenu(z), u = face.utile || face;
			const contenu = mode === "move" && (this._deplacer_contenu || e.altKey);
			let bouge = false, fini = false, animation = null, dernier = e;
			const ecoutes = new AbortController(), options = {signal: ecoutes.signal};
			const appliquer = ev => {
				if (!bouge && Math.hypot(ev.clientX-e.clientX, ev.clientY-e.clientY) < 3) return;
				const p = point(ev); if (!p) return;
				bouge = true;
				const dx = p.x-p0.x, dy = p.y-p0.y;
				if (contenu) z.decalage_contenu = this.decalage_contenu({...z, decalage_contenu: {x: d0.x+dx, y: d0.y+dy}});
				else if (mode === "move") {
					z.x = Math.min(Math.max(z0.x+dx, u.x), u.x+u.w-z.w);
					z.y = Math.min(Math.max(z0.y+dy, u.y), u.y+u.h-z.h);
				} else {
					z.w = Math.max(3, Math.min(z0.w+dx, u.x+u.w-z.x));
					z.h = Math.max(3, Math.min(z0.h+dy, u.y+u.h-z.y));
				}
				actualiser(); this.afficher_decalage_contenu(z);
				for (const [cle, valeur] of Object.entries({x: z.x-u.x, y: z.y-u.y, w: z.w, h: z.h}))
					this.$root.find(`.se-droite [data-pos="${cle}"]`).val(Math.round(valeur*1000)/1000);
			};
			const terminer = (annuler, rafraichir = true) => {
				if (fini) return; fini = true;
				if (animation !== null) cancelAnimationFrame(animation);
				ecoutes.abort();
				if (cible.hasPointerCapture?.(pointeur)) cible.releasePointerCapture(pointeur);
				this._glissement_zone = null;
				groupe.classList.remove("en-glissement");
				if (annuler) { Object.assign(z, z0); actualiser(); }
				const d = this.decalage_contenu(z);
				if (!annuler && design === this.nom && (z.x !== z0.x || z.y !== z0.y || z.w !== z0.w || z.h !== z0.h || d.x !== d0.x || d.y !== d0.y)) sauver();
				if (rafraichir) { this.rendre_scene(); this.appliquer_retour_enregistrement(); }
			};
			this._glissement_zone = {design, annuler: rafraichir => terminer(true, rafraichir)};
			this.zone_sel = indice;
			groupe.parentNode.appendChild(groupe); // La zone sélectionnée passe devant les zones superposées.
			selectionner(); this.face_info({...face, zones});
			groupe.classList.add("en-glissement");
			cible.setPointerCapture(pointeur);
			document.addEventListener("pointermove", ev => {
				if (ev.pointerId !== pointeur) return;
				ev.preventDefault(); dernier = ev;
				if (animation === null) animation = requestAnimationFrame(() => { animation = null; appliquer(dernier); });
			}, options);
			document.addEventListener("pointerup", ev => {
				if (ev.pointerId !== pointeur) return;
				appliquer(ev); terminer(false);
			}, options);
			document.addEventListener("pointercancel", ev => { if (ev.pointerId === pointeur) terminer(true); }, options);
			cible.addEventListener("lostpointercapture", () => terminer(true), options);
			window.addEventListener("blur", () => terminer(true), options);
			document.addEventListener("keydown", ev => { if (ev.key === "Escape") { ev.preventDefault(); terminer(true); } }, options);
		};
		cadre.addEventListener("pointerdown", debut("move"));
		poignee.addEventListener("pointerdown", debut("resize"));
	}
}
