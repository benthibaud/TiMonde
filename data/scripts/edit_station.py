#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script GTK3 autonome pour modifier le nom et l'URL d'une station de radio dans TiMonde.
Prend en argument: --name "Nom" --url "http://..."
Renvoie en stdout le JSON: {"name": "...", "url": "..."} si validé, exit code 0.
Exit code 1 si annulé.
"""

import sys
import json
import argparse
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk

class EditStationWindow(Gtk.Window):
    def __init__(self, current_name, current_url):
        super().__init__(title="✏️ Modifier la station (TiMonde)")
        self.set_default_size(480, 200)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_border_width(12)
        self.set_icon_name("audio-x-generic")

        self.saved = False
        self.result_data = None

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.add(vbox)

        # En-tête informatif
        header = Gtk.Label()
        header.set_markup("<b>Modifier les paramètres de la station :</b>")
        header.set_halign(Gtk.Align.START)
        vbox.pack_start(header, False, False, 0)

        # Grille pour les champs
        grid = Gtk.Grid()
        grid.set_column_spacing(10)
        grid.set_row_spacing(10)
        vbox.pack_start(grid, True, True, 0)

        lbl_name = Gtk.Label(label="Nom :")
        lbl_name.set_halign(Gtk.Align.END)
        grid.attach(lbl_name, 0, 0, 1, 1)

        self.entry_name = Gtk.Entry()
        self.entry_name.set_text(current_name)
        self.entry_name.set_hexpand(True)
        self.entry_name.connect("activate", self.on_save_clicked)
        grid.attach(self.entry_name, 1, 0, 1, 1)

        lbl_url = Gtk.Label(label="URL du flux :")
        lbl_url.set_halign(Gtk.Align.END)
        grid.attach(lbl_url, 0, 1, 1, 1)

        self.entry_url = Gtk.Entry()
        self.entry_url.set_text(current_url)
        self.entry_url.set_hexpand(True)
        self.entry_url.connect("activate", self.on_save_clicked)
        grid.attach(self.entry_url, 1, 1, 1, 1)

        # Boutons d'action
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        vbox.pack_start(btn_box, False, False, 0)

        btn_cancel = Gtk.Button(label="Annuler")
        btn_cancel.connect("clicked", self.on_cancel_clicked)
        btn_box.pack_start(btn_cancel, False, False, 0)

        spacer = Gtk.Box()
        btn_box.pack_start(spacer, True, True, 0)

        btn_save = Gtk.Button(label="💾 Enregistrer")
        btn_save.get_style_context().add_class("suggested-action")
        btn_save.connect("clicked", self.on_save_clicked)
        btn_box.pack_start(btn_save, False, False, 0)

        self.connect("destroy", Gtk.main_quit)
        self.connect("key-press-event", self.on_key_press)

    def on_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.destroy()
            return True
        return False

    def on_cancel_clicked(self, widget):
        self.destroy()

    def on_save_clicked(self, widget):
        name = self.entry_name.get_text().strip()
        url = self.entry_url.get_text().strip()
        if not name or not url:
            return

        self.result_data = {"name": name, "url": url}
        self.saved = True
        print(json.dumps(self.result_data, ensure_ascii=False))
        self.destroy()

def main():
    parser = argparse.ArgumentParser(description="Éditer une station TiMonde")
    parser.add_argument("--name", default="", help="Nom actuel de la station")
    parser.add_argument("--url", default="", help="URL actuelle du flux")
    args = parser.parse_args()

    win = EditStationWindow(args.name, args.url)
    win.show_all()
    Gtk.main()

    if win.saved and win.result_data:
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
