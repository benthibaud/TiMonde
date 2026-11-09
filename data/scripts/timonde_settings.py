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

import html
import json
import subprocess
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from timonde_i18n import _
except ImportError:
    def _(s): return s

from timonde_common import (
    make_btn,
    update_btn_content,
    clean_stream_url,
    infer_timezone,
    set_window_icon,
    find_script,
    get_user_bookmarks_groups,
    apply_timonde_app_css,
    status_markup,
    normalize_group_path,
    TIMONDE_VERSION,
    setup_window_geometry,
    atomic_write_file,
    call_timonde_mpris,
    find_timonde_binary,
    set_container_margins,
)
from reorder_groups import ReorderWidget
from browse_bouquets import DiscoverRadiosViews, parse_bouquets_xml
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
            atomic_write_file(AUTOSTART_PATH, content)
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
        payload = load_bookmarks_tree(path)
        stations = 0
        groups = 0
        for grp in payload:
            st_count = len(grp.get("stations", []))
            stations += st_count
            name = grp.get("name", "").strip()
            if name and name != "[ / ] (Racine — Sans groupe)":
                groups += 1
        return stations, groups
    except Exception:
        return 0, 0




def load_bookmarks_tree(path):
    """
    Charge l'arbre des favoris au format JSON via le moteur natif Rust (Option B).
    Délègue 100% du parsing XML, des conventions de slash et de la tolérance d'entités à Rust.
    """
    if not os.path.isfile(path):
        return []

    # 1. Appel unifié via D-Bus (mémoire vive) ou fallback CLI (dump atomique Rust)
    is_default = os.path.abspath(path) == os.path.abspath(DEFAULT_BOOKMARKS_PATH)
    fallback_cli = ["--dump-bookmarks-json", path]
    if is_default:
        ok, res = call_timonde_mpris("GetBookmarksJson", fallback_cli=fallback_cli)
        if ok and res:
            try:
                return json.loads(str(res))
            except Exception:
                pass
    else:
        # Fichier personnalisé : lecture directe via le CLI natif
        try:
            bin_path = find_timonde_binary() or "timonde"
            proc = subprocess.run([bin_path, "--dump-bookmarks-json", path], capture_output=True, text=True, timeout=5.0)
            if proc.returncode == 0 and proc.stdout.strip():
                return json.loads(proc.stdout)
        except Exception:
            pass

    return []


def save_bookmarks_tree(path, groups_payload):
    """
    Sauvegarde l'arbre des favoris via le moteur natif Rust (Option B).
    Délègue l'intégrité, la normalisation des URLs et l'écriture atomique à Rust.
    """
    try:
        json_bytes = json.dumps(groups_payload, ensure_ascii=False).encode("utf-8")
        cmd = ["timonde", "--save-bookmarks-json", "-"]
        if path:
            cmd.append(path)
        res = subprocess.run(
            cmd,
            input=json_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5.0
        )
        if res.returncode == 0:
            return True
    except Exception as e:
        sys.stderr.write(f"Erreur sauvegarde signets Rust : {e}\n")
    return False


def add_stations_to_bookmarks_xml(path, stations_list, default_group="Mes Radios", country_code=None):
    """
    Ajoute des stations aux favoris en manipulant le payload en mémoire
    puis en déléguant la persistance à Rust (Option B).
    """
    payload = load_bookmarks_tree(path)
    grp_name = default_group or "root"
    norm_target = normalize_group_path(grp_name, return_root_literal=True)

    target_group = None
    for g in payload:
        if g.get("name", "").strip().lower() == norm_target.lower() and not g.get("is_separator"):
            target_group = g
            break

    if target_group is None:
        target_group = {
            "name": norm_target,
            "stations": [],
            "is_separator": False,
        }
        payload.append(target_group)

    existing_urls = set()
    for g in payload:
        for s in g.get("stations", []):
            u = s.get("url", "").strip()
            if u:
                existing_urls.add(clean_stream_url(u))

    added_count = 0
    for st in stations_list:
        u = clean_stream_url(st.get("url", "").strip())
        n = st.get("name", "").strip()
        if not u or not n:
            continue
        if u in existing_urls:
            continue
        c = st.get("country") or country_code
        tz = st.get("timezone") or infer_timezone(str(c) if c else "", n, grp_name)
        new_st = {
            "name": n,
            "url": u,
            "country": str(c).strip().upper() if c else None,
            "timezone": str(tz).strip() if tz else None,
            "is_separator": False,
        }
        target_group["stations"].append(new_st)
        existing_urls.add(u)
        added_count += 1

    if added_count > 0:
        save_bookmarks_tree(path, payload)

    return added_count, 0


class SettingsWindow(Gtk.Window):
    def __init__(self, bookmarks_path=None):
        super().__init__(title=_("Settings & Control TiMonde"))
        setup_window_geometry(self, base_width=960, base_height=640, min_width=750, min_height=480)

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
        set_container_margins(main_vbox, margin=10)
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

        btn_close = make_btn(_("Close"), "window-close")
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
        self.reorder_view = ReorderWidget(
            data=payload,
            auto_check=False,
            embedded=True,
            on_save_callback=self.on_embedded_reorder_saved
        )
        self.reorder_view.btn_add_station.disconnect_by_func(self.reorder_view.on_add_station_clicked)
        self.reorder_view.btn_add_station.connect("clicked", self.on_embedded_add_station_clicked)

        self.stack.add_titled(self.reorder_view, "organization", _("My Radios"))

    def on_embedded_reorder_saved(self, new_payload):
        save_bookmarks_tree(self.bookmarks_path, new_payload)
        self.has_modifications = True
        self.refresh_stats()
        self.show_feedback(_("Bookmarks and stations saved successfully!"))

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
            self.show_feedback(f"« {data.get('name', 'Radio')} » {_('saved successfully!')}")

    # -------------------------------------------------------------------------
    # 2, 3, 4. Ateliers Recherche, Bouquets, et Fichiers (DiscoverRadiosWindow)
    # -------------------------------------------------------------------------
    def build_section_discovery(self):
        bouquets_db = parse_bouquets_xml()
        existing_stations = []
        payload = load_bookmarks_tree(self.bookmarks_path)
        for grp in payload:
            for s in grp.get("stations", []):
                existing_stations.append({
                    "name": s.get("name", ""),
                    "url": s.get("url", ""),
                    "country": s.get("country", ""),
                    "timezone": s.get("timezone", "")
                })

        available_groups = get_user_bookmarks_groups(self.bookmarks_path)
        self.discover_view = DiscoverRadiosViews(
            existing_stations=existing_stations,
            bouquets_db=bouquets_db,
            available_groups=available_groups,
            embedded=True,
            on_import_callback=self.on_embedded_discovery_import,
            on_export_csv_callback=lambda: self.reorder_view.on_export_csv_clicked(),
            on_backup_xml_callback=lambda: (self.reorder_view.flush_pending(), self.reorder_view.on_backup_xml_clicked()),
        )

        # 3 Ateliers directs dans le volet principal
        self.stack.add_titled(self.discover_view.view_search, "search", _("Search online"))
        self.stack.add_titled(self.discover_view.view_bouquets, "bouquets", _("Country bouquets"))
        self.stack.add_titled(self.discover_view.view_files, "files", _("Collections & Files"))

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
                msgs.append(f"{added} {_('new station(s) imported')}")
            if moved > 0:
                msgs.append(f"{moved} {_('station(s) moved to destination')}")
            self.show_feedback(" & ".join(msgs) + " !")
            self.stack.set_visible_child_name("organization")
        else:
            self.show_feedback(_("No new stations added (already in your bookmarks)."))

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
        set_container_margins(page, margin=8)

        # 1. Section Options Configurables
        lbl_cfg = Gtk.Label()
        lbl_cfg.set_markup("<b>" + _("SESSION OPTIONS") + "</b>")
        lbl_cfg.set_halign(Gtk.Align.START)
        lbl_cfg.get_style_context().add_class("section-separator-title")
        page.pack_start(lbl_cfg, False, False, 0)

        # Carte Autostart cliquable
        self.switch_autostart = Gtk.Switch()
        self.switch_autostart.set_active(is_autostart_active())
        self.switch_autostart.connect("notify::active", self.on_autostart_toggled)
        card_auto = self.create_card(
            _("Automatic launch on startup"),
            _("Discreetly starts TiMonde in the background as soon as your graphical session opens."),
            self.switch_autostart
        )
        page.pack_start(card_auto, False, False, 0)

        # 2. Section Informations Système (Lecture Seule)
        lbl_info = Gtk.Label()
        lbl_info.set_markup("<b>" + _("DETECTED ENVIRONMENT (READ ONLY)") + "</b>")
        lbl_info.set_halign(Gtk.Align.START)
        lbl_info.get_style_context().add_class("section-separator-title")
        page.pack_start(lbl_info, False, False, 4)

        # Version installée et exécutable actif
        timonde_bin = shutil.which("timonde") or os.path.expanduser("~/.local/bin/timonde")
        card_version = self.create_info_row(
            _("TiMonde version"),
            f"{_('Installed binary:')} {timonde_bin}",
            f"v{TIMONDE_VERSION}"
        )
        page.pack_start(card_version, False, False, 0)

        # Langue détectée
        env_lang = os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or "fr_FR.UTF-8"
        clean_lang = env_lang.split(".")[0]
        card_lang = self.create_info_row(
            _("System language"),
            _("Automatic detection according to your Linux locale settings."),
            f"{clean_lang}"
        )
        page.pack_start(card_lang, False, False, 0)

        # Bureau graphique & Intégration
        desktop_raw = os.environ.get("XDG_CURRENT_DESKTOP") or os.environ.get("DESKTOP_SESSION") or "Linux"
        session_type = (os.environ.get("XDG_SESSION_TYPE") or "x11").upper()
        env_badge = f"{desktop_raw} ({session_type})"
        card_desktop = self.create_info_row(
            _("Desktop environment & Tray"),
            _("Native integration in notification tray via StatusNotifierItem / XEmbed."),
            env_badge
        )
        page.pack_start(card_desktop, False, False, 0)

        # Détection proactive d'intégration GNOME (si AppIndicator est manquant)
        try:
            import gnome_tray_helper
            if gnome_tray_helper.is_gnome_shell() and not gnome_tray_helper.is_appindicator_active():
                helper_path = find_script("gnome_tray_helper.py")
                btn_fix = make_btn(_("Install GNOME integration"), "system-software-install-symbolic", primary=True)
                def on_install_gnome_clicked(widget):
                    if helper_path:
                        subprocess.Popen([sys.executable, helper_path, "--prompt"])
                btn_fix.connect("clicked", on_install_gnome_clicked)
                card_gnome_warning = self.create_card(
                    _("GNOME integration required"),
                    _("The AppIndicator extension is required to display the icon in GNOME top bar."),
                    btn_fix
                )
                page.pack_start(card_gnome_warning, False, False, 0)
        except Exception:
            pass

        # Détection proactive Cinnamon (Harmonisation Clic Gauche / Droit)
        is_cinnamon = "cinnamon" in desktop_raw.lower() or os.path.isdir(os.path.expanduser("~/.local/share/cinnamon"))
        if is_cinnamon:
            try:
                import patch_cinnamon_status_applet
                is_active = (patch_cinnamon_status_applet.check_status() == 0)
                btn_cin = make_btn(
                    _("Active (Left & Right clicks unified)") if is_active else _("Enable Left-Click"),
                    "emblem-default" if is_active else "system-run-symbolic",
                    primary=not is_active
                )
                if is_active:
                    btn_cin.set_sensitive(False)
                else:
                    cinnamon_patch_path = find_script("patch_cinnamon_status_applet.py")
                    def on_patch_cinnamon_clicked(widget):
                         if cinnamon_patch_path:
                            res = subprocess.run([sys.executable, cinnamon_patch_path, "--user"], timeout=10.0)
                            if res.returncode == 0:
                                update_btn_content(widget, _("Active (Left & Right clicks unified)"), "emblem-default")
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

        self.stack.add_titled(page, "general", _("Preferences"))

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
            status = _("enabled") if active else _("disabled")
            self.show_feedback(f"{_("Automatic startup")} {status}.")
        else:
            self.show_feedback(_("Error modifying autostart."), is_error=True)

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
                self.reorder_view.preview_player.stop(silent=True, sync=True)
        if hasattr(self, "discover_view") and self.discover_view:
            if hasattr(self.discover_view, "preview_player") and self.discover_view.preview_player:
                self.discover_view.preview_player.stop(silent=True, sync=True)
            self.discover_view.shutdown()
        # Transmettre le résultat JSON sur stdout à destination de TiMonde en Rust
        output = {"reload": self.has_modifications}
        print(json.dumps(output), flush=True)
        if Gtk.main_level() > 0:
            Gtk.main_quit()


def main():
    bookmarks_path = sys.argv[1] if len(sys.argv) > 1 else None
    win = SettingsWindow(bookmarks_path)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
