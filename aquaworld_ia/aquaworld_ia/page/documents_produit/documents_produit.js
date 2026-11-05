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
const dpLayoutDefault = () => ({position_photo:'apres',largeur_photo:65,hauteur_photo:65,alignement_titre:'gauche',couleur:'#087E8B',ordre:Object.keys(DP_BLOCKS),position_marque:'avant_titre',alignement_marque:'gauche',largeur_logo:32,afficher_nom_marque:0,logo_x:150,logo_y:8});
const dpLogoUrl = b => dpUrl(b?.logo)+(b?.logo_hash?'?v='+encodeURIComponent(b.logo_hash):'');

class DocumentsProduit {
  constructor(page, root) { this.page=page; this.root=root; this.name=null; this.current=null; this.dirty=false; this.activeTab='fiche'; this.selectedVersions={}; this.helpOpen={}; }
  async ouvrir() {
    clearTimeout(this.timer); this.name=frappe.get_route()[1] || null;
    this.loadSequence=(this.loadSequence||0)+1;this.jobTarget=null;this.selectedVersions={};
    this.root.html('<div class="dp-card">Chargement…</div>');
    if (!this.name) return this.liste();
    this.data=await dpCall('charger',{name:this.name}); this.current=null; this.dirty=false;
    let tab=frappe.get_route()[2];
    if(!Object.hasOwn(DP_TYPES,tab)){try{tab=sessionStorage.getItem('dp-tab:'+this.name);}catch{tab=null;}}
    this.activeTab=Object.hasOwn(DP_TYPES,tab)?tab:this.data.documents.some(v=>v.type_document===DP_TYPES.fiche)?'fiche':this.data.documents.some(v=>v.type_document===DP_TYPES.manuel)?'manuel':'fiche';
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
  scopeOptions(value='') {
    return `<option value="">Toute la gamme</option>${this.data.dossier.variantes.map(r=>`<option value="${dpEsc(r.article)}" ${r.article===value?'selected':''}>${dpEsc(r.article)}</option>`).join('')}`;
  }
  typeActif() { return DP_TYPES[this.activeTab]; }
  documentsActifs() { return this.data.documents.filter(v=>v.type_document===this.typeActif()); }
  async switchTab(tab) {
    if(!Object.hasOwn(DP_TYPES,tab)||tab===this.activeTab||this.switchingTab||['En attente','En cours'].includes(this.data.dossier.etat_traitement))return;
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
  usageGuide() {
    const manuel=this.activeTab==='manuel',titre=manuel?'Manuel d’utilisation':'Fiche technique',creer=manuel?'Créer le manuel':'Créer la fiche technique';
    return `<details class="dp-card dp-help" ${this.helpOpen[this.activeTab]?'open':''}>
      <summary>Comment utiliser cet onglet ? · ${titre}</summary>
      <div class="dp-help-body">
        <p>${manuel?'Cet onglet prépare un manuel pour accompagner l’installation, l’utilisation, l’entretien et le dépannage du produit, à partir des informations disponibles.':'Cet onglet prépare une fiche pour présenter le produit, ses applications, ses caractéristiques techniques et les variantes sélectionnées.'}</p>
        <ol class="dp-help-steps">
          <li><strong>Préparer les informations.</strong> Ouvrez <b>Sources, photos et variantes</b>. Sélectionnez les variantes, utilisez <b>Ajouter un document</b> pour vos sources et <b>Ajouter une photo</b> pour les images du produit. Précisez les pages utiles et la variante concernée si nécessaire. La première photo de la version sera la photo principale.
            <p>${manuel?'Ajoutez les notices du fabricant, les schémas et les photos utiles aux étapes d’installation ou d’entretien. Dans Consignes de rédaction, indiquez le public visé et les rubriques souhaitées.':'Vérifiez les données de l’article en cliquant sur sa référence en haut de la page. Renseignez les dimensions, matériaux, performances et applications dans l’article ou les documents sources. Utilisez Consignes de rédaction pour indiquer le public visé et le style souhaité.'} Cliquez sur <b>Enregistrer les sources et la sélection</b>.</p>
            <p><b>Sans PDF de référence :</b> l’IA part des données de l’article et des variantes. Vos consignes guident la rédaction, mais ne remplacent pas une source technique. Les informations manquantes restent à vérifier${manuel?', notamment les procédures d’installation, d’utilisation et de sécurité':''}.</p>
          </li>
          <li><strong>Choisir la marque et la présentation.</strong> Réglez <b>Marque du document</b>, <b>En-tête des PDF</b> et <b>Mise en page personnalisée</b> à l’aide des explications ci-dessous. La mise en page est propre à cet onglet.</li>
          <li><strong>Choisir le modèle et rédiger.</strong> Dans le cadre des coûts, <b>Régler les modèles par outil</b> ouvre les réglages IA. Choisissez le modèle de ${manuel?'manuel produit':'fiche technique'}, puis revenez ici et cliquez sur <b>${creer}</b>. L’IA rédige le contenu et enregistre une version française ; le coût estimé apparaît dans l’historique du dossier.
            <p>${manuel?'Les rubriques couvrent les étapes d’installation, de mise en service, d’utilisation, d’entretien et de dépannage selon les sources. Relisez en particulier les procédures, les réglages et les consignes de sécurité.':'L’IA prépare le titre, la présentation, les rubriques et les caractéristiques. La structure est prévue par l’outil ; les informations disponibles déterminent les rubriques remplies.'}</p>
          </li>
          <li><strong>Relire et corriger.</strong> Dans <b>${manuel?'Manuels et traductions enregistrés':'Fiches techniques et traductions enregistrées'}</b>, choisissez une version. Modifiez le titre, la présentation, les rubriques, les caractéristiques et les légendes, puis cliquez sur <b>Enregistrer mes corrections</b>. Résolvez les <b>Points à vérifier avant validation</b>, puis retirez de cette liste les points effectivement traités.</li>
          <li><strong>Produire le PDF.</strong> Cliquez sur <b>Générer le PDF</b> pour vérifier le résultat, ou sur <b>Valider et générer le PDF</b> une fois la relecture terminée et les points à vérifier résolus. L’aperçu et <b>Télécharger le PDF</b> apparaissent dans la version. LaTeX compose le document à partir du contenu et de vos réglages ; cette étape ne déclenche aucun appel IA.</li>
          <li><strong>Traduire si besoin.</strong> Depuis une version française, cliquez sur <b>Traduire</b> et choisissez la langue. Une nouvelle version est enregistrée dans cet onglet ; relisez-la puis générez son PDF. La traduction utilise l’IA et son coût figure dans l’historique.</li>
        </ol>
        <div class="dp-help-grid">
          <section><h4>Logo de la marque : ajouter et placer</h4>
            <p>Dans <b>Marque du document</b>, choisissez une marque ou utilisez <b>Créer une marque</b>, puis <b>Enregistrer la marque</b>. Cliquez sur <b>Ajouter / remplacer le logo</b> pour importer son image. Le logo est partagé avec les autres produits de cette marque ; <b>Actualiser le logo</b> recharge une image modifiée.</p>
            <p>Dans <b>Mise en page personnalisée → Zone de marque</b>, choisissez une position ou cliquez sur <b>Déplacer le logo à la souris</b>. Faites glisser son cadre sur la première page A4, ou saisissez les distances depuis les bords gauche et haut. Vous pouvez régler la largeur et afficher le nom de marque.</p>
            <p><b>Actualiser le fond PDF</b> affiche le contenu pour vérifier l’emplacement. Le logo libre se superpose au texte sur la première page : placez-le dans une zone dégagée. Vous pouvez déplacer son cadre avant d’avoir ajouté l’image.</p>
          </section>
          <section><h4>En-tête et pied de page</h4>
            <p>Dans <b>En-tête des PDF</b>, cliquez sur <b>Créer un en-tête</b>. L’éditeur visuel s’ouvre dans l’outil : donnez un nom au modèle, choisissez une disposition (logo à gauche, à droite ou centré), ajoutez votre logo et saisissez le nom et les coordonnées.</p>
            <p>Remplissez les deux blocs de contacts et le pied de page avec l’adresse et le site. Les blocs sans coordonnées sont masqués. Réglez la taille du logo, la couleur et les traits de séparation ; l’aperçu se met à jour automatiquement.</p>
            <p>Cliquez sur <b>Enregistrer et utiliser</b> : le modèle est sélectionné dans le dossier. Vous pourrez le reprendre avec <b>Modifier visuellement</b> ou en enregistrer une copie. Générez ensuite le PDF. L’en-tête et le pied de page se répètent sur chaque page ; le numéro de page est ajouté automatiquement.</p>
            <p><b>Réglages avancés</b> ouvre la fiche native pour les anciens modèles en image ou en HTML. Pour conserver aussi le logo dans le corps du document, cochez <b>Afficher aussi le logo de la marque avec un en-tête personnalisé</b>.</p>
          </section>
          <section><h4>Photo, description et ordre des blocs</h4>
            <p>Dans <b>Mise en page personnalisée</b>, choisissez <b>Une colonne</b> pour placer la photo et le texte l’un sous l’autre, ou <b>Deux colonnes</b> pour les mettre côte à côte. Choisissez le côté de la photo, sa largeur et sa hauteur maximale.</p>
            <p>Réglez l’alignement du titre, la couleur des titres et l’ordre des blocs avec les flèches ou le glisser-déposer. Cliquez sur <b>Enregistrer la mise en page</b>, puis sur <b>Générer le PDF</b> dans la version à mettre en forme. La longueur du contenu détermine le nombre de pages.</p>
          </section>
          <section><h4>Versions, réglages et coût</h4>
            <p>La marque, l’en-tête, les sources, les photos et les consignes sont communs aux deux onglets. La mise en page, les versions et les traductions sont propres à chaque onglet. Le modèle IA se règle par outil pour les prochaines générations. <b>Créer les deux</b> lance les deux rédactions.</p>
            <p>Pour modifier seulement le logo, l’en-tête ou la disposition, générez le PDF depuis le contenu existant. Une modification de présentation crée une nouvelle version et conserve les anciennes, sans nouvelle rédaction IA. Un changement de marque commerciale demande une nouvelle rédaction pour actualiser les textes.</p>
            <p><b>Modèles et tarifs par étape</b> affiche les modèles et tarifs configurés ; <b>Coût par génération du dossier</b> et <b>Détail</b> expliquent les montants. Rédaction, lecture des scans et traduction peuvent consommer des jetons. Corrections manuelles, placement du logo et composition PDF n’ajoutent aucun coût IA.</p>
          </section>
        </div>
      </div>
    </details>`;
  }
  renderStructure() {
    const z=this.root.find('.dp-layout'),m=this.layoutValues();
    const options=(items,value)=>Object.entries(items).map(([v,label])=>`<option value="${v}" ${v===value?'selected':''}>${label}</option>`).join('');
    z.html(`<summary>Mise en page personnalisée · ${this.activeTab==='fiche'?'fiche technique':'manuel'}</summary>
      <p class="dp-muted" style="margin-top:12px">Choisissez la position de la photo et l’ordre des blocs pour cet onglet. L’IA rédige le contenu ; ces réglages déterminent sa présentation en PDF.</p>
      <div class="dp-designer-grid"><div><div class="dp-brand-zone-settings"><h3>Zone de marque</h3>
      <p class="dp-muted dp-zone-brand-status" role="status"></p>
      <div class="dp-actions"><button class="btn btn-primary btn-sm dp-enable-free-logo">Déplacer le logo à la souris</button><button class="btn btn-default btn-sm dp-zone-upload">Choisir la marque / ajouter son logo</button><button class="btn btn-default btn-sm dp-zone-refresh">Actualiser le logo</button></div>
      <div class="dp-grid"><label class="dp-label">Position de la zone de marque<select class="form-control dp-layout-brand-position">${options({libre:'Placement libre sur la première page',avant_titre:'Au-dessus du titre',apres_titre:'Sous le titre',fin_document:'À la fin du document',masquee:'Masquer cette zone'},m.position_marque)}</select></label>
      <label class="dp-label">Alignement du logo<select class="form-control dp-layout-brand-align">${options({gauche:'À gauche',centre:'Centré',droite:'À droite'},m.alignement_marque)}</select></label>
      <label class="dp-label">Largeur maximale du logo (mm)<input class="form-control dp-layout-logo-width" type="number" min="10" max="70" step="1" value="${m.largeur_logo}"></label>
      <label class="dp-label"><input type="checkbox" class="dp-layout-brand-name" ${m.afficher_nom_marque?'checked':''}> Afficher aussi le nom dans cette zone</label></div>
      <div class="dp-free-controls"><div class="dp-grid"><label class="dp-label">Distance depuis le bord gauche (mm)<input class="form-control dp-logo-x" type="number" step="0.1" min="0" value="${m.logo_x}"></label><label class="dp-label">Distance depuis le bord haut (mm)<input class="form-control dp-logo-y" type="number" step="0.1" min="0" value="${m.logo_y}"></label></div><p class="dp-muted">Faites glisser le cadre dans la page A4 à droite, ou utilisez ces coordonnées. Au clavier : flèches = 1 mm ; Maj + flèches = 10 mm. Le logo se superpose au contenu de la première page : vérifiez qu’il ne couvre pas un texte.</p></div>
      <p class="dp-muted">Le logo conserve ses proportions. La zone apparaît une fois dans le document. L’en-tête personnalisé reste répété sur les pages.</p></div><h3>Zone photo et description</h3>
      <div class="dp-column-choices" role="group" aria-label="Diviser la zone photo et description">
      <button type="button" class="dp-column-choice" data-columns="1"><span class="dp-column-icon dp-column-icon-one" aria-hidden="true"><span>Photo</span><span>Description</span></span><b>Une colonne</b><small>Éléments l’un sous l’autre</small></button>
      <button type="button" class="dp-column-choice" data-columns="2"><span class="dp-column-icon dp-column-icon-two" aria-hidden="true"><span>Photo</span><span>Description</span></span><b>Deux colonnes</b><small>Photo et description côte à côte</small></button></div>
      <p class="dp-muted dp-column-proportions" aria-live="polite" style="margin-top:10px"></p><div class="dp-grid">
      <label class="dp-label">Position de la photo<select class="form-control dp-layout-position">${options({avant:'1 colonne · Photo au-dessus',apres:'1 colonne · Photo en dessous',gauche:'2 colonnes · Photo à gauche',droite:'2 colonnes · Photo à droite'},m.position_photo)}</select></label>
      <label class="dp-label">Alignement du titre<select class="form-control dp-layout-title-align">${options({gauche:'À gauche',centre:'Centré',droite:'À droite'},m.alignement_titre)}</select></label>
      <label class="dp-label"><span class="dp-layout-width-label">Largeur de la photo (%)</span><input class="form-control dp-layout-width" type="number" min="20" max="${['gauche','droite'].includes(m.position_photo)?55:80}" step="1" value="${m.largeur_photo}"></label>
      <label class="dp-label">Hauteur maximale de la photo (mm)<input class="form-control dp-layout-height" type="number" min="20" max="120" step="1" value="${m.hauteur_photo}"></label>
      <label class="dp-label">Couleur des titres<input class="form-control dp-layout-color" type="color" value="${m.couleur}" style="width:90px;height:36px"></label></div>
      <p class="dp-muted">La photo conserve ses proportions. À côté du texte, sa largeur est limitée à 55 %. La première photo de la version est la photo principale.</p>
      <h3 style="margin-top:18px">Ordre des blocs</h3><p class="dp-muted">Déplacez les blocs dans la liste ou utilisez les flèches. L’en-tête et le titre restent en haut, le pied de page en bas.</p><div class="dp-layout-order"></div>
      <div class="dp-actions" style="margin-top:14px"><button class="btn btn-primary btn-sm dp-save-layout">Enregistrer la mise en page</button><button class="btn btn-default btn-sm dp-reset-layout">Disposition initiale</button></div>
      <p class="dp-muted dp-layout-status" role="status" style="margin-top:10px">Après un changement, cliquez sur « Générer le PDF » dans la version du document. Une nouvelle version conserve la mise en page, sans nouvelle rédaction IA.</p>
      </div><div><div class="dp-layout-preview"></div><p class="dp-muted" style="margin-top:12px">Aperçu de disposition : les blocs sans contenu sont omis du PDF. La pagination dépend de la longueur du texte ; le document peut comporter plusieurs pages.</p></div></div>
      <details style="margin-top:14px"><summary>Comment le contenu est-il préparé ?</summary><ol class="dp-muted dp-outline"><li>Choisissez la marque, ajoutez son logo, les photos du produit et vos documents de référence éventuels dans les réglages du dossier.</li><li>Cliquez sur « ${this.activeTab==='fiche'?'Créer la fiche technique':'Créer le manuel'} ». L’IA rédige les textes à partir de l’article, des variantes, de vos consignes et des sources disponibles. Les informations manquantes restent à vérifier.</li><li>Relisez la version enregistrée. Vous pouvez modifier le titre, la description, les rubriques, les caractéristiques et les légendes directement dans l’outil.</li><li>Cliquez sur « Générer le PDF ». LaTeX place le contenu, les images et le logo selon vos réglages, sans nouvelle rédaction IA.</li></ol><p class="dp-muted">Un changement de logo ou de mise en page s’applique en générant le PDF. Un changement de marque commerciale demande une nouvelle rédaction pour actualiser aussi les textes. Les versions déjà enregistrées sont conservées.</p>${this.activeTab==='manuel'?'<p class="dp-muted">Les rubriques proposées couvrent installation, utilisation, entretien et dépannage, selon les sources disponibles.</p>':''}</details>`);
    z.find('.dp-layout-position,.dp-layout-title-align,.dp-layout-width,.dp-layout-height,.dp-layout-color,.dp-layout-brand-position,.dp-layout-brand-align,.dp-layout-logo-width,.dp-layout-brand-name,.dp-logo-x,.dp-logo-y').on('input change',()=>{
      const position=z.find('.dp-layout-position').val(),maximum=['gauche','droite'].includes(position)?55:80;
      const borne=(selector,min,max,def)=>Math.max(min,Math.min(max,Math.round(Number(z.find(selector).val())||def)));
      const largeur=borne('.dp-layout-width',20,maximum,65);
      if(Number(z.find('.dp-layout-width').val())>maximum)z.find('.dp-layout-width').val(largeur);
      z.find('.dp-layout-width').attr('max',maximum);
      this.layouts[this.activeTab]={...this.layoutValues(),position_photo:position,largeur_photo:largeur,hauteur_photo:borne('.dp-layout-height',20,120,65),alignement_titre:z.find('.dp-layout-title-align').val(),couleur:z.find('.dp-layout-color').val(),position_marque:z.find('.dp-layout-brand-position').val(),alignement_marque:z.find('.dp-layout-brand-align').val(),largeur_logo:borne('.dp-layout-logo-width',10,70,32),afficher_nom_marque:z.find('.dp-layout-brand-name').prop('checked')?1:0,logo_x:Number(z.find('.dp-logo-x').val())||0,logo_y:Number(z.find('.dp-logo-y').val())||0};
      this.clampLogoPosition();
      this.renderColumnChoices();this.renderLayoutPreview();this.layoutChanged();
    });
    z.find('.dp-enable-free-logo').on('click',()=>{z.find('.dp-layout-brand-position').val('libre').trigger('change');this.root.find('.dp-free-sheet')[0]?.scrollIntoView({behavior:'smooth',block:'center'});this.loadFreeBackground();});
    z.find('.dp-zone-upload').on('click',()=>{const upload=this.root.find('.dp-upload-brand-logo')[0];if(upload&&!upload.disabled)upload.click();else{this.root.find('.dp-brand-card')[0].scrollIntoView({behavior:'smooth',block:'center'});this.root.find('.dp-brand').trigger('focus');}});
    z.find('.dp-zone-refresh').on('click',()=>this.renderBrand());
    z.find('[data-columns]').on('click',e=>{
      const deux=$(e.currentTarget).attr('data-columns')==='2',cote=['gauche','droite'].includes(this.layoutValues().position_photo);
      if(deux===cote)return;
      if(deux)z.find('.dp-layout-width').val(50);
      z.find('.dp-layout-position').val(deux?'gauche':'apres').trigger('change');
    });
    z.find('.dp-save-layout').on('click',async()=>{if(this.dirty)await this.saveDocument();await this.saveConfig();this.root.find('.dp-layout-status').text('Mise en page enregistrée. Générez le PDF pour l’appliquer à la version choisie.');frappe.show_alert({message:'Mise en page enregistrée',indicator:'green'});});
    z.find('.dp-reset-layout').on('click',()=>{this.layouts[this.activeTab]=dpLayoutDefault();this.renderStructure();this.layoutChanged();this.showState(this.data.dossier);});
    this.renderColumnChoices();this.renderLayoutOrder();this.renderLayoutPreview();
  }
  renderColumnChoices() {
    const m=this.layoutValues(),cote=['gauche','droite'].includes(m.position_photo);
    this.root.find('[data-columns]').each((_,el)=>{const actif=el.dataset.columns===(cote?'2':'1');$(el).toggleClass('active',actif).attr('aria-pressed',String(actif));});
    this.root.find('.dp-layout-width-label').text(cote?'Largeur de la colonne photo (%)':'Largeur de la photo (%)');
    this.root.find('.dp-column-proportions').text(cote?`Deux colonnes : photo ${m.largeur_photo} % · description ${100-m.largeur_photo} %. La répartition concerne uniquement cette zone ; les autres blocs conservent toute la largeur.`:'Une colonne : la photo et la description se suivent sur la page.');
  }
  layoutValues() { return {...dpLayoutDefault(),...(this.layouts?.[this.activeTab]||{})}; }
  canMoveLogo() { return this.data.peut_ecrire&&!this.switchingTab&&!['En attente','En cours'].includes(this.data.dossier.etat_traitement); }
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
    const mise_en_page={};['position_photo','largeur_photo','hauteur_photo','alignement_titre','couleur','ordre'].forEach(k=>mise_en_page[k]=m[k]);
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
  layoutChanged() { this.root.find('.dp-layout-status').text('Disposition modifiée. Enregistrez-la ou générez le PDF pour l’appliquer.'); }
  moveLayoutBlock(from,to) {
    if(!this.data.peut_ecrire||this.switchingTab||['En attente','En cours'].includes(this.data.dossier.etat_traitement))return;
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
    const m=this.layoutValues(),c=this.current?.contenu,ctx=this.current?.contexte||this.data.contexte,im=ctx.images?.[0];
    this.root.find('.dp-free-controls').toggle(m.position_marque==='libre');
    this.root.find('.dp-layout-brand-align').closest('label').toggle(m.position_marque!=='libre');
    const marque=this.brandInfo||{name:this.root.find('.dp-brand').val()||this.data.contexte.article.brand||'',logo:''};
    const entete=this.root.find('.dp-letterhead').val(),logoAvecEntete=this.root.find('.dp-brand-with-header').prop('checked');
    const logoAutorise=!entete||logoAvecEntete,logo=logoAutorise&&dpUrl(marque.logo)?dpLogoUrl(marque):'';
    const alignMarque={gauche:'left',centre:'center',droite:'right'}[m.alignement_marque];
    let statut=this.brandLoading?'Chargement du logo…':!marque.name?'Choisissez une marque dans « Marque du document ».':!marque.logo?`${marque.name} : aucun logo disponible. Ajoutez son image pour la voir ici.`:`${marque.name} : le logo est visible dans cet aperçu de disposition.`;
    if(marque.logo&&!logoAutorise)statut='Pour afficher le logo avec l’en-tête choisi, cochez « Afficher aussi le logo de la marque avec un en-tête personnalisé » dans Marque du document.';
    if(m.position_marque==='masquee')statut='La zone de marque est masquée. Les mentions de la marque dans les textes sont conservées.';
    if(this.current&&marque.name!==(ctx.marque_document||ctx.article.brand||''))statut+=' La marque choisie diffère de cette version : créez une nouvelle fiche ou un nouveau manuel pour actualiser les textes.';
    this.root.find('.dp-zone-brand-status').text(statut);
    if(m.position_marque==='libre'){
      const hLogo=m.largeur_logo*18/32,h=hLogo+(m.afficher_nom_marque?8:0),fond=this.freeBackground?.key===this.freeBackgroundKey()?this.freeBackground:null;
      const image=logo?`<img class="dp-design-brand-logo dp-free-brand-logo" src="${logo}" alt="Logo ${dpEsc(marque.name)}" draggable="false" style="height:${hLogo/h*100}%">`:`<div class="dp-free-placeholder" style="height:${hLogo/h*100}%">${logoAutorise?'Logo à ajouter':'Logo masqué par l’en-tête'}</div>`;
      this.root.find('.dp-layout-preview').html(`<p class="dp-muted">Première page · A4 · 210 × 297 mm</p><div class="dp-free-sheet" aria-label="Page A4 pour placer librement le logo">${fond?`<img class="dp-free-background" src="${fond.image}" alt="Première page du document sans la zone de marque" draggable="false">`:'<div class="dp-free-margins"><span>Zone de contenu<br>Actualisez le fond pour voir le document.</span></div>'}<div class="dp-free-brand" role="group" aria-label="Logo déplaçable : utilisez la souris ou les flèches du clavier" tabindex="${this.canMoveLogo()?0:-1}" aria-disabled="${!this.canMoveLogo()}" style="left:${m.logo_x/210*100}%;top:${m.logo_y/297*100}%;width:${m.largeur_logo/210*100}%;height:${h/297*100}%">${image}${m.afficher_nom_marque?`<strong class="dp-free-brand-name" style="height:${8/h*100}%;font-size:calc(${Math.min(3,m.largeur_logo/(Math.max(marque.name.length,1)*.6))} * 100cqw / 210)">${dpEsc(marque.name)}</strong>`:''}</div></div><p class="dp-muted dp-free-coordinates" aria-live="polite">X : ${m.logo_x.toFixed(1)} mm · Y : ${m.logo_y.toFixed(1)} mm</p><button class="btn btn-default btn-sm dp-load-free-background" ${this.freePreviewLoading?'disabled':''}>${this.freePreviewLoading?'Préparation du fond…':'Actualiser le fond PDF'}</button><p class="dp-muted dp-free-background-status" style="margin-top:8px">${this.freePreviewError|| (fond?(fond.exemple?'Fond d’exemple : aucun contenu IA n’a été rédigé.':'Fond issu de la version sélectionnée, avec vos corrections en cours.'): 'Le fond doit être actualisé après un changement du contenu ou de la disposition.')} Déplacer le logo ne relance pas la composition du fond.</p>`);
      this.bindFreeLogo();return;
    }
    const contenuMarque=logo?`<img class="dp-design-brand-logo" src="${logo}" alt="Logo ${dpEsc(marque.name)}" style="width:${m.largeur_logo*1.8}px;max-height:${m.largeur_logo*18/32*1.8}px">`:logoAutorise?`<span class="dp-design-brand-placeholder">${this.brandLoading?'Chargement du logo…':'Logo '+dpEsc(marque.name||'de marque')+' à ajouter'}</span>`:'';
    const zoneMarque=m.position_marque!=='masquee'&&(contenuMarque||m.afficher_nom_marque)?`<div class="dp-design-brand" data-brand-position="${m.position_marque}" style="text-align:${alignMarque}">${contenuMarque}${m.afficher_nom_marque?`<strong class="dp-design-brand-name">${dpEsc(marque.name)}</strong>`:''}</div>`:'';
    const titre=this.root.find('.dp-title').val()??c?.titre??this.typeActif(),resume=this.root.find('.dp-summary').val()??c?.resume??'Description du produit, rédigée à partir des informations disponibles.';
    const couleur=/^#[0-9a-f]{6}$/i.test(m.couleur)?m.couleur:'#087E8B',align={gauche:'left',centre:'center',droite:'right'}[m.alignement_titre];
    const cote=['gauche','droite'].includes(m.position_photo),largeur=Math.min(cote?55:80,m.largeur_photo),hauteur=Math.min(120,m.hauteur_photo)*1.4;
    const photo=`<div class="dp-design-photo" style="${cote?'':`width:${largeur}%;margin-left:auto;margin-right:auto;`}">${im?`<img src="${dpUrl(im.image)}" alt="${dpEsc(im.legende||'Photo principale')}" style="max-height:${hauteur}px">`:`<div class="dp-design-placeholder" style="height:${hauteur}px">Photo principale</div>`}<small>${dpEsc(c?.legendes?.[0]||im?.legende||'Légende')}</small></div>`;
    const description=`<div class="dp-design-description">${dpEsc(resume.slice(0,210))}${resume.length>210?'…':''}</div>`;
    const parties=['avant','gauche'].includes(m.position_photo)?[photo,description]:[description,photo];
    const ratio=m.position_photo==='gauche'?largeur:100-largeur;
    const presentation=`<div class="dp-design-presentation ${cote?'dp-design-columns':''}" style="${cote?`grid-template-columns:minmax(0,${ratio}fr) minmax(0,${100-ratio}fr)`:''}">${parties.join('')}</div>`;
    const blocs={presentation,rubriques:`<div class="dp-design-block">${this.activeTab==='manuel'?'Installation · Utilisation<br>Entretien · Dépannage':'Présentation · Applications'}</div>`,caracteristiques:'<div class="dp-sheet-table">Caractéristiques techniques</div>',variantes:'<div class="dp-design-block">Tableau des variantes</div>',illustrations:'<div class="dp-design-block">Autres illustrations</div>'};
    this.root.find('.dp-layout-preview').html(`<div class="dp-sheet dp-design-sheet" aria-label="Aperçu de la mise en page"><div class="dp-sheet-header">${entete?'En-tête : '+dpEsc(entete):'Document A4'}</div>${m.position_marque==='avant_titre'?zoneMarque:''}<div class="dp-sheet-title" style="color:${couleur};text-align:${align}">${dpEsc(titre)}</div><div class="dp-sheet-small" style="text-align:${align}">${dpEsc(marque.name)} · ${dpEsc(ctx.article.name)}</div>${m.position_marque==='apres_titre'?zoneMarque:''}<div class="dp-design-blocks" style="--dp-accent:${couleur}">${m.ordre.map(k=>`<div data-preview-block="${k}">${blocs[k]}</div>`).join('')}</div>${m.position_marque==='fin_document'?zoneMarque:''}<div class="dp-sheet-footer">Pied de page et numéro de page</div></div>`);
  }
  rendre() {
    this.loadSequence=(this.loadSequence||0)+1;
    this.brandInfo=null;this.brandLoading=true;
    this.layouts=typeof this.data.dossier.mises_en_page==='string'?JSON.parse(this.data.dossier.mises_en_page||'{}'):(this.data.dossier.mises_en_page||{});
    const d=this.data.dossier, selected=new Set(d.variantes.map(v=>v.article)),versions=this.documentsActifs(),manuel=this.activeTab==='manuel';
    this.root.html(`<div class="dp-top"><div><a href="/app/documents-produit" class="dp-muted">← Tous les dossiers</a><h2>${dpEsc(d.titre)}</h2><div class="dp-sub"><a href="/app/item/${encodeURIComponent(d.article)}">${dpEsc(d.article)}</a> · ${dpEsc(this.data.contexte.marque_document||this.data.contexte.article.brand)} · français de référence</div></div>
      <button class="btn btn-default" data-generate="les_deux">Créer les deux</button></div>
      <div class="dp-tabs" role="tablist" aria-label="Type de document">${Object.keys(DP_TYPES).map(tab=>`<button class="dp-tab ${tab===this.activeTab?'active':''}" id="dp-tab-${tab}" type="button" role="tab" data-tab="${tab}" aria-selected="${tab===this.activeTab}" aria-controls="dp-type-panel" tabindex="${tab===this.activeTab?'0':'-1'}">${tab==='fiche'?'Fiche technique':'Manuel d’utilisation'} <span class="dp-tab-count">${this.data.documents.filter(v=>v.type_document===DP_TYPES[tab]).length}</span></button>`).join('')}</div>
      <div id="dp-type-panel" role="tabpanel" aria-labelledby="dp-tab-${this.activeTab}">
      <div class="dp-top dp-type-intro"><div><h3>${manuel?'Manuel d’utilisation':'Fiche technique'}</h3><p class="dp-sub">${manuel?'Préparer les instructions d’installation, d’utilisation et d’entretien documentées.':'Présenter le produit, ses caractéristiques et ses applications documentées.'}</p></div><button class="btn btn-primary" data-generate="${this.activeTab}">${manuel?'Créer le manuel':'Créer la fiche technique'}</button></div>
      ${this.usageGuide()}
      <div class="dp-progress"></div>
      <div class="dp-card dp-costs"></div>
      <details class="dp-card dp-layout" open></details>
      <p class="dp-shared-note">La marque, l’en-tête, les sources et les photos ci-dessous sont communs à la fiche technique et au manuel. Vos corrections sont enregistrées lors du changement d’onglet.</p>
      <div class="dp-card dp-brand-card"><h3>Marque du document</h3><div class="dp-actions">
      <select class="form-control dp-brand" aria-label="Marque du document" style="width:320px"><option value="">Marque de l’article${this.data.contexte.article.brand?' : '+dpEsc(this.data.contexte.article.brand):' (non renseignée)'}</option>${(this.data.marques||[]).map(b=>`<option value="${dpEsc(b.name)}" ${b.name===d.marque_document?'selected':''}>${dpEsc(b.name)}</option>`).join('')}${d.marque_document&&!(this.data.marques||[]).some(b=>b.name===d.marque_document)?`<option value="${dpEsc(d.marque_document)}" selected>${dpEsc(d.marque_document)}</option>`:''}</select>
      <button class="btn btn-default btn-sm dp-save-brand">Enregistrer la marque</button>${this.data.peut_creer_marque?'<button class="btn btn-default btn-sm dp-new-brand">Créer une marque</button>':''}<button class="btn btn-default btn-sm dp-refresh-brand">Actualiser le logo</button><button class="btn btn-default btn-sm dp-place-brand">Voir / placer le logo</button></div>
      <div class="dp-brand-preview" style="margin-top:12px"></div><label class="dp-label"><input type="checkbox" class="dp-brand-with-header" ${d.logo_marque_avec_entete?'checked':''}> Afficher aussi le logo de la marque avec un en-tête personnalisé</label>
      <p class="dp-muted" style="margin:8px 0 0">La marque choisie sera utilisée pour les prochaines fiches et les prochains manuels de ce dossier. Les marques des composants restent distinctes. Le logo est partagé par tous les produits de cette marque.</p></div>
      <div class="dp-card dp-letterhead-card"><h3>En-tête des PDF</h3><div class="dp-actions">
      <select class="form-control dp-letterhead" aria-label="En-tête des PDF" style="width:320px"><option value="">Logo de la marque</option>${(this.data.entetes||[]).map(h=>`<option value="${dpEsc(h.name)}" ${h.name===d.entete?'selected':''}>${dpEsc(h.name)}${h.a_completer?' (image à compléter)':''}</option>`).join('')}${d.entete&&!(this.data.entetes||[]).some(h=>h.name===d.entete)?`<option value="${dpEsc(d.entete)}" selected>${dpEsc(d.entete)} (désactivé)</option>`:''}</select>
      ${this.data.peut_creer_entete?'<button class="btn btn-primary btn-sm dp-new-letterhead">Créer un en-tête</button>':''}<button class="btn btn-default btn-sm dp-edit-letterhead" style="display:none">Modifier visuellement</button>
      <button class="btn btn-default btn-sm dp-preview-letterhead">Aperçu</button><button class="btn btn-default btn-sm dp-refresh-letterheads">Actualiser la liste</button>
      <a class="dp-letterhead-link" href="/app/letter-head" target="_blank" rel="noopener">Réglages avancés</a></div>
      <p class="dp-muted" style="margin:10px 0 0">Créez votre en-tête avec l’éditeur visuel : disposition, logo, coordonnées et pied de page, avec aperçu immédiat. Les modèles sont réutilisables ; l’en-tête et le pied de page se répètent sur chaque page. Après un changement, générez le PDF pour appliquer la présentation, sans nouvelle rédaction IA.</p>${this.data.erreur_entete?`<div class="dp-warning" style="margin-top:10px">${dpEsc(this.data.erreur_entete)}</div>`:''}</div>
      <details class="dp-card dp-configuration" ${this.data.documents.length?'':'open'}><summary>Sources, photos et variantes</summary>
      <div class="dp-grid"><div class="dp-full"><label class="dp-label">Consignes de rédaction</label><textarea class="form-control dp-consignes" rows="2" placeholder="Public visé, présentation souhaitée…">${dpEsc(d.consignes)}</textarea></div>
      <div class="dp-full"><div class="dp-actions"><h3 style="margin:0">Variantes couvertes (${d.variantes.length})</h3><button class="btn btn-xs btn-default" data-select-all="1">Toutes</button><button class="btn btn-xs btn-default" data-select-all="0">Aucune</button></div>
      <input class="form-control dp-search" placeholder="Filtrer les variantes…" style="margin-top:10px"><div class="dp-variants">${this.data.variantes.map(v=>`<label class="dp-variant" data-search="${dpEsc((v.name+' '+v.item_name).toLowerCase())}"><input type="checkbox" value="${dpEsc(v.name)}" ${selected.has(v.name)?'checked':''}><span><b>${dpEsc(v.name)}</b><small>${dpEsc(v.item_name)}</small></span></label>`).join('') || '<span class="dp-muted">Cet article n’a pas de variantes actives.</span>'}</div></div>
      <div class="dp-full"><h3>Manuels PDF et photos de pages</h3><div class="dp-actions"><button class="btn btn-default btn-sm dp-upload-source">Ajouter un document</button><button class="btn btn-default btn-sm dp-existing">Documents déjà liés aux articles</button></div>
      <div class="dp-muted" style="margin-top:8px">Sélectionnez les pages utiles (ex. 1-4,7), au maximum 40 pages par PDF. Indiquez la variante si le document lui est spécifique.</div>
      <div class="dp-sources">${d.sources.map((s,i)=>`<div class="dp-sources-row" data-index="${i}"><div>S${i+1} · <a href="${dpUrl(s.fichier)}" target="_blank" rel="noopener">${dpEsc(s.fichier.split('/').pop())}</a>${/\.pdf$/i.test(s.fichier)?` <button class="btn btn-xs btn-default dp-page" data-index="${i}">Illustrer avec une page</button>`:''}</div><input class="form-control input-sm dp-pages" value="${dpEsc(s.pages)}" placeholder="Pages"><select class="form-control input-sm dp-source-scope">${this.scopeOptions(s.article)}</select><button class="btn btn-xs btn-default dp-remove-source" data-index="${i}" title="Retirer">×</button></div>`).join('')}</div></div>
      <div class="dp-full"><h3>Photos du produit et illustrations</h3><button class="btn btn-default btn-sm dp-upload-image">Ajouter une photo</button><div class="dp-images">${d.images.map((im,i)=>`<div class="dp-image" data-index="${i}"><img src="${dpUrl(im.image)}" alt="${dpEsc(im.legende)}"><input class="form-control input-sm dp-caption" value="${dpEsc(im.legende)}" placeholder="Légende"><select class="form-control input-sm dp-image-scope">${this.scopeOptions(im.article)}</select><button class="btn btn-xs btn-default dp-remove-image" data-index="${i}" style="margin-top:6px">Retirer</button></div>`).join('')}</div></div>
      <div class="dp-full"><button class="btn btn-default dp-save-config">Enregistrer les sources et la sélection</button><span class="dp-muted"> Le logo de la marque est repris depuis sa fiche.</span></div></div></details>
      <div class="dp-card"><div class="dp-top"><h3 style="margin:0">${manuel?'Manuels et traductions enregistrés':'Fiches techniques et traductions enregistrées'}</h3><select class="form-control dp-versions" aria-label="Versions ${manuel?'du manuel':'de la fiche technique'}" style="max-width:640px"><option value="">Choisir une version…</option>${versions.map(v=>`<option value="${dpEsc(v.name)}">${dpEsc(v.libelle_langue)} · v${v.numero} · ${dpEsc(v.statut)}${v.a_actualiser?' · À actualiser':''}</option>`).join('')}</select></div><div class="dp-document">${versions.length?'Choisissez une version pour la relire, la traduire ou télécharger son PDF.':manuel?'Aucun manuel enregistré. Cliquez sur Créer le manuel pour préparer la première version.':'Aucune fiche technique enregistrée. Cliquez sur Créer la fiche technique pour préparer la première version.'}</div></div></div>`);
    const helpTab=this.activeTab;
    this.root.find('.dp-help').on('toggle',e=>{this.helpOpen[helpTab]=e.currentTarget.open;});
    this.bindConfig();
    this.renderCosts();
    this.renderStructure();
    this.renderBrand();
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
    z.html(`<div class="dp-cost-summary"><div class="dp-last-cost"><div class="dp-label">Coût estimé de la dernière génération du dossier</div><strong class="dp-cost-value">${latestCost}</strong><div class="dp-sub">${latest?dpEsc(dpAction(latest.action)+' · '+latest.langue):'Le montant apparaîtra automatiquement après votre première génération.'}</div>${latest?.inconnus?'<div class="dp-sub">Montant partiel : consommation manquante pour certains appels.</div>':''}</div><div><b>Modèle ${this.activeTab==='fiche'?'fiche technique':'manuel'} : ${dpEsc(modeleRedaction.modele)}</b><div class="dp-sub">${modeleCommun?'Même modèle pour la lecture des scans et la traduction':modeles.filter(m=>m!==modeleRedaction).map(m=>dpEsc(m.libelle+' : '+m.modele)).join('<br>')}</div><a class="dp-model-settings" href="/app/aquaworld-ia-reglages" target="_blank" rel="noopener">Régler les modèles par outil</a></div><div><b>Total estimé du dossier : ${dpMoney(c.total)}</b>${c.inconnus?'<div class="dp-warning">Total partiel : certains appels n’ont pas communiqué leur consommation.</div>':''}</div></div>
      <details class="dp-model-rates" style="margin-top:12px"><summary>Modèles et tarifs par étape</summary><div class="dp-table-wrap"><table class="dp-table"><thead><tr><th>Étape</th><th>Modèle</th><th>Entrée ($ / million de jetons)</th><th>Sortie ($ / million de jetons)</th></tr></thead><tbody>${modeles.map(m=>`<tr><td>${dpEsc(m.libelle)}</td><td>${dpEsc(m.modele)}</td><td>${dpMoney(m.prix_entree)}</td><td>${dpMoney(m.prix_sortie)}</td></tr>`).join('')}</tbody></table></div></details>
      <p class="dp-muted" style="margin-top:10px">Le coût dépend des modèles, des sources et de la longueur du résultat. PDF et corrections manuelles : aucun coût IA supplémentaire. Estimation selon les tarifs configurés, hors remises de cache et taxes.</p>
      <details ${(c.historique||[]).length?'open':''}><summary>Coût par génération du dossier · 50 dernières générations</summary>
      ${(c.historique||[]).length?`<div class="dp-table-wrap"><table class="dp-table"><thead><tr><th>Date</th><th>Génération</th><th>Langue</th><th>Modèle</th><th>Appels</th><th>Coût estimé</th><th></th></tr></thead><tbody>${c.historique.map(g=>`<tr><td>${dpEsc(frappe.datetime.str_to_user(g.debut))}</td><td>${dpEsc(dpAction(g.action))}${g.erreurs?'<div class="dp-warning">Appel en erreur</div>':''}</td><td>${dpEsc(g.langue)}</td><td>${dpEsc(g.modeles)}</td><td>${Number(g.appels)}</td><td>${g.inconnus?'≥ ':''}${dpMoney(g.cout)}${g.inconnus?'<div class="dp-muted">Consommation partielle</div>':''}</td><td><button class="btn btn-xs btn-default dp-cost-detail" data-generation="${dpEsc(g.generation)}">Détail</button></td></tr>`).join('')}</tbody></table></div>`:'<p class="dp-muted" style="margin-top:10px">Aucun appel IA enregistré pour ce dossier. Le coût apparaîtra après la première génération.</p>'}</details>`);
    z.find('.dp-cost-detail').on('click',async e=>{
      const rows=await dpCall('detail_cout',{name:this.name,generation:$(e.currentTarget).attr('data-generation')});
      frappe.msgprint({title:'Détail du coût de génération',wide:true,message:`<div class="dp-table-wrap" style="overflow-x:auto"><table class="table"><thead><tr><th>Étape</th><th>Modèle</th><th>Jetons entrée</th><th>Jetons sortie</th><th>Coût estimé</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${dpEsc(r.fonctionnalite)}${r.statut==='Erreur'?'<div>Appel en erreur</div>':''}</td><td>${dpEsc(r.modele)}</td><td>${Number(r.jetons_entree)}</td><td>${Number(r.jetons_sortie)}</td><td>${r.usage_inconnu?'Non communiqué':dpMoney(r.cout_estime)}</td></tr>`).join('')}</tbody></table></div><p class="text-muted">Les lectures de scans et les reprises sont incluses. Une génération interrompue peut déjà avoir consommé des jetons.</p>`});
    });
  }
  configValues() {
    const d=this.data.dossier;
    return {mises_en_page:this.layouts||{},marque_document:this.root.find('.dp-brand').val()||'',logo_marque_avec_entete:this.root.find('.dp-brand-with-header').prop('checked')?1:0,entete:this.root.find('.dp-letterhead').val()||'',consignes:this.root.find('.dp-consignes').val()||'',variantes:this.root.find('.dp-variants input:checked').map((_,el)=>({article:el.value})).get(),
      sources:this.root.find('.dp-sources-row').map((_,el)=>{const z=$(el),s=d.sources[+z.attr('data-index')];return {fichier:s.fichier,pages:z.find('.dp-pages').val(),article:z.find('.dp-source-scope').val()};}).get(),
      images:this.root.find('.dp-image').map((_,el)=>{const z=$(el),im=d.images[+z.attr('data-index')];return {image:im.image,legende:z.find('.dp-caption').val(),article:z.find('.dp-image-scope').val()};}).get()};
  }
  async saveConfig(redraw=false) {
    const values=this.configValues();
    if(JSON.stringify(values)===this.lastConfig)return;
    const r=await dpCall('enregistrer',{name:this.name,data:values,modified:this.data.dossier.modified});
    Object.assign(this.data.dossier,values,{modified:r.modified});this.lastConfig=JSON.stringify(values);
    if(redraw){this.data=await dpCall('charger',{name:this.name});this.rendre();frappe.show_alert({message:'Dossier enregistré',indicator:'green'});}
  }
  bindConfig() {
    this.lastConfig=JSON.stringify(this.configValues());
    this.root.find('.dp-brand').on('change',()=>this.renderBrand());
    this.root.find('.dp-brand-with-header').on('change',()=>this.renderLayoutPreview());
    this.root.find('.dp-refresh-brand').on('click',()=>this.renderBrand());
    this.root.find('.dp-place-brand').on('click',()=>{this.root.find('.dp-layout').prop('open',true);this.root.find('.dp-brand-zone-settings')[0].scrollIntoView({behavior:'smooth',block:'center'});this.root.find('.dp-layout-brand-position').trigger('focus');});
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
    this.root.find('.dp-save-config,.dp-save-brand').on('click',async()=>{if(this.dirty)await this.saveDocument();await this.saveConfig(true);});
    this.root.find('.dp-search').on('input',e=>{const q=e.target.value.toLowerCase();this.root.find('.dp-variant').each((_,el)=>$(el).toggle($(el).attr('data-search').includes(q)));});
    this.root.find('[data-select-all]').on('click',e=>this.root.find('.dp-variant:visible input').prop('checked',$(e.currentTarget).attr('data-select-all')==='1'));
    this.root.find('.dp-remove-source,.dp-remove-image').on('click',e=>$(e.currentTarget).closest('.dp-sources-row,.dp-image').remove());
    const ajouter=async(table,row)=>{if(this.dirty)await this.saveDocument();await this.saveConfig();const values=this.configValues();values[table].push(row);await dpCall('enregistrer',{name:this.name,data:values,modified:this.data.dossier.modified});this.data=await dpCall('charger',{name:this.name});this.rendre();};
    this.root.find('.dp-upload-source').on('click',()=>new frappe.ui.FileUploader({doctype:'Dossier Produit',docname:this.name,allow_multiple:true,is_private:1,restrictions:{allowed_file_types:['.pdf','.png','.jpg','.jpeg','.webp']},on_success:f=>{this.uploads=(this.uploads||Promise.resolve()).then(()=>ajouter('sources',{fichier:f.file_url,pages:'',article:''}));}}));
    this.root.find('.dp-upload-image').on('click',()=>new frappe.ui.FileUploader({doctype:'Dossier Produit',docname:this.name,allow_multiple:false,is_private:1,restrictions:{allowed_file_types:['.png','.jpg','.jpeg','.webp','.svg']},on_success:f=>ajouter('images',{image:f.file_url,legende:'',article:''})}));
    this.root.find('.dp-existing').on('click',()=>{
      const choices=this.data.sources_disponibles.filter(s=>!this.configValues().sources.some(x=>x.fichier===s.fichier));
      if(!choices.length)return frappe.msgprint('Aucun autre document joint aux articles ou aux manuels existants.');
      const d=new frappe.ui.Dialog({title:'Documents disponibles',fields:[{fieldtype:'Select',fieldname:'choix',label:'Document',options:choices.map((s,i)=>({label:s.nom,value:String(i)})),reqd:1}],primary_action_label:'Ajouter',primary_action:async v=>{d.hide();const s=choices[+v.choix];await ajouter('sources',{fichier:s.fichier,pages:'',article:s.article});}});d.show();
    });
    this.root.find('.dp-page').on('click',e=>{const i=+$(e.currentTarget).attr('data-index'),fichier=this.data.dossier.sources[i].fichier;frappe.prompt([{fieldtype:'Int',fieldname:'page',label:'Page à utiliser comme illustration',default:1,reqd:1}],async v=>{await this.saveConfig();await dpCall('illustrer_page',{name:this.name,fichier,page:v.page});this.data=await dpCall('charger',{name:this.name});this.rendre();},'Illustration du manuel','Ajouter l’illustration');});
  }
  async renderBrand() {
    const sequence=this.brandSequence=(this.brandSequence||0)+1,name=this.name,z=this.root.find('.dp-brand-preview');
    this.brandInfo=null;this.brandLoading=true;this.renderLayoutPreview();
    z.text('Chargement du logo…');
    try {
      const b=await dpCall('info_marque',{name,marque:this.root.find('.dp-brand').val()||''});
      if(sequence!==this.brandSequence||name!==this.name)return;
      this.brandInfo=b;this.brandLoading=false;this.renderLayoutPreview();
      z.html(`<div class="dp-actions">${dpUrl(b.logo)?`<img class="dp-brand-logo" src="${dpLogoUrl(b)}" alt="Logo ${dpEsc(b.name)}" style="width:110px;height:65px;object-fit:contain">`:'<span class="dp-muted">Aucun logo disponible.</span>'}${b.name?`<span><b>${dpEsc(b.name)}</b></span>${b.peut_modifier&&this.data.peut_ecrire?'<button class="btn btn-default btn-sm dp-upload-brand-logo">Ajouter / remplacer le logo</button>':''}<a href="/app/brand/${encodeURIComponent(b.name)}" target="_blank" rel="noopener">Ouvrir la fiche de marque</a>`:'<span class="dp-muted">Choisissez ou créez une marque.</span>'}</div>`);
      z.find('.dp-upload-brand-logo').on('click',async()=>{
        if(this.dirty)await this.saveDocument();await this.saveConfig();
        new frappe.ui.FileUploader({doctype:'Brand',docname:b.name,is_private:1,allow_multiple:false,restrictions:{allowed_file_types:['.png','.jpg','.jpeg','.webp','.svg']},on_success:async f=>{
          await dpCall('enregistrer_logo_marque',{name:this.name,marque:b.name,fichier:f.file_url});
          this.data=await dpCall('charger',{name:this.name});this.rendre();frappe.show_alert({message:'Logo de la marque enregistré',indicator:'green'});
        }});
      });
      this.showState(this.data.dossier);
    }catch(e){if(sequence===this.brandSequence){this.brandLoading=false;this.renderLayoutPreview();z.text('La marque ou son logo est inaccessible. Choisissez une marque autorisée.');this.root.find('.dp-zone-brand-status').text('La marque ou son logo est inaccessible. Choisissez une marque autorisée.');}}
  }
  async loadDocument(name) {
    const sequence=this.loadSequence=(this.loadSequence||0)+1,dossier=this.name,type=this.typeActif();
    const current=await dpCall('lire_document',{name});
    if(sequence!==this.loadSequence||dossier!==this.name||type!==this.typeActif()||current.doc.type_document!==type)return;
    this.current=current;this.selectedVersions[this.activeTab]=name;this.dirty=false;this.root.find('.dp-versions').val(name);this.renderDocument();this.renderLayoutPreview();
  }
  renderDocument() {
    const {doc,contenu:c,contexte:ctx}=this.current,z=this.root.find('.dp-document');
    const info=this.data.documents.find(v=>v.name===doc.name),scope=(value)=>`<option value="">Toute la gamme</option>${ctx.variantes.map(v=>`<option value="${dpEsc(v.name)}" ${value===v.name?'selected':''}>${dpEsc(v.name)}</option>`).join('')}`;
    z.html(`<div class="dp-actions"><span class="dp-badge">${dpEsc(doc.libelle_langue)} · version ${doc.numero} · ${dpEsc(doc.statut)}</span><button class="btn btn-default btn-sm dp-save-doc">Enregistrer mes corrections</button>${doc.langue==='fr'?'<button class="btn btn-default btn-sm dp-translate">Traduire</button>':''}<button class="btn btn-default btn-sm dp-pdf">Générer le PDF</button><button class="btn btn-primary btn-sm dp-validate">Valider et générer le PDF</button></div>
      ${info?.a_actualiser?'<div class="dp-warning" style="margin:12px 0">À actualiser : la marque, la présentation, les articles, les sources ou la version française ont changé depuis cette version.</div>':''}
      ${doc.source_fr?`<div class="dp-sub">Traduction enregistrée depuis la version française <a href="#" class="dp-source-fr">${dpEsc(doc.source_fr)}</a>.</div>`:''}
      <div class="dp-sub">En-tête enregistré avec cette version : ${dpEsc(ctx.entete?.nom||'Logo de la marque')}.</div>
      <div class="dp-sub">Marque enregistrée avec cette version : ${dpEsc(ctx.marque_document||ctx.article.brand||'Non renseignée')}.</div>
      ${(ctx.marque_document||ctx.article.brand||'')!==(this.data.contexte.marque_document||this.data.contexte.article.brand||'')?'<div class="dp-warning" style="margin-top:10px">Pour utiliser la marque sélectionnée, cliquez sur Créer la fiche technique ou Créer le manuel afin de rédiger une nouvelle version.</div>':''}
      <div class="dp-editor" ${doc.rtl?'dir="rtl"':''}><label class="dp-label">Titre</label><input class="form-control dp-title" value="${dpEsc(c.titre)}"><label class="dp-label">Présentation</label><textarea class="form-control dp-summary">${dpEsc(c.resume)}</textarea>
      <div class="dp-sections">${c.sections.map((s,i)=>`<div class="dp-section" data-index="${i}"><div class="dp-section-title"><input class="form-control dp-section-name" value="${dpEsc(s.titre)}" placeholder="Titre de la rubrique"><button class="btn btn-xs btn-default dp-remove-section">×</button></div><div class="dp-scope"><select class="form-control input-sm dp-section-scope">${scope(s.article)}</select><input class="form-control input-sm dp-section-source" value="${dpEsc(s.source)}" placeholder="Source : S1 p.3, Article…"></div><textarea class="form-control dp-section-text">${dpEsc(s.texte)}</textarea></div>`).join('')}</div>
      <button class="btn btn-default btn-xs dp-add-section" style="margin-top:10px">Ajouter une rubrique</button>
      <label class="dp-label">Caractéristiques techniques</label><div class="dp-table-wrap"><table class="dp-table"><thead><tr><th>Caractéristique</th><th>Valeur</th><th>Unité</th><th>Modèles concernés</th><th>Source</th><th></th></tr></thead><tbody>${c.caracteristiques.map((s,i)=>`<tr data-index="${i}"><td><input class="form-control input-sm" data-key="nom" value="${dpEsc(s.nom)}"></td><td><input class="form-control input-sm" data-key="valeur" value="${dpEsc(s.valeur)}"></td><td><input class="form-control input-sm" data-key="unite" value="${dpEsc(s.unite)}"></td><td><select class="form-control input-sm" data-key="article">${scope(s.article)}</select></td><td><input class="form-control input-sm" data-key="source" value="${dpEsc(s.source)}"></td><td><button class="btn btn-xs btn-default dp-remove-carac">×</button></td></tr>`).join('')}</tbody></table></div><button class="btn btn-default btn-xs dp-add-carac">Ajouter une caractéristique</button>
      <label class="dp-label">Légendes des photos</label>${c.legendes.map((s,i)=>`<input class="form-control dp-doc-caption" data-index="${i}" style="margin-bottom:6px" value="${dpEsc(s)}">`).join('') || '<div class="dp-muted">Aucune illustration sélectionnée.</div>'}
      <label class="dp-label">Points à vérifier avant validation — retirez chaque point une fois résolu</label><textarea class="form-control dp-checks" placeholder="Aucun point en attente">${dpEsc(c.points_a_verifier.join('\n'))}</textarea></div>
      <details style="margin-top:14px"><summary>Variantes et sources de cette version</summary><div class="dp-table-wrap"><table class="dp-table">${c.variantes.map(v=>`<tr><td>${dpEsc(v.article)}</td><td>${dpEsc(v.marque)}</td><td>${v.attributs.map(a=>dpEsc(a.nom+' : '+a.valeur)).join('<br>')}</td></tr>`).join('')}</table></div>${(ctx.preuves||[]).map(p=>`<details><summary>${dpEsc(p.source+' · '+p.fichier)}</summary><div style="white-space:pre-wrap;padding:10px">${dpEsc(p.texte)}</div></details>`).join('')}</details>
      <div class="dp-actions" style="margin-top:16px">${[['pdf','Télécharger le PDF'],['source_latex','Source LaTeX'],['archive_latex','LaTeX et images (ZIP)']].filter(([k])=>doc[k]).map(([k,label])=>`<a class="btn btn-default btn-sm" href="${dpUrl(doc[k])}" target="_blank" rel="noopener">${label}</a>`).join('')}</div>${doc.pdf?`<iframe class="dp-preview" title="Aperçu PDF" src="${dpUrl(doc.pdf)}#toolbar=1"></iframe>`:'<div class="dp-muted" style="margin-top:12px">Le contenu est enregistré en base. Générez son PDF après relecture.</div>'}`);
    z.find('.dp-editor').on('input change',()=>{this.dirty=true;this.renderLayoutPreview();});
    z.find('.dp-remove-section,.dp-remove-carac').on('click',e=>{$(e.currentTarget).closest('.dp-section,tr').remove();this.dirty=true;});
    const add=(key,row)=>{this.current.contenu=this.captureDocument();this.current.contenu[key].push(row);this.renderDocument();this.dirty=true;};
    z.find('.dp-add-section').on('click',()=>add('sections',{titre:'Nouvelle rubrique',texte:'',article:'',source:'Saisie manuelle'}));
    z.find('.dp-add-carac').on('click',()=>add('caracteristiques',{nom:'',valeur:'',unite:'',article:'',source:'Saisie manuelle'}));
    z.find('.dp-save-doc').on('click',()=>this.saveDocument());
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
    this.data.dossier.etat_traitement='En attente';this.showState(this.data.dossier);this.poll();
  }
  showState(s) {
    const busy=['En attente','En cours'].includes(s.etat_traitement),zone=this.root.find('.dp-progress');
    if(s.etat_traitement){zone.show().html(`<div class="${s.etat_traitement==='Échec'?'dp-error':''}">${dpEsc(s.message_traitement||s.etat_traitement)}</div>${busy?`<progress max="100" value="${s.progression||0}"></progress>`:''}`);}else zone.hide();
    this.root.find('button,input,textarea,select').prop('disabled',busy||!!this.switchingTab||!this.data.peut_ecrire);
    this.root.find('.dp-versions,.dp-tab').prop('disabled',busy||!!this.switchingTab);
    this.root.find('.dp-order-row').attr('draggable',!busy&&!this.switchingTab&&!!this.data.peut_ecrire);
    this.root.find('.dp-load-free-background').prop('disabled',busy||!!this.switchingTab||!!this.freePreviewLoading);
    this.root.find('.dp-free-brand').attr({'aria-disabled':String(!this.canMoveLogo()),tabindex:this.canMoveLogo()?0:-1});
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
