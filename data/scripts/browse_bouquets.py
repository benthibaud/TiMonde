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
    COUNTRIES_DB,
    COUNTRIES_REGISTRY,
    normalize_lookup,
    resolve_country_code,
    set_container_margins,
    attach_country_completion,
    GroupSelectorBar,
    RADIO_BROWSER_LANGUAGES,
    NATIVE_LANGUAGE_NAMES,
    DISPLAY_NATIVE_MAP,
    resolve_language_api_key,
    run_timonde_cli,
)

import json
import html
import glob
import shutil
import re
from concurrent.futures import ThreadPoolExecutor

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, Pango

USER_CONFIG_EXAMPLES_DIR = os.path.expanduser("~/.config/timonde/examples")

EXAMPLES_CANDIDATES = [
    USER_CONFIG_EXAMPLES_DIR,
    os.path.expanduser("~/.local/share/timonde/examples"),
    os.path.join(os.path.dirname(__file__), "..", "examples"),
    "/usr/share/timonde/examples",
    "data/examples",
]


def ensure_user_examples_dir(force_restore=False):
    """Initialise ou restaure le dossier ~/.config/timonde/examples avec les exemples par défaut."""
    copied = 0
    try:
        os.makedirs(USER_CONFIG_EXAMPLES_DIR, exist_ok=True)
        patterns = ["*.xml", "*.csv", "*.json", "*.m3u", "*.m3u8", "*.pls"]
        existing = [f for pat in patterns for f in glob.glob(os.path.join(USER_CONFIG_EXAMPLES_DIR, pat))]
        if force_restore or not existing:
            for sdir in EXAMPLES_CANDIDATES[1:]:
                if os.path.isdir(sdir):
                    for fname in os.listdir(sdir):
                        if fname.endswith(('.xml', '.csv', '.json', '.m3u', '.m3u8', '.pls', '.md')):
                            src_file = os.path.join(sdir, fname)
                            dst_file = os.path.join(USER_CONFIG_EXAMPLES_DIR, fname)
                            if os.path.isfile(src_file) and (force_restore or not os.path.exists(dst_file)):
                                shutil.copy2(src_file, dst_file)
                                copied += 1
                    if copied > 0:
                        break
    except Exception as e:
        sys.stderr.write(f"Avertissement initialisation {USER_CONFIG_EXAMPLES_DIR}: {e}\n")
    return (USER_CONFIG_EXAMPLES_DIR, copied) if force_restore else USER_CONFIG_EXAMPLES_DIR


def list_available_examples():
    """Liste tous les fichiers exemples disponibles (XML, CSV, JSON, M3U) en priorité depuis ~/.config/timonde/examples"""
    ensure_user_examples_dir()
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
    ext_labels = {
        ".csv": ("[Tableur CSV]", "Import CSV"),
        ".json": ("[Radiotray-NG JSON]", "Import JSON"),
        ".m3u": ("[Playlist M3U]", "Playlist M3U"),
        ".m3u8": ("[Playlist M3U]", "Playlist M3U"),
        ".pls": ("[Playlist PLS]", "Playlist PLS"),
    }
    for base in sorted(found_files.keys()):
        f = found_files[base]
        ext = os.path.splitext(f)[1].lower()
        if ext == ".xml":
            display_label, name = base, base
            try:
                with open(f, "r", encoding="utf-8", errors="replace") as xf:
                    head = xf.read(1024)
                m = re.search(r'<(?:bouquet|bookmarks|group)\b[^>]*\b(?:name|title)=["\']([^"\']+)["\']', head)
                if m and m.group(1).strip() and m.group(1).strip() != base:
                    name = m.group(1).strip()
                    display_label = f"{base}  —  {name}"
            except Exception:
                pass
            results.append((f, display_label, name))
        elif ext in ext_labels:
            tag, title = ext_labels[ext]
            results.append((f, f"{base}  —  {tag}", title))
    return results


def parse_user_radio_file(path):
    """Parse universel délégué au moteur natif Rust (.m3u, .pls, .csv, .xml, .json)."""
    if not path or not os.path.isfile(path):
        return []
    try:
        res = run_timonde_cli("--parse-file-json", path, timeout=10.0)
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
        return attach_country_completion(entry, on_selected=on_selected_cb)

    def _add_toggle_col(self, tree, title, col_idx, on_toggled):
        rend = Gtk.CellRendererToggle()
        rend.connect("toggled", on_toggled)
        col = Gtk.TreeViewColumn(title, rend, active=col_idx)
        col.set_resizable(False)
        tree.append_column(col)

    def _add_text_col(self, tree, title, col_idx, markup=False, ellipsize=False, expand=False, min_w=0):
        rend = Gtk.CellRendererText()
        if ellipsize:
            rend.set_property("ellipsize", Pango.EllipsizeMode.END)
        col = Gtk.TreeViewColumn(title, rend, **({"markup": col_idx} if markup else {"text": col_idx}))
        col.set_resizable(True)
        if expand:
            col.set_expand(True)
        if min_w:
            col.set_min_width(min_w)
        tree.append_column(col)

    # -------------------------------------------------------------------------
    # Helper Partagé : Barre inférieure de groupe de destination & import
    # -------------------------------------------------------------------------
    def create_target_group_bar(self, view_key, default_group_name, on_import_func):
        allow_orig = (view_key == "files")
        on_ch = (lambda e: self.update_files_group_column()) if allow_orig else None
        vbox = GroupSelectorBar.create(
            available_groups=self.available_groups,
            default_group=default_group_name,
            allow_original_structure=allow_orig,
            on_help_clicked=self.on_show_group_naming_help,
            on_changed=on_ch,
        )
        entry = vbox.entry
        hbox = vbox.get_children()[0]

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
        set_container_margins(tab_rb, margin=8)

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

        self._add_toggle_col(self.rb_tree, _("Add"), 0, self.on_rb_check_toggled)
        self._add_text_col(self.rb_tree, _("Station"), 1, ellipsize=True, expand=True, min_w=120)
        self._add_text_col(self.rb_tree, _("Country"), 2, min_w=45)
        self._add_text_col(self.rb_tree, _("Genre / Tags"), 3, ellipsize=True, min_w=90)
        self._add_text_col(self.rb_tree, _("Format & Bitrate"), 4, min_w=75)
        self._add_text_col(self.rb_tree, _("Availability"), 8, markup=True, ellipsize=True, min_w=105)
        self._add_text_col(self.rb_tree, _("Favorite status"), 9, markup=True, min_w=85)
        self._add_text_col(self.rb_tree, _("Votes"), 5, min_w=45)

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
        set_container_margins(tab_bouquets, margin=8)

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

        self._add_toggle_col(self.bouquet_tree, _("Import"), 0, self.on_bouquet_check_toggled)
        self._add_text_col(self.bouquet_tree, _("Station"), 1, ellipsize=True, expand=True, min_w=130)
        self._add_text_col(self.bouquet_tree, _("Genre / Topic"), 2, ellipsize=True, min_w=110)
        self._add_text_col(self.bouquet_tree, _("Live availability"), 3, markup=True, ellipsize=True, min_w=115)
        self._add_text_col(self.bouquet_tree, _("Favorite status"), 4, markup=True, min_w=90)

        # Bannière informative pour pays sans bouquet DAB+ pré-embarqué (Pont Radio-Browser)
        self.banner_no_bouquet = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        set_container_margins(self.banner_no_bouquet, margin=18)
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
        set_container_margins(box, margin=8)

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

        self._add_toggle_col(self.files_tree, _("Import"), 0, self.on_files_check_toggled)
        self._add_text_col(self.files_tree, _("Station"), 1, ellipsize=True, expand=True, min_w=120)
        self._add_text_col(self.files_tree, _("Folder / Group"), 2, ellipsize=True, min_w=90)
        self._add_text_col(self.files_tree, _("Country"), 3, min_w=45)
        self._add_text_col(self.files_tree, _("Availability"), 4, markup=True, ellipsize=True, min_w=105)
        self._add_text_col(self.files_tree, _("Favorite status"), 5, markup=True, min_w=85)
        self._add_text_col(self.files_tree, _("Stream URL"), 6, ellipsize=True, min_w=110)

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
            c_code = resolve_country_code(text)
            if not c_code or c_code not in self.bouquets_db:
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
        if info and not info.get("_loaded"):
            load_bouquet_details_on_demand(country_id, info)
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
        if info and not info.get("_loaded"):
            load_bouquet_details_on_demand(country_id, info)

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

    def _test_store_streams(self, store, url_col, id_col, health_col, broken_col, gen_attr, update_fn):
        items_to_check = []
        it = store.get_iter_first()
        while it:
            row_id = store.get_value(it, id_col)
            url = store.get_value(it, url_col)
            store.set_value(it, health_col, status_markup(_("Testing..."), kind="muted"))
            items_to_check.append((row_id, url))
            it = store.iter_next(it)
        setattr(self, gen_attr, getattr(self, gen_attr, 0) + 1)
        self._run_batch_checks(
            store=store,
            items_to_check=items_to_check,
            id_col=id_col,
            health_col=health_col,
            broken_col=broken_col,
            checked_col=0,
            gen_attr=gen_attr,
            on_update=update_fn,
        )

    def _toggle_store_row(self, store, path, update_fn):
        it = store.get_iter(path)
        if it:
            store.set_value(it, 0, not store.get_value(it, 0))
            update_fn()

    def _set_store_checks(self, store, val, update_fn, dup_col=None, dead_col=None, only_new=False):
        it = store.get_iter_first()
        while it:
            if only_new:
                is_dup = store.get_value(it, dup_col) if dup_col is not None else False
                is_dead = store.get_value(it, dead_col) if dead_col is not None else False
                store.set_value(it, 0, (not is_dup) and (not is_dead))
            elif val and (dup_col is not None or dead_col is not None):
                is_dup = store.get_value(it, dup_col) if dup_col is not None else False
                is_dead = store.get_value(it, dead_col) if dead_col is not None else False
                store.set_value(it, 0, False if (is_dup or is_dead) else True)
            else:
                store.set_value(it, 0, val)
            it = store.iter_next(it)
        update_fn()

    def test_bouquet_streams(self):
        self._test_store_streams(self.bouquet_store, 5, 8, 3, 7, "current_check_generation", self.update_bouquet_count)

    def on_bouquet_check_toggled(self, widget, path):
        self._toggle_store_row(self.bouquet_store, path, self.update_bouquet_count)

    def set_bouquet_checks(self, val):
        self._set_store_checks(self.bouquet_store, val, self.update_bouquet_count, dup_col=6, dead_col=7)

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

    def _open_contribute_dialog(self, station_name="", current_url="", country_code=""):
        dlg = ContributeStationDialog(
            parent=self.get_parent_window(),
            station_name=station_name,
            current_url=current_url,
            country_code=country_code,
        )
        dlg.connect("response", lambda d, r: d.destroy())
        dlg.show_all()

    def on_contribute_new_to_radio_browser(self):
        c_code = self.get_selected_country_code() if hasattr(self, "get_selected_country_code") else ""
        st_name = self.entry_rb_name.get_text().strip() if hasattr(self, "entry_rb_name") else ""
        self._open_contribute_dialog(st_name, "", c_code)

    def _contribute_from_tree(self, tree, name_col, url_col, country_col=None, fallback_checked=False):
        model, tree_iter = tree.get_selection().get_selected()
        if not tree_iter and fallback_checked:
            it = model.get_iter_first()
            while it:
                if model.get_value(it, 0):
                    tree_iter = it
                    break
                it = model.iter_next(it)
        if not tree_iter:
            msg = _("Please select or check a radio station in the list first.") if fallback_checked else _("Please select a radio station in the list first.")
            d = Gtk.MessageDialog(
                transient_for=self.get_parent_window(),
                flags=Gtk.DialogFlags.MODAL,
                type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.OK,
                message_format=msg,
            )
            d.connect("response", lambda dialog, r: dialog.destroy())
            d.show_all()
            return
        st_name = model.get_value(tree_iter, name_col) or ""
        cur_url = model.get_value(tree_iter, url_col) or ""
        c_code = (model.get_value(tree_iter, country_col) or "") if country_col is not None else self.get_selected_country_code()
        self._open_contribute_dialog(st_name, cur_url, c_code)

    def on_contribute_bouquet_to_radio_browser(self):
        self._contribute_from_tree(self.bouquet_tree, 1, 5)

    def on_contribute_files_to_radio_browser(self):
        self._contribute_from_tree(self.files_tree, 1, 6, country_col=3, fallback_checked=True)

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
                shutil.copyfile(xml_path, target_file)

        try:
            with open(target_file, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            if old_url in content:
                content = content.replace(old_url, html.escape(new_url))
            else:
                esc_st = re.escape(station_name)
                content = re.sub(
                    rf'(<station\b[^>]*\bname=["\']{esc_st}["\'][^>]*\burl=["\'])[^"\']*(["\'])',
                    rf'\g<1>{html.escape(new_url)}\g<2>',
                    content,
                    flags=re.IGNORECASE
                )
            tmp_file = f"{target_file}.tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                f.write(content)
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
        self._test_store_streams(self.rb_store, 6, 10, 8, None, "current_rb_check_generation", self.update_rb_count)

    def on_rb_check_toggled(self, widget, path):
        self._toggle_store_row(self.rb_store, path, self.update_rb_count)

    def set_rb_checks(self, val):
        self._set_store_checks(self.rb_store, val, self.update_rb_count)

    def update_rb_count(self):
        checked = 0
        it = self.rb_store.get_iter_first()
        while it:
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
        for pat in ("*.xml", "*.csv", "*.json", "*.m3u", "*.m3u8", "*.pls"):
            filter_all.add_pattern(pat)
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

        info_text = f"<b>{_('File:')}</b> {os.path.basename(path)} — <b>{len(stations)}</b> station(s)"
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
            dup_tag = _("[Present]") if is_dup else _("[New]")
            dup_markup = status_markup(dup_tag, kind="warn" if is_dup else "new")
            health_markup = status_markup(f"○ {_('Untested')}", kind="untested")

            self.files_store.append([False, name, grp, country, health_markup, dup_markup, url, is_dup, False, i, grp])

        self.update_files_group_column()
        self.update_files_count()

    def on_files_check_toggled(self, widget, path):
        self._toggle_store_row(self.files_store, path, self.update_files_count)

    def set_files_checks(self, val):
        self._set_store_checks(self.files_store, val, self.update_files_count)

    def set_files_checks_new_only(self):
        self._set_store_checks(self.files_store, True, self.update_files_count, dup_col=7, dead_col=8, only_new=True)

    def test_files_streams(self):
        self._test_store_streams(self.files_store, 6, 9, 4, 8, "current_files_check_generation", self.update_files_count)

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
        _, restored = ensure_user_examples_dir(force_restore=True)
        self.on_refresh_examples_clicked(None)
        self.show_preview_message(f"{restored} {_('sample files restored.')}")

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
            self.preview_player.stop(silent=True, sync=True)
        try:
            self.executor.shutdown(wait=False)
        except Exception:
            pass


def load_bouquet_details_on_demand(country_code, country_data):
    """Charge paresseusement les stations d'un bouquet via le binaire Rust 'timonde --dump-bouquet-json'."""
    if not country_data or country_data.get("_loaded"):
        return
    country_data["_loaded"] = True
    if not country_data.get("has_bouquet"):
        return
    try:
        from timonde_common import run_timonde_cli
        res = run_timonde_cli("--dump-bouquet-json", country_code, timeout=2.0)
        if res.returncode == 0 and res.stdout.strip():
            details = json.loads(res.stdout)
            country_data["multilingual"] = details.get("multilingual", False)
            country_data["languages"] = [(l["id"], l["name"]) for l in details.get("languages", [])]
            country_data["national"] = [(s["name"], s["url"], s.get("genre", "")) for s in details.get("national", [])]
            country_data["regions"] = {reg: [(s["name"], s["url"], s.get("genre", "")) for s in st_list] for reg, st_list in details.get("regions", {}).items()}
            country_data["sub_bouquets"] = {}
            for l_id, sub in details.get("sub_bouquets", {}).items():
                country_data["sub_bouquets"][l_id] = {
                    "national": [(s["name"], s["url"], s.get("genre", "")) for s in sub.get("national", [])],
                    "regions": {reg: [(s["name"], s["url"], s.get("genre", "")) for s in st_list] for reg, st_list in sub.get("regions", {}).items()},
                }
            country_data["xml_path"] = details.get("xml_path")
    except Exception as e:
        sys.stderr.write(f"Erreur chargement bouquet {country_code} via Rust : {e}\n")


def parse_bouquets_xml():
    """Initialise le référentiel des bouquets instantanément via le binaire Rust (sans parsing XML lourd en Python)."""
    db = {}
    from timonde_common import run_timonde_cli
    available_codes = set()
    try:
        res = run_timonde_cli("--list-bouquets", timeout=2.0)
        if res.returncode == 0 and res.stdout.strip():
            available_codes = set(json.loads(res.stdout))
    except Exception:
        pass

    for iso_code, fr_name, _flag in COUNTRIES_DB:
        has_b = iso_code in available_codes
        db[iso_code] = {
            "name": f"{fr_name}  [{iso_code}]" if iso_code else fr_name,
            "country_name": fr_name,
            "code": iso_code,
            "has_bouquet": has_b,
            "multilingual": False,
            "languages": [],
            "sub_bouquets": {},
            "national": [],
            "regions": {},
            "xml_path": None,
            "_loaded": False,
        }

    return db
