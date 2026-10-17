#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TiMonde — Interface Unifiée de Découverte & Importation de Radios
Unified Radio Discovery & Import Interface for TiMonde.

Fonctionnalités / Features:
1. Sélecteur universel de pays (Code ISO 3166-1 alpha-2, noms traduits et drapeaux).
   Universal country picker (ISO 3166-1 alpha-2 code, translated names and flags).
2. Onglet 1 : Bouquets officiels (DAB+ & sélections vérifiées) avec test frugal en direct.
   Tab 1: Official bouquets with live lightweight HTTP health check.
3. Réparation automatique des flux morts via Radio-Browser avec mise à jour du XML source.
   Live repair of broken streams using Radio-Browser with source XML update.
4. Onglet 2 : Recherche mondiale Radio-Browser pré-filtrée par code pays ISO sans barrière de langue.
   Tab 2: Global Radio-Browser exploration pre-filtered by ISO country code without language barrier.
5. Importation de fichiers XML externes (bouquets ou bookmarks locaux).
   External XML file loader (local bouquets or bookmarks).
"""

import sys
import os

# Neutralisation inconditionnelle d'IBus pour éviter tout gel des frappes clavier sous GTK3
# (les sessions de bureau avec socket IBus orpheline ou rompue absorbent et perdent les touches)
os.environ.pop("GTK_IM_MODULE", None)
os.environ.pop("XMODIFIERS", None)
os.environ.pop("QT_IM_MODULE", None)

# Module d internationalisation & socle commun TiMonde
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from timonde_i18n import _
except ImportError:
    def _(s): return s

from timonde_common import (
    clean_stream_url,
    safe_parse_xml,
    strip_unsupported_emojis,
    get_user_bookmarks_groups,
    normalize_group_path,
    make_btn,
    infer_timezone,
    StreamPreviewPlayer,
    update_btn_content,
)

from timonde_world_data import (
    WORLD_COUNTRIES,
    RADIO_BROWSER_LANGUAGES,
    COUNTRY_BY_CODE,
    COUNTRY_LOOKUP_MAP,
    NATIVE_COUNTRY_NAMES,
    NATIVE_LANGUAGE_NAMES,
    DISPLAY_NATIVE_MAP,
    resolve_language_api_key,
    resolve_country_code,
    normalize_lookup,
)

import json
import html
import glob
import shutil
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
import re
import csv
from concurrent.futures import ThreadPoolExecutor

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

# -----------------------------------------------------------------------------
# Configuration & Constantes / Configuration & Constants
# -----------------------------------------------------------------------------

RADIO_BROWSER_ENDPOINTS = [
    "https://de1.api.radio-browser.info",
    "https://nl1.api.radio-browser.info",
    "https://at1.api.radio-browser.info",
]

USER_AGENT = "TiMonde/0.2.0 (Linux; x86_64; VLC/3.0.20)"

# Répertoires de recherche des bouquets XML / Bouquets search paths
BOUQUETS_CANDIDATES = [
    os.path.join(os.path.dirname(__file__), "..", "bouquets"),
    os.path.expanduser("~/.local/share/timonde/bouquets"),
    "/usr/share/timonde/bouquets",
    "/usr/local/share/timonde/bouquets",
    "data/bouquets",
]


USER_CONFIG_EXAMPLES_DIR = os.path.expanduser("~/.config/timonde/examples")

EXAMPLES_CANDIDATES = [
    USER_CONFIG_EXAMPLES_DIR,
    os.path.expanduser("~/.local/share/timonde/examples"),
    os.path.join(os.path.dirname(__file__), "..", "examples"),
    "/usr/share/timonde/examples",
    "data/examples",
]

def ensure_user_examples_dir():
    """Initialise le dossier ~/.config/timonde/examples et le peuple avec les exemples par défaut si vide."""
    try:
        os.makedirs(USER_CONFIG_EXAMPLES_DIR, exist_ok=True)
        # Vérifie si le dossier contient déjà des fichiers exemples
        patterns = ["*.xml", "*.csv", "*.json", "*.m3u", "*.m3u8", "*.pls"]
        existing = []
        for pat in patterns:
            existing.extend(glob.glob(os.path.join(USER_CONFIG_EXAMPLES_DIR, pat)))
        if not existing:
            # Chercher le répertoire source système ou local
            source_dirs = [
                "/usr/share/timonde/examples",
                os.path.join(os.path.dirname(__file__), "..", "examples"),
                os.path.join(os.path.dirname(__file__), "../../data/examples"),
                os.path.expanduser("~/.local/share/timonde/examples"),
                "data/examples"
            ]
            import shutil
            for sdir in source_dirs:
                if os.path.isdir(sdir):
                    for fname in os.listdir(sdir):
                        if fname.endswith(('.xml', '.csv', '.json', '.m3u', '.m3u8', '.pls', '.md')):
                            src_file = os.path.join(sdir, fname)
                            dst_file = os.path.join(USER_CONFIG_EXAMPLES_DIR, fname)
                            if os.path.isfile(src_file) and not os.path.exists(dst_file):
                                shutil.copy2(src_file, dst_file)
                    break
    except Exception as e:
        sys.stderr.write(f"Avertissement initialisation {USER_CONFIG_EXAMPLES_DIR}: {e}\n")
    return USER_CONFIG_EXAMPLES_DIR

def find_examples_dir():
    """Localise le dossier des exemples XML / Locate examples directory"""
    ensure_user_examples_dir()
    for path in EXAMPLES_CANDIDATES:
        if os.path.isdir(path) and glob.glob(os.path.join(path, "*.xml")):
            return os.path.abspath(path)
    return None

def list_available_examples():
    """Liste tous les fichiers exemples disponibles (XML, CSV, JSON, M3U) en priorité depuis ~/.config/timonde/examples"""
    user_dir = ensure_user_examples_dir()
    patterns = ["*.xml", "*.csv", "*.json", "*.m3u", "*.m3u8", "*.pls"]
    found_files = {}

    # 1. Explorer en priorité le dossier utilisateur ~/.config/timonde/examples
    if os.path.isdir(user_dir):
        for pat in patterns:
            for f in glob.glob(os.path.join(user_dir, pat)):
                base = os.path.basename(f)
                if base not in found_files:
                    found_files[base] = f

    # 2. Explorer les autres dossiers candidats si nécessaire
    for d in EXAMPLES_CANDIDATES:
        if os.path.isdir(d):
            for pat in patterns:
                for f in glob.glob(os.path.join(d, pat)):
                    base = os.path.basename(f)
                    if base not in found_files:
                        found_files[base] = f

    results = []
    for base in sorted(found_files.keys()):
        f = found_files[base]
        if f.endswith(".xml"):
            try:
                tree = ET.parse(f)
                root = tree.getroot()
                name = root.attrib.get("name", "")
                country = root.attrib.get("country", "")
                if name and name != base:
                    display_label = f"{base}  —  {name}"
                else:
                    display_label = base
                results.append((f, display_label, name or base))
            except Exception:
                results.append((f, base, base))
        elif f.endswith(".csv"):
            results.append((f, f"{base}  —  [Tableur CSV]", "Import CSV"))
        elif f.endswith(".json"):
            results.append((f, f"{base}  —  [Radiotray-NG JSON]", "Import JSON"))
        elif f.endswith((".m3u", ".m3u8")):
            results.append((f, f"{base}  —  [Playlist M3U]", "Playlist M3U"))
        elif f.endswith(".pls"):
            results.append((f, f"{base}  —  [Playlist PLS]", "Playlist PLS"))
    return results


# -----------------------------------------------------------------------------
# Fonctions Utilitaires / Utility Functions
# -----------------------------------------------------------------------------

def find_bouquets_dir():
    """Localise le dossier principal des bouquets XML / Locate main bouquets directory"""
    for path in BOUQUETS_CANDIDATES:
        if os.path.isdir(path) and glob.glob(os.path.join(path, "*.xml")):
            return os.path.abspath(path)
    return None

def check_stream_url(url, timeout=2.0):
    """
    Test frugal et rapide de disponibilité d'un flux audio (en-têtes HTTP uniquement).
    Lightweight, fast HTTP stream health check (headers only, no body download).
    """
    if not url or url.strip() == "":
        return False, "URL vide"
    url = url.strip()
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "*/*",
                "Icy-MetaData": "1"
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.getcode()
            if 200 <= code < 400:
                ct = resp.headers.get("Content-Type", "")
                codec = "Audio"
                if "aac" in ct: codec = "AAC"
                elif "mpeg" in ct or "mp3" in ct: codec = "MP3"
                elif "ogg" in ct: codec = "OGG"
                elif "flac" in ct: codec = "FLAC"
                return True, f"En ligne ({codec})"
            return False, f"Erreur HTTP {code}"
    except urllib.error.HTTPError as e:
        if e.code in (403, 451) or (e.code == 503 and any(k in url.lower() for k in ["amperwave", "audacy", "streamtheworld", "akamai", "geoblock", "leanstream"])):
            return "GEOBLOCKED", f"Géobloqué (VPN)"
        return False, f"Erreur {e.code}"
    except urllib.error.URLError:
        return False, "Serveur inaccessible"
    except Exception as e:
        return False, "Délai dépassé"

def query_radio_browser(endpoint, path, params):
    """Interroge l'annuaire Radio-Browser / Query Radio-Browser API"""
    query_str = urllib.parse.urlencode(params)
    url = f"{endpoint}/json/{path}?{query_str}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            if resp.getcode() == 200:
                return json.loads(resp.read().decode("utf-8"))
    except Exception:
        pass
    return None

def search_radio_browser_api(name="", country_code="", tag="", language="", limit=30):
    """
    Recherche multicritères sur les miroirs Radio-Browser (nom, pays, genre, langue).
    Interroge la clé canonique et fusionne automatiquement avec les alias en graphies natives
    (ex: arabe + العربية, russe + русский) pour ne rater aucune station exclusive.
    """
    # Déterminer les variantes linguistiques à interroger
    lang_queries = []
    if language:
        lang_clean = language.strip().lower()
        lang_queries.append(lang_clean)
        if lang_clean in NATIVE_LANGUAGE_NAMES:
            for nat_alias in NATIVE_LANGUAGE_NAMES[lang_clean][:3]:
                if nat_alias not in lang_queries:
                    lang_queries.append(nat_alias)
    else:
        lang_queries.append("")

    all_stations = []
    seen_keys = set()

    for l_val in lang_queries:
        params = {"limit": str(limit), "hidebroken": "true", "order": "votes", "reverse": "true"}
        if name: params["name"] = name
        if country_code:
            cc_up = country_code.strip().upper()
            params["countrycode"] = "GB" if cc_up == "UK" else cc_up
        if tag: params["tag"] = tag
        if l_val: params["language"] = l_val

        for ep in RADIO_BROWSER_ENDPOINTS:
            res = query_radio_browser(ep, "stations/search", params)
            if res is not None:
                for s in res:
                    uid = s.get("stationuuid") or s.get("url_resolved") or s.get("url", "")
                    clean_uid = uid.strip()
                    if clean_uid and clean_uid not in seen_keys:
                        seen_keys.add(clean_uid)
                        all_stations.append(s)
                break

    return all_stations

# Langues populaires pour raccourcis rapides
QUICK_POPULAR_LANGUAGES = [
    ("Toutes les langues", ""),
    ("Français", "french"),
    ("Anglais", "english"),
    ("Espagnol", "spanish"),
    ("Arabe", "arabic"),
    ("Allemand", "german"),
    ("Italien", "italian"),
    ("Portugais", "portuguese"),
    ("Russe", "russian"),
    ("Hindi", "hindi"),
    ("Thaï", "thai"),
    ("Chinois", "chinese"),
    ("Japonais", "japanese"),
    ("Néerlandais", "dutch"),
    ("Turc", "turkish"),
    ("Polonais", "polish"),
    ("Grec", "greek"),
]

# -----------------------------------------------------------------------------
# Boîte de dialogue : Réparation de flux mort via Radio-Browser
# Dialog: Repair broken stream using Radio-Browser
# -----------------------------------------------------------------------------

class RepairStreamDialog(Gtk.Dialog):
    def __init__(self, parent, station_name, current_url, country_code=""):
        super().__init__(
            title=f"Remplacer le flux : {station_name}",
            transient_for=parent,
            modal=True,
        )
        self.add_button("Annuler", Gtk.ResponseType.CANCEL)
        self.add_button("Valider et remplacer", Gtk.ResponseType.OK)
        self.set_default_size(720, 420)
        self.set_border_width(10)
        self.station_name = station_name
        self.country_code = country_code
        self.selected_url = None

        content = self.get_content_area()
        content.set_spacing(10)

        # En-tête explicatif / Header description
        info_lbl = Gtk.Label(
            label=f"<b>Le flux d'origine ne répond plus :</b>\n"
                  f"<small><tt>{current_url[:65]}...</tt></small>\n\n"
                  f"Sélectionnez un flux de remplacement vérifié sur Radio-Browser :"
        )
        info_lbl.set_use_markup(True)
        info_lbl.set_halign(Gtk.Align.START)
        content.pack_start(info_lbl, False, False, 0)

        # Barre de recherche / Search bar
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        content.pack_start(search_box, False, False, 0)

        self.entry_query = Gtk.Entry()
        self.entry_query.set_text(station_name)
        self.entry_query.set_hexpand(True)
        self.entry_query.connect("activate", lambda w: self.perform_search())
        search_box.pack_start(self.entry_query, True, True, 0)

        btn_search = make_btn("Rechercher", "system-search")
        btn_search.connect("clicked", lambda w: self.perform_search())
        search_box.pack_start(btn_search, False, False, 0)

        # Liste des résultats / Results list
        # Store: [name, codec, bitrate, country, url, votes]
        self.store = Gtk.ListStore(str, str, str, str, str, int)
        self.tree = Gtk.TreeView(model=self.store)
        
        col_name = Gtk.TreeViewColumn("Station", Gtk.CellRendererText(), text=0)
        col_name.set_expand(True)
        self.tree.append_column(col_name)

        col_codec = Gtk.TreeViewColumn("Format", Gtk.CellRendererText(), text=1)
        self.tree.append_column(col_codec)

        col_bitrate = Gtk.TreeViewColumn("Débit", Gtk.CellRendererText(), text=2)
        self.tree.append_column(col_bitrate)

        col_country = Gtk.TreeViewColumn("Pays", Gtk.CellRendererText(), text=3)
        self.tree.append_column(col_country)

        col_votes = Gtk.TreeViewColumn("Popularité", Gtk.CellRendererText(), text=5)
        self.tree.append_column(col_votes)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_shadow_type(Gtk.ShadowType.IN)
        scroll.add(self.tree)
        content.pack_start(scroll, True, True, 0)

        self.lbl_status = Gtk.Label(label="Recherche des flux en cours...")
        self.lbl_status.set_halign(Gtk.Align.START)
        content.pack_start(self.lbl_status, False, False, 0)

        self.show_all()
        GLib.idle_add(self.perform_search)

    def perform_search(self):
        query = self.entry_query.get_text().strip()
        self.lbl_status.set_text("Recherche sur Radio-Browser...")
        self.store.clear()

        def worker():
            results = search_radio_browser_api(name=query, country_code=self.country_code, limit=20)
            if not results and self.country_code:
                # Si aucun résultat avec filtre pays, élargir au monde entier
                results = search_radio_browser_api(name=query, limit=20)

            def on_done():
                if not results:
                    self.lbl_status.set_text("Aucun flux trouvé pour ce nom. Modifiez le texte ci-dessus.")
                    return
                for r in results:
                    name = r.get("name", "Sans nom")
                    codec = r.get("codec", "MP3")
                    bitrate = f"{r.get('bitrate', 128)} kbps" if r.get('bitrate') else "-"
                    country = r.get("country", "")
                    url = r.get("url_resolved") or r.get("url", "")
                    votes = r.get("votes", 0)
                    self.store.append([name, codec, bitrate, country, url, votes])
                self.lbl_status.set_text(f"{len(results)} flux trouvés. Sélectionnez le flux souhaité puis validez.")
                # Sélectionner le premier résultat par défaut
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

# -----------------------------------------------------------------------------
# Fenêtre Principale : Découverte & Importation de Radios
# Main Window: Discovery & Import of Radios
# -----------------------------------------------------------------------------




def parse_user_radio_file(path):
    """
    Parse universel pour fichiers de radios utilisateurs :
    - XML : Radio Tray, TiMonde, formats bouquets ou OPML (tolérant aux & non échappés)
    - JSON : radiotray-ng (groupes) ou listes plates
    - CSV / TSV : auto-détection du délimiteur (,, ;, tab) et des colonnes (Nom, URL, Pays, Groupe)
    - M3U / M3U8 : playlists avec ou sans métadonnées group-title
    - PLS : playlists au format INI standard
    """
    if not os.path.isfile(path):
        return []

    ext = os.path.splitext(path)[1].lower()
    base_name = os.path.splitext(os.path.basename(path))[0]
    stations = []

    # 1. XML
    if ext == ".xml":
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                raw_xml = f.read()

            # Assainissement des esperluettes orphelines
            sanitized = re.sub(r'&(?!(amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)', '&amp;', raw_xml)
            root = ET.fromstring(sanitized)
            def_country = (root.attrib.get("country") or root.attrib.get("countrycode") or "").strip().upper()

            def walk_group(elem, current_path=""):
                local_stations = []
                g_name = elem.attrib.get("name", "").strip()
                if elem != root and g_name and g_name.lower() != "root":
                    full_group = f"{current_path}/{g_name}".strip("/") if current_path else g_name
                else:
                    full_group = current_path

                elem_country = (elem.attrib.get("country") or elem.attrib.get("countrycode") or def_country).strip().upper()

                for child in elem:
                    if child.tag in ("group", "region", "national"):
                        sub_path = full_group
                        if child.tag == "region" and child.attrib.get("name"):
                            sub_name = child.attrib.get("name").strip()
                            sub_path = f"{full_group}/{sub_name}".strip("/") if full_group else sub_name
                        local_stations.extend(walk_group(child, sub_path))
                    elif child.tag in ("bookmark", "station"):
                        name = child.attrib.get("name", "").strip()
                        url = clean_stream_url(child.attrib.get("url", "").strip())
                        country = (child.attrib.get("country") or child.attrib.get("countrycode") or elem_country).strip().upper()
                        tz = (child.attrib.get("timezone") or child.attrib.get("tz") or "").strip()
                        genre = child.attrib.get("genre", "").strip()
                        explicit_grp = child.attrib.get("group", "").strip()
                        if name and url and not name.startswith("[separator"):
                            grp = explicit_grp if explicit_grp else (full_group if full_group else base_name)
                            if not tz and country:
                                tz = infer_timezone(country, name, grp)
                            local_stations.append({
                                "name": name,
                                "url": url,
                                "group": grp,
                                "country": country,
                                "timezone": tz,
                                "genre": genre
                            })
                return local_stations

            stations = walk_group(root, "")
            if not stations:
                # Format plat de secours
                for elem in root.iter():
                    if elem.tag in ("station", "bookmark"):
                        name = elem.attrib.get("name", "").strip()
                        url = elem.attrib.get("url", "").strip()
                        country = (elem.attrib.get("country") or elem.attrib.get("countrycode") or def_country).strip().upper()
                        tz = (elem.attrib.get("timezone") or elem.attrib.get("tz") or "").strip()
                        grp = elem.attrib.get("group") or base_name
                        genre = elem.attrib.get("genre", "").strip()
                        if name and url and not name.startswith("[separator"):
                            if not tz and country:
                                tz = infer_timezone(country, name, grp)
                            stations.append({
                                "name": name,
                                "url": url,
                                "group": grp,
                                "country": country,
                                "timezone": tz,
                                "genre": genre
                            })
        except Exception as e:
            sys.stderr.write(f"Erreur lecture XML utilisateur {path}: {e}\n")

    # 2. JSON
    elif ext == ".json":
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        if "group" in item and "stations" in item and isinstance(item["stations"], list):
                            grp_name = item.get("group", "").strip() or base_name
                            for s in item["stations"]:
                                if isinstance(s, dict):
                                    name = s.get("name", "").strip()
                                    url = s.get("url", "").strip()
                                    country = (s.get("country") or s.get("country_code") or "").strip().upper()
                                    tz = (s.get("timezone") or s.get("tz") or "").strip()
                                    if not tz and country:
                                        tz = infer_timezone(country, name, grp_name)
                                    genre = (s.get("genre") or "").strip()
                                    if name and url:
                                        stations.append({
                                            "name": name,
                                            "url": url,
                                            "group": grp_name,
                                            "country": country,
                                            "timezone": tz,
                                            "genre": genre
                                        })
                        elif "name" in item and "url" in item:
                            name = item.get("name", "").strip()
                            url = item.get("url", "").strip()
                            grp = item.get("group", "").strip() or base_name
                            country = (item.get("country") or item.get("country_code") or "").strip().upper()
                            tz = (item.get("timezone") or item.get("tz") or "").strip()
                            if not tz and country:
                                tz = infer_timezone(country, name, grp)
                            genre = (item.get("genre") or "").strip()
                            if name and url:
                                stations.append({
                                    "name": name,
                                    "url": url,
                                    "group": grp,
                                    "country": country,
                                    "timezone": tz,
                                    "genre": genre
                                })
        except Exception as e:
            sys.stderr.write(f"Erreur lecture JSON utilisateur {path}: {e}\n")

    # 3. CSV
    elif ext in (".csv", ".txt", ".tsv"):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                sample = f.read(4096)
                f.seek(0)
                delimiter = ';' if ';' in sample and sample.count(';') > sample.count(',') else (',' if ',' in sample else '\t')
                reader = csv.reader(f, delimiter=delimiter)
                for row in reader:
                    clean_row = [c.strip() for c in row if c.strip()]
                    if not clean_row:
                        continue
                    first = clean_row[0].lower()
                    if first.startswith("#") or first in ("nom", "name", "groupe", "group", "station"):
                        continue
                    if len(clean_row) == 2 and (clean_row[1].startswith("http://") or clean_row[1].startswith("https://")):
                        tz = infer_timezone("", clean_row[0], base_name)
                        stations.append({
                            "name": clean_row[0],
                            "url": clean_row[1],
                            "group": base_name,
                            "country": "",
                            "genre": "",
                            "timezone": tz
                        })
                    elif len(clean_row) == 3:
                        if clean_row[1].startswith("http://") or clean_row[1].startswith("https://"):
                            c = clean_row[2].upper()
                            tz = infer_timezone(c, clean_row[0], base_name)
                            stations.append({
                                "name": clean_row[0],
                                "url": clean_row[1],
                                "group": base_name,
                                "country": c,
                                "genre": "",
                                "timezone": tz
                            })
                        elif clean_row[2].startswith("http://") or clean_row[2].startswith("https://"):
                            stations.append({
                                "name": clean_row[1],
                                "url": clean_row[2],
                                "group": clean_row[0],
                                "country": "",
                                "genre": "",
                                "timezone": ""
                            })
                    elif len(clean_row) >= 4 and (clean_row[2].startswith("http://") or clean_row[2].startswith("https://")):
                        st_c = clean_row[3].upper()
                        tz_val = clean_row[4].strip() if len(clean_row) >= 5 else ""
                        if not tz_val and st_c:
                            tz_val = infer_timezone(st_c, clean_row[1], clean_row[0])
                        stations.append({
                            "name": clean_row[1],
                            "url": clean_row[2],
                            "group": clean_row[0],
                            "country": st_c,
                            "genre": "",
                            "timezone": tz_val
                        })
        except Exception as e:
            sys.stderr.write(f"Erreur lecture CSV utilisateur {path}: {e}\n")

    # 4. M3U / M3U8
    elif ext in (".m3u", ".m3u8"):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            current_name = None
            current_group = base_name
            for line in lines:
                l = line.strip()
                if not l:
                    continue
                if l.startswith("#EXTINF:"):
                    grp_match = re.search(r'group-title="([^"]+)"', l, re.IGNORECASE)
                    if grp_match:
                        current_group = grp_match.group(1).strip()
                    else:
                        current_group = base_name
                    if "," in l:
                        current_name = l.split(",", 1)[1].strip()
                elif not l.startswith("#") and (l.startswith("http://") or l.startswith("https://")):
                    name = current_name or os.path.basename(l)
                    stations.append({
                        "name": name,
                        "url": l,
                        "group": current_group,
                        "country": "",
                        "genre": ""
                    })
                    current_name = None
        except Exception as e:
            sys.stderr.write(f"Erreur lecture M3U utilisateur {path}: {e}\n")

    # 5. PLS
    elif ext == ".pls":
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            entries = {}
            for line in lines:
                l = line.strip()
                if "=" in l and not l.startswith("#") and not l.startswith("["):
                    k, v = l.split("=", 1)
                    entries[k.strip().lower()] = v.strip()
            idx = 1
            while f"file{idx}" in entries:
                url = entries.get(f"file{idx}", "")
                title = entries.get(f"title{idx}", f"Station {idx}")
                if url.startswith("http://") or url.startswith("https://"):
                    stations.append({
                        "name": title,
                        "url": url,
                        "group": base_name,
                        "country": "",
                        "genre": ""
                    })
                idx += 1
        except Exception as e:
            sys.stderr.write(f"Erreur lecture PLS utilisateur {path}: {e}\n")

    return stations





class DiscoverRadiosWindow(Gtk.Window):
    def __init__(
        self,
        existing_stations,
        bouquets_db,
        initial_tab=0,
        initial_file=None,
        available_groups=None,
        embedded=False,
        on_import_callback=None,
        on_export_csv_callback=None,
        on_backup_xml_callback=None,
    ):
        self.embedded = embedded
        self.on_import_callback = on_import_callback
        self.on_export_csv_callback = on_export_csv_callback
        self.on_backup_xml_callback = on_backup_xml_callback
        if not embedded:
            super().__init__(title=_("Découvrir et importer des radios (TiMonde)"))
            self.set_default_size(960, 640)
            self.set_position(Gtk.WindowPosition.CENTER)
            self.set_border_width(10)

            for icon_path in [
                "/usr/share/icons/hicolor/48x48/apps/timonde_on.png",
                "/usr/share/icons/hicolor/32x32/apps/timonde_on.png",
                "/usr/share/icons/hicolor/24x24/apps/timonde_on.png",
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "../icons/hicolor/48x48/apps/timonde_on.png"),
            ]:
                if os.path.exists(icon_path):
                    try:
                        self.set_icon_from_file(icon_path)
                        break
                    except Exception:
                        pass
            else:
                self.set_icon_name("audio-x-generic")

            self.connect("destroy", self.on_destroy)
            self.set_focus_on_map(True)
        else:
            super().__init__()

        self.existing_stations = existing_stations
        self.existing_urls = {s.get("url", "").strip() for s in existing_stations}
        self.existing_names = {s.get("name", "").strip().lower() for s in existing_stations}
        self.bouquets_db = bouquets_db
        self.available_groups = available_groups if available_groups is not None else get_user_bookmarks_groups()

        self.saved = False
        self.chosen_group_name = ""
        self.selected_stations = []

        self.executor = ThreadPoolExecutor(max_workers=8)
        self.current_check_generation = 0
        self.current_rb_check_generation = 0
        self.current_files_check_generation = 0
        self.current_file_path = None
        self.current_file_stations = []

        self.preview_buttons = []
        self.preview_labels = []
        self.preview_player = StreamPreviewPlayer(on_status_change=self.on_preview_status_update)

        # Magasin universel de complétion pays (indexé sur les 55 langues)
        self.country_comp_store = Gtk.ListStore(str, str, str, str)
        for c_code, c_info in sorted(self.bouquets_db.items(), key=lambda x: normalize_lookup(x[1].get("country_name", ""))):
            nat_str = normalize_lookup(f"{c_info['name']} {c_code} {' '.join(NATIVE_COUNTRY_NAMES.get(c_code, []))}")
            self.country_comp_store.append([
                c_info["name"],
                c_code,
                normalize_lookup(c_info.get("country_name", c_code)),
                nat_str,
            ])

        # Construction des 3 vues autonomes de 1er niveau
        self.view_search = self.build_view_search()
        self.view_bouquets = self.build_view_bouquets()
        self.view_files = self.build_view_files()

        # Initialisation des données
        self.update_languages()
        self.update_regions_combo()
        self.load_current_bouquet()

        if initial_file:
            self.load_file_into_store(initial_file)
        elif getattr(self, "available_examples", None):
            self.load_file_into_store(self.available_examples[0][0])

        if not self.embedded:
            self.build_standalone_window(initial_tab)

    def setup_country_completion(self, entry, on_selected_cb=None):
        country_completion = Gtk.EntryCompletion()
        country_completion.set_model(self.country_comp_store)
        country_completion.set_text_column(0)
        country_completion.set_minimum_key_length(1)
        country_completion.set_inline_completion(False)
        country_completion.set_popup_completion(True)

        def country_match_func(comp, key, tree_iter, data):
            norm_key = normalize_lookup(key)
            if not norm_key:
                return False
            code = self.country_comp_store.get_value(tree_iter, 1)
            norm_name = self.country_comp_store.get_value(tree_iter, 2) or ""
            norm_nat = self.country_comp_store.get_value(tree_iter, 3) or ""
            norm_code = code.lower()
            return (norm_key in norm_name) or (norm_key == norm_code) or (norm_code.startswith(norm_key)) or (norm_key in norm_nat)

        country_completion.set_match_func(country_match_func, None)

        def on_country_match_selected(comp, model, tree_iter):
            c_code = model.get_value(tree_iter, 1)
            disp_name = model.get_value(tree_iter, 0)
            entry.set_text(disp_name)
            if on_selected_cb:
                on_selected_cb(c_code, disp_name)
            return True

        country_completion.connect("match-selected", on_country_match_selected)
        entry.set_completion(country_completion)
        return country_completion

    # -------------------------------------------------------------------------
    # Helper Partagé : Barre inférieure de groupe de destination & import
    # -------------------------------------------------------------------------
    def create_target_group_bar(self, view_key, default_group_name, on_import_func):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        vbox.pack_start(hbox, False, False, 0)

        lbl = Gtk.Label(label="<b>" + _("Groupe :") + "</b>")
        lbl.set_use_markup(True)
        hbox.pack_start(lbl, False, False, 0)

        entry = Gtk.Entry()
        entry.set_text(default_group_name)
        entry.set_width_chars(26)
        entry.set_placeholder_text(_("Ex: /France/Jazz ou / pour racine"))
        entry.set_can_focus(True)
        entry.set_editable(True)

        comp = Gtk.EntryCompletion()
        store = Gtk.ListStore(str)
        store.append(["[ / ] (Racine — Sans groupe)"])
        for g in sorted(self.available_groups):
            if g and g not in ("[ / ] (Racine — Sans groupe)", "/"):
                store.append([g])
        comp.set_model(store)
        comp.set_text_column(0)
        comp.set_inline_completion(True)
        comp.set_popup_completion(True)
        entry.set_completion(comp)

        entry.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, "edit-clear")
        entry.set_icon_tooltip_text(Gtk.EntryIconPosition.SECONDARY, _("Effacer le champ"))
        def on_clear(e, icon_pos, event):
            if icon_pos == Gtk.EntryIconPosition.SECONDARY:
                e.set_text("")
        entry.connect("icon-press", on_clear)
        hbox.pack_start(entry, True, True, 0)

        btn_choose = make_btn("", "pan-down", _("Choisir parmi les groupes existants"))
        def on_choose(b):
            menu = Gtk.Menu()
            it_root = Gtk.MenuItem(label="[ / ] (Racine — Sans groupe)")
            it_root.connect("activate", lambda mi: entry.set_text("/"))
            menu.append(it_root)
            if self.available_groups:
                menu.append(Gtk.SeparatorMenuItem())
                for g in sorted(self.available_groups):
                    if g and g not in ("[ / ] (Racine — Sans groupe)", "/"):
                        item = Gtk.MenuItem(label=g)
                        item.connect("activate", lambda mi, grp=g: entry.set_text(grp))
                        menu.append(item)
            menu.show_all()
            menu.popup_at_widget(b, Gdk.Gravity.SOUTH_WEST, Gdk.Gravity.NORTH_WEST, None)
        btn_choose.connect("clicked", on_choose)
        hbox.pack_start(btn_choose, False, False, 0)

        btn_help = make_btn("", "help-browser", _("Aide sur les groupes et sous-groupes"))
        btn_help.connect("clicked", self.on_show_group_naming_help)
        hbox.pack_start(btn_help, False, False, 0)

        btn_preview = make_btn(_("Écouter"), "media-playback-start", _("Écouter la radio sélectionnée"))
        btn_preview.connect("clicked", lambda w: self.on_preview_clicked(view_key))
        self.preview_buttons.append(btn_preview)
        hbox.pack_start(btn_preview, False, False, 0)

        lbl_preview = Gtk.Label(label="")
        lbl_preview.set_use_markup(True)
        lbl_preview.set_halign(Gtk.Align.START)
        self.preview_labels.append(lbl_preview)
        hbox.pack_start(lbl_preview, False, False, 0)

        btn_import = make_btn(_("Importer dans mes favoris"), "list-add")
        btn_import.get_style_context().add_class("suggested-action")
        btn_import.set_sensitive(False)
        btn_import.connect("clicked", lambda w: on_import_func())
        hbox.pack_end(btn_import, False, False, 0)

        return vbox, entry, btn_import

    # -------------------------------------------------------------------------
    # 1. Atelier « Rechercher en ligne » (Radio-Browser)
    # -------------------------------------------------------------------------
    def build_view_search(self):
        tab_rb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        tab_rb.set_border_width(8)

        # 1. En-tête explicatif Radio-Browser
        info_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        lbl_info = Gtk.Label()
        lbl_info.set_markup("<small><i>" + _("Recherche mondiale sur l'annuaire libre et collaboratif <b>Radio-Browser</b> (+45 000 stations).") + "</i></small>")
        lbl_info.set_xalign(0.0)
        info_box.pack_start(lbl_info, True, True, 0)
        tab_rb.pack_start(info_box, False, False, 0)

        # 2. Ligne 1 : Mots-clés, Genre & Bouton de recherche
        rb_filter_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        tab_rb.pack_start(rb_filter_box, False, False, 0)

        lbl_rb_name = Gtk.Label(label=_("Mot-clé :"))
        rb_filter_box.pack_start(lbl_rb_name, False, False, 0)

        self.entry_rb_name = Gtk.Entry()
        self.entry_rb_name.set_placeholder_text("Ex: Jazz, Rock, FIP, RMC, BBC...")
        self.entry_rb_name.set_can_focus(True)
        self.entry_rb_name.set_editable(True)
        self.entry_rb_name.connect("activate", lambda w: self.on_search_rb_clicked())
        rb_filter_box.pack_start(self.entry_rb_name, True, True, 0)

        lbl_rb_tag = Gtk.Label(label=_("Genre :"))
        rb_filter_box.pack_start(lbl_rb_tag, False, False, 0)

        self.entry_rb_tag = Gtk.Entry()
        self.entry_rb_tag.set_placeholder_text("Ex: news, classical, ambient...")
        self.entry_rb_tag.set_width_chars(16)
        self.entry_rb_tag.set_can_focus(True)
        self.entry_rb_tag.set_editable(True)
        self.entry_rb_tag.connect("activate", lambda w: self.on_search_rb_clicked())
        rb_filter_box.pack_start(self.entry_rb_tag, False, False, 0)

        btn_rb_search = make_btn(_("Rechercher"), "system-search")
        btn_rb_search.get_style_context().add_class("suggested-action")
        btn_rb_search.connect("clicked", lambda w: self.on_search_rb_clicked())
        rb_filter_box.pack_start(btn_rb_search, False, False, 0)

        # 3. Ligne 2 : Filtres ciblés (Pays explicite et Langue avec autocomplétion)
        rb_geo_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        tab_rb.pack_start(rb_geo_box, False, False, 0)

        self.check_rb_only_country = Gtk.CheckButton(label=_("Filtrer par pays :"))
        self.check_rb_only_country.set_active(True)
        rb_geo_box.pack_start(self.check_rb_only_country, False, False, 0)

        self.entry_rb_country = Gtk.Entry()
        self.entry_rb_country.set_placeholder_text(_("Tous les pays (mondial)"))
        self.entry_rb_country.set_width_chars(26)
        self.entry_rb_country.set_can_focus(True)
        self.entry_rb_country.set_editable(True)
        self.entry_rb_country.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, "edit-clear")
        self.entry_rb_country.set_icon_tooltip_text(Gtk.EntryIconPosition.SECONDARY, _("Effacer le filtre pays"))
        def on_rb_country_clear_press(entry, icon_pos, event):
            if icon_pos == Gtk.EntryIconPosition.SECONDARY:
                entry.set_text("")
                self.check_rb_only_country.set_active(False)
        self.entry_rb_country.connect("icon-press", on_rb_country_clear_press)
        self.entry_rb_country.connect("activate", lambda w: self.on_search_rb_clicked())

        def on_rb_country_selected(c_code, disp_name):
            self.check_rb_only_country.set_active(True)
            self.entry_rb_country.set_sensitive(True)

        self.setup_country_completion(self.entry_rb_country, on_rb_country_selected)

        def on_check_country_toggled(btn):
            active = btn.get_active()
            self.entry_rb_country.set_sensitive(active)
            if active and not self.entry_rb_country.get_text().strip():
                c_code = self.get_selected_country_code()
                c_info = self.bouquets_db.get(c_code, {})
                if c_info:
                    self.entry_rb_country.set_text(c_info.get("name", c_code))

        self.check_rb_only_country.connect("toggled", on_check_country_toggled)
        rb_geo_box.pack_start(self.entry_rb_country, False, False, 0)

        init_c_code = "FR" if "FR" in self.bouquets_db else (list(self.bouquets_db.keys())[0] if self.bouquets_db else "")
        if init_c_code and init_c_code in self.bouquets_db:
            self.entry_rb_country.set_text(self.bouquets_db[init_c_code].get("name", init_c_code))

        lbl_rb_lang = Gtk.Label(label=_("Langue :"))
        rb_geo_box.pack_start(lbl_rb_lang, False, False, 0)

        self.entry_rb_lang = Gtk.Entry()
        self.entry_rb_lang.set_placeholder_text(_("Toutes les langues"))
        self.entry_rb_lang.set_width_chars(20)
        self.entry_rb_lang.set_can_focus(True)
        self.entry_rb_lang.set_editable(True)
        self.entry_rb_lang.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, "edit-clear")
        self.entry_rb_lang.set_icon_tooltip_text(Gtk.EntryIconPosition.SECONDARY, _("Effacer le filtre langue"))
        def on_rb_lang_clear_press(entry, icon_pos, event):
            if icon_pos == Gtk.EntryIconPosition.SECONDARY:
                entry.set_text("")
        self.entry_rb_lang.connect("icon-press", on_rb_lang_clear_press)
        self.entry_rb_lang.connect("activate", lambda w: self.on_search_rb_clicked())

        # Complétion langue
        lang_completion = Gtk.EntryCompletion()
        self.lang_comp_store = Gtk.ListStore(str, str, str, str)
        for api_key, fr_name, cnt in RADIO_BROWSER_LANGUAGES:
            native_str = DISPLAY_NATIVE_MAP.get(api_key, "")
            if native_str:
                display_label = f"{fr_name} — {native_str} ({api_key})"
            elif fr_name.lower() != api_key:
                display_label = f"{fr_name} ({api_key})"
            else:
                display_label = fr_name
            aliases_str = " ".join(NATIVE_LANGUAGE_NAMES.get(api_key, []))
            norm_all = normalize_lookup(f"{display_label} {api_key} {fr_name} {native_str} {aliases_str}")
            self.lang_comp_store.append([display_label, api_key, fr_name, norm_all])

        lang_completion.set_model(self.lang_comp_store)
        lang_completion.set_text_column(0)
        lang_completion.set_minimum_key_length(1)
        lang_completion.set_inline_completion(False)
        lang_completion.set_popup_completion(True)

        def lang_match_func(comp, key, tree_iter, data):
            norm_key = normalize_lookup(key)
            if not norm_key:
                return False
            norm_all = self.lang_comp_store.get_value(tree_iter, 3) or ""
            return norm_key in norm_all

        lang_completion.set_match_func(lang_match_func, None)

        def on_lang_match_selected(comp, model, tree_iter):
            disp = model.get_value(tree_iter, 0)
            self.entry_rb_lang.set_text(disp)
            return True

        lang_completion.connect("match-selected", on_lang_match_selected)
        self.entry_rb_lang.set_completion(lang_completion)
        rb_geo_box.pack_start(self.entry_rb_lang, False, False, 0)

        # Tableau des résultats
        # Store: [checked, name, country, tags, codec_bitrate, votes, url, is_dup, health_markup, dup_markup, row_id]
        self.rb_store = Gtk.ListStore(bool, str, str, str, str, int, str, bool, str, str, int)
        self.rb_tree = Gtk.TreeView(model=self.rb_store)
        self.rb_tree.connect("row-activated", lambda tv, path, col: self.on_tree_row_activated(tv, path, col, "search"))

        renderer_rb_check = Gtk.CellRendererToggle()
        renderer_rb_check.connect("toggled", self.on_rb_check_toggled)
        col_rb_check = Gtk.TreeViewColumn(_("Ajouter"), renderer_rb_check, active=0)
        self.rb_tree.append_column(col_rb_check)

        col_rb_name = Gtk.TreeViewColumn(_("Station"), Gtk.CellRendererText(), text=1)
        col_rb_name.set_expand(True)
        self.rb_tree.append_column(col_rb_name)

        col_rb_c = Gtk.TreeViewColumn(_("Pays"), Gtk.CellRendererText(), text=2)
        col_rb_c.set_fixed_width(65)
        self.rb_tree.append_column(col_rb_c)

        col_rb_tags = Gtk.TreeViewColumn(_("Genre / Tags"), Gtk.CellRendererText(), text=3)
        col_rb_tags.set_fixed_width(160)
        self.rb_tree.append_column(col_rb_tags)

        col_rb_codec = Gtk.TreeViewColumn(_("Format & Débit"), Gtk.CellRendererText(), text=4)
        col_rb_codec.set_fixed_width(120)
        self.rb_tree.append_column(col_rb_codec)

        col_rb_health = Gtk.TreeViewColumn(_("Disponibilité"), Gtk.CellRendererText(), markup=8)
        col_rb_health.set_fixed_width(150)
        self.rb_tree.append_column(col_rb_health)

        col_rb_dup = Gtk.TreeViewColumn(_("Statut Favoris"), Gtk.CellRendererText(), markup=9)
        col_rb_dup.set_fixed_width(130)
        self.rb_tree.append_column(col_rb_dup)

        col_rb_votes = Gtk.TreeViewColumn(_("Votes"), Gtk.CellRendererText(), text=5)
        col_rb_votes.set_fixed_width(65)
        self.rb_tree.append_column(col_rb_votes)

        scroll_rb = Gtk.ScrolledWindow()
        scroll_rb.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll_rb.set_shadow_type(Gtk.ShadowType.IN)
        scroll_rb.add(self.rb_tree)
        tab_rb.pack_start(scroll_rb, True, True, 0)

        # Ligne d'actions sous le tableau
        rb_bot_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        tab_rb.pack_start(rb_bot_box, False, False, 0)

        btn_rb_check_all = make_btn(_("Tout cocher"), "edit-select-all")
        btn_rb_check_all.connect("clicked", lambda w: self.set_rb_checks(True))
        rb_bot_box.pack_start(btn_rb_check_all, False, False, 0)

        btn_rb_uncheck_all = make_btn(_("Tout décocher"), "edit-clear")
        btn_rb_uncheck_all.connect("clicked", lambda w: self.set_rb_checks(False))
        rb_bot_box.pack_start(btn_rb_uncheck_all, False, False, 0)

        self.btn_rb_test = make_btn(_("Tester les flux"), "network-idle", _("Vérifier la disponibilité en direct des radios trouvées"))
        self.btn_rb_test.connect("clicked", lambda w: self.test_rb_streams())
        rb_bot_box.pack_start(self.btn_rb_test, False, False, 0)

        self.lbl_rb_status = Gtk.Label(label=_("Saisissez un mot-clé ou cliquez sur Rechercher pour explorer l'annuaire."))
        self.lbl_rb_status.set_halign(Gtk.Align.END)
        rb_bot_box.pack_end(self.lbl_rb_status, False, False, 0)

        # Barre de groupe et import
        bar_box, self.entry_group_search, self.btn_import_search = self.create_target_group_bar(
            "search", "Radio-Browser", self.on_import_search
        )
        tab_rb.pack_start(bar_box, False, False, 0)

        return tab_rb

    # -------------------------------------------------------------------------
    # 2. Atelier « Bouquets par pays » (DAB+ & Vérifiés)
    # -------------------------------------------------------------------------
    def build_view_bouquets(self):
        tab_bouquets = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        tab_bouquets.set_border_width(8)

        # 1. En-tête explicatif Bouquets DAB+
        info_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        lbl_info = Gtk.Label()
        lbl_info.set_markup("<small><i>" + _("Sélection officielle et vérifiée parmi 146 pays et régions (bouquets numériques DAB+ et grandes stations nationales).") + "</i></small>")
        lbl_info.set_xalign(0.0)
        info_box.pack_start(lbl_info, True, True, 0)
        tab_bouquets.pack_start(info_box, False, False, 0)

        # 2. Barre supérieure : Sélecteur de pays universel (55 langues ISO)
        top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        tab_bouquets.pack_start(top_bar, False, False, 0)

        lbl_country = Gtk.Label(label="<b>" + _("Pays :") + "</b>")
        lbl_country.set_use_markup(True)
        top_bar.pack_start(lbl_country, False, False, 0)

        self.combo_country = Gtk.ComboBoxText.new_with_entry()
        self.entry_country = self.combo_country.get_child()
        self.entry_country.set_placeholder_text(_("Tapez un pays (ex: France, Deutschland, Canada...)"))
        self.entry_country.set_width_chars(28)
        self._last_resolved_country = "FR"

        def on_bouquets_country_match(c_code, disp_name):
            self.combo_country.set_active_id(c_code)

        self.setup_country_completion(self.entry_country, on_bouquets_country_match)

        for c_code, c_info in sorted(self.bouquets_db.items(), key=lambda x: normalize_lookup(x[1].get("country_name", ""))):
            self.combo_country.append(c_code, c_info["name"])

        if "FR" in self.bouquets_db:
            self.combo_country.set_active_id("FR")
        elif self.bouquets_db:
            self.combo_country.set_active(0)

        self.combo_country.connect("changed", self.on_country_changed)
        top_bar.pack_start(self.combo_country, False, False, 0)

        # Options National / Régions & Langue
        scope_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        tab_bouquets.pack_start(scope_box, False, False, 0)

        self.radio_national = Gtk.RadioButton.new_with_label(None, _("Bouquet National (Grandes stations)"))
        self.radio_national.connect("toggled", self.on_scope_changed)
        scope_box.pack_start(self.radio_national, False, False, 0)

        self.radio_region = Gtk.RadioButton.new_with_label_from_widget(self.radio_national, _("Régions & Locales :"))
        self.radio_region.connect("toggled", self.on_scope_changed)
        scope_box.pack_start(self.radio_region, False, False, 0)

        self.combo_region = Gtk.ComboBoxText()
        self.combo_region.connect("changed", self.on_region_changed)
        scope_box.pack_start(self.combo_region, False, False, 0)

        self.lbl_lang = Gtk.Label(label="<b>" + _("Langue :") + "</b>")
        self.lbl_lang.set_use_markup(True)
        scope_box.pack_start(self.lbl_lang, False, False, 0)

        self.combo_lang = Gtk.ComboBoxText()
        self.combo_lang.connect("changed", self.on_lang_changed)
        scope_box.pack_start(self.combo_lang, False, False, 0)

        # Tableau des stations du bouquet
        # Store: [checked, name, genre, health_markup, dup_markup, url, is_dup, is_dead, row_id]
        self.bouquet_store = Gtk.ListStore(bool, str, str, str, str, str, bool, bool, int)
        self.bouquet_tree = Gtk.TreeView(model=self.bouquet_store)
        self.bouquet_tree.connect("row-activated", lambda tv, path, col: self.on_tree_row_activated(tv, path, col, "bouquets"))

        renderer_check = Gtk.CellRendererToggle()
        renderer_check.connect("toggled", self.on_bouquet_check_toggled)
        col_check = Gtk.TreeViewColumn(_("Importer"), renderer_check, active=0)
        self.bouquet_tree.append_column(col_check)

        col_name = Gtk.TreeViewColumn(_("Station"), Gtk.CellRendererText(), text=1)
        col_name.set_expand(True)
        self.bouquet_tree.append_column(col_name)

        col_genre = Gtk.TreeViewColumn(_("Genre / Thématique"), Gtk.CellRendererText(), text=2)
        col_genre.set_fixed_width(170)
        self.bouquet_tree.append_column(col_genre)

        renderer_health = Gtk.CellRendererText()
        col_health = Gtk.TreeViewColumn(_("Disponibilité en direct"), renderer_health, markup=3)
        col_health.set_fixed_width(160)
        self.bouquet_tree.append_column(col_health)

        renderer_dup = Gtk.CellRendererText()
        col_dup = Gtk.TreeViewColumn(_("Statut Favoris"), renderer_dup, markup=4)
        col_dup.set_fixed_width(150)
        self.bouquet_tree.append_column(col_dup)

        scroll_b = Gtk.ScrolledWindow()
        scroll_b.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll_b.set_shadow_type(Gtk.ShadowType.IN)
        scroll_b.add(self.bouquet_tree)
        tab_bouquets.pack_start(scroll_b, True, True, 0)

        # Ligne d'actions sous la liste
        b_action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        tab_bouquets.pack_start(b_action_box, False, False, 0)

        self.btn_bouquet_check_all = make_btn(_("Tout cocher"), "edit-select-all")
        self.btn_bouquet_check_all.connect("clicked", lambda w: self.set_bouquet_checks(True))
        b_action_box.pack_start(self.btn_bouquet_check_all, False, False, 0)

        self.btn_bouquet_uncheck_all = make_btn(_("Tout décocher"), "edit-clear")
        self.btn_bouquet_uncheck_all.connect("clicked", lambda w: self.set_bouquet_checks(False))
        b_action_box.pack_start(self.btn_bouquet_uncheck_all, False, False, 0)

        self.btn_bouquet_test = make_btn(_("Tester les flux"), "network-idle", _("Vérifier la disponibilité en direct des radios"))
        self.btn_bouquet_test.connect("clicked", lambda w: self.test_bouquet_streams())
        b_action_box.pack_start(self.btn_bouquet_test, False, False, 0)

        self.btn_repair = make_btn(_("Réparer le flux..."), "system-search", _("Remplacer le lien sélectionné par un flux officiel actif"))
        self.btn_repair.connect("clicked", self.on_repair_clicked)
        b_action_box.pack_start(self.btn_repair, False, False, 0)

        self.lbl_bouquet_count = Gtk.Label()
        self.lbl_bouquet_count.set_halign(Gtk.Align.END)
        b_action_box.pack_end(self.lbl_bouquet_count, False, False, 0)

        # Barre de groupe et import
        bar_box, self.entry_group_bouquets, self.btn_import_bouquets = self.create_target_group_bar(
            "bouquets", "Radios Nationales (France)", self.on_import_bouquets
        )
        tab_bouquets.pack_start(bar_box, False, False, 0)

        return tab_bouquets

    # -------------------------------------------------------------------------
    # 3. Atelier « Importer & Exporter » (Fichiers, Exemples, CSV, Dossiers)
    # -------------------------------------------------------------------------
    def build_view_files(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(8)

        # 1. Rangée supérieure : Sélection et gestion des Exemples Thématiques (Mise en valeur)
        ex_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.pack_start(ex_bar, False, False, 0)

        lbl_ex = Gtk.Label()
        lbl_ex.set_markup("<b>" + _("Exemples thématiques :") + "</b>")
        lbl_ex.set_halign(Gtk.Align.START)
        ex_bar.pack_start(lbl_ex, False, False, 0)

        self.combo_examples = Gtk.ComboBoxText()
        self.combo_examples.get_style_context().add_class("highlight-combo")
        self.available_examples = list_available_examples()
        for fpath, label, title in self.available_examples:
            self.combo_examples.append(fpath, label)
        if self.available_examples:
            self.combo_examples.set_active(0)
        self.combo_examples.connect("changed", self.on_files_example_changed)
        ex_bar.pack_start(self.combo_examples, True, True, 0)

        btn_refresh_ex = make_btn("", "view-refresh", _("Actualiser la liste des exemples"))
        btn_refresh_ex.connect("clicked", self.on_refresh_examples_clicked)
        ex_bar.pack_start(btn_refresh_ex, False, False, 0)

        btn_open_ex = make_btn(_("Dossier des exemples"), "folder-open", _("Ouvrir ~/.config/timonde/examples"))
        btn_open_ex.connect("clicked", self.on_open_examples_folder)
        ex_bar.pack_start(btn_open_ex, False, False, 0)

        btn_restore_ex = make_btn(_("Restaurer exemples"), "edit-undo", _("Rétablir les 19 exemples d'origine"))
        btn_restore_ex.connect("clicked", self.on_restore_examples_action)
        ex_bar.pack_start(btn_restore_ex, False, False, 0)

        # 2. Rangée inférieure : Fichier personnel / externe & Outils (À la ligne)
        ext_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.pack_start(ext_bar, False, False, 0)

        lbl_custom = Gtk.Label()
        lbl_custom.set_markup("<b>" + _("Fichier externe :") + "</b>")
        lbl_custom.set_halign(Gtk.Align.START)
        ext_bar.pack_start(lbl_custom, False, False, 0)

        btn_browse = make_btn(_("Charger un fichier..."), "document-open", _("Charger un fichier XML, CSV, JSON, M3U ou PLS"))
        btn_browse.connect("clicked", self.on_files_browse_clicked)
        ext_bar.pack_start(btn_browse, False, False, 0)

        self.btn_files_reload = make_btn(_("Recharger"), "view-refresh", _("Recharger le fichier actuellement affiché"))
        self.btn_files_reload.set_sensitive(False)
        self.btn_files_reload.connect("clicked", lambda w: self.load_file_into_store(self.current_file_path) if self.current_file_path else None)
        ext_bar.pack_start(self.btn_files_reload, False, False, 0)

        self.chk_preserve_groups = Gtk.CheckButton(label=_("Conserver l'organisation en dossiers"))
        self.chk_preserve_groups.set_active(True)
        self.chk_preserve_groups.set_tooltip_text(_("Préserver les sous-groupes définis dans le fichier au lieu de tout importer dans un groupe unique."))
        self.chk_preserve_groups.connect("toggled", self.on_files_preserve_toggled)
        ext_bar.pack_start(self.chk_preserve_groups, False, False, 0)

        btn_csv = make_btn(_("Exporter en tableau (CSV)..."), "x-office-spreadsheet", _("Générer une liste plate pour tableur Calc ou Excel"))
        btn_csv.connect("clicked", self.on_export_csv_action)
        ext_bar.pack_end(btn_csv, False, False, 0)

        btn_backup = make_btn(_("Sauvegarder mes radios (XML)..."), "document-save", _("Créer une sauvegarde complète de votre collection (avec dossiers et fuseaux horaires)"))
        btn_backup.connect("clicked", self.on_backup_xml_action)
        ext_bar.pack_end(btn_backup, False, False, 0)

        btn_open_bm = make_btn(_("Dossier des signets"), "folder", _("Ouvrir ~/.config/timonde"))
        btn_open_bm.connect("clicked", lambda w: self.open_directory(os.path.expanduser("~/.config/timonde")))
        ext_bar.pack_end(btn_open_bm, False, False, 0)

        # 3. Label d'information sur la source
        self.lbl_files_info = Gtk.Label(label=_("<i>Sélectionnez un fichier ou un exemple ci-dessus.</i>"))
        self.lbl_files_info.set_use_markup(True)
        self.lbl_files_info.set_halign(Gtk.Align.START)
        box.pack_start(self.lbl_files_info, False, False, 0)

        # 4. Tableau des stations (files_store)
        # Store: [checked, name, group_display, country, health_markup, dup_markup, url, is_dup, is_dead, row_id, raw_group]
        self.files_store = Gtk.ListStore(bool, str, str, str, str, str, str, bool, bool, int, str)
        self.files_tree = Gtk.TreeView(model=self.files_store)
        self.files_tree.connect("row-activated", lambda tv, path, col: self.on_tree_row_activated(tv, path, col, "files"))

        renderer_f_check = Gtk.CellRendererToggle()
        renderer_f_check.connect("toggled", self.on_files_check_toggled)
        col_f_check = Gtk.TreeViewColumn(_("Importer"), renderer_f_check, active=0)
        self.files_tree.append_column(col_f_check)

        col_f_name = Gtk.TreeViewColumn(_("Station"), Gtk.CellRendererText(), text=1)
        col_f_name.set_expand(True)
        self.files_tree.append_column(col_f_name)

        col_f_grp = Gtk.TreeViewColumn(_("Dossier / Groupe"), Gtk.CellRendererText(), text=2)
        col_f_grp.set_fixed_width(170)
        self.files_tree.append_column(col_f_grp)

        col_f_country = Gtk.TreeViewColumn(_("Pays"), Gtk.CellRendererText(), text=3)
        col_f_country.set_fixed_width(65)
        self.files_tree.append_column(col_f_country)

        col_f_health = Gtk.TreeViewColumn(_("Disponibilité"), Gtk.CellRendererText(), markup=4)
        col_f_health.set_fixed_width(150)
        self.files_tree.append_column(col_f_health)

        col_f_dup = Gtk.TreeViewColumn(_("Statut Favoris"), Gtk.CellRendererText(), markup=5)
        col_f_dup.set_fixed_width(130)
        self.files_tree.append_column(col_f_dup)

        col_f_url = Gtk.TreeViewColumn(_("URL du flux"), Gtk.CellRendererText(), text=6)
        col_f_url.set_fixed_width(220)
        self.files_tree.append_column(col_f_url)

        scroll_files = Gtk.ScrolledWindow()
        scroll_files.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll_files.set_shadow_type(Gtk.ShadowType.IN)
        scroll_files.add(self.files_tree)
        box.pack_start(scroll_files, True, True, 0)

        # Ligne d'actions sous le tableau
        f_action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.pack_start(f_action_box, False, False, 0)

        btn_f_check_all = make_btn(_("Tout cocher"), "edit-select-all")
        btn_f_check_all.connect("clicked", lambda w: self.set_files_checks(True))
        f_action_box.pack_start(btn_f_check_all, False, False, 0)

        btn_f_uncheck_all = make_btn(_("Tout décocher"), "edit-clear")
        btn_f_uncheck_all.connect("clicked", lambda w: self.set_files_checks(False))
        f_action_box.pack_start(btn_f_uncheck_all, False, False, 0)

        btn_f_new_only = make_btn(_("Nouveaux uniquement"), "list-add")
        btn_f_new_only.connect("clicked", lambda w: self.set_files_checks_new_only())
        f_action_box.pack_start(btn_f_new_only, False, False, 0)

        self.btn_files_test = make_btn(_("Tester les flux"), "network-idle", _("Vérifier en direct la disponibilité des liens"))
        self.btn_files_test.connect("clicked", lambda w: self.test_files_streams())
        f_action_box.pack_start(self.btn_files_test, False, False, 0)

        self.lbl_files_count = Gtk.Label()
        self.lbl_files_count.set_halign(Gtk.Align.END)
        f_action_box.pack_end(self.lbl_files_count, False, False, 0)

        # Barre de groupe et import
        bar_box, self.entry_group_files, self.btn_import_files = self.create_target_group_bar(
            "files", "Import", self.on_import_files
        )
        box.pack_start(bar_box, False, False, 0)

        return box

    # -------------------------------------------------------------------------
    # Mode Autonome (CLI / Standalone)
    # -------------------------------------------------------------------------
    def build_standalone_window(self, initial_tab=0):
        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add(main_vbox)

        hcontent = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        main_vbox.pack_start(hcontent, True, True, 0)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(150)

        sidebar = Gtk.StackSidebar()
        sidebar.set_stack(self.stack)
        sidebar.set_size_request(210, -1)
        hcontent.pack_start(sidebar, False, False, 0)
        hcontent.pack_start(self.stack, True, True, 0)

        self.stack.add_titled(self.view_search, "search", _("Rechercher en ligne"))
        self.stack.add_titled(self.view_bouquets, "bouquets", _("Bouquets par pays"))
        self.stack.add_titled(self.view_files, "files", _("Importer & Exporter"))

        self.stack.connect("notify::visible-child-name", lambda s, p: self.preview_player.stop() if self.preview_player else None)

        bot_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        main_vbox.pack_start(bot_box, False, False, 0)

        btn_close = make_btn(_("Fermer"), "window-close")
        btn_close.connect("clicked", lambda w: self.destroy())
        bot_box.pack_end(btn_close, False, False, 0)

        pages = ["search", "bouquets", "files"]
        target = pages[initial_tab] if 0 <= initial_tab < len(pages) else "search"
        self.stack.set_visible_child_name(target)

    # -------------------------------------------------------------------------
    # Écoute en direct (Preview Player) & Double-clic
    # -------------------------------------------------------------------------
    def on_tree_row_activated(self, treeview, path, column, view_key):
        model = treeview.get_model()
        it = model.get_iter(path)
        if not it:
            return
        if view_key == "search":
            name = model.get_value(it, 1)
            url = model.get_value(it, 6)
        elif view_key == "bouquets":
            name = model.get_value(it, 1)
            url = model.get_value(it, 5)
        elif view_key == "files":
            name = model.get_value(it, 1)
            url = model.get_value(it, 6)
        else:
            name, url = None, None

        if name and url:
            self.toggle_preview_station(name, url)

    def on_preview_clicked(self, view_key):
        if view_key == "search":
            model, it = self.rb_tree.get_selection().get_selected()
            if it:
                self.toggle_preview_station(model.get_value(it, 1), model.get_value(it, 6))
                return
        elif view_key == "bouquets":
            model, it = self.bouquet_tree.get_selection().get_selected()
            if it:
                self.toggle_preview_station(model.get_value(it, 1), model.get_value(it, 5))
                return
        elif view_key == "files":
            model, it = self.files_tree.get_selection().get_selected()
            if it:
                self.toggle_preview_station(model.get_value(it, 1), model.get_value(it, 6))
                return
        self.show_preview_message(_("Sélectionnez une station dans le tableau pour l'écouter."))

    def toggle_preview_station(self, name, url):
        if not url:
            self.show_preview_message(_("Sélectionnez une radio pour l'écouter."))
            return
        clean = clean_stream_url(url)
        if self.preview_player.is_playing and self.preview_player.current_url == clean:
            self.preview_player.stop()
        else:
            self.preview_player.play(name, clean)

    def on_preview_status_update(self, is_playing, url, message, is_error):
        for btn in self.preview_buttons:
            if is_playing:
                update_btn_content(btn, _("Arrêter"), "media-playback-stop")
            else:
                update_btn_content(btn, _("Écouter"), "media-playback-start")

        color = "#d32f2f" if is_error else ("#2e7d32" if is_playing else "#555555")
        markup = f"<small><span color='{color}'><b>{html.escape(message)}</b></span></small>" if message else ""
        for lbl in self.preview_labels:
            lbl.set_markup(markup)

    def show_preview_message(self, message):
        for lbl in self.preview_labels:
            lbl.set_markup(f"<small><span color='#e67e22'>{html.escape(message)}</span></small>")

    # -------------------------------------------------------------------------
    # Gestion des Bouquets DAB+
    # -------------------------------------------------------------------------
    def get_selected_country_code(self):
        if hasattr(self, "combo_country") and self.combo_country:
            active_id = self.combo_country.get_active_id()
            if active_id:
                return active_id
            entry = self.combo_country.get_child()
            if entry:
                text = entry.get_text().strip()
                if text:
                    code = resolve_country_code(text)
                    if code and code in self.bouquets_db:
                        return code
        return "FR" if "FR" in self.bouquets_db else ""

    def on_country_changed(self, widget):
        active_id = self.combo_country.get_active_id()
        if active_id is None:
            entry = self.combo_country.get_child()
            text = entry.get_text().strip() if entry else ""
            norm_text = normalize_lookup(text)
            if not norm_text or norm_text not in COUNTRY_LOOKUP_MAP:
                return
            c_code = COUNTRY_LOOKUP_MAP[norm_text]
            if c_code not in self.bouquets_db:
                return
        else:
            c_code = active_id

        if getattr(self, "_last_resolved_country", None) == c_code and active_id is None:
            return
        self._last_resolved_country = c_code

        self.update_languages()
        self.update_regions_combo()
        self.load_current_bouquet()

        c_name = self.bouquets_db.get(c_code, {}).get("country_name", c_code or "Radio")
        if hasattr(self, "entry_group_search"):
            self.entry_group_search.set_text(f"Radio-Browser - {c_name}")
        if hasattr(self, "entry_rb_country") and hasattr(self, "check_rb_only_country"):
            c_info = self.bouquets_db.get(c_code, {})
            if c_info:
                self.entry_rb_country.set_text(c_info.get("name", c_code))

    def update_languages(self):
        country_id = self.get_selected_country_code()
        info = self.bouquets_db.get(country_id, {})
        is_multi = info.get("multilingual", False)

        self.lbl_lang.set_visible(is_multi)
        self.combo_lang.set_visible(is_multi)
        self.combo_lang.remove_all()

        if is_multi:
            for l_code, l_label in info.get("languages", []):
                self.combo_lang.append(l_code, l_label)
            if info.get("languages"):
                self.combo_lang.set_active(0)

    def update_regions_combo(self):
        country_id, info, national, regions = self.get_current_data()
        prev_region = self.combo_region.get_active_text()

        try:
            self.combo_region.disconnect_by_func(self.on_region_changed)
        except Exception:
            pass

        self.combo_region.remove_all()
        for reg_name in regions.keys():
            self.combo_region.append_text(reg_name)

        if regions:
            self.radio_region.set_sensitive(True)
            target_idx = 0
            if prev_region:
                for idx, r in enumerate(regions.keys()):
                    if r == prev_region:
                        target_idx = idx
                        break
            self.combo_region.set_active(target_idx)
        else:
            self.radio_region.set_sensitive(False)
            if self.radio_region.get_active():
                self.radio_national.set_active(True)

        self.combo_region.connect("changed", self.on_region_changed)
        is_region = self.radio_region.get_active()
        self.combo_region.set_sensitive(is_region and bool(regions))

    def on_lang_changed(self, widget):
        self.update_regions_combo()
        self.load_current_bouquet()

    def on_scope_changed(self, widget):
        if widget.get_active():
            country_id, info, national, regions = self.get_current_data()
            is_region = self.radio_region.get_active()
            self.combo_region.set_sensitive(is_region and bool(regions))
            self.load_current_bouquet()

    def on_region_changed(self, widget):
        if self.radio_region.get_active():
            self.load_current_bouquet()

    def get_current_data(self):
        country_id = self.get_selected_country_code()
        info = self.bouquets_db.get(country_id, {})

        if info.get("multilingual", False):
            lang_id = self.combo_lang.get_active_id() or (info["languages"][0][0] if info.get("languages") else "GEN")
            sub = info.get("sub_bouquets", {}).get(lang_id, {})
            national = sub.get("national", [])
            regions = sub.get("regions", {})
        else:
            national = info.get("national", [])
            regions = info.get("regions", {})

        return country_id, info, national, regions

    def load_current_bouquet(self):
        country_id, info, national, regions = self.get_current_data()
        is_region = self.radio_region.get_active()
        self.combo_region.set_sensitive(is_region and bool(regions))

        stations = []
        country_name = info.get("country_name") or info.get("name", "Pays").split("  [")[0]
        if is_region and regions:
            reg_name = self.combo_region.get_active_text() or (list(regions.keys())[0] if regions else "")
            stations = regions.get(reg_name, [])
            default_group = f"Radios {reg_name}"
        else:
            stations = national
            if info.get("multilingual", False):
                lang_text = self.combo_lang.get_active_text() or ""
                lang_short = lang_text.split()[0] if lang_text else ""
                default_group = f"Radios Nationales ({country_name} - {lang_short})"
            else:
                default_group = f"Radios Nationales ({country_name})"

        if hasattr(self, "entry_group_bouquets"):
            self.entry_group_bouquets.set_text(default_group)

        self.bouquet_store.clear()
        self.current_check_generation += 1
        gen = self.current_check_generation

        items_to_check = []
        for i, (name, url, genre) in enumerate(stations):
            clean_url = url.strip()
            clean_name = name.strip().lower()

            is_dup = (clean_url in self.existing_urls) or (clean_name in self.existing_names)
            checked = False
            status_note = "<span color='#888888'><i>(Déjà dans vos favoris)</i></span>" if is_dup else "<span color='#2e7d32'><b>Nouveau</b></span>"
            health_note = "<span color='#888888'>Vérification...</span>"

            self.bouquet_store.append([checked, name, genre, health_note, status_note, clean_url, is_dup, False, i])
            items_to_check.append((i, clean_url))

        self.update_bouquet_count()

        def check_worker(item_id, target_url, target_gen):
            is_ok, msg = check_stream_url(target_url)

            def update_ui():
                if target_gen != self.current_check_generation:
                    return
                it = self.bouquet_store.get_iter_first()
                while it:
                    if self.bouquet_store.get_value(it, 8) == item_id:
                        if is_ok == "GEOBLOCKED":
                            markup = f"<span color='#f57c00'><b>● {msg}</b></span>"
                            self.bouquet_store.set_value(it, 3, markup)
                            self.bouquet_store.set_value(it, 7, False)
                        elif is_ok:
                            markup = f"<span color='#2e7d32'><b>●</b> {msg}</span>"
                            self.bouquet_store.set_value(it, 3, markup)
                            self.bouquet_store.set_value(it, 7, False)
                        else:
                            markup = f"<span color='#d32f2f'><b>● {msg}</b></span>"
                            self.bouquet_store.set_value(it, 3, markup)
                            self.bouquet_store.set_value(it, 7, True)
                            self.bouquet_store.set_value(it, 0, False)
                        break
                    it = self.bouquet_store.iter_next(it)
                self.update_bouquet_count()

            GLib.idle_add(update_ui)

        for item_id, url in items_to_check:
            self.executor.submit(check_worker, item_id, url, gen)

    def test_bouquet_streams(self):
        items_to_check = []
        it = self.bouquet_store.get_iter_first()
        while it:
            row_id = self.bouquet_store.get_value(it, 8)
            url = self.bouquet_store.get_value(it, 5)
            self.bouquet_store.set_value(it, 3, "<span foreground='#888888'>Test...</span>")
            items_to_check.append((row_id, url))
            it = self.bouquet_store.iter_next(it)

        self.current_check_generation += 1
        gen = self.current_check_generation

        def check_worker(item_id, target_url, target_gen):
            is_ok, msg = check_stream_url(target_url)

            def update_ui():
                if target_gen != self.current_check_generation:
                    return
                it_find = self.bouquet_store.get_iter_first()
                while it_find:
                    if self.bouquet_store.get_value(it_find, 8) == item_id:
                        if is_ok == "GEOBLOCKED":
                            markup = f"<span color='#f57c00'><b>● {msg}</b></span>"
                            self.bouquet_store.set_value(it_find, 3, markup)
                            self.bouquet_store.set_value(it_find, 7, False)
                        elif is_ok:
                            markup = f"<span color='#2e7d32'><b>●</b> {msg}</span>"
                            self.bouquet_store.set_value(it_find, 3, markup)
                            self.bouquet_store.set_value(it_find, 7, False)
                        else:
                            markup = f"<span color='#d32f2f'><b>● {msg}</b></span>"
                            self.bouquet_store.set_value(it_find, 3, markup)
                            self.bouquet_store.set_value(it_find, 7, True)
                            self.bouquet_store.set_value(it_find, 0, False)
                        break
                    it_find = self.bouquet_store.iter_next(it_find)
                self.update_bouquet_count()

            GLib.idle_add(update_ui)

        for item_id, url in items_to_check:
            self.executor.submit(check_worker, item_id, url, gen)

    def on_bouquet_check_toggled(self, widget, path):
        it = self.bouquet_store.get_iter(path)
        cur = self.bouquet_store.get_value(it, 0)
        self.bouquet_store.set_value(it, 0, not cur)
        self.update_bouquet_count()

    def set_bouquet_checks(self, val):
        it = self.bouquet_store.get_iter_first()
        while it:
            is_dup = self.bouquet_store.get_value(it, 6)
            is_dead = self.bouquet_store.get_value(it, 7)
            if val and (is_dup or is_dead):
                self.bouquet_store.set_value(it, 0, False)
            else:
                self.bouquet_store.set_value(it, 0, val)
            it = self.bouquet_store.iter_next(it)
        self.update_bouquet_count()

    def update_bouquet_count(self):
        total = 0
        checked = 0
        it = self.bouquet_store.get_iter_first()
        while it:
            total += 1
            if self.bouquet_store.get_value(it, 0):
                checked += 1
            it = self.bouquet_store.iter_next(it)

        if total == 0:
            c_code = self.get_selected_country_code()
            c_name = self.bouquets_db.get(c_code, {}).get("country_name", c_code or "ce pays")
            self.lbl_bouquet_count.set_markup(f"<span color='#888888'><i>Aucun bouquet DAB+ pour {html.escape(c_name)} — Utilisez « Rechercher en ligne ».</i></span>")
            self.btn_bouquet_check_all.set_sensitive(False)
            self.btn_bouquet_uncheck_all.set_sensitive(False)
            self.btn_repair.set_sensitive(False)
        else:
            self.lbl_bouquet_count.set_text(f"{checked} / {total} station(s) sélectionnée(s)")
            self.btn_bouquet_check_all.set_sensitive(True)
            self.btn_bouquet_uncheck_all.set_sensitive(True)
            self.btn_repair.set_sensitive(True)

        if hasattr(self, "btn_import_bouquets"):
            self.btn_import_bouquets.set_sensitive(checked > 0)

    def on_repair_clicked(self, widget):
        model, tree_iter = self.bouquet_tree.get_selection().get_selected()
        if not tree_iter:
            return

        station_name = model.get_value(tree_iter, 1)
        current_url = model.get_value(tree_iter, 5)
        country_id = self.get_selected_country_code()

        dlg = RepairStreamDialog(self, station_name, current_url, country_id)
        res = dlg.run()
        new_url = dlg.get_chosen_url()
        dlg.destroy()

        if res == Gtk.ResponseType.OK and new_url:
            clean_new_url = new_url.strip()
            model.set_value(tree_iter, 5, clean_new_url)
            model.set_value(tree_iter, 3, "<span color='#2e7d32'><b>● Réparé (En ligne)</b></span>")
            model.set_value(tree_iter, 7, False)
            model.set_value(tree_iter, 0, True)
            self.update_bouquet_count()
            self.save_stream_to_xml(station_name, current_url, clean_new_url)

    def save_stream_to_xml(self, station_name, old_url, new_url):
        country_id, info, _nat, _regs = self.get_current_data()
        xml_path = info.get("xml_path")
        if not xml_path or not os.path.exists(xml_path):
            return

        target_file = xml_path
        if not os.access(xml_path, os.W_OK):
            user_b_dir = os.path.expanduser("~/.local/share/timonde/bouquets")
            os.makedirs(user_b_dir, exist_ok=True)
            target_file = os.path.join(user_b_dir, os.path.basename(xml_path))
            if not os.path.exists(target_file):
                import shutil
                shutil.copyfile(xml_path, target_file)

        try:
            tree = ET.parse(target_file)
            root = tree.getroot()
            modified = False
            for st in root.iter("station"):
                if st.attrib.get("name", "").strip().lower() == station_name.strip().lower() or st.attrib.get("url") == old_url:
                    st.attrib["url"] = new_url
                    modified = True

            if modified:
                tree.write(target_file, encoding="utf-8", xml_declaration=True)
                sys.stderr.write(f"Flux réparé enregistré dans : {target_file}\n")
        except Exception as e:
            sys.stderr.write(f"Erreur écriture XML : {e}\n")

    # -------------------------------------------------------------------------
    # Recherche Radio-Browser Mondiale
    # -------------------------------------------------------------------------
    def on_search_rb_clicked(self):
        query = self.entry_rb_name.get_text().strip()
        tag = self.entry_rb_tag.get_text().strip()
        raw_lang = self.entry_rb_lang.get_text().strip() if hasattr(self, "entry_rb_lang") else ""
        lang = resolve_language_api_key(raw_lang) if raw_lang else ""
        country_code = ""
        if self.check_rb_only_country.get_active():
            raw_c = self.entry_rb_country.get_text().strip() if hasattr(self, "entry_rb_country") else ""
            if raw_c:
                country_code = resolve_country_code(raw_c) or raw_c.upper()
            else:
                country_code = self.get_selected_country_code()

        self.lbl_rb_status.set_text(_("Recherche sur Radio-Browser en cours..."))
        self.rb_store.clear()

        def worker():
            results = search_radio_browser_api(name=query, country_code=country_code, tag=tag, language=lang, limit=40)

            def on_done():
                if not results:
                    if country_code and lang:
                        c_name = self.bouquets_db.get(country_code, {}).get("country_name", country_code)
                        self.lbl_rb_status.set_text(f"Aucune radio trouvée pour cette langue en {c_name}. Décochez « Filtrer par pays » ou effacez la langue.")
                    elif country_code:
                        c_name = self.bouquets_db.get(country_code, {}).get("country_name", country_code)
                        self.lbl_rb_status.set_text(f"Aucune radio trouvée pour ces critères en {c_name}. Décochez « Filtrer par pays » pour chercher mondialement.")
                    else:
                        self.lbl_rb_status.set_text(_("Aucune radio trouvée sur Radio-Browser pour ces critères."))
                    return
                for i, r in enumerate(results):
                    name = r.get("name", "Sans nom").strip()
                    c_code = r.get("countrycode", "").upper()
                    tags = r.get("tags", "")
                    codec = r.get("codec", "MP3")
                    bitrate = f"{r.get('bitrate', 128)}k" if r.get("bitrate") else ""
                    codec_str = f"{codec} {bitrate}".strip()
                    votes = r.get("votes", 0)
                    url = (r.get("url_resolved") or r.get("url", "")).strip()

                    is_dup = (url in self.existing_urls) or (name.lower() in self.existing_names)
                    dup_markup = '<span foreground="#e67e22">[Présent]</span>' if is_dup else '<span foreground="#27ae60">[Nouveau]</span>'
                    health_markup = '<span foreground="#95a5a6">○ Non testé</span>'
                    self.rb_store.append([False, name, c_code, tags[:30], codec_str, votes, url, is_dup, health_markup, dup_markup, i])

                self.lbl_rb_status.set_text(f"{len(results)} stations trouvées.")
                self.update_rb_count()

            GLib.idle_add(on_done)

        self.executor.submit(worker)

    def test_rb_streams(self):
        items_to_check = []
        it = self.rb_store.get_iter_first()
        while it:
            row_id = self.rb_store.get_value(it, 10)
            url = self.rb_store.get_value(it, 6)
            self.rb_store.set_value(it, 8, "<span foreground='#888888'>Test...</span>")
            items_to_check.append((row_id, url))
            it = self.rb_store.iter_next(it)

        self.current_rb_check_generation += 1
        gen = self.current_rb_check_generation

        def check_worker(item_id, target_url, target_gen):
            is_ok, msg = check_stream_url(target_url)

            def update_ui():
                if target_gen != self.current_rb_check_generation:
                    return
                it_find = self.rb_store.get_iter_first()
                while it_find:
                    if self.rb_store.get_value(it_find, 10) == item_id:
                        if is_ok == "GEOBLOCKED":
                            markup = f"<span foreground='#f57c00'><b>● {msg}</b></span>"
                        elif is_ok:
                            markup = f"<span foreground='#2ecc71'><b>●</b> {msg}</span>"
                        else:
                            markup = f"<span foreground='#e74c3c'><b>● {msg}</b></span>"
                            self.rb_store.set_value(it_find, 0, False)
                        self.rb_store.set_value(it_find, 8, markup)
                        break
                    it_find = self.rb_store.iter_next(it_find)
                self.update_rb_count()

            GLib.idle_add(update_ui)

        for item_id, url in items_to_check:
            self.executor.submit(check_worker, item_id, url, gen)

    def on_rb_check_toggled(self, widget, path):
        it = self.rb_store.get_iter(path)
        if it:
            cur = self.rb_store.get_value(it, 0)
            self.rb_store.set_value(it, 0, not cur)
            self.update_rb_count()

    def set_rb_checks(self, val):
        it = self.rb_store.get_iter_first()
        while it:
            self.rb_store.set_value(it, 0, val)
            it = self.rb_store.iter_next(it)
        self.update_rb_count()

    def update_rb_count(self):
        checked = 0
        total = 0
        it = self.rb_store.get_iter_first()
        while it:
            total += 1
            if self.rb_store.get_value(it, 0):
                checked += 1
            it = self.rb_store.iter_next(it)
        if hasattr(self, "btn_import_search"):
            self.btn_import_search.set_sensitive(checked > 0)

    # -------------------------------------------------------------------------
    # Gestion des Fichiers & Exemples
    # -------------------------------------------------------------------------
    def on_files_browse_clicked(self, widget):
        chooser = Gtk.FileChooserDialog(
            title=_("Choisir un fichier de radios"),
            transient_for=self if not self.embedded else None,
            action=Gtk.FileChooserAction.OPEN,
        )
        chooser.add_button(_("Annuler"), Gtk.ResponseType.CANCEL)
        chooser.add_button(_("Ouvrir"), Gtk.ResponseType.OK)

        filter_all = Gtk.FileFilter()
        filter_all.set_name("Tous fichiers supportés (*.xml, *.csv, *.json, *.m3u, *.pls)")
        filter_all.add_pattern("*.xml")
        filter_all.add_pattern("*.csv")
        filter_all.add_pattern("*.json")
        filter_all.add_pattern("*.m3u")
        filter_all.add_pattern("*.m3u8")
        filter_all.add_pattern("*.pls")
        chooser.add_filter(filter_all)

        res = chooser.run()
        filename = chooser.get_filename()
        chooser.destroy()

        if res == Gtk.ResponseType.OK and filename:
            self.load_file_into_store(filename)

    def on_files_example_changed(self, widget):
        path = self.combo_examples.get_active_id()
        if path:
            self.load_file_into_store(path)

    def on_refresh_examples_clicked(self, widget):
        self.combo_examples.remove_all()
        self.available_examples = list_available_examples()
        for fpath, label, title in self.available_examples:
            self.combo_examples.append(fpath, label)
        if self.available_examples:
            self.combo_examples.set_active(0)

    def on_files_preserve_toggled(self, widget):
        if self.chk_preserve_groups.get_active():
            self.entry_group_files.set_text("(Groupes préservés du fichier)")
        else:
            base_name = os.path.splitext(os.path.basename(self.current_file_path or ""))[0] or "Import"
            self.entry_group_files.set_text(f"Import {base_name}")

    def load_file_into_store(self, path):
        if not path or not os.path.isfile(path):
            return

        self.current_file_path = path
        self.btn_files_reload.set_sensitive(True)
        base_name = os.path.splitext(os.path.basename(path))[0]

        stations = parse_user_radio_file(path)
        self.current_file_stations = stations
        groups = set(s.get("group", "") for s in stations if s.get("group"))

        info_text = f"<b>{_('Fichier :')}</b> {os.path.basename(path)} — <b>{len(stations)}</b> station(s)"
        if groups:
            info_text += f", <b>{len(groups)}</b> groupe(s)"
        self.lbl_files_info.set_markup(info_text)

        if hasattr(self, "entry_group_files"):
            if self.chk_preserve_groups.get_active() and len(groups) > 1:
                self.entry_group_files.set_text("(Groupes préservés du fichier)")
            else:
                first_grp = next(iter(groups)) if groups else base_name
                self.entry_group_files.set_text(first_grp or f"Import {base_name}")

        self.files_store.clear()
        self.current_files_check_generation += 1

        for i, st in enumerate(stations):
            name = st.get("name", "Station")
            url = st.get("url", "").strip()
            grp = st.get("group", "").strip() or base_name
            country = st.get("country", "").strip().upper()

            is_dup = (url in self.existing_urls) or (name.strip().lower() in self.existing_names)
            checked = False
            dup_markup = '<span foreground="#e67e22">[Présent]</span>' if is_dup else '<span foreground="#27ae60">[Nouveau]</span>'
            health_markup = '<span foreground="#95a5a6">○ Non testé</span>'

            # Store: [checked, name, group_display, country, health_markup, dup_markup, url, is_dup, is_dead, row_id, raw_group]
            self.files_store.append([checked, name, grp, country, health_markup, dup_markup, url, is_dup, False, i, grp])

        self.update_files_count()

    def on_files_check_toggled(self, widget, path):
        it = self.files_store.get_iter(path)
        if it:
            val = self.files_store.get_value(it, 0)
            self.files_store.set_value(it, 0, not val)
            self.update_files_count()

    def set_files_checks(self, val):
        it = self.files_store.get_iter_first()
        while it:
            self.files_store.set_value(it, 0, val)
            it = self.files_store.iter_next(it)
        self.update_files_count()

    def set_files_checks_new_only(self):
        it = self.files_store.get_iter_first()
        while it:
            is_dup = self.files_store.get_value(it, 7)
            is_dead = self.files_store.get_value(it, 8)
            self.files_store.set_value(it, 0, (not is_dup) and (not is_dead))
            it = self.files_store.iter_next(it)
        self.update_files_count()

    def test_files_streams(self):
        items_to_check = []
        it = self.files_store.get_iter_first()
        while it:
            row_id = self.files_store.get_value(it, 9)
            url = self.files_store.get_value(it, 6)
            self.files_store.set_value(it, 4, "<span foreground='#888888'>Test...</span>")
            items_to_check.append((row_id, url))
            it = self.files_store.iter_next(it)

        self.current_files_check_generation += 1
        gen = self.current_files_check_generation

        def check_worker(item_id, target_url, target_gen):
            is_ok, msg = check_stream_url(target_url)

            def update_ui():
                if target_gen != self.current_files_check_generation:
                    return
                it_find = self.files_store.get_iter_first()
                while it_find:
                    if self.files_store.get_value(it_find, 9) == item_id:
                        if is_ok == "GEOBLOCKED":
                            markup = f"<span foreground='#f57c00'><b>● {msg}</b></span>"
                            self.files_store.set_value(it_find, 4, markup)
                            self.files_store.set_value(it_find, 8, False)
                        elif is_ok:
                            markup = f"<span foreground='#2ecc71'><b>●</b> {msg}</span>"
                            self.files_store.set_value(it_find, 4, markup)
                            self.files_store.set_value(it_find, 8, False)
                        else:
                            markup = f"<span foreground='#e74c3c'><b>● {msg}</b></span>"
                            self.files_store.set_value(it_find, 4, markup)
                            self.files_store.set_value(it_find, 8, True)
                            self.files_store.set_value(it_find, 0, False)
                        break
                    it_find = self.files_store.iter_next(it_find)
                self.update_files_count()

            GLib.idle_add(update_ui)

        for item_id, url in items_to_check:
            self.executor.submit(check_worker, item_id, url, gen)

    def update_files_count(self):
        checked = 0
        total = 0
        it = self.files_store.get_iter_first()
        while it:
            total += 1
            if self.files_store.get_value(it, 0):
                checked += 1
            it = self.files_store.iter_next(it)
        self.lbl_files_count.set_text(f"{checked} / {total} station(s) sélectionnée(s)")
        if hasattr(self, "btn_import_files"):
            self.btn_import_files.set_sensitive(checked > 0)

    # -------------------------------------------------------------------------
    # Actions & Importation finale
    # -------------------------------------------------------------------------
    def on_import_search(self):
        raw_grp = self.entry_group_search.get_text().strip()
        group_name = normalize_group_path(raw_grp, return_root_literal=True)
        country_id = self.get_selected_country_code()

        selected = []
        it = self.rb_store.get_iter_first()
        while it:
            if self.rb_store.get_value(it, 0):
                name = self.rb_store.get_value(it, 1)
                rb_country = (self.rb_store.get_value(it, 2) or "").strip() or country_id
                url = self.rb_store.get_value(it, 6)
                tz = infer_timezone(rb_country, name, group_name)
                st_data = {"name": name, "url": url, "country": rb_country}
                if tz:
                    st_data["timezone"] = tz
                selected.append(st_data)
            it = self.rb_store.iter_next(it)

        self.finalize_import(selected, group_name, country_id)

    def on_import_bouquets(self):
        raw_grp = self.entry_group_bouquets.get_text().strip()
        group_name = normalize_group_path(raw_grp, return_root_literal=True)
        country_id = self.get_selected_country_code()

        selected = []
        it = self.bouquet_store.get_iter_first()
        while it:
            if self.bouquet_store.get_value(it, 0):
                name = self.bouquet_store.get_value(it, 1)
                url = self.bouquet_store.get_value(it, 5)
                tz = infer_timezone(country_id, name, group_name)
                st_data = {"name": name, "url": url, "country": country_id}
                if tz:
                    st_data["timezone"] = tz
                selected.append(st_data)
            it = self.bouquet_store.iter_next(it)

        self.finalize_import(selected, group_name, country_id)

    def on_import_files(self):
        raw_grp = self.entry_group_files.get_text().strip()
        group_name = normalize_group_path(raw_grp, return_root_literal=True)
        preserve = self.chk_preserve_groups.get_active()

        selected = []
        it = self.files_store.get_iter_first()
        while it:
            if self.files_store.get_value(it, 0):
                name = self.files_store.get_value(it, 1)
                url = self.files_store.get_value(it, 6)
                st_group_raw = self.files_store.get_value(it, 10)
                st_country = self.files_store.get_value(it, 3) or ""
                raw_target = st_group_raw if (preserve and st_group_raw) else group_name
                if raw_target:
                    clean_t = raw_target.strip()
                    if clean_t in ("[ / ] (Racine — Sans groupe)", "/", "root", "(Racine)"):
                        target_st_grp = "root"
                    else:
                        target_st_grp = clean_t.strip("/").strip()
                else:
                    target_st_grp = "root"

                row_id = self.files_store.get_value(it, 9)
                orig_tz = ""
                if hasattr(self, "current_file_stations") and 0 <= row_id < len(self.current_file_stations):
                    orig_tz = self.current_file_stations[row_id].get("timezone", "")
                tz = orig_tz or infer_timezone(st_country, name, target_st_grp)
                st_data = {
                    "name": name,
                    "url": url,
                    "country": st_country,
                    "group": target_st_grp
                }
                if tz:
                    st_data["timezone"] = tz
                selected.append(st_data)
            it = self.files_store.iter_next(it)

        self.finalize_import(selected, group_name, None)

    def finalize_import(self, stations, group_name, country_code=None):
        if hasattr(self, "preview_player") and self.preview_player:
            self.preview_player.stop()

        if not stations:
            return

        self.chosen_group_name = group_name
        self.selected_stations = stations
        self.saved = True

        result = {
            "group_name": group_name,
            "country_code": country_code,
            "stations": stations,
        }

        if self.on_import_callback:
            self.on_import_callback(result)

        if not self.embedded:
            print(json.dumps(result, ensure_ascii=False), flush=True)
            self.destroy()

    def on_show_group_naming_help(self, widget):
        dialog = Gtk.MessageDialog(
            transient_for=self if not self.embedded else None,
            flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
            type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            message_format=_("Organisation des groupes et sous-groupes (Convention Linux)")
        )
        dialog.format_secondary_markup(
            "TiMonde utilise la convention des chemins avec le séparateur <b>/</b> :\n\n"
            "• <b>/</b> ou <b>(Racine)</b> : Place les radios à la racine du menu (sans groupe).\n"
            "• <b>/Gabon</b> ou <b>Gabon</b> : Place les radios dans le groupe « Gabon ».\n"
            "• <b>/France/Bretagne</b> : Place les radios dans le sous-groupe « Bretagne » sous « France ».\n"
            "• <b>/Belgique/NL</b> : Place les radios dans le sous-groupe « NL » sous « Belgique ».\n"
            "• <b>France/Radios locales ICI</b> : Sous-groupe à espaces sous « France ».\n\n"
            "<i>Les groupes et sous-groupes sont créés automatiquement s'ils n'existent pas encore.</i>"
        )
        dialog.run()
        dialog.destroy()

    def open_directory(self, path):
        try:
            os.makedirs(path, exist_ok=True)
            from gi.repository import Gio
            f = Gio.File.new_for_path(path)
            Gio.AppInfo.launch_default_for_uri(f.get_uri(), None)
        except Exception as e:
            sys.stderr.write(f"Impossible d'ouvrir le dossier {path}: {e}\n")

    def on_open_examples_folder(self, widget):
        user_dir = ensure_user_examples_dir()
        self.open_directory(user_dir)

    def on_restore_examples_action(self, widget):
        source_dirs = [
            "/usr/share/timonde/examples",
            os.path.join(os.path.dirname(__file__), "..", "examples"),
            os.path.join(os.path.dirname(__file__), "../../data/examples"),
            "data/examples"
        ]
        restored = 0
        os.makedirs(USER_CONFIG_EXAMPLES_DIR, exist_ok=True)
        for sdir in source_dirs:
            if os.path.isdir(sdir):
                for fname in os.listdir(sdir):
                    src_file = os.path.join(sdir, fname)
                    dst_file = os.path.join(USER_CONFIG_EXAMPLES_DIR, fname)
                    if os.path.isfile(src_file):
                        shutil.copy2(src_file, dst_file)
                        restored += 1
                if restored > 0:
                    break
        self.on_refresh_examples_clicked(None)
        self.show_preview_message(f"{restored} {_('fichiers exemples restaurés.')}")

    def on_export_csv_action(self, widget):
        if self.on_export_csv_callback:
            self.on_export_csv_callback()
        else:
            self.show_preview_message(_("L'exportation CSV est accessible depuis les paramètres."))

    def on_backup_xml_action(self, widget):
        if self.on_backup_xml_callback:
            self.on_backup_xml_callback()
        else:
            self.show_preview_message(_("La sauvegarde XML est accessible depuis les paramètres."))

    def on_destroy(self, widget):
        if hasattr(self, "preview_player") and self.preview_player:
            self.preview_player.stop()
        try:
            self.executor.shutdown(wait=False)
        except Exception:
            pass
        if not getattr(self, "embedded", False):
            Gtk.main_quit()



def parse_bouquets_xml():
    b_dir = find_bouquets_dir()
    db = {}

    if b_dir:
        for xml_file in sorted(glob.glob(os.path.join(b_dir, "*.xml"))):
            try:
                root = safe_parse_xml(xml_file)
                if root is None:
                    continue
                code = root.attrib.get("country", os.path.splitext(os.path.basename(xml_file))[0].upper()).upper()
                if code == "UK":
                    code = "GB"
                raw_name = strip_unsupported_emojis(root.attrib.get("name", code))
                name = raw_name if (raw_name and raw_name != code) else COUNTRY_BY_CODE.get(code, code)
                display_name = f"{name}  [{code}]" if code else name
                multilingual = root.attrib.get("multilingual", "false").lower() == "true"

                country_data = {
                    "name": display_name,
                    "country_name": name,
                    "code": code,
                    "has_bouquet": True,
                    "multilingual": multilingual,
                    "languages": [],
                    "sub_bouquets": {},
                    "national": [],
                    "regions": {},
                    "xml_path": xml_file,
                }

                if multilingual:
                    for comm in root.findall("community"):
                        c_id = comm.attrib.get("id", "GEN")
                        c_name = comm.attrib.get("name", c_id)
                        country_data["languages"].append((c_id, c_name))
                        sub_data = {"national": [], "regions": {}}

                        nat = comm.find("national")
                        if nat is not None:
                            for st in nat.findall("station"):
                                sub_data["national"].append((st.attrib.get("name", ""), st.attrib.get("url", ""), st.attrib.get("genre", "")))

                        regs = comm.find("regions")
                        if regs is not None:
                            for reg in regs.findall("region"):
                                r_name = reg.attrib.get("name", "Région")
                                st_list = []
                                for st in reg.findall("station"):
                                    st_list.append((st.attrib.get("name", ""), st.attrib.get("url", ""), st.attrib.get("genre", "")))
                                sub_data["regions"][r_name] = st_list

                        country_data["sub_bouquets"][c_id] = sub_data
                else:
                    nat = root.find("national")
                    if nat is not None:
                        for st in nat.findall("station"):
                            country_data["national"].append((st.attrib.get("name", ""), st.attrib.get("url", ""), st.attrib.get("genre", "")))

                    regs = root.find("regions")
                    if regs is not None:
                        for reg in regs.findall("region"):
                            r_name = reg.attrib.get("name", "Région")
                            st_list = []
                            for st in reg.findall("station"):
                                st_list.append((st.attrib.get("name", ""), st.attrib.get("url", ""), st.attrib.get("genre", "")))
                            country_data["regions"][r_name] = st_list

                db[code] = country_data
            except Exception:
                pass

    for iso_code, fr_name, _en_name in WORLD_COUNTRIES:
        if iso_code not in db:
            db[iso_code] = {
                "name": f"{fr_name}  [{iso_code}]",
                "country_name": fr_name,
                "code": iso_code,
                "has_bouquet": False,
                "multilingual": False,
                "languages": [],
                "sub_bouquets": {},
                "national": [],
                "regions": {},
                "xml_path": None,
            }

    return db


def main():
    existing_stations = []
    initial_tab = 0
    initial_file = None

    for arg in sys.argv[1:]:
        if arg.startswith("--tab="):
            tab_val = arg.split("=", 1)[1].strip()
            if tab_val.isdigit():
                initial_tab = int(tab_val)
            elif tab_val in ("import", "user", "file", "mes_fichiers", "files"):
                initial_tab = 2
            elif tab_val in ("examples", "exemples"):
                initial_tab = 2
            elif tab_val in ("dab", "bouquets"):
                initial_tab = 1
            elif tab_val in ("rb", "search", "radio-browser"):
                initial_tab = 0
        elif arg.startswith("--file="):
            initial_file = arg.split("=", 1)[1].strip()
        elif os.path.isfile(arg) and not arg.endswith(".py"):
            if arg.endswith(".json"):
                try:
                    with open(arg, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, list): existing_stations = data
                except Exception:
                    initial_file = arg
            else:
                initial_file = arg

    available_groups = []

    if not existing_stations and not sys.stdin.isatty():
        try:
            raw = sys.stdin.read().strip()
            if raw:
                data = json.loads(raw)
                if isinstance(data, list):
                    existing_stations = data
                elif isinstance(data, dict):
                    existing_stations = data.get("stations", [])
                    available_groups = data.get("groups", [])
        except Exception: pass

    if not available_groups:
        available_groups = get_user_bookmarks_groups()

    bouquets_db = parse_bouquets_xml()
    if not bouquets_db:
        sys.stderr.write("Aucun bouquet disponible.\n")
        sys.exit(1)

    try:
        settings = Gtk.Settings.get_default()
        if settings:
            settings.set_property("gtk-entry-select-on-focus", False)
    except Exception:
        pass

    pages = ["search", "bouquets", "files"]
    target_page = "search"
    if 0 <= initial_tab < len(pages):
        target_page = pages[initial_tab]
    elif initial_tab == 3:
        target_page = "files"

    win = DiscoverRadiosWindow(
        existing_stations,
        bouquets_db,
        initial_tab=initial_tab,
        initial_file=initial_file,
        available_groups=available_groups,
    )
    win.show_all()
    win.present()
    if hasattr(win, "stack"):
        win.stack.set_visible_child_name(target_page)
    if target_page == "search" and hasattr(win, "entry_rb_name"):
        GLib.idle_add(win.entry_rb_name.grab_focus)
    Gtk.main()

    if win.saved:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
