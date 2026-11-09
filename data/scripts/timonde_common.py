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
import html
import subprocess
import shutil
import json

# Neutralisation inconditionnelle d'IBus et XMODIFIERS dès le chargement du module
for _var in ("GTK_IM_MODULE", "XMODIFIERS", "QT_IM_MODULE"):
    os.environ.pop(_var, None)

# Internationalisation TiMonde
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from timonde_i18n import _
except ImportError:
    def _(s): return s

TIMONDE_VERSION = "0.2.5"
TIMONDE_USER_AGENT = f"TiMonde/{TIMONDE_VERSION}"
USER_AGENT = TIMONDE_USER_AGENT
USER_AGENT_PROBE = f"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) TiMonde/{TIMONDE_VERSION}"
PREVIEW_USER_AGENT = USER_AGENT_PROBE


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


def find_timonde_binary():
    """Localise le binaire officiel ou local de TiMonde."""
    # 1. Priorité locale en mode développement (présence de Cargo.toml à la racine)
    root_cargo = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../Cargo.toml"))
    if os.path.exists(root_cargo):
        dev_rel = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../target/release/timonde"))
        if os.path.exists(dev_rel):
            return dev_rel
        dev_deb = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../target/debug/timonde"))
        if os.path.exists(dev_deb):
            return dev_deb

    # 2. Binaire dans le PATH ou installé localement
    w = shutil.which("timonde")
    if w and os.path.exists(w):
        return w
    local = os.path.expanduser("~/.local/bin/timonde")
    if os.path.exists(local):
        return local
    if os.path.exists("/usr/bin/timonde"):
        return "/usr/bin/timonde"
    return None


def check_stream_url(url, timeout=3.0, with_redirect=False, fetch_meta=False):
    """
    Test universel, frugal et rapide de disponibilité d'un flux audio.
    Délègue en priorité absolue au moteur natif Rust (timonde --probe-stream).
    Retourne (status, msg) par défaut, ou (status, msg, redirected_url) si with_redirect=True.
    Si fetch_meta=True, retourne (status, msg, meta) ou (status, msg, redirected_url, meta)
    où meta est un dictionnaire {'icy_name': ..., 'icy_genre': ..., 'icy_br': ..., 'content_type': ...}.
    Status vaut True, False, ou 'GEO' (géo-restreint).
    """
    meta = {"icy_name": "", "icy_genre": "", "icy_br": "", "content_type": ""}

    def _format_ret(st, m, rd=None):
        if fetch_meta:
            return (st, m, rd, meta) if with_redirect else (st, m, meta)
        return (st, m, rd) if with_redirect else (st, m)

    if not url or not url.strip():
        msg_empty = _("Empty URL")
        return _format_ret(False, msg_empty)

    clean = url.strip()

    # 1. Délégation native vers le moteur Rust (sans GIL, sans socket urllib lourd)
    timonde_bin = find_timonde_binary()
    if timonde_bin:
        try:
            to_sec = str(max(1, int(round(timeout))))
            cmd = [timonde_bin, "--probe-stream", clean, "--timeout", to_sec, "--json"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 1.5)
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout)
                ok = data.get("ok", False)
                is_geo = data.get("is_geo", False)
                msg_raw = data.get("message", "")
                redir = data.get("redirected_url")
                raw_meta = data.get("meta", {})
                meta["icy_name"] = raw_meta.get("icy_name", "")
                meta["icy_genre"] = raw_meta.get("icy_genre", "")
                meta["icy_br"] = raw_meta.get("icy_br", "")
                meta["content_type"] = raw_meta.get("content_type", "")

                if is_geo:
                    return _format_ret("GEO", _("Geoblocked (VPN)"), redir)
                elif ok:
                    codec = data.get("codec") or "Audio"
                    return _format_ret(True, _("Live ({codec})").format(codec=codec), redir)
                else:
                    if "HTML" in msg_raw:
                        msg = _("Offline (HTML error page)")
                    elif "inaccessible" in msg_raw:
                        msg = _("Server unreachable")
                    elif "dépassé" in msg_raw:
                        msg = _("Timeout")
                    else:
                        msg = msg_raw
                    return _format_ret(False, msg, redir)
        except Exception:
            pass

    # 2. Fallback de secours minimal en pur Python
    import urllib.request
    import urllib.error
    try:
        req = urllib.request.Request(
            clean,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "*/*",
                "Icy-MetaData": "1",
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.getcode()
            final_url = resp.geturl()
            redir = final_url if final_url != clean else None

            raw_name = resp.headers.get("icy-name") or resp.headers.get("x-audiocast-name") or ""
            raw_genre = resp.headers.get("icy-genre") or ""
            raw_br = resp.headers.get("icy-br") or ""
            ct = resp.headers.get("Content-Type", "")

            def _safe_header_str(val):
                if not val:
                    return ""
                try:
                    return val.encode("latin-1").decode("utf-8", errors="strict").strip()
                except Exception:
                    return str(val).strip()

            meta["icy_name"] = _safe_header_str(raw_name)
            meta["icy_genre"] = _safe_header_str(raw_genre)
            meta["icy_br"] = str(raw_br).strip()
            meta["content_type"] = ct.strip()

            if 200 <= code < 400:
                ct_low = ct.lower()
                if "text/html" in ct_low or "text/plain" in ct_low:
                    if not any(ext in clean.lower() for ext in [".m3u", ".m3u8", ".pls", ".asx"]):
                        msg_html = _("Offline (HTML error page)")
                        return _format_ret(False, msg_html, redir)

                codec = "Audio"
                if "aac" in ct_low: codec = "AAC"
                elif "mpeg" in ct_low or "mp3" in ct_low: codec = "MP3"
                elif "ogg" in ct_low: codec = "OGG"
                elif "flac" in ct_low: codec = "FLAC"
                elif "vnd.apple.mpegurl" in ct_low: codec = "HLS"
                msg = _("Live ({codec})").format(codec=codec)
                return _format_ret(True, msg, redir)
            err_http = _("HTTP Error {code}").format(code=code)
            return _format_ret(False, err_http, redir)
    except urllib.error.HTTPError as e:
        if e.code in (403, 451) or (e.code == 503 and any(k in clean.lower() for k in ["amperwave", "audacy", "streamtheworld", "akamai", "geoblock", "leanstream"])):
            msg_geo = _("Geoblocked (VPN)")
            return _format_ret("GEO", msg_geo)
        err_code = _("Error {code}").format(code=e.code)
        return _format_ret(False, err_code)
    except urllib.error.URLError:
        msg_unreach = _("Server unreachable")
        return _format_ret(False, msg_unreach)
    except Exception as e:
        line = getattr(e, "line", "") or str(e)
        if "ICY 200" in line or "200 OK" in line:
            msg_icy = _("Live (Shoutcast)")
            return _format_ret(True, msg_icy)
        msg_timeout = _("Timeout")
        return _format_ret(False, msg_timeout)



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



def get_user_bookmarks_groups(path=None):
    """Lit les groupes et sous-groupes existants depuis bookmarks.xml (chemin spécifié ou par défaut)."""
    candidates = [path] if path else [
        os.path.expanduser("~/.config/timonde/bookmarks.xml"),
        os.path.expanduser("~/.local/share/timonde/bookmarks.xml"),
        os.path.expanduser("~/.config/radiotray-ng/bookmarks.xml"),
        "bookmarks.xml",
    ]
    groups = []
    for cand in candidates:
        if cand and os.path.exists(cand):
            root = safe_parse_xml(cand)
            if root is not None:
                def walk_groups(el, prefix):
                    for g in el.findall("group"):
                        g_title = g.attrib.get("title", "").strip() or g.attrib.get("name", "").strip()
                        if g_title and g_title.lower() != "root":
                            full = f"{prefix}/{g_title}" if prefix else g_title
                            if full not in groups:
                                groups.append(full)
                            walk_groups(g, full)
                walk_groups(root, "")
                break
    return groups


# -----------------------------------------------------------------------------
# 4. Registre des Pays SANS EMOJI & Fuseaux Horaires (antiX-safe)
import unicodedata

def normalize_lookup(text: str) -> str:
    """Normalise une chaîne pour recherche insensible à la casse et aux accents."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFD", text.strip())
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn").lower()


def _load_countries_from_rust():
    timonde_bin = find_timonde_binary()
    aliases_map = {}
    if timonde_bin and os.path.exists(timonde_bin):
        try:
            res = subprocess.run([timonde_bin, "--dump-countries-json"], capture_output=True, text=True, timeout=2.0)
            if res.returncode == 0 and res.stdout.strip():
                items = json.loads(res.stdout)
                db = [(it["code"], it["name"], it.get("flag", "")) for it in items]
                reg = {}
                for it in items:
                    c_code = it["code"]
                    c_name = it["name"]
                    c_flag = it.get("flag", "")
                    c_aliases = it.get("aliases", [])
                    reg[c_code] = (c_name, c_flag, c_aliases)
                    aliases_map[c_code.lower()] = c_code
                    aliases_map[normalize_lookup(c_name)] = c_code
                    for al in c_aliases:
                        aliases_map[normalize_lookup(al)] = c_code
                return db, reg, aliases_map
        except Exception:
            pass
    # Fallback de secours minimal si binaire absent
    fallback = [
        ("FR", "France", ""), ("GP", "Guadeloupe", ""), ("MQ", "Martinique", ""), ("GF", "Guyane", ""),
        ("RE", "La Réunion", ""), ("BE", "Belgique", ""), ("CH", "Suisse", ""), ("CA", "Canada", ""),
        ("US", "États-Unis", ""), ("UK", "Royaume-Uni", ""), ("GB", "Royaume-Uni", ""), ("DE", "Allemagne", ""), ("ES", "Espagne", ""),
    ]
    reg = {}
    for c in fallback:
        reg[c[0]] = (c[1], c[2], [])
        aliases_map[c[0].lower()] = c[0]
        aliases_map[normalize_lookup(c[1])] = c[0]
    return fallback, reg, aliases_map

COUNTRIES_DB, COUNTRIES_REGISTRY, COUNTRY_ALIASES_MAP = _load_countries_from_rust()

_COUNTRY_RESOLVE_CACHE = {}

def resolve_country_code(query: str) -> str:
    """Résout une saisie libre en code ISO via le moteur natif Rust (avec cache mémoire)."""
    if not query:
        return ""
    q_str = query.strip()
    if q_str in _COUNTRY_RESOLVE_CACHE:
        return _COUNTRY_RESOLVE_CACHE[q_str]

    # 1. Détection code ISO direct entre parenthèses ou crochets (ex: "[FR]" ou "(FR)")
    m = re.search(r'[\[\(]([A-Za-z]{2})[\]\)]', q_str)
    if m:
        cand = m.group(1).upper()
        if cand in COUNTRIES_REGISTRY:
            _COUNTRY_RESOLVE_CACHE[q_str] = cand
            return cand

    # 2. Vérification rapide dans COUNTRY_ALIASES_MAP
    norm = normalize_lookup(q_str)
    if norm in COUNTRY_ALIASES_MAP:
        code = COUNTRY_ALIASES_MAP[norm]
        _COUNTRY_RESOLVE_CACHE[q_str] = code
        return code

    # 3. Délégation au binaire Rust
    timonde_bin = find_timonde_binary()
    if timonde_bin and os.path.exists(timonde_bin):
        try:
            res = subprocess.run([timonde_bin, "--resolve-country", q_str], capture_output=True, text=True, timeout=2.0)
            if res.returncode == 0 and res.stdout.strip():
                code = res.stdout.strip().upper()
                _COUNTRY_RESOLVE_CACHE[q_str] = code
                return code
        except Exception:
            pass

    code = q_str.upper() if len(q_str) == 2 else ""
    if code:
        _COUNTRY_RESOLVE_CACHE[q_str] = code
    return code

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


_INFER_TZ_CACHE = {}


def infer_timezone(country_code: str = "", station_name: str = "", group_path: str = "") -> str:
    """
    Infère intelligemment le fuseau horaire exact d'une station à partir de son pays ISO,
    son nom et son groupe/arborescence en déléguant au moteur Rust de TiMonde.
    """
    cc = (country_code or "").strip().upper()
    cache_key = (cc, station_name or "", group_path or "")
    if cache_key in _INFER_TZ_CACHE:
        return _INFER_TZ_CACHE[cache_key]

    timonde_bin = shutil.which("timonde") or os.path.expanduser("~/.local/bin/timonde")
    if os.path.exists(timonde_bin):
        try:
            cmd = [timonde_bin, "--infer-timezone", cc, station_name or "", group_path or ""]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=2.0)
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout.strip())
                tz = data.get("timezone", "")
                if tz:
                    _INFER_TZ_CACHE[cache_key] = tz
                    return tz
        except Exception:
            pass

    # Fallback standard par pays
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

def make_btn(label_text, icon_name=None, tooltip=None, primary=False):
    """Génère un bouton GTK avec icône et libellé alignés proprement sans doublon d'icône."""
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    btn = Gtk.Button()
    if primary:
        btn.get_style_context().add_class("suggested-action")
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

def set_window_icon(window, icon_name="timonde_on"):
    """
    Définit l'icône d'une fenêtre GTK3 en essayant les chemins système standard multi-résolutions ou le dossier local data/icons/.
    """
    for icon_path in [
        f"/usr/share/icons/hicolor/48x48/apps/{icon_name}.png",
        f"/usr/share/icons/hicolor/32x32/apps/{icon_name}.png",
        f"/usr/share/icons/hicolor/24x24/apps/{icon_name}.png",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), f"../icons/hicolor/48x48/apps/{icon_name}.png"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), f"../icons/{icon_name}.svg"),
    ]:
        if os.path.exists(icon_path):
            try:
                window.set_icon_from_file(icon_path)
                return
            except Exception:
                pass
    try:
        window.set_icon_name("audio-x-generic")
    except Exception:
        pass


def setup_window_geometry(window, base_width=920, base_height=620, min_width=750, min_height=480, max_ratio_w=0.90, max_ratio_h=0.85):
    """
    Calcule et applique une taille de fenêtre adaptative sans dépréciation GTK 3.22+.
    S'assure que la fenêtre reste contenue dans l'écran visible de l'utilisateur.
    """
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, Gdk

    geom = None
    try:
        display = Gdk.Display.get_default()
        if display:
            monitor = display.get_primary_monitor() or (display.get_monitor(0) if display.get_n_monitors() > 0 else None)
            if monitor:
                geom = monitor.get_geometry()
    except Exception:
        pass

    if geom is None:
        try:
            screen = Gdk.Screen.get_default()
            if screen:
                geom = screen.get_monitor_geometry(0)
        except Exception:
            pass

    target_w, target_h = base_width, base_height
    if geom:
        max_w = int(geom.width * max_ratio_w)
        max_h = int(geom.height * max_ratio_h)
        target_w = min(target_w, max_w)
        target_h = min(target_h, max_h)

    window.set_default_size(max(target_w, min_width), max(target_h, min_height))
    window.set_position(Gtk.WindowPosition.CENTER)


def atomic_write_file(path, content, encoding="utf-8"):
    """
    Écriture atomique et sûre sur disque selon la norme POSIX.
    Écrit d'abord dans un fichier temporaire adjacent (.tmp), force la synchronisation
    physique (flush + fsync), puis renomme de façon atomique via os.replace.
    """
    abs_path = os.path.abspath(os.path.expanduser(path))
    parent_dir = os.path.dirname(abs_path)
    if parent_dir and not os.path.exists(parent_dir):
        os.makedirs(parent_dir, exist_ok=True)

    tmp_path = abs_path + ".tmp"
    with open(tmp_path, "w", encoding=encoding) as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())

    os.replace(tmp_path, abs_path)


def apply_timonde_menu_css():
    """Injecte la feuille de style GTK3 pour hiérarchiser visuellement l'en-tête 'En écoute'."""
    global _MENU_CSS_APPLIED
    if _MENU_CSS_APPLIED:
        return
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk, Gdk

        # Détection dynamique du contraste du menu pour garantir une flèche éclatante
        suffix = ""
        try:
            test_m = Gtk.Menu()
            test_mi = Gtk.MenuItem(label="t")
            test_m.append(test_mi)
            test_m.show_all()
            fg = test_mi.get_style_context().get_color(Gtk.StateFlags.NORMAL)
            lum = (fg.red * 0.299 + fg.green * 0.587 + fg.blue * 0.114)
            if lum < 0.45:
                suffix = "-dark"
            test_m.destroy()
        except Exception:
            pass

        # Flèches de sous-menus : certains packs d'icônes (ex. Qogir sous antiX) fournissent
        # pan-end-symbolic en PNG gris fixe, invisible sur fond sombre. On impose notre SVG.
        # Si le SVG est absent, aucune règle n'est émise : la flèche du thème reste en place.
        icon_dirs = [
            "/usr/share/timonde/icons",
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "icons"),
        ]
        arrow_css = ""
        for direction, name in (("ltr", "pan-end-symbolic"), ("rtl", "pan-end-symbolic-rtl")):
            svg = next((os.path.join(d, f"{name}{suffix}.svg") for d in icon_dirs
                        if os.path.exists(os.path.join(d, f"{name}{suffix}.svg"))), None)
            if svg:
                arrow_css += (
                    f"menu menuitem arrow:dir({direction}), .menu menuitem arrow:dir({direction}) {{\n"
                    f"    min-width: 16px;\n    min-height: 16px;\n"
                    f"    -gtk-icon-source: url(\"{svg}\");\n}}\n"
                )

        # Rappel : GTK3 rejette TOUTE la feuille à la moindre propriété inconnue
        # (ex. width/height n'existent pas, seulement min-width/min-height).
        provider = Gtk.CssProvider()
        provider.load_from_data(f"""
        menu separator, menuitem.separator {{
            min-height: 2px;
            margin: 4px 8px;
            background-color: alpha(currentColor, 0.28);
        }}
        menuitem.timonde-header-action {{
            background-color: alpha(@theme_selected_bg_color, 0.14);
            border-radius: 2px;
            padding-top: 5px;
            padding-bottom: 5px;
        }}
        menuitem.timonde-info-time,
        menuitem.timonde-info-time:disabled {{
            background-color: alpha(currentColor, 0.08);
            border-left: 3px solid @theme_selected_bg_color;
            color: inherit;
            opacity: 0.92;
            padding-top: 3px;
            padding-bottom: 3px;
        }}
        menuitem.timonde-info-time label,
        menuitem.timonde-info-time:disabled label {{
            color: inherit;
        }}
        menuitem.timonde-info-track,
        menuitem.timonde-info-track:disabled {{
            background-color: alpha(currentColor, 0.08);
            border-left: 3px solid @theme_selected_bg_color;
            color: inherit;
            opacity: 0.95;
            padding-top: 3px;
            padding-bottom: 4px;
        }}
        menuitem.timonde-info-track label,
        menuitem.timonde-info-track:disabled label {{
            color: inherit;
            font-style: italic;
            font-weight: bold;
        }}
        menuitem.timonde-sep-header,
        menuitem.timonde-sep-header:disabled {{
            color: inherit;
            opacity: 0.75;
        }}
        {arrow_css}
        /* Icones de menu : heritent de la couleur du texte et restent parfaitement lisibles */
        menu menuitem image,
        menuitem image,
        menu image {{
            color: inherit;
            opacity: 0.90;
        }}
        menu menuitem:hover image,
        menuitem:hover image {{
            color: inherit;
            opacity: 1.0;
        }}
        """.encode("utf-8"))
        screen = Gdk.Screen.get_default()
        if screen:
            Gtk.StyleContext.add_provider_for_screen(
                screen,
                provider,
                Gtk.STYLE_PROVIDER_PRIORITY_USER
            )
            _MENU_CSS_APPLIED = True
    except Exception as e:
        sys.stderr.write(f"TiMonde: CSS du menu rejeté par GTK : {e}\n")


def status_markup(text: str, kind: str = "ok", with_bullet: bool = False, bold: bool = False) -> str:
    """
    Génère un balisage Pango harmonisé pour les indicateurs d'état et de santé des flux,
    garantissant un contraste optimal sur thèmes GTK clairs et sombres.
    """
    kind_lower = (kind or "ok").lower()
    palette = {
        "ok": "#2ecc71",
        "online": "#2ecc71",
        "success": "#2ecc71",
        "new": "#2ecc71",
        "warn": "#f39c12",
        "warning": "#f39c12",
        "geo": "#f39c12",
        "geoblocked": "#f39c12",
        "error": "#e74c3c",
        "offline": "#e74c3c",
        "dead": "#e74c3c",
        "muted": "#888888",
        "dim": "#888888",
        "info": "#3498db",
        "untested": "#888888",
    }
    color = palette.get(kind_lower, "#888888")
    escaped = html.escape(str(text))
    content = f"<b>{escaped}</b>" if bold else escaped
    if with_bullet:
        return f'<span foreground="{color}"><b>●</b> {content}</span>'
    return f'<span foreground="{color}">{content}</span>'


_APP_CSS_APPLIED = False

def apply_timonde_app_css():
    """Injecte un style GTK3 sobre et cohérent, respectant strictement le thème système (clair/sombre)."""
    global _APP_CSS_APPLIED
    if _APP_CSS_APPLIED:
        return
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk, Gdk
        provider = Gtk.CssProvider()
        provider.load_from_data(b"""
        .timonde-status-ok { color: #2ecc71; }
        .timonde-status-warn { color: #f39c12; }
        .timonde-status-error { color: #e74c3c; }
        .timonde-status-muted { color: alpha(@theme_fg_color, 0.65); }
        treeview.timonde-tree {
            border-radius: 3px;
        }
        """)
        screen = Gdk.Screen.get_default()
        if screen:
            Gtk.StyleContext.add_provider_for_screen(
                screen,
                provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
            _APP_CSS_APPLIED = True
    except Exception as e:
        sys.stderr.write(f"TiMonde: CSS applicatif rejeté par GTK : {e}\n")


def _find_label_widget(widget):
    """Recherche récursivement le label de texte principal d'un Gtk.MenuItem."""
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    if isinstance(widget, (Gtk.AccelLabel, Gtk.Label)):
        return widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            found = _find_label_widget(child)
            if found is not None:
                return found
    return None


_RECOLORED_ICONS_CACHE = {}

def get_recolored_menu_pixbuf(icon_name: str, fg_rgba, size_px: int = 16):
    """
    Charge une icône et recolorise directement ses canaux RVB selon la couleur du texte du menu,
    en conservant intact son canal alpha (antialiasing).
    Garantit un contraste parfait même lorsque le pack d'icônes fournit des PNG matriciels fixes.
    """
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import Gtk, GdkPixbuf, GLib

    r = int(getattr(fg_rgba, "red", 1.0) * 255)
    g = int(getattr(fg_rgba, "green", 1.0) * 255)
    b = int(getattr(fg_rgba, "blue", 1.0) * 255)
    cache_key = (icon_name, r, g, b, size_px)
    if cache_key in _RECOLORED_ICONS_CACHE:
        return _RECOLORED_ICONS_CACHE[cache_key]

    theme = Gtk.IconTheme.get_default()
    if not theme:
        return None

    clean_name = icon_name.replace("-symbolic", "")
    candidates = [f"{clean_name}-symbolic", clean_name]
    icon_info = None
    for cand in candidates:
        if theme.has_icon(cand):
            icon_info = theme.lookup_icon(cand, size_px, 0)
            if icon_info:
                break

    if not icon_info:
        return None

    try:
        pix = icon_info.load_icon()
        if not pix:
            return None

        if pix.get_width() != size_px or pix.get_height() != size_px:
            pix = pix.scale_simple(size_px, size_px, GdkPixbuf.InterpType.BILINEAR)

        if not pix.get_has_alpha():
            pix = pix.add_alpha(False, 0, 0, 0)

        w, h = pix.get_width(), pix.get_height()
        rowstride = pix.get_rowstride()
        n_channels = pix.get_n_channels()
        data = bytearray(pix.get_pixels())

        for y in range(h):
            for x in range(w):
                idx = y * rowstride + x * n_channels
                data[idx] = r
                data[idx + 1] = g
                data[idx + 2] = b

        recolored = GdkPixbuf.Pixbuf.new_from_bytes(
            GLib.Bytes.new(bytes(data)),
            pix.get_colorspace(),
            True,
            pix.get_bits_per_sample(),
            w,
            h,
            rowstride
        )
        _RECOLORED_ICONS_CACHE[cache_key] = recolored
        return recolored
    except Exception:
        return None


def _find_and_convert_images(widget, fg_rgba):
    """Recherche récursivement tous les Gtk.Image et leur injecte le Pixbuf recolorisé contrasté."""
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    if isinstance(widget, Gtk.Image):
        try:
            orig_name = getattr(widget, "_timonde_orig_icon", None)
            if not orig_name:
                icon_info = widget.get_icon_name()
                if icon_info and icon_info[0]:
                    orig_name = icon_info[0]
                    widget._timonde_orig_icon = orig_name

            if orig_name:
                pix = get_recolored_menu_pixbuf(orig_name, fg_rgba, size_px=16)
                if pix:
                    widget.set_from_pixbuf(pix)
        except Exception:
            pass
    elif isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            _find_and_convert_images(child, fg_rgba)


def style_dbusmenu_gtk(menu, is_root=True):
    """
    Parcourt un DbusmenuGtk3.Menu pour :
    - Corriger les séparateurs libdbusmenu ("Label Empty")
    - Mettre en gras l'action principale de la station en tête
    - Appliquer un fond distinct et une taille adaptée à la ligne d'heure locale
    - Mettre en italique avec fond distinct le titre du morceau en cours (♪)
    - Garantir la netteté et le contraste des icônes symboliques
    """
    if not menu:
        return
    apply_timonde_menu_css()
    try:
        import html
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk, Gdk

        ctx_menu = menu.get_style_context()
        fg_rgba = None
        try:
            fg_rgba = ctx_menu.get_color(Gtk.StateFlags.NORMAL)
        except Exception:
            pass
        if not fg_rgba:
            fg_rgba = Gdk.RGBA(0.96, 0.96, 0.96, 1.0)

        children = menu.get_children()
        for idx, child in enumerate(children):
            if isinstance(child, Gtk.SeparatorMenuItem):
                child.set_visible(True)
                continue
            if not isinstance(child, Gtk.MenuItem):
                continue

            # Conversion et recoloration immédiate des icônes du menuitem
            child_fg = None
            try:
                child_fg = child.get_style_context().get_color(Gtk.StateFlags.NORMAL)
            except Exception:
                pass
            _find_and_convert_images(child, child_fg or fg_rgba)

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
                if not getattr(sub, "_timonde_show_connected", False):
                    try:
                        sub.connect("show", lambda s: style_dbusmenu_gtk(s, is_root=False))
                        sub._timonde_show_connected = True
                    except Exception:
                        pass
    except Exception as e:
        sys.stderr.write(f"TiMonde: erreur de stylisation du menu : {e}\n")


# -----------------------------------------------------------------------------
# 7. Vérification HTTP & Lecteur de Pré-écoute GStreamer (StreamPreviewPlayer)
# -----------------------------------------------------------------------------



def call_timonde_mpris(method_name: str, *args, fallback_cli: list = None, timeout: float = 5.0):
    """
    Exécute un appel unifié vers TiMonde via D-Bus MPRIS (priorité 1),
    avec repli automatique et transparent vers la CLI timonde (priorité 2).
    Retourne (succès: bool, résultat: any).
    """
    # 1. Tentative D-Bus si le bus de session est disponible
    try:
        import dbus
        bus = dbus.SessionBus()
        if bus.name_has_owner("org.mpris.MediaPlayer2.timonde"):
            obj = bus.get_object("org.mpris.MediaPlayer2.timonde", "/org/mpris/MediaPlayer2")
            player = dbus.Interface(obj, "org.mpris.MediaPlayer2.Player")
            method = getattr(player, method_name, None)
            if method:
                res = method(*args)
                return True, res
    except Exception:
        pass

    # 2. Repli transparent via CLI si des arguments CLI sont spécifiés
    if fallback_cli:
        timonde_bin = find_timonde_binary() or "timonde"
        try:
            cmd = [timonde_bin] + fallback_cli
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
            if proc.returncode == 0:
                return True, proc.stdout.strip()
        except Exception:
            pass

    return False, None


class StreamPreviewPlayer:
    """
    Lecteur d'aperçu audio déporté vers le moteur natif Rust (Option B).
    Éradication totale de GStreamer côté Python : délègue la lecture et l'arrêt
    au serveur TiMonde (via D-Bus ou CLI timonde).
    """
    def __init__(self, on_status_changed=None, on_status_change=None):
        self.on_status_changed = on_status_changed or on_status_change
        self.current_url = None
        self.current_name = None
        self.is_playing = False

    def _emit_status(self, playing, message, is_error=False):
        if self.on_status_changed:
            try:
                from gi.repository import GLib
                GLib.idle_add(self.on_status_changed, playing, self.current_url or "", message, is_error)
            except Exception:
                pass

    def toggle(self, station_name, url=None):
        if url is None:
            url = station_name
            station_name = _("Radio")
        clean = clean_stream_url(url)
        if not clean:
            self._emit_status(False, f"[!] {_('Empty stream URL')}", is_error=True)
            return False
        if self.is_playing and self.current_url == clean:
            self.stop()
            return False
        return self.play(station_name, clean)

    def play(self, station_name, url=None):
        if url is None:
            url = station_name
            station_name = _("Radio")
        clean = clean_stream_url(url)
        if not clean:
            self._emit_status(False, f"[!] {_('Empty stream URL')}", is_error=True)
            return False

        self.stop(silent=True)
        self.current_url = clean
        self.current_name = station_name or _("Radio")
        self.is_playing = True
        self._emit_status(True, f"[►] {_('Playing:')} « {self.current_name} »", is_error=False)

        def run_play():
            disp_name = self.current_name or ""
            call_timonde_mpris("PlayPreview", clean, disp_name, fallback_cli=["--preview-play", clean, disp_name])

        import threading
        threading.Thread(target=run_play, daemon=True).start()
        return True

    def stop(self, silent=False):
        was_playing = self.is_playing
        self.is_playing = False
        self.current_url = None
        self.current_name = None

        def run_stop():
            call_timonde_mpris("StopPreview", fallback_cli=["--preview-stop"])

        import threading
        threading.Thread(target=run_stop, daemon=True).start()
        if was_playing and not silent:
            self._emit_status(False, "", is_error=False)


def find_script(script_name: str):
    """Localise un script Python compagnon dans les répertoires standards ou locaux."""
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), script_name),
        os.path.join("/usr/share/timonde/scripts", script_name),
        os.path.join("/usr/local/share/timonde/scripts", script_name),
        os.path.expanduser(f"~/.local/share/timonde/scripts/{script_name}"),
        f"data/scripts/{script_name}"
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


# -----------------------------------------------------------------------------
# 8. API Radio-Browser & Boîte de Dialogue de Réparation de Flux
# -----------------------------------------------------------------------------

import urllib.request
import urllib.parse
import json
from concurrent.futures import ThreadPoolExecutor

RADIO_BROWSER_ENDPOINTS = [
    "https://de1.api.radio-browser.info",
    "https://nl1.api.radio-browser.info",
    "https://at1.api.radio-browser.info",
]


def query_radio_browser(endpoint, path, params):
    """Interroge l'annuaire Radio-Browser API de façon sécurisée avec TIMONDE_USER_AGENT."""
    query_str = urllib.parse.urlencode(params)
    url = f"{endpoint}/json/{path}?{query_str}"
    req = urllib.request.Request(url, headers={"User-Agent": TIMONDE_USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            if resp.getcode() == 200:
                data = json.loads(resp.read().decode("utf-8"))
                # Promotion du miroir actif en tête de liste pour accélérer les requêtes suivantes
                if endpoint in RADIO_BROWSER_ENDPOINTS and RADIO_BROWSER_ENDPOINTS[0] != endpoint:
                    try:
                        RADIO_BROWSER_ENDPOINTS.remove(endpoint)
                        RADIO_BROWSER_ENDPOINTS.insert(0, endpoint)
                    except Exception:
                        pass
                return data
    except Exception:
        pass
    return None


def search_radio_browser_api(name="", country_code="", tag="", language="", limit=30):
    """
    Recherche multicritères sur les miroirs Radio-Browser en déléguant au moteur Rust
    de TiMonde (bascule de miroir automatique, gestion du cache et typage strict).
    """
    timonde_bin = shutil.which("timonde") or os.path.expanduser("~/.local/bin/timonde")
    if os.path.exists(timonde_bin):
        cmd = [timonde_bin, "--search"]
        if name and name.strip():
            cmd.append(name.strip())
        if tag and tag.strip():
            cmd.extend(["--tag", tag.strip()])
        if country_code and country_code.strip():
            cmd.extend(["--country", country_code.strip()])
        if language and language.strip():
            cmd.extend(["--lang", language.strip()])
        if limit:
            cmd.extend(["--limit", str(limit)])
        cmd.append("--json")

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10.0)
            if res.returncode == 0 and res.stdout.strip():
                return json.loads(res.stdout)
        except Exception:
            pass

    # Fallback minimal direct en cas d'absence du binaire
    params = {"limit": str(limit), "hidebroken": "true", "order": "votes", "reverse": "true"}
    if name: params["name"] = name
    if country_code:
        cc_up = country_code.strip().upper()
        params["countrycode"] = "GB" if cc_up == "UK" else cc_up
    if tag: params["tag"] = tag
    if language: params["language"] = language.strip().lower()

    for ep in RADIO_BROWSER_ENDPOINTS:
        res = query_radio_browser(ep, "stations/search", params)
        if res is not None:
            return res
    return []


def lookup_station_by_url(stream_url: str):
    """
    Vérifie si une URL de flux (ou sa version nettoyée sans paramètres '?') est déjà répertoriée sur Radio-Browser.
    Retourne la station distante (dict) si trouvée, ou None.
    """
    if not stream_url or not stream_url.strip():
        return None
    clean = stream_url.strip()
    clean_no_query = clean.split("?")[0].strip()

    urls_to_test = [clean]
    if clean_no_query != clean:
        urls_to_test.append(clean_no_query)

    for ep in RADIO_BROWSER_ENDPOINTS:
        for u in urls_to_test:
            res = query_radio_browser(ep, "stations/byurl", {"url": u})
            if res and isinstance(res, list) and len(res) > 0:
                return res[0]
    return None


def contribute_station_to_radio_browser(name, url, country_code="", language="", tags="", homepage="", favicon=""):
    """
    Soumet une nouvelle radio à Radio-Browser via POST /json/add après vérification d'unicité.
    Retourne un tuple (success: bool, message: str, station_info: dict ou None).
    """
    if not name or not name.strip():
        return (False, _("Station name cannot be empty"), None)
    if not url or not url.strip():
        return (False, _("Stream URL cannot be empty"), None)

    clean_name = name.strip()
    clean_url = url.strip()

    # 1. Vérification préalable d'existence pour éviter les rejets serveur
    existing = lookup_station_by_url(clean_url)
    if existing:
        ex_name = existing.get("name", _("Unknown"))
        return (
            False,
            _("This stream URL is already registered on Radio-Browser as '{existing_name}'.").format(
                existing_name=ex_name
            ),
            existing
        )

    # 2. Préparation du payload
    payload = {
        "name": clean_name,
        "url": clean_url,
    }
    if country_code:
        cc_up = country_code.strip().upper()
        payload["countrycode"] = "GB" if cc_up == "UK" else cc_up
    if language:
        payload["language"] = language.strip().lower()
    if tags:
        payload["tags"] = tags.strip()
    if homepage:
        payload["homepage"] = homepage.strip()
    if favicon:
        payload["favicon"] = favicon.strip()

    # 3. Envoi POST aux miroirs
    post_data = json.dumps(payload).encode("utf-8")
    for ep in RADIO_BROWSER_ENDPOINTS:
        req = urllib.request.Request(
            f"{ep}/json/add",
            data=post_data,
            headers={
                "User-Agent": TIMONDE_USER_AGENT,
                "Content-Type": "application/json",
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                if resp.getcode() in (200, 201):
                    res_json = json.loads(resp.read().decode("utf-8"))
                    if isinstance(res_json, dict) and res_json.get("ok"):
                        msg_ok = _("Station successfully submitted to Radio-Browser.")
                        return (True, msg_ok, res_json)
                    msg_srv = res_json.get("message", _("Failed to add station")) if isinstance(res_json, dict) else _("Unknown error")
                    return (False, msg_srv, None)
        except urllib.error.HTTPError as e:
            try:
                err_body = json.loads(e.read().decode("utf-8"))
                err_msg = err_body.get("message", str(e))
            except Exception:
                err_msg = str(e)
            return (False, _("Server rejected submission: {error}").format(error=err_msg), None)
        except Exception:
            continue

    return (False, _("Radio-Browser servers unreachable"), None)


def show_group_naming_help_dialog(parent):
    """Affiche la boîte de dialogue modale d'aide sur la convention Linux des groupes /."""
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk
    except (ImportError, ValueError):
        return

    dialog = Gtk.MessageDialog(
        transient_for=parent,
        flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
        type=Gtk.MessageType.INFO,
        buttons=Gtk.ButtonsType.OK,
        message_format=_("Organizing groups and subgroups (Linux convention)")
    )
    dialog.format_secondary_markup(
        _("TiMonde uses path conventions with the <b>/</b> separator:\n\n"
          "• <b>/</b> or <b>(Root)</b> : Places the station at the root of the menu (without group).\n"
          "• <b>/Gabon</b> or <b>Gabon</b> : Places the station in group « Gabon ».\n"
          "• <b>/France/Brittany</b> : Places the station in subgroup « Brittany » under « France ».\n"
          "• <b>/Belgium/NL</b> : Places the station in subgroup « NL » under « Belgium ».\n"
          "• <b>France/Local Radios</b> : Subgroup with spaces under « France ».\n\n"
          "<i>Groups and subgroups are automatically created if they do not exist yet.</i>")
    )
    dialog.connect("response", lambda d, r: d.destroy())
    dialog.show_all()


try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, GLib
    _GtkDialogBase = Gtk.Dialog
except (ImportError, ValueError):
    _GtkDialogBase = object


class RepairStreamDialog(_GtkDialogBase):
    """Boîte de dialogue partagée de recherche et réparation de flux radio via Radio-Browser."""

    def __init__(self, parent, station_name, current_url, country_code=""):
        if _GtkDialogBase is object:
            raise RuntimeError("GTK 3.0 n'est pas disponible pour afficher ce dialogue.")

        from gi.repository import Gtk, GLib
        super().__init__(
            title=f"{_('Replace stream:')} {station_name}",
            transient_for=parent,
            modal=True,
        )
        self.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        self.add_button(_("Validate and replace"), Gtk.ResponseType.OK)
        self.set_default_size(720, 420)
        self.set_border_width(10)
        self.station_name = station_name
        self.country_code = country_code
        self.selected_url = None

        content = self.get_content_area()
        content.set_spacing(10)

        # En-tête explicatif
        url_snippet = (current_url[:65] + "...") if len(current_url) > 65 else current_url
        orig_title = _("Original stream is unreachable:")
        select_subtitle = _("Select a verified replacement stream from Radio-Browser:")
        info_lbl = Gtk.Label(
            label=f"<b>{orig_title}</b>\n"
                  f"<small><tt>{html.escape(url_snippet)}</tt></small>\n\n"
                  f"{select_subtitle}"
        )
        info_lbl.set_use_markup(True)
        info_lbl.set_halign(Gtk.Align.START)
        content.pack_start(info_lbl, False, False, 0)

        # Barre de recherche
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        content.pack_start(search_box, False, False, 0)

        self.entry_query = Gtk.Entry()
        self.entry_query.set_text(station_name)
        self.entry_query.set_hexpand(True)
        self.entry_query.connect("activate", lambda w: self.perform_search())
        search_box.pack_start(self.entry_query, True, True, 0)

        btn_search = make_btn(_("Search"), "system-search")
        btn_search.connect("clicked", lambda w: self.perform_search())
        search_box.pack_start(btn_search, False, False, 0)

        # Liste des résultats: [name, codec, bitrate, country, url, votes]
        self.store = Gtk.ListStore(str, str, str, str, str, int)
        self.tree = Gtk.TreeView(model=self.store)

        col_name = Gtk.TreeViewColumn(_("Station"), Gtk.CellRendererText(), text=0)
        col_name.set_expand(True)
        self.tree.append_column(col_name)

        col_codec = Gtk.TreeViewColumn(_("Format"), Gtk.CellRendererText(), text=1)
        self.tree.append_column(col_codec)

        col_bitrate = Gtk.TreeViewColumn(_("Bitrate"), Gtk.CellRendererText(), text=2)
        self.tree.append_column(col_bitrate)

        col_country = Gtk.TreeViewColumn(_("Country"), Gtk.CellRendererText(), text=3)
        self.tree.append_column(col_country)

        col_votes = Gtk.TreeViewColumn(_("Popularity"), Gtk.CellRendererText(), text=5)
        self.tree.append_column(col_votes)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_shadow_type(Gtk.ShadowType.IN)
        scroll.add(self.tree)
        content.pack_start(scroll, True, True, 0)

        self.lbl_status = Gtk.Label(label=_("Searching for streams..."))
        self.lbl_status.set_halign(Gtk.Align.START)
        content.pack_start(self.lbl_status, False, False, 0)

        self.show_all()
        GLib.idle_add(self.perform_search)

    def perform_search(self):
        from gi.repository import GLib
        query = self.entry_query.get_text().strip()
        self.lbl_status.set_text(_("Searching on Radio-Browser..."))
        self.store.clear()

        def worker():
            results = search_radio_browser_api(name=query, country_code=self.country_code, limit=20)
            if not results and self.country_code:
                results = search_radio_browser_api(name=query, limit=20)

            def on_done():
                if not results:
                    self.lbl_status.set_text(_("No stream found for this name. Modify the text above."))
                    return
                for r in results:
                    name = r.get("name", "Sans nom")
                    codec = r.get("codec", "MP3")
                    bitrate = f"{r.get('bitrate', 128)} kbps" if r.get('bitrate') else "-"
                    country = r.get("country", "")
                    url = r.get("url_resolved") or r.get("url", "")
                    votes = r.get("votes", 0)
                    self.store.append([name, codec, bitrate, country, url, votes])
                self.lbl_status.set_text(_("{count} streams found. Select the desired stream and validate.").format(count=len(results)))
                it = self.store.get_iter_first()
                if it:
                    self.tree.get_selection().select_iter(it)

            GLib.idle_add(on_done)

        ThreadPoolExecutor(max_workers=1).submit(worker)

    def get_chosen_url(self):
        model, tree_iter = self.tree.get_selection().get_selected()
        if tree_iter:
            return model[tree_iter][4]
        return None


def prompt_text_dialog(parent_window, title: str, label_text: str, default_text: str = "", ok_label: str = None, callback = None) -> str:
    """
    Dialogue modal léger GTK3 de saisie textuelle unifié.
    Si callback est fourni, fonctionne en mode non-bloquant asynchrone (retourne None).
    Sinon, retourne la chaîne saisie ou None si annulé (mode synchrone hérité).
    """
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk

    dlg = Gtk.Dialog(
        title=title,
        transient_for=parent_window,
        flags=Gtk.DialogFlags.MODAL
    )
    dlg.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
    dlg.add_button(ok_label or _("OK"), Gtk.ResponseType.OK)
    dlg.set_default_response(Gtk.ResponseType.OK)

    box = dlg.get_content_area()
    box.set_spacing(10)
    box.set_border_width(12)

    lbl = Gtk.Label()
    lbl.set_markup(label_text)
    lbl.set_halign(Gtk.Align.START)
    box.pack_start(lbl, False, False, 0)

    entry = Gtk.Entry()
    entry.set_text(default_text or "")
    entry.set_width_chars(35)
    entry.set_activates_default(True)
    box.pack_start(entry, False, False, 0)

    if callback is not None:
        def on_response(d, resp):
            txt = entry.get_text().strip()
            d.destroy()
            if resp == Gtk.ResponseType.OK:
                callback(txt)
            else:
                callback(None)

        dlg.connect("response", on_response)
        dlg.show_all()
        return None

    dlg.show_all()
    resp = dlg.run()
    txt = entry.get_text().strip()
    dlg.destroy()

    if resp == Gtk.ResponseType.OK:
        return txt
    return None


class ContributeStationDialog(_GtkDialogBase):
    """Boîte de dialogue universelle de vérification et contribution de radios vers Radio-Browser."""

    def __init__(self, parent, station_name="", current_url="", country_code="", tags="", homepage=""):
        if _GtkDialogBase is object:
            raise RuntimeError("GTK 3.0 n'est pas disponible pour afficher ce dialogue.")

        from gi.repository import Gtk, GLib
        import html
        import threading

        super().__init__(
            title=_("Contribute to Radio-Browser"),
            transient_for=parent,
            modal=True,
        )
        self.set_default_size(580, 360)
        self.set_border_width(12)

        self.station_name = (station_name or "").strip()
        self.current_url = (current_url or "").strip()
        self.country_code = (country_code or "").strip().upper()
        self.tags = (tags or "").strip()
        self.homepage = (homepage or "").strip()
        self.existing_info = None

        content = self.get_content_area()
        content.set_spacing(10)

        # En-tête explicatif
        self.lbl_header = Gtk.Label()
        self.lbl_header.set_markup(
            f"<b>{_('Contribute a station to the community Radio-Browser directory')}</b>\n"
            f"<small><i>{_('Radio-Browser is an open directory (+45 000 stations). Shared stations benefit all users.')}</i></small>"
        )
        self.lbl_header.set_halign(Gtk.Align.START)
        content.pack_start(self.lbl_header, False, False, 0)

        # Formulaire
        grid = Gtk.Grid()
        grid.set_column_spacing(12)
        grid.set_row_spacing(8)
        content.pack_start(grid, True, True, 0)

        # 1. Nom
        lbl_name = Gtk.Label(label=_("Station name:"))
        lbl_name.set_halign(Gtk.Align.END)
        grid.attach(lbl_name, 0, 0, 1, 1)

        self.entry_name = Gtk.Entry()
        self.entry_name.set_text(self.station_name)
        self.entry_name.set_hexpand(True)
        grid.attach(self.entry_name, 1, 0, 1, 1)

        # 2. URL
        lbl_url = Gtk.Label(label=_("Stream URL:"))
        lbl_url.set_halign(Gtk.Align.END)
        grid.attach(lbl_url, 0, 1, 1, 1)

        url_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.entry_url = Gtk.Entry()
        self.entry_url.set_text(self.current_url)
        self.entry_url.set_hexpand(True)
        url_box.pack_start(self.entry_url, True, True, 0)

        btn_check_again = make_btn(_("Check"), "view-refresh", _("Check entered stream URL again on Radio-Browser"))
        btn_check_again.connect("clicked", lambda w: self._start_lookup(self.entry_url.get_text().strip()))
        url_box.pack_start(btn_check_again, False, False, 0)

        grid.attach(url_box, 1, 1, 1, 1)

        # 3. Pays ISO
        lbl_cc = Gtk.Label(label=_("Country code (ISO):"))
        lbl_cc.set_halign(Gtk.Align.END)
        grid.attach(lbl_cc, 0, 2, 1, 1)

        self.entry_cc = Gtk.Entry()
        self.entry_cc.set_text(self.country_code)
        self.entry_cc.set_placeholder_text("Ex: FR, GP, MQ, GF, RE, YT, NC, PF, CA, BE...")
        grid.attach(self.entry_cc, 1, 2, 1, 1)

        # 4. Tags / Genres
        lbl_tags = Gtk.Label(label=_("Tags / Genres:"))
        lbl_tags.set_halign(Gtk.Align.END)
        grid.attach(lbl_tags, 0, 3, 1, 1)

        self.entry_tags = Gtk.Entry()
        self.entry_tags.set_text(self.tags)
        self.entry_tags.set_placeholder_text("Ex: news, talk, pop, zouk, kompa, rock...")
        grid.attach(self.entry_tags, 1, 3, 1, 1)

        # 5. Site Web
        lbl_hp = Gtk.Label(label=_("Website / Homepage:"))
        lbl_hp.set_halign(Gtk.Align.END)
        grid.attach(lbl_hp, 0, 4, 1, 1)

        self.entry_hp = Gtk.Entry()
        self.entry_hp.set_text(self.homepage)
        self.entry_hp.set_placeholder_text("https://...")
        grid.attach(self.entry_hp, 1, 4, 1, 1)

        # Zone d'information et de statut
        self.lbl_status = Gtk.Label(label="")
        self.lbl_status.set_use_markup(True)
        self.lbl_status.set_halign(Gtk.Align.START)
        self.lbl_status.set_no_show_all(True)
        content.pack_start(self.lbl_status, False, False, 0)

        # Boutons d'action intégrés (sans add_button pour ne pas fermer prématurément le dialogue sur soumission)
        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        content.pack_start(action_box, False, False, 4)

        self.btn_cancel = Gtk.Button(label=_("Close"))
        self.btn_cancel.connect("clicked", lambda w: self.response(Gtk.ResponseType.CLOSE))
        action_box.pack_start(self.btn_cancel, False, False, 0)

        self.btn_edit = Gtk.Button(label=_("Edit station"))
        self.btn_edit.connect("clicked", lambda w: self.response(Gtk.ResponseType.APPLY))
        self.btn_edit.set_no_show_all(True)
        self.btn_edit.hide()
        action_box.pack_start(self.btn_edit, False, False, 0)

        spacer = Gtk.Box()
        action_box.pack_start(spacer, True, True, 0)

        self.btn_submit = Gtk.Button(label=_("Submit to Radio-Browser"))
        self.btn_submit.get_style_context().add_class("suggested-action")
        self.btn_submit.connect("clicked", self._on_submit_clicked)
        action_box.pack_start(self.btn_submit, False, False, 0)

        self.connect("response", lambda d, r: self.hide())

        # Lancer la vérification initiale si une URL est présente
        if self.current_url:
            self._start_lookup(self.current_url)

        self.show_all()

    def _start_lookup(self, url_to_check):
        import html
        import threading
        from gi.repository import GLib

        if not url_to_check:
            self.lbl_status.set_markup(f"<small><span foreground='#e67e22'><b>{_('Please enter a stream URL.')}</b></span></small>")
            self.lbl_status.show()
            self.btn_submit.set_sensitive(False)
            return

        self.lbl_status.set_markup(f"<small><span foreground='#3498db'><b>{_('Checking Radio-Browser directory...')}</b></span></small>")
        self.lbl_status.show()
        self.btn_submit.set_sensitive(False)

        def _worker():
            res = lookup_station_by_url(url_to_check)
            GLib.idle_add(self._on_lookup_done, url_to_check, res)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_lookup_done(self, checked_url, existing):
        import html
        self.existing_info = existing
        if existing:
            ex_name = existing.get("name", _("Unknown"))
            ex_cc = existing.get("countrycode", _("Unknown"))
            self.lbl_status.set_markup(
                f"<small><span foreground='#2ecc71'><b>● {_('Already registered:')}</b></span> "
                f"« <b>{html.escape(ex_name)}</b> » ({_('Country:')} <b>{html.escape(ex_cc)}</b>)\n"
                f"<span foreground='#7f8c8d'><i>{_('Radio-Browser prevents duplicate stream URLs. No submission required.')}</i></span></small>"
            )
            self.btn_submit.set_sensitive(False)
            self.btn_submit.set_label(_("Already registered"))
            self.btn_edit.set_label(f"{_('Edit station')} ({ex_cc})")
            self.btn_edit.set_tooltip_text(_("Open editor to update this station and its country"))
            self.btn_edit.show()
        else:
            self.lbl_status.set_markup(
                f"<small><span foreground='#2980b9'><b>[+] {_('Not listed yet!')}</b></span> "
                f"{_('This stream URL is unpublished on Radio-Browser and ready to be contributed.')}</small>"
            )
            self.btn_submit.set_sensitive(True)
            self.btn_submit.set_label(_("Submit to Radio-Browser"))
            self.btn_edit.hide()
        self.lbl_status.show()

    def _on_submit_clicked(self, _button):
        from gi.repository import Gtk, GLib
        import threading
        import html

        name = self.entry_name.get_text().strip()
        url = clean_stream_url(self.entry_url.get_text().strip())
        cc = self.entry_cc.get_text().strip().upper()
        tags = self.entry_tags.get_text().strip()
        hp = self.entry_hp.get_text().strip()

        if not name or not url:
            self.lbl_status.set_markup(f"<small><span foreground='#e74c3c'><b>{_('Name and Stream URL are mandatory.')}</b></span></small>")
            self.lbl_status.show()
            return

        self.btn_submit.set_sensitive(False)
        self.btn_submit.set_label(_("Submitting..."))
        self.lbl_status.set_markup(f"<small><span foreground='#3498db'><b>{_('Submitting station to Radio-Browser...')}</b></span></small>")
        self.lbl_status.show()

        def _sub_worker():
            ok, msg, _info = contribute_station_to_radio_browser(
                name=name,
                url=url,
                country_code=cc,
                tags=tags,
                homepage=hp,
            )
            def _sub_done():
                if ok:
                    self.lbl_status.set_markup(f"<small><span foreground='#2ecc71'><b>● {html.escape(msg)}</b></span></small>")
                    self.lbl_status.show()
                    self.btn_submit.set_label(_("Submitted"))
                    self.btn_submit.set_sensitive(False)
                    self.btn_cancel.set_label(_("Close"))
                else:
                    self.lbl_status.set_markup(f"<small><span foreground='#e74c3c'><b>{html.escape(msg)}</b></span></small>")
                    self.lbl_status.show()
                    self.btn_submit.set_sensitive(True)
                    self.btn_submit.set_label(_("Submit to Radio-Browser"))
            GLib.idle_add(_sub_done)

        threading.Thread(target=_sub_worker, daemon=True).start()



