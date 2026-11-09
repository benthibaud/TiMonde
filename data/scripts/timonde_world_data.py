# -*- coding: utf-8 -*-
"""
TiMonde — Référentiel Frugal des Langues Radio-Browser (Allégé & Unifié)
Délègue l'intégralité du référentiel pays et l'inférence temporelle au moteur natif Rust (Option B pure).
"""

import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from timonde_common import (
    normalize_lookup,
    resolve_country_code,
    COUNTRIES_REGISTRY,
    COUNTRY_ALIASES_MAP,
)

class _LazyDict(dict):
    """Dictionnaire à initialisation paresseuse pour éviter toute latence au démarrage."""
    def __init__(self, builder):
        super().__init__()
        self._builder = builder
        self._loaded = False

    def _ensure(self):
        if not self._loaded:
            self._loaded = True
            self._builder(self)

    def __getitem__(self, key):
        self._ensure()
        return super().__getitem__(key)

    def __contains__(self, key):
        self._ensure()
        return super().__contains__(key)

    def get(self, key, default=None):
        self._ensure()
        return super().get(key, default)

    def items(self):
        self._ensure()
        return super().items()

    def values(self):
        self._ensure()
        return super().values()

    def keys(self):
        self._ensure()
        return super().keys()

# Rétrocompatibilité transparente pour les UIs
WORLD_COUNTRIES = [(c, val[0], val[0]) for c, val in COUNTRIES_REGISTRY.items()]
COUNTRY_BY_CODE = {c: val[0] for c, val in COUNTRIES_REGISTRY.items()}
COUNTRY_LOOKUP_MAP = COUNTRY_ALIASES_MAP
NATIVE_COUNTRY_NAMES = {c: val[2] if len(val) > 2 else [] for c, val in COUNTRIES_REGISTRY.items()}

RADIO_BROWSER_LANGUAGES = [
    ("#english", "#english", 3),
    ("#spanish", "#spanish", 10),
    ("128 brazilian portuguese", "128 brazilian portuguese", 3),
    ("80s", "80s", 3),
    ("aboriginal languages", "Aboriginal languages", 3),
    ("africa", "Africa", 4),
    ("afrikaans", "Afrikaans", 34),
    ("akan", "Akan", 66),
    ("albanian", "Albanais", 86),
    ("german", "Allemand", 4575),
    ("american english", "American english", 533),
    ("amharic", "Amharique", 19),
    ("ancient greek", "Ancient greek", 10),
    ("english", "Anglais", 14060),
    ("english uk", "Anglais", 152),
    ("english hindi", "Anglais", 9),
    ("english spanish", "Anglais", 6),
    ("angol", "Angol", 4),
    ("ar", "Ar", 176),
    ("arabic", "Arabe", 674),
    ("arabesk", "Arabesk", 3),
    ("arapça", "Arapça", 3),
    ("armenian", "Arménien", 18),
    ("assamese", "Assamais", 5),
    ("asturian", "Asturien", 3),
    ("asunción", "Asunción", 21),
    ("australian", "Australian", 5),
    ("aymara", "Aymara", 3),
    ("azerbaijani", "Azerbaïdjanais", 45),
    ("bashkir", "Bachkir", 6),
    ("bahasa indonesia", "Bahasa indonesia", 80),
    ("bahasa jawa", "Bahasa jawa", 3),
    ("bahasa sunda", "Bahasa sunda", 3),
    ("bambara", "Bambara", 11),
    ("bangla", "Bangla", 24),
    ("low german", "Bas saxon", 22),
    ("basque", "Basque", 27),
    ("belge", "Belge", 4),
    ("bengali", "Bengali", 20),
    ("bhojpuri", "Bhojpuri", 9),
    ("belarusian", "Biélorusse", 43),
    ("burmese", "Birman", 5),
    ("bisaya", "Bisaya", 4),
    ("bosnian", "Bosnien", 108),
    ("brasil", "Brasil", 11),
    ("brazilian portuguese", "Brazilian portuguese", 491),
    ("brazillian", "Brazillian", 5),
    ("breton", "Breton", 9),
    ("british english", "British english", 97),
    ("bulgarian", "Bulgare", 210),
    ("bulgaria", "Bulgaria", 3),
    ("canada", "Canada", 3),
    ("canadian", "Canadian", 5),
    ("canadian french", "Canadian french", 8),
    ("cantonese", "Cantonese", 128),
    ("carpatho-rusyn", "Carpatho-rusyn", 5),
    ("castellano. español", "Castellano. español", 175),
    ("castilian", "Castilian", 9),
    ("catalan", "Catalan", 109),
    ("catalán", "Catalán", 3),
    ("cebuano", "Cebuano", 9),
    ("česky", "Česky", 7),
    ("chaoshan dialect", "Chaoshan dialect", 4),
    ("china", "China", 7),
    ("chinese", "Chinois", 2462),
    ("sinhala", "Cinghalais", 38),
    ("korean", "Coréen", 110),
    ("creole", "Créole", 18),
    ("haitian creole", "Créole haïtien", 19),
    ("cree", "Cri", 3),
    ("croatian", "Croate", 215),
    ("croatia", "Croatia", 7),
    ("danish", "Danois", 117),
    ("dansk/oldnordisk", "Dansk/oldnordisk", 3),
    ("deutch", "Deutch", 26),
    ("deutsch fränkisch", "Deutsch fränkisch", 93),
    ("discography", "Discography", 3),
    ("engels", "Engels", 6),
    ("engilsh", "Engilsh", 145),
    ("engilsh uk", "Engilsh uk", 17),
    ("englisg", "Englisg", 3),
    ("english/ españa/ russian /francia /italia", "English/ españa/ russian /francia /italia", 11),
    ("english/ russian /francia /españa", "English/ russian /francia /españa", 7),
    ("english/tagalog", "English/tagalog", 3),
    ("englsh", "Englsh", 3),
    ("englsih", "Englsih", 15),
    ("spanish", "Espagnol", 5766),
    ("españa", "España", 4),
    ("espanish", "Espanish", 70),
    ("espaňol", "Espaňol", 65),
    ("español - latinoamerica", "Español - latinoamerica", 118),
    ("español argentina", "Español argentina", 158),
    ("español asunción", "Español asunción", 4),
    ("español chile", "Español chile", 62),
    ("español colombia", "Español colombia", 58),
    ("español ecuador", "Español ecuador", 13),
    ("español españa", "Español españa", 7),
    ("español internacional", "Español internacional", 131),
    ("español mexico", "Español mexico", 252),
    ("español paraguay", "Español paraguay", 5),
    ("español peruano", "Español peruano", 22),
    ("esperanto", "Espéranto", 6),
    ("estonia", "Estonia", 11),
    ("estonian", "Estonien", 86),
    ("euskera", "Euskera", 7),
    ("faroese", "Féroïen", 10),
    ("fijian", "Fidjien", 4),
    ("finnish", "Finnois", 114),
    ("flammish", "Flammish", 8),
    ("flemish", "Flemish", 24),
    ("french", "Français", 3357),
    ("français - lëtzebuergesch", "Français - lëtzebuergesch", 18),
    ("francaise", "Francaise", 88),
    ("frances", "Frances", 8),
    ("franch", "Franch", 17),
    ("französich", "Französich", 3),
    ("fulani", "Fulani", 3),
    ("gaelic", "Gaélique", 9),
    ("galego", "Galego", 11),
    ("galician", "Galicien", 20),
    ("welsh", "Gallois", 6),
    ("georgian", "Géorgien", 29),
    ("ger", "Ger", 5),
    ("gernan", "Gernan", 18),
    ("global", "Global", 5),
    ("greek", "Grec", 1236),
    ("guarani", "Guarani", 3),
    ("gujarati", "Gujarati", 3),
    ("hakka", "Hakka", 8),
    ("hausa", "Haoussa", 8),
    ("hawaiian", "Hawaïen", 4),
    ("hebrew", "Hébreu", 91),
    ("hindi", "Hindi", 501),
    ("hindu", "Hindu", 3),
    ("hokkien", "Hokkien", 39),
    ("hungarian", "Hongrois", 283),
    ("ilocano", "Ilocano", 8),
    ("indian", "Indian", 8),
    ("indonesian", "Indonésien", 232),
    ("ingles español", "Ingles español", 10),
    ("inglés/portugués/español", "Inglés/portugués/español", 18),
    ("iranian", "Iranian", 3),
    ("irish", "Irlandais (Gaélique)", 17),
    ("isixhosa", "Isixhosa", 3),
    ("isizulu", "Isizulu", 6),
    ("icelandic", "Islandais", 17),
    ("italian", "Italien", 1420),
    ("japanese", "Japonais", 217),
    ("java", "Java", 3),
    ("javanese", "Javanais", 16),
    ("jawa", "Jawa", 3),
    ("kannada", "Kannada", 34),
    ("kapampangan", "Kapampangan", 17),
    ("kazakh", "Kazakh", 30),
    ("khmer", "Khmer", 10),
    ("kiswahili", "Kiswahili", 8),
    ("kölscher dialekt", "Kölscher dialekt", 3),
    ("konkani", "Konkani", 3),
    ("kurdish", "Kurde", 33),
    ("kurdi", "Kurdi", 12),
    ("kyrgyz", "Kyrgyz", 6),
    ("latin", "Latin", 15),
    ("latino", "Latino", 6),
    ("latvian", "Letton", 88),
    ("limburgs", "Limburgs", 3),
    ("lingala", "Lingala", 4),
    ("lithuanian", "Lituanien", 56),
    ("luganda", "Luganda", 79),
    ("luganda english", "Luganda english", 4),
    ("lumasaba luganda english", "Lumasaba luganda english", 5),
    ("lusoga", "Lusoga", 9),
    ("luxembourgish", "Luxembourgeois", 11),
    ("macedonian", "Macédonien", 40),
    ("malay", "Malais", 35),
    ("malayalam", "Malayalam", 115),
    ("malagasy", "Malgache", 4),
    ("maltese", "Maltais", 3),
    ("mandarin", "Mandarin", 43),
    ("maori", "Maori", 6),
    ("marathi", "Marathe", 10),
    ("mg", "Mg", 3),
    ("moldovian", "Moldovian", 12),
    ("mongolian", "Mongol", 22),
    ("montenegrin", "Monténégrin", 17),
    ("montenegro", "Montenegro", 24),
    ("moroccan arabic", "Moroccan arabic", 11),
    ("multiculti", "Multiculti", 4),
    ("nederland", "Nederland", 13),
    ("dutch", "Néerlandais", 942),
    ("nepali", "Népalais", 151),
    ("norddeutsch", "Norddeutsch", 17),
    ("norsk", "Norsk", 16),
    ("norwegian", "Norvégien", 70),
    ("chichewa", "Nyanja", 41),
    ("occitan", "Occitan", 6),
    ("odia", "Odia", 12),
    ("only music", "Only music", 3),
    ("others", "Others", 3),
    ("urdu", "Ourdou", 63),
    ("uzbek", "Ouzbek", 5),
    ("papiamentu", "Papiamentu", 7),
    ("punjabi", "Pendjabi", 78),
    ("persian", "Persan (Farsi)", 36),
    ("filipino", "Philippin (Tagalog)", 166),
    ("pigin", "Pigin", 11),
    ("polish", "Polonais", 877),
    ("pop music", "Pop music", 3),
    ("portoguese", "Portoguese", 3),
    ("portuguese", "Portugais", 871),
    ("portuguese brazil", "Portugais", 3),
    ("português  brasil", "Português  brasil", 124),
    ("português (br)", "Português (br)", 33),
    ("português (brasil)", "Português (brasil)", 119),
    ("portugues brasil", "Portugues brasil", 4),
    ("portugues do braasil", "Portugues do braasil", 20),
    ("portugues do brasil", "Portugues do brasil", 76),
    ("pt-br", "Pt-br", 60),
    ("punjab", "Punjab", 3),
    ("quechua", "Quechua", 10),
    ("rock", "Rock", 5),
    ("română", "Română", 223),
    ("românä", "Românä", 66),
    ("româna", "Româna", 10),
    ("romansh", "Romanche", 4),
    ("romani", "Romani", 6),
    ("romania", "Romania", 199),
    ("rossia", "Rossia", 3),
    ("romanian", "Roumain", 371),
    ("rus", "Rus", 21),
    ("russian", "Russe", 1886),
    ("sächsisch", "Sächsisch", 4),
    ("sami", "Sami", 5),
    ("samoan", "Samoan", 5),
    ("san salvador", "San salvador", 3),
    ("sanskrit", "Sanskrit", 11),
    ("schweizerdeutsch", "Schweizerdeutsch", 5),
    ("sepedi", "Sepedi", 6),
    ("serbian", "Serbe", 334),
    ("sesotho", "Sesotho", 4),
    ("setswana", "Setswana", 5),
    ("shona", "Shona", 3),
    ("shqip", "Shqip", 5),
    ("sindhi", "Sindhi", 4),
    ("sint maarten", "Sint maarten", 11),
    ("siswati", "Siswati", 3),
    ("slovak", "Slovaque", 132),
    ("slovenian", "Slovène", 91),
    ("slovenski", "Slovenski", 9),
    ("sorbian", "Sorbian", 7),
    ("spain", "Spain", 17),
    ("swedish", "Suédois", 162),
    ("swiss german", "Suisse allemand", 57),
    ("suomi", "Suomi", 4),
    ("swahili", "Swahili", 40),
    ("tagalog", "Tagalog", 35),
    ("tamil", "Tamoul", 332),
    ("tatar", "Tatar", 12),
    ("czech", "Tchèque", 205),
    ("te reo", "Te reo", 4),
    ("te reo maori", "Te reo maori", 4),
    ("telugu", "Télougou", 39),
    ("teochew", "Teochew", 4),
    ("thai", "Thaï", 90),
    ("tibetan", "Tibétain", 14),
    ("tonga", "Tonga", 3),
    ("tr", "Tr", 8),
    ("tshivenda", "Tshivenda", 3),
    ("tunisian", "Tunisian", 9),
    ("turkish", "Turc", 359),
    ("turkçe", "Turkçe", 40),
    ("türkisch", "Türkisch", 19),
    ("türkish", "Türkish", 5),
    ("turkmen", "Turkmène", 3),
    ("twi", "Twi", 4),
    ("ukrainian", "Ukrainien", 230),
    ("ukranian", "Ukranian", 60),
    ("urdu/punjabi/seraiki", "Urdu/punjabi/seraiki", 4),
    ("uyghur", "Uyghur", 14),
    ("vietnamese", "Vietnamien", 21),
    ("willemstad", "Willemstad", 15),
    ("xhosa", "Xhosa", 3),
    ("xitsonga", "Xitsonga", 5),
    ("yiddish", "Yiddish", 6),
    ("yoruba", "Yoruba", 11),
    ("yugoslavian", "Yugoslavian", 3),
    ("zh", "Zh", 23),
    ("английский", "Английский", 7),
    ("английский русский", "Английский русский", 4),
    ("ру", "Ру", 8),
    ("украина", "Украина", 4),
    ("язык: ру", "Язык: ру", 7),
    ("язык: русский", "Язык: русский", 130),
    ("العربية", "العربية", 17),
    ("عربي", "عربي", 10),
    ("ภาษาไทย", "ภาษาไทย", 4),
    ("国语", "国语", 4),
]

NATIVE_LANGUAGE_NAMES = {
    "amharic": ["አማርኛ"],
    "arabic": ["العربية", "عربي", "عربية", "عرب", "moroccan arabic", "arabic.", "arabesk"],
    "armenian": ["հայերեն"],
    "basque": ["euskara", "euskera"],
    "belarusian": ["беларуская"],
    "bengali": ["বাংলা", "bangla"],
    "breton": ["brezhoneg"],
    "bulgarian": ["български", "bulgaria"],
    "burmese": ["မြန်မာစာ", "ဗမာစာ"],
    "catalan": ["català", "catala", "catalán"],
    "chinese": ["中文", "汉语", "漢語", "普通话", "国语", "國語", "cantonese", "mandarin", "china"],
    "corsican": ["corsu"],
    "croatian": ["hrvatski", "croatia", "hrvatska"],
    "czech": ["čeština", "cesky", "česky"],
    "danish": ["dansk", "dansk/oldnordisk", "dan"],
    "dutch": ["nederlands", "nederland", "flemish", "flammish", "nederlandstalig", "holland"],
    "english": ["american english", "english uk", "engilsh", "british english", "#english", "engilsh uk", "englsih", "englsh", "englisg", "английский", "english/ españa/ russian /francia /italia", "english hindi", "english/ russian /francia /españa", "english spanish", "lumasaba luganda english", "английский русский", "luganda english", "english/tagalog", "pigeon english", "caribbean english", "english russian", "english/sotho/afrikaans", "english.", "english - twi"],
    "finnish": ["suomi"],
    "french": ["français", "francais", "francaise", "franch", "frances", "französich", "canadian french", "français - lëtzebuergesch", "english/ españa/ russian /francia /italia", "english/ russian /francia /españa", "portugues francês", "francia"],
    "galician": ["galego"],
    "georgian": ["ქართული"],
    "german": ["deutsch", "deutsch fränkisch", "swiss german", "deutch", "low german", "gernan", "norddeutsch", "schweizerdeutsch"],
    "greek": ["ελληνικά", "ελληνική", "ελ", "ancient greek", "greek."],
    "gujarati": ["ગુજરાતી"],
    "hebrew": ["עברית"],
    "hindi": ["हिन्दी", "हिंदी", "english hindi", "hindu", "fijian hindi"],
    "hungarian": ["magyar"],
    "indonesian": ["bahasa indonesia"],
    "irish": ["gaeilge"],
    "italian": ["italiano", "english/ españa/ russian /francia /italia"],
    "japanese": ["日本語", "にほんご", "#japan"],
    "kannada": ["ಕನ್ನಡ"],
    "kazakh": ["қазақша", "қазақ тілі"],
    "khmer": ["ភាសាខ្មែរ"],
    "korean": ["한국어", "조선말"],
    "kurdish": ["کوردی", "kurdî", "kurdi"],
    "lao": ["ພາສາລາວ"],
    "macedonian": ["македонски"],
    "malayalam": ["മലയാളം"],
    "marathi": ["मराठी"],
    "mongolian": ["монгол хэл"],
    "pashto": ["پښتو"],
    "persian": ["فارسی", "پارسی"],
    "polish": ["polski"],
    "portuguese": ["português", "portugues", "brazilian portuguese", "português  brasil", "português (brasil)", "portugues do brasil", "pt-br", "português (br)", "portugues do braasil", "portoguese", "inglés/portugués/español", "portugues brasil", "128 brazilian portuguese", "portuguese brazil", "portuguêsa", "portuguese brazillian", "portugues francês"],
    "punjabi": ["ਪੰਜਾਬੀ", "پنجابی"],
    "romanian": ["română", "romana", "romania", "românä", "româna", "romani", "romansh", "romany"],
    "russian": ["русский", "язык: русский", "русский язык", "ру", "рус", "rus", "english/ españa/ russian /francia /italia", "english/ russian /francia /españa", "английский русский", "язык: russia", "russian/yakut", "english russian"],
    "serbian": ["српски"],
    "sinhala": ["සිංහල"],
    "spanish": ["español", "castellano", "español mexico", "castellano. español", "español argentina", "español internacional", "español - latinoamerica", "espanish", "espaňol", "español chile", "español colombia", "español peruano", "inglés/portugués/español", "español ecuador", "english/ españa/ russian /francia /italia", "#spanish", "ingles español", "español españa", "english/ russian /francia /españa", "english spanish", "español paraguay", "español asunción", "españa", "spanish saba", "espana", "español uruguay", "español ingles"],
    "swedish": ["svenska"],
    "tajik": ["тоҷикӣ"],
    "tamil": ["தமிழ்"],
    "tatar": ["татарча"],
    "telugu": ["తెలుగు"],
    "thai": ["ไทย", "ภาษาไทย"],
    "tibetan": ["བོད་སྐད་"],
    "turkish": ["turkçe", "türkisch", "türkish", "turkmen"],
    "ukrainian": ["українська", "ukranian", "українська мова", "укр", "украина"],
    "urdu": ["اردو", "urdu/punjabi/seraiki"],
    "welsh": ["cymraeg"],
    "yiddish": ["ייִדיש"],
}

DISPLAY_NATIVE_MAP = {
    "amharic": "አማርኛ",
    "arabic": "العربية",
    "armenian": "հայերեն",
    "belarusian": "Беларуская",
    "bengali": "বাংলা",
    "bulgarian": "Български",
    "chinese": "中文",
    "georgian": "ქართული",
    "greek": "Ελληνικά",
    "hebrew": "עברית",
    "hindi": "हिन्दी",
    "japanese": "日本語",
    "korean": "한국어",
    "marathi": "मराठी",
    "persian": "فارسی",
    "punjabi": "ਪੰਜਾਬੀ",
    "russian": "Русский",
    "serbian": "Српски",
    "tamil": "தமிழ்",
    "telugu": "తెలుగు",
    "thai": "ไทย",
    "ukrainian": "Українська",
    "urdu": "اردو",
}


_VALID_RB_API_KEYS = None

def _get_valid_rb_api_keys():
    global _VALID_RB_API_KEYS
    if _VALID_RB_API_KEYS is None:
        _VALID_RB_API_KEYS = {api_k.lower() for api_k, _fr, _cnt in RADIO_BROWSER_LANGUAGES}
    return _VALID_RB_API_KEYS


def _build_lang_map(m):
    for api_key, natives in NATIVE_LANGUAGE_NAMES.items():
        m[normalize_lookup(api_key)] = api_key
        for nat in natives:
            m[normalize_lookup(nat)] = api_key

    for api_key, fr_name, _cnt in RADIO_BROWSER_LANGUAGES:
        norm_fr = normalize_lookup(fr_name)
        norm_api = normalize_lookup(api_key)
        if norm_fr not in m:
            m[norm_fr] = api_key
        if norm_api not in m:
            m[norm_api] = api_key


LANG_MAP_BY_NAME = _LazyDict(_build_lang_map)


def resolve_language_api_key(query: str) -> str:
    if not query:
        return ""
    q_str = query.strip()

    valid_keys = _get_valid_rb_api_keys()

    # 0. Si le format contient des parenthèses avec la clé API (ex: "Hindi — हिन्दी (hindi)")
    m = re.search(r'\(([^)]+)\)$', q_str)
    if m:
        cand = m.group(1).strip().lower()
        if cand in valid_keys or cand in LANG_MAP_BY_NAME.values():
            return cand
        clean_cand = normalize_lookup(cand)
        if clean_cand in LANG_MAP_BY_NAME:
            return LANG_MAP_BY_NAME[clean_cand]

    # 1. Correspondance exacte sur la chaîne normalisée
    clean = normalize_lookup(q_str)
    if clean in LANG_MAP_BY_NAME:
        return LANG_MAP_BY_NAME[clean]

    # 2. Découpage par segments si la chaîne contient un tiret cadratin ou tiret standard (ex: "Hindi — हिन्दी")
    for part in re.split(r'[\s—\-\(\)]+', q_str):
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
