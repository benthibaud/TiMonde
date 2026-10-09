#!/usr/bin/env python3
# ==============================================================================
#  TiMonde — Pont SNI vers XEmbed (IceWM, Fluxbox, JWM sous antiX / Dérivés)
# ==============================================================================
# Ce script assure la compatibilité universelle sur les gestionnaires de fenêtres
# légers qui n'implémentent pas StatusNotifierWatcher (D-Bus SNI) mais uniquement
# le protocole de plateau historique X11 / XEmbed via GtkStatusIcon.
# ==============================================================================

import sys
import os
import signal
import dbus
import dbus.service
import dbus.mainloop.glib
import gi

# Mort automatique dès que le processus parent (TiMonde) disparaît (Linux prctl)
try:
    import ctypes
    libc = ctypes.CDLL(None)
    # PR_SET_PDEATHSIG = 1, SIGTERM = 15
    libc.prctl(1, signal.SIGTERM)
except Exception:
    pass

gi.require_version("Gtk", "3.0")
gi.require_version("DbusmenuGtk3", "0.4")
from gi.repository import Gtk, DbusmenuGtk3, GLib

# Filtrer les faux avertissements de resynchronisation interne de libdbusmenu
def _null_log_handler(*args):
    pass

GLib.log_set_handler("LIBDBUSMENU-GLIB", GLib.LogLevelFlags.LEVEL_WARNING | GLib.LogLevelFlags.LEVEL_CRITICAL, _null_log_handler, None)

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

try:
    session_bus = dbus.SessionBus()
except Exception as e:
    sys.stderr.write(f"TiMonde XEmbed Bridge: Erreur connexion session D-Bus: {e}\n")
    sys.exit(1)

_CURRENT_STATUS_ICON = None

def cleanup_and_exit(signum=None, frame=None):
    global _CURRENT_STATUS_ICON
    if _CURRENT_STATUS_ICON is not None:
        try:
            _CURRENT_STATUS_ICON.set_visible(False)
        except Exception:
            pass
        _CURRENT_STATUS_ICON = None
    try:
        Gtk.main_quit()
    except Exception:
        pass
    sys.exit(0)


signal.signal(signal.SIGINT, cleanup_and_exit)
signal.signal(signal.SIGTERM, cleanup_and_exit)


def apply_status_icon(status_icon, icon_name):
    """Charge l'icône en garantissant l'affichage même si le cache de thème est absent."""
    if not icon_name:
        icon_name = "audio-speakers"

    status_icon.set_from_icon_name(icon_name)

    if icon_name.startswith("timonde_"):
        candidates = [
            f"/usr/share/icons/hicolor/24x24/panel/{icon_name}.png",
            f"/usr/share/icons/hicolor/24x24/apps/{icon_name}.png",
            f"/usr/share/icons/hicolor/22x22/panel/{icon_name}.png",
            f"/usr/share/icons/hicolor/32x32/panel/{icon_name}.png",
            f"/usr/share/icons/hicolor/16x16/panel/{icon_name}.png",
            f"/usr/share/icons/hicolor/scalable/panel/{icon_name}.svg",
            f"/usr/share/icons/hicolor/scalable/apps/{icon_name}.svg",
            os.path.join(os.path.dirname(os.path.abspath(__file__)), f"../icons/{icon_name}.svg"),
        ]
        for path in candidates:
            if os.path.exists(path):
                try:
                    status_icon.set_from_file(path)
                    break
                except Exception:
                    pass


class StatusNotifierWatcher(dbus.service.Object):
    def __init__(self):
        bus_name = dbus.service.BusName("org.kde.StatusNotifierWatcher", session_bus)
        super().__init__(bus_name, "/StatusNotifierWatcher")
        self.registered_items = set()

    @dbus.service.method("org.kde.StatusNotifierWatcher", in_signature="s", out_signature="")
    def RegisterStatusNotifierItem(self, service):
        try:
            owner = str(session_bus.get_name_owner(service))
        except Exception:
            owner = service

        if owner in self.registered_items or service in self.registered_items:
            return

        self.registered_items.add(owner)
        self.registered_items.add(service)
        GLib.idle_add(attach_item, service)

    @dbus.service.method("org.kde.StatusNotifierWatcher", in_signature="s", out_signature="")
    def RegisterStatusNotifierHost(self, service):
        pass

    @dbus.service.signal("org.kde.StatusNotifierWatcher", signature="s")
    def StatusNotifierItemRegistered(self, service):
        pass

    @dbus.service.signal("org.kde.StatusNotifierWatcher", signature="s")
    def StatusNotifierItemUnregistered(self, service):
        pass


def attach_item(service):
    global _CURRENT_STATUS_ICON
    if _CURRENT_STATUS_ICON is not None:
        return False

    obj_path = "/StatusNotifierItem"
    bus_name = service

    try:
        obj = session_bus.get_object(bus_name, obj_path)
        props_iface = dbus.Interface(obj, "org.freedesktop.DBus.Properties")
        item_iface = dbus.Interface(obj, "org.kde.StatusNotifierItem")

        icon_name = "audio-speakers"
        try:
            icon_name = str(props_iface.Get("org.kde.StatusNotifierItem", "IconName"))
        except Exception:
            pass

        title = "TiMonde"
        try:
            title = str(props_iface.Get("org.kde.StatusNotifierItem", "Title"))
        except Exception:
            pass

        menu_path = "/MenuBar"
        try:
            menu_path = str(props_iface.Get("org.kde.StatusNotifierItem", "Menu"))
        except Exception:
            pass

        status_icon = Gtk.StatusIcon()
        apply_status_icon(status_icon, icon_name)
        status_icon.set_tooltip_text(title)
        status_icon.set_visible(True)

        # Menu GTK3 connecté directement à l'arbre D-Bus
        gtk_menu = None
        try:
            gtk_menu = DbusmenuGtk3.Menu.new(bus_name, menu_path)
        except Exception as e:
            sys.stderr.write(f"TiMonde XEmbed Bridge: Erreur création Dbusmenu: {e}\n")

        # Style CSS pour forcer la visibilité contrastée des séparateurs GTK3 sur les thèmes sombres et légers (IceWM/antiX)
        try:
            provider = Gtk.CssProvider()
            provider.load_from_data(b"""
            menu separator, menuitem.separator {
                min-height: 2px;
                margin: 4px 8px;
                background-color: #555555;
            }
            """)
            Gtk.StyleContext.add_provider_for_screen(
                Gdk.Screen.get_default(),
                provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
        except Exception:
            pass

        def sanitize_menu(m):
            if not m:
                return
            for child in m.get_children():
                if isinstance(child, Gtk.SeparatorMenuItem):
                    child.set_visible(True)
                elif isinstance(child, Gtk.MenuItem):
                    lbl = getattr(child, "get_label", lambda: None)() or ""
                    # Détection et correction immédiate du bug "Label Empty" de libdbusmenu
                    if lbl == "Label Empty" or (lbl.strip() == "" and not isinstance(child, Gtk.SeparatorMenuItem)):
                        child.set_label("────────────────────────")
                        child.set_sensitive(False)
                    elif "─────" in lbl or "───" in lbl:
                        child.set_sensitive(False)
                    
                    sub = child.get_submenu()
                    if sub:
                        sanitize_menu(sub)

        def calculate_menu_position(menu, _x, _y, icon):
            try:
                success, screen, area, orientation = icon.get_geometry()
                if success and screen:
                    screen_w = screen.get_width()
                    screen_h = screen.get_height()
                    
                    # Calcul de la géométrie réelle en sommant les éléments enfants visibles
                    children = [c for c in menu.get_children() if c.get_visible()]
                    if children:
                        menu_h = sum(c.get_preferred_height()[1] for c in children) + 16
                        menu_w = max((c.get_preferred_width()[1] for c in children), default=220) + 24
                    else:
                        menu_h = 350
                        menu_w = 260
                    
                    pos_x = area.x
                    if pos_x + menu_w > screen_w:
                        pos_x = max(4, screen_w - menu_w - 6)
                        
                    # Si barre des tâches en bas, positionner le bas du menu directement au-dessus du panel
                    if area.y > screen_h // 2:
                        pos_y = max(6, area.y - menu_h)
                    else:
                        pos_y = min(screen_h - menu_h - 6, area.y + area.height)
                        
                    return (int(pos_x), int(pos_y), True)
            except Exception:
                pass
            return (int(_x), int(_y), True)

        def on_activate(icon):
            # Clic gauche : ouverture du menu des stations en pleine hauteur
            if gtk_menu:
                gtk_menu.show_all()
                sanitize_menu(gtk_menu)
                gtk_menu.popup(None, None, calculate_menu_position, icon, 1, Gtk.get_current_event_time())
            else:
                try:
                    item_iface.Activate(0, 0)
                except Exception:
                    pass

        def on_popup(icon, button, activate_time):
            # Clic droit : ouverture du menu des stations en pleine hauteur
            if gtk_menu:
                gtk_menu.show_all()
                sanitize_menu(gtk_menu)
                gtk_menu.popup(None, None, calculate_menu_position, icon, button, activate_time)

        def on_button_press(icon, event):
            if event.button == 2:  # Clic de la molette (milieu) : Play/Stop instantané
                try:
                    item_iface.SecondaryActivate(0, 0)
                except Exception:
                    pass
                return True
            return False

        def on_scroll(icon, event):
            # Molette pour le volume sonore
            delta = -1 if event.direction == 0 else 1
            try:
                item_iface.Scroll(delta, "vertical")
            except Exception:
                pass
            return True

        status_icon.connect("activate", on_activate)
        status_icon.connect("popup-menu", on_popup)
        status_icon.connect("button-press-event", on_button_press)
        status_icon.connect("scroll-event", on_scroll)

        # Mise à jour de l'icône et du titre sur les signaux D-Bus
        def on_update(*args, **kwargs):
            try:
                new_icon = str(props_iface.Get("org.kde.StatusNotifierItem", "IconName"))
                apply_status_icon(status_icon, new_icon)
                new_title = str(props_iface.Get("org.kde.StatusNotifierItem", "Title"))
                status_icon.set_tooltip_text(new_title)
            except Exception:
                pass

        session_bus.add_signal_receiver(on_update, dbus_interface="org.kde.StatusNotifierItem", signal_name="NewIcon")
        session_bus.add_signal_receiver(on_update, dbus_interface="org.kde.StatusNotifierItem", signal_name="NewTitle")
        session_bus.add_signal_receiver(on_update, dbus_interface="org.kde.StatusNotifierItem", signal_name="NewToolTip")

        # Détecter la disparition de TiMonde pour fermer le pont et retirer l'icône instantanément
        def on_name_owner_changed(name, old_owner, new_owner):
            if name == bus_name and not new_owner:
                try:
                    status_icon.set_visible(False)
                except Exception:
                    pass
                GLib.idle_add(cleanup_and_exit)

        session_bus.add_signal_receiver(
            on_name_owner_changed,
            signal_name="NameOwnerChanged",
            dbus_interface="org.freedesktop.DBus",
            arg0=bus_name,
        )

        _CURRENT_STATUS_ICON = status_icon
        print("[OK] Icône XEmbed créée et connectée avec succès dans IceWM / Fluxbox !")
    except Exception as e:
        sys.stderr.write(f"TiMonde XEmbed Bridge: Erreur d'attachement item {service}: {e}\n")

    return False  # Arrête GLib.idle_add


def main():
    watcher = StatusNotifierWatcher()
    Gtk.main()


if __name__ == "__main__":
    main()
