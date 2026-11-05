frappe.provide('aquaworld_ia');

aquaworld_ia.EditeurEntete = class {
  constructor(page, modele=null) {
    this.page=page;this.modele=modele;this.name=page.name;this.closed=false;this.serial=0;
    this.esc=v=>frappe.utils.escape_html(String(v??''));
    this.call=async(method,args={})=>(await frappe.call({method:'aquaworld_ia.documents_produit.service.'+method,args:{name:this.name,...args}})).message;
  }
  async ouvrir() {
    this.data=await this.call('charger_editeur_entete',{modele:this.modele,marque:this.page.root.find('.dp-brand').val()||''});
    if(!this.data.compatible){
      frappe.msgprint('Ce modèle a été modifié dans les réglages avancés. Créez un nouvel en-tête visuel pour conserver l’original.');return;
    }
    this.dialog=new frappe.ui.Dialog({title:this.modele?'Modifier l’en-tête et le pied de page':'Créer un en-tête et un pied de page',size:'extra-large',
      fields:[{fieldtype:'HTML',fieldname:'editeur'}],primary_action_label:'Enregistrer et utiliser',primary_action:()=>this.enregistrer(),
      onhide:()=>{this.closed=true;clearTimeout(this.timer);this.serial++;}});
    this.root=this.dialog.fields_dict.editeur.$wrapper;
    this.render();this.dialog.show();this.queuePreview();
  }
  render() {
    const c=this.data.configuration,e=this.esc;
    const input=(key,label,max,placeholder='')=>`<label class="dp-head-field">${label}<input class="form-control" data-head-field="${key}" maxlength="${max}" value="${e(c[key])}" placeholder="${e(placeholder)}"></label>`;
    const area=(key,label,max,placeholder)=>`<label class="dp-head-field">${label}<textarea class="form-control" data-head-field="${key}" rows="3" maxlength="${max}" placeholder="${e(placeholder)}">${e(c[key])}</textarea></label>`;
    this.root.html(`<div class="dp-header-editor"><p class="dp-muted">Composez votre modèle, vérifiez l’aperçu puis enregistrez-le. Il sera sélectionné pour les fiches et les manuels de ce dossier. Aucun appel IA.</p>
      ${this.modele?'<p class="dp-muted">Ce modèle est réutilisable : les changements seront repris lors des prochaines générations PDF des dossiers qui l’utilisent. Les PDF déjà enregistrés restent conservés.</p>':''}
      <div class="dp-head-grid"><div class="dp-head-form">
      <label class="dp-head-field">Nom du modèle<input class="form-control dp-head-name" maxlength="140" value="${e(this.data.titre)}" ${this.modele?'readonly':''} placeholder="Ex. AquaWorld — Commercial et support"></label>
      <h4>1. Choisir la disposition</h4><div class="dp-head-layouts" role="group" aria-label="Disposition de l’en-tête">${[['gauche','Logo à gauche'],['droite','Logo à droite'],['centre','Centré']].map(([key,label])=>`<button type="button" class="dp-head-layout" data-head-layout="${key}" aria-pressed="${c.disposition===key}"><span class="dp-head-layout-icon dp-head-layout-${key}" aria-hidden="true"><span class="dp-head-logo-icon">Logo</span><span>Contacts</span></span>${label}</button>`).join('')}</div>
      <h4>2. Logo et identité</h4><div class="dp-head-logo-row"><div class="dp-head-logo-preview"></div><div><button type="button" class="btn btn-default btn-sm dp-head-upload">Ajouter / remplacer le logo</button><button type="button" class="btn btn-link btn-sm dp-head-remove-logo">Retirer</button><p class="dp-muted">Le logo de la marque est proposé au départ. Vous pouvez choisir un logo de société différent.</p></div></div>
      <label class="dp-head-field">Largeur maximale du logo : <span class="dp-head-width-value">${c.largeur_logo}</span> mm<input type="range" min="12" max="50" step="1" data-head-field="largeur_logo" value="${c.largeur_logo}"></label>
      ${input('nom_societe','Nom de la société ou de la marque',100,'Ex. AquaWorld & Servicing')}${input('sous_titre','Sous-titre (facultatif)',150,'Ex. Traitement de l’eau')}
      <h4>3. Coordonnées</h4><p class="dp-muted">Un bloc sans coordonnées est masqué. Saisissez une ligne par information : e-mail, téléphone, activité…</p>
      <div class="dp-head-contacts">${[1,2].map(n=>`<div>${input('titre_contact_'+n,'Titre du bloc '+n,70,n===1?'Service commercial':'Support technique')}${area('contact_'+n,'Coordonnées du bloc '+n,350,'E-mail\nTéléphone\nInformations utiles')}</div>`).join('')}</div>
      <h4>4. Pied de page et style</h4>${area('pied_page','Texte du pied de page',500,'Adresse complète\nSite web · E-mail')}<p class="dp-muted">Le numéro de page est ajouté automatiquement au PDF.</p>
      <div class="dp-head-style"><label class="dp-head-field">Couleur<input type="color" class="form-control" data-head-field="couleur" value="${e(c.couleur)}"></label><label class="dp-head-field">Taille du texte<select class="form-control" data-head-field="taille_texte">${[7,8,9,10,11,12].map(n=>`<option value="${n}" ${c.taille_texte===n?'selected':''}>${n} pt</option>`).join('')}</select></label></div>
      <label class="dp-head-field"><input type="checkbox" data-head-field="trait" ${c.trait?'checked':''}> Afficher les traits de séparation</label>
      </div><div class="dp-head-preview"><h4>Aperçu sur une page A4</h4><p class="dp-muted">L’en-tête et le pied de page se répètent sur chaque page.</p><div class="dp-head-paper"><div class="dp-head-preview-top"></div><div class="dp-head-preview-body"><b>${this.page.activeTab==='manuel'?'Manuel d’utilisation':'Fiche technique'}</b><p>Le contenu de votre document apparaîtra ici.</p><div></div><div></div><div></div></div><div class="dp-head-preview-bottom"></div><span class="dp-head-page-number">1</span></div><p class="dp-head-preview-status dp-muted" role="status" aria-live="polite"></p><p class="dp-head-error" role="alert" hidden></p></div></div></div>`);
    this.config={...c};
    this.root.find('[data-head-layout]').on('click',ev=>{this.config.disposition=ev.currentTarget.dataset.headLayout;this.root.find('[data-head-layout]').attr('aria-pressed','false');$(ev.currentTarget).attr('aria-pressed','true');this.queuePreview();});
    this.root.find('[data-head-field]').on('input change',()=>{this.root.find('.dp-head-width-value').text(this.root.find('[data-head-field="largeur_logo"]').val());this.queuePreview();});
    this.root.find('.dp-head-upload').on('click',()=>new frappe.ui.FileUploader({doctype:'Dossier Produit',docname:this.name,is_private:1,allow_multiple:false,
      restrictions:{allowed_file_types:['.png','.jpg','.jpeg','.webp','.svg']},on_success:f=>{if(this.closed)return;this.config.logo=f.file_url;this.renderLogo();this.queuePreview();}}));
    this.root.find('.dp-head-remove-logo').on('click',()=>{this.config.logo='';this.renderLogo();this.queuePreview();});
    this.renderLogo();
    if(this.modele&&this.data.peut_creer){this.dialog.set_secondary_action_label('Enregistrer une copie');this.dialog.set_secondary_action(()=>frappe.prompt([{fieldname:'titre',fieldtype:'Data',label:'Nom du nouveau modèle',reqd:1,default:this.data.titre+' — copie'}],v=>this.enregistrer(v.titre),'Créer une copie','Enregistrer et utiliser'));}
    if(this.modele&&!this.data.peut_modifier){this.root.find('input,textarea,select,button').prop('disabled',true);this.root.find('.dp-head-preview-status').text('Ce modèle est en lecture seule. Vous pouvez en enregistrer une copie si vous disposez des droits de création.');}
  }
  renderLogo() {
    const url=this.config.logo||'';
    this.root.find('.dp-head-logo-preview').html(/^\/(private\/)?files\//.test(url)?`<img src="${this.esc(url)}" alt="Logo de l’en-tête">`:'<span>Sans logo</span>');
    this.root.find('.dp-head-remove-logo').toggle(!!url);
  }
  values() {
    const c={...this.config};
    this.root.find('[data-head-field]').each((_,el)=>{c[el.dataset.headField]=el.type==='checkbox'?(el.checked?1:0):['largeur_logo','taille_texte'].includes(el.dataset.headField)?Number(el.value):el.value;});return c;
  }
  buttons() {
    const allowed=this.modele?this.data.peut_modifier:this.data.peut_creer;
    this.dialog.get_primary_btn().prop('disabled',this.saving||!this.ready||!allowed);
    this.dialog.get_secondary_btn().prop('disabled',this.saving||!this.ready);
    this.root.find('input,textarea,select,button').prop('disabled',!!this.saving||!allowed);
  }
  queuePreview() {
    clearTimeout(this.timer);const serial=++this.serial;this.ready=false;this.buttons();
    this.root.find('.dp-head-error').prop('hidden',true);
    this.root.find('.dp-head-preview-status').text('Actualisation de l’aperçu…');
    this.root.find('.dp-head-paper').addClass('dp-head-pending');
    this.timer=setTimeout(()=>this.preview(serial),400);
  }
  async preview(serial) {
    try{
      const r=await this.call('apercu_editeur_entete',{configuration:this.values()});
      if(this.closed||serial!==this.serial)return;
      if(r.erreur){this.error(r.erreur);this.root.find('.dp-head-preview-status').text('Corrigez les champs pour actualiser l’aperçu.');return;}
      for(const [key,selector] of [['haut','.dp-head-preview-top'],['bas','.dp-head-preview-bottom']]){
        const part=r[key];this.root.find(selector).html(part?.image?.startsWith('data:image/png;base64,')?`<img src="${part.image}" alt="${key==='haut'?'En-tête':'Pied de page'}">`:'');
      }
      this.ready=true;this.root.find('.dp-head-paper').removeClass('dp-head-pending');
      this.root.find('.dp-head-preview-status').text('Aperçu à jour. Enregistrez pour utiliser ce modèle dans le dossier.');
    }catch{if(!this.closed&&serial===this.serial){this.error('L’aperçu n’a pas pu être préparé. Vérifiez le logo et réessayez en modifiant un champ.');this.root.find('.dp-head-preview-status').text('Aperçu indisponible.');}}
    finally{if(!this.closed&&serial===this.serial)this.buttons();}
  }
  error(message) {this.root.find('.dp-head-error').text(message).prop('hidden',false);}
  async enregistrer(copie=null) {
    if(this.saving||!this.ready)return;
    const titre=copie||this.root.find('.dp-head-name').val().trim();if(!titre){this.error('Donnez un nom au modèle.');this.root.find('.dp-head-name').trigger('focus');return;}
    this.saving=true;this.buttons();this.root.find('.dp-head-error').prop('hidden',true);
    try{
      if(this.page.name!==this.name)throw new Error('Le dossier a changé. Fermez l’éditeur et rouvrez-le.');
      if(this.page.dirty)await this.page.saveDocument();await this.page.saveConfig();
      const r=await this.call('enregistrer_editeur_entete',{titre,configuration:this.values(),modele:copie?null:this.modele,modified:copie?null:this.data.modified,dossier_modified:this.page.data.dossier.modified});
      this.page.data.dossier.entete=r.name;this.page.data.dossier.modified=r.dossier_modified;this.page.data.entetes=r.entetes;this.page.data.erreur_entete=null;
      this.page.rendre();this.dialog.hide();
      frappe.show_alert({message:'En-tête enregistré et sélectionné. Générez le PDF pour l’appliquer.',indicator:'green'});
    }catch(e){this.error(e?.message||'L’enregistrement a échoué. Vérifiez les informations affichées et réessayez.');}
    finally{this.saving=false;if(!this.closed)this.buttons();}
  }
};
