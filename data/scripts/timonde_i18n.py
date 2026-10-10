# -*- coding: utf-8 -*-
"""
Module d'internationalisation universel pour TiMonde (Python/GTK).
Clés de référence en Anglais (pivot international).
Charge dynamiquement le catalogue binaire GNU Gettext (.mo) des 55 langues supportées,
incluant la distinction entre Chinois Mandarin (zh_CN) et Cantonais/Traditionnel (zh_TW).
"""

import os
import sys
import gettext

LOCALE_DIRS = [
    os.path.abspath(os.path.join(os.path.dirname(__file__), "../../po/locale")),
    os.path.expanduser("~/.local/share/locale"),
    "/usr/share/locale",
    "/usr/local/share/locale",
]

_CURRENT_TRANSLATOR = None

def normalize_lang_code(raw_code):
    base = raw_code.split(".")[0].strip()
    lower = base.lower()
    if lower.startswith("zh_tw") or lower.startswith("zh_hk") or lower.startswith("zh_mo") or lower == "yue":
        return "zh_TW"
    if lower.startswith("zh_cn") or lower.startswith("zh_sg") or lower == "zh":
        return "zh_CN"
    return lower.split("_")[0]

def get_translator():
    global _CURRENT_TRANSLATOR
    if _CURRENT_TRANSLATOR is not None:
        return _CURRENT_TRANSLATOR

    env_lang = os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or "en"
    lang_code = normalize_lang_code(env_lang)

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
    trans = get_translator()
    res = trans(msg)
    return res if res else msg
