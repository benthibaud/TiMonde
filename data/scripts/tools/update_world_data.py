#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TiMonde — Outil de mise à jour du registre mondial des pays, langues et alias.
Tool to update the offline static countries, languages and multi-alias database.

Usage :
    python3 update_world_data.py [--force]

Règles de fonctionnement :
1. Frugalité réseau : n'exécute la mise à jour que si la dernière compilation
   remonte à 10 jours au moins (sauf si --force est spécifié).
2. Détecte et regroupe automatiquement tous les alias linguistiques renvoyés
   par Radio-Browser (latins comme deutsch/español et non-latins comme russe/arabe).
3. Régénère data/scripts/timonde_world_data.py pour les futurs paquets .deb et .rpm.
"""

import os
import sys
import json
import time
import urllib.request
import gettext
import unicodedata

RADIO_BROWSER_ENDPOINTS = [
    "https://de1.api.radio-browser.info",
    "https://nl1.api.radio-browser.info",
    "https://at1.api.radio-browser.info",
]

USER_AGENT = "TiMonde-Maintainer/0.1.0"
MIN_DAYS_INTERVAL = 10.0

# Racines pivots pour lier dynamiquement les alias saisis aux clés canoniques
CANONICAL_ROOTS = {
    "german": ["deutsch", "german", "allemand"],
    "spanish": ["span", "españ", "espan", "castell"],
    "french": ["french", "franç", "franc"],
    "portuguese": ["portug"],
    "romanian": ["roman", "român", "romin"],
    "russian": ["russ", "рус"],
    "arabic": ["arab", "عرب"],
    "thai": ["thai", "ไทย"],
    "hindi": ["hind", "हिन्द", "हिंदी"],
    "chinese": ["chin", "mandar", "canton", "中文", "国语", "漢語", "汉语"],
    "japanese": ["japan", "nihon", "日本語"],
    "greek": ["greek", "grec", "ελλην"],
    "hebrew": ["hebrew", "hébr", "עבר"],
    "korean": ["korean", "coréen", "한국", "조선"],
    "ukrainian": ["ukrain", "украин", "україн"],
    "dutch": ["dutch", "nederland", "néerland", "holland"],
    "italian": ["ital"],
    "polish": ["polish", "polski", "polon"],
    "swedish": ["swed", "svensk", "suéd"],
    "danish": ["dan", "dansk"],
    "finnish": ["finn", "suomi", "finnois"],
    "czech": ["czech", "cesk", "češt", "tchèq"],
    "hungarian": ["hungar", "magyar", "hongr"],
    "croatian": ["croat", "hrvat"],
    "serbian": ["serb", "срб"],
    "bulgarian": ["bulgar", "българ"],
    "persian": ["pers", "farsi", "فارس"],
    "urdu": ["urdu", "ourd", "اردو"],
    "turkish": ["turk", "türk"],
    "vietnamese": ["viet", "viêt"],
    "indonesian": ["indones"],
    "catalan": ["català", "catala"],
    "basque": ["euskara"],
    "galician": ["galego"],
    "irish": ["gaeilge"],
    "welsh": ["cymraeg"],
    "breton": ["brezhoneg"],
    "corsican": ["corsu"],
}

# Endonymes et graphies de référence garanties
BASE_NATIVE_ALIASES = {
    "german": ["deutsch"],
    "spanish": ["español", "castellano"],
    "french": ["français", "francais"],
    "portuguese": ["português", "portugues"],
    "romanian": ["română", "romana"],
    "danish": ["dansk"],
    "italian": ["italiano"],
    "dutch": ["nederlands"],
    "polish": ["polski"],
    "swedish": ["svenska"],
    "finnish": ["suomi"],
    "czech": ["čeština", "cesky"],
    "croatian": ["hrvatski"],
    "hungarian": ["magyar"],
    "catalan": ["català", "catala"],
    "basque": ["euskara"],
    "galician": ["galego"],
    "irish": ["gaeilge"],
    "welsh": ["cymraeg"],
    "breton": ["brezhoneg"],
    "corsican": ["corsu"],
    "russian": ["русский", "русский язык", "ру", "рус"],
    "arabic": ["العربية", "عربي", "عربية", "عرب"],
    "hindi": ["हिन्दी", "हिंदी"],
    "thai": ["ไทย", "ภาษาไทย"],
    "chinese": ["中文", "汉语", "漢語", "普通话", "国语", "國語"],
    "japanese": ["日本語", "にほんご"],
    "greek": ["ελληνικά", "ελληνική", "ελ"],
    "hebrew": ["עברית"],
    "korean": ["한국어", "조선말"],
    "ukrainian": ["українська", "українська мова", "укр"],
    "bengali": ["বাংলা"],
    "tamil": ["தமிழ்"],
    "telugu": ["తెలుగు"],
    "marathi": ["मराठी"],
    "urdu": ["اردو"],
    "persian": ["فارسی", "پارسی"],
    "punjabi": ["ਪੰਜਾਬੀ", "پنجابی"],
    "gujarati": ["ગુજરાતી"],
    "malayalam": ["മലയാളം"],
    "kannada": ["ಕನ್ನಡ"],
    "sinhala": ["සිංහල"],
    "burmese": ["မြန်မာစာ", "ဗမာစာ"],
    "khmer": ["ភាសាខ្មែរ"],
    "lao": ["ພາສາລາວ"],
    "georgian": ["ქართული"],
    "armenian": ["հայերեն"],
    "amharic": ["አማርኛ"],
    "tibetan": ["བོད་སྐད་"],
    "serbian": ["српски"],
    "bulgarian": ["български"],
    "macedonian": ["македонски"],
    "belarusian": ["беларуская"],
    "kazakh": ["қазақша", "қазақ тілі"],
    "mongolian": ["монгол хэл"],
    "tatar": ["татарча"],
    "tajik": ["тоҷикӣ"],
    "pashto": ["پښتو"],
    "kurdish": ["کوردی", "kurdî"],
    "yiddish": ["ייִדיש"],
}

NATIVE_COUNTRY_NAMES = {
    "DZ": ["الجزائر"],
    "MA": ["المغرب"],
    "TN": ["تونس"],
    "EG": ["مصر"],
    "LB": ["لبنان"],
    "SA": ["السعودية", "المملكة العربية السعودية"],
    "AE": ["الإمارات"],
    "SY": ["سوريا"],
    "IQ": ["العراق"],
    "RU": ["Россия", "РФ"],
    "UA": ["Україна"],
    "BY": ["Беларусь"],
    "RS": ["Србија"],
    "BG": ["България"],
    "GR": ["Ελλάδα", "Ελλάς"],
    "IL": ["ישראל"],
    "CN": ["中国"],
    "TW": ["台湾", "臺灣"],
    "JP": ["日本"],
    "KR": ["한국", "대한민국"],
    "IN": ["भारत"],
    "TH": ["ไทย", "ประเทศไทย"],
}

DISPLAY_NATIVE_MAP = {
    "russian": "Русский",
    "arabic": "العربية",
    "hindi": "हिन्दी",
    "thai": "ไทย",
    "chinese": "中文",
    "japanese": "日本語",
    "greek": "Ελληνικά",
    "hebrew": "עברית",
    "korean": "한국어",
    "ukrainian": "Українська",
    "bengali": "বাংলা",
    "tamil": "தமிழ்",
    "telugu": "తెలుగు",
    "marathi": "मराठी",
    "urdu": "اردو",
    "persian": "فارسی",
    "punjabi": "ਪੰਜਾਬੀ",
    "georgian": "ქართული",
    "armenian": "հայերեն",
    "amharic": "አማርኛ",
    "serbian": "Српски",
    "bulgarian": "Български",
    "belarusian": "Беларуская",
}

def strip_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn').lower()

def update_data():
    out_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'timonde_world_data.py'))
    force_update = "--force" in sys.argv or "-f" in sys.argv

    # Règle de frugalité réseau : vérifier si la dernière mise à jour a moins de 10 jours
    if not force_update and os.path.exists(out_file):
        age_days = (time.time() - os.path.getmtime(out_file)) / 86400.0
        if age_days < MIN_DAYS_INTERVAL:
            print(f"ℹ️  Dernière actualisation il y a {age_days:.1f} jour(s) (< {MIN_DAYS_INTERVAL} jours).")
            print("   Mise à jour en ligne ignorée par frugalité réseau.")
            print("   Utilisez 'python3 update_world_data.py --force' pour forcer l'actualisation.\n")
            return

    print("=== Démarrage de la mise à jour des pays, langues et alias ===")

    # 1. Pays ISO 3166-1
    print("1. Extraction des pays ISO 3166-1...")
    t_country = gettext.translation('iso_3166-1', fallback=True)
    countries_dict = {}
    iso_path = '/usr/share/iso-codes/json/iso_3166-1.json'
    if os.path.exists(iso_path):
        with open(iso_path) as f:
            data_c = json.load(f).get('3166-1', [])
        for item in data_c:
            code = item.get('alpha_2', '').upper()
            name_en = item.get('name', '')
            common_en = item.get('common_name', name_en)
            name_fr = t_country.gettext(common_en)
            if name_fr == common_en:
                name_fr = t_country.gettext(name_en)
            if code:
                countries_dict[code] = (name_fr, name_en)
        if 'GB' in countries_dict and 'UK' not in countries_dict:
            countries_dict['UK'] = countries_dict['GB']

    sorted_countries = sorted(countries_dict.items(), key=lambda x: strip_accents(x[1][0]))
    print(f"   -> {len(sorted_countries)} pays indexés.")

    # 2. Interrogation Radio-Browser
    print("2. Interrogation des miroirs Radio-Browser pour langues & alias...")
    raw_langs = None
    for ep in RADIO_BROWSER_ENDPOINTS:
        try:
            url = f"{ep}/json/languages?order=stationcount&reverse=true"
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=8) as resp:
                if resp.getcode() == 200:
                    raw_langs = json.loads(resp.read().decode("utf-8"))
                    print(f"   -> Données reçues depuis {ep} ({len(raw_langs)} entrées)")
                    break
        except Exception as e:
            print(f"   -> Échec miroir {ep}: {e}")

    if not raw_langs:
        print("   -> Impossible de contacter les miroirs Radio-Browser. Abandon.")
        return

    # Détection dynamique des alias à partir des tags vivants de Radio-Browser
    dynamic_aliases = {k: list(v) for k, v in BASE_NATIVE_ALIASES.items()}
    for item in raw_langs:
        raw_name = (item.get('name') or '').strip()
        cnt = item.get('stationcount', 0)
        if cnt < 2 or len(raw_name) < 2 or raw_name.startswith('http') or any(c in raw_name for c in '{}[]<>'):
            continue
        low = raw_name.lower()
        norm = strip_accents(low)

        for canon, roots in CANONICAL_ROOTS.items():
            if any(r in norm or r in low for r in roots):
                if low != canon and low not in dynamic_aliases.setdefault(canon, []):
                    dynamic_aliases[canon].append(low)

    print(f"   -> Détection terminée : {sum(len(v) for v in dynamic_aliases.values())} alias cartographiés.")

    # Nettoyage et tri des langues principales
    t_lang = gettext.translation('iso_639-2', fallback=True)
    iso639_path = '/usr/share/iso-codes/json/iso_639-2.json'
    lang_map = {}
    if os.path.exists(iso639_path):
        with open(iso639_path) as f:
            for entry in json.load(f).get('639-2', []):
                en = entry.get('name')
                if en:
                    fr = t_lang.gettext(en).split(';')[0].strip()
                    lang_map[en.split(';')[0].strip().lower()] = fr

    manual = {
        'french': 'Français', 'english': 'Anglais', 'spanish': 'Espagnol',
        'german': 'Allemand', 'italian': 'Italien', 'portuguese': 'Portugais',
        'russian': 'Russe', 'arabic': 'Arabe', 'chinese': 'Chinois',
        'hindi': 'Hindi', 'thai': 'Thaï', 'japanese': 'Japonais',
        'dutch': 'Néerlandais', 'polish': 'Polonais', 'turkish': 'Turc',
        'greek': 'Grec', 'swedish': 'Suédois', 'korean': 'Coréen',
        'indonesian': 'Indonésien', 'vietnamese': 'Vietnamien',
        'ukrainian': 'Ukrainien', 'romanian': 'Roumain', 'czech': 'Tchèque',
        'hungarian': 'Hongrois', 'danish': 'Danois', 'finnish': 'Finnois',
        'norwegian': 'Norvégien', 'hebrew': 'Hébreu', 'tamil': 'Tamoul',
        'bengali': 'Bengali', 'punjabi': 'Pendjabi', 'urdu': 'Ourdou',
        'persian': 'Persan (Farsi)', 'swahili': 'Swahili', 'catalan': 'Catalan',
        'croatian': 'Croate', 'serbian': 'Serbe', 'bulgarian': 'Bulgare',
        'slovak': 'Slovaque', 'bosnian': 'Bosnien', 'filipino': 'Philippin (Tagalog)',
        'nepali': 'Népalais', 'albanian': 'Albanais', 'macedonian': 'Macédonien',
        'slovenian': 'Slovène', 'lithuanian': 'Lituanien', 'latvian': 'Letton',
        'estonian': 'Estonien', 'icelandic': 'Islandais', 'irish': 'Irlandais (Gaélique)',
        'welsh': 'Gallois', 'basque': 'Basque', 'galician': 'Galicien',
        'breton': 'Breton', 'corsican': 'Corse', 'occitan': 'Occitan',
        'armenian': 'Arménien', 'georgian': 'Géorgien', 'azerbaijani': 'Azerbaïdjanais',
        'kazakh': 'Kazakh', 'uzbek': 'Ouzbek', 'mongolian': 'Mongol',
        'tibetan': 'Tibétain', 'burmese': 'Birman', 'khmer': 'Khmer',
        'lao': 'Lao', 'malay': 'Malais', 'telugu': 'Télougou',
        'marathi': 'Marathe', 'gujarati': 'Gujarati', 'kannada': 'Kannada',
        'malayalam': 'Malayalam', 'sinhala': 'Cinghalais', 'amharic': 'Amharique',
        'somali': 'Somali', 'yoruba': 'Yoruba', 'hausa': 'Haoussa',
        'zulu': 'Zoulou', 'afrikaans': 'Afrikaans', 'creole': 'Créole',
        'haitian creole': 'Créole haïtien', 'esperanto': 'Espéranto',
        'latin': 'Latin', 'kurdish': 'Kurde', 'pashto': 'Pachto',
    }

    clean_langs = []
    seen = set()
    for item in raw_langs:
        raw_name = (item.get('name') or '').strip()
        cnt = item.get('stationcount', 0)
        low = raw_name.lower().rstrip('.,;:')
        if low in seen or cnt < 3 or len(low) < 2:
            continue
        if any(k in low for k in ['test', 'unknown', 'various', 'none', 'n/a', 'http', 'fm', 'radio', 'stereo', '64k', '128k', 'aac', 'mp3', 'station']):
            continue
        seen.add(low)
        fr_name = manual.get(low) or lang_map.get(low) or manual.get(low.split()[0]) or lang_map.get(low.split()[0]) or raw_name.capitalize()
        clean_langs.append((low, fr_name, cnt))

    sorted_langs = sorted(clean_langs, key=lambda x: strip_accents(x[1]))
    print(f"   -> {len(sorted_langs)} langues actives principales retenues.")

    # 3. Écriture du fichier final autonome
    print("3. Écriture de timonde_world_data.py...")
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write('# -*- coding: utf-8 -*-\n')
        f.write('"""\nTiMonde — Référentiel Statique Hors-Ligne des Pays, Langues et Multi-Alias\n')
        f.write('Généré automatiquement par tools/update_world_data.py.\n')
        f.write(f'Horodatage : {time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())}\n"""\n\n')
        f.write('import unicodedata\n\n')
        f.write('def normalize_lookup(text: str) -> str:\n')
        f.write('    if not text:\n        return ""\n')
        f.write('    nfkd = unicodedata.normalize("NFD", text.strip())\n')
        f.write('    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn").lower()\n\n')

        f.write('WORLD_COUNTRIES = [\n')
        for code, (fr, en) in sorted_countries:
            fr_esc = fr.replace('"', '\\"')
            en_esc = en.replace('"', '\\"')
            f.write(f'    ("{code}", "{fr_esc}", "{en_esc}"),\n')
        f.write(']\n\n')

        f.write('RADIO_BROWSER_LANGUAGES = [\n')
        for api_key, fr, cnt in sorted_langs:
            api_esc = api_key.replace('"', '\\"')
            fr_esc = fr.replace('"', '\\"')
            f.write(f'    ("{api_esc}", "{fr_esc}", {cnt}),\n')
        f.write(']\n\n')

        f.write('NATIVE_LANGUAGE_NAMES = {\n')
        for canon_k, alias_list in sorted(dynamic_aliases.items()):
            aliases_repr = json.dumps(alias_list, ensure_ascii=False)
            f.write(f'    "{canon_k}": {aliases_repr},\n')
        f.write('}\n\n')

        f.write('NATIVE_COUNTRY_NAMES = {\n')
        for c_k, c_natives in sorted(NATIVE_COUNTRY_NAMES.items()):
            c_repr = json.dumps(c_natives, ensure_ascii=False)
            f.write(f'    "{c_k}": {c_repr},\n')
        f.write('}\n\n')

        f.write('DISPLAY_NATIVE_MAP = {\n')
        for d_k, d_v in sorted(DISPLAY_NATIVE_MAP.items()):
            f.write(f'    "{d_k}": "{d_v}",\n')
        f.write('}\n\n')

        f.write('COUNTRY_BY_CODE = {c[0]: c[1] for c in WORLD_COUNTRIES}\n\n')
        f.write('COUNTRY_LOOKUP_MAP = {}\n')
        f.write('for code, fr_name, en_name in WORLD_COUNTRIES:\n')
        f.write('    COUNTRY_LOOKUP_MAP[normalize_lookup(code)] = code\n')
        f.write('    COUNTRY_LOOKUP_MAP[normalize_lookup(fr_name)] = code\n')
        f.write('    COUNTRY_LOOKUP_MAP[normalize_lookup(en_name)] = code\n')
        f.write('for code, natives in NATIVE_COUNTRY_NAMES.items():\n')
        f.write('    for nat in natives:\n')
        f.write('        COUNTRY_LOOKUP_MAP[normalize_lookup(nat)] = code\n\n')

        f.write('LANG_MAP_BY_NAME = {}\n')
        f.write('for api_key, natives in NATIVE_LANGUAGE_NAMES.items():\n')
        f.write('    for nat in natives:\n')
        f.write('        LANG_MAP_BY_NAME[normalize_lookup(nat)] = api_key\n\n')
        f.write('for api_key, fr_name, _cnt in RADIO_BROWSER_LANGUAGES:\n')
        f.write('    norm_fr = normalize_lookup(fr_name)\n')
        f.write('    norm_api = normalize_lookup(api_key)\n')
        f.write('    if norm_fr not in LANG_MAP_BY_NAME:\n')
        f.write('        LANG_MAP_BY_NAME[norm_fr] = api_key\n')
        f.write('    if norm_api not in LANG_MAP_BY_NAME:\n')
        f.write('        LANG_MAP_BY_NAME[norm_api] = api_key\n\n')

        f.write('def resolve_language_api_key(query: str) -> str:\n')
        f.write('    if not query:\n        return ""\n')
        f.write('    clean = normalize_lookup(query)\n')
        f.write('    if clean in LANG_MAP_BY_NAME:\n        return LANG_MAP_BY_NAME[clean]\n')
        f.write('    for k, v in LANG_MAP_BY_NAME.items():\n')
        f.write('        if len(k) > 2 and k.startswith(clean):\n            return v\n')
        f.write('    for k, v in LANG_MAP_BY_NAME.items():\n')
        f.write('        if len(k) > 2 and clean in k:\n            return v\n')
        f.write('    return query.strip().lower()\n\n')

        f.write('def resolve_country_code(query: str) -> str:\n')
        f.write('    if not query:\n        return ""\n')
        f.write('    clean = normalize_lookup(query)\n')
        f.write('    if clean in COUNTRY_LOOKUP_MAP:\n        return COUNTRY_LOOKUP_MAP[clean]\n')
        f.write('    for k, v in COUNTRY_LOOKUP_MAP.items():\n')
        f.write('        if len(k) > 2 and k.startswith(clean):\n            return v\n')
        f.write('    for k, v in COUNTRY_LOOKUP_MAP.items():\n')
        f.write('        if len(k) > 2 and clean in k:\n            return v\n')
        f.write('    return query.strip().upper()\n')

    print(f"✅ Succès ! Référentiel mis à jour : {out_file}\n")

if __name__ == '__main__':
    update_data()
