{% include "aquaworld_ia/public/js/studio_emballage/etat.js" %}
{% include "aquaworld_ia/public/js/studio_emballage/edition.js" %}
{% include "aquaworld_ia/public/js/studio_emballage/proprietes.js" %}
{% include "aquaworld_ia/public/js/studio_emballage/deplacement.js" %}
{% include "aquaworld_ia/public/js/studio_emballage/pictogrammes.js" %}
{% include "aquaworld_ia/public/js/studio_emballage/apercu.js" %}
{% include "aquaworld_ia/public/js/studio_emballage/medias.js" %}
{% include "aquaworld_ia/public/js/studio_emballage/resolution.js" %}
{% include "aquaworld_ia/public/js/studio_emballage/couleurs.js" %}
{% include "aquaworld_ia/public/js/studio_emballage/maquette_3d.js" %}
{% include "aquaworld_ia/public/js/studio_emballage/editeur_lignes.js" %}

// Studio emballage — la page plein écran pour concevoir un emballage.
//
// Quatre étapes, vues Édition / Aperçu imprimé / 3D et panneau de propriétés.
// Les modules inclus séparent état/sauvegarde, édition du plan et ateliers d’images.
// Les routes serveur sont communes à la fiche ERPNext et au studio.
frappe.pages["studio-emballage"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({ parent: wrapper, title: __("Studio emballage"), single_column: true });
	wrapper.studio = new StudioEmballage(wrapper);
	// Le conteneur Frappe émet « hide » sans appeler automatiquement on_page_hide.
	$(wrapper).on("hide.studioEmballage", e => {
		if (e.target === wrapper) frappe.pages["studio-emballage"].on_page_hide(wrapper);
	});
};
frappe.pages["studio-emballage"].on_page_show = function (wrapper) {
	if (wrapper.studio) {
		wrapper.studio.depuis_route();
		wrapper.studio.monter_defilement_colonnes();
	}
};
frappe.pages["studio-emballage"].on_page_hide = function (wrapper) {
	if (wrapper.studio) {
		wrapper.studio._glissement_zone?.annuler(false);
		wrapper.studio.attendre_sauvegardes().catch(() => {});
		wrapper.studio.arreter_suivi();
		wrapper.studio._volume_observer?.disconnect();
		wrapper.studio.arreter_defilement_colonnes();
	}
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
	rendre() {
		this.memoriser_panneau_proprietes();
		const gauche = this.$root.find(".se-gauche")[0];
		const defilement_gauche = gauche?.dataset.design === this.nom ? gauche.scrollTop : 0;
		const defilement_page = gauche?.dataset.design === this.nom ? window.scrollY : null;
		const scene = this.$root.find(".se-scene")[0];
		const defilement_scene = scene?.dataset.design === this.nom && scene.dataset.vue === this.onglet ? scene.scrollTop : 0;
		this.rendre_barre();
		this.$corps.html(`<div class="se-grid">
			<div class="se-col se-gauche" tabindex="0" role="region" aria-label="${__("Réglages du design")}"></div>
			<div class="se-col se-col-apercu"><div class="se-centre"><div class="se-onglets"></div><div class="se-scene" tabindex="0" role="region" aria-label="${__("Aperçu du design")}"></div></div></div>
			<div class="se-col se-droite" tabindex="0" role="region" aria-label="${__("Réglages de la sélection")}"></div></div>`);
		this.monter_defilement_colonnes();
		this.rendre_gauche();
		this.$root.find(".se-gauche").scrollTop(defilement_gauche);
		this.rendre_scene();
		this.$root.find(".se-scene").scrollTop(defilement_scene);
		this.rendre_droite();
		// Le remplacement temporaire de la grille peut raccourcir la page et faire remonter le navigateur.
		if (defilement_page !== null) window.scrollTo(window.scrollX, defilement_page);
	}

	rendre_barre() {
		const d = this.d;
		this.$barre.html(`
			<select data-role="selecteur"><option value="${this._esc(d.name)}">${this._esc(d.nom_produit || d.name)} · ${this._esc(d.name)}</option></select>
			<span class="se-titre">${this._esc(d.nom_produit || d.article || "")}</span>
			<span class="se-chip ${this.data.exports?.pdf === "a_jour" ? "ok" : "encours"}">${this.data.exports?.pdf === "a_jour" ? __("PDF à jour") : this.data.exports?.pdf === "a_regenerer" ? __("PDF à régénérer") : __("PDF à créer")}</span>
			<span class="small text-muted" data-role="sauvegarde"></span>
			<button class="btn btn-xs btn-default" data-role="reessayer-sauvegarde" style="display:none">${__("Réessayer")}</button>
			<button class="btn btn-xs btn-default" data-role="mediatheque">${__("Médiathèque")}</button>
			<span class="se-chip">${this._esc(d.type_boite || "")}</span>
			<a class="btn btn-xs btn-default" href="/app/design-emballage/${encodeURIComponent(d.name)}">${__("Fiche")}</a>
			<button class="btn btn-xs btn-default" data-role="dupliquer" title="${__("Une copie de ce design, pour un autre article ou une autre piste")}">⧉ ${__("Dupliquer")}</button>
			<span class="se-cout">${__("Coût IA de ce design : {0} $", [((this.data.etat || {}).cout_document || 0).toFixed(3)])}</span>`);
		this.maj_sauvegarde();
		this.$barre.find('[data-role="reessayer-sauvegarde"]').on("click", () => this.reessayer_sauvegarde());
		this.$barre.find('[data-role="mediatheque"]').on("click", () => this.mediatheque());
		const $sel = this.$barre.find('[data-role="selecteur"]');
		$sel.on("focus", async () => {
			if ($sel.data("charge")) return;
			const r = await frappe.call({ method: "aquaworld_ia.emballage.studio.liste", args: { limite: 30 } });
			$sel.html((r.message || []).map((l) => `<option value="${this._esc(l.name)}" ${l.name === d.name ? "selected" : ""}>${this._esc(l.nom_produit || l.name)} · ${this._esc(l.name)} · ${this._esc(l.statut || "")}</option>`).join(""));
			$sel.data("charge", 1);
		});
		$sel.on("change", () => frappe.set_route("studio-emballage", $sel.val()));
		this.$barre.find('[data-role="dupliquer"]').on("click", async () => {
			try { await this.attendre_sauvegardes(); }
			catch (e) { frappe.msgprint(this._msg(e)); return; }
			aqia_dupliquer_design(this.d, (nom) => frappe.set_route("studio-emballage", nom));
		});
	}

	rendre_gauche() {
		const d = this.d, esc = this._esc;
		const $g = this.$root.find(".se-gauche");
		const defilement = $g[0]?.dataset.design === this.nom ? $g[0].scrollTop : 0;
		const types = (this.data.types || []).map((t) => `
			<div class="se-type${t.type === d.type_boite ? " active" : ""}" data-type="${esc(t.type)}" title="${esc(t.description)}">${t.svg}<div class="nom">${esc(t.type)}</div></div>`).join("");
		const type = (this.data.types || []).find((t) => t.type === d.type_boite);
		const dims = type ? type.dimensions : ["Largeur", "Hauteur", "Profondeur"];
		// Un champ par dimension que la forme connaît (libellé null = sans objet, champ masqué).
		const champs_dims = ["L", "H", "P", "R"].map((k, i) => dims[i]
			? `<div><label>${esc(dims[i])}</label><input type="number" step="0.5" min="1" data-champ="${StudioEmballage.CHAMPS_DIMS[k]}" value="${d[StudioEmballage.CHAMPS_DIMS[k]] || ""}"></div>`
			: "").join("");
		const langues_actives = Object.keys(this.data.textes_imprimes || { fr: {} });
		const langues = (this.data.langues || []).map((l) => `<span class="c ${langues_actives.includes(l.code) ? "on" : ""}" data-langue="${esc(l.code)}">${esc(l.libelle)}</span>`).join("");
		const pictos = (this.data.pictos || []).map((p) => `<span class="c pic ${(d.pictogrammes || []).some((x) => x.pictogramme === p.code) ? "on" : ""}" data-picto="${esc(p.code)}" title="${esc(p.categorie || "")}">${p.url ? `<img src="${esc(p.url)}" alt="">` : ""}${esc(p.libelle)}</span>`).join("")
			+ `<span class="c ajout" data-ajouter-picto="1" title="${__("Ajouter un pictogramme ou une certification depuis une image")}">＋ ${__("Ajouter")}</span>`
			+ `<span class="c ajout" data-tampon-ia="1" title="${__("Un tampon / badge vectoriel (SVG) dessiné par l'IA : poids, garantie, « 100 % naturel »…")}">✨ ${__("Tampon IA")}</span>`;
		const fichier = (champ, libelle) => `
			<label>${libelle}</label><div class="se-fichier">
			${d[champ] ? `<img src="${esc(d[champ])}" alt="" data-voir="${champ}">` : ""}
			<button class="btn btn-xs btn-default" data-choisir-media="${champ}">${d[champ] ? __("Remplacer") : __("Choisir")}</button>
			${d[champ] ? `<button class="btn btn-xs btn-default" data-modifier-media="${champ}">${__("Modifier")}</button>` : ""}
			</div>`;
		const pretes = (d.variantes || []).filter((v) => v.statut === "Prête").length;
		const a_generer = (d.variantes || []).filter((v) => ["À générer", "Échec"].includes(v.statut)).length;
		const est = this.data.estimation || {};

		$g.html(`
			<div class="se-etape" data-etape="1">
				<div class="se-tete"><span class="num">1</span>${__("Produit et format")}</div>
				<div class="se-corps">
					<p class="small text-muted">${esc(d.article || "")}</p><div class="se-types">${types}</div>
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
					<label>${__("Caractéristiques imprimées")}</label><div data-role="editeur-car"></div><div data-role="avert-lignes"></div>
					<label>${__("Avertissements (un par ligne)")}</label><textarea data-champ="avertissements">${esc(d.avertissements || "")}</textarea>
					<label>${__("Contact")}</label><textarea data-champ="contact">${esc(d.contact || "")}</textarea>
					<div class="se-btns"><button class="btn btn-sm btn-default" data-action="textes">${__("Textes par langue")}</button>
					<button class="btn btn-sm btn-default" data-action="preparer">${__("Proposer des textes par IA")}</button>
					${d.textes_ia ? `<button class="btn btn-sm btn-default" data-action="propositions_textes">${__("Relire les propositions IA")}</button>` : ""}</div>
					<details class="se-avance"><summary>${__("Pictogrammes et certifications")} (<span data-role="nb-pictos">${(d.pictogrammes || []).length}</span>)</summary><div class="se-chips" data-liste="pictogrammes">${pictos}</div>
					<label class="se-check"><input type="checkbox" data-champ="pictos_sans_cartouche" ${d.pictos_sans_cartouche ? "checked" : ""} title="${__("Posés en transparence ; les pictogrammes monochromes prennent la couleur du texte de la face. Code-barres et QR gardent leur cartouche pour le scan.")}"> ${__("Sans cartouche blanc (en transparence)")}</label></details>
					<details class="se-avance"><summary>${__("Codes-barres et QR")}</summary><div class="se-3" style="grid-template-columns:1fr 1.4fr">
						<div><label>${__("Code")}</label><select data-champ="type_code_barres">${["EAN-13", "QR", "EAN-13 + QR", "Aucun"].map((o) => `<option ${o === d.type_code_barres ? "selected" : ""}>${o}</option>`).join("")}</select></div>
						<div><label>${__("EAN-13")}</label><input type="text" data-champ="code_barres" value="${esc(d.code_barres || "")}"></div>
					</div>
					<label>${__("URL du QR")}</label><input type="text" data-champ="url_qr" value="${esc(d.url_qr || "")}" placeholder="https://…">
					<label>${__("Couleur du QR")}</label>
					<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap"><input type="color" data-champ="couleur_qr" value="${esc(d.couleur_qr || "#000000")}" style="width:44px;height:26px;padding:1px">
						${this._palette().map((c) => { const ok = this._contraste_blanc(c) >= 3; return `<span class="se-pastille petite" style="background:${esc(c)};${ok ? "" : "opacity:.35;cursor:not-allowed"}" title="${esc(c)}${ok ? "" : " — " + __("trop clair pour un QR")}" ${ok ? `data-qr-couleur="${esc(c)}"` : ""}></span>`; }).join("")}
						${d.couleur_qr && d.couleur_qr !== "#000000" ? `<button class="btn btn-xs btn-default" data-qr-couleur="">${__("Noir")}</button>` : ""}</div>
					<div class="text-muted small">${__("Une teinte foncée : le QR se lit sur son cartouche blanc (les couleurs trop claires sont refusées). Pour le poser sur une face : épinglez-la, puis « Ajouter : QR code ».")}</div></details>
				</div>
			</div>
			<div class="se-etape" data-etape="3">
				<div class="se-tete"><span class="num">3</span>${__("Mise en page")}</div>
				<div class="se-corps">
					<label>${__("Fond de l'emballage")}</label>
					<div class="se-3" style="grid-template-columns:auto 1fr;align-items:center">
						<input type="color" data-champ="couleur_fond" value="${esc(d.couleur_fond || "#e5e7eb")}" style="width:44px;height:30px;padding:2px" title="${__("Couleur de fond")}">
						<span class="small text-muted">${d.couleur_fond ? esc(d.couleur_fond) + ` <a href="#" data-effacer="couleur_fond">✕</a>` : __("Sans couleur choisie : fond automatique.")}</span>
					</div>
					${fichier("image_fond", __("Image de fond (texture, motif)"))}
					<label class="se-check"><input type="checkbox" data-champ="fond_continu" ${d.fond_continu ? "checked" : ""}> ${__("Fond continu sur toutes les faces (panorama découpé aux plis)")}</label>
					<label class="se-check"><input type="checkbox" data-champ="faces_identiques" ${d.faces_identiques ? "checked" : ""}> ${__("Face arrière identique à la face avant")}</label>
					<label class="se-check"><input type="checkbox" data-champ="cotes_identiques" ${d.cotes_identiques ? "checked" : ""} title="${__("Avec le dos identique à l'avant, le code-barres et les avertissements sont dupliqués sur les deux côtés.")}"> ${__("Côtés identiques (gauche = droit)")}</label>
					<p class="text-muted small" style="margin:2px 0 6px">${__("Placez vos éléments sur le plan, puis créez le PDF à l’étape 4. L’IA est facultative.")}</p>
					<details class="se-avance"><summary>${__("Création assistée par IA (facultatif)")}</summary><div class="se-btns" style="margin-top:6px"><button class="btn btn-sm btn-default" data-action="fond" ${this._dims_ok() ? "" : "disabled"}>${__("Fond IA · 1 image · ≈ {0} $", [(est.cout || 0).toFixed(2)])}</button>
						<button class="btn btn-sm btn-default" data-action="integrer" ${this._dims_ok() ? "" : "disabled"} title="${__("L'IA fond ensemble l'image de fond, la photo du produit et les couleurs du logo sur une face, selon votre consigne")}">✨ ${__("Intégrer photo + fond (IA)")}</button></div>
					<label>${__("Brief de style")}</label><textarea data-champ="brief_style" placeholder="${__("ex. haut de gamme, bleu profond, minimaliste")}">${esc(d.brief_style || "")}</textarea>
					<div class="se-3" style="grid-template-columns:1.6fr 1fr">
						<div><label>${__("Palette (hex)")}</label><input type="text" data-champ="palette" value="${esc(d.palette || "")}">
							<button class="btn btn-xs btn-default" data-palette-pipette style="margin-top:6px">${__("＋ Couleur / pipette")}</button>
							<div class="se-palette" data-role="palette-pastilles">${this._pastilles_palette()}</div></div>
						<div><label>${__("Variantes")}</label><input type="number" min="1" max="4" data-champ="nb_variantes" value="${d.nb_variantes || 3}"></div>
					</div>
					<div class="se-btns">
						<button class="btn btn-sm btn-primary" data-action="generer" ${d.textes_ia && a_generer ? "" : "disabled"} title="${!d.textes_ia ? __("Préparez d'abord les textes.") : ""}">${__("Générer {0} variante(s) · ≈ {1} $", [a_generer, ((est.cout || 0) * a_generer).toFixed(2)])}</button>
					</div>
					<p class="text-muted small" style="margin:6px 0 0">${__("{0} variante(s) prête(s).", [pretes])}</p><button class="btn btn-sm btn-default" data-action="variantes">${__("Voir les variantes")}</button><button class="btn btn-sm btn-default" data-action="faces" ${d.variante_choisie ? "" : "disabled"}>${__("Faces secondaires par IA · 5 images")}</button></details>
				</div>
			</div>
			<div class="se-etape" data-etape="4">
				<div class="se-tete"><span class="num">4</span>${__("Vérifier et exporter")}</div>
				<div class="se-corps">
					${this.contenu_export()}
				</div>
			</div>`);
		this.rendre_etats_etapes();
		this.lier_gauche();
		$g.attr("data-design", this.nom).scrollTop(defilement);
	}

	contenu_export() {
		const d = this.d, esc = this._esc;
		const resolution = this.rapport_resolution(), traitement = this.data.etat || {};
		return `<label class="se-check"><input type="checkbox" data-champ="ameliorer_images_pdf" ${d.ameliorer_images_pdf ? "checked" : ""}> ${__("Préparer toutes les images à 300 ppp")}</label>
					<p class="small text-muted">${__("Gratuit · agrandissement fidèle jusqu’à ×4 dans le PDF. Les textes et les SVG vectoriels restent nets.")}</p>
					${traitement.tache === "resolution_pdf" && traitement.statut === "echec" ? `<p class="text-danger small">${esc(traitement.erreur || __("La préparation a échoué. Relancez l’export."))}</p>` : ""}
					${resolution ? `<button class="btn btn-sm btn-default" data-action="bilan_resolution">${__("Bilan résolution")} · ${resolution.ameliorees} ↑ ${resolution.insuffisantes ? `· ${resolution.insuffisantes} ${__("sous 300 ppp")}` : ""}</button>` : ""}
					<div class="se-btns">
						<button class="btn btn-sm btn-primary" data-action="composer" ${this._dims_ok() && !(this.data.verifications || []).length ? "" : "disabled"}>${d.plan_a_plat ? __("Actualiser le PDF") : __("Créer le PDF")}</button>
						<button class="btn btn-sm btn-default" data-action="voir_simulation">${d.type_boite === "Étui à rabats" ? __("Maquette 3D gratuite") : __("Ouvrir la vue 3D")}</button>
					</div>
					${this.commande_3d()}
					${d.variante_choisie && d.fond_continu && d.image_fond ? `<p class="text-danger small" style="margin:8px 0 0">⚠ ${__("« Fond continu » est coché avec une image de fond : le panorama remplace la variante IA choisie ({0}). Pour composer avec la variante, décochez « Fond continu » à l'étape 3 (ou retirez l'image de fond), puis recomposez.", [esc(((d.variantes || []).find((v) => v.numero === d.variante_choisie) || {}).titre || d.variante_choisie)])}</p>` : ""}
					${d.plan_a_plat ? `<p class="small" style="margin:8px 0 0"><a href="${esc(d.plan_a_plat)}" target="_blank">${this.data.exports?.pdf === "a_jour" ? __("Télécharger le PDF imprimeur") : __("Ouvrir le PDF précédent")}</a></p>` : ""}
					<div class="se-verifications">${(this.data.verifications || []).length ? this.data.verifications.map(x => `<p class="text-danger small">${esc(x)}</p>`).join("") : `<p class="small">✓ ${__("Format et produit renseignés. Contrôlez l’aperçu imprimé avant impression.")}</p>`}
					${this.data.exports?.pdf === "a_regenerer" ? `<p class="text-warning small">${__("Le PDF précédent doit être actualisé pour inclure le contenu actuel.")}</p>` : ""}
					${d.apercu_3d ? `<button class="btn btn-xs btn-default" data-action="voir_simulation">${__("Voir l’aperçu 3D")}</button>` : ""}</div>`;
	}

	etat_3d() {
		const e = this.data.etat || {};
		const en_cours = !!(this._mockup_en_cours || (e.tache === "mockup" && e.statut === "en cours"));
		const pdf_pret = this.data.exports?.pdf === "a_jour";
		const bloque = !!(en_cours || e.bloque || this.data.peut_ecrire === false);
		const raison = en_cours ? __("L’aperçu 3D est en cours de génération.")
			: this.data.peut_ecrire === false ? __("Vous avez accès à ce design en lecture seule.")
			: e.bloque ? __("Un traitement est en cours sur ce design.")
			: !pdf_pret ? __("Créez ou actualisez le PDF pour que la 3D utilise vos derniers logos, textes et images.") : "";
		return { en_cours, pdf_pret, bloque, raison };
	}

	commande_3d() {
		const e = this.etat_3d(), cout = this.data.estimation?.cout;
		const label = e.en_cours ? __("Génération 3D en cours…") : this.d.apercu_3d ? __("Régénérer l’aperçu 3D") : __("Générer l’aperçu 3D");
		return `<div class="se-btns" style="margin-top:8px"><button class="btn btn-sm btn-default" data-action="mockup" ${!e.pdf_pret || e.bloque ? "disabled" : ""}>${label}</button></div>
			<p class="text-muted small" style="margin-top:6px">${cout == null ? __("1 image IA facturée") : __("1 image IA · coût estimé : {0} $", [Number(cout).toFixed(2)])}</p>
			${e.raison ? `<p class="small text-muted">${e.raison}</p>` : ""}`;
	}

	scene_3d($s) {
		const d = this.d, e = this.data.etat || {}, etat = this.etat_3d();
		const preparation = !etat.pdf_pret && !etat.bloque
			? `<button class="btn btn-sm btn-primary" data-action="preparer_3d" ${this._dims_ok() && !(this.data.verifications || []).length ? "" : "disabled"}>${d.plan_a_plat ? __("Actualiser la maquette 3D") : __("Créer la maquette 3D")}</button><p class="text-muted small">${__("Le PDF sera actualisé avec vos dernières modifications.")}</p>` : "";
		const erreur = e.tache === "mockup" && e.statut === "echec" && !etat.en_cours
			? `<p class="text-danger small">${__("La dernière génération 3D a échoué : {0}", [this._esc(e.erreur || __("erreur inconnue"))])}</p>` : "";
		const image = d.apercu_3d
			? `${!this.data.exports?.simulation_a_jour ? `<p class="alert alert-warning">${__("Aperçu 3D précédent : il ne correspond plus au contenu actuel.")}</p>` : ""}<img class="se-img" src="${this._esc(d.apercu_3d)}" alt="${__("Aperçu 3D de l’emballage")}">`
			: "";
		$s.html(`<h5>${__("Maquette interactive · gratuite")}</h5>${preparation}<div data-role="maquette-3d"></div><hr>
			<h5>${__("Rendu réaliste par IA")}</h5>${this.commande_3d()}${erreur}
			${etat.en_cours ? `<p class="alert alert-info">${__("Génération 3D en cours, environ une minute. Le résultat s’affichera automatiquement.")} <span data-role="attente-txt">${this._esc(e.etape || "")}</span></p>` : ""}
			${image}<p class="text-muted small text-center">${__("Illustration IA non contractuelle. Le PDF reste le document d’impression.")}</p>`);
		$s.find("[data-action]").on("click", event => this.action($(event.currentTarget).attr("data-action")));
		this.monter_maquette($s.find('[data-role="maquette-3d"]'));
	}

	rendre_export() {
		this.$root.find('.se-etape[data-etape="4"] .se-corps').html(this.contenu_export())
			.find('[data-action]').on('click', e => this.action($(e.currentTarget).attr('data-action')));
		this.$root.find('[data-champ="ameliorer_images_pdf"]').on('change', e => this.modifier({ameliorer_images_pdf: e.currentTarget.checked ? 1 : 0}, true));
	}

	rendre_etats_etapes() {
		const d = this.d;
		this.$root.find('[data-role="nb-pictos"]').text((d.pictogrammes || []).length);
		const faites = {
			1: this._dims_ok(),
			2: !!(d.nom_produit || d.article),
			3: this._dims_ok() && !!(d.nom_produit || d.article),
			4: this.data.exports?.pdf === "a_jour",
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
			const o = { 1: "plan", 2: "plan", 3: "plan", 4: this.d.plan_a_plat ? "artwork" : "plan" }[this.etape];
			if (o !== this.onglet) { this.onglet = o; this.rendre_scene(); }
		});
		$g.find(".se-type").on("click", (e) => this.modifier({ type_boite: $(e.currentTarget).attr("data-type") }, true));
		const sauver = this.sauvegarde_differee(this.nom);
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
			const choisis = $c.parent().find(".c.on").map((_i, el) => $(el).attr(attr)).get();
			// Ajouter une langue conserve la langue principale et l’ordre d’impression existants.
			const existants = liste === "langues" ? Object.keys(this.data.textes_imprimes || { fr: {} }) : [];
			const codes = [...existants.filter(c => choisis.includes(c)), ...choisis.filter(c => !existants.includes(c))];
			if (liste === "langues" && !codes.length) { $c.addClass("on"); return; }
			this.modifier({ [liste]: codes }, liste === "langues");
		});
		$g.find("[data-choisir-media]").on("click", e => this.mediatheque($(e.currentTarget).attr("data-choisir-media")));
		$g.find("[data-modifier-media]").on("click", e => this.modifier_media($(e.currentTarget).attr("data-modifier-media")));
		$g.find("[data-televerser]").on("click", (e) => this.televerser($(e.currentTarget).attr("data-televerser")));
		$g.find("[data-effacer]").on("click", (e) => { e.preventDefault(); this.modifier({ [$(e.currentTarget).attr("data-effacer")]: "" }, true); });
		$g.find("[data-bibliotheque]").on("click", (e) => this.bibliotheque($(e.currentTarget).attr("data-bibliotheque")));
		$g.find("[data-garder]").on("click", (e) => this.garder($(e.currentTarget).attr("data-garder")));
		$g.find("[data-action]").on("click", (e) => this.action($(e.currentTarget).attr("data-action")));
		$g.find("[data-vectoriser]").on("click", (e) => this.atelier_vectorisation($(e.currentTarget).attr("data-vectoriser")));
		// Une vignette s'ouvre en grand, avec la pipette (demande utilisateur 06/10/2026).
		$g.find("[data-voir]").on("click", (e) => {
			const champ = $(e.currentTarget).attr("data-voir");
			this.visionneuse(this.d[champ], { logo: __("Logo"), photo_produit: __("Photo du produit"), image_fond: __("Image de fond") }[champ] || "");
		});
		// La palette se redessine pendant la frappe ; une pastille cliquée sort de la palette.
		$g.find('[data-champ="palette"]').on("input", (e) => $g.find('[data-role="palette-pastilles"]').html(this._pastilles_palette(e.currentTarget.value)));
		$g.find("[data-palette-pipette]").on("click", () => this.ouvrir_palette());
		$g.on("click", '[data-role="palette-pastilles"] [data-retirer]', (e) => {
			const c = $(e.currentTarget).attr("data-retirer");
			this.changer_palette(c, true).catch(erreur => frappe.msgprint(this._msg(erreur)));
		});
		this.monter_editeur();
	}

	// ─── caractéristiques : éditeur ligne par ligne, polices ─────────────────────
	rendre_scene() {
		this._glissement_zone?.annuler(false);
		this._volume_observer?.disconnect();
		const d = this.d;
		const onglets = [["plan", __("Édition")], ["artwork", __("Aperçu imprimé")], ["3d", __("3D")]];
		this.$root.find(".se-onglets").html(onglets.map(([k, l]) => `<div class="o ${k === this.onglet ? "on" : ""}" data-onglet="${k}">${l}</div>`).join(""))
			.find(".o").on("click", (e) => { this.onglet = $(e.currentTarget).attr("data-onglet"); this.rendre_scene(); });
		const $s = this.$root.find(".se-scene");
		const defilement = $s[0]?.dataset.design === this.nom && $s[0].dataset.vue === this.onglet ? $s[0].scrollTop : 0;
		try {
			if (this.onglet === "plan") return this.scene_plan($s);
			if (this.onglet === "variantes") return this.scene_variantes($s);
			if (this.onglet === "images") return this.scene_images($s);
			if (this.onglet === "artwork") return $s.html(d.apercu_plan ? `${this.data.exports?.pdf !== "a_jour" ? `<p class="alert alert-warning">${__("Aperçu précédent : actualisez le PDF à l’étape 4.")}</p>` : ""}<img class="se-img" src="${this._esc(d.apercu_plan)}" alt=""><p class="text-muted small text-center" style="margin-top:8px">${__("Aperçu à l'écran. Le PDF imprimeur est à l'échelle, avec le calque de découpe.")}</p>` : `<div class="se-vide">${__("Créez le PDF à l’étape 4 pour voir l’aperçu imprimé.")}</div>`);
			if (this.onglet === "3d") return this.scene_3d($s);
		} finally {
			$s.attr({"data-design": this.nom, "data-vue": this.onglet}).scrollTop(defilement);
		}
	}

	rendre_droite() {
		this.memoriser_panneau_proprietes();
		this.$root.find(".se-droite").html(`<div class="bloc" data-role="face">${__("Sélectionnez une face, puis un élément pour régler sa position et son apparence.")}</div>`);
		delete this.$root.find(".se-droite")[0].dataset.sectionsContexte;
		const f = this.epinglee && ((this.data.apercu || {}).faces || []).find(x => x.code === this.epinglee);
		if (f) this.face_info(f);
	}

	async action(nom) {
		try {
			await this.attendre_sauvegardes();
			if (nom === "preparer") {
				await frappe.call({ method: "aquaworld_ia.emballage.textes.preparer", args: { design: this.nom }, freeze: true,
					freeze_message: __("L'IA rédige les textes et propose des styles…") });
				frappe.show_alert({ message: __("Propositions prêtes : relisez-les avant de les appliquer."), indicator: "green" });
				await this.recharger(); this.etape = 2; this.rendre(); this.dialogue_textes(true);
			} else if (nom === "propositions_textes") {
				this.dialogue_textes(true);
			} else if (nom === "variantes") {
				this.ouvrir_variantes();
			} else if (nom === "voir_simulation") {
				this.onglet = "3d"; this.rendre_scene();
			} else if (nom === "textes") {
				this.dialogue_textes();
			} else if (nom === "generer") {
				const a_faire = (this.d.variantes || []).filter((v) => ["À générer", "Échec"].includes(v.statut)).map((v) => v.numero);
				const e = (await frappe.call({ method: "aquaworld_ia.emballage.job.estimation_variantes", args: { nombre: a_faire.length } })).message || {};
				frappe.confirm(__("Générer {0} variante(s), qualité {1}, coût estimé <b>{2} $</b> (dépensé ce mois : {3} $) ?", [a_faire.length, e.qualite, (e.cout || 0).toFixed(2), (e.mois || 0).toFixed(2)]), async () => {
					await frappe.call({ method: "aquaworld_ia.emballage.job.lancer_variantes", args: { design: this.nom, numeros: a_faire } });
					this.ouvrir_variantes(); this.suivre();
				});
			} else if (nom === "logo_ia") {
				this.atelier_image("logo");
			} else if (nom === "logo_couleur") {
				this.atelier_couleur();
			} else if (nom === "photo_ia") {
				this.atelier_image("photo_produit");
			} else if (nom === "mosaique") {
				this.atelier_mosaique();
			} else if (nom === "fond") {
				this.atelier_fond();
			} else if (nom === "integrer") {
				this.atelier_face(this.epinglee || "avant");
			} else if (nom === "composer" || nom === "preparer_3d") {
				if (this.d.ameliorer_images_pdf) {
					await frappe.call({method:"aquaworld_ia.emballage.resolution.lancer_pdf",args:{design:this.nom}});
					this.etape = 4; this.onglet = nom === "preparer_3d" ? "3d" : "artwork";
					await this.recharger(); this.suivre();
					return;
				}
				const r = await frappe.call({ method: "aquaworld_ia.emballage.composition.composer_et_attacher",
					args: { design: this.nom, variante: this.d.variante_choisie }, freeze: true, freeze_message: __("Composition du plan à l'échelle…") });
				frappe.show_alert({ message: __("Plan à plat prêt : feuille {0} × {1} mm.", [r.message.feuille.w, r.message.feuille.h]), indicator: "green" });
				await this.recharger(); this.etape = 4; this.onglet = nom === "preparer_3d" ? "3d" : "artwork"; this.rendre();
				this.signaler_reductions(r.message.reductions || []);
			} else if (nom === "bilan_resolution") {
				this.bilan_resolution();
			} else if (nom === "faces") {
				frappe.confirm(__("Générer les 5 autres faces dans le style de la variante choisie, puis recomposer le plan ? (5 images facturées)"), async () => {
					await frappe.call({ method: "aquaworld_ia.emballage.job.lancer_faces", args: { design: this.nom } });
					this.suivre();
				});
			} else if (nom === "mockup") {
				const e = this.etat_3d();
				if (!e.pdf_pret || e.bloque) { frappe.msgprint(e.raison); return; }
				await frappe.call({ method: "aquaworld_ia.emballage.job.lancer_mockup", args: { design: this.nom } });
				this.suivre(); this._mockup_en_cours = true;
				this.onglet = "3d"; this.rendre_scene(); this.rendre_export();
			}
		} catch (e) {
			frappe.msgprint(this._msg(e));
		}
	}

	// Les tailles choisies ligne par ligne sont des maximums : un bloc trop long pour sa zone est réduit
	// en entier. Le dire, sinon « 14 pt » imprimé plus petit paraît ignoré.
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

for (const composant of [StudioEtat, StudioEdition, StudioProprietes, StudioDeplacement, StudioPictogrammes, StudioApercu, StudioMedias, StudioResolution, StudioCouleurs, StudioMaquette3D]) {
	for (const nom of Object.getOwnPropertyNames(composant.prototype)) {
		if (nom !== "constructor") Object.defineProperty(StudioEmballage.prototype, nom, Object.getOwnPropertyDescriptor(composant.prototype, nom));
	}
}

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
