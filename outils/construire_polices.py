"""Construit les polices statiques livrées avec aquaworld_ia (OFL, https://github.com/google/fonts,
fichiers « src_<nom> » téléchargés depuis ofl/<famille>/) : instance 400/700 des polices variables,
sous-ensemble européen (latin étendu, grec, cyrillique, ponctuation, symboles), sans hinting.

⚠️ Une police à « Reserved Font Name » (Lato) ne peut PAS être modifiée sous son nom : elle est
copiée telle quelle (poids « copie » ci-dessous). Playfair Display (RFN, variable seulement) a été
écartée pour cette raison au profit d'EB Garamond.

Usage : python construire_polices.py <dossier de sortie>   (depuis le dossier des sources)"""
import os, shutil, sys
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools import subset

UNICODES = ("U+0000-024F,U+0250-02FF,U+0300-036F,U+0370-03FF,U+0400-052F,U+1E00-1EFF,U+2000-206F,U+2070-209F,"
            "U+20A0-20CF,U+2100-214F,U+2150-218F,U+2190-21FF,U+2200-22FF,U+2300-23FF,U+25A0-25FF,U+2600-26FF,"
            "U+2700-27BF,U+FB00-FB06,U+FEFF,U+FFFD")
OUT = sys.argv[1]
# famille -> {style: (source, poids)}
JOBS = {
	"NotoSans": {"Italic": ("NotoSans-Italic[wdth,wght].ttf", 400), "BoldItalic": ("NotoSans-Italic[wdth,wght].ttf", 700)},
	"NotoSerif": {"Regular": ("NotoSerif[wdth,wght].ttf", 400), "Bold": ("NotoSerif[wdth,wght].ttf", 700),
	              "Italic": ("NotoSerif-Italic[wdth,wght].ttf", 400), "BoldItalic": ("NotoSerif-Italic[wdth,wght].ttf", 700)},
	"Montserrat": {"Regular": ("Montserrat[wght].ttf", 400), "Bold": ("Montserrat[wght].ttf", 700),
	               "Italic": ("Montserrat-Italic[wght].ttf", 400), "BoldItalic": ("Montserrat-Italic[wght].ttf", 700)},
	"Poppins": {"Regular": ("Poppins-Regular.ttf", None), "Bold": ("Poppins-Bold.ttf", None),
	            "Italic": ("Poppins-Italic.ttf", None), "BoldItalic": ("Poppins-BoldItalic.ttf", None)},
	"OpenSans": {"Regular": ("OpenSans[wdth,wght].ttf", 400), "Bold": ("OpenSans[wdth,wght].ttf", 700),
	             "Italic": ("OpenSans-Italic[wdth,wght].ttf", 400), "BoldItalic": ("OpenSans-Italic[wdth,wght].ttf", 700)},
	"Lato": {"Regular": ("Lato-Regular.ttf", "copie"), "Bold": ("Lato-Bold.ttf", "copie"),
	         "Italic": ("Lato-Italic.ttf", "copie"), "BoldItalic": ("Lato-BoldItalic.ttf", "copie")},
	"Roboto": {"Regular": ("Roboto[wdth,wght].ttf", 400), "Bold": ("Roboto[wdth,wght].ttf", 700),
	           "Italic": ("Roboto-Italic[wdth,wght].ttf", 400), "BoldItalic": ("Roboto-Italic[wdth,wght].ttf", 700)},
	"EBGaramond": {"Regular": ("EBGaramond[wght].ttf", 400), "Bold": ("EBGaramond[wght].ttf", 700),
	               "Italic": ("EBGaramond-Italic[wght].ttf", 400), "BoldItalic": ("EBGaramond-Italic[wght].ttf", 700)},
	"Oswald": {"Regular": ("Oswald[wght].ttf", 400), "Bold": ("Oswald[wght].ttf", 700)},
}
for fam, styles in JOBS.items():
	for style, (src, poids) in styles.items():
		if poids == "copie":
			chemin = os.path.join(OUT, "%s-%s.ttf" % (fam, style))
			shutil.copyfile("src_" + src, chemin)
			print("%7d %s (copie intacte)" % (os.path.getsize(chemin), chemin))
			continue
		f = TTFont("src_" + src)
		if "fvar" in f:
			axes = {a.axisTag: a.defaultValue for a in f["fvar"].axes}
			axes["wght"] = poids
			if "wdth" in axes:
				axes["wdth"] = 100
			f = instantiateVariableFont(f, axes, updateFontNames=False)
		opts = subset.Options()
		opts.layout_features = ["*"]
		opts.name_IDs = ["*"]
		opts.name_languages = ["*"]
		opts.notdef_outline = True
		opts.hinting = False
		opts.desubroutinize = True
		sub = subset.Subsetter(opts)
		sub.populate(unicodes=subset.parse_unicodes(UNICODES))
		sub.subset(f)
		# Noms internes cohérents (une instance garde sinon le nom de l'instance par défaut, « Thin »).
		nom_fam = {"NotoSans": "Noto Sans", "NotoSerif": "Noto Serif", "OpenSans": "Open Sans",
		           "EBGaramond": "EB Garamond"}.get(fam, fam)
		sous = {"Regular": "Regular", "Bold": "Bold", "Italic": "Italic", "BoldItalic": "Bold Italic"}[style]
		nt = f["name"]
		for nid in (16, 17, 21, 22, 25):
			nt.removeNames(nameID=nid)
		for nid, val in ((1, nom_fam), (2, sous), (4, "%s %s" % (nom_fam, sous)), (6, "%s-%s" % (fam, style))):
			nt.setName(val, nid, 3, 1, 0x409)
			nt.setName(val, nid, 1, 0, 0)
		f["OS/2"].usWeightClass = 700 if "Bold" in style else 400
		chemin = os.path.join(OUT, "%s-%s.ttf" % (fam, style))
		f.save(chemin)
		print("%7d %s" % (os.path.getsize(chemin), chemin))
