#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TiMonde — Protocole d'audit et de vérification des flux des bouquets et exemples.
Audit & Verification Tool for all offline station streams in TiMonde.

Distingue avec précision :
- 🟢 En ligne direct (Online)
- 🔄 Redirection propre (Accessible via nouvelle URL)
- 🟡 Géobloqué (Inaccessible depuis l'IP locale sans VPN : Amperwave/Audacy/StreamTheWorld/HTTP 403/451/503)
- 🔴 Hors-ligne réel (Erreur 404, DNS introuvable, timeout définitif, connexion refusée)
"""

import os
import sys
import glob
import json
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

# Importer le socle commun TiMonde
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
SCRIPTS_DIR = os.path.join(ROOT_DIR, "data/scripts")
sys.path.insert(0, SCRIPTS_DIR)

from timonde_common import check_stream_url, clean_stream_url, safe_parse_xml

def collect_all_stations():
    items = []
    
    # 1. Bouquets DAB+
    for bq_file in sorted(glob.glob(os.path.join(ROOT_DIR, "data/bouquets/*.xml"))):
        base = os.path.basename(bq_file)
        root = safe_parse_xml(bq_file)
        if root is not None:
            for s in root.findall(".//station"):
                name = s.attrib.get("name", "").strip()
                url = s.attrib.get("url", "").strip()
                country = s.attrib.get("country", "").strip() or base[:-4].upper()
                if url:
                    items.append({
                        "name": name,
                        "url": url,
                        "country": country,
                        "source_type": "bouquet",
                        "source_file": base,
                    })

    # 2. Exemples
    for ex_file in sorted(glob.glob(os.path.join(ROOT_DIR, "data/examples/*"))):
        base = os.path.basename(ex_file)
        if ex_file.endswith(".xml"):
            root = safe_parse_xml(ex_file)
            if root is not None:
                for s in root.findall(".//station"):
                    name = s.attrib.get("name", "").strip()
                    url = s.attrib.get("url", "").strip()
                    country = s.attrib.get("country", "").strip()
                    if url:
                        items.append({
                            "name": name,
                            "url": url,
                            "country": country,
                            "source_type": "example",
                            "source_file": base,
                        })
        elif ex_file.endswith(".json"):
            try:
                with open(ex_file, "r", encoding="utf-8") as jf:
                    data = json.load(jf)
                for it in data:
                    if isinstance(it, dict) and "stations" in it:
                        for s in it["stations"]:
                            if s.get("url"):
                                items.append({
                                    "name": s.get("name", "").strip(),
                                    "url": s.get("url", "").strip(),
                                    "country": s.get("country", "").strip(),
                                    "source_type": "example",
                                    "source_file": base,
                                })
                    elif isinstance(it, dict) and it.get("url"):
                        items.append({
                            "name": it.get("name", "").strip(),
                            "url": it.get("url", "").strip(),
                            "country": it.get("country", "").strip(),
                            "source_type": "example",
                            "source_file": base,
                        })
            except Exception:
                pass
        elif ex_file.endswith(".csv"):
            try:
                with open(ex_file, "r", encoding="utf-8", errors="replace") as cf:
                    for line in cf:
                        cols = [c.strip() for c in line.split(",")]
                        if len(cols) >= 2 and (cols[1].startswith("http://") or cols[1].startswith("https://")):
                            items.append({
                                "name": cols[0],
                                "url": cols[1],
                                "country": cols[2] if len(cols) > 2 else "",
                                "source_type": "example",
                                "source_file": base,
                            })
            except Exception:
                pass

    return items


def test_station(st):
    url = st["url"]
    status, msg, redir = check_stream_url(url, timeout=3.5, with_redirect=True)
    return {
        "station": st,
        "status": status,  # True, False, "GEO"
        "message": msg,
        "redirect": redir,
    }


def main():
    print("=" * 70)
    print("TiMonde — Audit complet des flux de la collection (DAB+ & Exemples)")
    print("=" * 70)
    
    stations = collect_all_stations()
    total_stations = len(stations)
    
    # Dédoublonnage par URL pour ne tester chaque flux qu'une seule fois
    url_to_stations = {}
    for st in stations:
        u = st["url"]
        if u not in url_to_stations:
            url_to_stations[u] = []
        url_to_stations[u].append(st)

    unique_urls = list(url_to_stations.keys())
    print(f"[*] Stations recensées : {total_stations} stations ({len(unique_urls)} URLs uniques)")
    print("[*] Lancement des tests multithreadés (32 threads, timeout 3.5s)...")

    start_t = time.time()
    
    def test_single_url(u):
        status, msg, redir = check_stream_url(u, timeout=3.5, with_redirect=True)
        return u, status, msg, redir

    with ThreadPoolExecutor(max_workers=32) as executor:
        url_results = list(executor.map(test_single_url, unique_urls))

    elapsed = time.time() - start_t
    print(f"[*] Test terminé en {elapsed:.1f} secondes.\n")

    results_map = {u: (status, msg, redir) for u, status, msg, redir in url_results}

    online_list = []
    redirect_list = []
    geoblocked_list = []
    offline_list = []

    for u, (status, msg, redir) in results_map.items():
        st_refs = url_to_stations[u]
        first_st = st_refs[0]
        entry = {
            "name": first_st["name"],
            "url": u,
            "country": first_st["country"],
            "source": f"{first_st['source_type']} ({first_st['source_file']})",
            "all_sources": [f"{s['source_type']}:{s['source_file']}" for s in st_refs],
            "message": msg,
            "redirect": redir,
        }
        if status is True:
            if redir:
                redirect_list.append(entry)
            else:
                online_list.append(entry)
        elif status == "GEO":
            geoblocked_list.append(entry)
        else:
            offline_list.append(entry)

    print("=" * 70)
    print("BILAN SYNTHÉTIQUE DE L'AUDIT")
    print("=" * 70)
    print(f"🟢 Directement fonctionnelles (Online)  : {len(online_list):4d} ({len(online_list)/len(unique_urls)*100:5.1f}%)")
    print(f"🔄 Redirections valides (Mise à jour)   : {len(redirect_list):4d} ({len(redirect_list)/len(unique_urls)*100:5.1f}%)")
    print(f"🟡 Géobloquées (Accessible via VPN)     : {len(geoblocked_list):4d} ({len(geoblocked_list)/len(unique_urls)*100:5.1f}%)")
    print(f"🔴 Réellement hors-ligne / Erreurs      : {len(offline_list):4d} ({len(offline_list)/len(unique_urls)*100:5.1f}%)")
    print(f"TOTAL URLs UNIQUES AUDITÉES             : {len(unique_urls):4d}")
    print("=" * 70)

    # Sauvegarde des rapports
    out_dir = os.path.join(ROOT_DIR, "temp")
    os.makedirs(out_dir, exist_ok=True)
    report_file = os.path.join(out_dir, "audit_streams_report.json")
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump({
            "audit_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_stations": total_stations,
            "unique_urls": len(unique_urls),
            "counts": {
                "online": len(online_list),
                "redirects": len(redirect_list),
                "geoblocked": len(geoblocked_list),
                "offline": len(offline_list),
            },
            "geoblocked_stations": geoblocked_list,
            "offline_stations": offline_list,
            "redirect_stations": redirect_list,
        }, f, indent=2, ensure_ascii=False)

    print(f"\n[+] Rapport complet sauvegardé dans {report_file}")

if __name__ == "__main__":
    main()
