#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script d'harmonisation Cinnamon pour TiMonde :
Permet d'ouvrir indifféremment le menu des radios avec le CLIC GAUCHE ou le CLIC DROIT.
Recharge l'applet xapp-status@cinnamon.org à chaud sans fermer la session.
"""

import os
import sys

APPLET_PATH = "/usr/share/cinnamon/applets/xapp-status@cinnamon.org/applet.js"

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

def main():
    if not os.path.exists(APPLET_PATH):
        # Cinnamon n'est pas installé sur cette machine
        return

    backup_path = f"{APPLET_PATH}.orig_timonde"

    if "--restore" in sys.argv:
        if os.path.exists(backup_path):
            import shutil
            shutil.copy2(backup_path, APPLET_PATH)
            os.remove(backup_path)
            print("Applet Cinnamon originale restaurée.")
        return

    with open(APPLET_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    if "iconStr.indexOf('timonde')" in content:
        print("L'applet Cinnamon prend déjà en charge le clic gauche pour TiMonde.")
    elif TARGET in content:
        # Création du backup d'origine avant modification
        if not os.path.exists(backup_path):
            try:
                import shutil
                shutil.copy2(APPLET_PATH, backup_path)
            except Exception as e:
                sys.stderr.write(f"Avertissement création backup : {e}\n")

        new_content = content.replace(TARGET, REPLACEMENT)
        with open(APPLET_PATH, "w", encoding="utf-8") as f:
            f.write(new_content)
        print("Cinnamon détecté : patch harmonisation clic gauche appliqué avec succès !")
    else:
        print("Motif cible non trouvé dans applet.js (version de Cinnamon différente).")

    # Rechargement D-Bus à chaud si exécuté dans la session de l'utilisateur
    if "DBUS_SESSION_BUS_ADDRESS" in os.environ:
        try:
            import dbus
            bus = dbus.SessionBus()
            obj = bus.get_object("org.Cinnamon", "/org/Cinnamon")
            iface = dbus.Interface(obj, "org.Cinnamon")
            iface.ReloadXlet("xapp-status@cinnamon.org", "APPLET")
            print("Applet Cinnamon rechargée à chaud avec succès !")
        except Exception:
            pass

if __name__ == "__main__":
    main()
