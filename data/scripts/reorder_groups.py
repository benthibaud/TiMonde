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
    run_timonde_cli,
    set_container_margins,
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
        self.btn_expand_all = make_btn(_("Expand all"), "pan-down-symbolic", _("Expand all groups and subgroups"))
        self.btn_expand_all.connect("clicked", lambda w: self.treeview.expand_all())
        self.header_title = Gtk.Label(halign=Gtk.Align.START)
        self.header_title.set_markup(f"<b>{_('My Radios')}</b>")
        self.btn_check_streams = make_btn(_("Check streams"), "view-refresh", _("Test stream availability and locate broken links"))
        self.btn_check_streams.connect("clicked", self.on_check_streams_clicked)
        self.chk_broken_only = Gtk.CheckButton(label=_("Dead links only"), tooltip_text=_("Display offline radio streams only"))
        self.chk_broken_only.connect("toggled", self.on_filter_broken_toggled)
        self.btn_apply_redirects = make_btn(_("Apply redirects"), "system-run", _("Automatically update redirected streams to direct URL"))
        self.btn_apply_redirects.connect("clicked", self.on_apply_redirects_clicked)
        self.btn_apply_redirects.hide()

        for w, exp, pad in [
            (self.btn_collapse_all, False, 0), (self.btn_expand_all, False, 0),
            (self.header_title, True, 6), (self.btn_check_streams, False, 0),
            (self.chk_broken_only, False, 0), (self.btn_apply_redirects, False, 0),
        ]:
            self.nav_box.pack_start(w, exp, exp, pad)

        self.help_label = Gtk.Label(halign=Gtk.Align.START)
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

        # Modèle TreeStore : 0:type, 1:nom, 2:détails/markup, 3:data_dict, 4:icon, 5:weight
        self.store = Gtk.TreeStore(str, str, str, object, str, int)
        self.treeview = Gtk.TreeView(model=self.store, reorderable=True)
        self.treeview.connect("row-activated", self.on_row_activated)
        self.treeview.connect("button-press-event", self.on_treeview_button_press)
        self.treeview.get_selection().set_mode(Gtk.SelectionMode.SINGLE)
        self.treeview.get_selection().connect("changed", self.on_selection_changed)

        self.col_element = Gtk.TreeViewColumn(_("Radio / Group"))
        self.col_element.set_expand(True)
        self.col_element.set_resizable(True)
        self.col_element.set_min_width(240)
        renderer_icon = Gtk.CellRendererPixbuf()
        self.col_element.pack_start(renderer_icon, False)
        self.col_element.add_attribute(renderer_icon, "icon-name", 4)
        self.renderer_name = Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END)
        self.col_element.pack_start(self.renderer_name, True)
        self.col_element.add_attribute(self.renderer_name, "text", 1)
        self.col_element.add_attribute(self.renderer_name, "weight", 5)
        self.treeview.append_column(self.col_element)
        self.treeview.set_expander_column(self.col_element)

        renderer_info = Gtk.CellRendererText(xalign=1.0, ellipsize=Pango.EllipsizeMode.MIDDLE)
        self.col_info = Gtk.TreeViewColumn(_("Details / Status"), renderer_info, markup=2)
        self.col_info.set_resizable(True)
        self.col_info.set_min_width(140)
        self.treeview.append_column(self.col_info)

        scrolled = Gtk.ScrolledWindow(shadow_type=Gtk.ShadowType.IN)
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.add(self.treeview)
        content_box.pack_start(scrolled, True, True, 0)

        # Boutons latéraux d'actions rapides
        side_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        content_box.pack_start(side_box, False, False, 0)

        def _side_btn(lbl, ico, tip, cb):
            b = make_btn(lbl, ico, tip)
            b.connect("clicked", cb)
            side_box.pack_start(b, False, False, 0)
            return b

        self.btn_preview = _side_btn(_("Listen"), "media-playback-start", _("Preview selected radio stream"), self.on_preview_clicked)
        self.btn_add_station = _side_btn(_("Add station"), "list-add", _("Add a new station to this group or to root"), self.on_add_station_clicked)
        self.btn_new_group = _side_btn(_("New group"), "folder-new", _("Create a new group or subgroup (Ctrl+N)"), self.on_create_group_clicked)
        self.btn_move_to = _side_btn(_("Move to..."), "go-jump", _("Move selection to another group (Ctrl+M)"), self.on_move_to_clicked)
        side_box.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 2)

        grid_order = Gtk.Grid(column_spacing=4, row_spacing=4, column_homogeneous=True)
        side_box.pack_start(grid_order, False, False, 0)
        for col, row, lbl, ico, tip, cb in [
            (0, 0, _("Top"), "go-top", _("Move selected item to the top"), self.on_move_top_clicked),
            (1, 0, _("Move up"), "go-up", _("Move up one rank"), self.on_move_up_clicked),
            (0, 1, _("Move down"), "go-down", _("Move down one rank"), self.on_move_down_clicked),
            (1, 1, "A-Z", "view-sort-ascending", _("Sort sibling items alphabetically"), self.on_sort_az_clicked),
        ]:
            b = make_btn(lbl, ico, tip)
            b.connect("clicked", cb)
            grid_order.attach(b, col, row, 1, 1)

        side_box.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 2)
        self.btn_add_sep = _side_btn(_("Separator"), "format-line-spacing", _("Insert a separator or header"), self.on_add_separator_clicked)
        _side_btn(_("Edit"), "document-edit", _("Edit selected name, URL or group (F2)"), self.on_edit_clicked)
        self.btn_repair = _side_btn(_("Repair stream..."), "system-search", _("Search Radio-Browser for a working replacement stream"), self.on_repair_stream_clicked)
        self.btn_contribute = _side_btn(_("Contribute to Radio-Browser..."), "network-server", _("Check or contribute selected station to Radio-Browser"), self.on_contribute_station_clicked)
        _side_btn(_("Delete"), "edit-delete", _("Delete selected item or group (Del)"), self.on_delete_clicked)

        # 3. Feedback & Barre d'actions inférieure
        self.lbl_feedback = Gtk.Label(label="", halign=Gtk.Align.START)
        self.vbox.pack_start(self.lbl_feedback, False, False, 0)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.vbox.pack_start(btn_box, False, False, 0)
        if not self.embedded:
            btn_cancel = make_btn(_("Cancel"), "process-stop")
            btn_cancel.connect("clicked", self.on_cancel_clicked)
            btn_box.pack_start(btn_cancel, False, False, 0)

        self.btn_export_csv = make_btn(_("Export to CSV"), "document-save-as", _("Export all stations to CSV spreadsheet format"))
        self.btn_export_csv.connect("clicked", lambda w: self.on_export_csv_clicked())
        btn_box.pack_start(self.btn_export_csv, False, False, 0)
        btn_box.pack_start(Gtk.Box(), True, True, 0)

        self.lbl_dirty_status = Gtk.Label(valign=Gtk.Align.CENTER)
        self.set_dirty(False)
        btn_box.pack_start(self.lbl_dirty_status, False, False, 6)

        self.btn_save = make_btn(_("Save now") if self.embedded else _("Save and reload"), "document-save")
        self.btn_save.get_style_context().add_class("suggested-action")
        self.btn_save.connect("clicked", self.on_save_clicked)
        btn_box.pack_start(self.btn_save, False, False, 0)

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

    def _remove_from_data(self, target_obj):
        """Retire un objet station ou groupe de self.data (utilisé lors d'une suppression en mode filtré)."""
        if not target_obj or not isinstance(self.data, list):
            return
        self.data = [g for g in self.data if g is not target_obj]
        for grp in self.data:
            stations = grp.get("stations")
            if isinstance(stations, list):
                grp["stations"] = [s for s in stations if s is not target_obj]

    def serialize_tree(self):
        """Parcourt récursivement le TreeStore et reconstruit la liste self.data conforme XML."""
        if getattr(self, "filter_broken_only", False):
            return self.data

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

                elif t == "separator" and parent_iter is None:
                    sep_name = data_obj.get("name", "") if isinstance(data_obj, dict) else ""
                    payload.append({
                        "name": sep_name.strip(),
                        "stations": [],
                        "is_separator": True,
                    })

                elif t == "station" and parent_iter is None:
                    # Station à la racine
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

        def _add_mi(lbl, cb):
            item = Gtk.MenuItem(label=lbl)
            item.connect("activate", cb)
            menu.append(item)

        if node_type == "station":
            if data_obj and data_obj.get("url"):
                clean_url = data_obj.get("url", "").strip()
                is_playing_this = (self.preview_player.is_playing and self.preview_player.current_url == clean_url)
                _add_mi(_("Stop playback") if is_playing_this else _("Play this station"), lambda w: self.on_preview_clicked(None))
                menu.append(Gtk.SeparatorMenuItem())
            for lbl, cb in [
                (_("Edit station..."), self.on_edit_clicked),
                (_("Move to another group..."), self.on_move_to_clicked),
                (_("Repair stream..."), self.on_repair_stream_clicked),
                (_("Contribute to Radio-Browser..."), lambda w: self.on_contribute_station_clicked(None)),
                (_("Delete this station"), self.on_delete_clicked),
            ]:
                _add_mi(lbl, cb)
        elif node_type == "group":
            for lbl, cb in [
                (_("Add station here..."), self.on_add_station_clicked),
                (_("New subgroup here..."), self.on_create_group_clicked),
                (_("Rename group..."), self.on_edit_clicked),
                (_("Delete group and stations"), self.on_delete_clicked),
            ]:
                _add_mi(lbl, cb)
        else:
            _add_mi(_("New group..."), self.on_create_group_clicked)
            _add_mi(_("Add station..."), self.on_add_station_clicked)

        menu.show_all()
        menu.popup(None, None, None, None, event.button, event.time)

    def on_key_press_event(self, widget, event):
        keyname = Gdk.keyval_name(event.keyval)
        ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        if keyname == "Delete":
            self.on_delete_clicked(None)
            return True
        if keyname == "F2":
            self.on_edit_clicked(None)
            return True
        if (ctrl and keyname in ("n", "N")) or (keyname in ("n", "N") and not ctrl and not self.treeview.is_focus()):
            self.on_create_group_clicked(None)
            return True
        if (ctrl and keyname in ("m", "M")) or (keyname in ("m", "M") and not ctrl and not self.treeview.is_focus()):
            self.on_move_to_clicked(None)
            return True
        return False

    def on_create_group_clicked(self, widget):
        node_type, name, data_obj, tree_iter, parent_iter = self.get_selected_node()
        parent_group = name if node_type == "group" else ""

        dialog = Gtk.Dialog(title=_("Create a new group"), transient_for=self.get_parent_window(), flags=Gtk.DialogFlags.MODAL)
        dialog.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        dialog.add_button(_("Create"), Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)

        box = dialog.get_content_area()
        box.set_spacing(10)
        set_container_margins(box, margin=12)

        lbl = Gtk.Label(label="<b>" + _("Name of the new group:") + "</b>", use_markup=True, halign=Gtk.Align.START)
        box.pack_start(lbl, False, False, 0)
        entry = Gtk.Entry(width_chars=35, activates_default=True)
        box.pack_start(entry, False, False, 0)

        chk_subgroup = None
        if parent_group:
            chk_subgroup = Gtk.CheckButton(label=f"{_('Create as a subgroup inside')} « {parent_group} »", active=True)
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
                self.treeview.get_selection().select_path(self.store.get_path(new_iter))
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
            mode="add", current_group=current_grp, available_groups=self.get_all_group_paths(),
            parent_window=self.get_parent_window(), standalone=False, on_done_callback=on_station_added
        )
        dlg.set_transient_for(self.get_parent_window())
        dlg.set_modal(True)
        dlg.show_all()

    def on_add_separator_clicked(self, widget):
        node_type, name, data_obj, tree_iter, parent_iter = self.get_selected_node()

        def on_sep_done(txt):
            if txt is not None:
                clean_txt = txt.strip()
                disp = f"─── {clean_txt} ───" if clean_txt else "────────────────────────"
                sep_obj = {"name": clean_txt, "is_separator": True, "url": ""}
                row_data = ["separator", disp, _("— Separator —"), sep_obj, "format-line-spacing", Pango.Weight.NORMAL]

                if node_type == "group" and tree_iter is not None:
                    new_iter = self.store.append(tree_iter, row_data)
                    grp_path = self.store.get_path(tree_iter)
                    if grp_path:
                        self.treeview.expand_row(grp_path, False)
                elif tree_iter is not None:
                    new_iter = self.store.insert_after(parent_iter, tree_iter, row_data)
                else:
                    new_iter = self.store.append(None, row_data)

                if new_iter:
                    new_path = self.store.get_path(new_iter)
                    if new_path:
                        self.treeview.get_selection().select_path(new_path)
                        self.treeview.scroll_to_cell(new_path, None, False, 0.0, 0.0)
                self.set_dirty(True)

        prompt_text_dialog(
            parent_window=self.get_parent_window(), title=_("Insert separator"),
            label_text=_("Optional title for this separator (leave blank for a simple line):"),
            ok_label=_("Insert"), callback=on_sep_done
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
                parent_window=self.get_parent_window(), title=_("Rename group"),
                label_text=_("New name for group:"), default_text=name,
                ok_label=_("Save"), callback=on_rename_done
            )
        elif node_type == "station" and EditStationWindow is not None:
            current_grp = self.get_selected_group_name() or ""

            def on_station_edited(val):
                if val and isinstance(val, dict):
                    if val.get("action") == "delete":
                        self._remove_from_data(data_obj)
                        self.store.remove(tree_iter)
                        self.set_dirty(True)
                        self.show_feedback(f"{_('Station deleted:')} « {name} »")
                        return

                    if isinstance(data_obj, dict):
                        data_obj.update(val)
                        val = data_obj

                    disp = strip_unsupported_emojis(val.get("name", "")) or val.get("name", "")
                    self.store.set_value(tree_iter, 1, disp)
                    self.store.set_value(tree_iter, 2, self.format_station_details(val))
                    self.store.set_value(tree_iter, 3, val)
                    self.set_dirty(True)
                    self.show_feedback(f"{_('Station updated:')} « {val.get('name', '')} »")

                    new_grp = (val.get("group") or "").strip().strip("/")
                    if new_grp != current_grp:
                        target_iter = self.find_group_iter(new_grp)
                        if new_grp and not target_iter:
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
                mode="edit", station_data=data_obj, current_group=current_grp,
                available_groups=self.get_all_group_paths(), parent_window=self.get_parent_window(),
                standalone=False, on_done_callback=on_station_edited
            )
            dlg.set_transient_for(self.get_parent_window())
            dlg.set_modal(True)
            dlg.show_all()

    def _count_stations_in_node(self, node_iter):
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
        msg = _("Are you sure you want to delete « {name} » ?").format(name=name)
        if node_type == "group":
            nb_stations = self._count_stations_in_node(tree_iter)
            if nb_stations > 0:
                is_group_with_stations = True
                unit = _("stations") if nb_stations > 1 else _("station")
                warning_text = _("Warning: this group contains {count} {unit} that will also be deleted.").format(count=nb_stations, unit=unit)
                msg = f"<b>{warning_text}</b>\n\n{msg}"

        dialog = Gtk.MessageDialog(
            transient_for=self.get_parent_window(), flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.WARNING if is_group_with_stations else Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO, text=_("Confirm deletion")
        )
        dialog.set_markup(msg)

        def on_delete_response(dlg, resp):
            dlg.destroy()
            if resp == Gtk.ResponseType.YES:
                self._remove_from_data(data_obj)
                self.store.remove(tree_iter)
                self.set_dirty(True)
                self.show_feedback(f"{_('Deleted:')} « {name} »")

        dialog.connect("response", on_delete_response)
        dialog.show_all()

    def on_move_up_clicked(self, widget):
        node_type, name, data_obj, tree_iter, parent_iter = self.get_selected_node()
        if not tree_iter:
            return
        indices = self.store.get_path(tree_iter).get_indices()
        if indices[-1] > 0:
            indices[-1] -= 1
            prev_path = Gtk.TreePath.new_from_indices(indices)
            self.store.swap(tree_iter, self.store.get_iter(prev_path))
            self.set_dirty(True)
            self.treeview.get_selection().select_path(prev_path)

    def on_move_down_clicked(self, widget):
        node_type, name, data_obj, tree_iter, parent_iter = self.get_selected_node()
        next_iter = self.store.iter_next(tree_iter) if tree_iter else None
        if next_iter:
            self.store.swap(tree_iter, next_iter)
            self.set_dirty(True)
            self.treeview.get_selection().select_path(self.store.get_path(tree_iter))

    def on_move_top_clicked(self, widget):
        node_type, name, data_obj, tree_iter, parent_iter = self.get_selected_node()
        if not tree_iter:
            return
        indices = self.store.get_path(tree_iter).get_indices()
        if indices[-1] > 0:
            first_path = Gtk.TreePath.new_from_indices(indices[:-1] + [0])
            self.store.move_before(tree_iter, self.store.get_iter(first_path))
            self.set_dirty(True)
            self.treeview.get_selection().select_path(first_path)

    def on_sort_az_clicked(self, widget):
        node_type, name, data_obj, tree_iter, parent_iter = self.get_selected_node()
        if node_type == "group":
            target_parent, target_name = tree_iter, name
        elif node_type in ("station", "separator") and parent_iter is not None:
            target_parent = parent_iter
            p_data = self.store.get_value(parent_iter, 3)
            p_name = self.store.get_value(parent_iter, 1)
            target_name = p_data.get("name", p_name) if isinstance(p_data, dict) else p_name
        else:
            target_parent, target_name = None, _("Root")

        children = self._copy_sub_tree(target_parent)
        if not children:
            self.show_feedback(_("No items to sort in this group."), is_success=False)
            return

        children.sort(key=lambda item: (0 if item[0][0] == "group" else (2 if item[0][0] == "separator" else 1), item[0][1].lower()))

        c = self.store.iter_children(target_parent)
        while c is not None:
            self.store.remove(c)
            c = self.store.iter_children(target_parent)

        self._restore_sub_tree(target_parent, children)
        self.set_dirty(True)

        if target_parent is not None:
            target_path = self.store.get_path(target_parent)
            self.treeview.expand_row(target_path, False)
            self.treeview.get_selection().select_path(target_path)
            self.treeview.scroll_to_cell(target_path, None, False, 0.0, 0.0)
            self.show_feedback(f"{_('Sorted alphabetically:')} « {target_name} »")
        else:
            self.show_feedback(_("Root items sorted alphabetically."))

    def _copy_sub_tree(self, parent_iter):
        res, c = [], self.store.iter_children(parent_iter)
        while c is not None:
            res.append(([self.store.get_value(c, col) for col in range(6)], self._copy_sub_tree(c)))
            c = self.store.iter_next(c)
        return res

    def _restore_sub_tree(self, parent_iter, sub_list):
        for row, sub in sub_list:
            self._restore_sub_tree(self.store.append(parent_iter, row), sub)

    def on_move_to_clicked(self, widget):
        node_type, name, data_obj, tree_iter, parent_iter = self.get_selected_node()
        if not tree_iter or node_type != "station":
            self.show_feedback(_("Please select a radio station to move."), is_success=False)
            return

        groups = [("/", _("[ / ] Root (Without group)"))] + [(g, g) for g in self.get_all_group_paths()]
        dialog = Gtk.Dialog(title=_("Move to another group"), transient_for=self.get_parent_window(), flags=Gtk.DialogFlags.MODAL)
        dialog.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        dialog.add_button(_("Move"), Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)

        box = dialog.get_content_area()
        box.set_spacing(10)
        set_container_margins(box, margin=12)
        box.pack_start(Gtk.Label(label="<b>" + _("Select the target destination:") + "</b>", use_markup=True, halign=Gtk.Align.START), False, False, 0)

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

    def on_preview_status_update(self, is_playing, url, message, is_error):
        update_btn_content(
            self.btn_preview,
            _("Stop") if is_playing else _("Listen"),
            "media-playback-stop" if is_playing else "media-playback-start"
        )
        self.show_feedback(message, is_success=not is_error)

    def on_preview_clicked(self, widget):
        node_type, name, data_obj, tree_iter, parent_iter = self.get_selected_node()
        if data_obj and node_type == "station":
            self.preview_player.toggle(name, data_obj.get("url", ""))

    def on_repair_stream_clicked(self, widget):
        node_type, name, data_obj, tree_iter, parent_iter = self.get_selected_node()
        if not data_obj or node_type != "station":
            self.show_feedback(_("Please select a station to repair."))
            return

        station_name = name or data_obj.get("name", "")
        dlg = RepairStreamDialog(
            parent=self.get_parent_window(), station_name=station_name,
            current_url=data_obj.get("url", ""), country_code=data_obj.get("country", ""),
        )

        def on_repair_response(dialog, res):
            new_url = dialog.get_chosen_url()
            dialog.destroy()
            if res == Gtk.ResponseType.OK and new_url:
                data_obj["url"] = new_url.strip()
                self.store.set_value(tree_iter, 3, data_obj)
                self.store.set_value(tree_iter, 2, self.format_station_details(data_obj))
                self.set_dirty(True)
                self.show_feedback(f"{_('Stream successfully repaired for')} « {station_name} »")

        dlg.connect("response", on_repair_response)
        dlg.show_all()

    def on_contribute_station_clicked(self, widget):
        node_type, name, data_obj, tree_iter, parent_iter = self.get_selected_node()
        if not data_obj or node_type != "station":
            self.show_feedback(_("Please select a station to contribute."))
            return

        dlg = ContributeStationDialog(
            parent=self.get_parent_window(), station_name=name or data_obj.get("name", ""),
            current_url=data_obj.get("url", ""), country_code=data_obj.get("country", ""),
        )

        def on_contribute_response(dialog, resp):
            existing = getattr(dialog, "existing_info", None)
            dialog.destroy()
            if resp == Gtk.ResponseType.APPLY:
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

    def on_check_streams_clicked(self, widget):
        from concurrent.futures import ThreadPoolExecutor

        stations_to_check = []
        def collect(p_iter):
            c = self.store.iter_children(p_iter)
            while c is not None:
                t, d = self.store.get_value(c, 0), self.store.get_value(c, 3)
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
            title=_("Checking your radio stations"), parent=self.get_parent_window(),
            flags=Gtk.DialogFlags.MODAL, buttons=(_("Stop"), Gtk.ResponseType.CANCEL)
        )
        dialog.set_default_size(440, 140)
        box = dialog.get_content_area()
        box.set_spacing(10)
        set_container_margins(box, margin=14)
        box.add(Gtk.Label(label="<b>" + _("Testing live radio streams...") + "</b>", use_markup=True, halign=Gtk.Align.START))
        pbar = Gtk.ProgressBar()
        box.add(pbar)
        lbl_status = Gtk.Label(label=f"0 / {total} " + _("stations checked..."), halign=Gtk.Align.START)
        box.add(lbl_status)
        dialog.show_all()

        cancel_event = threading.Event()

        def run_checks():
            done, done_lock = [0], threading.Lock()

            def check_one(c_iter, s):
                if cancel_event.is_set():
                    return
                url = s.get("url", "")
                ok, msg, redir = check_stream_url(url, timeout=3.0, with_redirect=True)
                if redir and any(token in redir for token in ["rj-tok=", "rj-ttl=", "userConsent", "token=", "expires="]):
                    redir = None
                status = ("redirect" if redir else "online") if ok is True else ("geo" if ok == "GEO" else "offline")
                self.audit_results[url] = {"status": status, "msg": msg, "redirect": redir}
                with done_lock:
                    done[0] += 1
                    cur_done = done[0]
                GLib.idle_add(pbar.set_fraction, cur_done / float(total))
                GLib.idle_add(lbl_status.set_text, f"{cur_done} / {total} {_('checked:')} {s.get('name', '')[:25]}")

            with ThreadPoolExecutor(max_workers=8) as executor:
                for f in [executor.submit(check_one, c_iter, s) for c_iter, s in stations_to_check]:
                    if cancel_event.is_set():
                        break
                    try:
                        f.result()
                    except Exception:
                        pass
            GLib.idle_add(lambda: dialog.response(Gtk.ResponseType.OK))

        def on_audit_response(dlg, res):
            if res == Gtk.ResponseType.CANCEL:
                cancel_event.set()
            dlg.destroy()

            if not self.filter_broken_only:
                self.data = self.serialize_tree()

            nb_online = sum(1 for r in self.audit_results.values() if r["status"] == "online")
            nb_dead = sum(1 for r in self.audit_results.values() if r["status"] == "offline")
            nb_redir = sum(1 for r in self.audit_results.values() if r["status"] == "redirect")
            self.show_feedback(f"{_('Audit completed:')} {nb_online} {_('online')} · {nb_dead} {_('broken')} · {nb_redir} {_('redirected')}")

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

            self.populate_tree()
            self.treeview.expand_all()

        dialog.connect("response", on_audit_response)
        dialog.show_all()
        threading.Thread(target=run_checks, daemon=True).start()

    def on_filter_broken_toggled(self, widget):
        new_state = widget.get_active()
        if not self.filter_broken_only and new_state:
            self.data = self.serialize_tree()
        self.filter_broken_only = new_state
        self.populate_tree()
        self.treeview.expand_all()

    def on_apply_redirects_clicked(self, widget):
        nb_applied = 0
        def apply_level(p_iter):
            nonlocal nb_applied
            c = self.store.iter_children(p_iter)
            while c is not None:
                t, d = self.store.get_value(c, 0), self.store.get_value(c, 3)
                if t == "station" and d:
                    audit = self.audit_results.get(d.get("url", ""))
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
            self.preview_player.stop(silent=True, sync=True)

    def on_export_csv_clicked(self, widget=None):
        chooser = Gtk.FileChooserDialog(
            title=_("Export stations to CSV"), parent=self.get_parent_window(),
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
                    proc = run_timonde_cli("--export-csv", path, "--from-json", "-", input_data=json.dumps(self.data), timeout=10.0)
                    if proc.returncode == 0:
                        self.show_feedback(f"{_('CSV export successful:')} {os.path.basename(path)}")
                    else:
                        self.show_feedback(f"{_('Export error:')} {proc.stderr.strip() or proc.returncode}", is_success=False)
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
            title=_("Backup my bookmarks (XML)"), parent=self.get_parent_window(),
            action=Gtk.FileChooserAction.SAVE,
            buttons=(_("Cancel"), Gtk.ResponseType.CANCEL, _("Save"), Gtk.ResponseType.OK),
        )
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.set_current_name("bookmarks_timonde_backup.xml")
        dialog.set_do_overwrite_confirmation(True)
        for name_f, pat in [(_("XML files (*.xml)"), "*.xml"), (_("All files (*.*)"), "*")]:
            flt = Gtk.FileFilter()
            flt.set_name(name_f)
            flt.add_pattern(pat)
            dialog.add_filter(flt)

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
                    m_type, m_txt = Gtk.MessageType.INFO, f"{_('Backup successful!')}\n\n{_('Your complete bookmarks have been saved to:')}\n{chosen_path}"
                except Exception as e:
                    m_type, m_txt = Gtk.MessageType.ERROR, f"{_('Error during backup:')}\n{e}"
                msg_diag = Gtk.MessageDialog(
                    parent=self.get_parent_window(), flags=Gtk.DialogFlags.MODAL,
                    type=m_type, buttons=Gtk.ButtonsType.OK, message_format=m_txt,
                )
                msg_diag.connect("response", lambda d, r: d.destroy())
                msg_diag.show_all()

        dialog.connect("response", on_backup_response)
        dialog.show_all()


class ReorderWindow(Gtk.Window):
    def __init__(self, data, auto_check=False, embedded=False, on_save_callback=None):
        super().__init__(title=_("Organize groups and stations (TiMonde)"))
        self.set_default_size(820, 600)
        self.set_position(Gtk.WindowPosition.CENTER)
        set_window_icon(self)
        apply_timonde_app_css()

        self.reorder_box = ReorderWidget(data=data, auto_check=auto_check, embedded=embedded, on_save_callback=on_save_callback)
        self.reorder_box.host_window = self
        set_container_margins(self.reorder_box, margin=12)
        self.add(self.reorder_box)
        self.connect("destroy", self.on_destroy_window)
        self.connect("delete-event", self.on_delete_event)
        self.connect("key-press-event", self.on_key_press_event)

    def on_delete_event(self, widget, event):
        if getattr(self.reorder_box, "dirty", False):
            dialog = Gtk.MessageDialog(
                transient_for=self, flags=Gtk.DialogFlags.MODAL,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO,
                text=_("Unsaved changes")
            )
            dialog.set_markup(f"<b>{_('You have unsaved changes.')}</b>\n\n{_('Do you want to discard them and exit?')}")

            def on_confirm_close(dlg, resp):
                dlg.destroy()
                if resp == Gtk.ResponseType.YES:
                    self.reorder_box.dirty = False
                    self.destroy()

            dialog.connect("response", on_confirm_close)
            dialog.show_all()
            return True
        return False

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
        return self.reorder_box.on_key_press_event(widget, event) if hasattr(self, "reorder_box") else False
