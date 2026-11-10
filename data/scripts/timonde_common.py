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

TIMONDE_VERSION = "0.2.7"
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
# 2. Exécution Sécurisée du Moteur Natif Rust (Anti-Boîte Noire & Dumb UI)
# -----------------------------------------------------------------------------

def run_timonde_cli(*args, input_text=None, input_data=None, timeout=5.0):
    """
    Exécute de manière standardisée et sécurisée une commande du binaire Rust 'timonde'.
    Retourne subprocess.CompletedProcess(stdout, stderr, returncode).
    """
    bin_path = find_timonde_binary() or "timonde"
    cmd = [bin_path] + [str(a) for a in args]
    stdin_str = input_text if input_text is not None else input_data
    return subprocess.run(
        cmd,
        input=stdin_str,
        capture_output=True,
        text=True,
        timeout=timeout
    )


def find_timonde_binary():
    """Localise le binaire officiel ou local de TiMonde."""
    env_bin = os.environ.get("TIMONDE_BIN")
    if env_bin and os.path.isfile(env_bin) and os.access(env_bin, os.X_OK):
        return env_bin

    root_cargo = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../Cargo.toml"))
    if os.path.exists(root_cargo):
        dev_rel = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../target/release/timonde"))
        dev_deb = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../target/debug/timonde"))
        rel_ok = os.path.isfile(dev_rel) and os.access(dev_rel, os.X_OK)
        deb_ok = os.path.isfile(dev_deb) and os.access(dev_deb, os.X_OK)
        if rel_ok and deb_ok:
            return dev_rel if os.path.getmtime(dev_rel) >= os.path.getmtime(dev_deb) else dev_deb
        if rel_ok:
            return dev_rel
        if deb_ok:
            return dev_deb

    for cand in (shutil.which("timonde"), os.path.expanduser("~/.local/bin/timonde"), "/usr/bin/timonde"):
        if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return None


def get_timonde_bin() -> str:
    """Retourne le chemin du binaire Rust ou lève RuntimeError si introuvable."""
    b = find_timonde_binary()
    if not b:
        raise RuntimeError(
            "Binaire TiMonde (Rust) introuvable. Veuillez compiler le projet ('cargo build --release') "
            "ou installer TiMonde dans votre PATH."
        )
    return b


def check_stream_url(url, timeout=3.0, with_redirect=False, fetch_meta=False):
    """
    Test universel, frugal et rapide de disponibilité d'un flux audio.
    Délègue exclusivement au moteur natif Rust (timonde --probe-stream).
    """
    meta = {"icy_name": "", "icy_genre": "", "icy_br": "", "content_type": ""}

    def _format_ret(st, m, rd=None):
        if fetch_meta:
            return (st, m, rd, meta) if with_redirect else (st, m, meta)
        return (st, m, rd) if with_redirect else (st, m)

    if not url or not url.strip():
        return _format_ret(False, _("Empty URL"))

    try:
        to_sec = str(max(1, int(round(timeout))))
        res = run_timonde_cli("--probe-stream", url.strip(), "--timeout", to_sec, "--json", timeout=timeout + 2.0)
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout)
            ok = data.get("ok", False)
            is_geo = data.get("is_geo", False)
            msg_raw = data.get("message", "")
            redir = data.get("redirected_url")
            raw_meta = data.get("meta", {})
            for k in meta:
                meta[k] = raw_meta.get(k, "")

            if is_geo:
                return _format_ret("GEO", _("Geoblocked (VPN)"), redir)
            if ok:
                codec = data.get("codec") or "Audio"
                return _format_ret(True, _("Live ({codec})").format(codec=codec), redir)
            msg = (
                _("Offline (HTML error page)") if "HTML" in msg_raw else
                _("Server unreachable") if "inaccessible" in msg_raw else
                _("Timeout") if "dépassé" in msg_raw else msg_raw
            )
            return _format_ret(False, msg, redir)
    except Exception as e:
        return _format_ret(False, str(e))

    return _format_ret(False, _("Check failed"))


# -----------------------------------------------------------------------------
# 3. Convention Linux pour les Groupes & Chemins (Arborescence '/')
# -----------------------------------------------------------------------------

def normalize_group_path(raw_path: str, return_root_literal: bool = False) -> str:
    """Normalise une chaîne de groupe selon la convention Linux avec slashes."""
    if not raw_path:
        return "root" if return_root_literal else ""
    s = raw_path.strip()
    if s in ("[ / ] (Racine — Sans groupe)", "/", "root", "(Racine)", "[/]"):
        return "root" if return_root_literal else ""
    cleaned = s.strip("/").strip()
    return cleaned if cleaned else ("root" if return_root_literal else "")


def get_user_bookmarks_groups(path=None):
    """Lit les groupes existants depuis bookmarks en déléguant au moteur natif Rust."""
    args = ["--dump-bookmarks-json"] + ([path] if path else [])
    try:
        res = run_timonde_cli(*args, timeout=3.0)
        if res.returncode == 0 and res.stdout.strip():
            groups = []
            for item in json.loads(res.stdout):
                g_name = item.get("name", "").strip()
                if g_name and g_name.lower() != "root" and not item.get("is_separator") and not g_name.startswith("[ / ]"):
                    cur = ""
                    for p in (p.strip() for p in g_name.split("/") if p.strip()):
                        cur = f"{cur}/{p}" if cur else p
                        if cur not in groups:
                            groups.append(cur)
            return groups
    except Exception as e:
        sys.stderr.write(f"Erreur lecture groupes via Rust : {e}\n")
    return []


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
    aliases_map = {}
    try:
        res = run_timonde_cli("--dump-countries-json", timeout=2.0)
        if res.returncode == 0 and res.stdout.strip():
            items = json.loads(res.stdout)
            db = [(it["code"], it["name"], it.get("flag", "")) for it in items]
            reg = {}
            for it in items:
                c_code, c_name, c_flag, c_aliases = it["code"], it["name"], it.get("flag", ""), it.get("aliases", [])
                reg[c_code] = (c_name, c_flag, c_aliases)
                aliases_map[c_code.lower()] = c_code
                aliases_map[normalize_lookup(c_name)] = c_code
                for al in c_aliases:
                    aliases_map[normalize_lookup(al)] = c_code
            return db, reg, aliases_map
    except Exception:
        pass
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

    m = re.search(r'[\[\(]([A-Za-z]{2})[\]\)]', q_str)
    if m:
        cand = m.group(1).upper()
        if cand in COUNTRIES_REGISTRY:
            _COUNTRY_RESOLVE_CACHE[q_str] = cand
            return cand

    norm = normalize_lookup(q_str)
    if norm in COUNTRY_ALIASES_MAP:
        code = COUNTRY_ALIASES_MAP[norm]
        _COUNTRY_RESOLVE_CACHE[q_str] = code
        return code

    try:
        res = run_timonde_cli("--resolve-country", q_str, timeout=2.0)
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



_INFER_TZ_CACHE = {}


def load_timezones_for_country(country_code=None):
    """Interroge le moteur Rust 'timonde --list-timezones' pour obtenir les fuseaux horaires d'un pays ou du monde."""
    args = ["--list-timezones"]
    if country_code:
        args.append(str(country_code).strip())
    try:
        res = run_timonde_cli(*args, timeout=2.0)
        if res.returncode == 0 and res.stdout.strip():
            items = json.loads(res.stdout)
            return [(it.get("timezone", ""), it.get("label", "")) for it in items]
    except Exception as e:
        sys.stderr.write(f"Erreur chargement fuseaux via Rust : {e}\n")
    return []


class _RustTimezonesDict(dict):
    """Accès dynamique aux fuseaux horaires délégué à Rust avec cache en mémoire."""
    def __init__(self):
        super().__init__()
        self._cache = {}

    def __getitem__(self, key):
        return self.get(key, [])

    def __contains__(self, key):
        return bool(self.get(key, []))

    def get(self, key, default=None):
        clean_key = (key or "").strip().upper()
        if clean_key not in self._cache:
            res = load_timezones_for_country(clean_key if clean_key else None)
            self._cache[clean_key] = res
        res = self._cache[clean_key]
        return res if res else (default if default is not None else [])


WORLD_TIMEZONES = _RustTimezonesDict()


def infer_timezone(country_code: str = "", station_name: str = "", group_path: str = "") -> str:
    """
    Infère intelligemment le fuseau horaire exact d'une station à partir de son pays ISO,
    son nom et son groupe/arborescence en déléguant au moteur Rust de TiMonde.
    """
    cc = (country_code or "").strip().upper()
    cache_key = (cc, station_name or "", group_path or "")
    if cache_key in _INFER_TZ_CACHE:
        return _INFER_TZ_CACHE[cache_key]

    try:
        res = run_timonde_cli("--infer-timezone", cc, station_name or "", group_path or "", timeout=2.0)
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout.strip())
            tz = data.get("timezone", "")
            if tz:
                _INFER_TZ_CACHE[cache_key] = tz
                return tz
    except Exception:
        pass

    # Fallback standard par pays via Rust
    tz_list = load_timezones_for_country(cc)
    if tz_list:
        return tz_list[0][0]

    return ""


def __getattr__(name):
    """Accès aux tables de fuseaux horaires délégué au moteur Rust."""
    if name == "DEFAULT_WORLD_TIMEZONES":
        return load_timezones_for_country(None)
    if name == "load_world_timezones":
        return lambda: WORLD_TIMEZONES
    if name in ("FRANCE_TIMEZONES", "CUSTOM_MULTI_TZ", "UK_TIMEZONES"):
        code = "FR" if name == "FRANCE_TIMEZONES" else ("GB" if name == "UK_TIMEZONES" else None)
        return load_timezones_for_country(code)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


_RB_LANG_SPECS = [
    ("afrikaans", "Afrikaans", "", []), ("albanian", "Albanais", "Shqip", ["shqip"]),
    ("amharic", "Amharique", "አማርኛ", []), ("arabic", "Arabe", "العربية", ["عربي", "moroccan arabic"]),
    ("armenian", "Arménien", "հայերեն", []), ("azerbaijani", "Azerbaïdjanais", "Azərbaycan", []),
    ("basque", "Basque", "Euskara", ["euskera"]), ("belarusian", "Biélorusse", "Беларуская", []),
    ("bengali", "Bengali", "বাংলা", ["bangla"]), ("bosnian", "Bosnien", "Bosanski", []),
    ("breton", "Breton", "Brezhoneg", []), ("bulgarian", "Bulgare", "Български", ["bulgaria"]),
    ("burmese", "Birman", "မြန်မာစာ", []), ("cantonese", "Cantonais", "粵語", []),
    ("catalan", "Catalan", "Català", ["catalán"]), ("chinese", "Chinois", "中文", ["汉语", "普通话", "国语", "mandarin", "china"]),
    ("corsican", "Corse", "Corsu", []), ("creole", "Créole", "", ["haitian creole"]),
    ("croatian", "Croate", "Hrvatski", ["croatia"]), ("czech", "Tchèque", "Čeština", ["cesky", "česky"]),
    ("danish", "Danois", "Dansk", []), ("dutch", "Néerlandais", "Nederlands", ["nederland", "flemish", "flammish"]),
    ("english", "Anglais", "English", ["american english", "english uk", "british english", "engilsh", "englsih", "englsh", "английский"]),
    ("esperanto", "Espéranto", "Esperanto", []), ("estonian", "Estonien", "Eesti", ["estonia"]),
    ("faroese", "Féroïen", "Føroyskt", []), ("filipino", "Philippin", "Tagalog", ["tagalog"]),
    ("finnish", "Finnois", "Suomi", ["suomi"]),
    ("french", "Français", "Français", ["francais", "francaise", "franch", "frances", "canadian french"]),
    ("galician", "Galicien", "Galego", ["galego"]), ("georgian", "Géorgien", "ქართული", []),
    ("german", "Allemand", "Deutsch", ["deutsch", "swiss german", "deutch", "low german", "gernan", "schweizerdeutsch"]),
    ("greek", "Grec", "Ελληνικά", ["ελληνικά"]), ("gujarati", "Gujarati", "ગુજરાતી", []),
    ("hausa", "Haoussa", "Hausa", []), ("hebrew", "Hébreu", "עברית", []),
    ("hindi", "Hindi", "हिन्दी", ["हिंदी", "hindu"]), ("hungarian", "Hongrois", "Magyar", ["magyar"]),
    ("icelandic", "Islandais", "Íslenska", []), ("indonesian", "Indonésien", "Bahasa Indonesia", ["bahasa indonesia"]),
    ("irish", "Irlandais", "Gaeilge", ["gaelic"]), ("italian", "Italien", "Italiano", ["italiano"]),
    ("japanese", "Japonais", "日本語", ["にほんご"]), ("javanese", "Javanais", "Basa Jawa", []),
    ("kannada", "Kannada", "ಕನ್ನಡ", []), ("kazakh", "Kazakh", "Қазақша", ["қазақша"]),
    ("khmer", "Khmer", "ភាសាខ្មែរ", []), ("korean", "Coréen", "한국어", []),
    ("kurdish", "Kurde", "Kurdî", ["کوردی", "kurdi"]), ("kyrgyz", "Kirghize", "Кыргызча", []),
    ("lao", "Lao", "ພາສາລາວ", []), ("latin", "Latin", "Latina", []),
    ("latvian", "Letton", "Latviešu", []), ("lithuanian", "Lituanien", "Lietuvių", []),
    ("luxembourgish", "Luxembourgeois", "Lëtzebuergesch", []), ("macedonian", "Macédonien", "Македонски", ["македонски"]),
    ("malagasy", "Malgache", "Malagasy", []), ("malay", "Malais", "Bahasa Melayu", []),
    ("malayalam", "Malayalam", "മലയാളം", []), ("maltese", "Maltais", "Malti", []),
    ("maori", "Maori", "Te Reo Māori", ["te reo"]), ("marathi", "Marathe", "मराठी", []),
    ("mongolian", "Mongol", "Монгол", ["монгол хэл"]), ("montenegrin", "Monténégrin", "Crnogorski", ["montenegro"]),
    ("nepali", "Népalais", "नेपाली", []), ("norwegian", "Norvégien", "Norsk", ["norsk"]),
    ("occitan", "Occitan", "Occitan", []), ("pashto", "Pachto", "پښتو", []),
    ("persian", "Persan", "فارسی", ["پارسی"]), ("polish", "Polonais", "Polski", ["polski"]),
    ("portuguese", "Portugais", "Português", ["portugues", "brazilian portuguese", "pt-br", "portoguese"]),
    ("punjabi", "Pendjabi", "ਪੰਜਾਬੀ", ["پنجابی"]), ("quechua", "Quechua", "Runasimi", []),
    ("romanian", "Roumain", "Română", ["romana", "romania", "românä"]),
    ("russian", "Russe", "Русский", ["русский", "язык: русский", "ру", "rus"]),
    ("serbian", "Serbe", "Српски", ["српски"]), ("sinhala", "Cinghalais", "සිංහල", []),
    ("slovak", "Slovaque", "Slovenčina", []), ("slovenian", "Slovène", "Slovenščina", ["slovenski"]),
    ("spanish", "Espagnol", "Español", ["español", "castellano", "espanish", "espaňol", "españa"]),
    ("swahili", "Swahili", "Kiswahili", ["kiswahili"]), ("swedish", "Suédois", "Svenska", ["svenska"]),
    ("tajik", "Tadjik", "Тоҷикӣ", []), ("tamil", "Tamoul", "தமிழ்", []),
    ("tatar", "Tatar", "Татарча", []), ("telugu", "Télougou", "తెలుగు", []),
    ("thai", "Thaï", "ไทย", ["ภาษาไทย"]), ("tibetan", "Tibétain", "བོད་སྐད་", []),
    ("turkish", "Turc", "Türkçe", ["turkçe", "türkisch", "türkish"]),
    ("ukrainian", "Ukrainien", "Українська", ["українська", "ukranian", "украина"]),
    ("urdu", "Ourdou", "اردو", []), ("uzbek", "Ouzbek", "Oʻzbek", []),
    ("vietnamese", "Vietnamien", "Tiếng Việt", []), ("welsh", "Gallois", "Cymraeg", []),
    ("yiddish", "Yiddish", "ייִדיש", []), ("yoruba", "Yoruba", "Yorùbá", []),
]
RADIO_BROWSER_LANGUAGES = [(k, fr, 100) for k, fr, _nat, _al in _RB_LANG_SPECS]
DISPLAY_NATIVE_MAP = {k: nat for k, _fr, nat, _al in _RB_LANG_SPECS if nat}
NATIVE_LANGUAGE_NAMES = {k: ([nat] if nat else []) + al for k, _fr, nat, al in _RB_LANG_SPECS}
LANG_MAP_BY_NAME = {}
for _k, _fr, _nat, _al in _RB_LANG_SPECS:
    LANG_MAP_BY_NAME[normalize_lookup(_k)] = _k
    LANG_MAP_BY_NAME[normalize_lookup(_fr)] = _k
    if _nat:
        LANG_MAP_BY_NAME[normalize_lookup(_nat)] = _k
    for _a in _al:
        LANG_MAP_BY_NAME[normalize_lookup(_a)] = _k


def resolve_language_api_key(query: str) -> str:
    """Résout une saisie libre de langue en clé API Radio-Browser."""
    if not query:
        return ""
    q_str = query.strip()
    m = re.search(r'\(([^)]+)\)$', q_str)
    if m:
        return m.group(1).strip().lower()
    clean = normalize_lookup(q_str)
    if clean in LANG_MAP_BY_NAME:
        return LANG_MAP_BY_NAME[clean]
    for part in re.split(r'[\s—\-\(\)]+', q_str):
        cp = normalize_lookup(part)
        if cp and cp in LANG_MAP_BY_NAME:
            return LANG_MAP_BY_NAME[cp]
    for k, v in LANG_MAP_BY_NAME.items():
        if len(k) > 2 and (k.startswith(clean) or clean in k):
            return v
    return q_str.lower()



def attach_country_completion(entry, on_selected=None):
    """
    Attache un compléteur de pays universel (recherche par nom français, code ISO, ou alias sans accent)
    sur n'importe quel Gtk.Entry.
    """
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk

    comp_store = Gtk.ListStore(str, str, str, str)  # 0: display, 1: code, 2: norm_name, 3: norm_aliases
    for code, (cname, _flag, aliases) in sorted(COUNTRIES_REGISTRY.items(), key=lambda x: normalize_lookup(x[1][0])):
        norm_name = normalize_lookup(cname)
        norm_al = normalize_lookup(" ".join(aliases)) if aliases else ""
        disp = f"[{code}] {cname}"
        comp_store.append([disp, code, norm_name, norm_al])

    comp = Gtk.EntryCompletion()
    comp.set_model(comp_store)
    comp.set_text_column(0)
    comp.set_minimum_key_length(1)
    comp.set_inline_completion(False)
    comp.set_popup_completion(True)

    def match_func(completion, key, tree_iter, data):
        norm_key = normalize_lookup(key)
        if not norm_key:
            return False
        code = comp_store.get_value(tree_iter, 1)
        norm_name = comp_store.get_value(tree_iter, 2) or ""
        norm_al = comp_store.get_value(tree_iter, 3) or ""
        norm_code = code.lower()
        return (norm_key in norm_name) or (norm_key == norm_code) or norm_code.startswith(norm_key) or (norm_key in norm_al)

    comp.set_match_func(match_func, None)

    def match_selected(completion, model, tree_iter):
        c_code = model.get_value(tree_iter, 1)
        disp_name = model.get_value(tree_iter, 0)
        entry.set_text(disp_name)
        if on_selected:
            on_selected(c_code, disp_name)
        return True

    comp.connect("match-selected", match_selected)
    entry.set_completion(comp)
    return comp


class GroupSelectorBar:
    """
    Fabrique de barre unifiée de sélection de groupe cible avec autocomplétion, menu déroulant,
    et bouton d'aide syntaxique /.
    """
    @staticmethod
    def create(available_groups=None, default_group="", allow_original_structure=False, on_help_clicked=None, on_changed=None):
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk, Gdk

        groups_list = list(available_groups or [])
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        vbox.pack_start(hbox, False, False, 0)

        lbl = Gtk.Label(label="<b>" + _("Group:") + "</b>")
        lbl.set_use_markup(True)
        hbox.pack_start(lbl, False, False, 0)

        entry = Gtk.Entry()
        entry.set_text(default_group)
        entry.set_width_chars(26)
        entry.set_placeholder_text(_("Ex: /France/Jazz or / for root"))
        entry.set_can_focus(True)
        entry.set_editable(True)

        comp = Gtk.EntryCompletion()
        store = Gtk.ListStore(str)
        store.append(["[ / ] (Racine — Sans groupe)"])
        for g in sorted(groups_list):
            if g and g not in ("[ / ] (Racine — Sans groupe)", "/"):
                store.append([g])
        comp.set_model(store)
        comp.set_text_column(0)
        comp.set_inline_completion(True)
        comp.set_popup_completion(True)
        entry.set_completion(comp)

        entry.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, "edit-clear")
        entry.set_icon_tooltip_text(Gtk.EntryIconPosition.SECONDARY, _("Clear field"))
        entry.connect("icon-press", lambda e, pos, ev: e.set_text("") if pos == Gtk.EntryIconPosition.SECONDARY else None)
        if on_changed:
            entry.connect("changed", on_changed)
        hbox.pack_start(entry, True, True, 0)

        btn_choose = make_btn("", "pan-down", _("Choose from existing groups"))
        def on_choose(b):
            menu = Gtk.Menu()
            if allow_original_structure:
                it_orig = Gtk.MenuItem(label=_("(Original folder structure)"))
                it_orig.connect("activate", lambda mi: entry.set_text(_("(Original folder structure)")))
                menu.append(it_orig)
                menu.append(Gtk.SeparatorMenuItem())
            it_root = Gtk.MenuItem(label="[ / ] (Racine — Sans groupe)")
            it_root.connect("activate", lambda mi: entry.set_text("/"))
            menu.append(it_root)
            if groups_list:
                menu.append(Gtk.SeparatorMenuItem())
                for g in sorted(groups_list):
                    if g and g not in ("[ / ] (Racine — Sans groupe)", "/"):
                        item = Gtk.MenuItem(label=g)
                        item.connect("activate", lambda mi, grp=g: entry.set_text(grp))
                        menu.append(item)
            menu.show_all()
            menu.popup_at_widget(b, Gdk.Gravity.SOUTH_WEST, Gdk.Gravity.NORTH_WEST, None)
        btn_choose.connect("clicked", on_choose)
        hbox.pack_start(btn_choose, False, False, 0)

        btn_help = make_btn("", "help-browser", _("Help on groups and subgroups"))
        if on_help_clicked:
            btn_help.connect("clicked", lambda b: on_help_clicked())
        else:
            btn_help.connect("clicked", lambda b: show_group_naming_help_dialog(vbox.get_toplevel()))
        hbox.pack_start(btn_help, False, False, 0)

        vbox.entry = entry
        vbox.btn_choose = btn_choose
        vbox.btn_help = btn_help
        vbox.get_group_text = lambda: entry.get_text().strip()
        vbox.set_group_text = lambda txt: entry.set_text(txt)
        return vbox



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


def set_container_margins(widget, margin=None, top=None, bottom=None, start=None, end=None):
    """Applique les marges sur un widget ou conteneur GTK3 (compatible RTL/LTR)."""
    if margin is not None:
        top = margin if top is None else top
        bottom = margin if bottom is None else bottom
        start = margin if start is None else start
        end = margin if end is None else end
    for val, attr in ((top, "set_margin_top"), (bottom, "set_margin_bottom"), (start, "set_margin_start"), (end, "set_margin_end")):
        if val is not None and hasattr(widget, attr):
            getattr(widget, attr)(int(val))


def atomic_write_file(path, content, encoding="utf-8"):
    """Écriture atomique POSIX via fichier temporaire adjacent (.tmp) + fsync + os.replace."""
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
    """Injecte la feuille de style GTK3 pour hiérarchiser visuellement le menu systray."""
    global _MENU_CSS_APPLIED
    if _MENU_CSS_APPLIED:
        return
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk, Gdk

        suffix = ""
        try:
            test_m, test_mi = Gtk.Menu(), Gtk.MenuItem(label="t")
            test_m.append(test_mi)
            test_m.show_all()
            fg = test_mi.get_style_context().get_color(Gtk.StateFlags.NORMAL)
            if (fg.red * 0.299 + fg.green * 0.587 + fg.blue * 0.114) < 0.45:
                suffix = "-dark"
            test_m.destroy()
        except Exception:
            pass

        icon_dirs = ["/usr/share/timonde/icons", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "icons")]
        arrow_css = ""
        for direction, name in (("ltr", "pan-end-symbolic"), ("rtl", "pan-end-symbolic-rtl")):
            svg = next((os.path.join(d, f"{name}{suffix}.svg") for d in icon_dirs if os.path.exists(os.path.join(d, f"{name}{suffix}.svg"))), None)
            if svg:
                arrow_css += f"menu menuitem arrow:dir({direction}), .menu menuitem arrow:dir({direction}) {{ min-width: 16px; min-height: 16px; -gtk-icon-source: url(\"{svg}\"); }}\n"

        provider = Gtk.CssProvider()
        provider.load_from_data(f"""
        menu separator, menuitem.separator {{ min-height: 2px; margin: 4px 8px; background-color: alpha(currentColor, 0.28); }}
        menuitem.timonde-header-action {{ background-color: alpha(@theme_selected_bg_color, 0.14); border-radius: 2px; padding-top: 5px; padding-bottom: 5px; }}
        menuitem.timonde-info-time, menuitem.timonde-info-time:disabled {{ background-color: alpha(currentColor, 0.08); border-left: 3px solid @theme_selected_bg_color; color: inherit; opacity: 0.92; padding-top: 3px; padding-bottom: 3px; }}
        menuitem.timonde-info-time label, menuitem.timonde-info-time:disabled label {{ color: inherit; }}
        menuitem.timonde-info-track, menuitem.timonde-info-track:disabled {{ background-color: alpha(currentColor, 0.08); border-left: 3px solid @theme_selected_bg_color; color: inherit; opacity: 0.95; padding-top: 3px; padding-bottom: 4px; }}
        menuitem.timonde-info-track label, menuitem.timonde-info-track:disabled label {{ color: inherit; font-style: italic; font-weight: bold; }}
        menuitem.timonde-sep-header, menuitem.timonde-sep-header:disabled {{ color: inherit; opacity: 0.75; }}
        {arrow_css}
        menu menuitem image, menuitem image, menu image {{ color: inherit; opacity: 0.90; }}
        menu menuitem:hover image, menuitem:hover image {{ color: inherit; opacity: 1.0; }}
        """.encode("utf-8"))
        screen = Gdk.Screen.get_default()
        if screen:
            Gtk.StyleContext.add_provider_for_screen(screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)
            _MENU_CSS_APPLIED = True
    except Exception as e:
        sys.stderr.write(f"TiMonde: CSS du menu rejeté par GTK : {e}\n")


def status_markup(text: str, kind: str = "ok", with_bullet: bool = False, bold: bool = False) -> str:
    """Génère un balisage Pango harmonisé pour les indicateurs d'état et de santé des flux."""
    palette = {
        "ok": "#2ecc71", "online": "#2ecc71", "success": "#2ecc71", "new": "#2ecc71",
        "warn": "#f39c12", "warning": "#f39c12", "geo": "#f39c12", "geoblocked": "#f39c12",
        "error": "#e74c3c", "offline": "#e74c3c", "dead": "#e74c3c",
        "muted": "#888888", "dim": "#888888", "untested": "#888888", "info": "#3498db",
    }
    color = palette.get((kind or "ok").lower(), "#888888")
    escaped = html.escape(str(text))
    content = f"<b>{escaped}</b>" if bold else escaped
    return f'<span foreground="{color}"><b>●</b> {content}</span>' if with_bullet else f'<span foreground="{color}">{content}</span>'


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
        treeview.timonde-tree { border-radius: 3px; }
        .settings-card { background-color: alpha(@theme_base_color, 0.4); border: 1px solid alpha(@theme_fg_color, 0.15); border-radius: 2px; padding: 12px; margin-bottom: 6px; }
        .info-card { background-color: alpha(@theme_base_color, 0.15); border: 1px dashed alpha(@theme_fg_color, 0.18); border-radius: 2px; padding: 10px 12px; margin-bottom: 6px; }
        .card-title { font-weight: bold; font-size: 1.05em; }
        .card-desc { opacity: 0.75; font-size: 0.9em; }
        .info-title { font-weight: bold; font-size: 0.95em; opacity: 0.85; }
        .info-desc { opacity: 0.65; font-size: 0.85em; }
        .status-badge { font-weight: bold; padding: 2px 6px; border-radius: 2px; }
        .info-badge { font-family: monospace; font-size: 0.9em; padding: 2px 8px; border-radius: 2px; background-color: alpha(@theme_fg_color, 0.08); color: @theme_fg_color; opacity: 0.9; }
        .section-separator-title { font-weight: bold; font-size: 0.82em; letter-spacing: 0.5px; opacity: 0.55; margin-top: 10px; margin-bottom: 4px; }
        .highlight-combo { font-weight: bold; border: 1px solid alpha(@theme_selected_bg_color, 0.6); border-radius: 2px; }
        """)
        screen = Gdk.Screen.get_default()
        if screen:
            Gtk.StyleContext.add_provider_for_screen(screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            _APP_CSS_APPLIED = True
    except Exception as e:
        sys.stderr.write(f"TiMonde: CSS applicatif rejeté par GTK : {e}\n")


def _find_label_widget(widget):
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
    """Charge une icône et recolorise ses canaux RVB selon la couleur du texte du menu."""
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import Gtk, GdkPixbuf, GLib

    r, g, b = int(getattr(fg_rgba, "red", 1.0) * 255), int(getattr(fg_rgba, "green", 1.0) * 255), int(getattr(fg_rgba, "blue", 1.0) * 255)
    cache_key = (icon_name, r, g, b, size_px)
    if cache_key in _RECOLORED_ICONS_CACHE:
        return _RECOLORED_ICONS_CACHE[cache_key]

    theme = Gtk.IconTheme.get_default()
    if not theme:
        return None
    clean_name = icon_name.replace("-symbolic", "")
    icon_info = next((theme.lookup_icon(c, size_px, 0) for c in (f"{clean_name}-symbolic", clean_name) if theme.has_icon(c)), None)
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

        w, h, rowstride, n_channels = pix.get_width(), pix.get_height(), pix.get_rowstride(), pix.get_n_channels()
        data = bytearray(pix.get_pixels())
        for y in range(h):
            for x in range(w):
                idx = y * rowstride + x * n_channels
                data[idx], data[idx + 1], data[idx + 2] = r, g, b

        recolored = GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(bytes(data)), pix.get_colorspace(), True, pix.get_bits_per_sample(), w, h, rowstride)
        _RECOLORED_ICONS_CACHE[cache_key] = recolored
        return recolored
    except Exception:
        return None


def _find_and_convert_images(widget, fg_rgba):
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    if isinstance(widget, Gtk.Image):
        try:
            orig_name = getattr(widget, "_timonde_orig_icon", None)
            if not orig_name:
                icon_info = widget.get_icon_name()
                if icon_info and icon_info[0]:
                    orig_name = widget._timonde_orig_icon = icon_info[0]
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
    """Parcourt un DbusmenuGtk3.Menu pour styliser séparateurs, en-tête, heure locale et titre musical."""
    if not menu:
        return
    apply_timonde_menu_css()
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk, Gdk

        try:
            fg_rgba = menu.get_style_context().get_color(Gtk.StateFlags.NORMAL)
        except Exception:
            fg_rgba = Gdk.RGBA(0.96, 0.96, 0.96, 1.0)

        for idx, child in enumerate(menu.get_children()):
            if isinstance(child, Gtk.SeparatorMenuItem):
                child.set_visible(True)
                continue
            if not isinstance(child, Gtk.MenuItem):
                continue

            try:
                child_fg = child.get_style_context().get_color(Gtk.StateFlags.NORMAL)
            except Exception:
                child_fg = None
            _find_and_convert_images(child, child_fg or fg_rgba)

            raw_lbl = getattr(child, "get_label", lambda: None)() or ""
            lbl_widget = _find_label_widget(child)
            ctx = child.get_style_context()

            if raw_lbl == "Label Empty" or (raw_lbl.strip() == "" and not isinstance(child, Gtk.SeparatorMenuItem)):
                child.set_label("────────────────────────")
                child.set_sensitive(False)
                ctx.add_class("timonde-sep-header")
            elif "─────" in raw_lbl or "───" in raw_lbl:
                child.set_sensitive(False)
                ctx.add_class("timonde-sep-header")
                if lbl_widget:
                    lbl_widget.set_markup(f"<span size='small'><b>{html.escape(raw_lbl.strip())}</b></span>")
            elif is_root and idx == 0:
                ctx.add_class("timonde-header-action")
                if lbl_widget:
                    lbl_widget.set_markup(f"<b>{html.escape(raw_lbl)}</b>")
            elif is_root and ("│ [" in raw_lbl or (raw_lbl.strip().startswith("[") and "•" in raw_lbl and "UTC" in raw_lbl)):
                ctx.add_class("timonde-info-time")
                clean_time = raw_lbl.replace("  │ ", "").replace("│ ", "").strip()
                if lbl_widget:
                    parts = clean_time.split("•", 1)
                    lbl_widget.set_markup(
                        f"<span size='small'><b>{html.escape(parts[0].strip())}</b> • {html.escape(parts[1].strip())}</span>"
                        if len(parts) == 2 else f"<span size='small'>{html.escape(clean_time)}</span>"
                    )
            elif is_root and "♪" in raw_lbl:
                ctx.add_class("timonde-info-track")
                if lbl_widget:
                    lbl_widget.set_markup(f"<i>{html.escape(raw_lbl.replace('  │ ', '').replace('│ ', '').strip())}</i>")

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


def call_timonde_mpris(method_name: str, *args, fallback_cli: list = None, timeout: float = 2.0):
    """Exécute un appel unifié vers TiMonde via D-Bus MPRIS (priorité 1) ou CLI timonde (priorité 2)."""
    try:
        import dbus
        try:
            import dbus.mainloop.glib
            dbus.mainloop.glib.threads_init()
        except Exception:
            pass
        bus = dbus.SessionBus()
        if bus.name_has_owner("org.mpris.MediaPlayer2.timonde"):
            obj = bus.get_object("org.mpris.MediaPlayer2.timonde", "/org/mpris/MediaPlayer2")
            method = getattr(dbus.Interface(obj, "org.mpris.MediaPlayer2.Player"), method_name, None)
            if method:
                return True, method(*args, timeout=timeout)
    except Exception:
        pass

    if fallback_cli:
        try:
            proc = run_timonde_cli(*fallback_cli, timeout=timeout)
            if proc.returncode == 0:
                return True, proc.stdout.strip()
        except Exception:
            pass
    return False, None


class StreamPreviewPlayer:
    """Lecteur d'aperçu audio déporté vers le moteur natif Rust (via D-Bus ou CLI timonde)."""
    def __init__(self, on_status_changed=None, on_status_change=None):
        import threading
        self._lock = threading.Lock()
        self._action_id = 0
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
            url, station_name = station_name, _("Radio")
        clean = clean_stream_url(url)
        if not clean:
            self._emit_status(False, f"[!] {_('Empty stream URL')}", is_error=True)
            return False
        with self._lock:
            already_playing_this = (self.is_playing and self.current_url == clean)
        if already_playing_this:
            self.stop()
            return False
        return self.play(station_name, clean)

    def play(self, station_name, url=None):
        import threading
        if url is None:
            url, station_name = station_name, _("Radio")
        clean = clean_stream_url(url)
        if not clean:
            self._emit_status(False, f"[!] {_('Empty stream URL')}", is_error=True)
            return False

        with self._lock:
            self._action_id += 1
            action_id = self._action_id
            self.current_url = clean
            self.current_name = station_name or _("Radio")
            self.is_playing = True

        self._emit_status(True, f"[►] {_('Playing:')} « {self.current_name} »", is_error=False)

        def run_play():
            with self._lock:
                if self._action_id != action_id:
                    return
                disp_name = self.current_name or ""
            call_timonde_mpris("PlayPreview", clean, disp_name, fallback_cli=["--preview-play", clean, disp_name], timeout=2.0)

        threading.Thread(target=run_play, daemon=True).start()
        return True

    def stop(self, silent=False, sync=False):
        import threading
        with self._lock:
            was_playing = self.is_playing
            self.is_playing, self.current_url, self.current_name = False, None, None
            self._action_id += 1
            action_id = self._action_id

        if not was_playing:
            return

        def run_stop():
            with self._lock:
                if self._action_id != action_id:
                    return
            call_timonde_mpris("StopPreview", fallback_cli=["--preview-stop"], timeout=1.5)

        if sync:
            run_stop()
        else:
            threading.Thread(target=run_stop, daemon=True).start()
        if not silent:
            self._emit_status(False, "", is_error=False)


def find_script(script_name: str):
    """Localise un script Python compagnon dans les répertoires standards ou locaux."""
    for c in (
        os.path.join(os.path.dirname(os.path.abspath(__file__)), script_name),
        os.path.join("/usr/share/timonde/scripts", script_name),
        os.path.join("/usr/local/share/timonde/scripts", script_name),
        os.path.expanduser(f"~/.local/share/timonde/scripts/{script_name}"),
        f"data/scripts/{script_name}",
    ):
        if os.path.isfile(c):
            return c
    return None


from concurrent.futures import ThreadPoolExecutor


def search_radio_browser_api(name="", country_code="", tag="", language="", limit=30):
    """Recherche multicritères sur les miroirs Radio-Browser en déléguant au moteur Rust."""
    args = ["--search"]
    if name and name.strip():
        args.append(name.strip())
    if tag and tag.strip():
        args.extend(["--tag", tag.strip()])
    if country_code and country_code.strip():
        args.extend(["--country", country_code.strip()])
    if language and language.strip():
        args.extend(["--lang", language.strip()])
    if limit:
        args.extend(["--limit", str(limit)])
    args.append("--json")
    try:
        res = run_timonde_cli(*args, timeout=12.0)
        if res.returncode == 0 and res.stdout.strip():
            return json.loads(res.stdout)
    except Exception as e:
        sys.stderr.write(f"Échec recherche Radio-Browser via Rust : {e}\n")
    return []


def lookup_station_by_url(stream_url: str):
    """Vérifie si une URL de flux est déjà répertoriée sur Radio-Browser via 'timonde --lookup-url'."""
    if not stream_url or not stream_url.strip():
        return None
    try:
        res = run_timonde_cli("--lookup-url", stream_url.strip(), timeout=10.0)
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout.strip())
            if data.get("exists"):
                return data.get("station")
    except Exception as e:
        sys.stderr.write(f"Échec lookup Radio-Browser via Rust : {e}\n")
    return None


def contribute_station_to_radio_browser(name, url, country_code="", language="", tags="", homepage="", favicon=""):
    """Soumet une nouvelle radio à Radio-Browser via 'timonde --contribute-station'."""
    if not name or not name.strip():
        return (False, _("Station name cannot be empty"), None)
    if not url or not url.strip():
        return (False, _("Stream URL cannot be empty"), None)

    clean_name, clean_url = name.strip(), url.strip()
    existing = lookup_station_by_url(clean_url)
    if existing:
        ex_name = existing.get("name", _("Unknown"))
        return (False, _("This stream URL is already registered on Radio-Browser as '{existing_name}'.").format(existing_name=ex_name), existing)

    payload = {
        "name": clean_name, "url": clean_url,
        "countrycode": (country_code or "").strip(), "language": (language or "").strip(),
        "tags": (tags or "").strip(), "homepage": (homepage or "").strip(), "favicon": (favicon or "").strip(),
    }
    try:
        res = run_timonde_cli("--contribute-station", "-", input_text=json.dumps(payload), timeout=12.0)
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout.strip())
            ok = data.get("ok", False)
            return (ok, data.get("message", _("Unknown status")), data if ok else None)
        return (False, res.stderr.strip() or _("Error communicating with TiMonde binary"), None)
    except Exception as e:
        return (False, str(e), None)


def show_group_naming_help_dialog(parent):
    """Affiche la boîte de dialogue modale d'aide sur la convention Linux des groupes /."""
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk
    except (ImportError, ValueError):
        return

    dialog = Gtk.MessageDialog(
        transient_for=parent, flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
        type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.OK,
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
        super().__init__(title=f"{_('Replace stream:')} {station_name}", transient_for=parent, modal=True)
        self.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        self.add_button(_("Validate and replace"), Gtk.ResponseType.OK)
        self.set_default_size(720, 420)
        self.station_name, self.country_code, self.selected_url = station_name, country_code, None

        content = self.get_content_area()
        content.set_spacing(10)
        set_container_margins(content, margin=10)

        url_snippet = (current_url[:65] + "...") if len(current_url) > 65 else current_url
        info_lbl = Gtk.Label(
            label=f"<b>{_('Original stream is unreachable:')}</b>\n<small><tt>{html.escape(url_snippet)}</tt></small>\n\n{_('Select a verified replacement stream from Radio-Browser:')}",
            use_markup=True, halign=Gtk.Align.START
        )
        content.pack_start(info_lbl, False, False, 0)

        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        content.pack_start(search_box, False, False, 0)
        self.entry_query = Gtk.Entry(text=station_name, hexpand=True)
        self.entry_query.connect("activate", lambda w: self.perform_search())
        search_box.pack_start(self.entry_query, True, True, 0)
        btn_search = make_btn(_("Search"), "system-search")
        btn_search.connect("clicked", lambda w: self.perform_search())
        search_box.pack_start(btn_search, False, False, 0)

        self.store = Gtk.ListStore(str, str, str, str, str, int)
        self.tree = Gtk.TreeView(model=self.store)
        for title, col_id, expand in [(_("Station"), 0, True), (_("Format"), 1, False), (_("Bitrate"), 2, False), (_("Country"), 3, False), (_("Popularity"), 5, False)]:
            col = Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=col_id)
            col.set_expand(expand)
            self.tree.append_column(col)

        scroll = Gtk.ScrolledWindow(shadow_type=Gtk.ShadowType.IN)
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self.tree)
        content.pack_start(scroll, True, True, 0)

        self.lbl_status = Gtk.Label(label=_("Searching for streams..."), halign=Gtk.Align.START)
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
                    self.store.append([
                        r.get("name", "Sans nom"), r.get("codec", "MP3"),
                        f"{r.get('bitrate', 128)} kbps" if r.get("bitrate") else "-",
                        r.get("country", ""), r.get("url_resolved") or r.get("url", ""), r.get("votes", 0)
                    ])
                self.lbl_status.set_text(_("{count} streams found. Select the desired stream and validate.").format(count=len(results)))
                it = self.store.get_iter_first()
                if it:
                    self.tree.get_selection().select_iter(it)

            GLib.idle_add(on_done)

        ThreadPoolExecutor(max_workers=1).submit(worker)

    def get_chosen_url(self):
        model, tree_iter = self.tree.get_selection().get_selected()
        return model[tree_iter][4] if tree_iter else None


def prompt_text_dialog(parent_window, title: str, label_text: str, default_text: str = "", ok_label: str = None, callback = None) -> str:
    """Dialogue modal léger GTK3 de saisie textuelle unifié (asynchrone non-bloquant via callback)."""
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk

    dlg = Gtk.Dialog(title=title, transient_for=parent_window, flags=Gtk.DialogFlags.MODAL)
    dlg.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
    dlg.add_button(ok_label or _("OK"), Gtk.ResponseType.OK)
    dlg.set_default_response(Gtk.ResponseType.OK)

    box = dlg.get_content_area()
    box.set_spacing(10)
    set_container_margins(box, margin=12)
    lbl = Gtk.Label(halign=Gtk.Align.START)
    lbl.set_markup(label_text)
    box.pack_start(lbl, False, False, 0)
    entry = Gtk.Entry(text=default_text or "", width_chars=35, activates_default=True)
    box.pack_start(entry, False, False, 0)

    def on_response(d, resp):
        txt = entry.get_text().strip()
        d.destroy()
        if callback is not None:
            callback(txt if resp == Gtk.ResponseType.OK else None)

    dlg.connect("response", on_response)
    dlg.show_all()
    return None


class ContributeStationDialog(_GtkDialogBase):
    """Boîte de dialogue universelle de vérification et contribution de radios vers Radio-Browser."""
    def __init__(self, parent, station_name="", current_url="", country_code="", tags="", homepage=""):
        if _GtkDialogBase is object:
            raise RuntimeError("GTK 3.0 n'est pas disponible pour afficher ce dialogue.")
        from gi.repository import Gtk, GLib

        super().__init__(title=_("Contribute to Radio-Browser"), transient_for=parent, modal=True)
        self.set_default_size(580, 360)
        self.station_name = (station_name or "").strip()
        self.current_url = (current_url or "").strip()
        self.country_code = (country_code or "").strip().upper()
        self.tags = (tags or "").strip()
        self.homepage = (homepage or "").strip()
        self.existing_info = None

        content = self.get_content_area()
        set_container_margins(content, margin=12)
        content.set_spacing(10)

        self.lbl_header = Gtk.Label(halign=Gtk.Align.START)
        self.lbl_header.set_markup(
            f"<b>{_('Contribute a station to the community Radio-Browser directory')}</b>\n"
            f"<small><i>{_('Radio-Browser is an open directory (+45 000 stations). Shared stations benefit all users.')}</i></small>"
        )
        content.pack_start(self.lbl_header, False, False, 0)

        grid = Gtk.Grid(column_spacing=12, row_spacing=8)
        content.pack_start(grid, True, True, 0)

        self.entry_name = Gtk.Entry(text=self.station_name, hexpand=True)
        self.entry_url = Gtk.Entry(text=self.current_url, hexpand=True)
        url_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        url_box.pack_start(self.entry_url, True, True, 0)
        btn_check_again = make_btn(_("Check"), "view-refresh", _("Check entered stream URL again on Radio-Browser"))
        btn_check_again.connect("clicked", lambda w: self._start_lookup(self.entry_url.get_text().strip()))
        url_box.pack_start(btn_check_again, False, False, 0)

        self.entry_cc = Gtk.Entry(text=self.country_code, placeholder_text="Ex: FR, GP, MQ, GF, RE, YT, NC, PF, CA, BE...")
        self.entry_tags = Gtk.Entry(text=self.tags, placeholder_text="Ex: news, talk, pop, zouk, kompa, rock...")
        self.entry_hp = Gtk.Entry(text=self.homepage, placeholder_text="https://...")

        for row_idx, (lbl_txt, widget) in enumerate([
            (_("Station name:"), self.entry_name),
            (_("Stream URL:"), url_box),
            (_("Country code (ISO):"), self.entry_cc),
            (_("Tags / Genres:"), self.entry_tags),
            (_("Website / Homepage:"), self.entry_hp),
        ]):
            grid.attach(Gtk.Label(label=lbl_txt, halign=Gtk.Align.END), 0, row_idx, 1, 1)
            grid.attach(widget, 1, row_idx, 1, 1)

        self.lbl_status = Gtk.Label(label="", use_markup=True, halign=Gtk.Align.START, no_show_all=True)
        content.pack_start(self.lbl_status, False, False, 0)

        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        content.pack_start(action_box, False, False, 4)

        self.btn_cancel = Gtk.Button(label=_("Close"))
        self.btn_cancel.connect("clicked", lambda w: self.response(Gtk.ResponseType.CLOSE))
        self.btn_edit = Gtk.Button(label=_("Edit station"), no_show_all=True)
        self.btn_edit.connect("clicked", lambda w: self.response(Gtk.ResponseType.APPLY))
        self.btn_edit.hide()
        self.btn_submit = Gtk.Button(label=_("Submit to Radio-Browser"))
        self.btn_submit.get_style_context().add_class("suggested-action")
        self.btn_submit.connect("clicked", self._on_submit_clicked)

        action_box.pack_start(self.btn_cancel, False, False, 0)
        action_box.pack_start(self.btn_edit, False, False, 0)
        action_box.pack_start(Gtk.Box(), True, True, 0)
        action_box.pack_start(self.btn_submit, False, False, 0)

        self.connect("response", lambda d, r: self.hide())
        if self.current_url:
            self._start_lookup(self.current_url)
        self.show_all()

    def _start_lookup(self, url_to_check):
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
        threading.Thread(target=lambda: GLib.idle_add(self._on_lookup_done, url_to_check, lookup_station_by_url(url_to_check)), daemon=True).start()

    def _on_lookup_done(self, checked_url, existing):
        self.existing_info = existing
        if existing:
            ex_name, ex_cc = existing.get("name", _("Unknown")), existing.get("countrycode", _("Unknown"))
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
        import threading
        from gi.repository import GLib

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
            ok, msg, _info = contribute_station_to_radio_browser(name=name, url=url, country_code=cc, tags=tags, homepage=hp)
            def _sub_done():
                color = "#2ecc71" if ok else "#e74c3c"
                prefix = "● " if ok else ""
                self.lbl_status.set_markup(f"<small><span foreground='{color}'><b>{prefix}{html.escape(msg)}</b></span></small>")
                self.lbl_status.show()
                self.btn_submit.set_label(_("Submitted") if ok else _("Submit to Radio-Browser"))
                self.btn_submit.set_sensitive(not ok)
                if ok:
                    self.btn_cancel.set_label(_("Close"))
            GLib.idle_add(_sub_done)

        threading.Thread(target=_sub_worker, daemon=True).start()



