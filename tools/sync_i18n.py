#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Outil officiel d'extraction et de maintenance Gettext pour TiMonde (56 langues).
Méthode i18n-clusters : extraction stricte, synchronisation via msgmerge et compilation .mo.
"""

import os
import sys
import re
import datetime
import subprocess

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
POT_FILE = os.path.join(REPO, "po", "timonde.pot")

def format_po_str(s):
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    lines = escaped.split("\n")
    if len(lines) == 1:
        return f'"{lines[0]}"'
    else:
        out = ['""']
        for i, line in enumerate(lines):
            suffix = '\\n"' if i < len(lines) - 1 else '"'
            out.append(f'"{line}{suffix}')
        return "\n".join(out)

def extract_all_keys():
    keys_map = {}
    
    # 1. Python files
    py_re = re.compile(r'(?<![a-zA-Z0-9_])_\(\s*([\'"])((?:\\.|(?!\1).)*)\1\s*\)', re.DOTALL)
    scripts_dir = os.path.join(REPO, "data", "scripts")
    for root, _, files in os.walk(scripts_dir):
        for f in sorted(files):
            if f.endswith(".py"):
                path = os.path.join(root, f)
                rel_path = os.path.relpath(path, REPO)
                with open(path, "r", encoding="utf-8") as fp:
                    content = fp.read()
                for m in py_re.finditer(content):
                    raw_val = m.group(2)
                    quote = m.group(1)
                    try:
                        val = eval(f"{quote}{raw_val}{quote}")
                    except Exception:
                        val = raw_val
                    line_no = content[:m.start()].count("\n") + 1
                    keys_map.setdefault(val, []).append((rel_path, line_no))

    # 2. Rust files
    rust_tr_re = re.compile(r'(?<![a-zA-Z0-9_])(?:crate::i18n::)?tr\(\s*"((?:\\.|[^"\\])*)"\s*\)')
    src_dir = os.path.join(REPO, "src")
    for root, _, files in os.walk(src_dir):
        for f in sorted(files):
            if f.endswith(".rs"):
                path = os.path.join(root, f)
                rel_path = os.path.relpath(path, REPO)
                with open(path, "r", encoding="utf-8") as fp:
                    content = fp.read()
                for m in rust_tr_re.finditer(content):
                    raw_val = m.group(1)
                    val = raw_val.replace(r"\n", "\n").replace(r"\"", "\"").replace(r"\\", "\\")
                    line_no = content[:m.start()].count("\n") + 1
                    keys_map.setdefault(val, []).append((rel_path, line_no))

    # Astronomical periods used via tr(raw_period)
    for period in ["Morning", "Daytime", "Evening", "Night"]:
        keys_map.setdefault(period, []).append(("src/timezone.rs", 521))

    return keys_map

def build_pot():
    keys = extract_all_keys()
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M%z")
    if not now_str.endswith(('+', '-')):
        now_str += "+0100"

    header = f"""# Translation template for TiMonde.
# Copyright (C) 2026 Ben Thibaud
# This file is distributed under the same license as the TiMonde package.
#
msgid ""
msgstr ""
"Project-Id-Version: TiMonde 2.0\\n"
"Report-Msgid-Bugs-To: \\n"
"POT-Creation-Date: {now_str}\\n"
"PO-Revision-Date: YEAR-MO-DA HO:MI+ZONE\\n"
"Last-Translator: TiMonde Translation Team\\n"
"Language-Team: LANGUAGE <LL@li.org>\\n"
"Language: \\n"
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Content-Transfer-Encoding: 8bit\\n"
"""
    body_blocks = []
    for k in sorted(keys.keys()):
        loc_comments = "\n".join(f"#: {f}:{l}" for f, l in keys[k])
        msgid_str = format_po_str(k)
        block = f"{loc_comments}\nmsgid {msgid_str}\nmsgstr \"\"\n"
        body_blocks.append(block)

    full_pot = header + "\n" + "\n".join(body_blocks)
    with open(POT_FILE, "w", encoding="utf-8") as f:
        f.write(full_pot)

    print(f"Generated {POT_FILE} with {len(keys)} entries.")
    return keys

if __name__ == "__main__":
    build_pot()
