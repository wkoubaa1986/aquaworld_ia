# Aquaworld IA

App Frappe/ERPNext v15 : deux fonctions IA (OpenAI) rattachées à l'Article.

## 1. Manuels d'utilisation multilingues (`Manuel Article`)

À partir du PDF **texte** anglais du fabricant, produit pour chaque langue de la liste prédéfinie
(`Aquaworld IA Langue` : fr, ar, de, es, it, pt, nl — activables) un PDF traduit **qui garde la
mise en page** : images, schémas et tableaux intacts, texte remplacé bloc par bloc (PyMuPDF
`insert_htmlbox`, police réduite si nécessaire, arabe façonné de droite à gauche avec Noto Naskh
Arabic embarquée).

Les lots de traduction partent 4 à la fois (`traduction.PARALLELE`, threads ; `chat_json_differe` sans Frappe,
journal écrit ensuite par le thread principal) : une langue de 12 pages en ~30 s au lieu de ~100 s.

Flux : fiche → PDF source → « Ajouter les langues actives » → « Traduire » → PDF téléchargeables
dans la grille, statistiques par langue (blocs réduits / non placés), journal.

Outil de diagnostic (sans fiche) :

```
bench --site <site> execute aquaworld_ia.manuels.spike.executer \
  --kwargs "{'chemin_pdf': '/chemin/manuel.pdf', 'langue': 'ar', 'pages': '1-5'}"
```

**Studio manuel** (`/app/studio-manuel/<MAN>`, bouton « Ouvrir le studio » de la fiche ; « Nouveau manuel » dans le
studio = article + PDF téléversé + langues, `studio.nouveau`) : la traduction
page par page, sur l'image du manuel d'origine. Gauche : les pages ; centre : la page telle qu'elle
sortira dans le PDF de la langue, avec un rectangle par bloc (bleu traduit, vert corrigé, gris à
traduire, rouge effacé, orange illustration) ; droite : le bloc cliqué — texte anglais, traduction à
corriger, taille maximale, traitement (traduire / laisser en anglais / effacer), « Retraduire » (IA, ce
bloc seul), « Rétablir la version IA ». Un bloc se glisse et s'agrandit par son coin ; « ＋ Case de
texte » pose un texte libre (fond blanc au choix, utile sur une page scannée) ; « ＋ Zone d'illustration »
ou une illustration détectée se redessine par IA avec ses mots traduits (une image facturée, à relire) ;
« Traduire la page » (IA, blocs manquants), « Traduire tout » (le job de la fiche), « Générer le PDF » (sans
IA), « PDF toutes langues » (`studio.combiner` : le PDF source puis chaque langue terminée, à la suite, un
signet par langue, attaché en `pdf_combine` ; aussi sur la fiche). Tout est dans `edition` de la ligne de langue (`manuels/edition.py`) ; les traductions IA restent à
part (`traductions`) et une correction prime toujours. Rendu : `rendu.plan_page` (pur) puis
`executer_plan` ; un titre d'une ligne s'élargit vers la droite, les entrées de liste qui se suivent
partagent une boîte (une ligne chacune). L'analyse du PDF est mise en cache sur la fiche (`analyse`,
`VERSION_ANALYSE`) et ses traductions reportées par texte quand elle est refaite.

**OCR** : une page sans couche texte (PDF CorelDRAW/Illustrator aux lettres en contours, scan) est lue par
Tesseract via PyMuPDF (`extraction.lignes_ocr`, 250 dpi, ~2,5 s/page) ; ses paragraphes sont rebâtis colonne
par colonne (`paragraphes_depuis_lignes`, puces rattachées, déchets des points de conduite nettoyés) et marqués
`ocr` : au rendu, les tracés de la boîte sont retirés et la boîte blanchie (`apply_redactions(graphics=1)`).
Le studio signale 🔍 OCR (texte à relire). Il faut `tesseract-ocr` + `tesseract-ocr-eng` dans l'image
(ajoutés aux Containerfiles custom et layered) ; sans eux, la page reste « image ».

**Mode « Reconstruit »** (studio, sélecteur En place / Reconstruit ; `manuels/reconstruit.py`) : pour les PDF où
le remplacement en place rend mal (lettres en contours, scans, mise en page dense). L'IA vision lit chaque page
(`chat_json_image`, image ≤ 1600 px + transcription OCR en indice, « Manuel lecture » au journal, ≈ 6 s et
2-4 ¢ par page) et rend un contenu structuré : titres (niveaux 1-3), paragraphes, listes, étapes, tableaux, notes,
figures (boîte en % de la page, découpée ensuite dans l'original) ; le sommaire d'origine est ignoré. Les cadres de
figures de l'IA sont RECALÉS sur les objets réels de la page (`extraction.detecter_figures` : images et groupes de
dessins hors texte, dans `analyse.figures` ; `reconstruit.ajuster_figure` : union des objets recouverts à ≥ 30 %),
et ces régions lui sont données en indice — sans cela les cadres étaient larges ou décalés (25/09/2026). Dans le studio,
« ✎ Cadrer / effacer » sur une figure : le cadre se déplace/redimensionne sur l'original, des zones rouges (`masques`,
en % de la page) sont blanchies dans la figure (`appliquer_masques`) ; bloc « Image ajoutée » (`type: image`, fichier
du site, largeur % du texte, alignement, légende) pour un logo, une certification, une photo — placé dans l'ordre des
blocs par le gabarit comme par la mise en page IA (« ajoutee » dans le prompt). Sur chaque bloc traduit : « 🤖 Traduire /
Retraduire » (`traduire_bloc`, ce seul bloc, tout de suite) ; sur une figure : « 🎨 Traduire les mots de l'image »
(`traduire_figure` = atelier de `studio.traduire_illustration`, résultat gardé PAR LANGUE sous la clé `figure:<id>`
de `traductions_structure`, utilisé par le gabarit et la mise en page IA ; « Retirer » revient à la découpe).
Structure dans `Manuel Article.structure` (identifiant = empreinte du contenu) ; on la corrige bloc par bloc dans
le studio (source anglaise ou traduction). « Traduire le contenu » traduit les textes manquants par clé
(type + empreinte : stable à la relecture, partagée entre pages) dans `traductions_structure`. « Générer le
manuel » compose un PDF neuf avec PyMuPDF Story : couverture (titre, article, langue, logo), sommaire avec pages,
corps fluide, pied de page « éditeur · n / N » ; gabarit dans les Réglages (logo, couleur, A4/A5, éditeur).
« PDF toutes langues » prend le manuel reconstruit d'une langue quand il existe.
**Mise en page par IA, page par page** (« 🎨 Mettre en page (IA) » / « Toutes les pages ») : l'IA vision écrit le HTML
d'UNE page imprimée (colonnes, figures, titres comme l'original) à partir des blocs traduits ; rendu par
wkhtmltopdf (QtWebKit patché : pas de flexbox/grid, tables/floats/absolu ; polices en data: URI, figures en JPEG),
stocké par langue dans `mises_en_page` ; l'aperçu de gauche montre la version IA (chip, « Retirer ») ; « Générer le
manuel » propose alors le mode IA (une page imprimée par page d'origine, le gabarit comble les pages sans mise en
page IA) ou le gabarit fluide. « Manuel mise en page » au journal. Plusieurs langues à la fois : « ＋ langue » ajoute toutes les langues cochées
(`studio.ajouter_langues`) ; « Traduire le contenu », « Mettre en page (IA) » (cette page / toutes), « Générer le manuel »
proposent les langues à cocher (une tâche de fond par langue, en parallèle ; génération langue après langue puis
« PDF toutes langues » en option). Onglet « Toutes » (`structure_page_multi`) : chaque bloc de la page avec l'anglais
puis une case par langue, 🤖 par langue ou « Toutes les langues » là où il manque, figures avec leurs mots traduits
par langue ; l'aperçu, la mise en page IA et la génération restent sur l'onglet d'une langue.

Limites : sans Tesseract, le texte en contours n'est pas traduit ; les tailles et le gras d'un texte OCR sont
estimés ; les points de conduite d'un sommaire restent des tracés (bloc à « effacer » à la main) ; les blocs trop serrés sont réduits puis signalés « non placés » (le studio
les montre, à agrandir) ; le texte vertical reste en anglais ; les polices d'origine sont remplacées par
Noto. Relecture humaine recommandée pour les avertissements de sécurité et les illustrations IA.

## 2. Design d'emballage (`Design Emballage`)

Pour un Article, avec les dimensions de la boîte (largeur de face avant, hauteur, profondeur),
le logo de marque et la photo produit :

1. **Préparer textes et styles** — l'IA reformule les caractéristiques saisies (sans en inventer),
   les traduit dans les langues demandées et propose N directions graphiques. Les textes se
   relisent et se corrigent avant toute image.
2. **Générer les variantes** — une image gpt-image-1 par style (face avant uniquement), photo
   produit et logo en référence. Galerie, choix, régénération.
3. **Composer le plan à plat** — PDF imprimeur à l'échelle (mm), page 1 artwork (visuel de la
   variante sur l'avant, aplat + bandeau sur les autres faces, logo vectoriel, textes par langue,
   EAN-13 / QR vectoriels, pictogrammes, calque « Découpe et plis »), page 2 fiche technique.
   Options : faces secondaires par IA (5 images), aperçu 3D (1 image, illustration).

**Mise en forme des caractéristiques** (studio, étape 2) : un éditeur ligne par ligne — gras, italique,
puce, taille en points et police par ligne, plus une police et une taille pour tout le bloc. Chaque
ligne garde sa mise en forme dans le texte même, sous forme d'un préfixe lisible
(`{14pt, gras, italique, sans puce, police: Montserrat} Débit 500 L/h`, voir `emballage/mise_en_forme.py`).
L'IA reçoit les lignes sans préfixe et doit en rendre autant, dans le même ordre ; la mise en forme est
reposée rang pour rang sur chaque langue (l'arabe garde sa police). Les tailles sont des maximums : un
bloc qui ne tient pas dans sa zone est réduit en entier, et le studio le signale après la composition.
Polices : 9 familles livrées (OFL, `public/fonts/POLICES.txt`), ou les vôtres (`Police Emballage` :
un fichier TTF/OTF par style, car le moteur PDF ne fabrique ni le gras ni l'italique).

**Dupliquer** (`studio.dupliquer`) : bouton ⧉ de la fiche et du studio, ou menu Actions de la liste
(une ou plusieurs lignes cochées). La copie reprend tout ce qui a été saisi, dessiné et généré (variantes
IA comprises, rien n'est refacturé) ; ses fichiers lui sont rattachés, supprimer l'original ne la casse
pas. Le plan à plat et les aperçus sont à recomposer. Une seule ligne cochée : on peut changer d'article.

Formes : « Étui à rabats », « Caisse américaine », « Sac à soufflets latéraux », « Sachet doypack »,
« Étiquette enveloppante », et « Sac à gueule ouverte agrafé » (plat ou à soufflets : L, H, R = repli
supérieur compris dans H, S = soufflet ; la bande du repli est hachurée dans l'aperçu et sur le calque du
PDF, aucun texte ni logo n'y est posé). Le plan de découpe est générique : à valider par le cartonnier. PDF **RVB** : conversion CMJN par l'imprimeur.
gpt-image-1 plafonne à 1536 px (≈ 300 dpi jusqu'à 13 cm) ; textes, logo, codes et pictos sont
vectoriels et restent nets. Les pictogrammes livrés dans `public/pictos/` sont des dessins
génériques **à faire valider** avant impression.

## Réglages et coûts

- Clé OpenAI : `AI Settings.openai_api_key` (Single livré par woocommerce_fusion) ou
  `site_config.json` (`openai_api_key`). Modèles dans `Aquaworld IA Reglages`.
- Chaque appel est journalisé (`Journal IA` : jetons, images, coût estimé). Plafond mensuel et
  seuil d'alerte e-mail dans les réglages ; grille de tarifs éditable (les prix OpenAI changent).

## Développement

```
bench --site <site> install-app aquaworld_ia
bench --site <site> run-tests --app aquaworld_ia      # fonctions pures, sans appel IA
```

Aucun DocType en fixtures : langues et pictogrammes sont semés (idempotents) par
`aquaworld_ia.install.after_migrate`.
