#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Interface GTK3 interactive pour ordonner, modifier et supprimer les groupes, les radios et les séparateurs de TiMonde.
- Niveau 1 : Liste des groupes (réordonnancement, renommage, suppression, création, déplacement/fusion, double-clic ou Ouvrir pour explorer)
- Niveau 2 : Radios & Séparateurs du groupe (réordonnancement, modification nom/URL/intertitre, ajout séparateur, suppression, déplacement vers un autre groupe, tri A-Z)
- Clic droit contextuel : Déplacer vers... / Nouveau groupe / Modifier / Insérer séparateur / Supprimer sur chaque élément.
- Raccourcis clavier : Ctrl+M (Déplacer vers), Ctrl+N (Nouveau groupe), Suppr (Supprimer), F2 (Modifier), Échap/Retour (Retour aux groupes).
"""

import sys
import os
import json

# Module d internationalisation TiMonde
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from timonde_i18n import _
except ImportError:
    def _(s): return s

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Pango



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

class ReorderWindow(Gtk.Window):
    def __init__(self, data):
        super().__init__(title=_("↕️ Gestion des groupes, radios et séparateurs (TiMonde)"))
        self.set_default_size(720, 530)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_border_width(12)
        self.set_icon_name("audio-x-generic")

        self.data = data
        self.current_group_idx = None  # None = vue Groupes, int = vue Radios du groupe data[idx]
        self.saved = False

        self.connect("key-press-event", self.on_key_press_event)

        self.vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(self.vbox)

        # 1. En-tête de navigation
        self.nav_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.vbox.pack_start(self.nav_box, False, False, 0)

        self.btn_back = Gtk.Button(label=_("⬅️ Retour aux groupes"))
        self.btn_back.set_tooltip_text("Revenir à la liste principale des groupes (Échap)")
        self.btn_back.connect("clicked", self.on_back_clicked)
        self.nav_box.pack_start(self.btn_back, False, False, 0)

        self.header_title = Gtk.Label()
        self.header_title.set_halign(Gtk.Align.START)
        self.nav_box.pack_start(self.header_title, True, True, 0)

        self.help_label = Gtk.Label()
        self.help_label.set_halign(Gtk.Align.START)
        self.help_label.set_line_wrap(True)
        self.vbox.pack_start(self.help_label, False, False, 0)

        # 2. Zone centrale : Liste + Boutons
        content_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.vbox.pack_start(content_box, True, True, 0)

        # Modèle de données : [index_reel, ordre_affiche, nom, info_supp]
        self.store = Gtk.ListStore(int, str, str, str)
        self.treeview = Gtk.TreeView(model=self.store)
        self.treeview.set_rules_hint(True)
        self.treeview.connect("row-activated", self.on_row_activated)
        self.treeview.connect("button-press-event", self.on_treeview_button_press)
        self.treeview.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)

        # Colonne 1 : Ordre (#)
        renderer_order = Gtk.CellRendererText()
        renderer_order.set_property("editable", True)
        renderer_order.connect("edited", self.on_order_edited)
        self.col_order = Gtk.TreeViewColumn("#", renderer_order, text=1)
        self.col_order.set_fixed_width(45)
        self.treeview.append_column(self.col_order)

        # Colonne 2 : Nom
        self.renderer_name = Gtk.CellRendererText()
        self.renderer_name.set_property("ellipsize", Pango.EllipsizeMode.END)
        self.col_name = Gtk.TreeViewColumn("Nom", self.renderer_name, text=2)
        self.col_name.set_expand(True)
        self.treeview.append_column(self.col_name)

        # Colonne 3 : Info (Radios / URL / Séparateur)
        renderer_info = Gtk.CellRendererText()
        renderer_info.set_property("xalign", 1.0)
        renderer_info.set_property("ellipsize", Pango.EllipsizeMode.MIDDLE)
        self.col_info = Gtk.TreeViewColumn("Détails", renderer_info, text=3)
        self.col_info.set_fixed_width(140)
        self.treeview.append_column(self.col_info)

        # Défilement
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_shadow_type(Gtk.ShadowType.IN)
        scrolled.add(self.treeview)
        content_box.pack_start(scrolled, True, True, 0)

        # Boutons latéraux
        side_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        content_box.pack_start(side_box, False, False, 0)

        self.btn_open = Gtk.Button(label=_("📂 Ouvrir"))
        self.btn_open.set_tooltip_text("Classer les radios de ce groupe (Entrée ou double-clic)")
        self.btn_open.connect("clicked", self.on_open_clicked)
        side_box.pack_start(self.btn_open, False, False, 0)

        self.btn_new_group = Gtk.Button(label=_("📁 Nouveau groupe"))
        self.btn_new_group.set_tooltip_text("Créer un nouveau groupe de radios (Ctrl+N)")
        self.btn_new_group.connect("clicked", self.on_create_group_clicked)
        side_box.pack_start(self.btn_new_group, False, False, 0)

        self.btn_move_to = Gtk.Button(label=_("➡️ Déplacer vers..."))
        self.btn_move_to.set_tooltip_text("Déplacer la ou les radios sélectionnées vers un autre groupe (Ctrl+M)")
        self.btn_move_to.connect("clicked", self.on_move_to_clicked)
        side_box.pack_start(self.btn_move_to, False, False, 0)

        sep0 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        side_box.pack_start(sep0, False, False, 2)

        btn_top = Gtk.Button(label=_("🔝 Premier"))
        btn_top.set_tooltip_text("Placer l'élément sélectionné en tout premier")
        btn_top.connect("clicked", self.on_move_top_clicked)
        side_box.pack_start(btn_top, False, False, 0)

        btn_up = Gtk.Button(label=_("⬆️ Monter"))
        btn_up.set_tooltip_text("Monter d'un rang")
        btn_up.connect("clicked", self.on_move_up_clicked)
        side_box.pack_start(btn_up, False, False, 0)

        btn_down = Gtk.Button(label=_("⬇️ Descendre"))
        btn_down.set_tooltip_text("Descendre d'un rang")
        btn_down.connect("clicked", self.on_move_down_clicked)
        side_box.pack_start(btn_down, False, False, 0)

        sep1 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        side_box.pack_start(sep1, False, False, 2)

        self.btn_add_station = Gtk.Button(label=_("➕ Ajouter radio"))
        self.btn_add_station.set_tooltip_text("Ajouter une nouvelle radio dans ce groupe")
        self.btn_add_station.connect("clicked", self.on_add_station_clicked)
        side_box.pack_start(self.btn_add_station, False, False, 0)

        self.btn_add_sep = Gtk.Button(label=_("➕ Séparateur"))
        self.btn_add_sep.set_tooltip_text("Insérer un séparateur ou un intertitre dans ce groupe")
        self.btn_add_sep.connect("clicked", self.on_add_separator_clicked)
        side_box.pack_start(self.btn_add_sep, False, False, 0)

        btn_sort = Gtk.Button(label=_("🔤 Tri A-Z"))
        btn_sort.set_tooltip_text("Trier automatiquement cette liste par ordre alphabétique")
        btn_sort.connect("clicked", self.on_sort_az_clicked)
        side_box.pack_start(btn_sort, False, False, 0)

        sep2 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        side_box.pack_start(sep2, False, False, 2)

        btn_edit = Gtk.Button(label=_("✏️ Modifier"))
        btn_edit.set_tooltip_text("Modifier le nom, l'URL ou l'intertitre sélectionné (F2)")
        btn_edit.connect("clicked", self.on_edit_clicked)
        side_box.pack_start(btn_edit, False, False, 0)

        btn_del = Gtk.Button(label=_("🗑️ Supprimer"))
        btn_del.set_tooltip_text("Supprimer l'élément ou le groupe sélectionné (Suppr)")
        btn_del.connect("clicked", self.on_delete_clicked)
        side_box.pack_start(btn_del, False, False, 0)

        # 3. Zone de notification / feedback visuel
        self.lbl_feedback = Gtk.Label(label="")
        self.lbl_feedback.set_halign(Gtk.Align.START)
        self.vbox.pack_start(self.lbl_feedback, False, False, 0)

        # 4. Barre d'actions inférieure
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.vbox.pack_start(btn_box, False, False, 0)

        btn_cancel = Gtk.Button(label=_("Annuler"))
        btn_cancel.connect("clicked", self.on_cancel_clicked)
        btn_box.pack_start(btn_cancel, False, False, 0)

        spacer = Gtk.Box()
        btn_box.pack_start(spacer, True, True, 0)

        btn_save = Gtk.Button(label=_("💾 Enregistrer et recharger"))
        btn_save.get_style_context().add_class("suggested-action")
        btn_save.connect("clicked", self.on_save_clicked)
        btn_box.pack_start(btn_save, False, False, 0)

        self.connect("destroy", Gtk.main_quit)

        # Affichage initial
        self.update_view()

    def on_key_press_event(self, widget, event):
        # Vérifier si l'utilisateur appuie sur des raccourcis claviers globaux
        keyname = Gdk.keyval_name(event.keyval)
        state = event.state

        ctrl_pressed = bool(state & Gdk.ModifierType.CONTROL_MASK)

        if keyname == "Delete":
            self.on_delete_clicked(None)
            return True
        elif keyname == "F2":
            self.on_edit_clicked(None)
            return True
        elif (ctrl_pressed and keyname in ("n", "N")) or (keyname in ("n", "N") and not ctrl_pressed and not self.treeview.is_focus()):
            self.on_create_group_clicked(None)
            return True
        elif (ctrl_pressed and keyname in ("m", "M")) or (keyname in ("m", "M") and not ctrl_pressed and not self.treeview.is_focus()):
            self.on_move_to_clicked(None)
            return True
        elif keyname in ("Escape", "BackSpace") and self.current_group_idx is not None:
            self.on_back_clicked(None)
            return True

        return False

    def get_current_list(self):
        if self.current_group_idx is None:
            return self.data
        else:
            return self.data[self.current_group_idx].get("stations", [])

    def is_item_separator(self, item):
        if item.get("is_separator"):
            return True
        url = item.get("url", "")
        name = item.get("name", "")
        if url == "" or url == "---":
            return True
        if name.startswith("[separator") or name == "---" or name == "separator - - -":
            return True
        return False

    def update_view(self, select_idx=None):
        self.store.clear()
        if self.current_group_idx is None:
            # Mode Groupes
            self.btn_back.hide()
            self.btn_open.show()
            self.btn_add_sep.hide()
            self.btn_add_station.hide()
            self.btn_move_to.set_label("➡️ Transférer...")
            self.btn_move_to.set_tooltip_text("Transférer le contenu de ce groupe vers un autre groupe (Ctrl+M)")
            self.btn_new_group.set_tooltip_text("Créer un nouveau groupe de radios (Ctrl+N)")
            self.header_title.set_markup("<b>📁 Groupes de radios</b>")
            self.help_label.set_markup(
                "<small>• Modifiez le <b>#</b> ou utilisez <b>Monter / Descendre</b> pour ordonner les groupes.\n"
                "• <b>Double-cliquez sur un groupe</b> (ou Ouvrir) pour classer ses radios et séparateurs.\n"
                "• Utilisez <b>➡️ Transférer...</b> pour fusionner ou déplacer le contenu vers un autre groupe.\n"
                "• Utilisez <b>📁 Nouveau groupe</b> pour ajouter un dossier de radios.</small>"
            )
            self.col_name.set_title(_("Nom du groupe"))
            self.col_info.set_title(_("Contenu"))

            for i, g in enumerate(self.data):
                stations = g.get("stations", [])
                nb_radios = sum(1 for s in stations if not self.is_item_separator(s))
                nb_seps = sum(1 for s in stations if self.is_item_separator(s))
                info_parts = [f"{nb_radios} radio{'s' if nb_radios > 1 else ''}"]
                if nb_seps > 0:
                    info_parts.append(f"{nb_seps} sép.")
                self.store.append([i, str(i + 1), g["name"], " · ".join(info_parts)])
        else:
            # Mode Radios du groupe
            grp = self.data[self.current_group_idx]
            self.btn_back.show()
            self.btn_open.hide()
            self.btn_add_sep.show()
            self.btn_add_station.show()
            self.btn_move_to.set_label("➡️ Déplacer vers...")
            self.btn_move_to.set_tooltip_text("Déplacer la ou les radios sélectionnées vers un autre groupe (Ctrl+M)")
            self.btn_new_group.set_tooltip_text("Créer un nouveau groupe et y déplacer les radios sélectionnées (Ctrl+N)")
            self.header_title.set_markup(f"<b>📻 Radios du groupe : {grp['name']}</b>")
            self.help_label.set_markup(
                "<small>• Modifiez le <b>#</b> ou utilisez <b>Monter / Descendre</b> pour classer les radios.\n"
                "• Utilisez <b>➡️ Déplacer vers...</b> pour déplacer la ou les radios vers un autre groupe.\n"
                "• Cliquez sur <b>➕ Séparateur</b> pour aérer la liste ou insérer un intertitre de section.\n"
                "• Cliquez sur <b>🔤 Tri A-Z</b> pour classer ce groupe par ordre alphabétique.</small>"
            )
            self.col_name.set_title(_("Nom / Intertitre"))
            self.col_info.set_title(_("Détails"))

            for i, s in enumerate(grp.get("stations", [])):
                if self.is_item_separator(s):
                    s["is_separator"] = True
                    s["url"] = ""
                    title = s.get("name", "").strip()
                    if title.startswith("[separator") or title == "---" or title == "separator - - -":
                        title = ""
                        s["name"] = ""
                    if title:
                        disp_name = f"─── {title} ───"
                        info_str = "Intertitre"
                    else:
                        disp_name = "────────────────────────"
                        info_str = "Séparateur"
                    self.store.append([i, str(i + 1), disp_name, info_str])
                else:
                    s["is_separator"] = False
                    url_short = s.get("url", "")
                    country_tag = s.get("country", "")
                    if country_tag:
                        info_str = f"[{country_tag}]"
                    elif len(url_short) > 28:
                        info_str = url_short[:25] + "..."
                    else:
                        info_str = url_short
                    self.store.append([i, str(i + 1), s["name"], info_str])

        if select_idx is not None:
            items = self.get_current_list()
            if 0 <= select_idx < len(items):
                path = Gtk.TreePath.new_from_string(str(select_idx))
                self.treeview.get_selection().select_path(path)
                self.treeview.scroll_to_cell(path, None, False, 0.0, 0.0)

    def get_selected_index(self):
        model, paths = self.treeview.get_selection().get_selected_rows()
        if paths:
            tree_iter = model.get_iter(paths[0])
            return model[tree_iter][0]
        return None

    def get_selected_indices(self):
        model, paths = self.treeview.get_selection().get_selected_rows()
        indices = []
        for p in paths:
            tree_iter = model.get_iter(p)
            indices.append(model[tree_iter][0])
        return sorted(indices)

    def on_row_activated(self, treeview, path, column):
        if self.current_group_idx is None and column != self.col_order:
            self.on_open_clicked(None)
        elif self.current_group_idx is not None and column != self.col_order:
            self.on_edit_clicked(None)

    def on_treeview_button_press(self, treeview, event):
        if event.button == 3:  # Clic droit
            pth = treeview.get_path_at_pos(int(event.x), int(event.y))
            if pth:
                path, col, _x, _y = pth
                sel = treeview.get_selection()
                model, paths = sel.get_selected_rows()
                if path not in paths:
                    sel.unselect_all()
                    sel.select_path(path)
                self.show_context_menu(event)
                return True
        return False

    def show_context_menu(self, event):
        menu = Gtk.Menu()
        idx = self.get_selected_index()
        items = self.get_current_list()

        if self.current_group_idx is None:
            item_open = Gtk.MenuItem(label="📂 Ouvrir les radios")
            item_open.connect("activate", self.on_open_clicked)
            menu.append(item_open)

            item_new_g = Gtk.MenuItem(label="📁 Nouveau groupe...")
            item_new_g.connect("activate", self.on_create_group_clicked)
            menu.append(item_new_g)

            item_move_g = Gtk.MenuItem(label="➡️ Transférer le contenu vers un autre groupe...")
            item_move_g.connect("activate", self.on_move_to_clicked)
            menu.append(item_move_g)

            item_edit = Gtk.MenuItem(label="✏️ Renommer le groupe...")
            item_edit.connect("activate", self.on_edit_clicked)
            menu.append(item_edit)

            item_del = Gtk.MenuItem(label="🗑️ Supprimer le groupe...")
            item_del.connect("activate", self.on_delete_clicked)
            menu.append(item_del)
        else:
            target = items[idx] if idx is not None and idx < len(items) else None
            is_sep = target and self.is_item_separator(target)

            if is_sep:
                item_edit = Gtk.MenuItem(label="✏️ Modifier l'intertitre...")
                item_edit.connect("activate", self.on_edit_clicked)
                menu.append(item_edit)
            else:
                item_edit = Gtk.MenuItem(label="✏️ Modifier la radio...")
                item_edit.connect("activate", self.on_edit_clicked)
                menu.append(item_edit)

            item_move_st = Gtk.MenuItem(label="➡️ Déplacer vers un autre groupe...")
            item_move_st.connect("activate", self.on_move_to_clicked)
            menu.append(item_move_st)

            item_new_g_here = Gtk.MenuItem(label="📁 Nouveau groupe...")
            item_new_g_here.connect("activate", self.on_create_group_clicked)
            menu.append(item_new_g_here)

            item_add_st = Gtk.MenuItem(label="➕ Ajouter une radio...")
            item_add_st.connect("activate", self.on_add_station_clicked)
            menu.append(item_add_st)

            item_add_sep = Gtk.MenuItem(label="➕ Insérer un séparateur ici...")
            item_add_sep.connect("activate", self.on_add_separator_clicked)
            menu.append(item_add_sep)

            item_top = Gtk.MenuItem(label="🔝 Placer en premier")
            item_top.connect("activate", self.on_move_top_clicked)
            menu.append(item_top)

            if is_sep:
                item_del = Gtk.MenuItem(label="🗑️ Supprimer ce séparateur")
            else:
                item_del = Gtk.MenuItem(label="🗑️ Supprimer cette radio...")
            item_del.connect("activate", self.on_delete_clicked)
            menu.append(item_del)

        menu.show_all()
        menu.popup(None, None, None, None, event.button, event.time)

    def show_feedback(self, text, is_success=True):
        color = "#27ae60" if is_success else "#e67e22"
        self.lbl_feedback.set_markup(f"<span foreground='{color}'><b>{text}</b></span>")

    def on_create_group_clicked(self, widget):
        dialog = Gtk.Dialog(
            title="📁 Créer un nouveau groupe",
            transient_for=self,
            flags=0
        )
        dialog.add_button("Annuler", Gtk.ResponseType.CANCEL)
        dialog.add_button("Créer", Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)

        box = dialog.get_content_area()
        box.set_spacing(10)
        box.set_border_width(12)

        lbl = Gtk.Label(label="<b>Nom du nouveau groupe de favoris :</b>")
        lbl.set_use_markup(True)
        lbl.set_halign(Gtk.Align.START)
        box.pack_start(lbl, False, False, 0)

        entry = Gtk.Entry()
        entry.set_width_chars(35)
        entry.set_activates_default(True)
        box.pack_start(entry, False, False, 0)

        # Si l'utilisateur est dans un groupe et a sélectionné des radios :
        # Proposer de déplacer directement ces radios vers le nouveau groupe
        chk_move_radios = None
        selected_indices = []
        if self.current_group_idx is not None:
            selected_indices = self.get_selected_indices()
            if selected_indices:
                nb = len(selected_indices)
                chk_move_radios = Gtk.CheckButton(
                    label=f"Déplacer immédiatement la ou les {nb} radio(s) sélectionnée(s) dans ce nouveau groupe"
                )
                chk_move_radios.set_active(True)
                box.pack_start(chk_move_radios, False, False, 0)

        dialog.show_all()
        response = dialog.run()
        name = entry.get_text().strip()
        should_move = chk_move_radios.get_active() if chk_move_radios else False
        dialog.destroy()

        if response == Gtk.ResponseType.OK and name:
            for g in self.data:
                if g["name"].strip().lower() == name.lower():
                    md = Gtk.MessageDialog(
                        transient_for=self,
                        flags=0,
                        message_type=Gtk.MessageType.WARNING,
                        buttons=Gtk.ButtonsType.OK,
                        text="Groupe déjà existant"
                    )
                    md.format_secondary_text(f"Un groupe nommé « {name} » existe déjà.")
                    md.run()
                    md.destroy()
                    return

            new_grp = {"name": name, "stations": []}
            self.data.append(new_grp)

            if should_move and selected_indices and self.current_group_idx is not None:
                src_stations = self.data[self.current_group_idx].get("stations", [])
                moved = []
                for i in reversed(selected_indices):
                    if i < len(src_stations):
                        moved.append(src_stations.pop(i))
                moved.reverse()
                new_grp["stations"].extend(moved)
                self.update_view()
                self.show_feedback(f"✅ Groupe « {name} » créé avec {len(moved)} radio(s) transférée(s)")
            else:
                if self.current_group_idx is None:
                    self.update_view(select_idx=len(self.data) - 1)
                else:
                    self.update_view()
                self.show_feedback(f"✅ Nouveau groupe « {name} » créé")

    def on_move_to_clicked(self, widget):
        indices = self.get_selected_indices()
        if not indices:
            md = Gtk.MessageDialog(
                transient_for=self,
                flags=0,
                message_type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.OK,
                text="Aucune sélection"
            )
            md.format_secondary_text("Veuillez d'abord sélectionner au moins un élément à déplacer.")
            md.run()
            md.destroy()
            return

        # =============================================================
        # CAS 1 : Déplacement de Radios depuis un groupe
        # =============================================================
        if self.current_group_idx is not None:
            current_grp = self.data[self.current_group_idx]
            current_stations = current_grp.get("stations", [])
            selected_stations = [current_stations[i] for i in indices if i < len(current_stations)]
            if not selected_stations:
                return

            available_targets = [(i, g["name"]) for i, g in enumerate(self.data) if i != self.current_group_idx]
            if not available_targets:
                self.on_create_group_clicked(None)
                available_targets = [(i, g["name"]) for i, g in enumerate(self.data) if i != self.current_group_idx]
                if not available_targets:
                    return

            dialog = Gtk.Dialog(
                title="➡️ Déplacer vers un autre groupe",
                transient_for=self,
                flags=0
            )
            dialog.add_button("Annuler", Gtk.ResponseType.CANCEL)
            dialog.add_button("Déplacer", Gtk.ResponseType.OK)
            dialog.set_default_response(Gtk.ResponseType.OK)

            box = dialog.get_content_area()
            box.set_spacing(10)
            box.set_border_width(12)

            nb_sel = len(selected_stations)
            if nb_sel == 1:
                st_name = selected_stations[0].get("name", "Station")
                lbl_text = f"Déplacer la radio : <b>« {st_name} »</b> vers :"
            elif nb_sel <= 3:
                names = ", ".join([f"« {s.get('name', 'Station')} »" for s in selected_stations])
                lbl_text = f"Déplacer les {nb_sel} radios ({names}) vers :"
            else:
                lbl_text = f"Déplacer les <b>{nb_sel} radios</b> sélectionnées vers :"

            lbl = Gtk.Label(label=lbl_text)
            lbl.set_use_markup(True)
            lbl.set_halign(Gtk.Align.START)
            box.pack_start(lbl, False, False, 0)

            combo = Gtk.ComboBoxText()
            for idx_g, g_name in available_targets:
                combo.append(str(idx_g), g_name)
            combo.set_active(0)
            box.pack_start(combo, False, False, 0)

            # Option d'insertion (Début ou Fin)
            pos_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            box.pack_start(pos_box, False, False, 0)
            lbl_pos = Gtk.Label(label="Position dans le groupe cible :")
            pos_box.pack_start(lbl_pos, False, False, 0)
            combo_pos = Gtk.ComboBoxText()
            combo_pos.append("end", "⬇️ À la fin (par défaut)")
            combo_pos.append("start", "⬆️ Au tout début")
            combo_pos.set_active(0)
            pos_box.pack_start(combo_pos, True, True, 0)

            # Bouton de création instantanée d'un nouveau groupe
            btn_new = Gtk.Button(label="➕ Créer un nouveau groupe cible...")
            def on_quick_create(b):
                ed = Gtk.Dialog(title="Nouveau groupe cible", transient_for=dialog, flags=0)
                ed.add_button("Annuler", Gtk.ResponseType.CANCEL)
                ed.add_button("Créer", Gtk.ResponseType.OK)
                ed.set_default_response(Gtk.ResponseType.OK)
                ebox = ed.get_content_area()
                ebox.set_spacing(6)
                ebox.set_border_width(10)
                elbl = Gtk.Label(label="Nom du nouveau groupe :")
                ebox.pack_start(elbl, False, False, 0)
                eentry = Gtk.Entry()
                eentry.set_activates_default(True)
                ebox.pack_start(eentry, False, False, 0)
                ed.show_all()
                res = ed.run()
                n = eentry.get_text().strip()
                ed.destroy()
                if res == Gtk.ResponseType.OK and n:
                    new_idx = len(self.data)
                    self.data.append({"name": n, "stations": []})
                    combo.append(str(new_idx), n)
                    combo.set_active_id(str(new_idx))
            btn_new.connect("clicked", on_quick_create)
            box.pack_start(btn_new, False, False, 0)

            dialog.show_all()
            response = dialog.run()
            target_id_str = combo.get_active_id()
            insert_pos = combo_pos.get_active_id() or "end"
            dialog.destroy()

            if response == Gtk.ResponseType.OK and target_id_str is not None:
                target_idx = int(target_id_str)
                target_name = self.data[target_idx]["name"]
                target_stations = self.data[target_idx].setdefault("stations", [])

                moved_items = []
                for i in reversed(indices):
                    if i < len(current_stations):
                        st = current_stations.pop(i)
                        moved_items.append(st)

                # Conserver l'ordre initial des éléments sélectionnés
                moved_items.reverse()
                if insert_pos == "start":
                    for st in reversed(moved_items):
                        target_stations.insert(0, st)
                else:
                    target_stations.extend(moved_items)

                self.update_view()
                self.show_feedback(f"✅ {len(moved_items)} élément(s) déplacé(s) vers « {target_name} »")

        # =============================================================
        # CAS 2 : Déplacement / Fusion depuis la vue Groupes
        # =============================================================
        else:
            if len(indices) == 1:
                src_idx = indices[0]
                src_grp = self.data[src_idx]
                available_targets = [(i, g["name"]) for i, g in enumerate(self.data) if i != src_idx]

                if not available_targets:
                    md = Gtk.MessageDialog(
                        transient_for=self,
                        flags=0,
                        message_type=Gtk.MessageType.INFO,
                        buttons=Gtk.ButtonsType.OK,
                        text="Aucun autre groupe"
                    )
                    md.format_secondary_text("Il n'y a aucun autre groupe vers lequel transférer les radios.")
                    md.run()
                    md.destroy()
                    return

                dialog = Gtk.Dialog(
                    title="➡️ Déplacer ou fusionner le groupe",
                    transient_for=self,
                    flags=0
                )
                dialog.add_button("Annuler", Gtk.ResponseType.CANCEL)
                dialog.add_button("Valider", Gtk.ResponseType.OK)
                dialog.set_default_response(Gtk.ResponseType.OK)

                box = dialog.get_content_area()
                box.set_spacing(10)
                box.set_border_width(12)

                nb_st = len(src_grp.get("stations", []))
                msg_lbl = f"Groupe source : <b>« {src_grp['name']} »</b> ({nb_st} radio(s))\nChoisissez le groupe de destination et l'action :"
                lbl = Gtk.Label(label=msg_lbl)
                lbl.set_use_markup(True)
                lbl.set_halign(Gtk.Align.START)
                box.pack_start(lbl, False, False, 0)

                combo = Gtk.ComboBoxText()
                for idx_g, g_name in available_targets:
                    combo.append(str(idx_g), g_name)
                combo.set_active(0)
                box.pack_start(combo, False, False, 0)

                # Bouton de création instantanée d'un nouveau groupe cible
                btn_new = Gtk.Button(label="➕ Créer un nouveau groupe cible...")
                def on_quick_create_group(b):
                    ed = Gtk.Dialog(title="Nouveau groupe cible", transient_for=dialog, flags=0)
                    ed.add_button("Annuler", Gtk.ResponseType.CANCEL)
                    ed.add_button("Créer", Gtk.ResponseType.OK)
                    ed.set_default_response(Gtk.ResponseType.OK)
                    ebox = ed.get_content_area()
                    ebox.set_spacing(6)
                    ebox.set_border_width(10)
                    elbl = Gtk.Label(label="Nom du nouveau groupe :")
                    ebox.pack_start(elbl, False, False, 0)
                    eentry = Gtk.Entry()
                    eentry.set_activates_default(True)
                    ebox.pack_start(eentry, False, False, 0)
                    ed.show_all()
                    res = ed.run()
                    n = eentry.get_text().strip()
                    ed.destroy()
                    if res == Gtk.ResponseType.OK and n:
                        new_idx = len(self.data)
                        self.data.append({"name": n, "stations": []})
                        combo.append(str(new_idx), n)
                        combo.set_active_id(str(new_idx))
                btn_new.connect("clicked", on_quick_create_group)
                box.pack_start(btn_new, False, False, 0)

                radio_merge = Gtk.RadioButton.new_with_label(None, "Fusionner : transférer toutes les radios dans le groupe cible")
                radio_subgrp = Gtk.RadioButton.new_with_label_from_widget(radio_merge, "Placer comme sous-groupe du groupe cible")
                box.pack_start(radio_merge, False, False, 0)
                box.pack_start(radio_subgrp, False, False, 0)

                chk_delete_src = Gtk.CheckButton(label="Supprimer le dossier d'origine une fois vidé (si fusion)")
                chk_delete_src.set_active(True)
                box.pack_start(chk_delete_src, False, False, 0)

                dialog.show_all()
                response = dialog.run()
                target_id_str = combo.get_active_id()
                is_subgrp = radio_subgrp.get_active()
                should_del = chk_delete_src.get_active()
                dialog.destroy()

                if response == Gtk.ResponseType.OK and target_id_str is not None:
                    target_idx = int(target_id_str)
                    target_name = self.data[target_idx]["name"]

                    if is_subgrp:
                        # Placer en sous-groupe
                        src_grp["name"] = f"{target_name}/{src_grp['name']}"
                        self.update_view(select_idx=src_idx)
                        self.show_feedback(f"✅ Groupe placé comme sous-groupe : « {src_grp['name']} »")
                    else:
                        # Fusion des radios
                        src_stations = src_grp.get("stations", [])
                        self.data[target_idx].setdefault("stations", []).extend(src_stations)

                        if should_del:
                            self.data.pop(src_idx)
                            self.update_view()
                        else:
                            src_grp["stations"] = []
                            self.update_view(select_idx=src_idx)

                        self.show_feedback(f"✅ {len(src_stations)} radio(s) transférée(s) dans « {target_name} »")

            else:
                # Plusieurs groupes sélectionnés : fusion groupée
                available_targets = [(i, g["name"]) for i, g in enumerate(self.data) if i not in indices]

                dialog = Gtk.Dialog(
                    title="➡️ Transférer les groupes sélectionnés",
                    transient_for=self,
                    flags=0
                )
                dialog.add_button("Annuler", Gtk.ResponseType.CANCEL)
                dialog.add_button("Fusionner", Gtk.ResponseType.OK)
                dialog.set_default_response(Gtk.ResponseType.OK)

                box = dialog.get_content_area()
                box.set_spacing(10)
                box.set_border_width(12)

                total_radios = sum(len(self.data[i].get("stations", [])) for i in indices)
                msg_lbl = f"<b>{len(indices)} groupes sélectionnés</b> ({total_radios} radio(s) au total)\nTransférer tout le contenu vers le groupe cible :"
                lbl = Gtk.Label(label=msg_lbl)
                lbl.set_use_markup(True)
                lbl.set_halign(Gtk.Align.START)
                box.pack_start(lbl, False, False, 0)

                combo = Gtk.ComboBoxText()
                for idx_g, g_name in available_targets:
                    combo.append(str(idx_g), g_name)
                if available_targets:
                    combo.set_active(0)
                box.pack_start(combo, False, False, 0)

                btn_new = Gtk.Button(label="➕ Créer un nouveau groupe cible...")
                def on_quick_create_group_multi(b):
                    ed = Gtk.Dialog(title="Nouveau groupe cible", transient_for=dialog, flags=0)
                    ed.add_button("Annuler", Gtk.ResponseType.CANCEL)
                    ed.add_button("Créer", Gtk.ResponseType.OK)
                    ed.set_default_response(Gtk.ResponseType.OK)
                    ebox = ed.get_content_area()
                    ebox.set_spacing(6)
                    ebox.set_border_width(10)
                    elbl = Gtk.Label(label="Nom du nouveau groupe :")
                    ebox.pack_start(elbl, False, False, 0)
                    eentry = Gtk.Entry()
                    eentry.set_activates_default(True)
                    ebox.pack_start(eentry, False, False, 0)
                    ed.show_all()
                    res = ed.run()
                    n = eentry.get_text().strip()
                    ed.destroy()
                    if res == Gtk.ResponseType.OK and n:
                        new_idx = len(self.data)
                        self.data.append({"name": n, "stations": []})
                        combo.append(str(new_idx), n)
                        combo.set_active_id(str(new_idx))
                btn_new.connect("clicked", on_quick_create_group_multi)
                box.pack_start(btn_new, False, False, 0)

                chk_delete = Gtk.CheckButton(label="Supprimer les groupes d'origine une fois vidés")
                chk_delete.set_active(True)
                box.pack_start(chk_delete, False, False, 0)

                dialog.show_all()
                response = dialog.run()
                target_id_str = combo.get_active_id()
                should_del = chk_delete.get_active()
                dialog.destroy()

                if response == Gtk.ResponseType.OK and target_id_str is not None:
                    target_idx = int(target_id_str)
                    target_grp = self.data[target_idx]
                    target_stations = target_grp.setdefault("stations", [])

                    total_transferred = 0
                    for i in indices:
                        if i < len(self.data):
                            sts = self.data[i].get("stations", [])
                            total_transferred += len(sts)
                            target_stations.extend(sts)
                            self.data[i]["stations"] = []

                    if should_del:
                        for i in reversed(indices):
                            if i != target_idx and i < len(self.data):
                                self.data.pop(i)

                    self.update_view()
                    self.show_feedback(f"✅ {total_transferred} radio(s) transférée(s) dans « {target_grp['name']} »")

    def on_open_clicked(self, widget):
        idx = self.get_selected_index()
        if idx is not None:
            self.current_group_idx = idx
            self.update_view()

    def on_back_clicked(self, widget):
        prev_idx = self.current_group_idx
        self.current_group_idx = None
        self.update_view(select_idx=prev_idx)

    def on_order_edited(self, renderer, path_str, new_text):
        try:
            new_order = int(new_text.strip())
        except ValueError:
            return

        old_idx = int(path_str)
        items = self.get_current_list()
        n = len(items)

        if new_order < 1:
            new_idx = 0
        elif new_order > n:
            new_idx = n - 1
        else:
            new_idx = new_order - 1

        if old_idx != new_idx:
            item = items.pop(old_idx)
            items.insert(new_idx, item)
            self.update_view(select_idx=new_idx)

    def on_move_top_clicked(self, widget):
        idx = self.get_selected_index()
        items = self.get_current_list()
        if idx is not None and idx > 0:
            item = items.pop(idx)
            items.insert(0, item)
            self.update_view(select_idx=0)

    def on_move_up_clicked(self, widget):
        idx = self.get_selected_index()
        items = self.get_current_list()
        if idx is not None and idx > 0:
            items[idx], items[idx - 1] = items[idx - 1], items[idx]
            self.update_view(select_idx=idx - 1)

    def on_move_down_clicked(self, widget):
        idx = self.get_selected_index()
        items = self.get_current_list()
        if idx is not None and idx < len(items) - 1:
            items[idx], items[idx + 1] = items[idx + 1], items[idx]
            self.update_view(select_idx=idx + 1)

    def on_sort_az_clicked(self, widget):
        items = self.get_current_list()
        # On trie en conservant un ordre alphabétique par nom
        items.sort(key=lambda x: x["name"].lower())
        self.update_view(select_idx=0)

    def on_add_station_clicked(self, widget):
        if self.current_group_idx is None:
            return

        grp = self.data[self.current_group_idx]
        current_grp_name = grp["name"]
        all_groups = [g["name"] for g in self.data]

        script_dir = os.path.dirname(os.path.abspath(__file__))
        edit_script = os.path.join(script_dir, "edit_station.py")
        if not os.path.exists(edit_script):
            home = os.environ.get("HOME", ".")
            edit_script = os.path.join(home, ".local/share/timonde/scripts/edit_station.py")

        cmd = [
            sys.executable, edit_script,
            "--mode", "add",
            "--group", current_grp_name,
            "--groups-json", json.dumps(all_groups)
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                val = json.loads(res.stdout.strip())
                new_st = {
                    "name": val["name"],
                    "url": val["url"],
                    "country": val.get("country"),
                    "timezone": val.get("timezone"),
                }
                target_grp_name = val.get("group") or current_grp_name
                target_grp = next((g for g in self.data if g["name"] == target_grp_name), grp)
                target_grp.setdefault("stations", []).append(new_st)
                self.show_feedback(f"Radio « {val['name']} » ajoutée")
                self.update_view(select_idx=len(target_grp.get("stations", [])) - 1 if target_grp == grp else None)
        except Exception as e:
            sys.stderr.write(f"Erreur ajout station: {e}\n")

    def on_add_separator_clicked(self, widget):
        if self.current_group_idx is None:
            return

        dialog = Gtk.Dialog(
            title="➕ Insérer un séparateur",
            parent=self,
            flags=Gtk.DialogFlags.MODAL,
            buttons=("Annuler", Gtk.ResponseType.CANCEL, "Insérer", Gtk.ResponseType.OK),
        )
        dialog.set_default_size(380, 150)
        box = dialog.get_content_area()
        box.set_spacing(10)
        box.set_border_width(12)

        lbl = Gtk.Label(
            label="Titre d'intertitre optionnel :\n"
            "<small>(Laissez vide pour un simple trait de séparation)</small>"
        )
        lbl.set_use_markup(True)
        lbl.set_halign(Gtk.Align.START)
        box.add(lbl)

        entry = Gtk.Entry()
        entry.set_placeholder_text("Ex : Jazz & Blues (ou laissez vide)")
        box.add(entry)
        dialog.show_all()

        if dialog.run() == Gtk.ResponseType.OK:
            title = entry.get_text().strip()
            items = self.get_current_list()
            cur_idx = self.get_selected_index()
            insert_pos = cur_idx + 1 if cur_idx is not None else len(items)

            new_sep = {
                "name": title,
                "url": "",
                "is_separator": True,
            }
            items.insert(insert_pos, new_sep)
            self.update_view(select_idx=insert_pos)
        dialog.destroy()

    def on_edit_clicked(self, widget):
        idx = self.get_selected_index()
        if idx is None:
            return

        items = self.get_current_list()
        target = items[idx]

        if self.current_group_idx is None:
            # Éditer le nom du groupe
            dialog = Gtk.Dialog(
                title="✏️ Renommer le groupe",
                parent=self,
                flags=Gtk.DialogFlags.MODAL,
                buttons=("Annuler", Gtk.ResponseType.CANCEL, "Enregistrer", Gtk.ResponseType.OK),
            )
            dialog.set_default_size(380, 140)
            box = dialog.get_content_area()
            box.set_spacing(10)
            box.set_border_width(12)

            lbl = Gtk.Label(label="Nouveau nom du groupe :")
            lbl.set_halign(Gtk.Align.START)
            box.add(lbl)

            entry = Gtk.Entry()
            entry.set_text(target["name"])
            box.add(entry)
            dialog.show_all()

            if dialog.run() == Gtk.ResponseType.OK:
                new_name = entry.get_text().strip()
                if new_name:
                    target["name"] = new_name
                    self.update_view(select_idx=idx)
            dialog.destroy()
        elif self.is_item_separator(target):
            # Éditer le titre du séparateur
            dialog = Gtk.Dialog(
                title="✏️ Modifier le titre du séparateur",
                parent=self,
                flags=Gtk.DialogFlags.MODAL,
                buttons=("Annuler", Gtk.ResponseType.CANCEL, "Enregistrer", Gtk.ResponseType.OK),
            )
            dialog.set_default_size(380, 140)
            box = dialog.get_content_area()
            box.set_spacing(10)
            box.set_border_width(12)

            lbl = Gtk.Label(
                label="Titre d'intertitre :\n<small>(Effacez tout pour un trait simple)</small>"
            )
            lbl.set_use_markup(True)
            lbl.set_halign(Gtk.Align.START)
            box.add(lbl)

            entry = Gtk.Entry()
            entry.set_text(target.get("name", ""))
            box.add(entry)
            dialog.show_all()

            if dialog.run() == Gtk.ResponseType.OK:
                new_title = entry.get_text().strip()
                target["name"] = new_title
                target["url"] = ""
                target["is_separator"] = True
                self.update_view(select_idx=idx)
            dialog.destroy()
        else:
            # Éditer la radio via le composant unifié edit_station.py
            script_dir = os.path.dirname(os.path.abspath(__file__))
            edit_script = os.path.join(script_dir, "edit_station.py")
            if not os.path.exists(edit_script):
                home = os.environ.get("HOME", ".")
                edit_script = os.path.join(home, ".local/share/timonde/scripts/edit_station.py")

            current_grp_name = self.data[self.current_group_idx]["name"] if self.current_group_idx is not None else ""
            all_groups = [g["name"] for g in self.data]

            cmd = [
                sys.executable, edit_script,
                "--mode", "edit",
                "--station-name", target.get("name", ""),
                "--url", target.get("url", ""),
                "--country", target.get("country", "") or "",
                "--timezone", target.get("timezone", "") or "",
                "--group", current_grp_name,
                "--groups-json", json.dumps(all_groups)
            ]
            try:
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0 and res.stdout.strip():
                    val = json.loads(res.stdout.strip())
                    if val.get("action") == "delete":
                        items.pop(idx)
                        self.show_feedback("Radio supprimée")
                        self.update_view()
                        return
                    target["name"] = val["name"]
                    target["url"] = val["url"]
                    target["country"] = val.get("country")
                    target["timezone"] = val.get("timezone")

                    new_grp_name = val.get("group")
                    if self.current_group_idx is not None and new_grp_name and new_grp_name != current_grp_name:
                        target_grp = next((g for g in self.data if g["name"] == new_grp_name), None)
                        if target_grp:
                            items.pop(idx)
                            target_grp.setdefault("stations", []).append(target)
                            self.show_feedback(f"Radio déplacée vers « {new_grp_name} »")
                    self.update_view(select_idx=idx if self.current_group_idx is not None else None)
            except Exception as e:
                pass

    def on_delete_clicked(self, widget):
        indices = self.get_selected_indices()
        if not indices:
            return

        items = self.get_current_list()

        if len(indices) == 1:
            target = items[indices[0]]
            name = target["name"]
            if self.current_group_idx is None:
                msg = f"Voulez-vous vraiment supprimer le groupe « {name} » et tout son contenu ?"
            elif self.is_item_separator(target):
                sep_desc = f"l'intertitre « {name} »" if name else "ce séparateur"
                msg = f"Voulez-vous supprimer {sep_desc} ?"
            else:
                msg = f"Voulez-vous vraiment supprimer la radio « {name} » ?"
        else:
            nb = len(indices)
            if self.current_group_idx is None:
                msg = f"Voulez-vous vraiment supprimer ces {nb} groupes et tout leur contenu ?"
            else:
                msg = f"Voulez-vous vraiment supprimer ces {nb} éléments ?"

        dialog = Gtk.MessageDialog(
            parent=self,
            flags=Gtk.DialogFlags.MODAL,
            type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            message_format=msg,
        )
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        response = dialog.run()
        dialog.destroy()

        if response == Gtk.ResponseType.OK:
            for i in reversed(indices):
                if i < len(items):
                    items.pop(i)
            next_idx = min(indices[0], max(0, len(items) - 1)) if items else None
            self.update_view(select_idx=next_idx)

    def on_cancel_clicked(self, widget):
        self.saved = False
        self.destroy()

    def on_save_clicked(self, widget):
        self.saved = True
        self.destroy()


def main():
    try:
        raw_input = sys.stdin.read()
        if not raw_input.strip():
            sys.exit(1)
        data = json.loads(raw_input)
    except Exception as e:
        sys.stderr.write(f"Erreur lecture stdin : {e}\n")
        sys.exit(1)

    win = ReorderWindow(data)
    win.show_all()
    win.btn_back.hide()
    win.btn_add_sep.hide()
    win.btn_add_station.hide()
    Gtk.main()

    if win.saved:
        json.dump(win.data, sys.stdout, ensure_ascii=False)
        sys.stdout.flush()
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
