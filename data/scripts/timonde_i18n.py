# -*- coding: utf-8 -*-
"""
Module d'internationalisation universel pour TiMonde (Python/GTK).
Clés de référence en Anglais (pivot international).
Charge dynamiquement le catalogue binaire GNU Gettext (.mo) de n'importe quelle
langue européenne installée (it, nl, pl, sv, da, nb, fi, cs, sk, hu, ro, el, hr, sl, bg, uk, et, lv, lt, ca, fr, es, de, pt).
"""

import os
import sys
import gettext

LOCALE_DIRS = [
    os.path.expanduser("~/.local/share/locale"),
    "/usr/share/locale",
    "/usr/local/share/locale",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "../../po/locale")),
]

_CURRENT_TRANSLATOR = None

def get_translator():
    global _CURRENT_TRANSLATOR
    if _CURRENT_TRANSLATOR is not None:
        return _CURRENT_TRANSLATOR

    env_lang = os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or "en"
    lang_code = env_lang.split(".")[0].split("_")[0].lower()

    if lang_code == "en":
        _CURRENT_TRANSLATOR = lambda s: s
        return _CURRENT_TRANSLATOR

    for ldir in LOCALE_DIRS:
        mo_file = os.path.join(ldir, lang_code, "LC_MESSAGES", "timonde.mo")
        if os.path.exists(mo_file):
            try:
                t = gettext.translation("timonde", localedir=ldir, languages=[lang_code], fallback=True)
                _CURRENT_TRANSLATOR = t.gettext
                return _CURRENT_TRANSLATOR
            except Exception:
                pass

    _CURRENT_TRANSLATOR = lambda s: s
    return _CURRENT_TRANSLATOR

def _(msg):
    # En cas de changement dynamique de LANG dans un même processus (tests unitaires)
    trans = get_translator()
    res = trans(msg)
    return res if res else msg
