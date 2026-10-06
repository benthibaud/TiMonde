#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TiMonde — Dialogue graphique de réorganisation de l'ordre des groupes de radios.
"""

import sys
import json
import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, Pango

class ReorderGroupsWindow(Gtk.Window):
    def __init__(self, groups):
        super().__init__(title="↕️ Réorganiser les groupes — TiMonde")
        self.set_default_size(480, 480)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_border_width(12)

        # Structure : [{"name": str, "count": int}, ...]
        self.groups = list(groups)
        self.saved = False

        # Conteneur vertical principal
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(vbox)

        # En-tête explicatif
        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        title_label = Gtk.Label()
        title_label.set_markup("<b>Ordre d'affichage des groupes de radios</b>")
        title_label.set_xalign(0.0)
        header_box.pack_start(title_label, False, False, 0)

        help_label = Gtk.Label()
        help_label.set_markup(
            "<small>• Modifiez directement le <b>numéro d'ordre</b> (#) par double-clic.\n"
            "• Ou utilisez les boutons <b>Monter / Descendre</b>.</small>"
        )
        help_label.set_xalign(0.0)
        header_box.pack_start(help_label, False, False, 0)
        vbox.pack_start(header_box, False, False, 0)

        # Zone centrale : Liste + Boutons d'action latéraux
        content_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        vbox.pack_start(content_box, True, True, 0)

        # Modèle de données : [index_int, ordre_str, nom_str, radios_count_str]
        self.store = Gtk.ListStore(int, str, str, str)
        self.treeview = Gtk.TreeView(model=self.store)
        self.treeview.set_headers_visible(True)

        # 1. Colonne Numéro d'ordre (Éditable)
        renderer_order = Gtk.CellRendererText()
        renderer_order.set_property("editable", True)
        renderer_order.set_property("weight", Pango.Weight.BOLD)
        renderer_order.set_property("xalign", 0.5)
        renderer_order.connect("edited", self.on_order_edited)
        col_order = Gtk.TreeViewColumn("#", renderer_order, text=1)
        col_order.set_fixed_width(55)
        col_order.set_resizable(False)
        self.treeview.append_column(col_order)

        # 2. Colonne Nom du groupe
        renderer_name = Gtk.CellRendererText()
        renderer_name.set_property("ellipsize", Pango.EllipsizeMode.END)
        col_name = Gtk.TreeViewColumn("Groupe", renderer_name, text=2)
        col_name.set_expand(True)
        self.treeview.append_column(col_name)

        # 3. Colonne Nombre de stations
        renderer_count = Gtk.CellRendererText()
        renderer_count.set_property("xalign", 1.0)
        col_count = Gtk.TreeViewColumn("Radios", renderer_count, text=3)
        col_count.set_fixed_width(80)
        self.treeview.append_column(col_count)

        # Défilement
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_shadow_type(Gtk.ShadowType.IN)
        scrolled.add(self.treeview)
        content_box.pack_start(scrolled, True, True, 0)

        # Boutons latéraux
        side_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        content_box.pack_start(side_box, False, False, 0)

        btn_top = Gtk.Button(label="🔝 Premier")
        btn_top.set_tooltip_text("Placer le groupe sélectionné en tout premier")
        btn_top.connect("clicked", self.on_move_top_clicked)
        side_box.pack_start(btn_top, False, False, 0)

        btn_up = Gtk.Button(label="⬆️ Monter")
        btn_up.set_tooltip_text("Monter le groupe d'un rang")
        btn_up.connect("clicked", self.on_move_up_clicked)
        side_box.pack_start(btn_up, False, False, 0)

        btn_down = Gtk.Button(label="⬇️ Descendre")
        btn_down.set_tooltip_text("Descendre le groupe d'un rang")
        btn_down.connect("clicked", self.on_move_down_clicked)
        side_box.pack_start(btn_down, False, False, 0)

        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        side_box.pack_start(separator, False, False, 4)

        btn_sort = Gtk.Button(label="🔤 Tri A-Z")
        btn_sort.set_tooltip_text("Trier automatiquement tous les groupes par ordre alphabétique")
        btn_sort.connect("clicked", self.on_sort_az_clicked)
        side_box.pack_start(btn_sort, False, False, 0)

        # Remplir le modèle
        self.refresh_store()

        # Barre d'actions inférieure (Annuler / Enregistrer)
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        vbox.pack_start(btn_box, False, False, 0)

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

    def refresh_store(self, select_idx=None):
        self.store.clear()
        for i, g in enumerate(self.groups):
            cnt_str = f"{g.get('count', 0)} radio{'s' if g.get('count', 0) > 1 else ''}"
            self.store.append([i, str(i + 1), g["name"], cnt_str])

        if select_idx is not None and 0 <= select_idx < len(self.groups):
            path = Gtk.TreePath.new_from_string(str(select_idx))
            self.treeview.get_selection().select_path(path)
            self.treeview.scroll_to_cell(path, None, False, 0.0, 0.0)

    def get_selected_index(self):
        model, tree_iter = self.treeview.get_selection().get_selected()
        if tree_iter:
            return model[tree_iter][0]
        return None

    def on_order_edited(self, renderer, path_str, new_text):
        try:
            target_order = int(new_text.strip())
        except ValueError:
            return

        current_idx = int(path_str)
        new_idx = target_order - 1

        if new_idx < 0:
            new_idx = 0
        elif new_idx >= len(self.groups):
            new_idx = len(self.groups) - 1

        if current_idx != new_idx:
            item = self.groups.pop(current_idx)
            self.groups.insert(new_idx, item)
            self.refresh_store(select_idx=new_idx)

    def on_move_top_clicked(self, widget):
        idx = self.get_selected_index()
        if idx is not None and idx > 0:
            item = self.groups.pop(idx)
            self.groups.insert(0, item)
            self.refresh_store(select_idx=0)

    def on_move_up_clicked(self, widget):
        idx = self.get_selected_index()
        if idx is not None and idx > 0:
            self.groups[idx], self.groups[idx - 1] = self.groups[idx - 1], self.groups[idx]
            self.refresh_store(select_idx=idx - 1)

    def on_move_down_clicked(self, widget):
        idx = self.get_selected_index()
        if idx is not None and idx + 1 < len(self.groups):
            self.groups[idx], self.groups[idx + 1] = self.groups[idx + 1], self.groups[idx]
            self.refresh_store(select_idx=idx + 1)

    def on_sort_az_clicked(self, widget):
        self.groups.sort(key=lambda g: g["name"].lower())
        self.refresh_store(select_idx=0)

    def on_cancel_clicked(self, widget):
        self.destroy()

    def on_save_clicked(self, widget):
        self.saved = True
        result = [g["name"] for g in self.groups]
        print(json.dumps(result, ensure_ascii=False))
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

    win = ReorderGroupsWindow(data)
    win.show_all()
    Gtk.main()

    if win.saved:
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
