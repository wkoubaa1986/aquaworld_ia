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

1. **Produit et format** — article, forme et dimensions.
2. **Contenus** — logo, photo, textes imprimés, langues et pictogrammes. L’IA peut proposer
   des textes ; ils ne remplacent les textes imprimés qu’après « Appliquer à l’impression ».
3. **Mise en page** — placement sur le plan, couleur et image de fond. La création de variantes
   et de faces par IA reste disponible dans une section facultative.
4. **Vérifier et exporter** — PDF imprimeur à l’échelle (mm), avec artwork, calque de découpe
   et fiche technique. Aucun texte IA, variante ni fond personnalisé n’est nécessaire.
   La simulation IA se lance seulement à partir d’un PDF à jour.

Le centre propose **Édition**, **Aperçu imprimé** et **3D**. La **Médiathèque** réunit les fichiers du
design, les ressources partagées et les propositions IA. Sous chaque image, **Modifier** donne
accès à la retouche, à la vectorisation couleur, à la mosaïque et à la bibliothèque selon l’usage.

**Logos différents par face ou par zone** : dans Édition, épingler une face, sélectionner sa
zone Logo (ou Ajouter → Logo), puis **Choisir un autre logo** dans les propriétés. Le sélecteur
propose les images du design, la bibliothèque et l’import PNG/JPEG/SVG. Le choix s’applique à
cette zone ; le logo commun du design reste inchangé. Plusieurs zones Logo peuvent coexister
sur une face. Une face personnalisée conserve ses propres éléments même si elle copiait l’avant.

**Retoucher le logo d’une zone par IA** : sélectionner le logo puis **Retoucher ce logo par IA**
au-dessus du plan, ou **Retoucher par IA** dans ses propriétés. L’atelier montre le logo réellement
utilisé par cette zone, la face ciblée et le coût estimé ; une proposition est demandée par défaut.
Comparer puis **Utiliser pour ce logo**, ou vectoriser la proposition en SVG couleur avant de
l’adopter. La cible reste la même pendant les essais et la vectorisation. Le logo commun, les
autres zones et les faces miroir gardent leur ancien visuel ; position, dimensions, rotation et
zoom sont conservés. Le centrage mesuré sur l’ancien fichier est retiré. Si le design a changé
entre-temps, l’adoption est refusée : les propositions restent disponibles dans la médiathèque.
Les tests simulent la réponse IA ; ils n’effectuent aucune génération payante.

**Couleurs et pipette** : dans Mise en page → Palette, **＋ Couleur / pipette** permet de
prélever une couleur sur le logo, la photo, le fond ou une image de la médiathèque. Le sélecteur
propose aussi une saisie HEX, un choix de couleur libre et la pipette écran si le navigateur la
prend en charge. Les ajouts conservent les couleurs déjà saisies et évitent les doublons.
Dans la retouche IA d’un logo (y compris par zone) ou d’une photo, **Pipette / image** remplit
la **Couleur demandée à l’IA** ; les pastilles reprennent la palette du design. On peut préciser
l’élément à recolorer et demander d’utiliser aussi la palette pour les autres couleurs modifiées.
Ces choix sont transmis au prompt et conservés lors d’un nouvel essai. Une sélection pour l’IA
ne modifie ni la palette ni le logo avant adoption. L’IA peut varier légèrement la teinte :
la recoloration uniforme sans IA reste le moyen d’obtenir un code couleur exact.

**Position et rotation** : sélectionner une zone Logo ou Photo, puis utiliser les champs X/Y,
largeur/hauteur et **Rotation (°)** dans le panneau de propriétés. **↶ 90° / ↷ 90°** échangent le
cadre de largeur et hauteur, l’ajustent à la face et conservent son centre autant que possible.
Un angle libre tourne le visuel à l’intérieur du cadre choisi, sans déborder. L’aperçu montre
l’image tournée ; le PDF applique le même angle horaire et conserve les logos SVG vectoriels.
Les contrôles de position sont disposés sur deux colonnes, y compris sur un panneau étroit.

**Zoom dans le cadre** : cliquer une zone Logo ou Photo puis déplacer **Zoom du visuel**
(25–400 %). L’image change de taille immédiatement, le cadre garde sa position et ses dimensions.
Le débordement est coupé aux bords, y compris après rotation. Relâcher le curseur enregistre le
réglage ; **Ajuster (100 %)** retrouve l’image entière. Le PDF et ses textures 3D reprennent ce
cadrage, en conservant les tracés des logos SVG. Les images héritées de l’article ou de la marque
sont également visibles dans l’éditeur.

**Déplacer le contenu dans son cadre** : sélectionner une zone puis utiliser **Contenu dans
le cadre** : flèches par pas de 1 mm, décalages horizontal et vertical puis **Appliquer**, ou
cocher **Glisser le contenu à la souris** et glisser sur la zone. **Alt + glisser** permet aussi
ce déplacement sans activer le mode. Le cadre garde sa position et sa taille ; les valeurs
positives vont à droite et en bas, même après rotation. **Réinitialiser** remet les deux décalages
à zéro sans changer le zoom. Logos, photos, textes, pictogrammes, tampons et codes suivent ce
réglage dans le plan, le PDF et les textures 3D ; les débordements sont coupés au cadre.

**Glissement et sauvegardes** : la barre au-dessus du plan indique **Déplacer : Le cadre / Le
contenu** et partage ce choix avec la case du panneau de droite. La zone saisie devient la
sélection active et passe devant les zones superposées. Un petit mouvement involontaire reste
un clic ; **Échap** ou une perte de focus annule le glissement. Le pointeur est capturé jusqu’au
relâchement, y compris sur écran tactile. Les sauvegardes prennent un instantané des réglages ;
les réponses intermédiaires ne redessinent plus le plan, et la dernière attend la fin d’un geste.
Les saisies de position non encore appliquées sont conservées pendant ce rafraîchissement.

**Centrage du logo visible** : dans les réglages d’une zone Logo, **Centrer le logo visible**
mesure localement les contours de l’écriture et du symbole, en ignorant les marges transparentes
ou le fond blanc. Le centre de ces contours est placé au milieu de la facette ; dimensions,
rotation et zoom sont conservés, et le décalage manuel est remis à zéro. **Centrage du fichier entier** désactive la correction. Le
réglage suit la zone dans le PDF et la 3D, sans modifier le fichier ni facturer d’IA. Un fond
opaque coloré fait partie du logo visible ; il n’est pas retiré par cette détection. La correction
ne s’applique qu’au fichier mesuré, et est retirée lorsqu’un autre logo est choisi pour la zone.

**Certifications différentes par zone** : sélectionner la facette puis son contenant
Pictogrammes, et cliquer **Choisir les pictogrammes de cette zone** au-dessus du plan, ou
**Modifier le contenu** à droite. Le sélecteur affiche les images de la liste **Contenus** :
cocher uniquement celles à imprimer ici, puis **Appliquer à cette zone**. **Tout décocher**
laisse cette zone vide ; **Suivre Contenus** reprend la liste générale, hors tampons. Une
sélection propre ne change pas les autres zones de la face. Une facette qui recopie encore
la face modifiée la suit : personnaliser sa propre zone pour lui donner une sélection différente.
Le dialogue indique les facettes liées. **Gérer la liste dans Contenus** permet d’y ajouter
d’autres pictogrammes ou images de certification. Les anciens designs gardent leur rendu.

**Couleur et SVG d’une certification ou d’un tampon** : sélectionner sa zone, puis **Couleur & SVG**
sous la vignette du pictogramme à droite. Choisir une couleur HEX, la palette ou **Pipette / image**,
conserver les parties blanches si nécessaire, puis **Prévisualiser** et **Appliquer à cette zone**.
Le résultat est téléchargeable en SVG. La couleur suit les **faces identiques liées**, que l’on
modifie la face source ou sa copie. **Original** rétablit le dessin d’origine sur ces mêmes faces.
Les autres zones et les facettes volontairement indépendantes gardent leur dessin.
Un vrai SVG conserve ses courbes et son texte, sans appel IA. Les SVG avec masques ou filtres
doivent d’abord être exportés avec leurs effets décomposés pour éviter de changer la silhouette.
Pour une source PNG/JPEG, **Vectoriser en couleurs** produit des tracés SVG avec 8 à 128 couleurs :
les petits détails restent à comparer à l’original, sans promesse de récupérer une résolution absente.
La variante est un fichier privé attaché au design, partagé par l’aperçu, le PDF et ses textures 3D ;
elle suit également la duplication du design. Pour créer un nouveau badge, **Contenus →
Pictogrammes et certifications → Tampon IA** propose déjà des SVG à partir du texte, de la forme
et des couleurs choisis. Pour reproduire une certification existante, importer son visuel d’origine.

**Rotation individuelle** : sélectionner la zone Pictogrammes. Sous chaque pictogramme,
certification ou tampon, saisir **Angle (°)** puis **Appliquer** (ou Entrée), ou utiliser
**−90°**, **+90°** et **0°**. Les angles positifs tournent dans le sens horaire autour du centre
du symbole ; son dessin s’ajuste à son emplacement pour rester dans la zone. Chaque angle est
propre à ce symbole dans cette zone, avec le même rendu sur le plan, le PDF et les textures 3D.
La rotation conserve les couleurs, la sélection, la disposition et le décalage du contenu.
Les autres zones conservent leur orientation. Les faces liées par **Face arrière identique**
ou **Côtés identiques** reprennent l’angle, même si on le change depuis la face copiée.
Les facettes déjà personnalisées restent indépendantes ; **Revenir à la maquette automatique**
sur la copie rétablit le lien avec la face source.

**Panneau de droite** : les propriétés sont repliables, avec une section ouverte à la fois.
Chaque pictogramme a aussi son volet pour la rotation et la couleur. La section, le pictogramme
ouvert et le défilement sont conservés pendant les sauvegardes et les changements de sélection
dans la session. Quand les trois colonnes sont côte à côte, chacune défile indépendamment :
la molette ou la barre de défilement de gauche et de droite parcourt les réglages sans déplacer
le composant affiché au centre. Le plan garde sa taille normale et sa propre barre de défilement.
La page entière reste fixe pendant le travail : descendre dans le plan ne masque pas les panneaux.
Les positions sont conservées lors des mises à jour du même design. Sur petit écran, la page
retrouve son défilement normal, sans bloquer les panneaux empilés. Ce défilement normal est aussi
rétabli dès que l’on quitte le studio.

**Disposition des pictogrammes** : dans les propriétés d’une zone Pictogrammes, choisir
**↔ Horizontal** pour une rangée ou **↕ Vertical** pour une colonne. Le même choix existe dans
le sélecteur de certifications, validé par **Appliquer à cette zone**. Les symboles gardent leur angle
et leur taille s’ajuste pour tenir dans le cadre ; le cadre, la sélection et le décalage du contenu
sont conservés. Le réglage est propre à chaque zone et repris dans le PDF et ses textures 3D.
Pour déplacer la rangée ou la colonne, utiliser **Contenu dans le cadre**. Sans réglage, les
anciens designs conservent leur disposition horizontale.

**Contenus visibles pendant l’édition** : toutes les facettes affichent leurs logos, photos,
pictogrammes, tampons, QR et EAN, même sans sélectionner une face. Les symboles utilisent
le même placement et les mêmes images que le PDF, avec une seule copie de chaque image dans la
réponse du studio. Un QR placé explicitement remplace le QR automatique du dos. Le menu **Ajouter**
montre un aperçu du choix avant de le placer, y compris pour les textes et les tampons. Chaque
ajout ouvre ses réglages et un bouton **Modifier le contenu** mène à sa saisie. Les zones vides
affichent **À renseigner** sur le plan et proposent **Renseigner le contenu** ; ces repères ne
s’impriment jamais. L’édition d’un texte par langue conserve les autres champs et traductions.
La photo automatique reste derrière les autres
éléments ; sélectionner une face donne accès aux cadres de déplacement et de redimensionnement.

**Textes visibles pendant l’édition** : chaque facette affiche le nom réel du produit,
l’accroche, les caractéristiques, avertissements, contacts et textes libres enregistrés. Le HTML
de mise en forme est partagé avec le PDF (polices, tailles, couleurs, langues et préfixes par
ligne) ; le texte saisi est échappé, jamais interprété comme du HTML. Les repères centraux de la
face contenant des éléments s’effacent pour dégager le contenu. Le navigateur ajuste le texte au cadre ;
**Aperçu imprimé** reste la référence pour les coupures de ligne et la réduction finale des textes.

**3D du design composé** : l’onglet **3D** propose deux possibilités :

- **Maquette interactive gratuite** : pour les étuis à rabats, les six faces du PDF actuel sont
  posées sur une boîte aux dimensions du design. Glisser à la souris ou au doigt pour tourner,
  utiliser les vues avant/arrière/côtés/dessus/dessous et le zoom. **Créer/Actualiser la maquette 3D**
  compose d’abord le PDF si nécessaire. Les textures restent dans la session, sans fichier ajouté
  ni appel IA ; elles sont renouvelées après un changement du design. Les autres formes gardent
  l’accès au rendu IA ; leur géométrie interactive n’est pas encore prise en charge.
- **Rendu réaliste par IA** : **Générer l’aperçu 3D** affiche le coût estimé d’une image et prend
  comme références les faces du PDF à jour, avec les logos et leur rotation. Ce résultat est une
  illustration. L’IA ne démarre que lorsque l’utilisateur clique sur le bouton de génération.

Les traits du calque « Découpe et plis » sont masqués dans les textures interactives et les
références IA, sans modifier le PDF imprimeur. Les textures sont plafonnées en résolution.

Les saisies sont regroupées et enregistrées dans l’ordre, sur leur design d’origine. Exporter
ou ouvrir un atelier attend les saisies en cours. L’état de sauvegarde apparaît dans l’en-tête,
avec une relance en cas d’échec. Les catalogues ne sont plus reconstruits à chaque sauvegarde.

**Textes et exports** : `textes_valides` contient les textes imprimés par langue ; les trois
champs de saisie de la fiche reflètent la première langue. `textes_ia` contient les propositions.
Les anciens designs conservent leurs textes imprimés lors de l’ouverture ; les traductions des
langues décochées restent disponibles. Une empreinte des entrées du design rend explicite
l’état « PDF à créer / à jour / à régénérer ». Les anciens PDF sans empreinte sont à régénérer
une fois, et restent téléchargeables. L’empreinte suit le design, pas les modifications externes
aux fichiers, aux fiches Article/Marque ou aux catalogues partagés : recomposer après ces changements.
L’empreinte inclut aussi la version du moteur : une correction de rendu indique les anciens
PDF et simulations comme étant à régénérer. Les bitmaps carrés gardent les mêmes proportions,
zoom et décalage que dans le studio. Pour les SVG imbriqués (certifications avec un logo dans
un cercle, par exemple), CairoSVG conserve le placement interne, la découpe et les chemins
vectoriels ; le centrage sur l’encre et la recoloration utilisent la même conversion.
Cette conversion nécessite `CairoSVG~=2.9.1` (dépendance Python de l’application) et `libcairo2`
sur le serveur. Installer les dépendances actualisées lors du déploiement.

**Organisation du code** :

- `emballage/studio.py` : lecture groupée, sauvegarde, bibliothèque et compatibilité des routes.
- `emballage/contenus.py` : version imprimée et synchronisation de la saisie.
- `emballage/exports.py` : vérifications et empreintes PDF/simulation.
- `emballage/atelier_images.py`, `vectorisation.py`, `ressources.py` : transformations et accès aux images.
- `public/js/studio_emballage/` : état/sauvegarde, édition du plan, médias, éditeur de lignes.
  Frappe assemble ces composants avec ses inclusions de Page ; les anciennes routes serveur restent valides.

Pour mettre à jour un site existant, appliquer le schéma avant d’utiliser les nouveaux scripts :

```sh
bench --site <site> reload-doc aquaworld_ia doctype design_emballage
bench --site <site> clear-cache
```

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

**Vectorisation couleur dans le studio** : étape 2 → « Modifier » sous la photo
produit ou le logo → « SVG couleur · gratuit ». Choisir un profil (logo, illustration, photo), 8 à 128 couleurs et, si besoin,
le retrait du fond blanc. Comparer l’original au résultat avant « Utiliser ce SVG », ou télécharger
le fichier. Chaque résultat reste dans la médiathèque ; la source n’est pas écrasée. Recomposer
ensuite le plan à l’étape 4 : les courbes restent vectorielles dans le PDF imprimeur.

L’atelier permet aussi de choisir une image de la galerie sans l’adopter. « SVG couleur » dans
la médiathèque ouvre directement la source choisie. Pour une image difficile à tracer,
« Préparer par IA… » ouvre la retouche existante avec une consigne d’illustration en aplats,
une seule proposition par défaut et le coût estimé avant génération. Chaque proposition IA
dispose ensuite de « Vectoriser en SVG couleur » : la conversion reste gratuite, seule la
préparation IA est facturée. Vérifier les détails du produit avant adoption.

Le traitement est local avec VTracer, sans appel ni coût IA. Entrées PNG/JPEG/WebP, maximum 20 Mo
et 25 mégapixels, tracé limité à 1 600 px au plus long côté. Les SVG existants n’ont pas besoin de
ce traitement ; « Recolorer le logo » reste disponible dans ses outils. Une photo vectorisée
devient une illustration : les reflets et dégradés sont simplifiés, les transparences partielles
sont seuillées. Pour un rendu photographique, conserver le PNG/JPEG haute résolution.

## Résolution des images et export groupé

Dans **Contenus → Modifier l’image → Améliorer la résolution**, choisir ×2 ou ×4 :
**Photo · IA locale** utilise FSRCNN sur CPU, gratuitement, sans envoyer de photo à une API ;
**agrandissement fidèle** utilise Lanczos, adapté aux logos et certifications. Comparer les deux
images avec le zoom puis cliquer **Utiliser cette image**. L’original reste en médiathèque.
Transparence, proportions et centrage du logo sont conservés. Une source ou un design modifié
pendant le traitement empêche l’adoption d’une proposition périmée.

À l’étape **Vérifier et exporter**, cocher **Préparer toutes les images à 300 ppp**, puis créer
ou actualiser le PDF. Ce choix est mémorisé sur le design. Un worker prépare le PDF courant,
mesure chaque image à sa taille imprimée (zoom et rotation compris), puis agrandit fidèlement
les images insuffisantes, jusqu’à ×4. Cela couvre fonds, photos, logos bitmap et images contenues
dans des SVG, y compris toutes leurs copies. Les textes, tracés SVG, codes, placements et
calques restent vectoriels/inchangés. Les fichiers sources du design ne sont pas remplacés.
Le **Bilan résolution** conserve les vignettes, dimensions et ppp avant/après et signale les
sources toujours insuffisantes ; il est marqué ancien si le design a changé depuis l’export.

Limites : 40 millions de pixels par image et 120 millions de pixels traités par PDF ; réduction
automatique du facteur et signalement si nécessaire. Le lot utilise le mode fidèle, sans
redessiner les certifications. L’IA pour une photo se compare dans son outil avant adoption.
Augmenter les pixels ne garantit pas de retrouver les détails perdus, ni une conformité PDF/X,
CMJN ou aux exigences particulières de l’imprimeur.

Installation : modèles FSRCNN ×2/×4 inclus avec leur licence Apache 2.0 dans
`emballage/modeles_resolution` ; `opencv-contrib-python-headless` remplace la distribution
OpenCV simple dans les deux apps du bench qui l’utilisent (ne pas installer les deux en même
temps). Après déploiement : installer les dépendances, `bench --site <site> migrate`, vider le
cache et redémarrer les workers. Aucun téléchargement de modèle à l’exécution.

Prévoir aussi la taille des fichiers d’impression : les PDF agrandis peuvent dépasser
10 Mo. Frappe contrôle la limite à deux endroits. Pour autoriser 100 Mo, renseigner
**System Settings → Max File Size (MB)** à `100` et exécuter
`bench --site <site> set-config --parse max_file_size 104857600` (nombre entier en octets). La limite concerne
les fichiers du site, pas seulement les PDF. Les nouvelles requêtes et nouveaux jobs
reprennent cette configuration ; relancer un export qui avait échoué avant le réglage.

## Transfert dev → prod des documents de travail

Les manuels et designs ne sont pas des fixtures. `transfert.exporter_travail(chemin, noms=None)` écrit un zip
(docs.json + files/ + files.json) ; `transfert.importer_travail(chemin, remplacer=0)` recrée les documents sous les
mêmes noms (existants sautés, sauf `remplacer`), pose les fichiers manquants et leurs fiches File, et aligne les
compteurs de série (`aligner_series`). Ex. :
`bench --site <site> execute aquaworld_ia.transfert.exporter_travail --kwargs "{'chemin': '/tmp/travail.zip'}"`.

## Réglages et coûts

- Clé OpenAI : `AI Settings.openai_api_key` (Single livré par woocommerce_fusion) ou
  `site_config.json` (`openai_api_key`). Modèles dans `Aquaworld IA Reglages`.
- Chaque appel est journalisé (`Journal IA` : jetons, images, coût estimé). Plafond mensuel et
  seuil d'alerte e-mail dans les réglages ; grille de tarifs éditable (les prix OpenAI changent).

Dans **Aquaworld IA → Réglages → Modèles par outil**, sélectionner indépendamment les modèles
des fiches techniques, des manuels produit, de la lecture des sources produit et de leurs
traductions. Les manuels multilingues, la lecture/mise en page du Studio manuel, les textes
d’emballage, les illustrations des manuels, les images/fonds d’emballage, les logos et les
mockups ont aussi leur propre réglage. Un champ vide reprend le modèle texte ou image général ;
le modèle texte général vide reprend `AI Settings`, puis la configuration du site.
Les identifiants restent saisissables librement et doivent être compatibles avec l’usage et
l’accès API. Lecture de scans et reconstruction de pages nécessitent la lecture d’images.

Le choix s’applique aux prochains appels, y compris les reprises et les traductions en lots
parallèles. Les modèles effectivement appelés sont conservés dans le journal. Les coûts
texte suivent leur grille intégrée, sauf tarif global explicitement renseigné ; les tarifs
image restent des estimations communes configurées par qualité. Aucun modèle actif n’est
changé lors de l’installation des nouveaux champs, laissés vides.

Le catalogue des réglages, vérifié le 05/11/2026 dans la [documentation OpenAI](https://developers.openai.com/api/docs/models/all),
inclut GPT-6 Astra, GPT-6.1 Sol, GPT-6.1 Terra, GPT-6 Luna, GPT-6 Sol, les trois modèles GPT-5.6,
GPT-5.5, GPT-5.4 et Mini, ainsi que les choix texte précédemment proposés. Pour les images,
GPT Image 2.6 et 2.5 Sunburst/Flare complètent GPT Image 2 et les anciens 1.5/1 Mini ; le modèle
retiré GPT Image 1 n’est plus suggéré. La saisie d’un identifiant complet reste possible et
la présence dans la liste ne garantit pas les droits d’accès API du compte.

Les appels GPT-6 et GPT-5.6 conservent le mode JSON et leur raisonnement par défaut, sans
paramètre de température incompatible. Les tarifs texte ajoutés sont ceux du traitement
Standard, hors cache, contexte long et suppléments éventuels. Le tarif promotionnel GPT-5.6
Sol est annoncé jusqu’au 30/11/2026 et devra être revérifié. Les estimations d’images restent
configurées par qualité et doivent être adaptées au modèle et à la taille employés.

## Développement

```
bench --site <site> install-app aquaworld_ia
bench --site <site> run-tests --app aquaworld_ia      # fonctions pures, sans appel IA
node --test aquaworld_ia/tests/test_studio_emballage.js  # depuis le dossier de l’app
```

Aucun DocType en fixtures : langues et pictogrammes sont semés (idempotents) par
`aquaworld_ia.install.after_migrate`.

## Documents produit IA

Dans l’onglet **Aquaworld IA**, le raccourci **Documents produit IA** ouvre le générateur.
La partie **Réglages** donne accès aux **En-têtes des documents**, aux réglages IA et aux
langues. Le formulaire **Aquaworld IA Réglages** comporte aussi une section pour créer ou
gérer les en-têtes et ouvrir le générateur.

Depuis une fiche Article, ouvrir **Aquaworld IA → Documents produit IA**, ou la section
**Documents produit**. La page `/app/documents-produit` regroupe les dossiers.
Un dossier appartient à l'article parent et définit les variantes couvertes, les sources
(PDF ou photos de pages) et les illustrations. Les manuels existants et les pièces jointes
aux articles peuvent être réutilisés. Une page de PDF peut devenir une illustration.

### Disposition de la page d’un dossier (06/11/2026)

La page suit l’ordre du travail, en quatre étapes affichées dans une colonne à gauche
(bandeau horizontal sur téléphone) : **1 Préparer** (consignes, variantes, sources, photos),
**2 Présenter** (marque et logo, en-tête, mise en page), **3 Rédiger** (modèle IA, coûts,
commandes de génération) et **4 Relire et produire** (versions, corrections, traduction, PDF).
Une seule étape est visible à la fois ; chaque étape de la colonne indique ce qui est fait
(✔), manquant (✖) ou facultatif (–) : variantes cochées, sources, photos, logo, en-tête,
mise en page, versions rédigées, points à vérifier, versions validées. Ces indications
suivent la saisie en cours, avant même l’enregistrement. À l’ouverture, la page s’ouvre
sur **Relire et produire** quand l’onglet a déjà une version, sinon sur **Préparer** ; la
dernière étape visitée est mémorisée dans la session du navigateur.

Une barre fixe en bas de page porte l’état (« Tout est enregistré » ou « Modifications non
enregistrées »), le bouton unique **Enregistrer** — qui sauve le dossier, la mise en page et
les corrections de la version en cours — et la commande **Créer la fiche technique** /
**Créer le manuel** de l’onglet actif. Ces commandes, comme **Créer les deux** à l’étape
Rédiger, enregistrent d’abord ce qui a changé ; une génération ouvre l’étape Relire.
Le bouton **Guide** en haut ouvre le mode d’emploi de l’onglet dans une fenêtre.

Les **variantes couvertes** sont présentées en tableau : une colonne par attribut (le premier
attribut, par exemple la membrane, groupe les lignes avec une case par groupe), la référence,
un filtre, **Toutes** / **Aucune**. Les variantes sans attribut gardent une ligne référence / nom.
À l’étape **Relire et produire**, l’éditeur de la version et l’aperçu PDF sont côte à côte sur
grand écran, l’aperçu restant visible pendant la relecture ; ils se superposent sous 1 100 px.
La **Mise en page** de l’étape Présenter est repliée, avec un résumé sur une ligne
(colonnes, position de la photo, zone de marque, photos des variantes) ; le réglage des
photos des variantes (avec leur référence ou dans les illustrations, une à trois colonnes)
s’y trouve, puisqu’il est propre à chaque onglet.

Dans **Préparer**, **Choisir les photos des articles** ouvre une
galerie des images principales et pièces jointes accessibles du parent, des variantes
cochées et du dossier. Plusieurs vues peuvent être choisies par variante. La suggestion
reprend les photos principales distinctes des articles qui n’ont pas déjà une vue
sélectionnée ; elle évite les images déjà choisies et ne fait aucun appel IA. Les images
répétées entre variantes sont masquées au départ ; un bouton ou une recherche permet
de les retrouver et de les choisir explicitement. Les associations suivent les articles d’origine
et restent modifiables. **Importer des photos** accepte plusieurs fichiers.

Choisir la **Photo principale**, saisir les légendes et régler l’ordre avec les flèches.
On peut regrouper les autres vues avec la référence et les attributs de leur variante,
et afficher les galeries sur une, deux ou trois colonnes. Les vues communes apparaissent
dans les illustrations ; les variantes sans autre vue restent dans un tableau compact.
Les dispositions sont propres à chaque onglet ; les images choisies
sont communes au dossier, limitées à 20. Retirer une vue ne supprime pas le fichier joint.

Après enregistrement, **Générer le PDF** applique aussi les ajouts, retraits, changements
d’ordre et d’association des photos à une nouvelle version, sans nouvelle rédaction IA.
Les légendes corrigées ou traduites des photos conservées sont maintenues ; une légende
modifiée ou ajoutée est reprise telle que saisie, sans traduction automatique. Les anciens
PDF restent conservés. Une photo associée à une variante absente de la version demande
d’abord une nouvelle rédaction avec cette variante. Une variante décochée ne réaffecte
jamais silencieusement ses photos à toute la gamme.

Chaque dossier comporte deux onglets : **Fiche technique** et **Manuel d’utilisation**.
Chacun a sa commande de génération, son modèle IA, sa mise en page, ses versions et ses
traductions. Le **Guide** est adapté à la fiche ou au manuel : préparation avec ou sans PDF
source, choix du modèle, rédaction, relecture, validation et traduction, logo et placement
libre, en-têtes et pieds de page, colonnes photo/description, versions et coûts.
La marque, l’en-tête, les consignes, les sources, les photos et les variantes sont partagés ;
les corrections sont enregistrées avant de changer d’onglet. Le dernier onglet est mémorisé
dans la session du navigateur ; un lien se terminant par `/fiche` ou `/manuel` ouvre
directement le type voulu.

**Mise en page** permet de définir une disposition différente par onglet
et par dossier. La **Zone photo et description** propose **Une colonne** ou **Deux colonnes**
(photo à gauche et description à droite, 50/50 au premier choix). On peut inverser les côtés
et ajuster la répartition ; les autres blocs gardent toute la largeur. Les réglages incluent
la photo au-dessus, sous, à gauche ou à droite de la description ; largeur
(20–80 %, limitée à 55 % à côté du texte), hauteur maximale (20–120 mm), alignement du
titre et couleur des titres. Les cinq blocs (présentation/photo, rubriques, caractéristiques,
variantes, autres illustrations) se déplacent par glisser-déposer ou avec les flèches.
L’en-tête, le titre et le pied de page conservent leurs emplacements. L’aperçu montre la
disposition ; le PDF final dépend du contenu et de la pagination A4.

La **Zone de marque** affiche le logo sélectionné dans l’aperçu, avec un choix de position
au-dessus du titre, sous le titre ou à la fin du document. Elle peut être masquée, alignée
à gauche, au centre ou à droite, avec une largeur maximale de logo entre 10 et 70 mm et
un nom de marque facultatif. La zone apparaît une seule fois ; les en-têtes personnalisés
restent répétés. La case **Afficher aussi le logo de la marque avec un en-tête personnalisé**
reste nécessaire pour combiner les deux. **Voir / placer le logo** rejoint ces réglages
depuis le cadre **Marque du document** ; **Actualiser le logo** récupère une modification
de la fiche de marque et renouvelle l’image affichée grâce à son empreinte de contenu.
L’aperçu montre la marque actuellement choisie et signale une différence avec celle de
la version affichée : une nouvelle rédaction reste nécessaire pour actualiser les textes.

**Déplacer le logo à la souris** active le **Placement libre sur la première page**.
Le cadre se déplace sur l’aperçu A4 à la souris, au doigt ou avec les flèches du clavier
(1 mm, ou 10 mm avec Maj). Les distances depuis les bords gauche et haut peuvent aussi
être saisies au dixième de millimètre ; le cadre reste dans les limites de la page.
On peut préparer son emplacement avant d’ajouter l’image de marque. **Actualiser le fond
PDF** affiche la version sélectionnée avec les corrections en cours, ou un exemple si
aucune version n’existe, sans IA ni création de document ou de fichier. Le logo libre
se superpose à la première page sans déplacer le texte : le fond permet de vérifier
son emplacement. Son déplacement ne relance pas la préparation du fond. Ces réglages
restent indépendants entre fiche technique et manuel.

**Enregistrer la mise en page**, puis **Générer le PDF**, applique ces réglages au contenu
existant dans une nouvelle version, sans appel IA et sans écraser les anciennes versions.
Les nouvelles rédactions conservent aussi la disposition choisie ; une traduction reprend
la présentation de sa version source. La photo principale reste la première photo de la
version. Le réglage d’une fiche ne modifie pas celui du manuel. **Disposition initiale**
rétablit le gabarit d’origine pour l’onglet actif.

Sans PDF de référence, les données de l’article et les éléments fournis servent de base,
avec des points à vérifier lorsque les informations manquent. Les textes, rubriques,
caractéristiques et légendes restent modifiables après génération.

**Marque du document** permet de choisir une marque existante (par exemple ecoPurium),
d’en créer une et d’ajouter ou remplacer son logo directement dans le générateur.
Le choix vide reprend la marque de l’article. Le choix explicite s’applique aux nouvelles
fiches et aux nouveaux manuels du dossier, sans modifier les articles du catalogue ni les
marques de leurs composants. Le logo est enregistré sur la marque et partagé avec ses
autres produits. Une option permet de l’afficher aussi avec un en-tête personnalisé.
Changer de marque nécessite une nouvelle rédaction pour les documents existants ; changer
seulement le logo puis **Générer le PDF** crée une version sans appel IA.

**Créer la fiche technique**, **Créer le manuel** ou **Créer les deux** lance la rédaction
française en arrière-plan. Relire les caractéristiques, leurs sources, leurs modèles
concernés et les points à vérifier. **Enregistrer mes corrections** crée une nouvelle
version. **Valider et générer le PDF** est disponible après résolution des points à vérifier.
Le PDF, le fichier `.tex` et l'archive LaTeX avec ses images restent attachés à la version.

**Traduire** part d'une version française. La traduction est sauvegardée immédiatement en
base, comme brouillon indépendant, avec sa langue et son lien vers la version française.
Sa sauvegarde ne dépend pas de la réussite d'une compilation PDF. Une nouvelle version
française ou une modification des articles/sources signale les documents concernés « À actualiser ».
Les PDF validés sont accessibles depuis le parent et les variantes couvertes. Les fichiers
restent privés et héritent des droits de l'article et du dossier.

Le studio affiche les **modèles effectifs par étape**, leurs tarifs et le **coût estimé par
génération** (50 derniers lancements avec appels IA), ainsi que le total du dossier.
Chaque lancement regroupe les lectures de scans, la rédaction et les reprises éventuelles ;
les traductions sont des lancements distincts. **Détail** donne les jetons et le coût de chaque
appel. Les coûts sont calculés après l'appel, hors remises de cache et taxes ; une consommation
non communiquée est signalée comme inconnue, jamais présentée comme un coût nul confirmé.
Les appels restent journalisés si une étape ultérieure échoue. PDF et corrections manuelles
ne déclenchent aucun appel IA. **Régler les modèles par outil** ouvre les réglages depuis le
générateur. Les tarifs se règlent dans **Aquaworld IA Réglages**.

**En-tête des PDF** permet de choisir parmi les modèles actifs **Letter Head / En-tête**
d’ERPNext, d’en créer plusieurs et d’en voir un aperçu. Le modèle et son pied de page sont
repris sur chaque page ; le choix vide conserve le logo de la marque. Les images locales
et le HTML de présentation sont pris en charge. Scripts, styles globaux et ressources
distantes ne sont pas exécutés : vérifier l’aperçu pour les modèles HTML complexes.

**Créer un en-tête** ouvre maintenant un éditeur visuel dans le générateur. Choisir le logo
à gauche, à droite ou centré ; ajouter ou remplacer l’image ; saisir le nom, le sous-titre,
deux blocs de contacts facultatifs et le pied de page. Largeur du logo, taille du texte,
couleur et traits sont réglables. L’aperçu des bandeaux utilise le rendu du PDF et se met
à jour après la saisie, sans IA ni enregistrement de fichier. Un bloc sans coordonnées
est masqué et la pagination est ajoutée automatiquement par le générateur.

Les **coordonnées** comptent jusqu’à quatre blocs côte à côte (06/11/2026) : les blocs 3 et 4
s’ajoutent avec **Ajouter un bloc** et se retirent (leur contenu est effacé) ; un bloc sans
coordonnées reste masqué dans le document. Chaque bloc a un titre en gras, une ligne
**Activité** en italique (facultative, ex. « Ventes, B2B, Partenariats »), ses lignes de
coordonnées et son **alignement du texte** (gauche, centré, droite). La case **Trait vertical
entre les blocs** trace, dans la couleur de l’en-tête, un trait à gauche de chaque bloc qui en
suit un autre (et à gauche du logo quand il est à droite), à la hauteur du texte du bloc : le
moteur de rendu des bandeaux ignore une bordure posée sur la cellule, le trait est donc porté
par le bloc lui-même. Les modèles enregistrés avant ces réglages se rendent à l’identique.

**Enregistrer et utiliser** crée un modèle réutilisable et le sélectionne dans le dossier.
**Modifier visuellement** permet de reprendre les modèles créés avec cet éditeur ;
**Enregistrer une copie** conserve l’original sous son nom. Le modèle global par défaut
d’ERPNext n’est pas changé par la création. Les anciens modèles en image ou en HTML restent
accessibles par **Réglages avancés** ; un modèle modifié manuellement hors de l’éditeur
n’est pas écrasé avec une configuration visuelle devenue obsolète. Les écritures vérifient
les droits et les modifications concurrentes du modèle et du dossier. Le champ masqué
de configuration sur **Letter Head** est installé après migration.

Le choix est enregistré avec le dossier et le contenu du modèle est figé dans chaque version.
Changer de modèle puis **Générer le PDF** crée une nouvelle version avec le texte existant,
sans appel IA et sans écraser l’ancienne. Les bandeaux sont inclus dans l’archive LaTeX.

### Installation

Les DocTypes et la page sont installés par `bench migrate`. `after_migrate` ajoute la section
Article. Sur un serveur hors Frappe Cloud, installer les dépendances déclarées dans
`pyproject.toml` avant de générer des PDF :

```sh
apt-get install --no-install-recommends texlive-xetex texlive-latex-extra texlive-fonts-recommended texlive-lang-arabic fonts-noto-core fonts-noto-cjk
bench --site SITE migrate
bench build --app aquaworld_ia
```

Un worker de la file `long` doit être actif. Les appels IA utilisent les réglages et le journal
existants de l'app. Aucun appel de génération d'image n'est nécessaire : les photos proviennent
des articles ou des documents sélectionnés. Maximum par dossier : 250 variantes, 12 sources,
20 illustrations ; 30 Mo par fichier et 40 pages utiles par PDF.

Le rendu utilise un modèle XeLaTeX contrôlé, des textes échappés et des images locales
rasterisées. L'exécution de commandes est désactivée avec `-no-shell-escape` ; le délai de
compilation est borné. Voir la [documentation XeTeX](https://tug.ctan.org/info/xetexref/xetex-reference.pdf).
L'arabe utilise `bidi` et Noto Naskh Arabic ; les scripts CJK et les principaux autres scripts
utilisent les familles Noto correspondantes. Une police manquante est signalée sans supprimer
la traduction enregistrée. La suite `aquaworld_ia.tests.test_documents_produit` contrôle les
versions, les permissions, les sources PDF/photo, les traductions (appels IA simulés) et les
PDF réels en français, arabe et chinois.
