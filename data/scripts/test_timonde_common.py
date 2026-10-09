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

if __name__ == "__main__":
    unittest.main()
