// Agrandissement local des images et bilan de résolution du PDF final.
class StudioResolution {
	async ameliorer_resolution(champ) {
		try { await this.attendre_sauvegardes(); } catch (e) { frappe.msgprint(this._msg(e)); return; }
		const design = this.nom, source = this.d[champ], esc = this._esc;
		if (!source) return;
		let occupe = false;
		const dlg = new frappe.ui.Dialog({ title: __("Améliorer la résolution"), size: "large", fields: [
			{ fieldtype: "HTML", options: `<img src="${esc(source)}" alt="" style="display:block;width:100%;height:200px;object-fit:contain">
				<p>${__("Augmente les pixels de l’image. Comparez les détails avant de l’utiliser ; l’original reste dans la médiathèque.")}</p>` },
			{ fieldtype: "Select", fieldname: "facteur", label: __("Agrandissement"), options: [{value:"2",label:"×2"},{value:"4",label:"×4"}], default: "2", reqd: 1 },
			{ fieldtype: "Select", fieldname: "methode", label: __("Traitement gratuit sur le serveur"),
				options: [{value:"ia",label:__("Photo · IA locale")},{value:"fidele",label:__("Logo / certification · agrandissement fidèle")}],
				default: champ === "photo_produit" ? "ia" : "fidele", reqd: 1,
				description: __("L’IA peut modifier de petits détails. Le mode fidèle rééchantillonne les pixels sans redessiner le contenu. Résultat limité à 40 millions de pixels.") },
		], primary_action_label: __("Améliorer et comparer"), primary_action: async values => {
			if (occupe || this.nom !== design) return;
			occupe = true; dlg.get_primary_btn().prop("disabled", true);
			try {
				const r = await frappe.call({ method: "aquaworld_ia.emballage.resolution.ameliorer_image", args: {
					design, champ, source_url: source, facteur: values.facteur, methode: values.methode,
				}, freeze: true, freeze_message: __("Amélioration locale de la résolution…") });
				dlg.hide();
				if (this.nom === design) this.comparer_resolution(design, champ, r.message);
			} catch (e) { frappe.msgprint(this._msg(e)); }
			finally { occupe = false; dlg.get_primary_btn().prop("disabled", false); }
		} });
		dlg.show();
	}

	comparer_resolution(design, champ, resultat) {
		const esc = this._esc;
		const vues = [[__("Avant"), resultat.source, resultat.avant], [__("Après"), resultat.candidat, resultat.apres]];
		const dlg = new frappe.ui.Dialog({ title: __("Comparer la résolution"), size: "extra-large", fields: [
			{fieldtype:"HTML",fieldname:"comparaison",options:`<div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px">
				${vues.map(([titre,url,dimensions]) => `<div><b>${titre} · ${dimensions.join(" × ")} px</b>
				<div data-resolution-vue style="height:300px;overflow:auto;background:repeating-conic-gradient(#eee 0% 25%,white 0% 50%) 0 0 / 16px 16px">
				<img src="${esc(url)}" alt="${titre}" style="display:block;width:100%;max-width:none"></div></div>`).join("")}</div>
				<label style="display:block;margin-top:12px">${__("Zoom de comparaison")} <input data-resolution-zoom type="range" min="100" max="400" value="100" style="width:100%"></label>
				<p class="small text-muted">${resultat.methode === "ia" ? __("IA locale : vérifiez les contours et les détails du produit.") : __("Agrandissement fidèle : davantage de pixels, sans reconstruction des détails manquants.")}</p>`},
		],primary_action_label:__("Utiliser cette image"),primary_action:async () => {
			dlg.get_primary_btn().prop("disabled",true);
			try {
				await this.attendre_sauvegardes();
				if (this.nom !== design) throw new Error(__("Le design a changé. Rouvrez l’outil."));
				await frappe.call({method:"aquaworld_ia.emballage.resolution.adopter_image",args:{design,champ,
					candidat:resultat.candidat,source:resultat.source,modifie_le:resultat.modifie_le},freeze:true});
				dlg.hide();
				if (this.nom === design) await this.recharger();
				frappe.show_alert({message:__("Image améliorée appliquée. Actualisez le PDF pour l’inclure."),indicator:"green"});
			} catch(e) { frappe.msgprint(this._msg(e)); }
			finally { dlg.get_primary_btn().prop("disabled",false); }
		}});
		const $v = dlg.fields_dict.comparaison.$wrapper;
		$v.find("[data-resolution-zoom]").on("input", e => $v.find("img").css("width", `${e.target.value}%`));
		let actif;
		$v.find("[data-resolution-vue]").on("mouseenter pointerdown", e => {actif=e.currentTarget;}).on("scroll",e=>{
			if(e.currentTarget!==actif) return;
			$v.find("[data-resolution-vue]").not(actif).each((_i,el)=>{el.scrollLeft=actif.scrollLeft;el.scrollTop=actif.scrollTop;});
		});
		dlg.show();
	}

	rapport_resolution() {
		try { return JSON.parse(this.d.rapport_resolution || "null"); } catch (_e) { return null; }
	}

	bilan_resolution() {
		const rapport = this.rapport_resolution(), esc = this._esc;
		if (!rapport) return;
		new frappe.ui.Dialog({title:__("Résolution des images du PDF"),size:"large",fields:[{fieldtype:"HTML",options:
			`<p>${__("{0} image(s) agrandie(s). {1} image(s) restent sous 300 ppp.",[rapport.ameliorees,rapport.insuffisantes])}</p>
			${this.data.exports?.pdf !== "a_jour" ? `<p class="text-warning">${__("Bilan du PDF précédent : actualisez-le après vos modifications.")}</p>` : ""}
			<div style="overflow:auto"><table class="table table-bordered"><thead><tr><th>${__("Image")}</th><th>${__("Avant")}</th><th>${__("Après")}</th><th>${__("Bilan")}</th></tr></thead><tbody>
			${rapport.images.map(im=>`<tr><td>${im.vignette ? `<img src="${esc(im.vignette)}" alt="" style="display:block;width:64px;height:64px;object-fit:contain;background:#f3f4f6">` : ""}${im.numero} · ×${im.facteur}<br><small>${__("{0} utilisation(s)",[im.occurrences])}</small></td>
			<td>${im.avant.join(" × ")} px<br>${im.ppp_avant} ppp</td><td>${im.apres.join(" × ")} px<br>${im.ppp_apres} ppp</td>
			<td>${esc(im.motif || __("Résolution cible atteinte"))}</td></tr>`).join("")}</tbody></table></div>
			<p class="small text-muted">${__("Mesure à la taille imprimée, zoom et rotation inclus. Agrandissement fidèle jusqu’à ×4 ; textes et tracés vectoriels conservés. Les originaux du design restent inchangés. L’augmentation des pixels ne garantit pas de nouveaux détails ni la conformité complète aux exigences de votre imprimeur.")}</p>`}]}).show();
	}
}
