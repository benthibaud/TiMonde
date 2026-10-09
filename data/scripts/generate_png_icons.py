#!/usr/bin/env python3
# ==============================================================================
# Générateur d'icônes matricielles PNG pour TiMonde
# Génère les résolutions 16, 22, 24, 32, 48, 64, 128, 256 à partir des SVG
# ==============================================================================

import os
import sys
import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "../.."))
ICONS_DIR = os.path.join(ROOT_DIR, "data/icons")

SIZES = [16, 22, 24, 32, 48, 64, 128, 256]
ICONS = ["timonde_on", "timonde_off", "timonde_error"]

def main():
    for icon_name in ICONS:
        svg_path = os.path.join(ICONS_DIR, f"{icon_name}.svg")
        if not os.path.exists(svg_path):
            print(f"[!] Fichier source introuvable : {svg_path}")
            continue

        for size in SIZES:
            for cat in ["apps", "panel"]:
                target_dir = os.path.join(ICONS_DIR, f"hicolor/{size}x{size}/{cat}")
                os.makedirs(target_dir, exist_ok=True)
                dest_file = os.path.join(target_dir, f"{icon_name}.png")

                try:
                    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(svg_path, size, size, True)
                    pb.savev(dest_file, "png", [], [])
                except Exception as e:
                    print(f"Erreur rendu {icon_name} {size}x{size}: {e}")

    print("[OK] Génération des icônes PNG terminée avec succès !")

if __name__ == "__main__":
    main()
