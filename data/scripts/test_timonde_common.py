#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests unitaires automatisés pour timonde_common.py
Vérifie :
1. Nettoyage et résilience des URLs de flux audio (clean_stream_url)
2. Détection et filtrage des emojis régionaux (strip_unsupported_emojis)
3. Tolérance du parseur XML aux entités non-échappées (safe_parse_xml)
4. Normalisation stricte de la convention Linux des groupes avec slashes (normalize_group_path)
5. Intégrité du catalogue des pays et des fuseaux horaires
"""

import unittest
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from timonde_common import (
    clean_stream_url,
    strip_unsupported_emojis,
    safe_parse_xml,
    normalize_group_path,
    infer_timezone,
    COUNTRIES_DB,
    COUNTRIES_REGISTRY,
    FRANCE_TIMEZONES,
    WORLD_TIMEZONES,
)

class TestTiMondeCommon(unittest.TestCase):

    def test_clean_stream_url(self):
        # Protocoles en double ou mal formés
        self.assertEqual(clean_stream_url("httpshttps://example.com/stream"), "https://example.com/stream")
        self.assertEqual(clean_stream_url("http ://radio.fr/live"), "http://radio.fr/live")
        self.assertEqual(clean_stream_url("//cdn.example.org/audio.mp3"), "https://cdn.example.org/audio.mp3")
        self.assertEqual(clean_stream_url("  https://ok.com/live  "), "https://ok.com/live")
        self.assertEqual(clean_stream_url(""), "")

    def test_strip_unsupported_emojis(self):
        text = "🇫🇷 France Musique"
        self.assertEqual(strip_unsupported_emojis(text), "France Musique")
        self.assertEqual(strip_unsupported_emojis("Simple Text"), "Simple Text")

    def test_normalize_group_path(self):
        # Cas racine
        self.assertEqual(normalize_group_path("[ / ] (Racine — Sans groupe)", return_root_literal=True), "root")
        self.assertEqual(normalize_group_path("/", return_root_literal=True), "root")
        self.assertEqual(normalize_group_path("", return_root_literal=True), "root")
        self.assertEqual(normalize_group_path("/", return_root_literal=False), "")

        # Sous-groupes avec slashes convention Linux
        self.assertEqual(normalize_group_path("/France/Bretagne/"), "France/Bretagne")
        self.assertEqual(normalize_group_path("France/Bretagne"), "France/Bretagne")
        self.assertEqual(normalize_group_path("///Belgique/Bruxelles///"), "Belgique/Bruxelles")
        self.assertEqual(normalize_group_path("  Jazz & Blues  "), "Jazz & Blues")

    def test_safe_parse_xml(self):
        # XML avec & non échappé (cas classique des titres radio comme "Rock & Roll")
        xml_content = """<?xml version="1.0" encoding="utf-8"?>
        <station name="Rock & Roll Radio" url="http://test.com/stream" />"""
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as f:
            f.write(xml_content)
            temp_path = f.name

        try:
            root = safe_parse_xml(temp_path)
            self.assertIsNotNone(root)
            self.assertEqual(root.attrib.get("name"), "Rock & Roll Radio")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_countries_and_timezones(self):
        self.assertTrue(len(COUNTRIES_DB) >= 70)
        self.assertTrue(len(COUNTRIES_REGISTRY) >= 200)
        self.assertIn("FR", COUNTRIES_REGISTRY)
        self.assertIn("GP", COUNTRIES_REGISTRY)  # Guadeloupe
        self.assertIn("US", COUNTRIES_REGISTRY)

        # Vérification fuseaux France (Métropole + DOM-TOM)
        fr_tz_ids = [tz[0] for tz in FRANCE_TIMEZONES]
        self.assertIn("Europe/Paris", fr_tz_ids)
        self.assertIn("America/Guadeloupe", fr_tz_ids)
        self.assertIn("Indian/Reunion", fr_tz_ids)
        self.assertIn("Pacific/Tahiti", fr_tz_ids)

    def test_infer_timezone(self):
        # France Métropole vs Outre-mer
        self.assertEqual(infer_timezone("FR", "France Inter", "Généraliste"), "Europe/Paris")
        self.assertEqual(infer_timezone("FR", "RCI Guadeloupe", "Antilles"), "America/Guadeloupe")
        self.assertEqual(infer_timezone("FR", "Radio Réunion 1ère", "Océan Indien"), "Indian/Reunion")
        self.assertEqual(infer_timezone("GP", "Radio Guadeloupe", ""), "America/Guadeloupe")

        # Royaume-Uni & Outre-mer
        self.assertEqual(infer_timezone("GB", "BBC Radio 1", "Londres"), "Europe/London")
        self.assertEqual(infer_timezone("GB", "BFBS Gibraltar", "Europe"), "Europe/Gibraltar")
        self.assertEqual(infer_timezone("BM", "Bermuda FM", ""), "Atlantic/Bermuda")

        # Canada
        self.assertEqual(infer_timezone("CA", "Vancouver Rock", "Colombie-Britannique"), "America/Vancouver")
        self.assertEqual(infer_timezone("CA", "Radio-Canada Montréal", "Québec"), "America/Toronto")

        # États-Unis
        self.assertEqual(infer_timezone("US", "KCRW Los Angeles", "Californie"), "America/Los_Angeles")
        self.assertEqual(infer_timezone("US", "WNYC New York", "News"), "America/New_York")

        # Fallbacks universels par pays (Algérie, Colombie)
        self.assertEqual(infer_timezone("DZ", "Chaine 1", ""), "Africa/Algiers")
        self.assertEqual(infer_timezone("CO", "Caracol Radio", ""), "America/Bogota")

    def test_multilingual_55_countries_and_language_aliases(self):
        from timonde_world_data import resolve_country_code, resolve_language_api_key
        country_cases = [
            ("Deutschland", "DE"), ("Germany", "DE"), ("Allemagne", "DE"), ("Alemania", "DE"),
            ("Germania", "DE"), ("Duitsland", "DE"), ("Niemcy", "DE"), ("Германия", "DE"),
            ("ألمانيا", "DE"), ("ドイツ", "DE"), ("德国", "DE"), ("德國", "DE"), ("Saksa", "DE"), ("Tyskland", "DE"),
            ("Suisse", "CH"), ("Schweiz", "CH"), ("Switzerland", "CH"), ("Svizzera", "CH"), ("Suiza", "CH"),
            ("España", "ES"), ("Spain", "ES"), ("Espagne", "ES"), ("Spanien", "ES"),
            ("United Kingdom", "GB"), ("Royaume-Uni", "GB"), ("UK", "GB"), ("England", "GB"),
            ("United States", "US"), ("USA", "US"), ("États-Unis", "US"), ("アメリカ合衆国", "US"), ("美国", "US"),
            ("Россия", "RU"), ("Russia", "RU"), ("Russie", "RU"),
            ("日本", "JP"), ("Japan", "JP"), ("Japon", "JP"),
            ("Ελλάδα", "GR"), ("Greece", "GR"), ("Grèce", "GR"),
        ]
        for query, expected in country_cases:
            self.assertEqual(resolve_country_code(query), expected, f"Échec pour {query}")

        lang_cases = [
            ("english", "english"), ("Anglais", "english"), ("English", "english"),
            ("engilsh", "english"), ("american english", "english"), ("english uk", "english"),
            ("American english (american english)", "american english"),
            ("deutch", "german"), ("Deutsch", "german"),
            ("espanish", "spanish"), ("francaise", "french"),
        ]
        for query, expected in lang_cases:
            self.assertEqual(resolve_language_api_key(query), expected, f"Échec langue pour {query}")

    def test_bookmarks_tree_root_and_nested_groups(self):
        from timonde_settings import load_bookmarks_tree, save_bookmarks_tree
        xml_sample = """<?xml version="1.0" encoding="utf-8"?>
<bookmarks>
    <bookmark name="Root Radio" url="https://example.com/root.mp3" country="FR" timezone="Europe/Paris"/>
    <group name="France">
        <group name="Bretagne">
            <bookmark name="Radio Armorique" url="https://example.com/bzh.mp3" country="FR" timezone="Europe/Paris"/>
        </group>
    </group>
</bookmarks>
"""
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as f:
            f.write(xml_sample)
            temp_path = f.name

        try:
            tree = load_bookmarks_tree(temp_path)
            self.assertEqual(len(tree), 2)
            self.assertEqual(tree[0]["name"], "[ / ] (Racine — Sans groupe)")
            self.assertEqual(tree[0]["stations"][0]["name"], "Root Radio")
            self.assertEqual(tree[1]["name"], "France/Bretagne")
            self.assertEqual(tree[1]["stations"][0]["name"], "Radio Armorique")

            save_bookmarks_tree(temp_path, tree)
            reloaded = load_bookmarks_tree(temp_path)
            self.assertEqual(len(reloaded), 2)
            self.assertEqual(reloaded[0]["stations"][0]["name"], "Root Radio")
            self.assertEqual(reloaded[0]["stations"][0]["timezone"], "Europe/Paris")
            self.assertEqual(reloaded[1]["name"], "France/Bretagne")
            self.assertEqual(reloaded[1]["stations"][0]["name"], "Radio Armorique")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

if __name__ == "__main__":
    unittest.main()
