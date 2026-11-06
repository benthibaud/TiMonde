#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TiMonde Settings — Console de Paramètres Unifiée
Console de configuration épurée et sans sous-menus pour TiMonde.
Regroupe le démarrage automatique, la bibliothèque, l'organisation, l'audit et la maintenance.
"""

import sys
import os

# Neutralisation d'IBus pour éviter tout blocage clavier sous GTK3
os.environ.pop("GTK_IM_MODULE", None)
os.environ.pop("XMODIFIERS", None)
os.environ.pop("QT_IM_MODULE", None)

import json
import subprocess
import html
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from timonde_i18n import _
except ImportError:
    def _(s): return s

from timonde_common import make_btn, safe_parse_xml, clean_stream_url, infer_timezone, find_or_create_group, set_window_icon, find_script, get_user_bookmarks_groups, apply_timonde_app_css, status_markup
from reorder_groups import ReorderWindow
from browse_bouquets import DiscoverRadiosWindow, parse_bouquets_xml
from edit_station import EditStationWindow

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk

AUTOSTART_PATH = os.path.expanduser("~/.config/autostart/timonde.desktop")
USER_CONFIG_DIR = os.path.expanduser("~/.config/timonde")
USER_EXAMPLES_DIR = os.path.join(USER_CONFIG_DIR, "examples")
DEFAULT_BOOKMARKS_PATH = os.path.join(USER_CONFIG_DIR, "bookmarks.xml")


def is_autostart_active():
    return os.path.isfile(AUTOSTART_PATH)


def set_autostart_active(active):
    try:
        os.makedirs(os.path.dirname(AUTOSTART_PATH), exist_ok=True)
        if active:
            content = (
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=TiMonde\n"
                "GenericName=Online Radio Player\n"
                "Comment=Lecteur de radios en ligne léger et discret\n"
                "Exec=timonde\n"
                "Icon=timonde_on\n"
                "Terminal=false\n"
                "Categories=AudioVideo;Audio;Player;\n"
                "StartupNotify=false\n"
                "X-GNOME-Autostart-enabled=true\n"
            )
            with open(AUTOSTART_PATH, "w", encoding="utf-8") as f:
                f.write(content)
        else:
            if os.path.exists(AUTOSTART_PATH):
                os.remove(AUTOSTART_PATH)
        return True
    except Exception as e:
        sys.stderr.write(f"Erreur configuration autostart: {e}\n")
        return False


def get_bookmarks_stats(path):
    if not os.path.isfile(path):
        return 0, 0
    try:
        root = safe_parse_xml(path)
        if root is None:
            return 0, 0
        stations = 0
        groups = 0
        for elem in root.iter():
            if elem.tag in ("bookmark", "station"):
                stations += 1
            elif elem.tag == "group" and elem.attrib.get("name", "").strip() != "root":
                groups += 1
        return stations, groups
    except Exception:
        return 0, 0




def load_bookmarks_tree(path):
    if not os.path.isfile(path):
        return []
    root = safe_parse_xml(path)
    if root is None:
        return []

    payload = []
    root_stations = []

    def parse_station_elem(st):
        if st.tag == "separator":
            st_title = st.attrib.get("title", "").strip()
            return {
                "name": st_title,
                "url": "",
                "is_separator": True,
            }
        elif st.tag in ("bookmark", "station"):
            st_name = st.attrib.get("name", "").strip()
            st_url = clean_stream_url(st.attrib.get("url", "").strip())
            st_country = st.attrib.get("country", "").strip() or None
            st_tz = st.attrib.get("timezone", "").strip() or None
            if st_name:
                return {
                    "name": st_name,
                    "url": st_url,
                    "country": st_country,
                    "timezone": st_tz,
                    "is_separator": False,
                }
        return None

    def walk(el, prefix):
        for child in el:
            if child.tag in ("bookmark", "station") and not prefix:
                st_obj = parse_station_elem(child)
                if st_obj:
                    root_stations.append(st_obj)
            elif child.tag == "separator" and not prefix:
                title = child.attrib.get("title", "").strip()
                payload.append({
                    "name": title,
                    "stations": [],
                    "is_separator": True,
                })
            elif child.tag == "group":
                name = child.attrib.get("name", "").strip() or child.attrib.get("title", "").strip()
                if not name:
                    continue
                if name.lower() == "root" and not prefix:
                    walk(child, "")
                    continue
                full_path = f"{prefix}/{name}" if prefix else name
                stations = []
                for st in child:
                    if st.tag in ("separator", "bookmark", "station"):
                        st_obj = parse_station_elem(st)
                        if st_obj:
                            stations.append(st_obj)
                if stations or not child.findall("group"):
                    payload.append({
                        "name": full_path,
                        "stations": stations,
                        "is_separator": False,
                    })
                walk(child, full_path)

    walk(root, "")
    if root_stations:
        payload.insert(0, {
            "name": "[ / ] (Racine — Sans groupe)",
            "stations": root_stations,
            "is_separator": False,
        })
    return payload


def _write_bookmarks_element_tree_atomic(path, root_el):
    lines = ['<?xml version="1.0" encoding="utf-8"?>', '<!DOCTYPE bookmarks>', '<bookmarks>']

    def esc(val):
        return (val or "").replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;").replace("'", "&apos;")

    def dump_station(st_el, indent):
        prefix = "\t" * indent
        s_name = esc(st_el.attrib.get("name", ""))
        s_url = esc(st_el.attrib.get("url", ""))
        attrs = f'name="{s_name}" url="{s_url}"'
        if st_el.attrib.get("country"):
            attrs += f' country="{esc(st_el.attrib["country"])}"'
        if st_el.attrib.get("timezone"):
            attrs += f' timezone="{esc(st_el.attrib["timezone"])}"'
        lines.append(f'{prefix}<bookmark {attrs}/>')

    def dump_group(grp_el, indent):
        prefix = "\t" * indent
        name = esc(grp_el.attrib.get("name", ""))
        lines.append(f'{prefix}<group name="{name}">')
        for child in grp_el:
            if child.tag == "group":
                dump_group(child, indent + 1)
            elif child.tag == "separator":
                lines.append(f'{prefix}\t<separator title="{esc(child.attrib.get("title", ""))}"/>')
            elif child.tag in ("bookmark", "station"):
                dump_station(child, indent + 1)
        lines.append(f'{prefix}</group>')

    for child in root_el:
        if child.tag == "group":
            dump_group(child, 1)
        elif child.tag == "separator":
            lines.append(f'\t<separator title="{esc(child.attrib.get("title", ""))}"/>')
        elif child.tag in ("bookmark", "station"):
            dump_station(child, 1)
    lines.append('</bookmarks>\n')

    abs_path = os.path.abspath(path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    tmp_path = f"{abs_path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, abs_path)


def save_bookmarks_tree(path, groups_payload):
    root = ET.Element("bookmarks")

    for grp in groups_payload:
        if grp.get("is_separator", False):
            ET.SubElement(root, "separator", {"title": grp.get("name", "")})
        else:
            target_el = find_or_create_group(root, grp.get("name", ""))
            for st in grp.get("stations", []):
                if st.get("is_separator", False):
                    ET.SubElement(target_el, "separator", {"title": st.get("name", "")})
                else:
                    attribs = {
                        "name": st.get("name", ""),
                        "url": st.get("url", ""),
                    }
                    if st.get("country"):
                        attribs["country"] = str(st["country"])
                    if st.get("timezone"):
                        attribs["timezone"] = str(st["timezone"])
                    ET.SubElement(target_el, "bookmark", attribs)

    _write_bookmarks_element_tree_atomic(path, root)


def add_stations_to_bookmarks_xml(path, stations_list, default_group="Mes Radios", country_code=None):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    root = None
    if os.path.isfile(path):
        root = safe_parse_xml(path)
    if root is None or root.tag not in ("bookmarks", "radios"):
        root = ET.Element("bookmarks")

    # Mappage de chaque URL existante vers (parent_elem, child_elem)
    existing_map = {}
    for parent in root.iter():
        for child in list(parent):
            if child.tag in ("bookmark", "station"):
                u = child.attrib.get("url", "").strip()
                if u:
                    existing_map[u] = (parent, child)

    added_count = 0
    moved_count = 0
    for st in stations_list:
        url = clean_stream_url(st.get("url", "").strip())
        name = st.get("name", "").strip()
        if not url or not name:
            continue

        grp_name = st.get("group")
        if not grp_name:
            grp_name = default_group or "root"
        target_group = find_or_create_group(root, grp_name)

        if url in existing_map:
            old_parent, existing_elem = existing_map[url]
            if old_parent != target_group and existing_elem is not None:
                # La station existe déjà mais l'utilisateur l'importe dans une nouvelle cible -> déplacement !
                old_parent.remove(existing_elem)
                if name:
                    existing_elem.attrib["name"] = name
                c = st.get("country") or country_code
                if c:
                    existing_elem.attrib["country"] = str(c).strip().upper()
                tz = st.get("timezone")
                if tz:
                    existing_elem.attrib["timezone"] = str(tz).strip()
                target_group.append(existing_elem)
                existing_map[url] = (target_group, existing_elem)
                moved_count += 1
            continue

        attribs = {"name": name, "url": url}
        c = st.get("country") or country_code
        if c:
            attribs["country"] = str(c).strip().upper()
        tz = st.get("timezone") or infer_timezone(attribs.get("country", ""), name, grp_name)
        if tz:
            attribs["timezone"] = str(tz).strip()

        new_el = ET.SubElement(target_group, "bookmark", attribs)
        existing_map[url] = (target_group, new_el)
        added_count += 1

    if added_count > 0 or moved_count > 0:
        _write_bookmarks_element_tree_atomic(path, root)

    return added_count, moved_count


class SettingsWindow(Gtk.Window):
    def __init__(self, bookmarks_path=None):
        super().__init__(title=_("Paramètres & Contrôle TiMonde"))
        screen = Gdk.Screen.get_default()
        target_w, target_h = 960, 640
        if screen:
            geom = screen.get_monitor_geometry(screen.get_primary_monitor() or 0)
            max_w = int(geom.width * 0.90)
            max_h = int(geom.height * 0.85)
            target_w = min(target_w, max_w)
            target_h = min(target_h, max_h)
        self.set_default_size(max(target_w, 750), max(target_h, 480))
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_border_width(10)

        self.bookmarks_path = bookmarks_path or DEFAULT_BOOKMARKS_PATH
        self.has_modifications = False

        set_window_icon(self)

        self.apply_custom_css()
        self.setup_ui()

    def apply_custom_css(self):
        apply_timonde_app_css()
        css_data = b"""
        .settings-card {
            background-color: alpha(@theme_base_color, 0.4);
            border: 1px solid alpha(@theme_fg_color, 0.15);
            border-radius: 2px;
            padding: 12px;
            margin-bottom: 6px;
        }
        .info-card {
            background-color: alpha(@theme_base_color, 0.15);
            border: 1px dashed alpha(@theme_fg_color, 0.18);
            border-radius: 2px;
            padding: 10px 12px;
            margin-bottom: 6px;
        }
        .card-title {
            font-weight: bold;
            font-size: 1.05em;
        }
        .card-desc {
            opacity: 0.75;
            font-size: 0.9em;
        }
        .info-title {
            font-weight: bold;
            font-size: 0.95em;
            opacity: 0.85;
        }
        .info-desc {
            opacity: 0.65;
            font-size: 0.85em;
        }
        .status-badge {
            font-weight: bold;
            padding: 2px 6px;
            border-radius: 2px;
        }
        .info-badge {
            font-family: monospace;
            font-size: 0.9em;
            padding: 2px 8px;
            border-radius: 2px;
            background-color: alpha(@theme_fg_color, 0.08);
            color: @theme_fg_color;
            opacity: 0.9;
        }
        .section-separator-title {
            font-weight: bold;
            font-size: 0.82em;
            letter-spacing: 0.5px;
            opacity: 0.55;
            margin-top: 10px;
            margin-bottom: 4px;
        }
        .highlight-combo {
            font-weight: bold;
            border: 1px solid alpha(@theme_selected_bg_color, 0.6);
            border-radius: 2px;
        }
        """
        provider = Gtk.CssProvider()
        try:
            provider.load_from_data(css_data)
            Gtk.StyleContext.add_provider_for_screen(
                Gdk.Screen.get_default(),
                provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
        except Exception:
            pass

    def setup_ui(self):
        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add(main_vbox)

        # Zone centrale : Volet de navigation (StackSidebar) + Pages (Stack)
        hcontent = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        main_vbox.pack_start(hcontent, True, True, 0)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(150)

        sidebar = Gtk.StackSidebar()
        sidebar.set_stack(self.stack)
        sidebar_scroll = Gtk.ScrolledWindow()
        sidebar_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sidebar_scroll.add(sidebar)
        sidebar_scroll.set_size_request(185, -1)
        hcontent.pack_start(sidebar_scroll, False, False, 0)

        hcontent.pack_start(self.stack, True, True, 0)

        # Les 5 ateliers unifiés de 1er niveau (Zéro sous-fenêtres, zéro sous-onglets)
        self.build_section_organization()
        self.build_section_discovery()
        self.build_section_general()

        self.stack.connect("notify::visible-child-name", self.on_stack_page_changed)

        # Barre inférieure : message de statut & bouton Fermer
        bottom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        main_vbox.pack_start(bottom_box, False, False, 0)

        self.lbl_feedback = Gtk.Label(label="")
        self.lbl_feedback.set_halign(Gtk.Align.START)
        bottom_box.pack_start(self.lbl_feedback, True, True, 0)

        btn_close = make_btn(_("Fermer"), "window-close")
        btn_close.get_style_context().add_class("suggested-action")
        btn_close.connect("clicked", lambda w: self.on_close_clicked())
        bottom_box.pack_end(btn_close, False, False, 0)

        self.connect("destroy", self.on_destroy_window)

    def create_card(self, title_text, desc_text, action_widget):
        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        card.get_style_context().add_class("settings-card")

        vbox_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        lbl_title = Gtk.Label()
        lbl_title.set_markup(f"<b>{html.escape(title_text)}</b>")
        lbl_title.set_halign(Gtk.Align.START)
        lbl_title.get_style_context().add_class("card-title")
        vbox_text.pack_start(lbl_title, False, False, 0)

        if desc_text:
            lbl_desc = Gtk.Label()
            lbl_desc.set_text(desc_text)
            lbl_desc.set_halign(Gtk.Align.START)
            lbl_desc.set_line_wrap(True)
            lbl_desc.get_style_context().add_class("card-desc")
            vbox_text.pack_start(lbl_desc, False, False, 0)

        card.pack_start(vbox_text, True, True, 0)

        if action_widget:
            action_widget.set_valign(Gtk.Align.CENTER)
            card.pack_end(action_widget, False, False, 0)

        return card

    def create_info_row(self, title_text, desc_text, badge_text):
        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        card.get_style_context().add_class("info-card")

        vbox_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        lbl_title = Gtk.Label()
        lbl_title.set_markup(f"<b>{html.escape(title_text)}</b>")
        lbl_title.set_halign(Gtk.Align.START)
        lbl_title.get_style_context().add_class("info-title")
        vbox_text.pack_start(lbl_title, False, False, 0)

        if desc_text:
            lbl_desc = Gtk.Label()
            lbl_desc.set_text(desc_text)
            lbl_desc.set_halign(Gtk.Align.START)
            lbl_desc.set_line_wrap(True)
            lbl_desc.get_style_context().add_class("info-desc")
            vbox_text.pack_start(lbl_desc, False, False, 0)

        card.pack_start(vbox_text, True, True, 0)

        if badge_text:
            lbl_badge = Gtk.Label(label=badge_text)
            lbl_badge.get_style_context().add_class("info-badge")
            lbl_badge.set_valign(Gtk.Align.CENTER)
            card.pack_end(lbl_badge, False, False, 0)

        return card

    # -------------------------------------------------------------------------
    # 1. Atelier « Mes Radios » (ReorderWindow intégrée en direct)
    # -------------------------------------------------------------------------
    def build_section_organization(self):
        payload = load_bookmarks_tree(self.bookmarks_path)
        self.reorder_view = ReorderWindow(
            data=payload,
            auto_check=False,
            embedded=True,
            on_save_callback=self.on_embedded_reorder_saved
        )
        self.reorder_view.btn_add_station.disconnect_by_func(self.reorder_view.on_add_station_clicked)
        self.reorder_view.btn_add_station.connect("clicked", self.on_embedded_add_station_clicked)

        self.stack.add_titled(self.reorder_view.vbox, "organization", _("Mes Radios"))

    def on_embedded_reorder_saved(self, new_payload):
        save_bookmarks_tree(self.bookmarks_path, new_payload)
        self.has_modifications = True
        self.refresh_stats()
        self.show_feedback(_("Signets et radios enregistrés avec succès !"))

    def on_embedded_add_station_clicked(self, widget):
        current_grp = self.reorder_view.get_selected_group_name() if hasattr(self.reorder_view, "get_selected_group_name") else ""
        groups = get_user_bookmarks_groups(self.bookmarks_path)
        dlg = EditStationWindow(
            mode="add",
            current_group=current_grp or "",
            available_groups=groups,
            standalone=False,
            on_done_callback=self.on_embedded_station_added
        )
        dlg.set_transient_for(self)
        dlg.set_modal(True)
        dlg.show_all()

    def on_embedded_station_added(self, data):
        if not data:
            return
        if hasattr(self, "reorder_view"):
            self.reorder_view.flush_pending()
        added, moved = add_stations_to_bookmarks_xml(self.bookmarks_path, [data], default_group=data.get("group"))
        if added > 0 or moved > 0:
            self.has_modifications = True
            payload = load_bookmarks_tree(self.bookmarks_path)
            self.reorder_view.data = payload
            self.reorder_view.set_dirty(False)
            self.reorder_view.update_view()
            self.refresh_stats()
            self.show_feedback(f"« {data.get('name', 'Radio')} » {_('enregistrée avec succès !')}")

    # -------------------------------------------------------------------------
    # 2, 3, 4. Ateliers Recherche, Bouquets, et Fichiers (DiscoverRadiosWindow)
    # -------------------------------------------------------------------------
    def build_section_discovery(self):
        bouquets_db = parse_bouquets_xml()
        existing_stations = []
        if os.path.isfile(self.bookmarks_path):
            root = safe_parse_xml(self.bookmarks_path)
            if root is not None:
                for el in root.iter():
                    if el.tag in ("bookmark", "station"):
                        existing_stations.append({
                            "name": el.attrib.get("name", ""),
                            "url": el.attrib.get("url", ""),
                            "country": el.attrib.get("country", ""),
                            "timezone": el.attrib.get("timezone", "")
                        })

        available_groups = get_user_bookmarks_groups(self.bookmarks_path)
        self.discover_view = DiscoverRadiosWindow(
            existing_stations=existing_stations,
            bouquets_db=bouquets_db,
            initial_tab=0,
            available_groups=available_groups,
            embedded=True,
            on_import_callback=self.on_embedded_discovery_import,
            on_export_csv_callback=lambda: self.reorder_view.on_export_csv_clicked(),
            on_backup_xml_callback=lambda: (self.reorder_view.flush_pending(), self.reorder_view.on_backup_xml_clicked()),
        )

        # 3 Ateliers directs dans le volet principal
        self.stack.add_titled(self.discover_view.view_search, "search", _("Rechercher en ligne"))
        self.stack.add_titled(self.discover_view.view_bouquets, "bouquets", _("Bouquets par pays"))
        self.stack.add_titled(self.discover_view.view_files, "files", _("Collections & Fichiers"))

    def on_embedded_discovery_import(self, result):
        if hasattr(self, "reorder_view"):
            self.reorder_view.flush_pending()
        stations = result.get("stations", [])
        grp_name = result.get("group_name", "Mes Radios")
        c_code = result.get("country_code")
        added, moved = add_stations_to_bookmarks_xml(self.bookmarks_path, stations, default_group=grp_name, country_code=c_code)
        if added > 0 or moved > 0:
            self.has_modifications = True
            payload = load_bookmarks_tree(self.bookmarks_path)
            self.reorder_view.data = payload
            self.reorder_view.set_dirty(False)
            self.reorder_view.update_view()
            self.refresh_stats()
            msgs = []
            if added > 0:
                msgs.append(f"{added} {_('nouvelle(s) radio(s) importée(s)')}")
            if moved > 0:
                msgs.append(f"{moved} {_('radio(s) déplacée(s) vers la cible')}")
            self.show_feedback(" & ".join(msgs) + " !")
            self.stack.set_visible_child_name("organization")
        else:
            self.show_feedback(_("Aucune nouvelle radio ajoutée (déjà présentes dans vos signets)."))

    def on_stack_page_changed(self, stack, gparam):
        """Sauvegarde les modifications en attente et arrête la pré-écoute lors du changement d'onglet."""
        if hasattr(self, "reorder_view"):
            self.reorder_view.flush_pending()
            if hasattr(self.reorder_view, "preview_player") and self.reorder_view.preview_player:
                self.reorder_view.preview_player.stop(silent=True)
        if hasattr(self, "discover_view") and hasattr(self.discover_view, "preview_player") and self.discover_view.preview_player:
            self.discover_view.preview_player.stop(silent=True)

    # -------------------------------------------------------------------------
    # 5. Section Préférences (Options & Diagnostic système)
    # -------------------------------------------------------------------------
    def build_section_general(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        page.set_border_width(8)

        # 1. Section Options Configurables
        lbl_cfg = Gtk.Label()
        lbl_cfg.set_markup("<b>" + _("OPTIONS DE SESSION") + "</b>")
        lbl_cfg.set_halign(Gtk.Align.START)
        lbl_cfg.get_style_context().add_class("section-separator-title")
        page.pack_start(lbl_cfg, False, False, 0)

        # Carte Autostart cliquable
        self.switch_autostart = Gtk.Switch()
        self.switch_autostart.set_active(is_autostart_active())
        self.switch_autostart.connect("notify::active", self.on_autostart_toggled)
        card_auto = self.create_card(
            _("Lancement automatique au démarrage"),
            _("Démarre discrètement TiMonde en arrière-plan dès l'ouverture de votre session graphique."),
            self.switch_autostart
        )
        page.pack_start(card_auto, False, False, 0)

        # 2. Section Informations Système (Lecture Seule)
        lbl_info = Gtk.Label()
        lbl_info.set_markup("<b>" + _("ENVIRONNEMENT DÉTECTÉ (LECTURE SEULE)") + "</b>")
        lbl_info.set_halign(Gtk.Align.START)
        lbl_info.get_style_context().add_class("section-separator-title")
        page.pack_start(lbl_info, False, False, 4)

        # Langue détectée
        env_lang = os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or "fr_FR.UTF-8"
        clean_lang = env_lang.split(".")[0]
        card_lang = self.create_info_row(
            _("Langue du système"),
            _("Détection automatique selon les paramètres régionaux de votre environnement Linux."),
            f"{clean_lang}"
        )
        page.pack_start(card_lang, False, False, 0)

        # Bureau graphique & Intégration
        desktop_raw = os.environ.get("XDG_CURRENT_DESKTOP") or os.environ.get("DESKTOP_SESSION") or "Linux"
        session_type = (os.environ.get("XDG_SESSION_TYPE") or "x11").upper()
        env_badge = f"{desktop_raw} ({session_type})"
        card_desktop = self.create_info_row(
            _("Bureau graphique & Plateau"),
            _("Intégration native dans la zone de notification via StatusNotifierItem / XEmbed."),
            env_badge
        )
        page.pack_start(card_desktop, False, False, 0)

        # Détection proactive d'intégration GNOME (si AppIndicator est manquant)
        helper_path = find_script("gnome_tray_helper.py")
        if helper_path:
            try:
                chk = subprocess.run([sys.executable, helper_path, "--check"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if chk.returncode == 1:
                    btn_fix = make_btn(_("Installer l'intégration GNOME"), "system-software-install-symbolic", primary=True)
                    def on_install_gnome_clicked(widget):
                        subprocess.run([sys.executable, helper_path, "--prompt"])
                    btn_fix.connect("clicked", on_install_gnome_clicked)
                    card_gnome_warning = self.create_card(
                        _("Intégration GNOME requise"),
                        _("L'extension AppIndicator est nécessaire pour afficher l'icône dans la barre supérieure sous GNOME."),
                        btn_fix
                    )
                    page.pack_start(card_gnome_warning, False, False, 0)
            except Exception:
                pass

        # Détection proactive Cinnamon (Harmonisation Clic Gauche / Droit)
        cinnamon_patch_path = find_script("patch_cinnamon_status_applet.py")
        is_cinnamon = "cinnamon" in desktop_raw.lower() or os.path.isdir(os.path.expanduser("~/.local/share/cinnamon"))
        if is_cinnamon and cinnamon_patch_path:
            try:
                chk = subprocess.run([sys.executable, cinnamon_patch_path, "--check"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                is_active = (chk.returncode == 0)
                btn_cin = make_btn(
                    _("Active (Left & Right clicks unified)") if is_active else _("Enable Left-Click"),
                    "emblem-default" if is_active else "system-run-symbolic",
                    primary=not is_active
                )
                if is_active:
                    btn_cin.set_sensitive(False)
                else:
                    def on_patch_cinnamon_clicked(widget):
                        res = subprocess.run([sys.executable, cinnamon_patch_path, "--user"])
                        if res.returncode == 0:
                            widget.set_label(_("Active (Left & Right clicks unified)"))
                            widget.set_sensitive(False)
                            self.show_feedback(_("Cinnamon left-click unification successfully enabled!"))
                        else:
                            self.show_feedback(_("Failed to enable Cinnamon unification."), is_error=True)
                    btn_cin.connect("clicked", on_patch_cinnamon_clicked)

                card_cinnamon = self.create_card(
                    _("Cinnamon Left-Click Unification"),
                    _("Allows opening the station menu interchangeably with left or right click."),
                    btn_cin
                )
                page.pack_start(card_cinnamon, False, False, 0)
            except Exception:
                pass

        self.stack.add_titled(page, "general", _("Préférences"))

    def refresh_stats(self):
        nb_st, nb_gr = get_bookmarks_stats(self.bookmarks_path)
        if hasattr(self, "lbl_bm_desc"):
            desc = _("<b>{nb_st}</b> station(s) in <b>{nb_gr}</b> group(s).").format(nb_st=nb_st, nb_gr=nb_gr)
            self.lbl_bm_desc.set_markup(f"{html.escape(self.bookmarks_path)}\n{desc}")

    # -------------------------------------------------------------------------
    # Actions & Exécution
    # -------------------------------------------------------------------------
    def on_autostart_toggled(self, switch, gparam):
        active = switch.get_active()
        ok = set_autostart_active(active)
        if ok:
            status = _("activé") if active else _("désactivé")
            self.show_feedback(f"{_('Démarrage automatique')} {status}.")
        else:
            self.show_feedback(_("Erreur lors de la modification de l'autostart."), is_error=True)

    def show_feedback(self, msg, is_error=False):
        kind = "error" if is_error else "ok"
        self.lbl_feedback.set_markup(status_markup(msg or "", kind=kind, with_bullet=False, bold=True))

    def on_close_clicked(self):
        self.destroy()

    def on_destroy_window(self, widget):
        # Sauvegarde étanche de toute modification de réorganisation en attente
        if hasattr(self, "reorder_view"):
            if self.reorder_view.flush_pending():
                self.has_modifications = True
            if hasattr(self.reorder_view, "preview_player") and self.reorder_view.preview_player:
                self.reorder_view.preview_player.stop(silent=True)
        if hasattr(self, "discover_view") and hasattr(self.discover_view, "preview_player") and self.discover_view.preview_player:
            self.discover_view.preview_player.stop(silent=True)
        # Transmettre le résultat JSON sur stdout à destination de TiMonde en Rust
        output = {"reload": self.has_modifications}
        print(json.dumps(output), flush=True)
        Gtk.main_quit()


def main():
    bookmarks_path = sys.argv[1] if len(sys.argv) > 1 else None
    win = SettingsWindow(bookmarks_path)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
