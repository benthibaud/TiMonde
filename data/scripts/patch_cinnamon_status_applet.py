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
        print(f"Applet Cinnamon non trouvée : {APPLET_PATH}")
        return

    with open(APPLET_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    if "iconStr.indexOf('timonde')" in content:
        print("L'applet Cinnamon prend déjà en charge le clic gauche pour TiMonde.")
    elif TARGET in content:
        new_content = content.replace(TARGET, REPLACEMENT)
        with open(APPLET_PATH, "w", encoding="utf-8") as f:
            f.write(new_content)
        print("Patch appliqué avec succès dans applet.js !")
    else:
        print("Motif cible non trouvé dans applet.js.")

    # Rechargement D-Bus à chaud de l'applet Cinnamon
    try:
        import dbus
        bus = dbus.SessionBus()
        obj = bus.get_object("org.Cinnamon", "/org/Cinnamon")
        iface = dbus.Interface(obj, "org.Cinnamon")
        iface.ReloadXlet("xapp-status@cinnamon.org", "APPLET")
        print("Applet Cinnamon rechargée à chaud avec succès !")
    except Exception as e:
        print(f"Information rechargement : {e}")

if __name__ == "__main__":
    main()
