#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Interface GTK3 interactive pour organiser les radios et groupes de TiMonde en arborescence hiérarchique.
- Navigation en arborescence naturelle (Gtk.TreeStore) : déploiement/repli des dossiers, sous-dossiers et radios.
- Affichage direct des radios sans groupe au premier niveau (racine).
- Actions riches : Déplacer vers... / Nouveau groupe ou sous-groupe / Modifier / Insérer séparateur / Supprimer / Écouter.
- Contrôles d'ordre : Monter / Descendre au sein du niveau parent, Tri A-Z.
- Audit et santé des flux : test de disponibilité en direct, détection des liens brisés et redirection automatique.
"""

import sys
import os

# Neutralisation inconditionnelle d'IBus pour éviter tout gel des frappes clavier sous GTK3
os.environ.pop("GTK_IM_MODULE", None)
os.environ.pop("XMODIFIERS", None)
os.environ.pop("QT_IM_MODULE", None)

import json
import html
import threading

# Module d'internationalisation & socle commun TiMonde
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from timonde_i18n import _
except ImportError:
    def _(s): return s

from timonde_common import (
    strip_unsupported_emojis,
    make_btn,
    StreamPreviewPlayer,
    update_btn_content,
    check_stream_url,
    set_window_icon,
    RepairStreamDialog,
    ContributeStationDialog,
    apply_timonde_app_css,
    status_markup,
    prompt_text_dialog,
)
try:
    from edit_station import EditStationWindow
except ImportError:
    EditStationWindow = None

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Pango, GLib


class ReorderWidget(Gtk.Box):
    def __init__(self, data, auto_check=False, embedded=False, on_save_callback=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.embedded = embedded
        self.on_save_callback = on_save_callback
        apply_timonde_app_css()

        self.data = data or []
        self.auto_check = auto_check
        self.saved = False
        self.dirty = False
        self.audit_results = {}  # url -> {"status": "online"|"offline"|"geo"|"redirect", "msg": str, "redirect": str|None}
        self.filter_broken_only = False

        self.preview_player = StreamPreviewPlayer(on_status_change=self.on_preview_status_update)

        # Alias de compatibilité
        self.vbox = self

        # 1. En-tête de navigation & Outils d'expansion / audit
        self.nav_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.vbox.pack_start(self.nav_box, False, False, 0)

        self.btn_collapse_all = make_btn(_("Collapse all"), "pan-up-symbolic", _("Collapse all groups for an overview"))
        self.btn_collapse_all.connect("clicked", lambda w: self.treeview.collapse_all())
        self.nav_box.pack_start(self.btn_collapse_all, False, False, 0)

        self.btn_expand_all = make_btn(_("Expand all"), "pan-down-symbolic", _("Expand all groups and subgroups"))
        self.btn_expand_all.connect("clicked", lambda w: self.treeview.expand_all())
        self.nav_box.pack_start(self.btn_expand_all, False, False, 0)

        self.header_title = Gtk.Label()
        self.header_title.set_halign(Gtk.Align.START)
        self.header_title.set_markup(f"<b>{_("My Radios")}</b>")
        self.nav_box.pack_start(self.header_title, True, True, 6)

        # Outils d'audit et vérification de santé des flux
        self.btn_check_streams = make_btn(_("Check streams"), "view-refresh", _("Test stream availability and locate broken links"))
        self.btn_check_streams.connect("clicked", self.on_check_streams_clicked)
        self.nav_box.pack_start(self.btn_check_streams, False, False, 0)

        self.chk_broken_only = Gtk.CheckButton(label=_("Dead links only"))
        self.chk_broken_only.set_tooltip_text(_("Display offline radio streams only"))
        self.chk_broken_only.connect("toggled", self.on_filter_broken_toggled)
        self.nav_box.pack_start(self.chk_broken_only, False, False, 0)

        self.btn_apply_redirects = make_btn(_("Apply redirects"), "system-run", _("Automatically update redirected streams to direct URL"))
        self.btn_apply_redirects.connect("clicked", self.on_apply_redirects_clicked)
        self.btn_apply_redirects.hide()
        self.nav_box.pack_start(self.btn_apply_redirects, False, False, 0)

        self.help_label = Gtk.Label()
        self.help_label.set_halign(Gtk.Align.START)
        self.help_label.set_line_wrap(True)
        self.help_label.set_markup(
            _("<small>• Expand folders <b>[▶]</b> to explore subgroups and stations.\n"
              "• Use <b>Move Up / Move Down</b> or Drag &amp; Drop to reorder.\n"
              "• Use <b>Move to...</b> to organize stations into another folder.</small>")
        )
        self.vbox.pack_start(self.help_label, False, False, 0)

        # 2. Zone centrale : Arborescence TreeView + Boutons d'actions latérales
        content_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.vbox.pack_start(content_box, True, True, 0)

        # Modèle de données TreeStore :
        # 0: type_str ("group", "station", "separator")
        # 1: nom affiché (str)
        # 2: détails/url (str markup)
        # 3: data_dict (dict)
        # 4: icon_name (str)
        # 5: font_weight (int Pango.Weight)
        self.store = Gtk.TreeStore(str, str, str, object, str, int)
        self.treeview = Gtk.TreeView(model=self.store)
        self.treeview.set_rules_hint(True)
        self.treeview.set_reorderable(True)
        self.treeview.connect("row-activated", self.on_row_activated)
        self.treeview.connect("button-press-event", self.on_treeview_button_press)
        self.treeview.get_selection().set_mode(Gtk.SelectionMode.SINGLE)
        self.treeview.get_selection().connect("changed", self.on_selection_changed)

        # Colonne 1 : Élément (avec icône et chevron d'expansion natif)
        self.col_element = Gtk.TreeViewColumn(_("Radio / Group"))
        self.col_element.set_expand(True)
        self.col_element.set_resizable(True)
        self.col_element.set_min_width(240)

        renderer_icon = Gtk.CellRendererPixbuf()
        self.col_element.pack_start(renderer_icon, False)
        self.col_element.add_attribute(renderer_icon, "icon-name", 4)

        self.renderer_name = Gtk.CellRendererText()
        self.renderer_name.set_property("ellipsize", Pango.EllipsizeMode.END)
        self.col_element.pack_start(self.renderer_name, True)
        self.col_element.add_attribute(self.renderer_name, "text", 1)
        self.col_element.add_attribute(self.renderer_name, "weight", 5)

        self.treeview.append_column(self.col_element)
        self.treeview.set_expander_column(self.col_element)

        # Colonne 2 : Détails / Statut en ligne
        renderer_info = Gtk.CellRendererText()
        renderer_info.set_property("xalign", 1.0)
        renderer_info.set_property("ellipsize", Pango.EllipsizeMode.MIDDLE)
        self.col_info = Gtk.TreeViewColumn(_("Details / Status"), renderer_info, markup=2)
        self.col_info.set_resizable(True)
        self.col_info.set_min_width(140)
        self.treeview.append_column(self.col_info)

        # Défilement
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_shadow_type(Gtk.ShadowType.IN)
        scrolled.add(self.treeview)
        content_box.pack_start(scrolled, True, True, 0)

        # Boutons latéraux d'actions rapides
        side_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        content_box.pack_start(side_box, False, False, 0)

        self.btn_preview = make_btn(_("Listen"), "media-playback-start", _("Preview selected radio stream"))
        self.btn_preview.connect("clicked", self.on_preview_clicked)
        side_box.pack_start(self.btn_preview, False, False, 0)

        self.btn_add_station = make_btn(_("Add station"), "list-add", _("Add a new station to this group or to root"))
        self.btn_add_station.connect("clicked", self.on_add_station_clicked)
        side_box.pack_start(self.btn_add_station, False, False, 0)

        self.btn_new_group = make_btn(_("New group"), "folder-new", _("Create a new group or subgroup (Ctrl+N)"))
        self.btn_new_group.connect("clicked", self.on_create_group_clicked)
        side_box.pack_start(self.btn_new_group, False, False, 0)

        self.btn_move_to = make_btn(_("Move to..."), "go-jump", _("Move selection to another group (Ctrl+M)"))
        self.btn_move_to.connect("clicked", self.on_move_to_clicked)
        side_box.pack_start(self.btn_move_to, False, False, 0)

        sep0 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        side_box.pack_start(sep0, False, False, 2)

        # Grille 2x2 compacte pour l'ordre
        grid_order = Gtk.Grid()
        grid_order.set_column_spacing(4)
        grid_order.set_row_spacing(4)
        grid_order.set_column_homogeneous(True)
        side_box.pack_start(grid_order, False, False, 0)

        btn_top = make_btn(_("Top"), "go-top", _("Move selected item to the top"))
        btn_top.connect("clicked", self.on_move_top_clicked)
        grid_order.attach(btn_top, 0, 0, 1, 1)

        btn_up = make_btn(_("Move up"), "go-up", _("Move up one rank"))
        btn_up.connect("clicked", self.on_move_up_clicked)
        grid_order.attach(btn_up, 1, 0, 1, 1)

        btn_down = make_btn(_("Move down"), "go-down", _("Move down one rank"))
        btn_down.connect("clicked", self.on_move_down_clicked)
        grid_order.attach(btn_down, 0, 1, 1, 1)

        btn_sort = make_btn("A-Z", "view-sort-ascending", _("Sort sibling items alphabetically"))
        btn_sort.connect("clicked", self.on_sort_az_clicked)
        grid_order.attach(btn_sort, 1, 1, 1, 1)

        sep1 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        side_box.pack_start(sep1, False, False, 2)

        self.btn_add_sep = make_btn(_("Separator"), "format-line-spacing", _("Insert a separator or header"))
        self.btn_add_sep.connect("clicked", self.on_add_separator_clicked)
        side_box.pack_start(self.btn_add_sep, False, False, 0)

        btn_edit = make_btn(_("Edit"), "document-edit", _("Edit selected name, URL or group (F2)"))
        btn_edit.connect("clicked", self.on_edit_clicked)
        side_box.pack_start(btn_edit, False, False, 0)

        self.btn_repair = make_btn(_("Repair stream..."), "system-search", _("Search Radio-Browser for a working replacement stream"))
        self.btn_repair.connect("clicked", self.on_repair_stream_clicked)
        side_box.pack_start(self.btn_repair, False, False, 0)

        self.btn_contribute = make_btn(_("Contribute to Radio-Browser..."), "network-server", _("Check or contribute selected station to Radio-Browser"))
        self.btn_contribute.connect("clicked", self.on_contribute_station_clicked)
        side_box.pack_start(self.btn_contribute, False, False, 0)

        btn_del = make_btn(_("Delete"), "edit-delete", _("Delete selected item or group (Del)"))
        btn_del.connect("clicked", self.on_delete_clicked)
        side_box.pack_start(btn_del, False, False, 0)

        # 3. Feedback / Notification visuelle
        self.lbl_feedback = Gtk.Label(label="")
        self.lbl_feedback.set_halign(Gtk.Align.START)
        self.vbox.pack_start(self.lbl_feedback, False, False, 0)

        # 4. Barre d'actions inférieure
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.vbox.pack_start(btn_box, False, False, 0)

        if not self.embedded:
            btn_cancel = make_btn(_("Cancel"), "process-stop")
            btn_cancel.connect("clicked", self.on_cancel_clicked)
            btn_box.pack_start(btn_cancel, False, False, 0)

        self.btn_export_csv = make_btn(_("Export to CSV"), "document-save-as", _("Export all stations to CSV spreadsheet format"))
        self.btn_export_csv.connect("clicked", lambda w: self.on_export_csv_clicked())
        btn_box.pack_start(self.btn_export_csv, False, False, 0)

        spacer = Gtk.Box()
        btn_box.pack_start(spacer, True, True, 0)

        self.lbl_dirty_status = Gtk.Label()
        self.lbl_dirty_status.set_valign(Gtk.Align.CENTER)
        self.set_dirty(False)
        btn_box.pack_start(self.lbl_dirty_status, False, False, 6)

        save_label = _("Save now") if self.embedded else _("Save and reload")
        self.btn_save = make_btn(save_label, "document-save")
        self.btn_save.get_style_context().add_class("suggested-action")
        self.btn_save.connect("clicked", self.on_save_clicked)
        btn_box.pack_start(self.btn_save, False, False, 0)

        # Peuple initialement le TreeStore (vue repliée par défaut pour vision d'ensemble nette)
        self.populate_tree()
        self.treeview.collapse_all()

    # -------------------------------------------------------------------------
    # Gestion d'état et persistance continue (anti-perte de données)
    # -------------------------------------------------------------------------
    def set_dirty(self, is_dirty=True):
        self.dirty = is_dirty
        if hasattr(self, "lbl_dirty_status") and self.lbl_dirty_status:
            if is_dirty:
                self.lbl_dirty_status.set_markup(status_markup(_("Unsaved changes"), kind="warn", with_bullet=True, bold=True))
            else:
                self.lbl_dirty_status.set_markup(f"<small><span alpha='65%'>{html.escape(_('All changes saved'))}</span></small>")

    def flush_pending(self):
        """Sauvegarde immédiatement les modifications en attente via on_save_callback si dirty."""
        if getattr(self, "dirty", False) and self.on_save_callback:
            self.data = self.serialize_tree()
            self.on_save_callback(self.data)
            self.set_dirty(False)
            return True
        return False

    def get_parent_window(self):
        toplevel = self.get_toplevel()
        if toplevel and toplevel.is_toplevel() and isinstance(toplevel, Gtk.Window):
            return toplevel
        return None

    def show_feedback(self, text, is_success=True):
        color = "#27ae60" if is_success else "#e67e22"
        self.lbl_feedback.set_markup(f"<span foreground='{color}'><b>{html.escape(text or '')}</b></span>")

    # -------------------------------------------------------------------------
    # Peuple et sérialisation récursive TreeStore <-> self.data
    # -------------------------------------------------------------------------
    def is_item_separator(self, item):
        if not item or not isinstance(item, dict):
            return False
        if item.get("is_separator"):
            return True
        url = item.get("url", "")
        name = item.get("name", "")
        if (url == "" or url == "---") and ("stations" not in item):
            return True
        if name.startswith("[separator") or name == "---" or name == "separator - - -":
            return True
        return False

    def populate_tree(self, select_path=None):
        self.store.clear()
        group_iters = {}

        for item in self.data:
            name = item.get("name", "")
            is_sep = self.is_item_separator(item)
            stations = item.get("stations", [])

            # 1. Radios orphelines sans groupe au premier niveau
            if name == "[ / ] (Racine — Sans groupe)":
                for st in stations:
                    self._append_leaf(None, st)
                continue

            # 2. Séparateur global à la racine
            if is_sep and not stations:
                title = name.strip("-").strip()
                disp = f"─── {title} ───" if title else "────────────────────────"
                self.store.append(None, ["separator", disp, _("— Separator —"), item, "format-line-spacing", Pango.Weight.NORMAL])
                continue

            # 3. Groupes et arborescences de sous-groupes (ex: "Europe/France/Bretagne")
            parts = [p.strip() for p in name.split("/") if p.strip()]
            current_path = ""
            parent_iter = None
            for p in parts:
                current_path = f"{current_path}/{p}" if current_path else p
                if current_path not in group_iters:
                    grp_iter = self.store.append(
                        parent_iter,
                        ["group", p, "", {"name": current_path, "stations": []}, "folder", Pango.Weight.BOLD]
                    )
                    group_iters[current_path] = grp_iter
                parent_iter = group_iters[current_path]

            # Mettre à jour le dossier feuille avec ses stations
            self.store.set_value(parent_iter, 3, item)
            nb_radios = sum(1 for s in stations if not self.is_item_separator(s))
            unit = _("radios") if nb_radios > 1 else _("radio")
            self.store.set_value(parent_iter, 2, f"{nb_radios} {unit}")

            for st in stations:
                self._append_leaf(parent_iter, st)

        if select_path:
            try:
                self.treeview.get_selection().select_path(select_path)
                self.treeview.scroll_to_cell(select_path, None, False, 0.0, 0.0)
            except Exception:
                pass

    def format_station_details(self, st):
        """Formate le libellé de la colonne Détails/Statut pour une station (pays ou statut de flux)."""
        if not st or not isinstance(st, dict):
            return ""
        url = st.get("url", "")
        audit = self.audit_results.get(url)
        if audit:
            st_val = audit.get("status")
            st_msg = audit.get("msg", "")
            if st_val == "online":
                return status_markup(_("[OK] Live"), kind="ok")
            elif st_val == "offline":
                return status_markup(f"{_('[!] Dead link')} ({st_msg})", kind="error", bold=True)
            elif st_val == "redirect":
                return status_markup(_("[~] Redirected"), kind="warn")
            elif st_val == "geo":
                return status_markup(_("[?] Geo-restricted"), kind="geo")
            else:
                return html.escape(st_msg)

        country_tag = (st.get("country") or "").strip().upper()
        if country_tag:
            return f"[{country_tag}]"
        elif len(url) > 28:
            return url[:25] + "..."
        else:
            return url

    def _append_leaf(self, parent_iter, st):
        if self.is_item_separator(st):
            if self.filter_broken_only:
                return
            title = st.get("name", "").strip()
            disp = f"─── {title} ───" if title else "────────────────────────"
            self.store.append(parent_iter, ["separator", disp, _("— Separator —"), st, "format-line-spacing", Pango.Weight.NORMAL])
        else:
            url = st.get("url", "")
            audit = self.audit_results.get(url)
            if self.filter_broken_only and (not audit or audit.get("status") != "offline"):
                return

            disp = strip_unsupported_emojis(st.get("name", "")) or st.get("name", "")
            details = self.format_station_details(st)
            self.store.append(parent_iter, ["station", disp, details, st, "audio-x-generic", Pango.Weight.NORMAL])

    def serialize_tree(self):
        """Parcourt récursivement le TreeStore et reconstruit la liste self.data conforme XML."""
        payload = []
        root_stations = []

        def walk_level(parent_iter, group_prefix):
            nonlocal payload, root_stations
            tree_iter = self.store.iter_children(parent_iter)
            while tree_iter is not None:
                t = self.store.get_value(tree_iter, 0)
                nom = self.store.get_value(tree_iter, 1)
                data_obj = self.store.get_value(tree_iter, 3)

                if t == "group":
                    grp_name = f"{group_prefix}/{nom}" if group_prefix else nom
                    child_iter = self.store.iter_children(tree_iter)
                    stations = []
                    while child_iter is not None:
                        c_type = self.store.get_value(child_iter, 0)
                        c_data = self.store.get_value(child_iter, 3)
                        if c_type in ("station", "separator"):
                            stations.append(c_data)
                        child_iter = self.store.iter_next(child_iter)

                    payload.append({
                        "name": grp_name,
                        "stations": stations,
                        "is_separator": False,
                    })
                    # Récursion pour explorer d'éventuels sous-groupes
                    walk_level(tree_iter, grp_name)

                elif t in ("station", "separator") and parent_iter is None:
                    # Station ou séparateur à la racine
                    root_stations.append(data_obj)

                tree_iter = self.store.iter_next(tree_iter)

        walk_level(None, "")
        if root_stations:
            payload.insert(0, {
                "name": "[ / ] (Racine — Sans groupe)",
                "stations": root_stations,
                "is_separator": False,
            })
        return payload

    # -------------------------------------------------------------------------
    # Sélection et Contexte
    # -------------------------------------------------------------------------
    def get_selected_node(self):
        """Retourne (type, nom, data_dict, tree_iter, parent_iter) ou (None, ...)"""
        model, paths = self.treeview.get_selection().get_selected_rows()
        if not paths:
            return None, None, None, None, None
        tree_iter = model.get_iter(paths[0])
        t = model.get_value(tree_iter, 0)
        name = model.get_value(tree_iter, 1)
        data_obj = model.get_value(tree_iter, 3)
        parent_iter = model.iter_parent(tree_iter)
        return t, name, data_obj, tree_iter, parent_iter

    def get_selected_group_name(self):
        """Retourne le chemin complet du groupe sélectionné ou du groupe parent de la radio sélectionnée, ou '' si racine."""
        node_type, name, data_obj, tree_iter, parent_iter = self.get_selected_node()
        if not tree_iter:
            return ""
        if node_type == "group":
            if isinstance(data_obj, dict):
                return data_obj.get("name", name)
            return name
        elif node_type in ("station", "separator"):
            if parent_iter:
                p_data = self.store.get_value(parent_iter, 3)
                p_name = self.store.get_value(parent_iter, 1)
                if isinstance(p_data, dict):
                    return p_data.get("name", p_name)
                return p_name
        return ""

    def get_all_group_paths(self):
        """Retourne la liste ordonnée de tous les chemins de dossiers existants dans l'arborescence."""
        groups = []
        def collect_groups(p_iter, prefix):
            c = self.store.iter_children(p_iter)
            while c is not None:
                if self.store.get_value(c, 0) == "group":
                    g_name = self.store.get_value(c, 1)
                    full = f"{prefix}/{g_name}" if prefix else g_name
                    groups.append(full)
                    collect_groups(c, full)
                c = self.store.iter_next(c)
        collect_groups(None, "")
        return groups

    def find_group_iter(self, group_path):
        """Trouve l'itérateur TreeIter d'un groupe selon son chemin complet (ex: 'Europe/France') ou None si racine/introuvable."""
        clean_path = (group_path or "").strip().strip("/")
        if not clean_path or clean_path in ("/", "[ / ] (Racine — Sans groupe)"):
            return None

        def search_level(p_iter, prefix):
            c = self.store.iter_children(p_iter)
            while c is not None:
                if self.store.get_value(c, 0) == "group":
                    g_name = self.store.get_value(c, 1)
                    full = f"{prefix}/{g_name}" if prefix else g_name
                    if full == clean_path:
                        return c
                    sub_res = search_level(c, full)
                    if sub_res:
                        return sub_res
                c = self.store.iter_next(c)
            return None

        return search_level(None, "")

    @property
    def current_group_idx(self):
        """Rétrocompatibilité : None car la sélection est désormais arborescente."""
        return None

    def update_view(self):
        """Alias pour rafraîchir l'arbre complet à partir de self.data."""
        self.populate_tree()
        self.treeview.collapse_all()

    def on_selection_changed(self, selection):
        node_type, name, data_obj, tree_iter, parent_iter = self.get_selected_node()
        is_station = node_type == "station"
        self.btn_preview.set_sensitive(is_station)
        self.btn_repair.set_sensitive(is_station)

    def on_row_activated(self, treeview, path, column):
        node_type, name, data_obj, tree_iter, parent_iter = self.get_selected_node()
        if node_type == "group":
            if self.treeview.row_expanded(path):
                self.treeview.collapse_row(path)
            else:
                self.treeview.expand_row(path, False)
        elif node_type == "station":
            self.on_edit_clicked(None)

    def on_treeview_button_press(self, treeview, event):
        if event.button == 3:  # Clic droit
            pth = treeview.get_path_at_pos(int(event.x), int(event.y))
            if pth:
                path, col, _x, _y = pth
                sel = treeview.get_selection()
                sel.unselect_all()
                sel.select_path(path)
                self.show_context_menu(event)
                return True
        return False

    def show_context_menu(self, event):
        menu = Gtk.Menu()
        node_type, name, data_obj, tree_iter, parent_iter = self.get_selected_node()

        if node_type == "station":
            if data_obj and data_obj.get("url"):
                clean_url = data_obj.get("url", "").strip()
                is_playing_this = (self.preview_player.is_playing and self.preview_player.current_url == clean_url)
                lbl_audio = _("Stop playback") if is_playing_this else _("Play this station")
                item_audio = Gtk.MenuItem(label=lbl_audio)
                item_audio.connect("activate", lambda w: self.on_preview_clicked(None))
                menu.append(item_audio)
                menu.append(Gtk.SeparatorMenuItem())

            item_edit = Gtk.MenuItem(label=_("Edit station..."))
            item_edit.connect("activate", self.on_edit_clicked)
            menu.append(item_edit)

            item_move = Gtk.MenuItem(label=_("Move to another group..."))
            item_move.connect("activate", self.on_move_to_clicked)
            menu.append(item_move)

            item_repair = Gtk.MenuItem(label=_("Repair stream..."))
            item_repair.connect("activate", self.on_repair_stream_clicked)
            menu.append(item_repair)

            item_contrib = Gtk.MenuItem(label=_("Contribute to Radio-Browser..."))
            item_contrib.connect("activate", lambda w: self.on_contribute_station_clicked(None))
            menu.append(item_contrib)

            item_del = Gtk.MenuItem(label=_("Delete this station"))
            item_del.connect("activate", self.on_delete_clicked)
            menu.append(item_del)

        elif node_type == "group":
            item_add = Gtk.MenuItem(label=_("Add station here..."))
            item_add.connect("activate", self.on_add_station_clicked)
            menu.append(item_add)

            item_sub = Gtk.MenuItem(label=_("New subgroup here..."))
            item_sub.connect("activate", self.on_create_group_clicked)
            menu.append(item_sub)

            item_rename = Gtk.MenuItem(label=_("Rename group..."))
            item_rename.connect("activate", self.on_edit_clicked)
            menu.append(item_rename)

            item_del = Gtk.MenuItem(label=_("Delete group and stations"))
            item_del.connect("activate", self.on_delete_clicked)
            menu.append(item_del)

        else:
            item_new_g = Gtk.MenuItem(label=_("New group..."))
            item_new_g.connect("activate", self.on_create_group_clicked)
            menu.append(item_new_g)

            item_add_st = Gtk.MenuItem(label=_("Add station..."))
            item_add_st.connect("activate", self.on_add_station_clicked)
            menu.append(item_add_st)

        menu.show_all()
        menu.popup(None, None, None, None, event.button, event.time)

    # -------------------------------------------------------------------------
    # Raccourcis Clavier
    # -------------------------------------------------------------------------
    def on_key_press_event(self, widget, event):
        keyname = Gdk.keyval_name(event.keyval)
        state = event.state
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)

        if keyname == "Delete":
            self.on_delete_clicked(None)
            return True
        elif keyname == "F2":
            self.on_edit_clicked(None)
            return True
        elif (ctrl and keyname in ("n", "N")) or (keyname in ("n", "N") and not ctrl and not self.treeview.is_focus()):
            self.on_create_group_clicked(None)
            return True
        elif (ctrl and keyname in ("m", "M")) or (keyname in ("m", "M") and not ctrl and not self.treeview.is_focus()):
            self.on_move_to_clicked(None)
            return True
        return False

    # -------------------------------------------------------------------------
    # Actions Métier : Ajout, Déplacement, Édition, Suppression
    # -------------------------------------------------------------------------
    def on_create_group_clicked(self, widget):
        node_type, name, data_obj, tree_iter, parent_iter = self.get_selected_node()
        parent_group = name if node_type == "group" else ""

        dialog = Gtk.Dialog(
            title=_("Create a new group"),
            transient_for=self.get_parent_window(),
            flags=Gtk.DialogFlags.MODAL
        )
        dialog.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        dialog.add_button(_("Create"), Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)

        box = dialog.get_content_area()
        box.set_spacing(10)
        box.set_border_width(12)

        lbl = Gtk.Label(label="<b>" + _("Name of the new group:") + "</b>")
        lbl.set_use_markup(True)
        lbl.set_halign(Gtk.Align.START)
        box.pack_start(lbl, False, False, 0)

        entry = Gtk.Entry()
        entry.set_width_chars(35)
        entry.set_activates_default(True)
        box.pack_start(entry, False, False, 0)

        chk_subgroup = None
        if parent_group:
            chk_subgroup = Gtk.CheckButton(label=f"{_('Create as a subgroup inside')} « {parent_group} »")
            chk_subgroup.set_active(True)
            box.pack_start(chk_subgroup, False, False, 0)

        def on_create_response(dlg, response):
            new_name = entry.get_text().strip()
            as_sub = chk_subgroup.get_active() if chk_subgroup else False
            dlg.destroy()
            if response == Gtk.ResponseType.OK and new_name:
                target_parent = tree_iter if (as_sub and node_type == "group") else None
                new_iter = self.store.append(
                    target_parent,
                    ["group", new_name, f"0 {_('radios')}", {"name": new_name, "stations": []}, "folder", Pango.Weight.BOLD]
                )
                self.set_dirty(True)
                path = self.store.get_path(new_iter)
                self.treeview.get_selection().select_path(path)
                self.show_feedback(f"{_('Group created:')} « {new_name} »")

        dialog.connect("response", on_create_response)
        dialog.show_all()

    def on_add_station_clicked(self, widget):
        node_type, name, data_obj, tree_iter, parent_iter = self.get_selected_node()
        current_grp = name if node_type == "group" else ""
        if EditStationWindow is None:
            self.show_feedback(_("Station editor unavailable."), is_success=False)
            return

        def on_station_added(val):
            if val and isinstance(val, dict):
                target_parent = tree_iter if node_type == "group" else parent_iter
                self._append_leaf(target_parent, val)
                self.set_dirty(True)
                self.show_feedback(f"{_('Station added:')} « {val.get('name', '')} »")

        dlg = EditStationWindow(
            mode="add",
            current_group=current_grp,
            available_groups=self.get_all_group_paths(),
            parent_window=self.get_parent_window(),
            standalone=False,
            on_done_callback=on_station_added
        )
        dlg.set_transient_for(self.get_parent_window())
        dlg.set_modal(True)
        dlg.show_all()

    def on_add_separator_clicked(self, widget):
        node_type, name, data_obj, tree_iter, parent_iter = self.get_selected_node()

        def on_sep_done(txt):
            if txt is not None:
                disp = f"─── {txt} ───" if txt else "────────────────────────"
                sep_obj = {"name": txt, "is_separator": True, "url": ""}
                target_parent = tree_iter if node_type == "group" else parent_iter
                self.store.append(target_parent, ["separator", disp, _("— Separator —"), sep_obj, "format-line-spacing", Pango.Weight.NORMAL])
                self.set_dirty(True)

        prompt_text_dialog(
            parent_window=self.get_parent_window(),
            title=_("Insert separator"),
            label_text=_("Optional title for this separator (leave blank for a simple line):"),
            ok_label=_("Insert"),
            callback=on_sep_done
        )

    def on_edit_clicked(self, widget):
        node_type, name, data_obj, tree_iter, parent_iter = self.get_selected_node()
        if not tree_iter:
            return

        if node_type == "group":
            def on_rename_done(new_n):
                if new_n:
                    self.store.set_value(tree_iter, 1, new_n)
                    if isinstance(data_obj, dict):
                        data_obj["name"] = new_n
                    self.set_dirty(True)
                    self.show_feedback(f"{_('Group renamed:')} « {new_n} »")

            prompt_text_dialog(
                parent_window=self.get_parent_window(),
                title=_("Rename group"),
                label_text=_("New name for group:"),
                default_text=name,
                ok_label=_("Save"),
                callback=on_rename_done
            )

        elif node_type == "station":
            if EditStationWindow is None:
                return

            current_grp = self.get_selected_group_name() or ""

            def on_station_edited(val):
                if val and isinstance(val, dict):
                    if val.get("action") == "delete":
                        self.store.remove(tree_iter)
                        self.set_dirty(True)
                        self.show_feedback(f"{_('Station deleted:')} « {name} »")
                        return

                    disp = strip_unsupported_emojis(val.get("name", "")) or val.get("name", "")
                    details = self.format_station_details(val)
                    self.store.set_value(tree_iter, 1, disp)
                    self.store.set_value(tree_iter, 2, details)
                    self.store.set_value(tree_iter, 3, val)
                    self.set_dirty(True)
                    self.show_feedback(f"{_('Station updated:')} « {val.get('name', '')} »")

                    # Si le groupe de la station a été modifié dans le dialogue d'édition
                    new_grp = (val.get("group") or "").strip().strip("/")
                    if new_grp != current_grp:
                        target_iter = self.find_group_iter(new_grp)
                        if new_grp and not target_iter:
                            # Reconstruire proprement si le groupe cible n'existe pas encore dans l'arbre
                            self.data = self.serialize_tree()
                            self.populate_tree()
                            self.set_dirty(True)
                        else:
                            row_data = [self.store.get_value(tree_iter, col) for col in range(6)]
                            self.store.remove(tree_iter)
                            new_node = self.store.append(target_iter, row_data)
                            if target_iter:
                                self.treeview.expand_row(self.store.get_path(target_iter), False)
                            self.treeview.get_selection().select_iter(new_node)

            dlg = EditStationWindow(
                mode="edit",
                station_data=data_obj,
                current_group=current_grp,
                available_groups=self.get_all_group_paths(),
                parent_window=self.get_parent_window(),
                standalone=False,
                on_done_callback=on_station_edited
            )
            dlg.set_transient_for(self.get_parent_window())
            dlg.set_modal(True)
            dlg.show_all()

    def _count_stations_in_node(self, node_iter):
        """Compte récursivement les stations contenues dans un groupe et ses sous-groupes."""
        count = 0
        c = self.store.iter_children(node_iter)
        while c is not None:
            t = self.store.get_value(c, 0)
            if t == "station":
                count += 1
            elif t == "group":
                count += self._count_stations_in_node(c)
            c = self.store.iter_next(c)
        return count

    def on_delete_clicked(self, widget):
        node_type, name, data_obj, tree_iter, parent_iter = self.get_selected_node()
        if not tree_iter:
            return

        is_group_with_stations = False
        nb_stations = 0
        if node_type == "group":
            nb_stations = self._count_stations_in_node(tree_iter)
            if nb_stations > 0:
                is_group_with_stations = True
                unit = _("stations") if nb_stations > 1 else _("station")
                warning_text = _("Warning: this group contains {count} {unit} that will also be deleted.").format(
                    count=nb_stations, unit=unit
                )
                msg = f"<b>{warning_text}</b>\n\n" + _("Are you sure you want to delete « {name} » ?").format(name=name)
            else:
                msg = _("Are you sure you want to delete « {name} » ?").format(name=name)
        else:
            msg = _("Are you sure you want to delete « {name} » ?").format(name=name)

        dialog = Gtk.MessageDialog(
            transient_for=self.get_parent_window(),
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.WARNING if is_group_with_stations else Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=_("Confirm deletion")
        )
        dialog.set_markup(msg)
        def on_delete_response(dlg, resp):
            dlg.destroy()
            if resp == Gtk.ResponseType.YES:
                self.store.remove(tree_iter)
                self.set_dirty(True)
                self.show_feedback(f"{_('Deleted:')} « {name} »")

        dialog.connect("response", on_delete_response)
        dialog.show_all()

    # -------------------------------------------------------------------------
    # Réordonnancement : Monter / Descendre / Tri A-Z
    # -------------------------------------------------------------------------
    def on_move_up_clicked(self, widget):
        node_type, name, data_obj, tree_iter, parent_iter = self.get_selected_node()
        if not tree_iter:
            return
        path = self.store.get_path(tree_iter)
        indices = path.get_indices()
        if indices[-1] > 0:
            indices[-1] -= 1
            prev_path = Gtk.TreePath.new_from_indices(indices)
            prev_iter = self.store.get_iter(prev_path)
            self.store.swap(tree_iter, prev_iter)
            self.set_dirty(True)
            self.treeview.get_selection().select_path(prev_path)

    def on_move_down_clicked(self, widget):
        node_type, name, data_obj, tree_iter, parent_iter = self.get_selected_node()
        if not tree_iter:
            return
        next_iter = self.store.iter_next(tree_iter)
        if next_iter:
            self.store.swap(tree_iter, next_iter)
            self.set_dirty(True)
            path = self.store.get_path(tree_iter)
            self.treeview.get_selection().select_path(path)

    def on_move_top_clicked(self, widget):
        node_type, name, data_obj, tree_iter, parent_iter = self.get_selected_node()
        if not tree_iter:
            return
        path = self.store.get_path(tree_iter)
        indices = path.get_indices()
        if indices[-1] > 0:
            first_path = Gtk.TreePath.new_from_indices(indices[:-1] + [0])
            first_iter = self.store.get_iter(first_path)
            self.store.move_before(tree_iter, first_iter)
            self.set_dirty(True)
            self.treeview.get_selection().select_path(first_path)

    def on_sort_az_clicked(self, widget):
        node_type, name, data_obj, tree_iter, parent_iter = self.get_selected_node()
        # Si un groupe est sélectionné, on trie le contenu de ce groupe
        # Si une station/séparateur est sélectionné, on trie le groupe parent contenant cette station
        # Si rien n'est sélectionné, on trie le niveau racine
        if node_type == "group":
            target_parent = tree_iter
            target_name = name
        elif node_type in ("station", "separator") and parent_iter is not None:
            target_parent = parent_iter
            p_data = self.store.get_value(parent_iter, 3)
            p_name = self.store.get_value(parent_iter, 1)
            target_name = p_data.get("name", p_name) if isinstance(p_data, dict) else p_name
        else:
            target_parent = None
            target_name = _("Root")

        children = []
        c = self.store.iter_children(target_parent)
        while c is not None:
            row_data = [self.store.get_value(c, col) for col in range(6)]
            sub_children = self._copy_sub_tree(c)
            children.append((row_data, sub_children))
            c = self.store.iter_next(c)

        if not children:
            self.show_feedback(_("No items to sort in this group."), is_success=False)
            return

        # Tri par type (dossiers en premier, puis radios par ordre alphabétique insensible à la casse)
        def sort_key(item):
            row = item[0]
            is_grp = 0 if row[0] == "group" else (2 if row[0] == "separator" else 1)
            return (is_grp, row[1].lower())

        children.sort(key=sort_key)

        # Reconstruire le niveau ciblé
        c = self.store.iter_children(target_parent)
        while c is not None:
            self.store.remove(c)
            c = self.store.iter_children(target_parent)

        for row_data, sub_children in children:
            new_c = self.store.append(target_parent, row_data)
            self._restore_sub_tree(new_c, sub_children)

        self.set_dirty(True)

        # Maintenir le groupe trié déployé et sélectionné dans la vue
        if target_parent is not None:
            target_path = self.store.get_path(target_parent)
            self.treeview.expand_row(target_path, False)
            self.treeview.get_selection().select_path(target_path)
            self.treeview.scroll_to_cell(target_path, None, False, 0.0, 0.0)
            self.show_feedback(f"{_('Sorted alphabetically:')} « {target_name} »")
        else:
            self.show_feedback(_("Root items sorted alphabetically."))

    def _copy_sub_tree(self, parent_iter):
        res = []
        c = self.store.iter_children(parent_iter)
        while c is not None:
            row = [self.store.get_value(c, col) for col in range(6)]
            sub = self._copy_sub_tree(c)
            res.append((row, sub))
            c = self.store.iter_next(c)
        return res

    def _restore_sub_tree(self, parent_iter, sub_list):
        for row, sub in sub_list:
            new_iter = self.store.append(parent_iter, row)
            self._restore_sub_tree(new_iter, sub)

    # -------------------------------------------------------------------------
    # Déplacement vers un autre groupe
    # -------------------------------------------------------------------------
    def on_move_to_clicked(self, widget):
        node_type, name, data_obj, tree_iter, parent_iter = self.get_selected_node()
        if not tree_iter or node_type != "station":
            self.show_feedback(_("Please select a radio station to move."), is_success=False)
            return

        # Lister tous les groupes disponibles + la racine
        groups = [("/", _("[ / ] Root (Without group)"))] + [(g, g) for g in self.get_all_group_paths()]

        dialog = Gtk.Dialog(
            title=_("Move to another group"),
            transient_for=self.get_parent_window(),
            flags=Gtk.DialogFlags.MODAL
        )
        dialog.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        dialog.add_button(_("Move"), Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)

        box = dialog.get_content_area()
        box.set_spacing(10)
        box.set_border_width(12)

        lbl = Gtk.Label(label="<b>" + _("Select the target destination:") + "</b>")
        lbl.set_use_markup(True)
        lbl.set_halign(Gtk.Align.START)
        box.pack_start(lbl, False, False, 0)

        combo = Gtk.ComboBoxText()
        for path_key, label_str in groups:
            combo.append(path_key, label_str)
        combo.set_active(0)
        box.pack_start(combo, False, False, 0)

        def on_move_response(dlg, res):
            target_path = combo.get_active_id()
            dlg.destroy()
            if res == Gtk.ResponseType.OK and target_path:
                target_iter = self.find_group_iter(target_path)
                row_data = [self.store.get_value(tree_iter, col) for col in range(6)]
                self.store.remove(tree_iter)
                new_iter = self.store.append(target_iter, row_data)
                self.set_dirty(True)
                self.treeview.get_selection().select_iter(new_iter)
                self.show_feedback(f"{_('Station moved to')} « {target_path} »")

        dialog.connect("response", on_move_response)
        dialog.show_all()

    # -------------------------------------------------------------------------
    # Lecture & Vérification des flux
    # -------------------------------------------------------------------------
    def on_preview_status_update(self, is_playing, url, message, is_error):
        update_btn_content(
            self.btn_preview,
            _("Stop") if is_playing else _("Listen"),
            "media-playback-stop" if is_playing else "media-playback-start"
        )
        self.show_feedback(message, is_success=not is_error)

    def on_preview_clicked(self, widget):
        node_type, name, data_obj, tree_iter, parent_iter = self.get_selected_node()
        if not data_obj or node_type != "station":
            return
        url = data_obj.get("url", "")
        self.preview_player.toggle(name, url)

    def on_repair_stream_clicked(self, widget):
        node_type, name, data_obj, tree_iter, parent_iter = self.get_selected_node()
        if not data_obj or node_type != "station":
            self.show_feedback(_("Please select a station to repair."))
            return

        station_name = name or data_obj.get("name", "")
        current_url = data_obj.get("url", "")
        country_id = data_obj.get("country", "")

        dlg = RepairStreamDialog(
            parent=self.get_parent_window(),
            station_name=station_name,
            current_url=current_url,
            country_code=country_id,
        )

        def on_repair_response(dialog, res):
            new_url = dialog.get_chosen_url()
            dialog.destroy()
            if res == Gtk.ResponseType.OK and new_url:
                clean_url = new_url.strip()
                data_obj["url"] = clean_url
                self.store.set_value(tree_iter, 3, data_obj)
                self.store.set_value(tree_iter, 2, self.format_station_details(data_obj))
                self.set_dirty(True)
                self.show_feedback(f"{_('Stream successfully repaired for')} « {station_name} »")

        dlg.connect("response", on_repair_response)
        dlg.show_all()
        if not isinstance(dlg, Gtk.Dialog) and hasattr(dlg, "run"):
            try:
                res = dlg.run()
                if res:
                    on_repair_response(dlg, res)
            except Exception:
                pass

    def on_contribute_station_clicked(self, widget):
        node_type, name, data_obj, tree_iter, parent_iter = self.get_selected_node()
        if not data_obj or node_type != "station":
            self.show_feedback(_("Please select a station to contribute."))
            return

        station_name = name or data_obj.get("name", "")
        current_url = data_obj.get("url", "")
        country_id = data_obj.get("country", "")

        dlg = ContributeStationDialog(
            parent=self.get_parent_window(),
            station_name=station_name,
            current_url=current_url,
            country_code=country_id
        )

        def on_contribute_response(dialog, resp):
            existing = getattr(dialog, "existing_info", None)
            dialog.destroy()
            if resp == Gtk.ResponseType.APPLY:
                # L'utilisateur a cliqué directement sur "Éditer la station" depuis le dialogue de contribution
                if existing and existing.get("countrycode"):
                    rb_cc = (existing.get("countrycode") or "").strip().upper()
                    if rb_cc and data_obj.get("country") != rb_cc:
                        data_obj["country"] = rb_cc
                        self.store.set_value(tree_iter, 2, self.format_station_details(data_obj))
                        self.store.set_value(tree_iter, 3, data_obj)
                if getattr(self, "host_window", None) and hasattr(self.host_window, "on_edit_clicked"):
                    self.host_window.on_edit_clicked(None)
                else:
                    self.on_edit_clicked(None)

        dlg.connect("response", on_contribute_response)
        dlg.show_all()
        if not isinstance(dlg, Gtk.Dialog) and hasattr(dlg, "run"):
            try:
                resp = dlg.run()
                if resp:
                    on_contribute_response(dlg, resp)
            except Exception:
                pass

    def on_check_streams_clicked(self, widget):
        from concurrent.futures import ThreadPoolExecutor

        stations_to_check = []
        def collect(p_iter):
            c = self.store.iter_children(p_iter)
            while c is not None:
                t = self.store.get_value(c, 0)
                d = self.store.get_value(c, 3)
                if t == "station" and d and d.get("url"):
                    stations_to_check.append((c, d))
                elif t == "group":
                    collect(c)
                c = self.store.iter_next(c)
        collect(None)

        if not stations_to_check:
            self.show_feedback(_("No stations to check."))
            return

        total = len(stations_to_check)
        dialog = Gtk.Dialog(
            title=_("Checking your radio stations"),
            parent=self.get_parent_window(),
            flags=Gtk.DialogFlags.MODAL,
            buttons=(_("Stop"), Gtk.ResponseType.CANCEL)
        )
        dialog.set_default_size(440, 140)
        box = dialog.get_content_area()
        box.set_spacing(10)
        box.set_border_width(14)

        lbl = Gtk.Label(label="<b>" + _("Testing live radio streams...") + "</b>")
        lbl.set_use_markup(True)
        lbl.set_halign(Gtk.Align.START)
        box.add(lbl)

        pbar = Gtk.ProgressBar()
        box.add(pbar)

        lbl_status = Gtk.Label(label=f"0 / {total} " + _("stations checked..."))
        lbl_status.set_halign(Gtk.Align.START)
        box.add(lbl_status)
        dialog.show_all()

        cancel_event = threading.Event()

        def run_checks():
            done = [0]
            done_lock = threading.Lock()

            def check_one(c_iter, s):
                if cancel_event.is_set():
                    return
                url = s.get("url", "")
                ok, msg, redir = check_stream_url(url, timeout=3.0, with_redirect=True)
                # Ignorer les redirections vers des CDN à jetons éphémères expirables (ex: ?rj-tok=..., &userConsent=...)
                if redir and any(token in redir for token in ["rj-tok=", "rj-ttl=", "userConsent", "token=", "expires="]):
                    redir = None

                if ok is True:
                    status = "redirect" if redir else "online"
                elif ok == "GEO":
                    status = "geo"
                else:
                    status = "offline"

                self.audit_results[url] = {
                    "status": status,
                    "msg": msg,
                    "redirect": redir,
                }
                with done_lock:
                    done[0] += 1
                    cur_done = done[0]
                fraction = cur_done / float(total)
                text = f"{cur_done} / {total} " + _("checked:") + f" {s.get('name', '')[:25]}"
                GLib.idle_add(pbar.set_fraction, fraction)
                GLib.idle_add(lbl_status.set_text, text)

            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = [executor.submit(check_one, c_iter, s) for c_iter, s in stations_to_check]
                for f in futures:
                    if cancel_event.is_set():
                        break
                    try:
                        f.result()
                    except Exception:
                        pass

            GLib.idle_add(on_finished)

        def on_finished():
            # Clôture propre du dialogue sans blocage de la boucle principale
            dialog.response(Gtk.ResponseType.OK)

        def on_audit_response(dlg, res):
            if res == Gtk.ResponseType.CANCEL:
                cancel_event.set()
            dlg.destroy()

            # Dépilement des résultats après la fermeture effective du dialogue
            nb_online = sum(1 for r in self.audit_results.values() if r["status"] == "online")
            nb_dead = sum(1 for r in self.audit_results.values() if r["status"] == "offline")
            nb_redir = sum(1 for r in self.audit_results.values() if r["status"] == "redirect")

            audit_done = _("Audit completed:")
            lbl_online = _("online")
            lbl_dead = _("broken")
            lbl_redir = _("redirected")
            self.show_feedback(f"{audit_done} {nb_online} {lbl_online} · {nb_dead} {lbl_dead} · {nb_redir} {lbl_redir}")

            if nb_dead > 0:
                self.chk_broken_only.show()
                self.chk_broken_only.set_label(f"{_('Dead links only')} ({nb_dead})")
                self.chk_broken_only.set_active(True)
            else:
                self.chk_broken_only.hide()
                self.chk_broken_only.set_active(False)

            if nb_redir > 0:
                self.btn_apply_redirects.show()
                update_btn_content(self.btn_apply_redirects, f"{_('Apply redirects')} ({nb_redir})", "emblem-symbolic-link")
            else:
                self.btn_apply_redirects.hide()

            # Rafraîchit les statuts dans l'arbre
            self.data = self.serialize_tree()
            self.populate_tree()
            self.treeview.expand_all()

        dialog.connect("response", on_audit_response)
        dialog.show_all()
        thread = threading.Thread(target=run_checks, daemon=True)
        thread.start()

    def on_filter_broken_toggled(self, widget):
        self.filter_broken_only = widget.get_active()
        self.data = self.serialize_tree()
        self.populate_tree()
        self.treeview.expand_all()

    def on_apply_redirects_clicked(self, widget):
        nb_applied = 0
        def apply_level(p_iter):
            nonlocal nb_applied
            c = self.store.iter_children(p_iter)
            while c is not None:
                t = self.store.get_value(c, 0)
                d = self.store.get_value(c, 3)
                if t == "station" and d:
                    u = d.get("url", "")
                    audit = self.audit_results.get(u)
                    if audit and audit.get("redirect"):
                        d["url"] = audit["redirect"]
                        self.store.set_value(c, 3, d)
                        nb_applied += 1
                elif t == "group":
                    apply_level(c)
                c = self.store.iter_next(c)
        apply_level(None)

        if nb_applied > 0:
            self.set_dirty(True)
            self.btn_apply_redirects.hide()
            self.show_feedback(f"{_('Redirects applied:')} {nb_applied} {_('stream(s) updated.')}")
            self.data = self.serialize_tree()
            self.populate_tree()

    # -------------------------------------------------------------------------
    # Clôture & Sauvegarde
    # -------------------------------------------------------------------------
    def on_save_clicked(self, widget):
        self.data = self.serialize_tree()
        self.saved = True
        self.set_dirty(False)
        if self.on_save_callback:
            self.on_save_callback(self.data)
        if not self.embedded:
            win = self.get_parent_window()
            if win:
                win.destroy()

    def on_cancel_clicked(self, widget):
        win = self.get_parent_window()
        if win:
            win.destroy()

    def on_destroy_window(self, widget=None):
        if hasattr(self, "preview_player") and self.preview_player:
            self.preview_player.stop()

    def on_export_csv_clicked(self, widget=None):
        chooser = Gtk.FileChooserDialog(
            title=_("Export stations to CSV"),
            parent=self.get_parent_window(),
            action=Gtk.FileChooserAction.SAVE,
            buttons=(_("Cancel"), Gtk.ResponseType.CANCEL, _("Export"), Gtk.ResponseType.OK)
        )
        chooser.set_current_name("mes_radios.csv")
        f_csv = Gtk.FileFilter()
        f_csv.set_name("Fichiers CSV (*.csv)")
        f_csv.add_pattern("*.csv")
        chooser.add_filter(f_csv)

        def on_export_response(dlg, res):
            path = dlg.get_filename()
            dlg.destroy()
            if res == Gtk.ResponseType.OK and path:
                if not path.endswith(".csv"):
                    path += ".csv"
                try:
                    self.data = self.serialize_tree()
                    import csv
                    with open(path, "w", encoding="utf-8", newline="") as f:
                        writer = csv.writer(f)
                        writer.writerow(["Group", "Name", "URL", "Country", "Timezone"])
                        for g in self.data:
                            grp_name = g.get("name", "")
                            for s in g.get("stations", []):
                                if not self.is_item_separator(s):
                                    writer.writerow([grp_name, s.get("name", ""), s.get("url", ""), s.get("country", ""), s.get("timezone", "")])
                    self.show_feedback(f"{_('CSV export successful:')} {os.path.basename(path)}")
                except Exception as e:
                    self.show_feedback(f"{_('Export error:')} {e}", is_success=False)

        chooser.connect("response", on_export_response)
        chooser.show_all()

    def on_backup_xml_clicked(self, widget=None):
        import shutil
        src_path = os.path.expanduser("~/.config/timonde/bookmarks.xml")
        if not os.path.isfile(src_path):
            self.show_feedback(_("No bookmarks.xml file found to backup."))
            return

        dialog = Gtk.FileChooserDialog(
            title=_("Backup my bookmarks (XML)"),
            parent=self.get_parent_window(),
            action=Gtk.FileChooserAction.SAVE,
            buttons=(_("Cancel"), Gtk.ResponseType.CANCEL, _("Save"), Gtk.ResponseType.OK),
        )
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.set_current_name("bookmarks_timonde_backup.xml")
        dialog.set_do_overwrite_confirmation(True)

        filter_xml = Gtk.FileFilter()
        filter_xml.set_name(_("XML files (*.xml)"))
        filter_xml.add_pattern("*.xml")
        dialog.add_filter(filter_xml)

        filter_all = Gtk.FileFilter()
        filter_all.set_name(_("All files (*.*)"))
        filter_all.add_pattern("*")
        dialog.add_filter(filter_all)

        def on_backup_response(dlg, res):
            chosen_path = dlg.get_filename()
            dlg.destroy()
            if res == Gtk.ResponseType.OK and chosen_path:
                if not chosen_path.lower().endswith(".xml"):
                    chosen_path += ".xml"
                try:
                    tmp_target = f"{chosen_path}.tmp"
                    shutil.copy2(src_path, tmp_target)
                    os.replace(tmp_target, chosen_path)
                    self.show_feedback(f"{_('XML backup successfully created in')} {os.path.basename(chosen_path)}")
                    msg_diag = Gtk.MessageDialog(
                        parent=self.get_parent_window(),
                        flags=Gtk.DialogFlags.MODAL,
                        type=Gtk.MessageType.INFO,
                        buttons=Gtk.ButtonsType.OK,
                        message_format=f"{_('Backup successful!')}\n\n{_('Your complete bookmarks have been saved to:')}\n{chosen_path}",
                    )
                    msg_diag.connect("response", lambda d, r: d.destroy())
                    msg_diag.show_all()
                except Exception as e:
                    err_diag = Gtk.MessageDialog(
                        parent=self.get_parent_window(),
                        flags=Gtk.DialogFlags.MODAL,
                        type=Gtk.MessageType.ERROR,
                        buttons=Gtk.ButtonsType.OK,
                        message_format=f"{_("Error during backup:")}\n{e}",
                    )
                    err_diag.connect("response", lambda d, r: d.destroy())
                    err_diag.show_all()

        dialog.connect("response", on_backup_response)
        dialog.show_all()

class ReorderWindow(Gtk.Window):
    """
    Conteneur de premier niveau autonome pour ReorderWidget (Gtk.Box).
    Utilisé en mode CLI indépendant (timonde --organize) ou pour les tests unitaires.
    """
    def __init__(self, data, auto_check=False, embedded=False, on_save_callback=None):
        super().__init__(title=_("Organize groups and stations (TiMonde)"))
        self.set_default_size(820, 600)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_border_width(12)
        set_window_icon(self)
        apply_timonde_app_css()

        self.reorder_box = ReorderWidget(
            data=data,
            auto_check=auto_check,
            embedded=embedded,
            on_save_callback=on_save_callback
        )
        self.reorder_box.host_window = self
        self.add(self.reorder_box)

        self.connect("destroy", self.on_destroy_window)
        self.connect("key-press-event", self.on_key_press_event)

    def on_edit_clicked(self, widget=None):
        return self.reorder_box.on_edit_clicked(widget)

    def __getattr__(self, name):
        reorder_box = self.__dict__.get("reorder_box")
        if reorder_box is not None:
            return getattr(reorder_box, name)
        raise AttributeError(f"'ReorderWindow' object has no attribute '{name}'")

    def on_destroy_window(self, widget=None):
        if hasattr(self, "reorder_box"):
            self.reorder_box.on_destroy_window(widget)

    def on_key_press_event(self, widget, event):
        if hasattr(self, "reorder_box"):
            return self.reorder_box.on_key_press_event(widget, event)
        return False


def main():
    try:
        raw_input = sys.stdin.read()
        if not raw_input.strip():
            sys.exit(1)
        data = json.loads(raw_input)
    except Exception as e:
        sys.stderr.write(f"Erreur lecture stdin : {e}\n")
        sys.exit(1)

    auto_check = "--check" in sys.argv or "--audit" in sys.argv
    win = ReorderWindow(data, auto_check=auto_check)
    win.show_all()
    if auto_check:
        GLib.idle_add(win.on_check_streams_clicked, None)
    Gtk.main()

    if win.saved:
        json.dump(win.data, sys.stdout, ensure_ascii=False)
        sys.stdout.flush()
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
