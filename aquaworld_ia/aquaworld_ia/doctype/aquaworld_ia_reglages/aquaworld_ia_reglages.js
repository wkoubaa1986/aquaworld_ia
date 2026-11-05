frappe.ui.form.on('Aquaworld IA Reglages', {
  onload(frm) {
    // Le catalogue suggère les identifiants courants ; une version datée ou un
    // autre identifiant accessible au compte peut aussi être saisi librement.
    for (const field of Object.values(frm.fields_dict)) {
      if (field.df.fieldtype === 'Autocomplete' && field.df.fieldname.startsWith('modele_')) {
        field.df.ignore_validation = true;
      }
    }
  }
});
