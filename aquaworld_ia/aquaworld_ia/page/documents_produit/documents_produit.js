frappe.pages['documents-produit'].on_page_load = function(wrapper) {
  const page = frappe.ui.make_app_page({parent:wrapper,title:'Documents produit IA',single_column:true});
  // Static markup: CSS media-query braces must not pass through the Jinja-style compiler.
  $(frappe.templates.documents_produit).appendTo(page.main);
  wrapper.dp = new DocumentsProduit(page, $(page.main).find('.dp-root'));
};
frappe.pages['documents-produit'].on_page_show = function(wrapper) { if (wrapper.dp) wrapper.dp.ouvrir(); };
const DP_API = 'aquaworld_ia.documents_produit.service.';
const dpEsc = v => frappe.utils.escape_html(String(v ?? ''));
const dpCall = async (method,args={}) => (await frappe.call({method:DP_API+method,args})).message;
const dpUrl = url => typeof url==='string' && /^\/(private\/)?files\//.test(url) ? dpEsc(url) : '';
const dpMoney = value => Number(value || 0).toLocaleString('fr-FR',{minimumFractionDigits:4,maximumFractionDigits:4})+' $';
const dpAction = action => ({fiche:'Fiche technique',manuel:'Manuel d’utilisation',les_deux:'Fiche + manuel',traduire:'Traduction'})[action] || action;
const DP_TYPES = {fiche:'Fiche technique',manuel:"Manuel d'utilisation"};
const DP_BLOCKS = {presentation:'Description et photo principale',rubriques:'Rubriques du document',caracteristiques:'Caractéristiques techniques',variantes:'Tableau des variantes',illustrations:'Autres illustrations'};
// Les quatre étapes du travail, dans l'ordre où on les fait : l'écran suit cet ordre (refonte du 06/11/2026).
const DP_STEPS = {preparer:'Préparer',presenter:'Présenter',rediger:'Rédiger',relire:'Relire et produire'};
// Modèles de consignes de rédaction : un point de départ à modifier, jamais une preuve technique (cf. traitement.generer).
const DP_CONSIGNES = [
  {nom:'Particuliers', texte:'Public : particuliers, sans connaissance technique. Vocabulaire simple, phrases courtes, pas d’abréviations sans explication. Mettre en avant le confort d’usage, la qualité de l’eau obtenue et la simplicité d’entretien. Donner les gestes d’entretien courants (changement des filtres, nettoyage) avec leur fréquence quand elle est documentée.'},
  {nom:'Installateurs / plombiers', texte:'Public : plombiers et installateurs professionnels. Ton technique et direct. Détailler le raccordement, les dimensions, la pression et le débit de service, les contraintes d’installation (espace, évacuation, alimentation électrique). Signaler les erreurs d’installation fréquentes et les points de contrôle à la mise en service.'},
  {nom:'Revendeurs / B2B', texte:'Public : revendeurs et clients professionnels. Présenter la gamme et ses variantes de façon comparative : ce qui distingue chaque modèle (étages, membrane, options). Ton commercial mais factuel, sans superlatif non justifié. Mettre en avant les arguments de vente documentés et les applications types.'},
  {nom:'Fiche courte (1 page)', texte:'Fiche technique sur une page maximum. Présentation en trois phrases, puis uniquement les caractéristiques essentielles et les applications. Pas de rubrique longue : privilégier les listes et le tableau des variantes.'},
  {nom:'Manuel d’entretien détaillé', texte:'Manuel orienté entretien et dépannage. Détailler chaque opération d’entretien pas à pas (remplacement des cartouches, désinfection, contrôle des fuites), avec la fréquence et les signes qui indiquent qu’elle est nécessaire. Prévoir une rubrique de dépannage sous forme « symptôme → cause probable → action ». Rappeler les consignes de sécurité documentées avant toute intervention.'},
  {nom:'Export / traduction', texte:'Document destiné à être traduit en plusieurs langues. Phrases courtes et sans tournures idiomatiques, vocabulaire technique standard, unités internationales (bar, L/h, mm). Éviter les références propres au marché local (normes ou services locaux) sauf si elles sont dans les sources.'},
];
const dpLayoutDefault = () => ({position_photo:'apres',largeur_photo:65,hauteur_photo:65,alignement_titre:'gauche',couleur:'#087E8B',ordre:Object.keys(DP_BLOCKS),position_marque:'avant_titre',alignement_marque:'gauche',largeur_logo:32,afficher_nom_marque:0,logo_x:150,logo_y:8,photos_variantes:0,colonnes_photos:1,qr_url:'',qr_legende:'',qr_position:'fin_document',qr_alignement:'droite',qr_taille:22});
const dpLogoUrl = b => dpUrl(b?.logo)+(b?.logo_hash?'?v='+encodeURIComponent(b.logo_hash):'');

class DocumentsProduit {
  constructor(page, root) { this.page=page; this.root=root; this.name=null; this.current=null; this.dirty=false; this.activeTab='fiche'; this.activeStep='preparer'; this.selectedVersions={}; }
  async ouvrir() {
    clearTimeout(this.timer); this.name=frappe.get_route()[1] || null;
    this.loadSequence=(this.loadSequence||0)+1;this.jobTarget=null;this.selectedVersions={};
    this.root.html('<div class="dp-card">Chargement…</div>');
    if (!this.name) return this.liste();
    this.data=await dpCall('charger',{name:this.name}); this.current=null; this.dirty=false;
    let tab=frappe.get_route()[2];
    if(!Object.hasOwn(DP_TYPES,tab)){try{tab=sessionStorage.getItem('dp-tab:'+this.name);}catch{tab=null;}}
    this.activeTab=Object.hasOwn(DP_TYPES,tab)?tab:this.data.documents.some(v=>v.type_document===DP_TYPES.fiche)?'fiche':this.data.documents.some(v=>v.type_document===DP_TYPES.manuel)?'manuel':'fiche';
    let step=null;try{step=sessionStorage.getItem('dp-step:'+this.name);}catch{step=null;}
    this.activeStep=Object.hasOwn(DP_STEPS,step)?step:this.documentsActifs().length?'relire':'preparer';
    this.rendre(); this.poll();
  }
  async liste() {
    const rows=await dpCall('lister');
    this.root.html(`<div class="dp-top"><div><h2>Documents produit</h2><div class="dp-sub">Fiches techniques et manuels en français · traductions à la demande</div></div><button class="btn btn-primary dp-new">Créer un dossier produit</button></div>
    <div class="dp-documents">${rows.map(d=>`<a class="dp-doc-link" href="/app/documents-produit/${encodeURIComponent(d.name)}"><b>${dpEsc(d.titre)}</b><div class="dp-sub">${dpEsc(d.article)} · ${d.documents.length} version(s) enregistrée(s)</div></a>`).join('') || '<div class="dp-card">Choisissez un article pour préparer sa fiche technique et son manuel.</div>'}</div>`);
    this.root.find('.dp-new').on('click',()=>frappe.prompt([{fieldtype:'Link',fieldname:'article',label:'Article parent ou variante',options:'Item',reqd:1}], async v=>{
      const r=await dpCall('creer',v); frappe.set_route('documents-produit',r.name);
    },'Créer un dossier produit','Ouvrir le dossier'));
  }
  scopeOptions(value='',courante=false) {
    const selection=courante?this.root.find('.dp-variants input:checked').map((_,el)=>el.value).get():this.data.dossier.variantes.map(r=>r.article);
    if(value===this.data.dossier.article)value='';
    return `<option value="">Toute la gamme</option>${selection.map(article=>`<option value="${dpEsc(article)}" ${article===value?'selected':''}>${dpEsc(article)}</option>`).join('')}${value&&!selection.includes(value)?`<option value="${dpEsc(value)}" selected>${dpEsc(value)} — variante non sélectionnée</option>`:''}`;
  }
  typeActif() { return DP_TYPES[this.activeTab]; }
  documentsActifs() { return this.data.documents.filter(v=>v.type_document===this.typeActif()); }
  busy() { return ['En attente','En cours'].includes(this.data.dossier.etat_traitement); }
  async switchTab(tab) {
    if(!Object.hasOwn(DP_TYPES,tab)||tab===this.activeTab||this.switchingTab||this.busy())return;
    this.switchingTab=true;this.showState(this.data.dossier);
    try {
      if(this.dirty)await this.saveDocument();
      await this.saveConfig();
      if(this.current)this.selectedVersions[this.activeTab]=this.current.doc.name;
      this.loadSequence=(this.loadSequence||0)+1;
      this.data=await dpCall('charger',{name:this.name});
      this.activeTab=tab;this.current=null;this.dirty=false;
      try{sessionStorage.setItem('dp-tab:'+this.name,tab);}catch{/* Le choix reste utilisable sans stockage navigateur. */}
      this.rendre();
    }finally{this.switchingTab=false;this.showState(this.data.dossier);}
  }
  // ---------------------------------------------------------------- étapes
  showStep(step) {
    if(!Object.hasOwn(DP_STEPS,step))return;
    this.activeStep=step;
    try{sessionStorage.setItem('dp-step:'+this.name,step);}catch{/* sans stockage, l'étape repart de la valeur par défaut */}
    this.root.find('.dp-step').each((_,el)=>{el.hidden=el.dataset.step!==step;});
    this.root.find('.dp-step-btn').each((_,el)=>{const actif=el.dataset.step===step;el.classList.toggle('active',actif);el.setAttribute('aria-current',actif?'step':'false');});
    if(step==='relire')this.renderLayoutPreview();
    this.updateBar();
  }
  stepStatus() {
    // Ce que chaque étape a de fait ou de manquant : lu dans l'écran, pas dans la base, pour suivre la saisie en cours.
    const v=this.configValues(),d=this.data,versions=this.documentsActifs(),m=this.layoutValues();
    const marque=this.brandInfo,logo=marque&&dpUrl(marque.logo);
    const defaut=JSON.stringify({...dpLayoutDefault(),...m})===JSON.stringify(dpLayoutDefault());
    const points=this.current&&this.current.doc.type_document===this.typeActif()?(this.root.find('.dp-checks').val()||'').split('\n').filter(s=>s.trim()).length:null;
    const fr=versions.filter(x=>x.langue==='fr').length,valides=versions.filter(x=>x.statut==='Validé').length;
    return {
      preparer:[
        {ok:v.variantes.length>0||!d.variantes.length,txt:d.variantes.length?`${v.variantes.length} / ${d.variantes.length} variantes`:'produit sans variante'},
        {ok:v.sources.length>0,opt:true,txt:v.sources.length?`${v.sources.length} source${v.sources.length>1?'s':''}`:'aucune source'},
        {ok:v.images.length>0,opt:true,txt:v.images.length?`${v.images.length} photo${v.images.length>1?'s':''}`:'aucune photo'}],
      presenter:[
        {ok:!!logo,opt:true,txt:this.brandLoading?'logo…':logo?`logo ${marque.name}`:'pas de logo'},
        {ok:!!v.entete,opt:true,txt:v.entete?`en-tête : ${v.entete}`:'en-tête : logo seul'},
        {ok:!defaut,opt:true,txt:defaut?'mise en page par défaut':'mise en page personnalisée'}],
      rediger:[
        {ok:fr>0,txt:fr?`${fr} version${fr>1?'s':''} en français`:'rien de rédigé'},
        ...(d.dossier.etat_traitement?[{ok:!['Échec'].includes(d.dossier.etat_traitement),txt:d.dossier.etat_traitement}]:[])],
      relire:[
        {ok:versions.length>0,txt:versions.length?`${versions.length} version${versions.length>1?'s':''}`:'aucune version'},
        ...(points!==null?[{ok:points===0,txt:points?`${points} point${points>1?'s':''} à vérifier`:'aucun point en attente'}]:[]),
        {ok:valides>0,opt:true,txt:valides?`${valides} validée${valides>1?'s':''}`:'aucune validée'}],
    };
  }
  renderSteps() {
    const etat=this.stepStatus();
    this.root.find('.dp-steps').html(Object.entries(DP_STEPS).map(([k,label],i)=>`<button type="button" class="dp-step-btn ${k===this.activeStep?'active':''}" data-step="${k}" aria-current="${k===this.activeStep?'step':'false'}"><span class="dp-step-num">${i+1}</span><span class="dp-step-body"><b>${label}</b>${etat[k].map(s=>`<small class="${s.ok?'dp-ok':s.opt?'dp-opt':'dp-ko'}">${s.ok?'✔':s.opt?'–':'✖'} ${dpEsc(s.txt)}</small>`).join('')}</span></button>`).join(''));
    this.root.find('.dp-step-btn').on('click',e=>this.showStep(e.currentTarget.dataset.step));
  }
  unsaved() { return this.dirty||JSON.stringify(this.configValues())!==this.lastConfig; }
  updateBar() {
    const bar=this.root.find('.dp-bar');if(!bar.length)return;
    const modif=this.unsaved(),manuel=this.activeTab==='manuel';
    bar.find('.dp-bar-state').text(this.busy()?'Traitement en cours…':modif?'Modifications non enregistrées':'Tout est enregistré').toggleClass('dp-bar-dirty',modif&&!this.busy());
    bar.find('.dp-save-all').prop('disabled',!modif||this.busy()||!this.data.peut_ecrire||!!this.switchingTab);
    const v=this.configValues();
    bar.find('.dp-bar-hint').text(v.sources.length||v.images.length?'':'Sans source ni photo, l’IA part des seules données de l’article.');
    bar.find('[data-generate]').text(manuel?'Créer le manuel':'Créer la fiche technique');
    this.renderSteps();
  }
  async enregistrerTout() {
    try{if(this.dirty)await this.saveDocument();else await this.saveConfig(true);}
    catch(e){if(e?.message!=='Variante non sélectionnée')throw e;}
    this.updateBar();
  }
  // ---------------------------------------------------------------- aide
  usageGuideBody() {
    const manuel=this.activeTab==='manuel',creer=manuel?'Créer le manuel':'Créer la fiche technique';
    return `<div class="dp-help-body">
        <p>${manuel?'Cet onglet prépare un manuel pour accompagner l’installation, l’utilisation, l’entretien et le dépannage du produit, à partir des informations disponibles.':'Cet onglet prépare une fiche pour présenter le produit, ses applications, ses caractéristiques techniques et les variantes sélectionnées.'}</p>
        <ol class="dp-help-steps">
          <li><strong>Préparer.</strong> Cochez les variantes couvertes, ajoutez vos sources avec <b>Ajouter un document</b> et choisissez les photos avec <b>Choisir les photos des articles</b> (plusieurs vues par variante, ou <b>Suggérer les photos principales</b>). <b>Importer des photos</b> accepte plusieurs fichiers. Chaque photo garde sa variante, sa légende et son ordre ; la première est la <b>Photo principale</b>.
            <p>${manuel?'Ajoutez les notices du fabricant, les schémas et les photos utiles aux étapes d’installation ou d’entretien. Dans Consignes de rédaction, indiquez le public visé et les rubriques souhaitées.':'Vérifiez les données de l’article en cliquant sur sa référence en haut de la page. Renseignez les dimensions, matériaux, performances et applications dans l’article ou les documents sources. Utilisez Consignes de rédaction pour indiquer le public visé et le style souhaité.'}</p>
            <p><b>Sans PDF de référence :</b> l’IA part des données de l’article et des variantes. Vos consignes guident la rédaction, mais ne remplacent pas une source technique. Les informations manquantes restent à vérifier${manuel?', notamment les procédures d’installation, d’utilisation et de sécurité':''}.</p>
          </li>
          <li><strong>Présenter.</strong> Réglez <b>Marque et logo</b>, <b>En-tête des PDF</b> et <b>Mise en page</b>. La marque, l’en-tête, les sources et les photos sont communs à la fiche et au manuel ; la mise en page est propre à chaque onglet.</li>
          <li><strong>Rédiger.</strong> <b>Régler les modèles par outil</b> ouvre les réglages IA. Cliquez sur <b>${creer}</b> : l’IA rédige le contenu et enregistre une version française ; le coût estimé apparaît dans l’historique du dossier.
            <p>${manuel?'Les rubriques couvrent les étapes d’installation, de mise en service, d’utilisation, d’entretien et de dépannage selon les sources. Relisez en particulier les procédures, les réglages et les consignes de sécurité.':'L’IA prépare le titre, la présentation, les rubriques et les caractéristiques. La structure est prévue par l’outil ; les informations disponibles déterminent les rubriques remplies.'}</p>
          </li>
          <li><strong>Relire et produire.</strong> Choisissez une version, corrigez le titre, la présentation, les rubriques, les caractéristiques et les légendes, puis <b>Enregistrer</b>. Résolvez les <b>Points à vérifier</b> et retirez-les de la liste. <b>Générer le PDF</b> compose le document sans appel IA ; <b>Valider et générer le PDF</b> fige la version. <b>Traduire</b> crée une version dans une autre langue, à relire avant son PDF.</li>
        </ol>
        <div class="dp-help-grid">
          <section><h4>Logo de la marque : ajouter et placer</h4>
            <p>Dans <b>Marque et logo</b>, choisissez une marque ou utilisez <b>Créer une marque</b>. Cliquez sur <b>Ajouter / remplacer le logo</b> pour importer son image. Le logo est partagé avec les autres produits de cette marque.</p>
            <p>Dans <b>Mise en page → Zone de marque</b>, choisissez une position ou cliquez sur <b>Déplacer le logo à la souris</b>. Faites glisser son cadre sur la première page A4, ou saisissez les distances depuis les bords. <b>Actualiser le fond PDF</b> affiche le contenu pour vérifier l’emplacement.</p>
          </section>
          <section><h4>En-tête et pied de page</h4>
            <p>Dans <b>En-tête des PDF</b>, cliquez sur <b>Créer un en-tête</b> : nom du modèle, disposition, logo, coordonnées, pied de page, avec aperçu. <b>Enregistrer et utiliser</b> le sélectionne dans le dossier. L’en-tête et le pied de page se répètent sur chaque page ; le numéro de page est ajouté automatiquement.</p>
            <p><b>Réglages avancés</b> ouvre la fiche native pour les modèles en image ou en HTML. Pour garder aussi le logo dans le corps du document, cochez <b>Afficher aussi le logo de la marque avec un en-tête personnalisé</b>.</p>
          </section>
          <section><h4>Photo, description et ordre des blocs</h4>
            <p>Dans <b>Mise en page</b>, choisissez <b>Une colonne</b> ou <b>Deux colonnes</b>, le côté, la largeur et la hauteur de la photo, l’alignement du titre, la couleur des titres et l’ordre des blocs (flèches ou glisser-déposer). Les photos des variantes peuvent être regroupées avec leur référence, sur une à trois colonnes.</p>
            <p>Un changement de mise en page, de logo, de photos ou d’en-tête s’applique en générant le PDF, sans nouvelle rédaction IA. Un changement de marque commerciale ou l’ajout de variantes demande une nouvelle rédaction.</p>
          </section>
          <section><h4>Versions et coût</h4>
            <p>Chaque rédaction, correction ou PDF crée une nouvelle version ; les anciennes sont conservées. <b>Créer les deux</b> lance la fiche et le manuel.</p>
            <p>Rédaction, lecture des scans et traduction consomment des jetons ; corrections, placement du logo et composition PDF n’ajoutent aucun coût. <b>Détail des coûts</b> affiche les modèles, les tarifs et chaque génération.</p>
          </section>
        </div></div>`;
  }
  openGuide() {
    frappe.msgprint({title:`Guide · ${this.activeTab==='manuel'?'Manuel d’utilisation':'Fiche technique'}`,wide:true,message:this.usageGuideBody()});
  }
  // ---------------------------------------------------------------- mise en page (étape 2)
  layoutSummary() {
    const m=this.layoutValues(),cote=['gauche','droite'].includes(m.position_photo);
    const marque={libre:'logo placé librement',avant_titre:'logo au-dessus du titre',apres_titre:'logo sous le titre',fin_document:'logo en fin de document',masquee:'zone de marque masquée'}[m.position_marque];
    const qr=m.qr_url?` · QR code ${{avant_titre:'au-dessus du titre',apres_titre:'sous le titre',illustrations:'dans les illustrations',fin_document:'en fin de document'}[m.qr_position]}`:'';
    return `${cote?`2 colonnes · photo à ${m.position_photo}`:`1 colonne · photo ${m.position_photo==='avant'?'au-dessus':'en dessous'}`} · ${marque} · photos des variantes ${m.photos_variantes?'avec leur référence':'dans les illustrations'}${qr}`;
  }
  renderStructure() {
    const z=this.root.find('.dp-layout'),m=this.layoutValues();
    const options=(items,value)=>Object.entries(items).map(([v,label])=>`<option value="${v}" ${v===value?'selected':''}>${label}</option>`).join('');
    z.html(`<summary><span>Mise en page · ${this.activeTab==='fiche'?'fiche technique':'manuel'}</span><small class="dp-layout-summary">${dpEsc(this.layoutSummary())}</small></summary>
      <div class="dp-designer-grid"><div><div class="dp-brand-zone-settings"><h3>Zone de marque</h3>
      <p class="dp-muted dp-zone-brand-status" role="status"></p>
      <div class="dp-actions"><button class="btn btn-default btn-sm dp-enable-free-logo">Déplacer le logo à la souris</button></div>
      <div class="dp-grid"><label class="dp-label">Position de la zone de marque<select class="form-control dp-layout-brand-position">${options({libre:'Placement libre sur la première page',avant_titre:'Au-dessus du titre',apres_titre:'Sous le titre',fin_document:'À la fin du document',masquee:'Masquer cette zone'},m.position_marque)}</select></label>
      <label class="dp-label">Alignement du logo<select class="form-control dp-layout-brand-align">${options({gauche:'À gauche',centre:'Centré',droite:'À droite'},m.alignement_marque)}</select></label>
      <label class="dp-label">Largeur maximale du logo (mm)<input class="form-control dp-layout-logo-width" type="number" min="10" max="70" step="1" value="${m.largeur_logo}"></label>
      <label class="dp-label"><input type="checkbox" class="dp-layout-brand-name" ${m.afficher_nom_marque?'checked':''}> Afficher aussi le nom dans cette zone</label></div>
      <div class="dp-free-controls"><div class="dp-grid"><label class="dp-label">Distance depuis le bord gauche (mm)<input class="form-control dp-logo-x" type="number" step="0.1" min="0" value="${m.logo_x}"></label><label class="dp-label">Distance depuis le bord haut (mm)<input class="form-control dp-logo-y" type="number" step="0.1" min="0" value="${m.logo_y}"></label></div><p class="dp-muted">Faites glisser le cadre dans la page A4, ou saisissez les coordonnées. Flèches = 1 mm, Maj + flèches = 10 mm. Le logo se superpose au contenu de la première page.</p></div></div>
      <h3>Zone photo et description</h3>
      <div class="dp-column-choices" role="group" aria-label="Diviser la zone photo et description">
      <button type="button" class="dp-column-choice" data-columns="1"><span class="dp-column-icon dp-column-icon-one" aria-hidden="true"><span>Photo</span><span>Description</span></span><b>Une colonne</b><small>Éléments l’un sous l’autre</small></button>
      <button type="button" class="dp-column-choice" data-columns="2"><span class="dp-column-icon dp-column-icon-two" aria-hidden="true"><span>Photo</span><span>Description</span></span><b>Deux colonnes</b><small>Photo et description côte à côte</small></button></div>
      <p class="dp-muted dp-column-proportions" aria-live="polite" style="margin-top:10px"></p><div class="dp-grid">
      <label class="dp-label">Position de la photo<select class="form-control dp-layout-position">${options({avant:'1 colonne · Photo au-dessus',apres:'1 colonne · Photo en dessous',gauche:'2 colonnes · Photo à gauche',droite:'2 colonnes · Photo à droite'},m.position_photo)}</select></label>
      <label class="dp-label">Alignement du titre<select class="form-control dp-layout-title-align">${options({gauche:'À gauche',centre:'Centré',droite:'À droite'},m.alignement_titre)}</select></label>
      <label class="dp-label"><span class="dp-layout-width-label">Largeur de la photo (%)</span><input class="form-control dp-layout-width" type="number" min="20" max="${['gauche','droite'].includes(m.position_photo)?55:80}" step="1" value="${m.largeur_photo}"></label>
      <label class="dp-label">Hauteur maximale de la photo (mm)<input class="form-control dp-layout-height" type="number" min="20" max="120" step="1" value="${m.hauteur_photo}"></label>
      <label class="dp-label">Couleur des titres<input class="form-control dp-layout-color" type="color" value="${m.couleur}" style="width:90px;height:36px"></label></div>
      <h3 style="margin-top:18px">Photos des variantes</h3>
      <div class="dp-grid"><label class="dp-label">Où placer les vues des variantes<select class="form-control dp-photo-group"><option value="1">Avec la référence et les caractéristiques de chaque variante</option><option value="0">Dans les illustrations à la fin</option></select></label><label class="dp-label">Galeries de photos<select class="form-control dp-photo-columns"><option value="1">Une photo par ligne</option><option value="2">Deux photos par ligne</option><option value="3">Trois photos par ligne</option></select></label></div>
      <h3 style="margin-top:18px">QR code d’un lien internet</h3>
      <p class="dp-muted">Facultatif. Le QR code mène au lien saisi (ex. la page du produit sur votre site) ; la légende s’affiche dessous. Dans le PDF, le code est aussi cliquable.</p>
      <div class="dp-grid"><label class="dp-label">Lien (https://…)<input class="form-control dp-qr-url" type="url" maxlength="500" value="${dpEsc(m.qr_url)}" placeholder="https://www.votresite.com/produit/..."></label>
      <label class="dp-label">Légende sous le QR code<input class="form-control dp-qr-legende" maxlength="120" value="${dpEsc(m.qr_legende)}" placeholder="Ex. Fiche produit en ligne"></label>
      <label class="dp-label">Position<select class="form-control dp-qr-position">${options({avant_titre:'Au-dessus du titre',apres_titre:'Sous le titre',illustrations:'Dans « Autres illustrations »',fin_document:'À la fin du document'},m.qr_position)}</select></label>
      <label class="dp-label">Alignement<select class="form-control dp-qr-align">${options({gauche:'À gauche',centre:'Centré',droite:'À droite'},m.qr_alignement)}</select></label>
      <label class="dp-label">Taille (mm)<input class="form-control dp-qr-taille" type="number" min="15" max="40" step="1" value="${m.qr_taille}"></label></div>
      <p class="dp-muted dp-qr-status" role="status"></p>
      <h3 style="margin-top:18px">Ordre des blocs</h3><div class="dp-layout-order"></div>
      <div class="dp-actions" style="margin-top:14px"><button class="btn btn-default btn-sm dp-reset-layout">Disposition initiale</button></div>
      <p class="dp-muted dp-layout-status" role="status" style="margin-top:10px">La mise en page s’applique en générant le PDF d’une version, sans nouvelle rédaction IA.</p>
      </div><div><div class="dp-layout-preview"></div><p class="dp-muted" style="margin-top:12px">Aperçu de disposition : les blocs sans contenu sont omis du PDF.</p></div></div>`);
    z.find('.dp-layout-position,.dp-layout-title-align,.dp-layout-width,.dp-layout-height,.dp-layout-color,.dp-layout-brand-position,.dp-layout-brand-align,.dp-layout-logo-width,.dp-layout-brand-name,.dp-logo-x,.dp-logo-y,.dp-qr-url,.dp-qr-legende,.dp-qr-position,.dp-qr-align,.dp-qr-taille').on('input change',e=>{
      const position=z.find('.dp-layout-position').val(),maximum=['gauche','droite'].includes(position)?55:80;
      const borne=(selector,min,max,def)=>Math.max(min,Math.min(max,Math.round(Number(z.find(selector).val())||def)));
      const largeur=borne('.dp-layout-width',20,maximum,65);
      if(Number(z.find('.dp-layout-width').val())>maximum)z.find('.dp-layout-width').val(largeur);
      z.find('.dp-layout-width').attr('max',maximum);
      this.layouts[this.activeTab]={...this.layoutValues(),position_photo:position,largeur_photo:largeur,hauteur_photo:borne('.dp-layout-height',20,120,65),alignement_titre:z.find('.dp-layout-title-align').val(),couleur:z.find('.dp-layout-color').val(),position_marque:z.find('.dp-layout-brand-position').val(),alignement_marque:z.find('.dp-layout-brand-align').val(),largeur_logo:borne('.dp-layout-logo-width',10,70,32),afficher_nom_marque:z.find('.dp-layout-brand-name').prop('checked')?1:0,logo_x:Number(z.find('.dp-logo-x').val())||0,logo_y:Number(z.find('.dp-logo-y').val())||0,
        qr_url:(z.find('.dp-qr-url').val()||'').trim(),qr_legende:(z.find('.dp-qr-legende').val()||'').trim().slice(0,120),qr_position:z.find('.dp-qr-position').val(),qr_alignement:z.find('.dp-qr-align').val(),qr_taille:borne('.dp-qr-taille',15,40,22)};
      this.clampLogoPosition();
      if($(e.target).hasClass('dp-qr-url'))this.loadQrPreview();
      this.renderColumnChoices();this.renderLayoutPreview();this.layoutChanged();
    });
    this.loadQrPreview();
    z.find('.dp-enable-free-logo').on('click',()=>{z.find('.dp-layout-brand-position').val('libre').trigger('change');this.root.find('.dp-free-sheet')[0]?.scrollIntoView({behavior:'smooth',block:'center'});this.loadFreeBackground();});
    z.find('[data-columns]').on('click',e=>{
      const deux=$(e.currentTarget).attr('data-columns')==='2',cote=['gauche','droite'].includes(this.layoutValues().position_photo);
      if(deux===cote)return;
      if(deux)z.find('.dp-layout-width').val(50);
      z.find('.dp-layout-position').val(deux?'gauche':'apres').trigger('change');
    });
    z.find('.dp-reset-layout').on('click',()=>{this.layouts[this.activeTab]=dpLayoutDefault();this.renderStructure();this.layoutChanged();this.showState(this.data.dossier);});
    z.find('.dp-photo-group').val(String(m.photos_variantes));z.find('.dp-photo-columns').val(String(m.colonnes_photos));
    z.find('.dp-photo-group,.dp-photo-columns').on('change',()=>{this.layouts[this.activeTab]={...this.layoutValues(),photos_variantes:Number(z.find('.dp-photo-group').val()),colonnes_photos:Number(z.find('.dp-photo-columns').val())};this.renderLayoutPreview();this.layoutChanged();});
    this.renderColumnChoices();this.renderLayoutOrder();this.renderLayoutPreview();
  }
  renderColumnChoices() {
    const m=this.layoutValues(),cote=['gauche','droite'].includes(m.position_photo);
    this.root.find('[data-columns]').each((_,el)=>{const actif=el.dataset.columns===(cote?'2':'1');$(el).toggleClass('active',actif).attr('aria-pressed',String(actif));});
    this.root.find('.dp-layout-width-label').text(cote?'Largeur de la colonne photo (%)':'Largeur de la photo (%)');
    this.root.find('.dp-column-proportions').text(cote?`Deux colonnes : photo ${m.largeur_photo} % · description ${100-m.largeur_photo} %.`:'Une colonne : la photo et la description se suivent sur la page.');
  }
  layoutValues() { return {...dpLayoutDefault(),...(this.layouts?.[this.activeTab]||{})}; }
  // Le QR de l'aperçu vient du serveur (même générateur que le PDF), avec un délai pour ne pas l'appeler à chaque frappe.
  loadQrPreview() {
    clearTimeout(this.qrTimer);
    const url=this.layoutValues().qr_url,statut=this.root.find('.dp-qr-status');
    if(!url){this.qrPreview=null;statut.text('Sans lien, aucun QR code n’est ajouté au document.');this.renderLayoutPreview();return;}
    if(!/^https?:\/\/\S+$/.test(url)){this.qrPreview=null;statut.text('Le lien doit commencer par http:// ou https:// et ne pas contenir d’espace.');this.renderLayoutPreview();return;}
    if(this.qrPreview?.url===url)return;
    statut.text('Préparation du QR code…');
    this.qrTimer=setTimeout(async()=>{
      try{const r=await dpCall('apercu_qr',{name:this.name,url});if(this.layoutValues().qr_url!==url)return;this.qrPreview={url,image:r.image};statut.text('QR code prêt : il mène à '+url);}
      catch{this.qrPreview=null;statut.text('Ce lien n’est pas accepté. Vérifiez son adresse.');}
      this.renderLayoutPreview();
    },500);
  }
  canMoveLogo() { return this.data.peut_ecrire&&!this.switchingTab&&!this.busy(); }
  clampLogoPosition() {
    const m=this.layoutValues(),height=m.largeur_logo*18/32+(m.afficher_nom_marque?8:0);
    if(m.position_marque==='libre'){
      this.layouts[this.activeTab]={...m,logo_x:Math.max(0,Math.min(210-m.largeur_logo,Math.round(m.logo_x*10)/10)),logo_y:Math.max(0,Math.min(Math.floor((297-height)*10)/10,Math.round(m.logo_y*10)/10))};
    }
    const actuel=this.layoutValues();
    this.root.find('.dp-logo-x').attr('max',210-m.largeur_logo).val(actuel.logo_x);
    this.root.find('.dp-logo-y').attr('max',Math.floor((297-height)*10)/10).val(actuel.logo_y);
  }
  moveFreeLogo(x,y) {
    if(!this.canMoveLogo())return;
    this.layouts[this.activeTab]={...this.layoutValues(),logo_x:x,logo_y:y};this.clampLogoPosition();
    const m=this.layoutValues();this.root.find('.dp-free-brand').css({left:m.logo_x/210*100+'%',top:m.logo_y/297*100+'%'});
    this.root.find('.dp-free-coordinates').text(`X : ${m.logo_x.toFixed(1)} mm · Y : ${m.logo_y.toFixed(1)} mm`);this.layoutChanged();
  }
  freeBackgroundKey() {
    const m=this.layoutValues(),configuration={...this.configValues()};delete configuration.mises_en_page;
    const mise_en_page={};['position_photo','largeur_photo','hauteur_photo','alignement_titre','couleur','ordre','qr_url','qr_legende','qr_position','qr_alignement','qr_taille'].forEach(k=>mise_en_page[k]=m[k]);
    return JSON.stringify({name:this.name,type:this.activeTab,document:this.current?.doc.name,contenu:this.root.find('.dp-editor').length?this.captureDocument():this.current?.contenu,configuration,mise_en_page});
  }
  async loadFreeBackground() {
    if(this.freePreviewLoading)return;
    this.freePreviewLoading=true;this.freePreviewError='';this.renderLayoutPreview();
    try{
      if(this.data.peut_ecrire)await this.saveConfig();
      const key=this.freeBackgroundKey();
      const resultat=await dpCall('apercu_placement_logo',{name:this.name,type_document:this.typeActif(),mise_en_page:this.layoutValues(),document_name:this.current?.doc.name,contenu:this.current?(this.root.find('.dp-editor').length?this.captureDocument():this.current.contenu):undefined});
      if(key===this.freeBackgroundKey()&&resultat?.image?.startsWith('data:image/png;base64,'))this.freeBackground={key,...resultat};
    }catch{this.freePreviewError='Le fond PDF n’a pas pu être préparé. Vous pouvez placer le logo sur la page blanche et réessayer.';}
    finally{this.freePreviewLoading=false;this.renderLayoutPreview();this.showState(this.data.dossier);}
  }
  bindFreeLogo() {
    const el=this.root.find('.dp-free-brand')[0],sheet=this.root.find('.dp-free-sheet')[0];if(!el)return;
    let drag=null;
    el.addEventListener('pointerdown',e=>{if(!this.canMoveLogo()||e.button!==0)return;e.preventDefault();const m=this.layoutValues();drag={x:e.clientX,y:e.clientY,logo_x:m.logo_x,logo_y:m.logo_y};el.setPointerCapture(e.pointerId);this.logoDragging=true;el.classList.add('dragging');el.focus({preventScroll:true});});
    el.addEventListener('pointermove',e=>{if(!drag)return;const r=sheet.getBoundingClientRect();this.moveFreeLogo(drag.logo_x+(e.clientX-drag.x)/r.width*210,drag.logo_y+(e.clientY-drag.y)/r.height*297);});
    const stop=()=>{drag=null;this.logoDragging=false;el.classList.remove('dragging');if(this.previewNeedsRender){this.previewNeedsRender=false;this.renderLayoutPreview();}};
    el.addEventListener('pointerup',stop);el.addEventListener('pointercancel',stop);el.addEventListener('lostpointercapture',stop);
    el.addEventListener('keydown',e=>{if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)||!this.canMoveLogo())return;e.preventDefault();const m=this.layoutValues(),pas=e.shiftKey?10:1;this.moveFreeLogo(m.logo_x+(e.key==='ArrowLeft'?-pas:e.key==='ArrowRight'?pas:0),m.logo_y+(e.key==='ArrowUp'?-pas:e.key==='ArrowDown'?pas:0));});
    this.root.find('.dp-load-free-background').on('click',()=>this.loadFreeBackground());
  }
  layoutChanged() { this.root.find('.dp-layout-status').text('Disposition modifiée : enregistrez, puis générez le PDF pour l’appliquer.');this.root.find('.dp-layout-summary').text(this.layoutSummary());this.updateBar(); }
  moveLayoutBlock(from,to) {
    if(!this.data.peut_ecrire||this.switchingTab||this.busy())return;
    const m=this.layoutValues(),ordre=[...m.ordre],i=ordre.indexOf(from),j=ordre.indexOf(to);
    if(i<0||j<0||i===j)return;
    ordre.splice(i,1);ordre.splice(j,0,from);this.layouts[this.activeTab]={...m,ordre};
    this.renderLayoutOrder();this.renderLayoutPreview();this.layoutChanged();this.showState(this.data.dossier);
  }
  renderLayoutOrder() {
    const z=this.root.find('.dp-layout-order'),ordre=this.layoutValues().ordre;
    z.html(ordre.map((cle,i)=>`<div class="dp-order-row" data-block="${cle}" draggable="${!!this.data.peut_ecrire}"><span><span aria-hidden="true">⠿</span> ${DP_BLOCKS[cle]}</span><div class="dp-actions">${i?`<button class="btn btn-xs btn-default" data-move="${ordre[i-1]}" aria-label="Monter ${DP_BLOCKS[cle]}">↑</button>`:''}${i<ordre.length-1?`<button class="btn btn-xs btn-default" data-move="${ordre[i+1]}" aria-label="Descendre ${DP_BLOCKS[cle]}">↓</button>`:''}</div></div>`).join(''));
    z.find('[data-move]').on('click',e=>{const row=$(e.currentTarget).closest('[data-block]'),cle=row.attr('data-block');this.moveLayoutBlock(cle,$(e.currentTarget).attr('data-move'));this.root.find(`[data-block="${cle}"] button`).first().trigger('focus');});
    z.find('[data-block]').on('dragstart',e=>{e.originalEvent.dataTransfer.setData('text/plain',$(e.currentTarget).attr('data-block'));e.originalEvent.dataTransfer.effectAllowed='move';}).on('dragover',e=>e.preventDefault()).on('drop',e=>{e.preventDefault();this.moveLayoutBlock(e.originalEvent.dataTransfer.getData('text/plain'),$(e.currentTarget).attr('data-block'));});
  }
  renderLayoutPreview() {
    if(this.logoDragging){this.previewNeedsRender=true;return;}
    const m=this.layoutValues(),c=this.current?.contenu,ctx=this.current?.contexte||this.data.contexte,images=this.configValues().images,im=images[0];
    this.root.find('.dp-free-controls').toggle(m.position_marque==='libre');
    this.root.find('.dp-layout-brand-align').closest('label').toggle(m.position_marque!=='libre');
    const marque=this.brandInfo||{name:this.root.find('.dp-brand').val()||this.data.contexte.article.brand||'',logo:''};
    const entete=this.root.find('.dp-letterhead').val(),logoAvecEntete=this.root.find('.dp-brand-with-header').prop('checked');
    const logoAutorise=!entete||logoAvecEntete,logo=logoAutorise&&dpUrl(marque.logo)?dpLogoUrl(marque):'';
    const alignMarque={gauche:'left',centre:'center',droite:'right'}[m.alignement_marque];
    let statut=this.brandLoading?'Chargement du logo…':!marque.name?'Choisissez une marque dans « Marque et logo ».':!marque.logo?`${marque.name} : aucun logo. Ajoutez son image dans « Marque et logo ».`:`${marque.name} : logo visible dans l’aperçu.`;
    if(marque.logo&&!logoAutorise)statut='Pour afficher le logo avec l’en-tête choisi, cochez « Afficher aussi le logo de la marque avec un en-tête personnalisé » dans Marque et logo.';
    if(m.position_marque==='masquee')statut='La zone de marque est masquée. Les mentions de la marque dans les textes sont conservées.';
    if(this.current&&marque.name!==(ctx.marque_document||ctx.article.brand||''))statut+=' La marque choisie diffère de cette version : créez une nouvelle fiche ou un nouveau manuel pour actualiser les textes.';
    this.root.find('.dp-zone-brand-status').text(statut);
    if(m.position_marque==='libre'){
      const hLogo=m.largeur_logo*18/32,h=hLogo+(m.afficher_nom_marque?8:0),fond=this.freeBackground?.key===this.freeBackgroundKey()?this.freeBackground:null;
      const image=logo?`<img class="dp-design-brand-logo dp-free-brand-logo" src="${logo}" alt="Logo ${dpEsc(marque.name)}" draggable="false" style="height:${hLogo/h*100}%">`:`<div class="dp-free-placeholder" style="height:${hLogo/h*100}%">${logoAutorise?'Logo à ajouter':'Logo masqué par l’en-tête'}</div>`;
      this.root.find('.dp-layout-preview').html(`<p class="dp-muted">Première page · A4 · 210 × 297 mm</p><div class="dp-free-sheet" aria-label="Page A4 pour placer librement le logo">${fond?`<img class="dp-free-background" src="${fond.image}" alt="Première page du document sans la zone de marque" draggable="false">`:'<div class="dp-free-margins"><span>Zone de contenu<br>Actualisez le fond pour voir le document.</span></div>'}<div class="dp-free-brand" role="group" aria-label="Logo déplaçable : utilisez la souris ou les flèches du clavier" tabindex="${this.canMoveLogo()?0:-1}" aria-disabled="${!this.canMoveLogo()}" style="left:${m.logo_x/210*100}%;top:${m.logo_y/297*100}%;width:${m.largeur_logo/210*100}%;height:${h/297*100}%">${image}${m.afficher_nom_marque?`<strong class="dp-free-brand-name" style="height:${8/h*100}%;font-size:calc(${Math.min(3,m.largeur_logo/(Math.max(marque.name.length,1)*.6))} * 100cqw / 210)">${dpEsc(marque.name)}</strong>`:''}</div></div><p class="dp-muted dp-free-coordinates" aria-live="polite">X : ${m.logo_x.toFixed(1)} mm · Y : ${m.logo_y.toFixed(1)} mm</p><button class="btn btn-default btn-sm dp-load-free-background" ${this.freePreviewLoading?'disabled':''}>${this.freePreviewLoading?'Préparation du fond…':'Actualiser le fond PDF'}</button><p class="dp-muted dp-free-background-status" style="margin-top:8px">${this.freePreviewError|| (fond?(fond.exemple?'Fond d’exemple : aucun contenu IA n’a été rédigé.':'Fond issu de la version sélectionnée, avec vos corrections en cours.'): 'Le fond doit être actualisé après un changement du contenu ou de la disposition.')}</p>`);
      this.bindFreeLogo();return;
    }
    const contenuMarque=logo?`<img class="dp-design-brand-logo" src="${logo}" alt="Logo ${dpEsc(marque.name)}" style="width:${m.largeur_logo*1.8}px;max-height:${m.largeur_logo*18/32*1.8}px">`:logoAutorise?`<span class="dp-design-brand-placeholder">${this.brandLoading?'Chargement du logo…':'Logo '+dpEsc(marque.name||'de marque')+' à ajouter'}</span>`:'';
    const zoneMarque=m.position_marque!=='masquee'&&(contenuMarque||m.afficher_nom_marque)?`<div class="dp-design-brand" data-brand-position="${m.position_marque}" style="text-align:${alignMarque}">${contenuMarque}${m.afficher_nom_marque?`<strong class="dp-design-brand-name">${dpEsc(marque.name)}</strong>`:''}</div>`:'';
    const alignQr={gauche:'left',centre:'center',droite:'right'}[m.qr_alignement],tailleQr=m.qr_taille*1.8;
    const zoneQr=m.qr_url?`<div class="dp-design-qr" style="text-align:${alignQr}">${this.qrPreview?.url===m.qr_url&&this.qrPreview.image?`<img src="${this.qrPreview.image}" alt="QR code vers ${dpEsc(m.qr_url)}" style="width:${tailleQr}px;height:${tailleQr}px">`:`<span class="dp-design-brand-placeholder" style="display:inline-flex;width:${tailleQr}px;height:${tailleQr}px;align-items:center;justify-content:center">QR</span>`}${m.qr_legende?`<small style="display:block">${dpEsc(m.qr_legende)}</small>`:''}</div>`:'';
    const zones=p=>(m.position_marque===p?zoneMarque:'')+(m.qr_position===p?zoneQr:'');
    const titre=this.root.find('.dp-title').val()??c?.titre??this.typeActif(),resume=this.root.find('.dp-summary').val()??c?.resume??'Description du produit, rédigée à partir des informations disponibles.';
    const couleur=/^#[0-9a-f]{6}$/i.test(m.couleur)?m.couleur:'#087E8B',align={gauche:'left',centre:'center',droite:'right'}[m.alignement_titre];
    const cote=['gauche','droite'].includes(m.position_photo),largeur=Math.min(cote?55:80,m.largeur_photo),hauteur=Math.min(120,m.hauteur_photo)*1.4;
    const photo=`<div class="dp-design-photo" style="${cote?'':`width:${largeur}%;margin-left:auto;margin-right:auto;`}">${im?`<img src="${dpUrl(im.image)}" alt="${dpEsc(im.legende||'Photo principale')}" style="max-height:${hauteur}px">`:`<div class="dp-design-placeholder" style="height:${hauteur}px">Photo principale</div>`}<small>${dpEsc(im?.legende||'Légende')}</small></div>`;
    const description=`<div class="dp-design-description">${dpEsc(resume.slice(0,210))}${resume.length>210?'…':''}</div>`;
    const parties=['avant','gauche'].includes(m.position_photo)?[photo,description]:[description,photo];
    const ratio=m.position_photo==='gauche'?largeur:100-largeur;
    const presentation=`<div class="dp-design-presentation ${cote?'dp-design-columns':''}" style="${cote?`grid-template-columns:minmax(0,${ratio}fr) minmax(0,${100-ratio}fr)`:''}">${parties.join('')}</div>`;
    const grille=photos=>`<div class="dp-photo-mini-grid" style="grid-template-columns:repeat(${m.colonnes_photos},minmax(0,1fr))">${photos.map(p=>`<img src="${dpUrl(p.image)}" alt="${dpEsc(p.legende)}">`).join('')}</div>`;
    const variantes=this.configValues().variantes.map(v=>v.article),supp=images.slice(1),communes=supp.filter(p=>!m.photos_variantes||!variantes.includes(p.article));
    const illustrees=variantes.filter(v=>supp.some(p=>p.article===v)),sansPhoto=variantes.length-illustrees.length;
    const apercuVariantes=illustrees.slice(0,3).map(v=>`<div class="dp-design-block"><b>${dpEsc(v)}</b>${grille(supp.filter(p=>p.article===v))}</div>`).join('')+(illustrees.length>3?`<div class="dp-sheet-small">+ ${illustrees.length-3} variantes illustrées dans le PDF</div>`:'')+(sansPhoto?`<div class="dp-design-block">Tableau : ${sansPhoto} variantes sans autre photo</div>`:'');
    const qrIllustrations=m.qr_position==='illustrations'?zoneQr:'';
    const blocs={presentation,rubriques:`<div class="dp-design-block">${this.activeTab==='manuel'?'Installation · Utilisation<br>Entretien · Dépannage':'Présentation · Applications'}</div>`,caracteristiques:'<div class="dp-sheet-table">Caractéristiques techniques</div>',variantes:m.photos_variantes?apercuVariantes:'<div class="dp-design-block">Tableau des variantes</div>',illustrations:`<div class="dp-design-block">Autres illustrations${communes.length?grille(communes):''}${qrIllustrations}</div>`};
    this.root.find('.dp-layout-preview').html(`<div class="dp-sheet dp-design-sheet" aria-label="Aperçu de la mise en page"><div class="dp-sheet-header">${entete?'En-tête : '+dpEsc(entete):'Document A4'}</div>${zones('avant_titre')}<div class="dp-sheet-title" style="color:${couleur};text-align:${align}">${dpEsc(titre)}</div><div class="dp-sheet-small" style="text-align:${align}">${dpEsc(marque.name)} · ${dpEsc(ctx.article.name)}</div>${zones('apres_titre')}<div class="dp-design-blocks" style="--dp-accent:${couleur}">${m.ordre.map(k=>`<div data-preview-block="${k}">${blocs[k]}</div>`).join('')}</div>${zones('fin_document')}<div class="dp-sheet-footer">Pied de page et numéro de page</div></div>`);
  }
  // ---------------------------------------------------------------- variantes (étape 1)
  variantTable(selected) {
    const vs=this.data.variantes;
    if(!vs.length)return '<span class="dp-muted">Cet article n’a pas de variantes actives.</span>';
    const noms=[];vs.forEach(v=>(v.attributs||[]).forEach(a=>{if(!noms.includes(a.nom))noms.push(a.nom);}));
    const valeur=(v,nom)=>(v.attributs||[]).find(a=>a.nom===nom)?.valeur||'';
    const row=v=>`<tr class="dp-variant" data-search="${dpEsc((v.name+' '+v.item_name).toLowerCase())}" title="${dpEsc(v.item_name)}"><td><input type="checkbox" value="${dpEsc(v.name)}" ${selected.has(v.name)?'checked':''} aria-label="${dpEsc(v.name)}"></td><td class="dp-variant-ref"><b>${dpEsc(v.name)}</b></td>${noms.length?noms.slice(1).map(n=>`<td>${dpEsc(valeur(v,n))}</td>`).join(''):`<td>${dpEsc(v.item_name)}</td>`}</tr>`;
    if(!noms.length)return `<table class="dp-vtable"><thead><tr><th></th><th>Référence</th><th>Nom</th></tr></thead><tbody>${vs.map(row).join('')}</tbody></table>`;
    // Groupées par le premier attribut (ex. membrane) : une case par groupe, les autres attributs en colonnes.
    const groupes=new Map();vs.forEach(v=>{const g=valeur(v,noms[0]);if(!groupes.has(g))groupes.set(g,[]);groupes.get(g).push(v);});
    const cols=noms.length+1;
    return `<table class="dp-vtable"><thead><tr><th></th><th>Référence</th>${noms.slice(1).map(n=>`<th>${dpEsc(n)}</th>`).join('')}</tr></thead>${Array.from(groupes).map(([g,items])=>`<tbody class="dp-vgroup" data-group="${dpEsc(g)}"><tr class="dp-vgroup-head"><th colspan="${cols}"><label><input type="checkbox" class="dp-vgroup-all" aria-label="Toutes les variantes ${dpEsc(g)}"> ${dpEsc(noms[0])} : <b>${dpEsc(g||'—')}</b> <span class="dp-muted">(${items.length})</span></label></th></tr>${items.map(row).join('')}</tbody>`).join('')}</table>`;
  }
  syncVariantGroups() {
    this.root.find('.dp-vgroup').each((_,g)=>{const cbs=$(g).find('.dp-variant input'),n=cbs.filter(':checked').length,all=$(g).find('.dp-vgroup-all')[0];if(!all)return;all.checked=n===cbs.length&&n>0;all.indeterminate=n>0&&n<cbs.length;});
    const v=this.configValues();this.root.find('.dp-variant-count').text(`${v.variantes.length} / ${this.data.variantes.length} cochées`);
  }
  // ---------------------------------------------------------------- rendu de la page
  rendre() {
    this.loadSequence=(this.loadSequence||0)+1;
    this.brandInfo=null;this.brandLoading=true;
    this.layouts=typeof this.data.dossier.mises_en_page==='string'?JSON.parse(this.data.dossier.mises_en_page||'{}'):(this.data.dossier.mises_en_page||{});
    const d=this.data.dossier, selected=new Set(d.variantes.map(v=>v.article)),versions=this.documentsActifs(),manuel=this.activeTab==='manuel';
    const c=this.data.couts_ia,total=c?dpMoney(c.total):'';
    this.root.html(`<div class="dp-top"><div><a href="/app/documents-produit" class="dp-muted">← Tous les dossiers</a><h2>${dpEsc(d.titre)}</h2><div class="dp-sub"><a href="/app/item/${encodeURIComponent(d.article)}">${dpEsc(d.article)}</a> · ${dpEsc(this.data.contexte.marque_document||this.data.contexte.article.brand)} · français de référence${c?` · coût IA du dossier : ${total}`:''}</div></div>
      <div class="dp-actions"><button class="btn btn-default btn-sm dp-guide">Guide</button></div></div>
      <div class="dp-tabs" role="tablist" aria-label="Type de document">${Object.keys(DP_TYPES).map(tab=>`<button class="dp-tab ${tab===this.activeTab?'active':''}" id="dp-tab-${tab}" type="button" role="tab" data-tab="${tab}" aria-selected="${tab===this.activeTab}" aria-controls="dp-type-panel" tabindex="${tab===this.activeTab?'0':'-1'}">${tab==='fiche'?'Fiche technique':'Manuel d’utilisation'} <span class="dp-tab-count">${this.data.documents.filter(v=>v.type_document===DP_TYPES[tab]).length}</span></button>`).join('')}</div>
      <div id="dp-type-panel" role="tabpanel" aria-labelledby="dp-tab-${this.activeTab}" class="dp-shell">
      <nav class="dp-steps" aria-label="Étapes"></nav>
      <div class="dp-main">
      <div class="dp-progress"></div>

      <section class="dp-step" data-step="preparer" hidden>
      <div class="dp-card"><div class="dp-actions dp-card-head"><h3>Consignes de rédaction <span class="dp-muted dp-shared">commun à la fiche et au manuel</span></h3><select class="form-control input-sm dp-consignes-modele" aria-label="Modèle de consignes" style="max-width:260px"><option value="">Partir d’un modèle…</option>${DP_CONSIGNES.map(m=>`<option value="${dpEsc(m.nom)}">${dpEsc(m.nom)}</option>`).join('')}</select></div><textarea class="form-control dp-consignes" rows="3" placeholder="Facultatif. Public visé, ton, longueur, rubriques à privilégier… L’IA s’en sert pour la forme, jamais comme source technique.">${dpEsc(d.consignes)}</textarea></div>
      <div class="dp-card"><div class="dp-actions dp-card-head"><h3>Variantes couvertes <span class="dp-muted dp-variant-count"></span></h3><input class="form-control input-sm dp-search" placeholder="Filtrer…" style="max-width:220px"><button class="btn btn-xs btn-default" data-select-all="1">Toutes</button><button class="btn btn-xs btn-default" data-select-all="0">Aucune</button></div>
      <div class="dp-variants">${this.variantTable(selected)}</div></div>
      <div class="dp-card"><div class="dp-actions dp-card-head"><h3>Sources <span class="dp-muted">manuels PDF, photos de pages</span></h3><button class="btn btn-default btn-sm dp-upload-source">Ajouter un document</button><button class="btn btn-default btn-sm dp-existing">Documents déjà liés aux articles</button></div>
      <div class="dp-sources">${d.sources.map((s,i)=>`<div class="dp-sources-row" data-index="${i}"><div>S${i+1} · <a href="${dpUrl(s.fichier)}" target="_blank" rel="noopener">${dpEsc(s.fichier.split('/').pop())}</a>${/\.pdf$/i.test(s.fichier)?` <button class="btn btn-xs btn-default dp-page" data-index="${i}">Illustrer avec une page</button>`:''}</div><input class="form-control input-sm dp-pages" value="${dpEsc(s.pages)}" placeholder="Pages (ex. 1-4,7)" title="Pages utiles, 40 au maximum par PDF"><select class="form-control input-sm dp-source-scope" title="Variante concernée">${this.scopeOptions(s.article)}</select><button class="btn btn-xs btn-default dp-remove-source" data-index="${i}" title="Retirer">×</button></div>`).join('')||'<p class="dp-muted">Aucune source. Sans PDF de référence, l’IA part des données de l’article.</p>'}</div></div>
      <div class="dp-card dp-photo-section"><div class="dp-actions dp-card-head"><h3>Photos du produit et des variantes <span class="dp-photo-count dp-muted" role="status"></span></h3><button class="btn btn-primary btn-sm dp-choose-images">Choisir les photos des articles</button><button class="btn btn-default btn-sm dp-upload-image">Importer des photos</button></div>
      <p class="dp-muted">La première photo est la photo principale. Retirer une photo ici conserve le fichier d’origine.</p>
      <div class="dp-images">${d.images.map((im,i)=>`<div class="dp-image" data-index="${i}"><a href="${dpUrl(im.image)}" target="_blank" rel="noopener" aria-label="Voir la photo en grand"><img src="${dpUrl(im.image)}" alt="${dpEsc(im.legende)}" loading="lazy"></a><button class="btn btn-xs btn-default dp-main-image" aria-pressed="${i===0}">${i===0?'★ Photo principale':'Définir comme principale'}</button><label class="dp-label">Légende<input class="form-control input-sm dp-caption" value="${dpEsc(im.legende)}" maxlength="140" placeholder="Ex. Vue de face"></label><label class="dp-label">Produit / variante<select class="form-control input-sm dp-image-scope">${this.scopeOptions(im.article)}</select></label><div class="dp-actions"><button class="btn btn-xs btn-default dp-image-prev" aria-label="Avancer cette photo">←</button><button class="btn btn-xs btn-default dp-image-next" aria-label="Reculer cette photo">→</button><button class="btn btn-xs btn-default dp-remove-image" data-index="${i}">Retirer</button></div></div>`).join('')}</div></div>
      <div class="dp-actions dp-step-next"><button class="btn btn-default" data-goto="presenter">Étape suivante : Présenter →</button></div>
      </section>

      <section class="dp-step" data-step="presenter" hidden>
      <div class="dp-card dp-brand-card"><h3>Marque et logo <span class="dp-muted dp-shared">commun à la fiche et au manuel</span></h3><div class="dp-actions">
      <select class="form-control dp-brand" aria-label="Marque du document" style="width:320px"><option value="">Marque de l’article${this.data.contexte.article.brand?' : '+dpEsc(this.data.contexte.article.brand):' (non renseignée)'}</option>${(this.data.marques||[]).map(b=>`<option value="${dpEsc(b.name)}" ${b.name===d.marque_document?'selected':''}>${dpEsc(b.name)}</option>`).join('')}${d.marque_document&&!(this.data.marques||[]).some(b=>b.name===d.marque_document)?`<option value="${dpEsc(d.marque_document)}" selected>${dpEsc(d.marque_document)}</option>`:''}</select>
      ${this.data.peut_creer_marque?'<button class="btn btn-default btn-sm dp-new-brand">Créer une marque</button>':''}</div>
      <div class="dp-brand-preview" style="margin-top:12px"></div><label class="dp-label"><input type="checkbox" class="dp-brand-with-header" ${d.logo_marque_avec_entete?'checked':''}> Afficher aussi le logo de la marque avec un en-tête personnalisé</label>
      <p class="dp-muted" style="margin:8px 0 0">Le logo est partagé par tous les produits de cette marque. Son emplacement dans le document se règle dans la mise en page ci-dessous.</p></div>
      <div class="dp-card dp-letterhead-card"><h3>En-tête des PDF <span class="dp-muted dp-shared">commun à la fiche et au manuel</span></h3><div class="dp-actions">
      <select class="form-control dp-letterhead" aria-label="En-tête des PDF" style="width:320px"><option value="">Logo de la marque</option>${(this.data.entetes||[]).map(h=>`<option value="${dpEsc(h.name)}" ${h.name===d.entete?'selected':''}>${dpEsc(h.name)}${h.a_completer?' (image à compléter)':''}</option>`).join('')}${d.entete&&!(this.data.entetes||[]).some(h=>h.name===d.entete)?`<option value="${dpEsc(d.entete)}" selected>${dpEsc(d.entete)} (désactivé)</option>`:''}</select>
      ${this.data.peut_creer_entete?'<button class="btn btn-default btn-sm dp-new-letterhead">Créer un en-tête</button>':''}<button class="btn btn-default btn-sm dp-edit-letterhead" style="display:none">Modifier visuellement</button>
      <button class="btn btn-default btn-sm dp-preview-letterhead">Aperçu</button><button class="btn btn-default btn-sm dp-refresh-letterheads" title="Recharger la liste des en-têtes">↻</button>
      <a class="dp-letterhead-link" href="/app/letter-head" target="_blank" rel="noopener">Réglages avancés</a></div>
      <p class="dp-muted" style="margin:10px 0 0">L’en-tête et le pied de page se répètent sur chaque page.</p>${this.data.erreur_entete?`<div class="dp-warning" style="margin-top:10px">${dpEsc(this.data.erreur_entete)}</div>`:''}</div>
      <details class="dp-card dp-layout"></details>
      <div class="dp-actions dp-step-next"><button class="btn btn-default" data-goto="rediger">Étape suivante : Rédiger →</button></div>
      </section>

      <section class="dp-step" data-step="rediger" hidden>
      <div class="dp-card"><h3>${manuel?'Rédiger le manuel d’utilisation':'Rédiger la fiche technique'}</h3>
      <p class="dp-sub">${manuel?'L’IA rédige les instructions d’installation, d’utilisation et d’entretien à partir des sources et des données des articles, puis enregistre une version française à relire.':'L’IA rédige la présentation, les rubriques et les caractéristiques à partir des sources et des données des articles, puis enregistre une version française à relire.'}</p>
      <div class="dp-actions" style="margin-top:14px"><button class="btn btn-primary" data-generate="${this.activeTab}">${manuel?'Créer le manuel':'Créer la fiche technique'}</button><button class="btn btn-default" data-generate="les_deux">Créer les deux</button><span class="dp-muted dp-bar-hint"></span></div></div>
      <div class="dp-card dp-costs"></div>
      </section>

      <section class="dp-step" data-step="relire" hidden>
      <div class="dp-card"><div class="dp-actions dp-card-head"><h3 style="margin:0">${manuel?'Manuels et traductions':'Fiches techniques et traductions'}</h3><select class="form-control dp-versions" aria-label="Versions ${manuel?'du manuel':'de la fiche technique'}" style="max-width:520px"><option value="">Choisir une version…</option>${versions.map(v=>`<option value="${dpEsc(v.name)}">${dpEsc(v.libelle_langue)} · v${v.numero} · ${dpEsc(v.statut)}${v.a_actualiser?' · À actualiser':''}</option>`).join('')}</select></div><div class="dp-document">${versions.length?'Choisissez une version pour la relire, la traduire ou télécharger son PDF.':manuel?'Aucun manuel enregistré. Passez par l’étape Rédiger pour préparer la première version.':'Aucune fiche technique enregistrée. Passez par l’étape Rédiger pour préparer la première version.'}</div></div>
      </section>
      </div></div>
      <div class="dp-bar"><span class="dp-bar-state"></span><div class="dp-actions"><button class="btn btn-default dp-save-all">Enregistrer</button><button class="btn btn-primary" data-generate="${this.activeTab}">${manuel?'Créer le manuel':'Créer la fiche technique'}</button></div></div>`);
    this.bindConfig();
    this.renderCosts();
    this.renderStructure();
    this.renderBrand();
    this.root.find('.dp-guide').on('click',()=>this.openGuide());
    this.root.find('[data-goto]').on('click',e=>{this.showStep(e.currentTarget.dataset.goto);window.scrollTo({top:0,behavior:'smooth'});});
    this.root.find('.dp-save-all').on('click',()=>this.enregistrerTout());
    this.root.find('.dp-main').on('input change',()=>this.updateBar());
    this.root.find('.dp-tab').on('click',e=>this.switchTab($(e.currentTarget).attr('data-tab'))).on('keydown',async e=>{
      if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;
      e.preventDefault();const tab=e.key==='Home'?'fiche':e.key==='End'?'manuel':this.activeTab==='fiche'?'manuel':'fiche';
      await this.switchTab(tab);this.root.find(`[data-tab="${this.activeTab}"]`).trigger('focus');
    });
    this.root.find('[data-generate]').on('click',e=>this.lancer($(e.currentTarget).attr('data-generate')));
    this.root.find('.dp-versions').on('change',async e=>{const name=e.target.value; if(this.current&&this.dirty) await this.saveDocument(); if(name)await this.loadDocument(name);});
    if (!this.data.peut_ecrire) this.root.find('button,input,textarea').prop('disabled',true);
    const current=this.current?.doc.type_document===this.typeActif()?this.current.doc.name:this.selectedVersions[this.activeTab];
    if(current && versions.some(v=>v.name===current)) this.loadDocument(current);
    else if(versions.length) this.loadDocument(versions[0].name);
    else {this.current=null;this.dirty=false;}
    this.showStep(this.activeStep);
    this.showState(d);
  }
  renderCosts() {
    const c=this.data.couts_ia,z=this.root.find('.dp-costs');
    if(!c){z.hide();return;}
    const latest=(c.historique||[])[0];
    const latestCost=!latest?'—':Number(latest.inconnus)===Number(latest.appels)?'Non communiqué':dpMoney(latest.cout);
    const modeles=c.modeles?.filter(m=>[this.activeTab,'lecture','traduire'].includes(m.action))||[{libelle:'Rédaction, lecture et traduction',modele:c.modele,prix_entree:c.prix_entree,prix_sortie:c.prix_sortie}];
    const modeleRedaction=modeles.find(m=>m.action===this.activeTab)||modeles[0];
    const modeleCommun=new Set(modeles.map(m=>m.modele)).size===1;
    z.html(`<h3>Modèle IA et coûts</h3><div class="dp-cost-summary"><div><b>Modèle ${this.activeTab==='fiche'?'fiche technique':'manuel'} : ${dpEsc(modeleRedaction.modele)}</b><div class="dp-sub">${modeleCommun?'Même modèle pour la lecture des scans et la traduction':modeles.filter(m=>m!==modeleRedaction).map(m=>dpEsc(m.libelle+' : '+m.modele)).join('<br>')}</div><a class="dp-model-settings" href="/app/aquaworld-ia-reglages" target="_blank" rel="noopener">Régler les modèles par outil</a></div>
      <div><b>Dernière génération : ${latestCost}</b><div class="dp-sub">${latest?dpEsc(dpAction(latest.action)+' · '+latest.langue):'Le montant apparaîtra après la première génération.'}</div>${latest?.inconnus?'<div class="dp-sub">Montant partiel : consommation manquante pour certains appels.</div>':''}</div>
      <div><b>Total du dossier : ${dpMoney(c.total)}</b>${c.inconnus?'<div class="dp-warning">Total partiel : certains appels n’ont pas communiqué leur consommation.</div>':''}<div class="dp-sub">Hors remises de cache et taxes. PDF et corrections : aucun coût.</div></div></div>
      <details class="dp-model-rates" style="margin-top:12px"><summary>Modèles et tarifs par étape</summary><div class="dp-table-wrap"><table class="dp-table"><thead><tr><th>Étape</th><th>Modèle</th><th>Entrée ($ / million de jetons)</th><th>Sortie ($ / million de jetons)</th></tr></thead><tbody>${modeles.map(m=>`<tr><td>${dpEsc(m.libelle)}</td><td>${dpEsc(m.modele)}</td><td>${dpMoney(m.prix_entree)}</td><td>${dpMoney(m.prix_sortie)}</td></tr>`).join('')}</tbody></table></div></details>
      <details><summary>Coût par génération du dossier · 50 dernières générations</summary>
      ${(c.historique||[]).length?`<div class="dp-table-wrap"><table class="dp-table"><thead><tr><th>Date</th><th>Génération</th><th>Langue</th><th>Modèle</th><th>Appels</th><th>Coût estimé</th><th></th></tr></thead><tbody>${c.historique.map(g=>`<tr><td>${dpEsc(frappe.datetime.str_to_user(g.debut))}</td><td>${dpEsc(dpAction(g.action))}${g.erreurs?'<div class="dp-warning">Appel en erreur</div>':''}</td><td>${dpEsc(g.langue)}</td><td>${dpEsc(g.modeles)}</td><td>${Number(g.appels)}</td><td>${g.inconnus?'≥ ':''}${dpMoney(g.cout)}${g.inconnus?'<div class="dp-muted">Consommation partielle</div>':''}</td><td><button class="btn btn-xs btn-default dp-cost-detail" data-generation="${dpEsc(g.generation)}">Détail</button></td></tr>`).join('')}</tbody></table></div>`:'<p class="dp-muted" style="margin-top:10px">Aucun appel IA enregistré pour ce dossier.</p>'}</details>`);
    z.find('.dp-cost-detail').on('click',async e=>{
      const rows=await dpCall('detail_cout',{name:this.name,generation:$(e.currentTarget).attr('data-generation')});
      frappe.msgprint({title:'Détail du coût de génération',wide:true,message:`<div class="dp-table-wrap" style="overflow-x:auto"><table class="table"><thead><tr><th>Étape</th><th>Modèle</th><th>Jetons entrée</th><th>Jetons sortie</th><th>Coût estimé</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${dpEsc(r.fonctionnalite)}${r.statut==='Erreur'?'<div>Appel en erreur</div>':''}</td><td>${dpEsc(r.modele)}</td><td>${Number(r.jetons_entree)}</td><td>${Number(r.jetons_sortie)}</td><td>${r.usage_inconnu?'Non communiqué':dpMoney(r.cout_estime)}</td></tr>`).join('')}</tbody></table></div><p class="text-muted">Les lectures de scans et les reprises sont incluses. Une génération interrompue peut déjà avoir consommé des jetons.</p>`});
    });
  }
  configValues() {
    const d=this.data.dossier;
    return {mises_en_page:this.layouts||{},marque_document:this.root.find('.dp-brand').val()||'',logo_marque_avec_entete:this.root.find('.dp-brand-with-header').prop('checked')?1:0,entete:this.root.find('.dp-letterhead').val()||'',consignes:this.root.find('.dp-consignes').val()||'',variantes:this.root.find('.dp-variants .dp-variant input:checked').map((_,el)=>({article:el.value})).get(),
      sources:this.root.find('.dp-sources-row').map((_,el)=>{const z=$(el),s=d.sources[+z.attr('data-index')];return {fichier:s.fichier,pages:z.find('.dp-pages').val(),article:z.find('.dp-source-scope').val()};}).get(),
      images:this.root.find('.dp-image').map((_,el)=>{const z=$(el),im=d.images[+z.attr('data-index')];return {image:im.image,legende:z.find('.dp-caption').val(),article:z.find('.dp-image-scope').val()};}).get()};
  }
  async saveConfig(redraw=false) {
    const values=this.configValues();
    if(JSON.stringify(values)===this.lastConfig)return;
    const selection=new Set([this.data.dossier.article,...values.variantes.map(v=>v.article)]);
    if([...values.images,...values.sources].some(x=>x.article&&!selection.has(x.article))){frappe.msgprint('Une photo ou une source concerne une variante décochée. Rétablissez cette variante, retirez sa photo/source de la sélection ou corrigez son association.');throw new Error('Variante non sélectionnée');}
    const r=await dpCall('enregistrer',{name:this.name,data:values,modified:this.data.dossier.modified});
    Object.assign(this.data.dossier,values,{modified:r.modified});this.lastConfig=JSON.stringify(values);
    if(redraw){this.data=await dpCall('charger',{name:this.name});this.rendre();frappe.show_alert({message:'Dossier enregistré',indicator:'green'});}
  }
  bindConfig() {
    this.lastConfig=JSON.stringify(this.configValues());
    this.root.find('.dp-consignes-modele').on('change',e=>{
      const modele=DP_CONSIGNES.find(m=>m.nom===e.target.value),ta=this.root.find('.dp-consignes');e.target.value='';
      if(!modele)return;
      const appliquer=()=>{ta.val(modele.texte).trigger('input').trigger('focus');};
      if(ta.val().trim())frappe.confirm(`Remplacer les consignes actuelles par le modèle « ${dpEsc(modele.nom)} » ?`,appliquer);else appliquer();
    });
    this.root.find('.dp-choose-images').on('click',async()=>{await frappe.require('/assets/aquaworld_ia/js/documents_produit_photos.js');await new aquaworld_ia.PhotosProduit(this).ouvrir();});
    this.root.find('.dp-brand').on('change',()=>this.renderBrand());
    this.root.find('.dp-brand-with-header').on('change',()=>this.renderLayoutPreview());
    this.root.find('.dp-new-brand').on('click',()=>frappe.prompt([{fieldtype:'Data',fieldname:'marque',label:'Nom de la marque',reqd:1}],async v=>{
      if(this.dirty)await this.saveDocument();await this.saveConfig();
      const b=await dpCall('creer_marque',{name:this.name,marque:v.marque});
      if(!this.root.find('.dp-brand option').toArray().some(o=>o.value===b.name))$('<option>').val(b.name).text(b.name).appendTo(this.root.find('.dp-brand'));
      this.root.find('.dp-brand').val(b.name);await this.saveConfig(true);
    },'Créer une marque','Créer et utiliser'));
    const ouvrirEditeur=async(modele=null)=>{await frappe.require('/assets/aquaworld_ia/js/documents_produit_entete.js');await new aquaworld_ia.EditeurEntete(this,modele).ouvrir();};
    this.root.find('.dp-new-letterhead').on('click',()=>ouvrirEditeur());
    this.root.find('.dp-edit-letterhead').on('click',()=>ouvrirEditeur(this.root.find('.dp-letterhead').val()));
    const lienEntete=()=>{const name=this.root.find('.dp-letterhead').val();this.root.find('.dp-letterhead-link').attr('href',name?'/app/letter-head/'+encodeURIComponent(name):'/app/letter-head');this.root.find('.dp-edit-letterhead').toggle(!!this.data.entetes?.find(h=>h.name===name&&h.visuel));};
    this.root.find('.dp-letterhead').on('change',()=>{lienEntete();this.renderLayoutPreview();});lienEntete();
    this.root.find('.dp-refresh-letterheads').on('click',async()=>{if(this.dirty)await this.saveDocument();await this.saveConfig();this.data=await dpCall('charger',{name:this.name});this.rendre();});
    this.root.find('.dp-preview-letterhead').on('click',async()=>{
      const entete=this.root.find('.dp-letterhead').val();
      if(!entete)return frappe.msgprint('Le logo de la marque choisie sera repris dans le document.');
      const images=await dpCall('apercu_entete',{name:this.name,entete});
      frappe.msgprint({title:'Aperçu — '+dpEsc(entete),wide:true,message:[['haut','En-tête'],['bas','Pied de page']].filter(([k])=>images[k]?.startsWith('data:image/png;base64,')).map(([k,label])=>`<p><b>${label}</b></p><img src="${dpEsc(images[k])}" alt="${label}" style="width:100%;max-width:100%;border:1px solid var(--border-color);margin-bottom:18px">`).join('')});
    });
    this.root.find('.dp-search').on('input',e=>{const q=e.target.value.toLowerCase();this.root.find('.dp-variant').each((_,el)=>$(el).toggle($(el).attr('data-search').includes(q)));this.root.find('.dp-vgroup').each((_,g)=>$(g).toggle($(g).find('.dp-variant').toArray().some(r=>r.style.display!=='none')));});
    const scopes=()=>this.root.find('.dp-image-scope,.dp-source-scope').each((_,el)=>{const v=el.value;$(el).html(this.scopeOptions(v,true));});
    this.root.find('.dp-variant input').on('change',()=>{scopes();this.syncVariantGroups();});
    this.root.find('.dp-vgroup-all').on('change',e=>{const g=$(e.currentTarget).closest('.dp-vgroup');g.find('.dp-variant:visible input').prop('checked',e.currentTarget.checked);scopes();this.syncVariantGroups();this.updateBar();});
    this.root.find('[data-select-all]').on('click',e=>{this.root.find('.dp-variant:visible input').prop('checked',$(e.currentTarget).attr('data-select-all')==='1');scopes();this.syncVariantGroups();this.updateBar();});
    this.syncVariantGroups();
    this.root.find('.dp-remove-source,.dp-remove-image').on('click',e=>{$(e.currentTarget).closest('.dp-sources-row,.dp-image').remove();this.photoOrder();this.updateBar();});
    this.root.find('.dp-main-image,.dp-image-prev,.dp-image-next').on('click',e=>{const b=$(e.currentTarget),card=b.closest('.dp-image');if(b.hasClass('dp-main-image'))card.prependTo(this.root.find('.dp-images'));else if(b.hasClass('dp-image-prev'))card.prev('.dp-image').before(card);else card.next('.dp-image').after(card);this.photoOrder();this.updateBar();});
    this.root.find('.dp-caption,.dp-image-scope').on('input change',()=>this.renderLayoutPreview());
    this.photoOrder();
    const ajouter=async(table,row)=>{if(this.dirty)await this.saveDocument();await this.saveConfig();const values=this.configValues();values[table].push(row);await dpCall('enregistrer',{name:this.name,data:values,modified:this.data.dossier.modified});this.data=await dpCall('charger',{name:this.name});this.rendre();};
    this.root.find('.dp-upload-source').on('click',()=>new frappe.ui.FileUploader({doctype:'Dossier Produit',docname:this.name,allow_multiple:true,is_private:1,restrictions:{allowed_file_types:['.pdf','.png','.jpg','.jpeg','.webp']},on_success:f=>{this.uploads=(this.uploads||Promise.resolve()).then(()=>ajouter('sources',{fichier:f.file_url,pages:'',article:''}));}}));
    this.root.find('.dp-upload-image').on('click',()=>{const name=this.name;new frappe.ui.FileUploader({doctype:'Dossier Produit',docname:name,allow_multiple:true,is_private:1,restrictions:{allowed_file_types:['.png','.jpg','.jpeg','.webp','.svg']},on_success:f=>{this.uploads=(this.uploads||Promise.resolve()).catch(()=>{}).then(async()=>{if(this.name!==name)return;if(this.configValues().images.length>=20)return frappe.msgprint('20 photos sont déjà sélectionnées. Le fichier reste joint au dossier et peut être choisi plus tard.');await ajouter('images',{image:f.file_url,legende:'',article:''});});}});});
    this.root.find('.dp-existing').on('click',()=>{
      const choices=this.data.sources_disponibles.filter(s=>!this.configValues().sources.some(x=>x.fichier===s.fichier));
      if(!choices.length)return frappe.msgprint('Aucun autre document joint aux articles ou aux manuels existants.');
      const d=new frappe.ui.Dialog({title:'Documents disponibles',fields:[{fieldtype:'Select',fieldname:'choix',label:'Document',options:choices.map((s,i)=>({label:s.nom,value:String(i)})),reqd:1}],primary_action_label:'Ajouter',primary_action:async v=>{d.hide();const s=choices[+v.choix];await ajouter('sources',{fichier:s.fichier,pages:'',article:s.article});}});d.show();
    });
    this.root.find('.dp-page').on('click',e=>{const i=+$(e.currentTarget).attr('data-index'),fichier=this.data.dossier.sources[i].fichier;frappe.prompt([{fieldtype:'Int',fieldname:'page',label:'Page à utiliser comme illustration',default:1,reqd:1}],async v=>{await this.saveConfig();await dpCall('illustrer_page',{name:this.name,fichier,page:v.page});this.data=await dpCall('charger',{name:this.name});this.rendre();},'Illustration du manuel','Ajouter l’illustration');});
  }
  photoOrder() {
    const cards=this.root.find('.dp-image');this.root.find('.dp-photo-count').text(`${cards.length} / 20`);
    cards.each((i,el)=>$(el).find('.dp-main-image').attr('aria-pressed',i===0).text(i===0?'★ Photo principale':'Définir comme principale'));
    this.renderLayoutPreview();
  }
  async ajouterPhotos(images,presentation) {
    if(this.dirty)await this.saveDocument();
    const values=this.configValues(),cle=im=>JSON.stringify([im.image,im.article||'']);
    const connus=new Set(values.images.map(cle));
    for(const im of images)if(!connus.has(cle(im))){values.images.push(im);connus.add(cle(im));}
    if(values.images.length>20)throw new Error('Sélectionnez au maximum 20 photos au total.');
    values.mises_en_page[this.activeTab]={...this.layoutValues(),...presentation};
    await dpCall('enregistrer',{name:this.name,data:values,modified:this.data.dossier.modified});
    this.data=await dpCall('charger',{name:this.name});this.rendre();
    frappe.show_alert({message:'Photos sélectionnées. Générez le PDF pour les appliquer.',indicator:'green'});
  }
  async renderBrand() {
    const sequence=this.brandSequence=(this.brandSequence||0)+1,name=this.name,z=this.root.find('.dp-brand-preview');
    this.brandInfo=null;this.brandLoading=true;this.renderLayoutPreview();
    z.text('Chargement du logo…');
    try {
      const b=await dpCall('info_marque',{name,marque:this.root.find('.dp-brand').val()||''});
      if(sequence!==this.brandSequence||name!==this.name)return;
      this.brandInfo=b;this.brandLoading=false;this.renderLayoutPreview();
      z.html(`<div class="dp-actions">${dpUrl(b.logo)?`<img class="dp-brand-logo" src="${dpLogoUrl(b)}" alt="Logo ${dpEsc(b.name)}" style="width:110px;height:65px;object-fit:contain">`:'<span class="dp-muted">Aucun logo.</span>'}${b.name?`<span><b>${dpEsc(b.name)}</b></span>${b.peut_modifier&&this.data.peut_ecrire?'<button class="btn btn-default btn-sm dp-upload-brand-logo">Ajouter / remplacer le logo</button>':''}<a href="/app/brand/${encodeURIComponent(b.name)}" target="_blank" rel="noopener">Fiche de marque</a>`:'<span class="dp-muted">Choisissez ou créez une marque.</span>'}</div>`);
      z.find('.dp-upload-brand-logo').on('click',async()=>{
        if(this.dirty)await this.saveDocument();await this.saveConfig();
        new frappe.ui.FileUploader({doctype:'Brand',docname:b.name,is_private:1,allow_multiple:false,restrictions:{allowed_file_types:['.png','.jpg','.jpeg','.webp','.svg']},on_success:async f=>{
          await dpCall('enregistrer_logo_marque',{name:this.name,marque:b.name,fichier:f.file_url});
          this.data=await dpCall('charger',{name:this.name});this.rendre();frappe.show_alert({message:'Logo de la marque enregistré',indicator:'green'});
        }});
      });
      this.showState(this.data.dossier);
    }catch(e){if(sequence===this.brandSequence){this.brandLoading=false;this.renderLayoutPreview();z.text('La marque ou son logo est inaccessible. Choisissez une marque autorisée.');this.root.find('.dp-zone-brand-status').text('La marque ou son logo est inaccessible. Choisissez une marque autorisée.');}}
    this.renderSteps();
  }
  async loadDocument(name) {
    const sequence=this.loadSequence=(this.loadSequence||0)+1,dossier=this.name,type=this.typeActif();
    const current=await dpCall('lire_document',{name});
    if(sequence!==this.loadSequence||dossier!==this.name||type!==this.typeActif()||current.doc.type_document!==type)return;
    this.current=current;this.selectedVersions[this.activeTab]=name;this.dirty=false;this.root.find('.dp-versions').val(name);this.renderDocument();this.renderLayoutPreview();this.updateBar();
  }
  renderDocument() {
    const {doc,contenu:c,contexte:ctx}=this.current,z=this.root.find('.dp-document');
    const info=this.data.documents.find(v=>v.name===doc.name),scope=(value)=>`<option value="">Toute la gamme</option>${ctx.variantes.map(v=>`<option value="${dpEsc(v.name)}" ${value===v.name?'selected':''}>${dpEsc(v.name)}</option>`).join('')}`;
    z.html(`<div class="dp-actions"><span class="dp-badge">${dpEsc(doc.libelle_langue)} · version ${doc.numero} · ${dpEsc(doc.statut)}</span>${doc.langue==='fr'?'<button class="btn btn-default btn-sm dp-translate">Traduire</button>':''}<button class="btn btn-default btn-sm dp-pdf">Générer le PDF</button><button class="btn btn-primary btn-sm dp-validate">Valider et générer le PDF</button>${[['pdf','Télécharger le PDF'],['source_latex','Source LaTeX'],['archive_latex','LaTeX et images (ZIP)']].filter(([k])=>doc[k]).map(([k,label])=>`<a class="btn btn-default btn-sm" href="${dpUrl(doc[k])}" target="_blank" rel="noopener">${label}</a>`).join('')}</div>
      ${info?.a_actualiser?'<div class="dp-warning" style="margin:12px 0">À actualiser : la marque, la présentation, les articles, les sources ou la version française ont changé depuis cette version.</div>':''}
      <div class="dp-sub" style="margin-top:8px">${doc.source_fr?`Traduction de la version française <a href="#" class="dp-source-fr">${dpEsc(doc.source_fr)}</a> · `:''}En-tête : ${dpEsc(ctx.entete?.nom||'Logo de la marque')} · Marque : ${dpEsc(ctx.marque_document||ctx.article.brand||'Non renseignée')}</div>
      ${(ctx.marque_document||ctx.article.brand||'')!==(this.data.contexte.marque_document||this.data.contexte.article.brand||'')?'<div class="dp-warning" style="margin-top:10px">Pour utiliser la marque sélectionnée, rédigez une nouvelle version (étape Rédiger).</div>':''}
      <div class="dp-review ${doc.pdf?'dp-review-split':''}"><div class="dp-editor" ${doc.rtl?'dir="rtl"':''}><label class="dp-label">Titre</label><input class="form-control dp-title" value="${dpEsc(c.titre)}"><label class="dp-label">Présentation</label><textarea class="form-control dp-summary">${dpEsc(c.resume)}</textarea>
      <div class="dp-sections">${c.sections.map((s,i)=>`<div class="dp-section" data-index="${i}"><div class="dp-section-title"><input class="form-control dp-section-name" value="${dpEsc(s.titre)}" placeholder="Titre de la rubrique"><button class="btn btn-xs btn-default dp-remove-section">×</button></div><div class="dp-scope"><select class="form-control input-sm dp-section-scope">${scope(s.article)}</select><input class="form-control input-sm dp-section-source" value="${dpEsc(s.source)}" placeholder="Source : S1 p.3, Article…"></div><textarea class="form-control dp-section-text">${dpEsc(s.texte)}</textarea></div>`).join('')}</div>
      <button class="btn btn-default btn-xs dp-add-section" style="margin-top:10px">Ajouter une rubrique</button>
      <label class="dp-label">Caractéristiques techniques</label><div class="dp-table-wrap"><table class="dp-table"><thead><tr><th>Caractéristique</th><th>Valeur</th><th>Unité</th><th>Modèles concernés</th><th>Source</th><th></th></tr></thead><tbody>${c.caracteristiques.map((s,i)=>`<tr data-index="${i}"><td><input class="form-control input-sm" data-key="nom" value="${dpEsc(s.nom)}"></td><td><input class="form-control input-sm" data-key="valeur" value="${dpEsc(s.valeur)}"></td><td><input class="form-control input-sm" data-key="unite" value="${dpEsc(s.unite)}"></td><td><select class="form-control input-sm" data-key="article">${scope(s.article)}</select></td><td><input class="form-control input-sm" data-key="source" value="${dpEsc(s.source)}"></td><td><button class="btn btn-xs btn-default dp-remove-carac">×</button></td></tr>`).join('')}</tbody></table></div><button class="btn btn-default btn-xs dp-add-carac">Ajouter une caractéristique</button>
      <label class="dp-label">Légendes des photos</label>${c.legendes.map((s,i)=>`<input class="form-control dp-doc-caption" data-index="${i}" style="margin-bottom:6px" value="${dpEsc(s)}">`).join('') || '<div class="dp-muted">Aucune illustration sélectionnée.</div>'}
      <label class="dp-label">Points à vérifier avant validation — retirez chaque point une fois résolu</label><textarea class="form-control dp-checks" placeholder="Aucun point en attente">${dpEsc(c.points_a_verifier.join('\n'))}</textarea>
      <details style="margin-top:14px"><summary>Variantes et sources de cette version</summary><div class="dp-table-wrap"><table class="dp-table">${c.variantes.map(v=>`<tr><td>${dpEsc(v.article)}</td><td>${dpEsc(v.marque)}</td><td>${v.attributs.map(a=>dpEsc(a.nom+' : '+a.valeur)).join('<br>')}</td></tr>`).join('')}</table></div>${(ctx.preuves||[]).map(p=>`<details><summary>${dpEsc(p.source+' · '+p.fichier)}</summary><div style="white-space:pre-wrap;padding:10px">${dpEsc(p.texte)}</div></details>`).join('')}</details></div>
      ${doc.pdf?`<div class="dp-review-pdf"><iframe class="dp-preview" title="Aperçu PDF" src="${dpUrl(doc.pdf)}#toolbar=1"></iframe></div>`:'<div class="dp-muted dp-review-pdf" style="margin-top:12px">Pas encore de PDF pour cette version : relisez, puis cliquez sur « Générer le PDF ».</div>'}</div>`);
    z.find('.dp-editor').on('input change',()=>{this.dirty=true;this.renderLayoutPreview();this.updateBar();});
    z.find('.dp-remove-section,.dp-remove-carac').on('click',e=>{$(e.currentTarget).closest('.dp-section,tr').remove();this.dirty=true;this.updateBar();});
    const add=(key,row)=>{this.current.contenu=this.captureDocument();this.current.contenu[key].push(row);this.renderDocument();this.dirty=true;this.updateBar();};
    z.find('.dp-add-section').on('click',()=>add('sections',{titre:'Nouvelle rubrique',texte:'',article:'',source:'Saisie manuelle'}));
    z.find('.dp-add-carac').on('click',()=>add('caracteristiques',{nom:'',valeur:'',unite:'',article:'',source:'Saisie manuelle'}));
    z.find('.dp-translate').on('click',()=>this.translation());
    z.find('.dp-pdf').on('click',()=>this.lancer('pdf'));
    z.find('.dp-validate').on('click',()=>this.lancer('valider'));
    z.find('.dp-source-fr').on('click',async e=>{e.preventDefault();if(this.dirty)await this.saveDocument();await this.loadDocument(doc.source_fr);});
    if(!this.data.peut_ecrire)z.find('button,input,textarea,select').prop('disabled',true);
    this.showState(this.data.dossier);
  }
  captureDocument() {
    const c=JSON.parse(JSON.stringify(this.current.contenu)),z=this.root.find('.dp-editor');
    c.titre=z.find('.dp-title').val();c.resume=z.find('.dp-summary').val();
    c.sections=z.find('.dp-section').map((_,el)=>{const q=$(el);return {titre:q.find('.dp-section-name').val(),texte:q.find('.dp-section-text').val(),article:q.find('.dp-section-scope').val(),source:q.find('.dp-section-source').val()};}).get();
    c.caracteristiques=z.find('.dp-table tbody tr').map((_,el)=>{const r={};$(el).find('[data-key]').each((_,f)=>r[$(f).attr('data-key')]=$(f).val());return r;}).get();
    c.points_a_verifier=(z.find('.dp-checks').val()||'').split('\n').map(s=>s.trim()).filter(Boolean);
    c.legendes=z.find('.dp-doc-caption').map((_,el)=>el.value).get();return c;
  }
  async saveDocument() {
    if(!this.current||!this.dirty)return;
    await this.saveConfig();
    const r=await dpCall('corriger',{name:this.current.doc.name,contenu:this.captureDocument()});
    this.current=await dpCall('lire_document',{name:r.name});this.dirty=false;
    this.data=await dpCall('charger',{name:this.name});this.rendre();
    frappe.show_alert({message:'Version enregistrée',indicator:'green'});
  }
  async translation() {
    if(this.dirty)await this.saveDocument();
    const opts=this.data.langues.filter(l=>l.code!=='fr').map(l=>({label:l.libelle,value:l.code}));opts.push({label:'Autre langue…',value:'autre'});
    const d=new frappe.ui.Dialog({title:'Traduire et enregistrer',fields:[{fieldtype:'Select',fieldname:'choix',label:'Langue',options:opts,default:opts.some(x=>x.value==='en')?'en':opts[0]?.value},
      {fieldtype:'Data',fieldname:'code',label:'Code de langue (ex. ja, zh, tr)',depends_on:"eval:doc.choix === 'autre'"},{fieldtype:'Data',fieldname:'libelle',label:'Nom de la langue',depends_on:"eval:doc.choix === 'autre'"},
      {fieldtype:'Check',fieldname:'rtl',label:'Écriture de droite à gauche',depends_on:"eval:doc.choix === 'autre'"},
      {fieldtype:'HTML',fieldname:'info',options:'<p class="text-muted small">La traduction sera enregistrée automatiquement comme nouvelle version. Vous pourrez ensuite la corriger et générer son PDF.</p>'}],
      primary_action_label:'Traduire et enregistrer',primary_action:async v=>{const langue=v.choix==='autre'?v.code:v.choix,libelle=v.choix==='autre'?v.libelle:this.data.langues.find(x=>x.code===v.choix)?.libelle;
        if(!langue||!libelle)return frappe.msgprint('Indiquez le code et le nom de la langue.');await this.lancer('traduire',{langue,libelle,rtl:v.rtl||0});d.hide();}});d.show();
  }
  async lancer(action,extra={}) {
    if(this.dirty)await this.saveDocument();await this.saveConfig();
    const doc=this.current?.doc;
    this.jobTarget={type:DP_TYPES[action]||(action==='les_deux'?this.typeActif():doc?.type_document),langue:extra.langue||(action==='pdf'||action==='valider'?doc?.langue:'fr')};
    await dpCall('lancer',{name:this.name,action,document_name:doc?.name,...extra});
    this.data.dossier.etat_traitement='En attente';this.showState(this.data.dossier);
    if(['fiche','manuel','les_deux','traduire'].includes(action))this.showStep('relire');
    this.poll();
  }
  showState(s) {
    const busy=['En attente','En cours'].includes(s.etat_traitement),zone=this.root.find('.dp-progress');
    if(s.etat_traitement){zone.show().html(`<div class="${s.etat_traitement==='Échec'?'dp-error':''}">${dpEsc(s.message_traitement||s.etat_traitement)}</div>${busy?`<progress max="100" value="${s.progression||0}"></progress>`:''}`);}else zone.hide();
    this.root.find('button,input,textarea,select').prop('disabled',busy||!!this.switchingTab||!this.data.peut_ecrire);
    this.root.find('.dp-versions,.dp-tab').prop('disabled',busy||!!this.switchingTab);
    // Naviguer entre les étapes et lire le guide reste possible pendant un traitement.
    this.root.find('.dp-step-btn,.dp-guide,[data-goto]').prop('disabled',false);
    this.root.find('.dp-order-row').attr('draggable',!busy&&!this.switchingTab&&!!this.data.peut_ecrire);
    this.root.find('.dp-load-free-background').prop('disabled',busy||!!this.switchingTab||!!this.freePreviewLoading);
    this.root.find('.dp-free-brand').attr({'aria-disabled':String(!this.canMoveLogo()),tabindex:this.canMoveLogo()?0:-1});
    this.updateBar();
  }
  async poll() {
    clearTimeout(this.timer);if(frappe.get_route()[0]!=='documents-produit'||frappe.get_route()[1]!==this.name)return;
    try{
      const s=await dpCall('etat',{name:this.name}),wasBusy=['En attente','En cours'].includes(this.data.dossier.etat_traitement);
      const {modified,...etat}=s;Object.assign(this.data.dossier,etat);this.showState(s);
      if(wasBusy&&!['En attente','En cours'].includes(s.etat_traitement)){
        this.data=await dpCall('charger',{name:this.name});this.rendre();
        const target=this.jobTarget&&this.documentsActifs().find(v=>(!this.jobTarget.type||v.type_document===this.jobTarget.type)&&v.langue===this.jobTarget.langue);
        if(target)await this.loadDocument(target.name);this.jobTarget=null;
      }
    }catch(e){console.error(e);}
    this.timer=setTimeout(()=>this.poll(),2500);
  }
}
