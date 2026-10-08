#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TiMonde — Interface Unifiée de Découverte & Importation de Radios
Unified Radio Discovery & Import Interface for TiMonde.

Fonctionnalités / Features:
1. Sélecteur universel de pays (Code ISO 3166-1 alpha-2, noms traduits et drapeaux).
   Universal country picker (ISO 3166-1 alpha-2 code, translated names and flags).
2. Onglet 1 : Bouquets officiels (DAB+ & sélections vérifiées) avec test frugal en direct (🟢/🔴).
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

# Module d internationalisation TiMonde
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from timonde_i18n import _
except ImportError:
    def _(s): return s

import json
import glob
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import re
import csv
from concurrent.futures import ThreadPoolExecutor

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, Pango

# -----------------------------------------------------------------------------
# Configuration & Constantes / Configuration & Constants
# -----------------------------------------------------------------------------

RADIO_BROWSER_ENDPOINTS = [
    "https://de1.api.radio-browser.info",
    "https://nl1.api.radio-browser.info",
    "https://at1.api.radio-browser.info",
]

USER_AGENT = "TiMonde/0.1.0 (Linux; x86_64; VLC/3.0.20)"

# Répertoires de recherche des bouquets XML / Bouquets search paths
BOUQUETS_CANDIDATES = [
    os.path.join(os.path.dirname(__file__), "..", "bouquets"),
    os.path.expanduser("~/.local/share/timonde/bouquets"),
    "/usr/share/timonde/bouquets",
    "/usr/local/share/timonde/bouquets",
    "data/bouquets",
]

def safe_parse_xml(path):
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

EXAMPLES_CANDIDATES = [
    os.path.expanduser("~/.local/share/timonde/examples"),
    os.path.join(os.path.dirname(__file__), "..", "examples"),
    "/usr/share/timonde/examples",
    "data/examples",
]

def find_examples_dir():
    """Localise le dossier des exemples XML / Locate examples directory"""
    for path in EXAMPLES_CANDIDATES:
        if os.path.isdir(path) and glob.glob(os.path.join(path, "*.xml")):
            return os.path.abspath(path)
    return None

def list_available_examples():
    """Liste tous les fichiers exemples disponibles (XML, CSV, JSON, M3U) depuis tous les répertoires candidats"""
    patterns = ["*.xml", "*.csv", "*.json", "*.m3u", "*.m3u8", "*.pls"]
    found_files = {}
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
                name = root.attrib.get("name", base)
                flag = root.attrib.get("flag", "📂")
                results.append((f, f"{flag} {name} ({base})", name))
            except Exception:
                results.append((f, f"📂 {base}", base))
        elif f.endswith(".csv"):
            results.append((f, f"📊 {base}", "Import CSV"))
        elif f.endswith(".json"):
            results.append((f, f"📋 {base}", "Import JSON"))
        elif f.endswith((".m3u", ".m3u8")):
            results.append((f, f"🎵 {base}", "Playlist M3U"))
        elif f.endswith(".pls"):
            results.append((f, f"📻 {base}", "Playlist PLS"))
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

def search_radio_browser_api(name="", country_code="", tag="", limit=30):
    """
    Recherche multicritères sur les miroirs Radio-Browser.
    Multi-criteria search on Radio-Browser mirrors.
    """
    params = {"limit": str(limit), "hidebroken": "true", "order": "votes", "reverse": "true"}
    if name: params["name"] = name
    if country_code: params["countrycode"] = country_code.upper()
    if tag: params["tag"] = tag

    for ep in RADIO_BROWSER_ENDPOINTS:
        res = query_radio_browser(ep, "stations/search", params)
        if res is not None:
            return res
    return []

# -----------------------------------------------------------------------------
# Boîte de dialogue : Réparation de flux mort via Radio-Browser
# Dialog: Repair broken stream using Radio-Browser
# -----------------------------------------------------------------------------

class RepairStreamDialog(Gtk.Dialog):
    def __init__(self, parent, station_name, current_url, country_code=""):
        super().__init__(
            title=f"🔎 Remplacer le flux : {station_name}",
            transient_for=parent,
            modal=True,
        )
        self.add_button("Annuler", Gtk.ResponseType.CANCEL)
        self.add_button("✅ Valider et remplacer", Gtk.ResponseType.OK)
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

        btn_search = Gtk.Button(label="🔎 Rechercher")
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
                    self.lbl_status.set_text("❌ Aucun flux trouvé pour ce nom. Modifiez le texte ci-dessus.")
                    return
                for r in results:
                    name = r.get("name", "Sans nom")
                    codec = r.get("codec", "MP3")
                    bitrate = f"{r.get('bitrate', 128)} kbps" if r.get('bitrate') else "-"
                    country = r.get("country", "")
                    url = r.get("url_resolved") or r.get("url", "")
                    votes = r.get("votes", 0)
                    self.store.append([name, codec, bitrate, country, url, votes])
                self.lbl_status.set_text(f"✅ {len(results)} flux trouvés. Sélectionnez le flux souhaité puis validez.")
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

    if u.startswith("https:///"):
        u = "https://" + u[9:].lstrip("/")
    elif u.startswith("http:///"):
        u = "http://" + u[8:].lstrip("/")

    return u.strip()

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

            def walk_group(elem, current_path=""):
                local_stations = []
                g_name = elem.attrib.get("name", "").strip()
                if g_name and g_name != "root":
                    full_group = f"{current_path}/{g_name}".strip("/") if current_path else g_name
                else:
                    full_group = current_path

                for child in elem:
                    if child.tag == "group":
                        local_stations.extend(walk_group(child, full_group))
                    elif child.tag in ("bookmark", "station"):
                        name = child.attrib.get("name", "").strip()
                        url = clean_stream_url(child.attrib.get("url", "").strip())
                        country = (child.attrib.get("country") or child.attrib.get("countrycode") or "").strip().upper()
                        genre = child.attrib.get("genre", "").strip()
                        if name and url and not name.startswith("[separator"):
                            grp = full_group if full_group else base_name
                            local_stations.append({
                                "name": name,
                                "url": url,
                                "group": grp,
                                "country": country,
                                "genre": genre
                            })
                return local_stations

            if root.tag == "bookmarks":
                stations = walk_group(root)
            else:
                def_country = (root.attrib.get("country") or root.attrib.get("countrycode") or "").strip().upper()
                def_group = root.attrib.get("name") or base_name
                for elem in root.iter():
                    if elem.tag in ("station", "bookmark"):
                        name = elem.attrib.get("name", "").strip()
                        url = elem.attrib.get("url", "").strip()
                        country = (elem.attrib.get("country") or elem.attrib.get("countrycode") or def_country).strip().upper()
                        grp = elem.attrib.get("group") or def_group
                        genre = elem.attrib.get("genre", "").strip()
                        if name and url and not name.startswith("[separator"):
                            stations.append({
                                "name": name,
                                "url": url,
                                "group": grp,
                                "country": country,
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
                                    genre = (s.get("genre") or "").strip()
                                    if name and url:
                                        stations.append({
                                            "name": name,
                                            "url": url,
                                            "group": grp_name,
                                            "country": country,
                                            "genre": genre
                                        })
                        elif "name" in item and "url" in item:
                            name = item.get("name", "").strip()
                            url = item.get("url", "").strip()
                            grp = item.get("group", "").strip() or base_name
                            country = (item.get("country") or item.get("country_code") or "").strip().upper()
                            genre = (item.get("genre") or "").strip()
                            if name and url:
                                stations.append({
                                    "name": name,
                                    "url": url,
                                    "group": grp,
                                    "country": country,
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
                    if first in ("nom", "name", "groupe", "group", "station"):
                        continue
                    if len(clean_row) == 2 and (clean_row[1].startswith("http://") or clean_row[1].startswith("https://")):
                        stations.append({
                            "name": clean_row[0],
                            "url": clean_row[1],
                            "group": base_name,
                            "country": "",
                            "genre": ""
                        })
                    elif len(clean_row) == 3:
                        if clean_row[1].startswith("http://") or clean_row[1].startswith("https://"):
                            stations.append({
                                "name": clean_row[0],
                                "url": clean_row[1],
                                "group": base_name,
                                "country": clean_row[2].upper(),
                                "genre": ""
                            })
                        elif clean_row[2].startswith("http://") or clean_row[2].startswith("https://"):
                            stations.append({
                                "name": clean_row[1],
                                "url": clean_row[2],
                                "group": clean_row[0],
                                "country": "",
                                "genre": ""
                            })
                    elif len(clean_row) >= 4 and (clean_row[2].startswith("http://") or clean_row[2].startswith("https://")):
                        stations.append({
                            "name": clean_row[1],
                            "url": clean_row[2],
                            "group": clean_row[0],
                            "country": clean_row[3].upper(),
                            "genre": ""
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
    def __init__(self, existing_stations, bouquets_db, initial_tab=0, initial_file=None):
        super().__init__(title=_("📻 Discover & Import stations (TiMonde)"))
        self.set_default_size(880, 600)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_border_width(12)
        self.set_icon_name("audio-x-generic")
        self.connect("destroy", self.on_destroy)

        self.existing_stations = existing_stations
        self.existing_urls = {s.get("url", "").strip() for s in existing_stations}
        self.existing_names = {s.get("name", "").strip().lower() for s in existing_stations}
        self.bouquets_db = bouquets_db

        self.saved = False
        self.chosen_group_name = ""
        self.selected_stations = []

        # Pool de threads pour test de santé / Health check worker pool
        self.executor = ThreadPoolExecutor(max_workers=8)
        self.current_check_generation = 0
        self.current_user_file = None
        self.current_user_group_default = "Mes Stations"
        self.current_user_check_generation = 0

        # Boîte verticale principale / Main VBox
        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(main_vbox)

        # 1. Barre supérieure : Sélecteur de Pays ISO universel & Bouton XML externe
        top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        main_vbox.pack_start(top_bar, False, False, 0)

        lbl_country = Gtk.Label(label=_("<b>🌍 Country:</b>"))
        lbl_country.set_use_markup(True)
        top_bar.pack_start(lbl_country, False, False, 0)

        self.combo_country = Gtk.ComboBoxText()
        for c_code, c_info in sorted(self.bouquets_db.items(), key=lambda x: x[1]["name"]):
            self.combo_country.append(c_code, c_info["name"])
        if "FR" in self.bouquets_db:
            self.combo_country.set_active_id("FR")
        elif self.bouquets_db:
            self.combo_country.set_active(0)
        self.combo_country.connect("changed", self.on_country_changed)
        top_bar.pack_start(self.combo_country, False, False, 0)

        # Communauté / Langue pour pays multilingues
        self.lbl_lang = Gtk.Label(label=_("<b>Language:</b>"))
        self.lbl_lang.set_use_markup(True)
        top_bar.pack_start(self.lbl_lang, False, False, 0)

        self.combo_lang = Gtk.ComboBoxText()
        self.combo_lang.connect("changed", self.on_lang_changed)
        top_bar.pack_start(self.combo_lang, False, False, 0)

        # Bouton XML externe
        btn_open_xml = Gtk.Button(label="📂 Ouvrir un XML externe...")
        btn_open_xml.set_tooltip_text("Charger et tester n'importe quel fichier XML de radios ou bouquets")
        btn_open_xml.connect("clicked", self.on_open_external_xml)
        top_bar.pack_end(btn_open_xml, False, False, 0)

        # 2. Onglets de Navigation :
        #   1: 🔎 Recherche Radio-Browser
        #   2: ⭐ Bouquets vérifiés (DAB+)
        #   3: 📂 Fichiers exemples (XML)
        self.notebook = Gtk.Notebook()
        self.notebook.connect("switch-page", self.on_notebook_page_changed)
        main_vbox.pack_start(self.notebook, True, True, 0)

        # =====================================================================
        # --- Onglet 1 : Recherche dans l'annuaire mondial Radio-Browser ---
        # =====================================================================
        tab_rb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        tab_rb.set_border_width(8)

        rb_filter_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        tab_rb.pack_start(rb_filter_box, False, False, 0)

        lbl_rb_name = Gtk.Label(label=_("Name / Keyword:"))
        rb_filter_box.pack_start(lbl_rb_name, False, False, 0)

        self.entry_rb_name = Gtk.Entry()
        self.entry_rb_name.set_placeholder_text("Ex: Jazz, Rock, FIP, RMC...")
        self.entry_rb_name.connect("activate", lambda w: self.on_search_rb_clicked())
        rb_filter_box.pack_start(self.entry_rb_name, True, True, 0)

        lbl_rb_tag = Gtk.Label(label=_("Genre:"))
        rb_filter_box.pack_start(lbl_rb_tag, False, False, 0)

        self.entry_rb_tag = Gtk.Entry()
        self.entry_rb_tag.set_placeholder_text("Ex: news, classical, ambient...")
        self.entry_rb_tag.connect("activate", lambda w: self.on_search_rb_clicked())
        rb_filter_box.pack_start(self.entry_rb_tag, False, False, 0)

        self.check_rb_only_country = Gtk.CheckButton(label="Filtrer sur ce pays")
        self.check_rb_only_country.set_active(True)
        rb_filter_box.pack_start(self.check_rb_only_country, False, False, 0)

        btn_rb_search = Gtk.Button(label="🔎 Rechercher")
        btn_rb_search.get_style_context().add_class("suggested-action")
        btn_rb_search.connect("clicked", lambda w: self.on_search_rb_clicked())
        rb_filter_box.pack_start(btn_rb_search, False, False, 0)

        # Tableau des résultats Radio-Browser
        # Store: [checked, name, country, tags, codec_bitrate, votes, url, is_dup]
        self.rb_store = Gtk.ListStore(bool, str, str, str, str, int, str, bool)
        self.rb_tree = Gtk.TreeView(model=self.rb_store)
        
        renderer_rb_check = Gtk.CellRendererToggle()
        renderer_rb_check.connect("toggled", self.on_rb_check_toggled)
        col_rb_check = Gtk.TreeViewColumn("Ajouter", renderer_rb_check, active=0)
        self.rb_tree.append_column(col_rb_check)

        col_rb_name = Gtk.TreeViewColumn("Station", Gtk.CellRendererText(), text=1)
        col_rb_name.set_expand(True)
        self.rb_tree.append_column(col_rb_name)

        col_rb_c = Gtk.TreeViewColumn("Pays", Gtk.CellRendererText(), text=2)
        self.rb_tree.append_column(col_rb_c)

        col_rb_tags = Gtk.TreeViewColumn("Tags / Style", Gtk.CellRendererText(), text=3)
        self.rb_tree.append_column(col_rb_tags)

        col_rb_codec = Gtk.TreeViewColumn("Format & Débit", Gtk.CellRendererText(), text=4)
        self.rb_tree.append_column(col_rb_codec)

        col_rb_votes = Gtk.TreeViewColumn("Votes", Gtk.CellRendererText(), text=5)
        self.rb_tree.append_column(col_rb_votes)

        scroll_rb = Gtk.ScrolledWindow()
        scroll_rb.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll_rb.set_shadow_type(Gtk.ShadowType.IN)
        scroll_rb.add(self.rb_tree)
        tab_rb.pack_start(scroll_rb, True, True, 0)

        rb_bot_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        tab_rb.pack_start(rb_bot_box, False, False, 0)

        btn_rb_check_all = Gtk.Button(label="Tout cocher")
        btn_rb_check_all.connect("clicked", lambda w: self.set_rb_checks(True))
        rb_bot_box.pack_start(btn_rb_check_all, False, False, 0)

        btn_rb_uncheck_all = Gtk.Button(label="Tout décocher")
        btn_rb_uncheck_all.connect("clicked", lambda w: self.set_rb_checks(False))
        rb_bot_box.pack_start(btn_rb_uncheck_all, False, False, 0)

        self.lbl_rb_status = Gtk.Label(label="Saisissez un mot-clé ou cliquez sur Rechercher pour explorer l'annuaire.")
        self.lbl_rb_status.set_halign(Gtk.Align.END)
        rb_bot_box.pack_end(self.lbl_rb_status, False, False, 0)

        self.notebook.append_page(tab_rb, Gtk.Label(label=_("🔎 Radio-Browser Search")))

        # =====================================================================
        # --- Onglet 2 : Bouquets vérifiés DAB+ ---
        # =====================================================================
        tab_bouquets = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        tab_bouquets.set_border_width(8)

        # Options National / Régions
        scope_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        tab_bouquets.pack_start(scope_box, False, False, 0)

        self.radio_national = Gtk.RadioButton.new_with_label(None, "⭐ Bouquet National (Grandes stations)")
        self.radio_national.connect("toggled", self.on_scope_changed)
        scope_box.pack_start(self.radio_national, False, False, 0)

        self.radio_region = Gtk.RadioButton.new_with_label_from_widget(self.radio_national, "📍 Régions & Locales :")
        self.radio_region.connect("toggled", self.on_scope_changed)
        scope_box.pack_start(self.radio_region, False, False, 0)

        self.combo_region = Gtk.ComboBoxText()
        self.combo_region.connect("changed", self.on_region_changed)
        scope_box.pack_start(self.combo_region, False, False, 0)

        # Tableau des stations du bouquet
        # Store: [checked, name, genre, health_markup, dup_markup, url, is_dup, is_dead, row_id]
        self.bouquet_store = Gtk.ListStore(bool, str, str, str, str, str, bool, bool, int)
        self.bouquet_tree = Gtk.TreeView(model=self.bouquet_store)
        
        renderer_check = Gtk.CellRendererToggle()
        renderer_check.connect("toggled", self.on_bouquet_check_toggled)
        col_check = Gtk.TreeViewColumn("Importer", renderer_check, active=0)
        self.bouquet_tree.append_column(col_check)

        col_name = Gtk.TreeViewColumn("Station", Gtk.CellRendererText(), text=1)
        col_name.set_expand(True)
        self.bouquet_tree.append_column(col_name)

        col_genre = Gtk.TreeViewColumn("Genre / Thématique", Gtk.CellRendererText(), text=2)
        col_genre.set_fixed_width(170)
        self.bouquet_tree.append_column(col_genre)

        renderer_health = Gtk.CellRendererText()
        col_health = Gtk.TreeViewColumn("Disponibilité en direct", renderer_health, markup=3)
        col_health.set_fixed_width(160)
        self.bouquet_tree.append_column(col_health)

        renderer_dup = Gtk.CellRendererText()
        col_dup = Gtk.TreeViewColumn("Statut Favoris", renderer_dup, markup=4)
        col_dup.set_fixed_width(150)
        self.bouquet_tree.append_column(col_dup)

        scroll_b = Gtk.ScrolledWindow()
        scroll_b.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll_b.set_shadow_type(Gtk.ShadowType.IN)
        scroll_b.add(self.bouquet_tree)
        tab_bouquets.pack_start(scroll_b, True, True, 0)

        # Boutons d'action sous la liste du bouquet
        b_action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        tab_bouquets.pack_start(b_action_box, False, False, 0)

        btn_check_all = Gtk.Button(label="Tout cocher")
        btn_check_all.connect("clicked", lambda w: self.set_bouquet_checks(True))
        b_action_box.pack_start(btn_check_all, False, False, 0)

        btn_uncheck_all = Gtk.Button(label="Tout décocher")
        btn_uncheck_all.connect("clicked", lambda w: self.set_bouquet_checks(False))
        b_action_box.pack_start(btn_uncheck_all, False, False, 0)

        self.btn_repair = Gtk.Button(label="🔧 Réparer le flux sélectionné (Radio-Browser)...")
        self.btn_repair.set_tooltip_text("Remplacer le lien mort sélectionné par un flux officiel actif")
        self.btn_repair.connect("clicked", self.on_repair_clicked)
        b_action_box.pack_start(self.btn_repair, False, False, 0)

        self.lbl_bouquet_count = Gtk.Label()
        self.lbl_bouquet_count.set_halign(Gtk.Align.END)
        b_action_box.pack_end(self.lbl_bouquet_count, False, False, 0)

        self.notebook.append_page(tab_bouquets, Gtk.Label(label=_("⭐ Verified DAB+ Bouquets")))

        # =====================================================================
        # --- Onglet 3 : Fichiers exemples (XML) & Thématiques hors-DAB ---
        # =====================================================================
        tab_examples = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        tab_examples.set_border_width(8)

        ex_top_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        tab_examples.pack_start(ex_top_box, False, False, 0)

        lbl_ex = Gtk.Label(label=_("<b>Sample file:</b>"))
        lbl_ex.set_use_markup(True)
        ex_top_box.pack_start(lbl_ex, False, False, 0)

        self.combo_examples = Gtk.ComboBoxText()
        self.available_examples = list_available_examples()
        for fpath, label, title in self.available_examples:
            self.combo_examples.append(fpath, label)
        if self.available_examples:
            self.combo_examples.set_active(0)
        self.combo_examples.connect("changed", self.on_example_changed)
        ex_top_box.pack_start(self.combo_examples, True, True, 0)

        btn_browse_xml = Gtk.Button(label="📂 Parcourir un fichier XML...")
        btn_browse_xml.set_tooltip_text("Charger et tester n'importe quel fichier XML externe")
        btn_browse_xml.connect("clicked", self.on_browse_external_xml)
        ex_top_box.pack_start(btn_browse_xml, False, False, 0)

        # Tableau des stations de l'exemple
        # Store: [checked, name, genre, health_markup, dup_markup, url, is_dup, is_dead, row_id]
        self.example_store = Gtk.ListStore(bool, str, str, str, str, str, bool, bool, int, str)
        self.example_tree = Gtk.TreeView(model=self.example_store)

        renderer_ex_check = Gtk.CellRendererToggle()
        renderer_ex_check.connect("toggled", self.on_example_check_toggled)
        col_ex_check = Gtk.TreeViewColumn("Importer", renderer_ex_check, active=0)
        self.example_tree.append_column(col_ex_check)

        col_ex_name = Gtk.TreeViewColumn("Station", Gtk.CellRendererText(), text=1)
        col_ex_name.set_expand(True)
        self.example_tree.append_column(col_ex_name)

        col_ex_genre = Gtk.TreeViewColumn("Genre / Thématique", Gtk.CellRendererText(), text=2)
        col_ex_genre.set_fixed_width(180)
        self.example_tree.append_column(col_ex_genre)

        col_ex_health = Gtk.TreeViewColumn("Disponibilité", Gtk.CellRendererText(), markup=3)
        col_ex_health.set_fixed_width(160)
        self.example_tree.append_column(col_ex_health)

        col_ex_dup = Gtk.TreeViewColumn("Statut Favoris", Gtk.CellRendererText(), markup=4)
        col_ex_dup.set_fixed_width(150)
        self.example_tree.append_column(col_ex_dup)

        scroll_ex = Gtk.ScrolledWindow()
        scroll_ex.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll_ex.set_shadow_type(Gtk.ShadowType.IN)
        scroll_ex.add(self.example_tree)
        tab_examples.pack_start(scroll_ex, True, True, 0)

        # Boutons d'action sous la liste d'exemples
        ex_action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        tab_examples.pack_start(ex_action_box, False, False, 0)

        btn_ex_check_all = Gtk.Button(label="Tout cocher")
        btn_ex_check_all.connect("clicked", lambda w: self.set_example_checks(True))
        ex_action_box.pack_start(btn_ex_check_all, False, False, 0)

        btn_ex_uncheck_all = Gtk.Button(label="Tout décocher")
        btn_ex_uncheck_all.connect("clicked", lambda w: self.set_example_checks(False))
        ex_action_box.pack_start(btn_ex_uncheck_all, False, False, 0)

        self.lbl_example_count = Gtk.Label()
        self.lbl_example_count.set_halign(Gtk.Align.END)
        ex_action_box.pack_end(self.lbl_example_count, False, False, 0)

        self.notebook.append_page(tab_examples, Gtk.Label(label=_("📂 Sample Files")))

        # =====================================================================
        # --- Onglet 4 : Importer mes fichiers (XML, CSV, JSON, M3U, PLS) ---
        # =====================================================================
        tab_user = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        tab_user.set_border_width(8)

        # Barre supérieure du 4ème onglet
        user_top_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        tab_user.pack_start(user_top_box, False, False, 0)

        btn_user_browse = Gtk.Button(label="📂 Choisir un fichier...")
        btn_user_browse.get_style_context().add_class("suggested-action")
        btn_user_browse.set_tooltip_text("Sélectionner un fichier XML (RadioTray, TiMonde), CSV, JSON, M3U ou PLS")
        btn_user_browse.connect("clicked", self.on_user_browse_clicked)
        user_top_box.pack_start(btn_user_browse, False, False, 0)

        self.btn_user_reload = Gtk.Button(label="🔄 Recharger")
        self.btn_user_reload.set_sensitive(False)
        self.btn_user_reload.connect("clicked", lambda w: self.load_user_file(self.current_user_file) if self.current_user_file else None)
        user_top_box.pack_start(self.btn_user_reload, False, False, 0)

        self.lbl_user_file_info = Gtk.Label(label="<i>Aucun fichier sélectionné (XML, CSV, JSON, M3U, PLS)</i>")
        self.lbl_user_file_info.set_use_markup(True)
        self.lbl_user_file_info.set_halign(Gtk.Align.START)
        user_top_box.pack_start(self.lbl_user_file_info, True, True, 0)

        # Option : préserver les groupes
        self.chk_preserve_groups = Gtk.CheckButton(label="📁 Conserver l'organisation en dossiers / groupes")
        self.chk_preserve_groups.set_active(True)
        self.chk_preserve_groups.set_tooltip_text("Si coché, chaque station sera ajoutée dans son groupe respectif d'origine.")
        self.chk_preserve_groups.connect("toggled", self.on_preserve_groups_toggled)
        user_top_box.pack_end(self.chk_preserve_groups, False, False, 0)

        # Tableau des stations utilisateur
        # Store: [checked, name, group_display, country, health_markup, dup_markup, url, is_dup, is_dead, row_id, raw_group]
        self.user_store = Gtk.ListStore(bool, str, str, str, str, str, str, bool, bool, int, str)
        self.user_tree = Gtk.TreeView(model=self.user_store)

        renderer_u_check = Gtk.CellRendererToggle()
        renderer_u_check.connect("toggled", self.on_user_check_toggled)
        col_u_check = Gtk.TreeViewColumn("Importer", renderer_u_check, active=0)
        self.user_tree.append_column(col_u_check)

        col_u_name = Gtk.TreeViewColumn("Station", Gtk.CellRendererText(), text=1)
        col_u_name.set_expand(True)
        self.user_tree.append_column(col_u_name)

        col_u_grp = Gtk.TreeViewColumn("Dossier / Groupe", Gtk.CellRendererText(), text=2)
        col_u_grp.set_fixed_width(170)
        self.user_tree.append_column(col_u_grp)

        col_u_country = Gtk.TreeViewColumn("Pays", Gtk.CellRendererText(), text=3)
        col_u_country.set_fixed_width(65)
        self.user_tree.append_column(col_u_country)

        col_u_health = Gtk.TreeViewColumn("Disponibilité", Gtk.CellRendererText(), markup=4)
        col_u_health.set_fixed_width(150)
        self.user_tree.append_column(col_u_health)

        col_u_dup = Gtk.TreeViewColumn("Statut Favoris", Gtk.CellRendererText(), markup=5)
        col_u_dup.set_fixed_width(130)
        self.user_tree.append_column(col_u_dup)

        col_u_url = Gtk.TreeViewColumn("URL du flux", Gtk.CellRendererText(), text=6)
        col_u_url.set_fixed_width(220)
        self.user_tree.append_column(col_u_url)

        scroll_user = Gtk.ScrolledWindow()
        scroll_user.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll_user.set_shadow_type(Gtk.ShadowType.IN)
        scroll_user.add(self.user_tree)
        tab_user.pack_start(scroll_user, True, True, 0)

        # Barre d'actions sous le tableau utilisateur
        user_action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        tab_user.pack_start(user_action_box, False, False, 0)

        btn_u_check_all = Gtk.Button(label="Tout cocher")
        btn_u_check_all.connect("clicked", lambda w: self.set_user_checks(True))
        user_action_box.pack_start(btn_u_check_all, False, False, 0)

        btn_u_uncheck_all = Gtk.Button(label="Tout décocher")
        btn_u_uncheck_all.connect("clicked", lambda w: self.set_user_checks(False))
        user_action_box.pack_start(btn_u_uncheck_all, False, False, 0)

        btn_u_new_only = Gtk.Button(label="Cocher uniquement les nouveaux")
        btn_u_new_only.connect("clicked", lambda w: self.set_user_checks_new_only())
        user_action_box.pack_start(btn_u_new_only, False, False, 0)

        btn_u_test = Gtk.Button(label="🌐 Tester les flux")
        btn_u_test.set_tooltip_text("Vérifier en direct la disponibilité des liens du fichier")
        btn_u_test.connect("clicked", lambda w: self.test_user_streams())
        user_action_box.pack_start(btn_u_test, False, False, 0)

        self.lbl_user_count = Gtk.Label()
        self.lbl_user_count.set_halign(Gtk.Align.END)
        user_action_box.pack_end(self.lbl_user_count, False, False, 0)

        self.notebook.append_page(tab_user, Gtk.Label(label=_("📥 Import my files")))

        # 3. Pied de page commun : Groupe cible & Boutons
        bottom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        main_vbox.pack_start(bottom_box, False, False, 0)

        lbl_target = Gtk.Label(label=_("<b>Group name in your favorites:</b>"))
        lbl_target.set_use_markup(True)
        bottom_box.pack_start(lbl_target, False, False, 0)

        self.entry_group = Gtk.Entry()
        self.entry_group.set_width_chars(32)
        bottom_box.pack_start(self.entry_group, True, True, 0)

        btn_cancel = Gtk.Button(label=" Annuler ")
        btn_cancel.connect("clicked", lambda w: self.destroy())
        bottom_box.pack_start(btn_cancel, False, False, 0)

        self.btn_import = Gtk.Button(label=" ➕ Importer dans mes favoris ")
        self.btn_import.get_style_context().add_class("suggested-action")
        self.btn_import.set_sensitive(False)
        self.btn_import.connect("clicked", self.on_import_clicked)
        bottom_box.pack_start(self.btn_import, False, False, 0)

        # Initialisation
        self.update_languages()
        self.update_regions_combo()
        self.load_current_bouquet()
        if self.available_examples:
            self.load_example_file(self.available_examples[0][0])
        # Définir l'onglet initial demandé (par défaut 0 : Radio-Browser)
        target_tab = initial_tab if (0 <= initial_tab < self.notebook.get_n_pages()) else 0
        self.notebook.set_current_page(target_tab)
        if initial_file:
            self.load_user_file(initial_file)

    # -------------------------------------------------------------------------
    # Gestion des Onglets & Sélection
    # -------------------------------------------------------------------------

    def on_country_changed(self, widget):
        self.update_languages()
        self.update_regions_combo()
        self.load_current_bouquet()

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

    def on_destroy(self, widget):
        try:
            self.executor.shutdown(wait=False)
        except Exception:
            pass
        Gtk.main_quit()

    def on_notebook_page_changed(self, notebook, page, page_num):
        if not hasattr(self, "entry_group"):
            return
        if page_num == 0:
            c_name = self.combo_country.get_active_text() or "Radio"
            self.entry_group.set_text(f"Radio-Browser - {c_name}")
        elif page_num == 1:
            country_id, info, national, regions = self.get_current_data()
            if self.radio_region.get_active():
                reg = self.combo_region.get_active_text() or "Régions"
                self.entry_group.set_text(f"{info.get('name', 'Bouquet')} - {reg}")
            else:
                self.entry_group.set_text(f"{info.get('name', 'Bouquet')} (National)")
        elif page_num == 2:
            active_id = self.combo_examples.get_active_id()
            if active_id:
                try:
                    tree = ET.parse(active_id)
                    title = tree.getroot().attrib.get("name")
                    if title:
                        self.entry_group.set_text(title)
                    else:
                        self.entry_group.set_text(os.path.splitext(os.path.basename(active_id))[0])
                except Exception:
                    self.entry_group.set_text(os.path.splitext(os.path.basename(active_id))[0])
        elif page_num == 3:
            if self.chk_preserve_groups.get_active() and self.current_user_file:
                self.entry_group.set_text("(Groupes préservés du fichier)")
            else:
                self.entry_group.set_text(self.current_user_group_default)
        self.update_import_button_sensitivity()

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

    def update_languages(self):
        country_id = self.combo_country.get_active_id()
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

    def get_current_data(self):
        country_id = self.combo_country.get_active_id()
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

    # -------------------------------------------------------------------------
    # Chargement & Test Frugal en direct du Bouquet
    # -------------------------------------------------------------------------

    def load_current_bouquet(self):
        country_id, info, national, regions = self.get_current_data()
        is_region = self.radio_region.get_active()
        self.combo_region.set_sensitive(is_region and bool(regions))

        stations = []
        country_name = info.get("name", "").split()[0]
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

        self.entry_group.set_text(default_group)
        self.bouquet_store.clear()

        self.current_check_generation += 1
        gen = self.current_check_generation

        items_to_check = []
        for i, (name, url, genre) in enumerate(stations):
            clean_url = url.strip()
            clean_name = name.strip().lower()

            is_dup = (clean_url in self.existing_urls) or (clean_name in self.existing_names)
            # RÈGLE D'OR : ZÉRO sélection automatique par défaut (l'utilisateur choisit explicitement ses stations)
            checked = False
            status_note = "<span color='#888888'><i>(Déjà dans vos favoris)</i></span>" if is_dup else "<span color='#2e7d32'><b>Nouveau</b></span>"
            health_note = "<span color='#888888'>⏳ Vérification...</span>"

            tree_iter = self.bouquet_store.append([checked, name, genre, health_note, status_note, clean_url, is_dup, False, i])
            items_to_check.append((i, clean_url))

        self.update_bouquet_count()

        # Lancer le test frugal en arrière-plan
        def check_worker(item_id, target_url, target_gen):
            is_ok, msg = check_stream_url(target_url)

            def update_ui():
                if target_gen != self.current_check_generation:
                    return
                # Trouver la ligne correspondante
                it = self.bouquet_store.get_iter_first()
                while it:
                    if self.bouquet_store.get_value(it, 8) == item_id:
                        if is_ok == "GEOBLOCKED":
                            markup = f"<span color='#f57c00'><b>🟠 {msg}</b></span>"
                            self.bouquet_store.set_value(it, 3, markup)
                            self.bouquet_store.set_value(it, 7, False)
                        elif is_ok:
                            markup = f"<span color='#2e7d32'>🟢 {msg}</span>"
                            self.bouquet_store.set_value(it, 3, markup)
                            self.bouquet_store.set_value(it, 7, False)
                        else:
                            markup = f"<span color='#d32f2f'><b>🔴 {msg}</b></span>"
                            self.bouquet_store.set_value(it, 3, markup)
                            self.bouquet_store.set_value(it, 7, True)
                            # Règle d'or : décocher automatiquement si le lien est mort
                            self.bouquet_store.set_value(it, 0, False)
                        break
                    it = self.bouquet_store.iter_next(it)
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
            # Ne pas cocher les doublons ni les flux morts lors d'un "Tout cocher"
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
        self.lbl_bouquet_count.set_text(f"{checked} / {total} station(s) sélectionnée(s)")
        self.update_import_button_sensitivity()

    def update_import_button_sensitivity(self):
        current_page = self.notebook.get_current_page()
        selected_count = 0
        if current_page == 0:
            it = self.rb_store.get_iter_first()
            while it:
                if self.rb_store.get_value(it, 0):
                    selected_count += 1
                it = self.rb_store.iter_next(it)
        elif current_page == 1:
            it = self.bouquet_store.get_iter_first()
            while it:
                if self.bouquet_store.get_value(it, 0):
                    selected_count += 1
                it = self.bouquet_store.iter_next(it)
        elif current_page == 2:
            it = self.example_store.get_iter_first()
            while it:
                if self.example_store.get_value(it, 0):
                    selected_count += 1
                it = self.example_store.iter_next(it)
        self.btn_import.set_sensitive(selected_count > 0)

    # -------------------------------------------------------------------------
    # Réparation de Flux Mort via Radio-Browser & Remplacement XML
    # -------------------------------------------------------------------------

    def on_repair_clicked(self, widget):
        model, tree_iter = self.bouquet_tree.get_selection().get_selected()
        if not tree_iter:
            return

        station_name = model.get_value(tree_iter, 1)
        current_url = model.get_value(tree_iter, 5)
        country_id = self.combo_country.get_active_id() or ""

        dlg = RepairStreamDialog(self, station_name, current_url, country_id)
        res = dlg.run()
        new_url = dlg.get_chosen_url()
        dlg.destroy()

        if res == Gtk.ResponseType.OK and new_url:
            clean_new_url = new_url.strip()
            # Mettre à jour l'affichage
            model.set_value(tree_iter, 5, clean_new_url)
            model.set_value(tree_iter, 3, "<span color='#2e7d32'>🟢 Réparé (En ligne)</span>")
            model.set_value(tree_iter, 7, False)
            model.set_value(tree_iter, 0, True)
            self.update_bouquet_count()

            # Mettre à jour le fichier XML d'origine
            self.save_stream_to_xml(station_name, current_url, clean_new_url)

    def save_stream_to_xml(self, station_name, old_url, new_url):
        country_id, info, _nat, _regs = self.get_current_data()
        xml_path = info.get("xml_path")
        if not xml_path or not os.path.exists(xml_path):
            return

        target_file = xml_path
        # Si le fichier est en lecture seule système, dupliquer vers ~/.local/share/timonde/bouquets/
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
    # Onglet Radio-Browser : Recherche Mondiale
    # -------------------------------------------------------------------------

    def on_search_rb_clicked(self):
        query = self.entry_rb_name.get_text().strip()
        tag = self.entry_rb_tag.get_text().strip()
        country_code = self.combo_country.get_active_id() if self.check_rb_only_country.get_active() else ""

        self.lbl_rb_status.set_text("Recherche sur Radio-Browser en cours...")
        self.rb_store.clear()

        def worker():
            results = search_radio_browser_api(name=query, country_code=country_code, tag=tag, limit=40)

            def on_done():
                if not results:
                    self.lbl_rb_status.set_text("❌ Aucune radio trouvée pour ces critères.")
                    return
                for r in results:
                    name = r.get("name", "Sans nom").strip()
                    c_code = r.get("countrycode", "").upper()
                    tags = r.get("tags", "")
                    codec = r.get("codec", "MP3")
                    bitrate = f"{r.get('bitrate', 128)}k" if r.get("bitrate") else ""
                    codec_str = f"{codec} {bitrate}".strip()
                    votes = r.get("votes", 0)
                    url = (r.get("url_resolved") or r.get("url", "")).strip()

                    is_dup = (url in self.existing_urls) or (name.lower() in self.existing_names)
                    self.rb_store.append([False, name, c_code, tags[:30], codec_str, votes, url, is_dup])

                self.lbl_rb_status.set_text(f"✅ {len(results)} stations trouvées.")
                self.update_import_button_sensitivity()

            GLib.idle_add(on_done)

        self.executor.submit(worker)

    def on_rb_check_toggled(self, widget, path):
        it = self.rb_store.get_iter(path)
        cur = self.rb_store.get_value(it, 0)
        self.rb_store.set_value(it, 0, not cur)
        self.update_import_button_sensitivity()

    def set_rb_checks(self, val):
        it = self.rb_store.get_iter_first()
        while it:
            is_dup = self.rb_store.get_value(it, 7)
            if val and is_dup:
                self.rb_store.set_value(it, 0, False)
            else:
                self.rb_store.set_value(it, 0, val)
            it = self.rb_store.iter_next(it)
        self.update_import_button_sensitivity()

    # -------------------------------------------------------------------------
    # Import de Fichier XML externe
    # -------------------------------------------------------------------------

    def on_open_external_xml(self, widget):
        chooser = Gtk.FileChooserDialog(
            title="📂 Choisir un fichier bouquet XML",
            transient_for=self,
            action=Gtk.FileChooserAction.OPEN,
        )
        chooser.add_button("Annuler", Gtk.ResponseType.CANCEL)
        chooser.add_button("Ouvrir", Gtk.ResponseType.OK)
        filter_xml = Gtk.FileFilter()
        filter_xml.set_name("Fichiers XML (*.xml)")
        filter_xml.add_pattern("*.xml")
        chooser.add_filter(filter_xml)

        res = chooser.run()
        filename = chooser.get_filename()
        chooser.destroy()

        if res == Gtk.ResponseType.OK and filename:
            self.load_external_xml(filename)

    def load_external_xml(self, path):
        try:
            root = safe_parse_xml(path)
            if root is None:
                sys.stderr.write(f"Fichier XML illisible : {path}\n")
                return
            stations = []
            for st in root.iter("station"):
                name = st.attrib.get("name", "")
                url = st.attrib.get("url", "")
                genre = st.attrib.get("genre", "Divers")
                if name and url:
                    stations.append((name, url, genre))
            for bk in root.iter("bookmark"):
                name = bk.attrib.get("name", "")
                url = bk.attrib.get("url", "")
                if name and url and not name.startswith("[separator"):
                    stations.append((name, url, "Favoris"))

            if not stations:
                sys.stderr.write("Aucune station exploitable dans ce fichier XML.\n")
                return

            base_name = os.path.splitext(os.path.basename(path))[0]
            country_attr = (root.attrib.get("country") or root.attrib.get("countrycode") or "").strip().upper()
            custom_id = country_attr if country_attr else f"EXT_{base_name.upper()}"
            self.bouquets_db[custom_id] = {
                "name": f"📂 {base_name}" if not country_attr else f"📂 {base_name} [{country_attr}]",
                "country_code": country_attr,
                "multilingual": False,
                "languages": [],
                "sub_bouquets": {},
                "national": stations,
                "regions": {},
                "xml_path": path
            }
            self.combo_country.append(custom_id, f"📂 {base_name}")
            self.combo_country.set_active_id(custom_id)
        except Exception as e:
            sys.stderr.write(f"Erreur chargement XML externe : {e}\n")

    # -------------------------------------------------------------------------
    # Validation Finale & Export JSON pour TiMonde
    # -------------------------------------------------------------------------

    def on_import_clicked(self, widget):
        group_name = self.entry_group.get_text().strip()
        if not group_name:
            group_name = "Bouquets Radio"

        selected = []
        all_bouquet_stations = []
        current_page = self.notebook.get_current_page()
        country_id = self.combo_country.get_active_id() or ""

        if current_page == 0:
            # Onglet 1 : Radio-Browser
            it = self.rb_store.get_iter_first()
            while it:
                if self.rb_store.get_value(it, 0):
                    name = self.rb_store.get_value(it, 1)
                    rb_country = (self.rb_store.get_value(it, 2) or "").strip() or country_id
                    url = self.rb_store.get_value(it, 6)
                    selected.append({"name": name, "url": url, "country": rb_country})
                it = self.rb_store.iter_next(it)
        elif current_page == 1:
            # Onglet 2 : Bouquets DAB+
            it = self.bouquet_store.get_iter_first()
            while it:
                name = self.bouquet_store.get_value(it, 1)
                url = self.bouquet_store.get_value(it, 5)
                all_bouquet_stations.append({"name": name, "url": url, "country": country_id})
                if self.bouquet_store.get_value(it, 0):
                    selected.append({"name": name, "url": url, "country": country_id})
                it = self.bouquet_store.iter_next(it)
        elif current_page == 2:
            # Onglet 3 : Exemples (XML, CSV, JSON)
            it = self.example_store.get_iter_first()
            while it:
                if self.example_store.get_value(it, 0):
                    name = self.example_store.get_value(it, 1)
                    url = self.example_store.get_value(it, 5)
                    st_country = self.example_store.get_value(it, 9) if self.example_store.get_n_columns() > 9 else ""
                    selected.append({"name": name, "url": url, "country": st_country})
                it = self.example_store.iter_next(it)
        elif current_page == 3:
            # Onglet 4 : Importer mes fichiers
            preserve = self.chk_preserve_groups.get_active()
            it = self.user_store.get_iter_first()
            while it:
                if self.user_store.get_value(it, 0):
                    name = self.user_store.get_value(it, 1)
                    st_group_raw = self.user_store.get_value(it, 10)
                    st_country = self.user_store.get_value(it, 3) or ""
                    url = self.user_store.get_value(it, 6)
                    target_st_grp = st_group_raw if (preserve and st_group_raw) else group_name
                    selected.append({
                        "name": name,
                        "url": url,
                        "country": st_country,
                        "group": target_st_grp
                    })
                it = self.user_store.iter_next(it)

        if not selected and not all_bouquet_stations:
            return

        self.chosen_group_name = group_name
        self.selected_stations = selected
        self.saved = True

        result = {
            "group_name": self.chosen_group_name,
            "country_code": country_id,
            "stations": self.selected_stations,
            "all_bouquet_stations": all_bouquet_stations
        }
        print(json.dumps(result, ensure_ascii=False), flush=True)
        self.destroy()

# -----------------------------------------------------------------------------
# Parseur des Bouquets XML existants / Existing XML Bouquets Parser
# -----------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    # Gestion de l'Onglet 3 : Fichiers exemples XML & Thématiques
    # -------------------------------------------------------------------------

    def on_example_changed(self, widget):
        path = self.combo_examples.get_active_id()
        if path:
            self.load_example_file(path)

    def on_browse_external_xml(self, widget):
        chooser = Gtk.FileChooserDialog(
            title="📂 Choisir un fichier de radios (XML, CSV, JSON)",
            transient_for=self,
            action=Gtk.FileChooserAction.OPEN,
        )
        chooser.add_button("Annuler", Gtk.ResponseType.CANCEL)
        chooser.add_button("Ouvrir", Gtk.ResponseType.OK)
        
        filter_all = Gtk.FileFilter()
        filter_all.set_name("Tous fichiers supportés (*.xml, *.csv, *.json)")
        filter_all.add_pattern("*.xml")
        filter_all.add_pattern("*.csv")
        filter_all.add_pattern("*.json")
        chooser.add_filter(filter_all)

        res = chooser.run()
        filename = chooser.get_filename()
        chooser.destroy()

        if res == Gtk.ResponseType.OK and filename:
            base = os.path.basename(filename)
            self.combo_examples.append(filename, f"📄 {base}")
            self.combo_examples.set_active_id(filename)
            self.load_example_file(filename)

    def load_example_file(self, path):
        stations = []
        group_name = os.path.splitext(os.path.basename(path))[0]

        if path.endswith(".xml"):
            try:
                tree = ET.parse(path)
                root = tree.getroot()
                group_name = root.attrib.get("name", group_name)

                for st in root.iter("station"):
                    name = st.attrib.get("name", "")
                    url = st.attrib.get("url", "")
                    genre = st.attrib.get("genre", "Divers")
                    country = st.attrib.get("country", "")
                    status = st.attrib.get("status", "unknown")
                    if name and url:
                        stations.append((name, url, genre, country, status))

                for bk in root.iter("bookmark"):
                    name = bk.attrib.get("name", "")
                    url = bk.attrib.get("url", "")
                    country = bk.attrib.get("country", "")
                    if name and url and not name.startswith("[separator"):
                        stations.append((name, url, "Favoris", country, "unknown"))
            except Exception as e:
                sys.stderr.write(f"Erreur parsing XML {path}: {e}\n")

        elif path.endswith(".csv"):
            group_name = "Import CSV"
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if line.lower().startswith("nom,") or line.lower().startswith("groupe,") or line.lower().startswith("name,"):
                            continue
                        cols = [c.strip() for c in line.split(",")]
                        if len(cols) == 2 and (cols[1].startswith("http://") or cols[1].startswith("https://")):
                            stations.append((cols[0], cols[1], "CSV", "", "online"))
                        elif len(cols) == 3:
                            if cols[1].startswith("http://") or cols[1].startswith("https://"):
                                stations.append((cols[0], cols[1], "CSV", cols[2], "online"))
                            elif cols[2].startswith("http://") or cols[2].startswith("https://"):
                                group_name = cols[0] or group_name
                                stations.append((cols[1], cols[2], "CSV", "", "online"))
                        elif len(cols) >= 4 and (cols[2].startswith("http://") or cols[2].startswith("https://")):
                            group_name = cols[0] or group_name
                            stations.append((cols[1], cols[2], "CSV", cols[3], "online"))
            except Exception as e:
                sys.stderr.write(f"Erreur parsing CSV {path}: {e}\n")

        elif path.endswith(".json"):
            group_name = "Import JSON"
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and "stations" in item:
                            g_title = item.get("group", group_name)
                            for s in item.get("stations", []):
                                stations.append((s.get("name", "Station"), s.get("url", ""), g_title, s.get("country", ""), "online"))
                        elif isinstance(item, dict) and "url" in item:
                            stations.append((item.get("name", "Station"), item.get("url", ""), "JSON", item.get("country", ""), "online"))
            except Exception as e:
                sys.stderr.write(f"Erreur parsing JSON {path}: {e}\n")
        elif path.endswith((".m3u", ".m3u8", ".pls")):
            parsed = parse_user_file_into_stations(path)
            for s in parsed:
                stations.append((s["name"], s["url"], s.get("genre") or s.get("group") or "Playlist", s.get("country", ""), "online"))

        self.entry_group.set_text(group_name)
        self.example_store.clear()
        row_id = 0
        for name, url, genre, country, status in stations:
            is_dup = url.strip() in self.existing_urls or name.strip().lower() in self.existing_names
            dup_markup = '<span foreground="#e67e22">⚠️ Présent</span>' if is_dup else '<span foreground="#27ae60">Nouveau</span>'
            if status == "online":
                health_markup = '<span foreground="#2ecc71">🟢 En direct</span>'
                is_dead = False
            elif status == "offline":
                health_markup = '<span foreground="#e74c3c">🔴 Inactif</span>'
                is_dead = True
            else:
                health_markup = '<span foreground="#95a5a6">⚪ Non testé</span>'
                is_dead = False

            display_genre = f"{genre} [{country}]" if country else genre
            self.example_store.append([False, name, display_genre, health_markup, dup_markup, url, is_dup, is_dead, row_id, country])
            row_id += 1

        self.update_example_count()

    # -------------------------------------------------------------------------
    # Gestion de l'Onglet 4 : Importer mes fichiers personnels
    # -------------------------------------------------------------------------

    def on_preserve_groups_toggled(self, widget):
        if self.notebook.get_current_page() == 3:
            if self.chk_preserve_groups.get_active() and self.current_user_file:
                self.entry_group.set_text("(Groupes préservés du fichier)")
            else:
                self.entry_group.set_text(self.current_user_group_default)

    def on_user_browse_clicked(self, widget):
        chooser = Gtk.FileChooserDialog(
            title="📂 Choisir un fichier personnel de radios",
            transient_for=self,
            action=Gtk.FileChooserAction.OPEN,
        )
        chooser.add_button("Annuler", Gtk.ResponseType.CANCEL)
        chooser.add_button("Ouvrir", Gtk.ResponseType.OK)

        filter_all = Gtk.FileFilter()
        filter_all.set_name("Tous fichiers supportés (*.xml, *.csv, *.json, *.m3u, *.pls)")
        filter_all.add_pattern("*.xml")
        filter_all.add_pattern("*.csv")
        filter_all.add_pattern("*.json")
        filter_all.add_pattern("*.m3u")
        filter_all.add_pattern("*.m3u8")
        filter_all.add_pattern("*.pls")
        chooser.add_filter(filter_all)

        filter_xml = Gtk.FileFilter()
        filter_xml.set_name("Signets XML (*.xml)")
        filter_xml.add_pattern("*.xml")
        chooser.add_filter(filter_xml)

        filter_csv = Gtk.FileFilter()
        filter_csv.set_name("Fichiers CSV (*.csv)")
        filter_csv.add_pattern("*.csv")
        chooser.add_filter(filter_csv)

        filter_json = Gtk.FileFilter()
        filter_json.set_name("Fichiers JSON (*.json)")
        filter_json.add_pattern("*.json")
        chooser.add_filter(filter_json)

        filter_m3u = Gtk.FileFilter()
        filter_m3u.set_name("Playlists M3U / M3U8 (*.m3u, *.m3u8)")
        filter_m3u.add_pattern("*.m3u")
        filter_m3u.add_pattern("*.m3u8")
        chooser.add_filter(filter_m3u)

        res = chooser.run()
        filename = chooser.get_filename()
        chooser.destroy()

        if res == Gtk.ResponseType.OK and filename:
            self.load_user_file(filename)

    def load_user_file(self, path):
        if not os.path.isfile(path):
            return

        self.current_user_file = path
        self.btn_user_reload.set_sensitive(True)
        base_name = os.path.splitext(os.path.basename(path))[0]
        self.current_user_group_default = f"Import {base_name}"

        stations = parse_user_radio_file(path)
        groups = set(s.get("group", "") for s in stations if s.get("group"))

        info_text = f"<b>Fichier :</b> {os.path.basename(path)} — <b>{len(stations)}</b> station(s)"
        if groups:
            info_text += f", <b>{len(groups)}</b> groupe(s)"
        self.lbl_user_file_info.set_markup(info_text)

        if self.notebook.get_current_page() == 3:
            if self.chk_preserve_groups.get_active() and groups:
                self.entry_group.set_text("(Groupes préservés du fichier)")
            else:
                self.entry_group.set_text(self.current_user_group_default)

        self.user_store.clear()
        self.current_user_check_generation += 1

        for i, st in enumerate(stations):
            name = st.get("name", "Station")
            url = st.get("url", "").strip()
            grp = st.get("group", "").strip() or base_name
            country = st.get("country", "").strip().upper()

            is_dup = (url in self.existing_urls) or (name.strip().lower() in self.existing_names)
            checked = False
            dup_markup = '<span foreground="#e67e22">⚠️ Présent</span>' if is_dup else '<span foreground="#27ae60">Nouveau</span>'
            health_markup = '<span foreground="#95a5a6">⚪ Non testé</span>'

            # Store: [checked, name, group_display, country, health_markup, dup_markup, url, is_dup, is_dead, row_id, raw_group]
            self.user_store.append([checked, name, grp, country, health_markup, dup_markup, url, is_dup, False, i, grp])

        self.update_user_count()

    def on_user_check_toggled(self, widget, path):
        it = self.user_store.get_iter(path)
        if it:
            val = self.user_store.get_value(it, 0)
            self.user_store.set_value(it, 0, not val)
            self.update_user_count()

    def set_user_checks(self, val):
        it = self.user_store.get_iter_first()
        while it:
            self.user_store.set_value(it, 0, val)
            it = self.user_store.iter_next(it)
        self.update_user_count()

    def set_user_checks_new_only(self):
        it = self.user_store.get_iter_first()
        while it:
            is_dup = self.user_store.get_value(it, 7)
            is_dead = self.user_store.get_value(it, 8)
            self.user_store.set_value(it, 0, (not is_dup) and (not is_dead))
            it = self.user_store.iter_next(it)
        self.update_user_count()

    def test_user_streams(self):
        items_to_check = []
        it = self.user_store.get_iter_first()
        while it:
            row_id = self.user_store.get_value(it, 9)
            url = self.user_store.get_value(it, 6)
            self.user_store.set_value(it, 4, "<span foreground='#888888'>⏳ Test...</span>")
            items_to_check.append((row_id, url))
            it = self.user_store.iter_next(it)

        self.current_user_check_generation += 1
        gen = self.current_user_check_generation

        def check_worker(item_id, target_url, target_gen):
            is_ok, msg = check_stream_url(target_url)

            def update_ui():
                if target_gen != self.current_user_check_generation:
                    return
                it_find = self.user_store.get_iter_first()
                while it_find:
                    if self.user_store.get_value(it_find, 9) == item_id:
                        if is_ok == "GEOBLOCKED":
                            markup = f"<span foreground='#f57c00'><b>🟠 {msg}</b></span>"
                            self.user_store.set_value(it_find, 4, markup)
                            self.user_store.set_value(it_find, 8, False)
                        elif is_ok:
                            markup = f"<span foreground='#2ecc71'>🟢 {msg}</span>"
                            self.user_store.set_value(it_find, 4, markup)
                            self.user_store.set_value(it_find, 8, False)
                        else:
                            markup = f"<span foreground='#e74c3c'><b>🔴 {msg}</b></span>"
                            self.user_store.set_value(it_find, 4, markup)
                            self.user_store.set_value(it_find, 8, True)
                        break
                    it_find = self.user_store.iter_next(it_find)

            GLib.idle_add(update_ui)

        for item_id, url in items_to_check:
            self.executor.submit(check_worker, item_id, url, gen)

    def update_user_count(self):
        it = self.user_store.get_iter_first()
        checked = 0
        total = 0
        while it:
            total += 1
            if self.user_store.get_value(it, 0):
                checked += 1
            it = self.user_store.iter_next(it)
        self.lbl_user_count.set_text(f"{checked} / {total} station(s) sélectionnée(s)")
        self.update_import_button_sensitivity()


    def on_example_check_toggled(self, widget, path):
        it = self.example_store.get_iter(path)
        if it:
            val = self.example_store.get_value(it, 0)
            self.example_store.set_value(it, 0, not val)
            self.update_example_count()

    def set_example_checks(self, val):
        it = self.example_store.get_iter_first()
        while it:
            self.example_store.set_value(it, 0, val)
            it = self.example_store.iter_next(it)
        self.update_example_count()

    def update_example_count(self):
        it = self.example_store.get_iter_first()
        checked = 0
        total = 0
        while it:
            total += 1
            if self.example_store.get_value(it, 0):
                checked += 1
            it = self.example_store.iter_next(it)
        self.lbl_example_count.set_text(f"{checked} / {total} station(s) sélectionnée(s)")
        self.update_import_button_sensitivity()

def parse_bouquets_xml():
    b_dir = find_bouquets_dir()
    db = {}
    if not b_dir:
        return db

    for xml_file in sorted(glob.glob(os.path.join(b_dir, "*.xml"))):
        try:
            root = safe_parse_xml(xml_file)
            if root is None:
                continue
            code = root.attrib.get("country", os.path.splitext(os.path.basename(xml_file))[0].upper()).upper()
            name = root.attrib.get("name", code)
            flag = root.attrib.get("flag", "")
            display_name = f"{flag} {name}".strip()
            multilingual = root.attrib.get("multilingual", "false").lower() == "true"

            country_data = {
                "name": display_name,
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

    return db

# -----------------------------------------------------------------------------
# Point d'Entrée Principal / Main Entry Point
# -----------------------------------------------------------------------------

def main():
    existing_stations = []
    initial_tab = 0
    initial_file = None

    for arg in sys.argv[1:]:
        if arg.startswith("--tab="):
            tab_val = arg.split("=", 1)[1].strip()
            if tab_val.isdigit():
                initial_tab = int(tab_val)
            elif tab_val in ("import", "user", "file", "mes_fichiers"):
                initial_tab = 3
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

    if not existing_stations and not sys.stdin.isatty():
        try:
            raw = sys.stdin.read().strip()
            if raw:
                data = json.loads(raw)
                if isinstance(data, list): existing_stations = data
        except Exception: pass

    bouquets_db = parse_bouquets_xml()
    if not bouquets_db:
        sys.stderr.write("Aucun bouquet disponible.\n")
        sys.exit(1)

    win = DiscoverRadiosWindow(existing_stations, bouquets_db, initial_tab=initial_tab, initial_file=initial_file)
    win.show_all()
    Gtk.main()

    if win.saved:
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
