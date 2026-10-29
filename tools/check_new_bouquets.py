#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TiMonde — Détection des nouveaux bouquets DAB+ / mondiaux non répertoriés.
Détecte les pays et territoires du monde (ISO 3166-1) disposant de stations actives
mais ne possédant pas encore de fichier de bouquet dans data/bouquets/.

Usage :
    python3 tools/check_new_bouquets.py [--min-stations 5] [--limit 30]
"""

import os
import sys
import glob
import json
import urllib.request
import xml.etree.ElementTree as ET

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
BOUQUETS_DIR = os.path.join(ROOT_DIR, "data/bouquets")

RADIO_BROWSER_ENDPOINTS = [
    "https://de1.api.radio-browser.info",
    "https://nl1.api.radio-browser.info",
    "https://at1.api.radio-browser.info",
]
USER_AGENT = "TiMonde-Maintainer/0.2.0"

# Alias connus entre codes ISO et noms de fichiers
ISO_FILENAME_ALIASES = {
    "GB": "UK",
}


def get_existing_bouquet_countries():
    """Retourne la liste des codes ISO en majuscules des bouquets existants."""
    existing = set()
    for f in glob.glob(os.path.join(BOUQUETS_DIR, "*.xml")):
        code = os.path.basename(f)[:-4].upper()
        existing.add(code)
        # Gérer les équivalences
        if code == "UK":
            existing.add("GB")
        elif code == "GB":
            existing.add("UK")
    return existing


def fetch_world_countries_stats():
    """Récupère la liste des pays et leur volume de stations sur Radio-Browser."""
    for base in RADIO_BROWSER_ENDPOINTS:
        url = f"{base}/json/countries"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            continue
    return []


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Détection de bouquets manquants dans TiMonde")
    parser.add_argument("--min-stations", type=int, default=5, help="Seuil minimal de stations (défaut: 5)")
    parser.add_argument("--limit", type=int, default=25, help="Nombre max de candidats affichés (défaut: 25)")
    args = parser.parse_args()

    existing = get_existing_bouquet_countries()
    print("=" * 70)
    print("TiMonde — Détection de nouveaux bouquets mondiaux éligibles")
    print("=" * 70)
    print(f"[*] Bouquets déjà répertoriés dans data/bouquets/ : {len(existing)} pays/territoires")
    print("[*] Interrogation des registres mondiaux (Radio-Browser / ISO 3166-1)...")

    countries_data = fetch_world_countries_stats()
    if not countries_data:
        print("[!] Impossible de joindre les serveurs Radio-Browser.")
        sys.exit(1)

    candidates = []
    for c in countries_data:
        iso = (c.get("iso_3166_1") or "").upper().strip()
        count = int(c.get("stationcount", 0))
        name = c.get("name", "").strip()
        if not iso or count < args.min_stations:
            continue
        if iso not in existing:
            candidates.append({
                "iso": iso,
                "name": name,
                "station_count": count,
            })

    candidates.sort(key=lambda x: x["station_count"], reverse=True)

    print(f"\n[+] Nombre de pays/territoires éligibles non répertoriés (>= {args.min_stations} radios) : {len(candidates)}")
    print("=" * 70)
    print(f"{'Code':<6} | {'Pays / Territoire':<38} | {'Stations':<8}")
    print("-" * 70)
    for c in candidates[:args.limit]:
        print(f"[{c['iso']:<4}] | {c['name'][:38]:<38} | {c['station_count']:<8}")
    print("=" * 70)

    # Sauvegarde du rapport en JSON
    out_dir = os.path.join(ROOT_DIR, "temp")
    os.makedirs(out_dir, exist_ok=True)
    report_file = os.path.join(out_dir, "missing_bouquets_candidates.json")
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump({
            "total_existing_bouquets": len(existing),
            "total_candidates": len(candidates),
            "min_stations_threshold": args.min_stations,
            "candidates": candidates,
        }, f, indent=2, ensure_ascii=False)
    print(f"[+] Rapport des candidats sauvegardé dans {report_file}\n")


if __name__ == "__main__":
    main()
