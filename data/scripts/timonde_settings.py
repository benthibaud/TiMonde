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
import glob
import shutil
import html
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from timonde_i18n import _
except ImportError:
    def _(s): return s

from timonde_common import make_btn, safe_parse_xml

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Pango, GLib

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


def load_bookmarks_groups_list(path):
    groups = []
    if not os.path.isfile(path):
        return groups
    root = safe_parse_xml(path)
    if root is None:
        return groups
    def walk(el, prefix):
        for child in el.findall("group"):
            name = child.attrib.get("name", "").strip() or child.attrib.get("title", "").strip()
            if name and name.lower() != "root":
                full = f"{prefix}/{name}" if prefix else name
                if full not in groups:
                    groups.append(full)
                walk(child, full)
    walk(root, "")
    return groups


def load_bookmarks_tree(path):
    if not os.path.isfile(path):
        return []
    root = safe_parse_xml(path)
    if root is None:
        return []
    
    payload = []
    def walk(el, prefix):
        for child in el:
            if child.tag == "separator":
                title = child.attrib.get("title", "").strip()
                payload.append({
                    "name": title,
                    "stations": [],
                    "is_separator": True
                })
            elif child.tag == "group":
                name = child.attrib.get("name", "").strip() or child.attrib.get("title", "").strip()
                if not name or name.lower() == "root":
                    continue
                full_path = f"{prefix}/{name}" if prefix else name
                stations = []
                for st in child:
                    if st.tag == "separator":
                        st_title = st.attrib.get("title", "").strip()
                        stations.append({
                            "name": st_title,
                            "url": "",
                            "is_separator": True
                        })
                    elif st.tag in ("bookmark", "station"):
                        st_name = st.attrib.get("name", "").strip()
                        st_url = clean_stream_url(st.attrib.get("url", "").strip())
                        st_country = st.attrib.get("country", "").strip() or None
                        st_tz = st.attrib.get("timezone", "").strip() or None
                        if st_name:
                            stations.append({
                                "name": st_name,
                                "url": st_url,
                                "country": st_country,
                                "timezone": st_tz,
                                "is_separator": False
                            })
                payload.append({
                    "name": full_path,
                    "stations": stations,
                    "is_separator": False
                })
                walk(child, full_path)
    walk(root, "")
    return payload


def save_bookmarks_tree(path, groups_payload):
    lines = ['<?xml version="1.0" encoding="utf-8"?>', '<!DOCTYPE bookmarks>', '<bookmarks>']
    for grp in groups_payload:
        if grp.get("is_separator", False):
            title = grp.get("name", "").replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
            lines.append(f'\t<separator title="{title}"/>')
        else:
            name = grp.get("name", "").replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
            lines.append(f'\t<group name="{name}">')
            for st in grp.get("stations", []):
                if st.get("is_separator", False):
                    st_title = st.get("name", "").replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
                    lines.append(f'\t\t<separator title="{st_title}"/>')
                else:
                    s_name = st.get("name", "").replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
                    s_url = st.get("url", "").replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
                    attrs = f'name="{s_name}" url="{s_url}"'
                    if st.get("country"):
                        c = str(st["country"]).replace("&", "&amp;").replace('"', "&quot;")
                        attrs += f' country="{c}"'
                    if st.get("timezone"):
                        tz = str(st["timezone"]).replace("&", "&amp;").replace('"', "&quot;")
                        attrs += f' timezone="{tz}"'
                    lines.append(f'\t\t<bookmark {attrs}/>')
            lines.append('\t</group>')
    lines.append('</bookmarks>\n')
    
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def add_stations_to_bookmarks_xml(path, stations_list, default_group="Mes Radios", country_code=None):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    root = None
    if os.path.isfile(path):
        root = safe_parse_xml(path)
    if root is None or root.tag not in ("bookmarks", "radios"):
        root = ET.Element("bookmarks")

    existing_urls = set()
    for elem in root.iter():
        if elem.tag in ("bookmark", "station"):
            u = elem.attrib.get("url", "").strip()
            if u:
                existing_urls.add(u)

    def find_or_create_group(parent_elem, group_path):
        parts = [p.strip() for p in group_path.split("/") if p.strip() and p.strip().lower() != "root"]
        curr = parent_elem
        for part in parts:
            found = None
            for child in curr.findall("group"):
                if child.attrib.get("name", "").strip().lower() == part.lower():
                    found = child
                    break
            if found is None:
                found = ET.SubElement(curr, "group", {"name": part})
            curr = found
        return curr

    added_count = 0
    for st in stations_list:
        url = clean_stream_url(st.get("url", "").strip())
        name = st.get("name", "").strip()
        if not url or not name:
            continue
        if url in existing_urls:
            continue
        grp_name = st.get("group") or default_group or "Mes Radios"
        target_group = find_or_create_group(root, grp_name)
        
        attribs = {"name": name, "url": url}
        c = st.get("country") or country_code
        if c:
            attribs["country"] = str(c).strip().upper()
        if st.get("timezone"):
            attribs["timezone"] = str(st["timezone"]).strip()
        
        ET.SubElement(target_group, "bookmark", attribs)
        existing_urls.add(url)
        added_count += 1

    if added_count > 0:
        lines = ['<?xml version="1.0" encoding="utf-8"?>', '<!DOCTYPE bookmarks>', '<bookmarks>']
        def dump_group(grp_el, indent):
            prefix = "\t" * indent
            name = grp_el.attrib.get("name", "").replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
            lines.append(f'{prefix}<group name="{name}">')
            for child in grp_el:
                if child.tag == "group":
                    dump_group(child, indent + 1)
                elif child.tag == "separator":
                    t = child.attrib.get("title", "").replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
                    lines.append(f'{prefix}\t<separator title="{t}"/>')
                elif child.tag in ("bookmark", "station"):
                    s_name = child.attrib.get("name", "").replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
                    s_url = child.attrib.get("url", "").replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
                    attrs = f'name="{s_name}" url="{s_url}"'
                    if child.attrib.get("country"):
                        sc = child.attrib["country"].replace("&", "&amp;").replace('"', "&quot;")
                        attrs += f' country="{sc}"'
                    if child.attrib.get("timezone"):
                        stz = child.attrib["timezone"].replace("&", "&amp;").replace('"', "&quot;")
                        attrs += f' timezone="{stz}"'
                    lines.append(f'{prefix}\t<bookmark {attrs}/>')
            lines.append(f'{prefix}</group>')

        for child in root:
            if child.tag == "group":
                dump_group(child, 1)
            elif child.tag == "separator":
                t = child.attrib.get("title", "").replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
                lines.append(f'\t<separator title="{t}"/>')
            elif child.tag in ("bookmark", "station"):
                s_name = child.attrib.get("name", "").replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
                s_url = child.attrib.get("url", "").replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
                attrs = f'name="{s_name}" url="{s_url}"'
                if child.attrib.get("country"):
                    sc = child.attrib["country"].replace("&", "&amp;").replace('"', "&quot;")
                    attrs += f' country="{sc}"'
                if child.attrib.get("timezone"):
                    stz = child.attrib["timezone"].replace("&", "&amp;").replace('"', "&quot;")
                    attrs += f' timezone="{stz}"'
                lines.append(f'\t<bookmark {attrs}/>')
        lines.append('</bookmarks>\n')
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    return added_count


class SettingsWindow(Gtk.Window):
    def __init__(self, bookmarks_path=None):
        super().__init__(title=_("Paramètres TiMonde"))
        self.set_default_size(780, 520)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_border_width(12)

        self.bookmarks_path = bookmarks_path or DEFAULT_BOOKMARKS_PATH
        self.has_modifications = False

        # Icône native multi-résolutions
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
            self.set_icon_name("preferences-system")

        self.apply_custom_css()
        self.setup_ui()

    def apply_custom_css(self):
        css_data = b"""
        .settings-card {
            background-color: alpha(@theme_base_color, 0.4);
            border: 1px solid alpha(@theme_fg_color, 0.15);
            border-radius: 2px;
            padding: 12px;
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
        .status-badge {
            font-weight: bold;
            padding: 2px 6px;
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
        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(main_vbox)

        # En-tête sobre
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        main_vbox.pack_start(header_box, False, False, 0)

        lbl_header = Gtk.Label()
        header_title = html.escape(_("Paramètres & Contrôle TiMonde"))
        lbl_header.set_markup(f"<big><b>⚙️ {header_title}</b></big>")
        lbl_header.set_halign(Gtk.Align.START)
        header_box.pack_start(lbl_header, True, True, 0)

        # Zone centrale : Volet de navigation (StackSidebar) + Pages (Stack)
        hcontent = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        main_vbox.pack_start(hcontent, True, True, 0)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(150)

        sidebar = Gtk.StackSidebar()
        sidebar.set_stack(self.stack)
        sidebar.set_size_request(200, -1)
        hcontent.pack_start(sidebar, False, False, 0)

        hcontent.pack_start(self.stack, True, True, 0)

        # Création des 4 sections
        self.build_section_general()
        self.build_section_library()
        self.build_section_organization()
        self.build_section_data()

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

    # -------------------------------------------------------------------------
    # 1. Section Général & Système
    # -------------------------------------------------------------------------
    def build_section_general(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        # Carte Autostart
        self.switch_autostart = Gtk.Switch()
        self.switch_autostart.set_active(is_autostart_active())
        self.switch_autostart.connect("notify::active", self.on_autostart_toggled)
        card_auto = self.create_card(
            _("Lancement automatique au démarrage"),
            _("Démarre discrètement TiMonde en arrière-plan dès l'ouverture de votre session graphique."),
            self.switch_autostart
        )
        page.pack_start(card_auto, False, False, 0)

        # Carte Langue / Localisation
        env_lang = os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or "fr"
        lang_code = env_lang.split(".")[0]
        lbl_lang_badge = Gtk.Label(label=f"🌐 {lang_code}")
        lbl_lang_badge.get_style_context().add_class("status-badge")
        card_lang = self.create_card(
            _("Langue et Région"),
            _("Détection automatique selon votre système. 55 langues mondiales supportées avec drapeaux."),
            lbl_lang_badge
        )
        page.pack_start(card_lang, False, False, 0)

        # Carte Zone de notification & Multi-bureaux
        lbl_desktop = Gtk.Label(label=f"🐧 {os.environ.get('XDG_CURRENT_DESKTOP', 'Linux')}")
        lbl_desktop.get_style_context().add_class("status-badge")
        card_tray = self.create_card(
            _("Intégration du bureau & Plateau"),
            _("Compatible natif Wayland et X11 via StatusNotifierItem (XFCE, Cinnamon, GNOME, KDE, MATE)."),
            lbl_desktop
        )
        page.pack_start(card_tray, False, False, 0)

        self.stack.add_titled(page, "general", _("🖥️ Général"))

    # -------------------------------------------------------------------------
    # 2. Section Bibliothèque & Radios
    # -------------------------------------------------------------------------
    def build_section_library(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        # Carte Ajouter une station manuelle
        btn_add = make_btn(_("Nouvelle radio..."), "list-add")
        btn_add.connect("clicked", lambda w: self.action_add_station())
        card_add = self.create_card(
            _("Ajouter une radio manuellement"),
            _("Saisir directement un nom, une URL de flux (AAC, MP3, HLS), un pays et un fuseau horaire."),
            btn_add
        )
        page.pack_start(card_add, False, False, 0)

        # Carte Découverte & DAB+
        btn_dab = make_btn(_("Explorer DAB+..."), "media-optical")
        btn_dab.connect("clicked", lambda w: self.action_browse_bouquets(1))
        card_dab = self.create_card(
            _("Bouquets DAB+ & Sélections officielles"),
            _("Parcourez 146 bouquets nationaux et régionaux vérifiés sans quitter votre bureau."),
            btn_dab
        )
        page.pack_start(card_dab, False, False, 0)

        # Carte Recherche mondiale Radio-Browser
        btn_rb = make_btn(_("Rechercher..."), "system-search")
        btn_rb.connect("clicked", lambda w: self.action_browse_bouquets(0))
        card_rb = self.create_card(
            _("Recherche mondiale Radio-Browser"),
            _("Accédez à plus de 40 000 stations en ligne classées par pays, genre ou mots-clés."),
            btn_rb
        )
        page.pack_start(card_rb, False, False, 0)

        # Carte Importer un fichier personnel
        btn_import_file = make_btn(_("Importer fichier..."), "document-open")
        btn_import_file.connect("clicked", lambda w: self.action_browse_bouquets(3))
        card_imp = self.create_card(
            _("Importer des fichiers personnels"),
            _("Importez vos listes et favoris aux formats XML (RadioTray, TiMonde), CSV, JSON, M3U ou PLS."),
            btn_import_file
        )
        page.pack_start(card_imp, False, False, 0)

        # Carte Exemples thématiques
        box_ex = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_ex_browse = make_btn(_("Parcourir..."), "folder-open")
        btn_ex_browse.connect("clicked", lambda w: self.action_browse_bouquets(2))
        btn_ex_open = make_btn(_("Ouvrir dossier"), "folder")
        btn_ex_open.connect("clicked", lambda w: self.open_directory(USER_EXAMPLES_DIR))
        box_ex.pack_start(btn_ex_browse, False, False, 0)
        box_ex.pack_start(btn_ex_open, False, False, 0)
        card_ex = self.create_card(
            _("Fichiers exemples thématiques"),
            _("Consultez les 17 sélections thématiques ou déposez vos propres fichiers dans ~/.config/timonde/examples/."),
            box_ex
        )
        page.pack_start(card_ex, False, False, 0)

        self.stack.add_titled(page, "library", _("📻 Bibliothèque"))

    # -------------------------------------------------------------------------
    # 3. Section Organisation & Santé des flux
    # -------------------------------------------------------------------------
    def build_section_organization(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        # Carte Organiser les groupes et radios
        btn_reorder = make_btn(_("Gérer les radios..."), "edit-select-all")
        btn_reorder.connect("clicked", lambda w: self.action_reorder_groups())
        card_reorder = self.create_card(
            _("Organiser les groupes et les radios"),
            _("Triez, renommez, supprimez et déplacez vos stations. Créez des dossiers et des sous-groupes (ex: Musique/Jazz)."),
            btn_reorder
        )
        page.pack_start(card_reorder, False, False, 0)

        # Carte Audit & Liens morts
        btn_check = make_btn(_("Lancer l'audit..."), "view-refresh")
        btn_check.connect("clicked", lambda w: self.action_reorder_groups(check_mode=True))
        card_check = self.create_card(
            _("Vérificateur de flux & Liens morts"),
            _("Teste en direct la disponibilité de tous vos flux, détecte les liens inactifs et applique les redirections."),
            btn_check
        )
        page.pack_start(card_check, False, False, 0)

        # Carte Astuce Séparateurs
        card_tips = self.create_card(
            _("💡 Astuce d'agencement visuel"),
            _("Insérez des séparateurs (---) ou des intertitres de section dans vos groupes pour aérer votre menu."),
            None
        )
        page.pack_start(card_tips, False, False, 0)

        self.stack.add_titled(page, "organization", _("↕️ Organisation"))

    # -------------------------------------------------------------------------
    # 4. Section Données & Fichiers
    # -------------------------------------------------------------------------
    def build_section_data(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        # Carte Emplacement des signets
        nb_st, nb_gr = get_bookmarks_stats(self.bookmarks_path)
        box_bm = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_bm_dir = make_btn(_("Ouvrir dossier"), "folder")
        btn_bm_dir.connect("clicked", lambda w: self.open_directory(USER_CONFIG_DIR))
        box_bm.pack_start(btn_bm_dir, False, False, 0)

        self.lbl_bm_desc = Gtk.Label()
        self.lbl_bm_desc.set_markup(f"{html.escape(self.bookmarks_path)}\n<b>{nb_st}</b> station(s) réparties dans <b>{nb_gr}</b> groupe(s).")
        self.lbl_bm_desc.set_halign(Gtk.Align.START)

        card_bm = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        card_bm.get_style_context().add_class("settings-card")
        vbox_bm_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        lbl_bm_title = Gtk.Label()
        lbl_bm_title.set_markup(f"<b>{_('Signets actuels (bookmarks.xml)')}</b>")
        lbl_bm_title.get_style_context().add_class("card-title")
        lbl_bm_title.set_halign(Gtk.Align.START)
        vbox_bm_text.pack_start(lbl_bm_title, False, False, 0)
        vbox_bm_text.pack_start(self.lbl_bm_desc, False, False, 0)
        card_bm.pack_start(vbox_bm_text, True, True, 0)
        box_bm.set_valign(Gtk.Align.CENTER)
        card_bm.pack_end(box_bm, False, False, 0)
        page.pack_start(card_bm, False, False, 0)

        # Carte Exportation CSV
        btn_csv = make_btn(_("Exporter en CSV..."), "document-save-as")
        btn_csv.connect("clicked", lambda w: self.action_reorder_groups(export_mode=True))
        card_csv = self.create_card(
            _("Exporter vos radios en tableur (CSV)"),
            _("Générez une feuille de calcul avec les noms, URLs, groupes et pays de vos stations pour sauvegarde."),
            btn_csv
        )
        page.pack_start(card_csv, False, False, 0)

        # Carte Restauration des exemples
        btn_reset_ex = make_btn(_("Restaurer"), "edit-undo")
        btn_reset_ex.connect("clicked", lambda w: self.restore_default_examples())
        card_reset_ex = self.create_card(
            _("Restaurer les fichiers exemples"),
            _("Rétablit les 17 exemples thématiques par défaut dans votre dossier personnel s'ils ont été supprimés."),
            btn_reset_ex
        )
        page.pack_start(card_reset_ex, False, False, 0)

        self.stack.add_titled(page, "data", _("💾 Données & Fichiers"))

    def refresh_stats(self):
        nb_st, nb_gr = get_bookmarks_stats(self.bookmarks_path)
        if hasattr(self, "lbl_bm_desc"):
            self.lbl_bm_desc.set_markup(f"{html.escape(self.bookmarks_path)}\n<b>{nb_st}</b> station(s) réparties dans <b>{nb_gr}</b> groupe(s).")

    # -------------------------------------------------------------------------
    # Actions Métier & Intégration des sous-outils
    # -------------------------------------------------------------------------
    def find_script(self, script_name):
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

    def action_add_station(self):
        script_path = self.find_script("edit_station.py")
        if not script_path:
            self.show_feedback(f"{_('Outil introuvable :')} edit_station.py", is_error=True)
            return

        groups = load_bookmarks_groups_list(self.bookmarks_path)
        cmd = [
            sys.executable,
            script_path,
            "--mode", "add",
            "--groups-json", json.dumps(groups)
        ]

        try:
            self.set_sensitive(False)
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.set_sensitive(True)
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout.strip())
                added = add_stations_to_bookmarks_xml(self.bookmarks_path, [data], default_group=data.get("group"))
                if added > 0:
                    self.has_modifications = True
                    self.refresh_stats()
                    st_name = data.get("name", "Nouvelle radio")
                    self.show_feedback(f"« {st_name} » {_('ajoutée avec succès à vos signets !')}")
            elif res.returncode != 0:
                pass # Annulé par l'utilisateur
        except Exception as e:
            self.set_sensitive(True)
            self.show_feedback(f"{_('Erreur :')} {e}", is_error=True)

    def action_browse_bouquets(self, tab_index):
        script_path = self.find_script("browse_bouquets.py")
        if not script_path:
            self.show_feedback(f"{_('Outil introuvable :')} browse_bouquets.py", is_error=True)
            return

        cmd = [sys.executable, script_path, f"--tab={tab_index}"]

        try:
            self.set_sensitive(False)
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.set_sensitive(True)
            if res.returncode == 0 and res.stdout.strip():
                try:
                    data = json.loads(res.stdout.strip())
                    stations = data.get("stations", [])
                    group_name = data.get("group_name", "Mes Stations")
                    country_code = data.get("country_code")
                    added = add_stations_to_bookmarks_xml(self.bookmarks_path, stations, default_group=group_name, country_code=country_code)
                    if added > 0:
                        self.has_modifications = True
                        self.refresh_stats()
                        self.show_feedback(f"{added} {_('radio(s) ajoutée(s) à vos signets !')}")
                    else:
                        self.show_feedback(_("Aucune nouvelle radio ajoutée (déjà présentes)."))
                except Exception as ex:
                    self.show_feedback(f"{_('Erreur import JSON :')} {ex}", is_error=True)
        except Exception as e:
            self.set_sensitive(True)
            self.show_feedback(f"{_('Erreur :')} {e}", is_error=True)

    def action_reorder_groups(self, check_mode=False, export_mode=False):
        script_path = self.find_script("reorder_groups.py")
        if not script_path:
            self.show_feedback(f"{_('Outil introuvable :')} reorder_groups.py", is_error=True)
            return

        payload = load_bookmarks_tree(self.bookmarks_path)
        json_input = json.dumps(payload)

        cmd = [sys.executable, script_path]
        if check_mode:
            cmd.append("--check")
        elif export_mode:
            cmd.append("--export")

        try:
            self.set_sensitive(False)
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            stdout_str, stderr_str = proc.communicate(input=json_input)
            self.set_sensitive(True)

            if proc.returncode == 0 and not export_mode and stdout_str.strip():
                new_payload = json.loads(stdout_str.strip())
                save_bookmarks_tree(self.bookmarks_path, new_payload)
                self.has_modifications = True
                self.refresh_stats()
                self.show_feedback(_("Signets réorganisés et enregistrés avec succès !"))
            elif export_mode and proc.returncode == 0:
                self.show_feedback(_("Exportation CSV terminée."))
        except Exception as e:
            self.set_sensitive(True)
            self.show_feedback(f"{_('Erreur :')} {e}", is_error=True)

    # -------------------------------------------------------------------------
    # Actions & Exécution des sous-outils
    # -------------------------------------------------------------------------
    def on_autostart_toggled(self, switch, gparam):
        active = switch.get_active()
        ok = set_autostart_active(active)
        if ok:
            status = _("activé") if active else _("désactivé")
            self.show_feedback(f"{_('Démarrage automatique')} {status}.")
        else:
            self.show_feedback(_("Erreur lors de la modification de l'autostart."), is_error=True)

    def open_directory(self, path):
        try:
            os.makedirs(path, exist_ok=True)
            subprocess.Popen(["xdg-open", path])
            self.show_feedback(f"{_('Dossier ouvert :')} {os.path.basename(path)}")
        except Exception as e:
            self.show_feedback(f"{_('Impossible d ouvrir le dossier :')} {e}", is_error=True)

    def restore_default_examples(self):
        source_dirs = [
            "/usr/share/timonde/examples",
            os.path.join(os.path.dirname(__file__), "../examples"),
            os.path.join(os.path.dirname(__file__), "../../data/examples"),
            "data/examples"
        ]
        restored = 0
        os.makedirs(USER_EXAMPLES_DIR, exist_ok=True)
        for sdir in source_dirs:
            if os.path.isdir(sdir):
                for fname in os.listdir(sdir):
                    src_file = os.path.join(sdir, fname)
                    dst_file = os.path.join(USER_EXAMPLES_DIR, fname)
                    if os.path.isfile(src_file):
                        shutil.copy2(src_file, dst_file)
                        restored += 1
                if restored > 0:
                    break
        self.show_feedback(f"{restored} {_('fichiers exemples restaurés dans')} ~/.config/timonde/examples/")

    def run_subtool(self, script_name, extra_args=None):
        # Recherche du script
        candidates = [
            os.path.join(os.path.dirname(__file__), script_name),
            os.path.join("/usr/share/timonde/scripts", script_name),
            os.path.join("/usr/local/share/timonde/scripts", script_name),
            os.path.expanduser(f"~/.local/share/timonde/scripts/{script_name}"),
            f"data/scripts/{script_name}"
        ]
        script_path = None
        for c in candidates:
            if os.path.isfile(c):
                script_path = c
                break

        if not script_path:
            self.show_feedback(f"{_('Outil introuvable :')} {script_name}", is_error=True)
            return

        cmd = [sys.executable, script_path]
        if extra_args:
            cmd.extend(extra_args)

        try:
            self.set_sensitive(False)
            res = subprocess.run(cmd)
            self.set_sensitive(True)
            if res.returncode == 0:
                self.has_modifications = True
                self.show_feedback(_("Modifications prises en compte."))
        except Exception as e:
            self.set_sensitive(True)
            self.show_feedback(f"{_('Erreur exécution :')} {e}", is_error=True)

    def show_feedback(self, msg, is_error=False):
        color = "#e74c3c" if is_error else "#2ecc71"
        self.lbl_feedback.set_markup(f"<span foreground='{color}'><b>{msg}</b></span>")

    def on_close_clicked(self):
        self.destroy()

    def on_destroy_window(self, widget):
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
