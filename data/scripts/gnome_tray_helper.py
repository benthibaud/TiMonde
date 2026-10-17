#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TiMonde — Assistant d'Intégration du Bureau GNOME Shell
Vérifie la présence du support StatusNotifierItem / AppIndicator sous GNOME Shell.
Si le support est absent, propose à l'utilisateur de l'installer en un clic via pkexec
pour les distributions Debian, Ubuntu, Linux Mint, Fedora, openSUSE et Arch Linux.
"""

import sys
import os
import subprocess
import shutil

# Neutralisation préventive IBus pour éviter tout conflit GTK
for _v in ("GTK_IM_MODULE", "XMODIFIERS", "QT_IM_MODULE"):
    os.environ.pop(_v, None)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from timonde_i18n import _
except ImportError:
    def _(s): return s


def is_gnome_shell():
    """Détecte formellement si la session graphique active est GNOME Shell."""
    desktop = (os.environ.get("XDG_CURRENT_DESKTOP") or "").upper()
    session = (os.environ.get("DESKTOP_SESSION") or "").upper()

    # Exclure les bureaux dérivés ou équipés de leur propre barre des tâches native
    for other in ("XFCE", "CINNAMON", "MATE", "KDE", "LXQT", "PANTHEON", "COSMIC"):
        if other in desktop or other in session:
            return False

    if "GNOME" in desktop or "GNOME" in session:
        return True

    # Vérification secondaire via binaire gnome-shell
    if shutil.which("gnome-shell"):
        # Vérifier si gnome-shell est en cours d'exécution
        try:
            res = subprocess.run(["pgrep", "-x", "gnome-shell"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode == 0:
                return True
        except Exception:
            pass

    return False


def is_appindicator_active():
    """Vérifie si un watcher StatusNotifierItem ou l'extension AppIndicator est actif."""
    # 1. Vérification D-Bus : si org.kde.StatusNotifierWatcher est possédé sur le session bus
    try:
        import dbus
        bus = dbus.SessionBus()
        if bus.name_has_owner("org.kde.StatusNotifierWatcher"):
            return True
    except Exception:
        pass

    # 2. Vérification via commande gnome-extensions
    if shutil.which("gnome-extensions"):
        try:
            res = subprocess.run(
                ["gnome-extensions", "list", "--enabled"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            if res.returncode == 0:
                out = res.stdout.lower()
                if "appindicator" in out or "ubuntu-appindicators" in out or "kstatusnotifieritem" in out:
                    return True
        except Exception:
            pass

    return False


def get_install_command():
    """Détermine la commande d'installation Polkit selon la distribution Linux."""
    if shutil.which("apt-get"):
        return ["pkexec", "apt-get", "install", "-y", "gnome-shell-extension-appindicator"]
    elif shutil.which("dnf"):
        return ["pkexec", "dnf", "install", "-y", "gnome-shell-extension-appindicator"]
    elif shutil.which("zypper"):
        return ["pkexec", "zypper", "--non-interactive", "in", "gnome-shell-extension-appindicator"]
    elif shutil.which("pacman"):
        return ["pkexec", "pacman", "-S", "--noconfirm", "gnome-shell-extension-appindicator"]
    return None


def enable_gnome_extensions():
    """Tente d'activer l'extension GNOME installée."""
    if not shutil.which("gnome-extensions"):
        return
    for ext_id in ("appindicatorsupport@rgcjonas.gmail.com", "ubuntu-appindicators@ubuntu.com"):
        try:
            subprocess.run(["gnome-extensions", "enable", ext_id], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass


class GnomeHelperDialog:
    """Boîte de dialogue GTK3 soignée invitant à installer l'extension sous GNOME."""

    def __init__(self):
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk, Gdk

        self.Gtk = Gtk
        self.success = False

        self.win = Gtk.Window(title=_("TiMonde — Intégration Bureau GNOME"))
        self.win.set_position(Gtk.WindowPosition.CENTER)
        self.win.set_default_size(480, 220)
        self.win.set_border_width(16)
        self.win.set_resizable(False)

        # Icône de fenêtre
        for icon_path in (
            "/usr/share/icons/hicolor/scalable/apps/timonde_on.svg",
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "../icons/timonde_on.svg")
        ):
            if os.path.isfile(icon_path):
                self.win.set_icon_from_file(icon_path)
                break

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.win.add(vbox)

        # En-tête avec titre et icône
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        vbox.pack_start(header_box, False, False, 0)

        lbl_icon = Gtk.Label()
        lbl_icon.set_markup("<span font='32'>📻</span>")
        header_box.pack_start(lbl_icon, False, False, 0)

        vbox_titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        lbl_title = Gtk.Label()
        lbl_title.set_markup("<b><span size='large'>" + _("Intégration dans la barre supérieure GNOME") + "</span></b>")
        lbl_title.set_halign(Gtk.Align.START)
        vbox_titles.pack_start(lbl_title, False, False, 0)

        lbl_sub = Gtk.Label()
        lbl_sub.set_markup("<span opacity='0.75'>" + _("Environnement GNOME Shell détecté") + "</span>")
        lbl_sub.set_halign(Gtk.Align.START)
        vbox_titles.pack_start(lbl_sub, False, False, 0)

        header_box.pack_start(vbox_titles, True, True, 0)

        # Explication claire
        lbl_desc = Gtk.Label()
        lbl_desc.set_markup(
            _("Pour afficher discrètement l'icône de lecture dans la barre supérieure de votre bureau GNOME, "
              "l'extension système <b>AppIndicator</b> est nécessaire.<br/><br/>"
              "Souhaitez-vous l'installer maintenant ?")
        )
        lbl_desc.set_line_wrap(True)
        lbl_desc.set_halign(Gtk.Align.START)
        vbox.pack_start(lbl_desc, True, True, 0)

        # Message d'état / erreur
        self.lbl_status = Gtk.Label(label="")
        self.lbl_status.set_halign(Gtk.Align.START)
        vbox.pack_start(self.lbl_status, False, False, 0)

        # Boutons d'action
        bbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        bbox.set_halign(Gtk.Align.END)
        vbox.pack_end(bbox, False, False, 0)

        self.btn_quit = Gtk.Button(label=_("Quitter"))
        self.btn_quit.connect("clicked", self.on_quit_clicked)
        bbox.pack_start(self.btn_quit, False, False, 0)

        self.btn_install = Gtk.Button(label=_("Installer l'intégration GNOME"))
        self.btn_install.get_style_context().add_class("suggested-action")
        self.btn_install.connect("clicked", self.on_install_clicked)
        bbox.pack_start(self.btn_install, False, False, 0)

        self.win.connect("delete-event", lambda w, e: Gtk.main_quit())

    def on_quit_clicked(self, widget):
        self.success = False
        self.Gtk.main_quit()

    def on_install_clicked(self, widget):
        cmd = get_install_command()
        if not cmd:
            self.lbl_status.set_markup("<span color='#e06c75'>" + _("Gestionnaire de paquets non reconnu.") + "</span>")
            return

        self.btn_install.set_sensitive(False)
        self.btn_quit.set_sensitive(False)
        self.lbl_status.set_markup("<i>" + _("Installation en cours (veuillez valider l'invite système)...") + "</i>")

        # Forcer le rafraîchissement GTK avant de bloquer sur pkexec
        while self.Gtk.events_pending():
            self.Gtk.main_iteration()

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode == 0:
                enable_gnome_extensions()
                self.success = True
                self.Gtk.main_quit()
            else:
                self.btn_install.set_sensitive(True)
                self.btn_quit.set_sensitive(True)
                self.lbl_status.set_markup("<span color='#e06c75'>" + _("L'installation a été annulée ou a échoué.") + "</span>")
        except Exception as e:
            self.btn_install.set_sensitive(True)
            self.btn_quit.set_sensitive(True)
            self.lbl_status.set_markup(f"<span color='#e06c75'>{_('Erreur :')} {e}</span>")

    def run(self):
        import gi
        from gi.repository import Gtk
        self.win.show_all()
        Gtk.main()
        return 0 if self.success else 1


def main():
    if "--check" in sys.argv:
        # Retourne 1 si GNOME et AppIndicator absent, 0 sinon
        if is_gnome_shell() and not is_appindicator_active():
            sys.exit(1)
        sys.exit(0)

    if "--prompt" in sys.argv or len(sys.argv) == 1:
        if is_gnome_shell() and not is_appindicator_active():
            helper = GnomeHelperDialog()
            code = helper.run()
            sys.exit(code)
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
