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
2. Extrait les traductions officielles ISO 3166-1 des 249 pays dans les 55 langues
   supportées par TiMonde afin de permettre la recherche d'un pays dans n'importe
   laquelle des 55 langues (sur les bouquets DAB+ comme sur Radio-Browser).
3. Détecte et regroupe automatiquement tous les alias linguistiques renvoyés
   par Radio-Browser (anglais + orthographes alternatives saisies sur Radio-Browser).
4. Régénère data/scripts/timonde_world_data.py pour les futurs paquets .deb et .rpm.
"""

import os
import sys
import re
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

USER_AGENT = "TiMonde-Maintainer/0.2.0"
MIN_DAYS_INTERVAL = 10.0

# Les 55 langues de TiMonde (+ variantes régionales ISO pour gettext système)
TIMONDE_55_LOCALES = [
    "am", "ar", "az", "bg", "bn", "bs", "ca", "cs", "da", "de",
    "el", "es", "et", "fi", "fr", "he", "hr", "hu", "hy", "id",
    "is", "it", "ja", "ka", "kk", "km", "ko", "ky", "lo", "lt",
    "lv", "mk", "mn", "ms", "my", "nb", "nb_NO", "no", "ne", "nl",
    "pl", "pt", "pt_BR", "ro", "ru", "si", "sk", "sl", "sq", "sr",
    "sv", "tg", "th", "tr", "uk", "uz", "vi", "zh_CN", "zh_TW", "zh_HK",
]

# Racines pivots pour lier dynamiquement les alias saisis sur Radio-Browser aux clés canoniques anglaises
CANONICAL_ROOTS = {
    "english": ["english", "engilsh", "englsih", "englsh", "englisg", "английск"],
    "german": ["deutsch", "german", "allemand", "deutch", "gernan"],
    "spanish": ["span", "españ", "espan", "castell"],
    "french": ["french", "franç", "franc"],
    "portuguese": ["portug", "portog", "pt-br"],
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
    "ukrainian": ["ukrain", "ukran", "украин", "україн"],
    "dutch": ["dutch", "nederland", "néerland", "holland", "flemish", "flammish"],
    "italian": ["ital"],
    "polish": ["polish", "polski", "polon"],
    "swedish": ["swed", "svensk", "suéd"],
    "danish": ["dan", "dansk"],
    "finnish": ["finn", "suomi", "finnois"],
    "czech": ["czech", "cesk", "česk", "češt", "tchèq"],
    "hungarian": ["hungar", "magyar", "hongr"],
    "croatian": ["croat", "hrvat"],
    "serbian": ["serb", "срб", "срп"],
    "bulgarian": ["bulgar", "българ"],
    "persian": ["pers", "farsi", "فارس"],
    "urdu": ["urdu", "ourd", "اردو"],
    "turkish": ["turk", "türk"],
    "vietnamese": ["viet", "viêt"],
    "indonesian": ["indones", "bahasa indonesia"],
    "catalan": ["català", "catala", "catalán"],
    "basque": ["euskara", "euskera"],
    "galician": ["galego"],
    "irish": ["gaeilge"],
    "welsh": ["cymraeg"],
    "breton": ["brezhoneg"],
    "corsican": ["corsu"],
}

# Endonymes et orthographes alternatives réellement utilisés comme tags sur Radio-Browser
BASE_NATIVE_ALIASES = {
    "english": ["american english", "english uk", "engilsh", "british english", "#english", "engilsh uk", "englsih", "englsh", "englisg", "английский"],
    "german": ["deutsch", "deutsch fränkisch", "swiss german", "deutch", "low german", "gernan", "norddeutsch", "schweizerdeutsch"],
    "spanish": ["español", "castellano", "español mexico", "castellano. español", "español argentina", "español internacional", "español - latinoamerica", "espanish", "espaňol"],
    "french": ["français", "francais", "francaise", "franch", "frances", "französich", "canadian french"],
    "portuguese": ["português", "portugues", "brazilian portuguese", "português  brasil", "português (brasil)", "portugues do brasil", "pt-br", "português (br)", "portugues do braasil", "portoguese"],
    "romanian": ["română", "romana", "romania", "românä", "româna"],
    "danish": ["dansk"],
    "italian": ["italiano"],
    "dutch": ["nederlands", "nederland", "flemish", "flammish"],
    "polish": ["polski"],
    "swedish": ["svenska"],
    "finnish": ["suomi"],
    "czech": ["čeština", "cesky", "česky"],
    "croatian": ["hrvatski", "croatia"],
    "hungarian": ["magyar"],
    "catalan": ["català", "catala", "catalán"],
    "basque": ["euskara", "euskera"],
    "galician": ["galego"],
    "irish": ["gaeilge"],
    "welsh": ["cymraeg"],
    "breton": ["brezhoneg"],
    "corsican": ["corsu"],
    "russian": ["русский", "язык: русский", "русский язык", "ру", "рус", "rus"],
    "arabic": ["العربية", "عربي", "عربية", "عرب", "moroccan arabic"],
    "hindi": ["हिन्दी", "हिंदी", "english hindi", "hindu"],
    "thai": ["ไทย", "ภาษาไทย"],
    "chinese": ["中文", "汉语", "漢語", "普通话", "国语", "國語", "cantonese", "mandarin"],
    "japanese": ["日本語", "にほんご"],
    "greek": ["ελληνικά", "ελληνική", "ελ", "ancient greek"],
    "hebrew": ["עברית"],
    "korean": ["한국어", "조선말"],
    "ukrainian": ["українська", "ukranian", "українська мова", "укр", "украина"],
    "bengali": ["বাংলা", "bangla"],
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
    "bulgarian": ["български", "bulgaria"],
    "macedonian": ["македонски"],
    "belarusian": ["беларуская"],
    "kazakh": ["қазақша", "қазақ тілі"],
    "mongolian": ["монгол хэл"],
    "tatar": ["татарча"],
    "tajik": ["тоҷикӣ"],
    "pashto": ["پښتو"],
    "kurdish": ["کوردی", "kurdî", "kurdi"],
    "turkish": ["turkçe", "türkisch", "türkish", "turkmen"],
    "yiddish": ["ייִדיש"],
}

# Alias courts et endonymes additionnels garantis par code pays ISO
EXTRA_COUNTRY_ALIASES = {
    "AE": ["الإمارات", "UAE", "Émirats", "Emirats"],
    "AT": ["Österreich", "Autriche", "Oostenrijk"],
    "BE": ["Belgique", "België", "Belgien", "Belgium"],
    "BG": ["България", "Bulgarie", "Bulgaria"],
    "BO": ["Bolivia", "Bolivie"],
    "BR": ["Brasil", "Brésil", "Brazil"],
    "BY": ["Беларусь", "Biélorussie", "Bielorussie", "Belarus"],
    "CA": ["Canada", "Kanada", "カナダ", "加拿大", "캐나다"],
    "CD": ["RD Congo", "RDC", "Congo-Kinshasa", "DR Congo"],
    "CG": ["Congo", "Congo-Brazzaville"],
    "CH": ["Suisse", "Schweiz", "Svizzera", "Svizra", "Switzerland", "スイス", "瑞士", "스위스"],
    "CI": ["Côte d'Ivoire", "Cote d'Ivoire", "Ivory Coast"],
    "CN": ["中国", "中國", "Chine", "China", "Zhongguo", "중국", "中国"],
    "CZ": ["Česko", "Česká republika", "Tchéquie", "République tchèque", "Czech Republic", "Czechia", "Tschechien"],
    "DE": ["Deutschland", "Allemagne", "Germany", "Alemania", "Germania", "Duitsland", "Niemcy", "ドイツ", "德国", "德國", "독일"],
    "DK": ["Danmark", "Danemark", "Denmark", "Dänemark"],
    "DO": ["Rép. Dominicaine", "République dominicaine", "Dominican Republic", "República Dominicana"],
    "DZ": ["الجزائر", "Algérie", "Algerie", "Algeria", "Algerien"],
    "EG": ["مصر", "Égypte", "Egypte", "Egypt", "Ägypten", "Egipto"],
    "ES": ["España", "Espana", "Espagne", "Spain", "Spanien", "Spagna", "スペイン", "西班牙", "스페인"],
    "FI": ["Suomi", "Finlande", "Finland", "Finnland"],
    "FR": ["France", "Frankreich", "Francia", "França", "Frankrijk", "フランス", "法国", "法國", "프랑스"],
    "GB": ["Royaume-Uni", "United Kingdom", "UK", "Great Britain", "Grande-Bretagne", "Angleterre", "England", "Scotland", "Écosse", "Wales", "Pays de Galles", "Großbritannien", "Reino Unido", "Regno Unito", "イギリス", "英国", "英國", "영국"],
    "GR": ["Ελλάδα", "Ελλάς", "Grèce", "Grece", "Greece", "Griechenland", "Grecia", "Hellas", "Ellada"],
    "HR": ["Hrvatska", "Croatie", "Croatia", "Kroatien"],
    "HU": ["Magyarország", "Hongrie", "Hungary", "Ungarn"],
    "IE": ["Éire", "Eire", "Irlande", "Ireland", "Irland", "Irlanda"],
    "IL": ["ישראל", "Israël", "Israel"],
    "IN": ["भारत", "Inde", "India", "Indien", "Bharat", "インド", "印度", "인도"],
    "IQ": ["العراق", "Irak", "Iraq"],
    "IR": ["ایران", "Iran"],
    "IS": ["Ísland", "Islande", "Iceland", "Island"],
    "IT": ["Italia", "Italie", "Italy", "Italien", "イタリア", "意大利", "이탈리아"],
    "JP": ["日本", "Japon", "Japan", "Giappone", "Japón", "Nihon", "Nippon", "일본"],
    "KP": ["Corée du Nord", "North Korea", "Nordkorea", "Corea del Norte", "조선", "北朝鮮", "북한"],
    "KR": ["한국", "대한민국", "Corée du Sud", "South Korea", "Südkorea", "Corea del Sur", "Corea", "Hanguk", "韓国", "韩国", "韓國"],
    "LA": ["Laos", "ລາວ"],
    "LB": ["لبنان", "Liban", "Lebanon", "Libanon"],
    "MA": ["المغرب", "Maroc", "Morocco", "Marokko", "Marruecos"],
    "MD": ["Moldova", "Moldavie"],
    "MX": ["México", "Mexico", "Mexique", "Mexiko"],
    "NL": ["Nederland", "Pays-Bas", "Netherlands", "Holland", "Hollande", "Niederlande", "Países Bajos", "Paesi Bassi"],
    "NO": ["Norge", "Noreg", "Norvège", "Norway", "Norwegen", "Noruega"],
    "PL": ["Polska", "Pologne", "Poland", "Polen", "Polonia"],
    "PS": ["فلسطين", "Palestine", "Palästina", "Palestina"],
    "PT": ["Portugal", "Portogallo"],
    "RO": ["România", "Romania", "Roumanie", "Rumänien"],
    "RS": ["Србија", "Srbija", "Serbie", "Serbia", "Serbien"],
    "RU": ["Россия", "РФ", "Russie", "Russia", "Russland", "Rusia", "Rossiya", "ロシア", "俄罗斯", "俄羅斯", "러시아"],
    "SA": ["السعودية", "المملكة العربية السعودية", "Arabie saoudite", "Saudi Arabia", "Saudi-Arabien"],
    "SE": ["Sverige", "Suède", "Suede", "Sweden", "Schweden", "Suecia"],
    "SY": ["سوريا", "Syrie", "Syria", "Syrien", "Siria"],
    "TH": ["ไทย", "ประเทศไทย", "Thaïlande", "Thailande", "Thailand", "Tailandia", "タイ", "泰国", "泰國", "태국"],
    "TN": ["تونس", "Tunisie", "Tunisia", "Tunesien", "Túnez"],
    "TR": ["Türkiye", "Turkiye", "Turquie", "Turkey", "Türkei", "Turchia", "Turquía"],
    "TW": ["台湾", "臺灣", "Taïwan", "Taiwan", "대만"],
    "TZ": ["Tanzania", "Tanzanie"],
    "UA": ["Україна", "Ukraine", "Ucrania", "Ucraina"],
    "UK": ["Royaume-Uni", "United Kingdom", "UK", "Great Britain", "Grande-Bretagne", "Angleterre", "England"],
    "US": ["États-Unis", "Etats-Unis", "United States", "United States of America", "USA", "U.S.A.", "Amérique", "Vereinigte Staaten", "Estados Unidos", "Stati Uniti", "アメリカ", "アメリカ合衆国", "米国", "美国", "美國", "미국"],
    "VA": ["Vatican", "Vaticano", "Vatikan"],
    "VE": ["Venezuela", "Vénézuela"],
    "VN": ["Việt Nam", "Viêt Nam", "Vietnam"],
    "ZA": ["Afrique du Sud", "South Africa", "Südafrika", "Sudáfrica", "Sudafrica", "Zuid-Afrika"],
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
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()


def extract_multilingual_countries():
    """Extrait les 249 pays ISO 3166-1 et leurs noms traduits dans les 55 langues."""
    t_fr = gettext.translation("iso_3166-1", languages=["fr"], fallback=True)
    countries_dict = {}
    multilingual_aliases = {}

    iso_path = "/usr/share/iso-codes/json/iso_3166-1.json"
    iso_items = []
    if os.path.exists(iso_path):
        with open(iso_path, "r", encoding="utf-8") as f:
            iso_items = json.load(f).get("3166-1", [])

    # Charger les traducteurs gettext pour les 55 langues de TiMonde
    translators = []
    for lang in TIMONDE_55_LOCALES:
        for loc_dir in ("/usr/share/locale", "/usr/share/locale-langpack"):
            try:
                t = gettext.translation("iso_3166-1", localedir=loc_dir, languages=[lang])
                translators.append(t)
                break
            except Exception:
                pass

    for item in iso_items:
        code = item.get("alpha_2", "").upper()
        if not code:
            continue
        name_en = item.get("name", "")
        common_en = item.get("common_name", name_en)
        official_en = item.get("official_name", "")
        name_fr = t_fr.gettext(common_en)
        if name_fr == common_en:
            name_fr = t_fr.gettext(name_en)
        countries_dict[code] = (name_fr, common_en or name_en)

        aliases = []
        seen_norm = set()

        def add_alias(val):
            if not val:
                return
            v = val.strip()
            norm = strip_accents(v)
            if v and norm not in seen_norm:
                seen_norm.add(norm)
                aliases.append(v)

        # 1. Noms prioritaires (FR, EN commun, EN standard, EN officiel, extras)
        add_alias(name_fr)
        add_alias(common_en)
        add_alias(name_en)
        if official_en:
            add_alias(official_en)
            add_alias(t_fr.gettext(official_en))
        for ex in EXTRA_COUNTRY_ALIASES.get(code, []):
            add_alias(ex)

        # 2. Traductions dans les 55 langues
        for t in translators:
            if common_en:
                add_alias(t.gettext(common_en))
            if name_en:
                add_alias(t.gettext(name_en))
            if official_en:
                add_alias(t.gettext(official_en))

        multilingual_aliases[code] = aliases

    sorted_countries = sorted(countries_dict.items(), key=lambda x: strip_accents(x[1][0]))
    return sorted_countries, multilingual_aliases


def update_data():
    out_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "timonde_world_data.py"))
    force_update = "--force" in sys.argv or "-f" in sys.argv

    if not force_update and os.path.exists(out_file):
        age_days = (time.time() - os.path.getmtime(out_file)) / 86400.0
        if age_days < MIN_DAYS_INTERVAL:
            print(f"ℹ️  Dernière actualisation il y a {age_days:.1f} jour(s) (< {MIN_DAYS_INTERVAL} jours).")
            print("   Mise à jour en ligne ignorée par frugalité réseau.")
            print("   Utilisez 'python3 update_world_data.py --force' pour forcer l'actualisation.\n")
            return

    print("=== Démarrage de la mise à jour des pays (55 langues), langues et alias ===")

    # 1. Pays ISO 3166-1 dans les 55 langues
    print("1. Extraction des pays ISO 3166-1 dans les 55 langues...")
    sorted_countries, multilingual_country_aliases = extract_multilingual_countries()
    total_c_aliases = sum(len(v) for v in multilingual_country_aliases.values())
    print(f"   -> {len(sorted_countries)} pays indexés ({total_c_aliases} noms multilingues sur 55 langues).")

    # 2. Interrogation Radio-Browser (avec repli sur le catalogue existant si hors-ligne)
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

    dynamic_aliases = {k: list(v) for k, v in BASE_NATIVE_ALIASES.items()}
    sorted_langs = []

    if raw_langs:
        for item in raw_langs:
            raw_name = (item.get("name") or "").strip()
            cnt = item.get("stationcount", 0)
            if cnt < 2 or len(raw_name) < 2 or "http" in raw_name.lower() or any(c in raw_name for c in "{}[]<>"):
                continue
            low = raw_name.lower()
            norm = strip_accents(low)

            for canon, roots in CANONICAL_ROOTS.items():
                if any(r in norm or r in low for r in roots):
                    if low != canon and low not in dynamic_aliases.setdefault(canon, []):
                        dynamic_aliases[canon].append(low)

        t_lang = gettext.translation("iso_639-2", fallback=True)
        iso639_path = "/usr/share/iso-codes/json/iso_639-2.json"
        lang_map = {}
        if os.path.exists(iso639_path):
            with open(iso639_path, "r", encoding="utf-8") as f:
                for entry in json.load(f).get("639-2", []):
                    en = entry.get("name")
                    if en:
                        fr = t_lang.gettext(en).split(";")[0].strip()
                        lang_map[en.split(";")[0].strip().lower()] = fr

        manual = {
            "french": "Français", "english": "Anglais", "spanish": "Espagnol",
            "german": "Allemand", "italian": "Italien", "portuguese": "Portugais",
            "russian": "Russe", "arabic": "Arabe", "chinese": "Chinois",
            "hindi": "Hindi", "thai": "Thaï", "japanese": "Japonais",
            "dutch": "Néerlandais", "polish": "Polonais", "turkish": "Turc",
            "greek": "Grec", "swedish": "Suédois", "korean": "Coréen",
            "indonesian": "Indonésien", "vietnamese": "Vietnamien",
            "ukrainian": "Ukrainien", "romanian": "Roumain", "czech": "Tchèque",
            "hungarian": "Hongrois", "danish": "Danois", "finnish": "Finnois",
            "norwegian": "Norvégien", "hebrew": "Hébreu", "tamil": "Tamoul",
            "bengali": "Bengali", "punjabi": "Pendjabi", "urdu": "Ourdou",
            "persian": "Persan (Farsi)", "swahili": "Swahili", "catalan": "Catalan",
            "croatian": "Croate", "serbian": "Serbe", "bulgarian": "Bulgare",
            "slovak": "Slovaque", "bosnian": "Bosnien", "filipino": "Philippin (Tagalog)",
            "nepali": "Népalais", "albanian": "Albanais", "macedonian": "Macédonien",
            "slovenian": "Slovène", "lithuanian": "Lituanien", "latvian": "Letton",
            "estonian": "Estonien", "icelandic": "Islandais", "irish": "Irlandais (Gaélique)",
            "welsh": "Gallois", "basque": "Basque", "galician": "Galicien",
            "breton": "Breton", "corsican": "Corse", "occitan": "Occitan",
            "armenian": "Arménien", "georgian": "Géorgien", "azerbaijani": "Azerbaïdjanais",
            "kazakh": "Kazakh", "uzbek": "Ouzbek", "mongolian": "Mongol",
            "tibetan": "Tibétain", "burmese": "Birman", "khmer": "Khmer",
            "lao": "Lao", "malay": "Malais", "telugu": "Télougou",
            "marathi": "Marathe", "gujarati": "Gujarati", "kannada": "Kannada",
            "malayalam": "Malayalam", "sinhala": "Cinghalais", "amharic": "Amharique",
            "somali": "Somali", "yoruba": "Yoruba", "hausa": "Haoussa",
            "zulu": "Zoulou", "afrikaans": "Afrikaans", "creole": "Créole",
            "haitian creole": "Créole haïtien", "esperanto": "Espéranto",
            "latin": "Latin", "kurdish": "Kurde", "pashto": "Pachto",
        }

        clean_langs = []
        seen = set()
        for item in raw_langs:
            raw_name = (item.get("name") or "").strip()
            cnt = item.get("stationcount", 0)
            low = raw_name.lower().rstrip(".,;:")
            if low in seen or cnt < 3 or len(low) < 2:
                continue
            if any(k in low for k in ["test", "unknown", "various", "none", "n/a", "http", "fm", "radio", "stereo", "64k", "128k", "aac", "mp3", "station"]):
                continue
            seen.add(low)
            fr_name = manual.get(low) or lang_map.get(low) or manual.get(low.split()[0]) or lang_map.get(low.split()[0]) or raw_name.capitalize()
            clean_langs.append((low, fr_name, cnt))

        sorted_langs = sorted(clean_langs, key=lambda x: strip_accents(x[1]))
    else:
        print("   -> Mode hors-ligne : conservation des langues et alias Radio-Browser existants.")
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
        import timonde_world_data as existing_twd
        sorted_langs = list(existing_twd.RADIO_BROWSER_LANGUAGES)
        for k, v in existing_twd.NATIVE_LANGUAGE_NAMES.items():
            cur = dynamic_aliases.setdefault(k, [])
            for alias in v:
                if alias not in cur:
                    cur.append(alias)

    print(f"   -> {len(sorted_langs)} entrées Radio-Browser et {sum(len(v) for v in dynamic_aliases.values())} alias linguistiques actifs.")

    # 3. Écriture du fichier final autonome
    print("3. Écriture de timonde_world_data.py...")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("# -*- coding: utf-8 -*-\n")
        f.write('"""\nTiMonde — Référentiel Statique Hors-Ligne des Pays (55 langues), Langues et Multi-Alias\n')
        f.write("Généré automatiquement par tools/update_world_data.py.\n")
        f.write(f'Horodatage : {time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())}\n"""\n\n')
        f.write("import unicodedata\nimport re\nimport gettext\n\n")
        f.write("def normalize_lookup(text: str) -> str:\n")
        f.write("    if not text:\n        return \"\"\n")
        f.write("    nfkd = unicodedata.normalize(\"NFD\", text.strip())\n")
        f.write("    return \"\".join(c for c in nfkd if unicodedata.category(c) != \"Mn\").lower()\n\n")

        f.write("WORLD_COUNTRIES = [\n")
        for code, (fr, en) in sorted_countries:
            fr_esc = fr.replace('"', '\\"')
            en_esc = en.replace('"', '\\"')
            f.write(f'    ("{code}", "{fr_esc}", "{en_esc}"),\n')
        f.write("]\n\n")

        f.write("RADIO_BROWSER_LANGUAGES = [\n")
        for api_key, fr, cnt in sorted_langs:
            api_esc = api_key.replace('"', '\\"')
            fr_esc = fr.replace('"', '\\"')
            f.write(f'    ("{api_esc}", "{fr_esc}", {cnt}),\n')
        f.write("]\n\n")

        f.write("NATIVE_LANGUAGE_NAMES = {\n")
        for canon_k, alias_list in sorted(dynamic_aliases.items()):
            aliases_repr = json.dumps(alias_list, ensure_ascii=False)
            f.write(f'    "{canon_k}": {aliases_repr},\n')
        f.write("}\n\n")

        f.write("NATIVE_COUNTRY_NAMES = {\n")
        for c_k, c_natives in sorted(multilingual_country_aliases.items()):
            c_repr = json.dumps(c_natives, ensure_ascii=False)
            f.write(f'    "{c_k}": {c_repr},\n')
        f.write("}\n\n")

        f.write("DISPLAY_NATIVE_MAP = {\n")
        for d_k, d_v in sorted(DISPLAY_NATIVE_MAP.items()):
            f.write(f'    "{d_k}": "{d_v}",\n')
        f.write("}\n\n")

        f.write("""COUNTRY_BY_CODE = {c[0]: c[1] for c in WORLD_COUNTRIES}
COUNTRY_BY_CODE["UK"] = COUNTRY_BY_CODE.get("GB", "Royaume-Uni")
COUNTRY_EN_BY_CODE = {c[0]: c[2] for c in WORLD_COUNTRIES}
COUNTRY_EN_BY_CODE["UK"] = COUNTRY_EN_BY_CODE.get("GB", "United Kingdom")
if "GB" in NATIVE_COUNTRY_NAMES and "UK" not in NATIVE_COUNTRY_NAMES:
    NATIVE_COUNTRY_NAMES["UK"] = NATIVE_COUNTRY_NAMES["GB"]

def get_localized_country_name(code: str) -> str:
    \"\"\"Retourne le nom du pays traduit dans la langue système courante (ou français par défaut).\"\"\"
    c_up = (code or "").strip().upper()
    if c_up == "UK":
        c_up = "GB"
    en_name = COUNTRY_EN_BY_CODE.get(c_up)
    fr_name = COUNTRY_BY_CODE.get(c_up, c_up)
    if not en_name:
        return fr_name
    try:
        t = gettext.translation("iso_3166-1", fallback=True)
        loc = t.gettext(en_name)
        if loc and loc != en_name:
            return loc
    except Exception:
        pass
    return fr_name

_MINOR_TERRITORIES = {
    "UM", "VI", "VG", "IO", "TF", "BQ", "HM", "BV", "GS", "AQ",
    "AS", "GU", "MP", "CC", "CX", "NF", "SH", "PM", "WF", "BL",
    "MF", "SX", "SJ", "AX",
}

COUNTRY_LOOKUP_MAP = {}
for code, fr_name, en_name in WORLD_COUNTRIES:
    if code not in _MINOR_TERRITORIES:
        COUNTRY_LOOKUP_MAP[normalize_lookup(en_name)] = code
        COUNTRY_LOOKUP_MAP[normalize_lookup(fr_name)] = code
    COUNTRY_LOOKUP_MAP[normalize_lookup(code)] = code
COUNTRY_LOOKUP_MAP["uk"] = "GB"

# 1. Pays souverains en priorité
for code, natives in NATIVE_COUNTRY_NAMES.items():
    if code == "UK" or code in _MINOR_TERRITORIES:
        continue
    for nat in natives:
        norm_n = normalize_lookup(nat)
        if norm_n and norm_n not in COUNTRY_LOOKUP_MAP:
            COUNTRY_LOOKUP_MAP[norm_n] = code

# 2. Territoires secondaires ensuite
for code, natives in NATIVE_COUNTRY_NAMES.items():
    if code not in _MINOR_TERRITORIES:
        continue
    for nat in natives:
        norm_n = normalize_lookup(nat)
        if norm_n and norm_n not in COUNTRY_LOOKUP_MAP:
            COUNTRY_LOOKUP_MAP[norm_n] = code

# Liste triée par longueur croissante pour privilégier les noms courts lors des recherches par préfixe
_SORTED_COUNTRY_LOOKUP = sorted(
    [(k, v) for k, v in COUNTRY_LOOKUP_MAP.items() if len(k) >= 2],
    key=lambda x: (x[1] in _MINOR_TERRITORIES, len(x[0]))
)

_VALID_RB_API_KEYS = {api_k.lower() for api_k, _fr, _cnt in RADIO_BROWSER_LANGUAGES}

LANG_MAP_BY_NAME = {}
for api_key, natives in NATIVE_LANGUAGE_NAMES.items():
    LANG_MAP_BY_NAME[normalize_lookup(api_key)] = api_key
    for nat in natives:
        LANG_MAP_BY_NAME[normalize_lookup(nat)] = api_key

for api_key, fr_name, _cnt in RADIO_BROWSER_LANGUAGES:
    norm_fr = normalize_lookup(fr_name)
    norm_api = normalize_lookup(api_key)
    if norm_fr not in LANG_MAP_BY_NAME:
        LANG_MAP_BY_NAME[norm_fr] = api_key
    if norm_api not in LANG_MAP_BY_NAME:
        LANG_MAP_BY_NAME[norm_api] = api_key

def resolve_language_api_key(query: str) -> str:
    if not query:
        return ""
    q_str = query.strip()

    # 0. Si le format contient des parenthèses avec la clé API (ex: "Hindi — हिन्दी (hindi)" ou "American english (american english)")
    m = re.search(r'\\(([^)]+)\\)$', q_str)
    if m:
        cand = m.group(1).strip().lower()
        if cand in _VALID_RB_API_KEYS or cand in LANG_MAP_BY_NAME.values():
            return cand
        clean_cand = normalize_lookup(cand)
        if clean_cand in LANG_MAP_BY_NAME:
            return LANG_MAP_BY_NAME[clean_cand]

    # 1. Correspondance exacte sur la chaîne normalisée
    clean = normalize_lookup(q_str)
    if clean in LANG_MAP_BY_NAME:
        return LANG_MAP_BY_NAME[clean]

    # 2. Découpage par segments si la chaîne contient un tiret cadratin ou tiret standard (ex: "Hindi — हिन्दी")
    for part in re.split(r'[\\s—\\-\\(\\)]+', q_str):
        clean_p = normalize_lookup(part)
        if clean_p and clean_p in LANG_MAP_BY_NAME:
            return LANG_MAP_BY_NAME[clean_p]

    # 3. Préfixe sur le nom de langue (ex: 'deuts' -> 'german')
    for k, v in LANG_MAP_BY_NAME.items():
        if len(k) > 2 and k.startswith(clean):
            return v
    # 4. Sous-chaîne dans le nom de langue
    for k, v in LANG_MAP_BY_NAME.items():
        if len(k) > 2 and clean in k:
            return v
    return q_str.lower()


def resolve_country_code(query: str) -> str:
    \"\"\"Résout une saisie libre (code ISO ou nom dans l'une des 55 langues) en code ISO 3166-1 alpha-2.\"\"\"
    if not query:
        return ""
    q_str = query.strip()

    # 0. Si le format contient un code ISO entre crochets ou parenthèses (ex: "Allemagne  [DE]" ou "[DE] Allemagne")
    m = re.search(r'[\\[\\(]([A-Za-z]{2})[\\]\\)]', q_str)
    if m:
        cand = m.group(1).upper()
        if cand == "UK":
            return "GB"
        if cand in COUNTRY_BY_CODE:
            return cand

    clean = normalize_lookup(q_str)
    if not clean:
        return ""

    # 1. Correspondance exacte dans le registre (codes ISO + noms complets dans les 55 langues)
    if clean in COUNTRY_LOOKUP_MAP:
        return COUNTRY_LOOKUP_MAP[clean]

    # 2. Préfixe sur nom de pays (uniquement à partir de 2 caractères, du nom le plus court au plus long)
    if len(clean) >= 2:
        for k, v in _SORTED_COUNTRY_LOOKUP:
            if len(k) > 2 and k.startswith(clean):
                return v

    # 3. Sous-chaîne dans le nom complet (uniquement à partir de 3 caractères)
    if len(clean) >= 3:
        for k, v in _SORTED_COUNTRY_LOOKUP:
            if len(k) > 2 and clean in k:
                return v

    return q_str.upper()
""")

    print(f"✅ Succès ! Référentiel mis à jour : {out_file}\n")


if __name__ == "__main__":
    update_data()
