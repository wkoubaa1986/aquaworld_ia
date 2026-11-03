// Visuels du plan : mêmes contenus pour les faces au repos et pour leurs zones éditables.
class StudioApercu {
	contenu_zone_disponible(z) {
		return !!(this.url_image_zone(z) || z.apercu_texte || z.apercu_elements?.length);
	}

	message_zone_vide(z) {
		return z.apercu_message || ({
			logo: __("Choisissez un logo pour cette zone."), photo: __("Choisissez une photo du produit dans Contenus."),
			texte_libre: __("Saisissez le texte de cette zone."), nom: __("Renseignez le nom du produit dans Contenus."),
		}[z.zone] || __("Ce texte est vide dans les langues choisies. Renseignez-le pour le voir ici."));
	}

	dessiner_contenu_zone(el, z, indice) {
		if (!this.contenu_zone_disponible(z)) return this.dessiner_zone_vide(el, z);
		// Les images appliquent le décalage avant leur découpe, pour révéler les parties zoomées.
		if (!this.url_image_zone(z)) {
			const creer = el, id = `se-contenu-${this._serie_contenus = (this._serie_contenus || 0) + 1}`;
			const clip = creer("clipPath", {id, clipPathUnits: "userSpaceOnUse"});
			const limite = creer("rect", {}); clip.appendChild(limite);
			const cadre = creer("g", {}), contenu = creer("g", {"pointer-events": "none"}); cadre.appendChild(contenu);
			el = (tag, attrs) => { const n = creer(tag, attrs); contenu.appendChild(n); return n; };
			const mises_a_jour = [this.dessiner_symboles_zone(el, z, indice)];
			if (z.apercu_texte) mises_a_jour.push(this.dessiner_texte_zone(el, z, indice));
			const actualiser = () => {
				const d = this.decalage_contenu(z);
				Object.entries({x: z.x, y: z.y, width: z.w, height: z.h}).forEach(([k, v]) => limite.setAttribute(k, v));
				// À zéro, conserver aussi les anciennes maquettes EAN + QR adjacent.
				cadre.setAttribute("clip-path", d.x || d.y ? `url(#${id})` : "none");
				contenu.setAttribute("transform", `translate(${d.x} ${d.y})`);
				mises_a_jour.forEach(fn => fn());
			};
			actualiser(); return actualiser;
		}
		const mises_a_jour = [this.dessiner_image_zone(el, z, indice), this.dessiner_symboles_zone(el, z, indice)];
		if (z.apercu_texte) mises_a_jour.push(this.dessiner_texte_zone(el, z, indice));
		return () => mises_a_jour.forEach(fn => fn());
	}

	dessiner_zone_vide(el, z) {
		// Repère d'édition uniquement : il ne fait jamais partie des données imprimées.
		const cadre = el("svg", {viewBox: "0 0 100 40", "pointer-events": "none", "data-zone-vide": z.zone});
		const fond = el("rect", {width: 100, height: 40, rx: 2, fill: "#fffbeb", stroke: "#d97706", "stroke-dasharray": "2 2"});
		cadre.appendChild(fond);
		const vide_choisi = z.zone === "pictos" && this.pictos_selection_zone(z)?.length === 0;
		for (const [texte, y, taille] of [[z.libelle || z.zone, 16, 7], [vide_choisi ? __("Aucun") : __("À renseigner"), 29, 8]]) {
			const ligne = el("text", {x: 50, y, "text-anchor": "middle", "font-family": "sans-serif", "font-size": taille, fill: "#92400e"});
			ligne.textContent = texte; cadre.appendChild(ligne);
		}
		const actualiser = () => Object.entries({x: z.x, y: z.y, width: z.w, height: z.h}).forEach(([k, v]) => cadre.setAttribute(k, v));
		actualiser(); return actualiser;
	}

	rendre_apercu_ajout($s, type) {
		const $b = $s.find('[data-role="apercu-ajout"]'), z = this.data.apercu.choix_zones?.[type];
		if (!z) return $b.empty();
		const disponible = this.contenu_zone_disponible(z);
		$b.html(`<svg class="se-apercu-choix" viewBox="0 0 ${z.w} ${z.h}" aria-label="${this._esc(z.libelle)}"></svg>
			<div><b>${this._esc($s.find('[data-role="type-zone-plan"] option:selected').text())}</b>
			<p class="small text-muted">${disponible ? __("Aperçu du contenu à placer sur cette face.") : this._esc(this.message_zone_vide(z))}</p>
			<span class="small">${__("Ajoutez la zone pour la placer et modifier son contenu.")}</span></div>`);
		const svg = $b.find("svg")[0];
		const el = (tag, attrs) => { const n = document.createElementNS("http://www.w3.org/2000/svg", tag); Object.entries(attrs).forEach(([k, v]) => n.setAttribute(k, v)); svg.appendChild(n); return n; };
		this.dessiner_contenu_zone(el, z);
	}

	ordre_zones(zones) {
		// La photo automatique est un fond : dans le PDF elle précède tous les autres éléments.
		return zones.map((z, i) => ({ z, i })).sort((a, b) => Number(!!b.z.auto) - Number(!!a.z.auto));
	}

	dessiner_contenus_plan($s) {
		const svg = $s.find("svg.aqia-plan")[0], NS = "http://www.w3.org/2000/svg";
		if (!svg) return;
		for (const face of this.data.apercu.faces || []) {
			if (face.code === this.epinglee) continue;
			const g = document.createElementNS(NS, "g");
			g.setAttribute("class", "se-contenus-face"); g.setAttribute("data-face", face.code);
			g.setAttribute("pointer-events", "none"); svg.appendChild(g);
			const el = (tag, attrs) => { const n = document.createElementNS(NS, tag); Object.entries(attrs).forEach(([k, v]) => n.setAttribute(k, v)); g.appendChild(n); return n; };
			let visible = false;
			for (const {z} of this.ordre_zones(face.zones || [])) {
				if (z.style?.fond) el("rect", { x: z.x, y: z.y, width: z.w, height: z.h, rx: z.style.rayon || 0, fill: z.style.fond });
				this.dessiner_contenu_zone(el, z); visible = true;
			}
			if (visible) $s.find(`[data-face-label="${face.code}"]`).hide();
		}
	}

	dessiner_image_zone(el, z, indice) {
		const url = this.url_image_zone(z);
		if (!url) return () => {};
		const id = `se-image-${this._serie_images = (this._serie_images || 0) + 1}`;
		const clip = el("clipPath", { id, clipPathUnits: "userSpaceOnUse" });
		const limite = document.createElementNS("http://www.w3.org/2000/svg", "rect"); clip.appendChild(limite);
		const conteneur = el("g", { "clip-path": `url(#${id})` });
		const im = el("image", { href: url, "pointer-events": "none", ...(indice == null ? {} : { "data-zone-image": indice }) });
		conteneur.appendChild(im);
		this._tailles_images ||= new Map();
		const actualiser = () => {
			Object.entries({ x: z.x, y: z.y, width: z.w, height: z.h }).forEach(([k, v]) => limite.setAttribute(k, v));
			const taille = this._tailles_images.get(url);
			if (!taille) return;
			const c = this.cadre_image(z, taille.w, taille.h, url);
			Object.entries({ x: c.x, y: c.y, width: c.w, height: c.h, transform: `rotate(${c.angle} ${c.cx} ${c.cy})` }).forEach(([k, v]) => im.setAttribute(k, v));
		};
		actualiser();
		if (!this._tailles_images.has(url)) {
			const charge = new Image();
			charge.onload = () => { this._tailles_images.set(url, { w: charge.naturalWidth, h: charge.naturalHeight }); if (im.isConnected) actualiser(); };
			charge.src = url;
		}
		return actualiser;
	}

	dessiner_symboles_zone(el, z, indice) {
		if (!z.apercu_elements?.length) return () => {};
		const g = el("g", { "pointer-events": "none", ...(indice == null ? {"data-apercu-symboles": z.zone} : {"data-zone-symboles": indice}) });
		const origine = {x: z.x, y: z.y, w: z.w, h: z.h}, elements = [];
		for (const symbole of z.apercu_elements || []) {
			const url = this.data.apercu.images_zones?.[symbole.image];
			if (!url) continue;
			if (symbole.fond) {
				const fond = el("rect", {fill: "#fff"}); g.appendChild(fond); elements.push({n: fond, r: symbole.fond});
			}
			const image = el("image", {href: url, preserveAspectRatio: "xMidYMid meet", "data-symbole": symbole.code});
			g.appendChild(image); elements.push({n: image, r: symbole.rect, code: symbole.code, url});
		}
		const actualiser = () => {
			const sx = z.w / origine.w, sy = z.h / origine.h;
			for (const e of elements) {
				const {n, r} = e, cadre = {x: z.x + (r[0]-origine.x)*sx, y: z.y + (r[1]-origine.y)*sy, w: r[2]*sx, h: r[3]*sy};
				let attrs = {x: cadre.x, y: cadre.y, width: cadre.w, height: cadre.h};
				if (e.url) {
					const angle = this.rotation_picto(z, e.code);
					attrs.transform = "";
					if (angle) {
						this._tailles_images ||= new Map();
						const taille = this._tailles_images.get(e.url);
						// Même ajustement au cadre après rotation que show_pdf_page dans le PDF.
						const c = this.cadre_image({...cadre, rotation: angle}, taille?.w || 1, taille?.h || 1);
						attrs = {x: c.x, y: c.y, width: c.w, height: c.h, transform: `rotate(${c.angle} ${c.cx} ${c.cy})`};
						if (!taille && !e.charge) {
							e.charge = true;
							const image = new Image();
							image.onload = () => {
								if (image.naturalWidth && image.naturalHeight) this._tailles_images.set(e.url, {w: image.naturalWidth, h: image.naturalHeight});
								if (n.isConnected) actualiser();
							};
							image.src = e.url;
						}
					}
				}
				Object.entries(attrs).forEach(([k, v]) => n.setAttribute(k, v));
			}
		};
		actualiser();
		return actualiser;
	}

	dessiner_texte_zone(el, z, indice) {
		// Le serveur prépare le même HTML que pour le PDF. Le SVG interne convertit ses pt
		// CSS en mm sur la feuille ; le navigateur assure le retour à la ligne et l'arabe.
		const cadre = el("svg", { "pointer-events": "none", overflow: "hidden", ...(indice == null ? {} : { "data-zone-texte": indice }) });
		const fo = document.createElementNS("http://www.w3.org/2000/svg", "foreignObject"); cadre.appendChild(fo);
		const texte = document.createElementNS("http://www.w3.org/1999/xhtml", "div"); fo.appendChild(texte);
		texte.style.cssText = "all:initial;display:flow-root;transform-origin:top left;font-synthesis:none;pointer-events:none;user-select:none;";
		texte.innerHTML = z.apercu_texte;
		texte.querySelectorAll("p").forEach(p => {
			const famille = p.style.fontFamily.replace(/^['"]|['"]$/g, "");
			p.style.fontFamily = `${JSON.stringify("AQIA " + famille)}, sans-serif`;
			p.style.padding = "0";
			if (p.style.direction === "rtl" && !p.style.textAlign) p.style.textAlign = "right";
		});
		let largeur, hauteur;
		const ajuster = () => {
			if (!cadre.isConnected) return;
			const tient = echelle => {
				texte.style.width = `${largeur / echelle}px`;
				return texte.scrollHeight * echelle <= hauteur + 0.5 && texte.scrollWidth * echelle <= largeur + 0.5;
			};
			let echelle = 1;
			if (!tient(1)) {
				let bas = 0.4, haut = 1;
				for (let j = 0; j < 10; j++) { const milieu = (bas + haut) / 2; if (tient(milieu)) bas = milieu; else haut = milieu; }
				echelle = bas;
			}
			tient(echelle); texte.style.transform = `scale(${echelle})`;
		};
		const actualiser = () => {
			const m = z.style?.fond ? Math.min(2, z.w / 4, z.h / 4) : 0;
			largeur = (z.w - 2 * m) * 96 / 25.4; hauteur = (z.h - 2 * m) * 96 / 25.4;
			Object.entries({ x: z.x + m, y: z.y + m, width: z.w - 2 * m, height: z.h - 2 * m, viewBox: `0 0 ${largeur} ${hauteur}` }).forEach(([k, v]) => cadre.setAttribute(k, v));
			fo.setAttribute("width", largeur); fo.setAttribute("height", hauteur);
			ajuster();
		};
		actualiser();
		document.fonts?.ready.then(ajuster);
		return actualiser;
	}

}
