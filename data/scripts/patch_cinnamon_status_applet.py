#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script d'harmonisation Cinnamon pour TiMonde (Approche Hybride Automatique) :
Permet d'ouvrir indifféremment le menu des radios avec le CLIC GAUCHE ou le CLIC DROIT.

Modes d'exécution :
- Mode Utilisateur (par défaut hors root ou avec --user) :
  Si ~/.local/share/cinnamon/ existe, installe l'applet harmonisée dans
  ~/.local/share/cinnamon/applets/xapp-status@cinnamon.org/ (immunisé contre les mises à jour APT).
  Si ~/.local/share/cinnamon/ n'existe pas, ne fait rien (système hôte non-Cinnamon préservé).
- Mode Système (root ou avec --system) :
  Si /usr/share/cinnamon/ existe, patche l'applet système et installe un hook APT
  dans /etc/apt/apt.conf.d/99timonde-cinnamon pour pérenniser le patch pour toutes les sessions.
- Mode Diagnostic (--check) :
  Retourne le code 0 si TiMonde est harmonisé sous Cinnamon, code 1 sinon.
- Mode Restauration (--restore / --uninstall) :
  Restaure l'applet Cinnamon d'origine.
"""

import os
import sys
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from timonde_common import atomic_write_file
except ImportError:
    def atomic_write_file(path, content, encoding="utf-8"):
        tmp = path + ".tmp"
        with open(tmp, "w", encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

SYS_APPLET_DIR = "/usr/share/cinnamon/applets/xapp-status@cinnamon.org"
SYS_APPLET_PATH = os.path.join(SYS_APPLET_DIR, "applet.js")
SYS_BACKUP_PATH = f"{SYS_APPLET_PATH}.orig_timonde"
APT_HOOK_PATH = "/etc/apt/apt.conf.d/99timonde-cinnamon"

USER_CINNAMON_DIR = os.path.expanduser("~/.local/share/cinnamon")
USER_APPLET_DIR = os.path.join(USER_CINNAMON_DIR, "applets", "xapp-status@cinnamon.org")
USER_APPLET_PATH = os.path.join(USER_APPLET_DIR, "applet.js")

TARGET = """    onButtonPressEvent(actor, event) {
        this._tooltip.hide();
        this._tooltip.preventShow = true;

        if (event.get_button() == Clutter.BUTTON_SECONDARY && event.get_state() & Clutter.ModifierType.CONTROL_MASK) {
            return Clutter.EVENT_PROPAGATE;
        }

        let [x, y, o] = this.getEventPositionInfo(actor);

        this.proxy.call_button_press(x, y, event.get_button(), event.get_time(), o, null, null);

        return Clutter.EVENT_STOP;
    }

    onButtonReleaseEvent(actor, event) {
        let [x, y, o] = this.getEventPositionInfo(actor);

        this.proxy.call_button_release(x, y, event.get_button(), event.get_time(), o, null, null);

        return Clutter.EVENT_STOP;
    }"""

REPLACEMENT = """    onButtonPressEvent(actor, event) {
        this._tooltip.hide();
        this._tooltip.preventShow = true;

        if (event.get_button() == Clutter.BUTTON_SECONDARY && event.get_state() & Clutter.ModifierType.CONTROL_MASK) {
            return Clutter.EVENT_PROPAGATE;
        }

        let [x, y, o] = this.getEventPositionInfo(actor);

        let button = event.get_button();
        let iconStr = (this.iconName || '').toLowerCase();
        if (iconStr.indexOf('timonde') !== -1 && button === Clutter.BUTTON_PRIMARY) {
            button = Clutter.BUTTON_SECONDARY;
        }

        this.proxy.call_button_press(x, y, button, event.get_time(), o, null, null);

        return Clutter.EVENT_STOP;
    }

    onButtonReleaseEvent(actor, event) {
        let [x, y, o] = this.getEventPositionInfo(actor);

        let button = event.get_button();
        let iconStr = (this.iconName || '').toLowerCase();
        if (iconStr.indexOf('timonde') !== -1 && button === Clutter.BUTTON_PRIMARY) {
            button = Clutter.BUTTON_SECONDARY;
        }

        this.proxy.call_button_release(x, y, button, event.get_time(), o, null, null);

        return Clutter.EVENT_STOP;
    }"""


def reload_cinnamon_applet():
    """Recharge l'applet Cinnamon à chaud via D-Bus sans redémarrer la session."""
    if "DBUS_SESSION_BUS_ADDRESS" not in os.environ:
        return False
    try:
        import dbus
        bus = dbus.SessionBus()
        obj = bus.get_object("org.Cinnamon", "/org/Cinnamon")
        iface = dbus.Interface(obj, "org.Cinnamon")
        iface.ReloadXlet("xapp-status@cinnamon.org", "APPLET")
        return True
    except Exception:
        return False


def is_patched(filepath):
    if not os.path.isfile(filepath):
        return False
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        return "iconStr.indexOf('timonde')" in content
    except Exception:
        return False


def apply_patch_to_string(content):
    if "iconStr.indexOf('timonde')" in content:
        return content, True
    if TARGET in content:
        return content.replace(TARGET, REPLACEMENT), True
    return content, False


def check_status():
    """Retourne 0 si un patch actif est détecté, 1 sinon."""
    if is_patched(USER_APPLET_PATH) or is_patched(SYS_APPLET_PATH):
        return 0
    return 1


def restore():
    restored = False
    # 1. Restauration utilisateur
    if os.path.exists(USER_APPLET_DIR):
        try:
            shutil.rmtree(USER_APPLET_DIR)
            print(f"[OK] Applet utilisateur supprimée : {USER_APPLET_DIR}")
            restored = True
        except Exception as e:
            sys.stderr.write(f"Erreur suppression {USER_APPLET_DIR}: {e}\n")

    # 2. Restauration système si root
    if os.path.exists(SYS_BACKUP_PATH) and os.access(SYS_APPLET_DIR, os.W_OK):
        try:
            shutil.copy2(SYS_BACKUP_PATH, SYS_APPLET_PATH)
            os.remove(SYS_BACKUP_PATH)
            print(f"[OK] Applet système d'origine restaurée : {SYS_APPLET_PATH}")
            restored = True
        except Exception as e:
            sys.stderr.write(f"Erreur restauration {SYS_APPLET_PATH}: {e}\n")

    if os.path.exists(APT_HOOK_PATH) and os.access(os.path.dirname(APT_HOOK_PATH), os.W_OK):
        try:
            os.remove(APT_HOOK_PATH)
        except Exception:
            pass

    if restored:
        reload_cinnamon_applet()
    return 0


def install_user_mode():
    # Si ~/.local/share/cinnamon/ n'existe pas, l'utilisateur n'est pas sous Cinnamon
    if not os.path.isdir(USER_CINNAMON_DIR):
        print(f"Environnement Cinnamon non détecté ({USER_CINNAMON_DIR} absent). Aucune action requise.")
        return 0

    if not os.path.isfile(SYS_APPLET_PATH):
        print("Applet système xapp-status@cinnamon.org introuvable.")
        return 0

    os.makedirs(USER_APPLET_DIR, exist_ok=True)

    # Copier metadata.json si absent
    src_meta = os.path.join(SYS_APPLET_DIR, "metadata.json")
    dst_meta = os.path.join(USER_APPLET_DIR, "metadata.json")
    if os.path.isfile(src_meta) and not os.path.isfile(dst_meta):
        shutil.copy2(src_meta, dst_meta)

    # Récupérer la version propre d'applet.js
    source_js = SYS_BACKUP_PATH if os.path.isfile(SYS_BACKUP_PATH) else SYS_APPLET_PATH
    with open(source_js, "r", encoding="utf-8") as f:
        src_content = f.read()

    new_content, ok = apply_patch_to_string(src_content)
    if not ok:
        print("Avertissement : motif de patch introuvable dans applet.js.")
        return 1

    atomic_write_file(USER_APPLET_PATH, new_content)

    print(f"[OK] Patch Cinnamon installé dans l'espace utilisateur : {USER_APPLET_PATH}")
    if reload_cinnamon_applet():
        print("[OK] Applet Cinnamon rechargée à chaud avec succès !")
    return 0


def install_system_mode():
    if not os.path.isfile(SYS_APPLET_PATH):
        print(f"Cinnamon non détecté au niveau système ({SYS_APPLET_PATH} absent).")
        return 0

    if not os.access(SYS_APPLET_PATH, os.W_OK):
        sys.stderr.write("Erreur : droits administrateur (root/sudo) requis pour le mode système.\n")
        return 1

    with open(SYS_APPLET_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    if is_patched(SYS_APPLET_PATH):
        print("L'applet système Cinnamon prend déjà en charge TiMonde.")
    else:
        # Créer le backup si absent
        if not os.path.exists(SYS_BACKUP_PATH):
            shutil.copy2(SYS_APPLET_PATH, SYS_BACKUP_PATH)

        new_content, ok = apply_patch_to_string(content)
        if not ok:
            print("Avertissement : motif de patch introuvable dans applet.js.")
            return 1

        atomic_write_file(SYS_APPLET_PATH, new_content)
        print(f"[OK] Patch Cinnamon appliqué au niveau système : {SYS_APPLET_PATH}")

    # Installer le hook APT si possible pour pérenniser lors des mises à jour système
    apt_dir = os.path.dirname(APT_HOOK_PATH)
    if os.path.isdir(apt_dir) and os.access(apt_dir, os.W_OK):
        hook_content = (
            '// Maintien automatique de l\'harmonisation TiMonde sous Cinnamon\n'
            'DPkg::Post-Invoke {"if [ -x /usr/share/timonde/scripts/patch_cinnamon_status_applet.py ]; '
            'then /usr/share/timonde/scripts/patch_cinnamon_status_applet.py --system >/dev/null 2>&1 || true; fi;"};\n'
        )
        try:
            atomic_write_file(APT_HOOK_PATH, hook_content)
            print(f"[OK] Hook APT enregistré : {APT_HOOK_PATH}")
        except Exception:
            pass

    reload_cinnamon_applet()
    return 0


def main():
    if "--check" in sys.argv:
        sys.exit(check_status())

    if "--restore" in sys.argv or "--uninstall" in sys.argv:
        sys.exit(restore())

    force_system = "--system" in sys.argv
    force_user = "--user" in sys.argv

    # Décision automatique :
    # Si root ou explicitement demandé, mode système.
    # Sinon, mode utilisateur.
    if force_system or (os.geteuid() == 0 and not force_user):
        sys.exit(install_system_mode())
    else:
        sys.exit(install_user_mode())


if __name__ == "__main__":
    main()
