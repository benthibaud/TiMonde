#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TiMonde — Dialogue graphique de réorganisation des groupes et des radios.
Permet d'ordonner les groupes ET d'entrer par double-clic dans un groupe pour ordonner ses radios.
"""

import sys
import json
import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Pango

class ReorderWindow(Gtk.Window):
    def __init__(self, data):
        super().__init__(title="↕️ Réorganiser groupes et radios — TiMonde")
        self.set_default_size(540, 520)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_border_width(12)

        # Structure : [{"name": str, "stations": [{"name": str, "url": str}, ...]}, ...]
        self.data = list(data)
        self.current_group_idx = None  # None = vue Groupes, int = vue Radios du groupe
        self.saved = False

        # Conteneur vertical principal
        self.vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(self.vbox)

        # 1. En-tête de navigation
        self.header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.vbox.pack_start(self.header_box, False, False, 0)

        self.btn_back = Gtk.Button(label="⬅️ Retour aux groupes")
        self.btn_back.set_tooltip_text("Revenir à la liste des groupes")
        self.btn_back.connect("clicked", self.on_back_clicked)
        self.header_box.pack_start(self.btn_back, False, False, 0)

        self.header_title = Gtk.Label()
        self.header_title.set_xalign(0.0)
        self.header_box.pack_start(self.header_title, True, True, 0)

        # Message d'aide
        self.help_label = Gtk.Label()
        self.help_label.set_xalign(0.0)
        self.vbox.pack_start(self.help_label, False, False, 0)

        # 2. Zone centrale : Liste + Boutons d'action latéraux
        content_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.vbox.pack_start(content_box, True, True, 0)

        # Modèle de données : [index_int, ordre_str, nom_str, info_secondaire_str]
        self.store = Gtk.ListStore(int, str, str, str)
        self.treeview = Gtk.TreeView(model=self.store)
        self.treeview.set_headers_visible(True)
        self.treeview.connect("row-activated", self.on_row_activated)

        # Colonne 1 : Numéro d'ordre (Éditable par double-clic)
        renderer_order = Gtk.CellRendererText()
        renderer_order.set_property("editable", True)
        renderer_order.set_property("weight", Pango.Weight.BOLD)
        renderer_order.set_property("xalign", 0.5)
        renderer_order.connect("edited", self.on_order_edited)
        self.col_order = Gtk.TreeViewColumn("#", renderer_order, text=1)
        self.col_order.set_fixed_width(55)
        self.col_order.set_resizable(False)
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
        self.col_info.set_fixed_width(120)
        self.treeview.append_column(self.col_info)

        # Défilement
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_shadow_type(Gtk.ShadowType.IN)
        scrolled.add(self.treeview)
        content_box.pack_start(scrolled, True, True, 0)

        # Boutons latéraux
        side_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
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

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        side_box.pack_start(sep, False, False, 4)

        btn_sort = Gtk.Button(label="🔤 Tri A-Z")
        btn_sort.set_tooltip_text("Trier automatiquement cette liste par ordre alphabétique")
        btn_sort.connect("clicked", self.on_sort_az_clicked)
        side_box.pack_start(btn_sort, False, False, 0)

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
                "• <b>Double-cliquez sur un groupe</b> (ou cliquez sur Ouvrir) pour classer ses radios.</small>"
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
    # Le bouton retour est masqué au début
    win.btn_back.hide()
    Gtk.main()

    if win.saved:
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
