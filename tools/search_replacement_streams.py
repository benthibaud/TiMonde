#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TiMonde — Recherche multi-sources de flux de remplacement pour les stations hors-ligne.
Interroge Radio-Browser, Radio.net API et Streema, valide en temps réel l'accessibilité
du stream audio (codec, HTTP 200, non-géobloqué) et génère des propositions ou applique les mises à jour.

Usage :
    python3 tools/search_replacement_streams.py [--apply]
"""

import os
import sys
import json
import time
import re
import base64
import zlib
import urllib.request
import urllib.parse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
SCRIPTS_DIR = os.path.join(ROOT_DIR, "data/scripts")
sys.path.insert(0, SCRIPTS_DIR)

from timonde_common import check_stream_url

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) TiMonde-Maintainer/0.2.0"


def query_radio_browser(name, country_code):
    """Recherche un flux opérationnel sur Radio-Browser."""
    # Nettoyer les suffixes fréquents
    clean_name = re.sub(r'\s*\([^)]*\)', '', name)
    clean_name = re.sub(r'\s*/\s*.*', '', clean_name).strip()
    encoded_name = urllib.parse.quote(clean_name)
    url = f"https://de1.api.radio-browser.info/json/stations/byname/{encoded_name}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for item in data:
                # Si pays spécifié, vérifier la cohérence
                item_cc = (item.get("countrycode") or "").upper()
                if country_code and item_cc and item_cc != country_code.upper():
                    continue
                st_url = item.get("url_resolved") or item.get("url")
                if not st_url or not (st_url.startswith("http://") or st_url.startswith("https://")):
                    continue
                ok, msg = check_stream_url(st_url, timeout=3)
                if ok is True:
                    return {
                        "source": "Radio-Browser",
                        "name": item.get("name"),
                        "url": st_url,
                        "codec": msg,
                    }
    except Exception:
        pass
    return None


def query_radio_net(name):
    """Recherche un flux opérationnel sur Radio.net API."""
    clean_name = re.sub(r'\s*\([^)]*\)', '', name)
    clean_name = re.sub(r'\s*/\s*.*', '', clean_name).strip()
    encoded = urllib.parse.quote(clean_name)
    url = f"https://prod.radio-api.net/stations/search?query={encoded}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for p in data.get("playables", []):
                for st in p.get("streams", []):
                    st_url = st.get("url")
                    if not st_url or not (st_url.startswith("http://") or st_url.startswith("https://")):
                        continue
                    ok, msg = check_stream_url(st_url, timeout=3)
                    if ok is True:
                        return {
                            "source": "Radio.net",
                            "name": p.get("name"),
                            "url": st_url,
                            "codec": msg,
                        }
    except Exception:
        pass
    return None


def query_streema(slug):
    """Interroge Streema et décode la payload Nuxt zlib+base64."""
    url = f"https://streema.com/radios/play/{slug}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            m = re.search(r'\"encoded_stream_url\":\s*\"([^\"]+)\"', html)
            if m:
                dec = zlib.decompress(base64.b64decode(m.group(1))).decode("utf-8")
                ok, msg = check_stream_url(dec, timeout=3)
                if ok is True:
                    return {
                        "source": "Streema",
                        "name": slug,
                        "url": dec,
                        "codec": msg,
                    }
    except Exception:
        pass
    return None


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Recherche de flux de substitution pour radios hors-ligne")
    parser.add_argument("--apply", action="store_true", help="Appliquer les remplacements trouvés dans les XML")
    args = parser.parse_args()

    report_path = os.path.join(ROOT_DIR, "temp/audit_streams_report.json")
    if not os.path.exists(report_path):
        print(f"[!] Fichier {report_path} introuvable. Lancez tools/audit_collection_streams.py au préalable.")
        sys.exit(1)

    with open(report_path, "r", encoding="utf-8") as f:
        audit_data = json.load(f)

    offline_stations = audit_data.get("offline_stations", [])
    print("=" * 70)
    print(f"TiMonde — Recherche multi-sources pour {len(offline_stations)} stations hors-ligne")
    print("=" * 70)

    found_replacements = []

    for i, st in enumerate(offline_stations, 1):
        name = st.get("name")
        country = st.get("country")
        source = st.get("source")
        old_url = st.get("url")

        print(f"[{i:2d}/{len(offline_stations)}] Recherche pour : [{country}] {name}...", end=" ", flush=True)

        res = query_radio_net(name)
        if not res:
            res = query_radio_browser(name, country)
        if not res:
            # Essai slug Streema
            slug = re.sub(r'[^a-zA-Z0-9]+', '_', name).strip('_')
            res = query_streema(slug)

        if res:
            print(f"TROUVÉ via {res['source']} ({res['codec']})")
            print(f"    Ancien : {old_url}")
            print(f"    Nouveau : {res['url']}")
            found_replacements.append({
                "station": st,
                "replacement": res,
            })
        else:
            print("Aucun flux opérationnel validé")

    print("\n" + "=" * 70)
    print(f"BILAN DES FLUX DE REMPLACEMENT : {len(found_replacements)} trouvés / {len(offline_stations)} hors-ligne")
    print("=" * 70)

    # Sauvegarde du rapport
    rep_file = os.path.join(ROOT_DIR, "temp/found_stream_replacements.json")
    with open(rep_file, "w", encoding="utf-8") as f:
        json.dump(found_replacements, f, indent=2, ensure_ascii=False)
    print(f"[+] Propositions sauvegardées dans {rep_file}")

    if args.apply and found_replacements:
        print("\n[*] Application des remplacements dans les fichiers de bouquets...")
        modified_files = set()
        for item in found_replacements:
            st = item["station"]
            new_url = item["replacement"]["url"]
            old_url = st["url"]
            # Trouver le fichier cible
            all_sources = st.get("all_sources", [])
            for src in all_sources:
                stype, sfile = src.split(":")
                if stype == "bouquet":
                    target_xml = os.path.join(ROOT_DIR, "data/bouquets", sfile)
                else:
                    target_xml = os.path.join(ROOT_DIR, "data/examples", sfile)
                if os.path.exists(target_xml):
                    with open(target_xml, "r", encoding="utf-8") as xf:
                        content = xf.read()
                    if old_url in content:
                        content = content.replace(f'url="{old_url}"', f'url="{new_url}"')
                        with open(target_xml, "w", encoding="utf-8") as xf:
                            xf.write(content)
                        modified_files.add(target_xml)
        print(f"[+] {len(modified_files)} fichiers mis à jour avec succès.")


if __name__ == "__main__":
    main()
