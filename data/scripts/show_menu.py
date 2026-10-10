#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TiMonde — Afficheur de menu contextuel sur Clic Gauche (D-BusMenu GTK3)
Permet d'ouvrir le menu TiMonde sur clic gauche pour tous les environnements
qui transmettent l'action Activate(x, y) au lieu d'ouvrir le menu nativement (LXQt, XFCE, etc.).
"""

import sys
import os

# Neutralisation d'éventuelles sockets IBus bloquantes
os.environ.pop("GTK_IM_MODULE", None)
os.environ.pop("XMODIFIERS", None)
os.environ.pop("QT_IM_MODULE", None)

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("DbusmenuGtk3", "0.4")
from gi.repository import Gtk, DbusmenuGtk3, Gdk, GLib
import dbus

def main():
    bus_name = None
    menu_path = "/MenuBar"
    
    # 1. Récupération du bus name passé en argument ou recherche automatique
    for arg in sys.argv[1:]:
        if arg.startswith("--bus="):
            bus_name = arg.split("=", 1)[1]
        elif arg.startswith("org.kde.StatusNotifierItem-"):
            bus_name = arg

    if not bus_name:
        # Trouver le bus name de TiMonde actif
        try:
            session_bus = dbus.SessionBus()
            for name in session_bus.list_names():
                if name.startswith("org.kde.StatusNotifierItem-") and name.endswith("-1"):
                    bus_name = str(name)
                    break
        except Exception:
            pass

    if not bus_name:
        sys.exit(1)

    menu = DbusmenuGtk3.Menu.new(bus_name, menu_path)

    def on_ready():
        menu.show_all()
        # Ouvrir le menu à la position du curseur
        menu.popup(None, None, None, None, 1, Gtk.get_current_event_time())
        return False

    menu.connect("deactivate", lambda m: Gtk.main_quit())
    GLib.idle_add(on_ready)
    Gtk.main()

if __name__ == "__main__":
    main()
