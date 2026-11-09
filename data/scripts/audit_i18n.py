#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TiMonde — Outil & Protocole Officiel d'Audit Internationalisation (i18n)
Conforme aux standards de la compétence i18n-clusters et aux exigences d'Argon / Céline.

Fonctionnalités :
1. Extraction chirurgicale des clés via AST Python (gérant les concaténations implicites).
2. Extraction des clés Rust (tr(...) et crate::i18n::tr(...)).
3. Contrôle strict du respect de la langue pivot anglaise (bannit les msgid en français).
4. Analyse d'écart avec le gabarit maître (po/timonde.pot).
5. Analyse de complétion de la traduction française officielle (po/fr.po).
6. Audit massif des 56 catalogues linguistiques (.po) avec statistiques et vérification msgfmt.
"""

import sys
import os
import ast
import re
import glob
import subprocess
from collections import Counter

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
PO_DIR = os.path.join(ROOT_DIR, "po")
POT_FILE = os.path.join(PO_DIR, "timonde.pot")

# Mots français caractéristiques pour traquer les fausses clés non-anglaises
FRENCH_STOPWORDS = {
    "le", "la", "les", "des", "du", "pour", "dans", "avec", "est", "une", "un",
    "votre", "vos", "enregistrer", "supprimer", "fermer", "annuler", "ajouter",
    "rechercher", "flux", "écoute", "arrêt", "pays", "station", "options"
}


def extract_python_keys(root_dir=ROOT_DIR):
    """Extrait fidèlement toutes les chaînes passées à _(...) via l'arbre syntaxique (AST)."""
    keys = {}
    scripts_dir = os.path.join(root_dir, "data/scripts")
    for root, _, files in os.walk(scripts_dir):
        for f in files:
            if f.endswith(".py") and not f.startswith("test_") and f != "audit_i18n.py":
                p = os.path.join(root, f)
                rel_path = os.path.relpath(p, root_dir)
                with open(p, "r", encoding="utf-8", errors="ignore") as fh:
                    try:
                        tree = ast.parse(fh.read(), p)
                    except SyntaxError:
                        continue
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        func_name = None
                        if isinstance(node.func, ast.Name):
                            func_name = node.func.id
                        elif isinstance(node.func, ast.Attribute):
                            func_name = node.func.attr
                        if func_name == "_":
                            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                                s = node.args[0].value
                                keys.setdefault(s, []).append(f"{rel_path}:{node.lineno}")
    return keys


def extract_rust_keys(root_dir=ROOT_DIR):
    """Extrait toutes les chaînes passées à tr(...) dans le code source Rust."""
    keys = {}
    src_dir = os.path.join(root_dir, "src")
    for root, _, files in os.walk(src_dir):
        for f in files:
            if f.endswith(".rs"):
                p = os.path.join(root, f)
                rel_path = os.path.relpath(p, root_dir)
                with open(p, "r", encoding="utf-8", errors="ignore") as fh:
                    for line_no, line in enumerate(fh, 1):
                        for m in re.finditer(r"\btr\(\s*\"((?:\\\"|[^\"])*)\"\s*\)", line):
                            s = m.group(1).replace('\\"', '"').replace("\\n", "\n")
                            keys.setdefault(s, []).append(f"{rel_path}:{line_no}")
    return keys


def parse_po_file(po_path):
    """Analyse fidèlement un fichier .po ou .pot en gérant les chaînes multi-lignes Gettext."""
    translations = {}
    if not os.path.exists(po_path):
        return translations
    with open(po_path, "r", encoding="utf-8", errors="ignore") as fh:
        lines = fh.readlines()

    current_msgid = None
    current_msgstr = None
    state = None

    for line in lines:
        line_s = line.strip()
        if not line_s or line_s.startswith("#"):
            if current_msgid is not None and current_msgstr is not None:
                translations[current_msgid] = current_msgstr
                current_msgid = None
                current_msgstr = None
                state = None
            continue

        if line_s.startswith("msgid "):
            raw = line_s[6:].strip()
            try:
                current_msgid = ast.literal_eval(raw)
            except Exception:
                current_msgid = raw.strip("\"")
            state = "msgid"
        elif line_s.startswith("msgstr "):
            raw = line_s[7:].strip()
            try:
                current_msgstr = ast.literal_eval(raw)
            except Exception:
                current_msgstr = raw.strip("\"")
            state = "msgstr"
        elif line_s.startswith("\"") and line_s.endswith("\""):
            try:
                chunk = ast.literal_eval(line_s)
            except Exception:
                chunk = line_s.strip("\"")
            if state == "msgid" and current_msgid is not None:
                current_msgid += chunk
            elif state == "msgstr" and current_msgstr is not None:
                current_msgstr += chunk

    if current_msgid is not None and current_msgstr is not None:
        translations[current_msgid] = current_msgstr
    return translations


def audit_translations():
    """Exécute l'audit complet du système de traduction et retourne un rapport structuré."""
    py_keys = extract_python_keys()
    rs_keys = extract_rust_keys()
    all_keys = {**py_keys}
    for k, locs in rs_keys.items():
        all_keys.setdefault(k, []).extend(locs)

    # 1. Contrôle de la langue pivot (détection de français non intentionnel)
    french_violations = []
    for k, locs in all_keys.items():
        words = set(re.findall(r"\b[a-zA-ZàâäéèêëîïôöùûüçÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ]+\b", k.lower()))
        common = words & FRENCH_STOPWORDS
        if len(common) >= 2 or any(w in words for w in ["enregistrer", "supprimer", "fermer", "annuler", "écoute", "arrêt", "flux", "rechercher"]):
            french_violations.append((k, locs, common))

    # 2. Alignement avec po/timonde.pot
    pot_translations = parse_po_file(POT_FILE)
    pot_keys = set(pot_translations.keys())
    code_keys = set(all_keys.keys())

    missing_in_pot = sorted(list(code_keys - pot_keys))
    obsolete_in_pot = sorted(list(pot_keys - code_keys))

    # 3. Alignement avec po/fr.po
    fr_file = os.path.join(PO_DIR, "fr.po")
    fr_translations = parse_po_file(fr_file)
    untranslated_fr = []
    for k in sorted(code_keys):
        val = fr_translations.get(k, "").strip()
        if not val:
            untranslated_fr.append((k, all_keys[k]))

    # 4. Audit de compilation des 56 catalogues .po
    po_stats = []
    for po in sorted(glob.glob(os.path.join(PO_DIR, "*.po"))):
        lang = os.path.basename(po).replace(".po", "")
        proc = subprocess.run(["msgfmt", "--statistics", "-c", "-o", "/dev/null", po], capture_output=True, text=True)
        out = proc.stderr.strip()
        tr = re.search(r"(\d+)\s+message[s]?\s+traduit|(\d+)\s+translated", out)
        un = re.search(r"(\d+)\s+message[s]?\s+non\s+traduit|(\d+)\s+untranslated", out)
        fz = re.search(r"(\d+)\s+traduction[s]?\s+approximative|(\d+)\s+fuzzy", out)
        nb_tr = int(tr.group(1) or tr.group(2)) if tr else 0
        nb_un = int(un.group(1) or un.group(2)) if un else 0
        nb_fz = int(fz.group(1) or fz.group(2)) if fz else 0
        po_stats.append({
            "lang": lang,
            "translated": nb_tr,
            "untranslated": nb_un,
            "fuzzy": nb_fz,
            "valid": proc.returncode == 0,
            "raw": out
        })

    return {
        "total_keys": len(all_keys),
        "python_keys": len(py_keys),
        "rust_keys": len(rs_keys),
        "pot_keys": len(pot_keys),
        "french_violations": french_violations,
        "missing_in_pot": missing_in_pot,
        "obsolete_in_pot": obsolete_in_pot,
        "untranslated_fr": untranslated_fr,
        "po_stats": po_stats,
    }


def main():
    report = audit_translations()
    print("=" * 70)
    print("AUDIT OFFICIEL DES TRADUCTIONS TIMONDE (CÉLINE / i18n-clusters)")
    print("=" * 70)
    print(f"Total clés réelles dans le code source : {report['total_keys']}")
    print(f"  • Python (data/scripts/)             : {report['python_keys']}")
    print(f"  • Rust (src/)                        : {report['rust_keys']}")
    print(f"Clés dans le gabarit maître (timonde.pot): {report['pot_keys']}")
    print("-" * 70)

    # 1. Pivot anglais
    if report["french_violations"]:
        print(f"[!] VIOLATION PIVOT ANGLAIS : {len(report['french_violations'])} clés en français !")
        for k, locs, w in report["french_violations"]:
            print(f"    - \"{k}\" ({locs[0]}) [mots: {w}]")
    else:
        print("[✓] PIVOT ANGLAIS : 100 % respecté (zéro chaîne française dans le code).")

    # 2. Gabarit .pot
    print(f"[i] Clés du code absentes de timonde.pot  : {len(report['missing_in_pot'])}")
    print(f"[i] Clés de timonde.pot obsolètes         : {len(report['obsolete_in_pot'])}")

    # 3. Français po/fr.po
    print("-" * 70)
    print(f"[*] Clés non traduites en Français (po/fr.po) : {len(report['untranslated_fr'])}")
    for k, locs in report["untranslated_fr"]:
        preview = k.replace("\n", " ")
        if len(preview) > 60:
            preview = preview[:57] + "..."
        print(f"    • \"{preview}\" -> {locs[0]}")

    # 4. Catalogues .po
    print("-" * 70)
    syntax_errors = [s for s in report["po_stats"] if not s["valid"]]
    if syntax_errors:
        print(f"[!] ERREURS DE SYNTAXE MSGFMT : {len(syntax_errors)} fichier(s) brisé(s) !")
        for s in syntax_errors:
            print(f"    - po/{s['lang']}.po : {s['raw']}")
    else:
        print(f"[✓] SYNTAXE MSGFMT : 100 % des {len(report['po_stats'])} catalogues compilent sans erreur.")

    print("=" * 70)
    if report["untranslated_fr"] or report["missing_in_pot"] or report["french_violations"]:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
