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

# Enrichissement avec tous les pays du monde depuis zone.tab
def build_countries_registry():
    d = {code: (name, flag) for code, name, flag in COUNTRIES_DB}
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
    """Génère un bouton GTK avec icône et libellé alignés proprement."""
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    btn = Gtk.Button()
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    box.set_halign(Gtk.Align.CENTER)
    if icon_name:
        img = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.BUTTON)
        box.pack_start(img, False, False, 0)
    lbl = Gtk.Label(label=label_text)
    box.pack_start(lbl, False, False, 0)
    btn.add(box)
    btn._label_widget = lbl
    if tooltip:
        btn.set_tooltip_text(tooltip)
    return btn
