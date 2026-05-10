"""
Filtre de texte pour imprimantes thermiques ESC/POS.
Convertit emojis et caracteres typographiques Unicode en equivalents ASCII.
"""
import re
import unicodedata

# Caracteres typographiques (apostrophes, guillemets, tirets, etc.)
# On utilise les escape sequences \u pour eviter les problemes d'encodage
# lors du copier-coller dans le terminal.
TYPO_MAP = {
    "\u2018": "'",   # apostrophe gauche
    "\u2019": "'",   # apostrophe droite (la classique)
    "\u201A": "'",   # virgule simple basse
    "\u201B": "'",
    "\u201C": '"',   # guillemet typographique gauche
    "\u201D": '"',   # guillemet typographique droit
    "\u201E": '"',   # guillemet bas
    "\u201F": '"',
    "\u00AB": '"',   # guillemet francais ouvrant
    "\u00BB": '"',   # guillemet francais fermant
    "\u2039": "<",
    "\u203A": ">",
    "\u2013": "-",   # en-dash
    "\u2014": "-",   # em-dash
    "\u2015": "-",
    "\u2010": "-",
    "\u2011": "-",
    "\u2212": "-",
    "\u2026": "...", # points de suspension
    "\u00B7": ".",
    "\u2022": "*",   # bullet
    "\u25E6": "o",
    "\u25AA": "-",
    "\u25AB": "-",
    "\u00A0": " ",   # espace insecable
    "\u2009": " ",
    "\u200B": "",
    "\u200C": "",
    "\u200D": "",
    "\uFEFF": "",
    "\u00A9": "(c)",
    "\u00AE": "(R)",
    "\u2122": "(TM)",
    "\u00B0": " deg",
    "\u00B1": "+/-",
    "\u00D7": "x",
    "\u00F7": "/",
    "\u2248": "~",
    "\u2260": "!=",
    "\u2264": "<=",
    "\u2265": ">=",
    "\u2192": "->",
    "\u2190": "<-",
    "\u2191": "^",
    "\u2193": "v",
    "\u2194": "<->",
    "\u21D2": "=>",
    "\u21D0": "<=",
    "\u2713": "v",
    "\u2717": "x",
    "\u2605": "*",
    "\u2606": "*",
}

# Emojis -> equivalents ASCII expressifs
EMOJI_MAP = {
    # Meteo
    "\u2600\ufe0f": "(*)", "\u2600": "(*)",                     # soleil
    "\U0001F324\ufe0f": "(*~)", "\U0001F324": "(*~)",           # soleil derriere nuage
    "\u26C5\ufe0f": "(~)", "\u26C5": "(~)",                     # soleil partiel
    "\u2601\ufe0f": "(##)", "\u2601": "(##)",                   # nuage
    "\U0001F325\ufe0f": "(#~)", "\U0001F325": "(#~)",
    "\U0001F326\ufe0f": "(#.)", "\U0001F326": "(#.)",
    "\U0001F327\ufe0f": "(///)", "\U0001F327": "(///)",         # pluie
    "\u26C8\ufe0f": "(/Z/)", "\u26C8": "(/Z/)",                 # orage
    "\U0001F329\ufe0f": "(Z)", "\U0001F329": "(Z)",
    "\U0001F328\ufe0f": "(***)", "\U0001F328": "(***)",         # neige
    "\u2744\ufe0f": "(*)", "\u2744": "(*)",                     # flocon
    "\U0001F32B\ufe0f": "(===)", "\U0001F32B": "(===)",         # brouillard
    "\U0001F32A\ufe0f": "(@)", "\U0001F32A": "(@)",
    "\U0001F308": "(/^\\)",                                     # arc-en-ciel
    "\U0001F4A7": "(.)",                                        # goutte
    "\U0001F4A6": "(:)",                                        # eclaboussure

    # Emotions
    "\U0001F600": ":D", "\U0001F603": ":D", "\U0001F604": ":D", "\U0001F601": ":D",
    "\U0001F60A": ":)", "\U0001F642": ":)", "\U0001F607": ":)",
    "\U0001F609": ";)",
    "\U0001F60D": "<3", "\U0001F970": "<3", "\U0001F618": ":-*",
    "\U0001F60E": "B-)",
    "\U0001F61C": ":P", "\U0001F61B": ":P", "\U0001F61D": ":P", "\U0001F92A": ":P",
    "\U0001F914": ":-?", "\U0001F928": "o.O",
    "\U0001F622": ":(", "\U0001F62D": ":'(", "\U0001F97A": ":(",
    "\U0001F621": ">:(", "\U0001F620": ">:(",
    "\U0001F631": ":-O", "\U0001F628": ":-O", "\U0001F630": ":-/",
    "\U0001F634": "z..z",
    "\U0001F923": "XD", "\U0001F602": "XD",
    "\U0001F605": ":')",
    "\U0001F643": "(_:",
    "\U0001F636": ":|", "\U0001F610": ":|", "\U0001F611": ":|",
    "\U0001F910": ":-X",
    "\U0001F480": "X_X", "\u2620\ufe0f": "X_X", "\u2620": "X_X",
    "\U0001F47B": "(.o.)",
    "\U0001F47D": "(O_O)",
    "\U0001F916": "[O_O]",

    # Coeurs
    "\u2764\ufe0f": "<3", "\u2764": "<3", "\u2665\ufe0f": "<3", "\u2665": "<3",
    "\U0001F49B": "<3", "\U0001F49A": "<3", "\U0001F499": "<3", "\U0001F49C": "<3",
    "\U0001F5A4": "</3", "\U0001F90D": "<3", "\U0001F90E": "<3",
    "\U0001F494": "</3",
    "\U0001F495": "<3<3", "\U0001F49E": "<3<3", "\U0001F493": "<3", "\U0001F497": "<3", "\U0001F496": "<3*",
    "\U0001F498": "<3->",
    "\U0001F49D": "<3]",

    # Validation
    "\u2705": "[OK]", "\u2714\ufe0f": "[v]", "\u2714": "[v]",
    "\u2611\ufe0f": "[x]", "\u2611": "[x]",
    "\u274C": "[X]", "\u274E": "[X]",
    "\u2B55": "(O)",
    "\u2757": "!", "\u2755": "!", "\u203C\ufe0f": "!!", "\u203C": "!!",
    "\u2753": "?", "\u2754": "?", "\u2049\ufe0f": "!?", "\u2049": "!?",
    "\u26A0\ufe0f": "/!\\", "\u26A0": "/!\\",
    "\U0001F6AB": "(X)", "\u26D4": "(X)",
    "\u2728": "*sparkle*",
    "\u2B50": "(*)", "\U0001F31F": "(*)", "\U0001F4AB": "(*~)",
    "\U0001F525": "*FIRE*",
    "\U0001F4AF": "100",

    # Mains
    "\U0001F44D": "(y)", "\U0001F44E": "(n)",
    "\U0001F44C": "(ok)",
    "\U0001F44F": "*clap*",
    "\U0001F64F": "*merci*",
    "\U0001F4AA": "*muscle*",
    "\U0001F91D": "(handshake)",
    "\U0001F44B": "*wave*",
    "\u270C\ufe0f": "(V)", "\u270C": "(V)",
    "\U0001F449": "->", "\U0001F448": "<-",

    # Fleches
    "\u27A1\ufe0f": "->", "\u27A1": "->",
    "\u2B05\ufe0f": "<-", "\u2B05": "<-",
    "\u2B06\ufe0f": "/\\", "\u2B06": "/\\",
    "\u2B07\ufe0f": "\\/", "\u2B07": "\\/",

    # Objets et fete
    "\U0001F389": "***", "\U0001F38A": "***", "\U0001F973": "*party*",
    "\U0001F381": "[cadeau]", "\U0001F382": "[gateau]",
    "\U0001F4A1": "[idea]",
    "\U0001F527": "[tool]", "\U0001F528": "[hammer]",
    "\u2699\ufe0f": "[gear]", "\u2699": "[gear]",
    "\U0001F4F1": "[phone]", "\U0001F4BB": "[PC]",
    "\U0001F5A8\ufe0f": "[print]", "\U0001F5A8": "[print]",
    "\U0001F4F7": "[photo]", "\U0001F4F8": "[photo]",
    "\U0001F680": ">>>",
    "\U0001F41B": "[bug]",
    "\u2615": "[cafe]", "\U0001F375": "[the]",
}


def _build_regex(mapping):
    """Construit une regex qui matche les cles les plus longues d'abord."""
    keys = sorted(mapping.keys(), key=len, reverse=True)
    return re.compile("|".join(re.escape(k) for k in keys))


_typo_regex = _build_regex(TYPO_MAP)
_emoji_regex = _build_regex(EMOJI_MAP)


def replace_typo(text: str) -> str:
    return _typo_regex.sub(lambda m: TYPO_MAP[m.group(0)], text)


def replace_emojis(text: str) -> str:
    return _emoji_regex.sub(lambda m: EMOJI_MAP[m.group(0)], text)


def strip_remaining_unicode(text: str) -> str:
    """Nettoie ce qui reste : remplace les caracteres exotiques par '?' ou rien."""
    out = []
    for ch in text:
        cp = ord(ch)
        # ASCII de base + accents latins (CP858 / CP1252) -> on garde
        if cp < 0x180:
            out.append(ch)
        # Symboles, emojis, fleches non gerees -> '?'
        elif (0x2000 <= cp <= 0x27FF
              or 0x2900 <= cp <= 0x29FF
              or 0x1F000 <= cp <= 0x1FFFF):
            out.append("?")
        # Autres : tentative de decomposition NFKD
        else:
            try:
                normalized = unicodedata.normalize("NFKD", ch)
                ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
                out.append(ascii_only or "?")
            except Exception:
                out.append("?")
    return "".join(out)


def clean_for_printer(text: str) -> str:
    """Pipeline: typo -> emojis -> nettoyage."""
    if not text:
        return text
    text = replace_typo(text)
    text = replace_emojis(text)
    text = strip_remaining_unicode(text)
    return text
