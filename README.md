# Aquaworld IA

App Frappe/ERPNext v15 : deux fonctions IA (OpenAI) rattachées à l'Article.

## 1. Manuels d'utilisation multilingues (`Manuel Article`)

À partir du PDF **texte** anglais du fabricant, produit pour chaque langue de la liste prédéfinie
(`Aquaworld IA Langue` : fr, ar, de, es, it, pt, nl — activables) un PDF traduit **qui garde la
mise en page** : images, schémas et tableaux intacts, texte remplacé bloc par bloc (PyMuPDF
`insert_htmlbox`, police réduite si nécessaire, arabe façonné de droite à gauche avec Noto Naskh
Arabic embarquée).

Flux : fiche → PDF source → « Ajouter les langues actives » → « Traduire » → PDF téléchargeables
dans la grille, statistiques par langue (blocs réduits / non placés), journal.

Outil de diagnostic (sans fiche) :

```
bench --site <site> execute aquaworld_ia.manuels.spike.executer \
  --kwargs "{'chemin_pdf': '/chemin/manuel.pdf', 'langue': 'ar', 'pages': '1-5'}"
```

Limites : le texte incrusté dans les images et le texte en contours vectoriels ne sont pas
traduits ; les scans sont refusés (pas d'OCR) ; les blocs trop serrés sont réduits puis signalés
« non placés » ; le texte vertical reste en anglais ; les polices d'origine sont remplacées par
Noto. Relecture humaine recommandée pour les avertissements de sécurité.

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
