// Maquette de l’étui : six textures du PDF, aux dimensions du design, sans génération IA.
class StudioMaquette3D {
	async monter_maquette($h) {
		const design = this.nom, empreinte = this.d.empreinte_plan;
		if (this.data.exports?.pdf !== "a_jour") {
			$h.html(`<p class="se-vide">${__("Préparez la maquette pour voir le design actuel en volume.")}</p>`);
			return;
		}
		const cle = `${design}:${empreinte}`;
		this._maquettes_3d ||= new Map();
		$h.html(`<p class="se-vide">${__("Préparation des six faces du design…")}</p>`);
		try {
			if (!this._maquettes_3d.has(cle)) {
				if (this._maquettes_3d.size >= 3) this._maquettes_3d.delete(this._maquettes_3d.keys().next().value);
				this._maquettes_3d.set(cle, frappe.call({ method: "aquaworld_ia.emballage.mockup.apercu_interactif", args: { design } }).then(r => r.message));
			}
			const m = await this._maquettes_3d.get(cle);
			if (!$h[0].isConnected || design !== this.nom || empreinte !== this.d.empreinte_plan || this.data.exports?.pdf !== "a_jour") return;
			if (!m.disponible) { $h.html(`<p class="text-muted">${this._esc(m.raison)}</p>`); return; }
			this.dessiner_maquette($h, m);
		} catch (e) {
			this._maquettes_3d.delete(cle);
			if (!$h[0].isConnected) return;
			$h.html(`<p class="text-danger">${this._esc(this._msg(e))}</p><button class="btn btn-sm btn-default" data-recharger-volume>${__("Réessayer")}</button>`);
			$h.find("[data-recharger-volume]").on("click", () => this.monter_maquette($h));
		}
	}

	dessiner_maquette($h, m) {
		const D = m.dimensions, esc = this._esc;
		const vues = [["avant", __("Avant")], ["arriere", __("Arrière")], ["cote_droit", __("Droite")], ["cote_gauche", __("Gauche")], ["dessus", __("Dessus")], ["dessous", __("Dessous")]];
		$h.html(`<div class="se-volume" tabindex="0" role="region" aria-label="${__("Maquette 3D : glissez pour tourner, ou utilisez les flèches du clavier.")}">
			<div class="se-volume-boite">${vues.map(([code, nom]) => `<img class="se-volume-face" data-face-volume="${code}" src="${esc(m.faces[code])}" alt="${nom}" draggable="false">`).join("")}</div>
			<span class="se-volume-aide">${__("Glissez pour tourner")}</span></div>
			<div class="se-volume-commandes">${vues.map(([code, nom]) => `<button class="btn btn-xs btn-default" data-vue-volume="${code}">${nom}</button>`).join("")}
			<button class="btn btn-xs btn-default" data-vue-volume="perspective">${__("Perspective")}</button></div>
			<label class="se-volume-zoom">${__("Zoom")}<input type="range" min="0.5" max="1.8" step="0.05" value="1" data-zoom-volume></label>
			<p class="text-muted small">${__("{0} × {1} × {2} mm · faces issues du PDF actuel", [D.largeur, D.hauteur, D.profondeur])}</p>`);
		const cadre = $h.find(".se-volume")[0], boite = $h.find(".se-volume-boite")[0];
		if (this._vue_volume?.design !== this.nom) this._vue_volume = { design: this.nom, x: -18, y: -28, zoom: 1 };
		const vue = this._vue_volume;
		const afficher = () => { boite.style.transform = `rotateX(${vue.x}deg) rotateY(${vue.y}deg) scale3d(${vue.zoom},${vue.zoom},${vue.zoom})`; };
		const dimensionner = () => {
			const facteur = Math.min(Math.max(cadre.clientWidth - 100, 100) / Math.hypot(D.largeur, D.profondeur), 300 / Math.hypot(D.hauteur, D.profondeur));
			const w = D.largeur * facteur, h = D.hauteur * facteur, p = D.profondeur * facteur;
			const faces = { avant: [w, h, `translateZ(${p / 2}px)`], arriere: [w, h, `rotateY(180deg) translateZ(${p / 2}px)`],
				cote_droit: [p, h, `rotateY(90deg) translateZ(${w / 2}px)`], cote_gauche: [p, h, `rotateY(-90deg) translateZ(${w / 2}px)`],
				dessus: [w, p, `rotateX(90deg) translateZ(${h / 2}px)`], dessous: [w, p, `rotateX(-90deg) translateZ(${h / 2}px)`] };
			for (const [code, [largeur, hauteur, transform]] of Object.entries(faces)) {
				const im = boite.querySelector(`[data-face-volume="${code}"]`);
				Object.assign(im.style, { width: `${largeur}px`, height: `${hauteur}px`, left: `${-largeur / 2}px`, top: `${-hauteur / 2}px`, transform });
			}
			afficher();
		};
		let glisser = null;
		cadre.addEventListener("pointerdown", e => {
			if (e.button !== 0) return;
			glisser = { x: e.clientX, y: e.clientY, rx: vue.x, ry: vue.y };
			cadre.setPointerCapture(e.pointerId); cadre.classList.add("en-rotation");
		});
		cadre.addEventListener("pointermove", e => {
			if (!glisser) return;
			vue.y = glisser.ry + (e.clientX - glisser.x) * 0.5;
			vue.x = Math.max(-89, Math.min(89, glisser.rx - (e.clientY - glisser.y) * 0.5));
			afficher();
		});
		const finir = () => { glisser = null; cadre.classList.remove("en-rotation"); };
		cadre.addEventListener("pointerup", finir); cadre.addEventListener("pointercancel", finir);
		cadre.addEventListener("keydown", e => {
			if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)) return;
			e.preventDefault();
			if (e.key === "ArrowLeft") vue.y -= 10;
			if (e.key === "ArrowRight") vue.y += 10;
			if (e.key === "ArrowUp") vue.x = Math.max(-89, vue.x - 10);
			if (e.key === "ArrowDown") vue.x = Math.min(89, vue.x + 10);
			afficher();
		});
		$h.find("[data-zoom-volume]").val(vue.zoom).on("input", e => { vue.zoom = Number(e.currentTarget.value); afficher(); });
		$h.find("[data-vue-volume]").on("click", e => {
			const angles = { avant: [0, 0], arriere: [0, 180], cote_droit: [0, -90], cote_gauche: [0, 90], dessus: [-89, 0], dessous: [89, 0], perspective: [-18, -28] };
			[vue.x, vue.y] = angles[$(e.currentTarget).attr("data-vue-volume")]; afficher();
		});
		this._volume_observer?.disconnect();
		this._volume_observer = new ResizeObserver(dimensionner);
		this._volume_observer.observe(cadre);
		dimensionner();
	}
}
