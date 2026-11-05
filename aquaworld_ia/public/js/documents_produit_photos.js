frappe.provide('aquaworld_ia');

aquaworld_ia.PhotosProduit = class {
  constructor(page) {this.page=page;this.name=page.name;this.tab=page.activeTab;this.esc=v=>frappe.utils.escape_html(String(v??''));}
  async ouvrir() {
    const values=this.page.configValues();
    this.existing=values.images;this.selected=new Set();
    this.photos=(await frappe.call({method:'aquaworld_ia.documents_produit.service.photos_disponibles',args:{name:this.name,variantes:values.variantes.map(v=>v.article)}})).message;
    if(this.name!==this.page.name)return;
    this.dialog=new frappe.ui.Dialog({title:'Choisir les photos du produit et des variantes',size:'extra-large',fields:[{fieldtype:'HTML',fieldname:'galerie'}],primary_action_label:'Ajouter les photos',primary_action:()=>this.ajouter()});
    this.root=this.dialog.fields_dict.galerie.$wrapper;this.render();this.dialog.show();
  }
  key(im) {return JSON.stringify([im.image,im.article||'']);}
  render() {
    const e=this.esc,existing=new Set(this.existing.map(im=>this.key(im))),groupes=new Map(),vues=new Set();
    this.photos.forEach((im,i)=>{const cle=im.article||'';if(!groupes.has(cle))groupes.set(cle,[]);groupes.get(cle).push([im,i]);});
    this.root.html(`<div class="dp-photo-picker"><p>Les photos sont classées selon l’article auquel elles sont jointes. Vous pouvez choisir plusieurs vues par variante, puis ajuster leurs légendes et associations dans le dossier.</p>
      <div class="dp-actions"><button type="button" class="btn btn-default btn-sm dp-photo-suggest">Suggérer les photos principales</button><button type="button" class="btn btn-link btn-sm dp-photo-clear">Effacer mon choix</button></div>
      <p class="text-muted small">La suggestion choisit des photos principales distinctes, en évitant les images déjà présentes. Elle utilise les associations des articles et ne consomme aucun crédit IA.</p>
      <label>Rechercher une photo ou une variante<input class="form-control dp-photo-filter" placeholder="Référence, nom du fichier…"></label>
      <label><input type="checkbox" class="dp-photo-show-duplicates"> Afficher aussi les photos identiques liées à d’autres variantes</label>
      <p class="dp-photo-status" role="status" aria-live="polite"></p>
      <div class="dp-photo-groups">${Array.from(groupes).map(([article,items])=>`<section class="dp-photo-library-group"><h4>${e(article||'Produit / toute la gamme')}${article?' · '+e(this.page.data.variantes.find(v=>v.name===article)?.item_name||''):''}</h4><div class="dp-photo-library-grid">${items.map(([im,i])=>{const added=existing.has(this.key(im)),duplicate=vues.has(im.image);vues.add(im.image);return `<div class="dp-photo-choice ${added?'dp-photo-added':''}" data-photo-index="${i}" data-duplicate="${duplicate?'1':'0'}" data-search="${e((im.article+' '+im.nom+' '+im.origine).toLowerCase())}"><label><input type="checkbox" value="${i}" ${added?'checked disabled':''}><span>${added?'Déjà sélectionnée':im.principale_article?'Photo principale de l’article':'Pièce jointe'}</span><img src="${/^\/(private\/)?files\//.test(im.image)?e(im.image):''}" loading="lazy" alt="${e(im.nom)}"><b>${e(im.nom)}</b></label><small>Origine : ${e(im.origine)}${duplicate?' · image partagée':''}</small></div>`;}).join('')}</div></section>`).join('')||'<p class="text-muted">Aucune photo accessible jointe aux articles sélectionnés. Utilisez « Importer des photos » dans le dossier pour en ajouter.</p>'}</div>
      <div class="dp-photo-options"><label><input type="checkbox" class="dp-photo-library-grouping" checked> Regrouper les vues avec leur variante dans ${this.tab==='manuel'?'le manuel':'la fiche technique'}</label><label>Photos par ligne<select class="form-control dp-photo-library-columns"><option value="1">Une</option><option value="2" selected>Deux</option><option value="3">Trois</option></select></label><p class="text-muted small">La photo principale reste dans la présentation du produit. Les autres vues sont regroupées par variante ; les vues communes restent dans les illustrations. Les variantes sans autre photo restent dans un tableau compact. Vous pouvez changer cette disposition ensuite.</p></div>
      <p class="dp-photo-library-error text-danger" role="alert" hidden></p></div>`);
    this.root.find('.dp-photo-choice input:not(:disabled)').on('change',ev=>{const i=Number(ev.target.value);if(ev.target.checked)this.selected.add(i);else this.selected.delete(i);this.update();});
    this.root.find('.dp-photo-suggest').on('click',()=>{
      const scopes=new Set([...this.existing,...Array.from(this.selected,i=>this.photos[i])].map(im=>im.article||''));
      const images=new Set([...this.existing,...Array.from(this.selected,i=>this.photos[i])].map(im=>im.image));
      const avant=this.selected.size;
      this.photos.forEach((im,i)=>{if(im.principale_article&&!images.has(im.image)&&!existing.has(this.key(im))&&!scopes.has(im.article||'')&&this.existing.length+this.selected.size<20){this.selected.add(i);scopes.add(im.article||'');images.add(im.image);}});this.update();
      if(this.selected.size===avant)this.root.find('.dp-photo-status').append(' Aucune autre photo principale distincte à proposer ; choisissez les vues utiles dans la galerie.');
    });
    this.root.find('.dp-photo-clear').on('click',()=>{this.selected.clear();this.update();});
    this.root.find('.dp-photo-filter,.dp-photo-show-duplicates').on('input change',()=>this.filter());
    this.update();this.filter();
  }
  filter() {
    const q=this.root.find('.dp-photo-filter').val().toLowerCase().trim(),doublons=this.root.find('.dp-photo-show-duplicates').prop('checked');
    this.root.find('.dp-photo-choice').each((_,el)=>$(el).toggle(el.dataset.search.includes(q)&&(q||doublons||el.dataset.duplicate==='0'||this.selected.has(Number(el.dataset.photoIndex)))));
    this.root.find('.dp-photo-library-group').each((_,el)=>$(el).toggle($(el).find('.dp-photo-choice').toArray().some(c=>c.style.display!=='none')));
  }
  update() {
    const n=this.selected.size,total=this.existing.length+n;
    this.root.find('.dp-photo-choice input:not(:disabled)').each((_,el)=>{el.checked=this.selected.has(Number(el.value));});
    this.root.find('.dp-photo-choice').each((_,el)=>$(el).toggleClass('dp-photo-chosen',$(el).find('input').prop('checked')));
    this.root.find('.dp-photo-status').text(`${n} nouvelle(s) photo(s) choisie(s) · ${total} / 20 au total · ${new Set(this.photos.map(im=>im.image)).size} fichier(s) distinct(s) disponible(s)${total>20?' — retirez des photos pour continuer':''}`);
    this.dialog.get_primary_btn().text(`Ajouter ${n} photo${n>1?'s':''}`);
    this.dialog.get_primary_btn().prop('disabled',this.saving||!n||total>20);
  }
  async ajouter() {
    if(this.saving||!this.selected.size||this.existing.length+this.selected.size>20)return;
    const images=Array.from(this.selected).sort((a,b)=>a-b).map(i=>{const im=this.photos[i];return {image:im.image,article:im.article,legende:im.legende};});
    const presentation={photos_variantes:this.root.find('.dp-photo-library-grouping').prop('checked')?1:0,colonnes_photos:Number(this.root.find('.dp-photo-library-columns').val())};
    this.saving=true;this.update();this.root.find('input,button,select').prop('disabled',true);
    try{
      if(this.name!==this.page.name||this.tab!==this.page.activeTab)throw new Error('Le dossier ou l’onglet a changé. Rouvrez la sélection.');
      await this.page.ajouterPhotos(images,presentation);this.dialog.hide();
    }catch(err){this.saving=false;this.render();this.root.find('.dp-photo-library-grouping').prop('checked',!!presentation.photos_variantes);this.root.find('.dp-photo-library-columns').val(String(presentation.colonnes_photos));this.root.find('.dp-photo-library-error').text(err?.message||'L’enregistrement a échoué. Vérifiez la sélection et réessayez.').prop('hidden',false);}
  }
};
