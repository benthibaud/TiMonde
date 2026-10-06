#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Interface GTK3 interactive pour ordonner, modifier et supprimer les groupes et les radios de TiMonde.
- Niveau 1 : Liste des groupes (réordonnancement, renommage, suppression, double-clic ou Ouvrir pour explorer)
- Niveau 2 : Radios du groupe (réordonnancement, modification nom/URL, suppression, tri A-Z)
- Clic droit contextuel : Modifier / Supprimer sur chaque élément.
"""

import sys
import json
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Pango

class ReorderWindow(Gtk.Window):
    def __init__(self, data):
        super().__init__(title="↕️ Gestion des groupes et radios (TiMonde)")
        self.set_default_size(680, 500)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_border_width(12)
        self.set_icon_name("audio-x-generic")

        self.data = data
        self.current_group_idx = None  # None = vue Groupes, int = vue Radios du groupe data[idx]
        self.saved = False

        self.vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(self.vbox)

        # 1. En-tête de navigation
        self.nav_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.vbox.pack_start(self.nav_box, False, False, 0)

        self.btn_back = Gtk.Button(label="⬅️ Retour aux groupes")
        self.btn_back.set_tooltip_text("Revenir à la liste principale des groupes")
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

        # Colonne 3 : Info (Radios / URL)
        renderer_info = Gtk.CellRendererText()
        renderer_info.set_property("xalign", 1.0)
        renderer_info.set_property("ellipsize", Pango.EllipsizeMode.MIDDLE)
        self.col_info = Gtk.TreeViewColumn("Détails", renderer_info, text=3)
        self.col_info.set_fixed_width(130)
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

        self.btn_open = Gtk.Button(label="📂 Ouvrir")
        self.btn_open.set_tooltip_text("Classer les radios de ce groupe")
        self.btn_open.connect("clicked", self.on_open_clicked)
        side_box.pack_start(self.btn_open, False, False, 0)

        btn_top = Gtk.Button(label="🔝 Premier")
        btn_top.set_tooltip_text("Placer l'élément sélectionné en tout premier")
        btn_top.connect("clicked", self.on_move_top_clicked)
        side_box.pack_start(btn_top, False, False, 0)

        btn_up = Gtk.Button(label="⬆️ Monter")
        btn_up.set_tooltip_text("Monter d'un rang")
        btn_up.connect("clicked", self.on_move_up_clicked)
        side_box.pack_start(btn_up, False, False, 0)

        btn_down = Gtk.Button(label="⬇️ Descendre")
        btn_down.set_tooltip_text("Descendre d'un rang")
        btn_down.connect("clicked", self.on_move_down_clicked)
        side_box.pack_start(btn_down, False, False, 0)

        sep1 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        side_box.pack_start(sep1, False, False, 2)

        btn_sort = Gtk.Button(label="🔤 Tri A-Z")
        btn_sort.set_tooltip_text("Trier automatiquement cette liste par ordre alphabétique")
        btn_sort.connect("clicked", self.on_sort_az_clicked)
        side_box.pack_start(btn_sort, False, False, 0)

        sep2 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        side_box.pack_start(sep2, False, False, 2)

        btn_edit = Gtk.Button(label="✏️ Modifier")
        btn_edit.set_tooltip_text("Modifier le nom ou l'URL de l'élément sélectionné")
        btn_edit.connect("clicked", self.on_edit_clicked)
        side_box.pack_start(btn_edit, False, False, 0)

        btn_del = Gtk.Button(label="🗑️ Supprimer")
        btn_del.set_tooltip_text("Supprimer l'élément sélectionné de vos favoris")
        btn_del.connect("clicked", self.on_delete_clicked)
        side_box.pack_start(btn_del, False, False, 0)

        # 3. Barre d'actions inférieure
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.vbox.pack_start(btn_box, False, False, 0)

        btn_cancel = Gtk.Button(label="Annuler")
        btn_cancel.connect("clicked", self.on_cancel_clicked)
        btn_box.pack_start(btn_cancel, False, False, 0)

        spacer = Gtk.Box()
        btn_box.pack_start(spacer, True, True, 0)

        btn_save = Gtk.Button(label="💾 Enregistrer et recharger")
        btn_save.get_style_context().add_class("suggested-action")
        btn_save.connect("clicked", self.on_save_clicked)
        btn_box.pack_start(btn_save, False, False, 0)

        self.connect("destroy", Gtk.main_quit)

        # Affichage initial
        self.update_view()

    def get_current_list(self):
        if self.current_group_idx is None:
            return self.data
        else:
            return self.data[self.current_group_idx].get("stations", [])

    def update_view(self, select_idx=None):
        self.store.clear()
        if self.current_group_idx is None:
            # Mode Groupes
            self.btn_back.hide()
            self.btn_open.show()
            self.header_title.set_markup("<b>📁 Groupes de radios</b>")
            self.help_label.set_markup(
                "<small>• Modifiez le <b>#</b> ou utilisez <b>Monter / Descendre</b> pour ordonner les groupes.\n"
                "• <b>Double-cliquez sur un groupe</b> (ou Ouvrir) pour classer ses radios.\n"
                "• Utilisez <b>Modifier</b> ou <b>Supprimer</b> (ou clic droit) pour ajuster les éléments.</small>"
            )
            self.col_name.set_title("Nom du groupe")
            self.col_info.set_title("Radios")

            for i, g in enumerate(self.data):
                nb = len(g.get("stations", []))
                cnt_str = f"{nb} radio{'s' if nb > 1 else ''}"
                self.store.append([i, str(i + 1), g["name"], cnt_str])
        else:
            # Mode Radios du groupe
            grp = self.data[self.current_group_idx]
            self.btn_back.show()
            self.btn_open.hide()
            self.header_title.set_markup(f"<b>📻 Radios du groupe : {grp['name']}</b>")
            self.help_label.set_markup(
                "<small>• Modifiez le <b>#</b> ou utilisez <b>Monter / Descendre</b> pour classer les radios.\n"
                "• Cliquez sur <b>✏️ Modifier</b> ou <b>🗑️ Supprimer</b> (ou clic droit) pour gérer une radio.\n"
                "• Cliquez sur <b>🔤 Tri A-Z</b> pour classer ce groupe par ordre alphabétique.</small>"
            )
            self.col_name.set_title("Nom de la radio")
            self.col_info.set_title("Flux")

            for i, s in enumerate(grp.get("stations", [])):
                url_short = s.get("url", "")
                if len(url_short) > 28:
                    url_short = url_short[:25] + "..."
                self.store.append([i, str(i + 1), s["name"], url_short])

        if select_idx is not None:
            items = self.get_current_list()
            if 0 <= select_idx < len(items):
                path = Gtk.TreePath.new_from_string(str(select_idx))
                self.treeview.get_selection().select_path(path)
                self.treeview.scroll_to_cell(path, None, False, 0.0, 0.0)

    def get_selected_index(self):
        model, tree_iter = self.treeview.get_selection().get_selected()
        if tree_iter:
            return model[tree_iter][0]
        return None

    def on_row_activated(self, treeview, path, column):
        # Si on est dans la vue Groupes et qu'on double-clique ailleurs que sur la colonne #
        if self.current_group_idx is None and column != self.col_order:
            self.on_open_clicked(None)
        elif self.current_group_idx is not None and column != self.col_order:
            self.on_edit_clicked(None)

    def on_treeview_button_press(self, treeview, event):
        if event.button == 3:  # Clic droit
            pth = treeview.get_path_at_pos(int(event.x), int(event.y))
            if pth:
                path, col, _, _ = pth
                treeview.get_selection().select_path(path)
                self.show_context_menu(event)
                return True
        return False

    def show_context_menu(self, event):
        menu = Gtk.Menu()

        if self.current_group_idx is None:
            item_open = Gtk.MenuItem(label="📂 Ouvrir les radios")
            item_open.connect("activate", self.on_open_clicked)
            menu.append(item_open)

            item_edit = Gtk.MenuItem(label="✏️ Renommer le groupe...")
            item_edit.connect("activate", self.on_edit_clicked)
            menu.append(item_edit)

            item_del = Gtk.MenuItem(label="🗑️ Supprimer le groupe...")
            item_del.connect("activate", self.on_delete_clicked)
            menu.append(item_del)
        else:
            item_edit = Gtk.MenuItem(label="✏️ Modifier la radio...")
            item_edit.connect("activate", self.on_edit_clicked)
            menu.append(item_edit)

            item_top = Gtk.MenuItem(label="🔝 Placer en premier")
            item_top.connect("activate", self.on_move_top_clicked)
            menu.append(item_top)

            item_del = Gtk.MenuItem(label="🗑️ Supprimer cette radio...")
            item_del.connect("activate", self.on_delete_clicked)
            menu.append(item_del)

        menu.show_all()
        menu.popup(None, None, None, None, event.button, event.time)

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
            target_order = int(new_text.strip())
        except ValueError:
            return

        items = self.get_current_list()
        current_idx = int(path_str)
        new_idx = target_order - 1

        if new_idx < 0:
            new_idx = 0
        elif new_idx >= len(items):
            new_idx = len(items) - 1

        if current_idx != new_idx:
            item = items.pop(current_idx)
            items.insert(new_idx, item)
            self.update_view(select_idx=new_idx)

    def on_move_top_clicked(self, widget):
        idx = self.get_selected_index()
        items = self.get_current_list()
        if idx is not None and idx > 0 and len(items) > 1:
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
        if idx is not None and idx + 1 < len(items):
            items[idx], items[idx + 1] = items[idx + 1], items[idx]
            self.update_view(select_idx=idx + 1)

    def on_sort_az_clicked(self, widget):
        items = self.get_current_list()
        items.sort(key=lambda x: x["name"].lower())
        self.update_view(select_idx=0)

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
            dialog.set_default_size(360, 140)
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
        else:
            # Éditer nom et URL de la radio
            dialog = Gtk.Dialog(
                title="✏️ Modifier la radio",
                parent=self,
                flags=Gtk.DialogFlags.MODAL,
                buttons=("Annuler", Gtk.ResponseType.CANCEL, "Enregistrer", Gtk.ResponseType.OK),
            )
            dialog.set_default_size(440, 180)
            box = dialog.get_content_area()
            box.set_spacing(10)
            box.set_border_width(12)

            grid = Gtk.Grid()
            grid.set_column_spacing(10)
            grid.set_row_spacing(10)
            box.add(grid)

            l1 = Gtk.Label(label="Nom :")
            l1.set_halign(Gtk.Align.END)
            grid.attach(l1, 0, 0, 1, 1)

            entry_name = Gtk.Entry()
            entry_name.set_hexpand(True)
            entry_name.set_text(target["name"])
            grid.attach(entry_name, 1, 0, 1, 1)

            l2 = Gtk.Label(label="URL :")
            l2.set_halign(Gtk.Align.END)
            grid.attach(l2, 0, 1, 1, 1)

            entry_url = Gtk.Entry()
            entry_url.set_hexpand(True)
            entry_url.set_text(target.get("url", ""))
            grid.attach(entry_url, 1, 1, 1, 1)

            dialog.show_all()
            if dialog.run() == Gtk.ResponseType.OK:
                new_n = entry_name.get_text().strip()
                new_u = entry_url.get_text().strip()
                if new_n and new_u:
                    target["name"] = new_n
                    target["url"] = new_u
                    self.update_view(select_idx=idx)
            dialog.destroy()

    def on_delete_clicked(self, widget):
        idx = self.get_selected_index()
        if idx is None:
            return

        items = self.get_current_list()
        target = items[idx]
        name = target["name"]

        if self.current_group_idx is None:
            msg = f"Voulez-vous vraiment supprimer le groupe « {name} » et toutes ses radios ?"
        else:
            msg = f"Voulez-vous vraiment supprimer la radio « {name} » ?"

        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text="Confirmation de suppression",
        )
        dialog.format_secondary_text(msg)
        response = dialog.run()
        dialog.destroy()

        if response == Gtk.ResponseType.OK:
            items.pop(idx)
            new_sel = min(idx, len(items) - 1) if items else None
            self.update_view(select_idx=new_sel)

    def on_cancel_clicked(self, widget):
        self.destroy()

    def on_save_clicked(self, widget):
        self.saved = True
        print(json.dumps(self.data, ensure_ascii=False))
        self.destroy()

def main():
    raw_input = ""
    if len(sys.argv) > 1 and sys.argv[1] != "-":
        try:
            with open(sys.argv[1], "r", encoding="utf-8") as f:
                raw_input = f.read()
        except Exception as e:
            sys.stderr.write(f"Erreur de lecture du fichier : {e}\n")
            sys.exit(1)
    else:
        raw_input = sys.stdin.read()

    try:
        data = json.loads(raw_input)
    except Exception as e:
        sys.stderr.write(f"Format JSON invalide : {e}\n")
        sys.exit(1)

    if not isinstance(data, list) or len(data) == 0:
        sys.stderr.write("Liste de groupes vide.\n")
        sys.exit(1)

    win = ReorderWindow(data)
    win.show_all()
    win.btn_back.hide()
    Gtk.main()

    if win.saved:
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
