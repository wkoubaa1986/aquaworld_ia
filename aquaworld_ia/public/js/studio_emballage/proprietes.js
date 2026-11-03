// Accordéons de propriétés : état local à la sélection, conservé pendant les sauvegardes.
class StudioProprietes {
	monter_defilement_colonnes() {
		this.arreter_defilement_colonnes({liberer: false});
		const grille = this.$root.find(".se-grid")[0];
		if (!grille) { this.liberer_page_studio(); return; }
		const ajuster = () => {
			if (!grille.isConnected || !grille.offsetWidth) return;
			// Suivre la disposition réelle, y compris avec le zoom ou un conteneur redimensionné.
			const style = getComputedStyle(grille);
			const cote_a_cote = style.gridTemplateColumns.trim().split(/\s+/).length === 3;
			grille.classList.toggle("se-defilement-colonnes", cote_a_cote);
			if (cote_a_cote) {
				// Coordonnée dans le document : le défilement de la page ne doit pas allonger la grille.
				const cadre = grille.getBoundingClientRect();
				const haut = cadre.top + window.scrollY;
				// Le rectangle est déjà agrandi par le zoom CSS, contrairement à la hauteur à appliquer.
				const echelle = cadre.width / (parseFloat(style.width) || cadre.width);
				const hauteur = `${Math.floor(Math.max(160, window.innerHeight - haut - 16) / echelle)}px`;
				if (grille.style.getPropertyValue("--se-hauteur-colonnes") !== hauteur) grille.style.setProperty("--se-hauteur-colonnes", hauteur);
				if (window.innerHeight - haut >= 176) {
					// Le Desk ajoute des marges après le studio : empêcher la page entière d'emporter les panneaux.
					const html = document.documentElement;
					for (const [nom, element] of [["html", html], ["body", document.body]]) {
						const zoom = element.getBoundingClientRect().width / (parseFloat(getComputedStyle(element).width) || element.getBoundingClientRect().width);
						const valeur = `${window.innerHeight / zoom}px`, propriete = `--se-hauteur-${nom}`;
						if (html.style.getPropertyValue(propriete) !== valeur) html.style.setProperty(propriete, valeur);
					}
					html.classList.add("se-studio-fixe");
					if (window.scrollY) window.scrollTo(window.scrollX, 0);
				} else this.liberer_page_studio();
			} else {
				grille.style.removeProperty("--se-hauteur-colonnes");
				this.liberer_page_studio();
			}
		};
		const observer = new ResizeObserver(ajuster);
		observer.observe(grille);
		observer.observe(this.$root[0]);
		observer.observe(this.$barre[0]);
		window.addEventListener("resize", ajuster);
		this._arreter_defilement_colonnes = () => { observer.disconnect(); window.removeEventListener("resize", ajuster); };
		ajuster();
	}

	arreter_defilement_colonnes({liberer = true} = {}) {
		this._arreter_defilement_colonnes?.();
		this._arreter_defilement_colonnes = null;
		if (liberer) this.liberer_page_studio();
	}

	liberer_page_studio() {
		const html = document.documentElement;
		html.classList.remove("se-studio-fixe");
		html.style.removeProperty("--se-hauteur-html");
		html.style.removeProperty("--se-hauteur-body");
	}

	memoriser_panneau_proprietes() {
		const panneau = this.$root?.find(".se-droite")[0];
		const etat = this._panneaux_proprietes?.get(panneau?.dataset.sectionsContexte);
		if (!etat) return;
		etat.section = panneau.querySelector("details[data-section-propriete][open]")?.dataset.sectionPropriete || null;
		etat.picto = panneau.querySelector("details[data-propriete-picto][open]")?.dataset.proprietePicto || null;
		etat.defilement = panneau.scrollTop;
	}

	monter_sections_proprietes($bloc, face, zone) {
		const panneau = this.$root.find(".se-droite")[0];
		if (!panneau || !$bloc[0]) return;
		const cle = JSON.stringify([this.nom, face.code, zone ? this.zone_sel : null, zone?.zone]);
		this._panneaux_proprietes ||= new Map();
		if (!this._panneaux_proprietes.has(cle)) {
			if (this._panneaux_proprietes.size >= 100) this._panneaux_proprietes.delete(this._panneaux_proprietes.keys().next().value);
			const section = !zone ? "elements" : {pictos: "pictos", logo: "logo", photo: "zoom", code_barres: "code"}[zone.zone] || "texte";
			this._panneaux_proprietes.set(cle, {section, picto: $bloc[0].querySelector("[data-propriete-picto]")?.dataset.proprietePicto || null, defilement: 0});
		}
		const etat = this._panneaux_proprietes.get(cle);
		panneau.dataset.sectionsContexte = cle;
		// Conserver les nœuds des champs et leurs sélecteurs : replier ne détruit aucune saisie.
		for (const bloc of $bloc[0].querySelectorAll("[data-section-propriete]")) {
			if (bloc.tagName === "DETAILS") continue;
			const titre = bloc.querySelector(":scope > h6");
			if (!titre) continue;
			const details = document.createElement("details"), summary = document.createElement("summary"), corps = document.createElement("div");
			for (const {name, value} of [...bloc.attributes]) details.setAttribute(name, value);
			details.style.padding = "";
			summary.append(...titre.childNodes); titre.remove();
			corps.className = "se-section-corps"; corps.append(...bloc.childNodes);
			details.append(summary, corps); bloc.replaceWith(details);
		}
		const groupe = (selecteur, attribut, propriete) => {
			const volets = [...$bloc[0].querySelectorAll(selecteur)];
			for (const volet of volets) {
				volet.open = volet.dataset[attribut] === etat[propriete];
				volet.addEventListener("toggle", () => {
					if (!volet.isConnected || panneau.dataset.sectionsContexte !== cle) return;
					if (volet.open) {
						etat[propriete] = volet.dataset[attribut];
						for (const autre of volets) if (autre !== volet) autre.open = false;
					} else if (etat[propriete] === volet.dataset[attribut]) etat[propriete] = null;
				});
			}
		};
		groupe("details[data-section-propriete]", "sectionPropriete", "section");
		groupe("details[data-propriete-picto]", "proprietePicto", "picto");
		panneau.scrollTop = etat.defilement;
		panneau.onscroll = () => { if (panneau.isConnected && panneau.dataset.sectionsContexte === cle) etat.defilement = panneau.scrollTop; };
	}
}
