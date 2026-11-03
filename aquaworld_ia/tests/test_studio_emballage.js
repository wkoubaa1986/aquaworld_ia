// Régressions des saisies rapides et de la navigation pendant une sauvegarde.
// Exécution : node --test aquaworld_ia/tests/test_studio_emballage.js
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

function lireScript(fichier) {
	return readFileSync(fichier, "utf8").replace(/\{% include "aquaworld_ia\/(.*?)" %\}/g,
		(_match, relatif) => lireScript(path.join(__dirname, "..", relatif)));
}

function studio() {
	let envoyer;
	const frappe = { pages: { "studio-emballage": {} }, utils: {
		debounce: (fn) => () => { envoyer = fn; },
	} };
	const context = vm.createContext({ frappe, __: (s) => s });
	const source = lireScript(path.join(__dirname, "../aquaworld_ia/page/studio_emballage/studio_emballage.js"));
	vm.runInContext(`${source}\nthis.Studio = StudioEmballage;`, context);
	const instance = Object.create(context.Studio.prototype);
	instance.nom = "A";
	return { instance, frappe, envoyer: () => envoyer() };
}

test("une certification choisie sur le dos ne remplace ni l'avant ni les autres contenants", async () => {
	const {instance} = studio();
	instance.d = {modified: "v1", pictogrammes: [{pictogramme: "ce"}, {pictogramme: "eau"}]};
	const picto = {zone: "pictos", x: 220, y: 35, w: 50, h: 20, decalage_contenu: {x: 2, y: -1}};
	const logo = {zone: "logo", x: 220, y: 5, w: 50, h: 20, logo: "/logo.svg", rotation: 37, zoom_image: 1.5};
	instance.data = {pictos: [{code: "ce"}, {code: "eau"}], apercu: {faces: [{code: "arriere", copie_de: "avant", zones: [logo, picto, {...picto, y: 75}, {zone: "photo", auto: 1}]}]}};
	instance.mep = {avant: [{...picto, x: 20, pictos: ["ce"]}]};
	const avant = JSON.stringify(instance.mep);
	instance.attendre_sauvegardes = async () => {};
	let payload;
	instance.enregistrer = async (v, design) => {payload = v; assert.equal(design, "A");};
	const cible = {design: "A", face: "arriere", indice: 1, revision: "v1"};
	await instance.appliquer_pictos_zone(cible, ["eau", "eau"]);
	assert.equal(JSON.stringify(payload.mise_en_page.arriere[1]), JSON.stringify({...picto, pictos_mode: "selection", pictos: ["eau"]}));
	assert.equal(JSON.stringify(payload.mise_en_page.arriere[0]), JSON.stringify(logo));
	assert.equal(payload.mise_en_page.arriere.length, 3); // Ne pas convertir la photo automatique en photo explicite.
	assert.equal(payload.mise_en_page.arriere[2].pictos_mode, undefined);
	assert.equal(JSON.stringify(instance.mep), avant);
	await instance.appliquer_pictos_zone(cible, []);
	assert.equal(payload.mise_en_page.arriere[1].pictos_mode, "selection");
	assert.equal(payload.mise_en_page.arriere[1].pictos.length, 0);
	assert.equal(instance.zone_a_enregistrer(payload.mise_en_page.arriere[1]).pictos_mode, "selection");
	await instance.appliquer_pictos_zone(cible, null);
	assert.equal(payload.mise_en_page.arriere[1].pictos_mode, undefined);
	assert.equal(payload.mise_en_page.arriere[1].pictos, undefined);
});

test("le sélecteur de certifications refuse un design changé et montre les choix réellement hérités", async () => {
	const {instance} = studio();
	instance.d = {modified: "v1", pictogrammes: [{pictogramme: "ce"}, {pictogramme: "tampon"}]};
	instance.data = {pictos: [{code: "ce"}, {code: "tampon", categorie: "Tampon"}]};
	assert.equal(JSON.stringify(instance.pictos_effectifs_zone({}).map(p => p.code)), '["ce"]');
	assert.equal(JSON.stringify(instance.pictos_effectifs_zone({pictos: []}).map(p => p.code)), '["ce"]');
	assert.equal(instance.pictos_effectifs_zone({pictos: [], pictos_mode: "selection"}).length, 0);
	assert.equal(JSON.stringify(instance.pictos_effectifs_zone({pictos: ["tampon"]}).map(p => p.code)), '["tampon"]');
	instance.enregistrer = async () => assert.fail("Ne doit pas enregistrer un choix périmé");
	instance.attendre_sauvegardes = async () => {instance.d.modified = "v2";};
	await assert.rejects(instance.appliquer_pictos_zone({design: "A", revision: "v1"}, ["ce"]), /changé/);
	instance.attendre_sauvegardes = async () => {instance.nom = "B";};
	await assert.rejects(instance.appliquer_pictos_zone({design: "A", revision: "v2"}, ["ce"]), /changé/);
});

test("enregistrer un QR garde son type et son décalage sans les données d'aperçu", () => {
	const {instance} = studio();
	const z = {zone: "code_barres", code: "qr", x: 10, y: 20, w: 30, h: 30, decalage_contenu: {x: 1, y: 2}};
	assert.deepEqual(JSON.parse(JSON.stringify(instance.zone_a_enregistrer({...z, apercu_elements: [{image: "pixels"}], auto: 1}))), z);
});

test("la disposition des pictogrammes est propre à la zone et survit au changement de sélection", async () => {
	const {instance} = studio();
	instance.d = {modified: "v1", pictogrammes: [{pictogramme: "ce"}, {pictogramme: "eau"}]};
	const z = {zone: "pictos", x: 10, y: 20, w: 30, h: 80, decalage_contenu: {x: 2, y: -1}};
	instance.data = {pictos: [{code: "ce"}, {code: "eau"}], apercu: {faces: [{code: "avant", zones: [z, {...z, x: 50}]}]}};
	instance.mep = {}; instance.attendre_sauvegardes = async () => {};
	let envoi;
	instance.enregistrer = async v => {envoi = v; instance.data.apercu.faces[0].zones = v.mise_en_page.avant;};
	const cible = {design: "A", face: "avant", indice: 0, revision: "v1"};
	await instance.appliquer_pictos_zone(cible, null, "vertical");
	assert.equal(envoi.mise_en_page.avant[0].pictos_disposition, "vertical");
	assert.equal(envoi.mise_en_page.avant[0].pictos_mode, undefined);
	assert.equal(envoi.mise_en_page.avant[1].pictos_disposition, undefined);
	for (const cle of ["x", "y", "w", "h"]) assert.equal(envoi.mise_en_page.avant[0][cle], z[cle]);
	assert.equal(JSON.stringify(envoi.mise_en_page.avant[0].decalage_contenu), JSON.stringify(z.decalage_contenu));
	await instance.appliquer_pictos_zone(cible, ["ce"]);
	assert.equal(envoi.mise_en_page.avant[0].pictos_disposition, "vertical");
	assert.equal(instance.zone_a_enregistrer(envoi.mise_en_page.avant[0]).pictos_disposition, "vertical");
	await instance.appliquer_pictos_zone(cible, [], "horizontal");
	assert.equal(envoi.mise_en_page.avant[0].pictos_disposition, undefined);
	assert.equal(envoi.mise_en_page.avant[0].pictos_mode, "selection");
	assert.equal(envoi.mise_en_page.avant[0].pictos.length, 0);
});

test("une variante de certification conserve les autres zones et le lien des faces identiques", async () => {
	const {instance} = studio();
	const z = {zone: "pictos", x: 10, y: 20, w: 40, h: 50, pictos_disposition: "vertical", decalage_contenu: {x: 1, y: 2}, pictos_rotations: {ce: 37.5}};
	instance.d = {modified: "v1", pictogrammes: [{pictogramme: "ce"}]};
	instance.data = {pictos: [{code: "ce", url: "/original.svg"}], apercu: {faces: [
		{code: "avant", zones: [z, {...z, x: 60}]},
		{code: "arriere", copie_de: "avant", zones: [{...z, x: 210}, {zone: "photo", auto: 1}]},
	]}};
	instance.mep = {}; instance.attendre_sauvegardes = async () => {};
	let payload;
	instance.enregistrer = async v => {payload = v; instance.data.apercu.faces[0].zones = v.mise_en_page.avant;};
	const cible = {design: "A", face: "avant", indice: 0, revision: "v1", code: "ce"};
	await instance.appliquer_variante_picto(cible, "/private/files/vert.svg");
	assert.deepEqual(JSON.parse(JSON.stringify(payload.mise_en_page.avant[0])), {...z, pictos_images: {ce: "/private/files/vert.svg"}});
	assert.equal(payload.mise_en_page.avant[1].pictos_images, undefined);
	assert.equal(payload.mise_en_page.arriere, undefined, "La couleur ne doit pas figer la copie");
	assert.equal(instance.data.apercu.faces[1].copie_de, "avant");
	assert.equal(instance.pictos_effectifs_zone(payload.mise_en_page.avant[0])[0].url, "/private/files/vert.svg");
	assert.equal(instance.data.pictos[0].url, "/original.svg");
	await instance.appliquer_variante_picto(cible, null);
	assert.equal(payload.mise_en_page.avant[0].pictos_images, undefined);
	assert.equal(instance.pictos_effectifs_zone(payload.mise_en_page.avant[0])[0].url, "/original.svg");
});

test("couleur et retour à l'original depuis une copie modifient la source dans ses coordonnées", async () => {
	for (const [source, copie] of [["avant", "arriere"], ["cote_droit", "cote_gauche"]]) {
		const {instance} = studio();
		const z = {zone: "pictos", x: 20, y: 30, w: 30, h: 60, pictos: ["ce", "eau"], pictos_mode: "selection",
			pictos_images: {eau: "/eau.svg"}, pictos_rotations: {ce: 90, eau: 37.5},
			pictos_disposition: "vertical", decalage_contenu: {x: 1, y: -2}};
		const origine = {code: source, zones: [z, {...z, y: 110}, {zone: "photo", auto: 1}]};
		const face = {code: copie, copie_de: source, zones: origine.zones.map(z => ({...z, x: 220}))};
		instance.data = {pictos: [{code: "ce", url: "/ce.svg"}, {code: "eau"}], apercu: {faces: [origine, face]}};
		instance.d = {modified: "v1", pictogrammes: [{pictogramme: "ce"}, {pictogramme: "eau"}]};
		instance.mep = {dessus: [{zone: "logo"}]}; instance.attendre_sauvegardes = async () => {};
		instance.epinglee = "dessus"; // Le dialogue garde sa cible même si la sélection a changé.
		let payload;
		instance.enregistrer = async (v, nom) => {payload = JSON.parse(JSON.stringify(v)); assert.equal(nom, "A"); origine.zones = v.mise_en_page[source];};
		const cible = {design: "A", face: copie, indice: 0, code: "ce", revision: "v1"};
		await instance.appliquer_variante_picto(cible, "/bleu.svg");
		assert.deepEqual(payload.mise_en_page[source][0], {...z, pictos_images: {eau: "/eau.svg", ce: "/bleu.svg"}});
		assert.deepEqual(payload.mise_en_page[source][1], {...z, y: 110});
		assert.equal(payload.mise_en_page[source].length, 2); // La photo automatique reste automatique.
		assert.equal(payload.mise_en_page[copie], undefined);
		assert.deepEqual(payload.mise_en_page.dessus, [{zone: "logo"}]);
		await instance.appliquer_variante_picto(cible, null);
		assert.deepEqual(payload.mise_en_page[source][0], z);
		assert.equal(payload.mise_en_page[copie], undefined);
		assert.equal(face.copie_de, source);
	}
});

test("recolorer une face indépendante ne remplace pas la couleur de l'autre face", async () => {
	const {instance} = studio();
	const z = {zone: "pictos", x: 20, y: 30, w: 30, h: 60};
	const source = {code: "cote_droit", zones: [z]}, face = {code: "cote_gauche", copie_bloquee: "cote_droit", zones: [{...z, x: 220}]};
	instance.data = {pictos: [{code: "ce"}], apercu: {faces: [source, face]}};
	instance.d = {modified: "v1", cotes_identiques: 1, pictogrammes: [{pictogramme: "ce"}]};
	instance.mep = {cote_droit: [{...z, pictos_images: {ce: "/rouge.svg"}}], cote_gauche: face.zones};
	instance.attendre_sauvegardes = async () => {};
	let payload; instance.enregistrer = async v => {payload = JSON.parse(JSON.stringify(v));};
	await instance.appliquer_variante_picto({design: "A", face: face.code, indice: 0, code: "ce", revision: "v1"}, "/bleu.svg");
	assert.equal(payload.mise_en_page.cote_droit[0].pictos_images.ce, "/rouge.svg");
	assert.equal(payload.mise_en_page.cote_gauche[0].pictos_images.ce, "/bleu.svg");
	assert.equal(payload.mise_en_page.cote_gauche[0].x, 220);
});

test("une ancienne proposition de couleur ne s'applique pas à un design ou une sélection modifiée", async () => {
	const {instance} = studio();
	instance.d = {modified: "v2"}; instance.attendre_sauvegardes = async () => {};
	instance.enregistrer = async () => assert.fail("Aucune adoption périmée");
	await assert.rejects(instance.appliquer_variante_picto({design: "A", revision: "v1"}, "/variante.svg"), /changé/);
	await assert.rejects(instance.appliquer_variante_picto({design: "B", revision: "v2"}, "/variante.svg"), /changé/);
});

test("la photo automatique reste derrière les symboles sans changer leurs indices", () => {
	const { instance } = studio();
	const zones = [{zone: "pictos"}, {zone: "nom"}, {zone: "photo", auto: 1}];
	const ordre = instance.ordre_zones(zones);
	assert.equal(JSON.stringify(ordre.map(x => x.i)), "[2,0,1]");
	assert.equal(zones[0].zone, "pictos");
});

test("les couleurs saisies ou prélevées sont normalisées et dédoublonnées", () => {
	const {instance} = studio();
	instance.d = {palette: "#ABC, aabbcc; #F00 123456 faux"};
	assert.equal(JSON.stringify(instance._palette()), JSON.stringify(["#aabbcc", "#ff0000", "#123456"]));
	for (const v of ["", "red", "#12345", "#12345g", "#12345678", "#fff; color:red"]) assert.equal(instance.normaliser_couleur(v), null);
	assert.equal(instance.normaliser_couleur("  #008BCD  "), "#008bcd");
});

test("les ajouts rapides à la palette préservent la saisie en attente et les autres couleurs", async () => {
	const {instance, frappe} = studio();
	instance.d = {palette: "#000000"};
	let attente = true;
	instance.attendre_sauvegardes = async () => {if (attente) {instance.d.palette = "#123456"; attente = false;}};
	const envois = [];
	instance.enregistrer = async ({palette}, design) => {envois.push({palette, design}); instance.d.palette = palette;};
	instance.rendre_gauche = () => {}; frappe.show_alert = () => {};
	await Promise.all([instance.ajouter_a_la_palette("#ABC"), instance.ajouter_a_la_palette("#def"), instance.ajouter_a_la_palette("aabbcc")]);
	assert.equal(instance.d.palette, "#123456, #aabbcc, #ddeeff");
	assert.equal(envois.length, 2); assert(envois.every(e => e.design === "A"));
	await instance.changer_palette("#abc", true);
	assert.equal(instance.d.palette, "#123456, #ddeeff");
});

test("un échec de palette ou une navigation ne produit ni succès trompeur ni écriture sur un autre design", async () => {
	const {instance, frappe} = studio();
	instance.d = {palette: ""}; instance.rendre_gauche = () => {};
	let alertes = 0, appels = 0; frappe.show_alert = () => alertes++;
	instance.enregistrer = async () => {appels++; throw new Error("réseau");};
	await assert.rejects(instance.ajouter_a_la_palette("#f00"), /réseau/);
	assert.equal(alertes, 0);
	instance.attendre_sauvegardes = async () => {instance.nom = "B";};
	await assert.rejects(instance.ajouter_a_la_palette("#0f0"), /Rouvrez le design/);
	assert.equal(appels, 1); assert.equal(alertes, 0);
});

test("chaque type ajouté sélectionne sa zone pour renseigner immédiatement son contenu", () => {
	const { instance, frappe } = studio();
	instance.d = {type_code_barres: "QR", url_qr: "https://example.com"};
	frappe.show_alert = () => {};
	let sauvegardes = 0;
	const zones = [{zone: "logo"}];
	instance._zones_en_cours = {face: {x: 10, y: 20, w: 100, h: 200}, zones, sauver: () => sauvegardes++};
	for (const type of ["logo", "nom", "accroche", "caracteristiques", "avertissements", "contact", "texte_libre", "pictos", "code_barres", "qr", "photo"]) {
		instance.ajouter_zone(type);
		assert.equal(instance.zone_sel, zones.length - 1);
		assert.equal(zones.at(-1).zone, type === "qr" ? "code_barres" : type);
	}
	assert.equal(sauvegardes, 11);
});

test("modifier une accroche par langue conserve les autres champs et vide les valeurs effacées", async () => {
	const { instance, frappe } = studio();
	let dialog, ecriture, recharges = 0;
	const textes = {fr: {accroche: "Avant", caracteristiques: ["Débit"], avertissements: ["Attention"], contact: "Contact FR"},
		ar: {accroche: "ماء", caracteristiques: ["اختبار"], avertissements: [], contact: "Contact AR"}};
	instance.data = {textes_imprimes: textes}; instance.d = {};
	instance.attendre_sauvegardes = async () => {};
	instance.injecter_polices = () => {};
	instance.recharger = async () => recharges++;
	frappe.ui = {Dialog: class {constructor(opts) {dialog = opts;} show() {} hide() {}}};
	frappe.call = async ({args}) => {ecriture = args;};
	await instance.dialogue_textes(false, "accroche");
	assert.equal(dialog.fields.filter(f => f.fieldname).length, 2);
	instance.nom = "B";
	await dialog.primary_action({acc_fr: "Après", acc_ar: ""});
	assert.equal(ecriture.design, "A");
	assert.equal(ecriture.textes.fr.accroche, "Après");
	assert.equal(ecriture.textes.ar.accroche, "");
	for (const c of ["fr", "ar"]) for (const champ of ["caracteristiques", "avertissements", "contact"]) assert.equal(JSON.stringify(ecriture.textes[c][champ]), JSON.stringify(textes[c][champ]));
	assert.equal(recharges, 0);
});

test("les symboles visibles suivent le déplacement et le redimensionnement de leur zone", () => {
	const { instance } = studio();
	instance.data = {apercu: {images_zones: {test: "data:image/svg+xml;base64,AAA"}}};
	const elements = [];
	const el = (tag, attrs) => { const n = {tag, attrs: {...attrs}, appendChild() {}, setAttribute(k, v) {this.attrs[k] = v;}}; elements.push(n); return n; };
	const z = {zone: "pictos", x: 10, y: 20, w: 40, h: 20,
		apercu_elements: [{image: "test", code: "wqa", rect: [12, 22, 16, 16], fond: [10, 20, 20, 20]}]};
	const actualiser = instance.dessiner_symboles_zone(el, z, 3);
	const image = elements.find(n => n.tag === "image"), fond = elements.find(n => n.tag === "rect");
	assert.equal(image.attrs.href, instance.data.apercu.images_zones.test);
	assert.equal(image.attrs.x, 12); assert.equal(image.attrs.width, 16);
	z.x = 30; z.y = 50; z.w = 80; z.h = 40; actualiser();
	assert.equal(image.attrs.x, 34); assert.equal(image.attrs.y, 54);
	assert.equal(image.attrs.width, 32); assert.equal(image.attrs.height, 32);
	assert.equal(image.attrs.preserveAspectRatio, "xMidYMid meet");
	assert.equal(fond.attrs.x, 30); assert.equal(fond.attrs.y, 50);
});

test("les angles des pictogrammes sont normalisés et conservés avec les autres propriétés", () => {
	const {instance} = studio();
	const z = {zone: "pictos", x: 10, y: 20, w: 60, h: 30, pictos_rotations: {
		ce: -90, tampon: "397.25", tour: 720, arrondi: 359.9999, vide: "", nul: null, bool: true, nan: NaN, inf: Infinity, liste: [],
	}, pictos_images: {ce: "/couleur.svg"}, decalage_contenu: {x: 2, y: -1}};
	assert.deepEqual(JSON.parse(JSON.stringify(instance.rotations_pictos(z))), {ce: 270, tampon: 37.25});
	const sauvegarde = instance.zone_a_enregistrer(z);
	assert.deepEqual(JSON.parse(JSON.stringify(sauvegarde.pictos_rotations)), {ce: 270, tampon: 37.25});
	assert.equal(sauvegarde.pictos_images.ce, z.pictos_images.ce);
	assert.equal(sauvegarde.decalage_contenu.x, 2);
	assert.equal(instance.zone_a_enregistrer({...z, zone: "code_barres"}).pictos_rotations, undefined);
});

test("un symbole tourne autour de son centre, reste ajusté et suit le cadre", () => {
	const {instance} = studio(), url = "data:image/svg+xml;base64,AAA";
	instance.data = {apercu: {images_zones: {test: url}}};
	instance._tailles_images = new Map([[url, {w: 120, h: 30}]]);
	const elements = [], el = (tag, attrs) => {
		const n = {tag, attrs: {...attrs}, appendChild() {}, setAttribute(k, v) {this.attrs[k] = v;}}; elements.push(n); return n;
	};
	const z = {zone: "pictos", x: 10, y: 20, w: 60, h: 30, pictos_rotations: {a: 90}, apercu_elements: [
		{image: "test", code: "a", rect: [12, 22, 20, 20]}, {image: "test", code: "b", rect: [34, 22, 20, 20]},
	]};
	const actualiser = instance.dessiner_symboles_zone(el, z, 0), [a, b] = elements.filter(n => n.tag === "image");
	assert.equal(a.attrs.transform, "rotate(90 22 32)");
	assert(Math.abs(a.attrs.width-20)<1e-10); assert(Math.abs(a.attrs.height-5)<1e-10);
	assert.equal(b.attrs.transform, "");
	z.pictos_rotations.a = 37.5; z.x += 10; z.w *= 2; actualiser();
	assert.equal(a.attrs.transform, "rotate(37.5 44 32)");
	const r = 37.5*Math.PI/180;
	assert(a.attrs.width*Math.cos(r)+a.attrs.height*Math.sin(r) <= 40+1e-10);
	assert(a.attrs.width*Math.sin(r)+a.attrs.height*Math.cos(r) <= 20+1e-10);
	assert.equal(b.attrs.transform, "");
	delete z.pictos_rotations.a; actualiser();
	assert.equal(a.attrs.transform, ""); assert.equal(a.attrs.width, 40); assert.equal(a.attrs.height, 20);
});

test("les rotations rapides gardent chaque instantané et le lien des faces identiques", async () => {
	const {instance} = studio(), z = {zone: "pictos", x: 10, y: 20, w: 60, h: 30, pictos_rotations: {b: 37.5}, pictos_images: {a: "/couleur.svg"}};
	instance.epinglee = "avant"; instance.zone_sel = 0; instance.mep = {};
	instance.d = {pictogrammes: [{pictogramme: "a"}, {pictogramme: "b"}]};
	instance.data = {peut_ecrire: true, pictos: [{code: "a"}, {code: "b"}], apercu: {faces: [{code: "arriere", copie_de: "avant", zones: [{...z, x: 210}]}]}};
	const input = {filter() {return this;}, val(v) {this.value = v; return this;}, removeAttr() {return this;}};
	instance.$root = {find: () => input};
	const envois = [], fins = [];
	instance._zones_en_cours = {face: {code: "avant"}, zones: [z], actualiser: [() => {}], sauver: () => {
		envois.push(instance.zone_a_enregistrer(z)); return new Promise(resolve => fins.push(resolve));
	}};
	const actions = [90, 180, 270].map(a => instance.regler_rotation_picto("a", a));
	assert.deepEqual(envois.map(z => z.pictos_rotations.a), [90, 180, 270]);
	assert(envois.every(z => z.pictos_rotations.b === 37.5 && z.pictos_images.a === "/couleur.svg"));
	assert.equal(instance.mep.arriere, undefined, "La rotation ne doit pas figer la copie");
	assert.equal(instance.data.apercu.faces[0].copie_de, "avant");
	assert.equal(instance.data.apercu.faces[0].zones[0].pictos_rotations.a, 270);
	fins.forEach(fn => fn()); await Promise.all(actions);
	instance._zones_en_cours.sauver = async () => {};
	await instance.regler_rotation_picto("a", 0);
	assert.equal(z.pictos_rotations.a, undefined); assert.equal(z.pictos_rotations.b, 37.5);
});

test("tourner depuis une face identique met à jour la source sans détacher la copie", async () => {
	for (const [source, copie] of [["avant", "arriere"], ["cote_droit", "cote_gauche"]]) {
		const {instance} = studio();
		const z = {zone: "pictos", x: 20, y: 30, w: 30, h: 60, pictos_rotations: {b: 37.5},
			pictos_disposition: "vertical", pictos_images: {a: "/bleu.svg"}, decalage_contenu: {x: 2, y: 3}};
		const origine = {code: source, zones: [z, {...z, y: 110}, {zone: "photo", auto: 1}]};
		const face = {code: copie, copie_de: source, zones: origine.zones.map(z => ({...z, x: 220}))};
		instance.data = {peut_ecrire: true, pictos: [{code: "a"}, {code: "b"}], apercu: {faces: [origine, face]}};
		instance.d = {pictogrammes: [{pictogramme: "a"}, {pictogramme: "b"}]};
		instance.epinglee = copie; instance.zone_sel = 0; instance.mep = {dessus: [{zone: "logo"}]};
		const input = {filter() {return this;}, val() {return this;}, removeAttr() {return this;}};
		instance.$root = {find: () => input};
		instance._zones_en_cours = {face, zones: face.zones.map(z => ({...z})), actualiser: [], sauver: () => assert.fail("Ne pas enregistrer de surcharge sur la copie")};
		const envois = [], fins = [];
		instance.modifier = (v, differe, design) => {
			assert.equal(design, "A"); assert.equal(differe, false);
			envois.push(JSON.parse(JSON.stringify(v.mise_en_page)));
			return new Promise(resolve => fins.push(resolve));
		};
		const actions = [90, 180, 270, 0].map(a => instance.regler_rotation_picto("a", a));
		assert.deepEqual(envois.map(m => m[source][0].pictos_rotations.a || 0), [90, 180, 270, 0]);
		assert(envois.every(m => !Object.hasOwn(m, copie) && m[source].length === 2 && m[source][0].x === 20));
		assert(envois.every(m => m[source][0].pictos_rotations.b === 37.5 && m[source][0].pictos_images.a === "/bleu.svg"));
		assert.deepEqual(envois[0][source][0].decalage_contenu, {x: 2, y: 3});
		assert.equal(envois[0][source][0].pictos_disposition, "vertical");
		assert(envois.every(m => m[source][1].pictos_rotations.a === undefined));
		assert.equal(face.copie_de, source);
		assert.equal(face.zones[0].x, 220);
		assert.equal(face.zones[0].pictos_rotations.a, undefined);
		assert.deepEqual(envois[0].dessus, [{zone: "logo"}]);
		fins.forEach(fn => fn()); await Promise.all(actions);
	}
});

test("la rotation garde indépendantes les faces volontairement personnalisées", async () => {
	const {instance} = studio();
	const z = {zone: "pictos", x: 20, y: 30, w: 30, h: 60};
	const face = {code: "cote_droit", zones: [z]}, gauche = {code: "cote_gauche", copie_bloquee: "cote_droit", zones: [{...z, x: 220, pictos_rotations: {a: 37}}]};
	instance.data = {peut_ecrire: true, pictos: [{code: "a"}], apercu: {faces: [face, gauche]}};
	instance.d = {cotes_identiques: 1, pictogrammes: [{pictogramme: "a"}]};
	instance.epinglee = face.code; instance.zone_sel = 0; instance.mep = {cote_gauche: gauche.zones};
	const input = {filter() {return this;}, val() {return this;}, removeAttr() {return this;}};
	instance.$root = {find: () => input};
	let sauvegarde = false;
	instance._zones_en_cours = {face, zones: [z], actualiser: [], sauver: async () => {sauvegarde = true;}};
	await instance.regler_rotation_picto("a", 90);
	assert(sauvegarde); assert.equal(z.pictos_rotations.a, 90);
	assert.equal(gauche.zones[0].pictos_rotations.a, 37);
	assert.equal(instance.mep.cote_gauche[0].pictos_rotations.a, 37);
});

test("zoomer un visuel conserve son centre, sa rotation et la géométrie du cadre", () => {
	const { instance } = studio();
	for (const rotation of [0, 37, 90, 270]) {
		const z = { x: 10, y: 20, w: 60, h: 80, rotation };
		const avant = JSON.stringify(z), ajuste = instance.cadre_image(z, 120, 30);
		for (const zoom_image of [.25, .5, 2, 4]) {
			const c = instance.cadre_image({ ...z, zoom_image }, 120, 30);
			assert.equal(c.w, ajuste.w * zoom_image);
			assert.equal(c.h, ajuste.h * zoom_image);
			assert.equal(c.cx, ajuste.cx);
			assert.equal(c.cy, ajuste.cy);
			assert.equal(c.angle, rotation);
		}
		assert.equal(JSON.stringify(z), avant);
	}
	for (const valeur of [undefined, null, "", "abc", NaN, Infinity]) assert.equal(instance.zoom_image(valeur), 1);
	assert.equal(instance.zoom_image(0), .25);
	assert.equal(instance.zoom_image(12), 4);
});

test("le centre visible du logo reste au milieu du cadre avec le zoom et la rotation", () => {
	const { instance } = studio();
	for (const rotation of [0, 37, 90, 270]) for (const zoom_image of [.5, 1, 2]) {
		const z = {zone: "logo", x: 10, y: 20, w: 60, h: 80, rotation, zoom_image,
			centre_visuel: {x: .6, y: .2, source: "/logo.svg"}};
		const c = instance.cadre_image(z, 200, 100, "/logo.svg");
		assert(Math.abs(c.x + c.w * .6 - c.cx) < 1e-10);
		assert(Math.abs(c.y + c.h * .2 - c.cy) < 1e-10);
		assert.equal(c.cx, 40); assert.equal(c.cy, 60);
		const autre = instance.cadre_image(z, 200, 100, "/autre.svg");
		assert(Math.abs(autre.x + autre.w / 2 - autre.cx) < 1e-10);
	}
});

test("le centrage détecté s'applique à la facette sans changer le zoom ni les dimensions", async () => {
	const { instance, frappe } = studio();
	let sauvegardes = 0;
	const z = {zone: "logo", x: 2, y: 3, w: 40, h: 20, zoom_image: 1.75, rotation: 37};
	instance.d = {logo: "/logo.svg"}; instance.data = {};
	instance.epinglee = "dessus"; instance.zone_sel = 0;
	instance.attendre_sauvegardes = async () => {};
	instance._zones_en_cours = {face: {x: 100, y: 20, w: 142, h: 30}, zones: [z], sauver: async () => sauvegardes++};
	frappe.call = async () => ({message: {centre: {x: .6, y: .2, source: "/logo.svg"}}});
	await instance.centrer_logo_visible();
	assert.equal(sauvegardes, 1);
	assert.equal(z.x + z.w / 2, 171); assert.equal(z.y + z.h / 2, 35);
	assert.equal(z.w, 40); assert.equal(z.h, 20);
	assert.equal(z.zoom_image, 1.75); assert.equal(z.rotation, 37);
	assert.equal(z.centre_visuel.x, .6);
});

test("une détection terminée après un changement de sélection ne modifie aucune zone", async () => {
	const { instance, frappe } = studio();
	let terminer, annoncer, sauvegardes = 0;
	const parti = new Promise(resolve => { annoncer = resolve; });
	instance.d = {logo: "/logo.svg"}; instance.data = {};
	instance.epinglee = "dessus"; instance.zone_sel = 0;
	instance.attendre_sauvegardes = async () => {};
	const z = {zone: "logo"};
	instance._zones_en_cours = {zones: [z], sauver: async () => sauvegardes++};
	frappe.call = () => new Promise(resolve => { terminer = resolve; annoncer(); });
	const traitement = instance.centrer_logo_visible();
	await parti;
	instance.nom = "B";
	terminer({message: {centre: {x: .6, y: .2, source: "/logo.svg"}}});
	await traitement;
	assert.equal(sauvegardes, 0); assert.equal(z.centre_visuel, undefined);
});

test("ajouter un tampon à une face miroir préserve le zoom, la rotation et le décalage hérités", async () => {
	const { instance, frappe } = studio();
	const logo = {zone: "logo", x: 200, y: 0, w: 40, h: 30, rotation: 37, zoom_image: 2.5, decalage_contenu: {x: -3, y: 4}, logo: "/logo.svg"};
	instance.data = {apercu: {faces: [{code: "arriere", x: 200, y: 0, w: 142, h: 355, zones: [logo]}]}};
	instance.mep = {};
	instance.modifier = async () => {};
	instance.rendre_scene = () => {};
	frappe.show_alert = () => {};
	await instance.placer_tampon("test", "arriere");
	assert.equal(instance.mep.arriere[0].rotation, 37);
	assert.equal(instance.mep.arriere[0].zoom_image, 2.5);
	assert.equal(instance.mep.arriere[0].logo, "/logo.svg");
	assert.equal(JSON.stringify(instance.mep.arriere[0].decalage_contenu), '{"x":-3,"y":4}');
	assert.equal(instance.mep.arriere[1].zone, "pictos");
});

test("déplacer le contenu conserve taille, zoom, rotation et centrage visible du logo", () => {
	const {instance} = studio();
	for (const rotation of [0, 37, 90, 270]) for (const zoom_image of [.5, 1, 4]) {
		const z = {zone: "logo", x: 12, y: 50, w: 80, h: 20, rotation, zoom_image,
			centre_visuel: {x: .6, y: .2, source: "/logo.svg"}};
		const avant = instance.cadre_image(z, 200, 100, "/logo.svg");
		const apres = instance.cadre_image({...z, decalage_contenu: {x: -7, y: 3}}, 200, 100, "/logo.svg");
		for (const cle of ["w", "h", "angle"]) assert.equal(apres[cle], avant[cle]);
		for (const cle of ["x", "cx"]) assert(Math.abs(apres[cle] - avant[cle] + 7) < 1e-8);
		for (const cle of ["y", "cy"]) assert(Math.abs(apres[cle] - avant[cle] - 3) < 1e-8);
	}
	for (const valeur of [null, [], "abc", {x: NaN, y: Infinity}])
		assert.equal(JSON.stringify(instance.decalage_contenu({w: 10, h: 20, decalage_contenu: valeur})), '{"x":0,"y":0}');
	assert.equal(JSON.stringify(instance.decalage_contenu({w: 10, h: 20, decalage_contenu: {x: -99, y: 99}})), '{"x":-10,"y":20}');
});

test("deux champs saisis rapidement sont tous les deux enregistrés sur le design d’origine", () => {
	const s = studio(), appels = [];
	s.instance.modifier = (...args) => appels.push(args);
	const sauver = s.instance.sauvegarde_differee("A");
	sauver("longueur_mm", 100);
	sauver("hauteur_mm", 200);
	sauver("longueur_mm", 120);
	s.instance.nom = "B";
	s.envoyer();
	assert.equal(JSON.stringify(appels), JSON.stringify([[{ longueur_mm: 120, hauteur_mm: 200 }, false, "A"]]));
	sauver("hauteur_mm", 220);
	s.envoyer();
	assert.equal(JSON.stringify(appels[1]), JSON.stringify([{ hauteur_mm: 220 }, false, "A"]));
});

test("la file capture le design au moment de la saisie, avant le départ réseau", async () => {
	const { instance } = studio(), appels = [];
	instance._enregistrer = async (valeurs, design) => appels.push([valeurs, design]);
	const a = instance.enregistrer({ nom_produit: "Robinet" });
	instance.nom = "B";
	const b = instance.enregistrer({ nom_produit: "Filtre" });
	await Promise.all([a, b]);
	assert.deepEqual(JSON.parse(JSON.stringify(appels)), [[{ nom_produit: "Robinet" }, "A"], [{ nom_produit: "Filtre" }, "B"]]);
});

test("les sauvegardes gardent un instantané et seule la dernière réponse redessine", async () => {
	const {instance, frappe} = studio();
	instance.d = {name: "A"}; instance.data = {doc: instance.d}; instance.mep = {};
	let dessins = 0, dessins_gauche = 0;
	for (const m of ["rendre_scene", "rendre_droite", "rendre_barre", "rendre_etats_etapes", "rendre_avert_lignes", "rendre_export"]) instance[m] = () => { if (m === "rendre_scene") dessins++; };
	instance.rendre_gauche = () => dessins_gauche++;
	const appels = [], fin = [];
	frappe.call = r => new Promise(resolve => {appels.push(r.args); fin.push(resolve);});
	const valeurs = {mise_en_page: {avant: [{zone: "logo", x: 10}]}};
	const a = instance.modifier(valeurs, true);
	valeurs.mise_en_page.avant[0].x = 20;
	const b = instance.enregistrer(valeurs);
	await new Promise(resolve => setImmediate(resolve));
	assert.equal(appels[0].valeurs.mise_en_page.avant[0].x, 10);
	const message = x => ({message: {doc: {name: "A", mise_en_page: JSON.stringify({avant: [{zone: "logo", x}]})}}});
	fin[0](message(10)); await a;
	assert.equal(dessins, 0); assert.equal(dessins_gauche, 0); assert.equal(instance.mep.avant, undefined);
	await new Promise(resolve => setImmediate(resolve));
	assert.equal(appels[1].valeurs.mise_en_page.avant[0].x, 20);
	fin[1](message(20)); await b;
	assert.equal(dessins, 1); assert.equal(dessins_gauche, 1); assert.equal(instance.mep.avant[0].x, 20);
});

test("un rechargement de fin de traitement attend lui aussi la fin du glissement", async () => {
	const {instance, frappe} = studio();
	instance.d = {name: "A"}; instance.data = {doc: instance.d}; instance._glissement_zone = {design: "A"};
	let dessins = 0; instance.rendre = () => dessins++;
	frappe.call = async () => ({message: {doc: {name: "A", modified: "recharge"}}});
	await instance.recharger();
	assert.equal(dessins, 0); assert.equal(instance.d.modified, undefined);
	instance._glissement_zone = null; instance.appliquer_retour_enregistrement();
	assert.equal(dessins, 1); assert.equal(instance.d.modified, "recharge");
});

test("une réponse pendant un glissement attend sa fin sans écraser le geste suivant", async () => {
	const {instance, frappe} = studio();
	instance.d = {name: "A", modified: "avant"}; instance.data = {doc: instance.d};
	let dessins = 0;
	for (const m of ["_lire_mep", "rendre_scene", "rendre_droite", "rendre_barre", "rendre_etats_etapes", "rendre_avert_lignes", "rendre_export"]) instance[m] = () => {if (m === "rendre_scene") dessins++;};
	instance._glissement_zone = {design: "A"};
	frappe.call = async () => ({message: {doc: {name: "A", modified: "sauve"}}});
	await instance.enregistrer({mise_en_page: {}});
	assert.equal(dessins, 0); assert.equal(instance.d.modified, "avant");
	instance._glissement_zone = null; instance.appliquer_retour_enregistrement();
	assert.equal(dessins, 1); assert.equal(instance.d.modified, "sauve");
	instance._glissement_zone = {design: "A"};
	await instance.enregistrer({mise_en_page: {avant: []}});
	instance._glissement_zone = null;
	let terminer; frappe.call = () => new Promise(resolve => {terminer = resolve;});
	const suite = instance.enregistrer({mise_en_page: {avant: [{x: 42}]}});
	instance.appliquer_retour_enregistrement(); assert.equal(dessins, 1);
	await new Promise(resolve => setImmediate(resolve));
	terminer({message: {doc: {name: "A", modified: "dernier"}}}); await suite;
	assert.equal(dessins, 2); assert.equal(instance.d.modified, "dernier");
});

test("la sélection locale conserve la position des symboles sans appliquer deux fois le déplacement", () => {
	const {instance} = studio();
	const z = {zone: "pictos", x: 30, y: 40, w: 20, h: 10, _origine_apercu: {x: 10, y: 20, w: 20, h: 10},
		apercu_elements: [{rect: [11, 21, 8, 8], fond: [10, 20, 10, 10]}]};
	instance.data = {apercu: {faces: [{code: "avant", zones: []}]}};
	instance.memoriser_apercu_zones({code: "avant"}, [z]);
	const copie = instance.data.apercu.faces[0].zones[0];
	assert.equal(JSON.stringify(copie.apercu_elements[0].rect), '[31,41,8,8]');
	assert.equal(JSON.stringify(instance.zone_pour_apercu(copie).apercu_elements), JSON.stringify(copie.apercu_elements));
	assert.equal(copie._origine_apercu, undefined);
	assert.equal(z.apercu_elements[0].rect[0], 11);
});

test("une ancienne réponse de sauvegarde ne remplace pas le design affiché", async () => {
	const { instance, frappe } = studio();
	let terminer;
	frappe.call = () => new Promise((resolve) => { terminer = resolve; });
	const sauvegarde = instance._enregistrer({ nom_produit: "Robinet" }, "A");
	instance.nom = "B";
	instance.d = { name: "B" };
	terminer({ message: { doc: { name: "A" } } });
	await sauvegarde;
	assert.equal(instance.d.name, "B");
});

test("un échec reste visible jusqu’à la réussite des champs concernés", async () => {
	const { instance } = studio();
	instance._enregistrer = async () => { throw new Error("réseau"); };
	await assert.rejects(instance.enregistrer({ contact: "À conserver" }));
	instance._enregistrer = async () => {};
	await instance.enregistrer({ nom_produit: "Robinet" });
	await assert.rejects(instance.attendre_sauvegardes(), /enregistrée/);
	assert.equal(instance._erreurs_enreg.get("A").contact, "À conserver");
	await instance.reessayer_sauvegarde();
	await instance.attendre_sauvegardes();
	assert.equal(instance._erreurs_enreg.has("A"), false);
});

test("exporter vide la saisie différée avant de continuer", async () => {
	const { instance } = studio(), appels = [];
	instance._enregistrer = async valeurs => { appels.push(valeurs); };
	instance.sauvegarde_differee("A")("contact", "Texte à imprimer");
	assert.equal(appels.length, 0);
	await instance.attendre_sauvegardes();
	assert.equal(JSON.stringify(appels), JSON.stringify([{contact: "Texte à imprimer"}]));
});

test("les étapes et l’export manuel ne dépendent pas des textes ou variantes IA", () => {
	const { instance } = studio();
	instance.d = {type_boite: "Étui à rabats", longueur_mm: 142, hauteur_mm: 355, profondeur_mm: 30, nom_produit: "Robinet"};
	instance.data = {exports: {pdf: "absent"}};
	assert.equal(instance._etape_par_defaut(), 3);
	assert.equal(instance._onglet_par_defaut(), "plan");
	instance.data.exports.pdf = "a_jour";
	assert.equal(instance._etape_par_defaut(), 4);
	assert.equal(instance._onglet_par_defaut(), "artwork");
});

test("une réponse légère préserve les catalogues déjà chargés", async () => {
	const { instance, frappe } = studio();
	const types = [{type: "Étui à rabats"}];
	instance.data = {types, polices: ["Poppins"]};
	frappe.call = async () => ({message: {doc: {name: "A"}, exports: {pdf: "a_regenerer"}}});
	for (const methode of ["_lire_mep", "rendre_scene", "rendre_droite", "rendre_barre", "rendre_etats_etapes", "rendre_avert_lignes", "rendre_export"]) instance[methode] = () => {};
	await instance._enregistrer({contact: "Nouveau"}, "A");
	assert.equal(instance.data.types, types);
	assert.equal(instance.data.exports.pdf, "a_regenerer");
});

test("chaque zone Logo garde son image et les autres faces restent inchangées", async () => {
	const { instance } = studio();
	instance.d = {logo: "/files/commun.svg"};
	instance.data = {apercu: {faces: []}};
	instance.mep = {avant: [{zone: "logo", logo: "/files/a.svg"}, {zone: "logo", logo: "/files/b.svg"}],
		arriere: [{zone: "logo", logo: "/files/c.svg"}]};
	instance.enregistrer = async ({mise_en_page}) => { instance.mep = mise_en_page; };
	await instance.appliquer_logo_zone("avant", 1, "/files/second.svg");
	assert.equal(instance.mep.avant[1].logo, "/files/second.svg");
	assert.equal(instance.mep.avant[0].logo, "/files/a.svg");
	assert.equal(instance.mep.arriere[0].logo, "/files/c.svg");
	assert.equal(instance.d.logo, "/files/commun.svg");
	await instance.appliquer_logo_zone("avant", 1, null);
	assert.equal(instance.mep.avant[1].logo, undefined);
	await assert.rejects(instance.appliquer_logo_zone("avant", 8, "/files/autre.svg"), /n’existe plus/);
});

test("le choix d’un logo de zone cible le design et la zone d’origine", async () => {
	const { instance } = studio();
	instance.epinglee = "avant"; instance.zone_sel = 1;
	let choisir;
	instance.mediatheque = async (_champ, callback) => { choisir = callback; };
	await instance.choisir_logo_zone();
	instance.nom = "B";
	await assert.rejects(choisir("/files/autre.svg"), /Rouvrez le design/);
});

test("la retouche IA prend le logo de la zone sélectionnée, y compris un logo commun hérité", async () => {
	const { instance } = studio();
	instance.epinglee = "dessus"; instance.zone_sel = 1;
	instance.d = {logo: "/files/commun.svg", modified: "revision"};
	instance.data = {peut_ecrire: true, apercu: {faces: [{code: "dessus", libelle: "Dessus",
		zones: [{zone: "nom"}, {zone: "logo", logo: "/files/dessus.svg"}]}]}};
	let appel;
	instance.atelier_image = (champ, options) => {appel = {champ, options};};
	await instance.retoucher_logo_zone();
	assert.equal(appel.champ, "logo"); assert.equal(appel.options.source_url, "/files/dessus.svg");
	assert.equal(JSON.stringify(appel.options.cible_zone), JSON.stringify({face: "dessus", indice: 1, modifie_le: "revision"}));
	delete instance.data.apercu.faces[0].zones[1].logo;
	await instance.retoucher_logo_zone();
	assert.equal(appel.options.source_url, "/files/commun.svg");
});

test("une sélection changée pendant la sauvegarde n’ouvre pas la retouche d’un autre logo", async () => {
	const { instance } = studio();
	instance.epinglee = "dessus"; instance.zone_sel = 0; instance.data = {peut_ecrire: true};
	instance.attendre_sauvegardes = async () => {instance.zone_sel = 1;};
	let ouvert = false; instance.atelier_image = () => {ouvert = true;};
	await instance.retoucher_logo_zone(); assert.equal(ouvert, false);
});

test("l’adoption IA ou SVG garde la cible capturée même si une autre face est sélectionnée", async () => {
	const { instance, frappe } = studio();
	const cible_zone = {face: "dessus", indice: 1, modifie_le: "revision"};
	instance.epinglee = "avant"; instance.zone_sel = 5;
	instance.data = {polices: ["Noto Sans"]};
	instance._lire_mep = () => {}; instance.rendre = () => {};
	let args;
	frappe.call = async r => {args = r.args; return {message: {doc: {name: "A", logo: "/files/commun.svg"}}};};
	await instance.adopter_proposition_image("A", "logo", "/files/proposition.svg", {cible_zone});
	assert.equal(args.cible_zone, cible_zone);
	assert.equal(instance.epinglee, "dessus"); assert.equal(instance.zone_sel, 1);
	assert.equal(instance.d.logo, "/files/commun.svg"); assert.equal(instance.data.polices[0], "Noto Sans");
	instance.nom = "B";
	await assert.rejects(instance.adopter_proposition_image("A", "logo", "/files/proposition.svg", {cible_zone}), /Rouvrez le design/);
});

test("le bouton 3D explique le PDF périmé et reste disponible pour un PDF à jour", () => {
	const { instance } = studio();
	instance.d = {};
	instance.data = {exports: {pdf: "a_regenerer"}};
	assert.equal(instance.etat_3d().pdf_pret, false);
	assert.match(instance.etat_3d().raison, /actualisez le PDF/);
	assert.match(instance.commande_3d(), /data-action="mockup" disabled/);
	instance.data.exports.pdf = "a_jour";
	assert.equal(instance.etat_3d().bloque, false);
	assert.doesNotMatch(instance.commande_3d(), /disabled/);
	instance._mockup_en_cours = true;
	assert.equal(instance.etat_3d().en_cours, true);
	assert.match(instance.commande_3d(), /disabled/);
});

test("le quart de tour vertical reste dans la petite face et conserve le logo", () => {
	const { instance } = studio();
	let enregistrements = 0;
	const z = {zone: "logo", x: 40, y: 10, w: 56, h: 5, logo: "/files/logo.svg"};
	instance.zone_sel = 0;
	instance._zones_en_cours = {face: {x: 0, y: 0, w: 140, h: 24}, zones: [z], sauver: () => enregistrements++};
	instance.tourner_zone(90);
	assert.equal(z.rotation, 90);
	assert(z.h > z.w);
	assert(z.x >= 0 && z.y >= 0 && z.x + z.w <= 140 && z.y + z.h <= 24);
	assert.equal(z.logo, "/files/logo.svg");
	assert.equal(enregistrements, 1);
});

test("l’aperçu d’un visuel tourné garde les proportions et tient dans son cadre", () => {
	const { instance } = studio();
	for (const angle of [0, 37, 90, 180, 270]) {
		const z = {x: 15, y: 20, w: 30, h: 90, rotation: angle};
		const r = instance.cadre_image(z, 120, 30), a = angle * Math.PI / 180;
		assert(Math.abs(r.w / r.h - 4) < 1e-6);
		assert(r.w * Math.abs(Math.cos(a)) + r.h * Math.abs(Math.sin(a)) <= z.w + 1e-6);
		assert(r.w * Math.abs(Math.sin(a)) + r.h * Math.abs(Math.cos(a)) <= z.h + 1e-6);
	}
	assert.equal(instance.angle_zone(-90), 270);
});
