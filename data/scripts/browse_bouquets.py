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
    check_stream_url,
    set_window_icon,
    search_radio_browser_api,
    show_group_naming_help_dialog,
    RepairStreamDialog,
    ContributeStationDialog,
    status_markup,
    apply_timonde_app_css,
    setup_window_geometry,
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
import subprocess
import glob
import shutil
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
# Fenêtre Principale : Découverte & Importation de Radios
# Main Window: Discovery & Import of Radios
# -----------------------------------------------------------------------------




def parse_user_radio_file(path):
    """
    Parse universel délégué au moteur natif Rust (Option B pure).
    Prend en charge .m3u, .pls, .csv, .xml, .json avec encodages multiples et inférence de fuseau.
    """
    if not path or not os.path.isfile(path):
        return []
    try:
        res = subprocess.run(
            ["timonde", "--parse-file-json", path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10.0
        )
        if res.returncode == 0 and res.stdout.strip():
            return json.loads(res.stdout)
    except Exception as e:
        sys.stderr.write(f"Erreur parsing fichier {path} via Rust : {e}\n")
    return []

class DiscoverRadiosViews:
    def __init__(
        self,
        existing_stations,
        bouquets_db,
        initial_file=None,
        available_groups=None,
        embedded=True,
        on_import_callback=None,
        on_export_csv_callback=None,
        on_backup_xml_callback=None,
    ):
        self.embedded = embedded
        self.on_import_callback = on_import_callback
        self.on_export_csv_callback = on_export_csv_callback
        self.on_backup_xml_callback = on_backup_xml_callback
        apply_timonde_app_css()

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

    def get_parent_window(self):
        for v in (getattr(self, "view_search", None), getattr(self, "view_bouquets", None), getattr(self, "view_files", None)):
            if v is not None:
                toplevel = v.get_toplevel()
                if isinstance(toplevel, Gtk.Window):
                    return toplevel
        return None

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

        lbl = Gtk.Label(label="<b>" + _("Group:") + "</b>")
        lbl.set_use_markup(True)
        hbox.pack_start(lbl, False, False, 0)

        entry = Gtk.Entry()
        entry.set_text(default_group_name)
        entry.set_width_chars(26)
        entry.set_placeholder_text(_("Ex: /France/Jazz or / for root"))
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
        entry.set_icon_tooltip_text(Gtk.EntryIconPosition.SECONDARY, _("Clear field"))
        def on_clear(e, icon_pos, event):
            if icon_pos == Gtk.EntryIconPosition.SECONDARY:
                e.set_text("")
        entry.connect("icon-press", on_clear)
        hbox.pack_start(entry, True, True, 0)

        btn_choose = make_btn("", "pan-down", _("Choose from existing groups"))
        def on_choose(b):
            menu = Gtk.Menu()
            if view_key == "files":
                it_orig = Gtk.MenuItem(label=_("(Original folder structure)"))
                it_orig.connect("activate", lambda mi: entry.set_text(_("(Original folder structure)")))
                menu.append(it_orig)
                menu.append(Gtk.SeparatorMenuItem())
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

        if view_key == "files":
            entry.connect("changed", lambda e: self.update_files_group_column())

        btn_help = make_btn("", "help-browser", _("Help on groups and subgroups"))
        btn_help.connect("clicked", self.on_show_group_naming_help)
        hbox.pack_start(btn_help, False, False, 0)

        btn_preview = make_btn(_("Listen"), "media-playback-start", _("Listen to selected station"))
        btn_preview.connect("clicked", lambda w: self.on_preview_clicked(view_key))
        self.preview_buttons.append(btn_preview)
        hbox.pack_start(btn_preview, False, False, 0)

        lbl_preview = Gtk.Label(label="")
        lbl_preview.set_use_markup(True)
        lbl_preview.set_halign(Gtk.Align.START)
        self.preview_labels.append(lbl_preview)
        hbox.pack_start(lbl_preview, False, False, 0)

        btn_import = make_btn(_("Import to my favorites"), "list-add")
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
        info_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl_info = Gtk.Label()
        lbl_info.set_markup("<small><i>" + _("Global search on the free and open <b>Radio-Browser</b> directory (+45,000 stations).") + "</i></small>")
        lbl_info.set_xalign(0.0)
        info_box.pack_start(lbl_info, True, True, 0)

        btn_contribute_new = make_btn(_("Contribute a station"), "list-add", _("Submit a new station to community Radio-Browser directory"))
        btn_contribute_new.connect("clicked", lambda w: self.on_contribute_new_to_radio_browser())
        info_box.pack_end(btn_contribute_new, False, False, 0)

        tab_rb.pack_start(info_box, False, False, 0)

        # 2. Ligne 1 : Mots-clés, Genre & Bouton de recherche
        rb_filter_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        tab_rb.pack_start(rb_filter_box, False, False, 0)

        lbl_rb_name = Gtk.Label(label=_("Keyword:"))
        rb_filter_box.pack_start(lbl_rb_name, False, False, 0)

        self.entry_rb_name = Gtk.Entry()
        self.entry_rb_name.set_placeholder_text("Ex: Jazz, Rock, FIP, RMC, BBC...")
        self.entry_rb_name.set_can_focus(True)
        self.entry_rb_name.set_editable(True)
        self.entry_rb_name.connect("activate", lambda w: self.on_search_rb_clicked())
        rb_filter_box.pack_start(self.entry_rb_name, True, True, 0)

        lbl_rb_tag = Gtk.Label(label=_("Genre:"))
        rb_filter_box.pack_start(lbl_rb_tag, False, False, 0)

        self.entry_rb_tag = Gtk.Entry()
        self.entry_rb_tag.set_placeholder_text("Ex: news, classical, ambient...")
        self.entry_rb_tag.set_width_chars(16)
        self.entry_rb_tag.set_can_focus(True)
        self.entry_rb_tag.set_editable(True)
        self.entry_rb_tag.connect("activate", lambda w: self.on_search_rb_clicked())
        rb_filter_box.pack_start(self.entry_rb_tag, False, False, 0)

        btn_rb_search = make_btn(_("Search"), "system-search")
        btn_rb_search.get_style_context().add_class("suggested-action")
        btn_rb_search.connect("clicked", lambda w: self.on_search_rb_clicked())
        rb_filter_box.pack_start(btn_rb_search, False, False, 0)

        # 3. Ligne 2 : Filtres ciblés (Pays explicite et Langue avec autocomplétion)
        rb_geo_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        tab_rb.pack_start(rb_geo_box, False, False, 0)

        self.check_rb_only_country = Gtk.CheckButton(label=_("Filter by country:"))
        self.check_rb_only_country.set_active(True)
        rb_geo_box.pack_start(self.check_rb_only_country, False, False, 0)

        self.entry_rb_country = Gtk.Entry()
        self.entry_rb_country.set_placeholder_text(_("All countries (Worldwide)"))
        self.entry_rb_country.set_width_chars(26)
        self.entry_rb_country.set_can_focus(True)
        self.entry_rb_country.set_editable(True)
        self.entry_rb_country.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, "edit-clear")
        self.entry_rb_country.set_icon_tooltip_text(Gtk.EntryIconPosition.SECONDARY, _("Clear country filter"))
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

        lbl_rb_lang = Gtk.Label(label=_("Language:"))
        rb_geo_box.pack_start(lbl_rb_lang, False, False, 0)

        self.entry_rb_lang = Gtk.Entry()
        self.entry_rb_lang.set_placeholder_text(_("All languages"))
        self.entry_rb_lang.set_width_chars(20)
        self.entry_rb_lang.set_can_focus(True)
        self.entry_rb_lang.set_editable(True)
        self.entry_rb_lang.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, "edit-clear")
        self.entry_rb_lang.set_icon_tooltip_text(Gtk.EntryIconPosition.SECONDARY, _("Clear language filter"))
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
        col_rb_check = Gtk.TreeViewColumn(_("Add"), renderer_rb_check, active=0)
        col_rb_check.set_resizable(False)
        self.rb_tree.append_column(col_rb_check)

        rend_rb_name = Gtk.CellRendererText()
        rend_rb_name.set_property("ellipsize", Pango.EllipsizeMode.END)
        col_rb_name = Gtk.TreeViewColumn(_("Station"), rend_rb_name, text=1)
        col_rb_name.set_expand(True)
        col_rb_name.set_resizable(True)
        col_rb_name.set_min_width(120)
        self.rb_tree.append_column(col_rb_name)

        col_rb_c = Gtk.TreeViewColumn(_("Country"), Gtk.CellRendererText(), text=2)
        col_rb_c.set_resizable(True)
        col_rb_c.set_min_width(45)
        self.rb_tree.append_column(col_rb_c)

        rend_rb_tags = Gtk.CellRendererText()
        rend_rb_tags.set_property("ellipsize", Pango.EllipsizeMode.END)
        col_rb_tags = Gtk.TreeViewColumn(_("Genre / Tags"), rend_rb_tags, text=3)
        col_rb_tags.set_resizable(True)
        col_rb_tags.set_min_width(90)
        self.rb_tree.append_column(col_rb_tags)

        col_rb_codec = Gtk.TreeViewColumn(_("Format & Bitrate"), Gtk.CellRendererText(), text=4)
        col_rb_codec.set_resizable(True)
        col_rb_codec.set_min_width(75)
        self.rb_tree.append_column(col_rb_codec)

        rend_rb_health = Gtk.CellRendererText()
        rend_rb_health.set_property("ellipsize", Pango.EllipsizeMode.END)
        col_rb_health = Gtk.TreeViewColumn(_("Availability"), rend_rb_health, markup=8)
        col_rb_health.set_resizable(True)
        col_rb_health.set_min_width(105)
        self.rb_tree.append_column(col_rb_health)

        col_rb_dup = Gtk.TreeViewColumn(_("Favorite status"), Gtk.CellRendererText(), markup=9)
        col_rb_dup.set_resizable(True)
        col_rb_dup.set_min_width(85)
        self.rb_tree.append_column(col_rb_dup)

        col_rb_votes = Gtk.TreeViewColumn(_("Votes"), Gtk.CellRendererText(), text=5)
        col_rb_votes.set_resizable(True)
        col_rb_votes.set_min_width(45)
        self.rb_tree.append_column(col_rb_votes)

        scroll_rb = Gtk.ScrolledWindow()
        scroll_rb.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll_rb.set_shadow_type(Gtk.ShadowType.IN)
        scroll_rb.add(self.rb_tree)
        tab_rb.pack_start(scroll_rb, True, True, 0)

        # Ligne d'actions sous le tableau
        rb_bot_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        tab_rb.pack_start(rb_bot_box, False, False, 0)

        btn_rb_check_all = make_btn(_("Check all"), "edit-select-all")
        btn_rb_check_all.connect("clicked", lambda w: self.set_rb_checks(True))
        rb_bot_box.pack_start(btn_rb_check_all, False, False, 0)

        btn_rb_uncheck_all = make_btn(_("Uncheck all"), "edit-clear")
        btn_rb_uncheck_all.connect("clicked", lambda w: self.set_rb_checks(False))
        rb_bot_box.pack_start(btn_rb_uncheck_all, False, False, 0)

        self.btn_rb_test = make_btn(_("Test streams"), "network-idle", _("Check live availability of found stations"))
        self.btn_rb_test.connect("clicked", lambda w: self.test_rb_streams())
        rb_bot_box.pack_start(self.btn_rb_test, False, False, 0)

        self.lbl_rb_status = Gtk.Label(label=_("Enter a keyword or click Search to browse the directory."))
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
        lbl_info.set_markup("<small><i>" + _("Official and verified selection across 146 countries and regions (digital DAB+ bouquets and major national stations).") + "</i></small>")
        lbl_info.set_xalign(0.0)
        info_box.pack_start(lbl_info, True, True, 0)
        tab_bouquets.pack_start(info_box, False, False, 0)

        # 2. Barre supérieure : Sélecteur de pays universel (55 langues ISO)
        top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        tab_bouquets.pack_start(top_bar, False, False, 0)

        lbl_country = Gtk.Label(label="<b>" + _("Country:") + "</b>")
        lbl_country.set_use_markup(True)
        top_bar.pack_start(lbl_country, False, False, 0)

        self.combo_country = Gtk.ComboBoxText.new_with_entry()
        self.entry_country = self.combo_country.get_child()
        self.entry_country.set_placeholder_text(_("Type a country (e.g. France, Germany, Canada...)"))
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

        self.radio_national = Gtk.RadioButton.new_with_label(None, _("National Bouquet (Major stations)"))
        self.radio_national.connect("toggled", self.on_scope_changed)
        scope_box.pack_start(self.radio_national, False, False, 0)

        self.radio_region = Gtk.RadioButton.new_with_label_from_widget(self.radio_national, _("Regions & Local:"))
        self.radio_region.connect("toggled", self.on_scope_changed)
        scope_box.pack_start(self.radio_region, False, False, 0)

        self.combo_region = Gtk.ComboBoxText()
        self.combo_region.connect("changed", self.on_region_changed)
        scope_box.pack_start(self.combo_region, False, False, 0)

        self.lbl_lang = Gtk.Label(label="<b>" + _("Language:") + "</b>")
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
        col_check = Gtk.TreeViewColumn(_("Import"), renderer_check, active=0)
        col_check.set_resizable(False)
        self.bouquet_tree.append_column(col_check)

        rend_name = Gtk.CellRendererText()
        rend_name.set_property("ellipsize", Pango.EllipsizeMode.END)
        col_name = Gtk.TreeViewColumn(_("Station"), rend_name, text=1)
        col_name.set_expand(True)
        col_name.set_resizable(True)
        col_name.set_min_width(130)
        self.bouquet_tree.append_column(col_name)

        rend_genre = Gtk.CellRendererText()
        rend_genre.set_property("ellipsize", Pango.EllipsizeMode.END)
        col_genre = Gtk.TreeViewColumn(_("Genre / Topic"), rend_genre, text=2)
        col_genre.set_resizable(True)
        col_genre.set_min_width(110)
        self.bouquet_tree.append_column(col_genre)

        rend_health = Gtk.CellRendererText()
        rend_health.set_property("ellipsize", Pango.EllipsizeMode.END)
        col_health = Gtk.TreeViewColumn(_("Live availability"), rend_health, markup=3)
        col_health.set_resizable(True)
        col_health.set_min_width(115)
        self.bouquet_tree.append_column(col_health)

        rend_dup = Gtk.CellRendererText()
        col_dup = Gtk.TreeViewColumn(_("Favorite status"), rend_dup, markup=4)
        col_dup.set_resizable(True)
        col_dup.set_min_width(90)
        self.bouquet_tree.append_column(col_dup)

        # Bannière informative pour pays sans bouquet DAB+ pré-embarqué (Pont Radio-Browser)
        self.banner_no_bouquet = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.banner_no_bouquet.set_border_width(18)
        self.banner_no_bouquet.set_no_show_all(True)

        self.lbl_no_bouquet = Gtk.Label()
        self.lbl_no_bouquet.set_use_markup(True)
        self.lbl_no_bouquet.set_line_wrap(True)
        self.lbl_no_bouquet.set_justify(Gtk.Justification.CENTER)
        self.banner_no_bouquet.pack_start(self.lbl_no_bouquet, False, False, 0)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_box.set_halign(Gtk.Align.CENTER)
        self.banner_no_bouquet.pack_start(btn_box, False, False, 0)

        self.btn_goto_radio_browser = make_btn(
            _("Explore stations from this country on Radio-Browser"),
            "system-search",
            _("Switch to the global directory with this country pre-selected")
        )
        self.btn_goto_radio_browser.get_style_context().add_class("suggested-action")
        self.btn_goto_radio_browser.connect("clicked", self.on_goto_radio_browser_clicked)
        btn_box.pack_start(self.btn_goto_radio_browser, False, False, 0)

        tab_bouquets.pack_start(self.banner_no_bouquet, True, True, 10)

        self.scroll_b = Gtk.ScrolledWindow()
        self.scroll_b.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.scroll_b.set_shadow_type(Gtk.ShadowType.IN)
        self.scroll_b.add(self.bouquet_tree)
        tab_bouquets.pack_start(self.scroll_b, True, True, 0)

        # Ligne d'actions sous la liste
        self.b_action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        tab_bouquets.pack_start(self.b_action_box, False, False, 0)

        self.btn_bouquet_check_all = make_btn(_("Check all"), "edit-select-all")
        self.btn_bouquet_check_all.connect("clicked", lambda w: self.set_bouquet_checks(True))
        self.b_action_box.pack_start(self.btn_bouquet_check_all, False, False, 0)

        self.btn_bouquet_uncheck_all = make_btn(_("Uncheck all"), "edit-clear")
        self.btn_bouquet_uncheck_all.connect("clicked", lambda w: self.set_bouquet_checks(False))
        self.b_action_box.pack_start(self.btn_bouquet_uncheck_all, False, False, 0)

        self.btn_bouquet_test = make_btn(_("Test streams"), "network-idle", _("Check stations live availability"))
        self.btn_bouquet_test.connect("clicked", lambda w: self.test_bouquet_streams())
        self.b_action_box.pack_start(self.btn_bouquet_test, False, False, 0)

        self.btn_repair = make_btn(_("Repair stream..."), "system-search", _("Replace selected link with an active official stream"))
        self.btn_repair.connect("clicked", self.on_repair_clicked)
        self.b_action_box.pack_start(self.btn_repair, False, False, 0)

        self.btn_bouquet_contribute = make_btn(_("Contribute to Radio-Browser"), "network-server", _("Check and submit selected station to Radio-Browser directory"))
        self.btn_bouquet_contribute.connect("clicked", lambda w: self.on_contribute_bouquet_to_radio_browser())
        self.b_action_box.pack_start(self.btn_bouquet_contribute, False, False, 0)

        self.lbl_bouquet_count = Gtk.Label()
        self.lbl_bouquet_count.set_halign(Gtk.Align.END)
        self.b_action_box.pack_end(self.lbl_bouquet_count, False, False, 0)

        # Barre de groupe et import
        self.bar_box_bouquets, self.entry_group_bouquets, self.btn_import_bouquets = self.create_target_group_bar(
            "bouquets", "Radios Nationales (France)", self.on_import_bouquets
        )
        tab_bouquets.pack_start(self.bar_box_bouquets, False, False, 0)

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
        lbl_ex.set_markup("<b>" + _("Thematic samples:") + "</b>")
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

        btn_refresh_ex = make_btn("", "view-refresh", _("Refresh examples list"))
        btn_refresh_ex.connect("clicked", self.on_refresh_examples_clicked)
        ex_bar.pack_start(btn_refresh_ex, False, False, 0)

        btn_open_ex = make_btn(_("Examples folder"), "folder-open", _("Open ~/.config/timonde/examples"))
        btn_open_ex.connect("clicked", self.on_open_examples_folder)
        ex_bar.pack_start(btn_open_ex, False, False, 0)

        btn_restore_ex = make_btn(_("Restore samples"), "edit-undo", _("Restore the 19 original samples"))
        btn_restore_ex.connect("clicked", self.on_restore_examples_action)
        ex_bar.pack_start(btn_restore_ex, False, False, 0)

        # 2. Rangée inférieure : Fichier personnel / externe & Outils (À la ligne)
        ext_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.pack_start(ext_bar, False, False, 0)

        lbl_custom = Gtk.Label()
        lbl_custom.set_markup("<b>" + _("External file:") + "</b>")
        lbl_custom.set_halign(Gtk.Align.START)
        ext_bar.pack_start(lbl_custom, False, False, 0)

        btn_browse = make_btn(_("Load a file..."), "document-open", _("Load an XML, CSV, JSON, M3U or PLS file"))
        btn_browse.connect("clicked", self.on_files_browse_clicked)
        ext_bar.pack_start(btn_browse, False, False, 0)

        self.btn_files_reload = make_btn(_("Reload"), "view-refresh", _("Reload currently displayed file"))
        self.btn_files_reload.set_sensitive(False)
        self.btn_files_reload.connect("clicked", lambda w: self.load_file_into_store(self.current_file_path) if self.current_file_path else None)
        ext_bar.pack_start(self.btn_files_reload, False, False, 0)

        btn_csv = make_btn(_("Export to spreadsheet (CSV)..."), "x-office-spreadsheet", _("Generate a flat list for Calc or Excel spreadsheet"))
        btn_csv.connect("clicked", self.on_export_csv_action)
        ext_bar.pack_end(btn_csv, False, False, 0)

        btn_backup = make_btn(_("Backup my radios (XML)..."), "document-save", _("Create a full backup of your collection (with folders and timezones)"))
        btn_backup.connect("clicked", self.on_backup_xml_action)
        ext_bar.pack_end(btn_backup, False, False, 0)

        btn_open_bm = make_btn(_("Bookmarks folder"), "folder", _("Open ~/.config/timonde"))
        btn_open_bm.connect("clicked", lambda w: self.open_directory(os.path.expanduser("~/.config/timonde")))
        ext_bar.pack_end(btn_open_bm, False, False, 0)

        # 3. Label d'information sur la source
        self.lbl_files_info = Gtk.Label(label=_("<i>Select a file or sample above.</i>"))
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
        col_f_check = Gtk.TreeViewColumn(_("Import"), renderer_f_check, active=0)
        col_f_check.set_resizable(False)
        self.files_tree.append_column(col_f_check)

        rend_f_name = Gtk.CellRendererText()
        rend_f_name.set_property("ellipsize", Pango.EllipsizeMode.END)
        col_f_name = Gtk.TreeViewColumn(_("Station"), rend_f_name, text=1)
        col_f_name.set_expand(True)
        col_f_name.set_resizable(True)
        col_f_name.set_min_width(120)
        self.files_tree.append_column(col_f_name)

        rend_f_grp = Gtk.CellRendererText()
        rend_f_grp.set_property("ellipsize", Pango.EllipsizeMode.END)
        col_f_grp = Gtk.TreeViewColumn(_("Folder / Group"), rend_f_grp, text=2)
        col_f_grp.set_resizable(True)
        col_f_grp.set_min_width(90)
        self.files_tree.append_column(col_f_grp)

        col_f_country = Gtk.TreeViewColumn(_("Country"), Gtk.CellRendererText(), text=3)
        col_f_country.set_resizable(True)
        col_f_country.set_min_width(45)
        self.files_tree.append_column(col_f_country)

        rend_f_health = Gtk.CellRendererText()
        rend_f_health.set_property("ellipsize", Pango.EllipsizeMode.END)
        col_f_health = Gtk.TreeViewColumn(_("Availability"), rend_f_health, markup=4)
        col_f_health.set_resizable(True)
        col_f_health.set_min_width(105)
        self.files_tree.append_column(col_f_health)

        col_f_dup = Gtk.TreeViewColumn(_("Favorite status"), Gtk.CellRendererText(), markup=5)
        col_f_dup.set_resizable(True)
        col_f_dup.set_min_width(85)
        self.files_tree.append_column(col_f_dup)

        rend_f_url = Gtk.CellRendererText()
        rend_f_url.set_property("ellipsize", Pango.EllipsizeMode.END)
        col_f_url = Gtk.TreeViewColumn(_("Stream URL"), rend_f_url, text=6)
        col_f_url.set_resizable(True)
        col_f_url.set_min_width(110)
        self.files_tree.append_column(col_f_url)

        scroll_files = Gtk.ScrolledWindow()
        scroll_files.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll_files.set_shadow_type(Gtk.ShadowType.IN)
        scroll_files.add(self.files_tree)
        box.pack_start(scroll_files, True, True, 0)

        # Ligne d'actions sous le tableau
        f_action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.pack_start(f_action_box, False, False, 0)

        btn_f_check_all = make_btn(_("Check all"), "edit-select-all")
        btn_f_check_all.connect("clicked", lambda w: self.set_files_checks(True))
        f_action_box.pack_start(btn_f_check_all, False, False, 0)

        btn_f_uncheck_all = make_btn(_("Uncheck all"), "edit-clear")
        btn_f_uncheck_all.connect("clicked", lambda w: self.set_files_checks(False))
        f_action_box.pack_start(btn_f_uncheck_all, False, False, 0)

        btn_f_new_only = make_btn(_("New only"), "list-add")
        btn_f_new_only.connect("clicked", lambda w: self.set_files_checks_new_only())
        f_action_box.pack_start(btn_f_new_only, False, False, 0)

        self.btn_files_test = make_btn(_("Test streams"), "network-idle", _("Check links availability live"))
        self.btn_files_test.connect("clicked", lambda w: self.test_files_streams())
        f_action_box.pack_start(self.btn_files_test, False, False, 0)

        self.btn_files_contribute = make_btn(_("Contribute to Radio-Browser"), "network-server", _("Check and submit selected station to Radio-Browser directory"))
        self.btn_files_contribute.connect("clicked", lambda w: self.on_contribute_files_to_radio_browser())
        f_action_box.pack_start(self.btn_files_contribute, False, False, 0)

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

        self.stack.add_titled(self.view_search, "search", _("Search online"))
        self.stack.add_titled(self.view_bouquets, "bouquets", _("Country bouquets"))
        self.stack.add_titled(self.view_files, "files", _("Import & Export"))

        self.stack.connect("notify::visible-child-name", lambda s, p: self.preview_player.stop() if self.preview_player else None)

        bot_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        main_vbox.pack_start(bot_box, False, False, 0)

        btn_close = make_btn(_("Close"), "window-close")
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
        self.show_preview_message(_("Select a station in table to listen to."))

    def toggle_preview_station(self, name, url):
        if not url:
            self.show_preview_message(_("Select a station to listen to."))
            return
        clean = clean_stream_url(url)
        if self.preview_player.is_playing and self.preview_player.current_url == clean:
            self.preview_player.stop()
        else:
            self.preview_player.play(name, clean)

    def on_preview_status_update(self, is_playing, url, message, is_error):
        for btn in self.preview_buttons:
            if is_playing:
                update_btn_content(btn, _("Stop"), "media-playback-stop")
            else:
                update_btn_content(btn, _("Listen"), "media-playback-start")

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

    def on_goto_radio_browser_clicked(self, widget):
        c_code = self.get_selected_country_code()
        c_info = self.bouquets_db.get(c_code, {})
        c_name = c_info.get("country_name") or c_info.get("name", c_code).split("  [")[0]

        # Configurer l'onglet Recherche (Radio-Browser)
        if hasattr(self, "check_rb_only_country"):
            self.check_rb_only_country.set_active(True)
        if hasattr(self, "entry_rb_country"):
            self.entry_rb_country.set_sensitive(True)
            self.entry_rb_country.set_text(c_name)
        if hasattr(self, "entry_rb_name"):
            self.entry_rb_name.set_text("")
        if hasattr(self, "entry_rb_tag"):
            self.entry_rb_tag.set_text("")

        # Basculer vers l'onglet Recherche
        if hasattr(self, "stack") and self.stack:
            self.stack.set_visible_child_name("search")

        # Déclencher la recherche
        GLib.idle_add(self.on_search_rb_clicked)

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

    def _run_batch_checks(self, store, items_to_check, id_col, health_col, broken_col=None, checked_col=None, gen_attr="current_check_generation", on_update=None):
        """Vérifie un lot d'URLs de manière asynchrone et met à jour le GtkListStore cible."""
        gen = getattr(self, gen_attr, 0)

        def check_worker(item_id, target_url, target_gen):
            is_ok, msg = check_stream_url(target_url)

            def update_ui():
                if target_gen != getattr(self, gen_attr, 0):
                    return
                it = store.get_iter_first()
                while it:
                    if store.get_value(it, id_col) == item_id:
                        if is_ok in ("GEO", "GEOBLOCKED"):
                            markup = status_markup(f"● {msg}", kind="geo", bold=True)
                            store.set_value(it, health_col, markup)
                            if broken_col is not None:
                                store.set_value(it, broken_col, False)
                        elif is_ok:
                            markup = status_markup(msg, kind="ok", with_bullet=True)
                            store.set_value(it, health_col, markup)
                            if broken_col is not None:
                                store.set_value(it, broken_col, False)
                        else:
                            markup = status_markup(f"● {msg}", kind="error", bold=True)
                            store.set_value(it, health_col, markup)
                            if broken_col is not None:
                                store.set_value(it, broken_col, True)
                            if checked_col is not None:
                                store.set_value(it, checked_col, False)
                        break
                    it = store.iter_next(it)
                if on_update:
                    on_update()

            GLib.idle_add(update_ui)

        for item_id, url in items_to_check:
            self.executor.submit(check_worker, item_id, url, gen)

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
            nat_prefix = _("National Radios")
            if info.get("multilingual", False):
                lang_text = self.combo_lang.get_active_text() or ""
                lang_short = lang_text.split()[0] if lang_text else ""
                default_group = f"{nat_prefix} ({country_name} - {lang_short})"
            else:
                default_group = f"{nat_prefix} ({country_name})"

        if hasattr(self, "entry_group_bouquets"):
            self.entry_group_bouquets.set_text(default_group)

        has_bouquet = info.get("has_bouquet", False) and bool(stations)
        if hasattr(self, "banner_no_bouquet"):
            if not has_bouquet:
                self.banner_no_bouquet.show()
                country_label = info.get("country_name") or info.get("name", country_id).split("  [")[0]
                self.lbl_no_bouquet.set_markup(
                    f"<span size='large'><b>{_('No pre-loaded DAB+ bouquet for this country.')}</b></span>\n\n"
                    f"{_('You can explore and import stations for this territory directly from the global directory.')}"
                )
                btn_txt = _("Explore stations from {country} on Radio-Browser ➔").format(country=country_label)
                update_btn_content(self.btn_goto_radio_browser, btn_txt, "system-search")
                if hasattr(self, "scroll_b"):
                    self.scroll_b.hide()
                if hasattr(self, "b_action_box"):
                    self.b_action_box.hide()
                if hasattr(self, "bar_box_bouquets"):
                    self.bar_box_bouquets.hide()
            else:
                self.banner_no_bouquet.hide()
                if hasattr(self, "scroll_b"):
                    self.scroll_b.show()
                if hasattr(self, "b_action_box"):
                    self.b_action_box.show()
                if hasattr(self, "bar_box_bouquets"):
                    self.bar_box_bouquets.show()

        self.bouquet_store.clear()
        self.current_check_generation += 1

        items_to_check = []
        for i, (name, url, genre) in enumerate(stations):
            clean_url = url.strip()
            clean_name = name.strip().lower()

            is_dup = (clean_url in self.existing_urls) or (clean_name in self.existing_names)
            checked = False
            status_note = status_markup(_("(Already in favorites)"), kind="muted") if is_dup else status_markup(_("New"), kind="ok", bold=True)
            health_note = status_markup(_("Checking..."), kind="muted")

            self.bouquet_store.append([checked, name, genre, health_note, status_note, clean_url, is_dup, False, i])
            items_to_check.append((i, clean_url))

        self.update_bouquet_count()
        self._run_batch_checks(
            store=self.bouquet_store,
            items_to_check=items_to_check,
            id_col=8,
            health_col=3,
            broken_col=7,
            checked_col=0,
            gen_attr="current_check_generation",
            on_update=self.update_bouquet_count,
        )

    def test_bouquet_streams(self):
        items_to_check = []
        it = self.bouquet_store.get_iter_first()
        while it:
            row_id = self.bouquet_store.get_value(it, 8)
            url = self.bouquet_store.get_value(it, 5)
            self.bouquet_store.set_value(it, 3, status_markup(_("Testing..."), kind="muted"))
            items_to_check.append((row_id, url))
            it = self.bouquet_store.iter_next(it)

        self.current_check_generation += 1
        self._run_batch_checks(
            store=self.bouquet_store,
            items_to_check=items_to_check,
            id_col=8,
            health_col=3,
            broken_col=7,
            checked_col=0,
            gen_attr="current_check_generation",
            on_update=self.update_bouquet_count,
        )

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
            c_name = self.bouquets_db.get(c_code, {}).get("country_name", c_code or _("this country"))
            msg = _("No DAB+ bouquet for {country} — Use 'Search online'.").format(country=html.escape(c_name))
            self.lbl_bouquet_count.set_markup(f"<span color='#888888'><i>{msg}</i></span>")
            self.btn_bouquet_check_all.set_sensitive(False)
            self.btn_bouquet_uncheck_all.set_sensitive(False)
            self.btn_repair.set_sensitive(False)
        else:
            self.lbl_bouquet_count.set_text(
                _("{checked} / {total} station(s) selected").format(checked=checked, total=total)
            )
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

        dlg = RepairStreamDialog(self.get_parent_window(), station_name, current_url, country_id)

        def on_repair_resp(d, res):
            new_url = d.get_chosen_url()
            d.destroy()
            if res == Gtk.ResponseType.OK and new_url:
                clean_new_url = new_url.strip()
                model.set_value(tree_iter, 5, clean_new_url)
                repaired_lbl = _("● Repaired (Live)")
                model.set_value(tree_iter, 3, f"<span color='#2e7d32'><b>{repaired_lbl}</b></span>")
                model.set_value(tree_iter, 7, False)
                model.set_value(tree_iter, 0, True)
                self.update_bouquet_count()
                self.save_stream_to_xml(station_name, current_url, clean_new_url)

        dlg.connect("response", on_repair_resp)
        dlg.show_all()

    def on_contribute_new_to_radio_browser(self):
        c_code = self.get_selected_country_code() if hasattr(self, "get_selected_country_code") else ""
        dlg = ContributeStationDialog(
            parent=self.get_parent_window(),
            station_name=self.entry_rb_name.get_text().strip() if hasattr(self, "entry_rb_name") else "",
            current_url="",
            country_code=c_code
        )
        dlg.connect("response", lambda d, r: d.destroy())
        dlg.show_all()

    def on_contribute_bouquet_to_radio_browser(self):
        model, tree_iter = self.bouquet_tree.get_selection().get_selected()
        if not tree_iter:
            d = Gtk.MessageDialog(
                transient_for=self.get_parent_window(),
                flags=Gtk.DialogFlags.MODAL,
                type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.OK,
                message_format=_("Please select a radio station in the list first.")
            )
            d.connect("response", lambda dialog, r: dialog.destroy())
            d.show_all()
            return
        station_name = model.get_value(tree_iter, 1) or ""
        current_url = model.get_value(tree_iter, 5) or ""
        country_id = self.get_selected_country_code()
        dlg = ContributeStationDialog(
            parent=self.get_parent_window(),
            station_name=station_name,
            current_url=current_url,
            country_code=country_id
        )
        dlg.connect("response", lambda d, r: d.destroy())
        dlg.show_all()

    def on_contribute_files_to_radio_browser(self):
        model, tree_iter = self.files_tree.get_selection().get_selected()
        station_name = ""
        current_url = ""
        country_id = ""
        if tree_iter:
            station_name = model.get_value(tree_iter, 1) or ""
            country_id = model.get_value(tree_iter, 3) or ""
            current_url = model.get_value(tree_iter, 6) or ""
        else:
            # Si aucune sélection active, prendre la première station cochée
            it = model.get_iter_first()
            while it:
                if model.get_value(it, 0):
                    station_name = model.get_value(it, 1) or ""
                    country_id = model.get_value(it, 3) or ""
                    current_url = model.get_value(it, 6) or ""
                    break
                it = model.iter_next(it)

        if not current_url:
            d = Gtk.MessageDialog(
                transient_for=self.get_parent_window(),
                flags=Gtk.DialogFlags.MODAL,
                type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.OK,
                message_format=_("Please select or check a radio station in the list first.")
            )
            d.connect("response", lambda dialog, r: dialog.destroy())
            d.show_all()
            return

        dlg = ContributeStationDialog(
            parent=self.get_parent_window(),
            station_name=station_name,
            current_url=current_url,
            country_code=country_id
        )
        dlg.connect("response", lambda d, r: d.destroy())
        dlg.show_all()

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
                tmp_file = f"{target_file}.tmp"
                tree.write(tmp_file, encoding="utf-8", xml_declaration=True)
                os.replace(tmp_file, target_file)
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

        self.lbl_rb_status.set_text(_("Searching Radio-Browser..."))
        self.rb_store.clear()

        def worker():
            results = search_radio_browser_api(name=query, country_code=country_code, tag=tag, language=lang, limit=40)

            def on_done():
                if not results:
                    if country_code and lang:
                        c_name = self.bouquets_db.get(country_code, {}).get("country_name", country_code)
                        self.lbl_rb_status.set_text(_("No radio found for this language in {country}. Uncheck 'Filter by country' or clear the language.").format(country=c_name))
                    elif country_code:
                        c_name = self.bouquets_db.get(country_code, {}).get("country_name", country_code)
                        self.lbl_rb_status.set_text(_("No radio found for these criteria in {country}. Uncheck 'Filter by country' to search globally.").format(country=c_name))
                    else:
                        self.lbl_rb_status.set_text(_("No radio found on Radio-Browser for these criteria."))
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
                    dup_tag = _("[Present]") if is_dup else _("[New]")
                    dup_markup = status_markup(dup_tag, kind="warn" if is_dup else "new")
                    health_markup = status_markup(f"○ {_('Untested')}", kind="untested")
                    self.rb_store.append([False, name, c_code, tags[:30], codec_str, votes, url, is_dup, health_markup, dup_markup, i])

                self.lbl_rb_status.set_text(_("{count} stations found.").format(count=len(results)))
                self.update_rb_count()

            GLib.idle_add(on_done)

        self.executor.submit(worker)

    def test_rb_streams(self):
        items_to_check = []
        it = self.rb_store.get_iter_first()
        while it:
            row_id = self.rb_store.get_value(it, 10)
            url = self.rb_store.get_value(it, 6)
            self.rb_store.set_value(it, 8, status_markup(_("Testing..."), kind="muted"))
            items_to_check.append((row_id, url))
            it = self.rb_store.iter_next(it)

        self.current_rb_check_generation += 1
        self._run_batch_checks(
            store=self.rb_store,
            items_to_check=items_to_check,
            id_col=10,
            health_col=8,
            broken_col=None,
            checked_col=0,
            gen_attr="current_rb_check_generation",
            on_update=self.update_rb_count,
        )

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
            title=_("Choose a radio station file"),
            transient_for=self.get_parent_window(),
            action=Gtk.FileChooserAction.OPEN,
        )
        chooser.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        chooser.add_button(_("Open"), Gtk.ResponseType.OK)

        filter_all = Gtk.FileFilter()
        filter_all.set_name("Tous fichiers supportés (*.xml, *.csv, *.json, *.m3u, *.pls)")
        filter_all.add_pattern("*.xml")
        filter_all.add_pattern("*.csv")
        filter_all.add_pattern("*.json")
        filter_all.add_pattern("*.m3u")
        filter_all.add_pattern("*.m3u8")
        filter_all.add_pattern("*.pls")
        chooser.add_filter(filter_all)

        def on_chooser_resp(dlg, res):
            filename = dlg.get_filename()
            dlg.destroy()
            if res == Gtk.ResponseType.OK and filename:
                self.load_file_into_store(filename)

        chooser.connect("response", on_chooser_resp)
        chooser.show_all()

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

    def update_files_group_column(self):
        if not hasattr(self, "entry_group_files") or not hasattr(self, "files_store"):
            return
        raw_text = self.entry_group_files.get_text().strip()
        is_orig = raw_text in (
            _("(Original folder structure)"),
            "(Original folder structure)",
            "(Dossiers d'origine du fichier)",
            "(Groupes préservés du fichier)",
        )

        if is_orig:
            target_display = None
        else:
            norm = normalize_group_path(raw_text, return_root_literal=True)
            if norm in ("[ / ] (Racine — Sans groupe)", "/", "root", "(Racine)", ""):
                target_display = "[ / ] (Racine)"
            else:
                target_display = norm

        it = self.files_store.get_iter_first()
        while it:
            if is_orig:
                raw_grp = self.files_store.get_value(it, 10) or "[ / ] (Racine)"
                self.files_store.set_value(it, 2, raw_grp)
            else:
                self.files_store.set_value(it, 2, target_display)
            it = self.files_store.iter_next(it)

    def load_file_into_store(self, path):
        if not path or not os.path.isfile(path):
            return

        self.current_file_path = path
        self.btn_files_reload.set_sensitive(True)
        base_name = os.path.splitext(os.path.basename(path))[0]

        stations = parse_user_radio_file(path)
        self.current_file_stations = stations
        groups = set(s.get("group", "") for s in stations if s.get("group"))

        info_text = f"<b>{_("File:")}</b> {os.path.basename(path)} — <b>{len(stations)}</b> station(s)"
        if groups:
            info_text += f", <b>{len(groups)}</b> groupe(s)"
        self.lbl_files_info.set_markup(info_text)

        if hasattr(self, "entry_group_files"):
            if len(groups) > 1:
                self.entry_group_files.set_text(_("(Original folder structure)"))
            elif len(groups) == 1:
                self.entry_group_files.set_text(next(iter(groups)))
            else:
                self.entry_group_files.set_text(f"Import {base_name}")

        self.files_store.clear()
        self.current_files_check_generation += 1

        for i, st in enumerate(stations):
            name = st.get("name", "Station")
            url = st.get("url", "").strip()
            grp = st.get("group", "").strip() or base_name
            country = st.get("country", "").strip().upper()

            is_dup = (url in self.existing_urls) or (name.strip().lower() in self.existing_names)
            checked = False
            dup_tag = _("[Present]") if is_dup else _("[New]")
            dup_markup = status_markup(dup_tag, kind="warn" if is_dup else "new")
            health_markup = status_markup(f"○ {_('Untested')}", kind="untested")

            # Store: [checked, name, group_display, country, health_markup, dup_markup, url, is_dup, is_dead, row_id, raw_group]
            self.files_store.append([checked, name, grp, country, health_markup, dup_markup, url, is_dup, False, i, grp])

        self.update_files_group_column()
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
            self.files_store.set_value(it, 4, status_markup(_("Testing..."), kind="muted"))
            items_to_check.append((row_id, url))
            it = self.files_store.iter_next(it)

        self.current_files_check_generation += 1
        self._run_batch_checks(
            store=self.files_store,
            items_to_check=items_to_check,
            id_col=9,
            health_col=4,
            broken_col=8,
            checked_col=0,
            gen_attr="current_files_check_generation",
            on_update=self.update_files_count,
        )

    def update_files_count(self):
        checked = 0
        total = 0
        it = self.files_store.get_iter_first()
        while it:
            total += 1
            if self.files_store.get_value(it, 0):
                checked += 1
            it = self.files_store.iter_next(it)
        self.lbl_files_count.set_text(
            _("{checked} / {total} station(s) selected").format(checked=checked, total=total)
        )
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
        is_original = raw_grp in (
            _("(Original folder structure)"),
            "(Original folder structure)",
            "(Dossiers d'origine du fichier)",
            "(Groupes préservés du fichier)",
        )

        if is_original:
            group_name = "root"
        else:
            group_name = normalize_group_path(raw_grp, return_root_literal=True)
            if group_name in ("[ / ] (Racine — Sans groupe)", "/", "root", "(Racine)", ""):
                group_name = "root"

        selected = []
        it = self.files_store.get_iter_first()
        while it:
            if self.files_store.get_value(it, 0):
                name = self.files_store.get_value(it, 1)
                url = self.files_store.get_value(it, 6)
                st_group_raw = self.files_store.get_value(it, 10)
                st_country = self.files_store.get_value(it, 3) or ""

                if is_original and st_group_raw:
                    clean_orig = st_group_raw.strip()
                    if clean_orig in ("[ / ] (Racine — Sans groupe)", "/", "root", "(Racine)"):
                        target_st_grp = "root"
                    else:
                        target_st_grp = clean_orig.strip("/").strip()
                else:
                    target_st_grp = group_name

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

        self.finalize_import(selected, group_name if not is_original else "root", None)

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
            parent = self.get_parent_window()
            if parent:
                parent.destroy()
            else:
                self.shutdown()

    def on_show_group_naming_help(self, widget):
        show_group_naming_help_dialog(self.get_parent_window())

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
        self.show_preview_message(f"{restored} {_("sample files restored.")}")

    def on_export_csv_action(self, widget):
        if self.on_export_csv_callback:
            self.on_export_csv_callback()
        else:
            self.show_preview_message(_("CSV export is available from settings."))

    def on_backup_xml_action(self, widget):
        if self.on_backup_xml_callback:
            self.on_backup_xml_callback()
        else:
            self.show_preview_message(_("XML backup is available from settings."))

    def shutdown(self):
        if hasattr(self, "preview_player") and self.preview_player:
            self.preview_player.stop()
        try:
            self.executor.shutdown(wait=False)
        except Exception:
            pass


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
        apply_timonde_app_css()
        if embedded:
            super().__init__()
            self.views = DiscoverRadiosViews(
                existing_stations=existing_stations,
                bouquets_db=bouquets_db,
                initial_file=initial_file,
                available_groups=available_groups,
                embedded=True,
                on_import_callback=on_import_callback,
                on_export_csv_callback=on_export_csv_callback,
                on_backup_xml_callback=on_backup_xml_callback,
            )
            self.view_search = self.views.view_search
            self.view_bouquets = self.views.view_bouquets
            self.view_files = self.views.view_files
            return

        super().__init__(title=_("Discover & Import stations (TiMonde)"))
        setup_window_geometry(self, base_width=960, base_height=640, min_width=750, min_height=480)
        self.set_border_width(10)

        set_window_icon(self)
        self.connect("destroy", self.on_destroy)
        self.set_focus_on_map(True)

        self.views = DiscoverRadiosViews(
            existing_stations=existing_stations,
            bouquets_db=bouquets_db,
            initial_file=initial_file,
            available_groups=available_groups,
            embedded=False,
            on_import_callback=on_import_callback,
            on_export_csv_callback=on_export_csv_callback,
            on_backup_xml_callback=on_backup_xml_callback,
        )
        self.view_search = self.views.view_search
        self.view_bouquets = self.views.view_bouquets
        self.view_files = self.views.view_files

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

        self.stack.add_titled(self.view_search, "search", _("Search online"))
        self.stack.add_titled(self.view_bouquets, "bouquets", _("Country bouquets"))
        self.stack.add_titled(self.view_files, "files", _("Import & Export"))

        self.stack.connect("notify::visible-child-name", lambda s, p: self.views.preview_player.stop() if hasattr(self.views, "preview_player") and self.views.preview_player else None)

        bot_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        main_vbox.pack_start(bot_box, False, False, 0)

        btn_close = make_btn(_("Close"), "window-close")
        btn_close.connect("clicked", lambda w: self.destroy())
        bot_box.pack_end(btn_close, False, False, 0)

        pages = ["search", "bouquets", "files"]
        target = pages[initial_tab] if 0 <= initial_tab < len(pages) else "search"
        self.stack.set_visible_child_name(target)

    def on_destroy(self, widget):
        if hasattr(self, "views") and self.views:
            self.views.shutdown()
        Gtk.main_quit()

    def __getattr__(self, name):
        return getattr(self.views, name)



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
