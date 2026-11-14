#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Garde-fou d'architecture pour TiMonde (Antigravity Quality Standard).
Vérifie le respect absolu de la règle :
« Desktop Linux : Rust-First & Dumb UI Python »

Règles auditées :
1. Zéro réseau en Python : interdiction absolue de urllib, requests, http.client.
   Tout le réseau (streaming, HTTP, Radio-Browser, probing) est exclusivement réservé à Rust.
2. Zéro dialogue modal bloquant (anti-deadlock) : interdiction absolue de dlg.run().
   Tous les dialogues GTK3 doivent utiliser le modèle asynchrone connecté au signal 'response'.
"""

import sys
import os
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
DATA_SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "data", "scripts")

FORBIDDEN_IMPORTS = [
    (re.compile(r"^\s*(?:import|from)\s+(?:urllib|urllib\.request|urllib\.error|urllib\.parse)\b"), "urllib (Réseau en Python interdit - utiliser le binaire Rust 'timonde')"),
    (re.compile(r"^\s*(?:import|from)\s+requests\b"), "requests (Réseau en Python interdit - utiliser le binaire Rust 'timonde')"),
    (re.compile(r"^\s*(?:import|from)\s+http\.client\b"), "http.client (Réseau en Python interdit - utiliser le binaire Rust 'timonde')"),
    (re.compile(r"^\s*(?:import|from)\s+(?:xml\.etree|xml\.etree\.ElementTree)\b"), "xml.etree (Parsing XML en Python interdit - utiliser le binaire Rust 'timonde')"),
]

FORBIDDEN_PATTERNS = [
    (re.compile(r"\b(?!subprocess\b)[a-zA-Z0-9_]+\.run\(\)"), "Appel bloquant .run() interdit sur dialogue/objet GTK (utiliser connect('response', ...) + show_all())"),
]

# Scripts exemptés de l'interdiction de dialogues (ex: scripts utilitaires d'installation standalone)
EXEMPT_FILES = {
    "gnome_tray_helper.py", # Assistant autonome pré-démarrage quand GTK loop n'est pas encore actif
}

def check_file(path: str) -> list[str]:
    fname = os.path.basename(path)
    errors = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for idx, line in enumerate(f, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue

            for pattern, reason in FORBIDDEN_IMPORTS:
                if pattern.search(line):
                    errors.append(f"{fname}:{idx}: [IMPORT INTERDIT] {reason}")

            if fname not in EXEMPT_FILES:
                for pattern, reason in FORBIDDEN_PATTERNS:
                    if pattern.search(line):
                        errors.append(f"{fname}:{idx}: [PATTERN INTERDIT] {reason}")

    return errors

def main():
    print("=======================================================")
    print("Contrôle d'Architecture TiMonde : Règle d'or Rust-First")
    print("=======================================================")

    if not os.path.isdir(DATA_SCRIPTS_DIR):
        print(f"Erreur : répertoire {DATA_SCRIPTS_DIR} introuvable.")
        sys.exit(1)

    py_files = sorted([
        os.path.join(DATA_SCRIPTS_DIR, f)
        for f in os.listdir(DATA_SCRIPTS_DIR)
        if f.endswith(".py")
    ])

    all_errors = []
    for f in py_files:
        errs = check_file(f)
        all_errors.extend(errs)

    if all_errors:
        print(f"\nÉCHEC : {len(all_errors)} violation(s) d'architecture détectée(s) :")
        for e in all_errors:
            print(f"  ❌ {e}")
        print("\nConsultez docs/ARCHITECTURE.md pour les directives de séparation Rust / Python.")
        sys.exit(1)

    print(f"\nSUCCÈS : {len(py_files)} scripts Python audités. Zéro réseau clandestin, zéro dialogue bloquant.")
    print("Le socle Python respecte scrupuleusement le rôle de Dumb UI.")
    sys.exit(0)

if __name__ == "__main__":
    main()
