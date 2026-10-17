# -*- coding: utf-8 -*-
"""
Module partagé et socle commun pour les utilitaires GTK/Python de TiMonde.
Fournit :
1. Neutralisation d'environnement (IBus, XMODIFIERS) pour compatibilité X11/GTK3.
2. Nettoyage et sécurisation des URLs de flux audio (clean_stream_url).
3. Lecture XML robuste et tolérante aux entités non échappées (safe_parse_xml).
4. Registre universel des pays SANS EMOJI (compatibilité absolue antiX/Live ISO).
5. Gestion et inférence des fuseaux horaires (FRANCE_TIMEZONES, CUSTOM_MULTI_TZ, WORLD_TIMEZONES).
6. Parsing et normalisation des groupes avec la convention Linux / (get_user_bookmarks_groups, normalize_group_path).
7. Fabrique de boutons GTK3 unifiée (make_btn).
"""

import sys
import os
import re
import xml.etree.ElementTree as ET
import collections

# Neutralisation inconditionnelle d'IBus et XMODIFIERS dès le chargement du module
for _var in ("GTK_IM_MODULE", "XMODIFIERS", "QT_IM_MODULE"):
    os.environ.pop(_var, None)

# Internationalisation TiMonde
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from timonde_i18n import _
except ImportError:
    def _(s): return s


# -----------------------------------------------------------------------------
# 1. Nettoyage d'URLs & Utilitaires Textuels
# -----------------------------------------------------------------------------

def clean_stream_url(url: str) -> str:
    """Nettoie préventivement une URL de flux audio (protocoles dupliqués, espaces, slashes)."""
    if not url:
        return ""
    u = url.strip()
    if u.startswith("http ://"):
        u = "http://" + u[8:]
    elif u.startswith("https ://"):
        u = "https://" + u[9:]
    elif u.startswith("//"):
        u = "https://" + u[2:]

    while True:
        if u.startswith("httpshttps://"):
            u = "https://" + u[13:]
            continue
        if u.startswith("httphttp://"):
            u = "http://" + u[11:]
            continue
        if u.startswith("http://https://"):
            u = "https://" + u[15:]
            continue
        if u.startswith("https://http://"):
            u = "http://" + u[15:]
            continue
        if u.startswith("https://https://"):
            u = "https://" + u[16:]
            continue
        if u.startswith("http://http://"):
            u = "http://" + u[14:]
            continue
        break
    return u


def strip_unsupported_emojis(text: str) -> str:
    """Retire tous les emojis et indicateurs régionaux Unicode pour compatibilité antiX/Live ISO."""
    if not text:
        return ""
    pattern = re.compile(
        "[🇦-🇿"  # Indicateurs régionaux (drapeaux)
        "🌀-🧿"  # Symboles et émojis
        "🨀-🫿"  # Symboles étendus
        "☀-➿"  # Divers symboles météo/alertes
        "]+",
        flags=re.UNICODE
    )
    cleaned = pattern.sub("", text)
    return re.sub(r"\s+", " ", cleaned).strip()


# -----------------------------------------------------------------------------
# 2. Parsing XML Tolérant & Sécurisé
# -----------------------------------------------------------------------------

def safe_parse_xml(path: str):
    """Parse un fichier XML avec tolérance absolue aux entités ampersand non échappées."""
    try:
        return ET.parse(path).getroot()
    except Exception:
        pass
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            raw = f.read()
        cleaned = re.sub(r"&(?!(?:amp|lt|gt|apos|quot|#\d+|#x[0-9a-fA-F]+);)", "&amp;", raw)
        return ET.fromstring(cleaned)
    except Exception as e:
        sys.stderr.write(f"Échec de lecture XML ({path}) : {e}\n")
        return None


# -----------------------------------------------------------------------------
# 3. Convention Linux pour les Groupes & Chemins (Arborescence '/')
# -----------------------------------------------------------------------------

def normalize_group_path(raw_path: str, return_root_literal: bool = False) -> str:
    """
    Normalise une chaîne de groupe selon la convention Linux avec slashes.
    """
    if not raw_path:
        return "root" if return_root_literal else ""
    s = raw_path.strip()
    if s in ("[ / ] (Racine — Sans groupe)", "/", "root", "(Racine)", "[/]"):
        return "root" if return_root_literal else ""
    cleaned = s.strip("/").strip()
    if not cleaned:
        return "root" if return_root_literal else ""
    return cleaned


def get_user_bookmarks_groups():
    """Lit les groupes et sous-groupes existants depuis bookmarks.xml de l'utilisateur."""
    candidates = [
        os.path.expanduser("~/.config/timonde/bookmarks.xml"),
        os.path.expanduser("~/.local/share/timonde/bookmarks.xml"),
        os.path.expanduser("~/.config/radiotray-ng/bookmarks.xml"),
        "bookmarks.xml",
    ]
    groups = []
    for path in candidates:
        if os.path.exists(path):
            root = safe_parse_xml(path)
            if root is not None:
                def walk_groups(el, prefix):
                    for g in el.findall("group"):
                        g_title = g.attrib.get("title", "").strip() or g.attrib.get("name", "").strip()
                        if g_title:
                            full = f"{prefix}/{g_title}" if prefix else g_title
                            if full not in groups:
                                groups.append(full)
                            walk_groups(g, full)
                walk_groups(root, "")
                break
    return groups


# -----------------------------------------------------------------------------
# 4. Registre des Pays SANS EMOJI & Fuseaux Horaires (antiX-safe)
# -----------------------------------------------------------------------------

COUNTRIES_DB = [
    ("FR", "France", ""),
    ("GP", "Guadeloupe", ""),
    ("MQ", "Martinique", ""),
    ("GF", "Guyane", ""),
    ("RE", "La Réunion", ""),
    ("YT", "Mayotte", ""),
    ("NC", "Nouvelle-Calédonie", ""),
    ("PF", "Polynésie française", ""),
    ("PM", "Saint-Pierre-et-Miquelon", ""),
    ("BL", "Saint-Barthélemy", ""),
    ("MF", "Saint-Martin", ""),
    ("WF", "Wallis-et-Futuna", ""),
    ("BE", "Belgique", ""),
    ("CH", "Suisse", ""),
    ("CA", "Canada", ""),
    ("US", "États-Unis", ""),
    ("GB", "Royaume-Uni", ""),
    ("DE", "Allemagne", ""),
    ("IT", "Italie", ""),
    ("ES", "Espagne", ""),
    ("PT", "Portugal", ""),
    ("NL", "Pays-Bas", ""),
    ("SN", "Sénégal", ""),
    ("CI", "Côte d'Ivoire", ""),
    ("MA", "Maroc", ""),
    ("DZ", "Algérie", ""),
    ("TN", "Tunisie", ""),
    ("ML", "Mali", ""),
    ("GN", "Guinée", ""),
    ("CM", "Cameroun", ""),
    ("MG", "Madagascar", ""),
    ("HT", "Haïti", ""),
    ("LU", "Luxembourg", ""),
    ("MC", "Monaco", ""),
    ("AD", "Andorre", ""),
    ("IE", "Irlande", ""),
    ("AT", "Autriche", ""),
    ("SE", "Suède", ""),
    ("NO", "Norvège", ""),
    ("DK", "Danemark", ""),
    ("FI", "Finlande", ""),
    ("IS", "Islande", ""),
    ("GR", "Grèce", ""),
    ("PL", "Pologne", ""),
    ("CZ", "Tchéquie", ""),
    ("SK", "Slovaquie", ""),
    ("HU", "Hongrie", ""),
    ("RO", "Roumanie", ""),
    ("BG", "Bulgarie", ""),
    ("HR", "Croatie", ""),
    ("RS", "Serbie", ""),
    ("BA", "Bosnie-Herzégovine", ""),
    ("SI", "Slovénie", ""),
    ("JP", "Japon", ""),
    ("CN", "Chine", ""),
    ("KR", "Corée du Sud", ""),
    ("IN", "Inde", ""),
    ("BR", "Brésil", ""),
    ("AR", "Argentine", ""),
    ("MX", "Mexique", ""),
    ("CO", "Colombie", ""),
    ("CL", "Chili", ""),
    ("PE", "Pérou", ""),
    ("AU", "Australie", ""),
    ("NZ", "Nouvelle-Zélande", ""),
    ("ZA", "Afrique du Sud", ""),
    ("RU", "Russie", ""),
    ("UA", "Ukraine", ""),
    ("TR", "Turquie", ""),
    ("IL", "Israël", ""),
    ("LB", "Liban", ""),
]

# Enrichissement avec tous les pays du monde depuis timonde_world_data et zone.tab
def build_countries_registry():
    d = {code: (name, flag) for code, name, flag in COUNTRIES_DB}
    try:
        from timonde_world_data import WORLD_COUNTRIES
        for code, fr_name, _en_name in WORLD_COUNTRIES:
            if code not in d:
                d[code] = (fr_name, "")
    except Exception:
        pass
    zone_tab = "/usr/share/zoneinfo/zone.tab"
    if os.path.exists(zone_tab):
        try:
            with open(zone_tab, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("\t")
                    cc = parts[0].strip().upper()
                    if cc not in d:
                        d[cc] = (cc, "")
        except Exception:
            pass
    return d

COUNTRIES_REGISTRY = build_countries_registry()

# Fuseaux horaires complets pour la France (Métropole + Outre-mer)
FRANCE_TIMEZONES = [
    ("Europe/Paris", "Europe/Paris (France métropolitaine)"),
    ("America/Guadeloupe", "America/Guadeloupe (Guadeloupe - Antilles)"),
    ("America/Martinique", "America/Martinique (Martinique - Antilles)"),
    ("America/Cayenne", "America/Cayenne (Guyane française)"),
    ("Indian/Reunion", "Indian/Reunion (La Réunion - Océan Indien)"),
    ("Indian/Mayotte", "Indian/Mayotte (Mayotte - Océan Indien)"),
    ("America/Miquelon", "America/Miquelon (Saint-Pierre-et-Miquelon)"),
    ("America/St_Barthelemy", "America/St_Barthelemy (Saint-Barthélemy)"),
    ("America/Marigot", "America/Marigot (Saint-Martin)"),
    ("Pacific/Noumea", "Pacific/Noumea (Nouvelle-Calédonie)"),
    ("Pacific/Tahiti", "Pacific/Tahiti (Polynésie française - Tahiti)"),
    ("Pacific/Marquesas", "Pacific/Marquesas (Polynésie - Îles Marquises)"),
    ("Pacific/Gambier", "Pacific/Gambier (Polynésie - Îles Gambier)"),
    ("Pacific/Wallis", "Pacific/Wallis (Wallis-et-Futuna)"),
]

# Libellés clairs pour les pays multi-fuseaux majeurs
CUSTOM_MULTI_TZ = {
    "CA": [
        ("America/Toronto", "America/Toronto (Est - Québec, Ontario)"),
        ("America/Moncton", "America/Moncton (Atlantique - Nouveau-Brunswick, Acadie)"),
        ("America/Halifax", "America/Halifax (Atlantique - Nouvelle-Écosse)"),
        ("America/St_Johns", "America/St_Johns (Terre-Neuve)"),
        ("America/Winnipeg", "America/Winnipeg (Centre - Manitoba)"),
        ("America/Regina", "America/Regina (Centre - Saskatchewan)"),
        ("America/Edmonton", "America/Edmonton (Rocheuses - Alberta)"),
        ("America/Vancouver", "America/Vancouver (Pacifique - Colombie-Britannique)"),
        ("America/Whitehorse", "America/Whitehorse (Yukon)"),
    ],
    "US": [
        ("America/New_York", "America/New_York (Heure de l'Est : Caroline du Nord [NC], NY, FL, DC, GA, VA, PA...)"),
        ("America/Chicago", "America/Chicago (Heure du Centre : Chicago, Texas, Louisiane, Tennessee, MO...)"),
        ("America/Denver", "America/Denver (Heure des Montagnes : Denver, Colorado, Utah, NM...)"),
        ("America/Phoenix", "America/Phoenix (Montagnes sans heure d'été : Arizona)"),
        ("America/Los_Angeles", "America/Los_Angeles (Heure du Pacifique : Californie, Washington, Oregon...)"),
        ("America/Anchorage", "America/Anchorage (Alaska)"),
        ("Pacific/Honolulu", "Pacific/Honolulu (Hawaï)"),
    ],
    "BR": [
        ("America/Sao_Paulo", "America/Sao_Paulo (Brasília, São Paulo, Rio)"),
        ("America/Manaus", "America/Manaus (Amazonie)"),
        ("America/Cuiaba", "America/Cuiaba (Centre-Ouest)"),
        ("America/Rio_Branco", "America/Rio_Branco (Acre)"),
        ("America/Noronha", "America/Noronha (Fernando de Noronha)"),
    ],
    "AU": [
        ("Australia/Sydney", "Australia/Sydney (Est - Sydney, Melbourne)"),
        ("Australia/Brisbane", "Australia/Brisbane (Est - Queensland sans heure d'été)"),
        ("Australia/Adelaide", "Australia/Adelaide (Centre - Adélaïde)"),
        ("Australia/Darwin", "Australia/Darwin (Centre - Territoire du Nord)"),
        ("Australia/Perth", "Australia/Perth (Ouest - Perth)"),
    ],
    "RU": [
        ("Europe/Moscow", "Europe/Moscow (Moscou, Saint-Pétersbourg - UTC+3)"),
        ("Europe/Kaliningrad", "Europe/Kaliningrad (Kaliningrad - UTC+2)"),
        ("Europe/Samara", "Europe/Samara (Samara - UTC+4)"),
        ("Asia/Yekaterinburg", "Asia/Yekaterinburg (Oural - UTC+5)"),
        ("Asia/Omsk", "Asia/Omsk (Omsk - UTC+6)"),
        ("Asia/Novosibirsk", "Asia/Novosibirsk (Novossibirsk - UTC+7)"),
        ("Asia/Krasnoyarsk", "Asia/Krasnoyarsk (Krasnoïarsk - UTC+7)"),
        ("Asia/Irkutsk", "Asia/Irkutsk (Irkoutsk - UTC+8)"),
        ("Asia/Yakutsk", "Asia/Yakutsk (Iakoutsk - UTC+9)"),
        ("Asia/Vladivostok", "Asia/Vladivostok (Vladivostok - UTC+10)"),
        ("Asia/Magadan", "Asia/Magadan (Magadan - UTC+11)"),
        ("Asia/Kamchatka", "Asia/Kamchatka (Kamtchatka - UTC+12)"),
    ],
    "ES": [
        ("Europe/Madrid", "Europe/Madrid (Péninsule ibérique et Baléares)"),
        ("Atlantic/Canary", "Atlantic/Canary (Îles Canaries)"),
        ("Africa/Ceuta", "Africa/Ceuta (Ceuta et Melilla)"),
    ],
    "PT": [
        ("Europe/Lisbon", "Europe/Lisbon (Portugal continental et Madère)"),
        ("Atlantic/Azores", "Atlantic/Azores (Açores)"),
    ],
    "GB": [
        ("Europe/London", "Europe/London (Royaume-Uni métropolitain - Londres, Écosse, Pays de Galles, Irlande du Nord)"),
        ("Europe/Gibraltar", "Europe/Gibraltar (Gibraltar - Méditerranée)"),
        ("Atlantic/Bermuda", "Atlantic/Bermuda (Bermudes - Atlantique Nord)"),
        ("America/Cayman", "America/Cayman (Îles Caïmans - Caraïbes)"),
        ("America/Tortola", "America/Tortola (Îles Vierges britanniques)"),
        ("America/Montserrat", "America/Montserrat (Montserrat - Caraïbes)"),
        ("America/Grand_Turk", "America/Grand_Turk (Îles Turques-et-Caïques)"),
        ("America/Anguilla", "America/Anguilla (Anguilla - Caraïbes)"),
        ("Atlantic/Stanley", "Atlantic/Stanley (Îles Malouines / Falkland)"),
        ("Atlantic/South_Georgia", "Atlantic/South_Georgia (Géorgie du Sud)"),
        ("Atlantic/St_Helena", "Atlantic/St_Helena (Sainte-Hélène, Ascension, Tristan da Cunha)"),
        ("Indian/Chagos", "Indian/Chagos (Territoire britannique de l'océan Indien)"),
        ("Pacific/Pitcairn", "Pacific/Pitcairn (Îles Pitcairn)"),
    ],
}

UK_TIMEZONES = CUSTOM_MULTI_TZ["GB"]


def load_world_timezones() -> dict:
    catalogue = collections.defaultdict(list)
    zone_tab_path = "/usr/share/zoneinfo/zone.tab"
    if os.path.exists(zone_tab_path):
        try:
            with open(zone_tab_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("\t")
                    if len(parts) >= 3:
                        cc = parts[0].strip().upper()
                        tz = parts[2].strip()
                        comment = parts[3].strip() if len(parts) > 3 else ""
                        desc = f"{tz} ({comment})" if comment else tz
                        catalogue[cc].append((tz, desc))
        except Exception:
            pass

    catalogue["FR"] = list(FRANCE_TIMEZONES)
    for cc, tz_list in CUSTOM_MULTI_TZ.items():
        catalogue[cc] = list(tz_list)

    overseas_direct = {
        "GP": [("America/Guadeloupe", "America/Guadeloupe (Guadeloupe)")],
        "MQ": [("America/Martinique", "America/Martinique (Martinique)")],
        "GF": [("America/Cayenne", "America/Cayenne (Guyane)")],
        "RE": [("Indian/Reunion", "Indian/Reunion (La Réunion)")],
        "YT": [("Indian/Mayotte", "Indian/Mayotte (Mayotte)")],
        "NC": [("Pacific/Noumea", "Pacific/Noumea (Nouvelle-Calédonie)")],
        "PF": [("Pacific/Tahiti", "Pacific/Tahiti (Polynésie française)")],
        "PM": [("America/Miquelon", "America/Miquelon (Saint-Pierre-et-Miquelon)")],
        "BL": [("America/St_Barthelemy", "America/St_Barthelemy (Saint-Barthélemy)")],
        "MF": [("America/Marigot", "America/Marigot (Saint-Martin)")],
        "WF": [("Pacific/Wallis", "Pacific/Wallis (Wallis-et-Futuna)")],
        # Territoires britanniques d'outre-mer directs
        "BM": [("Atlantic/Bermuda", "Atlantic/Bermuda (Bermudes)")],
        "KY": [("America/Cayman", "America/Cayman (Îles Caïmans)")],
        "VG": [("America/Tortola", "America/Tortola (Îles Vierges britanniques)")],
        "MS": [("America/Montserrat", "America/Montserrat (Montserrat)")],
        "TC": [("America/Grand_Turk", "America/Grand_Turk (Îles Turques-et-Caïques)")],
        "AI": [("America/Anguilla", "America/Anguilla (Anguilla)")],
        "FK": [("Atlantic/Stanley", "Atlantic/Stanley (Îles Malouines / Falkland)")],
        "GI": [("Europe/Gibraltar", "Europe/Gibraltar (Gibraltar)")],
        "GS": [("Atlantic/South_Georgia", "Atlantic/South_Georgia (Géorgie du Sud)")],
        "SH": [("Atlantic/St_Helena", "Atlantic/St_Helena (Sainte-Hélène)")],
        "IO": [("Indian/Chagos", "Indian/Chagos (Territoire britannique de l'océan Indien)")],
        "PN": [("Pacific/Pitcairn", "Pacific/Pitcairn (Îles Pitcairn)")],
    }
    for cc, tzs in overseas_direct.items():
        catalogue[cc] = tzs

    return catalogue


WORLD_TIMEZONES = load_world_timezones()


def infer_timezone(country_code: str = "", station_name: str = "", group_path: str = "") -> str:
    """
    Infère intelligemment le fuseau horaire exact d'une station à partir de son pays ISO,
    son nom et son groupe/arborescence.
    """
    cc = (country_code or "").strip().upper()
    corpus = f"{station_name} {group_path}".lower()

    # 1. France & Outre-mer
    if cc in ("FR", ""):
        if any(w in corpus for w in ("guadeloupe", "antilles", "pointe-à-pitre", "basse-terre", "rci guadeloupe")):
            return "America/Guadeloupe"
        if any(w in corpus for w in ("martinique", "fort-de-france", "rci martinique")):
            return "America/Martinique"
        if any(w in corpus for w in ("guyane", "cayenne", "kourou")):
            return "America/Cayenne"
        if any(w in corpus for w in ("reunion", "réunion", "saint-denis de la réunion", "saint-pierre")):
            return "Indian/Reunion"
        if any(w in corpus for w in ("mayotte", "mamoudzou", "dzaoudzi")):
            return "Indian/Mayotte"
        if any(w in corpus for w in ("nouvelle-caledonie", "nouvelle-calédonie", "noumea", "nouméa", "djiido")):
            return "Pacific/Noumea"
        if any(w in corpus for w in ("polynesie", "polynésie", "tahiti", "papeete", "tiare")):
            return "Pacific/Tahiti"
        if any(w in corpus for w in ("saint-pierre-et-miquelon", "miquelon")):
            return "America/Miquelon"
        if any(w in corpus for w in ("saint-barthelemy", "saint-barthélemy", "st-barth")):
            return "America/St_Barthelemy"
        if any(w in corpus for w in ("saint-martin", "st-martin", "marigot")):
            return "America/Marigot"
        if any(w in corpus for w in ("wallis", "futuna", "mata-utu")):
            return "Pacific/Wallis"
        if cc == "FR":
            return "Europe/Paris"

    # 2. Royaume-Uni & Territoires d'Outre-mer
    if cc in ("GB", "UK"):
        if any(w in corpus for w in ("gibraltar", "bFBS gibraltar")):
            return "Europe/Gibraltar"
        if any(w in corpus for w in ("bermuda", "bermudes", "hamilton")):
            return "Atlantic/Bermuda"
        if any(w in corpus for w in ("cayman", "caïmans", "george town")):
            return "America/Cayman"
        if any(w in corpus for w in ("falkland", "malouines", "stanley")):
            return "Atlantic/Stanley"
        if any(w in corpus for w in ("virgin islands", "tortola", "road town")):
            return "America/Tortola"
        if any(w in corpus for w in ("montserrat", "plymouth", "brades")):
            return "America/Montserrat"
        if any(w in corpus for w in ("turks", "caicos", "grand turk")):
            return "America/Grand_Turk"
        if any(w in corpus for w in ("anguilla", "the valley")):
            return "America/Anguilla"
        if any(w in corpus for w in ("st helena", "sainte-hélène", "jamestown", "ascension")):
            return "Atlantic/St_Helena"
        return "Europe/London"

    # 3. Territoires directs
    direct_map = {
        "GP": "America/Guadeloupe",
        "MQ": "America/Martinique",
        "GF": "America/Cayenne",
        "RE": "Indian/Reunion",
        "YT": "Indian/Mayotte",
        "NC": "Pacific/Noumea",
        "PF": "Pacific/Tahiti",
        "PM": "America/Miquelon",
        "BL": "America/St_Barthelemy",
        "MF": "America/Marigot",
        "WF": "Pacific/Wallis",
        "BM": "Atlantic/Bermuda",
        "KY": "America/Cayman",
        "VG": "America/Tortola",
        "MS": "America/Montserrat",
        "TC": "America/Grand_Turk",
        "AI": "America/Anguilla",
        "FK": "Atlantic/Stanley",
        "GI": "Europe/Gibraltar",
        "SH": "Atlantic/St_Helena",
    }
    if cc in direct_map:
        return direct_map[cc]

    # 4. Canada
    if cc == "CA":
        if any(w in corpus for w in ("vancouver", "colombie-britannique", "british columbia", "victoria")):
            return "America/Vancouver"
        if any(w in corpus for w in ("alberta", "calgary", "edmonton")):
            return "America/Edmonton"
        if any(w in corpus for w in ("saskatchewan", "regina", "saskatoon")):
            return "America/Regina"
        if any(w in corpus for w in ("manitoba", "winnipeg")):
            return "America/Winnipeg"
        if any(w in corpus for w in ("halifax", "nouvelle-ecosse", "nova scotia")):
            return "America/Halifax"
        if any(w in corpus for w in ("terre-neuve", "newfoundland", "st. john")):
            return "America/St_Johns"
        return "America/Toronto"

    # 5. États-Unis
    if cc == "US":
        if any(w in corpus for w in ("california", "los angeles", "san francisco", "seattle", "washington", "oregon")):
            return "America/Los_Angeles"
        if any(w in corpus for w in ("chicago", "texas", "houston", "dallas", "louisiana", "new orleans", "illinois")):
            return "America/Chicago"
        if any(w in corpus for w in ("denver", "colorado", "utah", "salt lake", "phoenix", "arizona")):
            return "America/Denver"
        if any(w in corpus for w in ("alaska", "anchorage")):
            return "America/Anchorage"
        if any(w in corpus for w in ("hawaii", "honolulu")):
            return "Pacific/Honolulu"
        return "America/New_York"

    # 6. Australie
    if cc == "AU":
        if any(w in corpus for w in ("perth", "western australia")):
            return "Australia/Perth"
        if any(w in corpus for w in ("adelaide", "south australia")):
            return "Australia/Adelaide"
        if any(w in corpus for w in ("darwin", "northern territory")):
            return "Australia/Darwin"
        if any(w in corpus for w in ("brisbane", "queensland")):
            return "Australia/Brisbane"
        return "Australia/Sydney"

    # 7. Fallback standard par pays
    tz_list = WORLD_TIMEZONES.get(cc, [])
    if tz_list:
        return tz_list[0][0]

    return ""


DEFAULT_WORLD_TIMEZONES = [
    ("", "(Déduction automatique selon le nom / groupe)"),
    ("America/New_York", "America/New_York (Heure de l'Est : Caroline du Nord [NC], NY, FL, DC, GA, VA, PA...)"),
    ("America/Chicago", "America/Chicago (Heure du Centre : Chicago, Texas, Louisiane, Tennessee, MO...)"),
    ("America/Denver", "America/Denver (Heure des Montagnes : Denver, Colorado, Utah, NM...)"),
    ("America/Phoenix", "America/Phoenix (Montagnes sans heure d'été : Arizona)"),
    ("America/Los_Angeles", "America/Los_Angeles (Heure du Pacifique : Californie, Washington, Oregon...)"),
    ("America/Anchorage", "America/Anchorage (Alaska)"),
    ("Pacific/Honolulu", "Pacific/Honolulu (Hawaï)"),
    ("Europe/Paris", "Europe/Paris (France métropolitaine, Belgique, Suisse, Europe centrale)"),
    ("Europe/London", "Europe/London (Royaume-Uni, Portugal, UTC)"),
    ("America/Toronto", "America/Toronto (Canada Est - Québec, Ontario)"),
    ("America/Vancouver", "America/Vancouver (Canada Pacifique)"),
    ("America/Guadeloupe", "America/Guadeloupe (Antilles - Guadeloupe, Martinique)"),
    ("Indian/Reunion", "Indian/Reunion (La Réunion)"),
    ("Pacific/Noumea", "Pacific/Noumea (Nouvelle-Calédonie)"),
    ("Pacific/Tahiti", "Pacific/Tahiti (Polynésie française)"),
    ("Asia/Tokyo", "Asia/Tokyo (Japon)"),
    ("Australia/Sydney", "Australia/Sydney (Australie Est)"),
]


# -----------------------------------------------------------------------------
# 5. Widget Helpers GTK3
# -----------------------------------------------------------------------------

def make_btn(label_text, icon_name=None, tooltip=None):
    """Génère un bouton GTK avec icône et libellé alignés proprement sans doublon d'icône."""
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    btn = Gtk.Button()
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    box.set_halign(Gtk.Align.CENTER)
    img = None
    if icon_name:
        img = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.BUTTON)
        box.pack_start(img, False, False, 0)

    clean_text = label_text or ""
    if icon_name:
        if clean_text == "?":
            clean_text = ""
        elif clean_text.startswith("▶ "):
            clean_text = clean_text[2:].strip()
        elif clean_text.startswith("⏹ "):
            clean_text = clean_text[2:].strip()

    lbl = Gtk.Label(label=clean_text)
    if clean_text:
        box.pack_start(lbl, False, False, 0)
    btn.add(box)
    btn._label_widget = lbl
    btn._image_widget = img
    if tooltip:
        btn.set_tooltip_text(tooltip)
    return btn


def update_btn_content(btn, label_text, icon_name=None):
    """Met à jour dynamiquement le texte et l'icône d'un bouton créé via make_btn sans doublon d'icône."""
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    clean_text = label_text or ""
    if icon_name:
        if clean_text == "?":
            clean_text = ""
        elif clean_text.startswith("▶ "):
            clean_text = clean_text[2:].strip()
        elif clean_text.startswith("⏹ "):
            clean_text = clean_text[2:].strip()

    if hasattr(btn, "_label_widget") and btn._label_widget:
        btn._label_widget.set_text(clean_text)
        btn._label_widget.set_visible(bool(clean_text))
    if icon_name and hasattr(btn, "_image_widget") and btn._image_widget:
        btn._image_widget.set_from_icon_name(icon_name, Gtk.IconSize.BUTTON)


# -----------------------------------------------------------------------------
# 6. Stylisation du Menu Systray GTK3 (XEmbed IceWM/Fluxbox & show_menu.py)
# -----------------------------------------------------------------------------

_MENU_CSS_APPLIED = False

def apply_timonde_menu_css():
    """Injecte la feuille de style GTK3 pour hiérarchiser visuellement l'en-tête 'En écoute'."""
    global _MENU_CSS_APPLIED
    if _MENU_CSS_APPLIED:
        return
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk, Gdk
        provider = Gtk.CssProvider()
        provider.load_from_data(b"""
        menu separator, menuitem.separator {
            min-height: 2px;
            margin: 4px 8px;
            background-color: alpha(@theme_fg_color, 0.28);
        }
        menuitem.timonde-header-action {
            background-color: alpha(@theme_selected_bg_color, 0.14);
            border-radius: 2px;
            padding-top: 5px;
            padding-bottom: 5px;
        }
        menuitem.timonde-info-time,
        menuitem.timonde-info-time:disabled {
            background-color: alpha(@theme_fg_color, 0.08);
            border-left: 3px solid @theme_selected_bg_color;
            color: @theme_fg_color;
            opacity: 0.92;
            padding-top: 3px;
            padding-bottom: 3px;
        }
        menuitem.timonde-info-track,
        menuitem.timonde-info-track:disabled {
            background-color: alpha(@theme_fg_color, 0.08);
            border-left: 3px solid @theme_selected_bg_color;
            color: @theme_fg_color;
            opacity: 0.95;
            padding-top: 3px;
            padding-bottom: 4px;
        }
        menuitem.timonde-sep-header,
        menuitem.timonde-sep-header:disabled {
            color: @theme_fg_color;
            opacity: 0.75;
        }
        """)
        screen = Gdk.Screen.get_default()
        if screen:
            Gtk.StyleContext.add_provider_for_screen(
                screen,
                provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
            _MENU_CSS_APPLIED = True
    except Exception:
        pass


def _find_label_widget(widget):
    """Recherche récursivement le premier Gtk.Label enfant d'un Gtk.MenuItem."""
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    if isinstance(widget, Gtk.Label):
        return widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            found = _find_label_widget(child)
            if found is not None:
                return found
    return None


def style_dbusmenu_gtk(menu, is_root=True):
    """
    Parcourt un DbusmenuGtk3.Menu pour :
    - Corriger les séparateurs libdbusmenu ("Label Empty")
    - Mettre en gras l'action principale de la station en tête
    - Appliquer un fond distinct et une taille adaptée à la ligne d'heure locale
    - Mettre en italique avec fond distinct le titre du morceau en cours (♪)
    """
    if not menu:
        return
    apply_timonde_menu_css()
    try:
        import html
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk

        children = menu.get_children()
        for idx, child in enumerate(children):
            if isinstance(child, Gtk.SeparatorMenuItem):
                child.set_visible(True)
                continue
            if not isinstance(child, Gtk.MenuItem):
                continue

            raw_lbl = getattr(child, "get_label", lambda: None)() or ""
            lbl_widget = _find_label_widget(child)
            ctx = child.get_style_context()

            # 1. Séparateurs textuels ou bug "Label Empty"
            if raw_lbl == "Label Empty" or (raw_lbl.strip() == "" and not isinstance(child, Gtk.SeparatorMenuItem)):
                child.set_label("────────────────────────")
                child.set_sensitive(False)
                ctx.add_class("timonde-sep-header")
            elif "─────" in raw_lbl or "───" in raw_lbl:
                child.set_sensitive(False)
                ctx.add_class("timonde-sep-header")
                if lbl_widget:
                    lbl_widget.set_markup(f"<span size='small'><b>{html.escape(raw_lbl.strip())}</b></span>")

            # 2. En-tête de lecture principal (ligne 0 du menu racine)
            elif is_root and idx == 0:
                ctx.add_class("timonde-header-action")
                if lbl_widget:
                    lbl_widget.set_markup(f"<b>{html.escape(raw_lbl)}</b>")

            # 3. Ligne d'heure locale de la station en cours
            elif is_root and ("│ [" in raw_lbl or (raw_lbl.strip().startswith("[") and "•" in raw_lbl and "UTC" in raw_lbl)):
                ctx.add_class("timonde-info-time")
                clean_time = raw_lbl.replace("  │ ", "").replace("│ ", "").strip()
                if lbl_widget:
                    parts = clean_time.split("•", 1)
                    if len(parts) == 2:
                        lbl_widget.set_markup(
                            f"<span size='small'><b>{html.escape(parts[0].strip())}</b> • {html.escape(parts[1].strip())}</span>"
                        )
                    else:
                        lbl_widget.set_markup(f"<span size='small'>{html.escape(clean_time)}</span>")

            # 4. Ligne du titre musical en cours (♪)
            elif is_root and "♪" in raw_lbl:
                ctx.add_class("timonde-info-track")
                clean_track = raw_lbl.replace("  │ ", "").replace("│ ", "").strip()
                if lbl_widget:
                    lbl_widget.set_markup(f"<i>{html.escape(clean_track)}</i>")

            sub = child.get_submenu()
            if sub:
                style_dbusmenu_gtk(sub, is_root=False)
    except Exception:
        pass


# -----------------------------------------------------------------------------
# 7. Vérification HTTP & Lecteur de Pré-écoute GStreamer (StreamPreviewPlayer)
# -----------------------------------------------------------------------------

PREVIEW_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) TiMonde/0.2.0"


def resolve_playlist_stream_url(url, timeout=3.5):
    """Résout si nécessaire une playlist .m3u/.pls vers l'URL de flux direct."""
    import urllib.request
    clean = clean_stream_url(url)
    lower = clean.lower().split("?")[0]
    if not (lower.endswith(".pls") or lower.endswith(".m3u") or lower.endswith(".m3u8")):
        return clean
    try:
        req = urllib.request.Request(clean, headers={"User-Agent": PREVIEW_USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if any(x in ctype for x in ("audio/mpeg", "audio/aac", "audio/ogg", "audio/flac", "application/ogg")):
                return resp.geturl() or clean
            body = resp.read(8192).decode("utf-8", errors="replace")
            for line in body.splitlines():
                l = line.strip()
                if not l or l.startswith("#"):
                    continue
                if l.lower().startswith("file") and "=" in l:
                    candidate = l.split("=", 1)[1].strip()
                    if candidate.startswith("http://") or candidate.startswith("https://"):
                        return candidate
                elif l.startswith("http://") or l.startswith("https://"):
                    return l
    except Exception:
        pass
    return clean


def pause_main_timonde_instance():
    """Met en pause le flux principal de TiMonde via D-Bus MPRIS2 pour éviter deux flux simultanés."""
    try:
        import dbus
        bus = dbus.SessionBus()
        if bus.name_has_owner("org.mpris.MediaPlayer2.timonde"):
            obj = bus.get_object("org.mpris.MediaPlayer2.timonde", "/org/mpris/MediaPlayer2")
            player = dbus.Interface(obj, "org.mpris.MediaPlayer2.Player")
            player.Pause()
    except Exception:
        pass


class StreamPreviewPlayer:
    """
    Lecteur d'aperçu audio léger basé sur GStreamer playbin.
    Permet de vérifier et d'écouter immédiatement une station avant de l'importer
    ou pendant l'édition/organisation, sans conflit avec l'instance principale TiMonde.
    """
    def __init__(self, on_status_changed=None, on_status_change=None):
        self.on_status_changed = on_status_changed or on_status_change
        self.playbin = None
        self.current_url = None
        self.current_name = None
        self.is_playing = False
        self._gst_ready = False

    def _ensure_gst(self):
        if self._gst_ready:
            return self.playbin is not None
        self._gst_ready = True
        try:
            import gi
            gi.require_version("Gst", "1.0")
            from gi.repository import Gst
            Gst.init(None)
            self.Gst = Gst
            self.playbin = Gst.ElementFactory.make("playbin", "timonde-preview")
            if self.playbin:
                self.playbin.set_property("volume", 0.85)
                bus = self.playbin.get_bus()
                bus.add_signal_watch()
                bus.connect("message", self._on_bus_message)
            return self.playbin is not None
        except Exception:
            self.playbin = None
            return False

    def _emit_status(self, playing, message, is_error=False):
        if self.on_status_changed:
            try:
                from gi.repository import GLib
                GLib.idle_add(self.on_status_changed, playing, self.current_url or "", message, is_error)
            except Exception:
                pass

    def _on_bus_message(self, _bus, msg):
        if not hasattr(self, "Gst"):
            return
        t = msg.type
        if t == self.Gst.MessageType.ERROR:
            err, _dbg = msg.parse_error()
            err_str = str(err.message) if err else "Flux illisible"
            self.stop(silent=True)
            self._emit_status(False, f"❌ Flux inaccessible ({err_str})", is_error=True)
        elif t == self.Gst.MessageType.EOS:
            self.stop(silent=True)
            self._emit_status(False, "⏹ Fin du flux", is_error=False)
        elif t == self.Gst.MessageType.STATE_CHANGED:
            if msg.src == self.playbin:
                _old, new_state, _pending = msg.parse_state_changed()
                if new_state == self.Gst.State.PLAYING:
                    self.is_playing = True
                    self._emit_status(True, f"🔊 En écoute : « {self.current_name or 'Radio'} »", is_error=False)
        elif t == self.Gst.MessageType.TAG:
            taglist = msg.parse_tag()
            ok, title = taglist.get_string("title")
            if ok and title and title.strip():
                self.is_playing = True
                self._emit_status(
                    True,
                    f"🔊 « {self.current_name or 'Radio'} » — ♪ {title.strip()}",
                    is_error=False
                )

    def is_playing_url(self, url):
        return bool(self.is_playing and self.current_url and clean_stream_url(url) == self.current_url)

    def toggle(self, station_name, url=None):
        if url is None:
            url = station_name
            station_name = "Radio"
        clean = clean_stream_url(url)
        if not clean:
            self._emit_status(False, "❌ URL de flux vide", is_error=True)
            return False
        if self.is_playing and self.current_url == clean:
            self.stop()
            return False
        return self.play(station_name, clean)

    def play(self, station_name, url=None):
        if url is None:
            url = station_name
            station_name = "Radio"
        import threading
        clean = clean_stream_url(url)
        if not clean:
            self._emit_status(False, "❌ URL de flux vide", is_error=True)
            return False

        if not self._ensure_gst():
            self._emit_status(False, "❌ GStreamer non disponible", is_error=True)
            return False

        self.stop(silent=True)
        pause_main_timonde_instance()

        self.current_url = clean
        self.current_name = station_name or "Radio"
        self.is_playing = True
        self._emit_status(True, f"⏳ Connexion à « {self.current_name} »...", is_error=False)

        def start_worker(target_url, target_name):
            resolved = resolve_playlist_stream_url(target_url)
            from gi.repository import GLib
            def apply_uri():
                if self.current_url != target_url or not self.playbin:
                    return False
                self.playbin.set_state(self.Gst.State.NULL)
                self.playbin.set_property("uri", resolved)
                self.playbin.set_state(self.Gst.State.PLAYING)
                return False
            GLib.idle_add(apply_uri)

        threading.Thread(target=start_worker, args=(clean, self.current_name), daemon=True).start()
        return True

    def stop(self, silent=False):
        if self.playbin and hasattr(self, "Gst"):
            try:
                self.playbin.set_state(self.Gst.State.NULL)
            except Exception:
                pass
        was_playing = self.is_playing
        self.is_playing = False
        self.current_url = None
        self.current_name = None
        if was_playing and not silent:
            self._emit_status(False, "", is_error=False)

